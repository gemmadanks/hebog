# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Group the pixels of a label plane once, for bounded per-label work.

A scan of the whole plane for each label, such as
``np.nonzero(labels == value)``, costs image size times label count, so it
grows with the square of image size at a fixed source density. Grouping the
labelled pixels once instead costs one sort of the labelled pixels, after
which each label's support, extent and extremes are bounded by that label's
own pixel count.

Pixels stay in row-major order inside a group, so a label's first pixel is
the same pixel a per-label scan would report, and results do not depend on
label order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import find_objects

_ValueT = TypeVar("_ValueT", bound=np.generic)

_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class LabelledPixelGroups:
    """Every labelled pixel, grouped by label in row-major order.

    ``flat_positions`` indexes the flattened plane, so an aligned value
    plane is sampled with ``values.reshape(-1)[flat_positions]``. Entry
    ``index`` of every array describes label ``index + 1``.
    """

    flat_positions: npt.NDArray[np.int64]
    starts: npt.NDArray[np.int64]
    sizes: npt.NDArray[np.int64]
    y: npt.NDArray[np.int64]
    x: npt.NDArray[np.int64]
    first_y: npt.NDArray[np.int64]
    first_x: npt.NDArray[np.int64]

    def _require_aligned(self, values: npt.NDArray[Any]) -> None:
        if values.shape != self.flat_positions.shape:
            raise ValueError(
                "label group values must be aligned with the grouped pixels"
            )

    def minimum(self, values: npt.NDArray[_ValueT]) -> npt.NDArray[_ValueT]:
        """Return the smallest value of each label."""
        self._require_aligned(values)
        if self.starts.size == 0:
            return values[:0]
        return np.minimum.reduceat(values, self.starts)

    def maximum(self, values: npt.NDArray[_ValueT]) -> npt.NDArray[_ValueT]:
        """Return the largest value of each label."""
        self._require_aligned(values)
        if self.starts.size == 0:
            return values[:0]
        return np.maximum.reduceat(values, self.starts)


def label_windows(
    labels: npt.NDArray[np.int32] | npt.NDArray[np.int64],
) -> tuple[tuple[slice, slice] | None, ...]:
    """Return the smallest window holding each label, in one pass.

    Entry ``index`` describes label ``index + 1``, and is ``None`` when no
    pixel carries that label. Measuring a label inside its window costs its
    own support instead of the whole plane.
    """
    return tuple(
        cast(
            list[tuple[slice, slice] | None],
            find_objects(np.asarray(labels)),
        )
    )


def group_labelled_pixels(
    labels: npt.NDArray[np.int32] | npt.NDArray[np.int64],
    *,
    label_count: int,
) -> LabelledPixelGroups:
    """Group the pixels of labels ``1`` to ``label_count`` in one pass.

    Raises:
        ValueError: If ``labels`` is not a non-negative two-dimensional
            plane, a label in the range has no pixel, or the plane carries a
            label above ``label_count``. Reductions assume contiguous
            non-empty groups running to the end of the grouped pixels, so
            both a missing label and a stray one fail closed rather than
            borrowing or donating another label's pixels.
    """
    plane = np.asarray(labels)
    if plane.ndim != _IMAGE_DIMENSIONS:
        raise ValueError("label groups need a two-dimensional label plane")
    if plane.size and int(plane.min()) < 0:
        raise ValueError("label groups need non-negative labels")
    flat_labels = plane.reshape(-1)
    positions = np.flatnonzero(flat_labels)
    values = flat_labels[positions]
    if values.size and int(values.max()) > label_count:
        raise ValueError(
            "label groups cannot hold a label above the declared label count"
        )
    order = np.argsort(values, kind="stable")
    positions = positions[order].astype(np.int64, copy=False)
    values = values[order]
    label_values = np.arange(1, label_count + 1, dtype=values.dtype)
    starts = np.searchsorted(values, label_values, side="left")
    stops = np.searchsorted(values, label_values, side="right")
    sizes = (stops - starts).astype(np.int64, copy=False)
    if label_count and int(sizes.min()) == 0:
        raise ValueError("label groups need every label to have support")
    width = plane.shape[1]
    y_pixels = positions // width
    x_pixels = positions % width
    starts = starts.astype(np.int64, copy=False)
    return LabelledPixelGroups(
        flat_positions=positions,
        starts=starts,
        sizes=sizes,
        y=y_pixels,
        x=x_pixels,
        first_y=y_pixels[starts] if label_count else y_pixels[:0],
        first_x=x_pixels[starts] if label_count else x_pixels[:0],
    )


@dataclass(frozen=True, slots=True)
class LabelExtents:
    """Each present label's window, first pixel and size, in row-major order.

    Entry ``index`` of every array describes label ``values[index]``, and
    ``values`` is ascending. ``y_stop`` and ``x_stop`` are exclusive, so the
    window of a label is ``labels[y_start:y_stop, x_start:x_stop]``.
    """

    values: npt.NDArray[np.int64]
    y_start: npt.NDArray[np.int64]
    y_stop: npt.NDArray[np.int64]
    x_start: npt.NDArray[np.int64]
    x_stop: npt.NDArray[np.int64]
    first_y: npt.NDArray[np.int64]
    first_x: npt.NDArray[np.int64]
    pixel_count: npt.NDArray[np.int64]


def label_extents(
    labels: npt.NDArray[np.int32] | npt.NDArray[np.int64],
) -> LabelExtents:
    """Return every positive label's window, first pixel and size, in one pass.

    Unlike :func:`group_labelled_pixels` this accepts any positive labels,
    including a sparse global set with gaps, and describes only the labels a
    pixel actually carries. Non-positive pixels are background.

    Raises:
        ValueError: If ``labels`` is not a two-dimensional plane.
    """
    plane = np.asarray(labels)
    if plane.ndim != _IMAGE_DIMENSIONS:
        raise ValueError("label extents need a two-dimensional label plane")
    flat_labels = plane.reshape(-1)
    positions = np.flatnonzero(flat_labels > 0)
    values = flat_labels[positions]
    order = np.argsort(values, kind="stable")
    positions = positions[order]
    values = values[order].astype(np.int64, copy=False)
    starts = np.flatnonzero(
        np.concatenate(
            (
                np.ones(min(values.size, 1), dtype=np.bool_),
                values[1:] != values[:-1],
            )
        )
    )
    width = plane.shape[1]
    y_pixels = (positions // width).astype(np.int64, copy=False)
    x_pixels = (positions % width).astype(np.int64, copy=False)
    if starts.size == 0:
        empty = np.zeros(0, dtype=np.int64)
        return LabelExtents(
            values=empty,
            y_start=empty,
            y_stop=empty,
            x_start=empty,
            x_stop=empty,
            first_y=empty,
            first_x=empty,
            pixel_count=empty,
        )
    return LabelExtents(
        values=values[starts],
        y_start=np.minimum.reduceat(y_pixels, starts),
        y_stop=np.maximum.reduceat(y_pixels, starts) + 1,
        x_start=np.minimum.reduceat(x_pixels, starts),
        x_stop=np.maximum.reduceat(x_pixels, starts) + 1,
        first_y=y_pixels[starts],
        first_x=x_pixels[starts],
        pixel_count=np.diff(np.append(starts, values.size)).astype(
            np.int64, copy=False
        ),
    )
