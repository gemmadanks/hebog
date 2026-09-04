"""Tests for sparse adaptive background/RMS refinement."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

import numpy as np
import pytest

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
)
from hebog.data_models import ImageBounds, TilePartition
from hebog.executors import SerialExecutor
from hebog.io.base import ImageWindow
from hebog.stages.background import (
    BackgroundRmsGrids,
    estimate_background_rms_grids,
    estimate_background_rms_tile,
    prepare_background_rms_tile_request,
    refine_background_rms_grids,
)

Input = TypeVar("Input")
Output = TypeVar("Output")


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


class _RetryExecutor:
    """Repeat region work while returning one canonical ordered result."""

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
    ) -> list[Output]:
        """Inject one identical retry without changing returned evidence."""
        inputs = list(batches)
        results = [function(batch) for batch in inputs]
        if inputs:
            function(inputs[-1])
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
