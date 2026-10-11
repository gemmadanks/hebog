"""Bright-region refinement reads bounded contexts however candidates chain."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from math import prod
from typing import TypeVar

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)
from hebog.data_models import ImageBounds
from hebog.executors import Executor, SerialExecutor, TaskRequirement
from hebog.io.base import ImageWindow
from hebog.stages import background as background_stage
from hebog.stages.background import (
    BackgroundRmsGrids,
    MultiscaleSourceProtection,
    estimate_background_rms_grids,
    refine_background_rms_grids,
)

Input = TypeVar("Input")
Output = TypeVar("Output")


class _Source:
    """Serve bounded synthetic windows while recording every read."""

    def __init__(self, image: npt.NDArray[np.float64]) -> None:
        self.image = image
        self.bounds: list[ImageBounds] = []

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        self.bounds.append(bounds)
        values = self.image[
            bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
        ].copy()
        return ImageWindow(bounds, values, np.isfinite(values))


class _ReverseRetryExecutor(SerialExecutor):
    """Reorder completed blocks and repeat one without duplicating results."""

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[Output]:
        """Retry the first block, then complete the rest in reverse."""
        inputs = list(batches)
        if inputs:
            super().map_batches(function, inputs[:1])
        return list(
            reversed(
                super().map_batches(
                    function, list(reversed(inputs)), requirement=requirement
                )
            )
        )


def _config() -> BackgroundRmsConfig:
    """Use small scientific windows so a lattice chains on a small image."""

    def grid(window: int, step: int) -> RmsGridConfig:
        return RmsGridConfig(
            (window, window),
            (step, step),
            RmsWindowStatisticsConfig(3.0, 10, 6),
            8,
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


def _lattice(
    shape_yx: tuple[int, int] = (384, 448), spacing: int = 48
) -> tuple[npt.NDArray[np.float64], tuple[tuple[float, float], ...]]:
    """Return bright compact sources close enough for their regions to chain.

    Each candidate's influence box is 67 pixels wide under ``_config``, so
    sources 48 pixels apart merge into one region spanning the image.
    """
    yy, xx = np.mgrid[: shape_yx[0], : shape_yx[1]]
    image = np.where((yy + xx) % 2, -1.0, 1.0)
    positions = tuple(
        (float(y), float(x))
        for y in range(spacing // 2, shape_yx[0], spacing)
        for x in range(spacing // 2, shape_yx[1], spacing)
    )
    for y, x in positions:
        image += 400.0 * np.exp(-0.5 * ((yy - y) ** 2 + (xx - x) ** 2) / 4.0)
    return image, positions


def _refined(
    image: npt.NDArray[np.float64],
    positions: tuple[tuple[float, float], ...],
    *,
    config: BackgroundRmsConfig,
    executor: Executor,
) -> tuple[BackgroundRmsGrids, list[ImageBounds]]:
    """Refine around the candidates and return the reads refinement made."""
    source = _Source(image)
    coarse = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        executor,
        bright_candidate_positions_yx=(),
    )
    source.bounds.clear()
    grids = refine_background_rms_grids(
        source,
        coarse,
        config,
        executor,
        bright_candidate_positions_yx=positions,
        source_protection_island_threshold_sigma=3.0,
        multiscale_protection=_policy(),
    )
    return grids, source.bounds


def test_a_chained_bright_region_is_read_in_bounded_contexts() -> None:
    """Given candidates that chain across the image, no task reads it whole.

    The region's fine cells are estimated in blocks, each read with the
    same context the local-noise blocks read, so the largest read is set by
    the scientific windows and the beam rather than by how far the
    candidates chain. The estimate reports that largest read.
    """
    image, positions = _lattice()

    grids, reads = _refined(
        image, positions, config=_config(), executor=SerialExecutor()
    )

    (region,) = grids.adaptive_regions
    assert len(region.bright_candidate_positions_yx) == len(positions)
    assert len(reads) > 1
    largest = max(prod(bounds.shape_yx) for bounds in reads)
    assert largest < image.size / 2
    assert grids.largest_bright_region_read_pixels == largest


@pytest.mark.parametrize(
    "executor", (SerialExecutor(), _ReverseRetryExecutor())
)
def test_a_bright_region_does_not_depend_on_its_blocks(
    monkeypatch: pytest.MonkeyPatch, executor: Executor
) -> None:
    """Given the same lattice, small and whole-region blocks agree exactly.

    Sources straddle block sides, so this holds only if emission a side
    cuts off from its candidate is still protected.
    """
    image, positions = _lattice()
    config = _config()
    monkeypatch.setattr(background_stage, "_PROTECTED_CONTEXT_CELLS", 64)
    blocked, blocked_reads = _refined(
        image, positions, config=config, executor=executor
    )
    monkeypatch.setattr(background_stage, "_PROTECTED_CONTEXT_CELLS", 10**6)
    whole, whole_reads = _refined(
        image, positions, config=config, executor=SerialExecutor()
    )

    assert len(whole_reads) == 1
    assert len(blocked_reads) > len(positions)
    assert blocked.adaptive_protected_window_count > 0
    assert (
        blocked.adaptive_protected_window_count
        == whole.adaptive_protected_window_count
    )
    assert (
        blocked.adaptive_protected_pixel_count
        == whole.adaptive_protected_pixel_count
    )
    for actual, expected in zip(
        blocked.adaptive_regions, whole.adaptive_regions, strict=True
    ):
        assert actual.grid.geometry == expected.grid.geometry
        np.testing.assert_array_equal(
            actual.grid.background, expected.grid.background
        )
        np.testing.assert_array_equal(actual.grid.rms, expected.grid.rms)
        np.testing.assert_array_equal(
            actual.grid.fallback_cells, expected.grid.fallback_cells
        )


def test_an_oversize_bright_context_is_refused_before_any_read() -> None:
    """A beam too wide for the admitted read stops the estimate unread."""
    image, positions = _lattice()
    config = _config()
    source = _Source(image)
    coarse = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    source.bounds.clear()

    with pytest.raises(
        ValueError, match=r"bright region context.*bounded read"
    ):
        refine_background_rms_grids(
            source,
            coarse,
            replace(config, maximum_constant_map_pixels=10_000),
            SerialExecutor(),
            bright_candidate_positions_yx=positions,
            source_protection_island_threshold_sigma=3.0,
            multiscale_protection=_policy(),
        )
    assert source.bounds == []


def test_no_bright_candidate_reads_nothing_for_refinement() -> None:
    """Without a candidate the estimate reports no bright-region read."""
    image, _ = _lattice()

    grids, reads = _refined(
        image, (), config=_config(), executor=SerialExecutor()
    )

    assert grids.adaptive_regions == ()
    assert reads == []
    assert grids.largest_bright_region_read_pixels == 0


def test_blocks_may_protect_more_than_one_read_of_the_region_never_less(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given emission no bright source reaches, blocks may protect it.

    A block cannot see past its read, so emission a side of it cuts off may
    belong to a bright source beyond: the block protects it, with the
    multiscale support joined to it. One read of the whole region sees that
    this filament reaches no candidate and keeps its windows. Blocks reject
    every window that read rejects, and the filament's too.
    """
    image, positions = _lattice()
    image[48:50, :] += 8.0
    config = _config()
    monkeypatch.setattr(background_stage, "_PROTECTED_CONTEXT_CELLS", 64)
    blocked, _ = _refined(
        image, positions, config=config, executor=SerialExecutor()
    )
    monkeypatch.setattr(background_stage, "_PROTECTED_CONTEXT_CELLS", 10**6)
    whole, _ = _refined(
        image, positions, config=config, executor=SerialExecutor()
    )

    (blocked_region,) = blocked.adaptive_regions
    (whole_region,) = whole.adaptive_regions
    blocked_rejects = blocked_region.grid.fallback_cells
    whole_rejects = whole_region.grid.fallback_cells
    filament = (
        np.abs(
            np.asarray(blocked_region.grid.geometry.sample_coordinates_y)
            - 48.5
        )
        <= 2
    )
    assert not np.any(whole_rejects & ~blocked_rejects)
    assert np.all(blocked_rejects[filament])
    assert not np.all(whole_rejects[filament])


def test_a_region_without_positive_coarse_noise_is_skipped_unread() -> None:
    """Given zero coarse noise around one candidate, only the other refines.

    Source protection can leave a defined zero-variance coarse estimate, in
    which an old candidate has no support in sigma, so its region is left
    unread rather than its emission re-estimated as noise.
    """
    yy, xx = np.mgrid[:80, :256]
    image = np.where((yy + xx) % 2, -1.0, 1.0)
    positions = ((40.0, 30.0), (40.0, 220.0))
    for y, x in positions:
        image[int(y), int(x)] += 100.0
    config = _config()
    source = _Source(image)
    coarse = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    rms = np.array(coarse.coarse.rms)
    rms[:, np.asarray(coarse.coarse.geometry.sample_coordinates_x) < 128] = 0
    coarse = replace(coarse, coarse=replace(coarse.coarse, rms=rms))
    source.bounds.clear()

    refined = refine_background_rms_grids(
        source,
        coarse,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=positions,
        source_protection_island_threshold_sigma=3.0,
        multiscale_protection=_policy(),
    )

    (region,) = refined.adaptive_regions
    assert region.bright_candidate_positions_yx == (positions[1],)
    assert source.bounds
    assert all(bounds.x_start > 128 for bounds in source.bounds)
