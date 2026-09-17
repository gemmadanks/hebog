"""Configuration, measurement, statistics and evidence of the benchmark."""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hebog.validation.contracts import load_performance_matrix
from hebog.validation.evidence import (
    BenchmarkEvidence,
    EvidenceStatus,
    ExecutorKind,
    SoftwareIdentity,
    WorkloadClass,
    load_evidence,
)
from hebog.validation.quick_benchmark import (
    SINGLE_THREAD_ENVIRONMENT,
    ProcessUsage,
    Repetition,
    benchmark_evidence,
    compare_with_previous_release,
    compare_with_pybdsf_master,
    development_dataset,
    load_quick_benchmark_configuration,
    local_resources,
    machine_identity,
    measured_wall_seconds,
    median_ratio,
    peak_rss_bytes,
    physical_memory_bytes,
    run_measured_process,
    source_tree_sha256,
    summarise_timings,
    tier_cases,
    worker_environment,
)
from hebog.validation.quick_check import GeneratedCase

_ROOT = Path(__file__).parents[3]
_CONFIGURATION = _ROOT / "config/benchmarks/quick-benchmark.json"
_CONTRACT = load_performance_matrix(
    _ROOT / "config/benchmarks/phase-0-performance.json"
)
_SHA = "a" * 64
_POSIX_ONLY = pytest.mark.skipif(
    not hasattr(os, "wait4"), reason="process measurement needs os.wait4"
)
_SYSCONF_ONLY = pytest.mark.skipif(
    not hasattr(os, "sysconf"), reason="physical memory needs os.sysconf"
)


def test_checked_in_configuration_defines_every_tier() -> None:
    """Smoke is small, default is 1,024², large adds larger real cut-outs."""
    configuration = load_quick_benchmark_configuration(_CONFIGURATION)

    smoke = tier_cases(configuration, "smoke")
    default = tier_cases(configuration, "default")
    large = tier_cases(configuration, "large")

    assert [case.case_id for case in smoke] == ["compact-snr-ladder"]
    assert any(isinstance(case.case, GeneratedCase) for case in default)
    assert sum(case.case.kind == "image" for case in default) >= 2
    default_ids = {case.case_id for case in default}
    assert default_ids < {case.case_id for case in large}
    assert all(case.tier in {"default", "large"} for case in large)
    windows = [
        case.case.remote_source.window.size
        for case in large
        if case.tier == "large"
        and case.case.kind == "image"
        and case.case.remote_source is not None
    ]
    assert max(windows) >= 3600
    assert (_ROOT / configuration.performance_contract).exists()


def test_configuration_needs_unique_cases_and_smoke_and_default_tiers(
    tmp_path: Path,
) -> None:
    """A duplicate identifier or a missing tier is rejected."""
    document = json.loads(_CONFIGURATION.read_text(encoding="utf-8"))
    duplicated = document | {
        "cases": [*document["cases"], document["cases"][0]]
    }
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(duplicated))
    with pytest.raises(ValidationError, match="must be unique"):
        load_quick_benchmark_configuration(path)

    without_smoke = document | {
        "cases": [
            case for case in document["cases"] if case["tier"] != "smoke"
        ]
    }
    path.write_text(json.dumps(without_smoke))
    with pytest.raises(ValidationError, match="smoke and one default"):
        load_quick_benchmark_configuration(path)


def test_peak_memory_units_follow_the_operating_system() -> None:
    """``ru_maxrss`` is bytes on macOS and KiB on Linux."""
    assert peak_rss_bytes(4096, "darwin") == 4096
    assert peak_rss_bytes(4096, "linux") == 4096 * 1024


def test_worker_environment_isolates_the_interpreter_and_threads() -> None:
    """Inherited import paths are removed and libraries use one thread."""
    environment = worker_environment(
        {
            "PATH": "/bin",
            "PYTHONPATH": "/repository/src",
            "VIRTUAL_ENV": "/repository/.venv",
            "OMP_NUM_THREADS": "8",
        }
    )

    assert environment["PATH"] == "/bin"
    assert "PYTHONPATH" not in environment
    assert "VIRTUAL_ENV" not in environment
    assert environment["OMP_NUM_THREADS"] == "1"
    assert set(SINGLE_THREAD_ENVIRONMENT) <= set(environment)


@_POSIX_ONLY
def test_measured_process_reports_its_own_cpu_and_memory() -> None:
    """A busy child is measured through wait4, not the parent's usage."""
    usage = run_measured_process(
        [
            sys.executable,
            "-c",
            "values = bytearray(64 * 2**20)\ntotal = sum(range(3_000_000))",
        ],
        environment=dict(os.environ),
    )

    assert usage.wall_seconds > 0
    assert usage.cpu_seconds > 0
    assert usage.peak_rss_bytes >= 64 * 2**20


@_POSIX_ONLY
def test_measured_process_failure_raises() -> None:
    """A failed repetition is an error, never a timing."""
    with pytest.raises(subprocess.CalledProcessError):
        run_measured_process(
            [sys.executable, "-c", "raise SystemExit(3)"],
            environment=dict(os.environ),
        )


def test_timing_summary_reports_median_and_spread() -> None:
    """The median and its absolute deviation resist one slow repetition."""
    summary = summarise_timings([10.0, 11.0, 9.0, 10.0, 30.0])

    assert summary.repetitions == 5
    assert summary.median_seconds == 10.0
    assert summary.minimum_seconds == 9.0
    assert summary.maximum_seconds == 30.0
    assert summary.median_absolute_deviation_seconds == 1.0
    with pytest.raises(ValueError, match="at least one"):
        summarise_timings([])


def test_median_ratio_bounds_are_reproducible_and_ordered() -> None:
    """Bootstrap bounds bracket the observed ratio for a fixed seed."""
    candidate = [10.0, 10.5, 9.8, 10.2, 11.0]
    baseline = [5.0, 5.2, 4.9, 5.1, 5.3]

    first = median_ratio(
        candidate, baseline, resamples=2000, confidence_level=0.95
    )
    second = median_ratio(
        candidate, baseline, resamples=2000, confidence_level=0.95
    )

    assert first == second
    assert first.lower_bound <= first.ratio <= first.upper_bound
    assert first.ratio == pytest.approx(10.2 / 5.1)
    with pytest.raises(ValueError, match="at least one"):
        median_ratio([], baseline, resamples=10, confidence_level=0.95)


def test_previous_release_outcome_follows_both_ratio_bounds() -> None:
    """A lower bound above 1.05 regresses; straddling it is inconclusive."""
    gate = _CONTRACT.previous_hebog
    previous = [10.0, 10.1, 9.9, 10.0, 10.2]

    unchanged = compare_with_previous_release(
        [10.1, 9.8, 10.0, 10.3, 9.9], previous, gate
    )
    uncertain = compare_with_previous_release(
        [10.5, 9.5, 11.5, 10.4, 10.8], previous, gate
    )
    slower = compare_with_previous_release(
        [12.0, 12.1, 11.9, 12.2, 12.0], previous, gate
    )

    assert unchanged.outcome == "pass"
    assert unchanged.ratio.upper_bound <= gate.regression_ratio_lower_bound
    assert uncertain.outcome == "inconclusive"
    assert slower.outcome == "fail"
    assert slower.ratio.lower_bound > gate.regression_ratio_lower_bound


def test_master_comparison_uses_the_deployment_ratio() -> None:
    """The deployment ratio passes only when the upper bound is within it."""
    gate = _CONTRACT.pybdsf_master
    reference = [10.0, 10.1, 9.9, 10.0, 10.2]

    faster = compare_with_pybdsf_master(
        [4.0, 4.1, 3.9, 4.0, 4.2], reference, gate, resamples=2000
    )
    slower = compare_with_pybdsf_master(
        [6.0, 6.1, 5.9, 6.0, 6.2], reference, gate, resamples=2000
    )

    assert faster.outcome == "pass" and faster.baseline == "pybdsf-master"
    assert slower.outcome == "fail"
    assert slower.ratio.lower_bound > gate.maximum_ratio


def _evidence() -> BenchmarkEvidence:
    configuration = load_quick_benchmark_configuration(_CONFIGURATION)
    case = tier_cases(configuration, "smoke")[0]
    usage = ProcessUsage(wall_seconds=2.0, cpu_seconds=1.5, peak_rss_bytes=10)
    finder = ProcessUsage(wall_seconds=1.0, cpu_seconds=1.0, peak_rss_bytes=9)
    return benchmark_evidence(
        run_id="quick-benchmark-compact-snr-ladder",
        captured_at=datetime(2026, 9, 17, tzinfo=UTC),
        dataset=development_dataset(
            case, content_sha256=_SHA, shape_yx=(512, 512)
        ),
        configuration_sha256=_SHA,
        subject=SoftwareIdentity(
            name="hebog",
            version="0.8.0",
            dependency_inventory_sha256=_SHA,
        ),
        environment_sha256=_SHA,
        resources=local_resources(
            ExecutorKind.SERIAL, allocated_cpu_cores=1, memory_bytes=2**34
        ),
        finder_stage="find-sources",
        repetitions=[
            Repetition(warmup=index == 0, complete=usage, finder=finder)
            for index in range(6)
        ],
    )


def test_evidence_records_every_repetition_as_exploratory(
    tmp_path: Path,
) -> None:
    """Evidence round-trips, explains unavailable metrics and skips warm-up."""
    evidence = _evidence()
    path = tmp_path / "evidence.json"
    path.write_text(evidence.model_dump_json())

    loaded = load_evidence(path)

    assert loaded == evidence
    assert evidence.status is EvidenceStatus.EXPLORATORY
    assert evidence.dataset.workload_class is WorkloadClass.EMPTY_SPARSE
    assert measured_wall_seconds(evidence) == (2.0,) * 5
    metrics = evidence.measurements[0].complete
    assert metrics.dask_task_count is None
    assert {item.metric for item in metrics.unavailable_metrics} == {
        "array_copy_count",
        "array_copy_bytes",
        "dask_task_count",
        "transfer_bytes",
        "spill_bytes",
    }
    assert evidence.measurements[0].stages[0].stage == "find-sources"


def test_source_tree_identity_ignores_bytecode_caches(tmp_path: Path) -> None:
    """Content and paths change the identity; ``__pycache__`` does not."""
    package = tmp_path / "hebog"
    package.mkdir()
    (package / "module.py").write_text("value = 1\n")
    first = source_tree_sha256(package)

    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "module.pyc").write_bytes(b"cache")
    assert source_tree_sha256(package) == first

    (package / "module.py").write_text("value = 2\n")
    assert source_tree_sha256(package) != first


def test_physical_memory_needs_sysconf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without POSIX sysconf, as on Windows, memory is a clear OSError."""
    monkeypatch.delattr(os, "sysconf", raising=False)

    with pytest.raises(OSError, match=r"os\.sysconf"):
        physical_memory_bytes()


@_SYSCONF_ONLY
def test_machine_identity_describes_hardware_and_system() -> None:
    """Cached baselines are keyed by the processor, memory and system."""
    identity = machine_identity()

    assert set(identity) == {
        "logical_cpus",
        "machine",
        "memory_bytes",
        "processor",
        "release",
        "system",
    }


def test_runner_caches_baseline_evidence_and_failures(tmp_path: Path) -> None:
    """A baseline is measured once; a failed baseline is not retried."""
    runner: dict[str, Any] = runpy.run_path(
        str(_ROOT / "scripts/benchmark/quick_benchmark.py")
    )
    cached_or_measured = runner["_cached_or_measured"]
    calls: list[str] = []

    def measure() -> BenchmarkEvidence:
        calls.append("measure")
        return _evidence()

    def fail() -> BenchmarkEvidence:
        calls.append("fail")
        raise subprocess.CalledProcessError(1, ["worker"])

    status, _ = cached_or_measured(tmp_path / "ok", measure, description="ok")
    assert status == "measured"
    status, evidence = cached_or_measured(
        tmp_path / "ok", measure, description="ok"
    )
    assert (status, evidence) == ("cached", _evidence())
    assert cached_or_measured(tmp_path / "bad", fail, description="bad") == (
        "failed",
        None,
    )
    assert cached_or_measured(tmp_path / "bad", fail, description="bad") == (
        "failed",
        None,
    )
    assert runner["_cached_failure"](tmp_path / "bad") == (
        "CalledProcessError: Command '['worker']' returned non-zero exit "
        "status 1."
    )
    status, _ = cached_or_measured(
        tmp_path / "ok", measure, description="ok", refresh=True
    )
    assert status == "measured"
    assert calls == ["measure", "fail", "measure"]


def _runner() -> dict[str, Any]:
    return runpy.run_path(str(_ROOT / "scripts/benchmark/quick_benchmark.py"))


def test_every_baseline_identity_includes_the_measurement_revision() -> None:
    """Changing how repetitions run remeasures Hebog and PyBDSF baselines."""
    runner = _runner()
    machine: dict[str, object] = {"processor": "arm"}

    identity = runner["_baseline_identity"](
        {"container_image_id": "image"}, machine=machine, contract=_CONTRACT
    )

    assert identity == {
        "container_image_id": "image",
        "machine": machine,
        "measurement_revision": runner["_MEASUREMENT_REVISION"],
        "protocol": _CONTRACT.previous_hebog.model_dump(mode="json"),
    }


def _case_record(
    case_id: str, *, previous_release: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "status": "success",
        "previous_release": previous_release,
    }


def test_missing_previous_release_is_reported_without_failing() -> None:
    """A baseline that cannot be measured is named, not a silent pass."""
    runner = _runner()
    records = [
        _case_record(
            "passed", previous_release={"comparison": {"outcome": "pass"}}
        ),
        _case_record("unchecked", previous_release={"status": "failed"}),
        _case_record("skipped", previous_release=None),
    ]

    outcome = runner["_run_outcome"](records)

    assert outcome.failed_cases == ()
    assert outcome.regressions == ()
    assert outcome.unchecked_cases == ("unchecked",)
    assert outcome.exit_status == 0


def test_failed_cases_and_regressions_fail_the_run() -> None:
    """A failed case or a previous-release regression exits non-zero."""
    runner = _runner()
    regressed = _case_record(
        "slower", previous_release={"comparison": {"outcome": "fail"}}
    )
    failed = {"case_id": "broken", "status": "failure", "error": "boom"}

    regression = runner["_run_outcome"]([regressed])
    failure = runner["_run_outcome"]([failed])

    assert (regression.regressions, regression.exit_status) == (("slower",), 1)
    assert (failure.failed_cases, failure.exit_status) == (("broken",), 1)


def test_budget_is_not_assessed_when_a_case_failed() -> None:
    """A failed case's time is missing, so the total cannot pass a budget."""
    runner = _runner()
    within_budget = runner["_within_budget"]
    complete = runner["_run_outcome"](
        [_case_record("ok", previous_release=None)]
    )
    incomplete = runner["_run_outcome"](
        [{"case_id": "broken", "status": "failure", "error": "boom"}]
    )

    assert within_budget(10.0, 600.0, complete) is True
    assert within_budget(900.0, 600.0, complete) is False
    assert within_budget(10.0, 600.0, incomplete) is None
    assert within_budget(10.0, None, complete) is None
