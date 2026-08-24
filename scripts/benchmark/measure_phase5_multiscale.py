# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Measure the complete incremental Phase 5 multiscale stage."""

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
from math import atan2, degrees, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Generic, TypeVar

import numpy as np
import psutil
from astropy.wcs import FITSFixedWarning
from distributed import Client

from hebog.algorithms.astrometry import compact_geometry_at_pixel
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.phase_five_execution import scale_filter_halo_pixels
from hebog.config import ResidualMultiscaleDetectionConfig
from hebog.data_models.partitioning import PartitionManifest
from hebog.executors.base import Executor
from hebog.executors.dask import DaskExecutor
from hebog.executors.serial import SerialExecutor
from hebog.io import FitsImageSource, ZarrProductSink
from hebog.stages.detection import run_detection_stage
from hebog.stages.multiscale import (
    PhaseFiveMultiscaleStageConfig,
    run_phase_five_multiscale_stage,
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
from hebog.validation.hebog_campaign import phase_four_candidate_configs

Input = TypeVar("Input")
Output = TypeVar("Output")
Result_co = TypeVar("Result_co", covariant=True)

_FWHM_PER_SIGMA = 2.0 * sqrt(2.0 * np.log(2.0))
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
    "counters; bounded tile arrays are recorded structurally"
)
_DASK_ACCOUNTING_REASON = (
    "the reused in-process Dask client does not expose stable per-stage "
    "transfer and spill attribution"
)


@dataclass(frozen=True, slots=True)
class _TimedResult(Generic[Result_co]):
    """One synchronous result and process-level resource observation."""

    value: Result_co
    wall_seconds: float
    cpu_seconds: float
    peak_rss_bytes: int


@dataclass(frozen=True, slots=True)
class _RunResult:
    """One incremental repetition plus bounded execution evidence."""

    measurement: Measurement
    detection_island_count: int
    reconstruction_island_count: int
    scale_island_counts: tuple[int, ...]
    partition_count: int
    task_count: int
    maximum_graph_width: int
    maximum_batch_partition_count: int
    maximum_read_pixel_count: int
    maximum_workspace_bytes: int
    maximum_retained_array_bytes: int
    maximum_worker_bytes: int
    boundary_summary_array_bytes: int
    published_product_shard_count: int


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
    """Sample portable aggregate process-tree RSS during one stage."""

    def __init__(self) -> None:
        self._peak_bytes = 0
        self._stop = threading.Event()
        self._process = psutil.Process()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _current_bytes(self) -> int:
        total = int(self._process.memory_info().rss)
        for child in self._process.children(recursive=True):
            try:
                total += int(child.memory_info().rss)
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        return total

    def _sample(self) -> None:
        while not self._stop.is_set():
            self._peak_bytes = max(self._peak_bytes, self._current_bytes())
            self._stop.wait(0.005)

    def start(self) -> None:
        """Start process-level resident-memory sampling."""
        self._peak_bytes = self._current_bytes()
        self._thread.start()

    def stop(self) -> int:
        """Stop sampling and return the largest observed resident set."""
        self._stop.set()
        self._thread.join()
        return max(self._peak_bytes, self._current_bytes())


def _parse_args() -> argparse.Namespace:
    """Parse one controlled incremental benchmark request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--workload-class",
        required=True,
        choices=tuple(item.value for item in WorkloadClass),
    )
    parser.add_argument("--tile-size", required=True, type=int)
    parser.add_argument("--maximum-tiles-per-batch", required=True, type=int)
    parser.add_argument(
        "--executor",
        required=True,
        choices=(ExecutorKind.SERIAL.value, ExecutorKind.DASK.value),
    )
    parser.add_argument("--workers", default=4, type=int)
    parser.add_argument("--threads-per-worker", default=1, type=int)
    parser.add_argument("--warmups", default=1, type=int)
    parser.add_argument("--repetitions", default=5, type=int)
    return parser.parse_args()


def _measure(function: Callable[[], Result_co]) -> _TimedResult[Result_co]:
    """Measure one configured synchronous stage."""
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
    """Convert one observation without inventing optional counters."""
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


def _sha256(path: Path) -> str:
    """Hash one complete file without loading it into memory."""
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
    """Hash all production Python used by an uncommitted benchmark."""
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


def _cpu_affinity() -> tuple[int, ...] | None:
    """Return portable process affinity when the platform exposes it."""
    process = psutil.Process()
    try:
        return tuple(
            int(item)
            for item in process.cpu_affinity()  # pyright: ignore[reportAttributeAccessIssue]
        )
    except (AttributeError, NotImplementedError):
        return None


def _beam_from_metadata(source: FitsImageSource) -> BeamShapePixels:
    """Derive local pixel-beam axes and angle from image metadata."""
    metadata = source.metadata()
    geometry = compact_geometry_at_pixel(
        metadata,
        (metadata.shape_yx[1] / 2.0, metadata.shape_yx[0] / 2.0),
    )
    beam_covariance = geometry.restoring_beam_covariance_pixels_squared
    if beam_covariance is None:
        raise ValueError("image geometry has no restoring-beam covariance")
    xx, xy, yy = beam_covariance
    covariance = np.asarray(((xx, xy), (xy, yy)), dtype=np.float64)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    major_index = int(np.argmax(eigenvalues))
    minor_index = 1 - major_index
    major_vector = eigenvectors[:, major_index]
    angle = degrees(atan2(major_vector[1], major_vector[0])) % 180.0
    return BeamShapePixels(
        major_fwhm_pixels=(
            _FWHM_PER_SIGMA * sqrt(float(eigenvalues[major_index]))
        ),
        minor_fwhm_pixels=(
            _FWHM_PER_SIGMA * sqrt(float(eigenvalues[minor_index]))
        ),
        position_angle_degrees=angle,
    )


def _run_once(  # noqa: PLR0913
    *,
    source: FitsImageSource,
    background_rms_source: ZarrProductSink,
    manifest: PartitionManifest,
    config: PhaseFiveMultiscaleStageConfig,
    executor: Executor,
    executor_kind: ExecutorKind,
    work_parent: Path,
    repetition_index: int,
    warmup: bool,
) -> _RunResult:
    """Measure filtering, reconciliation, and atomic Zarr publication."""
    with TemporaryDirectory(
        prefix=f"phase5-{repetition_index:02d}-",
        dir=work_parent,
    ) as output_directory:
        counted = _CountingExecutor(executor)
        sink = ZarrProductSink(
            Path(output_directory) / "multiscale.zarr",
            manifest,
            generation_id=f"phase-5-benchmark-{repetition_index:02d}",
        )
        measured = _measure(
            lambda: run_phase_five_multiscale_stage(
                source,
                background_rms_source,
                manifest,
                config=config,
                executor=counted,
                sink=sink,
            )
        )
        result = measured.value
    if counted.task_count != result.executor_task_count:
        raise ValueError("measured Phase 5 task count is inconsistent")
    metrics = _runtime_metrics(
        measured,
        executor_kind=executor_kind,
        task_count=counted.task_count,
    )
    return _RunResult(
        measurement=Measurement(
            repetition_index=repetition_index,
            warmup=warmup,
            complete=metrics,
            stages=(
                StageMetrics(
                    stage="multiscale-processing-and-merge",
                    metrics=metrics,
                ),
            ),
        ),
        detection_island_count=len(result.detection_islands),
        reconstruction_island_count=len(result.reconstruction_islands),
        scale_island_counts=tuple(
            len(islands) for islands in result.scale_islands_by_order
        ),
        partition_count=result.partition_count,
        task_count=result.executor_task_count,
        maximum_graph_width=result.maximum_graph_width,
        maximum_batch_partition_count=result.maximum_batch_partition_count,
        maximum_read_pixel_count=result.maximum_read_pixel_count,
        maximum_workspace_bytes=result.maximum_workspace_bytes,
        maximum_retained_array_bytes=result.maximum_retained_array_bytes,
        maximum_worker_bytes=result.maximum_worker_bytes,
        boundary_summary_array_bytes=result.boundary_summary_array_bytes,
        published_product_shard_count=(result.published_product_shard_count),
    )


def main() -> None:  # noqa: PLR0915
    """Run one cell and write typed incremental benchmark evidence."""
    args = _parse_args()
    positive = (
        args.tile_size,
        args.maximum_tiles_per_batch,
        args.workers,
        args.threads_per_worker,
    )
    if any(value < 1 for value in positive):
        raise ValueError("benchmark geometry and resources must be positive")
    if args.warmups < 1 or args.repetitions < _MINIMUM_REPETITIONS:
        raise ValueError("benchmark requires a warm-up and five measurements")
    if not args.input.is_file():
        raise ValueError(f"benchmark input is not a file: {args.input}")
    if args.output.exists():
        raise FileExistsError(f"benchmark evidence exists: {args.output}")

    captured_at = datetime.now(timezone.utc)
    source = FitsImageSource(args.input)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FITSFixedWarning)
        metadata = source.metadata()
        beam = _beam_from_metadata(source)
    detection_config = phase_four_candidate_configs()[0]
    multiscale_detection = ResidualMultiscaleDetectionConfig(
        detection_threshold_sigma=5.0,
        island_threshold_sigma=3.0,
        minimum_scale_support_fraction=0.5,
        minimum_island_area_beams=1.0,
    )
    stage_config = PhaseFiveMultiscaleStageConfig(
        beam=beam,
        detection=multiscale_detection,
        maximum_tiles_per_batch=args.maximum_tiles_per_batch,
    )
    dependencies = {
        name: importlib.metadata.version(name) for name in _DEPENDENCIES
    }
    source_tree_sha256 = _source_tree_sha256()
    configuration = {
        "beam": asdict(beam),
        "component_boundary": "after-prepared-phase-2-background-rms",
        "detection": asdict(multiscale_detection),
        "executor": args.executor,
        "maximum_tiles_per_batch": args.maximum_tiles_per_batch,
        "profile": args.profile,
        "source_tree_sha256": source_tree_sha256,
        "tile_shape_yx": (args.tile_size, args.tile_size),
        "warmups": args.warmups,
        "repetitions": args.repetitions,
    }
    environment = {
        "cpu_affinity": _cpu_affinity(),
        "cpu_count": os.cpu_count(),
        "dependencies": dependencies,
        "machine": platform.machine(),
        "platform": platform.platform(),
        "peak_rss_scope": "driver process tree sampled every 5 ms",
        "python": platform.python_version(),
        "worker_isolation": (
            "process" if args.executor == ExecutorKind.DASK.value else "none"
        ),
    }
    total_memory = int(psutil.virtual_memory().total)
    executor_kind = ExecutorKind(args.executor)
    workers = args.workers if executor_kind is ExecutorKind.DASK else 1
    threads_per_worker = (
        args.threads_per_worker if executor_kind is ExecutorKind.DASK else 1
    )
    worker_memory = total_memory // workers

    def run_with(
        executor: Executor,
    ) -> tuple[tuple[_RunResult, ...], float]:
        """Prepare Phase 2 once and measure only Phase 5 repeatedly."""
        with (
            TemporaryDirectory(prefix="hebog-phase5-") as directory,
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore", FITSFixedWarning)
            work_parent = Path(directory)
            prepared_manifest = plan_image_partitions(
                image_shape_yx=metadata.shape_yx,
                tile_core_shape_yx=(args.tile_size, args.tile_size),
                halo_yx=(0, 0),
            )
            prepared_sink = ZarrProductSink(
                work_parent / "prepared-phase2.zarr",
                prepared_manifest,
                generation_id="phase-5-benchmark-prepared-phase2",
            )
            setup = _measure(
                lambda: run_detection_stage(
                    source,
                    prepared_manifest,
                    detection_config,
                    executor,
                    prepared_sink,
                )
            )
            halo = scale_filter_halo_pixels(beam)
            manifest = plan_image_partitions(
                image_shape_yx=metadata.shape_yx,
                tile_core_shape_yx=(args.tile_size, args.tile_size),
                halo_yx=(halo, halo),
            )
            runs = tuple(
                _run_once(
                    source=source,
                    background_rms_source=prepared_sink,
                    manifest=manifest,
                    config=stage_config,
                    executor=executor,
                    executor_kind=executor_kind,
                    work_parent=work_parent,
                    repetition_index=index,
                    warmup=index < args.warmups,
                )
                for index in range(args.warmups + args.repetitions)
            )
        return runs, setup.wall_seconds

    if executor_kind is ExecutorKind.SERIAL:
        runs, setup_wall_seconds = run_with(SerialExecutor())
    else:
        with Client(
            n_workers=workers,
            threads_per_worker=threads_per_worker,
            processes=True,
            dashboard_address=None,
            memory_limit=worker_memory,
        ) as client:
            runs, setup_wall_seconds = run_with(DaskExecutor(client))

    structures = {
        (
            run.detection_island_count,
            run.reconstruction_island_count,
            run.scale_island_counts,
            run.partition_count,
            run.task_count,
            run.maximum_graph_width,
            run.maximum_batch_partition_count,
            run.maximum_read_pixel_count,
            run.maximum_workspace_bytes,
            run.maximum_retained_array_bytes,
            run.maximum_worker_bytes,
            run.boundary_summary_array_bytes,
            run.published_product_shard_count,
        )
        for run in runs
    }
    if len(structures) != 1:
        raise ValueError("Phase 5 benchmark repetitions changed structure")

    evidence = BenchmarkEvidence(
        schema_version=1,
        evidence_type="benchmark",
        run_id=f"phase-5-multiscale-{captured_at.strftime('%Y%m%d%H%M%S')}",
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
    last = runs[-1]
    measured = tuple(
        run.measurement.complete.wall_seconds
        for run in runs
        if not run.measurement.warmup
    )
    print(
        json.dumps(
            {
                "boundary_summary_array_bytes": (
                    last.boundary_summary_array_bytes
                ),
                "detection_island_count": last.detection_island_count,
                "evidence": str(args.output),
                "maximum_batch_partition_count": (
                    last.maximum_batch_partition_count
                ),
                "maximum_graph_width": last.maximum_graph_width,
                "maximum_read_pixel_count": last.maximum_read_pixel_count,
                "maximum_retained_array_bytes": (
                    last.maximum_retained_array_bytes
                ),
                "maximum_worker_bytes": last.maximum_worker_bytes,
                "maximum_workspace_bytes": last.maximum_workspace_bytes,
                "median_wall_seconds": sorted(measured)[len(measured) // 2],
                "partition_count": last.partition_count,
                "published_product_shard_count": (
                    last.published_product_shard_count
                ),
                "reconstruction_island_count": (
                    last.reconstruction_island_count
                ),
                "scale_island_counts": last.scale_island_counts,
                "setup_wall_seconds": setup_wall_seconds,
                "task_count": last.task_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
