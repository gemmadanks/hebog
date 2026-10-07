"""Which input pixels the finder measures: the ingress validity rule.

A pixel is invalid when its value is not finite (NaN, or an infinity), or
when it lies in a block of one repeated value: when any 3x3 square that
holds it holds one value. Every pixel of such a square is invalid, its edge
as much as its centre. Imagers and mosaicking tools fill regions they did
not observe with a constant, often zero, as others fill them with NaN, and
noise has no such squares. Blanking the whole square blanks a constant
region up to its last pixel, as NaN padding is blank, so no ring of the
constant is left beside the data as a step that detection could find, no
noise or background window measures it, and the finder never publishes a
noise estimate of zero over it.

A square holds one value when its centre equals all eight of its
neighbours, so the invalid pixels are those centres and every pixel beside
one. At the image edge a square is clipped to the image: the outside of the
image is no different value, so a pixel at the edge is a centre when it
equals the neighbours it has inside the image (five, or three at a corner),
and a block reaches the image edge. NaN equals nothing, so a square that
holds a NaN is not of one value.

A pixel's validity therefore depends on the pixels up to two away: a centre
beside it, and that centre's own neighbours. A window's validity is decided
from a read two pixels wider on every side, clipped to the image, which
makes it independent of how the image is tiled.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from hebog.data_models.partitioning import ImageBounds

# How far, in pixels, a 3x3 square reaches from its centre.
_SQUARE_REACH_PIXELS = 1
# How far a pixel's validity looks: to a centre beside it, and from there to
# that centre's neighbours.
_VALIDITY_REACH_PIXELS = 2 * _SQUARE_REACH_PIXELS


def validity_read_bounds(
    bounds: ImageBounds,
    image_shape_yx: tuple[int, int],
) -> ImageBounds:
    """Return the read that decides the validity of ``bounds``.

    It is ``bounds`` widened by two pixels on every side, clipped to the
    image.

    Examples:
        >>> validity_read_bounds(ImageBounds(0, 4, 3, 6), (10, 6))
        ImageBounds(y_start=0, y_stop=6, x_start=1, x_stop=6)
    """
    return bounds.expanded(_VALIDITY_REACH_PIXELS, image_shape_yx)


def constant_square_centres(
    neighbourhood: npt.NDArray[np.float64],
) -> npt.NDArray[np.bool_]:
    """Return which pixels equal all eight of their neighbours.

    Such a pixel is the centre of a 3x3 square of one value.

    Args:
        neighbourhood: Values with a one-pixel border around the pixels
            tested, so the result is two pixels smaller on each axis.

    Returns:
        ``True`` where a pixel equals every neighbour. NaN equals nothing.

    Examples:
        >>> values = np.zeros((4, 5))
        >>> values[:, 3:] = [1.0, 2.0]
        >>> constant_square_centres(values).astype(int)
        array([[1, 0, 0],
               [1, 0, 0]])
    """
    # A pixel equals all eight neighbours when its 3x3 square holds one
    # value: each of the square's three rows, and its middle column, is a run
    # of three equal values. Each adjacent pair is compared once, and the
    # squares that contain the pair share the answer. NaN equals nothing.
    equal_to_right = neighbourhood[:, :-1] == neighbourhood[:, 1:]
    equal_below = neighbourhood[:-1, :] == neighbourhood[1:, :]
    row_runs = equal_to_right[:, :-1] & equal_to_right[:, 1:]
    column_runs = equal_below[:-1, 1:-1] & equal_below[1:, 1:-1]
    return row_runs[:-2] & row_runs[1:-1] & row_runs[2:] & column_runs


def _marked_or_beside_marked(
    marked: npt.NDArray[np.bool_],
) -> npt.NDArray[np.bool_]:
    """Return which pixels are marked or beside a marked pixel.

    ``marked`` has a one-pixel border around the pixels returned, so the
    result is two pixels smaller on each axis. This is a dilation by a 3x3
    square, taken as three rows and then three columns.
    """
    rows = marked[:-2] | marked[1:-1] | marked[2:]
    return rows[:, :-2] | rows[:, 1:-1] | rows[:, 2:]


def _clipped_margin(
    inner: ImageBounds,
    outer: ImageBounds,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return how much of a one-pixel margin clipping took on each side.

    ``outer`` is ``inner`` widened by one pixel and clipped to the image, so
    each side of the result is 0, or 1 where ``inner`` meets the image
    edge.
    """
    reach = _SQUARE_REACH_PIXELS
    return (
        (
            reach - (inner.y_start - outer.y_start),
            reach - (outer.y_stop - inner.y_stop),
        ),
        (
            reach - (inner.x_start - outer.x_start),
            reach - (outer.x_stop - inner.x_stop),
        ),
    )


def valid_input_pixels(
    values: npt.NDArray[np.float64],
    bounds: ImageBounds,
    image_shape_yx: tuple[int, int],
) -> npt.NDArray[np.bool_]:
    """Return which pixels of ``bounds`` the finder measures.

    Args:
        values: Physical pixel values read over
            :func:`validity_read_bounds` of ``bounds``.
        bounds: The window whose validity is wanted.
        image_shape_yx: The shape of the whole image.

    Returns:
        A mask of shape ``bounds.shape_yx``: ``True`` where the pixel is
        finite and no 3x3 square of one value holds it.

    Raises:
        ValueError: If ``values`` does not cover the validity read.

    Examples:
        >>> values = np.zeros((4, 6))
        >>> values[:, 4:] = np.arange(8.0).reshape(4, 2) + 1.0
        >>> bounds = ImageBounds(0, 4, 0, 6)
        >>> valid_input_pixels(values, bounds, (4, 6)).astype(int)
        array([[0, 0, 0, 0, 1, 1],
               [0, 0, 0, 0, 1, 1],
               [0, 0, 0, 0, 1, 1],
               [0, 0, 0, 0, 1, 1]])
    """
    read = validity_read_bounds(bounds, image_shape_yx)
    if values.shape != read.shape_yx:
        raise ValueError(
            f"validity of {bounds} needs values over {read}, "
            f"not shape {values.shape}"
        )
    # A centre whose square can hold a window pixel lies inside the image
    # and at most one pixel beyond the window; the read is that region
    # widened by one pixel, clipped to the image.
    centre_bounds = bounds.expanded(_SQUARE_REACH_PIXELS, image_shape_yx)
    # Where the read stops at the image edge, the border is the edge pixel
    # repeated, which the centre test never counts as a different value, so
    # an edge pixel is compared with the neighbours it has.
    edge_padding = _clipped_margin(centre_bounds, read)
    neighbourhood = (
        np.pad(values, edge_padding, mode="edge")
        if any(any(side) for side in edge_padding)
        else values
    )
    centres = constant_square_centres(neighbourhood)
    # Outside the image there is no centre, so the border there is False.
    in_square = _marked_or_beside_marked(
        np.pad(centres, _clipped_margin(bounds, centre_bounds))
    )
    y_offset = bounds.y_start - read.y_start
    x_offset = bounds.x_start - read.x_start
    height, width = bounds.shape_yx
    window_values = values[
        y_offset : y_offset + height,
        x_offset : x_offset + width,
    ]
    return np.isfinite(window_values) & ~in_square
