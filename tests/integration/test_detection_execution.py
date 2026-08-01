"""Serial, Dask, retry, partition, and Zarr compact-detection contracts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
from distributed import Client

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)
from hebog.data_models import ImageBounds, PartitionManifest
from hebog.executors import DaskExecutor, SerialExecutor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.stages.detection import (
    DetectionStageConfig,
    DetectionStageResult,
    run_detection_stage,
)

pytestmark = pytest.mark.integration


class _ArrayImageSource:
    """Pickleable bounded image source for local executor tests."""

    def __init__(self, values: npt.NDArray[np.float64]) -> None:
        self._values = np.asarray(values, dtype=np.float64)

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return one owned, aligned scientific window."""
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
    """Return a small bounded RMS policy."""
    return RmsGridConfig(
        window_shape_yx=(window, window),
        step_yx=(step, step),
        statistics=RmsWindowStatisticsConfig(3.0, 8, 6),
        maximum_batch_cells=8,
    )


def _background_config() -> BackgroundRmsConfig:
    """Return explicit coarse, candidate, and adaptive policies."""
    return BackgroundRmsConfig(
        coarse=_grid(7, 3),
        adaptive=AdaptiveRmsConfig(
            grid=_grid(5, 2),
            candidate_threshold_sigma=20.0,
            influence_radius_pixels=6.0,
            transition_width_pixels=2.0,
        ),
        maximum_spatial_window_fraction=0.3,
        maximum_constant_map_pixels=4096,
    )


def _source_finder_config() -> SourceFinderConfig:
    """Return explicit compact source thresholds and size policy."""
    return SourceFinderConfig(
        detection_threshold_sigma=5.0,
        island_threshold_sigma=3.0,
        minimum_island_pixels=2,
    )


def _image() -> npt.NDArray[np.float64]:
    """Return compact emission spanning a four-tile corner and one blend."""
    y, x = np.indices((24, 28))
    image = np.where((x + y) % 2 == 0, -1.0, 1.0).astype(np.float64)
    image[11, 13] = 40.0
    image[12, 14] = 50.0
    image[4, 4] = 9.0
    image[4, 5] = 4.0
    return image


def _run(
    root: Path,
    manifest: PartitionManifest,
    executor: SerialExecutor | DaskExecutor,
) -> tuple[DetectionStageResult, ZarrProductSink]:
    """Run one generation against the shared analytic image."""
    sink = ZarrProductSink(root, manifest, generation_id="phase-3-test")
    result = run_detection_stage(
        _ArrayImageSource(_image()),
        manifest,
        DetectionStageConfig(
            background_rms=_background_config(),
            source_finder=_source_finder_config(),
        ),
        executor,
        sink,
    )
    return result, sink


def _read_plane(
    sink: ZarrProductSink,
    result: DetectionStageResult,
    product_name: str,
) -> npt.NDArray[np.generic]:
    """Assemble one small test plane from validated generation chunks."""
    dtype = np.dtype(
        next(
            chunk.dtype
            for chunk in result.generation.chunks
            if chunk.product_name == product_name
        )
    )
    values = np.empty(sink.manifest.image_shape_yx, dtype=dtype)
    for chunk in result.generation.chunks:
        if chunk.product_name != product_name:
            continue
        bounds = chunk.core_bounds
        values[
            bounds.y_start : bounds.y_stop,
            bounds.x_start : bounds.x_stop,
        ] = sink.read_chunk(chunk)
    return values


def test_one_and_many_tile_detection_publish_identical_topology(
    tmp_path: Path,
) -> None:
    """Storage partitioning does not alter candidates, islands, or masks."""
    one_tile = plan_image_partitions(
        image_shape_yx=_image().shape,
        tile_core_shape_yx=(32, 32),
        halo_yx=(0, 0),
    )
    many_tiles = plan_image_partitions(
        image_shape_yx=_image().shape,
        tile_core_shape_yx=(12, 14),
        halo_yx=(0, 0),
    )

    one_result, one_sink = _run(
        tmp_path / "one.zarr",
        one_tile,
        SerialExecutor(),
    )
    many_result, many_sink = _run(
        tmp_path / "many.zarr",
        many_tiles,
        SerialExecutor(),
    )

    assert many_result.adaptive_candidate_positions_yx == ((12.0, 14.0),)
    assert many_result.adaptive_candidate_positions_yx == (
        one_result.adaptive_candidate_positions_yx
    )
    assert many_result.islands == one_result.islands
    np.testing.assert_array_equal(
        _read_plane(many_sink, many_result, "source-filtering-mask"),
        _read_plane(one_sink, one_result, "source-filtering-mask"),
    )
    assert many_result.boundary_label_count < 4 * _image().size
    assert many_result.reconciliation_round_count == 2
    assert many_result.separate_candidate_scan
    assert many_result.generation.product_names == (
        "background",
        "rms",
        "source-filtering-mask",
    )


def test_identical_stage_retry_reuses_the_published_generation(
    tmp_path: Path,
) -> None:
    """A complete deterministic retry accepts existing identical chunks."""
    manifest = plan_image_partitions(
        image_shape_yx=_image().shape,
        tile_core_shape_yx=(12, 14),
        halo_yx=(0, 0),
    )
    first, sink = _run(tmp_path / "retry.zarr", manifest, SerialExecutor())

    second = run_detection_stage(
        _ArrayImageSource(_image()),
        manifest,
        DetectionStageConfig(
            background_rms=_background_config(),
            source_finder=_source_finder_config(),
        ),
        SerialExecutor(),
        sink,
    )

    assert second.generation == first.generation
    assert second.islands == first.islands


def test_dask_and_serial_detection_products_are_identical(
    tmp_path: Path,
) -> None:
    """Executor scheduling cannot change compact topology or product values."""
    manifest = plan_image_partitions(
        image_shape_yx=_image().shape,
        tile_core_shape_yx=(12, 14),
        halo_yx=(0, 0),
    )
    serial, serial_sink = _run(
        tmp_path / "serial.zarr",
        manifest,
        SerialExecutor(),
    )

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        dask, dask_sink = _run(
            tmp_path / "dask.zarr",
            manifest,
            DaskExecutor(client),
        )

    assert dask.islands == serial.islands
    assert (
        dask.adaptive_candidate_positions_yx
        == serial.adaptive_candidate_positions_yx
    )
    for product_name in dask.generation.product_names:
        np.testing.assert_array_equal(
            _read_plane(dask_sink, dask, product_name),
            _read_plane(serial_sink, serial, product_name),
        )
