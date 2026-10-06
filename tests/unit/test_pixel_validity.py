"""Tests for the ingress rule that decides which input pixels are valid."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from hebog.data_models import ImageBounds
from hebog.io.pixel_validity import (
    constant_square_centres,
    valid_input_pixels,
    validity_read_bounds,
)


def _whole_image_validity(
    values: npt.NDArray[np.float64],
) -> npt.NDArray[np.bool_]:
    """Return the validity of every pixel of one in-memory image."""
    shape_yx = (values.shape[0], values.shape[1])
    bounds = ImageBounds(0, shape_yx[0], 0, shape_yx[1])
    return valid_input_pixels(values, bounds, shape_yx)


def _in_a_constant_square(
    values: npt.NDArray[np.float64],
) -> npt.NDArray[np.bool_]:
    """Return the rule as written, one square at a time.

    A deliberately plain oracle: each pixel's 3x3 square, clipped to the
    image, and every pixel of the square when it holds one value.
    """
    height, width = values.shape
    held = np.zeros(values.shape, dtype=np.bool_)
    for y, x in np.ndindex(height, width):
        square = (
            slice(max(y - 1, 0), y + 2),
            slice(max(x - 1, 0), x + 2),
        )
        if np.all(values[square] == values[y, x]):
            held[square] = True
    return held


def test_every_pixel_of_a_square_of_one_value_is_invalid() -> None:
    """The square's edge is as invalid as its centre."""
    values = np.arange(25, dtype=np.float64).reshape(5, 5)
    values[1:4, 1:4] = 7.0

    validity = _whole_image_validity(values)

    expected = np.ones((5, 5), dtype=np.bool_)
    expected[1:4, 1:4] = False
    np.testing.assert_array_equal(validity, expected)


@pytest.mark.parametrize("pixel_yx", ((1, 1), (1, 3), (3, 2), (2, 3), (2, 2)))
def test_one_different_pixel_leaves_no_square_of_one_value(
    pixel_yx: tuple[int, int],
) -> None:
    """A corner of the square counts as much as its centre."""
    values = np.arange(25, dtype=np.float64).reshape(5, 5)
    values[1:4, 1:4] = 7.0
    values[pixel_yx] = 7.5

    assert _whole_image_validity(values).all()


def test_a_constant_region_is_invalid_up_to_its_last_pixel() -> None:
    """No ring of the constant is left beside the data, as with NaN."""
    values = np.random.default_rng(46).normal(size=(9, 12))
    values[:, :5] = 0.0
    values[2:6, 8:11] = 1.0

    validity = _whole_image_validity(values)

    assert not validity[:, :5].any()
    assert not validity[2:6, 8:11].any()
    assert validity[:, 5:8].all()
    assert validity[:2, 8:].all() and validity[6:, 8:].all()
    assert validity[:, 11].all()


def test_nan_and_infinite_pixels_are_invalid_and_equal_nothing() -> None:
    """A NaN breaks every square that holds it, but not the others.

    The zeros around a NaN inside zero padding lie in squares of zeros
    beside it, and are invalid; a zero that only squares holding a NaN or an
    infinity contain is valid. A block of infinities is invalid by the
    finite rule already.
    """
    values = np.zeros((7, 7))
    values[4, 4] = np.nan
    values[0, :] = np.inf
    values[1, 0] = -np.inf
    values[2, 1] = np.nan

    validity = _whole_image_validity(values)

    assert not validity[4, 4] and not validity[2, 1]
    assert not validity[0].any()
    assert not validity[1, 0]
    assert not validity[3:6, 3:6].any()
    # Every square holding these two zeros holds a NaN or an infinity.
    assert validity[1, 1] and validity[2, 0]
    assert np.count_nonzero(validity) == 2
    np.testing.assert_array_equal(
        validity, np.isfinite(values) & ~_in_a_constant_square(values)
    )


def test_a_square_at_the_image_edge_is_clipped_to_the_image() -> None:
    """Outside the image is no different value, so a block reaches the edge.

    A pixel at the edge is a square's centre when it equals the neighbours
    it has: five, or three at a corner.
    """
    values = np.zeros((4, 6))
    values[:, 4:] = np.arange(8, dtype=np.float64).reshape(4, 2) + 1.0

    validity = _whole_image_validity(values)

    assert not validity[:, :4].any()
    assert validity[:, 4:].all()


def test_two_by_two_of_one_value_is_a_square_only_in_an_image_corner() -> None:
    """A corner pixel's clipped square is two by two."""
    values = np.arange(48, dtype=np.float64).reshape(6, 8)
    values[0:2, 0:2] = -1.0
    values[2:4, 3:5] = -2.0
    values[4:6, 6:8] = -3.0

    validity = _whole_image_validity(values)

    assert not validity[0:2, 0:2].any()
    assert validity[2:4, 3:5].all()
    assert not validity[4:6, 6:8].any()
    assert np.count_nonzero(~validity) == 8


def test_a_constant_image_is_wholly_invalid() -> None:
    """An all-zero image is a block, as an all-NaN image is invalid."""
    assert not _whole_image_validity(np.zeros((3, 4))).any()
    assert not _whole_image_validity(np.full((1, 5), -2.0)).any()
    assert not _whole_image_validity(np.zeros((1, 1))).any()


def test_a_line_two_pixels_wide_is_no_block() -> None:
    """No 3x3 square fits inside a line two pixels wide."""
    values = np.random.default_rng(46).normal(size=(8, 8))
    values[3:5, :] = 0.0

    assert _whole_image_validity(values).all()


def test_a_strip_at_the_image_edge_is_a_block_from_two_pixels_wide() -> None:
    """A strip two pixels wide at the edge holds clipped squares."""
    values = np.random.default_rng(46).normal(size=(8, 8))
    values[:, 6:] = 0.0
    one_wide = values.copy()
    one_wide[:, 6] = 1.0

    validity = _whole_image_validity(values)

    assert validity[:, :6].all()
    assert not validity[:, 6:].any()
    assert _whole_image_validity(one_wide).all()


def test_validity_is_decided_from_two_pixels_beyond_the_window() -> None:
    """A square's centre beside the window, and its neighbours, decide.

    The window holds the left column of a square of zeros; the square's
    centre is one pixel beyond the window, and its right column two.
    """
    values = np.arange(54, dtype=np.float64).reshape(6, 9)
    values[1:4, 4:7] = 0.0
    bounds = ImageBounds(2, 4, 2, 5)
    read = validity_read_bounds(bounds, (6, 9))

    def window_validity(
        image: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.bool_]:
        return valid_input_pixels(
            image[read.y_start : read.y_stop, read.x_start : read.x_stop],
            bounds,
            (6, 9),
        )

    broken = values.copy()
    broken[2, 6] = 99.0

    assert read == ImageBounds(0, 6, 0, 7)
    np.testing.assert_array_equal(
        window_validity(values), ((True, True, False), (True, True, False))
    )
    assert window_validity(broken).all()


def test_validity_needs_values_over_its_whole_read() -> None:
    """A window read without its two-pixel margin cannot be judged."""
    with pytest.raises(ValueError, match="needs values over"):
        valid_input_pixels(np.zeros((4, 4)), ImageBounds(2, 4, 3, 5), (6, 7))


def test_constant_square_centres_returns_the_interior_shape() -> None:
    """The border is only compared against, never judged."""
    values = np.zeros((5, 6))
    values[0, 0] = np.nan

    centres = constant_square_centres(values)

    assert centres.shape == (3, 4)
    assert not centres[0, 0]
    assert centres[1:, :].all()
    assert centres[0, 1:].all()


def _equals_each_neighbour(
    neighbourhood: npt.NDArray[np.float64],
) -> npt.NDArray[np.bool_]:
    """Return the centre test as written: a pixel against each of its eight."""
    height = neighbourhood.shape[0] - 2
    width = neighbourhood.shape[1] - 2
    centre = neighbourhood[1:-1, 1:-1]
    repeated = np.ones((height, width), dtype=np.bool_)
    for y_offset, x_offset in np.ndindex(3, 3):
        if (y_offset, x_offset) != (1, 1):
            repeated &= (
                neighbourhood[
                    y_offset : y_offset + height,
                    x_offset : x_offset + width,
                ]
                == centre
            )
    return repeated


def _repeated_values(
    seed: int, shape_yx: tuple[int, int]
) -> npt.NDArray[np.float64]:
    """Return few, mostly equal values, so that squares of one value form.

    They include NaN, both infinities and the two zeros, which compare
    equal.
    """
    choices = np.array(
        [0.0, 0.0, 0.0, 0.0, -0.0, 1.0, np.nan, np.inf, -np.inf]
    )
    return np.random.default_rng(seed).choice(choices, size=shape_yx)


@pytest.mark.parametrize("seed", range(12))
def test_constant_square_centres_equal_each_pixel_against_its_neighbours(
    seed: int,
) -> None:
    """Comparing each adjacent pair once finds the pixels it always found."""
    shape = tuple(
        int(side) for side in np.random.default_rng(seed).integers(3, 14, 2)
    )
    values = _repeated_values(seed, (shape[0], shape[1]))

    np.testing.assert_array_equal(
        constant_square_centres(values), _equals_each_neighbour(values)
    )


@pytest.mark.parametrize("seed", range(12))
def test_the_rule_invalidates_every_pixel_of_every_square_of_one_value(
    seed: int,
) -> None:
    """The vectorised rule agrees with the rule as written."""
    shape = tuple(
        int(side) for side in np.random.default_rng(seed).integers(1, 14, 2)
    )
    values = _repeated_values(seed, (shape[0], shape[1]))

    np.testing.assert_array_equal(
        _whole_image_validity(values),
        np.isfinite(values) & ~_in_a_constant_square(values),
    )


@pytest.mark.parametrize("seed", range(6))
def test_a_windows_validity_is_that_of_the_same_pixels_in_the_image(
    seed: int,
) -> None:
    """Whatever window holds a pixel decides its validity the same way."""
    generator = np.random.default_rng(seed)
    shape_yx = (17, 23)
    values = generator.choice(np.array([0.0, 0.0, 0.0, 1.0, np.nan]), shape_yx)
    whole = _whole_image_validity(values)

    for _ in range(25):
        y_start, x_start = (
            int(generator.integers(0, side)) for side in shape_yx
        )
        bounds = ImageBounds(
            y_start,
            int(generator.integers(y_start + 1, shape_yx[0] + 1)),
            x_start,
            int(generator.integers(x_start + 1, shape_yx[1] + 1)),
        )
        read = validity_read_bounds(bounds, shape_yx)

        window = valid_input_pixels(
            values[read.y_start : read.y_stop, read.x_start : read.x_stop],
            bounds,
            shape_yx,
        )

        np.testing.assert_array_equal(
            window,
            whole[
                bounds.y_start : bounds.y_stop,
                bounds.x_start : bounds.x_stop,
            ],
        )


@pytest.mark.parametrize("tile_shape_yx", ((1, 1), (2, 3), (4, 4), (5, 7)))
def test_every_tiling_assembles_the_whole_image_validity(
    tile_shape_yx: tuple[int, int],
) -> None:
    """Squares cut by every seam and four-way corner are judged whole.

    Blocks end one and two pixels from the seams, cross them, and reach the
    image edges and corners.
    """
    shape_yx = (17, 23)
    values = np.random.default_rng(46).normal(size=shape_yx)
    values[0:4, 0:5] = 0.0
    values[3:9, 6:13] = 2.0
    values[12:, 18:] = -1.0
    values[10:13, 1:4] = 0.5
    values[14:17, 8:10] = 0.5
    whole = _whole_image_validity(values)
    assembled = np.zeros(shape_yx, dtype=np.bool_)

    for y_start in range(0, shape_yx[0], tile_shape_yx[0]):
        for x_start in range(0, shape_yx[1], tile_shape_yx[1]):
            bounds = ImageBounds(
                y_start,
                min(y_start + tile_shape_yx[0], shape_yx[0]),
                x_start,
                min(x_start + tile_shape_yx[1], shape_yx[1]),
            )
            read = validity_read_bounds(bounds, shape_yx)
            assembled[
                bounds.y_start : bounds.y_stop,
                bounds.x_start : bounds.x_stop,
            ] = valid_input_pixels(
                values[read.y_start : read.y_stop, read.x_start : read.x_stop],
                bounds,
                shape_yx,
            )

    np.testing.assert_array_equal(assembled, whole)
    np.testing.assert_array_equal(whole, ~_in_a_constant_square(values))
    assert not whole[0:4, 0:5].any() and not whole[3:9, 6:13].any()
    assert not whole[12:, 18:].any() and not whole[10:13, 1:4].any()
    assert whole[14:17, 8:10].all()
