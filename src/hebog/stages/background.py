# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Bounded source and executor orchestration for background estimation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import partial
from math import ceil, floor, isfinite, prod
from typing import Literal, Protocol, cast

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
    RmsWindowStatistics,
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
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    ScaleFilterBank,
    build_scale_filter_bank,
    calibrated_scale_snrs,
    evaluate_scale_filter_bank,
    prepare_scale_filter_inputs,
)
from hebog.algorithms.multiscale_association import (
    persistent_seeded_scale_support,
)
from hebog.config import BackgroundRmsConfig, RmsGridConfig, SourceFinderConfig
from hebog.data_models.partitioning import ImageBounds, TilePartition
from hebog.executors.base import Executor
from hebog.io.base import ImageWindow

_LOCAL_NOISE_CONTEXT_CELLS = 256


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
    coarse_protected_pixel_count: int = 0
    local_noise: PreparedRmsGrid | None = None
    local_noise_protected_window_count: int = 0

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
    local_noise: PreparedRmsGrid | None = None


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
    protection: Literal[
        "exclude-samples", "exclude-windows", "local-noise-windows"
    ] = "exclude-windows"
    guard_window_shape_yx: tuple[int, int] | None = None
    detection_rms: PreparedRmsGrid | None = None
    context_halo_pixels: int = 0


@dataclass(frozen=True, slots=True)
class _LocalNoiseRequest:
    """One globally owned fine-cell block and its bounded protection input."""

    batch: RmsWindowBatch
    region: _AdaptiveRegionRequest


@dataclass(frozen=True, slots=True)
class MultiscaleSourceProtection:
    """Caller-supplied beam and detection policy for fine-grid protection."""

    beam: BeamShapePixels
    source_finder: SourceFinderConfig
    minimum_support_fraction: float

    def __post_init__(self) -> None:
        """Validate filter admission before any image or candidate exists."""
        if not isfinite(self.minimum_support_fraction) or not (
            0.0 < self.minimum_support_fraction <= 1.0
        ):
            raise ValueError(
                "multiscale protection support fraction is invalid"
            )


def _protection_filter_bank(
    policy: MultiscaleSourceProtection,
) -> ScaleFilterBank:
    """Match the existing source-owned persistent measurement scales."""
    return build_scale_filter_bank(
        policy.beam,
        family="beam-aware-matched-filter",
        scales=((1, 1.0), (2, 2.0), (3, 4.0)),
        truncation_sigma=4.0,
        noise_correlation=policy.beam,
    )


def _filter_read_bounds(grid: RmsGridGeometry, halo: int) -> ImageBounds:
    """Include filtering context beyond the fine estimator windows."""
    bounds = _grid_read_bounds(grid)
    height, width = grid.image_shape_yx
    return ImageBounds(
        max(0, bounds.y_start - halo),
        min(height, bounds.y_stop + halo),
        max(0, bounds.x_start - halo),
        min(width, bounds.x_stop + halo),
    )


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
    multiscale_protection: MultiscaleSourceProtection | None = None,
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
        multiscale_protection=multiscale_protection,
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


def _connected_source_protection(  # noqa: PLR0913
    normalized_residual: npt.NDArray[np.float64],
    scientifically_valid: npt.NDArray[np.bool_],
    bounds: ImageBounds,
    positions_yx: tuple[tuple[float, float], ...],
    *,
    island_threshold_sigma: float,
    source_finder: SourceFinderConfig | None = None,
    protect_context_boundary: bool = False,
    image_shape_yx: tuple[int, int] | None = None,
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
    if source_finder is not None:
        counts = np.bincount(labels.ravel())
        seeded = np.unique(
            labels[
                scientifically_valid
                & (
                    normalized_residual
                    > source_finder.detection_threshold_sigma
                )
            ]
        )
        candidate_labels.update(
            int(label)
            for label in seeded
            if label > 0
            and counts[label] >= source_finder.minimum_island_pixels
        )
    if protect_context_boundary:
        if image_shape_yx is None:
            raise ValueError(
                "boundary protection requires the full image shape"
            )
        internal_sides = (
            bounds.y_start > 0,
            bounds.y_stop < image_shape_yx[0],
            bounds.x_start > 0,
            bounds.x_stop < image_shape_yx[1],
        )
        for internal, edge in zip(
            internal_sides,
            (labels[0], labels[-1], labels[:, 0], labels[:, -1]),
            strict=True,
        ):
            if internal:
                candidate_labels.update(
                    int(value) for value in np.unique(edge) if value > 0
                )
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
    if not np.any(protected):
        return protected
    distance_to_protection = np.asarray(
        ndimage.distance_transform_edt(~protected),
        dtype=np.float64,
    )
    guarded = (
        distance_to_protection <= guard_radius_pixels
    ) & scientifically_valid
    guarded.setflags(write=False)
    return np.asarray(guarded, dtype=np.bool_)


def _estimate_source_protected_region_statistics(
    request: _AdaptiveRegionRequest,
    *,
    source: _WindowReadable,
    config: RmsGridConfig,
    island_threshold_sigma: float,
    multiscale_protection: MultiscaleSourceProtection | None = None,
) -> tuple[RmsGridStatistics, int]:
    """Estimate one bounded protected grid with explicit sample ownership."""
    bank = (
        _protection_filter_bank(multiscale_protection)
        if multiscale_protection is not None
        else None
    )
    bounds = _filter_read_bounds(
        request.grid,
        (bank.maximum_halo_pixels if bank is not None else 0)
        + request.context_halo_pixels,
    )
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
    protection_rms = (
        interpolate_prepared_rms_grid(
            request.detection_rms,
            bounds,
            image_window.valid_pixels,
            extrapolate_rms=False,
        ).rms
        if request.detection_rms is not None
        else coarse.rms
    )
    normalized, scientifically_valid = normalize_residual(
        image_window.values,
        image_window.valid_pixels,
        coarse.background,
        protection_rms,
    )
    connected_protection = _connected_source_protection(
        normalized,
        scientifically_valid,
        bounds,
        # A pilot can explain a coarse bright peak as local noise. With
        # independent mask admission, old work anchors are not source seeds.
        () if request.detection_rms is not None else request.positions_yx,
        island_threshold_sigma=island_threshold_sigma,
        source_finder=(
            multiscale_protection.source_finder
            if (request.protection != "exclude-windows")
            and multiscale_protection is not None
            else None
        ),
        protect_context_boundary=request.protection == "local-noise-windows",
        image_shape_yx=request.grid.image_shape_yx,
    )
    if multiscale_protection is not None and bank is not None:
        policy = multiscale_protection
        responses = evaluate_scale_filter_bank(
            prepare_scale_filter_inputs(
                image_window.values,
                scientifically_valid,
                coarse.background,
                protection_rms,
            ),
            bank,
            minimum_support_fraction=policy.minimum_support_fraction,
        )
        persistent = persistent_seeded_scale_support(
            calibrated_scale_snrs(
                responses.responses,
                minimum_support_fraction=policy.minimum_support_fraction,
            ),
            tuple(item.response_jy_per_beam for item in responses.responses),
            scientifically_valid,
            detection_sigma=policy.source_finder.detection_threshold_sigma,
            island_sigma=policy.source_finder.island_threshold_sigma,
            minimum_pixels=policy.source_finder.minimum_island_pixels,
        )
        if request.protection != "exclude-windows":
            # Coarse and local-noise statistics exclude ordinary emission;
            # the bright-candidate threshold controls bright-region work.
            connected_protection = persistent | connected_protection
        else:
            labels, _ = cast(
                tuple[npt.NDArray[np.int32], int],
                ndimage.label(
                    persistent | connected_protection, np.ones((3, 3))
                ),
            )
            selected = np.unique(labels[connected_protection])
            connected_protection = np.isin(labels, selected[selected > 0])
        if request.protection == "local-noise-windows":
            # A protection context is not a source catalogue: components
            # whose seed search is truncated must not contaminate statistics.
            for snr in calibrated_scale_snrs(
                responses.responses,
                minimum_support_fraction=policy.minimum_support_fraction,
            ):
                connected_protection |= _connected_source_protection(
                    snr,
                    scientifically_valid,
                    bounds,
                    (),
                    island_threshold_sigma=island_threshold_sigma,
                    protect_context_boundary=True,
                    image_shape_yx=request.grid.image_shape_yx,
                )
    protected = _guard_source_protection(
        connected_protection,
        scientifically_valid,
        estimator_window_shape_yx=(
            request.guard_window_shape_yx or config.window_shape_yx
        ),
    )
    estimator_validity = (
        image_window.valid_pixels & ~protected
        if request.protection == "exclude-samples"
        else image_window.valid_pixels
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
                np.asarray(estimator_validity[local_selection]),
                request.grid,
                batch,
                config.statistics,
                protected_pixels=(
                    np.asarray(protected[local_selection])
                    if request.protection != "exclude-samples"
                    else None
                ),
            )
        )
    statistics = assemble_rms_grid_statistics(request.grid, results)
    return statistics, int(np.count_nonzero(protected))


def _estimate_source_protected_adaptive_region(
    request: _AdaptiveRegionRequest,
    *,
    source: _WindowReadable,
    config: RmsGridConfig,
    island_threshold_sigma: float,
    multiscale_protection: MultiscaleSourceProtection | None = None,
) -> AdaptiveRmsRegion:
    """Prepare one candidate region after all its raw statistics exist."""
    statistics, protected_pixel_count = (
        _estimate_source_protected_region_statistics(
            request,
            source=source,
            config=config,
            island_threshold_sigma=island_threshold_sigma,
            multiscale_protection=multiscale_protection,
        )
    )
    return AdaptiveRmsRegion(
        grid=prepare_rms_grid_for_interpolation(statistics),
        bright_candidate_positions_yx=request.positions_yx,
        protected_pixel_count=protected_pixel_count,
        protected_window_count=statistics.protected_window_count,
    )


def _estimate_local_noise_batch(
    request: _LocalNoiseRequest,
    *,
    source: _WindowReadable,
    config: RmsGridConfig,
    policy: MultiscaleSourceProtection,
) -> RmsGridBatchStatistics:
    """Return raw owned cells, never a block-local interpolated fallback."""
    statistics, _ = _estimate_source_protected_region_statistics(
        request.region,
        source=source,
        config=config,
        island_threshold_sigma=policy.source_finder.island_threshold_sigma,
        multiscale_protection=policy,
    )
    return RmsGridBatchStatistics(
        batch=request.batch,
        statistics=RmsWindowStatistics(
            background=statistics.background,
            rms=statistics.rms,
            available=statistics.available,
            valid_sample_count=statistics.valid_sample_count,
            retained_sample_count=statistics.retained_sample_count,
        ),
        protected_window_count=statistics.protected_window_count,
    )


def _estimate_local_noise_grid(  # noqa: PLR0913
    source: _WindowReadable,
    coarse: PreparedRmsGrid,
    pilot: PreparedRmsGrid,
    config: BackgroundRmsConfig,
    executor: Executor,
    *,
    policy: MultiscaleSourceProtection,
) -> RmsGridStatistics:
    """Protect all fine noise cells using fixed bounded scientific contexts."""
    assert config.adaptive is not None
    fine = config.adaptive.grid
    grid = pilot.geometry
    context_halo = (
        max(config.coarse.window_shape_yx) + max(fine.window_shape_yx) // 2
    )
    filter_halo = _protection_filter_bank(policy).maximum_halo_pixels
    requests: list[_LocalNoiseRequest] = []
    for batch in plan_rms_window_batches(
        grid, maximum_cells=_LOCAL_NOISE_CONTEXT_CELLS
    ):
        yy = slice(batch.grid_y_start, batch.grid_y_stop)
        xx = slice(batch.grid_x_start, batch.grid_x_stop)
        owned = replace(
            grid,
            window_starts_y=grid.window_starts_y[yy],
            window_starts_x=grid.window_starts_x[xx],
            sample_coordinates_y=grid.sample_coordinates_y[yy],
            sample_coordinates_x=grid.sample_coordinates_x[xx],
        )
        bounds = _filter_read_bounds(owned, context_halo + filter_halo)
        if prod(bounds.shape_yx) > config.maximum_constant_map_pixels:
            raise ValueError(
                "local noise context exceeds bounded read admission"
            )
        requests.append(
            _LocalNoiseRequest(
                batch,
                _AdaptiveRegionRequest(
                    grid=owned,
                    coarse=subset_prepared_rms_grid(coarse, bounds),
                    positions_yx=(),
                    detection_rms=subset_prepared_rms_grid(pilot, bounds),
                    context_halo_pixels=context_halo,
                    protection="local-noise-windows",
                ),
            )
        )
    results = executor.map_batches(
        partial(
            _estimate_local_noise_batch,
            source=source,
            config=fine,
            policy=policy,
        ),
        requests,
    )
    return assemble_rms_grid_statistics(grid, results)


def _adaptive_region_request(
    region: _CandidateRegion,
    *,
    global_geometry: RmsGridGeometry,
    coarse: PreparedRmsGrid,
    filter_halo_pixels: int = 0,
) -> _AdaptiveRegionRequest:
    """Bind one candidate region to its fine and coarse bounded summaries."""
    fine_grid = subset_rms_grid_geometry(global_geometry, region.bounds)
    return _AdaptiveRegionRequest(
        grid=fine_grid,
        coarse=subset_prepared_rms_grid(
            coarse,
            _filter_read_bounds(fine_grid, filter_halo_pixels),
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


def _require_local_noise_policy(
    config: BackgroundRmsConfig,
    policy: MultiscaleSourceProtection | None,
    island_threshold_sigma: float | None,
) -> None:
    """Require explicit consistent source admission before fine-grid reads."""
    if config.adaptive is None or policy is None:
        raise ValueError(
            "local noise refinement requires fine-grid source protection"
        )
    if island_threshold_sigma != policy.source_finder.island_threshold_sigma:
        raise ValueError(
            "local noise protection requires the same island threshold"
        )


def _require_bounded_coarse_protection(
    image_shape_yx: tuple[int, int],
    config: BackgroundRmsConfig,
    island_threshold_sigma: float | None,
) -> None:
    """Check whole-plane coarse-mask admission before any pilot read."""
    if island_threshold_sigma is None:
        raise ValueError(
            "coarse source protection requires an island threshold"
        )
    if prod(image_shape_yx) > config.maximum_constant_map_pixels:
        raise ValueError(
            "coarse source protection exceeds bounded image admission"
        )


def refine_background_rms_grids(  # noqa: PLR0913
    source: _WindowReadable,
    coarse_grids: BackgroundRmsGrids,
    config: BackgroundRmsConfig,
    executor: Executor,
    *,
    bright_candidate_positions_yx: tuple[tuple[float, float], ...],
    source_protection_island_threshold_sigma: float | None = None,
    multiscale_protection: MultiscaleSourceProtection | None = None,
    protect_coarse_source_support: bool = False,
    refine_local_noise: bool = False,
) -> BackgroundRmsGrids:
    """Estimate sparse adaptive cells while reusing a prepared coarse grid."""
    if coarse_grids.adaptive_regions or coarse_grids.local_noise is not None:
        raise ValueError("adaptive refinement requires a coarse-only cache")
    image_shape_yx = coarse_grids.coarse.geometry.image_shape_yx
    adaptive_config = config.adaptive
    if refine_local_noise:
        _require_local_noise_policy(
            config,
            multiscale_protection,
            source_protection_island_threshold_sigma,
        )
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

    if adaptive_config is None or (
        not candidate_regions
        and not protect_coarse_source_support
        and not refine_local_noise
    ):
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
    if protect_coarse_source_support:
        _require_bounded_coarse_protection(
            image_shape_yx, config, source_protection_island_threshold_sigma
        )
    # A coarse RMS can dilute noise excursions and misclassify their peaks
    # as sources. This unmasked pilot only admits source protection.
    detection_rms = (
        prepare_rms_grid_for_interpolation(
            estimate_rms_grid(
                source,
                plan_rms_grid(
                    image_shape_yx=image_shape_yx,
                    window_shape_yx=adaptive_config.grid.window_shape_yx,
                    step_yx=adaptive_config.grid.step_yx,
                ),
                adaptive_config.grid,
                executor,
            )
        )
        if multiscale_protection is not None
        and (protect_coarse_source_support or refine_local_noise)
        else None
    )
    if protect_coarse_source_support:
        assert source_protection_island_threshold_sigma is not None
        estimate_coarse = partial(
            _estimate_source_protected_adaptive_region,
            source=source,
            config=config.coarse,
            island_threshold_sigma=source_protection_island_threshold_sigma,
            multiscale_protection=multiscale_protection,
        )
        (protected_coarse,) = executor.map_batches(
            estimate_coarse,
            (
                _AdaptiveRegionRequest(
                    grid=coarse_grids.coarse.geometry,
                    coarse=coarse_grids.coarse,
                    positions_yx=bright_candidate_positions_yx,
                    protection="exclude-samples",
                    guard_window_shape_yx=adaptive_config.grid.window_shape_yx,
                    detection_rms=detection_rms,
                ),
            ),
        )
        coarse_grids = BackgroundRmsGrids(
            coarse=protected_coarse.grid,
            adaptive_regions=(),
            coarse_protected_pixel_count=protected_coarse.protected_pixel_count,
        )
        if not coarse_grids.coarse.scientifically_available:
            return coarse_grids
    if refine_local_noise:
        assert detection_rms is not None and multiscale_protection is not None
        statistics = _estimate_local_noise_grid(
            source,
            coarse_grids.coarse,
            detection_rms,
            config,
            executor,
            policy=multiscale_protection,
        )
        coarse_grids = replace(
            coarse_grids,
            local_noise=prepare_rms_grid_for_interpolation(statistics),
            local_noise_protected_window_count=statistics.protected_window_count,
        )
    if not candidate_regions:
        return coarse_grids
    return _refine_bright_regions(
        source,
        coarse_grids,
        candidate_regions,
        config,
        executor,
        source_protection_island_threshold_sigma=source_protection_island_threshold_sigma,
        multiscale_protection=multiscale_protection,
    )


def _refine_bright_regions(  # noqa: PLR0913
    source: _WindowReadable,
    coarse_grids: BackgroundRmsGrids,
    candidate_regions: tuple[_CandidateRegion, ...],
    config: BackgroundRmsConfig,
    executor: Executor,
    *,
    source_protection_island_threshold_sigma: float | None,
    multiscale_protection: MultiscaleSourceProtection | None,
) -> BackgroundRmsGrids:
    """Refine bright-source background without changing the noise policy."""
    adaptive_config = config.adaptive
    assert adaptive_config is not None
    global_adaptive_geometry = plan_rms_grid(
        image_shape_yx=coarse_grids.coarse.geometry.image_shape_yx,
        window_shape_yx=adaptive_config.grid.window_shape_yx,
        step_yx=adaptive_config.grid.step_yx,
    )
    if source_protection_island_threshold_sigma is None:
        return replace(
            coarse_grids,
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
            filter_halo_pixels=(
                _protection_filter_bank(
                    multiscale_protection
                ).maximum_halo_pixels
                if multiscale_protection is not None
                else 0
            ),
        )
        for region in candidate_regions
    )
    # Source protection can leave a defined zero-variance coarse estimate.
    # Old bright-region work anchors then have no sigma-domain support. Keep
    # that noise availability instead of re-estimating unprotected source
    # emission as noise; admit other independently usable regions unchanged.
    requests = tuple(
        request
        for request in requests
        if request.coarse.scientifically_available
        and np.any(np.isfinite(request.coarse.rms) & (request.coarse.rms > 0))
    )
    estimate_region = partial(
        _estimate_source_protected_adaptive_region,
        source=source,
        config=adaptive_config.grid,
        island_threshold_sigma=source_protection_island_threshold_sigma,
        multiscale_protection=multiscale_protection,
    )
    adaptive_regions = tuple(executor.map_batches(estimate_region, requests))
    return replace(
        coarse_grids,
        adaptive_regions=adaptive_regions,
    )


def prepare_background_rms_tile_request(
    partition: TilePartition,
    grids: BackgroundRmsGrids,
    config: BackgroundRmsConfig,
) -> BackgroundRmsTileRequest:
    """Build one local interpolation request without global grid payloads."""
    coarse = subset_prepared_rms_grid(grids.coarse, partition.core_bounds)
    local_noise = (
        subset_prepared_rms_grid(grids.local_noise, partition.core_bounds)
        if grids.local_noise is not None
        else None
    )
    adaptive_config = config.adaptive
    if not grids.adaptive_regions or adaptive_config is None:
        return BackgroundRmsTileRequest(
            partition=partition,
            coarse=coarse,
            adaptive_regions=(),
            influence_radius_pixels=None,
            transition_width_pixels=None,
            local_noise=local_noise,
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
        local_noise=local_noise,
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
    if request.adaptive_regions and (
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
            influence_radius_pixels=cast(
                float, request.influence_radius_pixels
            ),
            transition_width_pixels=cast(
                float, request.transition_width_pixels
            ),
        )
    if request.local_noise is not None:
        noise = interpolate_prepared_rms_grid(
            request.local_noise,
            bounds,
            image_window.valid_pixels,
            extrapolate_rms=False,
        )
        result = replace(
            result,
            rms=noise.rms,
            scientifically_available=(
                result.scientifically_available
                and noise.scientifically_available
            ),
            fallback_cell_count=result.fallback_cell_count
            + noise.fallback_cell_count,
        )
    return result
