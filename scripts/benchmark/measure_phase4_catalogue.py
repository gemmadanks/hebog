# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Measure the complete incremental Phase 4 compact catalogue path."""

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
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Generic, TypeVar

import psutil
from astropy.wcs import FITSFixedWarning
from distributed import Client

from hebog.adapters.rapthor_catalogue import write_rapthor_catalogue_fits
from hebog.algorithms.astrometry import compact_geometry_at_pixel
from hebog.algorithms.catalogue import (
    IncompleteCompactCatalogueError,
    complete_compact_catalogue,
)
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    CompactCatalogueConfig,
    CompactDeblendConfig,
    CompactGaussianFitConfig,
    CompactMomentConfig,
)
from hebog.data_models.images import ImageMetadata
from hebog.executors.base import Executor
from hebog.executors.dask import DaskExecutor
from hebog.executors.serial import SerialExecutor
from hebog.io import FitsImageSource, ZarrProductSink
from hebog.stages.catalogue import run_compact_catalogue_stage
from hebog.stages.detection import (
    DetectionStageConfig,
    DetectionStageResult,
    run_detection_stage,
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
    """One synchronous result and its process-level resource observation."""

    value: Result_co
    wall_seconds: float
    cpu_seconds: float
    peak_rss_bytes: int


@dataclass(frozen=True, slots=True)
class _TimedAttempt(Generic[Result_co]):
    """One result-or-typed-failure with complete timing evidence."""

    value: Result_co | None
    error: str | None
    wall_seconds: float
    cpu_seconds: float
    peak_rss_bytes: int


@dataclass(frozen=True, slots=True)
class _RunResult:
    """One incremental repetition plus structural output evidence."""

    measurement: Measurement
    planned_batch_count: int
    source_count: int
    component_count: int
    omission_count: int
    omission_reasons: tuple[tuple[str, int], ...]
    omission_objects: tuple[tuple[str, str], ...]
    deferred_island_count: int
    admitted_bounds_pixel_count: int
    maximum_processor_array_bytes: int
    completion_available: bool
    completion_error: str | None
    output_byte_count: int | None


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


def _configuration() -> tuple[
    DetectionStageConfig,
    CompactDeblendConfig,
    CompactMomentConfig,
    CompactGaussianFitConfig,
    CompactCatalogueConfig,
]:
    """Return the exact qualified Phase 4 candidate configuration."""
    return phase_four_candidate_configs()


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


def _measure_completion(
    function: Callable[[], Result_co],
) -> _TimedAttempt[Result_co]:
    """Measure catalogue completion while retaining its expected failure."""
    sampler = _ResidentMemorySampler()
    sampler.start()
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    value: Result_co | None = None
    error: str | None = None
    try:
        value = function()
    except IncompleteCompactCatalogueError as caught:
        error = str(caught)
    finally:
        peak_rss_bytes = sampler.stop()
    return _TimedAttempt(
        value=value,
        error=error,
        wall_seconds=time.perf_counter() - wall_started,
        cpu_seconds=time.process_time() - cpu_started,
        peak_rss_bytes=peak_rss_bytes,
    )


def _runtime_metrics(
    measured: _TimedResult[object] | _TimedAttempt[object],
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


def _stage_names(completion_available: bool) -> tuple[str, ...]:
    """Return the observable stages for success or fail-closed completion."""
    names = (
        "compact-measurement-fitting",
        "catalogue-reduction",
    )
    if completion_available:
        return (*names, "rapthor-catalogue-materialization")
    return names


def _run_once(  # noqa: PLR0913
    *,
    source: FitsImageSource,
    detection: DetectionStageResult,
    metadata: ImageMetadata,
    sink: ZarrProductSink,
    executor: Executor,
    executor_kind: ExecutorKind | str,
    deblend_config: CompactDeblendConfig,
    moment_config: CompactMomentConfig,
    fit_config: CompactGaussianFitConfig,
    catalogue_config: CompactCatalogueConfig,
    work_parent: Path,
    repetition_index: int,
    warmup: bool,
) -> _RunResult:
    """Measure worker fitting, bounded reduction, and compatibility output."""
    kind = ExecutorKind(executor_kind)
    counted = _CountingExecutor(executor)
    geometry = compact_geometry_at_pixel(
        metadata,
        (metadata.shape_yx[1] / 2.0, metadata.shape_yx[0] / 2.0),
    )
    stage = _measure(
        lambda: run_compact_catalogue_stage(
            source,
            detection,
            deblend_config=deblend_config,
            moment_config=moment_config,
            fit_config=fit_config,
            catalogue_config=catalogue_config,
            geometry=geometry,
            metadata=metadata,
            executor=counted,
            sink=sink,
        )
    )
    result = stage.value
    omissions = sum(len(shard.omissions) for shard in result.records)
    omission_reasons = Counter(
        omission.reason
        for shard in result.records
        for omission in shard.omissions
    )
    omission_objects = tuple(
        sorted(
            (omission.object_id, omission.reason)
            for shard in result.records
            for omission in shard.omissions
        )
    )
    completion = _measure_completion(
        lambda: complete_compact_catalogue(
            catalogue_id=f"phase-4-benchmark-{repetition_index:02d}",
            metadata=metadata,
            shards=result.records,
            deferred_island_ids=tuple(
                item.island.island_id for item in result.deferred_islands
            ),
            config=catalogue_config,
        )
    )
    materialization: _TimedResult[object] | None = None
    output_byte_count: int | None = None
    if completion.value is not None:
        output_path = work_parent / f"catalogue-{repetition_index:02d}.fits"
        materialization = _measure(
            lambda: write_rapthor_catalogue_fits(
                output_path,
                completion.value.catalogue,
            )
        )
        output_byte_count = materialization.value.byte_count
    stage_observations: list[
        tuple[str, _TimedResult[object] | _TimedAttempt[object], int]
    ] = [
        ("compact-measurement-fitting", stage, counted.task_count),
        ("catalogue-reduction", completion, 0),
    ]
    if materialization is not None:
        stage_observations.append(
            ("rapthor-catalogue-materialization", materialization, 0)
        )
    complete = _TimedResult(
        value=None,
        wall_seconds=sum(
            item.wall_seconds for _, item, _ in stage_observations
        ),
        cpu_seconds=sum(item.cpu_seconds for _, item, _ in stage_observations),
        peak_rss_bytes=max(
            item.peak_rss_bytes for _, item, _ in stage_observations
        ),
    )
    source_count = sum(len(shard.sources) for shard in result.records)
    component_count = sum(
        len(shard.gaussian_components) for shard in result.records
    )
    return _RunResult(
        measurement=Measurement(
            repetition_index=repetition_index,
            warmup=warmup,
            complete=_runtime_metrics(
                complete,
                executor_kind=kind,
                task_count=counted.task_count,
            ),
            stages=tuple(
                StageMetrics(
                    stage=name,
                    metrics=_runtime_metrics(
                        observation,
                        executor_kind=kind,
                        task_count=task_count,
                    ),
                )
                for name, observation, task_count in stage_observations
            ),
        ),
        planned_batch_count=result.planned_batch_count,
        source_count=source_count,
        component_count=component_count,
        omission_count=omissions,
        omission_reasons=tuple(sorted(omission_reasons.items())),
        omission_objects=omission_objects,
        deferred_island_count=len(result.deferred_islands),
        admitted_bounds_pixel_count=result.admitted_bounds_pixel_count,
        maximum_processor_array_bytes=result.maximum_processor_array_bytes,
        completion_available=completion.value is not None,
        completion_error=completion.error,
        output_byte_count=output_byte_count,
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
        return tuple(int(item) for item in process.cpu_affinity())
    except (AttributeError, NotImplementedError):
        return None


def main() -> None:
    """Run one cell and write exploratory typed evidence."""
    args = _parse_args()
    positive = (
        args.tile_size,
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
    (
        detection_config,
        deblend_config,
        moment_config,
        fit_config,
        catalogue_config,
    ) = _configuration()
    dependencies = {
        name: importlib.metadata.version(name) for name in _DEPENDENCIES
    }
    source_tree_sha256 = _source_tree_sha256()
    configuration = {
        "catalogue": asdict(catalogue_config),
        "component_boundary": "after-phase-3-compact-detection",
        "deblending": asdict(deblend_config),
        "executor": args.executor,
        "fit": asdict(fit_config),
        "moment": asdict(moment_config),
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

    def run_with(executor: Executor) -> tuple[tuple[_RunResult, ...], float]:
        """Prepare Phase 3 once and measure the incremental path repeatedly."""
        with (
            TemporaryDirectory(prefix="hebog-phase4-") as directory,
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore", FITSFixedWarning)
            work_parent = Path(directory)
            manifest = plan_image_partitions(
                image_shape_yx=metadata.shape_yx,
                tile_core_shape_yx=(args.tile_size, args.tile_size),
                halo_yx=(0, 0),
            )
            sink = ZarrProductSink(
                work_parent / "prepared-phase3.zarr",
                manifest,
                generation_id="phase-4-benchmark-prepared-phase3",
            )
            setup = _measure(
                lambda: run_detection_stage(
                    source,
                    manifest,
                    detection_config,
                    executor,
                    sink,
                )
            )
            runs = tuple(
                _run_once(
                    source=source,
                    detection=setup.value,
                    metadata=metadata,
                    sink=sink,
                    executor=executor,
                    executor_kind=executor_kind,
                    deblend_config=deblend_config,
                    moment_config=moment_config,
                    fit_config=fit_config,
                    catalogue_config=catalogue_config,
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

    evidence = BenchmarkEvidence(
        schema_version=1,
        evidence_type="benchmark",
        run_id=f"phase-4-catalogue-{captured_at.strftime('%Y%m%d%H%M%S')}",
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
                "completion_available": last.completion_available,
                "completion_error": last.completion_error,
                "component_count": last.component_count,
                "admitted_bounds_pixel_count": (
                    last.admitted_bounds_pixel_count
                ),
                "deferred_island_count": last.deferred_island_count,
                "evidence": str(args.output),
                "maximum_processor_array_bytes": (
                    last.maximum_processor_array_bytes
                ),
                "median_wall_seconds": sorted(measured)[len(measured) // 2],
                "omission_count": last.omission_count,
                "omission_objects": last.omission_objects,
                "omission_reasons": dict(last.omission_reasons),
                "output_byte_count": last.output_byte_count,
                "planned_batch_count": last.planned_batch_count,
                "setup_wall_seconds": setup_wall_seconds,
                "source_count": last.source_count,
                "stage_names": _stage_names(last.completion_available),
                "task_count": last.measurement.complete.dask_task_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
