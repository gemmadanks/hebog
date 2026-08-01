"""Tests for sparse adaptive background/RMS refinement."""

from __future__ import annotations

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
                influence_radius_pixels=7.0,
                transition_width_pixels=3.0,
            )
            if adaptive
            else None
        ),
        maximum_spatial_window_fraction=0.25,
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
                influence_radius_pixels=0.0,
                transition_width_pixels=1.0,
            ),
            "influence_radius_pixels",
        ),
        (
            lambda: AdaptiveRmsConfig(
                grid=_grid((5, 5), (2, 2)),
                influence_radius_pixels=4.0,
                transition_width_pixels=5.0,
            ),
            "transition_width_pixels",
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
        )


def test_adaptive_refinement_raises_local_rms_only_near_candidate() -> None:
    """A noisy bright region uses fine RMS while distant pixels stay coarse."""
    y, x = np.indices((40, 44))
    image = np.where((x + y) % 2 == 0, -1.0, 1.0)
    image[15:26, 17:28] *= 5.0
    source = _ArrayImageSource(image)
    candidate = ((20.0, 22.0),)

    grids = estimate_background_rms_grids(
        source,
        image.shape,
        _config(),
        SerialExecutor(),
        bright_candidate_positions_yx=candidate,
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


def test_distant_candidates_keep_separate_bounded_fine_grids() -> None:
    """Adaptive summary memory scales with regions, not full image area."""
    image = np.tile(np.array([-1.0, 1.0]), 100 * 55).reshape(100, 110)
    positions = ((15.0, 16.0), (82.0, 91.0))
    config = _config()

    forward = estimate_background_rms_grids(
        _ArrayImageSource(image),
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=positions,
    )
    reverse = estimate_background_rms_grids(
        _ArrayImageSource(image),
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=tuple(reversed(positions)),
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
    positions = ((18.0, 19.0),)
    config = _config()
    source = _ArrayImageSource(image)
    grids = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=positions,
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
