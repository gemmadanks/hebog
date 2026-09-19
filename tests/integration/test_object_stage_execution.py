# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Per-parent component topology, against the whole-plane deblender."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import TypeVar, cast

import numpy as np
import numpy.typing as npt
import pytest
from distributed import Client
from scipy.ndimage import label as ndimage_label

from hebog.algorithms.component_topology import deblend_component_topology
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import CompactDeblendConfig
from hebog.data_models.partitioning import ImageBounds, PartitionManifest
from hebog.executors import DaskExecutor, SerialExecutor, TaskRequirement
from hebog.io.zarr import ZarrProductSink
from hebog.science.configuration import source_finder_configs
from hebog.stages.objects import (
    ComponentTopologyStageConfig,
    ComponentTopologyStageResult,
    _ParentBatch,
    _TileBatch,
    _union_bounds,
    component_topology_product_names,
    run_component_topology_stage,
)

pytestmark = pytest.mark.integration

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SHAPE_YX = (48, 96)
_DETECTION_SIGMA = 5.0


class _ReverseCompletionExecutor(SerialExecutor):
    """Return completed task records in reverse order."""

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Evaluate canonically but expose reverse completion order."""
        return list(
            reversed(
                super().map_batches(function, batches, requirement=requirement)
            )
        )


class _DropNthMapExecutor(SerialExecutor):
    """Complete every round but one, to prove each fails closed."""

    def __init__(self, dropped_round: int) -> None:
        """Count maps so one chosen round can return nothing."""
        super().__init__()
        self._dropped_round = dropped_round
        self._call_count = 0

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Run every round except the chosen one."""
        self._call_count += 1
        if self._call_count == self._dropped_round:
            return []
        return super().map_batches(function, batches, requirement=requirement)


def _labelled(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.int32]:
    """Return eight-connected labels of one analytic mask."""
    labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage_label(mask, structure=np.ones((3, 3), dtype=np.int8)),
    )
    return labels


def _planes() -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.int32],
    npt.NDArray[np.int32],
    npt.NDArray[np.bool_],
]:
    """Return three parents: a blend, a single peak and a faint island.

    The blended parent has two well-separated peaks, so the reviewed
    watershed splits it and its measurement support has to be partitioned
    between the two new seeds. It spans several tile cores, which is what
    makes the per-parent round necessary.
    """
    yy, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    signal = np.zeros(_SHAPE_YX, dtype=np.float64)
    for amplitude, centre_y, centre_x in (
        (12.0, 20, 30),
        (11.0, 20, 37),
        (9.0, 36, 70),
        (5.5, 8, 80),
    ):
        signal += amplitude * np.exp(
            -((yy - centre_y) ** 2 + (xx - centre_x) ** 2) / 8.0
        )
    direct = np.zeros(_SHAPE_YX, dtype=np.int32)
    measurement = np.zeros(_SHAPE_YX, dtype=np.int32)
    labelled = _labelled(signal >= 3.0)
    for index, label_value in enumerate(
        sorted({int(value) for value in np.unique(labelled) if value}),
        start=1,
    ):
        direct[labelled == label_value] = index
    support_labels = _labelled(signal >= 2.0)
    for label_value in np.unique(support_labels):
        if label_value <= 0:
            continue
        region = support_labels == label_value
        owners = {int(value) for value in np.unique(direct[region]) if value}
        if len(owners) == 1:
            measurement[region] = owners.pop()
    measurement[direct > 0] = direct[direct > 0]
    return signal, direct, measurement, np.ones(_SHAPE_YX, dtype=np.bool_)


def _publish(
    root: Path,
    products: tuple[tuple[str, npt.NDArray[np.generic], str], ...],
    *,
    generation_id: str,
) -> ZarrProductSink:
    """Publish one generation of analytic planes over 16-pixel cores."""
    manifest = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(16, 16),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(root, manifest, generation_id=generation_id)
    for product_name, _, dtype in products:
        sink.initialize_product(
            product_name=product_name,
            dtype=np.dtype(dtype),
        )
    sink.publish_generation(
        product_names=tuple(name for name, _, _ in products),
        chunks=[
            sink.write_chunk(
                product_name=product_name,
                tile=tile,
                values=np.asarray(
                    values[
                        tile.core_bounds.y_start : tile.core_bounds.y_stop,
                        tile.core_bounds.x_start : tile.core_bounds.x_stop,
                    ]
                ),
            )
            for tile in manifest.tiles
            for product_name, values, _ in products
        ],
    )
    return sink


def _sources(root: Path) -> tuple[ZarrProductSink, ZarrProductSink]:
    """Publish the support and detection generations this pass reads."""
    signal, direct, measurement, valid = _planes()
    return (
        _publish(
            root / "support.zarr",
            (
                ("component-labels", direct, "<i4"),
                ("measurement-labels", measurement, "<i4"),
            ),
            generation_id="support-fixture",
        ),
        _publish(
            root / "detection.zarr",
            (
                ("direct-snr", signal, "<f8"),
                ("valid-pixels", valid, "bool"),
            ),
            generation_id="detection-fixture",
        ),
    )


def _deblend_config() -> CompactDeblendConfig:
    """Return the reviewed compact deblending policy the public path uses."""
    return replace(
        source_finder_configs()[1],
        minimum_peak_signal_to_noise=float(
            np.nextafter(_DETECTION_SIGMA, -np.inf)
        ),
    )


def _manifest(core: int) -> PartitionManifest:
    """Plan one core-only component partition."""
    return plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(core, core),
        halo_yx=(0, 0),
    )


def _config(
    *,
    maximum_tiles_per_batch: int = 2,
    maximum_batch_read_pixels: int = 8192,
) -> ComponentTopologyStageConfig:
    """Return the reviewed policy with bounded task limits."""
    return ComponentTopologyStageConfig(
        deblend=_deblend_config(),
        maximum_tiles_per_batch=maximum_tiles_per_batch,
        maximum_batch_read_pixels=maximum_batch_read_pixels,
    )


def _run(
    root: Path,
    *,
    core: int = 16,
    executor: object | None = None,
    config: ComponentTopologyStageConfig | None = None,
) -> tuple[ComponentTopologyStageResult, ZarrProductSink]:
    """Execute one isolated component-topology variant."""
    root.mkdir(parents=True, exist_ok=True)
    support_source, detection_source = _sources(root)
    manifest = _manifest(core)
    sink = ZarrProductSink(
        root / "components.zarr",
        manifest,
        generation_id="components",
    )
    result = run_component_topology_stage(
        support_source,
        detection_source,
        manifest,
        config=_config() if config is None else config,
        executor=(  # type: ignore[arg-type]
            SerialExecutor() if executor is None else executor
        ),
        sink=sink,
    )
    return result, sink


def _published(
    sink: ZarrProductSink,
) -> dict[str, npt.NDArray[np.int32]]:
    """Read both published component planes over the whole image."""
    bounds = ImageBounds(0, _SHAPE_YX[0], 0, _SHAPE_YX[1])
    return {
        name: np.asarray(
            sink.read_completed_window(name, bounds),
            dtype=np.int32,
        )
        for name in component_topology_product_names()
    }


def _whole_plane_topology() -> dict[str, npt.NDArray[np.int32]]:
    """Deblend every parent over complete planes, as the oracle."""
    signal, direct, measurement, valid = _planes()
    topology = deblend_component_topology(
        np.where(valid, signal, np.nan),
        direct,
        measurement,
        valid,
        _deblend_config(),
    )
    return {
        "component-direct-labels": np.asarray(
            topology.direct_component_labels,
            dtype=np.int32,
        ),
        "component-measurement-labels": np.asarray(
            topology.measurement_component_labels,
            dtype=np.int32,
        ),
    }


def test_published_components_match_the_whole_plane_deblender(
    tmp_path: Path,
) -> None:
    """One parent per task reproduces the whole-plane component topology."""
    result, sink = _run(tmp_path / "run")

    published = _published(sink)

    expected = _whole_plane_topology()
    for name, values in expected.items():
        np.testing.assert_array_equal(published[name], values, name)
    assert result.deblended_parent_count >= 1
    assert result.component_count > result.parent_count


def test_component_topology_is_partition_and_executor_invariant(
    tmp_path: Path,
) -> None:
    """One published generation survives geometry, batching and workers."""
    expected = _published(_run(tmp_path / "reference", core=64)[1])
    variants: list[tuple[str, int, object, ComponentTopologyStageConfig]] = [
        ("cores-16", 16, SerialExecutor(), _config()),
        ("cores-24", 24, SerialExecutor(), _config(maximum_tiles_per_batch=1)),
        (
            "one-parent-per-read",
            16,
            SerialExecutor(),
            _config(maximum_batch_read_pixels=1),
        ),
        ("reverse", 16, _ReverseCompletionExecutor(), _config()),
    ]
    for name, core, executor, config in variants:
        _, sink = _run(
            tmp_path / name,
            core=core,
            executor=executor,
            config=config,
        )
        published = _published(sink)
        for product_name, values in expected.items():
            np.testing.assert_array_equal(
                published[product_name],
                values,
                f"{name}:{product_name}",
            )

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        _, sink = _run(tmp_path / "dask", executor=DaskExecutor(client))
    published = _published(sink)
    for product_name, values in expected.items():
        np.testing.assert_array_equal(published[product_name], values)


def test_component_topology_defers_a_parent_above_the_compact_bound(
    tmp_path: Path,
) -> None:
    """An oversized parent stays one explicit component, never truncated."""
    config = ComponentTopologyStageConfig(
        deblend=replace(
            _deblend_config(),
            maximum_compact_island_pixels=4,
        ),
        maximum_tiles_per_batch=2,
        maximum_batch_read_pixels=8192,
    )

    result, sink = _run(tmp_path / "run", config=config)

    published = _published(sink)
    assert result.deferred_parent_count == result.parent_count
    assert result.component_count == result.parent_count
    np.testing.assert_array_equal(
        published["component-direct-labels"] > 0,
        _planes()[1] > 0,
    )


def test_component_topology_publishes_the_canonical_product_set(
    tmp_path: Path,
) -> None:
    """The generation carries exactly one chunk per product and core."""
    manifest = _manifest(16)

    result, _ = _run(tmp_path / "run")

    assert set(result.generation.product_names) == set(
        component_topology_product_names()
    )
    assert len(result.generation.chunks) == len(
        component_topology_product_names()
    ) * len(manifest.tiles)
    assert result.executor_task_count > 0
    assert result.maximum_graph_width > 0
    assert result.maximum_parent_read_pixels > 0
    assert result.parent_batch_count > 0


@pytest.mark.parametrize(
    "dropped_round, message",
    [
        (1, "no parent extent results"),
        (2, "no component deblend results"),
        (3, "no component publication results"),
    ],
)
def test_every_round_fails_closed_on_a_silent_executor(
    tmp_path: Path,
    dropped_round: int,
    message: str,
) -> None:
    """A dropped result is never published as a complete generation."""
    with pytest.raises(ValueError, match=message):
        _run(
            tmp_path / f"round-{dropped_round}",
            executor=_DropNthMapExecutor(dropped_round),
        )


def test_component_topology_rejects_a_haloed_manifest(tmp_path: Path) -> None:
    """The component write owns cores and reads no halo."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    support_source, detection_source = _sources(tmp_path)
    manifest = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(16, 16),
        halo_yx=(2, 2),
    )

    with pytest.raises(ValueError, match="cores without a halo"):
        run_component_topology_stage(
            support_source,
            detection_source,
            manifest,
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "components.zarr",
                manifest,
                generation_id="components",
            ),
        )


def test_component_topology_forbids_empty_executor_work_records() -> None:
    """An empty batch is a scheduling defect, not a task to submit."""
    with pytest.raises(ValueError, match="parent batch must not be empty"):
        _ParentBatch(parents=(), read_bounds=ImageBounds(0, 1, 0, 1))
    with pytest.raises(ValueError, match="tile batch must not be empty"):
        _TileBatch(requests=())


@pytest.mark.parametrize(
    "maximum_tiles_per_batch, maximum_batch_read_pixels, message",
    [
        (0, 8192, "maximum_tiles_per_batch"),
        (2, 0, "maximum_batch_read_pixels"),
    ],
)
def test_component_topology_rejects_invalid_configuration(
    maximum_tiles_per_batch: int,
    maximum_batch_read_pixels: int,
    message: str,
) -> None:
    """Configuration is validated before any product is initialized."""
    with pytest.raises(ValueError, match=message):
        ComponentTopologyStageConfig(
            deblend=_deblend_config(),
            maximum_tiles_per_batch=maximum_tiles_per_batch,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
        )


def test_component_topology_publishes_an_image_with_no_parent(
    tmp_path: Path,
) -> None:
    """An image with no admitted island publishes a complete core set."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    signal, _, _, valid = _planes()
    empty = np.zeros(_SHAPE_YX, dtype=np.int32)
    support_source = _publish(
        tmp_path / "support.zarr",
        (
            ("component-labels", empty, "<i4"),
            ("measurement-labels", empty, "<i4"),
        ),
        generation_id="support-fixture",
    )
    detection_source = _publish(
        tmp_path / "detection.zarr",
        (("direct-snr", signal, "<f8"), ("valid-pixels", valid, "bool")),
        generation_id="detection-fixture",
    )
    manifest = _manifest(16)
    sink = ZarrProductSink(
        tmp_path / "components.zarr",
        manifest,
        generation_id="components",
    )

    result = run_component_topology_stage(
        support_source,
        detection_source,
        manifest,
        config=_config(),
        executor=SerialExecutor(),
        sink=sink,
    )

    assert result.parent_count == 0
    assert result.component_count == 0
    assert result.parent_batch_count == 0
    assert result.maximum_parent_read_pixels == 0
    for values in _published(sink).values():
        assert not np.any(values)


def test_component_topology_requires_direct_support_for_every_parent(
    tmp_path: Path,
) -> None:
    """A measurement parent without direct support cannot be deblended."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    signal, direct, measurement, valid = _planes()
    orphaned = measurement.copy()
    orphaned[44:47, 4:7] = int(direct.max()) + 1
    support_source = _publish(
        tmp_path / "support.zarr",
        (
            ("component-labels", direct, "<i4"),
            ("measurement-labels", orphaned, "<i4"),
        ),
        generation_id="support-fixture",
    )
    detection_source = _publish(
        tmp_path / "detection.zarr",
        (("direct-snr", signal, "<f8"), ("valid-pixels", valid, "bool")),
        generation_id="detection-fixture",
    )
    manifest = _manifest(16)

    with pytest.raises(ValueError, match="must own direct support"):
        run_component_topology_stage(
            support_source,
            detection_source,
            manifest,
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "components.zarr",
                manifest,
                generation_id="components",
            ),
        )


def test_component_topology_requires_a_matching_sink_and_generations(
    tmp_path: Path,
) -> None:
    """Identities are checked before any product is initialized."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    support_source, detection_source = _sources(tmp_path)
    manifest = _manifest(16)
    other_shape = plan_image_partitions(
        image_shape_yx=(32, 32),
        tile_core_shape_yx=(16, 16),
        halo_yx=(0, 0),
    )
    incomplete = _publish(
        tmp_path / "incomplete.zarr",
        (("direct-snr", _planes()[0], "<f8"),),
        generation_id="incomplete",
    )

    with pytest.raises(ValueError, match="must use the stage manifest"):
        run_component_topology_stage(
            support_source,
            detection_source,
            manifest,
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "mismatched.zarr",
                _manifest(32),
                generation_id="mismatched",
            ),
        )
    with pytest.raises(ValueError, match="match the component image shape"):
        run_component_topology_stage(
            support_source,
            detection_source,
            other_shape,
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "other.zarr",
                other_shape,
                generation_id="other",
            ),
        )
    with pytest.raises(ValueError, match="every component plane read"):
        run_component_topology_stage(
            support_source,
            incomplete,
            manifest,
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "incomplete-components.zarr",
                manifest,
                generation_id="components",
            ),
        )


def test_parent_extents_merge_in_either_order() -> None:
    """A core that sees only one plane's support still contributes bounds."""
    first = ImageBounds(4, 8, 4, 8)
    second = ImageBounds(6, 12, 2, 5)

    assert _union_bounds(None, first) == first
    assert _union_bounds(first, None) == first
    assert _union_bounds(first, second) == ImageBounds(4, 12, 2, 8)
    assert _union_bounds(second, first) == ImageBounds(4, 12, 2, 8)
    assert _union_bounds(None, None) is None
