# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Scheduler-facing rounds that own the continuum catalogue's source planes.

ADR-008's catalogue rounds decide one object at a time. The owners a source
holds are a record map, so the cores write the source labels from the shard
that reaches them; the persistent support a source owns spans tiles, so it is
reconciled first and then assigned inside each connected component's own
window.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from numbers import Integral
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import label as ndimage_label

from hebog.algorithms.detection import DetectionThresholdMasks
from hebog.algorithms.extended_measurement import (
    assign_connected_source_support,
    nearest_source_seed_labels,
)
from hebog.algorithms.labelling import (
    LocalIslandTile,
    LocalIslandTileSummary,
    label_detection_tile,
)
from hebog.algorithms.reconciliation import (
    apply_tile_label_mapping,
    reconcile_candidate_tiles,
)
from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import ProductChunk
from hebog.executors.base import Executor
from hebog.io.zarr import ZarrProductSink
from hebog.stages.batching import (
    HeldObjects,
    batch_object_windows,
    cores_holding,
    map_round,
    read_pixels,
)

_LABEL_PRODUCT_NAMES = ("source-labels",)
_SUPPORT_PRODUCT_NAMES = ("source-measurement-labels",)


def source_label_product_names() -> tuple[str, ...]:
    """Return the canonical published source-label product set."""
    return _LABEL_PRODUCT_NAMES


def source_support_product_names() -> tuple[str, ...]:
    """Return the canonical published source-support product set."""
    return _SUPPORT_PRODUCT_NAMES


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
class SourceLabelStageConfig:
    """The bounded task limit of the source-label rounds."""

    maximum_tiles_per_batch: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before any product is initialized."""
        if (
            isinstance(self.maximum_tiles_per_batch, bool)
            or not isinstance(self.maximum_tiles_per_batch, Integral)
            or self.maximum_tiles_per_batch < 1
        ):
            raise ValueError(
                "maximum_tiles_per_batch must be a positive integer"
            )


@dataclass(frozen=True, slots=True)
class SourceLabelStageResult:
    """Published source labels and scalar execution evidence."""

    generation: ProductGenerationManifest
    source_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int


@dataclass(frozen=True, slots=True)
class _OwnerScanBatch:
    """One bounded coarse executor task over several cores."""

    partitions: tuple[TilePartition, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.partitions:
            raise ValueError("owner scan batch must not be empty")


@dataclass(frozen=True, slots=True)
class _OwnerScanResult:
    """The component owners each core holds."""

    owners_by_tile: tuple[tuple[str, tuple[int, ...]], ...]


@dataclass(frozen=True, slots=True)
class _LabelWriteRequest:
    """One core and the source each owner it holds belongs to."""

    partition: TilePartition
    source_by_owner: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class _LabelWriteBatch:
    """One bounded coarse executor task over several cores."""

    requests: tuple[_LabelWriteRequest, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.requests:
            raise ValueError("source label batch must not be empty")


@dataclass(frozen=True, slots=True)
class _WriteBatchResult:
    """Persisted chunk identities from one bounded publication task."""

    product_chunks: tuple[ProductChunk, ...]


def _core_batches[T](
    items: tuple[T, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[tuple[T, ...], ...]:
    """Group cores into bounded coarse tasks."""
    return tuple(
        tuple(items[start : start + maximum_tiles_per_batch])
        for start in range(0, len(items), maximum_tiles_per_batch)
    )


def _scan_owners(
    batch: _OwnerScanBatch,
    *,
    component_source: _CompletedProductSource,
) -> _OwnerScanResult:
    """Observe which component owners each core holds."""
    with component_source.access_session():
        owners: list[tuple[str, tuple[int, ...]]] = []
        for partition in batch.partitions:
            labels = np.asarray(
                component_source.read_completed_window(
                    "component-measurement-labels",
                    partition.core_bounds,
                ),
                dtype=np.int32,
            )
            owners.append(
                (
                    partition.tile_id,
                    tuple(
                        int(value)
                        for value in np.unique(labels)
                        if int(value) > 0
                    ),
                )
            )
        return _OwnerScanResult(owners_by_tile=tuple(owners))


def _publish_source_labels(
    batch: _LabelWriteBatch,
    *,
    component_source: _CompletedProductSource,
    sink: ZarrProductSink,
) -> _WriteBatchResult:
    """Write the source each core's component owners belong to."""
    with component_source.access_session(), sink.access_session():
        chunks: list[ProductChunk] = []
        for request in batch.requests:
            labels = np.asarray(
                component_source.read_completed_window(
                    "component-measurement-labels",
                    request.partition.core_bounds,
                ),
                dtype=np.int32,
            )
            values = np.zeros(labels.shape, dtype=np.int32)
            for owner, source_label in request.source_by_owner:
                values[labels == owner] = source_label
            if bool(np.any((labels > 0) & (values == 0))):
                raise ValueError(
                    "source memberships must own every component pixel"
                )
            chunks.append(
                sink.write_chunk(
                    product_name="source-labels",
                    tile=request.partition,
                    values=values,
                )
            )
        return _WriteBatchResult(product_chunks=tuple(chunks))


def run_source_label_stage(  # noqa: PLR0913
    component_source: _CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: SourceLabelStageConfig,
    source_by_owner: Mapping[int, int],
    executor: Executor,
    sink: ZarrProductSink,
) -> SourceLabelStageResult:
    """Write the catalogue source each component owner belongs to.

    Two rounds: the cores observe which owners they hold, and each then
    writes the labels of the shard that reaches it. The membership map is a
    record, so no accepted-label table is broadcast whole.
    """
    if sink.manifest != manifest:
        raise ValueError("source label sink must use the stage manifest")
    if manifest.halo_yx != (0, 0):
        raise ValueError("source labels write cores without a halo")
    if component_source.manifest.image_shape_yx != manifest.image_shape_yx:
        raise ValueError(
            "published generations must match the source image shape"
        )
    if "component-measurement-labels" not in (
        component_source.read_generation().product_names
    ):
        raise ValueError(
            "published generations must carry the component owner labels"
        )
    scan_batches = tuple(
        _OwnerScanBatch(partitions=group)
        for group in _core_batches(
            manifest.tiles,
            maximum_tiles_per_batch=config.maximum_tiles_per_batch,
        )
    )
    scan_results = tuple(
        executor.map_batches(
            partial(_scan_owners, component_source=component_source),
            scan_batches,
        )
    )
    if not scan_results:
        raise ValueError("executor returned no owner scan results")
    owners_by_tile = {
        tile_id: owners
        for result in scan_results
        for tile_id, owners in result.owners_by_tile
    }
    sink.initialize_product(
        product_name="source-labels",
        dtype=np.dtype("<i4"),
    )
    write_batches = tuple(
        _LabelWriteBatch(requests=group)
        for group in _core_batches(
            tuple(
                _LabelWriteRequest(
                    partition=partition,
                    source_by_owner=tuple(
                        (owner, source_by_owner[owner])
                        for owner in owners_by_tile[partition.tile_id]
                        if owner in source_by_owner
                    ),
                )
                for partition in manifest.tiles
            ),
            maximum_tiles_per_batch=config.maximum_tiles_per_batch,
        )
    )
    write_results = tuple(
        executor.map_batches(
            partial(
                _publish_source_labels,
                component_source=component_source,
                sink=sink,
            ),
            write_batches,
        )
    )
    if not write_results:
        raise ValueError("executor returned no source label results")
    return SourceLabelStageResult(
        generation=sink.publish_generation(
            product_names=_LABEL_PRODUCT_NAMES,
            chunks=(
                chunk
                for result in write_results
                for chunk in result.product_chunks
            ),
        ),
        source_count=len(set(source_by_owner.values())),
        partition_count=len(manifest.tiles),
        executor_task_count=len(scan_batches) + len(write_batches),
        maximum_graph_width=max(len(scan_batches), len(write_batches)),
    )


@dataclass(frozen=True, slots=True)
class SourceSupportStageConfig:
    """Reviewed support policy and the bounded task limits."""

    maximum_tiles_per_batch: int
    maximum_objects_per_batch: int
    maximum_batch_read_pixels: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before any product is initialized."""
        for name, value in (
            ("maximum_tiles_per_batch", self.maximum_tiles_per_batch),
            ("maximum_objects_per_batch", self.maximum_objects_per_batch),
            ("maximum_batch_read_pixels", self.maximum_batch_read_pixels),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class SourceSupportStageResult:
    """Published source measurement labels and execution evidence."""

    generation: ProductGenerationManifest
    support_component_count: int
    assigned_component_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    maximum_component_read_pixels: int
    reconciliation_round_count: int


@dataclass(frozen=True, slots=True)
class _SupportScanBatch:
    """One bounded coarse executor task over several cores."""

    partitions: tuple[TilePartition, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.partitions:
            raise ValueError("support scan batch must not be empty")


@dataclass(frozen=True, slots=True)
class _SupportScanResult:
    """Compact per-core support topology safe to return."""

    summaries: tuple[LocalIslandTileSummary, ...]


@dataclass(frozen=True, slots=True)
class _SupportComponent:
    """One reconciled connected support component, as records name it."""

    bounds: ImageBounds
    first_pixel_yx: tuple[int, int]


@dataclass(frozen=True, slots=True)
class _AssignBatch:
    """One bounded coarse executor task over several support components."""

    components: tuple[_SupportComponent, ...]
    read_bounds: ImageBounds

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.components:
            raise ValueError("support assignment batch must not be empty")


@dataclass(frozen=True, slots=True)
class _AssignBatchResult:
    """Bounded owner patches one batch of components produced."""

    patches: tuple[tuple[ImageBounds, npt.NDArray[np.int32]], ...]
    maximum_component_read_pixels: int


@dataclass(frozen=True, slots=True)
class _WideSupportBatch:
    """One bounded coarse executor task over the cores of wide components."""

    cores: tuple[HeldObjects, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.cores:
            raise ValueError("wide support batch must not be empty")


@dataclass(frozen=True, slots=True)
class _SupportPixels:
    """One wide component's seeds and unseeded support in one core.

    Every index is a global ``y * width + x`` position, so pieces from
    several cores join into the component's own pixel sets.
    """

    global_label: int
    seed_indices: npt.NDArray[np.int64]
    seed_labels: npt.NDArray[np.int64]
    candidate_indices: npt.NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class _WideSupportResult:
    """The wide components' pixels one batch of cores held."""

    pieces: tuple[_SupportPixels, ...]
    tile_ids: tuple[str, ...]
    maximum_core_read_pixels: int


@dataclass(frozen=True, slots=True)
class _Assignment:
    """One wide component's unseeded pixels and the source each goes to."""

    indices: npt.NDArray[np.int64]
    labels: npt.NDArray[np.int32]


@dataclass(frozen=True, slots=True)
class _SupportWriteRequest:
    """One core and the bounded owner patches that reach it."""

    partition: TilePartition
    patches: tuple[tuple[ImageBounds, npt.NDArray[np.int32]], ...]
    assignments: tuple[_Assignment, ...] = ()


@dataclass(frozen=True, slots=True)
class _SupportWriteBatch:
    """One bounded coarse executor task over several cores."""

    requests: tuple[_SupportWriteRequest, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.requests:
            raise ValueError("source support batch must not be empty")


def _persistent_window(
    bounds: ImageBounds,
    *,
    detection_source: _CompletedProductSource,
    scale_support_source: _CompletedProductSource,
    measurement_support_source: _CompletedProductSource,
) -> tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_]]:
    """Read one window's validity and the persistent support it carries."""
    valid = np.asarray(
        detection_source.read_completed_window("valid-pixels", bounds),
        dtype=np.bool_,
    )
    persistent = np.asarray(
        scale_support_source.read_completed_window(
            "persistent-scale-support",
            bounds,
        ),
        dtype=np.bool_,
    ) | np.asarray(
        measurement_support_source.read_completed_window(
            "measurement-support",
            bounds,
        ),
        dtype=np.bool_,
    )
    return valid, persistent


def _label_support(
    support: npt.NDArray[np.bool_],
    partition: TilePartition,
    *,
    image_shape_yx: tuple[int, int],
) -> LocalIslandTile:
    """Label one core's connected source support, exactly as the scan does."""
    return label_detection_tile(
        DetectionThresholdMasks(
            normalized_residual=np.zeros(support.shape, dtype=np.float64),
            island_membership=support,
            detection_seeds=support,
            valid_pixel_count=int(np.count_nonzero(support)),
        ),
        partition,
        image_shape_yx=image_shape_yx,
    )


def _scan_support(  # noqa: PLR0913
    batch: _SupportScanBatch,
    *,
    label_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    scale_support_source: _CompletedProductSource,
    measurement_support_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
) -> _SupportScanResult:
    """Label the support each core carries, as compact summaries."""
    with (
        label_source.access_session(),
        detection_source.access_session(),
        scale_support_source.access_session(),
        measurement_support_source.access_session(),
    ):
        summaries: list[LocalIslandTileSummary] = []
        for partition in batch.partitions:
            core = partition.core_bounds
            _, persistent = _persistent_window(
                core,
                detection_source=detection_source,
                scale_support_source=scale_support_source,
                measurement_support_source=measurement_support_source,
            )
            seeds = (
                np.asarray(
                    label_source.read_completed_window("source-labels", core),
                    dtype=np.int32,
                )
                > 0
            )
            summaries.append(
                _label_support(
                    seeds | persistent,
                    partition,
                    image_shape_yx=image_shape_yx,
                ).compact_summary()
            )
        return _SupportScanResult(summaries=tuple(summaries))


def _assign_batches(
    components: tuple[_SupportComponent, ...],
    *,
    maximum_objects_per_batch: int,
    maximum_batch_read_pixels: int,
) -> tuple[_AssignBatch, ...]:
    """Group components so one read serves several, within both budgets.

    Raises:
        ValueError: If one component's own window exceeds the read budget.
            No admission bounds a component's area, so such a component is
            assigned from its cores instead.
    """
    return tuple(
        _AssignBatch(components=batch.objects, read_bounds=batch.read_bounds)
        for batch in batch_object_windows(
            sorted(
                components,
                key=lambda item: (item.bounds.y_start, item.bounds.x_start),
            ),
            window=lambda component: component.bounds,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
            maximum_objects_per_batch=maximum_objects_per_batch,
        )
    )


def _assign_batch(
    batch: _AssignBatch,
    *,
    label_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    scale_support_source: _CompletedProductSource,
    measurement_support_source: _CompletedProductSource,
) -> _AssignBatchResult:
    """Assign each component's unseeded support inside its own window."""
    with (
        label_source.access_session(),
        detection_source.access_session(),
        scale_support_source.access_session(),
        measurement_support_source.access_session(),
    ):
        read = batch.read_bounds
        valid, persistent = _persistent_window(
            read,
            detection_source=detection_source,
            scale_support_source=scale_support_source,
            measurement_support_source=measurement_support_source,
        )
        seeds = np.asarray(
            label_source.read_completed_window("source-labels", read),
            dtype=np.int32,
        )
        del valid
        patches: list[tuple[ImageBounds, npt.NDArray[np.int32]]] = []
        for component in batch.components:
            bounds = component.bounds
            crop = (
                slice(
                    bounds.y_start - read.y_start, bounds.y_stop - read.y_start
                ),
                slice(
                    bounds.x_start - read.x_start, bounds.x_stop - read.x_start
                ),
            )
            window = np.array(seeds[crop], copy=True)
            assign_connected_source_support(
                window,
                persistent[crop],
                _support_component(window, persistent[crop], component),
            )
            patches.append(
                (bounds, np.where(seeds[crop] > 0, 0, window).astype(np.int32))
            )
        return _AssignBatchResult(
            patches=tuple(patches),
            maximum_component_read_pixels=int(np.prod(read.shape_yx)),
        )


def _support_component(
    seeds: npt.NDArray[np.int32],
    persistent: npt.NDArray[np.bool_],
    component: _SupportComponent,
) -> npt.NDArray[np.bool_]:
    """Recover one reconciled component inside its own bounds.

    The window is the component's reconciled bounds, so the component lies
    entirely inside it, and two globally distinct components are never
    adjacent, so labelling the union here separates them exactly. The
    canonical first pixel names which one this is.
    """
    labels = _connected_components(np.asarray((seeds > 0) | persistent))
    identity = int(
        labels[
            component.first_pixel_yx[0] - component.bounds.y_start,
            component.first_pixel_yx[1] - component.bounds.x_start,
        ]
    )
    if identity == 0:
        raise ValueError(
            "support component must own its canonical first pixel"
        )
    return np.asarray(labels == identity, dtype=np.bool_)


def _connected_components(
    mask: npt.NDArray[np.bool_],
) -> npt.NDArray[np.int32]:
    """Label one window's eight-connected components."""
    labels, _ = cast(
        "tuple[npt.NDArray[np.int32], int]",
        ndimage_label(mask, np.ones((3, 3))),
    )
    return labels


def _raster_indices(
    member: npt.NDArray[np.bool_],
    bounds: ImageBounds,
    *,
    image_width: int,
) -> npt.NDArray[np.int64]:
    """Return one core's selected pixels as global raster indices."""
    rows, columns = np.nonzero(member)
    return (
        (rows.astype(np.int64) + bounds.y_start) * image_width
        + columns
        + bounds.x_start
    )


def _gather_wide_support(  # noqa: PLR0913
    batch: _WideSupportBatch,
    *,
    label_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    scale_support_source: _CompletedProductSource,
    measurement_support_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
) -> _WideSupportResult:
    """Return each wide component's seeds and candidates, core by core.

    A core is relabelled exactly as the scan labelled it, so its reconciled
    mapping names the component's pixels there, and nothing beyond the core
    is read.
    """
    with (
        label_source.access_session(),
        detection_source.access_session(),
        scale_support_source.access_session(),
        measurement_support_source.access_session(),
    ):
        pieces: list[_SupportPixels] = []
        maximum_read_pixels = 0
        for core in batch.cores:
            bounds = core.partition.core_bounds
            _, persistent = _persistent_window(
                bounds,
                detection_source=detection_source,
                scale_support_source=scale_support_source,
                measurement_support_source=measurement_support_source,
            )
            seeds = np.asarray(
                label_source.read_completed_window("source-labels", bounds),
                dtype=np.int32,
            )
            labels = apply_tile_label_mapping(
                _label_support(
                    (seeds > 0) | persistent,
                    core.partition,
                    image_shape_yx=image_shape_yx,
                ),
                core.mapping,
            )
            for global_label in sorted(set(core.mapping.global_labels)):
                member = labels == global_label
                seeded = member & (seeds > 0)
                pieces.append(
                    _SupportPixels(
                        global_label=global_label,
                        seed_indices=_raster_indices(
                            seeded, bounds, image_width=image_shape_yx[1]
                        ),
                        seed_labels=np.asarray(seeds[seeded], dtype=np.int64),
                        candidate_indices=_raster_indices(
                            member & persistent & (seeds == 0),
                            bounds,
                            image_width=image_shape_yx[1],
                        ),
                    )
                )
            maximum_read_pixels = max(maximum_read_pixels, read_pixels(bounds))
        return _WideSupportResult(
            pieces=tuple(pieces),
            tile_ids=tuple(core.partition.tile_id for core in batch.cores),
            maximum_core_read_pixels=maximum_read_pixels,
        )


def _assign_wide_components(
    batches: tuple[_WideSupportBatch, ...],
    results: tuple[_WideSupportResult, ...],
    *,
    image_width: int,
) -> tuple[_Assignment, ...]:
    """Assign every wide component's unseeded pixels from its cores' pieces.

    Each unseeded pixel goes to its nearest seed of the same component, and
    the pieces hold exactly that component's seeds and candidates, so this
    is the assignment one window over the component would make.

    Raises:
        ValueError: If a core that holds a wide component did not answer,
            which would assign its support from part of its seeds.
    """
    requested = {
        core.partition.tile_id for batch in batches for core in batch.cores
    }
    answered = {tile_id for result in results for tile_id in result.tile_ids}
    if answered != requested:
        raise ValueError("every core holding a wide component must answer")
    pieces: dict[int, list[_SupportPixels]] = {}
    for result in results:
        for piece in result.pieces:
            pieces.setdefault(piece.global_label, []).append(piece)
    assignments: list[_Assignment] = []
    for _, parts in sorted(pieces.items()):
        seed_indices = np.concatenate([part.seed_indices for part in parts])
        candidates = np.sort(
            np.concatenate([part.candidate_indices for part in parts])
        )
        if not seed_indices.size or not candidates.size:
            continue
        order = np.argsort(seed_indices, kind="stable")
        owners = nearest_source_seed_labels(
            np.column_stack(np.divmod(seed_indices[order], image_width)),
            np.concatenate([part.seed_labels for part in parts])[order],
            np.column_stack(np.divmod(candidates, image_width)),
        )
        assignments.append(
            _Assignment(
                indices=candidates,
                labels=owners.astype(np.int32, copy=False),
            )
        )
    return tuple(assignments)


def _assignment_shard(
    assignments: tuple[_Assignment, ...],
    core: ImageBounds,
    *,
    image_width: int,
) -> tuple[_Assignment, ...]:
    """Restrict every wide assignment to the core that owns those pixels."""
    shard: list[_Assignment] = []
    for assignment in assignments:
        rows, columns = np.divmod(assignment.indices, image_width)
        inside = (
            (rows >= core.y_start)
            & (rows < core.y_stop)
            & (columns >= core.x_start)
            & (columns < core.x_stop)
        )
        if bool(np.any(inside)):
            shard.append(
                _Assignment(
                    indices=assignment.indices[inside],
                    labels=assignment.labels[inside],
                )
            )
    return tuple(shard)


def _publish_source_support(
    batch: _SupportWriteBatch,
    *,
    label_source: _CompletedProductSource,
    sink: ZarrProductSink,
    image_width: int,
) -> _WriteBatchResult:
    """Combine the owner patches that reach each core and write them.

    A wide component's assignment arrives as the unseeded pixels this core
    owns and the source each one goes to, so no window of it is ever held.
    """
    with label_source.access_session(), sink.access_session():
        chunks: list[ProductChunk] = []
        for request in batch.requests:
            core = request.partition.core_bounds
            values = np.array(
                np.asarray(
                    label_source.read_completed_window("source-labels", core),
                    dtype=np.int32,
                ),
                copy=True,
            )
            for bounds, patch in request.patches:
                overlap = ImageBounds(
                    max(core.y_start, bounds.y_start),
                    min(core.y_stop, bounds.y_stop),
                    max(core.x_start, bounds.x_start),
                    min(core.x_stop, bounds.x_stop),
                )
                target = (
                    slice(
                        overlap.y_start - core.y_start,
                        overlap.y_stop - core.y_start,
                    ),
                    slice(
                        overlap.x_start - core.x_start,
                        overlap.x_stop - core.x_start,
                    ),
                )
                owned = patch[
                    overlap.y_start - bounds.y_start : (
                        overlap.y_stop - bounds.y_start
                    ),
                    overlap.x_start - bounds.x_start : (
                        overlap.x_stop - bounds.x_start
                    ),
                ]
                values[target] = np.where(owned > 0, owned, values[target])
            for assignment in request.assignments:
                rows, columns = np.divmod(assignment.indices, image_width)
                values[rows - core.y_start, columns - core.x_start] = (
                    assignment.labels
                )
            chunks.append(
                sink.write_chunk(
                    product_name="source-measurement-labels",
                    tile=request.partition,
                    values=values,
                )
            )
        return _WriteBatchResult(product_chunks=tuple(chunks))


def run_source_support_stage(  # noqa: PLR0913
    label_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    scale_support_source: _CompletedProductSource,
    measurement_support_source: _CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: SourceSupportStageConfig,
    executor: Executor,
    sink: ZarrProductSink,
) -> SourceSupportStageResult:
    """Assign the persistent support each catalogue source owns.

    Three rounds: the cores label the support they carry and the pieces that
    meet across a core boundary are reconciled, one task per connected
    component assigns its unseeded pixels to their nearest source seed inside
    that component's own window, and the cores write the owner patches that
    reach them over the seeds they already hold.

    A component whose window exceeds ``maximum_batch_read_pixels`` is never
    read whole. The cores holding it return its seeds and unseeded pixels,
    and each of those pixels is assigned from the component's seeds alone,
    which is the assignment its window would make.
    """
    if sink.manifest != manifest:
        raise ValueError("source support sink must use the stage manifest")
    if manifest.halo_yx != (0, 0):
        raise ValueError("source support writes cores without a halo")
    for product_source, names in (
        (label_source, ("source-labels",)),
        (detection_source, ("valid-pixels",)),
        (scale_support_source, ("persistent-scale-support",)),
        (measurement_support_source, ("measurement-support",)),
    ):
        if product_source.manifest.image_shape_yx != manifest.image_shape_yx:
            raise ValueError(
                "published generations must match the support image shape"
            )
        if not set(names).issubset(
            product_source.read_generation().product_names
        ):
            raise ValueError(
                "published generations must carry every support plane read"
            )
    scan_results = tuple(
        executor.map_batches(
            partial(
                _scan_support,
                label_source=label_source,
                detection_source=detection_source,
                scale_support_source=scale_support_source,
                measurement_support_source=measurement_support_source,
                image_shape_yx=manifest.image_shape_yx,
            ),
            tuple(
                _SupportScanBatch(partitions=group)
                for group in _core_batches(
                    manifest.tiles,
                    maximum_tiles_per_batch=config.maximum_tiles_per_batch,
                )
            ),
        )
    )
    if not scan_results:
        raise ValueError("executor returned no support scan results")
    reconciled = reconcile_candidate_tiles(
        manifest,
        tuple(
            summary for result in scan_results for summary in result.summaries
        ),
    )
    budget = config.maximum_batch_read_pixels
    image_width = manifest.image_shape_yx[1]
    assign_batches = _assign_batches(
        tuple(
            _SupportComponent(
                bounds=island.bounds, first_pixel_yx=island.first_pixel_yx
            )
            for island in reconciled.islands
            if read_pixels(island.bounds) <= budget
        ),
        maximum_objects_per_batch=config.maximum_objects_per_batch,
        maximum_batch_read_pixels=budget,
    )
    assign_results = map_round(
        executor,
        partial(
            _assign_batch,
            label_source=label_source,
            detection_source=detection_source,
            scale_support_source=scale_support_source,
            measurement_support_source=measurement_support_source,
        ),
        assign_batches,
        round_name="support assignment",
    )
    wide_cores = cores_holding(
        frozenset(
            island.global_label
            for island in reconciled.islands
            if read_pixels(island.bounds) > budget
        ),
        manifest,
        reconciled.tile_mappings,
    )
    wide_batches = tuple(
        _WideSupportBatch(
            cores=wide_cores[start : start + config.maximum_tiles_per_batch]
        )
        for start in range(0, len(wide_cores), config.maximum_tiles_per_batch)
    )
    wide_results = map_round(
        executor,
        partial(
            _gather_wide_support,
            label_source=label_source,
            detection_source=detection_source,
            scale_support_source=scale_support_source,
            measurement_support_source=measurement_support_source,
            image_shape_yx=manifest.image_shape_yx,
        ),
        wide_batches,
        round_name="wide support",
    )
    assignments = _assign_wide_components(
        wide_batches, wide_results, image_width=image_width
    )
    patches = tuple(
        patch
        for result in assign_results
        for patch in result.patches
        if bool(np.any(patch[1] > 0))
    )
    sink.initialize_product(
        product_name="source-measurement-labels",
        dtype=np.dtype("<i4"),
    )
    write_results = tuple(
        executor.map_batches(
            partial(
                _publish_source_support,
                label_source=label_source,
                sink=sink,
                image_width=image_width,
            ),
            tuple(
                _SupportWriteBatch(requests=group)
                for group in _core_batches(
                    tuple(
                        _SupportWriteRequest(
                            partition=partition,
                            patches=tuple(
                                (bounds, patch)
                                for bounds, patch in patches
                                if _intersects(bounds, partition.core_bounds)
                            ),
                            assignments=_assignment_shard(
                                assignments,
                                partition.core_bounds,
                                image_width=image_width,
                            ),
                        )
                        for partition in manifest.tiles
                    ),
                    maximum_tiles_per_batch=config.maximum_tiles_per_batch,
                )
            ),
        )
    )
    if not write_results:
        raise ValueError("executor returned no source support results")
    return SourceSupportStageResult(
        generation=sink.publish_generation(
            product_names=_SUPPORT_PRODUCT_NAMES,
            chunks=(
                chunk
                for result in write_results
                for chunk in result.product_chunks
            ),
        ),
        support_component_count=len(reconciled.islands),
        assigned_component_count=len(patches) + len(assignments),
        partition_count=len(manifest.tiles),
        executor_task_count=(
            2 * len(manifest.tiles) + len(assign_batches) + len(wide_batches)
        ),
        maximum_graph_width=max(
            len(manifest.tiles), len(assign_batches), len(wide_batches)
        ),
        maximum_component_read_pixels=max(
            (
                *(
                    result.maximum_component_read_pixels
                    for result in assign_results
                ),
                *(result.maximum_core_read_pixels for result in wide_results),
            ),
            default=0,
        ),
        reconciliation_round_count=reconciled.reduction_round_count,
    )


def _intersects(first: ImageBounds, second: ImageBounds) -> bool:
    """Return whether two half-open bounds share a pixel."""
    return (
        first.y_start < second.y_stop
        and second.y_start < first.y_stop
        and first.x_start < second.x_stop
        and second.x_start < first.x_stop
    )
