"""Tests for sparse adaptive background/RMS refinement."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import TypeVar, cast

import numpy as np
import pytest

from hebog.algorithms.background import (
    BackgroundRmsTile,
    PreparedRmsGrid,
    RmsGridStatistics,
    blend_adaptive_background_rms,
    interpolate_prepared_rms_grid,
    plan_rms_grid,
    prepare_local_noise_rms_grid,
    prepare_refinement_rms_grid,
    prepare_rms_grid_for_interpolation,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)
from hebog.data_models import ImageBounds, TilePartition
from hebog.executors import SerialExecutor, TaskRequirement
from hebog.io.base import ImageWindow
from hebog.stages.background import (
    BackgroundRmsGrids,
    MultiscaleSourceProtection,
    estimate_background_rms_grids,
    estimate_background_rms_tile,
    prepare_background_rms_tile_request,
    refine_background_rms_grids,
)

Input = TypeVar("Input")
Output = TypeVar("Output")


@pytest.mark.parametrize("fraction", (0.0, 1.1, float("nan"), float("inf")))
def test_multiscale_protection_rejects_invalid_filter_support(
    fraction: float,
) -> None:
    """Invalid filtering policy must fail even when no source is discovered."""
    with pytest.raises(ValueError, match="support fraction"):
        MultiscaleSourceProtection(
            BeamShapePixels(4.0, 3.0, 0.0),
            SourceFinderConfig(5.0, 3.0, 7),
            fraction,
        )


class _ArrayImageSource:
    """Serve bounded reads from an in-memory scientific plane."""

    def __init__(self, values: np.ndarray) -> None:
        self.values = np.asarray(values, dtype=np.float64)
        self.read_bounds: list[ImageBounds] = []

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return one owned source window."""
        bounds.require_inside(tuple(self.values.shape))
        self.read_bounds.append(bounds)
        selection = (
            slice(bounds.y_start, bounds.y_stop),
            slice(bounds.x_start, bounds.x_stop),
        )
        values = np.array(self.values[selection], copy=True)
        return ImageWindow(
            bounds=bounds,
            values=values,
            valid_pixels=np.isfinite(values),
        )


class _RetryExecutor(SerialExecutor):
    """Repeat region work while returning one canonical ordered result."""

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[Output]:
        """Inject one identical retry without changing returned evidence."""
        inputs = list(batches)
        results = super().map_batches(
            function, inputs, requirement=requirement
        )
        if inputs:
            super().map_batches(function, inputs[-1:])
        return results


def _grid(
    window_shape_yx: tuple[int, int],
    step_yx: tuple[int, int],
) -> RmsGridConfig:
    """Return a bounded grid policy with one shared clipping policy."""
    return RmsGridConfig(
        window_shape_yx=window_shape_yx,
        step_yx=step_yx,
        statistics=RmsWindowStatisticsConfig(
            clipping_sigma=3.0,
            maximum_iterations=10,
            minimum_samples=6,
        ),
        maximum_batch_cells=8,
    )


def _config(*, adaptive: bool = True) -> BackgroundRmsConfig:
    """Return one explicit coarse and optional adaptive policy."""
    return BackgroundRmsConfig(
        coarse=_grid((9, 9), (4, 4)),
        adaptive=(
            AdaptiveRmsConfig(
                grid=_grid((5, 5), (2, 2)),
                candidate_threshold_sigma=20.0,
                influence_radius_pixels=7.0,
                transition_width_pixels=3.0,
            )
            if adaptive
            else None
        ),
        maximum_spatial_window_fraction=0.25,
        maximum_constant_map_pixels=4096,
    )


def _source_protection_config() -> BackgroundRmsConfig:
    """Return a coarse/fine scale separation for contamination fixtures."""
    return BackgroundRmsConfig(
        coarse=_grid((31, 31), (10, 10)),
        adaptive=AdaptiveRmsConfig(
            grid=_grid((5, 5), (2, 2)),
            candidate_threshold_sigma=20.0,
            influence_radius_pixels=12.0,
            transition_width_pixels=4.0,
        ),
        maximum_spatial_window_fraction=0.5,
        maximum_constant_map_pixels=4096,
    )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: _grid((0, 5), (2, 2)), "window shape"),
        (lambda: _grid((5, 5), (0, 2)), "step"),
        (lambda: _grid((5, 5), (6, 2)), "step"),
        (
            lambda: RmsGridConfig(
                window_shape_yx=(5, 5),
                step_yx=(2, 2),
                statistics=RmsWindowStatisticsConfig(3.0, 10, 6),
                maximum_batch_cells=True,  # type: ignore[arg-type]
            ),
            "maximum_batch_cells",
        ),
        (
            lambda: AdaptiveRmsConfig(
                grid=_grid((5, 5), (2, 2)),
                candidate_threshold_sigma=20.0,
                influence_radius_pixels=0.0,
                transition_width_pixels=1.0,
            ),
            "influence_radius_pixels",
        ),
        (
            lambda: AdaptiveRmsConfig(
                grid=_grid((5, 5), (2, 2)),
                candidate_threshold_sigma=20.0,
                influence_radius_pixels=4.0,
                transition_width_pixels=5.0,
            ),
            "transition_width_pixels",
        ),
        (
            lambda: AdaptiveRmsConfig(
                grid=_grid((5, 5), (2, 2)),
                candidate_threshold_sigma=float("nan"),
                influence_radius_pixels=4.0,
                transition_width_pixels=2.0,
            ),
            "candidate_threshold_sigma",
        ),
        (
            lambda: BackgroundRmsConfig(
                coarse=_grid((5, 5), (2, 2)),
                adaptive=None,
                maximum_spatial_window_fraction=float("nan"),
                maximum_constant_map_pixels=10,
            ),
            "maximum_spatial_window_fraction",
        ),
        (
            lambda: BackgroundRmsConfig(
                coarse=_grid((5, 5), (2, 2)),
                adaptive=None,
                maximum_spatial_window_fraction=0.25,
                maximum_constant_map_pixels=0,
            ),
            "maximum_constant_map_pixels",
        ),
    ],
)
def test_rejects_invalid_background_configuration(
    factory: object,
    message: str,
) -> None:
    """Invalid scientific and memory policies fail before image reads."""
    with pytest.raises(ValueError, match=message):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    "positions",
    [((-1.0, 2.0),), ((2.0, 40.0),), ((float("nan"), 2.0),)],
)
def test_rejects_invalid_bright_candidate_positions(
    positions: tuple[tuple[float, float], ...],
) -> None:
    """Adaptive regions must be anchored inside the logical image."""
    image = np.ones((32, 32), dtype=np.float64)

    with pytest.raises(ValueError, match="bright candidate"):
        estimate_background_rms_grids(
            _ArrayImageSource(image),
            image.shape,
            _config(),
            SerialExecutor(),
            bright_candidate_positions_yx=positions,
            source_protection_island_threshold_sigma=3.0,
        )


def test_adaptive_refinement_raises_local_rms_only_near_candidate() -> None:
    """A noisy bright region uses fine RMS while distant pixels stay coarse."""
    y, x = np.indices((40, 44))
    image = np.where((x + y) % 2 == 0, -1.0, 1.0)
    image[15:26, 17:28] *= 5.0
    image[20, 22] = 50.0
    source = _ArrayImageSource(image)
    candidate = ((20.0, 22.0),)

    grids = estimate_background_rms_grids(
        source,
        image.shape,
        _config(),
        SerialExecutor(),
        bright_candidate_positions_yx=candidate,
        source_protection_island_threshold_sigma=3.0,
    )
    manifest = plan_image_partitions(
        image_shape_yx=image.shape,
        tile_core_shape_yx=(20, 22),
        halo_yx=(0, 0),
    )
    centre_request = prepare_background_rms_tile_request(
        manifest.owner_for_position_yx(candidate[0]),
        grids,
        _config(),
    )
    far_request = prepare_background_rms_tile_request(
        manifest.tiles[0],
        grids,
        _config(),
    )
    centre_tile = estimate_background_rms_tile(source, centre_request)
    far_tile = estimate_background_rms_tile(source, far_request)

    assert len(grids.adaptive_regions) == 1
    full_fine_cell_count = ((image.shape[0] - 5) // 2 + 2) * (
        (image.shape[1] - 5) // 2 + 2
    )
    assert 0 < grids.adaptive_estimated_cell_count < full_fine_cell_count
    local_y = int(candidate[0][0] - centre_tile.bounds.y_start)
    local_x = int(candidate[0][1] - centre_tile.bounds.x_start)
    assert centre_tile.rms[local_y, local_x] > 2.0 * grids.coarse.rms.mean()
    np.testing.assert_allclose(far_tile.rms[0, 0], grids.coarse.rms[0, 0])


def test_adaptive_refinement_excludes_connected_bright_source_support() -> (
    None
):
    """Fine windows touching a candidate's 3-sigma island use fallback."""
    y, x = np.indices((80, 80))
    image = np.where((x + y) % 2 == 0, -1.0, 1.0)
    source_support = (y - 40) ** 2 + (x - 40) ** 2 <= 6**2
    image[source_support] += 25.0
    image[40, 40] += 75.0
    source = _ArrayImageSource(image)
    candidate = ((40.0, 40.0),)
    config = _source_protection_config()

    grids = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=candidate,
        source_protection_island_threshold_sigma=3.0,
    )
    manifest = plan_image_partitions(
        image_shape_yx=image.shape,
        tile_core_shape_yx=image.shape,
        halo_yx=(0, 0),
    )
    tile = estimate_background_rms_tile(
        source,
        prepare_background_rms_tile_request(
            manifest.tiles[0],
            grids,
            config,
        ),
    )

    assert len(grids.adaptive_regions) == 1
    region = grids.adaptive_regions[0]
    assert region.protected_pixel_count >= np.count_nonzero(source_support)
    assert region.protected_window_count > 0
    assert region.grid.fallback_cell_count == region.protected_window_count
    assert abs(tile.background[40, 40]) < 2.0


def test_adaptive_refinement_guards_one_estimator_half_width() -> None:
    """Fine samples stay one estimator footprint from bright support."""
    y, x = np.indices((80, 80))
    image = np.where((x + y) % 2 == 0, -1.0, 1.0)
    image[40, 40] = 100.0

    grids = estimate_background_rms_grids(
        _ArrayImageSource(image),
        image.shape,
        _source_protection_config(),
        SerialExecutor(),
        bright_candidate_positions_yx=((40.0, 40.0),),
        source_protection_island_threshold_sigma=3.0,
    )

    region = grids.adaptive_regions[0]
    assert region.protected_pixel_count == 13
    assert region.protected_window_count > 1


def test_adaptive_refinement_keeps_source_free_local_noise_estimates() -> None:
    """Protection does not disable adaptive RMS in a noisy neighbourhood."""
    y, x = np.indices((80, 80))
    image = np.where((x + y) % 2 == 0, -1.0, 1.0)
    noisy = (slice(31, 50), slice(31, 50))
    image[noisy] *= 6.0
    image[40, 40] = 100.0
    source = _ArrayImageSource(image)
    config = _source_protection_config()

    grids = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=((40.0, 40.0),),
        source_protection_island_threshold_sigma=3.0,
    )
    manifest = plan_image_partitions(
        image_shape_yx=image.shape,
        tile_core_shape_yx=image.shape,
        halo_yx=(0, 0),
    )
    tile = estimate_background_rms_tile(
        source,
        prepare_background_rms_tile_request(
            manifest.tiles[0],
            grids,
            config,
        ),
    )

    region = grids.adaptive_regions[0]
    assert 0 < region.protected_window_count < region.grid.geometry.cell_count
    assert tile.rms[40, 40] > 2.0 * grids.coarse.rms.mean()


def test_overlapping_and_disjoint_candidates_have_bounded_protection() -> None:
    """Merged influence regions protect every connected candidate island."""
    y, x = np.indices((96, 96))
    image = np.where((x + y) % 2 == 0, -1.0, 1.0)
    positions = ((30.0, 30.0), (30.0, 38.0), (72.0, 72.0))
    for candidate_y, candidate_x in positions:
        support = (y - candidate_y) ** 2 + (x - candidate_x) ** 2 <= 3**2
        image[support] += 25.0
        image[round(candidate_y), round(candidate_x)] += 75.0

    grids = estimate_background_rms_grids(
        _ArrayImageSource(image),
        image.shape,
        _source_protection_config(),
        SerialExecutor(),
        bright_candidate_positions_yx=tuple(reversed(positions)),
        source_protection_island_threshold_sigma=3.0,
    )

    assert len(grids.adaptive_regions) == 2
    assert (
        sum(
            len(region.bright_candidate_positions_yx)
            for region in grids.adaptive_regions
        )
        == 3
    )
    assert grids.adaptive_protected_pixel_count >= 3 * 29
    assert grids.adaptive_protected_window_count > 0


def test_edge_and_invalid_pixels_do_not_enter_source_protection() -> None:
    """Clipped support stays bounded and invalid pixels remain excluded."""
    y, x = np.indices((64, 68))
    image = np.where((x + y) % 2 == 0, -1.0, 1.0)
    support = (y - 2) ** 2 + (x - 2) ** 2 <= 4**2
    image[support] += 30.0
    image[2, 2] += 70.0
    image[0, 0] = np.nan
    config = _source_protection_config()
    source = _ArrayImageSource(image)

    grids = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=((2.0, 2.0),),
        source_protection_island_threshold_sigma=3.0,
    )
    manifest = plan_image_partitions(
        image_shape_yx=image.shape,
        tile_core_shape_yx=image.shape,
        halo_yx=(0, 0),
    )
    tile = estimate_background_rms_tile(
        source,
        prepare_background_rms_tile_request(manifest.tiles[0], grids, config),
    )

    valid_support = support & np.isfinite(image)
    support_positions = np.argwhere(valid_support)
    squared_distances = (y[..., np.newaxis] - support_positions[:, 0]) ** 2 + (
        x[..., np.newaxis] - support_positions[:, 1]
    ) ** 2
    expected_guard = np.any(squared_distances <= 2**2, axis=-1) & np.isfinite(
        image
    )
    assert grids.adaptive_protected_pixel_count == np.count_nonzero(
        expected_guard
    )
    assert np.isnan(tile.background[0, 0])
    assert np.isnan(tile.rms[0, 0])


def test_candidate_protection_threshold_is_bounded_when_enabled() -> None:
    """Source protection cannot use an invalid public island threshold."""
    image = np.tile(np.array([-1.0, 1.0]), 40 * 22).reshape(40, 44)
    image[20, 22] = 50.0
    source = _ArrayImageSource(image)

    for threshold in (0.0, 20.0, float("nan")):
        with pytest.raises(ValueError, match="public island threshold"):
            estimate_background_rms_grids(
                source,
                image.shape,
                _config(),
                SerialExecutor(),
                bright_candidate_positions_yx=((20.0, 22.0),),
                source_protection_island_threshold_sigma=threshold,
            )


def test_missing_protection_threshold_preserves_compact_background_path() -> (
    None
):
    """The explicit compact compatibility profile keeps its reviewed path."""
    image = np.tile(np.array([-1.0, 1.0]), 40 * 22).reshape(40, 44)
    image[20, 22] = 50.0

    grids = estimate_background_rms_grids(
        _ArrayImageSource(image),
        image.shape,
        _config(),
        SerialExecutor(),
        bright_candidate_positions_yx=((20.0, 22.0),),
    )

    assert len(grids.adaptive_regions) == 1
    assert grids.adaptive_protected_pixel_count == 0
    assert grids.adaptive_protected_window_count == 0


def test_adaptive_candidate_must_belong_to_public_island_support() -> None:
    """A stale or mismatched candidate cannot silently expose source pixels."""
    image = np.tile(np.array([-1.0, 1.0]), 40 * 22).reshape(40, 44)

    with pytest.raises(ValueError, match="absent from source-protection"):
        estimate_background_rms_grids(
            _ArrayImageSource(image),
            image.shape,
            _config(),
            SerialExecutor(),
            bright_candidate_positions_yx=((20.0, 22.0),),
            source_protection_island_threshold_sigma=3.0,
        )


def test_distant_candidates_keep_separate_bounded_fine_grids() -> None:
    """Adaptive summary memory scales with regions, not full image area."""
    image = np.tile(np.array([-1.0, 1.0]), 100 * 55).reshape(100, 110)
    positions = ((15.0, 16.0), (82.0, 91.0))
    image[15, 16] = 50.0
    image[82, 91] = 50.0
    config = _config()

    forward = estimate_background_rms_grids(
        _ArrayImageSource(image),
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=positions,
        source_protection_island_threshold_sigma=3.0,
    )
    reverse = estimate_background_rms_grids(
        _ArrayImageSource(image),
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=tuple(reversed(positions)),
        source_protection_island_threshold_sigma=3.0,
    )

    full_fine_cell_count = ((image.shape[0] - 5) // 2 + 2) * (
        (image.shape[1] - 5) // 2 + 2
    )
    assert len(forward.adaptive_regions) == 2
    assert forward.adaptive_estimated_cell_count < full_fine_cell_count / 4
    assert tuple(
        region.grid.geometry for region in forward.adaptive_regions
    ) == tuple(region.grid.geometry for region in reverse.adaptive_regions)
    for first, second in zip(
        forward.adaptive_regions,
        reverse.adaptive_regions,
        strict=True,
    ):
        np.testing.assert_array_equal(first.grid.rms, second.grid.rms)


def test_adaptive_protection_is_retry_and_completion_order_invariant() -> None:
    """Repeated or reversed region completion cannot change fine grids."""
    y, x = np.indices((96, 96))
    image = np.where((x + y) % 2 == 0, -1.0, 1.0)
    positions = ((20.0, 20.0), (74.0, 75.0))
    for candidate_y, candidate_x in positions:
        support = (y - candidate_y) ** 2 + (x - candidate_x) ** 2 <= 4**2
        image[support] += 25.0
        image[round(candidate_y), round(candidate_x)] += 75.0
    config = _source_protection_config()

    serial = estimate_background_rms_grids(
        _ArrayImageSource(image),
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=positions,
        source_protection_island_threshold_sigma=3.0,
    )
    retried = estimate_background_rms_grids(
        _ArrayImageSource(image),
        image.shape,
        config,
        _RetryExecutor(),
        bright_candidate_positions_yx=tuple(reversed(positions)),
        source_protection_island_threshold_sigma=3.0,
    )

    assert retried.adaptive_protected_pixel_count == (
        serial.adaptive_protected_pixel_count
    )
    assert retried.adaptive_protected_window_count == (
        serial.adaptive_protected_window_count
    )
    for expected, actual in zip(
        serial.adaptive_regions,
        retried.adaptive_regions,
        strict=True,
    ):
        np.testing.assert_array_equal(
            actual.grid.background,
            expected.grid.background,
        )
        np.testing.assert_array_equal(actual.grid.rms, expected.grid.rms)
        np.testing.assert_array_equal(
            actual.grid.fallback_cells, expected.grid.fallback_cells
        )


def _assemble_tiles(
    source: _ArrayImageSource,
    grids: BackgroundRmsGrids,
    config: BackgroundRmsConfig,
    tiles: tuple[TilePartition, ...],
) -> tuple[np.ndarray, np.ndarray]:
    """Assemble small analytic outputs for partition-invariance assertions."""
    shape = grids.coarse.geometry.image_shape_yx
    background = np.empty(shape, dtype=np.float64)
    rms = np.empty(shape, dtype=np.float64)
    for partition in tiles:
        request = prepare_background_rms_tile_request(
            partition,
            grids,
            config,
        )
        tile = estimate_background_rms_tile(source, request)
        bounds = partition.core_bounds
        selection = (
            slice(bounds.y_start, bounds.y_stop),
            slice(bounds.x_start, bounds.x_stop),
        )
        background[selection] = tile.background
        rms[selection] = tile.rms
    return background, rms


@pytest.mark.parametrize(
    ("core_shape", "origin"),
    [((36, 38), (0, 0)), ((12, 10), (0, 0)), ((12, 10), (5, 3))],
)
def test_output_is_invariant_to_tile_shape_and_partition_origin(
    core_shape: tuple[int, int],
    origin: tuple[int, int],
) -> None:
    """Global window ownership makes tile boundaries scientifically inert."""
    y, x = np.indices((36, 38), dtype=np.float64)
    image = 2.0 + 0.01 * y + np.where((x + y) % 2 == 0, -1.0, 1.0)
    image[13:24, 14:25] *= 3.0
    image[18, 19] = 50.0
    positions = ((18.0, 19.0),)
    config = _config()
    source = _ArrayImageSource(image)
    grids = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=positions,
        source_protection_island_threshold_sigma=3.0,
    )
    reference_manifest = plan_image_partitions(
        image_shape_yx=image.shape,
        tile_core_shape_yx=image.shape,
        halo_yx=(0, 0),
    )
    expected = _assemble_tiles(
        source,
        grids,
        config,
        reference_manifest.tiles,
    )
    manifest = plan_image_partitions(
        image_shape_yx=image.shape,
        tile_core_shape_yx=core_shape,
        halo_yx=(0, 0),
        partition_origin_yx=origin,
    )

    actual = _assemble_tiles(
        source,
        grids,
        config,
        tuple(reversed(manifest.tiles)),
    )

    np.testing.assert_allclose(actual[0], expected[0], atol=1e-12)
    np.testing.assert_allclose(actual[1], expected[1], atol=1e-12)


def _coarse_grid(image_shape_yx: tuple[int, int]) -> PreparedRmsGrid:
    """Return a 150-pixel coarse grid every 50 pixels, its RMS rising in x."""
    grid = plan_rms_grid(
        image_shape_yx=image_shape_yx,
        window_shape_yx=(150, 150),
        step_yx=(50, 50),
    )
    rms = np.broadcast_to(
        1.0 + 0.1 * np.arange(grid.shape_yx[1]), grid.shape_yx
    )
    return prepare_rms_grid_for_interpolation(
        RmsGridStatistics(
            geometry=grid,
            background=np.zeros(grid.shape_yx),
            rms=np.array(rms, dtype=np.float64),
            available=np.ones(grid.shape_yx, dtype=np.bool_),
            valid_sample_count=np.ones(grid.shape_yx, dtype=np.int64),
            retained_sample_count=np.ones(grid.shape_yx, dtype=np.int64),
        )
    )


def _fine_statistics(
    image_shape_yx: tuple[int, int],
    clean_rms: dict[tuple[int, int], float],
) -> RmsGridStatistics:
    """Return a 35-pixel grid every 7 pixels whose only clean cells are these.

    Every clean cell has a background of 0.5.
    """
    grid = plan_rms_grid(
        image_shape_yx=image_shape_yx,
        window_shape_yx=(35, 35),
        step_yx=(7, 7),
    )
    available = np.zeros(grid.shape_yx, dtype=np.bool_)
    rms = np.full(grid.shape_yx, np.nan)
    for cell, value in clean_rms.items():
        available[cell] = True
        rms[cell] = value
    samples = np.where(available, 35 * 35, 0).astype(np.int64)
    return RmsGridStatistics(
        geometry=grid,
        background=np.where(available, 0.5, np.nan),
        rms=rms,
        available=available,
        valid_sample_count=samples,
        retained_sample_count=samples,
    )


def _coarse_rms_at_cell(
    coarse: PreparedRmsGrid,
    statistics: RmsGridStatistics,
    cell: tuple[int, int],
) -> float:
    """Return the coarse RMS published at one fine cell's centre pixel."""
    y = int(statistics.geometry.sample_coordinates_y[cell[0]])
    x = int(statistics.geometry.sample_coordinates_x[cell[1]])
    return float(
        interpolate_prepared_rms_grid(
            coarse,
            ImageBounds(y, y + 1, x, x + 1),
            np.ones((1, 1), dtype=np.bool_),
        ).rms[0, 0]
    )


def test_a_refinement_cell_takes_a_clean_window_only_within_one_window() -> (
    None
):
    """A fine RMS fills cells up to one fine window from where it was made.

    The one clean window is cell (20, 20), centred on pixel (157, 157), and
    the reach is its 35-pixel width. Cells exactly 35 pixels away, along an
    axis or a 21-28-35 diagonal, take its RMS; cells 42 or 39.6 pixels away,
    and the far corners, keep the coarse RMS at their centres, which rises
    along x. The background is filled from the clean window, as before
    (plan task 63).
    """
    shape_yx = (300, 300)
    coarse = _coarse_grid(shape_yx)
    statistics = _fine_statistics(shape_yx, {(20, 20): 0.25})

    prepared = prepare_refinement_rms_grid(
        statistics, coarse, fill_reach_pixels=35.0
    )

    for within in ((20, 20), (20, 25), (20, 15), (25, 20), (23, 24), (17, 16)):
        assert prepared.rms[within] == 0.25
    for beyond in ((20, 26), (24, 24), (0, 0), (38, 38)):
        assert prepared.rms[beyond] == pytest.approx(
            _coarse_rms_at_cell(coarse, statistics, beyond), rel=1e-12
        )
    assert prepared.rms[20, 26] != prepared.rms[20, 38]
    np.testing.assert_array_equal(prepared.background, 0.5)
    np.testing.assert_array_equal(
        prepared.fallback_cells, ~statistics.available
    )
    assert prepared.scientifically_available


def test_a_refinement_cell_within_reach_takes_its_nearest_clean_window() -> (
    None
):
    """Between two clean windows a cell takes the nearer one's RMS."""
    shape_yx = (300, 300)
    statistics = _fine_statistics(shape_yx, {(20, 20): 0.25, (20, 28): 0.75})

    prepared = prepare_refinement_rms_grid(
        statistics, _coarse_grid(shape_yx), fill_reach_pixels=35.0
    )

    assert prepared.rms[20, 23] == 0.25
    assert prepared.rms[20, 25] == 0.75


def test_a_refinement_grid_within_reach_everywhere_is_filled_as_before() -> (
    None
):
    """With every cell within reach, the bounded fill is the nearest fill."""
    shape_yx = (60, 60)
    statistics = _fine_statistics(shape_yx, {(2, 2): 0.25, (4, 1): 0.5})

    bounded = prepare_refinement_rms_grid(
        statistics, _coarse_grid(shape_yx), fill_reach_pixels=35.0
    )
    nearest = prepare_rms_grid_for_interpolation(statistics)

    np.testing.assert_array_equal(bounded.rms, nearest.rms)
    np.testing.assert_array_equal(bounded.background, nearest.background)


def test_a_refinement_grid_without_a_clean_window_stays_unavailable() -> None:
    """No clean window means no fine estimate anywhere, not a coarse copy."""
    shape_yx = (300, 300)

    prepared = prepare_refinement_rms_grid(
        _fine_statistics(shape_yx, {}),
        _coarse_grid(shape_yx),
        fill_reach_pixels=35.0,
    )

    assert not prepared.scientifically_available
    assert np.all(np.isnan(prepared.rms))


@pytest.mark.parametrize("reach", (-1.0, float("nan"), float("inf")))
def test_a_refinement_fill_rejects_an_unbounded_or_negative_reach(
    reach: float,
) -> None:
    """The reach is a finite, non-negative distance in pixels."""
    shape_yx = (300, 300)
    with pytest.raises(ValueError, match="fill_reach_pixels"):
        prepare_refinement_rms_grid(
            _fine_statistics(shape_yx, {(20, 20): 0.25}),
            _coarse_grid(shape_yx),
            fill_reach_pixels=reach,
        )


def test_a_refinement_fill_needs_an_available_coarse_grid() -> None:
    """A fine estimate never stands in for a missing coarse estimate."""
    shape_yx = (300, 300)
    coarse = replace(_coarse_grid(shape_yx), scientifically_available=False)

    with pytest.raises(ValueError, match="available coarse grid"):
        prepare_refinement_rms_grid(
            _fine_statistics(shape_yx, {(20, 20): 0.25}),
            coarse,
            fill_reach_pixels=35.0,
        )


# Half a 150-pixel coarse window in 7-pixel fine cells.
_HALF_COARSE_WINDOW_CELLS = (10, 10)


def _floor_reference(
    coarse: PreparedRmsGrid,
    statistics: RmsGridStatistics,
    cell: tuple[int, int],
) -> float:
    """Return the smaller of the coarse RMS and the largest clean cell nearby.

    A clean cell is nearby within 10 cells along each axis; with none there
    is no floor (plan task 69).
    """
    reach_y, reach_x = _HALF_COARSE_WINDOW_CELLS
    nearby = (
        slice(max(cell[0] - reach_y, 0), cell[0] + reach_y + 1),
        slice(max(cell[1] - reach_x, 0), cell[1] + reach_x + 1),
    )
    clean = statistics.rms[nearby][statistics.available[nearby]]
    coarse_rms = _coarse_rms_at_cell(coarse, statistics, cell)
    return min(coarse_rms, float(clean.max())) if clean.size else 0.0


def test_a_fill_near_a_clean_window_reads_most_of_the_coarse_rms() -> None:
    """A filled cell within reach of a clean window reads 0.8 of the coarse.

    Cell (20, 20) measured a quiet 0.25 and cell (20, 30) a noisy 1.5,
    against a coarse RMS of 1.17 and 1.31 there. A cell filled from the quiet
    one within 10 cells of either is raised to 0.8 of the coarse RMS at its
    own centre, which rises along x; a cell filled from the noisy one keeps
    1.5; each measured cell keeps its own estimate; and a cell beyond the
    reach of both keeps its nearest fill (plan tasks 65 and 69). The
    background is filled as before.
    """
    shape_yx = (300, 300)
    coarse = _coarse_grid(shape_yx)
    statistics = _fine_statistics(shape_yx, {(20, 20): 0.25, (20, 30): 1.5})

    prepared = prepare_local_noise_rms_grid(
        statistics,
        coarse,
        minimum_coarse_fraction=0.8,
        clean_cell_reach_yx=_HALF_COARSE_WINDOW_CELLS,
    )

    assert prepared.rms[20, 20] == 0.25
    assert prepared.rms[20, 30] == 1.5
    for quiet_side in ((20, 21), (20, 24), (14, 24), (28, 22)):
        assert prepared.rms[quiet_side] == pytest.approx(
            0.8 * _coarse_rms_at_cell(coarse, statistics, quiet_side),
            rel=1e-12,
        )
    assert prepared.rms[20, 21] < prepared.rms[20, 24]
    for noisy_side in ((20, 26), (20, 31), (29, 38)):
        assert prepared.rms[noisy_side] == 1.5
    for beyond_reach in ((0, 0), (38, 10), (5, 20)):
        assert prepared.rms[beyond_reach] == 0.25
        assert prepared.rms[beyond_reach] < 0.8 * _coarse_rms_at_cell(
            coarse, statistics, beyond_reach
        )
    np.testing.assert_array_equal(prepared.background, 0.5)
    np.testing.assert_array_equal(
        prepared.fallback_cells, ~statistics.available
    )
    assert prepared.scientifically_available


@pytest.mark.parametrize("fraction", (0.0, 0.5, 0.8, 1.0))
def test_a_local_noise_fill_is_the_larger_of_the_nearest_and_the_floor(
    fraction: float,
) -> None:
    """Every filled cell is its nearest fill or the floor, whichever is larger.

    The cell (5, 5), at 0.5, caps the floor of the cells within its reach,
    where the coarse RMS is higher; with no floor the grid is the
    nearest-window fill unchanged.
    """
    shape_yx = (300, 300)
    coarse = _coarse_grid(shape_yx)
    statistics = _fine_statistics(
        shape_yx, {(5, 5): 0.5, (20, 20): 0.9, (35, 33): 1.3}
    )

    prepared = prepare_local_noise_rms_grid(
        statistics,
        coarse,
        minimum_coarse_fraction=fraction,
        clean_cell_reach_yx=_HALF_COARSE_WINDOW_CELLS,
    )
    nearest = prepare_rms_grid_for_interpolation(statistics)

    filled = ~statistics.available
    floor = np.array(
        [
            fraction * _floor_reference(coarse, statistics, cell)
            for cell in zip(*np.nonzero(filled), strict=True)
        ]
    )
    np.testing.assert_allclose(
        prepared.rms[filled],
        np.maximum(nearest.rms[filled], floor),
        rtol=1e-12,
    )
    np.testing.assert_array_equal(
        prepared.rms[~filled], statistics.rms[~filled]
    )
    np.testing.assert_array_equal(prepared.background, nearest.background)
    if fraction == 0.0:
        np.testing.assert_array_equal(prepared.rms, nearest.rms)
    elif fraction >= 0.8:
        assert np.any(prepared.rms[filled] > nearest.rms[filled])


def test_a_local_noise_floor_never_exceeds_the_clean_windows_nearby() -> None:
    """Clean windows that all read below the coarse RMS bound the floor.

    A coarse window over extended emission keeps emission the clipping does
    not remove, so its RMS can exceed every clean fine window around it.
    Here the clean cells (20, 20) and (22, 24) read 0.6 where the coarse RMS
    is 1.17 and 1.22: a filled cell within 10 cells of them is floored at 0.8
    of 0.6, not of the coarse RMS, and one beyond their reach has no floor
    and keeps its nearest fill (plan tasks 65 and 69).
    """
    shape_yx = (300, 300)
    coarse = _coarse_grid(shape_yx)
    statistics = _fine_statistics(shape_yx, {(20, 20): 0.6, (22, 24): 0.6})

    prepared = prepare_local_noise_rms_grid(
        statistics,
        coarse,
        minimum_coarse_fraction=0.8,
        clean_cell_reach_yx=_HALF_COARSE_WINDOW_CELLS,
    )

    for within in ((20, 21), (30, 30), (10, 14), (21, 34)):
        assert prepared.rms[within] == 0.6
    for beyond in ((0, 0), (38, 38), (21, 35)):
        assert prepared.rms[beyond] == 0.6
        assert prepared.rms[beyond] < 0.8 * _coarse_rms_at_cell(
            coarse, statistics, beyond
        )


def test_a_fill_inside_a_wide_source_keeps_its_nearest_window() -> None:
    """Beyond every clean window's reach the coarse RMS floors nothing.

    A source wider than twice the reach blanks every window over it, and
    the unprotected coarse window there holds the source's emission. Here
    the only clean cells, at 0.3, lie on the grid's left edge, and the coarse
    RMS rises to 1.4 on the right: cells within 10 of the clean column are
    floored at 0.8 of the smaller of the coarse RMS and 0.3, which is 0.24,
    below their fill, and every cell further right keeps the fill of 0.3
    although 0.8 of the coarse RMS there is more than twice that (plan task
    69).
    """
    shape_yx = (300, 300)
    coarse = _coarse_grid(shape_yx)
    statistics = _fine_statistics(
        shape_yx, {(row, 0): 0.3 for row in range(0, 40, 4)}
    )

    prepared = prepare_local_noise_rms_grid(
        statistics,
        coarse,
        minimum_coarse_fraction=0.8,
        clean_cell_reach_yx=_HALF_COARSE_WINDOW_CELLS,
    )

    np.testing.assert_array_equal(prepared.rms[~statistics.available], 0.3)
    for far in ((20, 20), (20, 37), (0, 37)):
        assert 0.8 * _coarse_rms_at_cell(coarse, statistics, far) > 0.6
    assert prepared.scientifically_available


@pytest.mark.parametrize(
    "reach", ((-1, 10), (10, -1), (10,), (10, 10, 10), (True, 10))
)
def test_a_local_noise_floor_rejects_a_reach_that_is_not_two_cell_counts(
    reach: tuple[int, ...],
) -> None:
    """The reach is a non-negative whole number of cells along each axis."""
    shape_yx = (300, 300)
    with pytest.raises(ValueError, match="clean_cell_reach_yx"):
        prepare_local_noise_rms_grid(
            _fine_statistics(shape_yx, {(20, 20): 0.25}),
            _coarse_grid(shape_yx),
            minimum_coarse_fraction=0.8,
            clean_cell_reach_yx=cast(tuple[int, int], reach),
        )


def test_a_local_noise_grid_with_every_cell_measured_is_unchanged() -> None:
    """A grid of measured cells keeps every estimate, however low."""
    shape_yx = (60, 60)
    grid = plan_rms_grid(
        image_shape_yx=shape_yx, window_shape_yx=(35, 35), step_yx=(7, 7)
    )
    statistics = _fine_statistics(
        shape_yx,
        {
            (y, x): 0.1 + 0.01 * (y + x)
            for y in range(grid.shape_yx[0])
            for x in range(grid.shape_yx[1])
        },
    )

    prepared = prepare_local_noise_rms_grid(
        statistics,
        _coarse_grid(shape_yx),
        minimum_coarse_fraction=0.8,
        clean_cell_reach_yx=_HALF_COARSE_WINDOW_CELLS,
    )

    np.testing.assert_array_equal(prepared.rms, statistics.rms)


def test_a_local_noise_grid_without_a_clean_window_stays_unavailable() -> None:
    """No clean window means no local noise, and no coarse estimate is read."""
    shape_yx = (300, 300)
    coarse = replace(_coarse_grid(shape_yx), scientifically_available=False)

    prepared = prepare_local_noise_rms_grid(
        _fine_statistics(shape_yx, {}),
        coarse,
        minimum_coarse_fraction=0.8,
        clean_cell_reach_yx=_HALF_COARSE_WINDOW_CELLS,
    )

    assert not prepared.scientifically_available
    assert np.all(np.isnan(prepared.rms))


@pytest.mark.parametrize("fraction", (-0.1, 1.1, float("nan"), float("inf")))
def test_a_local_noise_floor_rejects_a_fraction_outside_zero_to_one(
    fraction: float,
) -> None:
    """The floor is a finite fraction of the coarse RMS from 0 to 1."""
    shape_yx = (300, 300)
    with pytest.raises(ValueError, match="minimum_coarse_fraction"):
        prepare_local_noise_rms_grid(
            _fine_statistics(shape_yx, {(20, 20): 0.25}),
            _coarse_grid(shape_yx),
            minimum_coarse_fraction=fraction,
            clean_cell_reach_yx=_HALF_COARSE_WINDOW_CELLS,
        )


def test_a_local_noise_floor_needs_an_available_coarse_grid() -> None:
    """A fill is never floored against a missing coarse estimate."""
    shape_yx = (300, 300)
    coarse = replace(_coarse_grid(shape_yx), scientifically_available=False)

    with pytest.raises(ValueError, match="available coarse grid"):
        prepare_local_noise_rms_grid(
            _fine_statistics(shape_yx, {(20, 20): 0.25}),
            coarse,
            minimum_coarse_fraction=0.8,
            clean_cell_reach_yx=_HALF_COARSE_WINDOW_CELLS,
        )


def _tile(
    bounds: ImageBounds,
    background: np.ndarray,
    rms: np.ndarray,
) -> BackgroundRmsTile:
    """Return one available interpolated tile holding these planes."""
    return BackgroundRmsTile(
        bounds=bounds,
        background=np.asarray(background, dtype=np.float64),
        rms=np.asarray(rms, dtype=np.float64),
        scientifically_available=True,
        fallback_cell_count=0,
    )


def _candidate_weight(
    bounds: ImageBounds,
    positions_yx: tuple[tuple[float, float], ...],
    *,
    influence_radius_pixels: float,
    transition_width_pixels: float,
) -> np.ndarray:
    """Return the smooth-step weight of the nearest bright candidate."""
    y, x = np.mgrid[
        bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
    ]
    distance = np.min(
        [np.hypot(y - py, x - px) for py, px in positions_yx], axis=0
    )
    transition = np.clip(
        (influence_radius_pixels - distance) / transition_width_pixels,
        0.0,
        1.0,
    )
    return transition * transition * (3.0 - 2.0 * transition)


def test_the_bright_region_rms_only_raises_the_coarse_rms() -> None:
    """A fine RMS above the coarse one is blended in; one below is not.

    Around the candidate the fine RMS reads half the coarse RMS to the left
    and twice it to the right. To the right the blend is the weighted mean it
    always was; to the left the coarse RMS stands, so a quieter fine estimate
    never lowers the noise (plan task 63). The background blends both ways.
    """
    bounds = ImageBounds(0, 40, 0, 40)
    columns = np.broadcast_to(np.arange(40), (40, 40))
    coarse = _tile(bounds, np.zeros((40, 40)), np.ones((40, 40)))
    fine = _tile(bounds, np.ones((40, 40)), np.where(columns < 20, 0.5, 2.0))
    weight = _candidate_weight(
        bounds,
        ((20.0, 20.0),),
        influence_radius_pixels=12.0,
        transition_width_pixels=4.0,
    )

    blended = blend_adaptive_background_rms(
        coarse,
        fine,
        ((20.0, 20.0),),
        influence_radius_pixels=12.0,
        transition_width_pixels=4.0,
    )

    right = columns >= 20
    np.testing.assert_array_equal(
        blended.rms[right], ((1.0 - weight) * 1.0 + weight * 2.0)[right]
    )
    np.testing.assert_array_equal(blended.rms[~right], 1.0)
    np.testing.assert_array_equal(blended.background, weight)
    assert np.any(weight[~right] > 0.0)


def test_the_blended_rms_never_falls_below_the_coarse_rms() -> None:
    """Over random estimates and three candidates, coarse is the floor.

    Where the fine RMS is no higher the coarse RMS stands exactly; where it
    is higher the blend is the weighted mean, never below the coarse RMS.
    """
    generator = np.random.default_rng(63)
    bounds = ImageBounds(5, 45, 3, 51)
    shape = bounds.shape_yx
    coarse = _tile(
        bounds,
        generator.normal(size=shape),
        generator.uniform(0.5, 2.0, shape),
    )
    fine = _tile(
        bounds,
        generator.normal(size=shape),
        generator.uniform(0.5, 2.0, shape),
    )
    positions = ((10.0, 12.0), (30.0, 40.0), (44.0, 4.0))
    weight = _candidate_weight(
        bounds,
        positions,
        influence_radius_pixels=9.0,
        transition_width_pixels=3.0,
    )

    blended = blend_adaptive_background_rms(
        coarse,
        fine,
        positions,
        influence_radius_pixels=9.0,
        transition_width_pixels=3.0,
    )

    assert np.all(blended.rms >= coarse.rms)
    lower = fine.rms <= coarse.rms
    np.testing.assert_array_equal(blended.rms[lower], coarse.rms[lower])
    higher = ~lower & (weight > 0.0)
    assert np.any(higher) and np.any(lower & (weight > 0.0))
    np.testing.assert_allclose(
        blended.rms[higher],
        ((1.0 - weight) * coarse.rms + weight * fine.rms)[higher],
        rtol=1e-15,
    )


def test_a_bright_region_far_from_any_clean_window_keeps_the_coarse_rms() -> (
    None
):
    """Fine cells beyond one fine window from a clean one leave coarse noise.

    A bright disc of radius 6 protects the fine windows within about 10
    pixels of its centre, more than the 5-pixel fine window from the nearest
    clean one, so the coarse RMS stands at the centre, where the nearest
    clean window's RMS once did (plan task 63). Every tiling, in reverse
    order, publishes the one-tile planes, and no pixel's noise falls below
    the coarse RMS.
    """
    y, x = np.indices((96, 96))
    image = np.random.default_rng(6363).normal(0.0, 1.0, (96, 96))
    image[(y - 48) ** 2 + (x - 48) ** 2 <= 6**2] += 30.0
    image[48, 48] += 100.0
    config = _source_protection_config()
    source = _ArrayImageSource(image)
    grids = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=((48.0, 48.0),),
        source_protection_island_threshold_sigma=3.0,
    )
    whole = plan_image_partitions(
        image_shape_yx=image.shape,
        tile_core_shape_yx=image.shape,
        halo_yx=(0, 0),
    )
    tiled = plan_image_partitions(
        image_shape_yx=image.shape,
        tile_core_shape_yx=(13, 11),
        halo_yx=(0, 0),
        partition_origin_yx=(5, 3),
    )
    coarse = interpolate_prepared_rms_grid(
        grids.coarse,
        ImageBounds(0, 96, 0, 96),
        np.ones(image.shape, dtype=np.bool_),
    )

    expected = _assemble_tiles(source, grids, config, whole.tiles)
    actual = _assemble_tiles(
        source, grids, config, tuple(reversed(tiled.tiles))
    )

    (region,) = grids.adaptive_regions
    assert not np.all(region.grid.fallback_cells)
    np.testing.assert_allclose(actual[0], expected[0], atol=1e-12)
    np.testing.assert_allclose(actual[1], expected[1], atol=1e-12)
    assert np.all(expected[1] >= coarse.rms)
    assert expected[1][48, 48] == coarse.rms[48, 48]


def test_no_candidates_skip_adaptive_reads_and_match_coarse_only() -> None:
    """No bright region means adaptive configuration has zero extra cost."""
    image = np.tile(np.array([-1.0, 1.0]), 36 * 20).reshape(36, 40)
    adaptive_source = _ArrayImageSource(image)
    coarse_source = _ArrayImageSource(image)

    adaptive = estimate_background_rms_grids(
        adaptive_source,
        image.shape,
        _config(),
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    coarse = estimate_background_rms_grids(
        coarse_source,
        image.shape,
        _config(adaptive=False),
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )

    assert adaptive.adaptive_regions == ()
    assert adaptive.adaptive_estimated_cell_count == 0
    assert len(adaptive_source.read_bounds) == len(coarse_source.read_bounds)
    np.testing.assert_array_equal(adaptive.coarse.rms, coarse.coarse.rms)


def test_adaptive_refinement_reuses_the_prepared_coarse_cache() -> None:
    """Candidate refinement adds fine reads without repeating coarse work."""
    image = np.tile(np.array([-1.0, 1.0]), 40 * 22).reshape(40, 44)
    image[20, 22] = 50.0
    source = _ArrayImageSource(image)
    config = _config()
    coarse = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    coarse_read_count = len(source.read_bounds)

    refined = refine_background_rms_grids(
        source,
        coarse,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=((20.0, 22.0),),
        source_protection_island_threshold_sigma=3.0,
    )

    assert refined.coarse is coarse.coarse
    assert len(source.read_bounds) > coarse_read_count
    assert refined.adaptive_regions


def test_adaptive_refinement_rejects_an_already_refined_cache() -> None:
    """Retries cannot stack duplicate fine regions onto cached summaries."""
    image = np.tile(np.array([-1.0, 1.0]), 40 * 22).reshape(40, 44)
    image[20, 22] = 50.0
    source = _ArrayImageSource(image)
    config = _config()
    refined = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=((20.0, 22.0),),
        source_protection_island_threshold_sigma=3.0,
    )

    with pytest.raises(ValueError, match="coarse-only"):
        refine_background_rms_grids(
            source,
            refined,
            config,
            SerialExecutor(),
            bright_candidate_positions_yx=((20.0, 22.0),),
            source_protection_island_threshold_sigma=3.0,
        )


@pytest.mark.parametrize("missing", ("radius", "transition"))
def test_adaptive_tile_rejects_incomplete_blend_metadata(missing: str) -> None:
    """A malformed worker request cannot publish an undefined blend."""
    image = np.tile(np.array([-1.0, 1.0]), 40 * 22).reshape(40, 44)
    image[20, 22] = 50.0
    source = _ArrayImageSource(image)
    config = _config()
    grids = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=((20.0, 22.0),),
        source_protection_island_threshold_sigma=3.0,
    )
    partition = plan_image_partitions(
        image_shape_yx=image.shape,
        tile_core_shape_yx=image.shape,
        halo_yx=(0, 0),
    ).tiles[0]
    request = prepare_background_rms_tile_request(partition, grids, config)
    assert request.adaptive_regions
    request = replace(
        request,
        influence_radius_pixels=None
        if missing == "radius"
        else request.influence_radius_pixels,
        transition_width_pixels=None
        if missing == "transition"
        else request.transition_width_pixels,
    )
    with pytest.raises(ValueError, match="missing blend metadata"):
        estimate_background_rms_tile(source, request)


def test_large_constant_map_fallback_fails_before_unbounded_read() -> None:
    """Automatic constant fallback never gathers an unapproved large plane."""
    image = np.ones((80, 80), dtype=np.float64)
    source = _ArrayImageSource(image)
    config = BackgroundRmsConfig(
        coarse=_grid((30, 30), (10, 10)),
        adaptive=None,
        maximum_spatial_window_fraction=0.25,
        maximum_constant_map_pixels=4096,
    )

    with pytest.raises(ValueError, match="constant-map pixel limit"):
        estimate_background_rms_grids(
            source,
            image.shape,
            config,
            SerialExecutor(),
            bright_candidate_positions_yx=(),
        )

    assert source.read_bounds == []


@pytest.mark.parametrize("missing_threshold", (False, True))
def test_coarse_protection_rejects_unadmitted_work_before_read(
    missing_threshold: bool,
) -> None:
    """Neither absent science policy nor excess memory admits a full read."""
    image = np.tile(np.array([-1.0, 1.0]), 80 * 40).reshape(80, 80)
    image[40, 40] = 100
    source = _ArrayImageSource(image)
    config = _source_protection_config()
    coarse = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    read_count = len(source.read_bounds)
    message = (
        "island threshold" if missing_threshold else "bounded image admission"
    )
    with pytest.raises(ValueError, match=message):
        refine_background_rms_grids(
            source,
            coarse,
            config,
            SerialExecutor(),
            bright_candidate_positions_yx=((40, 40),),
            source_protection_island_threshold_sigma=None
            if missing_threshold
            else 3.0,
            protect_coarse_source_support=True,
        )
    assert len(source.read_bounds) == read_count


@pytest.mark.parametrize("source_fills_image", (False, True))
def test_coarse_protection_is_retry_invariant_and_never_removes_noise(
    source_fills_image: bool,
) -> None:
    """Protection excludes source samples; with none left it refines nothing.

    A field whose every pixel lies within the guard of some source support
    keeps no sample to protect an estimate with. The unprotected estimate
    then stands, as the coarse noise does for a bright region without a
    usable fine cell, rather than leaving a field of sources without noise.
    """
    noise = np.tile(np.array([-1.0, 1.0]), 80 * 40).reshape(80, 80)
    config = replace(
        _source_protection_config(), maximum_constant_map_pixels=6400
    )
    coarse = estimate_background_rms_grids(
        _ArrayImageSource(noise),
        noise.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    image = np.full_like(noise, 100.0) if source_fills_image else noise.copy()
    image[40, 40] = 100
    source = _ArrayImageSource(image)
    results = [
        refine_background_rms_grids(
            source,
            coarse,
            config,
            executor,
            bright_candidate_positions_yx=((40, 40),),
            source_protection_island_threshold_sigma=3.0,
            protect_coarse_source_support=True,
        )
        for executor in (SerialExecutor(), _RetryExecutor())
    ]
    first, second = results
    assert (
        first.coarse_protected_pixel_count
        == second.coarse_protected_pixel_count
    )
    np.testing.assert_array_equal(
        first.coarse.background, second.coarse.background
    )
    np.testing.assert_array_equal(first.coarse.rms, second.coarse.rms)
    assert first.coarse.scientifically_available
    if source_fills_image:
        assert first.coarse is coarse.coarse
        assert first.coarse_protected_pixel_count == 0
        # The bright region is still refined from the estimate that stands;
        # its own protection keeps no fine cell, so it blends nothing in.
        assert first.adaptive_regions
        assert not any(
            region.grid.scientifically_available
            for region in first.adaptive_regions
        )
    else:
        assert first.coarse_protected_pixel_count > 0
        assert first.adaptive_regions
        yy, xx = np.mgrid[:80, :80]
        assert config.adaptive is not None
        guard = max(config.adaptive.grid.window_shape_yx) // 2
        source_free = (yy - 40) ** 2 + (xx - 40) ** 2 > guard**2
        assert first.coarse_protected_pixel_count == np.count_nonzero(
            ~source_free
        )
        geometry = first.coarse.geometry
        height, width = geometry.effective_window_shape_yx
        expected = np.array(
            [
                [
                    np.median(
                        noise[y : y + height, x : x + width][
                            source_free[y : y + height, x : x + width]
                        ]
                    )
                    for x in geometry.window_starts_x
                ]
                for y in geometry.window_starts_y
            ]
        )
        np.testing.assert_array_equal(first.coarse.background, expected)
        np.testing.assert_allclose(first.coarse.rms, 1, atol=0.02)


@pytest.mark.parametrize("has_source", (False, True))
def test_coarse_protection_does_not_require_a_bright_adaptive_candidate(
    has_source: bool,
) -> None:
    """Protect ordinary emission without inventing support in empty noise."""
    yy, xx = np.mgrid[:80, :80]
    noise = np.tile(np.array([-1.0, 1.0]), 80 * 40).reshape(80, 80)
    image = noise.copy()
    if has_source:
        image += 25 * np.exp(-0.5 * ((yy - 40) ** 2 + (xx - 40) ** 2) / 5**2)
    config = replace(
        _source_protection_config(), maximum_constant_map_pixels=6400
    )
    coarse = estimate_background_rms_grids(
        _ArrayImageSource(noise),
        noise.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    result = refine_background_rms_grids(
        _ArrayImageSource(image),
        coarse,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
        source_protection_island_threshold_sigma=3.0,
        multiscale_protection=MultiscaleSourceProtection(
            BeamShapePixels(4.0, 3.0, 0.0),
            SourceFinderConfig(5.0, 3.0, 7),
            0.5,
        ),
        protect_coarse_source_support=True,
    )
    assert (result.coarse_protected_pixel_count > 0) is has_source
    assert result.coarse.scientifically_available
    assert result.adaptive_regions == ()
    if not has_source:
        np.testing.assert_array_equal(
            result.coarse.background, coarse.coarse.background
        )
        np.testing.assert_array_equal(result.coarse.rms, coarse.coarse.rms)
