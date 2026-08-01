# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Measure bounded Phase 3 detection from a prepared Phase 2 coarse grid."""

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
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Generic, TypeVar

import psutil
from astropy.wcs import FITSFixedWarning
from distributed import Client

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    CompactDeblendConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)
from hebog.executors.base import Executor
from hebog.executors.dask import DaskExecutor
from hebog.executors.serial import SerialExecutor
from hebog.io import FitsImageSource, ZarrProductSink
from hebog.stages.background import (
    BackgroundRmsGrids,
    estimate_background_rms_grids,
)
from hebog.stages.deblending import run_compact_deblend_stage
from hebog.stages.detection import (
    DetectionStageConfig,
    run_detection_from_coarse_grids,
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

Input = TypeVar("Input")
Output = TypeVar("Output")
Result_co = TypeVar("Result_co", covariant=True)
_MINIMUM_REPETITIONS = 5
_DEPENDENCIES = (
    "astropy",
    "distributed",
    "hebog",
    "numpy",
    "scipy",
    "zarr",
)
_COPY_REASON = (
    "NumPy, SciPy, Astropy, and Zarr do not expose complete allocation "
    "counters; bounded task inputs and outputs are tested structurally"
)
_DASK_ACCOUNTING_REASON = (
    "the reused in-process Dask client does not expose stable per-stage "
    "transfer and spill attribution"
)


@dataclass(frozen=True, slots=True)
class _TimedResult(Generic[Result_co]):
    """One stage result and its process-level resource observation."""

    value: Result_co
    wall_seconds: float
    cpu_seconds: float
    peak_rss_bytes: int


@dataclass(frozen=True, slots=True)
class _RunResult:
    """One bounded Phase 3 repetition and its structural observations."""

    measurement: Measurement
    partition_count: int
    boundary_label_count: int
    detected_island_count: int
    deblended_region_count: int
    deferred_island_count: int
    admitted_bounds_pixel_count: int


class _CountingExecutor:
    """Count coarse scheduler submissions without changing execution."""

    def __init__(self, executor: Executor) -> None:
        self._executor = executor
        self.task_count = 0

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
    ) -> list[Output]:
        """Forward one ordered batch collection and count its entries."""
        materialized = tuple(batches)
        self.task_count += len(materialized)
        return self._executor.map_batches(function, materialized)


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


def _parse_args() -> argparse.Namespace:
    """Parse one controlled Phase 3 benchmark configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--workload-class",
        default=WorkloadClass.NORMAL.value,
        choices=tuple(item.value for item in WorkloadClass),
    )
    parser.add_argument("--tile-size", default=1500, type=int)
    parser.add_argument(
        "--executor",
        default=ExecutorKind.DASK.value,
        choices=(ExecutorKind.SERIAL.value, ExecutorKind.DASK.value),
    )
    parser.add_argument("--workers", default=4, type=int)
    parser.add_argument("--threads-per-worker", default=1, type=int)
    parser.add_argument("--warmups", default=1, type=int)
    parser.add_argument("--repetitions", default=5, type=int)
    return parser.parse_args()


def _configuration() -> tuple[DetectionStageConfig, CompactDeblendConfig]:
    """Return the frozen Rapthor-compatible Phase 3 component policy."""
    statistics = RmsWindowStatisticsConfig(3.0, 10, 6)
    detection = DetectionStageConfig(
        background_rms=BackgroundRmsConfig(
            coarse=RmsGridConfig(
                window_shape_yx=(150, 150),
                step_yx=(50, 50),
                statistics=statistics,
                maximum_batch_cells=64,
            ),
            adaptive=AdaptiveRmsConfig(
                grid=RmsGridConfig(
                    window_shape_yx=(35, 35),
                    step_yx=(7, 7),
                    statistics=statistics,
                    maximum_batch_cells=512,
                ),
                candidate_threshold_sigma=75.0,
                influence_radius_pixels=75.0,
                transition_width_pixels=20.0,
            ),
            maximum_spatial_window_fraction=0.25,
            maximum_constant_map_pixels=10_000_000,
        ),
        source_finder=SourceFinderConfig(
            detection_threshold_sigma=5.0,
            island_threshold_sigma=3.0,
            minimum_island_pixels=6,
        ),
    )
    deblend = CompactDeblendConfig(
        minimum_peak_signal_to_noise=5.0,
        minimum_peak_separation_pixels=2,
        minimum_saddle_depth_sigma=1.0,
        maximum_compact_island_pixels=250_000,
        maximum_compact_bounds_pixels=1_000_000,
        maximum_batch_pixels=4_000_000,
    )
    return detection, deblend


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
    task_count: int,
) -> RuntimeMetrics:
    """Convert an observation without inventing unavailable counters."""
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
        dask_task_count=(
            task_count if executor_kind is ExecutorKind.DASK else 0
        ),
        transfer_bytes=transfer_bytes,
        spill_bytes=spill_bytes,
        unavailable_metrics=tuple(unavailable),
    )


def _run_once(  # noqa: PLR0913
    *,
    source: FitsImageSource,
    coarse_grids: BackgroundRmsGrids,
    detection_config: DetectionStageConfig,
    deblend_config: CompactDeblendConfig,
    executor: Executor,
    executor_kind: ExecutorKind | str,
    tile_size: int,
    work_parent: Path,
    repetition_index: int,
    warmup: bool,
) -> _RunResult:
    """Measure adaptive detection and compact deblending, excluding Phase 2."""
    kind = ExecutorKind(executor_kind)
    shape_yx = coarse_grids.coarse.geometry.image_shape_yx
    manifest = plan_image_partitions(
        image_shape_yx=shape_yx,
        tile_core_shape_yx=(tile_size, tile_size),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_parent / f"rep-{repetition_index:02d}.zarr",
        manifest,
        generation_id=f"phase3-benchmark-{repetition_index:02d}",
    )
    counted = _CountingExecutor(executor)
    detection = _measure(
        lambda: run_detection_from_coarse_grids(
            source,
            manifest,
            coarse_grids,
            config=detection_config,
            executor=counted,
            sink=sink,
        )
    )
    detection_tasks = counted.task_count
    deblend = _measure(
        lambda: run_compact_deblend_stage(
            source,
            detection.value,
            deblend_config,
            counted,
            sink,
        )
    )
    deblend_tasks = counted.task_count - detection_tasks
    combined = _TimedResult(
        value=None,
        wall_seconds=detection.wall_seconds + deblend.wall_seconds,
        cpu_seconds=detection.cpu_seconds + deblend.cpu_seconds,
        peak_rss_bytes=max(detection.peak_rss_bytes, deblend.peak_rss_bytes),
    )
    deblend_result = deblend.value
    return _RunResult(
        measurement=Measurement(
            repetition_index=repetition_index,
            warmup=warmup,
            complete=_runtime_metrics(
                combined,
                executor_kind=kind,
                task_count=counted.task_count,
            ),
            stages=(
                StageMetrics(
                    stage="compact-detection",
                    metrics=_runtime_metrics(
                        detection,
                        executor_kind=kind,
                        task_count=detection_tasks,
                    ),
                ),
                StageMetrics(
                    stage="compact-deblending",
                    metrics=_runtime_metrics(
                        deblend,
                        executor_kind=kind,
                        task_count=deblend_tasks,
                    ),
                ),
            ),
        ),
        partition_count=len(manifest.tiles),
        boundary_label_count=detection.value.boundary_label_count,
        detected_island_count=len(detection.value.islands),
        deblended_region_count=sum(
            len(island.regions) for island in deblend_result.islands
        ),
        deferred_island_count=len(deblend_result.deferred_islands),
        admitted_bounds_pixel_count=deblend_result.admitted_bounds_pixel_count,
    )


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


def _source_tree_sha256() -> str:
    """Hash production Python sources used by an uncommitted benchmark."""
    digest = hashlib.sha256()
    root = Path(__file__).parents[2]
    for path in sorted((root / "src" / "hebog").rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


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
    if any(
        value < 1
        for value in (
            args.tile_size,
            args.workers,
            args.threads_per_worker,
        )
    ):
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
    detection_config, deblend_config = _configuration()
    dependencies = {
        name: importlib.metadata.version(name) for name in _DEPENDENCIES
    }
    source_tree_sha256 = _source_tree_sha256()
    configuration = {
        "component_boundary": "after-phase-2-coarse-grid",
        "detection": asdict(detection_config),
        "deblending": asdict(deblend_config),
        "executor": args.executor,
        "tile_shape_yx": (args.tile_size, args.tile_size),
        "warmups": args.warmups,
        "repetitions": args.repetitions,
        "source_tree_sha256": source_tree_sha256,
    }
    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "dependencies": dependencies,
    }
    total_memory = int(psutil.virtual_memory().total)
    executor_kind = ExecutorKind(args.executor)
    workers = args.workers if executor_kind is ExecutorKind.DASK else 1
    threads_per_worker = (
        args.threads_per_worker if executor_kind is ExecutorKind.DASK else 1
    )
    worker_memory = total_memory // workers

    def run_with(executor: Executor) -> tuple[_RunResult, ...]:
        """Prepare Phase 2 once and measure Phase 3 repeatedly."""
        coarse_grids = estimate_background_rms_grids(
            source,
            metadata.shape_yx,
            detection_config.background_rms,
            executor,
            bright_candidate_positions_yx=(),
        )
        with (
            TemporaryDirectory(prefix="hebog-phase3-") as directory,
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore", FITSFixedWarning)
            runs = tuple(
                _run_once(
                    source=source,
                    coarse_grids=coarse_grids,
                    detection_config=detection_config,
                    deblend_config=deblend_config,
                    executor=executor,
                    executor_kind=executor_kind,
                    tile_size=args.tile_size,
                    work_parent=Path(directory),
                    repetition_index=index,
                    warmup=index < args.warmups,
                )
                for index in range(args.warmups + args.repetitions)
            )
        return runs

    if executor_kind is ExecutorKind.SERIAL:
        runs = run_with(SerialExecutor())
    else:
        with Client(
            n_workers=workers,
            threads_per_worker=threads_per_worker,
            processes=False,
            dashboard_address=None,
            memory_limit=worker_memory,
        ) as client:
            runs = run_with(DaskExecutor(client))

    evidence = BenchmarkEvidence(
        schema_version=1,
        evidence_type="benchmark",
        run_id=f"phase-3-detection-{captured_at.strftime('%Y%m%d%H%M%S')}",
        captured_at=captured_at,
        status=EvidenceStatus.EXPLORATORY,
        dataset=DatasetIdentity(
            identifier=args.dataset_id,
            role=DatasetRole.DEVELOPMENT,
            content_sha256=_sha256(args.input),
            shape_yx=metadata.shape_yx,
            workload_class=WorkloadClass(args.workload_class),
        ),
        configuration_sha256=_canonical_sha256(configuration),
        subject=SoftwareIdentity(
            name="hebog",
            version=importlib.metadata.version("hebog"),
            commit_sha=_git_commit(),
            source_tree_sha256=source_tree_sha256,
            dependency_inventory_sha256=_canonical_sha256(dependencies),
        ),
        environment_sha256=_canonical_sha256(environment),
        resources=ResourceAllocation(
            executor=executor_kind,
            worker_nodes=1,
            workers_per_node=workers,
            threads_per_worker=threads_per_worker,
            allocated_cpu_cores=workers * threads_per_worker,
            node_memory_bytes=total_memory,
            worker_memory_limit_bytes=worker_memory,
            reserved_headroom_per_node_bytes=(
                total_memory - worker_memory * workers
            ),
            storage_identifier=(
                "local-fits-zarr-reused-dask-client"
                if executor_kind is ExecutorKind.DASK
                else "local-fits-zarr-serial"
            ),
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
                "admitted_bounds_pixel_count": (
                    last.admitted_bounds_pixel_count
                ),
                "boundary_label_count": last.boundary_label_count,
                "deblended_region_count": last.deblended_region_count,
                "deferred_island_count": last.deferred_island_count,
                "detected_island_count": last.detected_island_count,
                "evidence": str(args.output),
                "median_wall_seconds": median_seconds,
                "partition_count": last.partition_count,
                "task_count": last.measurement.complete.dask_task_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
