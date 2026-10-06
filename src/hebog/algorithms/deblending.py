# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Deterministic bounded watershed deblending for compact islands."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
from scipy import ndimage

from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactDeblendConfig
from hebog.data_models.partitioning import (
    ImageBounds,
)

_EIGHT_CONNECTIVITY = np.ones((3, 3), dtype=np.bool_)
_EIGHT_NEIGHBOUR_OFFSETS = tuple(
    (y_offset, x_offset)
    for y_offset in (-1, 0, 1)
    for x_offset in (-1, 0, 1)
    if (y_offset, x_offset) != (0, 0)
)
_IMAGE_DIMENSIONS = 2


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


def _ascent_basins(
    normalized: npt.NDArray[np.float64],
    membership: npt.NDArray[np.bool_],
    bounds: ImageBounds,
    peak_positions_yx: tuple[tuple[int, int], ...],
) -> npt.NDArray[np.int32]:
    """Label each member pixel by the maximum its steepest ascent reaches.

    A pixel steps to its highest eight-connected member neighbour while that
    neighbour is higher, ties going to the first in row-major order as they
    do between marker plateau pixels; a marker never steps, so each heads its
    own basin. Every path rises, so a basin's pixels all join its maximum at
    or above their own value. The pass between two maxima is then the
    highest bottleneck over chains of adjacent basins, each link the
    highest saddle that pair shares, which joining basins in descending
    saddle order finds. Pointer jumping resolves every path in a number of
    whole-array passes logarithmic in the longest.
    """
    height, width = membership.shape
    linear = np.arange(height * width, dtype=np.int64).reshape(height, width)
    values = np.where(membership, normalized, -np.inf)
    padded_values = np.pad(values, 1, constant_values=-np.inf)
    padded_linear = np.pad(linear, 1)
    highest = values.copy()
    step = linear.copy()
    for y_offset, x_offset in _EIGHT_NEIGHBOUR_OFFSETS:
        window = (
            slice(1 + y_offset, 1 + y_offset + height),
            slice(1 + x_offset, 1 + x_offset + width),
        )
        neighbour = padded_values[window]
        neighbour_linear = padded_linear[window]
        higher = (neighbour > highest) | (
            (neighbour == highest) & (neighbour_linear < step)
        )
        highest = np.where(higher, neighbour, highest)
        step = np.where(higher, neighbour_linear, step)
    # Pixels outside the island are never labelled; holding them in place
    # keeps their equal -inf neighbours from adding jumps.
    step = np.where(membership, step, linear)
    for global_y, global_x in peak_positions_yx:
        marker = (global_y - bounds.y_start, global_x - bounds.x_start)
        step[marker] = linear[marker]
    roots = step.ravel()
    while True:
        jumped = roots[roots]
        if np.array_equal(jumped, roots):
            break
        roots = jumped
    _, basins = np.unique(
        roots.reshape(height, width)[membership], return_inverse=True
    )
    labels = np.zeros((height, width), dtype=np.int32)
    labels[membership] = basins.astype(np.int32) + 1
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
    """Merge only basins whose weaker peak lacks reviewed prominence.

    A group that holds no deblending peak joins the first neighbour it is
    offered; two groups that each hold one join only when the weaker peak
    lies less than the minimum depth above the saddle between them.
    """

    def __init__(
        self,
        basin_count: int,
        peaks: Mapping[int, tuple[float, tuple[int, int]]],
    ) -> None:
        self._parent = list(range(basin_count + 1))
        self._peak = dict(peaks)

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
        """Join two groups unless both hold a peak and the weaker is deep.

        A group without a peak always joins; between two peaks, the weaker
        stays apart when it lies at least ``minimum_depth`` above the saddle.
        """
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root == second_root:
            return
        if first_root not in self._peak or second_root not in self._peak:
            winner, loser = (
                (first_root, second_root)
                if first_root in self._peak
                else (second_root, first_root)
            )
        else:
            weaker_value = min(
                self._peak[first_root][0], self._peak[second_root][0]
            )
            if weaker_value - saddle >= minimum_depth:
                return
            winner, loser = sorted(
                (first_root, second_root),
                key=lambda root: (-self._peak[root][0], self._peak[root][1]),
            )
        self._parent[loser] = winner

    def holds_peak(self, label: int) -> bool:
        """Return whether the label's group holds a deblending peak."""
        return self.find(label) in self._peak


def _merge_shallow_regions(
    labels: npt.NDArray[np.int32],
    normalized: npt.NDArray[np.float64],
    bounds: ImageBounds,
    peak_positions_yx: tuple[tuple[int, int], ...],
    config: CompactDeblendConfig,
) -> npt.NDArray[np.int32]:
    """Merge basins by sparse boundary-saddle prominence.

    Each peak's group is the basin holding it. Saddles are taken highest
    first, so two groups are judged where they first meet as the island
    floods down, and every basin must end in a group with a peak.
    """
    peaks: dict[int, tuple[float, tuple[int, int]]] = {}
    for global_y, global_x in peak_positions_yx:
        local = (global_y - bounds.y_start, global_x - bounds.x_start)
        peaks[int(labels[local])] = (
            float(normalized[local]),
            (global_y, global_x),
        )
    basin_count = int(np.max(labels, initial=0))
    groups = _RegionGroups(basin_count, peaks)
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
    if not all(
        groups.holds_peak(label) for label in range(1, basin_count + 1)
    ):
        raise ValueError("watershed did not assign every island pixel")
    root_lookup = np.array(
        [groups.find(label) for label in range(basin_count + 1)],
        dtype=np.int32,
    )
    return _canonicalize_labels(root_lookup[labels])


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
    """Split one admitted island into deterministic watershed regions.

    The watershed floods the island's own intensity: every pixel belongs to
    the peak its steepest ascent reaches, and two peaks are judged at the
    pass between them, the highest level at which one connected part of the
    island holds both.
    """
    normalized, membership = _validate_input(compact_island, config)
    bounds = compact_island.island.bounds
    peaks = _marker_positions(normalized, membership, bounds, config)
    if len(peaks) == 1:
        labels = np.where(membership, 1, 0).astype(np.int32)
    else:
        basins = _ascent_basins(normalized, membership, bounds, peaks)
        labels = _merge_shallow_regions(
            basins,
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
