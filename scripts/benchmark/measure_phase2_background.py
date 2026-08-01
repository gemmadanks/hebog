# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Measure bounded Phase 2 background/RMS estimation on one FITS image."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import threading
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Generic, Protocol, TypeVar

import psutil
from astropy.wcs import FITSFixedWarning
from distributed import Client

from hebog.algorithms.background import plan_rms_window_batches
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    BackgroundRmsConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
)
from hebog.data_models.partitioning import ImageBounds
from hebog.executors.base import Executor
from hebog.executors.dask import DaskExecutor
from hebog.io import FitsImageSource
from hebog.io.base import ImageWindow
from hebog.stages.background import (
    estimate_background_rms_grids,
    estimate_background_rms_tile,
    prepare_background_rms_tile_request,
)
from hebog.validation.datasets import DatasetRole
from hebog.validation.evidence import (
    BenchmarkEvidence,
    DatasetIdentity,
    EvidenceStatus,
    ExecutorKind,
    Measurement,
    ResourceAllocation,
    RuntimeMetrics,
    SoftwareIdentity,
    StageMetrics,
    UnavailableMetric,
    WorkloadClass,
    write_evidence,
)

Result_co = TypeVar("Result_co", covariant=True)
_MINIMUM_REPETITIONS = 5
_DEPENDENCIES = ("astropy", "distributed", "hebog", "numpy", "scipy")
_COPY_REASON = (
    "NumPy, SciPy, Astropy, and Distributed do not expose complete "
    "allocation counters; bounded reads and tile outputs are tested "
    "structurally"
)
_DASK_ACCOUNTING_REASON = (
    "the reused in-process Dask client does not expose stable per-stage "
    "transfer and spill attribution"
)


class _WindowReadable(Protocol):
    """Read bounded image windows for one benchmark repetition."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return one globally bounded image window."""
        ...


@dataclass(frozen=True, slots=True)
class _TimedResult(Generic[Result_co]):
    """One stage result and its process-level resource observation."""

    value: Result_co
    wall_seconds: float
    cpu_seconds: float
    peak_rss_bytes: int


@dataclass(frozen=True, slots=True)
class _RunResult:
    """One repetition and its bounded-work observations."""

    measurement: Measurement
    partition_count: int
    coarse_cell_count: int
    maximum_tile_pixels: int


def _parse_args() -> argparse.Namespace:
    """Parse one controlled local background benchmark configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--stage",
        required=True,
        choices=("true-sky-background", "flat-noise-rms"),
    )
    parser.add_argument("--window-size", default=150, type=int)
    parser.add_argument("--step-size", default=50, type=int)
    parser.add_argument("--maximum-batch-cells", default=64, type=int)
    parser.add_argument("--tile-size", default=1500, type=int)
    parser.add_argument("--workers", default=4, type=int)
    parser.add_argument("--threads-per-worker", default=1, type=int)
    parser.add_argument("--warmups", default=1, type=int)
    parser.add_argument("--repetitions", default=5, type=int)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    """Hash one complete file without loading it as an array."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    """Hash one JSON-compatible value canonically."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _configuration(
    *,
    window_size: int,
    step_size: int,
    maximum_batch_cells: int,
) -> BackgroundRmsConfig:
    """Return the explicit Rapthor-compatible coarse RMS policy."""
    statistics = RmsWindowStatisticsConfig(
        clipping_sigma=3.0,
        maximum_iterations=10,
        minimum_samples=6,
    )
    return BackgroundRmsConfig(
        coarse=RmsGridConfig(
            window_shape_yx=(window_size, window_size),
            step_yx=(step_size, step_size),
            statistics=statistics,
            maximum_batch_cells=maximum_batch_cells,
        ),
        adaptive=None,
        maximum_spatial_window_fraction=0.25,
        maximum_constant_map_pixels=1_000_000,
    )


class _ResidentMemorySampler:
    """Sample portable current-process RSS during one synchronous stage."""

    def __init__(self) -> None:
        self._peak_bytes = 0
        self._stop = threading.Event()
        self._process = psutil.Process()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _current_bytes(self) -> int:
        return int(self._process.memory_info().rss)

    def _sample(self) -> None:
        while not self._stop.is_set():
            self._peak_bytes = max(self._peak_bytes, self._current_bytes())
            self._stop.wait(0.005)

    def start(self) -> None:
        """Start sampling resident memory."""
        self._peak_bytes = self._current_bytes()
        self._thread.start()

    def stop(self) -> int:
        """Stop sampling and return the largest observed resident set."""
        self._stop.set()
        self._thread.join()
        return max(self._peak_bytes, self._current_bytes())


def _measure(function: Callable[[], Result_co]) -> _TimedResult[Result_co]:
    """Measure one already-configured synchronous stage."""
    sampler = _ResidentMemorySampler()
    sampler.start()
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    try:
        value = function()
    finally:
        peak_rss_bytes = sampler.stop()
    return _TimedResult(
        value=value,
        wall_seconds=time.perf_counter() - wall_started,
        cpu_seconds=time.process_time() - cpu_started,
        peak_rss_bytes=peak_rss_bytes,
    )


def _runtime_metrics(
    measured: _TimedResult[object],
    *,
    executor_kind: ExecutorKind,
    dask_task_count: int,
) -> RuntimeMetrics:
    """Convert one observation without inventing unavailable counters."""
    unavailable = [
        UnavailableMetric(metric="array_copy_count", reason=_COPY_REASON),
        UnavailableMetric(metric="array_copy_bytes", reason=_COPY_REASON),
    ]
    if executor_kind is ExecutorKind.DASK:
        transfer_bytes = None
        spill_bytes = None
        unavailable.extend(
            (
                UnavailableMetric(
                    metric="transfer_bytes",
                    reason=_DASK_ACCOUNTING_REASON,
                ),
                UnavailableMetric(
                    metric="spill_bytes",
                    reason=_DASK_ACCOUNTING_REASON,
                ),
            )
        )
    else:
        transfer_bytes = 0
        spill_bytes = 0
    return RuntimeMetrics(
        wall_seconds=measured.wall_seconds,
        cpu_seconds=measured.cpu_seconds,
        peak_rss_bytes=measured.peak_rss_bytes,
        array_copy_count=None,
        array_copy_bytes=None,
        dask_task_count=dask_task_count,
        transfer_bytes=transfer_bytes,
        spill_bytes=spill_bytes,
        unavailable_metrics=tuple(unavailable),
    )


def _run_once(  # noqa: PLR0913
    *,
    source: _WindowReadable,
    image_shape_yx: tuple[int, int],
    config: BackgroundRmsConfig,
    executor: Executor,
    executor_kind: ExecutorKind | str,
    tile_size: int,
    repetition_index: int,
    warmup: bool,
) -> _RunResult:
    """Measure coarse estimation and bounded output interpolation once."""
    kind = ExecutorKind(executor_kind)
    grid_measurement = _measure(
        lambda: estimate_background_rms_grids(
            source,
            image_shape_yx,
            config,
            executor,
            bright_candidate_positions_yx=(),
        )
    )
    grids = grid_measurement.value
    if not hasattr(grids, "coarse"):  # pragma: no cover - typed callback
        raise TypeError("background estimation did not return RMS grids")
    coarse_task_count = len(
        plan_rms_window_batches(
            grids.coarse.geometry,
            maximum_cells=config.coarse.maximum_batch_cells,
        )
    )
    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(tile_size, tile_size),
        halo_yx=(0, 0),
    )

    def interpolate_tiles() -> None:
        for partition in manifest.tiles:
            request = prepare_background_rms_tile_request(
                partition,
                grids,
                config,
                bright_candidate_positions_yx=(),
            )
            estimate_background_rms_tile(source, request)

    interpolation_measurement = _measure(interpolate_tiles)
    grid_metrics = _runtime_metrics(
        grid_measurement,
        executor_kind=kind,
        dask_task_count=(
            coarse_task_count if kind is ExecutorKind.DASK else 0
        ),
    )
    interpolation_metrics = _runtime_metrics(
        interpolation_measurement,
        executor_kind=kind,
        dask_task_count=0,
    )
    combined = _TimedResult(
        value=None,
        wall_seconds=(
            grid_measurement.wall_seconds
            + interpolation_measurement.wall_seconds
        ),
        cpu_seconds=(
            grid_measurement.cpu_seconds
            + interpolation_measurement.cpu_seconds
        ),
        peak_rss_bytes=max(
            grid_measurement.peak_rss_bytes,
            interpolation_measurement.peak_rss_bytes,
        ),
    )
    return _RunResult(
        measurement=Measurement(
            repetition_index=repetition_index,
            warmup=warmup,
            complete=_runtime_metrics(
                combined,
                executor_kind=kind,
                dask_task_count=(
                    coarse_task_count if kind is ExecutorKind.DASK else 0
                ),
            ),
            stages=(
                StageMetrics(stage="coarse-rms-grid", metrics=grid_metrics),
                StageMetrics(
                    stage="rms-interpolation",
                    metrics=interpolation_metrics,
                ),
            ),
        ),
        partition_count=len(manifest.tiles),
        coarse_cell_count=grids.coarse.geometry.cell_count,
        maximum_tile_pixels=max(
            partition.core_bounds.shape_yx[0]
            * partition.core_bounds.shape_yx[1]
            for partition in manifest.tiles
        ),
    )


def _dependency_inventory() -> dict[str, str]:
    """Return relevant installed distribution versions."""
    return {name: importlib.metadata.version(name) for name in _DEPENDENCIES}


def _git_commit() -> str | None:
    """Return the checked-out commit when Git metadata is available."""
    try:
        value = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return value or None


def main() -> None:
    """Run the controlled benchmark and write exploratory typed evidence."""
    args = _parse_args()
    positive_values = (
        args.window_size,
        args.step_size,
        args.maximum_batch_cells,
        args.tile_size,
        args.workers,
        args.threads_per_worker,
    )
    if any(value < 1 for value in positive_values):
        raise ValueError("benchmark geometry and resources must be positive")
    if args.warmups < 1 or args.repetitions < _MINIMUM_REPETITIONS:
        raise ValueError("benchmark requires a warm-up and five measurements")
    if not args.input.is_file():
        raise ValueError(f"benchmark input is not a file: {args.input}")

    captured_at = datetime.now(timezone.utc)
    source = FitsImageSource(args.input)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FITSFixedWarning)
        metadata = source.metadata()
    config = _configuration(
        window_size=args.window_size,
        step_size=args.step_size,
        maximum_batch_cells=args.maximum_batch_cells,
    )
    dependency_inventory = _dependency_inventory()
    configuration = {
        "stage": args.stage,
        "window_shape_yx": config.coarse.window_shape_yx,
        "step_yx": config.coarse.step_yx,
        "maximum_batch_cells": args.maximum_batch_cells,
        "tile_shape_yx": (args.tile_size, args.tile_size),
        "clipping_sigma": config.coarse.statistics.clipping_sigma,
        "maximum_iterations": (config.coarse.statistics.maximum_iterations),
        "minimum_samples": config.coarse.statistics.minimum_samples,
        "dtype": "<f8",
        "adaptive_candidates": [],
        "warmups": args.warmups,
        "repetitions": args.repetitions,
    }
    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "dependencies": dependency_inventory,
    }
    total_memory = int(psutil.virtual_memory().total)
    worker_memory = total_memory // args.workers
    with Client(
        n_workers=args.workers,
        threads_per_worker=args.threads_per_worker,
        processes=False,
        dashboard_address=None,
        memory_limit=worker_memory,
    ) as client:
        executor = DaskExecutor(client)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FITSFixedWarning)
            runs = tuple(
                _run_once(
                    source=source,
                    image_shape_yx=metadata.shape_yx,
                    config=config,
                    executor=executor,
                    executor_kind=ExecutorKind.DASK,
                    tile_size=args.tile_size,
                    repetition_index=index,
                    warmup=index < args.warmups,
                )
                for index in range(args.warmups + args.repetitions)
            )

    evidence = BenchmarkEvidence(
        schema_version=1,
        evidence_type="benchmark",
        run_id=(
            f"phase-2-{args.stage}-{captured_at.strftime('%Y%m%d%H%M%S')}"
        ),
        captured_at=captured_at,
        status=EvidenceStatus.EXPLORATORY,
        dataset=DatasetIdentity(
            identifier=args.dataset_id,
            role=DatasetRole.DEVELOPMENT,
            content_sha256=_sha256(args.input),
            shape_yx=metadata.shape_yx,
            workload_class=WorkloadClass.NORMAL,
        ),
        configuration_sha256=_canonical_sha256(configuration),
        subject=SoftwareIdentity(
            name="hebog",
            version=importlib.metadata.version("hebog"),
            commit_sha=_git_commit(),
            dependency_inventory_sha256=_canonical_sha256(
                dependency_inventory
            ),
        ),
        environment_sha256=_canonical_sha256(environment),
        resources=ResourceAllocation(
            executor=ExecutorKind.DASK,
            worker_nodes=1,
            workers_per_node=args.workers,
            threads_per_worker=args.threads_per_worker,
            allocated_cpu_cores=args.workers * args.threads_per_worker,
            node_memory_bytes=total_memory,
            worker_memory_limit_bytes=worker_memory,
            reserved_headroom_per_node_bytes=(
                total_memory - worker_memory * args.workers
            ),
            storage_identifier="local-fits-reused-dask-client",
        ),
        measurements=tuple(run.measurement for run in runs),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(args.output, evidence)
    measured_seconds = sorted(
        run.measurement.complete.wall_seconds
        for run in runs
        if not run.measurement.warmup
    )
    median_seconds = measured_seconds[len(measured_seconds) // 2]
    last = runs[-1]
    print(
        json.dumps(
            {
                "coarse_cell_count": last.coarse_cell_count,
                "evidence": str(args.output),
                "maximum_tile_pixels": last.maximum_tile_pixels,
                "median_wall_seconds": median_seconds,
                "partition_count": last.partition_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
