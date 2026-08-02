"""Dask conformance tests for bounded background/RMS stages."""

from __future__ import annotations

from functools import partial

import numpy as np
import pytest
from distributed import Client

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
)
from hebog.data_models import ImageBounds
from hebog.executors import DaskExecutor, SerialExecutor
from hebog.io.base import ImageWindow
from hebog.stages.background import (
    estimate_background_rms_grids,
    estimate_background_rms_tile,
    prepare_background_rms_tile_request,
)

pytestmark = pytest.mark.integration


class _ArrayImageSource:
    """Pickleable bounded source for executor conformance."""

    def __init__(self, values: np.ndarray) -> None:
        self._values = np.asarray(values, dtype=np.float64)

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return one owned bounded input window."""
        selection = (
            slice(bounds.y_start, bounds.y_stop),
            slice(bounds.x_start, bounds.x_stop),
        )
        values = np.array(self._values[selection], copy=True)
        return ImageWindow(
            bounds=bounds,
            values=values,
            valid_pixels=np.isfinite(values),
        )


def _grid(window: int, step: int) -> RmsGridConfig:
    """Return one explicit bounded grid policy."""
    return RmsGridConfig(
        window_shape_yx=(window, window),
        step_yx=(step, step),
        statistics=RmsWindowStatisticsConfig(3.0, 10, 6),
        maximum_batch_cells=6,
    )


def _config() -> BackgroundRmsConfig:
    """Return coarse and adaptive policies for executor conformance."""
    return BackgroundRmsConfig(
        coarse=_grid(9, 4),
        adaptive=AdaptiveRmsConfig(
            grid=_grid(5, 2),
            candidate_threshold_sigma=20.0,
            influence_radius_pixels=7.0,
            transition_width_pixels=3.0,
        ),
        maximum_spatial_window_fraction=0.25,
        maximum_constant_map_pixels=4096,
    )


def test_dask_and_serial_background_stages_are_equivalent() -> None:
    """Executor choice does not alter grids or owned tile outputs."""
    y, x = np.indices((40, 44), dtype=np.float64)
    image = 1.0 + 0.01 * y + np.where((x + y) % 2 == 0, -1.0, 1.0)
    image[15:26, 17:28] *= 4.0
    positions = ((20.0, 22.0),)
    source = _ArrayImageSource(image)
    config = _config()
    serial_grids = estimate_background_rms_grids(
        source,
        image.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=positions,
    )

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        dask_executor = DaskExecutor(client)
        dask_grids = estimate_background_rms_grids(
            source,
            image.shape,
            config,
            dask_executor,
            bright_candidate_positions_yx=positions,
        )
        manifest = plan_image_partitions(
            image_shape_yx=image.shape,
            tile_core_shape_yx=(20, 22),
            halo_yx=(0, 0),
        )
        serial_requests = tuple(
            prepare_background_rms_tile_request(
                tile,
                serial_grids,
                config,
            )
            for tile in manifest.tiles
        )
        dask_requests = tuple(
            prepare_background_rms_tile_request(
                tile,
                dask_grids,
                config,
            )
            for tile in manifest.tiles
        )
        estimate_tile = partial(estimate_background_rms_tile, source)
        serial_tiles = SerialExecutor().map_batches(
            estimate_tile,
            serial_requests,
        )
        dask_tiles = dask_executor.map_batches(
            estimate_tile,
            dask_requests,
        )

    np.testing.assert_array_equal(
        dask_grids.coarse.background,
        serial_grids.coarse.background,
    )
    np.testing.assert_array_equal(
        dask_grids.coarse.rms, serial_grids.coarse.rms
    )
    assert len(dask_grids.adaptive_regions) == 1
    assert len(serial_grids.adaptive_regions) == 1
    np.testing.assert_array_equal(
        dask_grids.adaptive_regions[0].grid.rms,
        serial_grids.adaptive_regions[0].grid.rms,
    )
    for serial_tile, dask_tile in zip(serial_tiles, dask_tiles, strict=True):
        assert dask_tile.bounds == serial_tile.bounds
        np.testing.assert_array_equal(
            dask_tile.background,
            serial_tile.background,
        )
        np.testing.assert_array_equal(dask_tile.rms, serial_tile.rms)
