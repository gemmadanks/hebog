# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Extended groups: the components every connected support feature holds."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from numbers import Integral
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import label as ndimage_label

from hebog.algorithms.astrometry import (
    celestial_wcs_from_header_text,
)
from hebog.algorithms.component_measurement import (
    FitParentMeasurement,
    SupportFeatureGroups,
    compact_window_is_admitted,
    group_support_feature_components,
    support_feature_margin_pixels,
    support_feature_window,
)
from hebog.algorithms.detection import DetectionThresholdMasks
from hebog.algorithms.labelling import (
    LocalIslandTileSummary,
    label_detection_tile,
)
from hebog.algorithms.multiscale import ResidualAtrousPlan
from hebog.algorithms.reconciliation import (
    ReconciledIslands,
    reconcile_candidate_tiles,
)
from hebog.data_models.fitting import CompactGaussianFitResult
from hebog.data_models.images import RestoringBeam
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.executors.base import Executor
from hebog.io.base import CompletedProductSource, WindowReadable
from hebog.stages.batching import (
    WindowBatch,
    batch_object_windows,
    objects_per_batch,
)
from hebog.stages.object_extents import (
    bounds_intersect,
    core_label_extents,
    crop_slices,
    union_bounds,
)
from hebog.stages.task_memory import read_requirement

# Each round's cost per pixel of its largest read, which a task declares
# (``hebog.stages.task_memory``): the largest traced task peak over that read
# on the 3,000-, 10,000- and 15,402-pixel LoTSS-DR3 anchors and the dense
# ELAIS-N1 central 5,000 pixels, rounded up to eight bytes (plan task 17).
_FEATURE_SCAN_BYTES_PER_READ_PIXEL = 40
_GROUP_BYTES_PER_READ_PIXEL = 112


def _connected_components(
    mask: npt.NDArray[np.bool_],
) -> npt.NDArray[np.int32]:
    """Label one window's eight-connected components."""
    labels, _ = cast(
        "tuple[npt.NDArray[np.int32], int]",
        ndimage_label(mask, np.ones((3, 3))),
    )
    return labels


@dataclass(frozen=True, slots=True)
class ExtendedGroupStageConfig:
    """Reviewed grouping policy and the bounded task limits."""

    atrous_plan: ResidualAtrousPlan
    detection_sigma: float
    island_sigma: float
    minimum_pixels: int
    maximum_bounds_pixels: int
    minimum_support_fraction: float
    maximum_tiles_per_batch: int
    maximum_batch_read_pixels: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before any round is submitted."""
        for name, value in (
            ("maximum_tiles_per_batch", self.maximum_tiles_per_batch),
            ("maximum_batch_read_pixels", self.maximum_batch_read_pixels),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")

    @property
    def margin_pixels(self) -> int:
        """Return the context one support feature reads beyond its bounds."""
        return support_feature_margin_pixels(self.atrous_plan)


@dataclass(frozen=True, slots=True)
class SupportFeature:
    """One reconciled support feature and the window that groups it."""

    feature_label: int
    first_pixel_yx: tuple[int, int]
    window: ImageBounds


@dataclass(frozen=True, slots=True)
class ExtendedGroupStageResult:
    """Every support feature's extended groups and grouping evidence."""

    features: tuple[SupportFeatureGroups, ...]
    feature_count: int
    grouped_feature_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    maximum_feature_read_pixels: int
    feature_batch_count: int
    reconciliation_round_count: int


@dataclass(frozen=True, slots=True)
class _FeatureLink:
    """One measurement component seen inside one local support feature."""

    component_label: int
    local_feature_label: int


@dataclass(frozen=True, slots=True)
class _FeatureTile:
    """Compact per-core support-feature topology safe to return."""

    partition: TilePartition
    summary: LocalIslandTileSummary
    links: tuple[_FeatureLink, ...]
    component_bounds: tuple[tuple[int, ImageBounds], ...]


@dataclass(frozen=True, slots=True)
class _FeatureScanBatch:
    """One bounded coarse executor task over several cores."""

    partitions: tuple[TilePartition, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.partitions:
            raise ValueError("feature scan batch must not be empty")


@dataclass(frozen=True, slots=True)
class _FeatureBatchResult:
    """Array-free support-feature topology from one bounded scan task."""

    tiles: tuple[_FeatureTile, ...]


@dataclass(frozen=True, slots=True)
class _GroupBatch:
    """One bounded coarse executor task over several support features.

    The fit records and protected labels travel with the batch, sharded to
    the components whose measurement labels reach its read.
    """

    features: tuple[SupportFeature, ...]
    read_bounds: ImageBounds
    fits: tuple[tuple[int, CompactGaussianFitResult], ...]
    protected_labels: frozenset[int]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.features:
            raise ValueError("group batch must not be empty")


@dataclass(frozen=True, slots=True)
class _GroupBatchResult:
    """Bounded grouping records one batch of support features produced."""

    features: tuple[tuple[int, SupportFeatureGroups], ...]
    maximum_feature_read_pixels: int


def _feature_scan_batches(
    partitions: tuple[TilePartition, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_FeatureScanBatch, ...]:
    """Group cores into bounded coarse scan tasks."""
    return tuple(
        _FeatureScanBatch(
            partitions=tuple(
                partitions[start : start + maximum_tiles_per_batch]
            )
        )
        for start in range(0, len(partitions), maximum_tiles_per_batch)
    )


def _scan_support_features(
    batch: _FeatureScanBatch,
    *,
    detection_source: CompletedProductSource,
    component_source: CompletedProductSource,
    measurement_source: CompletedProductSource,
    image_shape_yx: tuple[int, int],
) -> _FeatureBatchResult:
    """Label each core's support features and observe the owners inside."""
    tiles: list[_FeatureTile] = []
    for partition in batch.partitions:
        core = partition.core_bounds
        support = np.asarray(
            measurement_source.read_completed_window(
                "measurement-support",
                core,
            ),
            dtype=np.bool_,
        ) & np.asarray(
            detection_source.read_completed_window("valid-pixels", core),
            dtype=np.bool_,
        )
        labels = np.asarray(
            component_source.read_completed_window(
                "component-measurement-labels",
                core,
            ),
            dtype=np.int32,
        )
        tile = label_detection_tile(
            DetectionThresholdMasks(
                normalized_residual=np.zeros(
                    support.shape,
                    dtype=np.float64,
                ),
                island_membership=support,
                detection_seeds=support,
                valid_pixel_count=int(np.count_nonzero(support)),
            ),
            partition,
            image_shape_yx=image_shape_yx,
        )
        owned = support & (labels > 0)
        pairs = (
            np.unique(
                np.column_stack((labels[owned], tile.labels[owned])),
                axis=0,
            )
            if bool(np.any(owned))
            else np.zeros((0, 2), dtype=np.int32)
        )
        tiles.append(
            _FeatureTile(
                partition=partition,
                summary=tile.compact_summary(),
                links=tuple(
                    _FeatureLink(
                        component_label=int(pair[0]),
                        local_feature_label=int(pair[1]),
                    )
                    for pair in pairs
                ),
                component_bounds=tuple(
                    (component_label, bounds)
                    for component_label, (bounds, _, _) in core_label_extents(
                        labels, core
                    ).items()
                ),
            )
        )
    return _FeatureBatchResult(tiles=tuple(tiles))


def _component_bounds(
    results: tuple[_FeatureBatchResult, ...],
) -> dict[int, ImageBounds]:
    """Merge every core's view into one global bound per component."""
    merged: dict[int, ImageBounds] = {}
    for result in results:
        for tile in result.tiles:
            for component_label, bounds in tile.component_bounds:
                known = union_bounds(merged.get(component_label), bounds)
                if known is None:  # pragma: no cover - bounds always exist
                    raise ValueError("component bounds must exist")
                merged[component_label] = known
    return merged


def _support_features(
    features: ReconciledIslands,
    *,
    margin: int,
    image_shape_yx: tuple[int, int],
    maximum_bounds_pixels: int,
) -> tuple[SupportFeature, ...]:
    """Bound every reconciled feature, dropping those beyond the work limit."""
    bounded: list[SupportFeature] = []
    for island in features.islands:
        window = support_feature_window(
            island.bounds,
            margin=margin,
            image_shape_yx=image_shape_yx,
            maximum_bounds_pixels=maximum_bounds_pixels,
        )
        if window is None:
            continue
        bounded.append(
            SupportFeature(
                feature_label=island.global_label,
                first_pixel_yx=island.first_pixel_yx,
                window=window,
            )
        )
    return tuple(
        sorted(
            bounded,
            key=lambda item: (item.first_pixel_yx, item.feature_label),
        )
    )


def _group_batches(  # noqa: PLR0913
    features: tuple[SupportFeature, ...],
    *,
    core_shape_yx: tuple[int, int],
    maximum_batch_read_pixels: int,
    maximum_bounds_pixels: int,
    fits: tuple[tuple[int, CompactGaussianFitResult], ...],
    protected_labels: frozenset[int],
    component_bounds: dict[int, ImageBounds],
    maximum_features_per_batch: int | None = None,
) -> tuple[_GroupBatch, ...]:
    """Group features so one read serves several, within the budget.

    A batch also closes at ``maximum_features_per_batch`` features, when
    given.

    Grouping needs a feature's whole window at once, and no core can stand
    in for it. The reviewed compact bound already limits that window: a
    feature beyond it is ADR-008 T3 work and is never grouped, exactly as
    the whole-plane pass leaves it. So a feature wider than the read budget
    is read alone, and its read is bounded by that admission, not by the
    image.

    Raises:
        ValueError: If a feature beyond the reviewed bound reaches a batch,
            which would leave its read bounded by nothing.
    """
    return tuple(
        _sharded_batch(
            batch,
            fits=fits,
            protected_labels=protected_labels,
            component_bounds=component_bounds,
        )
        for batch in batch_object_windows(
            features,
            window=lambda feature: feature.window,
            core_shape_yx=core_shape_yx,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
            maximum_objects_per_batch=maximum_features_per_batch,
            bounded_by_admission=lambda feature: compact_window_is_admitted(
                feature.window, maximum_bounds_pixels=maximum_bounds_pixels
            ),
        )
    )


def _sharded_batch(
    batch: WindowBatch[SupportFeature],
    *,
    fits: tuple[tuple[int, CompactGaussianFitResult], ...],
    protected_labels: frozenset[int],
    component_bounds: dict[int, ImageBounds],
) -> _GroupBatch:
    """Close one batch over the records its read can possibly need.

    A component outside every feature still enters the subtracted model when
    its measurement label reaches the read, so the shard is selected by
    bounding-box overlap. It is a superset of what the task uses, and the
    task re-checks pixel membership.
    """
    reachable = frozenset(
        component_label
        for component_label, bounds in component_bounds.items()
        if bounds_intersect(bounds, batch.read_bounds)
    )
    return _GroupBatch(
        features=batch.objects,
        read_bounds=batch.read_bounds,
        fits=tuple(item for item in fits if item[0] in reachable),
        protected_labels=protected_labels & reachable,
    )


def _group_batch(  # noqa: PLR0913
    batch: _GroupBatch,
    *,
    source: WindowReadable,
    background_rms_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    component_source: CompletedProductSource,
    measurement_source: CompletedProductSource,
    config: ExtendedGroupStageConfig,
    wcs_header_text: str,
    beam: RestoringBeam,
) -> _GroupBatchResult:
    """Group every support feature of one batch inside its own window."""
    wcs = celestial_wcs_from_header_text(wcs_header_text)
    bounds = batch.read_bounds
    window = source.read_window(bounds)
    if window.bounds != bounds:
        raise ValueError("image source returned different group-read bounds")
    residual = np.asarray(window.values, dtype=np.float64) - np.asarray(
        background_rms_source.read_completed_window("background", bounds),
        dtype=np.float64,
    )
    rms = np.asarray(
        background_rms_source.read_completed_window("rms", bounds),
        dtype=np.float64,
    )
    valid = np.asarray(
        detection_source.read_completed_window("valid-pixels", bounds),
        dtype=np.bool_,
    )
    support = np.asarray(
        measurement_source.read_completed_window(
            "measurement-support",
            bounds,
        ),
        dtype=np.bool_,
    )
    labels = np.asarray(
        component_source.read_completed_window(
            "component-measurement-labels",
            bounds,
        ),
        dtype=np.int32,
    )
    grouped: list[tuple[int, SupportFeatureGroups]] = []
    for feature in batch.features:
        crop = crop_slices(bounds, feature.window)
        grouped.append(
            (
                feature.feature_label,
                group_support_feature_components(
                    residual[crop],
                    rms[crop],
                    valid[crop],
                    labels[crop],
                    _feature_mask(
                        support[crop] & valid[crop],
                        feature,
                    ),
                    batch.fits,
                    batch.protected_labels,
                    wcs,
                    beam,
                    config.atrous_plan,
                    bounds=feature.window,
                    detection_sigma=config.detection_sigma,
                    island_sigma=config.island_sigma,
                    minimum_pixels=config.minimum_pixels,
                    minimum_support_fraction=(config.minimum_support_fraction),
                ),
            )
        )
    return _GroupBatchResult(
        features=tuple(grouped),
        maximum_feature_read_pixels=int(np.prod(bounds.shape_yx)),
    )


def _feature_mask(
    support: npt.NDArray[np.bool_],
    feature: SupportFeature,
) -> npt.NDArray[np.bool_]:
    """Recover one reconciled feature inside the window that contains it.

    The window is the feature's global bounds plus the margin, so the feature
    lies entirely inside it and local labelling reproduces it exactly. The
    canonical first pixel names which local component it is.
    """
    local = _connected_components(support)
    identity = int(
        local[
            feature.first_pixel_yx[0] - feature.window.y_start,
            feature.first_pixel_yx[1] - feature.window.x_start,
        ]
    )
    if identity == 0:
        raise ValueError("support feature must own its canonical first pixel")
    return np.asarray(local == identity, dtype=np.bool_)


def run_extended_group_stage(  # noqa: PLR0913, PLR0917
    source: WindowReadable,
    background_rms_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    component_source: CompletedProductSource,
    measurement_source: CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: ExtendedGroupStageConfig,
    parents: tuple[FitParentMeasurement, ...],
    wcs_header_text: str,
    beam: RestoringBeam,
    executor: Executor,
) -> ExtendedGroupStageResult:
    """Group the components every connected support feature holds.

    Two rounds and no write. The cores label the accumulated measurement
    support and observe which components lie in each local feature, and the
    reconciliation joins the features that meet across a core boundary. One
    task per batch of features then evaluates both cross-parent steps inside
    that feature's window, which is its reconciled bounds plus the reviewed
    margin.

    ``wcs_header_text`` is the caller's own header as
    :meth:`astropy.io.fits.Header.tostring` writes it, not a ``WCS``; see
    :func:`~hebog.algorithms.astrometry.celestial_wcs_from_header_text`.
    """
    if manifest.halo_yx != (0, 0):
        raise ValueError("support features read cores without a halo")
    for product_source, names in (
        (background_rms_source, ("background", "rms")),
        (detection_source, ("valid-pixels",)),
        (component_source, ("component-measurement-labels",)),
        (measurement_source, ("measurement-support",)),
    ):
        if product_source.manifest.image_shape_yx != manifest.image_shape_yx:
            raise ValueError(
                "published generations must match the grouping image shape"
            )
        if not set(names).issubset(
            product_source.read_generation().product_names
        ):
            raise ValueError(
                "published generations must carry every grouping plane read"
            )
    scan_results = tuple(
        executor.map_batches(
            partial(
                _scan_support_features,
                detection_source=detection_source,
                component_source=component_source,
                measurement_source=measurement_source,
                image_shape_yx=manifest.image_shape_yx,
            ),
            _feature_scan_batches(
                manifest.tiles,
                maximum_tiles_per_batch=config.maximum_tiles_per_batch,
            ),
            requirement=read_requirement(
                _FEATURE_SCAN_BYTES_PER_READ_PIXEL,
                (partition.read_bounds for partition in manifest.tiles),
                chunk_shape_yx=manifest.tile_core_shape_yx,
            ),
        )
    )
    if not scan_results:
        raise ValueError("executor returned no support-feature results")
    tiles = tuple(tile for result in scan_results for tile in result.tiles)
    reconciled = reconcile_candidate_tiles(
        manifest,
        tuple(tile.summary for tile in tiles),
    )
    features = _support_features(
        reconciled,
        margin=config.margin_pixels,
        image_shape_yx=manifest.image_shape_yx,
        maximum_bounds_pixels=config.maximum_bounds_pixels,
    )
    batches = _group_batches(
        features,
        core_shape_yx=manifest.tile_core_shape_yx,
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
        maximum_features_per_batch=objects_per_batch(
            len(features), executor.capacity
        ),
        maximum_bounds_pixels=config.maximum_bounds_pixels,
        fits=tuple(item for parent in parents for item in parent.fits),
        protected_labels=frozenset(
            index
            for parent in parents
            for group in parent.compact_groups
            for index in group
        ),
        component_bounds=_component_bounds(scan_results),
    )
    group_results: tuple[_GroupBatchResult, ...] = ()
    if batches:
        group_results = tuple(
            executor.map_batches(
                partial(
                    _group_batch,
                    source=source,
                    background_rms_source=background_rms_source,
                    detection_source=detection_source,
                    component_source=component_source,
                    measurement_source=measurement_source,
                    config=config,
                    wcs_header_text=wcs_header_text,
                    beam=beam,
                ),
                batches,
                requirement=read_requirement(
                    _GROUP_BYTES_PER_READ_PIXEL,
                    (batch.read_bounds for batch in batches),
                    chunk_shape_yx=manifest.tile_core_shape_yx,
                ),
            )
        )
        if not group_results:
            raise ValueError("executor returned no extended group results")
    return ExtendedGroupStageResult(
        features=tuple(
            groups
            for _, groups in sorted(
                (item for result in group_results for item in result.features),
                key=lambda item: item[0],
            )
        ),
        feature_count=len(reconciled.islands),
        grouped_feature_count=len(features),
        partition_count=len(manifest.tiles),
        executor_task_count=len(manifest.tiles) + len(batches),
        maximum_graph_width=max(len(manifest.tiles), len(batches)),
        maximum_feature_read_pixels=max(
            (result.maximum_feature_read_pixels for result in group_results),
            default=0,
        ),
        feature_batch_count=len(batches),
        reconciliation_round_count=reconciled.reduction_round_count,
    )
