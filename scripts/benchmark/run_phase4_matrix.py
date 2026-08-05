"""Run the frozen incremental Phase 4 compact-catalogue matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from hebog.validation.evidence import BenchmarkEvidence, load_evidence

_PROFILES = (
    "sparse",
    "normal",
    "dense",
    "blend-heavy",
    "fit-failure",
)
_STAGE_MEASUREMENT = "compact-measurement-fitting"
_STAGE_REDUCTION = "catalogue-reduction"
_STAGE_MATERIALIZATION = "rapthor-catalogue-materialization"


@dataclass(frozen=True, slots=True)
class MatrixProtocol:
    """Validated frozen protocol used by the closure runner."""

    benchmark_id: str
    sizes: tuple[int, ...]
    profiles: tuple[str, ...]
    workload_classes: dict[str, str]
    maximum_serial_size: int
    representative_tile_size: int
    warmups: int
    repetitions: int
    workers: int
    threads_per_worker: int
    representative_size: int
    measurement_fitting_budget_seconds: float
    catalogue_output_budget_seconds: float


@dataclass(frozen=True, slots=True)
class CellIdentity:
    """Execution coordinates for one matrix cell."""

    size: int
    profile: str
    executor: str
    tile_size: int


def _parse_args() -> argparse.Namespace:
    """Parse one frozen-matrix invocation."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=root / "config/benchmarks/phase-4-performance.json",
        type=Path,
    )
    parser.add_argument("--output-directory", required=True, type=Path)
    return parser.parse_args()


def _positive_integer(value: object, *, name: str) -> int:
    """Return one positive integer or reject malformed protocol data."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_number(value: object, *, name: str) -> float:
    """Return one finite positive budget."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive number")
    converted = float(value)
    if converted <= 0.0 or converted == float("inf"):
        raise ValueError(f"{name} must be a finite positive number")
    return converted


def _mapping(value: object, *, name: str) -> dict[str, Any]:
    """Return one string-keyed mapping from parsed JSON."""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{name} must be an object")
    return cast(dict[str, Any], value)


def _load_protocol(path: Path) -> MatrixProtocol:  # noqa: C901
    """Load and validate the complete frozen Phase 4 matrix protocol."""
    raw = _mapping(json.loads(path.read_text(encoding="utf-8")), name="root")
    required = {
        "benchmark_id",
        "budgets",
        "maximum_serial_size_pixels",
        "profiles",
        "repetitions",
        "representative_tile_size_pixels",
        "schema_version",
        "sizes_pixels",
        "status",
        "threads_per_worker",
        "warmups",
        "workers",
        "workload_classes",
    }
    if set(raw) != required:
        raise ValueError("Phase 4 matrix protocol fields changed")
    if raw["schema_version"] != 1 or raw["status"] != "frozen":
        raise ValueError("Phase 4 matrix protocol must be frozen schema 1")
    benchmark_id = raw["benchmark_id"]
    if not isinstance(benchmark_id, str) or not benchmark_id:
        raise ValueError("benchmark_id must be a non-empty string")
    sizes_raw = raw["sizes_pixels"]
    profiles_raw = raw["profiles"]
    if not isinstance(sizes_raw, list) or not isinstance(profiles_raw, list):
        raise ValueError("matrix sizes and profiles must be arrays")
    sizes = tuple(_positive_integer(item, name="size") for item in sizes_raw)
    if sizes != tuple(sorted(set(sizes))):
        raise ValueError("matrix sizes must be unique and increasing")
    if not all(isinstance(item, str) for item in profiles_raw):
        raise ValueError("matrix profiles must be strings")
    profiles = tuple(cast(list[str], profiles_raw))
    if profiles != _PROFILES:
        raise ValueError("Phase 4 matrix profiles changed")
    workload_raw = _mapping(raw["workload_classes"], name="workload_classes")
    if set(workload_raw) != set(profiles) or not all(
        isinstance(value, str) for value in workload_raw.values()
    ):
        raise ValueError("every profile requires one workload class")
    budgets = _mapping(raw["budgets"], name="budgets")
    if set(budgets) != {
        "catalogue_output_seconds",
        "measurement_fitting_seconds",
        "representative_size_pixels",
    }:
        raise ValueError("Phase 4 matrix budget fields changed")
    representative_size = _positive_integer(
        budgets["representative_size_pixels"],
        name="representative size",
    )
    if representative_size not in sizes:
        raise ValueError("representative size must be in the matrix")
    return MatrixProtocol(
        benchmark_id=benchmark_id,
        sizes=sizes,
        profiles=profiles,
        workload_classes=cast(dict[str, str], workload_raw),
        maximum_serial_size=_positive_integer(
            raw["maximum_serial_size_pixels"],
            name="maximum serial size",
        ),
        representative_tile_size=_positive_integer(
            raw["representative_tile_size_pixels"],
            name="representative tile size",
        ),
        warmups=_positive_integer(raw["warmups"], name="warmups"),
        repetitions=_positive_integer(raw["repetitions"], name="repetitions"),
        workers=_positive_integer(raw["workers"], name="workers"),
        threads_per_worker=_positive_integer(
            raw["threads_per_worker"], name="threads per worker"
        ),
        representative_size=representative_size,
        measurement_fitting_budget_seconds=_positive_number(
            budgets["measurement_fitting_seconds"],
            name="measurement and fitting budget",
        ),
        catalogue_output_budget_seconds=_positive_number(
            budgets["catalogue_output_seconds"],
            name="catalogue output budget",
        ),
    )


def _execution_policy(
    size: int,
    protocol: MatrixProtocol,
) -> tuple[str, int]:
    """Use serial below the reviewed crossover and Dask above it."""
    if size <= protocol.maximum_serial_size:
        return "serial", size
    return "dask", protocol.representative_tile_size


def _run(command: list[str]) -> dict[str, object]:
    """Run one matrix step and return its final JSON status line."""
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    lines = result.stdout.splitlines()
    if not lines:
        raise ValueError("matrix step produced no status output")
    print(lines[-1], flush=True)
    value = json.loads(lines[-1])
    if not isinstance(value, dict):
        raise ValueError("matrix step status must be a JSON object")
    return cast(dict[str, object], value)


def _stage_median(
    evidence: BenchmarkEvidence,
    stage_name: str,
) -> float | None:
    """Return a measured stage median or None when the stage is absent."""
    observations: list[float] = []
    for measurement in evidence.measurements:
        if measurement.warmup:
            continue
        stages = {item.stage: item.metrics for item in measurement.stages}
        if stage_name not in stages:
            return None
        observations.append(stages[stage_name].wall_seconds)
    if not observations:
        raise ValueError("matrix evidence contains no measured repetitions")
    return statistics.median(observations)


def _cell_summary(
    evidence_path: Path,
    status: dict[str, object],
    *,
    identity: CellIdentity,
) -> dict[str, object]:
    """Reduce one typed evidence document into a compact review record."""
    loaded = load_evidence(evidence_path)
    if not isinstance(loaded, BenchmarkEvidence):
        raise TypeError("matrix cell did not produce benchmark evidence")
    fitting = _stage_median(loaded, _STAGE_MEASUREMENT)
    reduction = _stage_median(loaded, _STAGE_REDUCTION)
    materialization = _stage_median(loaded, _STAGE_MATERIALIZATION)
    if fitting is None or reduction is None:
        raise ValueError("matrix evidence omitted a required Phase 4 stage")
    output = (
        reduction + materialization if materialization is not None else None
    )
    measured = tuple(
        item.complete for item in loaded.measurements if not item.warmup
    )
    return {
        "completion_available": status["completion_available"],
        "completion_error": status["completion_error"],
        "component_count": status["component_count"],
        "dataset_id": loaded.dataset.identifier,
        "deferred_island_count": status["deferred_island_count"],
        "evidence_sha256": hashlib.sha256(
            evidence_path.read_bytes()
        ).hexdigest(),
        "executor": identity.executor,
        "maximum_peak_rss_bytes": max(
            item.peak_rss_bytes for item in measured
        ),
        "maximum_processor_array_bytes": status[
            "maximum_processor_array_bytes"
        ],
        "median_catalogue_output_seconds": output,
        "median_complete_increment_seconds": statistics.median(
            item.wall_seconds for item in measured
        ),
        "median_measurement_fitting_seconds": fitting,
        "omission_count": status["omission_count"],
        "output_byte_count": status["output_byte_count"],
        "planned_batch_count": status["planned_batch_count"],
        "profile": identity.profile,
        "setup_wall_seconds_excluded": status["setup_wall_seconds"],
        "size_pixels": identity.size,
        "source_count": status["source_count"],
        "task_count": status["task_count"],
        "tile_size_pixels": identity.tile_size,
    }


def _budget_decision(
    cells: list[dict[str, object]],
    protocol: MatrixProtocol,
) -> dict[str, object]:
    """Apply the frozen representative component budgets."""
    representative = [
        cell
        for cell in cells
        if cell["size_pixels"] == protocol.representative_size
    ]
    fitting_failures = [
        cast(str, cell["profile"])
        for cell in representative
        if cast(float, cell["median_measurement_fitting_seconds"])
        > protocol.measurement_fitting_budget_seconds
    ]
    output_failures = [
        cast(str, cell["profile"])
        for cell in representative
        if cell["profile"] != "fit-failure"
        and (
            cell["median_catalogue_output_seconds"] is None
            or cast(float, cell["median_catalogue_output_seconds"])
            > protocol.catalogue_output_budget_seconds
        )
    ]
    fit_failure = next(
        cell for cell in representative if cell["profile"] == "fit-failure"
    )
    fit_failure_closed = (
        fit_failure["completion_available"] is False
        and cast(int, fit_failure["omission_count"]) > 0
        and fit_failure["output_byte_count"] is None
    )
    return {
        "catalogue_output_budget_seconds": (
            protocol.catalogue_output_budget_seconds
        ),
        "catalogue_output_failures": output_failures,
        "fit_failure_closed_without_output": fit_failure_closed,
        "measurement_fitting_budget_seconds": (
            protocol.measurement_fitting_budget_seconds
        ),
        "measurement_fitting_failures": fitting_failures,
        "passed": (
            not fitting_failures and not output_failures and fit_failure_closed
        ),
        "representative_size_pixels": protocol.representative_size,
    }


def _density_diagnostic(cells: list[dict[str, object]]) -> dict[str, object]:
    """Report per-source dense/normal cost ratios without inventing a gate."""
    rows: list[dict[str, object]] = []
    for size in sorted({cast(int, cell["size_pixels"]) for cell in cells}):
        normal = next(
            cell
            for cell in cells
            if cell["size_pixels"] == size and cell["profile"] == "normal"
        )
        dense = next(
            cell
            for cell in cells
            if cell["size_pixels"] == size and cell["profile"] == "dense"
        )
        normal_sources = max(1, cast(int, normal["source_count"]))
        dense_sources = max(1, cast(int, dense["source_count"]))
        normal_time = cast(float, normal["median_measurement_fitting_seconds"])
        dense_time = cast(float, dense["median_measurement_fitting_seconds"])
        rows.append(
            {
                "dense_to_normal_per_source_time_ratio": (
                    (dense_time / dense_sources)
                    / (normal_time / normal_sources)
                ),
                "dense_to_normal_source_count_ratio": (
                    dense_sources / normal_sources
                ),
                "dense_to_normal_time_ratio": dense_time / normal_time,
                "size_pixels": size,
            }
        )
    return {
        "interpretation": (
            "diagnostic only; compare time growth with accepted-source "
            "growth and inspect morphology before attributing superlinearity"
        ),
        "rows": rows,
    }


def main() -> None:
    """Generate every cell and write an immutable matrix summary."""
    args = _parse_args()
    protocol = _load_protocol(args.config)
    output = args.output_directory
    summary_path = output / "matrix-summary.json"
    if summary_path.exists():
        raise FileExistsError(f"matrix summary exists: {summary_path}")
    inputs = output / "inputs"
    evidence_directory = output / "evidence"
    status_directory = output / "status"
    inputs.mkdir(parents=True, exist_ok=True)
    evidence_directory.mkdir(parents=True, exist_ok=True)
    status_directory.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).parents[2]
    cells: list[dict[str, object]] = []
    for size in protocol.sizes:
        executor, tile_size = _execution_policy(size, protocol)
        for profile in protocol.profiles:
            identity = f"phase4-{profile}-{size}"
            input_path = inputs / f"{identity}.fits"
            evidence_path = evidence_directory / f"{identity}.json"
            status_path = status_directory / f"{identity}.json"
            if not input_path.exists():
                subprocess.run(
                    [
                        sys.executable,
                        str(
                            root / "scripts/benchmark/generate_phase4_input.py"
                        ),
                        "--size",
                        str(size),
                        "--profile",
                        profile,
                        "--output",
                        str(input_path),
                    ],
                    check=True,
                )
            if evidence_path.exists() and status_path.exists():
                status = _mapping(
                    json.loads(status_path.read_text(encoding="utf-8")),
                    name="cell status",
                )
            elif evidence_path.exists() or status_path.exists():
                raise ValueError(
                    f"incomplete matrix cell state for {identity}; use a "
                    "new output directory"
                )
            else:
                status = _run(
                    [
                        sys.executable,
                        str(
                            root
                            / "scripts/benchmark/measure_phase4_catalogue.py"
                        ),
                        "--input",
                        str(input_path),
                        "--dataset-id",
                        identity,
                        "--profile",
                        profile,
                        "--workload-class",
                        protocol.workload_classes[profile],
                        "--executor",
                        executor,
                        "--workers",
                        str(protocol.workers),
                        "--threads-per-worker",
                        str(protocol.threads_per_worker),
                        "--tile-size",
                        str(tile_size),
                        "--warmups",
                        str(protocol.warmups),
                        "--repetitions",
                        str(protocol.repetitions),
                        "--output",
                        str(evidence_path),
                    ]
                )
                status_path.write_text(
                    json.dumps(status, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            cells.append(
                _cell_summary(
                    evidence_path,
                    status,
                    identity=CellIdentity(
                        size=size,
                        profile=profile,
                        executor=executor,
                        tile_size=tile_size,
                    ),
                )
            )
    summary = {
        "benchmark_id": protocol.benchmark_id,
        "budget_decision": _budget_decision(cells, protocol),
        "cells": cells,
        "density_diagnostic": _density_diagnostic(cells),
        "protocol_sha256": hashlib.sha256(
            args.config.read_bytes()
        ).hexdigest(),
        "reference_context": (
            "This incremental Phase 4 component matrix establishes Hebog's "
            "first reviewed curve. Existing PyBDSF results measure the full "
            "Rapthor filter step and are context only, not a matched speedup."
        ),
        "schema_version": 1,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(summary_path)
    if not cast(dict[str, object], summary["budget_decision"])["passed"]:
        raise SystemExit("Phase 4 incremental performance budget failed")


if __name__ == "__main__":
    main()
