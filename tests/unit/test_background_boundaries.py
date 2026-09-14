"""Independent boundary conditioning and bounded-summary regressions."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from hebog.algorithms.background import (
    PreparedRmsGrid,
    interpolate_prepared_rms_grid,
    plan_rms_grid,
    subset_prepared_rms_grid,
)
from hebog.data_models import ImageBounds


def _affine_grid(
    shape: tuple[int, int], window: int, step: int
) -> PreparedRmsGrid:
    geometry = plan_rms_grid(
        image_shape_yx=shape,
        window_shape_yx=(window, window),
        step_yx=(step, step),
    )
    y, x = np.meshgrid(
        geometry.sample_coordinates_y,
        geometry.sample_coordinates_x,
        indexing="ij",
    )
    return PreparedRmsGrid(
        geometry=geometry,
        background=-0.002 + 1e-6 * y - 2e-6 * x,
        rms=np.full(geometry.shape_yx, 0.0002),
        fallback_cells=np.zeros(geometry.shape_yx, dtype=np.bool_),
        scientifically_available=True,
    )


@pytest.mark.parametrize("window,step", ((128, 42), (35, 7)))
@pytest.mark.parametrize("sign", (-1, 1))
@pytest.mark.parametrize("corner", ((0, 0), (0, -1), (-1, 0), (-1, -1)))
def test_boundary_sample_error_has_bounded_gain(
    window: int, step: int, sign: int, corner: tuple[int, int]
) -> None:
    """Stochastic cell slopes must not amplify 0.5-sigma errors 100-fold."""
    shape = (512, 509)
    grid = _affine_grid(shape, window, step)
    bounds = ImageBounds(0, shape[0], 0, shape[1])
    valid = np.ones(shape, dtype=np.bool_)
    reference = interpolate_prepared_rms_grid(grid, bounds, valid)
    perturbed = np.array(grid.background, copy=True)
    perturbation = sign * 1e-4
    perturbed[corner] += perturbation
    perturbed_rms = np.array(grid.rms, copy=True)
    perturbed_rms[corner] += perturbation
    actual = interpolate_prepared_rms_grid(
        replace(grid, background=perturbed, rms=perturbed_rms), bounds, valid
    )
    # A secant at least as long as the distance to the image edge has a
    # last-cell weight <= 2 per axis, hence <= 4 at a corner.
    assert np.max(np.abs(actual.background - reference.background)) <= (
        4 * abs(perturbation) + 1e-15
    )
    assert np.max(np.abs(actual.rms - reference.rms)) <= (
        4 * abs(perturbation) + 1e-15
    )


@pytest.mark.parametrize("window,step", ((128, 42), (35, 7)))
def test_real_gradient_and_boundary_subsets_are_preserved(
    window: int, step: int
) -> None:
    """Stable extrapolation must not flatten a real background gradient."""
    shape = (512, 509)
    grid = _affine_grid(shape, window, step)
    bounds = ImageBounds(0, shape[0], 0, shape[1])
    valid = np.ones(shape, dtype=np.bool_)
    valid[0, 0] = False
    full = interpolate_prepared_rms_grid(grid, bounds, valid)
    y, x = np.indices(shape)
    expected = -0.002 + 1e-6 * y - 2e-6 * x
    np.testing.assert_allclose(
        full.background[valid], expected[valid], atol=1e-15
    )
    assert np.isnan(full.background[0, 0])
    assert np.isnan(full.rms[0, 0])
    # One-pixel edge cores must carry the same extrapolation anchors as a
    # complete plane, even next to nearly coincident final window centres.
    for core in (
        ImageBounds(0, 1, 0, 1),
        ImageBounds(511, 512, 508, 509),
        ImageBounds(511, 512, 0, 64),
        ImageBounds(0, 64, 508, 509),
        ImageBounds(70, 90, 200, 211),
    ):
        selection = np.s_[
            core.y_start : core.y_stop, core.x_start : core.x_stop
        ]
        local = subset_prepared_rms_grid(grid, core)
        actual = interpolate_prepared_rms_grid(local, core, valid[selection])
        np.testing.assert_array_equal(
            actual.background, full.background[selection]
        )
        np.testing.assert_array_equal(actual.rms, full.rms[selection])


@pytest.mark.parametrize("shape", ((1, 1), (1, 73), (73, 1), (17, 18)))
def test_short_axes_retain_constant_and_unavailable_semantics(
    shape: tuple[int, int],
) -> None:
    """Singleton/short grids cannot invent slopes or unavailable samples."""
    initial = _affine_grid(shape, 16, 5)
    grid = replace(
        initial,
        background=np.full(initial.geometry.shape_yx, -2.0),
        rms=np.full(initial.geometry.shape_yx, 3.0),
    )
    bounds = ImageBounds(0, shape[0], 0, shape[1])
    valid = np.ones(shape, dtype=np.bool_)
    actual = interpolate_prepared_rms_grid(grid, bounds, valid)
    np.testing.assert_allclose(actual.background, -2.0, atol=1e-14)
    np.testing.assert_allclose(actual.rms, 3.0, atol=1e-14)
    corner = ImageBounds(shape[0] - 1, shape[0], shape[1] - 1, shape[1])
    subset = interpolate_prepared_rms_grid(
        subset_prepared_rms_grid(grid, corner),
        corner,
        np.ones((1, 1), dtype=np.bool_),
    )
    np.testing.assert_array_equal(
        subset.background, actual.background[-1:, -1:]
    )
    np.testing.assert_array_equal(subset.rms, actual.rms[-1:, -1:])
