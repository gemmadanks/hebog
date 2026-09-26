# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Bounded per-object rounds of the tile-native continuum composition.

ADR-008's pass D evaluates each object inside the window that holds it and
reduces the results hierarchically. Component topology is the first of those
rounds: every parent's deblending needs its complete support and nothing
beyond it, so one task decides one parent exactly, and the cores then write
the component labels they own.

Component numbering stays canonical because the driver offsets each parent's
local labels by the components every earlier parent produced, in ascending
parent order, which is the order a whole-plane pass would use. The driver
needs only each parent's component count for that, so no component pixel
reaches it: a core writing a deblended parent decides its memberships again
from the parent's own windows, which gives the same memberships bit for bit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from numbers import Integral
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import binary_dilation
from scipy.ndimage import label as ndimage_label

from hebog.algorithms.astrometry import (
    celestial_wcs_from_header_text,
    compact_geometries_from_wcs,
)
from hebog.algorithms.component_measurement import (
    FitParentMeasurement,
    SupportFeatureGroups,
    compact_window_is_admitted,
    fit_parent_margin_pixels,
    group_support_feature_components,
    measure_fit_parent_components,
    support_feature_margin_pixels,
    support_feature_window,
)
from hebog.algorithms.component_topology import (
    ParentComponentMembership,
    deblend_parent_components,
    parent_is_deferred,
)
from hebog.algorithms.detection import DetectionThresholdMasks
from hebog.algorithms.label_groups import label_extents
from hebog.algorithms.labelling import (
    LocalIslandTileSummary,
    label_detection_tile,
)
from hebog.algorithms.multiscale import ResidualAtrousPlan
from hebog.algorithms.reconciliation import (
    ReconciledIslands,
    TileLabelMapping,
    reconcile_candidate_tiles,
)
from hebog.algorithms.source_association import (
    build_detection_component_record,
    build_detection_component_records,
)
from hebog.config import (
    CompactDeblendConfig,
    CompactGaussianFitConfig,
    CompactMomentConfig,
)
from hebog.data_models.fitting import CompactGaussianFitResult
from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.images import RestoringBeam
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import ProductChunk
from hebog.data_models.source_association import DetectionComponentRecord
from hebog.executors.base import Executor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.stages.batching import (
    WindowBatch,
    batch_object_windows,
    map_round,
    read_pixels,
)

_TOPOLOGY_PRODUCT_NAMES = (
    "component-direct-labels",
    "component-measurement-labels",
)


class _WindowReadable(Protocol):
    """Read bounded global image windows without scheduler state."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


class _CompletedProductSource(Protocol):
    """Read checksum-validated windows from one published generation."""

    @property
    def manifest(self) -> PartitionManifest:
        """Return the source generation's canonical partition."""
        ...

    def read_generation(self) -> ProductGenerationManifest:
        """Validate and return the published completion record."""
        ...

    def read_completed_window(
        self,
        product_name: str,
        bounds: ImageBounds,
    ) -> npt.NDArray[np.generic]:
        """Read one validated bounded product window."""
        ...

    def access_session(self) -> AbstractContextManager[None]:
        """Reuse immutable metadata within one bounded coarse task."""
        ...


@dataclass(frozen=True, slots=True)
class ComponentTopologyStageConfig:
    """Reviewed deblending policy and the bounded task limits."""

    deblend: CompactDeblendConfig
    maximum_tiles_per_batch: int
    maximum_batch_read_pixels: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before stage products are initialized."""
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


@dataclass(frozen=True, slots=True)
class ComponentTopologyStageResult:
    """Published component labels and scalar execution evidence."""

    generation: ProductGenerationManifest
    component_count: int
    parent_count: int
    deblended_parent_count: int
    deferred_parent_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    maximum_parent_read_pixels: int
    parent_batch_count: int


@dataclass(frozen=True, slots=True)
class _ParentExtent:
    """One parent's support in each label plane, reduced over the cores."""

    parent_label: int
    direct_bounds: ImageBounds
    measurement_bounds: ImageBounds
    first_pixel_yx: tuple[int, int]
    direct_pixel_count: int


@dataclass(frozen=True, slots=True)
class _CoreExtent:
    """One parent's bounds and first pixel as one core observes them."""

    parent_label: int
    direct_bounds: ImageBounds | None
    measurement_bounds: ImageBounds
    first_pixel_yx: tuple[int, int] | None
    tile_id: str
    direct_pixel_count: int


@dataclass(frozen=True, slots=True)
class _ExtentBatchResult:
    """Array-free parent extents from one bounded scan task."""

    extents: tuple[_CoreExtent, ...]


@dataclass(frozen=True, slots=True)
class _ParentBatch:
    """One bounded coarse executor task over several parents."""

    parents: tuple[_ParentExtent, ...]
    read_bounds: ImageBounds

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.parents:
            raise ValueError("parent batch must not be empty")


@dataclass(frozen=True, slots=True)
class _ParentCount:
    """How many components one admitted parent deblends into."""

    parent_label: int
    component_count: int
    deferred: bool


@dataclass(frozen=True, slots=True)
class _DeblendBatchResult:
    """The component counts one batch of parents decided."""

    parents: tuple[_ParentCount, ...]
    maximum_parent_read_pixels: int


@dataclass(frozen=True, slots=True)
class _NumberedParent:
    """One deblended parent and the offset of its local component labels."""

    parent: _ParentExtent
    component_offset: int


@dataclass(frozen=True, slots=True)
class _TileRequest:
    """One core and the numbered parents it holds.

    ``single_components`` pairs each parent published as one component with
    that component's label; its pixels are the parent's own support, which
    the core already holds. ``deblended_parents`` are the parents that split,
    in canonical order, which the core decides again from their windows.
    """

    partition: TilePartition
    single_components: tuple[tuple[int, int], ...] = ()
    deblended_parents: tuple[_NumberedParent, ...] = ()


@dataclass(frozen=True, slots=True)
class _TileBatch:
    """One bounded coarse executor task over several cores."""

    requests: tuple[_TileRequest, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.requests:
            raise ValueError("component tile batch must not be empty")


@dataclass(frozen=True, slots=True)
class _PublishBatchResult:
    """Persisted product identities and the labels each plane carried.

    ``observed_labels`` pairs every label a core wrote with the plane that
    carried it — 0 for direct ownership, 1 for measurement ownership — so the
    stage can require both planes to name the same components without holding
    either.
    """

    product_chunks: tuple[ProductChunk, ...]
    observed_labels: tuple[tuple[int, int], ...] = ()
    maximum_parent_read_pixels: int = 0


def component_topology_product_names() -> tuple[str, ...]:
    """Return the canonical published component-topology product set."""
    return _TOPOLOGY_PRODUCT_NAMES


def _union_bounds(
    first: ImageBounds | None,
    second: ImageBounds | None,
) -> ImageBounds | None:
    """Return the smallest bounds containing both inputs, if either exists."""
    if first is None:
        return second
    if second is None:
        return first
    return ImageBounds(
        min(first.y_start, second.y_start),
        max(first.y_stop, second.y_stop),
        min(first.x_start, second.x_start),
        max(first.x_stop, second.x_stop),
    )


def _label_extents(
    labels: npt.NDArray[np.int32],
    bounds: ImageBounds,
) -> dict[int, tuple[ImageBounds, tuple[int, int], int]]:
    """Return each label's bounds, first pixel and size in one owned core."""
    extents = label_extents(labels)
    return {
        int(value): (
            ImageBounds(
                bounds.y_start + int(y_start),
                bounds.y_start + int(y_stop),
                bounds.x_start + int(x_start),
                bounds.x_start + int(x_stop),
            ),
            (bounds.y_start + int(first_y), bounds.x_start + int(first_x)),
            int(pixel_count),
        )
        for (
            value,
            y_start,
            y_stop,
            x_start,
            x_stop,
            first_y,
            first_x,
            pixel_count,
        ) in zip(
            extents.values,
            extents.y_start,
            extents.y_stop,
            extents.x_start,
            extents.x_stop,
            extents.first_y,
            extents.first_x,
            extents.pixel_count,
            strict=True,
        )
    }


def _scan_extents(
    batch: _TileBatch,
    *,
    support_source: _CompletedProductSource,
) -> _ExtentBatchResult:
    """Observe every parent's extent inside the cores of one batch."""
    with support_source.access_session():
        extents: list[_CoreExtent] = []
        for request in batch.requests:
            bounds = request.partition.core_bounds
            direct = _label_extents(
                np.asarray(
                    support_source.read_completed_window(
                        "component-labels",
                        bounds,
                    ),
                    dtype=np.int32,
                ),
                bounds,
            )
            measurement = _label_extents(
                np.asarray(
                    support_source.read_completed_window(
                        "measurement-labels",
                        bounds,
                    ),
                    dtype=np.int32,
                ),
                bounds,
            )
            for parent_label, (
                measurement_bounds,
                _,
                _,
            ) in measurement.items():
                direct_record = direct.get(parent_label)
                extents.append(
                    _CoreExtent(
                        parent_label=parent_label,
                        direct_bounds=(
                            None if direct_record is None else direct_record[0]
                        ),
                        measurement_bounds=measurement_bounds,
                        first_pixel_yx=(
                            None if direct_record is None else direct_record[1]
                        ),
                        tile_id=request.partition.tile_id,
                        direct_pixel_count=(
                            0 if direct_record is None else direct_record[2]
                        ),
                    )
                )
        return _ExtentBatchResult(extents=tuple(extents))


def _reduce_extents(
    results: tuple[_ExtentBatchResult, ...],
) -> tuple[_ParentExtent, ...]:
    """Merge every core's observation into one record per parent."""
    direct: dict[int, ImageBounds | None] = {}
    measurement: dict[int, ImageBounds | None] = {}
    first: dict[int, tuple[int, int] | None] = {}
    direct_pixel_counts: dict[int, int] = {}
    for result in results:
        for extent in result.extents:
            label = extent.parent_label
            direct_pixel_counts[label] = (
                direct_pixel_counts.get(label, 0) + extent.direct_pixel_count
            )
            direct[label] = _union_bounds(
                direct.get(label),
                extent.direct_bounds,
            )
            measurement[label] = _union_bounds(
                measurement.get(label),
                extent.measurement_bounds,
            )
            candidate = extent.first_pixel_yx
            if candidate is not None:
                known = first.get(label)
                first[label] = (
                    candidate if known is None else min(known, candidate)
                )
    parents: list[_ParentExtent] = []
    for label in sorted(measurement):
        direct_bounds = direct.get(label)
        first_pixel = first.get(label)
        measurement_bounds = measurement[label]
        if (
            direct_bounds is None
            or first_pixel is None
            or measurement_bounds is None
        ):
            raise ValueError(
                "every measurement parent must own direct support"
            )
        parents.append(
            _ParentExtent(
                parent_label=label,
                direct_bounds=direct_bounds,
                measurement_bounds=measurement_bounds,
                first_pixel_yx=first_pixel,
                direct_pixel_count=direct_pixel_counts[label],
            )
        )
    return tuple(
        sorted(
            parents,
            key=lambda parent: (parent.first_pixel_yx, parent.parent_label),
        )
    )


def _deferred(parent: _ParentExtent, deblend: CompactDeblendConfig) -> bool:
    """Return whether a parent is deferred, from its reconciled extent."""
    return parent_is_deferred(
        parent.direct_bounds, parent.direct_pixel_count, deblend
    )


def _parent_batches(
    parents: tuple[_ParentExtent, ...],
    *,
    maximum_batch_read_pixels: int,
    deblend: CompactDeblendConfig,
) -> tuple[_ParentBatch, ...]:
    """Group parents so one read serves several, within the budget.

    Deblending needs a parent's whole support at once, and no core can stand
    in for it. The reviewed compact bounds limit that support: a parent
    beyond either is deferred and never reaches a batch, so an admitted
    parent's direct window is within ``maximum_compact_bounds_pixels``, and
    its measurement support reaches no further beyond it than the reviewed
    recovery radius the support pass attaches it within. So a parent wider
    than the read budget is read alone, and its read is bounded by that
    admission, not by the image.

    Raises:
        ValueError: If a deferred parent reaches a batch, which would leave
            its read bounded by nothing.
    """
    return tuple(
        _ParentBatch(parents=batch.objects, read_bounds=batch.read_bounds)
        for batch in batch_object_windows(
            parents,
            window=lambda parent: parent.measurement_bounds,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
            bounded_by_admission=lambda parent: not _deferred(parent, deblend),
        )
    )


def _connected_components(
    mask: npt.NDArray[np.bool_],
) -> npt.NDArray[np.int32]:
    """Label one window's eight-connected components."""
    labels, _ = cast(
        "tuple[npt.NDArray[np.int32], int]",
        ndimage_label(mask, np.ones((3, 3))),
    )
    return labels


def _crop(bounds: ImageBounds, window: ImageBounds) -> tuple[slice, slice]:
    """Return the slices selecting one window inside a wider read."""
    return (
        slice(window.y_start - bounds.y_start, window.y_stop - bounds.y_start),
        slice(window.x_start - bounds.x_start, window.x_stop - bounds.x_start),
    )


def _deblend_parents(
    batch: _ParentBatch,
    *,
    support_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    deblend: CompactDeblendConfig,
    image_shape_yx: tuple[int, int],
) -> tuple[ParentComponentMembership, ...]:
    """Deblend every parent of one batch inside its own windows.

    The caller holds both sources' access sessions open. A parent's windows
    are its reconciled extents, whatever read serves them, so every task that
    deblends one parent decides the same memberships.
    """
    bounds = batch.read_bounds
    direct_snr = np.asarray(
        detection_source.read_completed_window("direct-snr", bounds),
        dtype=np.float64,
    )
    valid = np.asarray(
        detection_source.read_completed_window("valid-pixels", bounds),
        dtype=np.bool_,
    )
    normalized = np.where(valid, direct_snr, np.nan)
    direct_labels = np.asarray(
        support_source.read_completed_window("component-labels", bounds),
        dtype=np.int32,
    )
    measurement_labels = np.asarray(
        support_source.read_completed_window("measurement-labels", bounds),
        dtype=np.int32,
    )
    memberships: list[ParentComponentMembership] = []
    for parent in batch.parents:
        direct_crop = _crop(bounds, parent.direct_bounds)
        measurement_crop = _crop(bounds, parent.measurement_bounds)
        memberships.append(
            deblend_parent_components(
                normalized[direct_crop],
                direct_labels[direct_crop] == parent.parent_label,
                measurement_labels[measurement_crop] == parent.parent_label,
                valid[measurement_crop],
                parent_label=parent.parent_label,
                direct_bounds=parent.direct_bounds,
                measurement_bounds=parent.measurement_bounds,
                image_shape_yx=image_shape_yx,
                first_pixel_yx=parent.first_pixel_yx,
                config=deblend,
            )
        )
    return tuple(memberships)


def _deblend_batch(
    batch: _ParentBatch,
    *,
    support_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    config: ComponentTopologyStageConfig,
    image_shape_yx: tuple[int, int],
) -> _DeblendBatchResult:
    """Count the components every parent of one batch deblends into."""
    with support_source.access_session(), detection_source.access_session():
        memberships = _deblend_parents(
            batch,
            support_source=support_source,
            detection_source=detection_source,
            deblend=config.deblend,
            image_shape_yx=image_shape_yx,
        )
    return _DeblendBatchResult(
        parents=tuple(
            _ParentCount(
                parent_label=parent.parent_label,
                component_count=membership.component_count,
                deferred=membership.deferred,
            )
            for parent, membership in zip(
                batch.parents, memberships, strict=True
            )
        ),
        maximum_parent_read_pixels=read_pixels(batch.read_bounds),
    )


def _numbered_parents(
    parents: tuple[_ParentExtent, ...],
    counts: Mapping[int, _ParentCount],
) -> tuple[dict[int, int], dict[int, int], int]:
    """Offset each parent's local components into canonical global labels.

    ``parents`` is in canonical order, so numbering does not move with tile
    geometry or completion order. A parent absent from ``counts`` is
    deferred, and one component. Returns the label of every parent published
    as one component, the offset of every deblended parent's local labels,
    and the number of components.
    """
    single_components: dict[int, int] = {}
    component_offsets: dict[int, int] = {}
    next_label = 1
    for extent in parents:
        count = counts.get(extent.parent_label)
        component_count = 1 if count is None else count.component_count
        if component_count == 1:
            single_components[extent.parent_label] = next_label
        else:
            component_offsets[extent.parent_label] = next_label - 1
        next_label += component_count
    return single_components, component_offsets, next_label - 1


def _write_requests(
    manifest: PartitionManifest,
    parents: tuple[_ParentExtent, ...],
    *,
    single_components: Mapping[int, int],
    component_offsets: Mapping[int, int],
    holders: Mapping[int, frozenset[str]],
) -> tuple[_TileRequest, ...]:
    """Shard every numbered parent to the cores that hold its pixels.

    Each parent is visited once and appended to its holders, so the shards
    cost the parents' holdings rather than parents times cores.
    """
    held_single: dict[str, list[tuple[int, int]]] = {}
    held_deblended: dict[str, list[_NumberedParent]] = {}
    for extent in parents:
        label = extent.parent_label
        for tile_id in holders[label]:
            if label in single_components:
                held_single.setdefault(tile_id, []).append(
                    (label, single_components[label])
                )
            else:
                held_deblended.setdefault(tile_id, []).append(
                    _NumberedParent(
                        parent=extent,
                        component_offset=component_offsets[label],
                    )
                )
    return tuple(
        _TileRequest(
            partition=partition,
            single_components=tuple(held_single.get(partition.tile_id, ())),
            deblended_parents=tuple(held_deblended.get(partition.tile_id, ())),
        )
        for partition in manifest.tiles
    )


def _relabel_single_parents(
    planes: tuple[npt.NDArray[np.int32], npt.NDArray[np.int32]],
    parent_planes: tuple[npt.NDArray[np.int32], npt.NDArray[np.int32]],
    single_components: tuple[tuple[int, int], ...],
) -> None:
    """Write each single-component parent's label over its pixels, in place.

    Such a parent is published unchanged, so its component is exactly the
    parent's own support in each plane, and the core reads that support
    from its own window instead of receiving the pixels. Parents are looked
    up by sorted label, so one pass over the core serves all of them.
    """
    ordered = sorted(single_components)
    parent_labels = np.asarray([label for label, _ in ordered], dtype=np.int64)
    component_labels = np.asarray(
        [component for _, component in ordered], dtype=np.int32
    )
    for plane, parent_plane in zip(planes, parent_planes, strict=True):
        index = np.searchsorted(parent_labels, parent_plane)
        found = index < parent_labels.size
        found[found] = parent_labels[index[found]] == parent_plane[found]
        plane[found] = component_labels[index[found]]


def _write_owned_components(
    plane: npt.NDArray[np.int32],
    core: ImageBounds,
    window: ImageBounds,
    local_labels: npt.NDArray[np.int32],
    component_offset: int,
) -> None:
    """Write one parent's numbered components over the core pixels it owns."""
    if not _intersects(core, window):
        return
    overlap = ImageBounds(
        max(core.y_start, window.y_start),
        min(core.y_stop, window.y_stop),
        max(core.x_start, window.x_start),
        min(core.x_stop, window.x_stop),
    )
    owned = local_labels[_crop(window, overlap)]
    np.copyto(
        plane[_crop(core, overlap)],
        owned + np.int32(component_offset),
        where=owned > 0,
    )


def _write_deblended_parents(  # noqa: PLR0913
    planes: tuple[npt.NDArray[np.int32], npt.NDArray[np.int32]],
    core: ImageBounds,
    deblended_parents: tuple[_NumberedParent, ...],
    *,
    support_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    config: ComponentTopologyStageConfig,
    image_shape_yx: tuple[int, int],
) -> int:
    """Decide each deblended parent again and write the part a core owns.

    Returns the widest read this took. The parents are admitted, so each
    batch's read is bounded by the budget or by that admission.
    """
    offsets = {
        numbered.parent.parent_label: numbered.component_offset
        for numbered in deblended_parents
    }
    widest_read = 0
    for batch in _parent_batches(
        tuple(numbered.parent for numbered in deblended_parents),
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
        deblend=config.deblend,
    ):
        memberships = _deblend_parents(
            batch,
            support_source=support_source,
            detection_source=detection_source,
            deblend=config.deblend,
            image_shape_yx=image_shape_yx,
        )
        for parent, membership in zip(batch.parents, memberships, strict=True):
            offset = offsets[parent.parent_label]
            _write_owned_components(
                planes[0],
                core,
                parent.direct_bounds,
                membership.direct_labels,
                offset,
            )
            _write_owned_components(
                planes[1],
                core,
                parent.measurement_bounds,
                membership.measurement_labels,
                offset,
            )
        widest_read = max(widest_read, read_pixels(batch.read_bounds))
    return widest_read


def _publish_batch(  # noqa: PLR0913
    batch: _TileBatch,
    *,
    support_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    sink: ZarrProductSink,
    config: ComponentTopologyStageConfig,
    image_shape_yx: tuple[int, int],
) -> _PublishBatchResult:
    """Write the component labels each core of one batch owns.

    The core that writes both planes is where their agreement is decided, so
    it checks it: a direct owner must be scientifically valid and must carry
    the same label in the measurement plane. Asking the same question later
    would need both whole planes at once.

    Raises:
        ValueError: If a core's direct ownership is not a valid subset of its
            measurement ownership.
    """
    with (
        support_source.access_session(),
        detection_source.access_session(),
        sink.access_session(),
    ):
        chunks: list[ProductChunk] = []
        observed: set[tuple[int, int]] = set()
        widest_read = 0
        for request in batch.requests:
            core = request.partition.core_bounds
            direct = np.zeros(core.shape_yx, dtype=np.int32)
            measurement = np.zeros(core.shape_yx, dtype=np.int32)
            if request.single_components:
                _relabel_single_parents(
                    (direct, measurement),
                    (
                        np.asarray(
                            support_source.read_completed_window(
                                "component-labels", core
                            ),
                            dtype=np.int32,
                        ),
                        np.asarray(
                            support_source.read_completed_window(
                                "measurement-labels", core
                            ),
                            dtype=np.int32,
                        ),
                    ),
                    request.single_components,
                )
            if request.deblended_parents:
                widest_read = max(
                    widest_read,
                    _write_deblended_parents(
                        (direct, measurement),
                        core,
                        request.deblended_parents,
                        support_source=support_source,
                        detection_source=detection_source,
                        config=config,
                        image_shape_yx=image_shape_yx,
                    ),
                )
            valid = np.asarray(
                detection_source.read_completed_window("valid-pixels", core),
                dtype=np.bool_,
            )
            if bool(np.any((direct > 0) & (~valid | (measurement != direct)))):
                raise ValueError(
                    "direct component ownership must be a valid subset of "
                    "measurement ownership"
                )
            observed.update(
                (int(value), plane_index)
                for plane_index, plane in enumerate((direct, measurement))
                for value in np.unique(plane)
                if value > 0
            )
            chunks.extend(
                sink.write_chunk(
                    product_name=product_name,
                    tile=request.partition,
                    values=values,
                )
                for product_name, values in zip(
                    _TOPOLOGY_PRODUCT_NAMES, (direct, measurement), strict=True
                )
            )
        return _PublishBatchResult(
            product_chunks=tuple(chunks),
            observed_labels=tuple(sorted(observed)),
            maximum_parent_read_pixels=widest_read,
        )


def _tile_batches(
    requests: tuple[_TileRequest, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_TileBatch, ...]:
    """Group canonical cores without changing scientific ownership."""
    return tuple(
        _TileBatch(requests=requests[start : start + maximum_tiles_per_batch])
        for start in range(0, len(requests), maximum_tiles_per_batch)
    )


def _validate_stage_inputs(
    support_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    manifest: PartitionManifest,
    sink: ZarrProductSink,
) -> None:
    """Fail before output initialization when identities cannot compose."""
    if sink.manifest != manifest:
        raise ValueError("component sink must use the stage manifest")
    if manifest.halo_yx != (0, 0):
        raise ValueError("component topology writes cores without a halo")
    for source, names in (
        (support_source, ("component-labels", "measurement-labels")),
        (detection_source, ("direct-snr", "valid-pixels")),
    ):
        if source.manifest.image_shape_yx != manifest.image_shape_yx:
            raise ValueError(
                "published generations must match the component image shape"
            )
        if not set(names).issubset(source.read_generation().product_names):
            raise ValueError(
                "published generations must carry every component plane read"
            )


def _require_matching_component_identities(
    results: tuple[_PublishBatchResult, ...],
    component_count: int,
) -> None:
    """Require both published planes to name exactly the same components.

    Each core reported the labels it wrote and the plane that carried them, so
    the identity sets are compared from those summaries rather than from two
    whole planes. Every numbered component must appear in both: a component
    with no direct pixel has no identity, and one with no measurement pixel
    has no support to measure.

    Raises:
        ValueError: If the two planes name different components, or name one
            the numbering never produced.
    """
    named: tuple[set[int], set[int]] = (set(), set())
    for result in results:
        for label_value, plane_index in result.observed_labels:
            named[plane_index].add(label_value)
    expected = set(range(1, component_count + 1))
    if named[0] != expected or named[1] != expected:
        raise ValueError(
            "direct and measurement component identities must match"
        )


def run_component_topology_stage(  # noqa: PLR0913
    support_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: ComponentTopologyStageConfig,
    executor: Executor,
    sink: ZarrProductSink,
) -> ComponentTopologyStageResult:
    """Deblend every parent in its own window and publish the components.

    Three rounds: the cores observe each parent's extent, one task per batch
    of parents deblends them inside those extents and counts their
    components, and the cores write the component labels they own. Parent
    order is canonical, so the component numbering does not move with tile
    geometry or completion order.

    The driver holds records only. A parent published as one component is
    its own support in both planes, so the cores that hold it relabel it from
    their own windows. That covers a parent beyond either hard compact-work
    bound, which is deferred exactly as the whole-plane deblender defers it,
    from its extent alone, and whose window is never read. A parent that
    splits is deblended again by each core that holds it, inside the same
    windows, which decides the same memberships; returning them instead
    would make the driver hold every component pixel in the image.
    """
    _validate_stage_inputs(support_source, detection_source, manifest, sink)
    scan_batches = _tile_batches(
        tuple(
            _TileRequest(partition=partition) for partition in manifest.tiles
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    scan_results = tuple(
        executor.map_batches(
            partial(_scan_extents, support_source=support_source),
            scan_batches,
        )
    )
    if not scan_results:
        raise ValueError("executor returned no parent extent results")
    parents = _reduce_extents(scan_results)
    parent_batches = _parent_batches(
        tuple(
            parent
            for parent in parents
            if not _deferred(parent, config.deblend)
        ),
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
        deblend=config.deblend,
    )
    deblend_results = map_round(
        executor,
        partial(
            _deblend_batch,
            support_source=support_source,
            detection_source=detection_source,
            config=config,
            image_shape_yx=manifest.image_shape_yx,
        ),
        parent_batches,
        round_name="component deblend",
    )
    counts = {
        count.parent_label: count
        for result in deblend_results
        for count in result.parents
    }
    single_components, component_offsets, component_count = _numbered_parents(
        parents, counts
    )
    for product_name in _TOPOLOGY_PRODUCT_NAMES:
        sink.initialize_product(
            product_name=product_name,
            dtype=np.dtype("<i4"),
        )
    publish_batches = _tile_batches(
        _write_requests(
            manifest,
            parents,
            single_components=single_components,
            component_offsets=component_offsets,
            holders=_parent_holders(scan_results),
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    publish_results = tuple(
        executor.map_batches(
            partial(
                _publish_batch,
                support_source=support_source,
                detection_source=detection_source,
                sink=sink,
                config=config,
                image_shape_yx=manifest.image_shape_yx,
            ),
            publish_batches,
        )
    )
    if not publish_results:
        raise ValueError("executor returned no component publication results")
    _require_matching_component_identities(publish_results, component_count)
    return ComponentTopologyStageResult(
        generation=sink.publish_generation(
            product_names=_TOPOLOGY_PRODUCT_NAMES,
            chunks=(
                chunk
                for result in publish_results
                for chunk in result.product_chunks
            ),
        ),
        component_count=component_count,
        parent_count=len(parents),
        deblended_parent_count=len(component_offsets),
        deferred_parent_count=len(parents)
        - len(counts)
        + sum(int(count.deferred) for count in counts.values()),
        partition_count=len(manifest.tiles),
        executor_task_count=(
            len(scan_batches) + len(parent_batches) + len(publish_batches)
        ),
        maximum_graph_width=max(
            len(scan_batches),
            len(parent_batches),
            len(publish_batches),
        ),
        maximum_parent_read_pixels=max(
            (
                result.maximum_parent_read_pixels
                for result in (*deblend_results, *publish_results)
            ),
            default=0,
        ),
        parent_batch_count=len(parent_batches),
    )


_FIT_PARENT_PRODUCT_NAMES = ("fit-parent-labels",)


def fit_parent_product_names() -> tuple[str, ...]:
    """Return the canonical published fit-parent product set."""
    return _FIT_PARENT_PRODUCT_NAMES


@dataclass(frozen=True, slots=True)
class FitParentStageConfig:
    """The reviewed fit context margin and the bounded task limit."""

    context_margin_pixels: int
    maximum_tiles_per_batch: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before stage products are initialized."""
        if (
            isinstance(self.maximum_tiles_per_batch, bool)
            or not isinstance(self.maximum_tiles_per_batch, Integral)
            or self.maximum_tiles_per_batch < 1
        ):
            raise ValueError(
                "maximum_tiles_per_batch must be a positive integer"
            )
        if self.context_margin_pixels < 0:
            raise ValueError("context margin must be non-negative")


@dataclass(frozen=True, slots=True)
class FitParentStageResult:
    """Published fit-parent labels and scalar execution evidence."""

    generation: ProductGenerationManifest
    fit_parent_count: int
    context_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    reconciliation_round_count: int


@dataclass(frozen=True, slots=True)
class _ContextLink:
    """One owner seen inside one local fit-context component of a core."""

    owner_label: int
    local_context_label: int


@dataclass(frozen=True, slots=True)
class _ContextTile:
    """Compact per-core fit-context topology safe to return."""

    partition: TilePartition
    summary: LocalIslandTileSummary
    links: tuple[_ContextLink, ...]


@dataclass(frozen=True, slots=True)
class _ContextBatchResult:
    """Array-free fit-context topology from one bounded scan task."""

    tiles: tuple[_ContextTile, ...]


@dataclass(frozen=True, slots=True)
class _ContextPublicationRequest:
    """One core and the fit-parent number each local context carries."""

    partition: TilePartition
    fit_parent_by_local_label: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class _ContextPublicationBatch:
    """One bounded coarse executor task over several cores."""

    requests: tuple[_ContextPublicationRequest, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.requests:
            raise ValueError("fit-parent publication batch must not be empty")


def _fit_context_core(
    partition: TilePartition,
    *,
    component_source: _CompletedProductSource,
    context_margin_pixels: int,
) -> tuple[npt.NDArray[np.bool_], npt.NDArray[np.int32]]:
    """Return one core's fit-context mask and its measurement owners.

    The context is the measurement support dilated by the reviewed margin, so
    a core reads that far beyond itself and nothing further.
    """
    read = partition.read_bounds
    labels = np.asarray(
        component_source.read_completed_window(
            "component-measurement-labels",
            read,
        ),
        dtype=np.int32,
    )
    support = labels > 0
    contexts = (
        np.asarray(
            binary_dilation(
                support,
                structure=np.ones((3, 3), dtype=np.bool_),
                iterations=context_margin_pixels,
            ),
            dtype=np.bool_,
        )
        if context_margin_pixels
        else support
    )
    core = _crop(read, partition.core_bounds)
    return contexts[core], labels[core]


def _scan_contexts(
    batch: _ContextPublicationBatch,
    *,
    component_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
    context_margin_pixels: int,
) -> _ContextBatchResult:
    """Label each core's fit contexts and observe the owners inside them."""
    with component_source.access_session():
        tiles: list[_ContextTile] = []
        for request in batch.requests:
            partition = request.partition
            contexts, labels = _fit_context_core(
                partition,
                component_source=component_source,
                context_margin_pixels=context_margin_pixels,
            )
            tile = label_detection_tile(
                DetectionThresholdMasks(
                    normalized_residual=np.zeros(
                        contexts.shape,
                        dtype=np.float64,
                    ),
                    island_membership=contexts,
                    detection_seeds=contexts,
                    valid_pixel_count=int(np.count_nonzero(contexts)),
                ),
                partition,
                image_shape_yx=image_shape_yx,
            )
            support = labels > 0
            pairs = (
                np.unique(
                    np.column_stack((labels[support], tile.labels[support])),
                    axis=0,
                )
                if bool(np.any(support))
                else np.zeros((0, 2), dtype=np.int32)
            )
            tiles.append(
                _ContextTile(
                    partition=partition,
                    summary=tile.compact_summary(),
                    links=tuple(
                        _ContextLink(
                            owner_label=int(pair[0]),
                            local_context_label=int(pair[1]),
                        )
                        for pair in pairs
                    ),
                )
            )
        return _ContextBatchResult(tiles=tuple(tiles))


class _DisjointContexts:
    """Deterministic union-find over global fit-context labels."""

    def __init__(self, labels: tuple[int, ...]) -> None:
        """Start with every reconciled context as its own fit parent."""
        self._parent = {label: label for label in labels}

    def find(self, label: int) -> int:
        """Return a canonical root with path compression."""
        parent = self._parent[label]
        while parent != self._parent[parent]:
            parent = self._parent[parent]
        while label != parent:
            self._parent[label], label = parent, self._parent[label]
        return parent

    def union(self, first: int, second: int) -> None:
        """Join two contexts under the smaller label."""
        first_root, second_root = self.find(first), self.find(second)
        if first_root == second_root:
            return
        root, child = sorted((first_root, second_root))
        self._parent[child] = root

    def fit_parent_numbers(self) -> dict[int, int]:
        """Number the joined contexts by their smallest global label.

        A whole-plane pass numbers connected components by the smallest node
        index each contains, and reconciled context labels ascend with their
        canonical first pixel, so this reproduces that order exactly.
        """
        roots = sorted({self.find(label) for label in self._parent})
        numbers = {root: index for index, root in enumerate(roots, start=1)}
        return {
            label: numbers[self.find(label)] for label in sorted(self._parent)
        }


def _fit_parent_numbers(
    tiles: tuple[_ContextTile, ...],
    contexts: ReconciledIslands,
) -> dict[int, int]:
    """Join the contexts one owner's support reaches, then number them."""
    components = _DisjointContexts(
        tuple(island.global_label for island in contexts.islands)
    )
    for tile in tiles:
        mapping = contexts.mapping_for_tile(tile.partition.tile_id)
        by_owner: dict[int, list[int]] = {}
        for link in tile.links:
            by_owner.setdefault(link.owner_label, []).append(
                _global_context(mapping, link.local_context_label)
            )
        for joined in by_owner.values():
            for follower in joined[1:]:
                components.union(joined[0], follower)
    return components.fit_parent_numbers()


def _global_context(mapping: TileLabelMapping, local_label: int) -> int:
    """Return the global context one tile assigns to a local label."""
    for candidate, global_label in zip(
        mapping.local_labels,
        mapping.global_labels,
        strict=True,
    ):
        if candidate == local_label:
            return global_label
    raise ValueError("fit-context mapping must cover every local label")


def _publish_fit_parents(
    batch: _ContextPublicationBatch,
    *,
    component_source: _CompletedProductSource,
    sink: ZarrProductSink,
    image_shape_yx: tuple[int, int],
    context_margin_pixels: int,
) -> _PublishBatchResult:
    """Write the fit-parent number each core's support belongs to."""
    with component_source.access_session(), sink.access_session():
        chunks: list[ProductChunk] = []
        for request in batch.requests:
            partition = request.partition
            contexts, labels = _fit_context_core(
                partition,
                component_source=component_source,
                context_margin_pixels=context_margin_pixels,
            )
            local = label_detection_tile(
                DetectionThresholdMasks(
                    normalized_residual=np.zeros(
                        contexts.shape,
                        dtype=np.float64,
                    ),
                    island_membership=contexts,
                    detection_seeds=contexts,
                    valid_pixel_count=int(np.count_nonzero(contexts)),
                ),
                partition,
                image_shape_yx=image_shape_yx,
            )
            numbers = dict(request.fit_parent_by_local_label)
            values = np.zeros(contexts.shape, dtype=np.int32)
            for local_label, fit_parent in numbers.items():
                values[local.labels == local_label] = fit_parent
            chunks.append(
                sink.write_chunk(
                    product_name="fit-parent-labels",
                    tile=partition,
                    values=np.where(labels > 0, values, 0).astype(
                        np.int32,
                        copy=False,
                    ),
                )
            )
        return _PublishBatchResult(product_chunks=tuple(chunks))


def _context_batches(
    requests: tuple[_ContextPublicationRequest, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_ContextPublicationBatch, ...]:
    """Group canonical cores without changing scientific ownership."""
    return tuple(
        _ContextPublicationBatch(
            requests=requests[start : start + maximum_tiles_per_batch]
        )
        for start in range(0, len(requests), maximum_tiles_per_batch)
    )


def run_fit_parent_stage(
    component_source: _CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: FitParentStageConfig,
    executor: Executor,
    sink: ZarrProductSink,
) -> FitParentStageResult:
    """Reconcile the fit contexts owners share and publish their numbers.

    Owners whose contexts touch need a joint model, and that connectivity
    follows a chain of any length, so it is reconciled from compact per-core
    summaries before any fit runs. The cores then write the fit-parent number
    each support pixel belongs to.
    """
    if sink.manifest != manifest:
        raise ValueError("fit-parent sink must use the stage manifest")
    required_halo = config.context_margin_pixels
    if manifest.halo_yx != (required_halo, required_halo):
        raise ValueError(
            "fit-parent manifest must provide the exact context margin"
        )
    if component_source.manifest.image_shape_yx != manifest.image_shape_yx:
        raise ValueError(
            "component generation must match the fit-parent image shape"
        )
    if "component-measurement-labels" not in (
        component_source.read_generation().product_names
    ):
        raise ValueError(
            "component generation must publish measurement component labels"
        )
    scan_batches = _context_batches(
        tuple(
            _ContextPublicationRequest(
                partition=partition,
                fit_parent_by_local_label=(),
            )
            for partition in manifest.tiles
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    scan_results = tuple(
        executor.map_batches(
            partial(
                _scan_contexts,
                component_source=component_source,
                image_shape_yx=manifest.image_shape_yx,
                context_margin_pixels=config.context_margin_pixels,
            ),
            scan_batches,
        )
    )
    if not scan_results:
        raise ValueError("executor returned no fit-context results")
    tiles = tuple(tile for result in scan_results for tile in result.tiles)
    contexts = reconcile_candidate_tiles(
        manifest,
        tuple(tile.summary for tile in tiles),
    )
    numbers = _fit_parent_numbers(tiles, contexts)
    sink.initialize_product(
        product_name="fit-parent-labels",
        dtype=np.dtype("<i4"),
    )
    publish_batches = _context_batches(
        tuple(
            _ContextPublicationRequest(
                partition=tile.partition,
                fit_parent_by_local_label=tuple(
                    (
                        local_label,
                        numbers[
                            _global_context(
                                contexts.mapping_for_tile(
                                    tile.partition.tile_id
                                ),
                                local_label,
                            )
                        ],
                    )
                    for local_label in contexts.mapping_for_tile(
                        tile.partition.tile_id
                    ).local_labels
                ),
            )
            for tile in tiles
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    publish_results = tuple(
        executor.map_batches(
            partial(
                _publish_fit_parents,
                component_source=component_source,
                sink=sink,
                image_shape_yx=manifest.image_shape_yx,
                context_margin_pixels=config.context_margin_pixels,
            ),
            publish_batches,
        )
    )
    if not publish_results:
        raise ValueError("executor returned no fit-parent publication results")
    return FitParentStageResult(
        generation=sink.publish_generation(
            product_names=_FIT_PARENT_PRODUCT_NAMES,
            chunks=(
                chunk
                for result in publish_results
                for chunk in result.product_chunks
            ),
        ),
        fit_parent_count=len(set(numbers.values())),
        context_count=len(contexts.islands),
        partition_count=len(manifest.tiles),
        executor_task_count=len(scan_batches) + len(publish_batches),
        maximum_graph_width=max(len(scan_batches), len(publish_batches)),
        reconciliation_round_count=contexts.reduction_round_count,
    )


_MEASUREMENT_PRODUCT_NAMES = ("measurement-support",)


def component_fit_product_names() -> tuple[str, ...]:
    """Return the canonical published component-fit product set."""
    return _MEASUREMENT_PRODUCT_NAMES


@dataclass(frozen=True, slots=True)
class ComponentFitStageConfig:
    """Reviewed measurement policy and the bounded task limits."""

    moment: CompactMomentConfig
    fit: CompactGaussianFitConfig
    atrous_plan: ResidualAtrousPlan
    detection_sigma: float
    island_sigma: float
    minimum_pixels: int
    maximum_bounds_pixels: int
    minimum_support_fraction: float
    maximum_tiles_per_batch: int
    maximum_batch_read_pixels: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before stage products are initialized."""
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
        """Return the context a fit parent reads beyond its own support."""
        return fit_parent_margin_pixels(self.fit, self.atrous_plan)


@dataclass(frozen=True, slots=True)
class ComponentFitStageResult:
    """Published measurement support and every fit parent's records.

    ``component_records`` describes every direct component the association
    decision reads, in canonical first-pixel order. The parent that reads a
    component's pixels builds it: the residual, the validity and both
    component planes are already on that task, so nothing after the fits
    reads a component's window again.
    """

    generation: ProductGenerationManifest
    parents: tuple[FitParentMeasurement, ...]
    component_records: tuple[DetectionComponentRecord, ...]
    fit_parent_count: int
    deferred_parent_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    maximum_parent_read_pixels: int
    parent_batch_count: int


@dataclass(frozen=True, slots=True)
class _FitParentExtent:
    """One fit parent's support bounds and the window that measures it."""

    parent_index: int
    read_bounds: ImageBounds


@dataclass(frozen=True, slots=True)
class _FitBatch:
    """One bounded coarse executor task over several fit parents."""

    parents: tuple[_FitParentExtent, ...]
    read_bounds: ImageBounds

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.parents:
            raise ValueError("fit batch must not be empty")


@dataclass(frozen=True, slots=True)
class _FitBatchResult:
    """Bounded measurement records one batch of fit parents produced."""

    parents: tuple[tuple[int, FitParentMeasurement], ...]
    component_records: tuple[DetectionComponentRecord, ...]
    maximum_parent_read_pixels: int


@dataclass(frozen=True, slots=True)
class _SupportRequest:
    """One core and the bounded support windows that cover it."""

    partition: TilePartition
    patches: tuple[tuple[ImageBounds, npt.NDArray[np.bool_]], ...]


@dataclass(frozen=True, slots=True)
class _SupportBatch:
    """One bounded coarse executor task over several cores."""

    requests: tuple[_SupportRequest, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.requests:
            raise ValueError("support batch must not be empty")


@dataclass(frozen=True, slots=True)
class _DeferredCore:
    """One core and the deferred fit parents whose components it holds."""

    partition: TilePartition
    parent_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _DeferredBatch:
    """One bounded coarse executor task over the cores of deferred parents."""

    cores: tuple[_DeferredCore, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.cores:
            raise ValueError("deferred component batch must not be empty")


@dataclass(frozen=True, slots=True)
class _ComponentPiece:
    """One component's direct pixels in one core, in raster order.

    ``raster_indices`` are global ``y * width + x`` positions, so pieces
    from several cores sort back into the order one window presents them in.
    """

    label_value: int
    raster_indices: npt.NDArray[np.int64]
    residual: npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class _DeferredBatchResult:
    """The deferred parents' component pixels one batch of cores held."""

    pieces: tuple[_ComponentPiece, ...]
    tile_ids: tuple[str, ...]
    maximum_core_read_pixels: int


def _scan_fit_parent_extents(
    batch: _SupportBatch,
    *,
    fit_parent_source: _CompletedProductSource,
) -> _ExtentBatchResult:
    """Observe every fit parent's extent inside the cores of one batch."""
    with fit_parent_source.access_session():
        extents: list[_CoreExtent] = []
        for request in batch.requests:
            bounds = request.partition.core_bounds
            for parent_index, (
                parent_bounds,
                first,
                pixel_count,
            ) in _label_extents(
                np.asarray(
                    fit_parent_source.read_completed_window(
                        "fit-parent-labels",
                        bounds,
                    ),
                    dtype=np.int32,
                ),
                bounds,
            ).items():
                extents.append(
                    _CoreExtent(
                        parent_label=parent_index,
                        direct_bounds=parent_bounds,
                        measurement_bounds=parent_bounds,
                        first_pixel_yx=first,
                        tile_id=request.partition.tile_id,
                        direct_pixel_count=pixel_count,
                    )
                )
        return _ExtentBatchResult(extents=tuple(extents))


def _fit_batches(
    parents: tuple[_FitParentExtent, ...],
    *,
    maximum_batch_read_pixels: int,
    maximum_bounds_pixels: int,
) -> tuple[_FitBatch, ...]:
    """Group fit parents so one read serves several, within the budget.

    A joint fit needs a parent's whole window at once, and no core can stand
    in for it. The reviewed compact bound limits that window: a parent beyond
    it is deferred and never reaches a batch. So a parent wider than the
    read budget is read alone, and its read is bounded by that admission,
    not by the image.

    Raises:
        ValueError: If a parent beyond the reviewed bound reaches a batch,
            which would leave its read bounded by nothing.
    """
    return tuple(
        _FitBatch(parents=batch.objects, read_bounds=batch.read_bounds)
        for batch in batch_object_windows(
            parents,
            window=lambda parent: parent.read_bounds,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
            bounded_by_admission=lambda parent: compact_window_is_admitted(
                parent.read_bounds,
                maximum_bounds_pixels=maximum_bounds_pixels,
            ),
        )
    )


def _fit_batch(  # noqa: PLR0913
    batch: _FitBatch,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    fit_parent_source: _CompletedProductSource,
    config: ComponentFitStageConfig,
    wcs_header_text: str,
    beam: RestoringBeam,
    image_shape_yx: tuple[int, int],
) -> _FitBatchResult:
    """Fit every parent of one batch inside its own context window."""
    wcs = celestial_wcs_from_header_text(wcs_header_text)
    with (
        background_rms_source.access_session(),
        detection_source.access_session(),
        component_source.access_session(),
        fit_parent_source.access_session(),
    ):
        bounds = batch.read_bounds
        window = source.read_window(bounds)
        if window.bounds != bounds:
            raise ValueError("image source returned different fit-read bounds")
        background = np.asarray(
            background_rms_source.read_completed_window("background", bounds),
            dtype=np.float64,
        )
        residual = np.asarray(window.values, dtype=np.float64) - background
        rms = np.asarray(
            background_rms_source.read_completed_window("rms", bounds),
            dtype=np.float64,
        )
        valid = np.asarray(
            detection_source.read_completed_window("valid-pixels", bounds),
            dtype=np.bool_,
        )
        fit_parents = np.asarray(
            fit_parent_source.read_completed_window(
                "fit-parent-labels",
                bounds,
            ),
            dtype=np.int32,
        )
        direct = np.asarray(
            component_source.read_completed_window(
                "component-direct-labels",
                bounds,
            ),
            dtype=np.int32,
        )
        measurement = np.asarray(
            component_source.read_completed_window(
                "component-measurement-labels",
                bounds,
            ),
            dtype=np.int32,
        )
        # One conversion for the batch. Astropy pays its frame machinery per
        # call, not per position, so deriving each parent's geometry inside
        # the fit costs more than the fit does.
        geometries = compact_geometries_from_wcs(
            beam,
            wcs,
            tuple(parent.read_bounds.center_xy for parent in batch.parents),
        )
        measured: list[tuple[int, FitParentMeasurement]] = []
        records: list[DetectionComponentRecord] = []
        for parent, geometry in zip(batch.parents, geometries, strict=True):
            crop = _crop(bounds, parent.read_bounds)
            records.extend(
                _parent_component_records(
                    residual[crop],
                    valid[crop],
                    fit_parents[crop],
                    direct[crop],
                    parent,
                )
            )
            measured.append(
                (
                    parent.parent_index,
                    measure_fit_parent_components(
                        residual[crop],
                        rms[crop],
                        valid[crop],
                        fit_parents[crop],
                        direct[crop],
                        measurement[crop],
                        geometry,
                        config.moment,
                        config.fit,
                        parent_index=parent.parent_index,
                        bounds=parent.read_bounds,
                        image_shape_yx=image_shape_yx,
                        detection_sigma=config.detection_sigma,
                        island_sigma=config.island_sigma,
                        minimum_pixels=config.minimum_pixels,
                        maximum_bounds_pixels=config.maximum_bounds_pixels,
                        atrous_plan=config.atrous_plan,
                        minimum_support_fraction=(
                            config.minimum_support_fraction
                        ),
                    ),
                )
            )
        return _FitBatchResult(
            parents=tuple(measured),
            component_records=tuple(records),
            maximum_parent_read_pixels=int(np.prod(bounds.shape_yx)),
        )


def _parent_component_records(
    residual_window: npt.NDArray[np.float64],
    valid_window: npt.NDArray[np.bool_],
    fit_parent_window: npt.NDArray[np.int32],
    direct_window: npt.NDArray[np.int32],
    parent: _FitParentExtent,
) -> tuple[DetectionComponentRecord, ...]:
    """Describe the direct components one fit parent owns, from its own read.

    Every array covers that parent's support and the reviewed context margin
    around it. A component's direct support lies inside the measurement
    support this parent was dilated from, so the window holds each owned
    component entirely and the record costs the component's own pixels. The
    margin can expose a neighbour's pixels, so only the components standing
    on this parent's support are described.
    """
    return build_detection_component_records(
        np.where(
            fit_parent_window == parent.parent_index,
            direct_window,
            0,
        ).astype(np.int32, copy=False),
        residual_window,
        valid_window,
        origin_yx=(parent.read_bounds.y_start, parent.read_bounds.x_start),
    )


def _parent_holders(
    results: tuple[_ExtentBatchResult, ...],
) -> dict[int, frozenset[str]]:
    """Name the cores in which each parent holds a pixel."""
    holders: dict[int, set[str]] = {}
    for result in results:
        for extent in result.extents:
            holders.setdefault(extent.parent_label, set()).add(extent.tile_id)
    return {label: frozenset(tiles) for label, tiles in holders.items()}


def _deferred_batches(
    deferred: tuple[_FitParentExtent, ...],
    holders: dict[int, frozenset[str]],
    manifest: PartitionManifest,
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_DeferredBatch, ...]:
    """Name each core holding a deferred parent, and which parents it holds."""
    parents_by_tile: dict[str, list[int]] = {}
    for parent in deferred:
        for tile_id in holders[parent.parent_index]:
            parents_by_tile.setdefault(tile_id, []).append(parent.parent_index)
    cores = tuple(
        _DeferredCore(
            partition=partition,
            parent_indexes=tuple(sorted(parents_by_tile[partition.tile_id])),
        )
        for partition in manifest.tiles
        if partition.tile_id in parents_by_tile
    )
    return tuple(
        _DeferredBatch(cores=cores[start : start + maximum_tiles_per_batch])
        for start in range(0, len(cores), maximum_tiles_per_batch)
    )


def _gather_deferred_components(  # noqa: PLR0913
    batch: _DeferredBatch,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    fit_parent_source: _CompletedProductSource,
    image_width: int,
) -> _DeferredBatchResult:
    """Return the direct pixels of deferred parents' components, per core.

    A deferred parent is not fitted, so nothing needs its window: the record
    of each component it owns reads only that component's own pixels, which
    every core holding them returns with global raster indices.

    Raises:
        ValueError: If the image source answers with other bounds, or a
            component owns a pixel that is not scientifically valid.
    """
    with (
        background_rms_source.access_session(),
        detection_source.access_session(),
        component_source.access_session(),
        fit_parent_source.access_session(),
    ):
        pieces: list[_ComponentPiece] = []
        maximum_read_pixels = 0
        for core in batch.cores:
            bounds = core.partition.core_bounds
            window = source.read_window(bounds)
            if window.bounds != bounds:
                raise ValueError(
                    "image source returned different fit-read bounds"
                )
            residual = np.asarray(
                window.values, dtype=np.float64
            ) - np.asarray(
                background_rms_source.read_completed_window(
                    "background", bounds
                ),
                dtype=np.float64,
            )
            valid = np.asarray(
                detection_source.read_completed_window("valid-pixels", bounds),
                dtype=np.bool_,
            )
            direct = np.asarray(
                component_source.read_completed_window(
                    "component-direct-labels", bounds
                ),
                dtype=np.int32,
            )
            owned = (direct > 0) & np.isin(
                np.asarray(
                    fit_parent_source.read_completed_window(
                        "fit-parent-labels", bounds
                    ),
                    dtype=np.int32,
                ),
                core.parent_indexes,
            )
            if bool(np.any(owned & ~valid)):
                raise ValueError(
                    "component owner pixels must be scientifically valid"
                )
            rows, columns = np.nonzero(owned)
            labels = direct[rows, columns]
            raster_indices = (
                (rows.astype(np.int64) + bounds.y_start) * image_width
                + columns
                + bounds.x_start
            )
            values = residual[rows, columns]
            # Boolean selection keeps each component's pixels in the raster
            # order this core holds them in.
            for label_value in np.unique(labels):
                selected = labels == label_value
                pieces.append(
                    _ComponentPiece(
                        label_value=int(label_value),
                        raster_indices=raster_indices[selected],
                        residual=values[selected],
                    )
                )
            maximum_read_pixels = max(maximum_read_pixels, read_pixels(bounds))
        return _DeferredBatchResult(
            pieces=tuple(pieces),
            tile_ids=tuple(core.partition.tile_id for core in batch.cores),
            maximum_core_read_pixels=maximum_read_pixels,
        )


def _deferred_component_records(
    batches: tuple[_DeferredBatch, ...],
    results: tuple[_DeferredBatchResult, ...],
    *,
    image_width: int,
) -> tuple[DetectionComponentRecord, ...]:
    """Describe every component of a deferred parent from its cores' pieces.

    The pieces are put back in raster order, which is the order a window
    over the component presents its pixels, so each record is the one that
    window would build, bit for bit.

    Raises:
        ValueError: If a core that holds a deferred parent did not answer,
            which would describe its components from part of their pixels.
    """
    requested = {
        core.partition.tile_id for batch in batches for core in batch.cores
    }
    answered = {tile_id for result in results for tile_id in result.tile_ids}
    if answered != requested:
        raise ValueError(
            "every core holding a deferred fit parent must answer"
        )
    pieces: dict[int, list[_ComponentPiece]] = {}
    for result in results:
        for piece in result.pieces:
            pieces.setdefault(piece.label_value, []).append(piece)
    records: list[DetectionComponentRecord] = []
    for label_value, parts in sorted(pieces.items()):
        raster_indices = np.concatenate(
            [part.raster_indices for part in parts]
        )
        order = np.argsort(raster_indices, kind="stable")
        records.append(
            build_detection_component_record(
                label_value,
                raster_indices[order],
                np.concatenate([part.residual for part in parts])[order],
                image_width=image_width,
            )
        )
    return tuple(records)


def _publish_support(
    batch: _SupportBatch,
    *,
    sink: ZarrProductSink,
) -> _PublishBatchResult:
    """Combine every fit parent's support patch over the cores it reaches."""
    with sink.access_session():
        chunks: list[ProductChunk] = []
        for request in batch.requests:
            core = request.partition.core_bounds
            values = np.zeros(core.shape_yx, dtype=np.bool_)
            for patch_bounds, patch in request.patches:
                overlap = ImageBounds(
                    max(core.y_start, patch_bounds.y_start),
                    min(core.y_stop, patch_bounds.y_stop),
                    max(core.x_start, patch_bounds.x_start),
                    min(core.x_stop, patch_bounds.x_stop),
                )
                values[_crop(core, overlap)] |= patch[
                    _crop(patch_bounds, overlap)
                ]
            chunks.append(
                sink.write_chunk(
                    product_name="measurement-support",
                    tile=request.partition,
                    values=values,
                )
            )
        return _PublishBatchResult(product_chunks=tuple(chunks))


def _support_batches(
    requests: tuple[_SupportRequest, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_SupportBatch, ...]:
    """Group canonical cores without changing scientific ownership."""
    return tuple(
        _SupportBatch(
            requests=requests[start : start + maximum_tiles_per_batch]
        )
        for start in range(0, len(requests), maximum_tiles_per_batch)
    )


def _intersects(first: ImageBounds, second: ImageBounds) -> bool:
    """Return whether two half-open bounds share a pixel."""
    return (
        first.y_start < second.y_stop
        and second.y_start < first.y_stop
        and first.x_start < second.x_stop
        and second.x_start < first.x_stop
    )


def _reduce_component_records(
    component_records: Iterable[DetectionComponentRecord],
    *,
    component_count: int,
) -> tuple[DetectionComponentRecord, ...]:
    """Order every parent's component records canonically, once.

    Completion order decides nothing: the records are sorted by canonical
    first pixel, which is how a whole-plane pass over the direct labels would
    present them. The topology stage numbered the direct components
    ``1..component_count`` and required both of its planes to name exactly
    those, so the records must describe each of them once.

    Raises:
        ValueError: If two fit parents described the same component, which
            would mean a component's support reached beyond the parent whose
            measurement support it belongs to, or if the records do not
            describe exactly the published components, which would mean a
            fit parent's read missed a component that the association would
            otherwise silently lose.
    """
    records = tuple(
        sorted(
            component_records,
            key=lambda record: record.canonical_pixel_yx,
        )
    )
    described = {record.label_value for record in records}
    if len(described) != len(records):
        raise ValueError("every component must belong to one fit parent")
    if described != set(range(1, component_count + 1)):
        raise ValueError("fit parents must describe every published component")
    return records


def run_component_fit_stage(  # noqa: PLR0913, PLR0917
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    fit_parent_source: _CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: ComponentFitStageConfig,
    component_count: int,
    wcs_header_text: str,
    beam: RestoringBeam,
    executor: Executor,
    sink: ZarrProductSink,
) -> ComponentFitStageResult:
    """Fit every parent in its own context window and publish its support.

    Three rounds: the cores observe each fit parent's extent, one task per
    batch of parents measures them inside that extent plus the reviewed
    context margin, and the cores combine the support patches the parents
    contributed. Only the last round writes.

    The measuring round also describes the direct components each parent
    owns, because the residual and the validity those records need are
    already on the task that fits them.

    A parent whose window the reviewed compact bound refuses is deferred, as
    the whole-plane pass defers it, so its window is never read. Its
    components are described instead from the pixels each core holding them
    returns, restored to raster order, which gives the records a window would
    give, bit for bit. No read is then wider than the budget, one core, or
    one window that bound admits, whichever is largest.

    ``component_count`` is the count the topology stage that published
    ``component_source`` returned. The records must describe exactly those
    components, so a fit-parent read that misses one stops the stage rather
    than publishing fewer components.

    ``wcs_header_text`` is the caller's own header as
    :meth:`astropy.io.fits.Header.tostring` writes it, not a ``WCS``; see
    :func:`~hebog.algorithms.astrometry.celestial_wcs_from_header_text`.
    """
    if sink.manifest != manifest:
        raise ValueError("component fit sink must use the stage manifest")
    if manifest.halo_yx != (0, 0):
        raise ValueError("measurement support writes cores without a halo")
    for product_source, names in (
        (background_rms_source, ("background", "rms")),
        (detection_source, ("valid-pixels",)),
        (
            component_source,
            ("component-direct-labels", "component-measurement-labels"),
        ),
        (fit_parent_source, ("fit-parent-labels",)),
    ):
        if product_source.manifest.image_shape_yx != manifest.image_shape_yx:
            raise ValueError(
                "published generations must match the fit image shape"
            )
        if not set(names).issubset(
            product_source.read_generation().product_names
        ):
            raise ValueError(
                "published generations must carry every fit plane read"
            )
    image_shape_yx = manifest.image_shape_yx
    margin = config.margin_pixels
    scan_batches = _support_batches(
        tuple(
            _SupportRequest(partition=partition, patches=())
            for partition in manifest.tiles
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    scan_results = tuple(
        executor.map_batches(
            partial(
                _scan_fit_parent_extents,
                fit_parent_source=fit_parent_source,
            ),
            scan_batches,
        )
    )
    if not scan_results:
        raise ValueError("executor returned no fit-parent extent results")
    extents = tuple(
        _FitParentExtent(
            parent_index=parent.parent_label,
            read_bounds=parent.direct_bounds.expanded(margin, image_shape_yx),
        )
        for parent in sorted(
            _reduce_extents(scan_results),
            key=lambda item: item.parent_label,
        )
    )
    fitted = tuple(
        extent
        for extent in extents
        if compact_window_is_admitted(
            extent.read_bounds,
            maximum_bounds_pixels=config.maximum_bounds_pixels,
        )
    )
    deferred = tuple(
        extent
        for extent in extents
        if not compact_window_is_admitted(
            extent.read_bounds,
            maximum_bounds_pixels=config.maximum_bounds_pixels,
        )
    )
    fit_batches = _fit_batches(
        fitted,
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
        maximum_bounds_pixels=config.maximum_bounds_pixels,
    )
    fit_results = map_round(
        executor,
        partial(
            _fit_batch,
            source=source,
            background_rms_source=background_rms_source,
            detection_source=detection_source,
            component_source=component_source,
            fit_parent_source=fit_parent_source,
            config=config,
            wcs_header_text=wcs_header_text,
            beam=beam,
            image_shape_yx=image_shape_yx,
        ),
        fit_batches,
        round_name="component fit",
    )
    deferred_batches = _deferred_batches(
        deferred,
        _parent_holders(scan_results),
        manifest,
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    deferred_results = map_round(
        executor,
        partial(
            _gather_deferred_components,
            source=source,
            background_rms_source=background_rms_source,
            detection_source=detection_source,
            component_source=component_source,
            fit_parent_source=fit_parent_source,
            image_width=image_shape_yx[1],
        ),
        deferred_batches,
        round_name="deferred component",
    )
    measured = tuple(
        sorted(
            (
                *(item for result in fit_results for item in result.parents),
                *(
                    (parent.parent_index, FitParentMeasurement(deferred=True))
                    for parent in deferred
                ),
            ),
            key=lambda item: item[0],
        )
    )
    component_records = _reduce_component_records(
        (
            *(
                record
                for result in fit_results
                for record in result.component_records
            ),
            *_deferred_component_records(
                deferred_batches,
                deferred_results,
                image_width=image_shape_yx[1],
            ),
        ),
        component_count=component_count,
    )
    patches = tuple(
        (parent.support_bounds, parent.support_window)
        for _, parent in measured
        if parent.support_bounds is not None
        and parent.support_window is not None
    )
    sink.initialize_product(
        product_name="measurement-support",
        dtype=np.dtype(np.bool_),
    )
    publish_batches = _support_batches(
        tuple(
            _SupportRequest(
                partition=partition,
                patches=tuple(
                    (bounds, window)
                    for bounds, window in patches
                    if _intersects(bounds, partition.core_bounds)
                ),
            )
            for partition in manifest.tiles
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    publish_results = tuple(
        executor.map_batches(
            partial(_publish_support, sink=sink),
            publish_batches,
        )
    )
    if not publish_results:
        raise ValueError("executor returned no support publication results")
    return ComponentFitStageResult(
        generation=sink.publish_generation(
            product_names=_MEASUREMENT_PRODUCT_NAMES,
            chunks=(
                chunk
                for result in publish_results
                for chunk in result.product_chunks
            ),
        ),
        parents=tuple(parent for _, parent in measured),
        component_records=component_records,
        fit_parent_count=len(extents),
        deferred_parent_count=sum(
            int(parent.deferred) for _, parent in measured
        ),
        partition_count=len(manifest.tiles),
        executor_task_count=(
            len(scan_batches)
            + len(fit_batches)
            + len(deferred_batches)
            + len(publish_batches)
        ),
        maximum_graph_width=max(
            len(scan_batches),
            len(fit_batches),
            len(deferred_batches),
            len(publish_batches),
        ),
        maximum_parent_read_pixels=max(
            (
                *(result.maximum_parent_read_pixels for result in fit_results),
                *(
                    result.maximum_core_read_pixels
                    for result in deferred_results
                ),
            ),
            default=0,
        ),
        parent_batch_count=len(fit_batches),
    )


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
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    measurement_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
) -> _FeatureBatchResult:
    """Label each core's support features and observe the owners inside."""
    with (
        detection_source.access_session(),
        component_source.access_session(),
        measurement_source.access_session(),
    ):
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
                        for component_label, (bounds, _, _) in _label_extents(
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
                known = _union_bounds(merged.get(component_label), bounds)
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
    maximum_batch_read_pixels: int,
    maximum_bounds_pixels: int,
    fits: tuple[tuple[int, CompactGaussianFitResult], ...],
    protected_labels: frozenset[int],
    component_bounds: dict[int, ImageBounds],
) -> tuple[_GroupBatch, ...]:
    """Group features so one read serves several, within the budget.

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
            maximum_batch_read_pixels=maximum_batch_read_pixels,
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
        if _intersects(bounds, batch.read_bounds)
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
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    measurement_source: _CompletedProductSource,
    config: ExtendedGroupStageConfig,
    wcs_header_text: str,
    beam: RestoringBeam,
) -> _GroupBatchResult:
    """Group every support feature of one batch inside its own window."""
    wcs = celestial_wcs_from_header_text(wcs_header_text)
    with (
        background_rms_source.access_session(),
        detection_source.access_session(),
        component_source.access_session(),
        measurement_source.access_session(),
    ):
        bounds = batch.read_bounds
        window = source.read_window(bounds)
        if window.bounds != bounds:
            raise ValueError(
                "image source returned different group-read bounds"
            )
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
            crop = _crop(bounds, feature.window)
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
                        minimum_support_fraction=(
                            config.minimum_support_fraction
                        ),
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
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    measurement_source: _CompletedProductSource,
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
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
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
