#!/usr/bin/env python3
"""Profile how one sector's run scales with its executor's workers.

Plan task 73. For each executor's cases from
``config/benchmarks/sector-scaling-profile.json`` (the 10,000² LoTSS-DR3
anchor and the whole 15,402² mosaic) and each of its worker counts, this
runs ``profile_complete_execution.py`` once, in its own process, under
``runs/<label>/<case>/<executor>-<workers>``. Every run admits the same
memory to its tasks, ``--memory-budget-bytes``: the thread executor's whole
budget, or split evenly between the Dask workers' memory limits.
``--with-flat-noise`` pairs each image with itself as its flat-noise
counterpart, as Rapthor's sectors are analysed.

A configuration that fails, as one does when a Dask worker's share of the
budget is smaller than the largest task declares, is recorded with its
error beside its log, and the sweep goes on. A finished configuration is
not run again, so an interrupted sweep resumes where it stopped; an
unfinished one is removed and run again. ``scaling.json`` then summarises
every case under every executor (``hebog.validation.scaling_profile``).
Task 73 ran Dask at five counts on both cases and threads at two on the
anchor, since its pilot found the thread path barely faster on 12 threads::

    just profile-scaling --label task73 --memory-budget-bytes 16000000000 \\
        --thread-workers 1 12 --thread-cases lotss-dr3-1312-dense-10000

A profile is diagnostic: it ranks costs and never establishes a speedup,
which needs the quick benchmark.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hebog.validation.execution_profile import load_profile_configuration
from hebog.validation.quick_benchmark import (
    checkout_identity,
    machine_identity,
)
from hebog.validation.quick_check import file_sha256, write_report
from hebog.validation.scaling_profile import (
    ScalingPoint,
    scaling_point,
    scaling_summary,
)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIGURATION = (
    _ROOT / "config/benchmarks/sector-scaling-profile.json"
)
_DEFAULT_OUTPUT = _ROOT / "benchmark-results/profiles"
_PROFILER = _ROOT / "scripts/benchmark/profile_complete_execution.py"
_EXECUTOR_FLAGS = {"threads": "--threads", "dask": "--dask-workers"}
# The last line of a Python traceback names the exception.
_EXCEPTION_LINE = re.compile(r"^[\w.]+(Error|Exception)\b.*$", re.MULTILINE)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--configuration", type=Path, default=_DEFAULT_CONFIGURATION
    )
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--label", required=True, help="run directory name")
    for flag, executor in (("thread", "threads"), ("dask", "dask")):
        parser.add_argument(
            f"--{flag}-workers",
            nargs="*",
            type=int,
            default=[1, 2, 4, 8, 12],
            help=f"worker counts on {executor}; none skips it",
        )
        parser.add_argument(
            f"--{flag}-cases",
            nargs="+",
            help=f"case IDs to run on {executor}; every case by default",
        )
    parser.add_argument(
        "--memory-budget-bytes",
        type=int,
        required=True,
        help="memory admitted to every run's tasks",
    )
    parser.add_argument(
        "--with-flat-noise",
        action="store_true",
        help="pair each image with itself as its flat-noise counterpart",
    )
    parser.add_argument(
        "--summarise-existing",
        action="store_true",
        help="summarise the configurations already run",
    )
    return parser.parse_args()


def _configuration_root(
    run_root: Path, case_id: str, executor: str, workers: int
) -> Path:
    return run_root / case_id / f"{executor}-{workers}"


def _run_configuration(
    args: argparse.Namespace,
    run_root: Path,
    case_id: str,
    executor: str,
    workers: int,
) -> None:
    """Profile one case at one worker count, unless it already finished."""
    root = _configuration_root(run_root, case_id, executor, workers)
    if (root / "summary.json").exists() or (root / "failure.json").exists():
        return
    shutil.rmtree(root, ignore_errors=True)
    root.parent.mkdir(parents=True, exist_ok=True)
    log = root.parent / f"{executor}-{workers}.log"
    command = [
        sys.executable,
        str(_PROFILER),
        "--configuration",
        str(args.configuration.resolve()),
        "--output-root",
        str(args.output_root.resolve()),
        "--label",
        root.relative_to(args.output_root.resolve() / "runs").as_posix(),
        "--cases",
        case_id,
        _EXECUTOR_FLAGS[executor],
        str(workers),
        "--memory-budget-bytes",
        str(args.memory_budget_bytes),
    ]
    if args.with_flat_noise:
        command.append("--with-flat-noise")
    print(f"{case_id} {executor} {workers}", flush=True)
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as output:
        completed = subprocess.run(
            command, stdout=output, stderr=subprocess.STDOUT, check=False
        )
    if completed.returncode == 0:
        return
    # The profiler reports the worker's failure as its own
    # CalledProcessError; the worker's exception is the cause.
    errors = [
        match.group(0)
        for match in _EXCEPTION_LINE.finditer(log.read_text("utf-8"))
        if not match.group(0).startswith("subprocess.CalledProcessError")
    ]
    root.mkdir(parents=True, exist_ok=True)
    write_report(
        root / "failure.json",
        {
            "case_id": case_id,
            "executor": executor,
            "workers": workers,
            "return_code": completed.returncode,
            "elapsed_seconds": time.perf_counter() - started,
            # The run's own exception comes last, after any it chained.
            "errors": errors[-3:],
            "log": log.name,
        },
    )


def _case_summary(
    run_root: Path, case_id: str, executor: str, workers: list[int]
) -> dict[str, Any]:
    """Summarise one case under one executor from its finished runs."""
    points: list[ScalingPoint] = []
    failures: list[dict[str, Any]] = []
    input_identity: dict[str, Any] = {}
    for count in workers:
        root = _configuration_root(run_root, case_id, executor, count)
        case_file = root / case_id / "case.json"
        if case_file.exists():
            record = json.loads(case_file.read_text("utf-8"))
            input_identity = {
                "input_sha256": record["input_sha256"],
                "shape_yx": record["shape_yx"],
            }
            points.append(scaling_point(record["profile"]))
        elif (root / "failure.json").exists():
            failures.append(json.loads((root / "failure.json").read_text()))
    document: dict[str, Any] = input_identity | {"failures": failures}
    if any(point.workers == 1 for point in points):
        document |= scaling_summary(points)
    return document


def _requested_runs(
    args: argparse.Namespace, case_ids: list[str]
) -> dict[str, tuple[list[int], list[str]]]:
    """Return each executor's worker counts and case IDs to run."""
    requested = {
        "threads": (args.thread_workers, args.thread_cases),
        "dask": (args.dask_workers, args.dask_cases),
    }
    runs = {
        executor: (list(workers), list(cases or case_ids))
        for executor, (workers, cases) in requested.items()
        if workers
    }
    unknown = {
        case_id for _, cases in runs.values() for case_id in cases
    } - set(case_ids)
    if unknown:
        raise SystemExit(f"unknown case IDs: {sorted(unknown)}")
    return runs


def _print_summary(cases: dict[str, dict[str, dict[str, Any]]]) -> None:
    for case_id, executors in cases.items():
        for executor, summary in executors.items():
            for row in summary.get("curve", []):
                print(
                    f"{case_id} {executor} {row['workers']:>2}: "
                    f"{row['wall_seconds']:8.1f} s, speedup "
                    f"{row['speedup']:.2f}, idle "
                    f"{row['executor_idle_fraction']:.2f}"
                )
            for failure in summary["failures"]:
                print(
                    f"{case_id} {executor} {failure['workers']:>2}: failed, "
                    f"{(failure['errors'] or ['no error line'])[-1]}"
                )


def main() -> int:
    """Run every configuration not yet finished, then summarise."""
    args = _parse_args()
    configuration = load_profile_configuration(args.configuration)
    case_ids = [item.case.case_id for item in configuration.cases]
    runs = _requested_runs(args, case_ids)
    run_root = args.output_root.resolve() / "runs" / args.label
    checkout = checkout_identity(_ROOT)
    if not args.summarise_existing:
        for case_id in case_ids:
            for executor, (worker_counts, run_cases) in runs.items():
                for workers in worker_counts if case_id in run_cases else []:
                    _run_configuration(
                        args, run_root, case_id, executor, workers
                    )
    cases = {
        case_id: {
            executor: _case_summary(run_root, case_id, executor, worker_counts)
            for executor, (worker_counts, run_cases) in runs.items()
            if case_id in run_cases
        }
        for case_id in case_ids
    }
    report = {
        "schema_version": 1,
        "label": args.label,
        "created_at": datetime.now(UTC).isoformat(),
        "commit_sha": checkout.commit_sha,
        "worktree_dirty": checkout.worktree_dirty,
        "source_tree_sha256": checkout.source_tree_sha256,
        "configuration_sha256": file_sha256(args.configuration),
        "machine": machine_identity(),
        "memory_budget_bytes": args.memory_budget_bytes,
        "with_flat_noise": args.with_flat_noise,
        "runs": {
            executor: {"workers": worker_counts, "cases": run_cases}
            for executor, (worker_counts, run_cases) in runs.items()
        },
        "cases": cases,
    }
    (run_root / "scaling.json").unlink(missing_ok=True)
    write_report(run_root / "scaling.json", report)
    _print_summary(cases)
    print(f"\nSummary: {run_root / 'scaling.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
