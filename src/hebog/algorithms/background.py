# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Robust serial background and RMS statistics for bounded window batches."""

from __future__ import annotations

from dataclasses import dataclass
from math import isqrt
from numbers import Integral
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from astropy.stats import sigma_clip
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import distance_transform_edt

from hebog.config import RmsWindowStatisticsConfig
from hebog.data_models.partitioning import ImageBounds

_WINDOW_DIMENSIONS = 3
_STATISTIC_AXES = (-2, -1)
_MINIMUM_LINEAR_SAMPLES = 2


@dataclass(frozen=True, slots=True)
class RmsWindowStatistics:
    """Background and RMS estimates for a batch of independent windows."""

    background: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    available: npt.NDArray[np.bool_]
    valid_sample_count: npt.NDArray[np.int64]
    retained_sample_count: npt.NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class RmsGridGeometry:
    """Globally anchored coarse-grid geometry with edge-aligned windows."""

    image_shape_yx: tuple[int, int]
    configured_window_shape_yx: tuple[int, int]
    effective_window_shape_yx: tuple[int, int]
    step_yx: tuple[int, int]
    window_starts_y: tuple[int, ...]
    window_starts_x: tuple[int, ...]
    sample_coordinates_y: tuple[float, ...]
    sample_coordinates_x: tuple[float, ...]

    @property
    def shape_yx(self) -> tuple[int, int]:
        """Return the coarse-grid shape in NumPy axis order."""
        return (len(self.window_starts_y), len(self.window_starts_x))

    @property
    def cell_count(self) -> int:
        """Return the number of independently estimated window cells."""
        return self.shape_yx[0] * self.shape_yx[1]


@dataclass(frozen=True, slots=True)
class RmsWindowBatch:
    """One rectangular block of coarse cells sharing a bounded image read."""

    grid_y_start: int
    grid_y_stop: int
    grid_x_start: int
    grid_x_stop: int
    read_bounds: ImageBounds

    @property
    def shape_yx(self) -> tuple[int, int]:
        """Return the rectangular coarse-cell block shape."""
        return (
            self.grid_y_stop - self.grid_y_start,
            self.grid_x_stop - self.grid_x_start,
        )

    @property
    def cell_count(self) -> int:
        """Return the number of windows evaluated in this batch."""
        return self.shape_yx[0] * self.shape_yx[1]


@dataclass(frozen=True, slots=True)
class RmsGridBatchStatistics:
    """Small coarse statistics returned by one bounded window batch."""

    batch: RmsWindowBatch
    statistics: RmsWindowStatistics
    protected_window_count: int = 0


@dataclass(frozen=True, slots=True)
class RmsGridStatistics:
    """Canonical coarse background and RMS summaries for one image."""

    geometry: RmsGridGeometry
    background: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    available: npt.NDArray[np.bool_]
    valid_sample_count: npt.NDArray[np.int64]
    retained_sample_count: npt.NDArray[np.int64]
    protected_window_count: int = 0


@dataclass(frozen=True, slots=True)
class PreparedRmsGrid:
    """Coarse samples filled once and ready for repeated interpolation."""

    geometry: RmsGridGeometry
    background: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    fallback_cells: npt.NDArray[np.bool_]
    scientifically_available: bool

    @property
    def fallback_cell_count(self) -> int:
        """Return the number of unavailable cells filled from neighbours."""
        return int(np.count_nonzero(self.fallback_cells))


@dataclass(frozen=True, slots=True)
class BackgroundRmsTile:
    """One bounded interpolated background and RMS output core."""

    bounds: ImageBounds
    background: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    scientifically_available: bool
    fallback_cell_count: int


def _read_only(values: npt.NDArray[Any]) -> npt.NDArray[Any]:
    """Return an owned array that callers cannot mutate accidentally."""
    values.setflags(write=False)
    return values


def _axis_window_starts(
    *,
    length: int,
    window: int,
    step: int,
) -> tuple[int, ...]:
    """Return regular starts plus one deterministic edge-aligned window."""
    effective_window = min(length, window)
    final_start = length - effective_window
    if final_start == 0:
        return (0,)
    starts = tuple(range(0, final_start + 1, step))
    if starts[-1] == final_start:
        return starts
    return (*starts, final_start)


def plan_rms_grid(
    *,
    image_shape_yx: tuple[int, int],
    window_shape_yx: tuple[int, int],
    step_yx: tuple[int, int],
) -> RmsGridGeometry:
    """Plan deterministic global RMS windows independent of tile geometry."""
    if min(image_shape_yx) < 1:
        raise ValueError("image shape dimensions must be positive")
    if min(window_shape_yx) < 1:
        raise ValueError("window shape dimensions must be positive")
    if min(step_yx) < 1:
        raise ValueError("RMS grid step dimensions must be positive")
    if any(
        step > window
        for step, window in zip(step_yx, window_shape_yx, strict=True)
    ):
        raise ValueError("RMS grid step cannot exceed its window dimension")

    effective_window_shape_yx = (
        min(image_shape_yx[0], window_shape_yx[0]),
        min(image_shape_yx[1], window_shape_yx[1]),
    )
    starts_y = _axis_window_starts(
        length=image_shape_yx[0],
        window=window_shape_yx[0],
        step=step_yx[0],
    )
    starts_x = _axis_window_starts(
        length=image_shape_yx[1],
        window=window_shape_yx[1],
        step=step_yx[1],
    )
    y_offset = (effective_window_shape_yx[0] - 1) / 2.0
    x_offset = (effective_window_shape_yx[1] - 1) / 2.0
    return RmsGridGeometry(
        image_shape_yx=image_shape_yx,
        configured_window_shape_yx=window_shape_yx,
        effective_window_shape_yx=effective_window_shape_yx,
        step_yx=step_yx,
        window_starts_y=starts_y,
        window_starts_x=starts_x,
        sample_coordinates_y=tuple(start + y_offset for start in starts_y),
        sample_coordinates_x=tuple(start + x_offset for start in starts_x),
    )


def plan_rms_window_batches(
    grid: RmsGridGeometry,
    *,
    maximum_cells: int,
) -> tuple[RmsWindowBatch, ...]:
    """Group coarse cells into bounded rectangular image-read batches."""
    if (
        isinstance(maximum_cells, bool)
        or not isinstance(maximum_cells, Integral)
        or maximum_cells < 1
    ):
        raise ValueError("maximum_cells must be a positive integer")
    cells_y, cells_x = grid.shape_yx
    block_y = min(cells_y, max(1, isqrt(maximum_cells)))
    block_x = min(cells_x, max(1, maximum_cells // block_y))
    window_y, window_x = grid.effective_window_shape_yx
    batches: list[RmsWindowBatch] = []
    for grid_y_start in range(0, cells_y, block_y):
        grid_y_stop = min(cells_y, grid_y_start + block_y)
        for grid_x_start in range(0, cells_x, block_x):
            grid_x_stop = min(cells_x, grid_x_start + block_x)
            y_start = grid.window_starts_y[grid_y_start]
            x_start = grid.window_starts_x[grid_x_start]
            y_stop = grid.window_starts_y[grid_y_stop - 1] + window_y
            x_stop = grid.window_starts_x[grid_x_stop - 1] + window_x
            batches.append(
                RmsWindowBatch(
                    grid_y_start=grid_y_start,
                    grid_y_stop=grid_y_stop,
                    grid_x_start=grid_x_start,
                    grid_x_stop=grid_x_stop,
                    read_bounds=ImageBounds(y_start, y_stop, x_start, x_stop),
                )
            )
    return tuple(batches)


def _require_canonical_batch(
    grid: RmsGridGeometry,
    batch: RmsWindowBatch,
) -> None:
    """Reject invented batch geometry before reading source pixels."""
    cells_y, cells_x = grid.shape_yx
    if not (
        0 <= batch.grid_y_start < batch.grid_y_stop <= cells_y
        and 0 <= batch.grid_x_start < batch.grid_x_stop <= cells_x
    ):
        raise ValueError("RMS window batch lies outside the coarse grid")
    window_y, window_x = grid.effective_window_shape_yx
    expected = ImageBounds(
        grid.window_starts_y[batch.grid_y_start],
        grid.window_starts_y[batch.grid_y_stop - 1] + window_y,
        grid.window_starts_x[batch.grid_x_start],
        grid.window_starts_x[batch.grid_x_stop - 1] + window_x,
    )
    if batch.read_bounds != expected:
        raise ValueError("RMS window batch has non-canonical read bounds")


def estimate_rms_grid_batch(  # noqa: PLR0913
    values: npt.NDArray[np.floating[Any]],
    valid_pixels: npt.NDArray[np.bool_],
    grid: RmsGridGeometry,
    batch: RmsWindowBatch,
    config: RmsWindowStatisticsConfig,
    *,
    protected_pixels: npt.NDArray[np.bool_] | None = None,
) -> RmsGridBatchStatistics:
    """Estimate a rectangular window block without loops over grid cells.

    A fine-grid window that intersects ``protected_pixels`` is deliberately
    unavailable as a whole. This prevents connected bright-source support
    from contributing to either the background or RMS statistic while
    retaining the established deterministic interpolation fallback.
    """
    _require_canonical_batch(grid, batch)
    bounded_values = np.asarray(values)
    bounded_validity = np.asarray(valid_pixels, dtype=np.bool_)
    if (
        bounded_values.shape != batch.read_bounds.shape_yx
        or bounded_validity.shape != batch.read_bounds.shape_yx
    ):
        raise ValueError(
            "RMS batch values and validity must match read bounds"
        )
    bounded_protection: npt.NDArray[np.bool_] | None = None
    if protected_pixels is not None:
        bounded_protection = np.asarray(protected_pixels, dtype=np.bool_)
        if bounded_protection.shape != batch.read_bounds.shape_yx:
            raise ValueError(
                "protected pixels must match RMS batch read bounds"
            )

    window_shape = grid.effective_window_shape_yx
    value_views = np.lib.stride_tricks.sliding_window_view(
        bounded_values,
        window_shape,
    )
    validity_views = np.lib.stride_tricks.sliding_window_view(
        bounded_validity,
        window_shape,
    )
    y_offsets = (
        np.asarray(
            grid.window_starts_y[batch.grid_y_start : batch.grid_y_stop],
            dtype=np.int64,
        )
        - batch.read_bounds.y_start
    )
    x_offsets = (
        np.asarray(
            grid.window_starts_x[batch.grid_x_start : batch.grid_x_stop],
            dtype=np.int64,
        )
        - batch.read_bounds.x_start
    )
    selected_values = value_views[
        y_offsets[:, np.newaxis],
        x_offsets[np.newaxis, :],
    ]
    selected_validity = validity_views[
        y_offsets[:, np.newaxis],
        x_offsets[np.newaxis, :],
    ]
    all_values = np.reshape(
        selected_values,
        (batch.cell_count, *window_shape),
    )
    all_validity = np.reshape(
        selected_validity,
        (batch.cell_count, *window_shape),
    )
    statistics = estimate_rms_window_statistics(
        all_values,
        all_validity,
        config,
    )
    protected_window_count = 0
    if bounded_protection is not None:
        protection_views = np.lib.stride_tricks.sliding_window_view(
            bounded_protection,
            window_shape,
        )
        selected_protection = protection_views[
            y_offsets[:, np.newaxis],
            x_offsets[np.newaxis, :],
        ]
        protected_windows = np.any(
            np.reshape(
                selected_protection,
                (batch.cell_count, *window_shape),
            ),
            axis=_STATISTIC_AXES,
        )
        protected_window_count = int(np.count_nonzero(protected_windows))
        if protected_window_count:
            background = np.array(statistics.background, copy=True)
            rms = np.array(statistics.rms, copy=True)
            available = np.array(statistics.available, copy=True)
            retained_sample_count = np.array(
                statistics.retained_sample_count,
                copy=True,
            )
            background[protected_windows] = np.nan
            rms[protected_windows] = np.nan
            available[protected_windows] = False
            retained_sample_count[protected_windows] = 0
            statistics = RmsWindowStatistics(
                background=cast(
                    npt.NDArray[np.float64],
                    _read_only(background),
                ),
                rms=cast(
                    npt.NDArray[np.float64],
                    _read_only(rms),
                ),
                available=cast(
                    npt.NDArray[np.bool_],
                    _read_only(available),
                ),
                valid_sample_count=statistics.valid_sample_count,
                retained_sample_count=cast(
                    npt.NDArray[np.int64],
                    _read_only(retained_sample_count),
                ),
            )
    return RmsGridBatchStatistics(
        batch=batch,
        statistics=statistics,
        protected_window_count=protected_window_count,
    )


def assemble_rms_grid_statistics(
    grid: RmsGridGeometry,
    batch_results: Any,
) -> RmsGridStatistics:
    """Assemble complete coarse summaries independently of completion order."""
    shape = grid.shape_yx
    background = np.full(shape, np.nan, dtype=np.float64)
    rms = np.full(shape, np.nan, dtype=np.float64)
    available = np.zeros(shape, dtype=np.bool_)
    valid_sample_count = np.zeros(shape, dtype=np.int64)
    retained_sample_count = np.zeros(shape, dtype=np.int64)
    visits = np.zeros(shape, dtype=np.uint8)
    protected_window_count = 0
    for result in batch_results:
        if not isinstance(result, RmsGridBatchStatistics):
            raise ValueError("coarse-grid results contain an invalid batch")
        batch = result.batch
        _require_canonical_batch(grid, batch)
        selection = (
            slice(batch.grid_y_start, batch.grid_y_stop),
            slice(batch.grid_x_start, batch.grid_x_stop),
        )
        expected_size = batch.cell_count
        if any(
            values.size != expected_size
            for values in (
                result.statistics.background,
                result.statistics.rms,
                result.statistics.available,
                result.statistics.valid_sample_count,
                result.statistics.retained_sample_count,
            )
        ):
            raise ValueError("coarse-grid batch statistics are misaligned")
        if np.any(visits[selection]):
            raise ValueError("duplicate coarse-grid cells were returned")
        background[selection] = result.statistics.background.reshape(
            batch.shape_yx
        )
        rms[selection] = result.statistics.rms.reshape(batch.shape_yx)
        available[selection] = result.statistics.available.reshape(
            batch.shape_yx
        )
        valid_sample_count[selection] = (
            result.statistics.valid_sample_count.reshape(batch.shape_yx)
        )
        retained_sample_count[selection] = (
            result.statistics.retained_sample_count.reshape(batch.shape_yx)
        )
        visits[selection] += 1
        protected_window_count += result.protected_window_count
    if np.any(visits == 0):
        raise ValueError("missing coarse-grid cells prevent interpolation")
    return RmsGridStatistics(
        geometry=grid,
        background=cast(
            npt.NDArray[np.float64],
            _read_only(background),
        ),
        rms=cast(npt.NDArray[np.float64], _read_only(rms)),
        available=cast(npt.NDArray[np.bool_], _read_only(available)),
        valid_sample_count=cast(
            npt.NDArray[np.int64],
            _read_only(valid_sample_count),
        ),
        retained_sample_count=cast(
            npt.NDArray[np.int64],
            _read_only(retained_sample_count),
        ),
        protected_window_count=protected_window_count,
    )


def _nearest_available_values(
    values: npt.NDArray[np.float64],
    available: npt.NDArray[np.bool_],
) -> npt.NDArray[np.float64]:
    """Fill unavailable coarse cells from their nearest available neighbour."""
    nearest_indices = cast(
        npt.NDArray[np.intp],
        distance_transform_edt(
            ~available,
            return_distances=False,
            return_indices=True,
        ),
    )
    return np.asarray(values[tuple(nearest_indices)], dtype=np.float64)


def prepare_rms_grid_for_interpolation(
    statistics: RmsGridStatistics,
) -> PreparedRmsGrid:
    """Fill sparse cells once without recomputing window statistics."""
    available = statistics.available
    scientifically_available = bool(np.any(available))
    fallback_cells = np.asarray(~available, dtype=np.bool_)
    if scientifically_available:
        background = _nearest_available_values(
            statistics.background,
            available,
        )
        rms = _nearest_available_values(statistics.rms, available)
    else:
        background = np.full(statistics.geometry.shape_yx, np.nan)
        rms = np.full(statistics.geometry.shape_yx, np.nan)
        fallback_cells = np.zeros_like(available)
    return PreparedRmsGrid(
        geometry=statistics.geometry,
        background=cast(
            npt.NDArray[np.float64],
            _read_only(np.array(background, copy=True)),
        ),
        rms=cast(
            npt.NDArray[np.float64],
            _read_only(np.array(rms, copy=True)),
        ),
        fallback_cells=cast(
            npt.NDArray[np.bool_],
            _read_only(np.array(fallback_cells, copy=True)),
        ),
        scientifically_available=scientifically_available,
    )


def _expand_singleton_grid_axes(
    grid: PreparedRmsGrid,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Duplicate singleton axes for well-defined linear interpolation."""
    y_coordinates = np.asarray(
        grid.geometry.sample_coordinates_y,
        dtype=np.float64,
    )
    x_coordinates = np.asarray(
        grid.geometry.sample_coordinates_x,
        dtype=np.float64,
    )
    background = np.asarray(grid.background)
    rms = np.asarray(grid.rms)
    if y_coordinates.size == 1:
        y_coordinates = np.array(
            [-0.5, max(0.5, grid.geometry.image_shape_yx[0] - 0.5)],
            dtype=np.float64,
        )
        background = np.repeat(background, 2, axis=0)
        rms = np.repeat(rms, 2, axis=0)
    if x_coordinates.size == 1:
        x_coordinates = np.array(
            [-0.5, max(0.5, grid.geometry.image_shape_yx[1] - 0.5)],
            dtype=np.float64,
        )
        background = np.repeat(background, 2, axis=1)
        rms = np.repeat(rms, 2, axis=1)
    return y_coordinates, x_coordinates, background, rms


def _interpolation_axis_slice(
    coordinates: tuple[float, ...],
    *,
    output_start: int,
    output_stop: int,
) -> slice:
    """Select only samples bracketing one half-open output interval."""
    sample_coordinates = np.asarray(coordinates, dtype=np.float64)
    if sample_coordinates.size <= _MINIMUM_LINEAR_SAMPLES:
        return slice(0, sample_coordinates.size)
    first = max(
        0,
        int(np.searchsorted(sample_coordinates, output_start, side="right"))
        - 1,
    )
    last = min(
        sample_coordinates.size,
        int(
            np.searchsorted(
                sample_coordinates,
                output_stop - 1,
                side="left",
            )
        )
        + _MINIMUM_LINEAR_SAMPLES,
    )
    if last - first < _MINIMUM_LINEAR_SAMPLES:
        first = max(
            0,
            min(
                first,
                sample_coordinates.size - _MINIMUM_LINEAR_SAMPLES,
            ),
        )
        last = first + _MINIMUM_LINEAR_SAMPLES
    return slice(first, last)


def subset_rms_grid_geometry(
    grid: RmsGridGeometry,
    bounds: ImageBounds,
) -> RmsGridGeometry:
    """Return only globally anchored cells bracketing one bounded region."""
    bounds.require_inside(grid.image_shape_yx)
    y_selection = _interpolation_axis_slice(
        grid.sample_coordinates_y,
        output_start=bounds.y_start,
        output_stop=bounds.y_stop,
    )
    x_selection = _interpolation_axis_slice(
        grid.sample_coordinates_x,
        output_start=bounds.x_start,
        output_stop=bounds.x_stop,
    )
    return RmsGridGeometry(
        image_shape_yx=grid.image_shape_yx,
        configured_window_shape_yx=grid.configured_window_shape_yx,
        effective_window_shape_yx=grid.effective_window_shape_yx,
        step_yx=grid.step_yx,
        window_starts_y=grid.window_starts_y[y_selection],
        window_starts_x=grid.window_starts_x[x_selection],
        sample_coordinates_y=grid.sample_coordinates_y[y_selection],
        sample_coordinates_x=grid.sample_coordinates_x[x_selection],
    )


def subset_prepared_rms_grid(
    grid: PreparedRmsGrid,
    bounds: ImageBounds,
) -> PreparedRmsGrid:
    """Copy the bounded coarse summary needed to interpolate one tile."""
    bounds.require_inside(grid.geometry.image_shape_yx)
    y_selection = _interpolation_axis_slice(
        grid.geometry.sample_coordinates_y,
        output_start=bounds.y_start,
        output_stop=bounds.y_stop,
    )
    x_selection = _interpolation_axis_slice(
        grid.geometry.sample_coordinates_x,
        output_start=bounds.x_start,
        output_stop=bounds.x_stop,
    )
    geometry = subset_rms_grid_geometry(grid.geometry, bounds)
    selection = (y_selection, x_selection)
    return PreparedRmsGrid(
        geometry=geometry,
        background=cast(
            npt.NDArray[np.float64],
            _read_only(np.array(grid.background[selection], copy=True)),
        ),
        rms=cast(
            npt.NDArray[np.float64],
            _read_only(np.array(grid.rms[selection], copy=True)),
        ),
        fallback_cells=cast(
            npt.NDArray[np.bool_],
            _read_only(np.array(grid.fallback_cells[selection], copy=True)),
        ),
        scientifically_available=grid.scientifically_available,
    )


def interpolate_prepared_rms_grid(
    grid: PreparedRmsGrid,
    bounds: ImageBounds,
    valid_pixels: npt.NDArray[np.bool_],
) -> BackgroundRmsTile:
    """Linearly interpolate cached coarse samples into one bounded tile."""
    bounds.require_inside(grid.geometry.image_shape_yx)
    validity = np.asarray(valid_pixels, dtype=np.bool_)
    if validity.shape != bounds.shape_yx:
        raise ValueError("tile valid pixels must match the requested bounds")
    if not grid.scientifically_available:
        background = np.full(bounds.shape_yx, np.nan, dtype=np.float64)
        rms = np.full(bounds.shape_yx, np.nan, dtype=np.float64)
    else:
        (
            sample_y,
            sample_x,
            coarse_background,
            coarse_rms,
        ) = _expand_singleton_grid_axes(grid)
        output_y = np.arange(bounds.y_start, bounds.y_stop, dtype=np.float64)
        output_x = np.arange(bounds.x_start, bounds.x_stop, dtype=np.float64)
        y_coordinates, x_coordinates = np.meshgrid(
            output_y,
            output_x,
            indexing="ij",
        )
        query_points = np.stack((y_coordinates, x_coordinates), axis=-1)
        background = np.asarray(
            RegularGridInterpolator(
                (sample_y, sample_x),
                coarse_background,
                method="linear",
                bounds_error=False,
                fill_value=None,  # pyright: ignore[reportArgumentType]
            )(query_points),
            dtype=np.float64,
        )
        rms = np.asarray(
            RegularGridInterpolator(
                (sample_y, sample_x),
                coarse_rms,
                method="linear",
                bounds_error=False,
                fill_value=None,  # pyright: ignore[reportArgumentType]
            )(query_points),
            dtype=np.float64,
        )
        np.maximum(rms, 0.0, out=rms)
        background[~validity] = np.nan
        rms[~validity] = np.nan
    return BackgroundRmsTile(
        bounds=bounds,
        background=cast(
            npt.NDArray[np.float64],
            _read_only(background),
        ),
        rms=cast(npt.NDArray[np.float64], _read_only(rms)),
        scientifically_available=grid.scientifically_available,
        fallback_cell_count=grid.fallback_cell_count,
    )


def blend_adaptive_background_rms(
    coarse: BackgroundRmsTile,
    adaptive: BackgroundRmsTile,
    positions_yx: tuple[tuple[float, float], ...],
    *,
    influence_radius_pixels: float,
    transition_width_pixels: float,
) -> BackgroundRmsTile:
    """Blend cached fine estimates smoothly around bright candidates."""
    if coarse.bounds != adaptive.bounds:
        raise ValueError("coarse and adaptive RMS tiles must share bounds")
    if not positions_yx or not adaptive.scientifically_available:
        return coarse
    bounds = coarse.bounds
    output_y = np.arange(bounds.y_start, bounds.y_stop, dtype=np.float64)
    output_x = np.arange(bounds.x_start, bounds.x_stop, dtype=np.float64)
    y_coordinates, x_coordinates = np.meshgrid(
        output_y,
        output_x,
        indexing="ij",
    )
    minimum_distance = np.full(bounds.shape_yx, np.inf, dtype=np.float64)
    for y_position, x_position in positions_yx:
        np.minimum(
            minimum_distance,
            np.hypot(
                y_coordinates - y_position,
                x_coordinates - x_position,
            ),
            out=minimum_distance,
        )
    transition = np.clip(
        (influence_radius_pixels - minimum_distance) / transition_width_pixels,
        0.0,
        1.0,
    )
    weight = transition * transition * (3.0 - 2.0 * transition)
    usable_fine = np.isfinite(adaptive.background) & np.isfinite(adaptive.rms)
    weight[~usable_fine] = 0.0
    use_adaptive = weight > 0.0
    background = np.array(coarse.background, copy=True)
    rms = np.array(coarse.rms, copy=True)
    background[use_adaptive] = (
        1.0 - weight[use_adaptive]
    ) * coarse.background[use_adaptive] + weight[
        use_adaptive
    ] * adaptive.background[use_adaptive]
    rms[use_adaptive] = (1.0 - weight[use_adaptive]) * coarse.rms[
        use_adaptive
    ] + weight[use_adaptive] * adaptive.rms[use_adaptive]
    return BackgroundRmsTile(
        bounds=bounds,
        background=cast(
            npt.NDArray[np.float64],
            _read_only(background),
        ),
        rms=cast(npt.NDArray[np.float64], _read_only(rms)),
        scientifically_available=(
            coarse.scientifically_available
            or adaptive.scientifically_available
        ),
        fallback_cell_count=(
            coarse.fallback_cell_count + adaptive.fallback_cell_count
        ),
    )


def estimate_rms_window_statistics(
    windows: npt.NDArray[np.floating[Any]],
    valid_pixels: npt.NDArray[np.bool_],
    config: RmsWindowStatisticsConfig,
) -> RmsWindowStatistics:
    """Estimate robust background and RMS for a batch of 2-D windows.

    Non-finite or explicitly invalid pixels do not contribute. A window with
    too few retained samples has NaN estimates and ``available=False`` so a
    later interpolation stage can apply its documented fallback policy.
    """
    values = np.asarray(windows, dtype=np.float64)
    validity = np.asarray(valid_pixels, dtype=np.bool_)
    if values.ndim != _WINDOW_DIMENSIONS:
        raise ValueError(
            "RMS window values must be a three-dimensional "
            "(window, y, x) batch"
        )
    if min(values.shape) < 1:
        raise ValueError("RMS window batches and windows must be non-empty")
    if validity.shape != values.shape:
        raise ValueError(
            "RMS window values and valid pixels need the same shape"
        )

    effective_validity = validity & np.isfinite(values)
    valid_sample_count = np.count_nonzero(
        effective_validity,
        axis=_STATISTIC_AXES,
    ).astype(np.int64, copy=False)
    masked_values = np.ma.array(
        values,
        mask=~effective_validity,
        copy=True,
    )
    clipped = cast(
        np.ma.MaskedArray[Any, Any],
        sigma_clip(
            masked_values,
            sigma=config.clipping_sigma,
            maxiters=config.maximum_iterations,
            cenfunc="median",
            stdfunc="std",
            axis=_STATISTIC_AXES,
            masked=True,
            copy=True,
        ),
    )
    retained_sample_count = np.count_nonzero(
        ~np.ma.getmaskarray(clipped),
        axis=_STATISTIC_AXES,
    ).astype(np.int64, copy=False)
    available = retained_sample_count >= config.minimum_samples
    background = np.asarray(
        np.ma.median(clipped, axis=_STATISTIC_AXES).filled(np.nan),
        dtype=np.float64,
    )
    rms = np.asarray(
        np.ma.std(clipped, axis=_STATISTIC_AXES).filled(np.nan),
        dtype=np.float64,
    )
    background[~available] = np.nan
    rms[~available] = np.nan

    return RmsWindowStatistics(
        background=cast(npt.NDArray[np.float64], _read_only(background)),
        rms=cast(npt.NDArray[np.float64], _read_only(rms)),
        available=cast(npt.NDArray[np.bool_], _read_only(available)),
        valid_sample_count=cast(
            npt.NDArray[np.int64],
            _read_only(valid_sample_count),
        ),
        retained_sample_count=cast(
            npt.NDArray[np.int64],
            _read_only(retained_sample_count),
        ),
    )
