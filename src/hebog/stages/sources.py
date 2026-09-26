# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Scheduler-facing rounds that own the continuum catalogue's source planes.

ADR-008's catalogue rounds decide one object at a time. The owners a source
holds are a record map, so the cores write the source labels from the shard
that reaches them; the persistent support a source owns spans tiles, so it is
reconciled first and then assigned inside each connected component's own
window, by the cores that hold the component, so no assignment reaches the
driver.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from math import hypot
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
    TileLabelMapping,
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
    """Support components one core assigns from one shared read."""

    components: tuple[_SupportComponent, ...]
    read_bounds: ImageBounds

    def __post_init__(self) -> None:
        """Forbid an empty read."""
        if not self.components:
            raise ValueError("support assignment batch must not be empty")


@dataclass(frozen=True, slots=True)
class _WideSupportBatch:
    """One bounded coarse executor task over the cores of wide components."""

    cores: tuple[HeldObjects, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.cores:
            raise ValueError("wide support batch must not be empty")


@dataclass(frozen=True, slots=True)
class _WideSeedPiece:
    """One wide component's seeds in one core, and its unseeded count there.

    Every index is a global ``y * width + x`` position, so pieces from
    several cores join into the component's own seed set. The unseeded
    pixels stay in the core: its count says only whether the core has any
    to assign.
    """

    tile_id: str
    global_label: int
    seed_indices: npt.NDArray[np.int64]
    seed_labels: npt.NDArray[np.int32]
    candidate_count: int


@dataclass(frozen=True, slots=True)
class _WideSupportResult:
    """The wide components' seeds one batch of cores held."""

    pieces: tuple[_WideSeedPiece, ...]
    tile_ids: tuple[str, ...]
    maximum_core_read_pixels: int


@dataclass(frozen=True, slots=True)
class _ComponentSeeds:
    """The seeds of one wide component that can own a core's pixels."""

    global_label: int
    seed_indices: npt.NDArray[np.int64]
    seed_labels: npt.NDArray[np.int32]


@dataclass(frozen=True, slots=True)
class _WideSeedShards:
    """The seeds each core needs to assign the wide support it holds.

    ``assigning_component_count`` counts the wide components with a seed
    and an unseeded pixel, which are the ones that assign anything.
    """

    by_tile: Mapping[str, tuple[_ComponentSeeds, ...]]
    assigning_component_count: int


@dataclass(frozen=True, slots=True)
class _WideShare:
    """The wide components one core assigns, and the seeds that can own them.

    ``mapping`` is the core's reconciliation cut down to those components,
    so the core finds their pixels again exactly as the scan labelled them.
    """

    mapping: TileLabelMapping
    seeds: tuple[_ComponentSeeds, ...]


@dataclass(frozen=True, slots=True)
class _SupportWriteRequest:
    """One core, the narrow components it holds and its wide share."""

    partition: TilePartition
    components: tuple[_SupportComponent, ...] = ()
    wide: _WideShare | None = None


@dataclass(frozen=True, slots=True)
class _SupportWriteBatch:
    """One bounded coarse executor task over several cores."""

    requests: tuple[_SupportWriteRequest, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.requests:
            raise ValueError("source support batch must not be empty")


@dataclass(frozen=True, slots=True)
class _SupportWriteResult:
    """Persisted chunk identities and the evidence of one write task.

    ``assigned_components`` names, by canonical first pixel, each narrow
    component that gave any pixel to a source, so the stage counts them once
    however many cores assigned them.
    """

    product_chunks: tuple[ProductChunk, ...]
    assigned_components: tuple[tuple[int, int], ...]
    maximum_component_read_pixels: int


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
    """Group one core's components so one read serves several, in budget.

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


def _assigned_patches(
    batch: _AssignBatch,
    *,
    label_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    scale_support_source: _CompletedProductSource,
    measurement_support_source: _CompletedProductSource,
) -> tuple[npt.NDArray[np.int32], ...]:
    """Assign each component's unseeded support inside its own window.

    The caller holds every source's access session open. Each patch covers
    its component's bounds and holds only the pixels the assignment gave a
    source, so the component's window alone decides it, whichever core reads
    it.
    """
    read = batch.read_bounds
    _, persistent = _persistent_window(
        read,
        detection_source=detection_source,
        scale_support_source=scale_support_source,
        measurement_support_source=measurement_support_source,
    )
    seeds = np.asarray(
        label_source.read_completed_window("source-labels", read),
        dtype=np.int32,
    )
    patches: list[npt.NDArray[np.int32]] = []
    for component in batch.components:
        crop = _crop(read, component.bounds)
        window = np.array(seeds[crop], copy=True)
        assign_connected_source_support(
            window,
            persistent[crop],
            _support_component(window, persistent[crop], component),
        )
        patches.append(np.where(seeds[crop] > 0, 0, window).astype(np.int32))
    return tuple(patches)


def _crop(bounds: ImageBounds, window: ImageBounds) -> tuple[slice, slice]:
    """Return the slices selecting one window inside wider bounds."""
    return (
        slice(window.y_start - bounds.y_start, window.y_stop - bounds.y_start),
        slice(window.x_start - bounds.x_start, window.x_stop - bounds.x_start),
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


def _wide_component_labels(
    seeds: npt.NDArray[np.int32],
    persistent: npt.NDArray[np.bool_],
    partition: TilePartition,
    mapping: TileLabelMapping,
    *,
    image_shape_yx: tuple[int, int],
) -> npt.NDArray[np.int64]:
    """Name one core's wide components, relabelled exactly as the scan did.

    ``mapping`` is the core's reconciliation cut down to those components,
    so every other pixel maps to zero.
    """
    return apply_tile_label_mapping(
        _label_support(
            (seeds > 0) | persistent,
            partition,
            image_shape_yx=image_shape_yx,
        ),
        mapping,
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
    """Return each wide component's seeds, core by core.

    A core is relabelled exactly as the scan labelled it, so its reconciled
    mapping names the component's pixels there, and nothing beyond the core
    is read. The unseeded pixels stay here: the write round finds them
    again the same way and assigns them from the seeds.
    """
    with (
        label_source.access_session(),
        detection_source.access_session(),
        scale_support_source.access_session(),
        measurement_support_source.access_session(),
    ):
        pieces: list[_WideSeedPiece] = []
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
            labels = _wide_component_labels(
                seeds,
                persistent,
                core.partition,
                core.mapping,
                image_shape_yx=image_shape_yx,
            )
            for global_label in sorted(set(core.mapping.global_labels)):
                member = labels == global_label
                seeded = member & (seeds > 0)
                pieces.append(
                    _WideSeedPiece(
                        tile_id=core.partition.tile_id,
                        global_label=global_label,
                        seed_indices=_raster_indices(
                            seeded, bounds, image_width=image_shape_yx[1]
                        ),
                        seed_labels=seeds[seeded],
                        candidate_count=int(
                            np.count_nonzero(
                                member & persistent & (seeds == 0)
                            )
                        ),
                    )
                )
            maximum_read_pixels = max(maximum_read_pixels, read_pixels(bounds))
        return _WideSupportResult(
            pieces=tuple(pieces),
            tile_ids=tuple(core.partition.tile_id for core in batch.cores),
            maximum_core_read_pixels=maximum_read_pixels,
        )


def _seeds_near_core(
    seed_indices: npt.NDArray[np.int64],
    core: ImageBounds,
    *,
    image_width: int,
) -> npt.NDArray[np.bool_]:
    """Select every seed that can be the nearest to a pixel of one core.

    Every core pixel lies within the core's half-diagonal ``h`` of its
    centre, and the seed nearest the centre is ``d`` from it, so no pixel's
    nearest seed is farther than ``d + h`` from that pixel, or ``d + 2h``
    from the centre. A seed tied with it is exactly as near, and one pixel
    of margin keeps the nearest-seed kernel's tie tolerance inside. A seed
    beyond cannot own a core pixel, so leaving it out changes no owner.
    """
    rows, columns = np.divmod(seed_indices, image_width)
    centre_y = (core.y_start + core.y_stop - 1) / 2
    centre_x = (core.x_start + core.x_stop - 1) / 2
    half_diagonal = hypot(
        core.y_stop - 1 - centre_y, core.x_stop - 1 - centre_x
    )
    distances = np.hypot(rows - centre_y, columns - centre_x)
    return distances <= float(distances.min()) + 2 * half_diagonal + 1


def _wide_seed_shards(
    batches: tuple[_WideSupportBatch, ...],
    results: tuple[_WideSupportResult, ...],
    *,
    image_width: int,
) -> _WideSeedShards:
    """Send each core the seeds that can own the wide support it holds.

    Each unseeded pixel goes to its nearest seed of the same component, so
    a core holding some of a component's unseeded pixels needs only the
    seeds near it, and assigns those pixels itself. The driver holds each
    wide component's seeds, never its unseeded support. The kernel breaks
    an exact tie by label, so the seeds' order decides nothing.

    Raises:
        ValueError: If a core that holds a wide component did not answer,
            which would assign its support from part of its seeds.
    """
    requested = {
        core.partition.tile_id: core.partition.core_bounds
        for batch in batches
        for core in batch.cores
    }
    answered = {tile_id for result in results for tile_id in result.tile_ids}
    if answered != requested.keys():
        raise ValueError("every core holding a wide component must answer")
    pieces: dict[int, list[_WideSeedPiece]] = {}
    for result in results:
        for piece in result.pieces:
            pieces.setdefault(piece.global_label, []).append(piece)
    by_tile: dict[str, list[_ComponentSeeds]] = {}
    assigning_component_count = 0
    for global_label, parts in sorted(pieces.items()):
        seed_indices = np.concatenate([part.seed_indices for part in parts])
        if not seed_indices.size or not any(
            part.candidate_count for part in parts
        ):
            continue
        assigning_component_count += 1
        seed_labels = np.concatenate([part.seed_labels for part in parts])
        for part in parts:
            if not part.candidate_count:
                continue
            kept = _seeds_near_core(
                seed_indices, requested[part.tile_id], image_width=image_width
            )
            by_tile.setdefault(part.tile_id, []).append(
                _ComponentSeeds(
                    global_label=global_label,
                    seed_indices=seed_indices[kept],
                    seed_labels=seed_labels[kept],
                )
            )
    return _WideSeedShards(
        by_tile={tile_id: tuple(seeds) for tile_id, seeds in by_tile.items()},
        assigning_component_count=assigning_component_count,
    )


def _write_patch(
    values: npt.NDArray[np.int32],
    core: ImageBounds,
    bounds: ImageBounds,
    patch: npt.NDArray[np.int32],
) -> None:
    """Write the part of one component's assignment a core owns, in place.

    The core holds part of the component, so its bounds meet the core.
    """
    overlap = ImageBounds(
        max(core.y_start, bounds.y_start),
        min(core.y_stop, bounds.y_stop),
        max(core.x_start, bounds.x_start),
        min(core.x_stop, bounds.x_stop),
    )
    owned = patch[_crop(bounds, overlap)]
    np.copyto(values[_crop(core, overlap)], owned, where=owned > 0)


def _assign_wide_share(  # noqa: PLR0913
    values: npt.NDArray[np.int32],
    seeds: npt.NDArray[np.int32],
    persistent: npt.NDArray[np.bool_],
    partition: TilePartition,
    share: _WideShare,
    *,
    image_shape_yx: tuple[int, int],
) -> None:
    """Assign this core's unseeded pixels of each wide component, in place.

    Each goes to its nearest seed of the same component, which the seeds
    sent here include, so this is the assignment one window over the whole
    component would make. Every pixel is in this core.
    """
    core = partition.core_bounds
    labels = _wide_component_labels(
        seeds,
        persistent,
        partition,
        share.mapping,
        image_shape_yx=image_shape_yx,
    )
    unseeded = persistent & (seeds == 0)
    for component in share.seeds:
        rows, columns = np.nonzero(
            (labels == component.global_label) & unseeded
        )
        owners = nearest_source_seed_labels(
            np.column_stack(
                np.divmod(component.seed_indices, image_shape_yx[1])
            ),
            component.seed_labels.astype(np.int64),
            np.column_stack(
                (rows + core.y_start, columns + core.x_start)
            ).astype(np.int64),
        )
        values[rows, columns] = owners.astype(np.int32, copy=False)


def _publish_source_support(  # noqa: PLR0913
    batch: _SupportWriteBatch,
    *,
    label_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    scale_support_source: _CompletedProductSource,
    measurement_support_source: _CompletedProductSource,
    sink: ZarrProductSink,
    config: SourceSupportStageConfig,
    image_shape_yx: tuple[int, int],
) -> _SupportWriteResult:
    """Assign the support each core holds and write it over its seeds.

    A narrow component is assigned inside its own window by every core that
    holds part of it, and each keeps its own share, so no assignment crosses
    the executor boundary. A wide component is assigned here too, from the
    seeds that can own this core's share of it, so no window of it is ever
    held and no assignment reaches the driver.
    """
    with (
        label_source.access_session(),
        detection_source.access_session(),
        scale_support_source.access_session(),
        measurement_support_source.access_session(),
        sink.access_session(),
    ):
        chunks: list[ProductChunk] = []
        assigned: set[tuple[int, int]] = set()
        widest_read = 0
        for request in batch.requests:
            core = request.partition.core_bounds
            seeds = np.asarray(
                label_source.read_completed_window("source-labels", core),
                dtype=np.int32,
            )
            values = np.array(seeds, copy=True)
            for assign_batch in _assign_batches(
                request.components,
                maximum_objects_per_batch=config.maximum_objects_per_batch,
                maximum_batch_read_pixels=config.maximum_batch_read_pixels,
            ):
                patches = _assigned_patches(
                    assign_batch,
                    label_source=label_source,
                    detection_source=detection_source,
                    scale_support_source=scale_support_source,
                    measurement_support_source=measurement_support_source,
                )
                for component, patch in zip(
                    assign_batch.components, patches, strict=True
                ):
                    if bool(np.any(patch > 0)):
                        assigned.add(component.first_pixel_yx)
                    _write_patch(values, core, component.bounds, patch)
                widest_read = max(
                    widest_read, read_pixels(assign_batch.read_bounds)
                )
            if request.wide is not None:
                _, persistent = _persistent_window(
                    core,
                    detection_source=detection_source,
                    scale_support_source=scale_support_source,
                    measurement_support_source=measurement_support_source,
                )
                _assign_wide_share(
                    values,
                    seeds,
                    persistent,
                    request.partition,
                    request.wide,
                    image_shape_yx=image_shape_yx,
                )
                widest_read = max(widest_read, read_pixels(core))
            chunks.append(
                sink.write_chunk(
                    product_name="source-measurement-labels",
                    tile=request.partition,
                    values=values,
                )
            )
        return _SupportWriteResult(
            product_chunks=tuple(chunks),
            assigned_components=tuple(sorted(assigned)),
            maximum_component_read_pixels=widest_read,
        )


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

    Two rounds: the cores label the support they carry and the pieces that
    meet across a core boundary are reconciled, then each core assigns the
    connected components it holds, every unseeded pixel to its nearest
    source seed inside that component's own window, and writes its share
    over the seeds it already holds. A component spanning several cores is
    assigned by each of them from the same window, so they agree, and the
    driver holds each component's bounds rather than its assignment.

    A component whose window exceeds ``maximum_batch_read_pixels`` is never
    read whole. The cores holding it return its seeds in a round between
    those two, and each core that holds its unseeded pixels gets back the
    seeds that can own them and assigns them itself, which is the
    assignment its window would make. The driver holds the seeds, never the
    unseeded support.
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
    scan_batches = tuple(
        _SupportScanBatch(partitions=group)
        for group in _core_batches(
            manifest.tiles,
            maximum_tiles_per_batch=config.maximum_tiles_per_batch,
        )
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
            scan_batches,
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
    narrow = {
        island.global_label: _SupportComponent(
            bounds=island.bounds, first_pixel_yx=island.first_pixel_yx
        )
        for island in reconciled.islands
        if read_pixels(island.bounds) <= budget
    }
    held_narrow = {
        core.partition.tile_id: tuple(
            narrow[label] for label in sorted(set(core.mapping.global_labels))
        )
        for core in cores_holding(
            frozenset(narrow), manifest, reconciled.tile_mappings
        )
    }
    wide_cores = cores_holding(
        frozenset(
            island.global_label
            for island in reconciled.islands
            if island.global_label not in narrow
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
    wide_seeds = _wide_seed_shards(
        wide_batches, wide_results, image_width=image_width
    )
    wide_mappings = {
        core.partition.tile_id: core.mapping for core in wide_cores
    }
    sink.initialize_product(
        product_name="source-measurement-labels",
        dtype=np.dtype("<i4"),
    )
    write_batches = tuple(
        _SupportWriteBatch(requests=group)
        for group in _core_batches(
            tuple(
                _SupportWriteRequest(
                    partition=partition,
                    components=held_narrow.get(partition.tile_id, ()),
                    wide=(
                        _WideShare(
                            mapping=wide_mappings[partition.tile_id],
                            seeds=wide_seeds.by_tile[partition.tile_id],
                        )
                        if partition.tile_id in wide_seeds.by_tile
                        else None
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
                _publish_source_support,
                label_source=label_source,
                detection_source=detection_source,
                scale_support_source=scale_support_source,
                measurement_support_source=measurement_support_source,
                sink=sink,
                config=config,
                image_shape_yx=manifest.image_shape_yx,
            ),
            write_batches,
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
        assigned_component_count=len(
            {
                first_pixel
                for result in write_results
                for first_pixel in result.assigned_components
            }
        )
        + wide_seeds.assigning_component_count,
        partition_count=len(manifest.tiles),
        executor_task_count=(
            len(scan_batches) + len(wide_batches) + len(write_batches)
        ),
        maximum_graph_width=max(
            len(scan_batches), len(wide_batches), len(write_batches)
        ),
        maximum_component_read_pixels=max(
            (
                *(
                    result.maximum_component_read_pixels
                    for result in write_results
                ),
                *(result.maximum_core_read_pixels for result in wide_results),
            ),
            default=0,
        ),
        reconciliation_round_count=reconciled.reduction_round_count,
    )
