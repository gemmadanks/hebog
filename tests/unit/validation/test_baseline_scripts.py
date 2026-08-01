"""Tests for the isolated PyBDSF baseline entry points."""

from __future__ import annotations

import hashlib
import runpy
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from hebog.data_models.partitioning import ImageBounds
from hebog.executors import SerialExecutor
from hebog.io.base import ImageWindow


def _script(name: str) -> dict[str, Any]:
    """Load one script without invoking its command-line entry point."""
    root = Path(__file__).parents[3]
    return runpy.run_path(str(root / "scripts" / "benchmark" / name))


def test_reference_configuration_requires_explicit_ordered_thresholds() -> (
    None
):
    """A campaign cannot silently inherit the Rapthor helper defaults."""
    pytest.importorskip(
        "resource",
        reason="the reference runner executes inside a POSIX container",
    )
    namespace = _script("pybdsf_reference_run.py")
    configuration: Callable[[float, float], dict[str, object]] = namespace[
        "_configuration"
    ]

    assert configuration(5.0, 3.0)["threshold_pixel_sigma"] == 5.0
    assert configuration(5.0, 3.0)["threshold_island_sigma"] == 3.0
    with pytest.raises(ValueError, match="0 < island <= detection"):
        configuration(3.0, 5.0)


def test_directory_identity_excludes_mutable_casa_lock_files(
    tmp_path: Path,
) -> None:
    """Opening a Measurement Set must not change its scientific identity."""
    namespace = _script("run_phase0_pybdsf_baseline.py")
    path_sha256: Callable[[Path], str] = namespace["_path_sha256"]
    (tmp_path / "table.dat").write_bytes(b"science")
    (tmp_path / "table.lock").write_bytes(b"first lock state")

    first = path_sha256(tmp_path)
    (tmp_path / "table.lock").write_bytes(b"second lock state")

    assert path_sha256(tmp_path) == first
    assert first != hashlib.sha256(b"science").hexdigest()


def test_phase1_io_benchmark_samples_portable_current_rss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loading and measuring the benchmark must not require POSIX resource."""
    namespace = _script("measure_phase1_io.py")
    monkeypatch.setattr(
        namespace["psutil"],
        "Process",
        lambda: SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=8192)),
    )

    sampler = namespace["_ResidentMemorySampler"]()
    sampler.start()

    assert sampler.stop() == 8192


def test_phase1_io_benchmark_records_bounded_one_and_many_tile_runs(
    tmp_path: Path,
) -> None:
    """The benchmark observes the real FITS/Zarr path and its memory bound."""
    namespace = _script("measure_phase1_io.py")
    input_path = tmp_path / "input.fits"
    generate_input: Callable[..., None] = namespace["_generate_input"]
    run_once: Callable[..., Any] = namespace["_run_once"]
    generate_input(input_path, size=5)

    one_tile = run_once(
        input_path=input_path,
        work_parent=tmp_path,
        size=5,
        tile_size=8,
        repetition_index=0,
        warmup=True,
    )
    many_tile = run_once(
        input_path=input_path,
        work_parent=tmp_path,
        size=5,
        tile_size=3,
        repetition_index=1,
        warmup=False,
    )

    assert one_tile.partition_count == 1
    assert one_tile.maximum_row_block_bytes == 5 * 5 * 8
    assert many_tile.partition_count == 4
    assert many_tile.maximum_row_block_bytes == 3 * 5 * 8
    assert many_tile.object_count > one_tile.object_count
    assert many_tile.zarr_bytes > 0
    assert many_tile.final_fits_bytes > 0
    assert tuple(stage.stage for stage in many_tile.measurement.stages) == (
        "fits-zarr-ingestion",
        "zarr-fits-materialisation",
    )
    metrics = many_tile.measurement.complete
    assert metrics.dask_task_count == 0
    assert metrics.array_copy_count is None
    assert {item.metric for item in metrics.unavailable_metrics} == {
        "array_copy_bytes",
        "array_copy_count",
    }


def test_phase2_background_benchmark_records_bounded_stage_work() -> None:
    """The benchmark measures coarse batches and interpolation separately."""
    namespace = _script("measure_phase2_background.py")
    configuration: Callable[..., Any] = namespace["_configuration"]
    run_once: Callable[..., Any] = namespace["_run_once"]
    values = np.arange(20 * 24, dtype=np.float64).reshape(20, 24)

    class ArraySource:
        """Provide bounded windows for the benchmark contract test."""

        def read_window(self, bounds: ImageBounds) -> ImageWindow:
            return ImageWindow(
                bounds=bounds,
                values=values[
                    bounds.y_start : bounds.y_stop,
                    bounds.x_start : bounds.x_stop,
                ],
                valid_pixels=np.ones(bounds.shape_yx, dtype=np.bool_),
            )

    config = configuration(
        window_size=5,
        step_size=4,
        maximum_batch_cells=4,
    )
    result = run_once(
        source=ArraySource(),
        image_shape_yx=values.shape,
        config=config,
        executor=SerialExecutor(),
        executor_kind="serial",
        tile_size=12,
        repetition_index=1,
        warmup=False,
    )

    assert result.partition_count == 4
    assert result.coarse_cell_count == 30
    assert result.maximum_tile_pixels == 12 * 12
    assert tuple(stage.stage for stage in result.measurement.stages) == (
        "coarse-rms-grid",
        "rms-interpolation",
    )
    metrics = result.measurement.complete
    assert metrics.dask_task_count == 0
    assert metrics.transfer_bytes == 0
    assert metrics.spill_bytes == 0
