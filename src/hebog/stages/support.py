"""Global support reductions the tile-native support pass depends on.

ADR-008's pass C needs two quantities that no bounded halo can supply: the
connected components of the direct support unioned with the significant
multiscale support, which decide which seed a support pixel may attach to,
and the adjacent-scale persistence of the multiscale features, which decides
which recovered support may stay published. Both are reconciled here from
compact per-core summaries and written back as owned cores, so the composition
reads them by window instead of computing them over whole planes.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from itertools import pairwise
from numbers import Integral
from typing import Protocol

import numpy as np
import numpy.typing as npt

from hebog.algorithms.detection import DetectionThresholdMasks
from hebog.algorithms.labelling import (
    LocalIslandTile,
    LocalIslandTileSummary,
    label_detection_tile,
)
from hebog.algorithms.reconciliation import (
    ReconciledIslands,
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

_SUPPORT_PRODUCT_NAMES = ("persistent-support", "support-components")
_MINIMUM_PERSISTENT_SCALE_COUNT = 2


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
class SupportTopologyStageConfig:
    """Reviewed scale orders and the coarse executor-batch limit."""

    scale_orders: tuple[int, ...]
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
        if len(self.scale_orders) < _MINIMUM_PERSISTENT_SCALE_COUNT:
            raise ValueError(
                "adjacent-scale persistence needs at least two scale orders"
            )
        if tuple(sorted(set(self.scale_orders))) != tuple(self.scale_orders):
            raise ValueError("scale orders must be unique and ascending")


@dataclass(frozen=True, slots=True)
class SupportTopologyStageResult:
    """Published support planes and scalar execution evidence."""

    generation: ProductGenerationManifest
    support_component_count: int
    persistent_detection_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    maximum_read_pixel_count: int
    boundary_summary_array_bytes: int
    reconciliation_round_count: int


@dataclass(frozen=True, slots=True)
class _ScaleOverlap:
    """One adjacent-scale overlap observed inside a single tile core."""

    finer_index: int
    finer_local_label: int
    coarser_local_label: int


@dataclass(frozen=True, slots=True)
class _TileTopology:
    """Compact per-core topology safe to return through an executor."""

    partition: TilePartition
    support_summary: LocalIslandTileSummary
    scale_summaries: tuple[LocalIslandTileSummary, ...]
    overlaps: tuple[_ScaleOverlap, ...]


@dataclass(frozen=True, slots=True)
class _PartitionBatch:
    """One bounded coarse executor task containing canonical tiles."""

    partitions: tuple[TilePartition, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.partitions:
            raise ValueError("support partition batch must not be empty")


@dataclass(frozen=True, slots=True)
class _TopologyBatchResult:
    """Array-free first-pass topology from one executor task."""

    tiles: tuple[_TileTopology, ...]
    maximum_read_pixel_count: int
    summary_array_bytes: int


@dataclass(frozen=True, slots=True)
class _PublicationTileRequest:
    """One second-pass tile and its accepted global support mappings."""

    partition: TilePartition
    support_mapping: TileLabelMapping
    persistent_local_labels: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class _PublicationBatch:
    """One bounded second-pass executor task."""

    requests: tuple[_PublicationTileRequest, ...]

    def __post_init__(self) -> None:
        """Forbid empty publication work records."""
        if not self.requests:
            raise ValueError("support publication batch must not be empty")


@dataclass(frozen=True, slots=True)
class _PublicationBatchResult:
    """Persisted product identities from one executor task."""

    product_chunks: tuple[ProductChunk, ...]
    maximum_read_pixel_count: int


def support_product_names() -> tuple[str, ...]:
    """Return the canonical published support product set."""
    return _SUPPORT_PRODUCT_NAMES


def _product_dtype(product_name: str) -> np.dtype[np.generic]:
    """Return the stored element type of one published support plane."""
    return (
        np.dtype("<i4")
        if product_name == "support-components"
        else np.dtype(np.bool_)
    )


@dataclass(frozen=True, slots=True)
class _CoreMasks:
    """The exact core masks both support rounds derive from one read."""

    support_union: npt.NDArray[np.bool_]
    scale_masks: tuple[npt.NDArray[np.bool_], ...]


def _read_core_masks(
    partition: TilePartition,
    *,
    detection_source: _CompletedProductSource,
    scale_orders: tuple[int, ...],
) -> _CoreMasks:
    """Derive one core's support union and per-scale masks from one read.

    Both rounds derive the same masks from the same published planes, so the
    second round recomputes them instead of persisting the first round's
    local labels. The detection pass publishes the exact domain it ran over,
    so this pass never re-derives validity from the image and its noise.
    """
    bounds = partition.core_bounds
    scientifically_valid = np.asarray(
        detection_source.read_completed_window("valid-pixels", bounds),
        dtype=np.bool_,
    )
    detection_labels = np.asarray(
        detection_source.read_completed_window("detection-labels", bounds),
        dtype=np.int32,
    )
    reconstruction_mask = np.asarray(
        detection_source.read_completed_window("reconstruction-mask", bounds),
        dtype=np.bool_,
    )
    return _CoreMasks(
        support_union=np.asarray(
            ((detection_labels > 0) | reconstruction_mask)
            & scientifically_valid,
            dtype=np.bool_,
        ),
        scale_masks=tuple(
            np.asarray(
                detection_source.read_completed_window(
                    f"scale-{order}-significant",
                    bounds,
                ),
                dtype=np.bool_,
            )
            for order in scale_orders
        ),
    )


def _label_core(
    mask: npt.NDArray[np.bool_],
    partition: TilePartition,
    *,
    image_shape_yx: tuple[int, int],
) -> LocalIslandTile:
    """Label one owned core of a mask whose members are all seeds."""
    return label_detection_tile(
        DetectionThresholdMasks(
            normalized_residual=np.zeros(mask.shape, dtype=np.float64),
            island_membership=mask,
            detection_seeds=mask,
            valid_pixel_count=int(np.count_nonzero(mask)),
        ),
        partition,
        image_shape_yx=image_shape_yx,
    )


def _core_overlaps(
    scale_tiles: tuple[LocalIslandTile, ...],
) -> tuple[_ScaleOverlap, ...]:
    """Observe adjacent-scale label overlaps inside one owned core."""
    overlaps: list[_ScaleOverlap] = []
    for finer_index, (finer, coarser) in enumerate(pairwise(scale_tiles)):
        finer_labels = finer.labels
        coarser_labels = coarser.labels
        selected = (finer_labels > 0) & (coarser_labels > 0)
        if not bool(np.any(selected)):
            continue
        pairs = np.unique(
            np.column_stack(
                (finer_labels[selected], coarser_labels[selected])
            ),
            axis=0,
        )
        overlaps.extend(
            _ScaleOverlap(
                finer_index=finer_index,
                finer_local_label=int(pair[0]),
                coarser_local_label=int(pair[1]),
            )
            for pair in pairs
        )
    return tuple(overlaps)


def _summary_array_bytes(summary: LocalIslandTileSummary) -> int:
    """Return the boundary-array bytes one compact summary carries."""
    boundaries = summary.boundary_labels
    return sum(
        array.nbytes
        for array in (
            boundaries.top,
            boundaries.bottom,
            boundaries.left,
            boundaries.right,
        )
    )


def _scan_topology_batch(
    batch: _PartitionBatch,
    *,
    detection_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
    scale_orders: tuple[int, ...],
) -> _TopologyBatchResult:
    """Return compact support and scale topology for one bounded batch."""
    with detection_source.access_session():
        tiles: list[_TileTopology] = []
        maximum_read_pixels = 0
        summary_bytes = 0
        for partition in batch.partitions:
            masks = _read_core_masks(
                partition,
                detection_source=detection_source,
                scale_orders=scale_orders,
            )
            support = _label_core(
                masks.support_union,
                partition,
                image_shape_yx=image_shape_yx,
            )
            scale_tiles = tuple(
                _label_core(mask, partition, image_shape_yx=image_shape_yx)
                for mask in masks.scale_masks
            )
            topology = _TileTopology(
                partition=partition,
                support_summary=support.compact_summary(),
                scale_summaries=tuple(
                    tile.compact_summary() for tile in scale_tiles
                ),
                overlaps=_core_overlaps(scale_tiles),
            )
            tiles.append(topology)
            maximum_read_pixels = max(
                maximum_read_pixels,
                int(np.prod(partition.core_bounds.shape_yx)),
            )
            summary_bytes += _summary_array_bytes(
                topology.support_summary
            ) + sum(
                _summary_array_bytes(summary)
                for summary in topology.scale_summaries
            )
        return _TopologyBatchResult(
            tiles=tuple(tiles),
            maximum_read_pixel_count=maximum_read_pixels,
            summary_array_bytes=summary_bytes,
        )


class _DisjointScaleDetections:
    """Deterministic union-find over global ``(order index, label)`` nodes."""

    def __init__(self) -> None:
        """Start with no node; nodes are added as overlaps are observed."""
        self._parent: dict[tuple[int, int], tuple[int, int]] = {}

    def find(self, node: tuple[int, int]) -> tuple[int, int]:
        """Return a canonical root, adding the node when it is new."""
        parent = self._parent.setdefault(node, node)
        while parent != self._parent[parent]:
            parent = self._parent[parent]
        while node != parent:
            self._parent[node], node = parent, self._parent[node]
        return parent

    def union(self, first: tuple[int, int], second: tuple[int, int]) -> None:
        """Join two nodes under the lexicographically smaller root."""
        first_root, second_root = self.find(first), self.find(second)
        if first_root == second_root:
            return
        root, child = sorted((first_root, second_root))
        self._parent[child] = root

    def groups(self) -> tuple[tuple[tuple[int, int], ...], ...]:
        """Return canonically ordered connected groups of nodes."""
        grouped: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for node in sorted(self._parent):
            grouped.setdefault(self.find(node), []).append(node)
        return tuple(tuple(members) for _, members in sorted(grouped.items()))


def _persistent_global_nodes(
    tiles: tuple[_TileTopology, ...],
    scale_reconciliations: tuple[ReconciledIslands, ...],
) -> frozenset[tuple[int, int]]:
    """Return the scale features corroborated at an adjacent scale."""
    components = _DisjointScaleDetections()
    for tile in tiles:
        mappings = tuple(
            reconciliation.mapping_for_tile(tile.partition.tile_id)
            for reconciliation in scale_reconciliations
        )
        for overlap in tile.overlaps:
            finer = _global_label(
                mappings[overlap.finer_index],
                overlap.finer_local_label,
            )
            coarser = _global_label(
                mappings[overlap.finer_index + 1],
                overlap.coarser_local_label,
            )
            components.union(
                (overlap.finer_index, finer),
                (overlap.finer_index + 1, coarser),
            )
    return frozenset(
        node
        for group in components.groups()
        if len({index for index, _ in group})
        >= _MINIMUM_PERSISTENT_SCALE_COUNT
        for node in group
    )


def _global_label(mapping: TileLabelMapping, local_label: int) -> int:
    """Return the global label one tile assigns to a local label.

    Every labelled scale feature carries a seed and at least one pixel, so
    reconciliation accepts all of them and the mapping covers every local
    label the tile produced. A gap would silently drop an overlap edge and
    weaken persistence, so it fails instead.
    """
    for candidate, global_label in zip(
        mapping.local_labels,
        mapping.global_labels,
        strict=True,
    ):
        if candidate == local_label:
            return global_label
    raise ValueError("support mapping must cover every local scale label")


def _publication_requests(
    tiles: tuple[_TileTopology, ...],
    support: ReconciledIslands,
    scale_reconciliations: tuple[ReconciledIslands, ...],
    persistent_nodes: frozenset[tuple[int, int]],
) -> tuple[_PublicationTileRequest, ...]:
    """Shard the accepted support labels to the tiles that hold them."""
    return tuple(
        _PublicationTileRequest(
            partition=tile.partition,
            support_mapping=support.mapping_for_tile(tile.partition.tile_id),
            persistent_local_labels=tuple(
                tuple(
                    local_label
                    for local_label, global_label in zip(
                        mapping.local_labels,
                        mapping.global_labels,
                        strict=True,
                    )
                    if (index, global_label) in persistent_nodes
                )
                for index, mapping in enumerate(
                    reconciliation.mapping_for_tile(tile.partition.tile_id)
                    for reconciliation in scale_reconciliations
                )
            ),
        )
        for tile in tiles
    )


def _publish_batch(
    batch: _PublicationBatch,
    *,
    detection_source: _CompletedProductSource,
    sink: ZarrProductSink,
    image_shape_yx: tuple[int, int],
    scale_orders: tuple[int, ...],
) -> _PublicationBatchResult:
    """Write the accepted support planes for one bounded batch of cores."""
    with detection_source.access_session(), sink.access_session():
        chunks: list[ProductChunk] = []
        maximum_read_pixels = 0
        for request in batch.requests:
            partition = request.partition
            masks = _read_core_masks(
                partition,
                detection_source=detection_source,
                scale_orders=scale_orders,
            )
            components = np.asarray(
                apply_tile_label_mapping(
                    _label_core(
                        masks.support_union,
                        partition,
                        image_shape_yx=image_shape_yx,
                    ),
                    request.support_mapping,
                ),
                dtype=np.int32,
            )
            persistent = np.zeros(components.shape, dtype=np.bool_)
            for mask, local_labels in zip(
                masks.scale_masks,
                request.persistent_local_labels,
                strict=True,
            ):
                if not local_labels:
                    continue
                labels = _label_core(
                    mask,
                    partition,
                    image_shape_yx=image_shape_yx,
                ).labels
                persistent |= np.isin(
                    labels,
                    np.asarray(local_labels, dtype=np.int32),
                )
            chunks.extend(
                sink.write_chunk(
                    product_name=product_name,
                    tile=partition,
                    values=values,
                )
                for product_name, values in (
                    ("persistent-support", persistent),
                    ("support-components", components),
                )
            )
            maximum_read_pixels = max(
                maximum_read_pixels,
                int(np.prod(partition.core_bounds.shape_yx)),
            )
        return _PublicationBatchResult(
            product_chunks=tuple(chunks),
            maximum_read_pixel_count=maximum_read_pixels,
        )


def _partition_batches(
    manifest: PartitionManifest,
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_PartitionBatch, ...]:
    """Group canonical tiles without changing scientific ownership."""
    return tuple(
        _PartitionBatch(
            partitions=manifest.tiles[start : start + maximum_tiles_per_batch]
        )
        for start in range(0, len(manifest.tiles), maximum_tiles_per_batch)
    )


def _publication_batches(
    requests: tuple[_PublicationTileRequest, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_PublicationBatch, ...]:
    """Group mapped publication requests under the same bounded limit."""
    return tuple(
        _PublicationBatch(
            requests=requests[start : start + maximum_tiles_per_batch]
        )
        for start in range(0, len(requests), maximum_tiles_per_batch)
    )


def _validate_stage_inputs(
    detection_source: _CompletedProductSource,
    manifest: PartitionManifest,
    config: SupportTopologyStageConfig,
    sink: ZarrProductSink,
) -> None:
    """Fail before output initialization when identities cannot compose."""
    if sink.manifest != manifest:
        raise ValueError("support sink must use the stage manifest")
    if manifest.halo_yx != (0, 0):
        raise ValueError("support topology is a core-only reduction")
    if detection_source.manifest.image_shape_yx != manifest.image_shape_yx:
        raise ValueError(
            "detection generation must match the support image shape"
        )
    required = {
        "detection-labels",
        "reconstruction-mask",
        "valid-pixels",
        *(f"scale-{order}-significant" for order in config.scale_orders),
    }
    if not required.issubset(detection_source.read_generation().product_names):
        raise ValueError(
            "detection generation must publish labels, support and scales"
        )


def run_support_topology_stage(
    detection_source: _CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: SupportTopologyStageConfig,
    executor: Executor,
    sink: ZarrProductSink,
) -> SupportTopologyStageResult:
    """Reconcile the support pass's global topology and publish its planes.

    The first round returns only compact per-core summaries and the
    adjacent-scale label overlaps each core observes. After reconciliation the
    second round recomputes the same core masks, applies stable global label
    mappings, and writes the accepted cores. No scientific array is returned
    through the executor.
    """
    _validate_stage_inputs(detection_source, manifest, config, sink)
    scan = partial(
        _scan_topology_batch,
        detection_source=detection_source,
        image_shape_yx=manifest.image_shape_yx,
        scale_orders=config.scale_orders,
    )
    partition_batches = _partition_batches(
        manifest,
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    topology_results = tuple(executor.map_batches(scan, partition_batches))
    if not topology_results:
        raise ValueError("executor returned no support topology results")
    tiles = tuple(tile for result in topology_results for tile in result.tiles)
    support = reconcile_candidate_tiles(
        manifest,
        tuple(tile.support_summary for tile in tiles),
    )
    scale_reconciliations = tuple(
        reconcile_candidate_tiles(
            manifest,
            tuple(tile.scale_summaries[index] for tile in tiles),
        )
        for index in range(len(config.scale_orders))
    )
    persistent_nodes = _persistent_global_nodes(tiles, scale_reconciliations)
    for product_name in _SUPPORT_PRODUCT_NAMES:
        sink.initialize_product(
            product_name=product_name,
            dtype=_product_dtype(product_name),
        )
    publication_batches = _publication_batches(
        _publication_requests(
            tiles,
            support,
            scale_reconciliations,
            persistent_nodes,
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    publish = partial(
        _publish_batch,
        detection_source=detection_source,
        sink=sink,
        image_shape_yx=manifest.image_shape_yx,
        scale_orders=config.scale_orders,
    )
    publication_results = tuple(
        executor.map_batches(publish, publication_batches)
    )
    if not publication_results:
        raise ValueError("executor returned no support publication results")
    generation = sink.publish_generation(
        product_names=_SUPPORT_PRODUCT_NAMES,
        chunks=(
            chunk
            for result in publication_results
            for chunk in result.product_chunks
        ),
    )
    return SupportTopologyStageResult(
        generation=generation,
        support_component_count=len(support.islands),
        persistent_detection_count=len(persistent_nodes),
        partition_count=len(manifest.tiles),
        executor_task_count=len(partition_batches) + len(publication_batches),
        maximum_graph_width=max(
            len(partition_batches),
            len(publication_batches),
        ),
        maximum_read_pixel_count=max(
            (
                *(
                    result.maximum_read_pixel_count
                    for result in topology_results
                ),
                *(
                    result.maximum_read_pixel_count
                    for result in publication_results
                ),
            )
        ),
        boundary_summary_array_bytes=sum(
            result.summary_array_bytes for result in topology_results
        ),
        reconciliation_round_count=max(
            support.reduction_round_count,
            *(
                reconciliation.reduction_round_count
                for reconciliation in scale_reconciliations
            ),
        ),
    )
