# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Robust serial background and RMS statistics for bounded window batches."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite, isqrt
from numbers import Integral
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from astropy.stats import sigma_clip
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import distance_transform_edt, maximum_filter

from hebog.config import RmsWindowStatisticsConfig
from hebog.data_models.partitioning import ImageBounds

_WINDOW_DIMENSIONS = 3
_STATISTIC_AXES = (-2, -1)
_MINIMUM_LINEAR_SAMPLES = 2
_REACH_AXES = 2
# The finest spread a window measures as noise, as a fraction of the
# window's largest absolute valid value: single precision's machine epsilon,
# 2**-23 (see estimate_rms_window_statistics).
_NOISE_FLOOR_PER_WINDOW_SCALE = float(np.finfo(np.float32).eps)


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


def _nearest_available_indices(
    available: npt.NDArray[np.bool_],
) -> npt.NDArray[np.intp]:
    """Return each cell's nearest available cell as a ``(2, y, x)`` index."""
    return cast(
        npt.NDArray[np.intp],
        distance_transform_edt(
            ~available,
            return_distances=False,
            return_indices=True,
        ),
    )


def _nearest_available_values(
    values: npt.NDArray[np.float64],
    available: npt.NDArray[np.bool_],
) -> npt.NDArray[np.float64]:
    """Fill unavailable coarse cells from their nearest available neighbour."""
    nearest_indices = _nearest_available_indices(available)
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


def prepare_refinement_rms_grid(
    statistics: RmsGridStatistics,
    coarse: PreparedRmsGrid,
    *,
    fill_reach_pixels: float,
) -> PreparedRmsGrid:
    """Fill a refinement grid without carrying its RMS beyond a reach.

    Cells are filled from their nearest available cell, as
    :func:`prepare_rms_grid_for_interpolation` fills any grid, except that a
    cell whose nearest available cell's centre lies more than
    ``fill_reach_pixels`` from its own has no fine RMS: it takes the coarse
    RMS at its centre, so the coarse estimate stands there. A refinement grid
    over a crowded field keeps few windows clear of protected sources, and
    without the reach one of them would set the noise hundreds of pixels
    from where it was measured, across any step in the noise between. The
    background is filled as before, and an unavailable grid stays
    unavailable.

    Args:
        statistics: The refinement grid's assembled window statistics.
        coarse: The prepared coarse grid of the same image, available.
        fill_reach_pixels: The farthest distance, in pixels between window
            centres, over which a clean window's RMS fills another cell; a
            cell exactly at it is filled.

    Raises:
        ValueError: If the reach is negative or not finite, or the
            refinement grid is available and the coarse grid is not.
    """
    if not isfinite(fill_reach_pixels) or fill_reach_pixels < 0:
        raise ValueError("fill_reach_pixels must be finite and non-negative")
    prepared = prepare_rms_grid_for_interpolation(statistics)
    if not prepared.scientifically_available:
        return prepared
    if not coarse.scientifically_available:
        raise ValueError("a refinement grid needs an available coarse grid")
    nearest_y, nearest_x = _nearest_available_indices(statistics.available)
    sample_y = np.asarray(
        statistics.geometry.sample_coordinates_y, dtype=np.float64
    )
    sample_x = np.asarray(
        statistics.geometry.sample_coordinates_x, dtype=np.float64
    )
    cell_y, cell_x = np.meshgrid(sample_y, sample_x, indexing="ij")
    beyond_reach = (
        np.hypot(sample_y[nearest_y] - cell_y, sample_x[nearest_x] - cell_x)
        > fill_reach_pixels
    )
    if not np.any(beyond_reach):
        return prepared
    coarse_rms = np.asarray(
        _extended_rms_interpolator(coarse)(
            np.stack((cell_y, cell_x), axis=-1)
        ),
        dtype=np.float64,
    )
    rms = np.where(beyond_reach, coarse_rms, prepared.rms)
    return replace(
        prepared,
        rms=cast(npt.NDArray[np.float64], _read_only(rms)),
    )


def prepare_local_noise_rms_grid(
    statistics: RmsGridStatistics,
    coarse: PreparedRmsGrid,
    *,
    minimum_coarse_fraction: float,
    clean_cell_reach_yx: tuple[int, int],
) -> PreparedRmsGrid:
    """Fill a local-noise grid without letting a fill fall far below its noise.

    Cells are filled from their nearest available cell, as
    :func:`prepare_rms_grid_for_interpolation` fills any grid, except that a
    filled cell with an available cell within ``clean_cell_reach_yx`` cells
    of it never falls below ``minimum_coarse_fraction`` times a reference:
    the coarse RMS at its centre, or the largest available cell in that
    reach if that is smaller. Local noise blanks every window that touches
    guarded source support, and beside a sharp step in the noise the nearest
    clean window can lie on the quieter side, where its estimate would lower
    the noise beside the step. A coarse window over extended emission
    includes emission the clipping keeps, so where no clean window nearby
    reads as high as the coarse RMS, the excess is not noise and the clean
    windows set the reference; and a cell with no clean window in reach,
    as inside a source wider than twice the reach, keeps its nearest fill,
    because the coarse RMS alone is not a reference there. A cell that a
    clean window measured keeps its own estimate, however low, since that
    is what local noise measures. The background is filled as before, and
    an unavailable grid stays unavailable.

    Args:
        statistics: The local-noise grid's assembled window statistics.
        coarse: The prepared coarse grid of the same image, available.
        minimum_coarse_fraction: The fraction of the reference below which a
            filled cell's RMS never falls, from 0, no floor, to 1.
        clean_cell_reach_yx: How many cells along each axis, either side of
            a filled cell, a clean cell may lie and still floor it and cap
            its reference.

    Raises:
        ValueError: If the fraction is not finite or lies outside 0 to 1, a
            reach is not a non-negative integer, or the local-noise grid is
            available and the coarse grid is not.
    """
    if (
        not isfinite(minimum_coarse_fraction)
        or not 0 <= minimum_coarse_fraction <= 1
    ):
        raise ValueError(
            "minimum_coarse_fraction must be finite and between 0 and 1"
        )
    if len(clean_cell_reach_yx) != _REACH_AXES or any(
        isinstance(reach, bool) or not isinstance(reach, Integral) or reach < 0
        for reach in clean_cell_reach_yx
    ):
        raise ValueError(
            "clean_cell_reach_yx must be two non-negative integers"
        )
    prepared = prepare_rms_grid_for_interpolation(statistics)
    if not prepared.scientifically_available:
        return prepared
    if not coarse.scientifically_available:
        raise ValueError("a local-noise grid needs an available coarse grid")
    filled_y, filled_x = np.nonzero(~statistics.available)
    if filled_y.size == 0:
        return prepared
    reach_y, reach_x = (int(reach) for reach in clean_cell_reach_yx)
    largest_clean = np.asarray(
        maximum_filter(
            np.where(statistics.available, statistics.rms, -np.inf),
            size=(2 * reach_y + 1, 2 * reach_x + 1),
            mode="constant",
            cval=-np.inf,
        ),
        dtype=np.float64,
    )[filled_y, filled_x]
    # The coarse RMS is evaluated at filled cells only, so the driver holds
    # one point per filled cell, not two coordinates per cell of the grid.
    centres = np.stack(
        (
            np.asarray(
                statistics.geometry.sample_coordinates_y, dtype=np.float64
            )[filled_y],
            np.asarray(
                statistics.geometry.sample_coordinates_x, dtype=np.float64
            )[filled_x],
        ),
        axis=-1,
    )
    coarse_rms = np.asarray(
        _extended_rms_interpolator(coarse)(centres), dtype=np.float64
    )
    # With no clean cell in reach the maximum is -inf and there is no floor:
    # the coarse RMS alone is not a reference, because over a source wider
    # than the reach the unprotected coarse window holds the source's
    # emission.
    reference = np.where(
        np.isfinite(largest_clean),
        np.minimum(coarse_rms, largest_clean),
        0.0,
    )
    rms = np.array(prepared.rms, copy=True)
    rms[filled_y, filled_x] = np.maximum(
        rms[filled_y, filled_x], minimum_coarse_fraction * reference
    )
    return replace(
        prepared,
        rms=cast(npt.NDArray[np.float64], _read_only(rms)),
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
    image_length: int,
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
    lower_anchor, upper_anchor = _boundary_slope_anchors(
        sample_coordinates, image_length
    )
    if output_start < sample_coordinates[0]:
        last = max(last, lower_anchor + 1)
    if output_stop - 1 > sample_coordinates[-1]:
        first = min(first, upper_anchor)
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
        image_length=grid.image_shape_yx[0],
    )
    x_selection = _interpolation_axis_slice(
        grid.sample_coordinates_x,
        output_start=bounds.x_start,
        output_stop=bounds.x_stop,
        image_length=grid.image_shape_yx[1],
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
        image_length=grid.geometry.image_shape_yx[0],
    )
    x_selection = _interpolation_axis_slice(
        grid.geometry.sample_coordinates_x,
        output_start=bounds.x_start,
        output_stop=bounds.x_stop,
        image_length=grid.geometry.image_shape_yx[1],
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


def _boundary_slope_anchors(
    coordinates: npt.NDArray[np.float64], image_length: int
) -> tuple[int, int]:
    """Span at least the edge extrapolation distance where samples permit.

    Adjacent final windows can be almost coincident. A secant spanning the
    distance to the physical edge bounds its endpoint weight by two, without
    flattening an affine background. A short grid uses its full available
    span; a singleton is handled by constant extension before interpolation.
    """
    lower = min(
        int(
            cast(
                int,
                np.searchsorted(coordinates, 2 * coordinates[0], side="left"),
            )
        ),
        len(coordinates) - 1,
    )
    upper = max(
        int(
            cast(
                int,
                np.searchsorted(
                    coordinates,
                    2 * coordinates[-1] - (image_length - 1),
                    side="right",
                ),
            )
        )
        - 1,
        0,
    )
    return lower, upper


def _extend_grid_axis(
    coordinates: npt.NDArray[np.float64],
    values: npt.NDArray[np.float64],
    *,
    axis: int,
    image_length: int,
    bounded_below_by_edge_cell: bool,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Add physical-edge samples using stable, affine-preserving secants.

    With ``bounded_below_by_edge_cell``, a secant that falls towards the
    image edge stops at the edge cell's value, so the extension is never
    below the edge cell; one that rises is extended as it is. The second axis
    takes its secants through samples the first has already extended, so at
    a corner the extension can be lower than the unbounded one was, though
    still not below the edge cell.
    """
    lower, upper = _boundary_slope_anchors(coordinates, image_length)
    locations = [coordinates]
    samples = [values]
    for endpoint, anchor, location in (
        (0, lower, 0.0),
        (-1, upper, float(image_length - 1)),
    ):
        if coordinates[0] <= location <= coordinates[-1]:
            continue
        edge = np.take(values, [endpoint], axis=axis)
        slope = (edge - np.take(values, [anchor], axis=axis)) / (
            coordinates[endpoint] - coordinates[anchor]
        )
        extended = edge + (location - coordinates[endpoint]) * slope
        if bounded_below_by_edge_cell:
            np.maximum(extended, edge, out=extended)
        insert_at = 0 if endpoint == 0 else len(locations)
        locations.insert(insert_at, np.array([location]))
        samples.insert(insert_at, extended)
    return np.concatenate(locations), np.concatenate(samples, axis=axis)


def _extend_grid_to_image_edges(
    sample_y: npt.NDArray[np.float64],
    sample_x: npt.NDArray[np.float64],
    values: npt.NDArray[np.float64],
    image_shape_yx: tuple[int, int],
    *,
    bounded_below_by_edge_cell: bool,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Extend coarse samples along both axes to the physical image edges.

    The corners are extended twice, from samples the first axis has already
    extended, so a bound held along each axis also holds at the corners.
    """
    extended_y, values = _extend_grid_axis(
        sample_y,
        values,
        axis=0,
        image_length=image_shape_yx[0],
        bounded_below_by_edge_cell=bounded_below_by_edge_cell,
    )
    extended_x, values = _extend_grid_axis(
        sample_x,
        values,
        axis=1,
        image_length=image_shape_yx[1],
        bounded_below_by_edge_cell=bounded_below_by_edge_cell,
    )
    return extended_y, extended_x, values


def _extended_rms_interpolator(
    grid: PreparedRmsGrid,
) -> RegularGridInterpolator:
    """Return the linear RMS interpolant extended to the image edges.

    It takes ``(..., 2)`` points of global ``(y, x)`` pixel coordinates.
    """
    sample_y, sample_x, _, cell_rms = _expand_singleton_grid_axes(grid)
    rms_y, rms_x, rms_samples = _extend_grid_to_image_edges(
        sample_y,
        sample_x,
        cell_rms,
        grid.geometry.image_shape_yx,
        bounded_below_by_edge_cell=True,
    )
    return RegularGridInterpolator(
        (rms_y, rms_x),
        rms_samples,
        method="linear",
        bounds_error=False,
        fill_value=None,  # pyright: ignore[reportArgumentType]
    )


def interpolate_prepared_rms_grid(
    grid: PreparedRmsGrid,
    bounds: ImageBounds,
    valid_pixels: npt.NDArray[np.bool_],
    *,
    extrapolate_rms: bool = True,
) -> BackgroundRmsTile:
    """Interpolate cached samples, optionally extending RMS edge values.

    Fine noise cells have stochastic slopes, not a measured noise gradient
    beyond their centres. Constant edge extension preserves positive convex
    weights there. Background edge slopes span the extrapolation distance,
    not a possibly tiny gap between the final two window centres. Extended
    RMS follows the same secants but never falls below the edge cell: a noise
    level falling towards the image edge is held there, one rising is
    extended. At a corner the second axis' secant runs through samples the
    first has already extended, so a corner value can be lower than before
    the bound, but not below the corner cell.
    """
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
        image_shape_yx = grid.geometry.image_shape_yx
        output_y = np.arange(bounds.y_start, bounds.y_stop, dtype=np.float64)
        output_x = np.arange(bounds.x_start, bounds.x_stop, dtype=np.float64)
        y_coordinates, x_coordinates = np.meshgrid(
            output_y,
            output_x,
            indexing="ij",
        )
        query_points = np.stack((y_coordinates, x_coordinates), axis=-1)
        background_y, background_x, background_samples = (
            _extend_grid_to_image_edges(
                sample_y,
                sample_x,
                coarse_background,
                image_shape_yx,
                bounded_below_by_edge_cell=False,
            )
        )
        background = np.asarray(
            RegularGridInterpolator(
                (background_y, background_x),
                background_samples,
                method="linear",
                bounds_error=False,
                fill_value=None,  # pyright: ignore[reportArgumentType]
            )(query_points),
            dtype=np.float64,
        )
        if extrapolate_rms:
            rms_interpolator = _extended_rms_interpolator(grid)
            rms_points = query_points
        else:
            rms_interpolator = RegularGridInterpolator(
                (sample_y, sample_x),
                coarse_rms,
                method="linear",
                bounds_error=False,
                fill_value=None,  # pyright: ignore[reportArgumentType]
            )
            rms_points = np.stack(
                (
                    np.clip(y_coordinates, sample_y[0], sample_y[-1]),
                    np.clip(x_coordinates, sample_x[0], sample_x[-1]),
                ),
                axis=-1,
            )
        rms = np.asarray(rms_interpolator(rms_points), dtype=np.float64)
        # Every sample is a non-negative cell value or an extension held at
        # or above one, so this only guards the interpolation's rounding.
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
    """Blend cached fine estimates smoothly around bright candidates.

    The background is blended both ways. The fine RMS only raises the
    coarse one: near a bright source it measures the raised noise of its
    artefacts, which a coarse window dilutes, and where it reads lower the
    coarse RMS stands. PyBDSF's adaptive small box likewise applies near a
    bright source only out to where it stops reading well above its large
    one. So a quieter region's noise, measured by a fine window that missed
    the protected sources there, never lowers the noise beside it.
    """
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
    fine_weight = weight[use_adaptive]
    coarse_rms = coarse.rms[use_adaptive]
    fine_rms = adaptive.rms[use_adaptive]
    rms[use_adaptive] = np.where(
        fine_rms > coarse_rms,
        # The floor only absorbs the blend's rounding.
        np.maximum(
            (1.0 - fine_weight) * coarse_rms + fine_weight * fine_rms,
            coarse_rms,
        ),
        coarse_rms,
    )
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
    too few retained samples, or whose clipped spread is no greater than its
    noise floor, has NaN estimates and ``available=False`` so a later
    interpolation stage can apply its documented fallback policy. An
    available window therefore has a positive RMS.

    The noise floor is the window's largest absolute valid value, taken
    before clipping, times single precision's machine epsilon (2**-23,
    about 1.2e-7): single precision's resolution at that value. Radio
    images are commonly made and stored in single precision, so a spread
    finer than that resolution beside the window's brightest pixel is below
    what such an image can be relied on to hold, and is not taken for
    noise. Samples of
    one value, whose spread is exactly zero, are the limit case; another is
    a window holding a noise-free source, whose tails' clipped spread lies
    near 1e-12 of its peak. A window of a noise-free source's far tails
    alone has a spread close to its own values, which no floor relative to
    them can tell from noise. Real noise falls under the floor only within
    a window whose brightest pixel is more than eight million times the
    noise, and that window then takes the fallback, as a window over a
    protected source does. The floor scales with the values, so the units
    and absolute level of an image do not change which windows it rejects.

    The kernel runs on executor threads, so it emits no warning and never
    touches the process's warning filters: an invalid or empty window is
    ordinary input, reported through ``available``.
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
    # The floor is taken before clipping, so a source the clipping removes
    # still sets the window's scale; a window without a valid sample has a
    # floor of zero, and too few samples anyway.
    noise_floor = _NOISE_FLOOR_PER_WINDOW_SCALE * np.max(
        np.abs(values),
        axis=_STATISTIC_AXES,
        where=effective_validity,
        initial=0.0,
    )
    # Excluded samples are carried as NaN, which the reductions below skip
    # about twice as fast as a mask. They are also masked for the clipping,
    # which otherwise warns about every non-finite sample, and which returns
    # the plain array with every excluded or clipped sample NaN. A window of
    # subnormal values, as the tails of a noise-free source are, makes its
    # compiled spread invalid; ``errstate`` is local to the calling thread's
    # context, unlike a warning filter, and that spread is then NaN, which
    # leaves the window unavailable below.
    retained = np.where(effective_validity, values, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        retained = cast(
            npt.NDArray[np.float64],
            sigma_clip(
                np.ma.MaskedArray(retained, mask=~effective_validity),
                sigma=config.clipping_sigma,
                maxiters=config.maximum_iterations,
                cenfunc="median",
                stdfunc="std",
                axis=_STATISTIC_AXES,
                masked=False,
                copy=False,
            ),
        )
    retained_sample_count = np.count_nonzero(
        np.isfinite(retained),
        axis=_STATISTIC_AXES,
    ).astype(np.int64, copy=False)
    enough_samples = retained_sample_count >= config.minimum_samples
    # Only windows with enough samples are reduced, because NumPy warns about
    # a window with no sample. Selecting them copies, so a batch whose
    # windows all have enough is reduced as it is.
    samples = retained if np.all(enough_samples) else retained[enough_samples]
    window_background = np.nanmedian(samples, axis=_STATISTIC_AXES)
    window_rms = np.nanstd(samples, axis=_STATISTIC_AXES)
    # A spread no greater than the floor, such as that of samples which all
    # hold one value, is no noise estimate, and the window takes the
    # fallback of one that holds too few samples.
    measures_noise = window_rms > noise_floor[enough_samples]
    available = enough_samples.copy()
    available[enough_samples] = measures_noise
    background = np.full(available.shape, np.nan, dtype=np.float64)
    rms = np.full(available.shape, np.nan, dtype=np.float64)
    background[available] = window_background[measures_noise]
    rms[available] = window_rms[measures_noise]

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
