# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Run the frozen incremental Phase 5 multiscale matrix."""

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

_PROFILES = ("sparse", "normal", "extended")
_EXECUTORS = ("serial", "dask")
_STAGE_NAME = "multiscale-processing-and-merge"


@dataclass(frozen=True, slots=True)
class MatrixProtocol:
    """Validated frozen protocol used by the Phase 5 matrix runner."""

    benchmark_id: str
    sizes: tuple[int, ...]
    profiles: tuple[str, ...]
    workload_classes: dict[str, str]
    maximum_serial_size: int
    minimum_tile_size: int
    representative_tile_size: int
    maximum_tiles_per_batch: int
    crossover_sizes: tuple[int, ...]
    crossover_executors: tuple[str, ...]
    warmups: int
    repetitions: int
    workers: int
    threads_per_worker: int
    representative_size: int
    multiscale_budget_seconds: float


@dataclass(frozen=True, slots=True)
class CellIdentity:
    """Execution coordinates for one matrix cell."""

    size: int
    profile: str
    executor: str
    tile_size: int
    policy_role: str

    @property
    def identifier(self) -> str:
        """Return one stable filename-safe cell identity."""
        return (
            f"phase5-{self.profile}-{self.size}-{self.executor}-"
            f"{self.policy_role}"
        )


def _parse_args() -> argparse.Namespace:
    """Parse one frozen-matrix invocation."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=root / "config/benchmarks/phase-5-performance.json",
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


def _string_tuple(
    value: object,
    *,
    name: str,
) -> tuple[str, ...]:
    """Return one non-empty unique string tuple."""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ValueError(f"{name} must be a non-empty string array")
    result = tuple(cast(list[str], value))
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _integer_tuple(
    value: object,
    *,
    name: str,
) -> tuple[int, ...]:
    """Return one non-empty increasing positive integer tuple."""
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty integer array")
    result = tuple(_positive_integer(item, name=name) for item in value)
    if result != tuple(sorted(set(result))):
        raise ValueError(f"{name} must be unique and increasing")
    return result


def _load_protocol(path: Path) -> MatrixProtocol:  # noqa: C901
    """Load and validate the complete frozen Phase 5 matrix protocol."""
    raw = _mapping(json.loads(path.read_text(encoding="utf-8")), name="root")
    required = {
        "benchmark_id",
        "budgets",
        "crossover_executors",
        "crossover_sizes_pixels",
        "maximum_serial_size_pixels",
        "maximum_tiles_per_batch",
        "minimum_tile_size_pixels",
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
        raise ValueError("Phase 5 matrix protocol fields changed")
    if raw["schema_version"] != 1 or raw["status"] != "frozen":
        raise ValueError("Phase 5 matrix protocol must be frozen schema 1")
    benchmark_id = raw["benchmark_id"]
    if not isinstance(benchmark_id, str) or not benchmark_id:
        raise ValueError("benchmark_id must be a non-empty string")
    sizes = _integer_tuple(raw["sizes_pixels"], name="matrix sizes")
    profiles = _string_tuple(raw["profiles"], name="profiles")
    if profiles != _PROFILES:
        raise ValueError("Phase 5 matrix profiles changed")
    crossover_sizes = _integer_tuple(
        raw["crossover_sizes_pixels"],
        name="crossover sizes",
    )
    if not set(crossover_sizes).issubset(sizes):
        raise ValueError("crossover sizes must be matrix anchors")
    crossover_executors = _string_tuple(
        raw["crossover_executors"],
        name="crossover executors",
    )
    if crossover_executors != _EXECUTORS:
        raise ValueError("Phase 5 crossover executors changed")
    workload_raw = _mapping(raw["workload_classes"], name="workload_classes")
    if set(workload_raw) != set(profiles) or not all(
        isinstance(value, str) for value in workload_raw.values()
    ):
        raise ValueError("every profile requires one workload class")
    budgets = _mapping(raw["budgets"], name="budgets")
    if set(budgets) != {
        "multiscale_processing_seconds",
        "representative_size_pixels",
    }:
        raise ValueError("Phase 5 matrix budget fields changed")
    representative_size = _positive_integer(
        budgets["representative_size_pixels"],
        name="representative size",
    )
    if representative_size not in sizes:
        raise ValueError("representative size must be in the matrix")
    maximum_serial_size = _positive_integer(
        raw["maximum_serial_size_pixels"],
        name="maximum serial size",
    )
    if maximum_serial_size not in sizes:
        raise ValueError("maximum serial size must be a matrix anchor")
    return MatrixProtocol(
        benchmark_id=benchmark_id,
        sizes=sizes,
        profiles=profiles,
        workload_classes=cast(dict[str, str], workload_raw),
        maximum_serial_size=maximum_serial_size,
        minimum_tile_size=_positive_integer(
            raw["minimum_tile_size_pixels"],
            name="minimum tile size",
        ),
        representative_tile_size=_positive_integer(
            raw["representative_tile_size_pixels"],
            name="representative tile size",
        ),
        maximum_tiles_per_batch=_positive_integer(
            raw["maximum_tiles_per_batch"],
            name="maximum tiles per batch",
        ),
        crossover_sizes=crossover_sizes,
        crossover_executors=crossover_executors,
        warmups=_positive_integer(raw["warmups"], name="warmups"),
        repetitions=_positive_integer(raw["repetitions"], name="repetitions"),
        workers=_positive_integer(raw["workers"], name="workers"),
        threads_per_worker=_positive_integer(
            raw["threads_per_worker"], name="threads per worker"
        ),
        representative_size=representative_size,
        multiscale_budget_seconds=_positive_number(
            budgets["multiscale_processing_seconds"],
            name="multiscale budget",
        ),
    )


def _primary_executor(size: int, protocol: MatrixProtocol) -> str:
    """Use serial through the inherited crossover and Dask above it."""
    return "serial" if size <= protocol.maximum_serial_size else "dask"


def _tile_size(
    size: int,
    executor: str,
    protocol: MatrixProtocol,
) -> int:
    """Use one small serial tile and bounded representative large tiles."""
    if executor == "serial" and size <= protocol.maximum_serial_size:
        return max(size, protocol.minimum_tile_size)
    return max(
        protocol.minimum_tile_size,
        min(size, protocol.representative_tile_size),
    )


def _cell_identities(protocol: MatrixProtocol) -> tuple[CellIdentity, ...]:
    """Return primary cells plus non-duplicated crossover probes."""
    cells: list[CellIdentity] = []
    for size in protocol.sizes:
        primary = _primary_executor(size, protocol)
        for profile in protocol.profiles:
            cells.append(
                CellIdentity(
                    size=size,
                    profile=profile,
                    executor=primary,
                    tile_size=_tile_size(size, primary, protocol),
                    policy_role="primary",
                )
            )
            if size in protocol.crossover_sizes:
                alternate = "dask" if primary == "serial" else "serial"
                cells.append(
                    CellIdentity(
                        size=size,
                        profile=profile,
                        executor=alternate,
                        tile_size=_tile_size(size, alternate, protocol),
                        policy_role="crossover",
                    )
                )
    return tuple(cells)


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


def _measured_wall_times(evidence: BenchmarkEvidence) -> tuple[float, ...]:
    """Return complete measured stage times after validating stage identity."""
    observations: list[float] = []
    for measurement in evidence.measurements:
        if measurement.warmup:
            continue
        stages = {item.stage: item.metrics for item in measurement.stages}
        if set(stages) != {_STAGE_NAME}:
            raise ValueError("matrix evidence omitted the Phase 5 stage")
        if stages[_STAGE_NAME] != measurement.complete:
            raise ValueError("Phase 5 stage and complete metrics differ")
        observations.append(measurement.complete.wall_seconds)
    if not observations:
        raise ValueError("matrix evidence contains no measured repetitions")
    return tuple(observations)


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
    observations = _measured_wall_times(loaded)
    quartiles = statistics.quantiles(observations, n=4, method="inclusive")
    measured = tuple(
        item.complete for item in loaded.measurements if not item.warmup
    )
    return {
        "boundary_summary_array_bytes": status["boundary_summary_array_bytes"],
        "dataset_id": loaded.dataset.identifier,
        "detection_island_count": status["detection_island_count"],
        "evidence_sha256": hashlib.sha256(
            evidence_path.read_bytes()
        ).hexdigest(),
        "executor": identity.executor,
        "maximum_batch_partition_count": status[
            "maximum_batch_partition_count"
        ],
        "maximum_graph_width": status["maximum_graph_width"],
        "maximum_peak_rss_bytes": max(
            item.peak_rss_bytes for item in measured
        ),
        "maximum_read_pixel_count": status["maximum_read_pixel_count"],
        "maximum_retained_array_bytes": status["maximum_retained_array_bytes"],
        "maximum_wall_seconds": max(observations),
        "maximum_worker_bytes": status["maximum_worker_bytes"],
        "maximum_workspace_bytes": status["maximum_workspace_bytes"],
        "median_wall_seconds": statistics.median(observations),
        "minimum_wall_seconds": min(observations),
        "partition_count": status["partition_count"],
        "policy_role": identity.policy_role,
        "profile": identity.profile,
        "published_product_shard_count": status[
            "published_product_shard_count"
        ],
        "quartile_1_wall_seconds": quartiles[0],
        "quartile_3_wall_seconds": quartiles[2],
        "reconstruction_island_count": status["reconstruction_island_count"],
        "scale_island_counts": status["scale_island_counts"],
        "setup_wall_seconds_excluded": status["setup_wall_seconds"],
        "size_pixels": identity.size,
        "task_count": status["task_count"],
        "tile_size_pixels": identity.tile_size,
    }


def _budget_decision(
    cells: list[dict[str, object]],
    protocol: MatrixProtocol,
) -> dict[str, object]:
    """Apply the frozen representative incremental-stage budget."""
    representative = [
        cell
        for cell in cells
        if cell["size_pixels"] == protocol.representative_size
        and cell["policy_role"] == "primary"
    ]
    failures = [
        cast(str, cell["profile"])
        for cell in representative
        if cast(float, cell["median_wall_seconds"])
        > protocol.multiscale_budget_seconds
    ]
    return {
        "failed_profiles": failures,
        "multiscale_processing_budget_seconds": (
            protocol.multiscale_budget_seconds
        ),
        "passed": not failures,
        "representative_executor": _primary_executor(
            protocol.representative_size,
            protocol,
        ),
        "representative_size_pixels": protocol.representative_size,
    }


def _crossover_summary(
    cells: list[dict[str, object]],
    protocol: MatrixProtocol,
) -> dict[str, object]:
    """Compare both executor paths at the frozen crossover anchors."""
    rows: list[dict[str, object]] = []
    for size in protocol.crossover_sizes:
        for profile in protocol.profiles:
            by_executor = {
                cast(str, cell["executor"]): cell
                for cell in cells
                if cell["size_pixels"] == size and cell["profile"] == profile
            }
            if set(by_executor) != set(protocol.crossover_executors):
                raise ValueError("crossover evidence is incomplete")
            serial = cast(float, by_executor["serial"]["median_wall_seconds"])
            dask = cast(float, by_executor["dask"]["median_wall_seconds"])
            rows.append(
                {
                    "dask_median_seconds": dask,
                    "dask_to_serial_ratio": dask / serial,
                    "faster_executor": "dask" if dask < serial else "serial",
                    "profile": profile,
                    "serial_median_seconds": serial,
                    "size_pixels": size,
                }
            )
    return {
        "interpretation": (
            "development crossover evidence; changing the execution policy "
            "requires a prospective reviewed configuration update"
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
    for identity in _cell_identities(protocol):
        input_id = f"phase5-{identity.profile}-{identity.size}"
        input_path = inputs / f"{input_id}.fits"
        evidence_path = evidence_directory / f"{identity.identifier}.json"
        status_path = status_directory / f"{identity.identifier}.json"
        if not input_path.exists():
            subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts/benchmark/generate_phase5_input.py"),
                    "--size",
                    str(identity.size),
                    "--profile",
                    identity.profile,
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
                f"incomplete matrix cell state for {identity.identifier}; "
                "use a new output directory"
            )
        else:
            status = _run(
                [
                    sys.executable,
                    str(
                        root / "scripts/benchmark/measure_phase5_multiscale.py"
                    ),
                    "--input",
                    str(input_path),
                    "--dataset-id",
                    input_id,
                    "--profile",
                    identity.profile,
                    "--workload-class",
                    protocol.workload_classes[identity.profile],
                    "--executor",
                    identity.executor,
                    "--workers",
                    str(protocol.workers),
                    "--threads-per-worker",
                    str(protocol.threads_per_worker),
                    "--tile-size",
                    str(identity.tile_size),
                    "--maximum-tiles-per-batch",
                    str(protocol.maximum_tiles_per_batch),
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
        cells.append(_cell_summary(evidence_path, status, identity=identity))
    summary = {
        "benchmark_id": protocol.benchmark_id,
        "budget_decision": _budget_decision(cells, protocol),
        "cells": cells,
        "crossover_summary": _crossover_summary(cells, protocol),
        "previous_curve_comparison": {
            "available": False,
            "reason": (
                "this is the first reviewed complete Phase 5 incremental "
                "stage curve; later candidates must compare against it"
            ),
        },
        "protocol_sha256": hashlib.sha256(
            args.config.read_bytes()
        ).hexdigest(),
        "schema_version": 1,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(summary_path)
    if not cast(dict[str, object], summary["budget_decision"])["passed"]:
        raise SystemExit("Phase 5 incremental performance budget failed")


if __name__ == "__main__":
    main()
