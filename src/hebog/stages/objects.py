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
parent order, which is the order a whole-plane pass would use.
"""

from __future__ import annotations

from collections.abc import Sequence
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
    fit_parent_margin_pixels,
    group_support_feature_components,
    measure_fit_parent_components,
    support_feature_margin_pixels,
    support_feature_window,
)
from hebog.algorithms.component_topology import deblend_parent_components
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


@dataclass(frozen=True, slots=True)
class _CoreExtent:
    """One parent's bounds and first pixel as one core observes them."""

    parent_label: int
    direct_bounds: ImageBounds | None
    measurement_bounds: ImageBounds
    first_pixel_yx: tuple[int, int] | None


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
class _ParentComponents:
    """One parent's component pixels, as global row-major indices."""

    parent_label: int
    component_count: int
    deblended: bool
    deferred: bool
    direct_indices: npt.NDArray[np.int64]
    direct_components: npt.NDArray[np.int32]
    measurement_indices: npt.NDArray[np.int64]
    measurement_components: npt.NDArray[np.int32]


@dataclass(frozen=True, slots=True)
class _DeblendBatchResult:
    """Bounded component memberships one batch of parents decided."""

    parents: tuple[_ParentComponents, ...]
    maximum_parent_read_pixels: int


@dataclass(frozen=True, slots=True)
class _TileRequest:
    """One core and the component pixels it owns."""

    partition: TilePartition
    direct_indices: npt.NDArray[np.int64]
    direct_labels: npt.NDArray[np.int32]
    measurement_indices: npt.NDArray[np.int64]
    measurement_labels: npt.NDArray[np.int32]


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
    """Persisted product identities from one executor task."""

    product_chunks: tuple[ProductChunk, ...]


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
) -> dict[int, tuple[ImageBounds, tuple[int, int]]]:
    """Return each label's bounds and first pixel inside one owned core."""
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
        )
        for value, y_start, y_stop, x_start, x_stop, first_y, first_x in zip(
            extents.values,
            extents.y_start,
            extents.y_stop,
            extents.x_start,
            extents.x_stop,
            extents.first_y,
            extents.first_x,
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
    for result in results:
        for extent in result.extents:
            label = extent.parent_label
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
            )
        )
    return tuple(
        sorted(
            parents,
            key=lambda parent: (parent.first_pixel_yx, parent.parent_label),
        )
    )


def _parent_batches(
    parents: tuple[_ParentExtent, ...],
    *,
    maximum_batch_read_pixels: int,
) -> tuple[_ParentBatch, ...]:
    """Group parents so one read serves several without growing unbounded."""
    batches: list[_ParentBatch] = []
    grouped: list[_ParentExtent] = []
    for parent in parents:
        candidate = [*grouped, parent]
        if (
            grouped
            and int(np.prod(_batch_bounds(candidate).shape_yx))
            > maximum_batch_read_pixels
        ):
            batches.append(_parent_batch(grouped))
            grouped = [parent]
            continue
        grouped = candidate
    if grouped:
        batches.append(_parent_batch(grouped))
    return tuple(batches)


def _batch_bounds(parents: list[_ParentExtent]) -> ImageBounds:
    """Return the one read that serves every parent in a batch."""
    bounds = parents[0].measurement_bounds
    for parent in parents[1:]:
        merged = _union_bounds(bounds, parent.measurement_bounds)
        if merged is None:  # pragma: no cover - both bounds always exist
            raise ValueError("parent batch bounds must exist")
        bounds = merged
    return bounds


def _parent_batch(parents: list[_ParentExtent]) -> _ParentBatch:
    """Close one batch over the union of its parents' reads."""
    return _ParentBatch(
        parents=tuple(parents),
        read_bounds=_batch_bounds(parents),
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


def _sparse_components(
    labels: npt.NDArray[np.int32],
    window: ImageBounds,
    *,
    image_width: int,
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int32]]:
    """Describe one parent's component pixels as global row-major indices."""
    rows, columns = np.nonzero(labels > 0)
    return (
        np.asarray(
            (rows + window.y_start) * image_width + columns + window.x_start,
            dtype=np.int64,
        ),
        np.asarray(labels[rows, columns], dtype=np.int32),
    )


def _deblend_batch(
    batch: _ParentBatch,
    *,
    support_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    config: ComponentTopologyStageConfig,
    image_shape_yx: tuple[int, int],
) -> _DeblendBatchResult:
    """Deblend every parent of one batch inside its own windows."""
    with support_source.access_session(), detection_source.access_session():
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
            support_source.read_completed_window(
                "measurement-labels",
                bounds,
            ),
            dtype=np.int32,
        )
        image_width = image_shape_yx[1]
        parents: list[_ParentComponents] = []
        for parent in batch.parents:
            direct_crop = _crop(bounds, parent.direct_bounds)
            measurement_crop = _crop(bounds, parent.measurement_bounds)
            membership = deblend_parent_components(
                normalized[direct_crop],
                direct_labels[direct_crop] == parent.parent_label,
                measurement_labels[measurement_crop] == parent.parent_label,
                valid[measurement_crop],
                parent_label=parent.parent_label,
                direct_bounds=parent.direct_bounds,
                measurement_bounds=parent.measurement_bounds,
                image_shape_yx=image_shape_yx,
                first_pixel_yx=parent.first_pixel_yx,
                config=config.deblend,
            )
            direct_indices, direct_components = _sparse_components(
                membership.direct_labels,
                parent.direct_bounds,
                image_width=image_width,
            )
            measurement_indices, measurement_components = _sparse_components(
                membership.measurement_labels,
                parent.measurement_bounds,
                image_width=image_width,
            )
            parents.append(
                _ParentComponents(
                    parent_label=parent.parent_label,
                    component_count=membership.component_count,
                    deblended=membership.deblended,
                    deferred=membership.deferred,
                    direct_indices=direct_indices,
                    direct_components=direct_components,
                    measurement_indices=measurement_indices,
                    measurement_components=measurement_components,
                )
            )
        return _DeblendBatchResult(
            parents=tuple(parents),
            maximum_parent_read_pixels=int(np.prod(bounds.shape_yx)),
        )


@dataclass(frozen=True, slots=True)
class _ComponentPixels:
    """Every component pixel of one plane, in canonical parent order."""

    indices: npt.NDArray[np.int64]
    labels: npt.NDArray[np.int32]


def _numbered_components(
    parents: tuple[_ParentComponents, ...],
) -> tuple[_ComponentPixels, _ComponentPixels, int]:
    """Offset each parent's local components into canonical global labels."""
    direct_indices: list[npt.NDArray[np.int64]] = []
    direct_labels: list[npt.NDArray[np.int32]] = []
    measurement_indices: list[npt.NDArray[np.int64]] = []
    measurement_labels: list[npt.NDArray[np.int32]] = []
    next_label = 1
    for parent in parents:
        offset = np.int32(next_label - 1)
        direct_indices.append(parent.direct_indices)
        direct_labels.append(parent.direct_components + offset)
        measurement_indices.append(parent.measurement_indices)
        measurement_labels.append(parent.measurement_components + offset)
        next_label += parent.component_count
    return (
        _ComponentPixels(
            indices=_concatenated_indices(direct_indices),
            labels=_concatenated_labels(direct_labels),
        ),
        _ComponentPixels(
            indices=_concatenated_indices(measurement_indices),
            labels=_concatenated_labels(measurement_labels),
        ),
        next_label - 1,
    )


def _concatenated_indices(
    arrays: Sequence[npt.NDArray[np.int64]],
) -> npt.NDArray[np.int64]:
    """Join bounded per-parent index arrays into one canonical sequence."""
    if not arrays:
        return np.zeros(0, dtype=np.int64)
    return np.concatenate(arrays).astype(np.int64, copy=False)


def _concatenated_labels(
    arrays: Sequence[npt.NDArray[np.int32]],
) -> npt.NDArray[np.int32]:
    """Join bounded per-parent label arrays into one canonical sequence."""
    if not arrays:
        return np.zeros(0, dtype=np.int32)
    return np.concatenate(arrays).astype(np.int32, copy=False)


def _core_shard(
    pixels: _ComponentPixels,
    partition: TilePartition,
    *,
    image_width: int,
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int32]]:
    """Restrict component pixels to the core that owns them."""
    core = partition.core_bounds
    rows, columns = np.divmod(pixels.indices, image_width)
    inside = (
        (rows >= core.y_start)
        & (rows < core.y_stop)
        & (columns >= core.x_start)
        & (columns < core.x_stop)
    )
    return pixels.indices[inside], pixels.labels[inside]


def _publish_request(
    partition: TilePartition,
    direct_pixels: _ComponentPixels,
    measurement_pixels: _ComponentPixels,
    *,
    image_width: int,
) -> _TileRequest:
    """Shard every component pixel to the core that owns it."""
    direct_indices, direct_labels = _core_shard(
        direct_pixels,
        partition,
        image_width=image_width,
    )
    measurement_indices, measurement_labels = _core_shard(
        measurement_pixels,
        partition,
        image_width=image_width,
    )
    return _TileRequest(
        partition=partition,
        direct_indices=direct_indices,
        direct_labels=direct_labels,
        measurement_indices=measurement_indices,
        measurement_labels=measurement_labels,
    )


def _publish_batch(
    batch: _TileBatch,
    *,
    sink: ZarrProductSink,
    image_width: int,
) -> _PublishBatchResult:
    """Write the component labels each core of one batch owns."""
    with sink.access_session():
        chunks: list[ProductChunk] = []
        for request in batch.requests:
            core = request.partition.core_bounds
            products: list[tuple[str, npt.NDArray[np.int32]]] = []
            for product_name, indices, labels in (
                (
                    "component-direct-labels",
                    request.direct_indices,
                    request.direct_labels,
                ),
                (
                    "component-measurement-labels",
                    request.measurement_indices,
                    request.measurement_labels,
                ),
            ):
                values = np.zeros(core.shape_yx, dtype=np.int32)
                if indices.size:
                    rows, columns = np.divmod(indices, image_width)
                    values[
                        rows - core.y_start,
                        columns - core.x_start,
                    ] = labels
                products.append((product_name, values))
            chunks.extend(
                sink.write_chunk(
                    product_name=product_name,
                    tile=request.partition,
                    values=values,
                )
                for product_name, values in products
            )
        return _PublishBatchResult(product_chunks=tuple(chunks))


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
    of parents deblends them inside those extents, and the cores write the
    component labels they own. Parent order is canonical, so the component
    numbering does not move with tile geometry or completion order.
    """
    _validate_stage_inputs(support_source, detection_source, manifest, sink)
    image_width = manifest.image_shape_yx[1]
    scan_batches = _tile_batches(
        tuple(
            _TileRequest(
                partition=partition,
                direct_indices=np.zeros(0, dtype=np.int64),
                direct_labels=np.zeros(0, dtype=np.int32),
                measurement_indices=np.zeros(0, dtype=np.int64),
                measurement_labels=np.zeros(0, dtype=np.int32),
            )
            for partition in manifest.tiles
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
        parents,
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
    )
    deblend_results: tuple[_DeblendBatchResult, ...] = ()
    if parent_batches:
        deblend_results = tuple(
            executor.map_batches(
                partial(
                    _deblend_batch,
                    support_source=support_source,
                    detection_source=detection_source,
                    config=config,
                    image_shape_yx=manifest.image_shape_yx,
                ),
                parent_batches,
            )
        )
        if not deblend_results:
            raise ValueError("executor returned no component deblend results")
    deblended = tuple(
        parent for result in deblend_results for parent in result.parents
    )
    direct_pixels, measurement_pixels, component_count = _numbered_components(
        deblended
    )
    for product_name in _TOPOLOGY_PRODUCT_NAMES:
        sink.initialize_product(
            product_name=product_name,
            dtype=np.dtype("<i4"),
        )
    publish_batches = _tile_batches(
        tuple(
            _publish_request(
                partition,
                direct_pixels,
                measurement_pixels,
                image_width=image_width,
            )
            for partition in manifest.tiles
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    publish_results = tuple(
        executor.map_batches(
            partial(_publish_batch, sink=sink, image_width=image_width),
            publish_batches,
        )
    )
    if not publish_results:
        raise ValueError("executor returned no component publication results")
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
        deblended_parent_count=sum(
            int(parent.deblended) for parent in deblended
        ),
        deferred_parent_count=sum(
            int(parent.deferred) for parent in deblended
        ),
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
            (result.maximum_parent_read_pixels for result in deblend_results),
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
            for parent_index, (parent_bounds, first) in _label_extents(
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
                    )
                )
        return _ExtentBatchResult(extents=tuple(extents))


def _fit_batches(
    parents: tuple[_FitParentExtent, ...],
    *,
    maximum_batch_read_pixels: int,
) -> tuple[_FitBatch, ...]:
    """Group fit parents so one read serves several, within the budget."""
    batches: list[_FitBatch] = []
    grouped: list[_FitParentExtent] = []
    for parent in parents:
        candidate = [*grouped, parent]
        if (
            grouped
            and int(np.prod(_fit_batch_bounds(candidate).shape_yx))
            > maximum_batch_read_pixels
        ):
            batches.append(
                _FitBatch(
                    parents=tuple(grouped),
                    read_bounds=_fit_batch_bounds(grouped),
                )
            )
            grouped = [parent]
            continue
        grouped = candidate
    if grouped:
        batches.append(
            _FitBatch(
                parents=tuple(grouped),
                read_bounds=_fit_batch_bounds(grouped),
            )
        )
    return tuple(batches)


def _fit_batch_bounds(parents: list[_FitParentExtent]) -> ImageBounds:
    """Return the one read that serves every fit parent in a batch."""
    bounds = parents[0].read_bounds
    for parent in parents[1:]:
        merged = _union_bounds(bounds, parent.read_bounds)
        if merged is None:  # pragma: no cover - both bounds always exist
            raise ValueError("fit batch bounds must exist")
        bounds = merged
    return bounds


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
    results: tuple[_FitBatchResult, ...],
) -> tuple[DetectionComponentRecord, ...]:
    """Order every parent's component records canonically, once.

    Completion order decides nothing: the records are sorted by canonical
    first pixel, which is how a whole-plane pass over the direct labels would
    present them.

    Raises:
        ValueError: If two fit parents described the same component, which
            would mean a component's support reached beyond the parent whose
            measurement support it belongs to.
    """
    records = tuple(
        sorted(
            (
                record
                for result in results
                for record in result.component_records
            ),
            key=lambda record: record.canonical_pixel_yx,
        )
    )
    if len({record.label_value for record in records}) != len(records):
        raise ValueError("every component must belong to one fit parent")
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
    fit_batches = _fit_batches(
        extents,
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
    )
    fit_results: tuple[_FitBatchResult, ...] = ()
    if fit_batches:
        fit_results = tuple(
            executor.map_batches(
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
            )
        )
        if not fit_results:
            raise ValueError("executor returned no component fit results")
    measured = tuple(
        parent
        for result in fit_results
        for parent in sorted(result.parents, key=lambda item: item[0])
    )
    component_records = _reduce_component_records(fit_results)
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
            len(scan_batches) + len(fit_batches) + len(publish_batches)
        ),
        maximum_graph_width=max(
            len(scan_batches),
            len(fit_batches),
            len(publish_batches),
        ),
        maximum_parent_read_pixels=max(
            (result.maximum_parent_read_pixels for result in fit_results),
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
                        for component_label, (bounds, _) in _label_extents(
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


def _group_batches(
    features: tuple[SupportFeature, ...],
    *,
    maximum_batch_read_pixels: int,
    fits: tuple[tuple[int, CompactGaussianFitResult], ...],
    protected_labels: frozenset[int],
    component_bounds: dict[int, ImageBounds],
) -> tuple[_GroupBatch, ...]:
    """Group features so one read serves several, within the budget."""
    shard = partial(
        _sharded_batch,
        fits=fits,
        protected_labels=protected_labels,
        component_bounds=component_bounds,
    )
    batches: list[_GroupBatch] = []
    grouped: list[SupportFeature] = []
    for feature in features:
        candidate = [*grouped, feature]
        if (
            grouped
            and int(np.prod(_group_batch_bounds(candidate).shape_yx))
            > maximum_batch_read_pixels
        ):
            batches.append(shard(grouped))
            grouped = [feature]
            continue
        grouped = candidate
    if grouped:
        batches.append(shard(grouped))
    return tuple(batches)


def _sharded_batch(
    features: list[SupportFeature],
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
    read_bounds = _group_batch_bounds(features)
    reachable = frozenset(
        component_label
        for component_label, bounds in component_bounds.items()
        if _intersects(bounds, read_bounds)
    )
    return _GroupBatch(
        features=tuple(features),
        read_bounds=read_bounds,
        fits=tuple(item for item in fits if item[0] in reachable),
        protected_labels=protected_labels & reachable,
    )


def _group_batch_bounds(features: list[SupportFeature]) -> ImageBounds:
    """Return the one read that serves every feature in a batch."""
    bounds = features[0].window
    for feature in features[1:]:
        merged = _union_bounds(bounds, feature.window)
        if merged is None:  # pragma: no cover - both bounds always exist
            raise ValueError("group batch bounds must exist")
        bounds = merged
    return bounds


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
