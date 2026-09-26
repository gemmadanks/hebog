# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Source labels and owned persistent support, against the whole plane."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from math import ceil
from pathlib import Path
from typing import TypeVar, cast

import numpy as np
import numpy.typing as npt
import pytest
from conftest import RecordingExecutor, carried_array_bytes
from distributed import Client
from scipy.ndimage import label as ndimage_label

from hebog.algorithms.extended_measurement import (
    assign_persistent_source_support,
)
from hebog.algorithms.labelling import TileBoundaryLabels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.reconciliation import TileLabelMapping
from hebog.data_models.partitioning import ImageBounds, PartitionManifest
from hebog.executors import DaskExecutor, SerialExecutor, TaskRequirement
from hebog.io.zarr import ZarrProductSink
from hebog.stages.batching import HeldObjects, read_pixels
from hebog.stages.sources import (
    SourceLabelStageConfig,
    SourceSupportStageConfig,
    SourceSupportStageResult,
    _assign_wide_components,
    _AssignBatch,
    _LabelWriteBatch,
    _OwnerScanBatch,
    _support_component,
    _SupportComponent,
    _SupportPixels,
    _SupportScanBatch,
    _SupportWriteBatch,
    _WideSupportBatch,
    _WideSupportResult,
    run_source_label_stage,
    run_source_support_stage,
    source_label_product_names,
    source_support_product_names,
)

pytestmark = pytest.mark.integration

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SHAPE_YX = (80, 112)


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
        "tuple[npt.NDArray[np.int32], int]",
        ndimage_label(mask, structure=np.ones((3, 3), dtype=np.int8)),
    )
    return labels


def _planes() -> tuple[
    npt.NDArray[np.int32],
    npt.NDArray[np.bool_],
    npt.NDArray[np.bool_],
    npt.NDArray[np.bool_],
]:
    """Return the owner labels, validity and the two persistent supports.

    Two owners sit inside one broad halo, so their support is one connected
    component that spans several cores and has to be divided between them by
    distance. A third owner has a halo of its own, and a fourth has none.
    """
    yy, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    signal = (
        12.0 * np.exp(-0.5 * (((xx - 34) / 2.0) ** 2 + ((yy - 40) / 2.0) ** 2))
        + 12.0
        * np.exp(-0.5 * (((xx - 54) / 2.0) ** 2 + ((yy - 40) / 2.0) ** 2))
        + 5.0
        * np.exp(-0.5 * (((xx - 44) / 13.0) ** 2 + ((yy - 40) / 7.0) ** 2))
        + 11.0
        * np.exp(-0.5 * (((xx - 94) / 2.0) ** 2 + ((yy - 18) / 2.0) ** 2))
        + 4.0
        * np.exp(-0.5 * (((xx - 94) / 6.0) ** 2 + ((yy - 18) / 5.0) ** 2))
        + 10.0
        * np.exp(-0.5 * (((xx - 16) / 2.0) ** 2 + ((yy - 70) / 2.0) ** 2))
    )
    owners = np.asarray(_labelled(signal >= 8.0), dtype=np.int32)
    valid = np.ones(_SHAPE_YX, dtype=np.bool_)
    scale_support = (signal >= 2.0) & (signal < 6.0)
    measurement_support = (signal >= 6.0) & (signal < 8.0)
    return owners, valid, scale_support, measurement_support


def _source_by_owner() -> dict[int, int]:
    """Join the first two owners into one source and keep the rest apart."""
    owners = sorted(
        int(value) for value in np.unique(_planes()[0]) if int(value) > 0
    )
    assert len(owners) >= 3
    return {
        owners[0]: 1,
        owners[1]: 1,
        **{owner: index for index, owner in enumerate(owners[2:], start=2)},
    }


def _manifest(core: int) -> PartitionManifest:
    """Plan one core-only partition of the fixture image."""
    return plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(core, core),
        halo_yx=(0, 0),
    )


def _publish(
    root: Path,
    products: tuple[tuple[str, npt.NDArray[np.generic], str], ...],
    *,
    generation_id: str,
) -> ZarrProductSink:
    """Publish one generation of analytic planes over 16-pixel cores."""
    manifest = _manifest(16)
    sink = ZarrProductSink(root, manifest, generation_id=generation_id)
    for product_name, _, dtype in products:
        sink.initialize_product(
            product_name=product_name, dtype=np.dtype(dtype)
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


def _sources(root: Path) -> tuple[ZarrProductSink, ...]:
    """Publish every generation the source rounds read."""
    root.mkdir(parents=True, exist_ok=True)
    owners, valid, scale_support, measurement_support = _planes()
    return (
        _publish(
            root / "components.zarr",
            (("component-measurement-labels", owners, "<i4"),),
            generation_id="component-fixture",
        ),
        _publish(
            root / "detection.zarr",
            (("valid-pixels", valid, "bool"),),
            generation_id="detection-fixture",
        ),
        _publish(
            root / "hierarchy.zarr",
            (("persistent-scale-support", scale_support, "bool"),),
            generation_id="hierarchy-fixture",
        ),
        _publish(
            root / "fits.zarr",
            (("measurement-support", measurement_support, "bool"),),
            generation_id="fits-fixture",
        ),
    )


def _run(
    root: Path,
    *,
    core: int = 16,
    executor: object | None = None,
    **overrides: int,
) -> tuple[ZarrProductSink, ZarrProductSink]:
    """Publish the source labels and the support they own, in isolation."""
    label_sink, support_sink, _ = _run_support(
        root, core=core, executor=executor, **overrides
    )
    return label_sink, support_sink


def _run_support(
    root: Path,
    *,
    core: int = 16,
    executor: object | None = None,
    **overrides: int,
) -> tuple[ZarrProductSink, ZarrProductSink, SourceSupportStageResult]:
    """Publish both source planes, and keep the support round's evidence."""
    component, detection, hierarchy, fits = _sources(root)
    resolved = SerialExecutor() if executor is None else executor
    manifest = _manifest(core)
    label_sink = ZarrProductSink(
        root / "labels.zarr", manifest, generation_id="labels"
    )
    run_source_label_stage(
        component,
        manifest,
        config=SourceLabelStageConfig(maximum_tiles_per_batch=2),
        source_by_owner=_source_by_owner(),
        executor=resolved,  # type: ignore[arg-type]
        sink=label_sink,
    )
    support_sink = ZarrProductSink(
        root / "support.zarr", manifest, generation_id="support"
    )
    result = run_source_support_stage(
        label_sink,
        detection,
        hierarchy,
        fits,
        manifest,
        config=SourceSupportStageConfig(
            **{
                "maximum_tiles_per_batch": 2,
                "maximum_objects_per_batch": 2,
                "maximum_batch_read_pixels": 65536,
                **overrides,
            }
        ),
        executor=resolved,  # type: ignore[arg-type]
        sink=support_sink,
    )
    return label_sink, support_sink, result


def _window(sink: ZarrProductSink, product_name: str) -> npt.NDArray[np.int32]:
    """Read one published plane over the whole fixture image."""
    return np.asarray(
        sink.read_completed_window(
            product_name, ImageBounds(0, _SHAPE_YX[0], 0, _SHAPE_YX[1])
        ),
        dtype=np.int32,
    )


def _whole_plane() -> tuple[npt.NDArray[np.int32], npt.NDArray[np.int32]]:
    """Build the same planes over complete arrays, as the serial oracle."""
    owners, valid, scale_support, measurement_support = _planes()
    source_labels = np.zeros(_SHAPE_YX, dtype=np.int32)
    for owner, source_label in _source_by_owner().items():
        source_labels[owners == owner] = source_label
    return source_labels, assign_persistent_source_support(
        source_labels,
        scale_support | measurement_support,
        valid,
    )


def test_published_source_planes_match_the_whole_plane_assignment(
    tmp_path: Path,
) -> None:
    """Per-core and per-component rounds reproduce the whole-plane answer."""
    expected_labels, expected_support = _whole_plane()

    label_sink, support_sink = _run(tmp_path / "run")

    assert (expected_support > 0).sum() > (expected_labels > 0).sum(), (
        "the fixture must assign support beyond its seeds"
    )
    assert len(set(np.unique(expected_support)) - {0}) > 1
    np.testing.assert_array_equal(
        _window(label_sink, "source-labels"), expected_labels
    )
    np.testing.assert_array_equal(
        _window(support_sink, "source-measurement-labels"), expected_support
    )


def test_no_support_round_carries_assigned_pixels(tmp_path: Path) -> None:
    """The driver holds each component's bounds, never its assignment.

    ADR-008 rule 4: nothing that grows with object area reaches the driver.
    Summed over components, the assignments are as large as all the
    persistent support in the image, so each core that holds a component
    assigns it from its window and writes its own share. Only the support
    scan returns arrays, and those are its core's boundary labels, which
    reconciliation needs and one core bounds.
    """
    executor = RecordingExecutor()
    expected_labels, expected_support = _whole_plane()

    label_sink, support_sink, result = _run_support(
        tmp_path / "run", executor=executor
    )

    support_rounds = [
        (round_name, batches, results)
        for round_name, batches, results in executor.rounds
        if round_name not in {"_scan_owners", "_publish_source_labels"}
    ]
    for round_name, batches, results in support_rounds:
        assert carried_array_bytes(batches) == (0, 0), round_name
        carried, exempted = carried_array_bytes(
            results, exempt=(TileBoundaryLabels,)
        )
        assert carried == 0, round_name
        assert (exempted > 0) == (round_name == "_scan_support"), round_name
    assert [round_name for round_name, _, _ in support_rounds] == [
        "_scan_support",
        "_publish_source_support",
    ]
    assert result.assigned_component_count == 3
    np.testing.assert_array_equal(
        _window(label_sink, "source-labels"), expected_labels
    )
    np.testing.assert_array_equal(
        _window(support_sink, "source-measurement-labels"), expected_support
    )


@pytest.mark.parametrize("core", [16, 32, 80])
def test_source_planes_are_partition_and_batch_invariant(
    tmp_path: Path, core: int
) -> None:
    """Tile geometry and batching decide which task runs, not the planes."""
    reference = _run(tmp_path / "reference", core=80)

    result = _run(
        tmp_path / f"core-{core}",
        core=core,
        maximum_objects_per_batch=1,
        maximum_batch_read_pixels=1,
    )

    for candidate, expected, product_name in zip(
        result,
        reference,
        ("source-labels", "source-measurement-labels"),
        strict=True,
    ):
        np.testing.assert_array_equal(
            _window(candidate, product_name),
            _window(expected, product_name),
        )


def test_source_planes_are_executor_invariant(tmp_path: Path) -> None:
    """Workers publish exactly what one in-process reference publishes."""
    reference = _run(tmp_path / "reference")

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        result = _run(tmp_path / "dask", executor=DaskExecutor(client))

    for candidate, expected, product_name in zip(
        result,
        reference,
        ("source-labels", "source-measurement-labels"),
        strict=True,
    ):
        np.testing.assert_array_equal(
            _window(candidate, product_name),
            _window(expected, product_name),
        )


def test_source_stages_publish_canonical_products(tmp_path: Path) -> None:
    """Each generation carries exactly one chunk per product and core."""
    component, detection, hierarchy, fits = _sources(tmp_path / "run")
    manifest = _manifest(16)
    label_sink = ZarrProductSink(
        tmp_path / "run" / "labels.zarr", manifest, generation_id="labels"
    )
    support_sink = ZarrProductSink(
        tmp_path / "run" / "support.zarr", manifest, generation_id="support"
    )

    labels = run_source_label_stage(
        component,
        manifest,
        config=SourceLabelStageConfig(maximum_tiles_per_batch=2),
        source_by_owner=_source_by_owner(),
        executor=SerialExecutor(),
        sink=label_sink,
    )
    support = run_source_support_stage(
        label_sink,
        detection,
        hierarchy,
        fits,
        manifest,
        config=SourceSupportStageConfig(
            maximum_tiles_per_batch=2,
            maximum_objects_per_batch=2,
            maximum_batch_read_pixels=65536,
        ),
        executor=SerialExecutor(),
        sink=support_sink,
    )

    assert source_label_product_names() == ("source-labels",)
    assert source_support_product_names() == ("source-measurement-labels",)
    assert set(labels.generation.product_names) == {"source-labels"}
    assert len(labels.generation.chunks) == len(manifest.tiles)
    assert labels.source_count == 3
    assert labels.partition_count == len(manifest.tiles)
    assert labels.executor_task_count > 0
    assert labels.maximum_graph_width > 0
    assert len(support.generation.chunks) == len(manifest.tiles)
    assert support.support_component_count == 3
    assert support.assigned_component_count > 0
    assert support.executor_task_count == 2 * ceil(support.partition_count / 2)
    assert support.maximum_graph_width == ceil(support.partition_count / 2)
    assert support.maximum_component_read_pixels > 0
    assert support.reconciliation_round_count >= 1


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"maximum_tiles_per_batch": 0}, "maximum_tiles_per_batch"),
        ({"maximum_objects_per_batch": 0}, "maximum_objects_per_batch"),
        ({"maximum_batch_read_pixels": True}, "maximum_batch_read_pixels"),
    ],
)
def test_source_support_rejects_invalid_configuration(
    overrides: dict[str, int], message: str
) -> None:
    """Configuration is validated before any product is initialized."""
    with pytest.raises(ValueError, match=message):
        SourceSupportStageConfig(
            **{
                "maximum_tiles_per_batch": 2,
                "maximum_objects_per_batch": 2,
                "maximum_batch_read_pixels": 4096,
                **overrides,
            }
        )


@pytest.mark.parametrize("maximum_tiles_per_batch", [0, True])
def test_source_labels_reject_invalid_configuration(
    maximum_tiles_per_batch: int,
) -> None:
    """Batching must have one explicit positive bounded task size."""
    with pytest.raises(ValueError, match="maximum_tiles_per_batch"):
        SourceLabelStageConfig(maximum_tiles_per_batch=maximum_tiles_per_batch)


def test_source_rounds_forbid_empty_executor_work_records() -> None:
    """An empty batch is a scheduling defect, not a task to submit."""
    with pytest.raises(ValueError, match="owner scan batch must not be"):
        _OwnerScanBatch(partitions=())
    with pytest.raises(ValueError, match="source label batch must not be"):
        _LabelWriteBatch(requests=())
    with pytest.raises(ValueError, match="support scan batch must not be"):
        _SupportScanBatch(partitions=())
    with pytest.raises(ValueError, match="assignment batch must not be"):
        _AssignBatch(components=(), read_bounds=ImageBounds(0, 1, 0, 1))
    with pytest.raises(ValueError, match="source support batch must not be"):
        _SupportWriteBatch(requests=())
    with pytest.raises(ValueError, match="wide support batch must not be"):
        _WideSupportBatch(cores=())


def test_a_component_without_its_canonical_pixel_fails_closed() -> None:
    """A window that does not hold the component is never assigned."""
    seeds = np.zeros((8, 8), dtype=np.int32)
    seeds[2:4, 2:4] = 5
    persistent = np.zeros((8, 8), dtype=np.bool_)
    persistent[4:6, 2:4] = True
    bounds = ImageBounds(0, 8, 0, 8)

    found = _support_component(
        seeds,
        persistent,
        _SupportComponent(bounds=bounds, first_pixel_yx=(2, 2)),
    )

    np.testing.assert_array_equal(found, (seeds > 0) | persistent)
    with pytest.raises(ValueError, match="canonical first pixel"):
        _support_component(
            seeds,
            persistent,
            _SupportComponent(bounds=bounds, first_pixel_yx=(0, 0)),
        )


@pytest.mark.parametrize(
    "dropped_round, message",
    [
        (1, "no owner scan results"),
        (2, "no source label results"),
        (3, "no support scan results"),
        (4, "no source support results"),
    ],
)
def test_every_source_round_fails_closed_on_a_silent_executor(
    tmp_path: Path, dropped_round: int, message: str
) -> None:
    """A dropped result is never published as a complete generation."""
    with pytest.raises(ValueError, match=message):
        _run(
            tmp_path / f"round-{dropped_round}",
            executor=_DropNthMapExecutor(dropped_round),
        )


def test_source_stages_require_matching_sinks_and_generations(
    tmp_path: Path,
) -> None:
    """Identities are checked before any product is initialized."""
    component, detection, hierarchy, fits = _sources(tmp_path / "run")
    manifest = _manifest(16)
    other_shape = plan_image_partitions(
        image_shape_yx=(32, 32),
        tile_core_shape_yx=(16, 16),
        halo_yx=(0, 0),
    )
    haloed = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(32, 32),
        halo_yx=(2, 2),
    )
    incomplete = _publish(
        tmp_path / "incomplete.zarr",
        (("valid-pixels", _planes()[1], "bool"),),
        generation_id="incomplete",
    )

    def labels(
        target: PartitionManifest,
        *,
        source: ZarrProductSink = component,
        sink_manifest: PartitionManifest | None = None,
        name: str = "labels",
    ) -> None:
        run_source_label_stage(
            source,
            target,
            config=SourceLabelStageConfig(maximum_tiles_per_batch=2),
            source_by_owner=_source_by_owner(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / f"{name}.zarr",
                target if sink_manifest is None else sink_manifest,
                generation_id=name,
            ),
        )

    with pytest.raises(ValueError, match="must use the stage manifest"):
        labels(manifest, sink_manifest=other_shape, name="mismatched")
    with pytest.raises(ValueError, match="cores without a halo"):
        labels(haloed, name="haloed")
    with pytest.raises(ValueError, match="match the source image shape"):
        labels(other_shape, name="other")
    with pytest.raises(ValueError, match="component owner labels"):
        labels(manifest, source=incomplete, name="incomplete-labels")

    label_sink = ZarrProductSink(
        tmp_path / "run" / "labels.zarr", manifest, generation_id="labels"
    )
    run_source_label_stage(
        component,
        manifest,
        config=SourceLabelStageConfig(maximum_tiles_per_batch=2),
        source_by_owner=_source_by_owner(),
        executor=SerialExecutor(),
        sink=label_sink,
    )

    def support(
        target: PartitionManifest,
        *,
        detection_source: ZarrProductSink = detection,
        sink_manifest: PartitionManifest | None = None,
        name: str = "support",
    ) -> None:
        run_source_support_stage(
            label_sink,
            detection_source,
            hierarchy,
            fits,
            target,
            config=SourceSupportStageConfig(
                maximum_tiles_per_batch=2,
                maximum_objects_per_batch=2,
                maximum_batch_read_pixels=65536,
            ),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / f"{name}.zarr",
                target if sink_manifest is None else sink_manifest,
                generation_id=name,
            ),
        )

    with pytest.raises(ValueError, match="must use the stage manifest"):
        support(manifest, sink_manifest=other_shape, name="mismatched-support")
    with pytest.raises(ValueError, match="cores without a halo"):
        support(haloed, name="haloed-support")
    with pytest.raises(ValueError, match="match the support image shape"):
        support(other_shape, name="other-support")
    with pytest.raises(ValueError, match="every support plane read"):
        support(
            manifest,
            detection_source=_publish(
                tmp_path / "no-validity.zarr",
                (("persistent-scale-support", _planes()[2], "bool"),),
                generation_id="no-validity",
            ),
            name="incomplete-support",
        )


def test_a_source_membership_must_own_every_component_pixel(
    tmp_path: Path,
) -> None:
    """An owner the memberships omit is a defect, not an unlabelled pixel."""
    component, _, _, _ = _sources(tmp_path / "run")
    manifest = _manifest(16)
    partial_map = dict(_source_by_owner())
    partial_map.pop(max(partial_map))

    with pytest.raises(ValueError, match="own every component pixel"):
        run_source_label_stage(
            component,
            manifest,
            config=SourceLabelStageConfig(maximum_tiles_per_batch=2),
            source_by_owner=partial_map,
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "partial.zarr", manifest, generation_id="partial"
            ),
        )


def test_an_image_with_no_support_publishes_only_its_seeds(
    tmp_path: Path,
) -> None:
    """An image whose support is empty writes the source labels unchanged."""
    root = tmp_path / "run"
    root.mkdir(parents=True, exist_ok=True)
    owners, valid, _, _ = _planes()
    empty = np.zeros(_SHAPE_YX, dtype=np.bool_)
    component = _publish(
        root / "components.zarr",
        (("component-measurement-labels", owners, "<i4"),),
        generation_id="component-fixture",
    )
    detection = _publish(
        root / "detection.zarr",
        (("valid-pixels", valid, "bool"),),
        generation_id="detection-fixture",
    )
    hierarchy = _publish(
        root / "hierarchy.zarr",
        (("persistent-scale-support", empty, "bool"),),
        generation_id="hierarchy-fixture",
    )
    fits = _publish(
        root / "fits.zarr",
        (("measurement-support", empty, "bool"),),
        generation_id="fits-fixture",
    )
    manifest = _manifest(16)
    label_sink = ZarrProductSink(
        root / "labels.zarr", manifest, generation_id="labels"
    )
    run_source_label_stage(
        component,
        manifest,
        config=SourceLabelStageConfig(maximum_tiles_per_batch=2),
        source_by_owner=_source_by_owner(),
        executor=SerialExecutor(),
        sink=label_sink,
    )
    support_sink = ZarrProductSink(
        root / "support.zarr", manifest, generation_id="support"
    )

    result = run_source_support_stage(
        label_sink,
        detection,
        hierarchy,
        fits,
        manifest,
        config=SourceSupportStageConfig(
            maximum_tiles_per_batch=2,
            maximum_objects_per_batch=2,
            maximum_batch_read_pixels=65536,
        ),
        executor=SerialExecutor(),
        sink=support_sink,
    )

    assert result.assigned_component_count == 0
    assert result.maximum_component_read_pixels >= 0
    np.testing.assert_array_equal(
        _window(support_sink, "source-measurement-labels"),
        _window(label_sink, "source-labels"),
    )


def test_an_image_with_no_source_at_all_assigns_nothing(
    tmp_path: Path,
) -> None:
    """No owner and no support means no assignment round to submit."""
    root = tmp_path / "run"
    root.mkdir(parents=True, exist_ok=True)
    empty_labels = np.zeros(_SHAPE_YX, dtype=np.int32)
    empty_mask = np.zeros(_SHAPE_YX, dtype=np.bool_)
    manifest = _manifest(16)
    label_sink = ZarrProductSink(
        root / "labels.zarr", manifest, generation_id="labels"
    )
    run_source_label_stage(
        _publish(
            root / "components.zarr",
            (("component-measurement-labels", empty_labels, "<i4"),),
            generation_id="component-fixture",
        ),
        manifest,
        config=SourceLabelStageConfig(maximum_tiles_per_batch=2),
        source_by_owner={},
        executor=SerialExecutor(),
        sink=label_sink,
    )
    support_sink = ZarrProductSink(
        root / "support.zarr", manifest, generation_id="support"
    )

    result = run_source_support_stage(
        label_sink,
        _publish(
            root / "detection.zarr",
            (("valid-pixels", _planes()[1], "bool"),),
            generation_id="detection-fixture",
        ),
        _publish(
            root / "hierarchy.zarr",
            (("persistent-scale-support", empty_mask, "bool"),),
            generation_id="hierarchy-fixture",
        ),
        _publish(
            root / "fits.zarr",
            (("measurement-support", empty_mask, "bool"),),
            generation_id="fits-fixture",
        ),
        manifest,
        config=SourceSupportStageConfig(
            maximum_tiles_per_batch=2,
            maximum_objects_per_batch=2,
            maximum_batch_read_pixels=65536,
        ),
        executor=SerialExecutor(),
        sink=support_sink,
    )

    assert result.support_component_count == 0
    assert result.assigned_component_count == 0
    assert result.maximum_component_read_pixels == 0
    assert not _window(support_sink, "source-measurement-labels").any()


def _component_windows() -> tuple[int, ...]:
    """Return every connected support component's window size."""
    owners, _, scale_support, measurement_support = _planes()
    labels = _labelled((owners > 0) | scale_support | measurement_support)
    windows: list[int] = []
    for value in range(1, int(labels.max()) + 1):
        rows, columns = np.nonzero(labels == value)
        windows.append(
            read_pixels(
                ImageBounds(
                    int(rows.min()),
                    int(rows.max()) + 1,
                    int(columns.min()),
                    int(columns.max()) + 1,
                )
            )
        )
    return tuple(windows)


@pytest.mark.parametrize("core", [16, 24])
def test_a_wide_support_component_is_assigned_from_its_cores(
    tmp_path: Path, core: int
) -> None:
    """A component wider than the budget is never read in its window.

    Each unseeded pixel goes to its nearest seed of the same component, so
    the seeds and candidates its cores return decide it exactly. A one-pixel
    budget sends every component there: the planes equal the whole-plane
    assignment and no read is wider than one core.
    """
    _, expected_support = _whole_plane()

    _, support_sink, result = _run_support(
        tmp_path / "run",
        core=core,
        maximum_objects_per_batch=1,
        maximum_batch_read_pixels=1,
    )

    np.testing.assert_array_equal(
        _window(support_sink, "source-measurement-labels"), expected_support
    )
    assert result.assigned_component_count > 1
    assert 0 < result.maximum_component_read_pixels <= core * core


def test_narrow_and_wide_components_publish_one_assignment(
    tmp_path: Path,
) -> None:
    """A budget between the fixture's windows splits the work both ways."""
    windows = _component_windows()
    budget = min(windows)
    assert budget < max(windows), "the budget must leave work on both sides"
    _, expected_support = _whole_plane()

    _, support_sink, result = _run_support(
        tmp_path / "run", maximum_batch_read_pixels=budget
    )

    np.testing.assert_array_equal(
        _window(support_sink, "source-measurement-labels"), expected_support
    )
    assert result.maximum_component_read_pixels <= max(budget, 16 * 16)


def test_the_wide_support_round_fails_closed_on_a_silent_executor(
    tmp_path: Path,
) -> None:
    """With every component wide, the fourth round is the cores' round.

    The source labels take two rounds and the support scan one, and no
    component is left for the window round, which submits nothing.
    """
    with pytest.raises(ValueError, match="no wide support results"):
        _run(
            tmp_path / "run",
            executor=_DropNthMapExecutor(4),
            maximum_batch_read_pixels=1,
        )


def test_every_core_holding_a_wide_component_must_answer() -> None:
    """A component assigned from part of its seeds could move its owners."""
    partition = _manifest(16).tiles[0]
    batches = (
        _WideSupportBatch(
            cores=(
                HeldObjects(
                    partition=partition,
                    mapping=TileLabelMapping(
                        tile_id=partition.tile_id,
                        local_labels=(1,),
                        global_labels=(1,),
                    ),
                ),
            )
        ),
    )

    with pytest.raises(ValueError, match="must answer"):
        _assign_wide_components(batches, (), image_width=_SHAPE_YX[1])


def test_a_wide_component_without_seeds_or_candidates_assigns_nothing() -> (
    None
):
    """Support no seed reaches keeps no owner, as the window kernel leaves it.

    A component whose pixels are all seeds has nothing to assign either.
    """
    partition = _manifest(16).tiles[0]
    empty = np.zeros(0, dtype=np.int64)
    batches = (
        _WideSupportBatch(
            cores=(
                HeldObjects(
                    partition=partition,
                    mapping=TileLabelMapping(
                        tile_id=partition.tile_id,
                        local_labels=(1, 2),
                        global_labels=(1, 2),
                    ),
                ),
            )
        ),
    )
    result = _WideSupportResult(
        pieces=(
            _SupportPixels(
                global_label=1,
                seed_indices=empty,
                seed_labels=empty,
                candidate_indices=np.asarray([3], dtype=np.int64),
            ),
            _SupportPixels(
                global_label=2,
                seed_indices=np.asarray([5], dtype=np.int64),
                seed_labels=np.asarray([7], dtype=np.int64),
                candidate_indices=empty,
            ),
        ),
        tile_ids=(partition.tile_id,),
        maximum_core_read_pixels=1,
    )

    assert (
        _assign_wide_components(batches, (result,), image_width=_SHAPE_YX[1])
        == ()
    )
