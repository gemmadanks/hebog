# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Per-core and per-feature hierarchy overlaps, against their oracle."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypeVar, cast

import numpy as np
import numpy.typing as npt
import pytest
from distributed import Client
from scipy.ndimage import label as ndimage_label

from hebog.algorithms.multiscale_association import (
    ScaleDetectionPlane,
    ScaleDetectionRecords,
    build_scale_detection_plane,
    persistent_adjacent_scale_support,
)
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.reconciliation import TileLabelMapping
from hebog.algorithms.source_association import (
    HierarchyOverlaps,
    associate_from_hierarchy_overlaps,
    build_detection_component_records,
    scale_feature_envelope_bounds,
    scale_feature_influence_bounds,
    summarize_hierarchy_overlaps,
)
from hebog.data_models.partitioning import ImageBounds, PartitionManifest
from hebog.data_models.source_association import DetectionComponentRecord
from hebog.executors import DaskExecutor, SerialExecutor, TaskRequirement
from hebog.io.zarr import ZarrProductSink
from hebog.stages.association import (
    HierarchyOverlapStageConfig,
    HierarchyOverlapStageResult,
    _CoreBatch,
    _global_support,
    _InfluenceBatch,
    _one_support,
    _PairBatch,
    _reduce_wide_results,
    _SupportBatch,
    _WideBatch,
    _WideCore,
    hierarchy_overlap_product_names,
    run_hierarchy_overlap_stage,
)
from hebog.stages.batching import read_pixels

pytestmark = pytest.mark.integration

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SHAPE_YX = (96, 120)
_SCALE_ORDERS = (1, 2, 3)


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


def _signal() -> npt.NDArray[np.float64]:
    """Return three compact peaks and one broad neighbour.

    The peaks sit close enough that their coarse-scale features merge and
    their B3 envelopes meet, so the hierarchy has parent edges, shared
    support and envelope overlaps to reduce rather than an empty graph.
    """
    yy, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    return (
        14.0 * np.exp(-0.5 * (((xx - 40) / 2.0) ** 2 + ((yy - 44) / 2.0) ** 2))
        + 13.0
        * np.exp(-0.5 * (((xx - 54) / 2.0) ** 2 + ((yy - 44) / 2.0) ** 2))
        + 12.0
        * np.exp(-0.5 * (((xx - 47) / 2.0) ** 2 + ((yy - 56) / 2.0) ** 2))
        + 10.0
        * np.exp(-0.5 * (((xx - 96) / 2.5) ** 2 + ((yy - 24) / 2.5) ** 2))
        # Detected, but too weak for the finest scale: it attaches coarser.
        + 5.6
        * np.exp(-0.5 * (((xx - 16) / 2.0) ** 2 + ((yy - 16) / 2.0) ** 2))
        # Detected, and withheld from every scale: it attaches nowhere.
        + 5.6
        * np.exp(-0.5 * (((xx - 16) / 2.0) ** 2 + ((yy - 80) / 2.0) ** 2))
    )


def _planes() -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.bool_],
    npt.NDArray[np.int64],
    tuple[npt.NDArray[np.bool_], ...],
]:
    """Return the residual, validity, support and per-scale masks."""
    signal = _signal()
    valid = np.ones(_SHAPE_YX, dtype=np.bool_)
    direct = np.asarray(_labelled(signal >= 5.0), dtype=np.int64)
    scale_masks = [signal >= threshold for threshold in (6.0, 3.0, 1.0)]
    scale_masks[-1] = scale_masks[-1] | _distant_corner_features()
    for mask in scale_masks:
        mask[70:90, 6:26] = False
    significant = np.logical_or.reduce(tuple(scale_masks))
    return signal, valid, significant, direct, tuple(scale_masks)


def _distant_corner_features() -> npt.NDArray[np.bool_]:
    """Return two features whose boxes meet but whose envelopes cannot.

    The bent feature and the blob sit at opposite corners of one bounding
    box, so the box prefilter admits the pair while the reviewed B3 dilation
    leaves them apart. That is the candidate a task has to reject.
    """
    mask = np.zeros(_SHAPE_YX, dtype=np.bool_)
    mask[60:95, 70] = True
    mask[60, 70:110] = True
    mask[94, 109] = True
    return mask


def _scale_planes() -> tuple[ScaleDetectionPlane, ...]:
    """Build the scale feature planes the whole-plane oracle reads."""
    signal, valid, _, _, scale_masks = _planes()
    return tuple(
        build_scale_detection_plane(
            mask,
            np.maximum(signal, 1e-3),
            signal,
            valid,
            scale_order=order,
            nominal_scale_beam_fwhm=float(2 ** (order - 1)),
        )
        for order, mask in zip(_SCALE_ORDERS, scale_masks, strict=True)
    )


def _scale_records(
    planes: tuple[ScaleDetectionPlane, ...],
) -> tuple[ScaleDetectionRecords, ...]:
    """Describe the same features as the records a published pass returns."""
    return tuple(
        ScaleDetectionRecords(
            scale_order=plane.scale_order, detections=plane.detections
        )
        for plane in planes
    )


def _records() -> tuple[DetectionComponentRecord, ...]:
    """Return the direct component records the association decides over."""
    signal, valid, _, direct, _ = _planes()
    return build_detection_component_records(direct, signal, valid)


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


def _sources(root: Path) -> tuple[ZarrProductSink, ZarrProductSink]:
    """Publish the generations the overlap rounds read."""
    root.mkdir(parents=True, exist_ok=True)
    _, valid, significant, direct, _ = _planes()
    planes = _scale_planes()
    detection = _publish(
        root / "detection.zarr",
        (
            ("valid-pixels", valid, "bool"),
            ("reconstruction-mask", significant, "bool"),
            *(
                (
                    f"scale-{plane.scale_order}-labels",
                    np.asarray(plane.component_labels, dtype=np.int32),
                    "<i4",
                )
                for plane in planes
            ),
        ),
        generation_id="detection-fixture",
    )
    component = _publish(
        root / "components.zarr",
        (
            (
                "component-direct-labels",
                np.asarray(direct, dtype=np.int32),
                "<i4",
            ),
        ),
        generation_id="component-fixture",
    )
    return detection, component


def _config(**overrides: int) -> HierarchyOverlapStageConfig:
    """Return the stage configuration with one field replaced."""
    return HierarchyOverlapStageConfig(
        **{
            "maximum_tiles_per_batch": 2,
            "maximum_features_per_batch": 2,
            "maximum_pairs_per_batch": 2,
            "maximum_batch_read_pixels": 65536,
            **overrides,
        }
    )


def _run(
    root: Path,
    *,
    core: int = 16,
    executor: object | None = None,
    **overrides: int,
) -> HierarchyOverlapStageResult:
    """Reduce every overlap the hierarchy decision needs, in isolation."""
    detection, component = _sources(root)
    manifest = _manifest(core)
    return run_hierarchy_overlap_stage(
        detection,
        component,
        manifest,
        config=_config(**overrides),
        records=_records(),
        scale_detections=_scale_records(_scale_planes()),
        executor=SerialExecutor() if executor is None else executor,  # type: ignore[arg-type]
        sink=ZarrProductSink(
            root / "hierarchy.zarr", manifest, generation_id="hierarchy"
        ),
    )


def _whole_plane() -> HierarchyOverlaps:
    """Summarise every overlap over complete planes, as the serial oracle."""
    _, valid, significant, direct, _ = _planes()
    return summarize_hierarchy_overlaps(
        _records(), direct, _scale_planes(), valid, significant
    )


def test_reduced_overlaps_match_the_whole_plane_summary(
    tmp_path: Path,
) -> None:
    """Per-core and per-feature rounds reduce to the whole-plane answer."""
    expected = _whole_plane()

    result = _run(tmp_path / "run")

    assert expected.parent_edges, "the fixture must build a hierarchy"
    attached = expected.finest_features_by_component
    assert any(not features for features in attached.values()), (
        "the fixture must hold one owner that attaches to no feature"
    )
    assert any(
        features
        and all(
            expected.by_id()[feature_id].scale_order > 1
            for feature_id in features
        )
        for features in attached.values()
    ), "the fixture must hold one owner that attaches above the finest scale"
    assert expected.envelope_edges, "the fixture must overlap envelopes"
    assert any(
        feature.influence_component_ids for feature in expected.features
    )
    assert result.overlaps.features == expected.features
    assert (
        result.overlaps.finest_features_by_component
        == expected.finest_features_by_component
    )
    assert result.overlaps.parent_edges == expected.parent_edges
    assert (
        result.overlaps.support_component_by_component
        == expected.support_component_by_component
    )
    assert result.overlaps.envelope_edges == expected.envelope_edges


def test_the_reduced_overlaps_decide_the_same_association(
    tmp_path: Path,
) -> None:
    """The published association is the one the whole plane would give."""
    planes = _scale_planes()
    records = _records()

    result = _run(tmp_path / "run")

    assert associate_from_hierarchy_overlaps(
        records, planes, result.overlaps
    ) == associate_from_hierarchy_overlaps(records, planes, _whole_plane())


@pytest.mark.parametrize("core", [16, 32, 96])
def test_overlaps_are_partition_and_batch_invariant(
    tmp_path: Path, core: int
) -> None:
    """Tile geometry and batching decide which task runs, not the answer."""
    reference = _run(tmp_path / "reference", core=96)

    result = _run(
        tmp_path / f"core-{core}",
        core=core,
        maximum_tiles_per_batch=1,
        maximum_features_per_batch=1,
        maximum_pairs_per_batch=1,
        maximum_batch_read_pixels=1,
    )

    assert result.overlaps == reference.overlaps


def test_overlaps_are_executor_invariant(tmp_path: Path) -> None:
    """Workers reduce exactly what one in-process reference reduces."""
    reference = _run(tmp_path / "reference")

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        result = _run(tmp_path / "dask", executor=DaskExecutor(client))

    assert result.overlaps == reference.overlaps


def test_overlap_stage_publishes_scalar_execution_evidence(
    tmp_path: Path,
) -> None:
    """The stage reports the work it did without publishing a plane."""
    result = _run(tmp_path / "run")

    assert hierarchy_overlap_product_names() == ("persistent-scale-support",)
    assert set(result.generation.product_names) == set(
        hierarchy_overlap_product_names()
    )
    assert len(result.generation.chunks) == len(_manifest(16).tiles)
    assert result.partition_count == len(_manifest(16).tiles)
    assert result.feature_count > 0
    assert result.enveloped_feature_count == result.feature_count
    assert result.candidate_pair_count > len(result.overlaps.envelope_edges)
    assert result.executor_task_count > 2 * result.partition_count
    assert result.maximum_graph_width > 0
    assert result.reconciliation_round_count >= 1


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"maximum_tiles_per_batch": 0}, "maximum_tiles_per_batch"),
        ({"maximum_features_per_batch": 0}, "maximum_features_per_batch"),
        ({"maximum_pairs_per_batch": True}, "maximum_pairs_per_batch"),
        ({"maximum_batch_read_pixels": 0}, "maximum_batch_read_pixels"),
    ],
)
def test_overlap_stage_rejects_invalid_configuration(
    overrides: dict[str, int], message: str
) -> None:
    """Configuration is validated before any round is submitted."""
    with pytest.raises(ValueError, match=message):
        _config(**overrides)


def test_overlap_rounds_forbid_empty_executor_work_records() -> None:
    """An empty batch is a scheduling defect, not a task to submit."""
    with pytest.raises(ValueError, match="overlap scan batch must not be"):
        _CoreBatch(partitions=())
    with pytest.raises(ValueError, match="influence batch must not be empty"):
        _InfluenceBatch(features=(), read_bounds=ImageBounds(0, 1, 0, 1))
    with pytest.raises(ValueError, match="envelope pair batch must not be"):
        _PairBatch(pairs=(), read_bounds=ImageBounds(0, 1, 0, 1))
    with pytest.raises(ValueError, match="persistent support batch must not"):
        _SupportBatch(partitions=(), retained_by_scale=())
    with pytest.raises(ValueError, match="wide overlap batch must not be"):
        _WideBatch(cores=())


@pytest.mark.parametrize(
    "dropped_round, message",
    [
        (1, "no overlap scan results"),
        (2, "no feature influence results"),
        (3, "no envelope pair results"),
        (4, "no persistent support results"),
    ],
)
def test_every_overlap_round_fails_closed_on_a_silent_executor(
    tmp_path: Path, dropped_round: int, message: str
) -> None:
    """A dropped result is never reduced as a complete overlap set."""
    with pytest.raises(ValueError, match=message):
        _run(
            tmp_path / f"round-{dropped_round}",
            executor=_DropNthMapExecutor(dropped_round),
        )


def test_overlap_stage_requires_matching_generations_and_a_core_manifest(
    tmp_path: Path,
) -> None:
    """Identities are checked before any round is submitted."""
    detection, component = _sources(tmp_path / "run")
    incomplete = _publish(
        tmp_path / "incomplete.zarr",
        (("valid-pixels", _planes()[1], "bool"),),
        generation_id="incomplete",
    )
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

    def run(
        manifest: PartitionManifest,
        *,
        detection_source: ZarrProductSink = detection,
    ) -> None:
        run_hierarchy_overlap_stage(
            detection_source,
            component,
            manifest,
            config=_config(),
            records=_records(),
            scale_detections=_scale_records(_scale_planes()),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / f"sink-{manifest.tile_core_shape_yx[0]}.zarr",
                manifest,
                generation_id="hierarchy",
            ),
        )

    with pytest.raises(ValueError, match="cores without a halo"):
        run(haloed)
    with pytest.raises(ValueError, match="match the overlap image shape"):
        run(other_shape)
    with pytest.raises(ValueError, match="every overlap plane read"):
        run(_manifest(16), detection_source=incomplete)


def test_an_unmapped_support_label_fails_closed() -> None:
    """A tile mapping that omits a label is never silently numbered."""
    mapping = TileLabelMapping(
        tile_id="tile", local_labels=(1,), global_labels=(7,)
    )

    assert _global_support(mapping, 1) == 7
    with pytest.raises(ValueError, match="must cover every local label"):
        _global_support(mapping, 2)


@pytest.mark.parametrize("occupied", [set[int](), {0, 1}, {1, 2}])
def test_a_component_outside_one_support_parent_fails_closed(
    occupied: set[int],
) -> None:
    """A direct owner spanning or missing support is a defect, not a row."""
    assert _one_support({3}) == 3
    with pytest.raises(ValueError, match="one connected support parent"):
        _one_support(occupied)


def test_an_image_with_no_scale_feature_reduces_to_nothing(
    tmp_path: Path,
) -> None:
    """An image whose scales are empty submits no per-object round."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    _, valid, _, direct, _ = _planes()
    empty = np.zeros(_SHAPE_YX, dtype=np.bool_)
    detection = _publish(
        tmp_path / "detection.zarr",
        (
            ("valid-pixels", valid, "bool"),
            ("reconstruction-mask", empty, "bool"),
            *(
                (
                    f"scale-{order}-labels",
                    np.zeros(_SHAPE_YX, dtype=np.int32),
                    "<i4",
                )
                for order in _SCALE_ORDERS
            ),
        ),
        generation_id="empty-detection",
    )
    component = _publish(
        tmp_path / "components.zarr",
        (
            (
                "component-direct-labels",
                np.asarray(direct, dtype=np.int32),
                "<i4",
            ),
        ),
        generation_id="component-fixture",
    )

    result = run_hierarchy_overlap_stage(
        detection,
        component,
        _manifest(16),
        config=_config(),
        records=_records(),
        scale_detections=tuple(
            ScaleDetectionRecords(scale_order=order, detections=())
            for order in _SCALE_ORDERS
        ),
        executor=SerialExecutor(),
        sink=ZarrProductSink(
            tmp_path / "hierarchy.zarr", _manifest(16), generation_id="empty"
        ),
    )

    assert result.feature_count == 0
    assert result.candidate_pair_count == 0
    assert result.overlaps.features == ()
    assert result.overlaps.parent_edges == ()
    assert result.overlaps.envelope_edges == frozenset()
    assert all(
        not features
        for features in result.overlaps.finest_features_by_component.values()
    )
    assert result.executor_task_count == 2 * result.partition_count


def test_the_published_support_is_the_whole_plane_persistence(
    tmp_path: Path,
) -> None:
    """Cores paint exactly the support a whole-plane pass would keep."""
    planes = _scale_planes()

    result = _run(tmp_path / "run")

    published = np.asarray(
        ZarrProductSink(
            tmp_path / "run" / "hierarchy.zarr",
            _manifest(16),
            generation_id="hierarchy",
        ).read_completed_window(
            "persistent-scale-support",
            ImageBounds(0, _SHAPE_YX[0], 0, _SHAPE_YX[1]),
        ),
        dtype=np.bool_,
    )

    expected = persistent_adjacent_scale_support(planes)
    assert expected.any(), "the fixture must hold persistent support"
    np.testing.assert_array_equal(published, expected)
    assert result.generation.product_names


def test_an_unconfigured_scale_record_fails_closed() -> None:
    """A scale order below one is a defect, not a set of features."""
    assert ScaleDetectionRecords(scale_order=1, detections=()).detections == ()
    with pytest.raises(ValueError, match="scale order must be positive"):
        ScaleDetectionRecords(scale_order=0, detections=())


# Twice the widest reviewed B3 radius: an influence dilates an envelope that
# is itself a dilation of the feature's support.
_HALO = 2 * 14


@pytest.mark.parametrize("core", [16, 24, 32])
def test_wide_work_is_decided_from_the_cores_it_reaches(
    tmp_path: Path, core: int
) -> None:
    """No influence or envelope pair is read whole when it passes the budget.

    Both are dilations by the reviewed B3 radius, so each core the work can
    reach decides its own pixels under that halo. A one-pixel budget sends
    every influence and every pair there: the overlaps equal the whole-plane
    summary, and no read is wider than one core and that halo.
    """
    expected = _whole_plane()

    result = _run(
        tmp_path / f"core-{core}",
        core=core,
        maximum_tiles_per_batch=1,
        maximum_batch_read_pixels=1,
    )

    assert result.overlaps.features == expected.features
    assert result.overlaps.envelope_edges == expected.envelope_edges
    assert 0 < result.maximum_feature_read_pixels <= (core + 2 * _HALO) ** 2


def _influence_window_pixels() -> tuple[int, ...]:
    """Return every enveloped feature's influence window size, from records."""
    windows: list[int] = []
    for scale in _scale_records(_scale_planes()):
        for detection in scale.detections:
            envelope = scale_feature_envelope_bounds(
                ImageBounds(*detection.bounds_yx),
                scale_order=scale.scale_order,
                image_shape_yx=_SHAPE_YX,
            )
            if envelope is not None:
                windows.append(
                    read_pixels(
                        scale_feature_influence_bounds(
                            envelope,
                            scale_order=scale.scale_order,
                            image_shape_yx=_SHAPE_YX,
                        )
                    )
                )
    return tuple(windows)


def test_narrow_and_wide_work_decide_one_answer(tmp_path: Path) -> None:
    """A budget between the fixture's windows splits the work both ways.

    Windows under it are read whole and the rest are decided in their cores,
    and the reduced overlaps are the ones either path alone would give.
    """
    budget = 900
    windows = _influence_window_pixels()
    assert min(windows) <= budget < max(windows), (
        "the budget must leave work on both sides"
    )
    reference = _run(tmp_path / "reference", core=96)

    result = _run(
        tmp_path / "mixed", core=16, maximum_batch_read_pixels=budget
    )

    assert result.overlaps == reference.overlaps
    assert result.maximum_feature_read_pixels <= (16 + 2 * _HALO) ** 2


def test_wide_work_is_executor_invariant(tmp_path: Path) -> None:
    """Workers decide the cores' parts exactly as one process does."""
    reference = _run(tmp_path / "reference", maximum_batch_read_pixels=1)

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        result = _run(
            tmp_path / "dask",
            executor=DaskExecutor(client),
            maximum_batch_read_pixels=1,
        )

    assert result.overlaps == reference.overlaps


def test_the_wide_round_fails_closed_on_a_silent_executor(
    tmp_path: Path,
) -> None:
    """With every piece of work wide, the second round is the cores' round.

    The window rounds have nothing to do, so they submit nothing.
    """
    with pytest.raises(ValueError, match="no wide overlap results"):
        _run(
            tmp_path / "run",
            executor=_DropNthMapExecutor(2),
            maximum_batch_read_pixels=1,
        )


def test_every_core_that_wide_work_reaches_must_answer() -> None:
    """An influence or overlap decided from part of its cores is not one."""
    batches = (
        _WideBatch(
            cores=(
                _WideCore(
                    partition=_manifest(16).tiles[0], features=(), pairs=()
                ),
            )
        ),
    )

    with pytest.raises(ValueError, match="must answer"):
        _reduce_wide_results(batches, ())
