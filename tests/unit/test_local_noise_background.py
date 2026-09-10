"""Bounded local-noise ownership, unavailable cells and retry contracts."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import TypeVar

import numpy as np
import pytest

from hebog.algorithms.background import PreparedRmsGrid
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)
from hebog.data_models import ImageBounds
from hebog.executors import SerialExecutor
from hebog.io.base import ImageWindow
from hebog.stages.background import (
    MultiscaleSourceProtection,
    _connected_source_protection,
    _estimate_local_noise_grid,
    estimate_background_rms_grids,
    estimate_background_rms_tile,
    prepare_background_rms_tile_request,
    refine_background_rms_grids,
)

Input = TypeVar("Input")
Output = TypeVar("Output")


class _Source:
    """Serve bounded synthetic windows while recording read admission."""

    def __init__(self, image: np.ndarray) -> None:
        self.image = image
        self.bounds: list[ImageBounds] = []

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        self.bounds.append(bounds)
        values = self.image[
            bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
        ].copy()
        return ImageWindow(bounds, values, np.isfinite(values))


class _ReverseRetryExecutor:
    """Reorder completed blocks and repeat one without duplicating results."""

    def map_batches(
        self, function: Callable[[Input], Output], batches: Iterable[Input]
    ) -> list[Output]:
        inputs = list(batches)
        if inputs:
            function(inputs[0])
        return [function(item) for item in reversed(inputs)]


def _config(batch_cells: int = 8) -> BackgroundRmsConfig:
    """Use small fixed scientific windows with variable execution batching."""

    def grid(window: int, step: int) -> RmsGridConfig:
        return RmsGridConfig(
            (window, window),
            (step, step),
            RmsWindowStatisticsConfig(3.0, 10, 6),
            batch_cells,
        )

    return BackgroundRmsConfig(
        coarse=grid(32, 10),
        adaptive=AdaptiveRmsConfig(grid(11, 3), 75.0, 30.0, 10.0),
        maximum_spatial_window_fraction=1,
        maximum_constant_map_pixels=1_000_000,
    )


def _policy() -> MultiscaleSourceProtection:
    return MultiscaleSourceProtection(
        BeamShapePixels(2, 2, 0), SourceFinderConfig(5, 3, 7), 0.5
    )


@pytest.mark.parametrize(
    "defect", ("adaptive", "protection", "threshold", "mismatch")
)
def test_missing_local_noise_policy_fails_before_any_read(defect: str) -> None:
    source = _Source(np.ones((40, 44)))
    config = _config()
    coarse = estimate_background_rms_grids(
        source,
        source.image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    count = len(source.bounds)
    with pytest.raises(ValueError, match="local noise"):
        refine_background_rms_grids(
            source,
            coarse,
            replace(config, adaptive=None) if defect == "adaptive" else config,
            SerialExecutor(),
            bright_candidate_positions_yx=(),
            source_protection_island_threshold_sigma=(
                None
                if defect == "threshold"
                else 2.5
                if defect == "mismatch"
                else 3
            ),
            multiscale_protection=None
            if defect == "protection"
            else _policy(),
            refine_local_noise=True,
        )
    assert len(source.bounds) == count


@pytest.mark.parametrize(
    "scene", ("source", "source-filled", "empty", "invalid", "constant")
)
def test_local_noise_keeps_raw_availability_and_coverage(scene: str) -> None:
    yy, xx = np.mgrid[:80, :96]
    noise = np.where((yy + xx) % 2, -1.0, 1.0)
    image = noise.copy()
    if scene == "source":
        image += 20 * np.exp(-0.5 * ((yy - 40) ** 2 + (xx - 48) ** 2) / 5**2)
        image[:8, :8] = np.nan
    elif scene == "invalid":
        image[:] = np.nan
    elif scene == "constant":
        image[:] = 100
    elif scene == "source-filled":
        image += 100
    config = _config()
    coarse = estimate_background_rms_grids(
        _Source(noise),
        noise.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    grids = refine_background_rms_grids(
        _Source(image),
        coarse,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
        source_protection_island_threshold_sigma=3,
        multiscale_protection=_policy(),
        refine_local_noise=True,
    )
    assert grids.coarse is coarse.coarse
    assert not grids.adaptive_regions
    assert grids.local_noise is not None
    assert grids.local_noise.scientifically_available == (
        scene in ("source", "empty", "constant")
    )
    assert (grids.local_noise_protected_window_count > 0) == (
        scene in ("source", "source-filled")
    )
    if scene == "source":
        assert grids.local_noise.fallback_cell_count > 0
    manifest = plan_image_partitions(
        image_shape_yx=image.shape,
        tile_core_shape_yx=image.shape,
        halo_yx=(0, 0),
    )
    tile = estimate_background_rms_tile(
        _Source(image),
        prepare_background_rms_tile_request(manifest.tiles[0], grids, config),
    )
    if scene in ("invalid", "source-filled"):
        assert not tile.scientifically_available
        assert np.isnan(tile.rms).all()
    elif scene == "constant":
        # A zero-variance statistic is defined; normalize_residual separately
        # rejects zero RMS for source detection. Do not fabricate noise.
        np.testing.assert_array_equal(tile.rms, 0)
    else:
        np.testing.assert_allclose(tile.rms[np.isfinite(image)], 1, atol=0.02)
        assert np.isnan(tile.rms[~np.isfinite(image)]).all()
    with pytest.raises(ValueError, match="coarse-only"):
        refine_background_rms_grids(
            _Source(image),
            grids,
            config,
            SerialExecutor(),
            bright_candidate_positions_yx=(),
            refine_local_noise=True,
        )


def test_local_noise_contexts_are_bounded_and_execution_invariant() -> None:
    yy, xx = np.mgrid[:320, :384]
    image = np.where((yy + xx) % 2, -1.0, 1.0) * np.where(xx < 160, 1, 2)
    image += 20 * np.exp(-0.5 * ((yy - 100) ** 2 + (xx - 200) ** 2) / 5**2)
    results: list[PreparedRmsGrid] = []
    for cells, executor in (
        (7, SerialExecutor()),
        (19, _ReverseRetryExecutor()),
    ):
        config = _config(cells)
        source = _Source(image)
        coarse = estimate_background_rms_grids(
            source,
            image.shape,
            config,
            executor,
            bright_candidate_positions_yx=(),
        )
        grids = refine_background_rms_grids(
            source,
            coarse,
            config,
            executor,
            bright_candidate_positions_yx=(),
            source_protection_island_threshold_sigma=3,
            multiscale_protection=_policy(),
            refine_local_noise=True,
        )
        assert grids.local_noise is not None
        results.append(grids.local_noise)
        # Neither pilot nor protection reads a complete image; filter/context
        # halos are bounded by the scientific window sizes, not image size.
        assert max(max(bounds.shape_yx) for bounds in source.bounds) < min(
            image.shape
        )
    np.testing.assert_array_equal(results[0].rms, results[1].rms)
    np.testing.assert_array_equal(
        results[0].fallback_cells, results[1].fallback_cells
    )


def test_truncated_noise_protection_context_retains_boundary_support() -> None:
    residual = np.zeros((20, 24))
    residual[0:12, 4:6] = 4
    residual[12:15, 17:20] = 4
    actual = _connected_source_protection(
        residual,
        np.ones(residual.shape, dtype=np.bool_),
        ImageBounds(100, 120, 200, 224),
        (),
        island_threshold_sigma=3,
        source_finder=SourceFinderConfig(5, 3, 7),
        protect_context_boundary=True,
        image_shape_yx=(200, 300),
    )
    expected = np.zeros(residual.shape, dtype=np.bool_)
    expected[:12, 4:6] = True
    np.testing.assert_array_equal(actual, expected)


def test_observed_image_edge_is_not_a_truncated_source_seed_search() -> None:
    """Sub-threshold noise is not a source merely for touching the edge."""
    residual = np.zeros((20, 24))
    residual[:12, 4:6] = 4
    actual = _connected_source_protection(
        residual,
        np.ones(residual.shape, dtype=np.bool_),
        ImageBounds(0, 20, 0, 24),
        (),
        island_threshold_sigma=3,
        source_finder=SourceFinderConfig(5, 3, 7),
        protect_context_boundary=True,
        image_shape_yx=residual.shape,
    )
    assert not actual.any()
    with pytest.raises(ValueError, match="full image shape"):
        _connected_source_protection(
            residual,
            np.ones(residual.shape, dtype=np.bool_),
            ImageBounds(0, 20, 0, 24),
            (),
            island_threshold_sigma=3,
            protect_context_boundary=True,
        )


def test_oversize_noise_context_is_rejected_before_region_reads() -> None:
    source = _Source(np.ones((80, 96)))
    config = _config()
    coarse = estimate_background_rms_grids(
        source,
        source.image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    count = len(source.bounds)
    with pytest.raises(ValueError, match=r"local noise context.*bounded read"):
        _estimate_local_noise_grid(
            source,
            coarse.coarse,
            coarse.coarse,
            replace(config, maximum_constant_map_pixels=100),
            SerialExecutor(),
            policy=_policy(),
        )
    assert len(source.bounds) == count


def test_coarse_bright_candidate_can_be_noise_under_the_fine_pilot() -> None:
    """Corrected noise attribution is not a malformed source candidate."""
    yy, xx = np.mgrid[:80, :96]
    image = np.where((yy + xx) % 2, -1.0, 1.0)
    image[25:45, 39:59] *= 100
    config = _config()
    config = replace(
        config,
        coarse=replace(
            config.coarse, window_shape_yx=(64, 64), step_yx=(32, 32)
        ),
    )
    source = _Source(image)
    coarse = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    assert np.max(coarse.coarse.rms) < 100 / 75
    refined = refine_background_rms_grids(
        source,
        coarse,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=((32, 48),),
        source_protection_island_threshold_sigma=3,
        multiscale_protection=_policy(),
        protect_coarse_source_support=True,
        refine_local_noise=True,
    )
    assert refined.local_noise is not None
    assert refined.local_noise.scientifically_available
    assert np.max(refined.local_noise.rms) > 50
