# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Executor, batching and product contracts for the support reductions."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypeVar

import numpy as np
import numpy.typing as npt
import pytest
from distributed import Client

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.reconciliation import TileLabelMapping
from hebog.data_models.partitioning import ImageBounds, PartitionManifest
from hebog.executors import DaskExecutor, SerialExecutor, TaskRequirement
from hebog.io.zarr import ZarrProductSink
from hebog.stages.support import (
    SupportTopologyStageConfig,
    SupportTopologyStageResult,
    _DisjointScaleDetections,
    _global_label,
    _PartitionBatch,
    _PublicationBatch,
    run_support_topology_stage,
    support_product_names,
)

pytestmark = pytest.mark.integration

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SHAPE_YX = (48, 61)
_SCALE_ORDERS = (1, 2, 3)


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


class _EmptySecondPassExecutor(SerialExecutor):
    """Complete topology but drop every publication result."""

    def __init__(self) -> None:
        """Count maps so the second one can publish nothing."""
        super().__init__()
        self._call_count = 0

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Run the first map and return nothing from the second."""
        self._call_count += 1
        if self._call_count == 1:
            return super().map_batches(
                function, batches, requirement=requirement
            )
        return []


class _EmptyExecutor(SerialExecutor):
    """Drop every submitted result for fail-closed executor testing."""

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Return no result without evaluating work."""
        del function, batches, requirement
        return []


def _planes() -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.int32],
    npt.NDArray[np.bool_],
    tuple[npt.NDArray[np.bool_], ...],
]:
    """Return detection products whose support spans several tile cores."""
    detection_labels = np.zeros(_SHAPE_YX, dtype=np.int32)
    detection_labels[10, 5] = 1
    detection_labels[10, 55] = 2
    detection_labels[40, 30] = 3
    reconstruction = np.zeros(_SHAPE_YX, dtype=np.bool_)
    reconstruction[10, 5:56] = True
    reconstruction[38:43, 28:33] = True
    scale_masks = (
        np.zeros(_SHAPE_YX, dtype=np.bool_),
        np.zeros(_SHAPE_YX, dtype=np.bool_),
        np.zeros(_SHAPE_YX, dtype=np.bool_),
    )
    scale_masks[0][10, 5:56] = True
    scale_masks[1][10, 20:40] = True
    scale_masks[2][10, 25:35] = True
    scale_masks[2][38:43, 28:33] = True
    valid = np.ones(_SHAPE_YX, dtype=np.bool_)
    valid[40, 41] = False
    reconstruction[40, 41] = True
    return (
        np.ones(_SHAPE_YX, dtype=np.float64),
        valid,
        detection_labels,
        reconstruction,
        scale_masks,
    )


def _publish_detection(root: Path) -> ZarrProductSink:
    """Publish one detection generation the support stage can read."""
    _, valid, detection_labels, reconstruction, scale_masks = _planes()
    manifest = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(32, 32),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        root,
        manifest,
        generation_id="detection-fixture",
    )
    products: tuple[
        tuple[str, npt.NDArray[np.generic], np.dtype[np.generic]], ...
    ] = (
        ("detection-labels", detection_labels, np.dtype("<i4")),
        ("reconstruction-mask", reconstruction, np.dtype(np.bool_)),
        ("valid-pixels", valid, np.dtype(np.bool_)),
        *(
            (
                f"scale-{order}-significant",
                mask,
                np.dtype(np.bool_),
            )
            for order, mask in zip(_SCALE_ORDERS, scale_masks, strict=True)
        ),
    )
    for product_name, _, dtype in products:
        sink.initialize_product(product_name=product_name, dtype=dtype)
    chunks = [
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
    ]
    sink.publish_generation(
        product_names=tuple(name for name, _, _ in products),
        chunks=chunks,
    )
    return sink


def _manifest(core_yx: tuple[int, int]) -> PartitionManifest:
    """Plan one core-only support partition."""
    return plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=core_yx,
        halo_yx=(0, 0),
    )


def _run(
    root: Path,
    *,
    manifest: PartitionManifest,
    executor: object | None = None,
    tiles_per_batch: int = 2,
) -> tuple[SupportTopologyStageResult, ZarrProductSink]:
    """Execute one isolated support-stage variant."""
    root.mkdir(parents=True, exist_ok=True)
    sink = ZarrProductSink(
        root / "support.zarr",
        manifest,
        generation_id="support-invariance",
    )
    result = run_support_topology_stage(
        _publish_detection(root / "detection.zarr"),
        manifest,
        config=SupportTopologyStageConfig(
            scale_orders=_SCALE_ORDERS,
            maximum_tiles_per_batch=tiles_per_batch,
        ),
        executor=(  # type: ignore[arg-type]
            SerialExecutor() if executor is None else executor
        ),
        sink=sink,
    )
    return result, sink


def _published(
    sink: ZarrProductSink,
) -> tuple[npt.NDArray[np.int32], npt.NDArray[np.bool_]]:
    """Read both published support planes over the whole image."""
    bounds = ImageBounds(0, _SHAPE_YX[0], 0, _SHAPE_YX[1])
    return (
        np.asarray(
            sink.read_completed_window("support-components", bounds),
            dtype=np.int32,
        ),
        np.asarray(
            sink.read_completed_window("persistent-support", bounds),
            dtype=np.bool_,
        ),
    )


def test_support_components_join_a_path_no_single_core_contains(
    tmp_path: Path,
) -> None:
    """A component crossing several cores reconciles into one label."""
    result, sink = _run(tmp_path / "run", manifest=_manifest((16, 16)))

    components, _ = _published(sink)

    assert components[10, 5] == components[10, 55]
    assert components[10, 5] != components[40, 30]
    assert components[40, 41] == 0
    assert result.support_component_count == 2
    assert result.partition_count == len(_manifest((16, 16)).tiles)
    assert result.reconciliation_round_count > 0


def test_persistent_support_keeps_only_corroborated_scale_features(
    tmp_path: Path,
) -> None:
    """Support seen at one scale alone is not persistent.

    The finest, middle and coarsest features of the band overlap in one
    chain, so the group spans three scale orders; the coarse blob below it is
    seen at one scale only.
    """
    result, sink = _run(tmp_path / "run", manifest=_manifest((16, 16)))

    _, persistent = _published(sink)

    assert bool(persistent[10, 30])
    assert bool(persistent[10, 6])
    assert not bool(persistent[38, 28])
    assert result.persistent_detection_count == 3


def test_support_stage_is_partition_batch_and_executor_invariant(
    tmp_path: Path,
) -> None:
    """One published generation survives geometry, batching and workers."""
    expected_components, expected_persistent = _published(
        _run(tmp_path / "reference", manifest=_manifest((64, 64)))[1]
    )
    variants: list[tuple[str, PartitionManifest, object, int]] = [
        ("cores-16", _manifest((16, 16)), SerialExecutor(), 1),
        ("cores-24", _manifest((24, 20)), SerialExecutor(), 3),
        ("reverse", _manifest((16, 16)), _ReverseCompletionExecutor(), 2),
    ]
    for name, manifest, executor, batch_size in variants:
        _, sink = _run(
            tmp_path / name,
            manifest=manifest,
            executor=executor,
            tiles_per_batch=batch_size,
        )
        components, persistent = _published(sink)
        np.testing.assert_array_equal(components, expected_components, name)
        np.testing.assert_array_equal(persistent, expected_persistent, name)

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        _, sink = _run(
            tmp_path / "dask",
            manifest=_manifest((16, 16)),
            executor=DaskExecutor(client),
        )
    components, persistent = _published(sink)
    np.testing.assert_array_equal(components, expected_components)
    np.testing.assert_array_equal(persistent, expected_persistent)


def test_support_stage_publishes_the_canonical_product_set(
    tmp_path: Path,
) -> None:
    """The generation carries exactly one chunk per product and core."""
    manifest = _manifest((16, 16))

    result, _ = _run(tmp_path / "run", manifest=manifest)

    assert set(result.generation.product_names) == set(support_product_names())
    assert len(result.generation.chunks) == len(support_product_names()) * len(
        manifest.tiles
    )
    assert result.executor_task_count > 0
    assert result.maximum_graph_width > 0
    assert result.maximum_read_pixel_count > 0
    assert result.boundary_summary_array_bytes > 0


def test_support_stage_rejects_a_haloed_manifest(tmp_path: Path) -> None:
    """The reductions own cores only and read no halo."""
    manifest = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(32, 32),
        halo_yx=(4, 4),
    )

    with pytest.raises(ValueError, match="core-only reduction"):
        _run(tmp_path / "run", manifest=manifest)


def test_support_stage_fails_closed_on_a_silent_executor(
    tmp_path: Path,
) -> None:
    """A dropped result is never published as a complete generation."""
    with pytest.raises(ValueError, match="no support topology results"):
        _run(
            tmp_path / "run",
            manifest=_manifest((16, 16)),
            executor=_EmptyExecutor(),
        )


@pytest.mark.parametrize(
    "scale_orders, maximum_tiles_per_batch, message",
    [
        ((1, 2, 3), 0, "maximum_tiles_per_batch"),
        ((1,), 2, "at least two scale orders"),
        ((2, 1), 2, "unique and ascending"),
    ],
)
def test_support_stage_rejects_invalid_configuration(
    scale_orders: tuple[int, ...],
    maximum_tiles_per_batch: int,
    message: str,
) -> None:
    """Configuration is validated before any product is initialized."""
    with pytest.raises(ValueError, match=message):
        SupportTopologyStageConfig(
            scale_orders=scale_orders,
            maximum_tiles_per_batch=maximum_tiles_per_batch,
        )


def test_support_stage_fails_closed_on_a_silent_publication(
    tmp_path: Path,
) -> None:
    """A complete topology never publishes an incomplete generation."""
    with pytest.raises(ValueError, match="no support publication results"):
        _run(
            tmp_path / "run",
            manifest=_manifest((16, 16)),
            executor=_EmptySecondPassExecutor(),
        )


def test_support_stage_requires_a_matching_sink_and_generation(
    tmp_path: Path,
) -> None:
    """Identities are checked before any product is initialized."""
    manifest = _manifest((16, 16))
    detection = _publish_detection(tmp_path / "detection.zarr")
    other = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(32, 32),
        halo_yx=(0, 0),
    )

    with pytest.raises(ValueError, match="must use the stage manifest"):
        run_support_topology_stage(
            detection,
            manifest,
            config=SupportTopologyStageConfig(
                scale_orders=_SCALE_ORDERS,
                maximum_tiles_per_batch=2,
            ),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "mismatched.zarr",
                other,
                generation_id="mismatched",
            ),
        )


def test_support_stage_requires_the_detection_products_it_reads(
    tmp_path: Path,
) -> None:
    """A generation without the detection planes is rejected up front."""
    manifest = _manifest((16, 16))
    incomplete = ZarrProductSink(
        tmp_path / "incomplete.zarr",
        manifest,
        generation_id="incomplete",
    )
    incomplete.initialize_product(
        product_name="detection-labels",
        dtype=np.dtype("<i4"),
    )
    incomplete.publish_generation(
        product_names=("detection-labels",),
        chunks=[
            incomplete.write_chunk(
                product_name="detection-labels",
                tile=tile,
                values=np.zeros(tile.core_bounds.shape_yx, dtype=np.int32),
            )
            for tile in manifest.tiles
        ],
    )

    with pytest.raises(ValueError, match="labels, support and scales"):
        run_support_topology_stage(
            incomplete,
            manifest,
            config=SupportTopologyStageConfig(
                scale_orders=_SCALE_ORDERS,
                maximum_tiles_per_batch=2,
            ),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "support.zarr",
                manifest,
                generation_id="support",
            ),
        )


def test_support_stage_forbids_empty_executor_work_records() -> None:
    """An empty batch is a scheduling defect, not a task to submit."""
    with pytest.raises(ValueError, match="partition batch must not be empty"):
        _PartitionBatch(partitions=())
    with pytest.raises(
        ValueError,
        match="publication batch must not be empty",
    ):
        _PublicationBatch(requests=())


def test_support_mapping_must_cover_every_local_scale_label() -> None:
    """A dropped overlap edge would silently weaken persistence."""
    mapping = TileLabelMapping(
        tile_id="tile-0000-0000",
        local_labels=(1,),
        global_labels=(7,),
    )

    assert _global_label(mapping, 1) == 7
    with pytest.raises(ValueError, match="cover every local scale label"):
        _global_label(mapping, 2)


def test_support_stage_requires_a_matching_detection_image_shape(
    tmp_path: Path,
) -> None:
    """Two generations of different images cannot be composed."""
    detection = _publish_detection(tmp_path / "detection.zarr")
    other_shape = plan_image_partitions(
        image_shape_yx=(32, 32),
        tile_core_shape_yx=(16, 16),
        halo_yx=(0, 0),
    )

    with pytest.raises(ValueError, match="match the support image shape"):
        run_support_topology_stage(
            detection,
            other_shape,
            config=SupportTopologyStageConfig(
                scale_orders=_SCALE_ORDERS,
                maximum_tiles_per_batch=2,
            ),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "support.zarr",
                other_shape,
                generation_id="support",
            ),
        )


@pytest.mark.parametrize(
    "order",
    [
        ((2, 1), (1, 1), (1, 1), (0, 1)),
        ((0, 1), (1, 1), (1, 1), (2, 1)),
        ((1, 1), (2, 1), (0, 1), (1, 1)),
    ],
)
def test_scale_groups_do_not_depend_on_the_order_edges_arrive(
    order: tuple[tuple[int, int], ...],
) -> None:
    """Grouping is associative, so completion order cannot change it."""
    components = _DisjointScaleDetections()
    components.union(order[0], order[1])
    components.union(order[2], order[3])
    components.union((0, 9), (1, 9))

    assert components.groups() == (
        ((0, 1), (1, 1), (2, 1)),
        ((0, 9), (1, 9)),
    )
