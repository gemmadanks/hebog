"""Owner-scoped and core-scoped rounds of the tile-native support pass.

ADR-008 splits the support pass because two of its steps are scoped to an
owner rather than to a bounded neighbourhood: restoring an owner whose refined
support cleanup would split, and preserving the previously published regions
that bridge two retained parts of one owner. Each is decided once per owner,
from the window holding that owner, and returns a record; the cores then apply
those records and write the final labels and mask.

Every pixel quantity here is recomputed in the round that needs it rather than
persisted, exactly as the detection pass recomputes its filters instead of
storing a response bank.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from numbers import Integral
from typing import Protocol, TypeVar

import numpy as np
import numpy.typing as npt

from hebog.algorithms.extended_measurement import (
    apply_owner_restores,
    assign_seeded_multiscale_support,
    multiscale_recovery_radius_pixels,
    owner_support_is_split,
    preserve_owner_publication_bridges,
    refine_multiscale_segment_support,
    refine_persistent_publication_support,
    segment_refinement_halo_pixels,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import ProductChunk
from hebog.executors.base import Executor
from hebog.io.zarr import ZarrProductSink

_OwnerResult = TypeVar(
    "_OwnerResult",
    "_RestoreBatchResult",
    "_BridgeBatchResult",
)

_PUBLICATION_PRODUCT_NAMES = (
    "component-labels",
    "measurement-labels",
    "publication-labels",
    "retained-mask",
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
class PublicationStageConfig:
    """Reviewed support thresholds and the bounded task limits."""

    beam: BeamShapePixels
    island_threshold_sigma: float
    minimum_island_pixels: int
    maximum_island_pixels: int | None
    maximum_tiles_per_batch: int
    maximum_batch_read_pixels: int

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
        if (
            isinstance(self.maximum_batch_read_pixels, bool)
            or not isinstance(self.maximum_batch_read_pixels, Integral)
            or self.maximum_batch_read_pixels < 1
        ):
            raise ValueError(
                "maximum_batch_read_pixels must be a positive integer"
            )
        if self.minimum_island_pixels < 1:
            raise ValueError("minimum island pixels must be positive")

    @property
    def halo_pixels(self) -> int:
        """Return the halo every pixel decision in this pass reads."""
        return segment_refinement_halo_pixels(self.beam.major_fwhm_pixels)


@dataclass(frozen=True, slots=True)
class PublicationStageResult:
    """Published support products and scalar execution evidence."""

    generation: ProductGenerationManifest
    accepted_island_count: int
    restored_owner_count: int
    bridged_owner_count: int
    published_owner_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    maximum_owner_read_pixels: int
    maximum_batch_read_pixels: int
    owner_batch_count: int


@dataclass(frozen=True, slots=True)
class _OwnerRequest:
    """One owner, the window holding it, and the read that decides it."""

    label_value: int
    window: ImageBounds
    read_bounds: ImageBounds


@dataclass(frozen=True, slots=True)
class _OwnerBatch:
    """One bounded coarse executor task over several owners.

    The shards name only the owners the batch's own read can contain, so no
    global table crosses the executor boundary.
    """

    requests: tuple[_OwnerRequest, ...]
    read_bounds: ImageBounds
    seed_references_yx: tuple[tuple[int, tuple[int, int]], ...] = ()
    restored_owners: tuple[int, ...] = ()
    published_owners: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.requests:
            raise ValueError("owner batch must not be empty")


@dataclass(frozen=True, slots=True)
class _OwnerBridgePatch:
    """One owner's label corrections, bounded by that owner's window."""

    label_value: int
    published_indices: npt.NDArray[np.int64]
    cleared_indices: npt.NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class _RestoreBatchResult:
    """Owners whose refined support their own window shows to be split."""

    restored_owners: tuple[int, ...]
    maximum_owner_read_pixels: int


@dataclass(frozen=True, slots=True)
class _BridgeBatchResult:
    """Bounded label patches one batch of owners decided."""

    patches: tuple[_OwnerBridgePatch, ...]
    maximum_owner_read_pixels: int


@dataclass(frozen=True, slots=True)
class _TileRequest:
    """One core and the shards of global state its decisions need."""

    partition: TilePartition
    seed_references_yx: tuple[tuple[int, tuple[int, int]], ...]
    restored_owners: tuple[int, ...]
    published_owners: tuple[int, ...] = ()
    accepted_owners: tuple[int, ...] = ()
    patches: tuple[_OwnerBridgePatch, ...] = ()


@dataclass(frozen=True, slots=True)
class _TileBatch:
    """One bounded coarse executor task over several cores."""

    requests: tuple[_TileRequest, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.requests:
            raise ValueError("publication tile batch must not be empty")


@dataclass(frozen=True, slots=True)
class _PublishedOwnerBatchResult:
    """Owners with published support inside the cores of one batch."""

    published_owners: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _PublishBatchResult:
    """Persisted product identities from one executor task."""

    product_chunks: tuple[ProductChunk, ...]


@dataclass(frozen=True, slots=True)
class _ReadPlanes:
    """Every published plane one bounded support decision reads."""

    bounds: ImageBounds
    detection_labels: npt.NDArray[np.int32]
    direct_snr: npt.NDArray[np.float64]
    reconstruction_mask: npt.NDArray[np.bool_]
    valid_pixels: npt.NDArray[np.bool_]
    support_components: npt.NDArray[np.int32]
    persistent_support: npt.NDArray[np.bool_]


def publication_product_names() -> tuple[str, ...]:
    """Return the canonical published support product set."""
    return _PUBLICATION_PRODUCT_NAMES


def _product_dtype(product_name: str) -> np.dtype[np.generic]:
    """Return the stored element type of one published support plane."""
    return (
        np.dtype(np.bool_)
        if product_name == "retained-mask"
        else np.dtype("<i4")
    )


def _read_planes(
    bounds: ImageBounds,
    *,
    detection_source: _CompletedProductSource,
    support_source: _CompletedProductSource,
) -> _ReadPlanes:
    """Read one bounded window of every plane this pass decides from."""
    return _ReadPlanes(
        bounds=bounds,
        detection_labels=np.asarray(
            detection_source.read_completed_window("detection-labels", bounds),
            dtype=np.int32,
        ),
        direct_snr=np.asarray(
            detection_source.read_completed_window("direct-snr", bounds),
            dtype=np.float64,
        ),
        reconstruction_mask=np.asarray(
            detection_source.read_completed_window(
                "reconstruction-mask",
                bounds,
            ),
            dtype=np.bool_,
        ),
        valid_pixels=np.asarray(
            detection_source.read_completed_window("valid-pixels", bounds),
            dtype=np.bool_,
        ),
        support_components=np.asarray(
            support_source.read_completed_window("support-components", bounds),
            dtype=np.int32,
        ),
        persistent_support=np.asarray(
            support_source.read_completed_window("persistent-support", bounds),
            dtype=np.bool_,
        ),
    )


def _refined_support(
    planes: _ReadPlanes,
    config: PublicationStageConfig,
) -> npt.NDArray[np.int32]:
    """Refine direct-owner support over one read, without owner decisions."""
    return refine_multiscale_segment_support(
        planes.detection_labels,
        planes.direct_snr,
        planes.reconstruction_mask,
        beam_major_fwhm_pixels=config.beam.major_fwhm_pixels,
        recovered_minimum_snr=config.island_threshold_sigma,
    )


def _measurement_labels(
    planes: _ReadPlanes,
    config: PublicationStageConfig,
    seed_references_yx: tuple[tuple[int, tuple[int, int]], ...],
) -> npt.NDArray[np.int32]:
    """Attach bounded multiscale support to the owners of one read."""
    return np.asarray(
        assign_seeded_multiscale_support(
            planes.detection_labels,
            planes.reconstruction_mask,
            planes.valid_pixels,
            beam_major_fwhm_pixels=config.beam.major_fwhm_pixels,
            canonical_seed_references_yx=dict(seed_references_yx),
            support_component_labels=planes.support_components,
        ),
        dtype=np.int32,
    )


def _publication_labels(
    planes: _ReadPlanes,
    config: PublicationStageConfig,
    *,
    measurement: npt.NDArray[np.int32],
    restored_owners: tuple[int, ...],
) -> npt.NDArray[np.int32]:
    """Publish immutable direct-owner support over one read."""
    direct_publication = apply_owner_restores(
        planes.detection_labels,
        _refined_support(planes, config),
        restored_owners,
    )
    return np.where(
        (direct_publication > 0) & (measurement > 0),
        measurement,
        0,
    ).astype(np.int32, copy=False)


def _persistent_labels(
    planes: _ReadPlanes,
    *,
    measurement: npt.NDArray[np.int32],
    publication: npt.NDArray[np.int32],
    published_owners: tuple[int, ...],
) -> npt.NDArray[np.int32]:
    """Retain corroborated owner support over one read, per pixel."""
    return refine_persistent_publication_support(
        measurement,
        publication,
        planes.direct_snr,
        planes.persistent_support,
        published_owner_values=np.asarray(published_owners, dtype=np.int32),
    )


def _crop(bounds: ImageBounds, window: ImageBounds) -> tuple[slice, slice]:
    """Return the slices selecting one window inside a wider read."""
    return (
        slice(
            window.y_start - bounds.y_start,
            window.y_stop - bounds.y_start,
        ),
        slice(
            window.x_start - bounds.x_start,
            window.x_stop - bounds.x_start,
        ),
    )


def _decide_restores(
    batch: _OwnerBatch,
    *,
    detection_source: _CompletedProductSource,
    support_source: _CompletedProductSource,
    config: PublicationStageConfig,
) -> _RestoreBatchResult:
    """Decide, per owner, whether cleanup split its refined support."""
    with detection_source.access_session(), support_source.access_session():
        planes = _read_planes(
            batch.read_bounds,
            detection_source=detection_source,
            support_source=support_source,
        )
        refined = _refined_support(planes, config)
        restored = tuple(
            request.label_value
            for request in batch.requests
            if owner_support_is_split(
                refined[_crop(batch.read_bounds, request.window)],
                label_value=request.label_value,
            )
        )
        return _RestoreBatchResult(
            restored_owners=restored,
            maximum_owner_read_pixels=int(np.prod(batch.read_bounds.shape_yx)),
        )


def _scan_published_owners(
    batch: _TileBatch,
    *,
    detection_source: _CompletedProductSource,
    support_source: _CompletedProductSource,
    config: PublicationStageConfig,
) -> _PublishedOwnerBatchResult:
    """Return the owners published inside the cores of one batch."""
    with detection_source.access_session(), support_source.access_session():
        published: set[int] = set()
        for request in batch.requests:
            partition = request.partition
            planes = _read_planes(
                partition.read_bounds,
                detection_source=detection_source,
                support_source=support_source,
            )
            publication = _publication_labels(
                planes,
                config,
                measurement=_measurement_labels(
                    planes,
                    config,
                    request.seed_references_yx,
                ),
                restored_owners=request.restored_owners,
            )
            core = publication[
                _crop(partition.read_bounds, partition.core_bounds)
            ]
            published.update(int(value) for value in np.unique(core) if value)
        return _PublishedOwnerBatchResult(
            published_owners=tuple(sorted(published)),
        )


def _decide_bridges(
    batch: _OwnerBatch,
    *,
    detection_source: _CompletedProductSource,
    support_source: _CompletedProductSource,
    config: PublicationStageConfig,
    image_width: int,
) -> _BridgeBatchResult:
    """Decide, per owner, which previous regions bridge its support."""
    with detection_source.access_session(), support_source.access_session():
        planes = _read_planes(
            batch.read_bounds,
            detection_source=detection_source,
            support_source=support_source,
        )
        measurement = _measurement_labels(
            planes,
            config,
            batch.seed_references_yx,
        )
        publication = _publication_labels(
            planes,
            config,
            measurement=measurement,
            restored_owners=batch.restored_owners,
        )
        persistent = _persistent_labels(
            planes,
            measurement=measurement,
            publication=publication,
            published_owners=batch.published_owners,
        )
        patches: list[_OwnerBridgePatch] = []
        for request in batch.requests:
            crop = _crop(batch.read_bounds, request.window)
            before = persistent[crop]
            after = preserve_owner_publication_bridges(
                publication[crop],
                before,
                label_value=request.label_value,
            )
            patch = _owner_patch(
                before,
                after,
                label_value=request.label_value,
                window=request.window,
                image_width=image_width,
            )
            if patch is not None:
                patches.append(patch)
        return _BridgeBatchResult(
            patches=tuple(patches),
            maximum_owner_read_pixels=int(np.prod(batch.read_bounds.shape_yx)),
        )


def _owner_patch(
    before: npt.NDArray[np.int32],
    after: npt.NDArray[np.int32],
    *,
    label_value: int,
    window: ImageBounds,
    image_width: int,
) -> _OwnerBridgePatch | None:
    """Describe one owner's corrections as global row-major indices."""
    changed = before != after
    if not bool(np.any(changed)):
        return None
    rows, columns = np.nonzero(changed)
    indices = np.asarray(
        (rows + window.y_start) * image_width + columns + window.x_start,
        dtype=np.int64,
    )
    published = after[changed] == label_value
    return _OwnerBridgePatch(
        label_value=label_value,
        published_indices=indices[published],
        cleared_indices=indices[~published],
    )


def _publish_batch(  # noqa: PLR0913
    batch: _TileBatch,
    *,
    detection_source: _CompletedProductSource,
    support_source: _CompletedProductSource,
    sink: ZarrProductSink,
    config: PublicationStageConfig,
    image_width: int,
) -> _PublishBatchResult:
    """Write the accepted support products for one bounded batch of cores."""
    with (
        detection_source.access_session(),
        support_source.access_session(),
        sink.access_session(),
    ):
        chunks: list[ProductChunk] = []
        for request in batch.requests:
            partition = request.partition
            planes = _read_planes(
                partition.read_bounds,
                detection_source=detection_source,
                support_source=support_source,
            )
            measurement = _measurement_labels(
                planes,
                config,
                request.seed_references_yx,
            )
            publication = _publication_labels(
                planes,
                config,
                measurement=measurement,
                restored_owners=request.restored_owners,
            )
            final = _persistent_labels(
                planes,
                measurement=measurement,
                publication=publication,
                published_owners=request.published_owners,
            ).copy()
            _apply_patches(
                final,
                partition=partition,
                patches=request.patches,
                image_width=image_width,
            )
            core = _crop(partition.read_bounds, partition.core_bounds)
            accepted = np.asarray(request.accepted_owners, dtype=np.int32)
            products = _accepted_products(
                planes.detection_labels[core],
                measurement[core],
                final[core],
                accepted=accepted,
            )
            chunks.extend(
                sink.write_chunk(
                    product_name=product_name,
                    tile=partition,
                    values=values,
                )
                for product_name, values in products
            )
        return _PublishBatchResult(product_chunks=tuple(chunks))


def _apply_patches(
    final: npt.NDArray[np.int32],
    *,
    partition: TilePartition,
    patches: tuple[_OwnerBridgePatch, ...],
    image_width: int,
) -> None:
    """Apply the owner corrections this core owns, in canonical order."""
    bounds = partition.read_bounds
    for patch in patches:
        for indices, value in (
            (patch.published_indices, patch.label_value),
            (patch.cleared_indices, 0),
        ):
            if not indices.size:
                continue
            rows, columns = np.divmod(indices, image_width)
            local_rows = rows - bounds.y_start
            local_columns = columns - bounds.x_start
            final[local_rows, local_columns] = value


def _accepted_products(
    detection_labels: npt.NDArray[np.int32],
    measurement: npt.NDArray[np.int32],
    publication: npt.NDArray[np.int32],
    *,
    accepted: npt.NDArray[np.int32],
) -> tuple[tuple[str, npt.NDArray[np.generic]], ...]:
    """Apply the caller's island admission to one owned core."""

    def retain(labels: npt.NDArray[np.int32]) -> npt.NDArray[np.int32]:
        """Keep only the labels the caller's pixel-count limits admit."""
        return np.where(np.isin(labels, accepted), labels, 0).astype(
            np.int32,
            copy=False,
        )

    retained_publication = retain(publication)
    return (
        ("component-labels", retain(detection_labels)),
        ("measurement-labels", retain(measurement)),
        ("publication-labels", retained_publication),
        (
            "retained-mask",
            np.asarray(retained_publication > 0, dtype=np.bool_),
        ),
    )


def _owner_requests(
    detection_islands: tuple[DetectedIsland, ...],
    *,
    image_shape_yx: tuple[int, int],
    recovery_pixels: int,
    halo_pixels: int,
) -> tuple[_OwnerRequest, ...]:
    """Bound each owner's window and the read that decides it exactly.

    Refinement can only reach the recovery radius beyond an owner's direct
    support, and multiscale support the same distance, so the owner's window
    is its reconciled bounds grown by that radius. Deciding it needs one
    further halo, because the window's own pixels are refined values.
    """
    requests: list[_OwnerRequest] = []
    for island in detection_islands:
        window = island.bounds.expanded(recovery_pixels, image_shape_yx)
        requests.append(
            _OwnerRequest(
                label_value=island.global_label,
                window=window,
                read_bounds=window.expanded(halo_pixels, image_shape_yx),
            )
        )
    return tuple(requests)


def _union_bounds(first: ImageBounds, second: ImageBounds) -> ImageBounds:
    """Return the smallest bounds containing both inputs."""
    return ImageBounds(
        min(first.y_start, second.y_start),
        max(first.y_stop, second.y_stop),
        min(first.x_start, second.x_start),
        max(first.x_stop, second.x_stop),
    )


def _owner_batches(
    requests: tuple[_OwnerRequest, ...],
    *,
    maximum_batch_read_pixels: int,
) -> tuple[_OwnerBatch, ...]:
    """Group owners so one read serves several without growing unbounded.

    Owners arrive in canonical row-major order, so neighbours share a read.
    A batch closes as soon as the union of its reads would exceed the
    admitted pixel budget, which keeps one task's memory bounded however the
    owners are distributed.
    """
    batches: list[_OwnerBatch] = []
    grouped: list[_OwnerRequest] = []
    for request in requests:
        candidate = [*grouped, request]
        if (
            grouped
            and int(np.prod(_batch_bounds(candidate).shape_yx))
            > maximum_batch_read_pixels
        ):
            batches.append(_owner_batch(grouped))
            grouped = [request]
            continue
        grouped = candidate
    if grouped:
        batches.append(_owner_batch(grouped))
    return tuple(batches)


def _batch_bounds(requests: list[_OwnerRequest]) -> ImageBounds:
    """Return the one read that serves every owner in a batch."""
    bounds = requests[0].read_bounds
    for request in requests[1:]:
        bounds = _union_bounds(bounds, request.read_bounds)
    return bounds


def _owner_batch(requests: list[_OwnerRequest]) -> _OwnerBatch:
    """Close one batch over the union of its owners' reads."""
    return _OwnerBatch(
        requests=tuple(requests),
        read_bounds=_batch_bounds(requests),
    )


def _intersects(first: ImageBounds, second: ImageBounds) -> bool:
    """Return whether two half-open bounds share a pixel."""
    return (
        first.y_start < second.y_stop
        and second.y_start < first.y_stop
        and first.x_start < second.x_stop
        and second.x_start < first.x_stop
    )


def _seed_shard(
    detection_islands: tuple[DetectedIsland, ...],
    bounds: ImageBounds,
) -> tuple[tuple[int, tuple[int, int]], ...]:
    """Return the canonical reference of every owner this read can hold."""
    return tuple(
        (island.global_label, island.first_pixel_yx)
        for island in detection_islands
        if _intersects(island.bounds, bounds)
    )


def _owner_shard(
    detection_islands: tuple[DetectedIsland, ...],
    selected: frozenset[int],
    bounds: ImageBounds,
) -> tuple[int, ...]:
    """Return the selected owners whose support this read can hold."""
    return tuple(
        island.global_label
        for island in detection_islands
        if island.global_label in selected
        and _intersects(island.bounds, bounds)
    )


def _patch_shard(
    patches: tuple[_OwnerBridgePatch, ...],
    partition: TilePartition,
    *,
    image_width: int,
) -> tuple[_OwnerBridgePatch, ...]:
    """Restrict every owner correction to the core that owns those pixels."""
    core = partition.core_bounds
    shard: list[_OwnerBridgePatch] = []
    for patch in patches:
        selected: list[npt.NDArray[np.int64]] = []
        for indices in (patch.published_indices, patch.cleared_indices):
            rows, columns = np.divmod(indices, image_width)
            selected.append(
                indices[
                    (rows >= core.y_start)
                    & (rows < core.y_stop)
                    & (columns >= core.x_start)
                    & (columns < core.x_stop)
                ]
            )
        if selected[0].size or selected[1].size:
            shard.append(
                _OwnerBridgePatch(
                    label_value=patch.label_value,
                    published_indices=selected[0],
                    cleared_indices=selected[1],
                )
            )
    return tuple(shard)


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


def _accepted_islands(
    detection_islands: tuple[DetectedIsland, ...],
    config: PublicationStageConfig,
) -> frozenset[int]:
    """Apply the caller's pixel-count limits to reconciled island records."""
    return frozenset(
        island.global_label
        for island in detection_islands
        if island.pixel_count >= config.minimum_island_pixels
        and (
            config.maximum_island_pixels is None
            or island.pixel_count <= config.maximum_island_pixels
        )
    )


def _validate_stage_inputs(
    detection_source: _CompletedProductSource,
    support_source: _CompletedProductSource,
    manifest: PartitionManifest,
    config: PublicationStageConfig,
    sink: ZarrProductSink,
) -> None:
    """Fail before output initialization when identities cannot compose."""
    if sink.manifest != manifest:
        raise ValueError("publication sink must use the stage manifest")
    required_halo = config.halo_pixels
    if manifest.halo_yx != (required_halo, required_halo):
        raise ValueError(
            "publication manifest must provide the exact support halo"
        )
    for source, names in (
        (
            detection_source,
            (
                "detection-labels",
                "direct-snr",
                "reconstruction-mask",
                "valid-pixels",
            ),
        ),
        (support_source, ("support-components", "persistent-support")),
    ):
        if source.manifest.image_shape_yx != manifest.image_shape_yx:
            raise ValueError(
                "published generations must match the publication image shape"
            )
        if not set(names).issubset(source.read_generation().product_names):
            raise ValueError(
                "published generations must carry every support plane read"
            )


def run_publication_stage(  # noqa: PLR0913
    detection_source: _CompletedProductSource,
    support_source: _CompletedProductSource,
    manifest: PartitionManifest,
    *,
    detection_islands: tuple[DetectedIsland, ...],
    config: PublicationStageConfig,
    executor: Executor,
    sink: ZarrProductSink,
) -> PublicationStageResult:
    """Decide owner connectivity, then publish the final support products.

    Four rounds, in the order ADR-008 sets out: owners whose refined support
    cleanup would split, the owners published anywhere, the label patches
    that bridge an owner's support, and the cores that apply all three with
    the caller's island admission. Only the last round writes.
    """
    _validate_stage_inputs(
        detection_source,
        support_source,
        manifest,
        config,
        sink,
    )
    image_shape_yx = manifest.image_shape_yx
    image_width = image_shape_yx[1]
    owner_requests = _owner_requests(
        detection_islands,
        image_shape_yx=image_shape_yx,
        recovery_pixels=multiscale_recovery_radius_pixels(
            config.beam.major_fwhm_pixels
        ),
        halo_pixels=config.halo_pixels,
    )
    owner_batches = _owner_batches(
        owner_requests,
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
    )
    restore_results = _map_owner_batches(
        executor,
        owner_batches,
        partial(
            _decide_restores,
            detection_source=detection_source,
            support_source=support_source,
            config=config,
        ),
    )
    restored = frozenset(
        owner for result in restore_results for owner in result.restored_owners
    )

    def tile_request(
        partition: TilePartition,
        **shards: object,
    ) -> _TileRequest:
        """Shard the global decisions to one core's own read."""
        return _TileRequest(
            partition=partition,
            seed_references_yx=_seed_shard(
                detection_islands,
                partition.read_bounds,
            ),
            restored_owners=_owner_shard(
                detection_islands,
                restored,
                partition.read_bounds,
            ),
            **shards,  # type: ignore[arg-type]
        )

    scan_batches = _tile_batches(
        tuple(tile_request(partition) for partition in manifest.tiles),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    scan_results = tuple(
        executor.map_batches(
            partial(
                _scan_published_owners,
                detection_source=detection_source,
                support_source=support_source,
                config=config,
            ),
            scan_batches,
        )
    )
    if not scan_results:
        raise ValueError("executor returned no published-owner results")
    published = frozenset(
        owner for result in scan_results for owner in result.published_owners
    )
    bridge_results = _map_owner_batches(
        executor,
        tuple(
            _OwnerBatch(
                requests=batch.requests,
                read_bounds=batch.read_bounds,
                seed_references_yx=_seed_shard(
                    detection_islands,
                    batch.read_bounds,
                ),
                restored_owners=_owner_shard(
                    detection_islands,
                    restored,
                    batch.read_bounds,
                ),
                published_owners=_owner_shard(
                    detection_islands,
                    published,
                    batch.read_bounds,
                ),
            )
            for batch in owner_batches
        ),
        partial(
            _decide_bridges,
            detection_source=detection_source,
            support_source=support_source,
            config=config,
            image_width=image_width,
        ),
    )
    patches = tuple(
        patch for result in bridge_results for patch in result.patches
    )
    accepted = _accepted_islands(detection_islands, config)
    for product_name in _PUBLICATION_PRODUCT_NAMES:
        sink.initialize_product(
            product_name=product_name,
            dtype=_product_dtype(product_name),
        )
    publish_batches = _tile_batches(
        tuple(
            tile_request(
                partition,
                published_owners=_owner_shard(
                    detection_islands,
                    published,
                    partition.read_bounds,
                ),
                # Both shards are read-scoped, not core-scoped: an owner's
                # recovered support reaches the recovery radius beyond its
                # reconciled bounds, so an owner whose bounds stop just short
                # of this core can still hold pixels inside it. Naming only
                # the owners the core's bounds intersect would clear those
                # pixels, and the published support would move with the tiles.
                accepted_owners=_owner_shard(
                    detection_islands,
                    accepted,
                    partition.read_bounds,
                ),
                patches=_patch_shard(
                    patches,
                    partition,
                    image_width=image_width,
                ),
            )
            for partition in manifest.tiles
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    publish_results = tuple(
        executor.map_batches(
            partial(
                _publish_batch,
                detection_source=detection_source,
                support_source=support_source,
                sink=sink,
                config=config,
                image_width=image_width,
            ),
            publish_batches,
        )
    )
    if not publish_results:
        raise ValueError("executor returned no publication results")
    generation = sink.publish_generation(
        product_names=_PUBLICATION_PRODUCT_NAMES,
        chunks=(
            chunk
            for result in publish_results
            for chunk in result.product_chunks
        ),
    )
    owner_reads = tuple(
        result.maximum_owner_read_pixels
        for result in (*restore_results, *bridge_results)
    )
    return PublicationStageResult(
        generation=generation,
        accepted_island_count=len(accepted),
        restored_owner_count=len(restored),
        bridged_owner_count=len(patches),
        published_owner_count=len(published),
        partition_count=len(manifest.tiles),
        executor_task_count=(
            2 * len(owner_batches) + len(scan_batches) + len(publish_batches)
        ),
        maximum_graph_width=max(
            len(owner_batches),
            len(scan_batches),
            len(publish_batches),
        ),
        maximum_owner_read_pixels=max(owner_reads, default=0),
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
        owner_batch_count=len(owner_batches),
    )


def _map_owner_batches(
    executor: Executor,
    batches: tuple[_OwnerBatch, ...],
    function: Callable[[_OwnerBatch], _OwnerResult],
) -> tuple[_OwnerResult, ...]:
    """Evaluate owner work, tolerating an image with no owner at all."""
    if not batches:
        return ()
    results = tuple(executor.map_batches(function, batches))
    if not results:
        raise ValueError("executor returned no owner-decision results")
    return results
