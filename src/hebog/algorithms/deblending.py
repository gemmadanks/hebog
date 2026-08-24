# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Deterministic bounded watershed deblending for compact islands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
from scipy import ndimage

from hebog.algorithms.labelling import (
    LocalIslandSummary,
    LocalIslandTileSummary,
)
from hebog.algorithms.reconciliation import DetectedIsland, ReconciledIslands
from hebog.config import CompactDeblendConfig, DeferredIslandCompletionConfig
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)

_EIGHT_CONNECTIVITY = np.ones((3, 3), dtype=np.bool_)
_TOPOGRAPHY_MAXIMUM = np.iinfo(np.uint16).max
_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class CompactDeblendBatch:
    """A deterministic bounded batch of compact island records."""

    islands: tuple[DetectedIsland, ...]
    estimated_pixel_count: int


@dataclass(frozen=True, slots=True)
class DeferredDeblendIsland:
    """An island preserved explicitly for a later partitioned path."""

    island: DetectedIsland
    reason: Literal["island-pixel-limit", "bounds-pixel-limit"]


@dataclass(frozen=True, slots=True)
class CompactDeblendPlan:
    """Bounded compact work plus explicit extended-island deferrals."""

    batches: tuple[CompactDeblendBatch, ...]
    deferred_islands: tuple[DeferredDeblendIsland, ...]


@dataclass(frozen=True, slots=True)
class DeferredIslandShard:
    """One bounded tile-local fragment of a compact-deferred island."""

    island_id: str
    partition: TilePartition
    local_labels: tuple[int, ...]
    pixel_count: int
    bounds: ImageBounds
    first_pixel_yx: tuple[int, int]

    def __post_init__(self) -> None:
        """Require canonical labels and topology inside the owned tile."""
        if (
            not self.local_labels
            or self.local_labels != tuple(sorted(set(self.local_labels)))
            or any(label_value < 1 for label_value in self.local_labels)
        ):
            raise ValueError(
                "deferred shard labels must be positive canonical"
            )
        core = self.partition.core_bounds
        core_pixels = core.shape_yx[0] * core.shape_yx[1]
        if not 0 < self.pixel_count <= core_pixels:
            raise ValueError("deferred shard pixel count exceeds its tile")
        if not core.contains(self.bounds):
            raise ValueError("deferred shard bounds must lie inside its tile")
        y_pixel, x_pixel = self.first_pixel_yx
        if not (
            self.bounds.y_start <= y_pixel < self.bounds.y_stop
            and self.bounds.x_start <= x_pixel < self.bounds.x_stop
        ):
            raise ValueError("deferred shard first pixel must lie in bounds")


@dataclass(frozen=True, slots=True)
class PartitionedDeferredIsland:
    """Complete exact support ownership without an island-sized array."""

    island: DetectedIsland
    reason: Literal["island-pixel-limit", "bounds-pixel-limit"]
    shards: tuple[DeferredIslandShard, ...]

    def __post_init__(self) -> None:
        """Bind canonical bounded shards to the reconciled parent topology."""
        if not self.shards:
            raise ValueError("partitioned deferred island requires shards")
        ordered = tuple(
            sorted(
                self.shards,
                key=lambda shard: (
                    shard.partition.tile_y_index,
                    shard.partition.tile_x_index,
                ),
            )
        )
        if self.shards != ordered:
            raise ValueError("deferred island shards must be canonical")
        if any(shard.island_id != self.island.island_id for shard in ordered):
            raise ValueError("deferred shard parent identity disagrees")
        if self.pixel_count != self.island.pixel_count:
            raise ValueError("deferred shard membership disagrees with island")
        aggregate_bounds = ImageBounds(
            min(shard.bounds.y_start for shard in ordered),
            max(shard.bounds.y_stop for shard in ordered),
            min(shard.bounds.x_start for shard in ordered),
            max(shard.bounds.x_stop for shard in ordered),
        )
        if aggregate_bounds != self.island.bounds:
            raise ValueError("deferred shard bounds disagree with island")
        if min(shard.first_pixel_yx for shard in ordered) != (
            self.island.first_pixel_yx
        ):
            raise ValueError(
                "deferred shard first pixel disagrees with island"
            )

    @property
    def pixel_count(self) -> int:
        """Return the exact total owned membership."""
        return sum(shard.pixel_count for shard in self.shards)

    @property
    def maximum_shard_pixels(self) -> int:
        """Return the largest tile core admitted to one membership task."""
        return max(
            shard.partition.core_bounds.shape_yx[0]
            * shard.partition.core_bounds.shape_yx[1]
            for shard in self.shards
        )


@dataclass(frozen=True, slots=True)
class CompactIslandPixels:
    """One admitted normalized island bounds region and exact membership."""

    island: DetectedIsland
    normalized_residual: npt.NDArray[np.float64]
    island_membership: npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class DeblendedRegion:
    """One deterministic compact region for later scientific measurement."""

    region_id: str
    region_label: int
    island_id: str
    pixel_count: int
    bounds: ImageBounds
    peak_signal_to_noise: float
    peak_position_yx: tuple[int, int]
    first_pixel_yx: tuple[int, int]


@dataclass(frozen=True, slots=True)
class CompactDeblendResult:
    """Bounded region topology, not measured sources or Gaussian fits."""

    island_id: str
    status: Literal["single-region", "deblended"]
    regions: tuple[DeblendedRegion, ...]
    region_labels: npt.NDArray[np.int32]

    def compact_summary(self) -> CompactDeblendSummary:
        """Drop bounded region labels before returning through an executor."""
        return CompactDeblendSummary(
            island_id=self.island_id,
            status=self.status,
            regions=self.regions,
        )


@dataclass(frozen=True, slots=True)
class CompactDeblendSummary:
    """Executor-safe compact region facts with no pixel label arrays."""

    island_id: str
    status: Literal["single-region", "deblended"]
    regions: tuple[DeblendedRegion, ...]


def _bounds_pixel_count(bounds: ImageBounds) -> int:
    """Return one half-open rectangle's exact pixel count."""
    height, width = bounds.shape_yx
    return height * width


def plan_compact_deblend_batches(
    islands: tuple[DetectedIsland, ...],
    config: CompactDeblendConfig,
    *,
    context_margin_pixels: int = 0,
    image_shape_yx: tuple[int, int] | None = None,
) -> CompactDeblendPlan:
    """Admit compact bounds by cost without creating a task per island."""
    if context_margin_pixels < 0:
        raise ValueError("context margin cannot be negative")
    if context_margin_pixels and image_shape_yx is None:
        raise ValueError("context margin requires the logical image shape")
    if context_margin_pixels:
        assert image_shape_yx is not None
    ordered = tuple(
        sorted(
            islands,
            key=lambda island: (island.global_label, island.island_id),
        )
    )
    if len({island.island_id for island in ordered}) != len(ordered):
        raise ValueError("deblend plan island IDs must be unique")
    batches: list[CompactDeblendBatch] = []
    deferred: list[DeferredDeblendIsland] = []
    current: list[DetectedIsland] = []
    current_pixels = 0
    for island in ordered:
        admitted_bounds = (
            island.bounds
            if context_margin_pixels == 0
            else island.bounds.expanded(
                context_margin_pixels,
                cast(tuple[int, int], image_shape_yx),
            )
        )
        bounds_pixels = _bounds_pixel_count(admitted_bounds)
        if island.pixel_count > config.maximum_compact_island_pixels:
            deferred.append(
                DeferredDeblendIsland(
                    island=island,
                    reason="island-pixel-limit",
                )
            )
            continue
        if bounds_pixels > config.maximum_compact_bounds_pixels:
            deferred.append(
                DeferredDeblendIsland(
                    island=island,
                    reason="bounds-pixel-limit",
                )
            )
            continue
        if current and (
            current_pixels + bounds_pixels > config.target_batch_pixels
        ):
            batches.append(
                CompactDeblendBatch(
                    islands=tuple(current),
                    estimated_pixel_count=current_pixels,
                )
            )
            current = []
            current_pixels = 0
        current.append(island)
        current_pixels += bounds_pixels
    if current:
        batches.append(
            CompactDeblendBatch(
                islands=tuple(current),
                estimated_pixel_count=current_pixels,
            )
        )
    return CompactDeblendPlan(
        batches=tuple(batches),
        deferred_islands=tuple(deferred),
    )


def extract_island_membership(
    island: DetectedIsland,
    accepted_mask: npt.ArrayLike,
) -> npt.NDArray[np.bool_]:
    """Select one exact connected island from its bounded boolean window.

    A published source-filtering-mask window can contain disconnected islands
    whose bounds overlap or nest. The reconciled island's canonical first
    pixel selects its eight-connected component without requiring a durable
    global label plane.
    """
    mask = np.asarray(accepted_mask)
    if mask.ndim != _IMAGE_DIMENSIONS:
        raise ValueError("island mask window must be two-dimensional")
    if not np.issubdtype(mask.dtype, np.bool_):
        raise TypeError("island mask window must be boolean")
    if mask.shape != island.bounds.shape_yx:
        raise ValueError("island mask window must match island bounds")
    first_y = island.first_pixel_yx[0] - island.bounds.y_start
    first_x = island.first_pixel_yx[1] - island.bounds.x_start
    height, width = mask.shape
    if not (0 <= first_y < height and 0 <= first_x < width):
        raise ValueError("island first pixel is outside its bounds")
    raw_labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(mask, structure=_EIGHT_CONNECTIVITY),
    )
    labels = np.asarray(raw_labels, dtype=np.int32)
    selected_label = int(labels[first_y, first_x])
    if selected_label == 0:
        raise ValueError("island first pixel is absent from the mask")
    membership = np.asarray(labels == selected_label, dtype=np.bool_)
    if int(np.count_nonzero(membership)) != island.pixel_count:
        raise ValueError("connected mask membership disagrees with island")
    membership.setflags(write=False)
    return membership


def _summary_bounds(
    summaries: tuple[LocalIslandSummary, ...],
) -> ImageBounds:
    """Return aggregate bounds for objects exposing bounded topology."""
    return ImageBounds(
        min(summary.bounds.y_start for summary in summaries),
        max(summary.bounds.y_stop for summary in summaries),
        min(summary.bounds.x_start for summary in summaries),
        max(summary.bounds.x_stop for summary in summaries),
    )


def _same_island_topology(
    first: DetectedIsland,
    second: DetectedIsland,
) -> bool:
    """Compare identity and membership facts independent of response peaks."""
    return (
        first.island_id == second.island_id
        and first.global_label == second.global_label
        and first.pixel_count == second.pixel_count
        and first.bounds == second.bounds
        and first.first_pixel_yx == second.first_pixel_yx
        and first.touches_image_edge == second.touches_image_edge
    )


def _validate_deferred_partition_inputs(
    manifest: PartitionManifest,
    tiles: tuple[LocalIslandTileSummary, ...],
    reconciliation: ReconciledIslands,
    deferred_islands: tuple[DeferredDeblendIsland, ...],
    config: DeferredIslandCompletionConfig,
) -> dict[str, LocalIslandTileSummary]:
    """Validate bounded canonical inputs before constructing any shard."""
    if any(
        tile.core_bounds.shape_yx[0] * tile.core_bounds.shape_yx[1]
        > config.maximum_tile_pixels
        for tile in manifest.tiles
    ):
        raise ValueError("deferred completion tile exceeds its hard bound")
    tiles_by_id = {tile.partition.tile_id: tile for tile in tiles}
    expected_tile_ids = {tile.tile_id for tile in manifest.tiles}
    if len(tiles_by_id) != len(tiles) or set(tiles_by_id) != expected_tile_ids:
        raise ValueError("deferred completion tiles must be canonical")
    if any(
        tiles_by_id[partition.tile_id].partition != partition
        for partition in manifest.tiles
    ):
        raise ValueError("deferred completion tile partition is not canonical")
    mapping_ids = tuple(
        mapping.tile_id for mapping in reconciliation.tile_mappings
    )
    if (
        len(set(mapping_ids)) != len(mapping_ids)
        or set(mapping_ids) != expected_tile_ids
    ):
        raise ValueError("deferred reconciliation must cover every tile")
    if len({item.island.island_id for item in deferred_islands}) != len(
        deferred_islands
    ):
        raise ValueError("deferred island identities must be unique")
    reconciled_by_id = {
        island.island_id: island for island in reconciliation.islands
    }
    for deferred in deferred_islands:
        reconciled = reconciled_by_id.get(deferred.island.island_id)
        if reconciled is None or not _same_island_topology(
            deferred.island,
            reconciled,
        ):
            raise ValueError("deferred parent is not the reconciled island")
    return tiles_by_id


def partition_deferred_islands(
    manifest: PartitionManifest,
    tiles: tuple[LocalIslandTileSummary, ...],
    reconciliation: ReconciledIslands,
    deferred_islands: tuple[DeferredDeblendIsland, ...],
    config: DeferredIslandCompletionConfig,
) -> tuple[PartitionedDeferredIsland, ...]:
    """Bind exact deferred membership to canonical bounded tile shards."""
    tiles_by_id = _validate_deferred_partition_inputs(
        manifest,
        tiles,
        reconciliation,
        deferred_islands,
        config,
    )

    completed: list[PartitionedDeferredIsland] = []
    for deferred in sorted(
        deferred_islands,
        key=lambda item: (item.island.global_label, item.island.island_id),
    ):
        island = deferred.island
        shards: list[DeferredIslandShard] = []
        for partition in manifest.tiles:
            tile = tiles_by_id[partition.tile_id]
            mapping = reconciliation.mapping_for_tile(partition.tile_id)
            local_labels = tuple(
                local_label
                for local_label, global_label in zip(
                    mapping.local_labels,
                    mapping.global_labels,
                    strict=True,
                )
                if global_label == island.global_label
            )
            if not local_labels:
                continue
            summaries_by_label = {
                summary.local_label: summary for summary in tile.islands
            }
            if any(
                local_label not in summaries_by_label
                for local_label in local_labels
            ):
                raise ValueError(
                    "deferred reconciliation label is absent from its tile"
                )
            selected = tuple(
                summaries_by_label[local_label] for local_label in local_labels
            )
            shards.append(
                DeferredIslandShard(
                    island_id=island.island_id,
                    partition=partition,
                    local_labels=local_labels,
                    pixel_count=sum(item.pixel_count for item in selected),
                    bounds=_summary_bounds(selected),
                    first_pixel_yx=min(
                        item.first_pixel_yx for item in selected
                    ),
                )
            )
        completed.append(
            PartitionedDeferredIsland(
                island=island,
                reason=deferred.reason,
                shards=tuple(shards),
            )
        )
    return tuple(completed)


def extract_deferred_island_shard_membership(
    shard: DeferredIslandShard,
    accepted_mask: npt.ArrayLike,
) -> npt.NDArray[np.bool_]:
    """Select one exact deferred fragment from a bounded accepted-mask tile."""
    mask = np.asarray(accepted_mask)
    if mask.shape != shard.partition.core_bounds.shape_yx:
        raise ValueError("deferred mask must match its tile core")
    if not np.issubdtype(mask.dtype, np.bool_):
        raise TypeError("deferred mask must be boolean")
    raw_labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(mask, structure=_EIGHT_CONNECTIVITY),
    )
    membership = np.isin(raw_labels, shard.local_labels)
    positions = np.argwhere(membership)
    if positions.size == 0:
        raise ValueError("deferred shard membership is absent")
    bounds = shard.partition.core_bounds
    observed_bounds = ImageBounds(
        bounds.y_start + int(np.min(positions[:, 0])),
        bounds.y_start + int(np.max(positions[:, 0])) + 1,
        bounds.x_start + int(np.min(positions[:, 1])),
        bounds.x_start + int(np.max(positions[:, 1])) + 1,
    )
    observed_first = (
        int(positions[0, 0]) + bounds.y_start,
        int(positions[0, 1]) + bounds.x_start,
    )
    if (
        int(np.count_nonzero(membership)) != shard.pixel_count
        or observed_bounds != shard.bounds
        or observed_first != shard.first_pixel_yx
    ):
        raise ValueError("deferred shard membership disagrees with summary")
    membership = np.asarray(membership, dtype=np.bool_)
    membership.setflags(write=False)
    return membership


def _validate_input(
    compact_island: CompactIslandPixels,
    config: CompactDeblendConfig,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    """Validate exact topology and memory admission before SciPy work."""
    normalized = np.asarray(
        compact_island.normalized_residual,
        dtype=np.float64,
    )
    membership = np.asarray(compact_island.island_membership)
    expected_shape = compact_island.island.bounds.shape_yx
    if (
        normalized.ndim != _IMAGE_DIMENSIONS
        or membership.ndim != _IMAGE_DIMENSIONS
    ):
        raise ValueError("compact deblend arrays must be two-dimensional")
    if (
        normalized.shape != expected_shape
        or membership.shape != expected_shape
    ):
        raise ValueError("compact deblend arrays must match island bounds")
    if not np.issubdtype(membership.dtype, np.bool_):
        raise TypeError("compact deblend membership must be boolean")
    pixel_count = int(np.count_nonzero(membership))
    if pixel_count != compact_island.island.pixel_count:
        raise ValueError("compact deblend membership disagrees with island")
    if pixel_count > config.maximum_compact_island_pixels:
        raise ValueError("compact island exceeds its admitted pixel limit")
    if normalized.size > config.maximum_compact_bounds_pixels:
        raise ValueError("compact island bounds exceed their admitted limit")
    if not np.all(np.isfinite(normalized[membership])):
        raise ValueError(
            "compact island pixels must have finite normalized values"
        )
    return normalized, np.asarray(membership, dtype=np.bool_)


def _marker_positions(
    normalized: npt.NDArray[np.float64],
    membership: npt.NDArray[np.bool_],
    bounds: ImageBounds,
    config: CompactDeblendConfig,
) -> tuple[tuple[int, int], ...]:
    """Select strict local maxima and collapse connected equal plateaus."""
    radius = config.minimum_peak_separation_pixels
    footprint_size = 2 * radius + 1
    values = np.where(membership, normalized, -np.inf)
    local_maximum = ndimage.maximum_filter(
        values,
        size=footprint_size,
        mode="constant",
        cval=-np.inf,
    )
    peak_pixels = (
        membership
        & (normalized == local_maximum)
        & (normalized > config.minimum_peak_signal_to_noise)
    )
    plateau_labels, plateau_count = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(peak_pixels, structure=_EIGHT_CONNECTIVITY),
    )
    if plateau_count == 0:
        raise ValueError("compact island has no eligible deblending peak")
    local_y, local_x = np.indices(normalized.shape, dtype=np.int64)
    bounds_width = normalized.shape[1]
    local_linear = local_y * bounds_width + local_x
    first_linear = np.asarray(
        ndimage.minimum(
            local_linear,
            plateau_labels,
            index=np.arange(1, plateau_count + 1, dtype=np.int32),
        ),
        dtype=np.int64,
    )
    return tuple(
        (
            bounds.y_start + int(value) // bounds_width,
            bounds.x_start + int(value) % bounds_width,
        )
        for value in np.sort(first_linear)
    )


def _watershed_labels(
    membership: npt.NDArray[np.bool_],
    bounds: ImageBounds,
    peak_positions_yx: tuple[tuple[int, int], ...],
) -> npt.NDArray[np.int32]:
    """Partition one compact island with a marker-distance watershed."""
    markers = np.zeros(membership.shape, dtype=np.int32)
    for marker_label, (global_y, global_x) in enumerate(
        peak_positions_yx,
        start=1,
    ):
        markers[global_y - bounds.y_start, global_x - bounds.x_start] = (
            marker_label
        )
    if len(peak_positions_yx) == 1:
        return np.where(membership, 1, 0).astype(np.int32)

    distance = cast(
        npt.NDArray[np.float64],
        ndimage.distance_transform_edt(markers == 0),
    )
    maximum_distance = float(np.max(distance[membership]))
    topography = np.zeros(membership.shape, dtype=np.uint16)
    if maximum_distance > 0:
        topography = np.rint(
            distance / maximum_distance * (_TOPOGRAPHY_MAXIMUM - 1)
        ).astype(np.uint16)
    topography[~membership] = _TOPOGRAPHY_MAXIMUM
    raw = np.asarray(
        ndimage.watershed_ift(
            topography,
            markers,
            structure=_EIGHT_CONNECTIVITY,
        ),
        dtype=np.int32,
    )
    labels = np.where(membership & (raw > 0), raw, 0).astype(np.int32)
    if np.any(membership & (labels == 0)):
        raise ValueError("watershed did not assign every island pixel")
    return labels


def _boundary_saddles(
    labels: npt.NDArray[np.int32],
    normalized: npt.NDArray[np.float64],
) -> tuple[tuple[int, int, float], ...]:
    """Reduce adjacent region contacts to their highest discrete saddle."""
    pair_blocks: list[npt.NDArray[np.int32]] = []
    saddle_blocks: list[npt.NDArray[np.float64]] = []
    for y_offset, x_offset in ((0, 1), (1, -1), (1, 0), (1, 1)):
        first_y = slice(0, labels.shape[0] - y_offset)
        second_y = slice(y_offset, labels.shape[0])
        if x_offset < 0:
            first_x = slice(1, labels.shape[1])
            second_x = slice(0, labels.shape[1] - 1)
        else:
            first_x = slice(0, labels.shape[1] - x_offset)
            second_x = slice(x_offset, labels.shape[1])
        first = labels[first_y, first_x]
        second = labels[second_y, second_x]
        selected = (first > 0) & (second > 0) & (first != second)
        if not np.any(selected):
            continue
        pairs = np.column_stack((first[selected], second[selected]))
        pairs.sort(axis=1)
        pair_blocks.append(pairs)
        saddle_blocks.append(
            np.minimum(
                normalized[first_y, first_x][selected],
                normalized[second_y, second_x][selected],
            )
        )
    if not pair_blocks:
        return ()
    pairs = np.concatenate(pair_blocks)
    saddles = np.concatenate(saddle_blocks)
    unique_pairs, inverse = np.unique(pairs, axis=0, return_inverse=True)
    maximum_saddles = np.full(unique_pairs.shape[0], -np.inf)
    np.maximum.at(maximum_saddles, inverse, saddles)
    return tuple(
        (int(pair[0]), int(pair[1]), float(saddle))
        for pair, saddle in zip(unique_pairs, maximum_saddles, strict=True)
    )


class _RegionGroups:
    """Merge only basins whose weaker peak lacks reviewed prominence."""

    def __init__(
        self,
        peak_positions_yx: tuple[tuple[int, int], ...],
        normalized: npt.NDArray[np.float64],
        bounds: ImageBounds,
    ) -> None:
        self._parent = list(range(len(peak_positions_yx) + 1))
        self._peak = {
            label: (
                float(
                    normalized[
                        position[0] - bounds.y_start,
                        position[1] - bounds.x_start,
                    ]
                ),
                position,
            )
            for label, position in enumerate(peak_positions_yx, start=1)
        }

    def find(self, label: int) -> int:
        """Return one root with path compression."""
        root = label
        while root != self._parent[root]:
            root = self._parent[root]
        while label != root:
            next_label = self._parent[label]
            self._parent[label] = root
            label = next_label
        return root

    def merge_if_shallow(
        self,
        first: int,
        second: int,
        saddle: float,
        *,
        minimum_depth: float,
    ) -> None:
        """Merge the weaker basin only when its saddle depth is too small."""
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root == second_root:
            return
        first_peak = self._peak[first_root]
        second_peak = self._peak[second_root]
        weaker_value = min(first_peak[0], second_peak[0])
        if weaker_value - saddle >= minimum_depth:
            return
        winner, loser = sorted(
            (first_root, second_root),
            key=lambda root: (-self._peak[root][0], self._peak[root][1]),
        )
        self._parent[loser] = winner


def _merge_shallow_regions(
    labels: npt.NDArray[np.int32],
    normalized: npt.NDArray[np.float64],
    bounds: ImageBounds,
    peak_positions_yx: tuple[tuple[int, int], ...],
    config: CompactDeblendConfig,
) -> npt.NDArray[np.int32]:
    """Merge watershed basins by sparse boundary-saddle prominence."""
    groups = _RegionGroups(peak_positions_yx, normalized, bounds)
    saddles = sorted(
        _boundary_saddles(labels, normalized),
        key=lambda item: (-item[2], item[0], item[1]),
    )
    for first, second, saddle in saddles:
        groups.merge_if_shallow(
            first,
            second,
            saddle,
            minimum_depth=config.minimum_saddle_depth_sigma,
        )
    root_lookup = np.array(
        [groups.find(label) for label in range(len(peak_positions_yx) + 1)],
        dtype=np.int32,
    )
    merged = root_lookup[labels]
    roots = np.unique(merged[merged > 0])
    height, width = labels.shape
    local_y, local_x = np.indices((height, width), dtype=np.int64)
    local_linear = local_y * width + local_x
    first_linear = np.asarray(
        ndimage.minimum(local_linear, merged, index=roots),
        dtype=np.int64,
    )
    ordered_roots = roots[np.argsort(first_linear)]
    canonical = np.zeros(root_lookup.size, dtype=np.int32)
    canonical[ordered_roots] = np.arange(
        1,
        ordered_roots.size + 1,
        dtype=np.int32,
    )
    return canonical[merged]


def _canonicalize_labels(
    labels: npt.NDArray[np.int32],
) -> npt.NDArray[np.int32]:
    """Renumber present regions by their first row-major pixel."""
    present = np.unique(labels[labels > 0])
    height, width = labels.shape
    local_y, local_x = np.indices((height, width), dtype=np.int64)
    local_linear = local_y * width + local_x
    first_linear = np.asarray(
        ndimage.minimum(local_linear, labels, index=present),
        dtype=np.int64,
    )
    ordered = present[np.argsort(first_linear)]
    lookup = np.zeros(int(np.max(present, initial=0)) + 1, dtype=np.int32)
    lookup[ordered] = np.arange(1, ordered.size + 1, dtype=np.int32)
    return lookup[labels]


def _merge_undersized_regions(
    labels: npt.NDArray[np.int32],
    normalized: npt.NDArray[np.float64],
    *,
    minimum_region_pixels: int,
) -> npt.NDArray[np.int32]:
    """Join fit-ineligible basins across their strongest shared saddle."""
    merged = np.array(labels, dtype=np.int32, copy=True)
    while True:
        present, counts = np.unique(
            merged[merged > 0],
            return_counts=True,
        )
        if present.size <= 1:
            break
        undersized = [
            (int(count), int(label))
            for label, count in zip(present, counts, strict=True)
            if count < minimum_region_pixels
        ]
        if not undersized:
            break
        _, selected = min(undersized)
        contacts = [
            (saddle, second if first == selected else first)
            for first, second, saddle in _boundary_saddles(
                merged,
                normalized,
            )
            if selected in (first, second)
        ]
        if not contacts:
            raise ValueError("undersized deblend region has no adjacent basin")
        _, neighbour = min(
            contacts,
            key=lambda item: (-item[0], item[1]),
        )
        merged[merged == selected] = neighbour
    return _canonicalize_labels(merged)


def _summarize_regions(
    island: DetectedIsland,
    labels: npt.NDArray[np.int32],
    normalized: npt.NDArray[np.float64],
) -> tuple[DeblendedRegion, ...]:
    """Reduce canonical region labels without copying pixels per region."""
    region_count = int(np.max(labels, initial=0))
    indices = np.arange(1, region_count + 1, dtype=np.int32)
    counts = np.asarray(
        ndimage.sum_labels(
            np.ones(labels.shape, dtype=np.int64),
            labels,
            index=indices,
        ),
        dtype=np.int64,
    )
    peaks = np.asarray(
        ndimage.maximum(normalized, labels, index=indices),
        dtype=np.float64,
    )
    bounds = island.bounds
    bounds_width = labels.shape[1]
    local_y, local_x = np.indices(labels.shape, dtype=np.int64)
    local_linear = local_y * bounds_width + local_x
    first_linear = np.asarray(
        ndimage.minimum(local_linear, labels, index=indices),
        dtype=np.int64,
    )
    maximum_lookup = np.concatenate(([-np.inf], peaks))
    peak_pixels = (labels > 0) & (normalized == maximum_lookup[labels])
    peak_linear = np.asarray(
        ndimage.minimum(
            np.where(peak_pixels, local_linear, np.iinfo(np.int64).max),
            labels,
            index=indices,
        ),
        dtype=np.int64,
    )
    object_slices = ndimage.find_objects(labels, max_label=region_count)
    return tuple(
        DeblendedRegion(
            region_id=f"{island.island_id}-region-{label:03d}",
            region_label=label,
            island_id=island.island_id,
            pixel_count=int(counts[label - 1]),
            bounds=ImageBounds(
                bounds.y_start + object_slices[label - 1][0].start,
                bounds.y_start + object_slices[label - 1][0].stop,
                bounds.x_start + object_slices[label - 1][1].start,
                bounds.x_start + object_slices[label - 1][1].stop,
            ),
            peak_signal_to_noise=float(peaks[label - 1]),
            peak_position_yx=(
                bounds.y_start + int(peak_linear[label - 1]) // bounds_width,
                bounds.x_start + int(peak_linear[label - 1]) % bounds_width,
            ),
            first_pixel_yx=(
                bounds.y_start + int(first_linear[label - 1]) // bounds_width,
                bounds.x_start + int(first_linear[label - 1]) % bounds_width,
            ),
        )
        for label in range(1, region_count + 1)
    )


def deblend_compact_island(
    compact_island: CompactIslandPixels,
    config: CompactDeblendConfig,
) -> CompactDeblendResult:
    """Split one admitted island into deterministic watershed regions."""
    normalized, membership = _validate_input(compact_island, config)
    bounds = compact_island.island.bounds
    peaks = _marker_positions(normalized, membership, bounds, config)
    watershed = _watershed_labels(membership, bounds, peaks)
    labels = _merge_shallow_regions(
        watershed,
        normalized,
        bounds,
        peaks,
        config,
    )
    labels = _merge_undersized_regions(
        labels,
        normalized,
        minimum_region_pixels=config.minimum_region_pixels,
    )
    labels = np.asarray(labels, dtype=np.int32)
    labels.setflags(write=False)
    regions = _summarize_regions(
        compact_island.island,
        labels,
        normalized,
    )
    return CompactDeblendResult(
        island_id=compact_island.island.island_id,
        status="deblended" if len(regions) > 1 else "single-region",
        regions=regions,
        region_labels=labels,
    )


def deblend_compact_batch(
    islands: tuple[CompactIslandPixels, ...],
    config: CompactDeblendConfig,
) -> tuple[CompactDeblendResult, ...]:
    """Deblend one admitted batch without a scheduler task per island."""
    if (
        sum(item.normalized_residual.size for item in islands)
        > config.maximum_batch_pixels
    ):
        raise ValueError("compact deblend batch exceeds its admitted limit")
    return tuple(deblend_compact_island(item, config) for item in islands)
