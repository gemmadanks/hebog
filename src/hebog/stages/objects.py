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
from typing import Protocol

import numpy as np
import numpy.typing as npt

from hebog.algorithms.component_topology import deblend_parent_components
from hebog.config import CompactDeblendConfig
from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import ProductChunk
from hebog.executors.base import Executor
from hebog.io.zarr import ZarrProductSink

_TOPOLOGY_PRODUCT_NAMES = (
    "component-direct-labels",
    "component-measurement-labels",
)


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
    extents: dict[int, tuple[ImageBounds, tuple[int, int]]] = {}
    present = np.unique(labels)
    for value in present:
        label_value = int(value)
        if label_value <= 0:
            continue
        rows, columns = np.nonzero(labels == label_value)
        extents[label_value] = (
            ImageBounds(
                bounds.y_start + int(rows.min()),
                bounds.y_start + int(rows.max()) + 1,
                bounds.x_start + int(columns.min()),
                bounds.x_start + int(columns.max()) + 1,
            ),
            (
                bounds.y_start + int(rows[0]),
                bounds.x_start + int(columns[0]),
            ),
        )
    return extents


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
