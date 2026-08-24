# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Eight-connected local island labelling over deterministic tile cores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from scipy import ndimage

from hebog.algorithms.detection import DetectionThresholdMasks
from hebog.data_models.partitioning import ImageBounds, TilePartition


@dataclass(frozen=True, slots=True)
class LocalIslandSummary:
    """Small mergeable facts for one tile-local connected component."""

    local_label: int
    pixel_count: int
    bounds: ImageBounds
    peak_signal_to_noise: float
    peak_position_yx: tuple[int, int]
    first_pixel_yx: tuple[int, int]
    touches_image_edge: bool
    contains_detection_seed: bool


@dataclass(frozen=True, slots=True)
class TileBoundaryLabels:
    """Local labels on four owned core boundaries for reconciliation."""

    top: npt.NDArray[np.int32]
    bottom: npt.NDArray[np.int32]
    left: npt.NDArray[np.int32]
    right: npt.NDArray[np.int32]


@dataclass(frozen=True, slots=True)
class LocalIslandTileSummary:
    """Compact tile topology safe to return through an executor."""

    partition: TilePartition
    islands: tuple[LocalIslandSummary, ...]
    boundary_labels: TileBoundaryLabels


@dataclass(frozen=True, slots=True)
class LocalIslandTile:
    """One locally labelled core plus mergeable summaries and boundaries."""

    partition: TilePartition
    labels: npt.NDArray[np.int32]
    islands: tuple[LocalIslandSummary, ...]
    boundary_labels: TileBoundaryLabels

    def compact_summary(self) -> LocalIslandTileSummary:
        """Drop the image-sized label core before scheduler reconciliation."""
        return LocalIslandTileSummary(
            partition=self.partition,
            islands=self.islands,
            boundary_labels=self.boundary_labels,
        )


def _read_only_copy(
    values: npt.NDArray[Any],
) -> npt.NDArray[Any]:
    """Return one owned immutable boundary or label array."""
    copied = np.array(values, copy=True)
    copied.setflags(write=False)
    return copied


def _positions_from_linear_indices(
    values: npt.NDArray[np.integer[Any]],
    *,
    image_width: int,
) -> tuple[tuple[int, int], ...]:
    """Convert global row-major indices to integer ``(y, x)`` positions."""
    return tuple(
        (int(value) // image_width, int(value) % image_width)
        for value in values
    )


def label_detection_tile(
    masks: DetectionThresholdMasks,
    partition: TilePartition,
    *,
    image_shape_yx: tuple[int, int],
) -> LocalIslandTile:
    """Label one owned core and reduce component properties without copies."""
    partition.core_bounds.require_inside(image_shape_yx)
    expected_shape = partition.core_bounds.shape_yx
    arrays = (
        masks.normalized_residual,
        masks.island_membership,
        masks.detection_seeds,
    )
    if any(array.shape != expected_shape for array in arrays):
        raise ValueError("detection masks must match the tile core shape")
    if np.any(masks.detection_seeds & ~masks.island_membership):
        raise ValueError("detection seeds must be island members")

    connectivity = np.ones((3, 3), dtype=np.bool_)
    raw_labels, count = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(
            masks.island_membership,
            structure=connectivity,
        ),
    )
    labels = np.asarray(raw_labels, dtype=np.int32)
    bounds = partition.core_bounds
    image_width = image_shape_yx[1]

    if count:
        flat_labels = labels.ravel()
        member_indices = np.flatnonzero(flat_labels)
        member_labels = flat_labels[member_indices]
        member_values = masks.normalized_residual.ravel()[member_indices]
        pixel_counts = np.bincount(
            member_labels,
            minlength=count + 1,
        )[1:]
        local_y, local_x = np.divmod(member_indices, labels.shape[1])
        member_global_linear = np.asarray(
            (local_y + bounds.y_start) * image_width
            + local_x
            + bounds.x_start,
            dtype=np.int64,
        )
        maximum_lookup = np.full(count + 1, -np.inf, dtype=np.float64)
        np.maximum.at(maximum_lookup, member_labels, member_values)
        peak_values = maximum_lookup[1:]
        sentinel = np.iinfo(np.int64).max
        first_lookup = np.full(count + 1, sentinel, dtype=np.int64)
        np.minimum.at(first_lookup, member_labels, member_global_linear)
        first_linear = first_lookup[1:]
        peak_members = member_values == maximum_lookup[member_labels]
        peak_lookup = np.full(count + 1, sentinel, dtype=np.int64)
        np.minimum.at(
            peak_lookup,
            member_labels[peak_members],
            member_global_linear[peak_members],
        )
        peak_linear = peak_lookup[1:]
        object_slices = ndimage.find_objects(labels, max_label=count)
        first_positions = _positions_from_linear_indices(
            first_linear,
            image_width=image_width,
        )
        peak_positions = _positions_from_linear_indices(
            peak_linear,
            image_width=image_width,
        )
        seed_labels = {
            int(value)
            for value in np.unique(labels[masks.detection_seeds])
            if value > 0
        }
        summaries = tuple(
            LocalIslandSummary(
                local_label=local_label,
                pixel_count=int(pixel_counts[local_label - 1]),
                bounds=ImageBounds(
                    bounds.y_start + object_slices[local_label - 1][0].start,
                    bounds.y_start + object_slices[local_label - 1][0].stop,
                    bounds.x_start + object_slices[local_label - 1][1].start,
                    bounds.x_start + object_slices[local_label - 1][1].stop,
                ),
                peak_signal_to_noise=float(peak_values[local_label - 1]),
                peak_position_yx=peak_positions[local_label - 1],
                first_pixel_yx=first_positions[local_label - 1],
                touches_image_edge=(
                    object_slices[local_label - 1][0].start + bounds.y_start
                    == 0
                    or object_slices[local_label - 1][0].stop + bounds.y_start
                    == image_shape_yx[0]
                    or object_slices[local_label - 1][1].start + bounds.x_start
                    == 0
                    or object_slices[local_label - 1][1].stop + bounds.x_start
                    == image_shape_yx[1]
                ),
                contains_detection_seed=local_label in seed_labels,
            )
            for local_label in range(1, count + 1)
        )
    else:
        summaries = ()

    labels = cast(npt.NDArray[np.int32], _read_only_copy(labels))
    return LocalIslandTile(
        partition=partition,
        labels=labels,
        islands=summaries,
        boundary_labels=TileBoundaryLabels(
            top=cast(npt.NDArray[np.int32], _read_only_copy(labels[0, :])),
            bottom=cast(
                npt.NDArray[np.int32],
                _read_only_copy(labels[-1, :]),
            ),
            left=cast(npt.NDArray[np.int32], _read_only_copy(labels[:, 0])),
            right=cast(
                npt.NDArray[np.int32],
                _read_only_copy(labels[:, -1]),
            ),
        ),
    )
