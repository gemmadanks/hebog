"""Deterministic reconciliation of tile-local connected island labels."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from hebog.algorithms.labelling import LocalIslandSummary, LocalIslandTile
from hebog.config import SourceFinderConfig
from hebog.data_models.partitioning import ImageBounds, PartitionManifest

_LocalIslandKey = tuple[str, int]


@dataclass(frozen=True, slots=True)
class DetectedIsland:
    """Canonical detection-stage topology before scientific measurement."""

    island_id: str
    global_label: int
    pixel_count: int
    bounds: ImageBounds
    peak_signal_to_noise: float
    peak_position_yx: tuple[int, int]
    first_pixel_yx: tuple[int, int]
    touches_image_edge: bool


@dataclass(frozen=True, slots=True)
class TileLabelMapping:
    """Small mapping from one tile's local labels to accepted global labels."""

    tile_id: str
    local_labels: tuple[int, ...]
    global_labels: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ReconciledIslands:
    """Stable accepted islands and per-tile mappings for mask publication."""

    islands: tuple[DetectedIsland, ...]
    tile_mappings: tuple[TileLabelMapping, ...]

    def mapping_for_tile(self, tile_id: str) -> TileLabelMapping:
        """Return the exact mapping for one canonical tile."""
        for mapping in self.tile_mappings:
            if mapping.tile_id == tile_id:
                return mapping
        raise ValueError(f"reconciliation has no mapping for tile {tile_id!r}")


class _DisjointSet:
    """Deterministic union-find over tile-local island keys."""

    def __init__(self, values: tuple[_LocalIslandKey, ...]) -> None:
        self._parent = {value: value for value in values}

    def find(self, value: _LocalIslandKey) -> _LocalIslandKey:
        """Return a canonical root with path compression."""
        parent = self._parent[value]
        while parent != self._parent[parent]:
            parent = self._parent[parent]
        while value != parent:
            next_value = self._parent[value]
            self._parent[value] = parent
            value = next_value
        return parent

    def union(self, first: _LocalIslandKey, second: _LocalIslandKey) -> None:
        """Join two sets under the lexicographically smaller root."""
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root == second_root:
            return
        root, child = sorted((first_root, second_root))
        self._parent[child] = root


def _positive_pairs(
    first: npt.NDArray[np.int32],
    second: npt.NDArray[np.int32],
) -> tuple[tuple[int, int], ...]:
    """Return unique positive local-label adjacencies for aligned vectors."""
    selected = (first > 0) & (second > 0)
    if not np.any(selected):
        return ()
    pairs = np.column_stack((first[selected], second[selected]))
    return tuple(
        (int(pair[0]), int(pair[1])) for pair in np.unique(pairs, axis=0)
    )


def _union_vector_pairs(
    disjoint_set: _DisjointSet,
    first_tile_id: str,
    first: npt.NDArray[np.int32],
    second_tile_id: str,
    second: npt.NDArray[np.int32],
) -> None:
    """Union all positive label pairs across one aligned boundary relation."""
    for first_label, second_label in _positive_pairs(first, second):
        disjoint_set.union(
            (first_tile_id, first_label),
            (second_tile_id, second_label),
        )


def _union_scalar_pair(
    disjoint_set: _DisjointSet,
    first_tile_id: str,
    first_label: np.int32,
    second_tile_id: str,
    second_label: np.int32,
) -> None:
    """Union one diagonal tile-corner pair when both pixels are active."""
    if first_label > 0 and second_label > 0:
        disjoint_set.union(
            (first_tile_id, int(first_label)),
            (second_tile_id, int(second_label)),
        )


def _reconcile_boundaries(
    disjoint_set: _DisjointSet,
    tiles_by_index: dict[tuple[int, int], LocalIslandTile],
) -> None:
    """Union eight-connected labels across sides and four-tile corners."""
    for (tile_y_index, tile_x_index), tile in sorted(tiles_by_index.items()):
        right = tiles_by_index.get((tile_y_index, tile_x_index + 1))
        if right is not None:
            first = tile.boundary_labels.right
            second = right.boundary_labels.left
            _union_vector_pairs(
                disjoint_set,
                tile.partition.tile_id,
                first,
                right.partition.tile_id,
                second,
            )
            _union_vector_pairs(
                disjoint_set,
                tile.partition.tile_id,
                first[:-1],
                right.partition.tile_id,
                second[1:],
            )
            _union_vector_pairs(
                disjoint_set,
                tile.partition.tile_id,
                first[1:],
                right.partition.tile_id,
                second[:-1],
            )

        below = tiles_by_index.get((tile_y_index + 1, tile_x_index))
        if below is not None:
            first = tile.boundary_labels.bottom
            second = below.boundary_labels.top
            _union_vector_pairs(
                disjoint_set,
                tile.partition.tile_id,
                first,
                below.partition.tile_id,
                second,
            )
            _union_vector_pairs(
                disjoint_set,
                tile.partition.tile_id,
                first[:-1],
                below.partition.tile_id,
                second[1:],
            )
            _union_vector_pairs(
                disjoint_set,
                tile.partition.tile_id,
                first[1:],
                below.partition.tile_id,
                second[:-1],
            )

        below_right = tiles_by_index.get((tile_y_index + 1, tile_x_index + 1))
        if below_right is not None:
            _union_scalar_pair(
                disjoint_set,
                tile.partition.tile_id,
                tile.boundary_labels.bottom[-1],
                below_right.partition.tile_id,
                below_right.boundary_labels.top[0],
            )
        below_left = tiles_by_index.get((tile_y_index + 1, tile_x_index - 1))
        if below_left is not None:
            _union_scalar_pair(
                disjoint_set,
                tile.partition.tile_id,
                tile.boundary_labels.bottom[0],
                below_left.partition.tile_id,
                below_left.boundary_labels.top[-1],
            )


def _aggregate_group(
    summaries: tuple[LocalIslandSummary, ...],
) -> LocalIslandSummary:
    """Merge one connected set of tile fragments into global properties."""
    peak = min(
        summaries,
        key=lambda item: (
            -item.peak_signal_to_noise,
            item.peak_position_yx,
        ),
    )
    return LocalIslandSummary(
        local_label=0,
        pixel_count=sum(item.pixel_count for item in summaries),
        bounds=ImageBounds(
            min(item.bounds.y_start for item in summaries),
            max(item.bounds.y_stop for item in summaries),
            min(item.bounds.x_start for item in summaries),
            max(item.bounds.x_stop for item in summaries),
        ),
        peak_signal_to_noise=peak.peak_signal_to_noise,
        peak_position_yx=peak.peak_position_yx,
        first_pixel_yx=min(item.first_pixel_yx for item in summaries),
        touches_image_edge=any(item.touches_image_edge for item in summaries),
        contains_detection_seed=any(
            item.contains_detection_seed for item in summaries
        ),
    )


def reconcile_island_tiles(
    manifest: PartitionManifest,
    tiles: tuple[LocalIslandTile, ...],
    config: SourceFinderConfig,
) -> ReconciledIslands:
    """Merge local labels and apply seed and size cuts to global islands."""
    tiles_by_id = {tile.partition.tile_id: tile for tile in tiles}
    expected_by_id = {tile.tile_id: tile for tile in manifest.tiles}
    if len(tiles_by_id) != len(tiles) or set(tiles_by_id) != set(
        expected_by_id
    ):
        raise ValueError("island tiles must cover the canonical manifest once")
    for tile in tiles:
        canonical = expected_by_id[tile.partition.tile_id]
        if tile.partition != canonical:
            raise ValueError("island tile partition is not canonical")

    summaries_by_key = {
        (tile.partition.tile_id, summary.local_label): summary
        for tile in tiles
        for summary in tile.islands
    }
    disjoint_set = _DisjointSet(tuple(sorted(summaries_by_key)))
    tiles_by_index = {
        (tile.partition.tile_y_index, tile.partition.tile_x_index): tile
        for tile in tiles
    }
    _reconcile_boundaries(disjoint_set, tiles_by_index)

    members_by_root: dict[_LocalIslandKey, list[_LocalIslandKey]] = {}
    for key in summaries_by_key:
        members_by_root.setdefault(disjoint_set.find(key), []).append(key)
    aggregate_by_root = {
        root: _aggregate_group(
            tuple(summaries_by_key[key] for key in sorted(member_keys))
        )
        for root, member_keys in members_by_root.items()
    }
    maximum = config.maximum_island_pixels
    accepted = tuple(
        sorted(
            (
                (root, summary)
                for root, summary in aggregate_by_root.items()
                if summary.contains_detection_seed
                and summary.pixel_count >= config.minimum_island_pixels
                and (maximum is None or summary.pixel_count <= maximum)
            ),
            key=lambda item: item[1].first_pixel_yx,
        )
    )
    global_label_by_root = {
        root: global_label
        for global_label, (root, _) in enumerate(accepted, start=1)
    }
    islands = tuple(
        DetectedIsland(
            island_id=f"island-{global_label:05d}",
            global_label=global_label,
            pixel_count=summary.pixel_count,
            bounds=summary.bounds,
            peak_signal_to_noise=summary.peak_signal_to_noise,
            peak_position_yx=summary.peak_position_yx,
            first_pixel_yx=summary.first_pixel_yx,
            touches_image_edge=summary.touches_image_edge,
        )
        for global_label, (_, summary) in enumerate(accepted, start=1)
    )
    tile_mappings = tuple(
        TileLabelMapping(
            tile_id=tile.tile_id,
            local_labels=tuple(
                summary.local_label
                for summary in tiles_by_id[tile.tile_id].islands
            ),
            global_labels=tuple(
                global_label_by_root.get(
                    disjoint_set.find((tile.tile_id, summary.local_label)),
                    0,
                )
                for summary in tiles_by_id[tile.tile_id].islands
            ),
        )
        for tile in manifest.tiles
    )
    return ReconciledIslands(islands=islands, tile_mappings=tile_mappings)


def apply_reconciled_labels(
    tile: LocalIslandTile,
    reconciliation: ReconciledIslands,
) -> npt.NDArray[np.int64]:
    """Map one local label core to immutable stable global labels."""
    mapping = reconciliation.mapping_for_tile(tile.partition.tile_id)
    maximum_local_label = int(np.max(tile.labels, initial=0))
    lookup = np.zeros(maximum_local_label + 1, dtype=np.int64)
    for local_label, global_label in zip(
        mapping.local_labels,
        mapping.global_labels,
        strict=True,
    ):
        if local_label > maximum_local_label:
            raise ValueError("reconciliation local label is outside tile")
        lookup[local_label] = global_label
    labels = lookup[tile.labels]
    labels.setflags(write=False)
    return labels
