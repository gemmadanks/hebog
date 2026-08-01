"""Bounded source and executor orchestration for background estimation."""

from __future__ import annotations

from functools import partial
from typing import Protocol

import numpy as np

from hebog.algorithms.background import (
    RmsGridBatchStatistics,
    RmsGridGeometry,
    RmsGridStatistics,
    RmsWindowBatch,
    assemble_rms_grid_statistics,
    estimate_rms_grid_batch,
    plan_rms_window_batches,
)
from hebog.config import RmsWindowStatisticsConfig
from hebog.data_models.partitioning import ImageBounds
from hebog.executors.base import Executor
from hebog.io.base import ImageWindow


class _WindowReadable(Protocol):
    """Read bounded global image windows without requiring metadata access."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


def _estimate_source_batch(
    batch: RmsWindowBatch,
    *,
    source: _WindowReadable,
    grid: RmsGridGeometry,
    config: RmsWindowStatisticsConfig,
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
        config,
    )


def estimate_rms_grid(
    source: _WindowReadable,
    grid: RmsGridGeometry,
    config: RmsWindowStatisticsConfig,
    executor: Executor,
    *,
    maximum_batch_cells: int,
) -> RmsGridStatistics:
    """Estimate one complete coarse grid through bounded executor batches."""
    batches = plan_rms_window_batches(
        grid,
        maximum_cells=maximum_batch_cells,
    )
    estimate_batch = partial(
        _estimate_source_batch,
        source=source,
        grid=grid,
        config=config,
    )
    results = executor.map_batches(estimate_batch, batches)
    return assemble_rms_grid_statistics(grid, results)
