"""Tests for bounded coarse-grid background and RMS estimation."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from hebog.algorithms.background import (
    RmsGridBatchStatistics,
    RmsGridGeometry,
    RmsWindowBatch,
    assemble_rms_grid_statistics,
    estimate_rms_grid_batch,
    interpolate_prepared_rms_grid,
    plan_rms_grid,
    plan_rms_window_batches,
    prepare_rms_grid_for_interpolation,
)
from hebog.config import RmsWindowStatisticsConfig
from hebog.data_models import ImageBounds
from hebog.executors import SerialExecutor
from hebog.io.base import ImageWindow
from hebog.stages.background import estimate_rms_grid


class _ArrayImageSource:
    """Record bounded reads from one in-memory plane."""

    def __init__(
        self,
        values: np.ndarray,
        valid_pixels: np.ndarray | None = None,
    ) -> None:
        self.values = np.asarray(values, dtype=np.float64)
        self.valid_pixels = (
            np.isfinite(self.values)
            if valid_pixels is None
            else np.asarray(valid_pixels, dtype=np.bool_)
        )
        self.read_bounds: list[ImageBounds] = []

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return one owned bounded window and remember its geometry."""
        bounds.require_inside(tuple(self.values.shape))
        self.read_bounds.append(bounds)
        selection = (
            slice(bounds.y_start, bounds.y_stop),
            slice(bounds.x_start, bounds.x_stop),
        )
        return ImageWindow(
            bounds=bounds,
            values=np.array(self.values[selection], copy=True),
            valid_pixels=np.array(self.valid_pixels[selection], copy=True),
        )


def _statistics_config(
    *,
    minimum_samples: int = 6,
) -> RmsWindowStatisticsConfig:
    """Return the explicit policy shared by coarse-grid tests."""
    return RmsWindowStatisticsConfig(
        clipping_sigma=3.0,
        maximum_iterations=10,
        minimum_samples=minimum_samples,
    )


def _estimate_batch(
    source: _ArrayImageSource,
    grid: RmsGridGeometry,
    batch: RmsWindowBatch,
) -> RmsGridBatchStatistics:
    """Apply the pure batch kernel to one recorded bounded source read."""
    window = source.read_window(batch.read_bounds)
    return estimate_rms_grid_batch(
        window.values,
        window.valid_pixels,
        grid,
        batch,
        _statistics_config(),
    )


def test_plans_edge_aligned_global_windows_and_sample_coordinates() -> None:
    """A final shifted window covers each edge without clipping or padding."""
    grid = plan_rms_grid(
        image_shape_yx=(11, 14),
        window_shape_yx=(5, 6),
        step_yx=(4, 5),
    )

    assert grid.window_starts_y == (0, 4, 6)
    assert grid.window_starts_x == (0, 5, 8)
    assert grid.sample_coordinates_y == (2.0, 6.0, 8.0)
    assert grid.sample_coordinates_x == (2.5, 7.5, 10.5)
    assert grid.shape_yx == (3, 3)
    assert grid.cell_count == 9


def test_small_image_uses_one_clipped_whole_image_window() -> None:
    """A configured window larger than the image remains bounded."""
    grid = plan_rms_grid(
        image_shape_yx=(3, 4),
        window_shape_yx=(9, 8),
        step_yx=(3, 2),
    )

    assert grid.effective_window_shape_yx == (3, 4)
    assert grid.window_starts_y == (0,)
    assert grid.window_starts_x == (0,)
    assert grid.sample_coordinates_y == (1.0,)
    assert grid.sample_coordinates_x == (1.5,)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"image_shape_yx": (0, 8)}, "image shape"),
        ({"window_shape_yx": (0, 4)}, "window shape"),
        ({"step_yx": (0, 2)}, "step"),
        ({"window_shape_yx": (3, 4), "step_yx": (4, 2)}, "step"),
    ],
)
def test_rejects_invalid_grid_geometry(
    arguments: dict[str, tuple[int, int]],
    message: str,
) -> None:
    """Invalid window policies fail before reading image pixels."""
    values = {
        "image_shape_yx": (8, 8),
        "window_shape_yx": (4, 4),
        "step_yx": (2, 2),
    }
    values.update(arguments)

    with pytest.raises(ValueError, match=message):
        plan_rms_grid(**values)


def test_plans_rectangular_batches_covering_each_cell_once() -> None:
    """Cell batching bounds memory without creating one task per window."""
    grid = plan_rms_grid(
        image_shape_yx=(29, 31),
        window_shape_yx=(7, 9),
        step_yx=(4, 5),
    )

    batches = plan_rms_window_batches(grid, maximum_cells=6)
    visits = np.zeros(grid.shape_yx, dtype=np.uint8)
    for batch in batches:
        visits[
            batch.grid_y_start : batch.grid_y_stop,
            batch.grid_x_start : batch.grid_x_stop,
        ] += 1
        assert batch.cell_count <= 6
        assert batch.read_bounds.shape_yx[0] <= 11
        assert batch.read_bounds.shape_yx[1] <= 19

    np.testing.assert_array_equal(visits, 1)
    assert len(batches) < grid.cell_count


@pytest.mark.parametrize("maximum_cells", [0, -1, True, 2.5])
def test_rejects_invalid_batch_cell_limits(maximum_cells: object) -> None:
    """Batch sizing is a positive integer resource policy."""
    grid = plan_rms_grid(
        image_shape_yx=(8, 8),
        window_shape_yx=(4, 4),
        step_yx=(2, 2),
    )

    with pytest.raises(ValueError, match="maximum_cells"):
        plan_rms_window_batches(grid, maximum_cells=maximum_cells)  # type: ignore[arg-type]


def test_estimates_an_affine_background_from_vectorised_window_blocks() -> (
    None
):
    """Window medians lie on the analytic spatial-affine background."""
    y, x = np.indices((17, 19), dtype=np.float64)
    image = 4.0 + 0.25 * y - 0.1 * x
    source = _ArrayImageSource(image)
    grid = plan_rms_grid(
        image_shape_yx=image.shape,
        window_shape_yx=(5, 5),
        step_yx=(3, 4),
    )

    statistics = estimate_rms_grid(
        source,
        grid,
        _statistics_config(),
        SerialExecutor(),
        maximum_batch_cells=6,
    )

    expected_y, expected_x = np.meshgrid(
        grid.sample_coordinates_y,
        grid.sample_coordinates_x,
        indexing="ij",
    )
    np.testing.assert_allclose(
        statistics.background,
        4.0 + 0.25 * expected_y - 0.1 * expected_x,
        atol=1e-12,
    )
    np.testing.assert_array_equal(statistics.available, True)
    assert len(source.read_bounds) < grid.cell_count
    with pytest.raises(ValueError, match="read-only"):
        statistics.background[0, 0] = 0.0


def test_assembly_is_independent_of_batch_completion_order() -> None:
    """Canonical cell indices, not executor order, determine the grid."""
    image = np.arange(18 * 20, dtype=np.float64).reshape(18, 20)
    grid = plan_rms_grid(
        image_shape_yx=image.shape,
        window_shape_yx=(6, 6),
        step_yx=(3, 3),
    )
    batches = plan_rms_window_batches(grid, maximum_cells=8)
    source = _ArrayImageSource(image)
    expected = estimate_rms_grid(
        source,
        grid,
        _statistics_config(),
        SerialExecutor(),
        maximum_batch_cells=8,
    )
    batch_results = [_estimate_batch(source, grid, batch) for batch in batches]

    actual = assemble_rms_grid_statistics(grid, reversed(batch_results))

    np.testing.assert_array_equal(actual.background, expected.background)
    np.testing.assert_array_equal(actual.rms, expected.rms)
    np.testing.assert_array_equal(actual.available, expected.available)


@pytest.mark.parametrize("mode", ["missing", "duplicate"])
def test_assembly_rejects_missing_or_duplicate_cells(mode: str) -> None:
    """A partial or conflicting coarse grid cannot be interpolated."""
    image = np.ones((12, 12), dtype=np.float64)
    source = _ArrayImageSource(image)
    grid = plan_rms_grid(
        image_shape_yx=image.shape,
        window_shape_yx=(4, 4),
        step_yx=(2, 2),
    )
    batches = plan_rms_window_batches(grid, maximum_cells=4)
    results = [_estimate_batch(source, grid, batch) for batch in batches]
    supplied = results[:-1] if mode == "missing" else [*results, results[0]]

    with pytest.raises(ValueError, match=mode):
        assemble_rms_grid_statistics(grid, supplied)


def test_sparse_grid_cells_use_cached_nearest_fallback_before_interpolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unavailable cells are filled without rerunning window statistics."""
    image = np.tile(np.array([-1.0, 1.0]), 18).reshape(6, 6)
    valid = np.ones_like(image, dtype=np.bool_)
    valid[0:4, 2:4] = False
    source = _ArrayImageSource(image, valid)
    grid = plan_rms_grid(
        image_shape_yx=image.shape,
        window_shape_yx=(4, 4),
        step_yx=(2, 2),
    )
    statistics = estimate_rms_grid(
        source,
        grid,
        _statistics_config(minimum_samples=10),
        SerialExecutor(),
        maximum_batch_cells=4,
    )
    assert not statistics.available.all()
    prepared = prepare_rms_grid_for_interpolation(statistics)

    def fail_if_recomputed(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("interpolation recomputed RMS statistics")

    monkeypatch.setattr(
        "hebog.algorithms.background.estimate_rms_window_statistics",
        fail_if_recomputed,
    )
    bounds = ImageBounds(0, 6, 0, 6)
    first = interpolate_prepared_rms_grid(
        prepared,
        bounds,
        np.ones((6, 6), dtype=np.bool_),
    )
    second = interpolate_prepared_rms_grid(
        prepared,
        bounds,
        np.ones((6, 6), dtype=np.bool_),
    )

    assert first.fallback_cell_count == np.count_nonzero(~statistics.available)
    assert np.isfinite(first.background).all()
    assert np.isfinite(first.rms).all()
    np.testing.assert_array_equal(first.background, second.background)
    np.testing.assert_array_equal(first.rms, second.rms)


def test_interpolation_preserves_affine_background_at_edges_and_tiles() -> (
    None
):
    """Linear interpolation and extrapolation preserve spatial-affine maps."""
    y, x = np.indices((17, 19), dtype=np.float64)
    image = -3.0 + 0.5 * y + 0.25 * x
    source = _ArrayImageSource(image)
    grid = plan_rms_grid(
        image_shape_yx=image.shape,
        window_shape_yx=(5, 5),
        step_yx=(3, 4),
    )
    statistics = estimate_rms_grid(
        source,
        grid,
        _statistics_config(),
        SerialExecutor(),
        maximum_batch_cells=8,
    )
    prepared = prepare_rms_grid_for_interpolation(statistics)
    bounds = ImageBounds(7, 17, 8, 19)
    validity = np.ones(bounds.shape_yx, dtype=np.bool_)
    validity[-1, -1] = False

    tile = interpolate_prepared_rms_grid(prepared, bounds, validity)

    expected = image[7:17, 8:19]
    np.testing.assert_allclose(tile.background[:-1], expected[:-1], atol=1e-12)
    np.testing.assert_allclose(tile.background[-1, :-1], expected[-1, :-1])
    assert np.isnan(tile.background[-1, -1])
    assert np.isnan(tile.rms[-1, -1])
    assert tile.bounds == bounds
    with pytest.raises(ValueError, match="read-only"):
        tile.rms[0, 0] = 0.0


def test_all_invalid_grid_produces_explicitly_unavailable_nan_tile() -> None:
    """No fallback invents a scientific estimate when every cell is invalid."""
    image = np.full((8, 9), np.nan)
    source = _ArrayImageSource(image)
    grid = plan_rms_grid(
        image_shape_yx=image.shape,
        window_shape_yx=(4, 5),
        step_yx=(2, 2),
    )
    statistics = estimate_rms_grid(
        source,
        grid,
        _statistics_config(),
        SerialExecutor(),
        maximum_batch_cells=4,
    )

    prepared = prepare_rms_grid_for_interpolation(statistics)
    tile = interpolate_prepared_rms_grid(
        prepared,
        ImageBounds(0, 8, 0, 9),
        np.ones((8, 9), dtype=np.bool_),
    )

    assert not prepared.scientifically_available
    assert not tile.scientifically_available
    assert np.isnan(tile.background).all()
    assert np.isnan(tile.rms).all()


def test_interpolation_rejects_misaligned_tile_validity() -> None:
    """Tile validity must describe exactly the requested global core."""
    image = np.ones((8, 9), dtype=np.float64)
    grid = plan_rms_grid(
        image_shape_yx=image.shape,
        window_shape_yx=(4, 5),
        step_yx=(2, 2),
    )
    statistics = estimate_rms_grid(
        _ArrayImageSource(image),
        grid,
        _statistics_config(),
        SerialExecutor(),
        maximum_batch_cells=4,
    )
    prepared = prepare_rms_grid_for_interpolation(statistics)

    with pytest.raises(ValueError, match="valid pixels"):
        interpolate_prepared_rms_grid(
            prepared,
            ImageBounds(0, 4, 0, 5),
            np.ones((3, 5), dtype=np.bool_),
        )

    with pytest.raises(ValueError, match="inside"):
        interpolate_prepared_rms_grid(
            prepared,
            replace(ImageBounds(0, 4, 0, 5), x_stop=10),
            np.ones((4, 10), dtype=np.bool_),
        )
