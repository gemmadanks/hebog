# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Fit parents: the owners fitted together, numbered and published by core.

Owners whose fit contexts touch need a joint model, and that connectivity
follows a chain of any length, so it is reconciled from compact per-core
summaries before any fit runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from numbers import Integral

import numpy as np
import numpy.typing as npt
from scipy.ndimage import binary_dilation

from hebog.algorithms.component_measurement import (
    compact_window_is_admitted,
)
from hebog.algorithms.detection import DetectionThresholdMasks
from hebog.algorithms.fitting import joint_fit_admits
from hebog.algorithms.labelling import (
    LocalIslandTile,
    LocalIslandTileSummary,
    label_detection_tile,
)
from hebog.algorithms.reconciliation import (
    ReconciledIslands,
    TileLabelMapping,
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
from hebog.io.base import CompletedProductSource
from hebog.io.zarr import ZarrProductSink
from hebog.stages.object_extents import (
    PublishBatchResult,
    core_label_extents,
    crop_slices,
    union_bounds,
)
from hebog.stages.task_memory import read_requirement

# Each round's cost per pixel of its largest read, which a task declares
# (``hebog.stages.task_memory``): the largest traced task peak over that read
# on the 3,000-, 10,000- and 15,402-pixel LoTSS-DR3 anchors and the dense
# ELAIS-N1 central 5,000 pixels, rounded up to eight bytes (plan task 17).
_CONTEXT_BYTES_PER_READ_PIXEL = 64
_FIT_PARENT_PUBLICATION_BYTES_PER_READ_PIXEL = 72


_FIT_PARENT_PRODUCT_NAMES = ("fit-parent-labels",)


def fit_parent_product_names() -> tuple[str, ...]:
    """Return the canonical published fit-parent product set."""
    return _FIT_PARENT_PRODUCT_NAMES


@dataclass(frozen=True, slots=True)
class FitParentStageConfig:
    """The reviewed fit context margin, the joint-fit bounds and task limit.

    ``read_margin_pixels`` and ``maximum_bounds_pixels`` are the window the
    component-fit round reads around a parent and the compact bound that
    admits it, so they must be that round's own. The joint fit's work
    limits are not settings: the stage applies the fit's fixed ones, to a
    parent's owners and their direct pixels as an ``owned-region`` fit
    counts them. A parent beyond either is fitted island by island.
    """

    context_margin_pixels: int
    maximum_tiles_per_batch: int
    read_margin_pixels: int
    maximum_bounds_pixels: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before stage products are initialized."""
        for name in ("maximum_tiles_per_batch", "maximum_bounds_pixels"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")
        if self.context_margin_pixels < 0:
            raise ValueError("context margin must be non-negative")
        if (
            isinstance(self.read_margin_pixels, bool)
            or not isinstance(self.read_margin_pixels, Integral)
            or self.read_margin_pixels < 0
        ):
            raise ValueError("read margin must be a non-negative integer")


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
    """Compact per-core fit-context topology safe to return.

    ``support_bounds`` and ``direct_pixel_counts`` hold, for each local
    context, the bounds of the measurement support and the number of direct
    component pixels it holds in this core.
    """

    partition: TilePartition
    summary: LocalIslandTileSummary
    links: tuple[_ContextLink, ...]
    support_bounds: tuple[tuple[int, ImageBounds], ...] = ()
    direct_pixel_counts: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class _ContextBatchResult:
    """Array-free fit-context topology from one bounded scan task."""

    tiles: tuple[_ContextTile, ...]


@dataclass(frozen=True, slots=True)
class _ContextPublicationRequest:
    """One core and the fit-parent number each local context carries.

    A context of a parent fitted island by island carries no number; its
    support takes the numbers its local islands carry instead.
    """

    partition: TilePartition
    fit_parent_by_local_label: tuple[tuple[int, int], ...]
    fit_parent_by_local_island_label: tuple[tuple[int, int], ...] = ()


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
    component_source: CompletedProductSource,
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
    core = crop_slices(read, partition.core_bounds)
    return contexts[core], labels[core]


def _label_contexts(
    partition: TilePartition,
    *,
    component_source: CompletedProductSource,
    image_shape_yx: tuple[int, int],
    context_margin_pixels: int,
) -> tuple[LocalIslandTile, npt.NDArray[np.int32], tuple[_ContextLink, ...]]:
    """Label one core's fit contexts and link each owner to those it reaches.

    Returns the labelled core, its measurement owners and the links.
    """
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
    links = tuple(
        _ContextLink(
            owner_label=int(pair[0]),
            local_context_label=int(pair[1]),
        )
        for pair in pairs
    )
    return tile, labels, links


def _scan_contexts(
    batch: _ContextPublicationBatch,
    *,
    component_source: CompletedProductSource,
    image_shape_yx: tuple[int, int],
    context_margin_pixels: int,
) -> _ContextBatchResult:
    """Label each core's fit contexts and observe what each one holds.

    Each context's owners, direct component pixels and support bounds are
    what decide whether its parent can be fitted whole.
    """
    tiles: list[_ContextTile] = []
    for request in batch.requests:
        partition = request.partition
        tile, labels, links = _label_contexts(
            partition,
            component_source=component_source,
            image_shape_yx=image_shape_yx,
            context_margin_pixels=context_margin_pixels,
        )
        support = labels > 0
        tiles.append(
            _ContextTile(
                partition=partition,
                summary=tile.compact_summary(),
                links=links,
                support_bounds=tuple(
                    (local_label, bounds)
                    for local_label, (bounds, _, _) in core_label_extents(
                        np.where(support, tile.labels, 0).astype(np.int32),
                        partition.core_bounds,
                    ).items()
                ),
                direct_pixel_counts=_direct_pixel_counts(
                    tile.labels,
                    support,
                    partition,
                    component_source=component_source,
                ),
            )
        )
    return _ContextBatchResult(tiles=tuple(tiles))


def _scan_islands(
    batch: _ContextPublicationBatch,
    *,
    component_source: CompletedProductSource,
    image_shape_yx: tuple[int, int],
) -> _ContextBatchResult:
    """Label each core's islands, its zero-margin contexts, and owners."""
    tiles: list[_ContextTile] = []
    for request in batch.requests:
        tile, _, links = _label_contexts(
            request.partition,
            component_source=component_source,
            image_shape_yx=image_shape_yx,
            context_margin_pixels=0,
        )
        tiles.append(
            _ContextTile(
                partition=request.partition,
                summary=tile.compact_summary(),
                links=links,
            )
        )
    return _ContextBatchResult(tiles=tuple(tiles))


def _direct_pixel_counts(
    context_labels: npt.NDArray[np.int32],
    support: npt.NDArray[np.bool_],
    partition: TilePartition,
    *,
    component_source: CompletedProductSource,
) -> tuple[tuple[int, int], ...]:
    """Count the direct component pixels each local context holds."""
    direct = np.asarray(
        component_source.read_completed_window(
            "component-direct-labels", partition.core_bounds
        ),
        dtype=np.int32,
    )
    counts = np.bincount(context_labels[support & (direct > 0)])
    return tuple(
        (int(label), int(counts[label]))
        for label in np.flatnonzero(counts)
        if label > 0
    )


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
    """Join the contexts one owner's support reaches, then number them.

    An owner's pieces can lie in different cores, so its contexts are joined
    across every core, not only within one.
    """
    components = _DisjointContexts(
        tuple(island.global_label for island in contexts.islands)
    )
    first_context: dict[int, int] = {}
    for tile in tiles:
        mapping = contexts.mapping_for_tile(tile.partition.tile_id)
        for link in tile.links:
            context = _global_context(mapping, link.local_context_label)
            components.union(
                first_context.setdefault(link.owner_label, context), context
            )
    return components.fit_parent_numbers()


def _parents_to_fit_by_island(
    tiles: tuple[_ContextTile, ...],
    contexts: ReconciledIslands,
    numbers: dict[int, int],
    *,
    config: FitParentStageConfig,
    image_shape_yx: tuple[int, int],
) -> frozenset[int]:
    """Return the joined parents of several owners no joint fit can hold.

    The joint fit refuses a parent for its owners and their direct pixels,
    and the compact bound refuses one whose window, its support bounds plus
    the component-fit read margin, is too large. Fitted whole, such a parent
    would leave every component deferred. A parent of one owner is already
    one island. The direct pixels are exactly what a fit with the reviewed
    ``owned-region`` pixel support measures; one with ``bounded-context``
    support counts its whole window, so a parent this admits may still be
    refused and deferred whole.
    """
    owners: dict[int, set[int]] = {}
    pixels: dict[int, int] = {}
    bounds: dict[int, ImageBounds | None] = {}
    for tile in tiles:
        mapping = contexts.mapping_for_tile(tile.partition.tile_id)
        for link in tile.links:
            parent = numbers[
                _global_context(mapping, link.local_context_label)
            ]
            owners.setdefault(parent, set()).add(link.owner_label)
        for local_label, count in tile.direct_pixel_counts:
            parent = numbers[_global_context(mapping, local_label)]
            pixels[parent] = pixels.get(parent, 0) + count
        for local_label, support in tile.support_bounds:
            parent = numbers[_global_context(mapping, local_label)]
            bounds[parent] = union_bounds(bounds.get(parent), support)
    unfittable: set[int] = set()
    for parent, parent_owners in owners.items():
        support = bounds.get(parent)
        if support is None:
            raise ValueError("every fit parent must hold measurement support")
        if parent not in pixels:
            raise ValueError("every fit parent must hold direct pixels")
        fittable = joint_fit_admits(
            len(parent_owners), pixels[parent]
        ) and compact_window_is_admitted(
            support.expanded(config.read_margin_pixels, image_shape_yx),
            maximum_bounds_pixels=config.maximum_bounds_pixels,
        )
        if len(parent_owners) > 1 and not fittable:
            unfittable.add(parent)
    return frozenset(unfittable)


def _numbers_with_islands(  # noqa: PLR0913
    tiles: tuple[_ContextTile, ...],
    contexts: ReconciledIslands,
    numbers: dict[int, int],
    *,
    island_tiles: tuple[_ContextTile, ...],
    islands: ReconciledIslands,
    split: frozenset[int],
) -> tuple[dict[int, int], dict[int, int]]:
    """Renumber fit parents, a split parent's islands in its place.

    Parents keep the joined order, and a split parent's islands follow
    their own order, as the whole-plane rule numbers them. Returns the
    number each unsplit global context and each split global island takes.
    """
    island_numbers = _fit_parent_numbers(island_tiles, islands)
    parent_by_owner: dict[int, int] = {}
    for tile in tiles:
        mapping = contexts.mapping_for_tile(tile.partition.tile_id)
        for link in tile.links:
            parent_by_owner[link.owner_label] = numbers[
                _global_context(mapping, link.local_context_label)
            ]
    islands_by_parent: dict[int, set[int]] = {}
    for tile in island_tiles:
        mapping = islands.mapping_for_tile(tile.partition.tile_id)
        for link in tile.links:
            islands_by_parent.setdefault(
                parent_by_owner[link.owner_label], set()
            ).add(
                island_numbers[
                    _global_context(mapping, link.local_context_label)
                ]
            )
    final_parent: dict[int, int] = {}
    final_island: dict[int, int] = {}
    number = 0
    for parent in sorted(set(numbers.values())):
        if parent not in split:
            number += 1
            final_parent[parent] = number
            continue
        for island in sorted(islands_by_parent[parent]):
            number += 1
            final_island[island] = number
    return (
        {
            label: final_parent[parent]
            for label, parent in numbers.items()
            if parent in final_parent
        },
        {
            label: final_island[island]
            for label, island in island_numbers.items()
            if island in final_island
        },
    )


def _local_numbers(
    mapping: TileLabelMapping,
    numbers: dict[int, int],
) -> tuple[tuple[int, int], ...]:
    """Return the number each local label of one core carries, if any."""
    return tuple(
        (local_label, numbers[global_label])
        for local_label, global_label in zip(
            mapping.local_labels, mapping.global_labels, strict=True
        )
        if global_label in numbers
    )


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
    component_source: CompletedProductSource,
    sink: ZarrProductSink,
    image_shape_yx: tuple[int, int],
    context_margin_pixels: int,
) -> PublishBatchResult:
    """Write the fit-parent number each core's support belongs to."""
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
        if request.fit_parent_by_local_island_label:
            local_islands = label_detection_tile(
                DetectionThresholdMasks(
                    normalized_residual=np.zeros(
                        labels.shape,
                        dtype=np.float64,
                    ),
                    island_membership=labels > 0,
                    detection_seeds=labels > 0,
                    valid_pixel_count=int(np.count_nonzero(labels)),
                ),
                partition,
                image_shape_yx=image_shape_yx,
            )
            for (
                local_label,
                fit_parent,
            ) in request.fit_parent_by_local_island_label:
                values[local_islands.labels == local_label] = fit_parent
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
    return PublishBatchResult(product_chunks=tuple(chunks))


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
    component_source: CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: FitParentStageConfig,
    executor: Executor,
    sink: ZarrProductSink,
) -> FitParentStageResult:
    """Reconcile the fit contexts owners share and publish their numbers.

    Owners whose contexts touch need a joint model, and that connectivity
    follows a chain of any length, so it is reconciled from compact per-core
    summaries before any fit runs. A parent of several owners that no joint
    fit can hold, by its work limits or the compact bound on its window, is
    fitted island by island: only then are the islands scanned and
    reconciled in one further round. The cores then write the fit-parent
    number each support pixel belongs to.
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
    if not {
        "component-measurement-labels",
        "component-direct-labels",
    } <= set(component_source.read_generation().product_names):
        raise ValueError(
            "component generation must publish direct and measurement "
            "component labels"
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
    context_reads = tuple(
        partition.read_bounds for partition in manifest.tiles
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
            requirement=read_requirement(
                _CONTEXT_BYTES_PER_READ_PIXEL,
                context_reads,
                chunk_shape_yx=manifest.tile_core_shape_yx,
            ),
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
    split = _parents_to_fit_by_island(
        tiles,
        contexts,
        numbers,
        config=config,
        image_shape_yx=manifest.image_shape_yx,
    )
    by_context, by_island = numbers, {}
    islands: ReconciledIslands | None = None
    island_task_count = 0
    if split:
        # Only a parent no joint fit can hold needs its islands, so an image
        # without one never labels or reconciles them.
        island_results = tuple(
            executor.map_batches(
                partial(
                    _scan_islands,
                    component_source=component_source,
                    image_shape_yx=manifest.image_shape_yx,
                ),
                scan_batches,
                requirement=read_requirement(
                    _CONTEXT_BYTES_PER_READ_PIXEL,
                    context_reads,
                    chunk_shape_yx=manifest.tile_core_shape_yx,
                ),
            )
        )
        if not island_results:
            raise ValueError("executor returned no fit-island results")
        island_tiles = tuple(
            tile for result in island_results for tile in result.tiles
        )
        islands = reconcile_candidate_tiles(
            manifest,
            tuple(tile.summary for tile in island_tiles),
        )
        by_context, by_island = _numbers_with_islands(
            tiles,
            contexts,
            numbers,
            island_tiles=island_tiles,
            islands=islands,
            split=split,
        )
        island_task_count = len(scan_batches)
    sink.initialize_product(
        product_name="fit-parent-labels",
        dtype=np.dtype("<i4"),
    )
    publish_batches = _context_batches(
        tuple(
            _ContextPublicationRequest(
                partition=tile.partition,
                fit_parent_by_local_label=_local_numbers(
                    contexts.mapping_for_tile(tile.partition.tile_id),
                    by_context,
                ),
                fit_parent_by_local_island_label=(
                    ()
                    if islands is None
                    else _local_numbers(
                        islands.mapping_for_tile(tile.partition.tile_id),
                        by_island,
                    )
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
            requirement=read_requirement(
                _FIT_PARENT_PUBLICATION_BYTES_PER_READ_PIXEL,
                context_reads,
                chunk_shape_yx=manifest.tile_core_shape_yx,
            ),
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
        fit_parent_count=len({*by_context.values(), *by_island.values()}),
        context_count=len(contexts.islands),
        partition_count=len(manifest.tiles),
        executor_task_count=(
            len(scan_batches) + island_task_count + len(publish_batches)
        ),
        maximum_graph_width=max(len(scan_batches), len(publish_batches)),
        reconciliation_round_count=contexts.reduction_round_count
        + (0 if islands is None else islands.reduction_round_count),
    )
