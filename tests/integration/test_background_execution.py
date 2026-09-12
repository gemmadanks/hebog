"""Dask conformance tests for bounded background/RMS stages."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import replace
from functools import partial

import numpy as np
import pytest
from distributed import Client

from hebog.algorithms.component_measurement import (
    _persistent_measurement_support,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    build_residual_atrous_plan,
    build_scale_filter_bank,
    evaluate_scale_filter_bank,
    prepare_scale_filter_inputs,
)
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)
from hebog.data_models import ImageBounds
from hebog.executors import DaskExecutor, Executor, SerialExecutor
from hebog.io.base import ImageWindow
from hebog.stages.background import (
    BackgroundRmsGrids,
    MultiscaleSourceProtection,
    estimate_background_rms_grids,
    estimate_background_rms_tile,
    prepare_background_rms_tile_request,
    refine_background_rms_grids,
)

pytestmark = pytest.mark.integration


def test_filtered_response_support_is_serial_dask_retry_invariant() -> None:
    """A negative central depression does not alter executor semantics."""
    yy, xx = np.mgrid[:65, :73]
    image = 15 * np.exp(-((yy - 32) ** 2 + (xx - 36) ** 2) / 128)
    image[31:34, 35:38] = -1
    image[32, 36] = np.nan
    beam = BeamShapePixels(4, 3, 20)
    evaluate = partial(
        _persistent_measurement_support,
        rms=1 + xx / 73,
        valid=np.isfinite(image),
        plan=build_residual_atrous_plan(beam, noise_correlation=beam),
        minimum_support_fraction=0.5,
        detection_sigma=5,
        island_sigma=3,
        minimum_pixels=7,
    )
    serial = SerialExecutor().map_batches(evaluate, (image, image * 2))
    assert serial[0][31, 35] and not serial[0][32, 36]
    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        results = DaskExecutor(client).map_batches(
            evaluate,
            (image * 2, image, image),
        )
    for reference, actual in zip(
        (serial[1], serial[0], serial[0]), results, strict=True
    ):
        np.testing.assert_array_equal(reference, actual)


def test_near_noiseless_filter_is_exact_with_existing_dask() -> None:
    """The precision fallback is deterministic under caller-owned workers."""
    image = np.zeros((73, 79))
    image[36, 39] = 1
    image[33, 36] = np.nan
    prepared = prepare_scale_filter_inputs(
        image,
        np.isfinite(image),
        np.zeros_like(image),
        np.full_like(image, 1e-60),
    )
    bank = build_scale_filter_bank(
        BeamShapePixels(5, 3.5, 20),
        family="beam-aware-matched-filter",
        scales=((1, 1.0), (2, 2.0)),
    )
    evaluate = partial(
        evaluate_scale_filter_bank,
        filter_bank=bank,
        minimum_support_fraction=0.5,
    )
    serial = evaluate(prepared)
    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        results = DaskExecutor(client).map_batches(evaluate, (prepared,) * 2)
    for result in results:
        for reference, actual in zip(
            serial.responses, result.responses, strict=True
        ):
            np.testing.assert_array_equal(
                reference.response_jy_per_beam, actual.response_jy_per_beam
            )
            np.testing.assert_array_equal(
                reference.effective_rms_jy_per_beam,
                actual.effective_rms_jy_per_beam,
            )
            np.testing.assert_array_equal(
                reference.scientifically_valid, actual.scientifically_valid
            )


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


@pytest.mark.parametrize("noisy_neighbour", (False, True))
@pytest.mark.parametrize("local_noise", (False, True))
def test_zero_noise_region_admission_matches_existing_dask(
    noisy_neighbour: bool, local_noise: bool
) -> None:
    """Discard obsolete work, not independent noise estimates or regions."""
    yy, xx = np.mgrid[:128, :128]
    noise = np.where((yy + xx) % 2, -1.0, 1.0) * ((xx > 64) & noisy_neighbour)
    config = replace(_config(), maximum_constant_map_pixels=noise.size)
    coarse = estimate_background_rms_grids(
        _ArrayImageSource(noise),
        noise.shape,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    image = noise.copy()
    image[20, 20] += 100
    image[100, 100] += 100
    source = _ArrayImageSource(image)
    refine = partial(
        refine_background_rms_grids,
        source,
        coarse,
        config,
        bright_candidate_positions_yx=((20.0, 20.0), (100.0, 100.0)),
        source_protection_island_threshold_sigma=3.0,
        multiscale_protection=MultiscaleSourceProtection(
            BeamShapePixels(2, 1.5, 20), SourceFinderConfig(5, 3, 7), 0.5
        ),
        refine_local_noise=local_noise,
    )
    serial = refine(SerialExecutor())
    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        dask = refine(DaskExecutor(client))
    assert (
        len(serial.adaptive_regions)
        == len(dask.adaptive_regions)
        == (1 if noisy_neighbour else 0)
    )
    for actual in (serial, dask):
        assert actual.coarse is coarse.coarse
        if noisy_neighbour:
            assert actual.adaptive_regions[
                0
            ].bright_candidate_positions_yx == ((100.0, 100.0),)
    if local_noise:
        assert serial.local_noise is not None and dask.local_noise is not None
        np.testing.assert_array_equal(
            serial.local_noise.rms, dask.local_noise.rms
        )
        np.testing.assert_array_equal(
            serial.local_noise.fallback_cells, dask.local_noise.fallback_cells
        )
    if noisy_neighbour:
        np.testing.assert_array_equal(
            serial.adaptive_regions[0].grid.rms,
            dask.adaptive_regions[0].grid.rms,
        )


@pytest.mark.parametrize(
    ("multiscale", "local_noise"),
    ((False, False), (True, False), (True, True)),
)
@pytest.mark.parametrize("protect_coarse", (False, True))
def test_dask_and_serial_background_stages_are_equivalent(
    multiscale: bool,
    protect_coarse: bool,
    local_noise: bool,
) -> None:
    """Executor choice does not alter grids or owned tile outputs."""
    y, x = np.indices((40, 44), dtype=np.float64)
    image = 1.0 + 0.01 * y + np.where((x + y) % 2 == 0, -1.0, 1.0)
    image[15:26, 17:28] *= 4.0
    image[20, 22] = 50.0
    positions = ((20.0, 22.0),)
    source = _ArrayImageSource(image)
    config = _config()
    protection = (
        MultiscaleSourceProtection(
            BeamShapePixels(2.0, 1.5, 20.0),
            SourceFinderConfig(5.0, 3.0, 7),
            0.5,
        )
        if multiscale
        else None
    )

    def grids_for_executor(executor: Executor) -> BackgroundRmsGrids:
        coarse = estimate_background_rms_grids(
            source,
            image.shape,
            config,
            executor,
            bright_candidate_positions_yx=(),
        )
        return refine_background_rms_grids(
            source,
            coarse,
            config,
            executor,
            bright_candidate_positions_yx=positions,
            source_protection_island_threshold_sigma=3.0,
            multiscale_protection=protection,
            protect_coarse_source_support=protect_coarse,
            refine_local_noise=local_noise,
        )

    serial_grids = grids_for_executor(SerialExecutor())
    assert (serial_grids.coarse_protected_pixel_count > 0) == protect_coarse

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        dask_executor = DaskExecutor(client)
        dask_grids = grids_for_executor(dask_executor)
        assert (
            dask_grids.coarse_protected_pixel_count
            == serial_grids.coarse_protected_pixel_count
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
    if local_noise:
        assert serial_grids.local_noise is not None
        assert dask_grids.local_noise is not None
        np.testing.assert_array_equal(
            serial_grids.local_noise.rms, dask_grids.local_noise.rms
        )
        np.testing.assert_array_equal(
            serial_grids.local_noise.fallback_cells,
            dask_grids.local_noise.fallback_cells,
        )
        assert (
            serial_grids.local_noise_protected_window_count
            == dask_grids.local_noise_protected_window_count
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
