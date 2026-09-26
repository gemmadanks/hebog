#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
"""Measure the deterministic traced-allocation peak of admitted size tiers.

The plan gates every public envelope raise on ``tracemalloc``'s peak, which is
compared within the documented tolerance, rather than on peak resident memory,
which varies by tens of percent with machine load. This runner measures that
peak.

Cases and finder settings come from ``config/benchmarks/quick-benchmark.json``,
so the peak is measured on exactly the inputs and settings the quick benchmark
times. Every repetition runs ``measure_traced_peak_worker.py`` in a fresh
single-thread process, which starts tracing before it imports Hebog. Nothing
here times anything for comparison: tracing roughly doubles wall time, so the
traced run stays out of the timing path and the quick benchmark never traces.

Evidence goes under ``benchmark-results/traced-peak/runs/<label>``, one
document for each case. Exit status is 1 when a case fails, or when repeated
repetitions of one case disagree, because a peak that is not reproduced cannot
gate a raise.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import hebog
from hebog.io import FitsImageSource
from hebog.validation.campaign_runtime import (
    canonical_sha256,
    dependency_inventory_sha256,
)
from hebog.validation.evidence import (
    ExecutorKind,
    SoftwareIdentity,
    write_evidence,
)
from hebog.validation.quick_benchmark import (
    SINGLE_THREAD_ENVIRONMENT,
    BenchmarkCase,
    BenchmarkTier,
    QuickBenchmarkConfiguration,
    development_dataset,
    load_quick_benchmark_configuration,
    local_resources,
    machine_identity,
    physical_memory_bytes,
    run_measured_process,
    source_tree_sha256,
    tier_cases,
    worker_environment,
)
from hebog.validation.quick_check import (
    PreparedCase,
    file_sha256,
    prepare_case,
    write_report,
)
from hebog.validation.traced_peak import (
    TracedPeakRun,
    admits,
    load_traced_peak_record,
    mebibytes,
    summarise_traced_peaks,
    traced_peak_evidence,
    traced_peaks,
)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIGURATION = _ROOT / "config/benchmarks/quick-benchmark.json"
_DEFAULT_OUTPUT = _ROOT / "benchmark-results/traced-peak"
_QUICK_CHECK_INPUTS = _ROOT / "benchmark-results/quick-check/inputs"
_WORKER = _ROOT / "scripts/benchmark/measure_traced_peak_worker.py"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--configuration", type=Path, default=_DEFAULT_CONFIGURATION
    )
    parser.add_argument(
        "--tier",
        choices=("smoke", "default", "large"),
        default="default",
        help="large also runs the default cases (default: default)",
    )
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument(
        "--label", help="run directory name (default: commit and time)"
    )
    parser.add_argument("--cases", nargs="+", help="run only these case IDs")
    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="traced runs per case; the peak is deterministic (default: 1)",
    )
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="fetch missing configured cut-outs",
    )
    return parser.parse_args()


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _default_label() -> str:
    dirty = "-dirty" if _git("status", "--porcelain") else ""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{_git('rev-parse', '--short', 'HEAD')}{dirty}-{stamp}"


def _shape_yx(prepared: PreparedCase) -> tuple[int, int]:
    metadata = FitsImageSource(
        prepared.input_path, prepared.supplied_metadata
    ).metadata()
    return metadata.shape_yx


def _supplied_metadata(case: BenchmarkCase) -> dict[str, float] | None:
    return cast(
        dict[str, float] | None, getattr(case.case, "supplied_metadata", None)
    )


def _configuration_sha256(
    configuration: QuickBenchmarkConfiguration, case: BenchmarkCase
) -> str:
    """Identify the input and settings a peak was measured at.

    This is the quick benchmark's own case identity, so a traced peak and a
    timing are recognisably the same measured configuration.
    """
    return canonical_sha256(
        {
            "case": case.model_dump(mode="json"),
            "executor": "serial",
            "hebog": configuration.hebog.model_dump(mode="json"),
            "thread_environment": dict(SINGLE_THREAD_ENVIRONMENT),
        }
    )


def _worker_command(
    *,
    input_path: Path,
    case_id: str,
    settings_json: str,
    supplied_metadata: dict[str, float] | None,
    shape_yx: tuple[int, int],
) -> list[str]:
    """Build the worker invocation that traces one repetition.

    The diagnostic size limit is always passed, set to the input's own long
    axis, so a raise candidate above the public envelope can be measured
    before its tier is admitted. The worker reports the limit it would have
    applied, and the report says whether the size is supported.
    """
    command = [
        sys.executable,
        str(_WORKER),
        "--input",
        str(input_path),
        "--run-id",
        case_id,
        "--settings",
        settings_json,
    ]
    if supplied_metadata is not None:
        command += ["--supplied-metadata", json.dumps(supplied_metadata)]
    return [*command, "--diagnostic-size-limit", str(max(shape_yx))]


def _trace_case(
    *,
    case: BenchmarkCase,
    prepared: PreparedCase,
    configuration: QuickBenchmarkConfiguration,
    repetitions: int,
) -> list[TracedPeakRun]:
    """Trace one case in a fresh process for each repetition."""
    command = _worker_command(
        input_path=prepared.input_path,
        case_id=case.case_id,
        settings_json=configuration.hebog.model_dump_json(),
        supplied_metadata=_supplied_metadata(case),
        shape_yx=_shape_yx(prepared),
    )
    runs: list[TracedPeakRun] = []
    for index in range(repetitions):
        # Products go to the system temporary directory, which macOS
        # Spotlight does not index, as the quick benchmark does.
        with TemporaryDirectory(prefix="hebog-traced-peak-") as temporary:
            result_path = Path(temporary) / "result.json"
            usage = run_measured_process(
                [
                    *command,
                    "--output-directory",
                    str(Path(temporary) / "products"),
                    "--result",
                    str(result_path),
                ],
                environment=worker_environment(os.environ),
                working_directory=_ROOT,
            )
            record = load_traced_peak_record(result_path)
        runs.append(TracedPeakRun(record=record, usage=usage))
        print(
            f"  run {index + 1}/{repetitions}: "
            f"{mebibytes(record.peak_traced_bytes):.1f} MiB traced in "
            f"{record.traced_wall_seconds:.1f} s",
            flush=True,
        )
    return runs


def _case_record(  # noqa: PLR0913
    case: BenchmarkCase,
    *,
    prepared: PreparedCase,
    configuration: QuickBenchmarkConfiguration,
    subject: SoftwareIdentity,
    environment_sha256: str,
    run_root: Path,
    repetitions: int,
) -> dict[str, Any]:
    """Trace one case and write its evidence, or record why it failed."""
    shape_yx = _shape_yx(prepared)
    record: dict[str, Any] = {
        "case_id": case.case_id,
        "tier": case.tier,
        "workload_class": case.workload_class.value,
        "input_sha256": prepared.input_sha256,
        "shape_yx": list(shape_yx),
    }
    print(f"{case.case_id} {record['shape_yx']}", flush=True)
    try:
        runs = _trace_case(
            case=case,
            prepared=prepared,
            configuration=configuration,
            repetitions=repetitions,
        )
    except (subprocess.CalledProcessError, OSError, ValueError) as error:
        return record | {
            "status": "failure",
            "error": f"{type(error).__name__}: {error}",
        }
    evidence = traced_peak_evidence(
        run_id=f"traced-peak-{case.case_id}",
        captured_at=datetime.now(UTC),
        dataset=development_dataset(
            case, content_sha256=prepared.input_sha256, shape_yx=shape_yx
        ),
        configuration_sha256=_configuration_sha256(configuration, case),
        subject=subject,
        environment_sha256=environment_sha256,
        resources=local_resources(
            ExecutorKind.SERIAL,
            allocated_cpu_cores=1,
            memory_bytes=physical_memory_bytes(),
        ),
        runs=runs,
    )
    evidence_path = run_root / case.case_id / "traced-peak.json"
    evidence_path.parent.mkdir(parents=True)
    write_evidence(evidence_path, evidence)
    summary = summarise_traced_peaks(traced_peaks(evidence))
    first = evidence.measurements[0]
    return record | {
        "status": "success",
        "admitted": admits(shape_yx, runs[0].record.public_size_limit_pixels),
        "public_size_limit_pixels": runs[0].record.public_size_limit_pixels,
        "peak": asdict(summary),
        "peak_mebibytes": summary.peak_mebibytes,
        "finder_peak_mebibytes": mebibytes(first.finder_peak_traced_bytes),
        "import_mebibytes": mebibytes(first.import_traced_bytes),
        "peak_rss_mebibytes": mebibytes(
            max(
                measurement.peak_rss_bytes
                for measurement in evidence.measurements
            )
        ),
        "source_count": first.source_count,
        "gaussian_component_count": first.gaussian_component_count,
        "traced_wall_seconds": first.traced_wall_seconds,
        "evidence": str(evidence_path),
    }


def _print_summary(report: dict[str, Any]) -> None:
    print(
        "case | size | admitted | traced peak MiB | finder MiB | imports MiB "
        "| reproduced | peak RSS MiB | traced s"
    )
    for case in report["cases"]:
        if case["status"] != "success":
            print(f"{case['case_id']} | {case['status']}: {case['error']}")
            continue
        print(
            " | ".join(
                (
                    case["case_id"],
                    "x".join(str(value) for value in case["shape_yx"]),
                    "yes" if case["admitted"] else "no",
                    f"{case['peak_mebibytes']:.2f}",
                    f"{case['finder_peak_mebibytes']:.2f}",
                    f"{case['import_mebibytes']:.2f}",
                    _reproduced_text(case["peak"]["reproduced"]),
                    f"{case['peak_rss_mebibytes']:.0f}",
                    f"{case['traced_wall_seconds']:.1f}",
                )
            )
        )


def _reproduced_text(reproduced: bool | None) -> str:
    """Report an unmeasured reproducibility as unmeasured, not as a pass."""
    if reproduced is None:
        return "-"
    return "yes" if reproduced else "NO"


def _unreproduced_cases(records: list[dict[str, Any]]) -> tuple[str, ...]:
    """Name every case whose repetitions disagreed on the peak.

    One repetition measures no reproducibility, so it is not a failure; two
    that disagree are, because the gate rests on a peak that repeats.
    """
    return tuple(
        record["case_id"]
        for record in records
        if record["status"] == "success"
        and record["peak"]["reproduced"] is False
    )


def _failed_cases(records: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        record["case_id"]
        for record in records
        if record["status"] != "success"
    )


def main() -> int:
    args = _parse_args()
    started = time.perf_counter()
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be at least 1")
    configuration = load_quick_benchmark_configuration(args.configuration)
    tier = cast(BenchmarkTier, args.tier)
    cases = tier_cases(configuration, tier)
    selected: set[str] = set(cast(list[str], args.cases or []))
    unknown = selected - {case.case_id for case in cases}
    if unknown:
        raise SystemExit(
            f"unknown case IDs for tier {tier}: {sorted(unknown)}"
        )
    label = args.label or _default_label()
    run_root = args.output_root.resolve() / "runs" / label
    if run_root.exists():
        raise SystemExit(f"run directory already exists: {run_root}")
    machine = machine_identity()
    environment_sha = canonical_sha256(
        {
            "machine": machine,
            "thread_environment": dict(SINGLE_THREAD_ENVIRONMENT),
        }
    )
    subject = SoftwareIdentity(
        name="hebog",
        version=hebog.__version__,
        commit_sha=_git("rev-parse", "HEAD"),
        source_tree_sha256=source_tree_sha256(_ROOT / "src/hebog"),
        dependency_inventory_sha256=dependency_inventory_sha256(),
    )
    # Every input is ready before any case is traced, so a missing one fails
    # the run before it spends traced work that no report would then record.
    prepared_cases = [
        (
            case,
            prepare_case(
                case.case,
                dataset_manifest=_ROOT / configuration.dataset_manifest,
                repository_root=_ROOT,
                inputs_root=_QUICK_CHECK_INPUTS,
                allow_download=args.allow_download,
            ),
        )
        for case in cases
        if not selected or case.case_id in selected
    ]
    records = [
        _case_record(
            case,
            prepared=prepared,
            configuration=configuration,
            subject=subject,
            environment_sha256=environment_sha,
            run_root=run_root,
            repetitions=args.repetitions,
        )
        for case, prepared in prepared_cases
    ]
    report: dict[str, Any] = {
        "schema_version": 1,
        "measurement_id": "traced-peak",
        "tier": tier,
        "label": label,
        "created_at": datetime.now(UTC).isoformat(),
        "hebog_version": hebog.__version__,
        "commit_sha": subject.commit_sha,
        "worktree_dirty": bool(_git("status", "--porcelain")),
        "source_tree_sha256": subject.source_tree_sha256,
        "configuration_sha256": file_sha256(args.configuration),
        "machine": machine,
        "repetitions": args.repetitions,
        "total_elapsed_seconds": time.perf_counter() - started,
        "cases": records,
    }
    write_report(run_root / "report.json", report)
    _print_summary(report)
    print(f"Report: {run_root / 'report.json'}")
    failed = _failed_cases(records)
    unreproduced = _unreproduced_cases(records)
    for case_id in unreproduced:
        print(
            f"NOT REPRODUCED {case_id}: repetitions disagreed on the peak, "
            "so it cannot gate an envelope raise"
        )
    return 1 if failed or unreproduced else 0


if __name__ == "__main__":
    raise SystemExit(main())
