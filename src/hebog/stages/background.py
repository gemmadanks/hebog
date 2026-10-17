# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Bounded source and executor orchestration for background estimation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import partial
from itertools import chain, islice
from math import ceil, floor, isfinite, prod
from typing import Literal, cast

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
    RmsWindowBatchGroup,
    RmsWindowStatistics,
    assemble_rms_grid_statistics,
    blend_adaptive_background_rms,
    clean_cell_coverage,
    estimate_rms_grid_batch,
    group_rms_window_batches,
    interpolate_prepared_rms_grid,
    plan_rms_grid,
    plan_rms_window_batches,
    prepare_local_noise_rms_grid,
    prepare_refinement_rms_grid,
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
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    RmsGridConfig,
    SourceFinderConfig,
)
from hebog.data_models.partitioning import ImageBounds, TilePartition
from hebog.executors.base import Executor
from hebog.io.base import ImageWindow, WindowReadable
from hebog.stages.task_memory import read_requirement

# Every protected block, of local-noise cells or of a bright region's fine
# cells, reads its own cells plus the protection halo, and re-derives the
# wavelet bank over that whole context, so halo pixels are paid for once per
# block. The halo is many cell strides wide, which makes small blocks
# overwhelmingly halo: 16-by-16 cells filtered 22 times the image on a dense
# 1,024-pixel case, against 3.4 times at 48 by 48. Larger blocks are still
# bounded by the same context admission. The owned cells decide the result,
# except where emission a block's side cuts off reaches across the halo into
# them (see `_labels_cut_off_by_the_read`), so this trades occupancy for
# work and moves a value only beside such emission.
_PROTECTED_CONTEXT_CELLS = 2304
# A local-noise cell whose window touches guarded source support takes its
# nearest clean window's RMS, but never below this fraction of the coarse RMS
# at its centre, or of the largest clean window within half a coarse window
# if that is smaller: beside a sharp step in the noise the nearest clean
# window can lie on the quieter side. On the quick check's generated fields
# and SDC1 cut-outs the 0.1% quantile of the nearest fill is at least 0.806
# of the coarse RMS, so the floor acts beyond that scatter (plan task 65).
_LOCAL_NOISE_MINIMUM_COARSE_FRACTION = 0.8
# Most cells must have a clean fine window within the reach that floors
# their fills. Where fewer do, as on a deep field where protection leaves a
# handful of windows clear, most cells would take a distant window's
# estimate and the map would be a patchwork of those few values.
_LOCAL_NOISE_MINIMUM_CLEAN_COVERAGE = 0.5
# Each round's cost per pixel of its largest read, which a task declares
# (``hebog.stages.task_memory``): the largest traced task peak over that read
# on the 3,000-, 10,000- and 15,402-pixel LoTSS-DR3 anchors and the dense
# ELAIS-N1 central 5,000 pixels, rounded up to eight bytes (plan task 17).
_SOURCE_BATCH_BYTES_PER_READ_PIXEL = 152
_PROTECTED_BYTES_PER_READ_PIXEL = 272
# No anchor retired a bright candidate, so this round takes the cost of
# the source batches, which read the same input.
_CANDIDATE_SUPPORT_BYTES_PER_READ_PIXEL = 152
# One task estimates the window batches whose reads start in one square this
# wide, from one read of their union, running the kernel a batch at a time,
# which bounds its memory. One task a batch spent more on overhead than on
# work: on the 10,000-pixel anchor the fine pilot's 32-cell batches made
# 69,150 tasks of 2 ms on a thread, and under Dask each also opened and
# validated the FITS file again, about 6 ms, since a task's source arrives
# unopened, and waited about 3 ms on the scheduler (plan task 73). A square
# holds about 180 fine batches, so a task's overhead is a few per cent, the
# anchor still has hundreds of tasks for the workers, and each pixel is read
# about once rather than three times. The batches' cost per read pixel above
# still bounds a group's: it adds the reads, which cost the same per pixel,
# and one batch's kernel, which is no larger than the group.
_SOURCE_READ_SIDE_PIXELS = 512


@dataclass(frozen=True, slots=True)
class AdaptiveRmsRegion:
    """One merged bright-candidate region and its local fine-grid cache."""

    grid: PreparedRmsGrid
    bright_candidate_positions_yx: tuple[tuple[float, float], ...]
    protected_pixel_count: int
    protected_window_count: int


@dataclass(frozen=True, slots=True)
class BackgroundRmsGrids:
    """Prepared coarse and optional sparse adaptive interpolation caches.

    ``largest_bright_region_read_pixels`` is the most pixels one task read
    to estimate the fine grids around bright candidates, zero if none did.
    """

    coarse: PreparedRmsGrid
    adaptive_regions: tuple[AdaptiveRmsRegion, ...]
    coarse_protected_pixel_count: int = 0
    local_noise: PreparedRmsGrid | None = None
    local_noise_protected_window_count: int = 0
    largest_bright_region_read_pixels: int = 0

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
    background: Literal["estimated", "zero"] = "estimated"


@dataclass(frozen=True, slots=True)
class _CandidateRegion:
    """One bounded union of overlapping adaptive influence areas."""

    bounds: ImageBounds
    positions_yx: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class _AdaptiveRegionRequest:
    """Bounded inputs for one source-protected grid or block of its cells.

    A block reads its cells' windows widened by the filter and context halos
    and clipped to ``context_limit``. Emission that a side of the read inside
    the limit cuts off may belong to a source the block cannot see, so it is
    protected (:func:`_labels_cut_off_by_the_read`). ``counted_bounds`` are
    the pixels whose protection the block reports, so that blocks sharing
    pixels count each once; without them the whole read is counted.
    """

    grid: RmsGridGeometry
    coarse: PreparedRmsGrid
    positions_yx: tuple[tuple[float, float], ...]
    protection: Literal[
        "exclude-samples", "exclude-windows", "local-noise-windows"
    ] = "exclude-windows"
    guard_window_shape_yx: tuple[int, int] | None = None
    detection_rms: PreparedRmsGrid | None = None
    context_halo_pixels: int = 0
    context_limit: ImageBounds | None = None
    counted_bounds: ImageBounds | None = None


@dataclass(frozen=True, slots=True)
class _ProtectedBlockRequest:
    """One globally owned fine-cell block and its bounded protection input."""

    batch: RmsWindowBatch
    region: _AdaptiveRegionRequest


@dataclass(frozen=True, slots=True)
class _ContextBlock:
    """One block of cells, the window it reads and the pixels it counts."""

    batch: RmsWindowBatch
    cells: RmsGridGeometry
    read_bounds: ImageBounds
    counted_bounds: ImageBounds


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


def _filter_read_bounds(
    grid: RmsGridGeometry, halo: int, limit: ImageBounds | None = None
) -> ImageBounds:
    """Include filtering context beyond the fine estimator windows.

    The context is clipped to ``limit``, or to the image without one.
    """
    bounds = _grid_read_bounds(grid)
    if limit is None:
        height, width = grid.image_shape_yx
        limit = ImageBounds(0, height, 0, width)
    return ImageBounds(
        max(limit.y_start, bounds.y_start - halo),
        min(limit.y_stop, bounds.y_stop + halo),
        max(limit.x_start, bounds.x_start - halo),
        min(limit.x_stop, bounds.x_stop + halo),
    )


def _estimate_source_batches(
    group: RmsWindowBatchGroup,
    *,
    source: WindowReadable,
    grid: RmsGridGeometry,
    config: RmsGridConfig,
) -> tuple[RmsGridBatchStatistics, ...]:
    """Read one group's window, then apply the pure kernel to each batch.

    A source gives a pixel the same value and validity however large the
    window that holds it, so each batch sees exactly what its own read would.
    """
    bounds = group.read_bounds
    image_window = source.read_window(bounds)
    if image_window.bounds != bounds:
        raise ValueError("image source returned different window bounds")
    if (
        image_window.values.shape != bounds.shape_yx
        or image_window.valid_pixels.shape != bounds.shape_yx
    ):
        raise ValueError("image source returned a misaligned window")
    values = np.asarray(image_window.values)
    valid_pixels = np.asarray(image_window.valid_pixels)
    results: list[RmsGridBatchStatistics] = []
    for batch in group.batches:
        read = batch.read_bounds
        selection = (
            slice(read.y_start - bounds.y_start, read.y_stop - bounds.y_start),
            slice(read.x_start - bounds.x_start, read.x_stop - bounds.x_start),
        )
        results.append(
            estimate_rms_grid_batch(
                values[selection],
                valid_pixels[selection],
                grid,
                batch,
                config.statistics,
            )
        )
    return tuple(results)


def estimate_rms_grid(
    source: WindowReadable,
    grid: RmsGridGeometry,
    config: RmsGridConfig,
    executor: Executor,
) -> RmsGridStatistics:
    """Estimate one complete coarse grid through bounded executor batches.

    One task estimates the batches whose reads start in one square of
    ``_SOURCE_READ_SIDE_PIXELS``, from one read.
    """
    groups = group_rms_window_batches(
        plan_rms_window_batches(
            grid,
            maximum_cells=config.maximum_batch_cells,
        ),
        read_side_pixels=_SOURCE_READ_SIDE_PIXELS,
    )
    estimate_batches = partial(
        _estimate_source_batches,
        source=source,
        grid=grid,
        config=config,
    )
    results = executor.map_batches(
        estimate_batches,
        groups,
        requirement=read_requirement(
            _SOURCE_BATCH_BYTES_PER_READ_PIXEL,
            (group.read_bounds for group in groups),
        ),
    )
    return assemble_rms_grid_statistics(grid, chain.from_iterable(results))


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
    source: WindowReadable,
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


def _labels_cut_off_by_the_read(
    labels: npt.NDArray[np.int32],
    bounds: ImageBounds,
    limit: ImageBounds | None,
) -> set[int]:
    """Return the labels on a side of the read that lies inside ``limit``.

    Such a label may continue past the read to a source seed the task cannot
    see, so a bounded block protects it. A side on the limit is where the
    image ends, or where one read of a whole bright region would end, so no
    label continues past it that such a read would have seen. A read
    without a limit is a whole grid's, which no side cuts.
    """
    if limit is None:
        return set()
    cut_sides = (
        bounds.y_start > limit.y_start,
        bounds.y_stop < limit.y_stop,
        bounds.x_start > limit.x_start,
        bounds.x_stop < limit.x_stop,
    )
    return {
        int(value)
        for cut, edge in zip(
            cut_sides,
            (labels[0], labels[-1], labels[:, 0], labels[:, -1]),
            strict=True,
        )
        if cut
        for value in np.unique(edge)
        if value > 0
    }


def _connected_source_protection(  # noqa: PLR0913
    normalized_residual: npt.NDArray[np.float64],
    scientifically_valid: npt.NDArray[np.bool_],
    bounds: ImageBounds,
    positions_yx: tuple[tuple[float, float], ...],
    *,
    island_threshold_sigma: float,
    source_finder: SourceFinderConfig | None = None,
    context_limit: ImageBounds | None = None,
) -> npt.NDArray[np.bool_]:
    """Return candidate-connected public-island support in one bounded read.

    With ``context_limit``, support cut off by a side of the read inside it
    is protected too (:func:`_labels_cut_off_by_the_read`).
    """
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
    candidate_labels |= _labels_cut_off_by_the_read(
        labels, bounds, context_limit
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
    source: WindowReadable,
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
        request.context_limit,
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
        context_limit=request.context_limit,
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
            selected = {
                int(label)
                for label in np.unique(labels[connected_protection])
                if label > 0
            }
            selected |= _labels_cut_off_by_the_read(
                labels, bounds, request.context_limit
            )
            connected_protection = np.isin(labels, tuple(sorted(selected)))
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
                    context_limit=request.context_limit,
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
    counted = (
        bounds if request.counted_bounds is None else request.counted_bounds
    )
    counted_protection = protected[
        counted.y_start - bounds.y_start : counted.y_stop - bounds.y_start,
        counted.x_start - bounds.x_start : counted.x_stop - bounds.x_start,
    ]
    return statistics, int(np.count_nonzero(counted_protection))


def _estimate_source_protected_grid(
    request: _AdaptiveRegionRequest,
    *,
    source: WindowReadable,
    config: RmsGridConfig,
    island_threshold_sigma: float,
    multiscale_protection: MultiscaleSourceProtection | None = None,
) -> AdaptiveRmsRegion:
    """Prepare one protected grid after all its raw statistics exist.

    Every cell takes its nearest clean window's statistics, as a protected
    coarse grid needs.
    """
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


def _estimate_protected_block(
    request: _ProtectedBlockRequest,
    *,
    source: WindowReadable,
    config: RmsGridConfig,
    island_threshold_sigma: float,
    multiscale_protection: MultiscaleSourceProtection | None,
) -> tuple[RmsGridBatchStatistics, int]:
    """Return raw owned cells and the protected pixels the block counts.

    The cells are never a block-local interpolated fallback: the caller
    fills them once the whole grid is assembled.
    """
    statistics, protected_pixel_count = (
        _estimate_source_protected_region_statistics(
            request.region,
            source=source,
            config=config,
            island_threshold_sigma=island_threshold_sigma,
            multiscale_protection=multiscale_protection,
        )
    )
    return (
        RmsGridBatchStatistics(
            batch=request.batch,
            statistics=RmsWindowStatistics(
                background=statistics.background,
                rms=statistics.rms,
                available=statistics.available,
                valid_sample_count=statistics.valid_sample_count,
                retained_sample_count=statistics.retained_sample_count,
            ),
            protected_window_count=statistics.protected_window_count,
        ),
        protected_pixel_count,
    )


def _protection_context_halo(config: BackgroundRmsConfig) -> int:
    """Return the coarse and fine window context around a block of cells."""
    assert config.adaptive is not None
    return (
        max(config.coarse.window_shape_yx)
        + max(config.adaptive.grid.window_shape_yx) // 2
    )


def _half_coarse_window_cells(config: BackgroundRmsConfig) -> tuple[int, int]:
    """Return the fine cells along each axis within half a coarse window."""
    assert config.adaptive is not None
    (window_y, window_x), (step_y, step_x) = (
        config.coarse.window_shape_yx,
        config.adaptive.grid.step_yx,
    )
    return window_y // 2 // step_y, window_x // 2 // step_x


def _counted_span(
    window_starts: tuple[int, ...],
    first_cell: int,
    stop_cell: int,
    limit: tuple[int, int],
) -> tuple[int, int]:
    """Return the pixels a block of cells counts along one axis.

    They run from the block's first window start to the next block's, with
    the first and last blocks reaching ``limit``, so the blocks along an
    axis count each pixel within it once.
    """
    return (
        limit[0] if first_cell == 0 else window_starts[first_cell],
        limit[1]
        if stop_cell == len(window_starts)
        else window_starts[stop_cell],
    )


def _context_blocks(
    grid: RmsGridGeometry, halo: int, limit: ImageBounds
) -> list[_ContextBlock]:
    """Plan each block of a grid's cells with the window its task reads.

    A block reads its cells' windows widened by ``halo`` and clipped to
    ``limit``, which holds every window of the grid.
    """
    blocks: list[_ContextBlock] = []
    for batch in plan_rms_window_batches(
        grid, maximum_cells=_PROTECTED_CONTEXT_CELLS
    ):
        yy = slice(batch.grid_y_start, batch.grid_y_stop)
        xx = slice(batch.grid_x_start, batch.grid_x_stop)
        cells = replace(
            grid,
            window_starts_y=grid.window_starts_y[yy],
            window_starts_x=grid.window_starts_x[xx],
            sample_coordinates_y=grid.sample_coordinates_y[yy],
            sample_coordinates_x=grid.sample_coordinates_x[xx],
        )
        y_start, y_stop = _counted_span(
            grid.window_starts_y,
            batch.grid_y_start,
            batch.grid_y_stop,
            (limit.y_start, limit.y_stop),
        )
        x_start, x_stop = _counted_span(
            grid.window_starts_x,
            batch.grid_x_start,
            batch.grid_x_stop,
            (limit.x_start, limit.x_stop),
        )
        blocks.append(
            _ContextBlock(
                batch,
                cells,
                _filter_read_bounds(cells, halo, limit),
                ImageBounds(y_start, y_stop, x_start, x_stop),
            )
        )
    return blocks


def _local_noise_contexts(
    grid: RmsGridGeometry,
    config: BackgroundRmsConfig,
    policy: MultiscaleSourceProtection,
) -> list[_ContextBlock]:
    """Plan each block of fine cells with the window its task reads.

    A task reads its cells with the coarse and fine windows and the widest
    protection filter around them. The filter grows with the beam, so the
    window does too, until the image clips it.
    """
    height, width = grid.image_shape_yx
    return _context_blocks(
        grid,
        _protection_context_halo(config)
        + _protection_filter_bank(policy).maximum_halo_pixels,
        ImageBounds(0, height, 0, width),
    )


def _estimate_local_noise_grid(  # noqa: PLR0913
    source: WindowReadable,
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
    context_halo = _protection_context_halo(config)
    height, width = grid.image_shape_yx
    requests: list[_ProtectedBlockRequest] = []
    reads: list[ImageBounds] = []
    for block in _local_noise_contexts(grid, config, policy):
        if (
            prod(block.read_bounds.shape_yx)
            > config.maximum_constant_map_pixels
        ):
            raise ValueError(
                "local noise context exceeds bounded read admission"
            )
        reads.append(block.read_bounds)
        requests.append(
            _ProtectedBlockRequest(
                block.batch,
                _AdaptiveRegionRequest(
                    grid=block.cells,
                    coarse=subset_prepared_rms_grid(coarse, block.read_bounds),
                    positions_yx=(),
                    detection_rms=subset_prepared_rms_grid(
                        pilot, block.read_bounds
                    ),
                    context_halo_pixels=context_halo,
                    protection="local-noise-windows",
                    context_limit=ImageBounds(0, height, 0, width),
                ),
            )
        )
    results = executor.map_batches(
        partial(
            _estimate_protected_block,
            source=source,
            config=fine,
            island_threshold_sigma=policy.source_finder.island_threshold_sigma,
            multiscale_protection=policy,
        ),
        requests,
        requirement=read_requirement(_PROTECTED_BYTES_PER_READ_PIXEL, reads),
    )
    return assemble_rms_grid_statistics(
        grid, (statistics for statistics, _ in results)
    )


def _estimate_unprotected_adaptive_regions(
    source: WindowReadable,
    candidate_regions: tuple[_CandidateRegion, ...],
    region_grids: tuple[RmsGridGeometry, ...],
    config: RmsGridConfig,
    executor: Executor,
) -> tuple[AdaptiveRmsRegion, ...]:
    """Preserve the established compact-profile fine-grid calculation."""
    return tuple(
        AdaptiveRmsRegion(
            grid=prepare_rms_grid_for_interpolation(
                estimate_rms_grid(source, region_grid, config, executor)
            ),
            bright_candidate_positions_yx=region.positions_yx,
            protected_pixel_count=0,
            protected_window_count=0,
        )
        for region, region_grid in zip(
            candidate_regions, region_grids, strict=True
        )
    )


def _positions_inside(
    positions_yx: tuple[tuple[float, float], ...], bounds: ImageBounds
) -> tuple[tuple[float, float], ...]:
    """Return the candidates whose nearest pixel lies inside ``bounds``."""
    return tuple(
        (y, x)
        for y, x in positions_yx
        if bounds.y_start <= round(y) < bounds.y_stop
        and bounds.x_start <= round(x) < bounds.x_stop
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


def _require_protection_threshold(
    island_threshold_sigma: float | None,
    adaptive: AdaptiveRmsConfig,
) -> None:
    """Require a protection threshold below the bright-candidate threshold."""
    if island_threshold_sigma is not None and (
        not isfinite(island_threshold_sigma)
        or island_threshold_sigma <= 0
        or island_threshold_sigma >= adaptive.candidate_threshold_sigma
    ):
        raise ValueError(
            "adaptive refinement requires a finite positive public island "
            "threshold below its candidate threshold for source protection"
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


def _supported_candidate_positions(
    request: tuple[_CandidateRegion, PreparedRmsGrid],
    *,
    source: WindowReadable,
    island_threshold_sigma: float,
) -> tuple[tuple[float, float], ...]:
    """Revalidate sparse work anchors against a changed coarse estimate."""
    region, coarse = request
    window = source.read_window(region.bounds)
    if window.bounds != region.bounds:
        raise ValueError("image source returned different candidate bounds")
    if (
        window.values.shape != region.bounds.shape_yx
        or window.valid_pixels.shape != region.bounds.shape_yx
    ):
        raise ValueError("image source returned a misaligned candidate window")
    fields = interpolate_prepared_rms_grid(
        coarse, region.bounds, window.valid_pixels
    )
    normalized, valid = normalize_residual(
        window.values, window.valid_pixels, fields.background, fields.rms
    )
    return tuple(
        (y, x)
        for y, x in region.positions_yx
        if valid[
            round(y) - region.bounds.y_start, round(x) - region.bounds.x_start
        ]
        and normalized[
            round(y) - region.bounds.y_start, round(x) - region.bounds.x_start
        ]
        >= island_threshold_sigma
    )


def _adopt_protected_coarse(  # noqa: PLR0913
    protected: AdaptiveRmsRegion,
    unprotected: BackgroundRmsGrids,
    candidate_regions: tuple[_CandidateRegion, ...],
    source: WindowReadable,
    executor: Executor,
    *,
    island_threshold_sigma: float,
    margin_pixels: float,
) -> tuple[BackgroundRmsGrids, tuple[_CandidateRegion, ...]]:
    """Adopt a protected coarse estimate and retire the anchors it explains.

    A field whose every pixel lies within the guard of some source support
    keeps no sample to protect with. Protection then refines nothing and the
    unprotected estimate stands, with its anchors.

    Initial bright work anchors are not immutable source seeds. The protected
    coarse estimate can explain one as noise; retire only anchors without
    support in that new estimate. Unchanged-cache callers still reach the
    strict source-protection consistency guard.
    """
    if not protected.grid.scientifically_available:
        return unprotected, candidate_regions
    coarse = protected.grid
    retain = partial(
        _supported_candidate_positions,
        source=source,
        island_threshold_sigma=island_threshold_sigma,
    )
    retained = executor.map_batches(
        retain,
        tuple(
            (region, subset_prepared_rms_grid(coarse, region.bounds))
            for region in candidate_regions
        ),
        requirement=read_requirement(
            _CANDIDATE_SUPPORT_BYTES_PER_READ_PIXEL,
            (region.bounds for region in candidate_regions),
        ),
    )
    protected_grids = BackgroundRmsGrids(
        coarse=coarse,
        adaptive_regions=(),
        coarse_protected_pixel_count=protected.protected_pixel_count,
    )
    supported_regions = _merge_candidate_regions(
        tuple(position for positions in retained for position in positions),
        image_shape_yx=coarse.geometry.image_shape_yx,
        margin_pixels=margin_pixels,
    )
    return protected_grids, supported_regions


def refine_background_rms_grids(  # noqa: PLR0913
    source: WindowReadable,
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
    _require_protection_threshold(
        source_protection_island_threshold_sigma, adaptive_config
    )
    if protect_coarse_source_support:
        _require_bounded_coarse_protection(
            image_shape_yx, config, source_protection_island_threshold_sigma
        )
    # Without a coarse estimate no pixel has a background, so nothing here
    # can refine it and the estimate stays unavailable as a whole; the fine
    # pilot alone would be 4.8 million cells at 15,402 pixels.
    if not coarse_grids.coarse.scientifically_available:
        return coarse_grids
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
    unprotected_grids, unprotected_regions = coarse_grids, candidate_regions
    if protect_coarse_source_support:
        assert source_protection_island_threshold_sigma is not None
        estimate_coarse = partial(
            _estimate_source_protected_grid,
            source=source,
            config=config.coarse,
            island_threshold_sigma=source_protection_island_threshold_sigma,
            multiscale_protection=multiscale_protection,
        )
        image_height, image_width = coarse_grids.coarse.geometry.image_shape_yx
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
            # The protected coarse grid is estimated over the whole image in
            # one task, so it declares the whole image.
            requirement=read_requirement(
                _PROTECTED_BYTES_PER_READ_PIXEL,
                (ImageBounds(0, image_height, 0, image_width),),
            ),
        )
        coarse_grids, candidate_regions = _adopt_protected_coarse(
            protected_coarse,
            coarse_grids,
            candidate_regions,
            source,
            executor,
            island_threshold_sigma=source_protection_island_threshold_sigma,
            margin_pixels=adaptive_margin,
        )
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
        reach = _half_coarse_window_cells(config)
        local_noise = prepare_local_noise_rms_grid(
            statistics,
            coarse_grids.coarse,
            minimum_coarse_fraction=_LOCAL_NOISE_MINIMUM_COARSE_FRACTION,
            clean_cell_reach_yx=reach,
        )
        # A field so crowded that fine windows clear of source support reach
        # too few of its cells, or none at all, is too crowded to protect: a
        # protected coarse estimate there rests on the few pixels farthest
        # from every source, and the local noise would copy a few distant
        # windows across the field. The unprotected sigma-clipped estimate
        # stands instead, as PyBDSF's does, with its anchors, and the local
        # noise refines nothing.
        if (
            clean_cell_coverage(statistics.available, reach)
            < _LOCAL_NOISE_MINIMUM_CLEAN_COVERAGE
        ):
            coarse_grids, candidate_regions = (
                unprotected_grids,
                unprotected_regions,
            )
            local_noise = replace(local_noise, scientifically_available=False)
        coarse_grids = replace(
            coarse_grids,
            local_noise=local_noise,
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
    source: WindowReadable,
    coarse_grids: BackgroundRmsGrids,
    candidate_regions: tuple[_CandidateRegion, ...],
    config: BackgroundRmsConfig,
    executor: Executor,
    *,
    source_protection_island_threshold_sigma: float | None,
    multiscale_protection: MultiscaleSourceProtection | None,
) -> BackgroundRmsGrids:
    """Estimate the fine grids that refine the estimate around bright sources.

    The tile blend uses them for the background both ways and for the RMS
    only upwards (``blend_adaptive_background_rms``). Candidates close
    enough to chain merge into one region, which can span the image, so a
    protected region's cells are estimated in blocks. Each block reads the
    context a local-noise block reads, clipped to the window one read of the
    whole region would take, and protects emission its sides cut off from a
    candidate (:func:`_labels_cut_off_by_the_read`). A region of one block
    is read exactly as a whole. A larger one can protect more than one read
    of it would, never less: emission from a block's side that reaches its
    cells without reaching any candidate. On the ELAIS-N1 deep field's
    central 5,000², one region of 951 candidates, that is 117 of 505,521
    fine windows, all beside block seams.

    Raises:
        ValueError: If a block's read would exceed the admitted read, before
            any block is read.
    """
    adaptive_config = config.adaptive
    assert adaptive_config is not None
    global_adaptive_geometry = plan_rms_grid(
        image_shape_yx=coarse_grids.coarse.geometry.image_shape_yx,
        window_shape_yx=adaptive_config.grid.window_shape_yx,
        step_yx=adaptive_config.grid.step_yx,
    )
    region_grids = tuple(
        subset_rms_grid_geometry(global_adaptive_geometry, region.bounds)
        for region in candidate_regions
    )
    if source_protection_island_threshold_sigma is None:
        return replace(
            coarse_grids,
            adaptive_regions=_estimate_unprotected_adaptive_regions(
                source,
                candidate_regions,
                region_grids,
                adaptive_config.grid,
                executor,
            ),
            largest_bright_region_read_pixels=max(
                (
                    prod(batch.read_bounds.shape_yx)
                    for region_grid in region_grids
                    for batch in plan_rms_window_batches(
                        region_grid,
                        maximum_cells=adaptive_config.grid.maximum_batch_cells,
                    )
                ),
                default=0,
            ),
        )
    filter_halo = (
        _protection_filter_bank(multiscale_protection).maximum_halo_pixels
        if multiscale_protection is not None
        else 0
    )
    context_halo = _protection_context_halo(config)
    planned: list[
        tuple[_CandidateRegion, RmsGridGeometry, PreparedRmsGrid, int]
    ] = []
    requests: list[_ProtectedBlockRequest] = []
    reads: list[ImageBounds] = []
    largest_read = 0
    for region, region_grid in zip(
        candidate_regions, region_grids, strict=True
    ):
        limit = _filter_read_bounds(region_grid, filter_halo)
        region_coarse = subset_prepared_rms_grid(coarse_grids.coarse, limit)
        # Source protection can leave a defined zero-variance coarse
        # estimate. Old bright-region work anchors then have no sigma-domain
        # support. Keep that noise availability instead of re-estimating
        # unprotected source emission as noise; admit other independently
        # usable regions unchanged.
        if not region_coarse.scientifically_available or not np.any(
            np.isfinite(region_coarse.rms) & (region_coarse.rms > 0)
        ):
            continue
        blocks = _context_blocks(
            region_grid, filter_halo + context_halo, limit
        )
        for block in blocks:
            read_pixels = prod(block.read_bounds.shape_yx)
            if read_pixels > config.maximum_constant_map_pixels:
                raise ValueError(
                    "bright region context exceeds bounded read admission"
                )
            largest_read = max(largest_read, read_pixels)
            reads.append(block.read_bounds)
            requests.append(
                _ProtectedBlockRequest(
                    block.batch,
                    _AdaptiveRegionRequest(
                        grid=block.cells,
                        coarse=subset_prepared_rms_grid(
                            coarse_grids.coarse, block.read_bounds
                        ),
                        positions_yx=_positions_inside(
                            region.positions_yx, block.read_bounds
                        ),
                        context_halo_pixels=context_halo,
                        context_limit=limit,
                        counted_bounds=block.counted_bounds,
                    ),
                )
            )
        planned.append((region, region_grid, region_coarse, len(blocks)))
    results = iter(
        executor.map_batches(
            partial(
                _estimate_protected_block,
                source=source,
                config=adaptive_config.grid,
                island_threshold_sigma=source_protection_island_threshold_sigma,
                multiscale_protection=multiscale_protection,
            ),
            requests,
            requirement=read_requirement(
                _PROTECTED_BYTES_PER_READ_PIXEL, reads
            ),
        )
    )
    adaptive_regions: list[AdaptiveRmsRegion] = []
    for region, region_grid, region_coarse, block_count in planned:
        region_results = tuple(islice(results, block_count))
        statistics = assemble_rms_grid_statistics(
            region_grid, (block for block, _ in region_results)
        )
        adaptive_regions.append(
            AdaptiveRmsRegion(
                # A fine RMS reaches one fine window from where it was
                # measured.
                grid=prepare_refinement_rms_grid(
                    statistics,
                    region_coarse,
                    fill_reach_pixels=float(
                        max(adaptive_config.grid.window_shape_yx)
                    ),
                ),
                bright_candidate_positions_yx=region.positions_yx,
                protected_pixel_count=sum(
                    count for _, count in region_results
                ),
                protected_window_count=statistics.protected_window_count,
            )
        )
    return replace(
        coarse_grids,
        adaptive_regions=tuple(adaptive_regions),
        largest_bright_region_read_pixels=largest_read,
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
            background=config.background,
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
        background=config.background,
    )


def estimate_background_rms_tile(
    source: WindowReadable,
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
    # Local noise that keeps no cell anywhere refines nothing, as a bright
    # region without a usable fine cell does: the noise above stands, which
    # refine_background_rms_grids has made the unprotected coarse estimate.
    if (
        request.local_noise is not None
        and request.local_noise.scientifically_available
    ):
        noise = interpolate_prepared_rms_grid(
            request.local_noise,
            bounds,
            image_window.valid_pixels,
            extrapolate_rms=False,
        )
        result = replace(
            result,
            rms=noise.rms,
            fallback_cell_count=result.fallback_cell_count
            + noise.fallback_cell_count,
        )
    if request.background == "zero":
        # PyBDSF's mean_map="zero": the RMS above stands, and nothing is
        # subtracted where a background was defined.
        result = replace(
            result,
            background=np.where(
                np.isfinite(result.background), 0.0, result.background
            ),
        )
    return result
