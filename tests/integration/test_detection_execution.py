"""Serial, Dask, retry, partition, and Zarr compact-detection contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import pytest
from distributed import Client

from hebog.algorithms.deblending import (
    CompactDeblendResult,
    CompactIslandPixels,
    deblend_compact_island,
)
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    CompactDeblendConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)
from hebog.data_models import ImageBounds, PartitionManifest
from hebog.executors import DaskExecutor, SerialExecutor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.stages.deblending import run_compact_deblend_stage
from hebog.stages.detection import (
    DetectionStageConfig,
    DetectionStageResult,
    run_detection_from_coarse_grids,
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

    def read_windows(
        self,
        bounds_collection: tuple[ImageBounds, ...],
    ) -> tuple[ImageWindow, ...]:
        """Return ordered bounded windows through the batched source seam."""
        return tuple(self.read_window(bounds) for bounds in bounds_collection)


class _ReadOneImageSource:
    """Expose only the required single-window image-source protocol."""

    def __init__(self, values: npt.NDArray[np.float64]) -> None:
        self._delegate = _ArrayImageSource(values)

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return one bounded image window."""
        return self._delegate.read_window(bounds)


class _InvalidBatchImageSource(_ArrayImageSource):
    """Inject one deterministic invalid batched-window response."""

    def __init__(
        self,
        values: npt.NDArray[np.float64],
        failure: Literal["bounds", "shape", "validity"],
    ) -> None:
        super().__init__(values)
        self._failure = failure

    def read_windows(
        self,
        bounds_collection: tuple[ImageBounds, ...],
    ) -> tuple[ImageWindow, ...]:
        """Corrupt only the first response at the selected boundary."""
        windows = list(super().read_windows(bounds_collection))
        first = windows[0]
        if self._failure == "bounds":
            windows[0] = replace(
                first,
                bounds=ImageBounds(
                    first.bounds.y_start + 1,
                    first.bounds.y_stop + 1,
                    first.bounds.x_start,
                    first.bounds.x_stop,
                ),
            )
        elif self._failure == "shape":
            windows[0] = replace(
                first,
                values=first.values[:-1],
                valid_pixels=first.valid_pixels[:-1],
            )
        else:
            windows[0] = replace(
                first,
                valid_pixels=np.zeros(first.values.shape, dtype=np.bool_),
            )
        return tuple(windows)


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


def _deblend_config() -> CompactDeblendConfig:
    """Return bounded compact deblending policy for stage conformance."""
    return CompactDeblendConfig(
        minimum_peak_signal_to_noise=5.0,
        minimum_peak_separation_pixels=1,
        minimum_saddle_depth_sigma=2.0,
        maximum_compact_island_pixels=64,
        maximum_compact_bounds_pixels=128,
        maximum_batch_pixels=256,
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


def _deblend_results(
    sink: ZarrProductSink,
    result: DetectionStageResult,
) -> tuple[CompactDeblendResult, ...]:
    """Deblend small stage islands from exact generated products."""
    background = np.asarray(
        _read_plane(sink, result, "background"),
        dtype=np.float64,
    )
    rms = np.asarray(
        _read_plane(sink, result, "rms"),
        dtype=np.float64,
    )
    mask = _read_plane(sink, result, "source-filtering-mask").astype(np.bool_)
    normalized = np.asarray((_image() - background) / rms, dtype=np.float64)
    outputs: list[CompactDeblendResult] = []
    for island in result.islands:
        bounds = island.bounds
        selection = (
            slice(bounds.y_start, bounds.y_stop),
            slice(bounds.x_start, bounds.x_stop),
        )
        outputs.append(
            deblend_compact_island(
                CompactIslandPixels(
                    island=island,
                    normalized_residual=np.asarray(
                        normalized[selection],
                        dtype=np.float64,
                    ),
                    island_membership=np.asarray(mask[selection]),
                ),
                _deblend_config(),
            )
        )
    return tuple(outputs)


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
    one_deblended = _deblend_results(one_sink, one_result)
    many_deblended = _deblend_results(many_sink, many_result)
    assert tuple(item.regions for item in many_deblended) == tuple(
        item.regions for item in one_deblended
    )
    for many, one in zip(many_deblended, one_deblended, strict=True):
        np.testing.assert_array_equal(many.region_labels, one.region_labels)
    one_stage = run_compact_deblend_stage(
        _ArrayImageSource(_image()),
        one_result,
        _deblend_config(),
        SerialExecutor(),
        one_sink,
    )
    many_stage = run_compact_deblend_stage(
        _ArrayImageSource(_image()),
        many_result,
        _deblend_config(),
        SerialExecutor(),
        many_sink,
    )
    assert many_stage == one_stage
    assert many_stage.planned_batch_count == 1
    assert not any(
        hasattr(island, "region_labels") for island in many_stage.islands
    )
    assert many_result.boundary_label_count < 4 * _image().size
    assert many_result.reconciliation_round_count == 2
    assert many_result.separate_candidate_scan
    assert many_result.generation.product_names == (
        "background",
        "rms",
        "source-filtering-mask",
    )


def test_compact_deblend_stage_supports_single_window_sources(
    tmp_path: Path,
) -> None:
    """Pipeline-neutral sources need not implement the batching extension."""
    manifest = plan_image_partitions(
        image_shape_yx=_image().shape,
        tile_core_shape_yx=(12, 14),
        halo_yx=(0, 0),
    )
    detection, sink = _run(
        tmp_path / "single-window.zarr",
        manifest,
        SerialExecutor(),
    )

    result = run_compact_deblend_stage(
        _ReadOneImageSource(_image()),
        detection,
        _deblend_config(),
        SerialExecutor(),
        sink,
    )

    assert tuple(island.island_id for island in result.islands) == tuple(
        island.island_id for island in detection.islands
    )


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("bounds", "different island bounds"),
        ("shape", "misaligned island window"),
        ("validity", "mask contains an invalid pixel"),
    ],
)
def test_compact_deblend_stage_rejects_invalid_batched_windows(
    tmp_path: Path,
    failure: Literal["bounds", "shape", "validity"],
    message: str,
) -> None:
    """Batched source responses fail closed before scientific summaries."""
    manifest = plan_image_partitions(
        image_shape_yx=_image().shape,
        tile_core_shape_yx=(12, 14),
        halo_yx=(0, 0),
    )
    detection, sink = _run(
        tmp_path / f"invalid-{failure}.zarr",
        manifest,
        SerialExecutor(),
    )

    with pytest.raises(ValueError, match=message):
        run_compact_deblend_stage(
            _InvalidBatchImageSource(_image(), failure),
            detection,
            _deblend_config(),
            SerialExecutor(),
            sink,
        )


def test_compact_deblend_stage_rejects_a_different_generation(
    tmp_path: Path,
) -> None:
    """Compact consumers cannot mix products from different generations."""
    manifest = plan_image_partitions(
        image_shape_yx=_image().shape,
        tile_core_shape_yx=(12, 14),
        halo_yx=(0, 0),
    )
    detection, _ = _run(
        tmp_path / "source-generation.zarr",
        manifest,
        SerialExecutor(),
    )
    different_sink = ZarrProductSink(
        tmp_path / "different-generation.zarr",
        manifest,
        generation_id="different",
    )

    with pytest.raises(ValueError, match="does not match"):
        run_compact_deblend_stage(
            _ArrayImageSource(_image()),
            detection,
            _deblend_config(),
            SerialExecutor(),
            different_sink,
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


def test_prepared_detection_rejects_mismatched_or_refined_inputs(
    tmp_path: Path,
) -> None:
    """The reusable Phase 3 boundary requires its exact coarse generation."""
    manifest = plan_image_partitions(
        image_shape_yx=_image().shape,
        tile_core_shape_yx=(12, 14),
        halo_yx=(0, 0),
    )
    result, _ = _run(tmp_path / "source.zarr", manifest, SerialExecutor())
    config = DetectionStageConfig(
        background_rms=_background_config(),
        source_finder=_source_finder_config(),
    )
    wrong_manifest = plan_image_partitions(
        image_shape_yx=(12, 14),
        tile_core_shape_yx=(12, 14),
        halo_yx=(0, 0),
    )
    wrong_sink = ZarrProductSink(
        tmp_path / "wrong.zarr",
        wrong_manifest,
        generation_id="wrong",
    )

    with pytest.raises(ValueError, match="stage partition"):
        run_detection_from_coarse_grids(
            _ArrayImageSource(_image()),
            manifest,
            result.background_rms_grids,
            config=config,
            executor=SerialExecutor(),
            sink=wrong_sink,
        )

    refined_sink = ZarrProductSink(
        tmp_path / "refined.zarr",
        manifest,
        generation_id="refined",
    )
    with pytest.raises(ValueError, match="coarse-only"):
        run_detection_from_coarse_grids(
            _ArrayImageSource(_image()),
            manifest,
            result.background_rms_grids,
            config=config,
            executor=SerialExecutor(),
            sink=refined_sink,
        )

    shape_sink = ZarrProductSink(
        tmp_path / "shape.zarr",
        wrong_manifest,
        generation_id="shape",
    )
    coarse_only = result.background_rms_grids.__class__(
        coarse=result.background_rms_grids.coarse,
        adaptive_regions=(),
    )
    with pytest.raises(ValueError, match="image shape"):
        run_detection_from_coarse_grids(
            _ArrayImageSource(_image()),
            wrong_manifest,
            coarse_only,
            config=config,
            executor=SerialExecutor(),
            sink=shape_sink,
        )


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
        dask_deblended = run_compact_deblend_stage(
            _ArrayImageSource(_image()),
            dask,
            _deblend_config(),
            DaskExecutor(client),
            dask_sink,
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
    serial_deblended = run_compact_deblend_stage(
        _ArrayImageSource(_image()),
        serial,
        _deblend_config(),
        SerialExecutor(),
        serial_sink,
    )
    assert dask_deblended == serial_deblended
