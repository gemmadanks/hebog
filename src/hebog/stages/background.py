"""Bounded source and executor orchestration for background estimation."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from math import ceil, floor, isfinite, prod
from typing import Protocol

import numpy as np
import numpy.typing as npt

from hebog.algorithms.background import (
    BackgroundRmsTile,
    PreparedRmsGrid,
    RmsGridBatchStatistics,
    RmsGridGeometry,
    RmsGridStatistics,
    RmsWindowBatch,
    assemble_rms_grid_statistics,
    blend_adaptive_background_rms,
    estimate_rms_grid_batch,
    interpolate_prepared_rms_grid,
    plan_rms_grid,
    plan_rms_window_batches,
    prepare_rms_grid_for_interpolation,
    subset_prepared_rms_grid,
    subset_rms_grid_geometry,
)
from hebog.config import BackgroundRmsConfig, RmsGridConfig
from hebog.data_models.partitioning import ImageBounds, TilePartition
from hebog.executors.base import Executor
from hebog.io.base import ImageWindow


class _WindowReadable(Protocol):
    """Read bounded global image windows without requiring metadata access."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


@dataclass(frozen=True, slots=True)
class AdaptiveRmsRegion:
    """One merged bright-candidate region and its local fine-grid cache."""

    grid: PreparedRmsGrid
    bright_candidate_positions_yx: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class BackgroundRmsGrids:
    """Prepared coarse and optional sparse adaptive interpolation caches."""

    coarse: PreparedRmsGrid
    adaptive_regions: tuple[AdaptiveRmsRegion, ...]

    @property
    def adaptive_estimated_cell_count(self) -> int:
        """Return the total fine cells retained across local regions."""
        return sum(
            region.grid.geometry.cell_count for region in self.adaptive_regions
        )


@dataclass(frozen=True, slots=True)
class AdaptiveRmsTileSummary:
    """One tile-local adaptive interpolant and its candidate positions."""

    grid: PreparedRmsGrid
    bright_candidate_positions_yx: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class BackgroundRmsTileRequest:
    """Bounded interpolation summaries and blend metadata for one tile."""

    partition: TilePartition
    coarse: PreparedRmsGrid
    adaptive_regions: tuple[AdaptiveRmsTileSummary, ...]
    influence_radius_pixels: float | None
    transition_width_pixels: float | None


@dataclass(frozen=True, slots=True)
class _CandidateRegion:
    """One bounded union of overlapping adaptive influence areas."""

    bounds: ImageBounds
    positions_yx: tuple[tuple[float, float], ...]


def _estimate_source_batch(
    batch: RmsWindowBatch,
    *,
    source: _WindowReadable,
    grid: RmsGridGeometry,
    config: RmsGridConfig,
) -> RmsGridBatchStatistics:
    """Read one bounded source block before applying the pure batch kernel."""
    image_window = source.read_window(batch.read_bounds)
    if image_window.bounds != batch.read_bounds:
        raise ValueError("image source returned different window bounds")
    if (
        image_window.values.shape != batch.read_bounds.shape_yx
        or image_window.valid_pixels.shape != batch.read_bounds.shape_yx
    ):
        raise ValueError("image source returned a misaligned window")
    return estimate_rms_grid_batch(
        np.asarray(image_window.values),
        np.asarray(image_window.valid_pixels),
        grid,
        batch,
        config.statistics,
    )


def estimate_rms_grid(
    source: _WindowReadable,
    grid: RmsGridGeometry,
    config: RmsGridConfig,
    executor: Executor,
    *,
    selected_cells: npt.NDArray[np.bool_] | None = None,
) -> RmsGridStatistics:
    """Estimate one complete coarse grid through bounded executor batches."""
    batches = plan_rms_window_batches(
        grid,
        maximum_cells=config.maximum_batch_cells,
        selected_cells=selected_cells,
    )
    estimate_batch = partial(
        _estimate_source_batch,
        source=source,
        grid=grid,
        config=config,
    )
    results = executor.map_batches(estimate_batch, batches)
    return assemble_rms_grid_statistics(
        grid,
        results,
        required_cells=selected_cells,
    )


def _use_constant_map(
    image_shape_yx: tuple[int, int],
    config: BackgroundRmsConfig,
) -> bool:
    """Return whether configured windows are too large for a spatial map."""
    limiting_image_dimension = min(image_shape_yx)
    return max(config.coarse.window_shape_yx) > (
        config.maximum_spatial_window_fraction * limiting_image_dimension
    )


def _candidate_bounds(
    position_yx: tuple[float, float],
    *,
    image_shape_yx: tuple[int, int],
    margin_pixels: float,
) -> ImageBounds:
    """Return one clipped rectangular adaptive influence region."""
    y_position, x_position = position_yx
    return ImageBounds(
        max(0, floor(y_position - margin_pixels)),
        min(image_shape_yx[0], ceil(y_position + margin_pixels) + 1),
        max(0, floor(x_position - margin_pixels)),
        min(image_shape_yx[1], ceil(x_position + margin_pixels) + 1),
    )


def _regions_overlap(first: ImageBounds, second: ImageBounds) -> bool:
    """Return whether two half-open rectangles overlap or touch."""
    return not (
        first.y_stop < second.y_start
        or second.y_stop < first.y_start
        or first.x_stop < second.x_start
        or second.x_stop < first.x_start
    )


def _union_bounds(first: ImageBounds, second: ImageBounds) -> ImageBounds:
    """Return the smallest rectangle containing two candidate regions."""
    return ImageBounds(
        min(first.y_start, second.y_start),
        max(first.y_stop, second.y_stop),
        min(first.x_start, second.x_start),
        max(first.x_stop, second.x_stop),
    )


def _merge_candidate_regions(
    positions_yx: tuple[tuple[float, float], ...],
    *,
    image_shape_yx: tuple[int, int],
    margin_pixels: float,
) -> tuple[_CandidateRegion, ...]:
    """Merge overlapping candidate boxes deterministically without a mask."""
    height, width = image_shape_yx
    unique_positions = tuple(sorted(set(positions_yx)))
    for y_position, x_position in unique_positions:
        if (
            not isfinite(y_position)
            or not isfinite(x_position)
            or not 0 <= y_position < height
            or not 0 <= x_position < width
        ):
            raise ValueError(
                "bright candidate position must be finite and inside the image"
            )
    regions: list[_CandidateRegion] = []
    for position in unique_positions:
        merged_bounds = _candidate_bounds(
            position,
            image_shape_yx=image_shape_yx,
            margin_pixels=margin_pixels,
        )
        merged_positions = (position,)
        region_index = 0
        while region_index < len(regions):
            existing = regions[region_index]
            if _regions_overlap(merged_bounds, existing.bounds):
                merged_bounds = _union_bounds(
                    merged_bounds,
                    existing.bounds,
                )
                merged_positions = tuple(
                    sorted((*merged_positions, *existing.positions_yx))
                )
                regions.pop(region_index)
            else:
                region_index += 1
        regions.append(
            _CandidateRegion(
                bounds=merged_bounds,
                positions_yx=merged_positions,
            )
        )
    return tuple(
        sorted(
            regions,
            key=lambda region: (
                region.bounds.y_start,
                region.bounds.x_start,
                region.bounds.y_stop,
                region.bounds.x_stop,
            ),
        )
    )


def estimate_background_rms_grids(
    source: _WindowReadable,
    image_shape_yx: tuple[int, int],
    config: BackgroundRmsConfig,
    executor: Executor,
    *,
    bright_candidate_positions_yx: tuple[tuple[float, float], ...],
) -> BackgroundRmsGrids:
    """Estimate cached global coarse and sparse adaptive RMS summaries."""
    if min(image_shape_yx) < 1:
        raise ValueError("image shape dimensions must be positive")
    adaptive_config = config.adaptive
    adaptive_margin = (
        adaptive_config.influence_radius_pixels
        + max(adaptive_config.grid.step_yx)
        if adaptive_config is not None
        else 0.0
    )
    candidate_regions = _merge_candidate_regions(
        bright_candidate_positions_yx,
        image_shape_yx=image_shape_yx,
        margin_pixels=adaptive_margin,
    )
    use_constant_map = _use_constant_map(image_shape_yx, config)
    if (
        use_constant_map
        and prod(image_shape_yx) > config.maximum_constant_map_pixels
    ):
        raise ValueError(
            "constant-map pixel limit would require an unbounded image read"
        )
    coarse_geometry = plan_rms_grid(
        image_shape_yx=image_shape_yx,
        window_shape_yx=(
            image_shape_yx
            if use_constant_map
            else config.coarse.window_shape_yx
        ),
        step_yx=(
            image_shape_yx if use_constant_map else config.coarse.step_yx
        ),
    )
    coarse_statistics = estimate_rms_grid(
        source,
        coarse_geometry,
        config.coarse,
        executor,
    )
    coarse = prepare_rms_grid_for_interpolation(coarse_statistics)

    if adaptive_config is None or not candidate_regions:
        return BackgroundRmsGrids(
            coarse=coarse,
            adaptive_regions=(),
        )
    global_adaptive_geometry = plan_rms_grid(
        image_shape_yx=image_shape_yx,
        window_shape_yx=adaptive_config.grid.window_shape_yx,
        step_yx=adaptive_config.grid.step_yx,
    )
    adaptive_regions = tuple(
        AdaptiveRmsRegion(
            grid=prepare_rms_grid_for_interpolation(
                estimate_rms_grid(
                    source,
                    subset_rms_grid_geometry(
                        global_adaptive_geometry,
                        region.bounds,
                    ),
                    adaptive_config.grid,
                    executor,
                )
            ),
            bright_candidate_positions_yx=region.positions_yx,
        )
        for region in candidate_regions
    )
    return BackgroundRmsGrids(
        coarse=coarse,
        adaptive_regions=adaptive_regions,
    )


def prepare_background_rms_tile_request(
    partition: TilePartition,
    grids: BackgroundRmsGrids,
    config: BackgroundRmsConfig,
    *,
    bright_candidate_positions_yx: tuple[tuple[float, float], ...],
) -> BackgroundRmsTileRequest:
    """Build one local interpolation request without global grid payloads."""
    coarse = subset_prepared_rms_grid(grids.coarse, partition.core_bounds)
    adaptive_config = config.adaptive
    if not grids.adaptive_regions or adaptive_config is None:
        return BackgroundRmsTileRequest(
            partition=partition,
            coarse=coarse,
            adaptive_regions=(),
            influence_radius_pixels=None,
            transition_width_pixels=None,
        )
    bounds = partition.core_bounds
    radius = adaptive_config.influence_radius_pixels
    requested_positions = set(bright_candidate_positions_yx)
    summaries: list[AdaptiveRmsTileSummary] = []
    for region in grids.adaptive_regions:
        nearby_positions = tuple(
            (y_position, x_position)
            for y_position, x_position in (
                region.bright_candidate_positions_yx
            )
            if (y_position, x_position) in requested_positions
            and bounds.y_start - radius < y_position < bounds.y_stop + radius
            and bounds.x_start - radius < x_position < bounds.x_stop + radius
        )
        if nearby_positions:
            summaries.append(
                AdaptiveRmsTileSummary(
                    grid=subset_prepared_rms_grid(region.grid, bounds),
                    bright_candidate_positions_yx=nearby_positions,
                )
            )
    adaptive_regions = tuple(summaries)
    return BackgroundRmsTileRequest(
        partition=partition,
        coarse=coarse,
        adaptive_regions=adaptive_regions,
        influence_radius_pixels=(radius if adaptive_regions else None),
        transition_width_pixels=(
            adaptive_config.transition_width_pixels
            if adaptive_regions
            else None
        ),
    )


def estimate_background_rms_tile(
    source: _WindowReadable,
    request: BackgroundRmsTileRequest,
) -> BackgroundRmsTile:
    """Read validity and interpolate one deterministic owned output core."""
    bounds = request.partition.core_bounds
    image_window = source.read_window(bounds)
    if image_window.bounds != bounds:
        raise ValueError("image source returned different tile bounds")
    coarse = interpolate_prepared_rms_grid(
        request.coarse,
        bounds,
        image_window.valid_pixels,
    )
    if not request.adaptive_regions:
        return coarse
    if (
        request.influence_radius_pixels is None
        or request.transition_width_pixels is None
    ):
        raise ValueError("adaptive tile request is missing blend metadata")
    result = coarse
    for region in request.adaptive_regions:
        adaptive = interpolate_prepared_rms_grid(
            region.grid,
            bounds,
            image_window.valid_pixels,
        )
        result = blend_adaptive_background_rms(
            result,
            adaptive,
            region.bright_candidate_positions_yx,
            influence_radius_pixels=request.influence_radius_pixels,
            transition_width_pixels=request.transition_width_pixels,
        )
    return result
