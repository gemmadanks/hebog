#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
"""Run the quick benchmark and compare with cached baselines.

Cases and the everyday budget come from
``config/benchmarks/quick-benchmark.json``; repetition counts and comparison
rules come from the performance contract it names. Every repetition of
current Hebog runs ``quick_benchmark_worker.py`` in a fresh process. The
previous Hebog release is installed once from its Git tag and locked
dependencies, and it and pinned PyBDSF ``master`` are measured once per
input and machine, then cached under ``benchmark-results/quick-benchmark``.

Exit status is 1 when a case fails or current Hebog is slower than the
previous release under the contract's regression rule. The ``master`` ratio
is diagnostic: it is reported, but only the matched M4 benchmark can pass or
fail the deployment gate.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import runpy
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from typing import Any, cast

import hebog
from hebog import public_api
from hebog.io import FitsImageSource
from hebog.validation.contracts import (
    PerformanceMatrixContract,
    load_performance_matrix,
)
from hebog.validation.evidence import (
    BenchmarkEvidence,
    ExecutorKind,
    SoftwareIdentity,
    load_evidence,
    write_evidence,
)
from hebog.validation.quick_benchmark import (
    SINGLE_THREAD_ENVIRONMENT,
    BaselineComparison,
    BenchmarkCase,
    BenchmarkTier,
    ProcessUsage,
    QuickBenchmarkConfiguration,
    Repetition,
    benchmark_evidence,
    compare_with_previous_release,
    compare_with_pybdsf_master,
    development_dataset,
    load_quick_benchmark_configuration,
    local_resources,
    machine_identity,
    measured_wall_seconds,
    physical_memory_bytes,
    run_measured_process,
    source_tree_sha256,
    summarise_timings,
    tier_cases,
    worker_environment,
)
from hebog.validation.quick_check import (
    REFERENCE_CONTAINER_COMMAND,
    PreparedCase,
    container_image_identity,
    file_sha256,
    prepare_case,
    reference_cache_directory,
    reference_identity,
    write_report,
)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIGURATION = _ROOT / "config/benchmarks/quick-benchmark.json"
_DEFAULT_OUTPUT = _ROOT / "benchmark-results/quick-benchmark"
_QUICK_CHECK_INPUTS = _ROOT / "benchmark-results/quick-check/inputs"
_WORKER = _ROOT / "scripts/benchmark/quick_benchmark_worker.py"
_FINDER_STAGE = "find-sources"
_REFERENCE_STAGE = "process-image"
_MEASUREMENT_REVISION = 2
"""Increase when how a repetition runs changes, to remeasure baselines."""


@dataclass(frozen=True, slots=True)
class _Installation:
    """One Hebog to time: its interpreter and source identity."""

    label: str
    python: Path
    working_directory: Path
    commit_sha: str
    source_tree_sha256: str


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
        "--previous-release",
        help="release tag to compare with (default: latest v* tag in HEAD)",
    )
    parser.add_argument(
        "--no-previous-release",
        action="store_true",
        help="skip the previous-release comparison",
    )
    parser.add_argument(
        "--refresh-previous-release",
        action="store_true",
        help="measure the previous release again in this session",
    )
    parser.add_argument(
        "--no-reference",
        action="store_true",
        help="skip the pinned PyBDSF master comparison",
    )
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="fetch missing configured cut-outs",
    )
    parser.add_argument("--engine", default="podman")
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


def _latest_release_tag() -> str | None:
    try:
        return _git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*")
    except subprocess.CalledProcessError:
        return None


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _current_installation() -> _Installation:
    return _Installation(
        label="current",
        python=Path(sys.executable),
        working_directory=_ROOT,
        commit_sha=_git("rev-parse", "HEAD"),
        source_tree_sha256=source_tree_sha256(_ROOT / "src/hebog"),
    )


def _release_installation(tag: str, output_root: Path) -> _Installation:
    """Install a release from its tag with its locked dependencies, once."""
    commit = _git("rev-parse", f"{tag}^{{commit}}")
    directory = output_root / "releases" / f"{tag}-{commit[:12]}"
    installed = directory / ".installed"
    if not installed.exists():
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
        archive = subprocess.run(
            ["git", "archive", commit],
            cwd=_ROOT,
            check=True,
            capture_output=True,
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as contents:
            contents.extractall(directory, filter="data")
        print(f"Installing Hebog {tag} into {directory}", flush=True)
        subprocess.run(
            [
                "uv",
                "sync",
                "--frozen",
                "--no-default-groups",
                "--project",
                str(directory),
            ],
            check=True,
            env=worker_environment(os.environ),
        )
        installed.touch()
    return _Installation(
        label=tag,
        python=directory / ".venv/bin/python",
        working_directory=directory,
        commit_sha=commit,
        source_tree_sha256=source_tree_sha256(directory / "src/hebog"),
    )


def _supplied_metadata(case: BenchmarkCase) -> dict[str, float] | None:
    return cast(
        dict[str, float] | None, getattr(case.case, "supplied_metadata", None)
    )


def _shape_yx(prepared: PreparedCase) -> tuple[int, int]:
    shape = FitsImageSource(
        prepared.input_path, prepared.supplied_metadata
    ).metadata()
    return shape.shape_yx


def _configuration_sha256(
    configuration: QuickBenchmarkConfiguration, case: BenchmarkCase
) -> str:
    return _canonical_sha256(
        {
            "case": case.model_dump(mode="json"),
            "executor": "serial",
            "hebog": configuration.hebog.model_dump(mode="json"),
            "thread_environment": dict(SINGLE_THREAD_ENVIRONMENT),
        }
    )


def _environment_sha256(machine: dict[str, object]) -> str:
    return _canonical_sha256(
        {
            "machine": machine,
            "thread_environment": dict(SINGLE_THREAD_ENVIRONMENT),
        }
    )


def _time_hebog(  # noqa: PLR0913
    installation: _Installation,
    *,
    case: BenchmarkCase,
    prepared: PreparedCase,
    configuration: QuickBenchmarkConfiguration,
    contract: PerformanceMatrixContract,
    machine: dict[str, object],
) -> BenchmarkEvidence:
    """Run the warm-up and measured repetitions of one Hebog installation."""
    protocol = contract.previous_hebog
    shape_yx = _shape_yx(prepared)
    command = [
        str(installation.python),
        str(_WORKER),
        "--input",
        str(prepared.input_path),
        "--run-id",
        case.case_id,
        "--settings",
        configuration.hebog.model_dump_json(),
    ]
    supplied = _supplied_metadata(case)
    if supplied is not None:
        command += ["--supplied-metadata", json.dumps(supplied)]
    if max(shape_yx) > public_api._MAXIMUM_PREVIEW_DIMENSION:
        command += ["--diagnostic-size-limit", str(max(shape_yx))]
    repetitions: list[Repetition] = []
    record: dict[str, Any] = {}
    total = protocol.warmup_repetitions + protocol.minimum_measured_repetitions
    for index in range(total):
        warmup = index < protocol.warmup_repetitions
        # Products go to the system temporary directory, which macOS
        # Spotlight does not index; indexing under benchmark-results/ added
        # seconds of off-CPU time to some repetitions.
        with TemporaryDirectory(prefix="hebog-quick-benchmark-") as temporary:
            result_path = Path(temporary) / "result.json"
            complete = run_measured_process(
                [
                    *command,
                    "--output-directory",
                    str(Path(temporary) / "products"),
                    "--result",
                    str(result_path),
                ],
                environment=worker_environment(os.environ),
                working_directory=installation.working_directory,
            )
            record = json.loads(result_path.read_text(encoding="utf-8"))
        repetitions.append(
            Repetition(
                warmup=warmup,
                complete=complete,
                finder=ProcessUsage(**record["finder"]),
            )
        )
        print(
            f"  {installation.label} {'warm-up' if warmup else 'run'} "
            f"{index + 1}/{total}: {complete.wall_seconds:.1f} s",
            flush=True,
        )
    return benchmark_evidence(
        run_id=f"quick-benchmark-{case.case_id}",
        captured_at=datetime.now(UTC),
        dataset=development_dataset(
            case, content_sha256=prepared.input_sha256, shape_yx=shape_yx
        ),
        configuration_sha256=_configuration_sha256(configuration, case),
        subject=SoftwareIdentity(
            name="hebog",
            version=record["hebog_version"],
            commit_sha=installation.commit_sha,
            source_tree_sha256=installation.source_tree_sha256,
            dependency_inventory_sha256=record["dependency_inventory_sha256"],
        ),
        environment_sha256=_environment_sha256(machine),
        resources=local_resources(
            ExecutorKind.SERIAL,
            allocated_cpu_cores=1,
            memory_bytes=physical_memory_bytes(),
        ),
        finder_stage=_FINDER_STAGE,
        repetitions=repetitions,
    )


def _cached_or_measured(
    directory: Path,
    measure: Any,
    *,
    description: str,
    refresh: bool = False,
) -> tuple[str, BenchmarkEvidence | None]:
    """Load cached evidence, or measure and cache it, or a cached failure.

    A failure is cached for the same identity, so it is not repeated; the
    case is then reported without that comparison. ``refresh`` discards the
    cached evidence or failure and measures again.
    """
    evidence_path = directory / "evidence.json"
    failure_path = directory / "failure.json"
    if refresh:
        evidence_path.unlink(missing_ok=True)
        failure_path.unlink(missing_ok=True)
    if evidence_path.exists():
        return "cached", cast(BenchmarkEvidence, load_evidence(evidence_path))
    if failure_path.exists():
        return "failed", None
    print(f"  measuring {description}", flush=True)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        evidence = measure()
    except (subprocess.CalledProcessError, OSError, ValueError) as error:
        failure_path.write_text(
            json.dumps(
                {"error": f"{type(error).__name__}: {error}"},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"  {description} failed: {error}", flush=True)
        return "failed", None
    write_evidence(evidence_path, evidence)
    return "measured", evidence


def _time_reference(  # noqa: PLR0913
    *,
    case: BenchmarkCase,
    prepared: PreparedCase,
    configuration: QuickBenchmarkConfiguration,
    contract: PerformanceMatrixContract,
    output_root: Path,
    engine: str,
    machine: dict[str, object],
) -> BenchmarkEvidence:
    """Time pinned PyBDSF ``master`` in its container with the same protocol.

    Container start-up is excluded: the worker measures itself from before
    input validation to after product normalisation.
    """
    reference = configuration.reference
    protocol = contract.previous_hebog
    run_container = runpy.run_path(str(_ROOT / REFERENCE_CONTAINER_COMMAND))[
        "_run_container"
    ]
    scratch = output_root / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    repetitions: list[Repetition] = []
    result: dict[str, Any] = {}
    total = protocol.warmup_repetitions + protocol.minimum_measured_repetitions
    for index in range(total):
        with TemporaryDirectory(dir=scratch) as temporary:
            output = Path(temporary) / "reference"
            run_container(
                repository_root=_ROOT,
                comparison_root=output_root,
                engine=engine,
                image=reference.container_image,
                input_path=prepared.reference_input_path,
                output=output,
                case_id=case.case_id,
                finder_id=reference.finder_id,
                ncores=reference.ncores,
            )
            result = json.loads((output / "result.json").read_text())
        if result.get("process_usage") is None:
            raise ValueError("reference worker recorded no process usage")
        repetitions.append(
            Repetition(
                warmup=index < protocol.warmup_repetitions,
                complete=ProcessUsage(**result["process_usage"]),
                finder=ProcessUsage(**result["finder_usage"]),
            )
        )
        print(
            f"  pybdsf-master run {index + 1}/{total}: "
            f"{result['process_usage']['wall_seconds']:.1f} s",
            flush=True,
        )
    podman_memory = int(
        subprocess.run(
            [engine, "info", "--format", "{{.Host.MemTotal}}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return benchmark_evidence(
        run_id=f"quick-benchmark-{case.case_id}-pybdsf-master",
        captured_at=datetime.now(UTC),
        dataset=development_dataset(
            case,
            content_sha256=file_sha256(prepared.reference_input_path),
            shape_yx=_shape_yx(prepared),
        ),
        configuration_sha256=_canonical_sha256(
            {
                "finder_id": reference.finder_id,
                "ncores": reference.ncores,
                "settings": result["configuration"],
            }
        ),
        subject=SoftwareIdentity(
            name="pybdsf",
            version=result["runtime_version"],
            commit_sha=contract.pybdsf_master.commit_sha,
            container_image_digest="sha256:"
            + container_image_identity(engine, reference.container_image),
            dependency_inventory_sha256=result["dependency_inventory_sha256"],
        ),
        environment_sha256=_environment_sha256(machine),
        resources=local_resources(
            ExecutorKind.EXTERNAL,
            allocated_cpu_cores=reference.ncores,
            memory_bytes=podman_memory,
        ),
        finder_stage=_REFERENCE_STAGE,
        repetitions=repetitions,
    )


def _summary(evidence: BenchmarkEvidence) -> dict[str, Any]:
    measured = [m for m in evidence.measurements if not m.warmup]
    return asdict(summarise_timings(measured_wall_seconds(evidence))) | {
        "median_cpu_seconds": median(m.complete.cpu_seconds for m in measured),
        "peak_rss_bytes": max(m.complete.peak_rss_bytes for m in measured),
        "version": evidence.subject.version,
    }


def _comparison(comparison: BaselineComparison) -> dict[str, Any]:
    return asdict(comparison.ratio) | {"outcome": comparison.outcome}


def _baseline_identity(
    subject: dict[str, object],
    *,
    machine: dict[str, object],
    contract: PerformanceMatrixContract,
) -> dict[str, object]:
    """Key a cached baseline by its subject and how its repetitions ran."""
    return subject | {
        "machine": machine,
        "measurement_revision": _MEASUREMENT_REVISION,
        "protocol": contract.previous_hebog.model_dump(mode="json"),
    }


def _cached_failure(directory: Path) -> str:
    """Return the recorded error of a baseline that could not be measured."""
    failure = json.loads((directory / "failure.json").read_text("utf-8"))
    return str(failure["error"])


def _run_case(  # noqa: PLR0913
    case: BenchmarkCase,
    *,
    configuration: QuickBenchmarkConfiguration,
    contract: PerformanceMatrixContract,
    args: argparse.Namespace,
    run_root: Path,
    previous: _Installation | None,
    reference_identity_value: dict[str, object] | None,
    machine: dict[str, object],
) -> dict[str, Any]:
    output_root = args.output_root.resolve()
    prepared = prepare_case(
        case.case,
        dataset_manifest=_ROOT / configuration.dataset_manifest,
        repository_root=_ROOT,
        inputs_root=_QUICK_CHECK_INPUTS,
        allow_download=args.allow_download,
    )
    record: dict[str, Any] = {
        "case_id": case.case_id,
        "tier": case.tier,
        "workload_class": case.workload_class.value,
        "input_sha256": prepared.input_sha256,
        "shape_yx": list(_shape_yx(prepared)),
    }
    print(f"{case.case_id} {record['shape_yx']}", flush=True)
    timing = {
        "case": case,
        "prepared": prepared,
        "configuration": configuration,
        "contract": contract,
        "machine": machine,
    }
    try:
        current = _time_hebog(_current_installation(), **timing)
    except (subprocess.CalledProcessError, OSError, ValueError) as error:
        return record | {
            "status": "failure",
            "error": f"{type(error).__name__}: {error}",
        }
    evidence_path = run_root / case.case_id / "hebog.json"
    evidence_path.parent.mkdir(parents=True)
    write_evidence(evidence_path, current)
    current_seconds = measured_wall_seconds(current)
    record |= {
        "status": "success",
        "hebog": _summary(current) | {"evidence": str(evidence_path)},
        "previous_release": None,
        "pybdsf_master": None,
    }
    if previous is not None:
        directory = reference_cache_directory(
            output_root / "previous-releases",
            case_id=case.case_id,
            reference_input_sha256=prepared.input_sha256,
            finder_id=f"hebog-{previous.label}",
            identity=_baseline_identity(
                {
                    "commit_sha": previous.commit_sha,
                    "configuration_sha256": _configuration_sha256(
                        configuration, case
                    ),
                    "worker_sha256": file_sha256(_WORKER),
                },
                machine=machine,
                contract=contract,
            ),
        )
        status, evidence = _cached_or_measured(
            directory,
            lambda: _time_hebog(previous, **timing),
            description=f"Hebog {previous.label}",
            refresh=args.refresh_previous_release,
        )
        record["previous_release"] = {
            "tag": previous.label,
            "status": status,
            "cache": str(directory),
        }
        if evidence is None:
            record["previous_release"]["error"] = _cached_failure(directory)
        else:
            record["previous_release"] |= _summary(evidence) | {
                "comparison": _comparison(
                    compare_with_previous_release(
                        current_seconds,
                        measured_wall_seconds(evidence),
                        contract.previous_hebog,
                    )
                )
            }
    if reference_identity_value is not None:
        directory = reference_cache_directory(
            output_root / "references",
            case_id=case.case_id,
            reference_input_sha256=file_sha256(prepared.reference_input_path),
            finder_id=configuration.reference.finder_id,
            identity=_baseline_identity(
                reference_identity_value, machine=machine, contract=contract
            ),
        )
        status, evidence = _cached_or_measured(
            directory,
            lambda: _time_reference(
                output_root=output_root,
                engine=args.engine,
                **timing,
            ),
            description="pinned PyBDSF master",
        )
        record["pybdsf_master"] = {"status": status, "cache": str(directory)}
        if evidence is None:
            record["pybdsf_master"]["error"] = _cached_failure(directory)
        else:
            record["pybdsf_master"] |= _summary(evidence) | {
                "comparison": _comparison(
                    compare_with_pybdsf_master(
                        current_seconds,
                        measured_wall_seconds(evidence),
                        contract.pybdsf_master,
                        resamples=contract.previous_hebog.bootstrap_resamples,
                    )
                ),
                "matched": False,
            }
    return record


@dataclass(frozen=True, slots=True)
class _RunOutcome:
    """Cases that failed, regressed or had no previous-release check."""

    failed_cases: tuple[str, ...]
    regressions: tuple[str, ...]
    unchecked_cases: tuple[str, ...]

    @property
    def exit_status(self) -> int:
        """Fail on a failed case or regression, not on a missing baseline.

        A release that cannot run a case, for example because the case needs
        a later feature, cannot run it until the next release, so a missing
        baseline is reported instead of failing every run.
        """
        return 1 if self.failed_cases or self.regressions else 0


def _run_outcome(records: list[dict[str, Any]]) -> _RunOutcome:
    succeeded = [
        record
        for record in records
        if record["status"] == "success"
        and record["previous_release"] is not None
    ]
    return _RunOutcome(
        failed_cases=tuple(
            record["case_id"]
            for record in records
            if record["status"] != "success"
        ),
        regressions=tuple(
            record["case_id"]
            for record in succeeded
            if record["previous_release"].get("comparison", {}).get("outcome")
            == "fail"
        ),
        unchecked_cases=tuple(
            record["case_id"]
            for record in succeeded
            if "comparison" not in record["previous_release"]
        ),
    )


def _within_budget(
    hebog_seconds: float, budget: float | None, outcome: _RunOutcome
) -> bool | None:
    """Compare Hebog time with the budget when that time is complete.

    A failed case records no evidence, so its time is missing from the total
    and the budget cannot be assessed.
    """
    if budget is None or outcome.failed_cases:
        return None
    return hebog_seconds <= budget


def _ratio_text(baseline: dict[str, Any] | None) -> str:
    """Format a ratio with its one-sided bounds and outcome."""
    if baseline is None or "comparison" not in baseline:
        return "-"
    comparison = baseline["comparison"]
    return (
        f"{comparison['ratio']:.2f} [{comparison['lower_bound']:.2f}, "
        f"{comparison['upper_bound']:.2f}] {comparison['outcome']}"
    )


def _print_summary(report: dict[str, Any]) -> None:
    print(
        "case | size | Hebog median s (min-max) | previous s | "
        "ratio [bounds] | master s | ratio [bounds] | peak RSS MiB"
    )
    for case in report["cases"]:
        if case["status"] != "success":
            print(f"{case['case_id']} | {case['status']}: {case['error']}")
            continue
        hebog_summary = case["hebog"]
        previous = case["previous_release"]
        master = case["pybdsf_master"]
        print(
            " | ".join(
                (
                    case["case_id"],
                    "x".join(str(value) for value in case["shape_yx"]),
                    f"{hebog_summary['median_seconds']:.1f} "
                    f"({hebog_summary['minimum_seconds']:.1f}-"
                    f"{hebog_summary['maximum_seconds']:.1f})",
                    f"{previous['median_seconds']:.1f}"
                    if previous and "median_seconds" in previous
                    else "-",
                    _ratio_text(previous),
                    f"{master['median_seconds']:.1f}"
                    if master and "median_seconds" in master
                    else "-",
                    _ratio_text(master),
                    f"{hebog_summary['peak_rss_bytes'] / 2**20:.0f}",
                )
            )
        )
    if (
        report["budget_seconds"] is not None
        and report["within_budget"] is None
    ):
        print(
            f"Hebog time {report['hebog_elapsed_seconds']:.0f} s of "
            "successful cases only; the budget was not assessed because a "
            "case failed"
        )
    elif report["budget_seconds"] is not None:
        print(
            f"Hebog time {report['hebog_elapsed_seconds']:.0f} s of a "
            f"{report['budget_seconds']:.0f} s budget; total "
            f"{report['total_elapsed_seconds']:.0f} s"
        )


def main() -> int:
    args = _parse_args()
    started = time.perf_counter()
    configuration = load_quick_benchmark_configuration(args.configuration)
    contract = load_performance_matrix(
        _ROOT / configuration.performance_contract
    )
    tier = cast(BenchmarkTier, args.tier)
    cases = tier_cases(configuration, tier)
    selected: set[str] = set(cast(list[str], args.cases or []))
    unknown = selected - {case.case_id for case in cases}
    if unknown:
        raise SystemExit(
            f"unknown case IDs for tier {tier}: {sorted(unknown)}"
        )
    output_root = args.output_root.resolve()
    label = args.label or _default_label()
    run_root = output_root / "runs" / label
    if run_root.exists():
        raise SystemExit(f"run directory already exists: {run_root}")
    machine = machine_identity()
    previous = None
    if not args.no_previous_release:
        tag = args.previous_release or _latest_release_tag()
        if tag is None:
            print("No release tag found; skipping the previous release")
        else:
            previous = _release_installation(tag, output_root)
    identity = (
        None
        if args.no_reference
        else reference_identity(
            configuration.reference, engine=args.engine, repository_root=_ROOT
        )
    )
    records = [
        _run_case(
            case,
            configuration=configuration,
            contract=contract,
            args=args,
            run_root=run_root,
            previous=previous,
            reference_identity_value=identity,
            machine=machine,
        )
        for case in cases
        if not selected or case.case_id in selected
    ]
    hebog_seconds = 0.0
    for record in records:
        if record["status"] == "success":
            evidence = cast(
                BenchmarkEvidence,
                load_evidence(Path(record["hebog"]["evidence"])),
            )
            hebog_seconds += sum(
                measurement.complete.wall_seconds
                for measurement in evidence.measurements
            )
    budget = (
        configuration.default_budget_seconds if tier == "default" else None
    )
    outcome = _run_outcome(records)
    report: dict[str, Any] = {
        "schema_version": 1,
        "benchmark_id": configuration.benchmark_id,
        "tier": tier,
        "label": label,
        "created_at": datetime.now(UTC).isoformat(),
        "hebog_version": hebog.__version__,
        "commit_sha": _git("rev-parse", "HEAD"),
        "source_tree_sha256": source_tree_sha256(_ROOT / "src/hebog"),
        "configuration_sha256": file_sha256(args.configuration),
        "machine": machine,
        "previous_hebog_gate": contract.previous_hebog.model_dump(mode="json"),
        "pybdsf_master_gate": contract.pybdsf_master.model_dump(mode="json"),
        "budget_seconds": budget,
        "hebog_elapsed_seconds": hebog_seconds,
        "within_budget": _within_budget(hebog_seconds, budget, outcome),
        "total_elapsed_seconds": time.perf_counter() - started,
        "cases": records,
    }
    write_report(run_root / "report.json", report)
    _print_summary(report)
    print(f"Report: {run_root / 'report.json'}")
    label_text = previous.label if previous is not None else ""
    for case_id in outcome.regressions:
        print(f"REGRESSION {case_id}: slower than {label_text}")
    for case_id in outcome.unchecked_cases:
        print(
            f"NOT CHECKED {case_id}: {label_text} could not be measured, so "
            "there is no regression check; see the case's previous_release "
            "error, or retry with --refresh-previous-release"
        )
    return outcome.exit_status


if __name__ == "__main__":
    raise SystemExit(main())
