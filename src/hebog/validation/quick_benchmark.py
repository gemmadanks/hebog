"""Quick end-to-end runtime benchmark for everyday development.

The quick benchmark times complete FITS-to-products runs of the public finder
on a few fixed images: one warm-up and five measured repetitions per case,
each in a fresh process. It compares median wall times with the previous
Hebog release and with pinned PyBDSF ``master``. Both baselines are immutable,
so their measurements are cached per machine and reused.

Measurements from one development machine detect regressions and show the
size of the gap. They are not the matched deployment gate: Hebog runs natively
with the serial executor, and the reference runs in its Linux container.
Loading this module never reads data or starts work.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.contracts import PreviousHebogGate, PyBdsfMasterGate
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
)
from hebog.validation.quick_check import (
    HebogSettings,
    QuickCheckCase,
    ReferenceSettings,
)

BenchmarkTier = Literal["smoke", "default", "large"]
"""Case set: CI smoke, the everyday default, or default plus large inputs."""

SINGLE_THREAD_ENVIRONMENT: Mapping[str, str] = {
    "MKL_NUM_THREADS": "1",
    "NUMBA_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
}
"""Thread limits for every timed process, matching CI and the reference."""

_INHERITED_PYTHON_VARIABLES = ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV")
_UNAVAILABLE_REASONS: Mapping[str, str] = {
    "array_copy_count": (
        "NumPy, Astropy and Zarr expose no complete array-copy counter"
    ),
    "array_copy_bytes": (
        "NumPy, Astropy and Zarr expose no complete array-copy counter"
    ),
    "dask_task_count": "the timed process uses no Dask scheduler",
    "transfer_bytes": "the timed process uses no Dask scheduler",
    "spill_bytes": "the timed process uses no Dask scheduler",
}


class _QuickBenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BenchmarkCase(_QuickBenchmarkModel):
    """One timed input, its tier and the work it represents."""

    tier: BenchmarkTier
    workload_class: WorkloadClass
    case: QuickCheckCase

    @property
    def case_id(self) -> str:
        """Return the identifier of the underlying input case."""
        return self.case.case_id


class QuickBenchmarkConfiguration(_QuickBenchmarkModel):
    """Versioned cases, finder settings and budget for the quick benchmark.

    Repetition counts and comparison rules come from the performance
    contract, so the benchmark cannot drift from the frozen gates.
    """

    schema_version: Literal[1]
    benchmark_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    performance_contract: str = Field(min_length=1)
    dataset_manifest: str = Field(min_length=1)
    hebog: HebogSettings
    reference: ReferenceSettings
    default_budget_seconds: float = Field(gt=0)
    cases: tuple[BenchmarkCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> QuickBenchmarkConfiguration:
        """Require unique case identifiers and a smoke and default case."""
        identifiers = [case.case_id for case in self.cases]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("quick-benchmark case identifiers must be unique")
        tiers = {case.tier for case in self.cases}
        if not {"smoke", "default"} <= tiers:
            raise ValueError(
                "quick benchmark needs at least one smoke and one default case"
            )
        return self


def load_quick_benchmark_configuration(
    path: Path,
) -> QuickBenchmarkConfiguration:
    """Load and validate one quick-benchmark configuration."""
    return QuickBenchmarkConfiguration.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def tier_cases(
    configuration: QuickBenchmarkConfiguration, tier: BenchmarkTier
) -> tuple[BenchmarkCase, ...]:
    """Return the cases a tier runs; ``large`` also runs the default cases."""
    included: set[BenchmarkTier] = (
        {"default", "large"} if tier == "large" else {tier}
    )
    return tuple(case for case in configuration.cases if case.tier in included)


@dataclass(frozen=True, slots=True)
class ProcessUsage:
    """Wall time, CPU time and peak resident memory of one measured span."""

    wall_seconds: float
    cpu_seconds: float
    peak_rss_bytes: int


def peak_rss_bytes(maximum_resident_set: int, system: str) -> int:
    """Convert ``ru_maxrss`` to bytes: macOS reports bytes, Linux KiB."""
    return (
        maximum_resident_set
        if system == "darwin"
        else (maximum_resident_set * 1024)
    )


def worker_environment(base: Mapping[str, str]) -> dict[str, str]:
    """Return an environment for a timed worker process.

    Inherited interpreter paths are removed, so a worker imports only the
    Hebog installed in the interpreter it runs with, and numerical libraries
    are limited to one thread.
    """
    environment = {
        name: value
        for name, value in base.items()
        if name not in _INHERITED_PYTHON_VARIABLES
    }
    return environment | dict(SINGLE_THREAD_ENVIRONMENT)


def run_measured_process(
    command: Sequence[str],
    *,
    environment: Mapping[str, str],
    working_directory: Path | None = None,
) -> ProcessUsage:
    """Run one command to completion and measure it.

    CPU time and peak memory come from ``wait4``, so they include every
    descendant the command waited for; the peak is that of the largest
    process, not a sum. Only POSIX systems provide ``wait4``.

    Raises:
        OSError: If this platform cannot measure a child process.
        subprocess.CalledProcessError: If the command exits unsuccessfully.
    """
    wait4 = getattr(os, "wait4", None)
    if wait4 is None:
        raise OSError("process measurement needs os.wait4 (macOS or Linux)")
    started = time.perf_counter()
    process = subprocess.Popen(
        list(command), env=dict(environment), cwd=working_directory
    )
    _, status, usage = wait4(process.pid, 0)
    wall_seconds = time.perf_counter() - started
    process.returncode = os.waitstatus_to_exitcode(status)
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, list(command))
    return ProcessUsage(
        wall_seconds=wall_seconds,
        cpu_seconds=usage.ru_utime + usage.ru_stime,
        peak_rss_bytes=peak_rss_bytes(usage.ru_maxrss, sys.platform),
    )


@dataclass(frozen=True, slots=True)
class Repetition:
    """One timed run: the whole process and its source-finding call."""

    warmup: bool
    complete: ProcessUsage
    finder: ProcessUsage


def _runtime_metrics(usage: ProcessUsage) -> RuntimeMetrics:
    return RuntimeMetrics(
        wall_seconds=usage.wall_seconds,
        cpu_seconds=usage.cpu_seconds,
        peak_rss_bytes=usage.peak_rss_bytes,
        array_copy_count=None,
        array_copy_bytes=None,
        dask_task_count=None,
        transfer_bytes=None,
        spill_bytes=None,
        unavailable_metrics=tuple(
            UnavailableMetric.model_validate(
                {"metric": metric, "reason": reason}
            )
            for metric, reason in _UNAVAILABLE_REASONS.items()
        ),
    )


def local_resources(
    executor: ExecutorKind,
    *,
    allocated_cpu_cores: int,
    memory_bytes: int,
) -> ResourceAllocation:
    """Describe one process on the local development machine."""
    return ResourceAllocation(
        executor=executor,
        worker_nodes=1,
        workers_per_node=1,
        threads_per_worker=allocated_cpu_cores,
        allocated_cpu_cores=allocated_cpu_cores,
        node_memory_bytes=memory_bytes,
        worker_memory_limit_bytes=memory_bytes,
        reserved_headroom_per_node_bytes=0,
        storage_identifier="local-filesystem",
    )


def benchmark_evidence(  # noqa: PLR0913
    *,
    run_id: str,
    captured_at: datetime,
    dataset: DatasetIdentity,
    configuration_sha256: str,
    subject: SoftwareIdentity,
    environment_sha256: str,
    resources: ResourceAllocation,
    finder_stage: str,
    repetitions: Sequence[Repetition],
) -> BenchmarkEvidence:
    """Record every repetition of one case as exploratory evidence.

    Quick-benchmark evidence stays exploratory: it is reviewed, if ever,
    only as part of a named performance decision.
    """
    return BenchmarkEvidence(
        schema_version=1,
        evidence_type="benchmark",
        run_id=run_id,
        captured_at=captured_at,
        status=EvidenceStatus.EXPLORATORY,
        dataset=dataset,
        configuration_sha256=configuration_sha256,
        subject=subject,
        environment_sha256=environment_sha256,
        resources=resources,
        measurements=tuple(
            Measurement(
                repetition_index=index,
                warmup=repetition.warmup,
                complete=_runtime_metrics(repetition.complete),
                stages=(
                    StageMetrics(
                        stage=finder_stage,
                        metrics=_runtime_metrics(repetition.finder),
                    ),
                ),
            )
            for index, repetition in enumerate(repetitions)
        ),
    )


def development_dataset(
    case: BenchmarkCase, *, content_sha256: str, shape_yx: tuple[int, int]
) -> DatasetIdentity:
    """Identify one benchmark input; every case has the development role."""
    return DatasetIdentity(
        identifier=case.case_id,
        role=DatasetRole.DEVELOPMENT,
        content_sha256=content_sha256,
        shape_yx=shape_yx,
        workload_class=case.workload_class,
    )


def measured_wall_seconds(evidence: BenchmarkEvidence) -> tuple[float, ...]:
    """Return complete wall times of the measured, non-warm-up repetitions."""
    return tuple(
        measurement.complete.wall_seconds
        for measurement in evidence.measurements
        if not measurement.warmup
    )


@dataclass(frozen=True, slots=True)
class TimingSummary:
    """Median and dispersion of measured wall times."""

    repetitions: int
    median_seconds: float
    minimum_seconds: float
    maximum_seconds: float
    median_absolute_deviation_seconds: float


def summarise_timings(values: Sequence[float]) -> TimingSummary:
    """Summarise measured wall times by their median and spread."""
    if not values:
        raise ValueError("at least one measured repetition is required")
    centre = median(values)
    return TimingSummary(
        repetitions=len(values),
        median_seconds=centre,
        minimum_seconds=min(values),
        maximum_seconds=max(values),
        median_absolute_deviation_seconds=median(
            abs(value - centre) for value in values
        ),
    )


@dataclass(frozen=True, slots=True)
class MedianRatio:
    """Candidate-to-baseline median ratio with one-sided bootstrap bounds.

    ``lower_bound`` and ``upper_bound`` are each a one-sided bound at the
    requested confidence level, not the ends of one two-sided interval.
    """

    ratio: float
    lower_bound: float
    upper_bound: float


def median_ratio(
    candidate: Sequence[float],
    baseline: Sequence[float],
    *,
    resamples: int,
    confidence_level: float,
    seed: int = 0,
) -> MedianRatio:
    """Bootstrap the ratio of the candidate median to the baseline median.

    Each sample is resampled independently with replacement. The fixed seed
    makes the bounds reproducible for the same timings.

    >>> bounds = median_ratio(
    ...     [2.0, 2.0, 2.0], [1.0, 1.0, 1.0],
    ...     resamples=1000, confidence_level=0.95,
    ... )
    >>> (bounds.ratio, bounds.lower_bound, bounds.upper_bound)
    (2.0, 2.0, 2.0)
    """
    if not candidate or not baseline:
        raise ValueError("both samples need at least one measurement")
    generator = np.random.default_rng(seed)
    candidate_values = np.asarray(candidate, dtype=np.float64)
    baseline_values = np.asarray(baseline, dtype=np.float64)
    candidate_medians = np.median(
        generator.choice(
            candidate_values, size=(resamples, candidate_values.size)
        ),
        axis=1,
    )
    baseline_medians = np.median(
        generator.choice(
            baseline_values, size=(resamples, baseline_values.size)
        ),
        axis=1,
    )
    ratios = candidate_medians / baseline_medians
    return MedianRatio(
        ratio=float(np.median(candidate_values) / np.median(baseline_values)),
        lower_bound=float(np.quantile(ratios, 1.0 - confidence_level)),
        upper_bound=float(np.quantile(ratios, confidence_level)),
    )


ComparisonOutcome = Literal["pass", "inconclusive", "fail"]
"""Whether both ratio bounds, neither, or only one lies within a limit."""


def ratio_outcome(ratio: MedianRatio, limit: float) -> ComparisonOutcome:
    """Classify a ratio against a limit it must not exceed.

    The upper bound within the limit passes, the lower bound beyond it
    fails, and bounds on either side of the limit are inconclusive.

    >>> ratio_outcome(MedianRatio(1.0, 0.98, 1.02), 1.05)
    'pass'
    >>> ratio_outcome(MedianRatio(1.05, 1.01, 1.09), 1.05)
    'inconclusive'
    >>> ratio_outcome(MedianRatio(1.2, 1.1, 1.3), 1.05)
    'fail'
    """
    if ratio.upper_bound <= limit:
        return "pass"
    if ratio.lower_bound > limit:
        return "fail"
    return "inconclusive"


@dataclass(frozen=True, slots=True)
class BaselineComparison:
    """Comparison of current timings with one cached baseline."""

    baseline: Literal["previous-release", "pybdsf-master"]
    ratio: MedianRatio
    outcome: ComparisonOutcome


def compare_with_previous_release(
    current: Sequence[float],
    previous: Sequence[float],
    gate: PreviousHebogGate,
) -> BaselineComparison:
    """Compare with the previous release under the non-regression rule.

    An upper ratio bound within the gate passes; a lower bound beyond it is
    a regression.
    """
    ratio = median_ratio(
        current,
        previous,
        resamples=gate.bootstrap_resamples,
        confidence_level=gate.confidence_level,
    )
    return BaselineComparison(
        baseline="previous-release",
        ratio=ratio,
        outcome=ratio_outcome(ratio, gate.regression_ratio_lower_bound),
    )


def compare_with_pybdsf_master(
    current: Sequence[float],
    reference: Sequence[float],
    gate: PyBdsfMasterGate,
    *,
    resamples: int,
) -> BaselineComparison:
    """Compare with pinned ``master`` against the deployment ratio.

    On the quick benchmark this is diagnostic: the environments differ, so
    only the matched M4 benchmark can pass the deployment gate.
    """
    ratio = median_ratio(
        current,
        reference,
        resamples=resamples,
        confidence_level=gate.confidence_level,
    )
    return BaselineComparison(
        baseline="pybdsf-master",
        ratio=ratio,
        outcome=ratio_outcome(ratio, gate.maximum_ratio),
    )


def _processor_name() -> str:
    if sys.platform == "darwin":
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown"


def physical_memory_bytes() -> int:
    """Return the machine's physical memory on POSIX systems."""
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def machine_identity() -> dict[str, object]:
    """Describe the hardware and operating system that timings depend on.

    Cached baseline timings are keyed by this identity, so they are measured
    again after a hardware or operating-system change.
    """
    return {
        "logical_cpus": os.cpu_count(),
        "machine": platform.machine(),
        "memory_bytes": physical_memory_bytes(),
        "processor": _processor_name(),
        "release": platform.release(),
        "system": platform.system(),
    }


def source_tree_sha256(package_root: Path) -> str:
    """Hash every file of one package tree, ignoring bytecode caches."""
    digest = hashlib.sha256()
    for path in sorted(
        item
        for item in package_root.rglob("*")
        if item.is_file() and "__pycache__" not in item.parts
    ):
        digest.update(path.relative_to(package_root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
