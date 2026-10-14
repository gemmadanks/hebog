# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Records and window helpers the per-object stages share.

ADR-008's pass D evaluates each object inside the window that holds it and
reduces the results hierarchically. Each per-object stage first has the
cores observe every object's extent, reduces those observations into one
record per parent here, and then reads each object through a window cropped
from a wider read.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from hebog.algorithms.label_groups import label_extents
from hebog.data_models.partitioning import ImageBounds
from hebog.data_models.products import ProductChunk

# The extent scans' cost per pixel of their largest read, which their tasks
# declare (``hebog.stages.task_memory``): the largest traced task peak over
# that read on the 3,000-, 10,000- and 15,402-pixel LoTSS-DR3 anchors and the
# dense ELAIS-N1 central 5,000 pixels, rounded up to eight bytes (plan task
# 17). The component-topology and component-fit stages both scan extents.
EXTENT_SCAN_BYTES_PER_READ_PIXEL = 16


@dataclass(frozen=True, slots=True)
class ParentExtent:
    """One parent's support in each label plane, reduced over the cores."""

    parent_label: int
    direct_bounds: ImageBounds
    measurement_bounds: ImageBounds
    first_pixel_yx: tuple[int, int]
    direct_pixel_count: int


@dataclass(frozen=True, slots=True)
class CoreExtent:
    """One parent's bounds and first pixel as one core observes them."""

    parent_label: int
    direct_bounds: ImageBounds | None
    measurement_bounds: ImageBounds
    first_pixel_yx: tuple[int, int] | None
    tile_id: str
    direct_pixel_count: int


@dataclass(frozen=True, slots=True)
class ExtentBatchResult:
    """Array-free parent extents from one bounded scan task."""

    extents: tuple[CoreExtent, ...]


@dataclass(frozen=True, slots=True)
class PublishBatchResult:
    """Persisted product identities and the labels each plane carried.

    ``observed_labels`` pairs every label a core wrote with the plane that
    carried it — 0 for direct ownership, 1 for measurement ownership — so the
    stage can require both planes to name the same components without holding
    either.
    """

    product_chunks: tuple[ProductChunk, ...]
    observed_labels: tuple[tuple[int, int], ...] = ()
    maximum_parent_read_pixels: int = 0


def union_bounds(
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


def core_label_extents(
    labels: npt.NDArray[np.int32],
    bounds: ImageBounds,
) -> dict[int, tuple[ImageBounds, tuple[int, int], int]]:
    """Return each label's bounds, first pixel and size in one owned core."""
    extents = label_extents(labels)
    return {
        int(value): (
            ImageBounds(
                bounds.y_start + int(y_start),
                bounds.y_start + int(y_stop),
                bounds.x_start + int(x_start),
                bounds.x_start + int(x_stop),
            ),
            (bounds.y_start + int(first_y), bounds.x_start + int(first_x)),
            int(pixel_count),
        )
        for (
            value,
            y_start,
            y_stop,
            x_start,
            x_stop,
            first_y,
            first_x,
            pixel_count,
        ) in zip(
            extents.values,
            extents.y_start,
            extents.y_stop,
            extents.x_start,
            extents.x_stop,
            extents.first_y,
            extents.first_x,
            extents.pixel_count,
            strict=True,
        )
    }


def reduce_extents(
    results: tuple[ExtentBatchResult, ...],
) -> tuple[ParentExtent, ...]:
    """Merge every core's observation into one record per parent."""
    direct: dict[int, ImageBounds | None] = {}
    measurement: dict[int, ImageBounds | None] = {}
    first: dict[int, tuple[int, int] | None] = {}
    direct_pixel_counts: dict[int, int] = {}
    for result in results:
        for extent in result.extents:
            label = extent.parent_label
            direct_pixel_counts[label] = (
                direct_pixel_counts.get(label, 0) + extent.direct_pixel_count
            )
            direct[label] = union_bounds(
                direct.get(label),
                extent.direct_bounds,
            )
            measurement[label] = union_bounds(
                measurement.get(label),
                extent.measurement_bounds,
            )
            candidate = extent.first_pixel_yx
            if candidate is not None:
                known = first.get(label)
                first[label] = (
                    candidate if known is None else min(known, candidate)
                )
    parents: list[ParentExtent] = []
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
            ParentExtent(
                parent_label=label,
                direct_bounds=direct_bounds,
                measurement_bounds=measurement_bounds,
                first_pixel_yx=first_pixel,
                direct_pixel_count=direct_pixel_counts[label],
            )
        )
    return tuple(
        sorted(
            parents,
            key=lambda parent: (parent.first_pixel_yx, parent.parent_label),
        )
    )


def crop_slices(
    bounds: ImageBounds, window: ImageBounds
) -> tuple[slice, slice]:
    """Return the slices selecting one window inside a wider read."""
    return (
        slice(window.y_start - bounds.y_start, window.y_stop - bounds.y_start),
        slice(window.x_start - bounds.x_start, window.x_stop - bounds.x_start),
    )


def parent_holders(
    results: tuple[ExtentBatchResult, ...],
) -> dict[int, frozenset[str]]:
    """Name the cores in which each parent holds a pixel."""
    holders: dict[int, set[str]] = {}
    for result in results:
        for extent in result.extents:
            holders.setdefault(extent.parent_label, set()).add(extent.tile_id)
    return {label: frozenset(tiles) for label, tiles in holders.items()}


def bounds_intersect(first: ImageBounds, second: ImageBounds) -> bool:
    """Return whether two half-open bounds share a pixel."""
    return (
        first.y_start < second.y_stop
        and second.y_start < first.y_stop
        and first.x_start < second.x_stop
        and second.x_start < first.x_stop
    )
