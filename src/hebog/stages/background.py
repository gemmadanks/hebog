# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Bounded source and executor orchestration for background estimation."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from math import ceil, floor, isfinite, prod
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt
from scipy import ndimage

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
from hebog.algorithms.detection import normalize_residual
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
    protected_pixel_count: int
    protected_window_count: int


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

    @property
    def adaptive_protected_pixel_count(self) -> int:
        """Return bounded source-support pixels seen across fine regions."""
        return sum(
            region.protected_pixel_count for region in self.adaptive_regions
        )

    @property
    def adaptive_protected_window_count(self) -> int:
        """Return fine windows rejected for intersecting source support."""
        return sum(
            region.protected_window_count for region in self.adaptive_regions
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


@dataclass(frozen=True, slots=True)
class _AdaptiveRegionRequest:
    """Bounded inputs for one source-protected adaptive grid."""

    grid: RmsGridGeometry
    coarse: PreparedRmsGrid
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
) -> RmsGridStatistics:
    """Estimate one complete coarse grid through bounded executor batches."""
    batches = plan_rms_window_batches(
        grid,
        maximum_cells=config.maximum_batch_cells,
    )
    estimate_batch = partial(
        _estimate_source_batch,
        source=source,
        grid=grid,
        config=config,
    )
    results = executor.map_batches(estimate_batch, batches)
    return assemble_rms_grid_statistics(grid, results)


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


def estimate_background_rms_grids(  # noqa: PLR0913
    source: _WindowReadable,
    image_shape_yx: tuple[int, int],
    config: BackgroundRmsConfig,
    executor: Executor,
    *,
    bright_candidate_positions_yx: tuple[tuple[float, float], ...],
    source_protection_island_threshold_sigma: float | None = None,
) -> BackgroundRmsGrids:
    """Estimate cached global coarse and sparse adaptive RMS summaries."""
    if min(image_shape_yx) < 1:
        raise ValueError("image shape dimensions must be positive")
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

    return refine_background_rms_grids(
        source,
        BackgroundRmsGrids(coarse=coarse, adaptive_regions=()),
        config,
        executor,
        bright_candidate_positions_yx=bright_candidate_positions_yx,
        source_protection_island_threshold_sigma=(
            source_protection_island_threshold_sigma
        ),
    )


def _grid_read_bounds(grid: RmsGridGeometry) -> ImageBounds:
    """Return the smallest image window containing every planned cell."""
    window_y, window_x = grid.effective_window_shape_yx
    return ImageBounds(
        grid.window_starts_y[0],
        grid.window_starts_y[-1] + window_y,
        grid.window_starts_x[0],
        grid.window_starts_x[-1] + window_x,
    )


def _connected_source_protection(
    normalized_residual: npt.NDArray[np.float64],
    scientifically_valid: npt.NDArray[np.bool_],
    bounds: ImageBounds,
    positions_yx: tuple[tuple[float, float], ...],
    *,
    island_threshold_sigma: float,
) -> npt.NDArray[np.bool_]:
    """Return candidate-connected public-island support in one bounded read."""
    membership = scientifically_valid & (
        normalized_residual >= island_threshold_sigma
    )
    raw_labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(
            membership,
            structure=np.ones((3, 3), dtype=np.bool_),
        ),
    )
    labels = np.asarray(raw_labels, dtype=np.int32)
    candidate_labels: set[int] = set()
    for y_position, x_position in positions_yx:
        pixel_y = round(y_position)
        pixel_x = round(x_position)
        if not (
            bounds.y_start <= pixel_y < bounds.y_stop
            and bounds.x_start <= pixel_x < bounds.x_stop
        ):
            raise ValueError(
                "adaptive candidate lies outside its protection window"
            )
        label = int(
            labels[
                pixel_y - bounds.y_start,
                pixel_x - bounds.x_start,
            ]
        )
        if label == 0:
            raise ValueError(
                "adaptive candidate is absent from source-protection support"
            )
        candidate_labels.add(label)
    protected = np.isin(labels, tuple(sorted(candidate_labels)))
    protected.setflags(write=False)
    return np.asarray(protected, dtype=np.bool_)


def _guard_source_protection(
    protected: npt.NDArray[np.bool_],
    scientifically_valid: npt.NDArray[np.bool_],
    *,
    estimator_window_shape_yx: tuple[int, int],
) -> npt.NDArray[np.bool_]:
    """Keep fine estimators one window half-width from source support.

    The connected public-threshold island identifies source-owned pixels, but
    a neighbouring estimator window can still be dominated by sub-threshold
    source wings.  The guard is derived from the estimator footprint rather
    than a new scientific threshold and remains clipped to valid pixels.
    """
    guard_radius_pixels = max(estimator_window_shape_yx) // 2
    distance_to_protection = np.asarray(
        ndimage.distance_transform_edt(~protected),
        dtype=np.float64,
    )
    guarded = (
        distance_to_protection <= guard_radius_pixels
    ) & scientifically_valid
    guarded.setflags(write=False)
    return np.asarray(guarded, dtype=np.bool_)


def _estimate_source_protected_adaptive_region(
    request: _AdaptiveRegionRequest,
    *,
    source: _WindowReadable,
    config: RmsGridConfig,
    island_threshold_sigma: float,
) -> AdaptiveRmsRegion:
    """Estimate a fine grid without sampling bright-source support."""
    bounds = _grid_read_bounds(request.grid)
    image_window = source.read_window(bounds)
    if image_window.bounds != bounds:
        raise ValueError("image source returned different window bounds")
    if (
        image_window.values.shape != bounds.shape_yx
        or image_window.valid_pixels.shape != bounds.shape_yx
    ):
        raise ValueError("image source returned a misaligned window")
    coarse = interpolate_prepared_rms_grid(
        request.coarse,
        bounds,
        image_window.valid_pixels,
    )
    normalized, scientifically_valid = normalize_residual(
        image_window.values,
        image_window.valid_pixels,
        coarse.background,
        coarse.rms,
    )
    connected_protection = _connected_source_protection(
        normalized,
        scientifically_valid,
        bounds,
        request.positions_yx,
        island_threshold_sigma=island_threshold_sigma,
    )
    protected = _guard_source_protection(
        connected_protection,
        scientifically_valid,
        estimator_window_shape_yx=config.window_shape_yx,
    )
    results: list[RmsGridBatchStatistics] = []
    for batch in plan_rms_window_batches(
        request.grid,
        maximum_cells=config.maximum_batch_cells,
    ):
        local_selection = (
            slice(
                batch.read_bounds.y_start - bounds.y_start,
                batch.read_bounds.y_stop - bounds.y_start,
            ),
            slice(
                batch.read_bounds.x_start - bounds.x_start,
                batch.read_bounds.x_stop - bounds.x_start,
            ),
        )
        results.append(
            estimate_rms_grid_batch(
                np.asarray(image_window.values[local_selection]),
                np.asarray(image_window.valid_pixels[local_selection]),
                request.grid,
                batch,
                config.statistics,
                protected_pixels=np.asarray(protected[local_selection]),
            )
        )
    statistics = assemble_rms_grid_statistics(request.grid, results)
    return AdaptiveRmsRegion(
        grid=prepare_rms_grid_for_interpolation(statistics),
        bright_candidate_positions_yx=request.positions_yx,
        protected_pixel_count=int(np.count_nonzero(protected)),
        protected_window_count=statistics.protected_window_count,
    )


def _adaptive_region_request(
    region: _CandidateRegion,
    *,
    global_geometry: RmsGridGeometry,
    coarse: PreparedRmsGrid,
) -> _AdaptiveRegionRequest:
    """Bind one candidate region to its fine and coarse bounded summaries."""
    fine_grid = subset_rms_grid_geometry(global_geometry, region.bounds)
    return _AdaptiveRegionRequest(
        grid=fine_grid,
        coarse=subset_prepared_rms_grid(
            coarse,
            _grid_read_bounds(fine_grid),
        ),
        positions_yx=region.positions_yx,
    )


def _estimate_unprotected_adaptive_regions(
    source: _WindowReadable,
    candidate_regions: tuple[_CandidateRegion, ...],
    global_geometry: RmsGridGeometry,
    config: RmsGridConfig,
    executor: Executor,
) -> tuple[AdaptiveRmsRegion, ...]:
    """Preserve the established compact-profile fine-grid calculation."""
    return tuple(
        AdaptiveRmsRegion(
            grid=prepare_rms_grid_for_interpolation(
                estimate_rms_grid(
                    source,
                    subset_rms_grid_geometry(
                        global_geometry,
                        region.bounds,
                    ),
                    config,
                    executor,
                )
            ),
            bright_candidate_positions_yx=region.positions_yx,
            protected_pixel_count=0,
            protected_window_count=0,
        )
        for region in candidate_regions
    )


def refine_background_rms_grids(  # noqa: PLR0913
    source: _WindowReadable,
    coarse_grids: BackgroundRmsGrids,
    config: BackgroundRmsConfig,
    executor: Executor,
    *,
    bright_candidate_positions_yx: tuple[tuple[float, float], ...],
    source_protection_island_threshold_sigma: float | None = None,
) -> BackgroundRmsGrids:
    """Estimate sparse adaptive cells while reusing a prepared coarse grid."""
    if coarse_grids.adaptive_regions:
        raise ValueError("adaptive refinement requires a coarse-only cache")
    image_shape_yx = coarse_grids.coarse.geometry.image_shape_yx
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

    if adaptive_config is None or not candidate_regions:
        return coarse_grids
    if source_protection_island_threshold_sigma is not None and (
        not isfinite(source_protection_island_threshold_sigma)
        or source_protection_island_threshold_sigma <= 0
        or source_protection_island_threshold_sigma
        >= adaptive_config.candidate_threshold_sigma
    ):
        raise ValueError(
            "adaptive refinement requires a finite positive public island "
            "threshold below its candidate threshold for source protection"
        )
    global_adaptive_geometry = plan_rms_grid(
        image_shape_yx=image_shape_yx,
        window_shape_yx=adaptive_config.grid.window_shape_yx,
        step_yx=adaptive_config.grid.step_yx,
    )
    if source_protection_island_threshold_sigma is None:
        return BackgroundRmsGrids(
            coarse=coarse_grids.coarse,
            adaptive_regions=_estimate_unprotected_adaptive_regions(
                source,
                candidate_regions,
                global_adaptive_geometry,
                adaptive_config.grid,
                executor,
            ),
        )
    requests = tuple(
        _adaptive_region_request(
            region,
            global_geometry=global_adaptive_geometry,
            coarse=coarse_grids.coarse,
        )
        for region in candidate_regions
    )
    estimate_region = partial(
        _estimate_source_protected_adaptive_region,
        source=source,
        config=adaptive_config.grid,
        island_threshold_sigma=source_protection_island_threshold_sigma,
    )
    adaptive_regions = tuple(executor.map_batches(estimate_region, requests))
    return BackgroundRmsGrids(
        coarse=coarse_grids.coarse,
        adaptive_regions=adaptive_regions,
    )


def prepare_background_rms_tile_request(
    partition: TilePartition,
    grids: BackgroundRmsGrids,
    config: BackgroundRmsConfig,
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
    summaries: list[AdaptiveRmsTileSummary] = []
    for region in grids.adaptive_regions:
        nearby_positions = tuple(
            (y_position, x_position)
            for y_position, x_position in (
                region.bright_candidate_positions_yx
            )
            if bounds.y_start - radius < y_position < bounds.y_stop + radius
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
    return interpolate_background_rms_tile(image_window, request)


def interpolate_background_rms_tile(
    image_window: ImageWindow,
    request: BackgroundRmsTileRequest,
) -> BackgroundRmsTile:
    """Interpolate one owned core using an already-read source window."""
    bounds = request.partition.core_bounds
    if image_window.bounds != bounds:
        raise ValueError("image source returned different tile bounds")
    if (
        image_window.values.shape != bounds.shape_yx
        or image_window.valid_pixels.shape != bounds.shape_yx
    ):
        raise ValueError("image source returned a misaligned window")
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
