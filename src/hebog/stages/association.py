# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Scheduler-facing rounds that answer the source hierarchy's pixel questions.

ADR-008's association round produces
:class:`~hebog.algorithms.source_association.HierarchyOverlaps` and nothing
else: the decision that consumes it is pure record logic, so it cannot depend
on tile geometry or completion order. Three rounds produce it. The cores
observe which components, features and retained support components meet; one
task per feature derives that feature's B3 influence inside its own window;
and one task per candidate pair decides whether two envelopes overlap inside
the box that holds them both.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from numbers import Integral
from typing import Protocol

import numpy as np
import numpy.typing as npt

from hebog.algorithms.detection import DetectionThresholdMasks
from hebog.algorithms.labelling import (
    LocalIslandTileSummary,
    label_detection_tile,
)
from hebog.algorithms.multiscale import residual_atrous_scale_halos_pixels
from hebog.algorithms.multiscale_association import (
    ScaleDetections,
    persistent_scale_labels,
    persistent_scale_support_window,
)
from hebog.algorithms.reconciliation import (
    ReconciledIslands,
    TileLabelMapping,
    reconcile_candidate_tiles,
)
from hebog.algorithms.source_association import (
    FeatureOverlaps,
    HierarchyOverlaps,
    envelope_pair_is_needed,
    influence_candidate_feature_ids,
    scale_feature_envelope_bounds,
    scale_feature_envelope_support,
    scale_feature_envelopes_overlap,
    scale_feature_influence_bounds,
    scale_feature_influence_component_ids,
)
from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import ProductChunk
from hebog.data_models.source_association import DetectionComponentRecord
from hebog.executors.base import Executor
from hebog.io.zarr import ZarrProductSink
from hebog.stages.batching import (
    batch_object_windows,
    map_round,
    read_pixels,
)

_SCALE_ORDERS = (1, 2, 3)


class _CompletedProductSource(Protocol):
    """Read checksum-validated windows from one published generation."""

    @property
    def manifest(self) -> PartitionManifest:
        """Return the canonical partition the generation was written on."""
        ...

    def access_session(self) -> AbstractContextManager[None]:
        """Hold one bounded read session open for a batch of windows."""
        ...

    def read_generation(self) -> ProductGenerationManifest:
        """Return the published generation this source reads."""
        ...

    def read_completed_window(
        self,
        product_name: str,
        bounds: ImageBounds,
    ) -> npt.NDArray[np.generic]:
        """Read one checksum-validated bounded window."""
        ...


@dataclass(frozen=True, slots=True)
class HierarchyOverlapStageConfig:
    """The bounded task limits of the three association rounds."""

    maximum_tiles_per_batch: int
    maximum_features_per_batch: int
    maximum_pairs_per_batch: int
    maximum_batch_read_pixels: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before any round is submitted."""
        for name, value in (
            ("maximum_tiles_per_batch", self.maximum_tiles_per_batch),
            ("maximum_features_per_batch", self.maximum_features_per_batch),
            ("maximum_pairs_per_batch", self.maximum_pairs_per_batch),
            ("maximum_batch_read_pixels", self.maximum_batch_read_pixels),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class HierarchyOverlapStageResult:
    """The reduced pixel facts and this stage's scalar execution evidence."""

    generation: ProductGenerationManifest
    overlaps: HierarchyOverlaps
    partition_count: int
    feature_count: int
    enveloped_feature_count: int
    candidate_pair_count: int
    executor_task_count: int
    maximum_graph_width: int
    reconciliation_round_count: int
    maximum_feature_read_pixels: int


@dataclass(frozen=True, slots=True)
class _Feature:
    """One reconciled scale feature, as the driver knows it from records."""

    feature_id: str
    scale_order: int
    label_value: int
    bounds: ImageBounds
    envelope_bounds: ImageBounds | None


@dataclass(frozen=True, slots=True)
class _CoreBatch:
    """One bounded coarse executor task over several cores."""

    partitions: tuple[TilePartition, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.partitions:
            raise ValueError("overlap scan batch must not be empty")


@dataclass(frozen=True, slots=True)
class _CoreOverlaps:
    """Array-free overlap observations from one core."""

    partition: TilePartition
    summary: LocalIslandTileSummary
    component_support: tuple[tuple[int, int], ...]
    component_feature: tuple[tuple[int, int, int], ...]
    feature_support: tuple[tuple[int, int, int], ...]
    parent_links: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True, slots=True)
class _CoreBatchResult:
    """Overlap observations from one bounded scan task."""

    cores: tuple[_CoreOverlaps, ...]


@dataclass(frozen=True, slots=True)
class _InfluenceBatch:
    """One bounded coarse executor task over several feature windows."""

    features: tuple[_Feature, ...]
    read_bounds: ImageBounds

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.features:
            raise ValueError("influence batch must not be empty")


@dataclass(frozen=True, slots=True)
class _InfluenceBatchResult:
    """The owners each feature's reviewed B3 influence contains."""

    influence: tuple[tuple[str, tuple[str, ...]], ...]
    maximum_read_pixels: int


@dataclass(frozen=True, slots=True)
class _PairBatch:
    """One bounded coarse executor task over several candidate pairs."""

    pairs: tuple[tuple[_Feature, _Feature], ...]
    read_bounds: ImageBounds

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.pairs:
            raise ValueError("envelope pair batch must not be empty")


@dataclass(frozen=True, slots=True)
class _PairBatchResult:
    """The candidate pairs whose bounded envelopes actually overlap."""

    edges: tuple[tuple[str, str], ...]
    maximum_read_pixels: int


@dataclass(frozen=True, slots=True)
class _WideCore:
    """One core and the wide work whose envelopes can reach it."""

    partition: TilePartition
    features: tuple[_Feature, ...]
    pairs: tuple[tuple[_Feature, _Feature], ...]


@dataclass(frozen=True, slots=True)
class _WideBatch:
    """One bounded coarse executor task over the cores of wide work."""

    cores: tuple[_WideCore, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.cores:
            raise ValueError("wide overlap batch must not be empty")


@dataclass(frozen=True, slots=True)
class _WideBatchResult:
    """What one batch of cores observed of the wide influences and pairs."""

    influence: tuple[tuple[str, tuple[str, ...]], ...]
    edges: tuple[tuple[str, str], ...]
    tile_ids: tuple[str, ...]
    maximum_read_pixels: int


def _core_batches(
    partitions: tuple[TilePartition, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_CoreBatch, ...]:
    """Group cores into bounded coarse scan tasks."""
    return tuple(
        _CoreBatch(
            partitions=tuple(
                partitions[start : start + maximum_tiles_per_batch]
            )
        )
        for start in range(0, len(partitions), maximum_tiles_per_batch)
    )


def _scan_core_overlaps(
    batch: _CoreBatch,
    *,
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
) -> _CoreBatchResult:
    """Observe every overlap one core can see, as array-free records."""
    with detection_source.access_session(), component_source.access_session():
        cores: list[_CoreOverlaps] = []
        for partition in batch.partitions:
            core = partition.core_bounds
            valid = np.asarray(
                detection_source.read_completed_window("valid-pixels", core),
                dtype=np.bool_,
            )
            significant = np.asarray(
                detection_source.read_completed_window(
                    "reconstruction-mask",
                    core,
                ),
                dtype=np.bool_,
            )
            components = np.asarray(
                component_source.read_completed_window(
                    "component-direct-labels",
                    core,
                ),
                dtype=np.int64,
            )
            scale_labels = tuple(
                np.asarray(
                    detection_source.read_completed_window(
                        f"scale-{order}-labels",
                        core,
                    ),
                    dtype=np.int32,
                )
                for order in _SCALE_ORDERS
            )
            support = ((components > 0) | significant) & valid
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
            cores.append(
                _CoreOverlaps(
                    partition=partition,
                    summary=tile.compact_summary(),
                    component_support=_pairs(components, tile.labels),
                    component_feature=tuple(
                        (component, order, feature)
                        for order, labels in zip(
                            _SCALE_ORDERS, scale_labels, strict=True
                        )
                        for component, feature in _pairs(components, labels)
                    ),
                    feature_support=tuple(
                        (order, feature, support_label)
                        for order, labels in zip(
                            _SCALE_ORDERS, scale_labels, strict=True
                        )
                        for feature, support_label in _pairs(
                            labels, tile.labels, include_zero_second=True
                        )
                    ),
                    parent_links=tuple(
                        (_SCALE_ORDERS[index], child, parent)
                        for index in range(len(_SCALE_ORDERS) - 1)
                        for child, parent in _pairs(
                            scale_labels[index], scale_labels[index + 1]
                        )
                    ),
                )
            )
        return _CoreBatchResult(cores=tuple(cores))


def _pairs(
    first: npt.NDArray[np.generic],
    second: npt.NDArray[np.generic],
    *,
    include_zero_second: bool = False,
) -> tuple[tuple[int, int], ...]:
    """Return every distinct positive-to-other label pair in one window."""
    left = np.asarray(first, dtype=np.int64)
    right = np.asarray(second, dtype=np.int64)
    selected = (left > 0) if include_zero_second else (left > 0) & (right > 0)
    if not bool(np.any(selected)):
        return ()
    observed = np.unique(
        np.column_stack((left[selected], right[selected])),
        axis=0,
    )
    return tuple((int(row[0]), int(row[1])) for row in observed)


def _influence_batches(
    features: tuple[_Feature, ...],
    *,
    maximum_features_per_batch: int,
    maximum_batch_read_pixels: int,
    image_shape_yx: tuple[int, int],
) -> tuple[_InfluenceBatch, ...]:
    """Group enveloped features into bounded coarse influence tasks.

    Features are grouped in canonical order so that neighbours share one
    read, which is what keeps a task's window opens proportional to the work
    it does rather than to the number of features.
    """
    window = partial(_influence_window, image_shape_yx=image_shape_yx)
    return tuple(
        _InfluenceBatch(
            features=group,
            read_bounds=_union_bounds(
                tuple(window(feature) for feature in group)
            ),
        )
        for group in _spatial_groups(
            features,
            window=window,
            maximum_objects_per_batch=maximum_features_per_batch,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
        )
    )


def _influence_window(
    feature: _Feature,
    *,
    image_shape_yx: tuple[int, int],
) -> ImageBounds:
    """Return the window one feature's influence dilation reads."""
    bounds = feature.envelope_bounds
    if bounds is None:  # pragma: no cover - callers filter unenveloped scales
        raise ValueError("feature beyond the B3 footprint has no envelope")
    return scale_feature_influence_bounds(
        bounds,
        scale_order=feature.scale_order,
        image_shape_yx=image_shape_yx,
    )


def _union_bounds(bounds: tuple[ImageBounds, ...]) -> ImageBounds:
    """Return the one read that serves every window in a batch."""
    return ImageBounds(
        min(item.y_start for item in bounds),
        max(item.y_stop for item in bounds),
        min(item.x_start for item in bounds),
        max(item.x_stop for item in bounds),
    )


def _spatial_groups[T](
    objects: tuple[T, ...],
    *,
    window: Callable[[T], ImageBounds],
    maximum_objects_per_batch: int,
    maximum_batch_read_pixels: int,
) -> tuple[tuple[T, ...], ...]:
    """Group objects so one read serves several, within both budgets.

    Objects are visited in raster order of their windows, so a batch covers a
    compact region.

    Raises:
        ValueError: If one object's own window exceeds the read budget. Such
            work is decided from the cores it reaches instead.
    """
    return tuple(
        batch.objects
        for batch in batch_object_windows(
            sorted(
                objects,
                key=lambda item: (window(item).y_start, window(item).x_start),
            ),
            window=window,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
            maximum_objects_per_batch=maximum_objects_per_batch,
        )
    )


@dataclass(frozen=True, slots=True)
class _Read:
    """One batch's planes, read once and cropped per feature."""

    bounds: ImageBounds
    valid: npt.NDArray[np.bool_]
    labels_by_scale: Mapping[int, npt.NDArray[np.int32]]
    components: npt.NDArray[np.int64] | None = None

    def crop(self, window: ImageBounds) -> tuple[slice, slice]:
        """Return the slices selecting one window inside this read."""
        return (
            slice(
                window.y_start - self.bounds.y_start,
                window.y_stop - self.bounds.y_start,
            ),
            slice(
                window.x_start - self.bounds.x_start,
                window.x_stop - self.bounds.x_start,
            ),
        )


def _read_batch(
    bounds: ImageBounds,
    scale_orders: frozenset[int],
    *,
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource | None = None,
) -> _Read:
    """Read every plane one batch needs, once, over its own window."""
    return _Read(
        bounds=bounds,
        valid=np.asarray(
            detection_source.read_completed_window("valid-pixels", bounds),
            dtype=np.bool_,
        ),
        labels_by_scale={
            order: np.asarray(
                detection_source.read_completed_window(
                    f"scale-{order}-labels",
                    bounds,
                ),
                dtype=np.int32,
            )
            for order in sorted(scale_orders)
        },
        components=None
        if component_source is None
        else np.asarray(
            component_source.read_completed_window(
                "component-direct-labels",
                bounds,
            ),
            dtype=np.int64,
        ),
    )


def _feature_envelope(
    feature: _Feature,
    read: _Read,
) -> tuple[ImageBounds, npt.NDArray[np.bool_]]:
    """Dilate one feature's exact support inside its own envelope window."""
    bounds = feature.envelope_bounds
    if bounds is None:  # pragma: no cover - callers filter unenveloped scales
        raise ValueError("feature beyond the B3 footprint has no envelope")
    crop = read.crop(bounds)
    return bounds, scale_feature_envelope_support(
        np.asarray(
            read.labels_by_scale[feature.scale_order][crop]
            == feature.label_value
        ),
        read.valid[crop],
        scale_order=feature.scale_order,
    )


def _influence_batch(
    batch: _InfluenceBatch,
    *,
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
    component_id_by_label: Mapping[int, str],
) -> _InfluenceBatchResult:
    """Derive each feature's reviewed B3 influence inside its own window."""
    with detection_source.access_session(), component_source.access_session():
        read = _read_batch(
            batch.read_bounds,
            frozenset(feature.scale_order for feature in batch.features),
            detection_source=detection_source,
            component_source=component_source,
        )
        components = read.components
        if components is None:  # pragma: no cover - always read above
            raise ValueError("influence batch must read component labels")
        influence: list[tuple[str, tuple[str, ...]]] = []
        for feature in batch.features:
            envelope_bounds, envelope = _feature_envelope(feature, read)
            bounds = scale_feature_influence_bounds(
                envelope_bounds,
                scale_order=feature.scale_order,
                image_shape_yx=image_shape_yx,
            )
            seed = np.zeros(bounds.shape_yx, dtype=np.bool_)
            seed[
                envelope_bounds.y_start - bounds.y_start : (
                    envelope_bounds.y_stop - bounds.y_start
                ),
                envelope_bounds.x_start - bounds.x_start : (
                    envelope_bounds.x_stop - bounds.x_start
                ),
            ] = envelope
            crop = read.crop(bounds)
            influence.append(
                (
                    feature.feature_id,
                    tuple(
                        sorted(
                            scale_feature_influence_component_ids(
                                seed,
                                read.valid[crop],
                                components[crop],
                                scale_order=feature.scale_order,
                                component_id_by_label=component_id_by_label,
                            )
                        )
                    ),
                )
            )
        return _InfluenceBatchResult(
            influence=tuple(influence),
            maximum_read_pixels=read_pixels(batch.read_bounds),
        )


def _candidate_pairs(
    features: tuple[_Feature, ...],
    *,
    terminal_scale_order: int,
) -> tuple[tuple[_Feature, _Feature], ...]:
    """Return every feature pair whose envelope boxes can possibly meet.

    The boxes follow from the reconciled bounds, so this prefilter is record
    work. Only the pairs it admits read pixels.
    """
    enveloped = sorted(
        (
            feature
            for feature in features
            if feature.envelope_bounds is not None
        ),
        key=lambda item: (
            (item.envelope_bounds.y_start, item.feature_id)  # type: ignore[union-attr]
            if item.envelope_bounds is not None
            else (0, item.feature_id)
        ),
    )
    pairs: list[tuple[_Feature, _Feature]] = []
    active: list[_Feature] = []
    for feature in enveloped:
        bounds = feature.envelope_bounds
        assert bounds is not None
        active = [
            item
            for item in active
            if item.envelope_bounds is not None
            and item.envelope_bounds.y_stop > bounds.y_start
        ]
        for other in active:
            other_bounds = other.envelope_bounds
            assert other_bounds is not None
            if (
                other_bounds.x_start >= bounds.x_stop
                or bounds.x_start >= other_bounds.x_stop
                or not envelope_pair_is_needed(
                    other.scale_order,
                    feature.scale_order,
                    terminal_scale_order=terminal_scale_order,
                )
            ):
                continue
            pairs.append(
                (other, feature)
                if other.feature_id < feature.feature_id
                else (feature, other)
            )
        active.append(feature)
    return tuple(
        sorted(
            pairs,
            key=lambda item: (item[0].feature_id, item[1].feature_id),
        )
    )


def _pair_batches(
    pairs: tuple[tuple[_Feature, _Feature], ...],
    *,
    maximum_pairs_per_batch: int,
    maximum_batch_read_pixels: int,
) -> tuple[_PairBatch, ...]:
    """Group candidate pairs so one read serves several, within the budget."""
    return tuple(
        _PairBatch(pairs=group, read_bounds=_pair_read_bounds(group))
        for group in _spatial_groups(
            pairs,
            window=_pair_read_bounds_of,
            maximum_objects_per_batch=maximum_pairs_per_batch,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
        )
    )


def _pair_read_bounds_of(pair: tuple[_Feature, _Feature]) -> ImageBounds:
    """Return the window one candidate pair reads."""
    return _pair_read_bounds((pair,))


def _pair_read_bounds(
    pairs: tuple[tuple[_Feature, _Feature], ...],
) -> ImageBounds:
    """Return the one read that serves every envelope in a batch."""
    return _union_bounds(
        tuple(
            bounds
            for pair in pairs
            for feature in pair
            if (bounds := feature.envelope_bounds) is not None
        )
    )


def _pair_batch(
    batch: _PairBatch,
    *,
    detection_source: _CompletedProductSource,
) -> _PairBatchResult:
    """Decide each candidate pair inside the box that holds both envelopes.

    A feature usually meets several neighbours, and its envelope is the same
    dilation each time, so the batch derives it once. Batches are grouped by
    the canonically first feature, which is what makes that reuse pay.
    """
    envelopes: dict[str, tuple[ImageBounds, npt.NDArray[np.bool_]]] = {}
    with detection_source.access_session():
        read = _read_batch(
            batch.read_bounds,
            frozenset(
                feature.scale_order for pair in batch.pairs for feature in pair
            ),
            detection_source=detection_source,
        )

        def envelope(
            feature: _Feature,
        ) -> tuple[ImageBounds, npt.NDArray[np.bool_]]:
            """Return one feature's envelope, deriving it at most once."""
            if feature.feature_id not in envelopes:
                envelopes[feature.feature_id] = _feature_envelope(
                    feature, read
                )
            return envelopes[feature.feature_id]

        edges: list[tuple[str, str]] = []
        for first, second in batch.pairs:
            first_bounds, first_support = envelope(first)
            second_bounds, second_support = envelope(second)
            if scale_feature_envelopes_overlap(
                first_support,
                first_bounds,
                second_support,
                second_bounds,
            ):
                edges.append((first.feature_id, second.feature_id))
        return _PairBatchResult(
            edges=tuple(edges),
            maximum_read_pixels=read_pixels(batch.read_bounds),
        )


def _scale_radius(scale_order: int) -> int:
    """Return the reviewed B3 dilation radius of one scale, in pixels."""
    return residual_atrous_scale_halos_pixels()[scale_order - 1]


def _wide_overlap_batch(
    batch: _WideBatch,
    *,
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
    component_id_by_label: Mapping[int, str],
) -> _WideBatchResult:
    """Decide wide influences and envelope pairs from the cores they reach.

    An envelope is exact support dilated through valid pixels by the scale's
    reviewed radius, and an influence is that envelope dilated by the radius
    again, so every pixel either holds lies within that many pixels of the
    support. A core read with that halo therefore decides each of its own
    pixels exactly: an influence is the union of the owners each core finds
    in its part, and two envelopes overlap where any core finds a shared
    pixel.
    """
    with detection_source.access_session(), component_source.access_session():
        influence: list[tuple[str, tuple[str, ...]]] = []
        edges: list[tuple[str, str]] = []
        maximum_read_pixels = 0
        for core in batch.cores:
            needed = {
                feature.feature_id: feature
                for feature in (
                    *core.features,
                    *(feature for pair in core.pairs for feature in pair),
                )
            }
            read_bounds = core.partition.core_bounds.expanded(
                max(
                    (
                        *(
                            2 * _scale_radius(feature.scale_order)
                            for feature in core.features
                        ),
                        *(
                            _scale_radius(feature.scale_order)
                            for feature in needed.values()
                        ),
                    )
                ),
                image_shape_yx,
            )
            maximum_read_pixels = max(
                maximum_read_pixels, read_pixels(read_bounds)
            )
            read = _read_batch(
                read_bounds,
                frozenset(feature.scale_order for feature in needed.values()),
                detection_source=detection_source,
                component_source=component_source,
            )
            if read.components is None:  # pragma: no cover - always read
                raise ValueError("wide batch must read component labels")
            owned = np.zeros(read.valid.shape, dtype=np.bool_)
            owned[read.crop(core.partition.core_bounds)] = True
            owned_components = np.where(owned, read.components, 0)
            envelopes = {
                feature_id: scale_feature_envelope_support(
                    np.asarray(
                        read.labels_by_scale[feature.scale_order]
                        == feature.label_value
                    ),
                    read.valid,
                    scale_order=feature.scale_order,
                )
                for feature_id, feature in needed.items()
            }
            influence.extend(
                (
                    feature.feature_id,
                    tuple(
                        sorted(
                            scale_feature_influence_component_ids(
                                envelopes[feature.feature_id],
                                read.valid,
                                owned_components,
                                scale_order=feature.scale_order,
                                component_id_by_label=component_id_by_label,
                            )
                        )
                    ),
                )
                for feature in core.features
            )
            edges.extend(
                (first.feature_id, second.feature_id)
                for first, second in core.pairs
                if bool(
                    np.any(
                        envelopes[first.feature_id]
                        & envelopes[second.feature_id]
                        & owned
                    )
                )
            )
        return _WideBatchResult(
            influence=tuple(influence),
            edges=tuple(edges),
            tile_ids=tuple(core.partition.tile_id for core in batch.cores),
            maximum_read_pixels=maximum_read_pixels,
        )


def _feature_holders(
    cores: tuple[_CoreOverlaps, ...],
) -> dict[tuple[int, int], frozenset[str]]:
    """Name the cores holding each scale feature, by scale and label."""
    holders: dict[tuple[int, int], set[str]] = {}
    for core in cores:
        for order, feature_label, _ in core.feature_support:
            holders.setdefault((order, feature_label), set()).add(
                core.partition.tile_id
            )
    return {key: frozenset(tiles) for key, tiles in holders.items()}


def _wide_batches(
    features: tuple[_Feature, ...],
    pairs: tuple[tuple[_Feature, _Feature], ...],
    *,
    holders: Mapping[tuple[int, int], frozenset[str]],
    manifest: PartitionManifest,
    maximum_tiles_per_batch: int,
) -> tuple[_WideBatch, ...]:
    """Name each core wide work can reach, and the work it reaches there.

    A feature's influence can reach only cores within twice its radius of a
    core holding it, and two envelopes can meet only in a core within each
    feature's radius of one of its holders. The cores come from the grid, not
    from a scan, so the cost follows the work rather than the image.
    """
    partitions = {partition.tile_id: partition for partition in manifest.tiles}
    reach: dict[tuple[str, int], frozenset[str]] = {}

    def cores_within(feature: _Feature, radius: int) -> frozenset[str]:
        """Name every core within ``radius`` pixels of one of its holders."""
        key = (feature.feature_id, radius)
        if key not in reach:
            reach[key] = frozenset(
                tile.tile_id
                for tile_id in holders.get(
                    (feature.scale_order, feature.label_value), ()
                )
                for tile in manifest.tiles_meeting(
                    partitions[tile_id].core_bounds.expanded(
                        radius, manifest.image_shape_yx
                    )
                )
            )
        return reach[key]

    features_by_tile: dict[str, list[_Feature]] = {}
    for feature in features:
        for tile_id in cores_within(
            feature, 2 * _scale_radius(feature.scale_order)
        ):
            features_by_tile.setdefault(tile_id, []).append(feature)
    pairs_by_tile: dict[str, list[tuple[_Feature, _Feature]]] = {}
    for first, second in pairs:
        for tile_id in cores_within(
            first, _scale_radius(first.scale_order)
        ) & cores_within(second, _scale_radius(second.scale_order)):
            pairs_by_tile.setdefault(tile_id, []).append((first, second))
    cores = tuple(
        _WideCore(
            partition=partition,
            features=tuple(features_by_tile.get(partition.tile_id, ())),
            pairs=tuple(pairs_by_tile.get(partition.tile_id, ())),
        )
        for partition in manifest.tiles
        if partition.tile_id in features_by_tile
        or partition.tile_id in pairs_by_tile
    )
    return tuple(
        _WideBatch(cores=cores[start : start + maximum_tiles_per_batch])
        for start in range(0, len(cores), maximum_tiles_per_batch)
    )


def _reduce_wide_results(
    batches: tuple[_WideBatch, ...],
    results: tuple[_WideBatchResult, ...],
) -> tuple[dict[str, tuple[str, ...]], frozenset[frozenset[str]]]:
    """Join what every core observed into influences and overlap edges.

    Raises:
        ValueError: If a core the wide work reaches did not answer, which
            would decide an influence or an overlap from part of it.
    """
    requested = {
        core.partition.tile_id for batch in batches for core in batch.cores
    }
    answered = {tile_id for result in results for tile_id in result.tile_ids}
    if answered != requested:
        raise ValueError("every core that wide work reaches must answer")
    influence: dict[str, set[str]] = {}
    for result in results:
        for feature_id, component_ids in result.influence:
            influence.setdefault(feature_id, set()).update(component_ids)
    return (
        {
            feature_id: tuple(sorted(component_ids))
            for feature_id, component_ids in influence.items()
        },
        frozenset(
            frozenset(edge) for result in results for edge in result.edges
        ),
    )


def _features(
    scale_detections: Sequence[ScaleDetections],
    *,
    image_shape_yx: tuple[int, int],
) -> tuple[_Feature, ...]:
    """Name every reconciled scale feature and bound its envelope."""
    return tuple(
        _Feature(
            feature_id=detection.detection_id,
            scale_order=scale.scale_order,
            label_value=label_value,
            bounds=ImageBounds(*detection.bounds_yx),
            envelope_bounds=scale_feature_envelope_bounds(
                ImageBounds(*detection.bounds_yx),
                scale_order=scale.scale_order,
                image_shape_yx=image_shape_yx,
            ),
        )
        for scale in scale_detections
        for label_value, detection in enumerate(scale.detections, start=1)
    )


def _global_support(mapping: TileLabelMapping, local_label: int) -> int:
    """Return the global support component one tile assigns to a label."""
    for candidate, global_label in zip(
        mapping.local_labels, mapping.global_labels, strict=True
    ):
        if candidate == local_label:
            return global_label
    raise ValueError("support mapping must cover every local label")


@dataclass(frozen=True, slots=True)
class _MergedOverlaps:
    """Every core's observations, merged into one set of relations."""

    exact_component_ids: Mapping[str, frozenset[str]]
    finest_features_by_component: Mapping[str, tuple[str, ...]]
    parent_edges: tuple[tuple[str, str], ...]
    support_component_by_feature: Mapping[str, int]
    support_component_by_component: Mapping[str, int]


def _merge_cores(
    cores: tuple[_CoreOverlaps, ...],
    support: ReconciledIslands,
    features: tuple[_Feature, ...],
    records: tuple[DetectionComponentRecord, ...],
) -> _MergedOverlaps:
    """Merge every core's observation into one set of reduced relations."""
    component_id_by_label = {
        record.label_value: record.component_id for record in records
    }
    feature_by_key = {
        (feature.scale_order, feature.label_value): feature
        for feature in features
    }
    components_by_feature: dict[str, set[str]] = {}
    features_by_component: dict[str, dict[int, set[int]]] = {}
    support_by_feature: dict[str, set[int]] = {}
    support_by_component: dict[str, set[int]] = {}
    parent_edges: set[tuple[str, str]] = set()
    for core in cores:
        mapping = support.mapping_for_tile(core.partition.tile_id)
        for component_label, support_label in core.component_support:
            support_by_component.setdefault(
                component_id_by_label[component_label], set()
            ).add(_global_support(mapping, support_label))
        for component_label, order, feature_label in core.component_feature:
            feature = feature_by_key[(order, feature_label)]
            component_id = component_id_by_label[component_label]
            components_by_feature.setdefault(feature.feature_id, set()).add(
                component_id
            )
            features_by_component.setdefault(component_id, {}).setdefault(
                order, set()
            ).add(feature_label)
        for order, feature_label, support_label in core.feature_support:
            support_by_feature.setdefault(
                feature_by_key[(order, feature_label)].feature_id, set()
            ).add(
                0
                if support_label == 0
                else _global_support(mapping, support_label)
            )
        for order, child_label, parent_label in core.parent_links:
            parent_edges.add(
                (
                    feature_by_key[(order, child_label)].feature_id,
                    feature_by_key[(order + 1, parent_label)].feature_id,
                )
            )
    return _MergedOverlaps(
        exact_component_ids={
            feature.feature_id: frozenset(
                components_by_feature.get(feature.feature_id, ())
            )
            for feature in features
        },
        finest_features_by_component={
            record.component_id: _finest_features(
                features_by_component.get(record.component_id, {}),
                feature_by_key,
            )
            for record in records
        },
        parent_edges=tuple(sorted(parent_edges)),
        support_component_by_feature={
            feature.feature_id: _single_support(
                support_by_feature.get(feature.feature_id, set())
            )
            for feature in features
        },
        support_component_by_component={
            component_id: _one_support(occupied)
            for component_id, occupied in support_by_component.items()
        },
    )


def _reduce_overlaps(
    merged: _MergedOverlaps,
    features: tuple[_Feature, ...],
    influence: Mapping[str, tuple[str, ...]],
    edges: frozenset[frozenset[str]],
) -> HierarchyOverlaps:
    """Assemble the reduced relations into the decision's answer set."""
    return HierarchyOverlaps(
        features=tuple(
            FeatureOverlaps(
                feature_id=feature.feature_id,
                scale_order=feature.scale_order,
                exact_component_ids=merged.exact_component_ids[
                    feature.feature_id
                ],
                has_envelope=feature.envelope_bounds is not None,
                influence_component_ids=frozenset(
                    influence.get(feature.feature_id, ())
                ),
                support_component=merged.support_component_by_feature[
                    feature.feature_id
                ],
            )
            for feature in features
        ),
        finest_features_by_component=merged.finest_features_by_component,
        parent_edges=merged.parent_edges,
        support_component_by_component=(merged.support_component_by_component),
        envelope_edges=edges,
    )


def _single_support(occupied: set[int]) -> int:
    """Return the one retained support component holding every pixel."""
    return occupied.pop() if len(occupied) == 1 and 0 not in occupied else 0


def _one_support(occupied: set[int]) -> int:
    """Return one direct owner's support parent, or fail closed."""
    if len(occupied - {0}) != 1 or 0 in occupied:
        raise ValueError(
            "each direct component must occupy one connected support parent"
        )
    return next(iter(occupied))


def _finest_features(
    labels_by_order: Mapping[int, set[int]],
    feature_by_key: Mapping[tuple[int, int], _Feature],
) -> tuple[str, ...]:
    """Return the finest scale's features one direct owner intersects."""
    for order in _SCALE_ORDERS:
        labels = labels_by_order.get(order)
        if not labels:
            continue
        return tuple(
            feature_by_key[(order, label)].feature_id
            for label in sorted(labels)
        )
    return ()


_PRODUCT_NAMES = ("persistent-scale-support",)


def hierarchy_overlap_product_names() -> tuple[str, ...]:
    """Return the canonical published hierarchy-overlap product set."""
    return _PRODUCT_NAMES


@dataclass(frozen=True, slots=True)
class _SupportBatch:
    """One bounded coarse executor task over several cores."""

    partitions: tuple[TilePartition, ...]
    retained_by_scale: tuple[tuple[int, tuple[int, ...]], ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.partitions:
            raise ValueError("persistent support batch must not be empty")


@dataclass(frozen=True, slots=True)
class _SupportBatchResult:
    """Persisted persistent-support chunk identities from one task."""

    product_chunks: tuple[ProductChunk, ...]


def _publish_persistent_support(
    batch: _SupportBatch,
    *,
    detection_source: _CompletedProductSource,
    sink: ZarrProductSink,
) -> _SupportBatchResult:
    """Write the support whose features persist to an adjacent scale.

    Persistence was decided from the reduced overlap edges and the feature
    records, so each core only paints the labels its shard names.
    """
    with detection_source.access_session(), sink.access_session():
        chunks: list[ProductChunk] = []
        for partition in batch.partitions:
            core = partition.core_bounds
            support = np.zeros(core.shape_yx, dtype=np.bool_)
            for scale_order, retained in batch.retained_by_scale:
                support |= persistent_scale_support_window(
                    np.asarray(
                        detection_source.read_completed_window(
                            f"scale-{scale_order}-labels",
                            core,
                        ),
                        dtype=np.int32,
                    ),
                    retained,
                )
            chunks.append(
                sink.write_chunk(
                    product_name="persistent-scale-support",
                    tile=partition,
                    values=support,
                )
            )
        return _SupportBatchResult(product_chunks=tuple(chunks))


def _require_overlap_inputs(
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    manifest: PartitionManifest,
) -> None:
    """Check every identity before any round is submitted."""
    if manifest.halo_yx != (0, 0):
        raise ValueError("hierarchy overlaps read cores without a halo")
    for product_source, names in (
        (
            detection_source,
            (
                "valid-pixels",
                "reconstruction-mask",
                *(f"scale-{order}-labels" for order in _SCALE_ORDERS),
            ),
        ),
        (component_source, ("component-direct-labels",)),
    ):
        if product_source.manifest.image_shape_yx != manifest.image_shape_yx:
            raise ValueError(
                "published generations must match the overlap image shape"
            )
        if not set(names).issubset(
            product_source.read_generation().product_names
        ):
            raise ValueError(
                "published generations must carry every overlap plane read"
            )


def _publish_persistent_scale_support(  # noqa: PLR0913
    manifest: PartitionManifest,
    scale_detections: Sequence[ScaleDetections],
    parent_edges: tuple[tuple[str, str], ...],
    *,
    maximum_tiles_per_batch: int,
    detection_source: _CompletedProductSource,
    executor: Executor,
    sink: ZarrProductSink,
) -> ProductGenerationManifest:
    """Write the support whose features persist to an adjacent scale."""
    retained_by_scale = tuple(
        sorted(
            persistent_scale_labels(
                tuple(scale_detections), parent_edges
            ).items()
        )
    )
    sink.initialize_product(
        product_name="persistent-scale-support",
        dtype=np.dtype(np.bool_),
    )
    results = tuple(
        executor.map_batches(
            partial(
                _publish_persistent_support,
                detection_source=detection_source,
                sink=sink,
            ),
            tuple(
                _SupportBatch(
                    partitions=tuple(
                        manifest.tiles[start : start + maximum_tiles_per_batch]
                    ),
                    retained_by_scale=retained_by_scale,
                )
                for start in range(
                    0, len(manifest.tiles), maximum_tiles_per_batch
                )
            ),
        )
    )
    if not results:
        raise ValueError("executor returned no persistent support results")
    return sink.publish_generation(
        product_names=_PRODUCT_NAMES,
        chunks=(
            chunk for result in results for chunk in result.product_chunks
        ),
    )


def run_hierarchy_overlap_stage(  # noqa: PLR0913
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: HierarchyOverlapStageConfig,
    records: tuple[DetectionComponentRecord, ...],
    scale_detections: Sequence[ScaleDetections],
    executor: Executor,
    sink: ZarrProductSink,
) -> HierarchyOverlapStageResult:
    """Answer every pixel question the source hierarchy decision asks.

    Three rounds and no write. The cores observe which components, features
    and retained support components meet, and the support components are
    reconciled across core boundaries; one task per feature derives that
    feature's reviewed B3 influence inside its own window; and one task per
    candidate pair decides whether two envelopes overlap inside the box that
    holds them both. Candidate pairs follow from the reconciled bounds, so
    only the pairs that can possibly meet read pixels.

    A feature whose influence window, or a pair whose box, exceeds the read
    budget is never read whole. Both are dilations by the reviewed B3
    radius, so each core that the work can reach decides its own pixels
    under that halo, and the parts join exactly.
    """
    _require_overlap_inputs(detection_source, component_source, manifest)
    scan_results = tuple(
        executor.map_batches(
            partial(
                _scan_core_overlaps,
                detection_source=detection_source,
                component_source=component_source,
                image_shape_yx=manifest.image_shape_yx,
            ),
            _core_batches(
                manifest.tiles,
                maximum_tiles_per_batch=config.maximum_tiles_per_batch,
            ),
        )
    )
    if not scan_results:
        raise ValueError("executor returned no overlap scan results")
    cores = tuple(core for result in scan_results for core in result.cores)
    support = reconcile_candidate_tiles(
        manifest,
        tuple(core.summary for core in cores),
    )
    features = _features(
        scale_detections,
        image_shape_yx=manifest.image_shape_yx,
    )
    merged = _merge_cores(cores, support, features, records)
    budget = config.maximum_batch_read_pixels
    candidates = influence_candidate_feature_ids(
        merged.exact_component_ids, merged.parent_edges
    )
    influenced = tuple(
        feature
        for feature in features
        if feature.envelope_bounds is not None
        and feature.feature_id in candidates
    )
    influence_window = partial(
        _influence_window, image_shape_yx=manifest.image_shape_yx
    )
    component_id_by_label = {
        record.label_value: record.component_id for record in records
    }
    influence_batches = _influence_batches(
        tuple(
            feature
            for feature in influenced
            if read_pixels(influence_window(feature)) <= budget
        ),
        maximum_features_per_batch=config.maximum_features_per_batch,
        maximum_batch_read_pixels=budget,
        image_shape_yx=manifest.image_shape_yx,
    )
    influence_results = map_round(
        executor,
        partial(
            _influence_batch,
            detection_source=detection_source,
            component_source=component_source,
            image_shape_yx=manifest.image_shape_yx,
            component_id_by_label=component_id_by_label,
        ),
        influence_batches,
        round_name="feature influence",
    )
    pairs = _candidate_pairs(
        features,
        terminal_scale_order=_SCALE_ORDERS[-1],
    )
    pair_batches = _pair_batches(
        tuple(
            pair
            for pair in pairs
            if read_pixels(_pair_read_bounds_of(pair)) <= budget
        ),
        maximum_pairs_per_batch=config.maximum_pairs_per_batch,
        maximum_batch_read_pixels=budget,
    )
    pair_results = map_round(
        executor,
        partial(_pair_batch, detection_source=detection_source),
        pair_batches,
        round_name="envelope pair",
    )
    wide_batches = _wide_batches(
        tuple(
            feature
            for feature in influenced
            if read_pixels(influence_window(feature)) > budget
        ),
        tuple(
            pair
            for pair in pairs
            if read_pixels(_pair_read_bounds_of(pair)) > budget
        ),
        holders=_feature_holders(cores),
        manifest=manifest,
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    wide_results = map_round(
        executor,
        partial(
            _wide_overlap_batch,
            detection_source=detection_source,
            component_source=component_source,
            image_shape_yx=manifest.image_shape_yx,
            component_id_by_label=component_id_by_label,
        ),
        wide_batches,
        round_name="wide overlap",
    )
    wide_influence, wide_edges = _reduce_wide_results(
        wide_batches, wide_results
    )
    influence = {
        **{
            feature_id: component_ids
            for result in influence_results
            for feature_id, component_ids in result.influence
        },
        **wide_influence,
    }
    edges = wide_edges | frozenset(
        frozenset(edge) for result in pair_results for edge in result.edges
    )
    return HierarchyOverlapStageResult(
        generation=_publish_persistent_scale_support(
            manifest,
            scale_detections,
            merged.parent_edges,
            maximum_tiles_per_batch=config.maximum_tiles_per_batch,
            detection_source=detection_source,
            executor=executor,
            sink=sink,
        ),
        overlaps=_reduce_overlaps(merged, features, influence, edges),
        partition_count=len(manifest.tiles),
        feature_count=len(features),
        enveloped_feature_count=sum(
            1 for feature in features if feature.envelope_bounds is not None
        ),
        candidate_pair_count=len(pairs),
        executor_task_count=(
            2 * len(manifest.tiles)
            + len(influence_batches)
            + len(pair_batches)
            + len(wide_batches)
        ),
        maximum_graph_width=max(
            len(manifest.tiles),
            len(influence_batches),
            len(pair_batches),
            len(wide_batches),
        ),
        reconciliation_round_count=support.reduction_round_count,
        maximum_feature_read_pixels=max(
            (
                *(result.maximum_read_pixels for result in influence_results),
                *(result.maximum_read_pixels for result in pair_results),
                *(result.maximum_read_pixels for result in wide_results),
            ),
            default=0,
        ),
    )
