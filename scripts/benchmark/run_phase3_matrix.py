"""Run the frozen local Phase 3 size and compact-density benchmark matrix."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

from hebog.validation.evidence import WorkloadClass, load_evidence

_SIZES = (256, 512, 1024, 3000)
_WORKLOADS = tuple(item.value for item in WorkloadClass)
_MAXIMUM_SERIAL_SIZE = 1024
_REPRESENTATIVE_TILE_SIZE = 1000


def _parse_args() -> argparse.Namespace:
    """Parse the controlled local matrix request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--workers", default=4, type=int)
    parser.add_argument("--warmups", default=1, type=int)
    parser.add_argument("--repetitions", default=5, type=int)
    return parser.parse_args()


def _execution_policy(size: int) -> tuple[str, int]:
    """Use the low-overhead path below the measured Dask crossover."""
    if size <= _MAXIMUM_SERIAL_SIZE:
        return "serial", size
    return "dask", _REPRESENTATIVE_TILE_SIZE


def _run(command: list[str]) -> None:
    """Run one matrix step and fail without hiding its output."""
    subprocess.run(command, check=True)


def main() -> None:
    """Generate inputs, execute every cell, and write a compact summary."""
    args = _parse_args()
    if args.workers < 1:
        raise ValueError("matrix workers must be positive")
    output = args.output_directory
    inputs = output / "inputs"
    evidence_directory = output / "evidence"
    inputs.mkdir(parents=True, exist_ok=True)
    evidence_directory.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).parents[2]
    summaries: list[dict[str, object]] = []
    for size in _SIZES:
        executor, tile_size = _execution_policy(size)
        for workload in _WORKLOADS:
            identity = f"phase3-{workload}-{size}"
            input_path = inputs / f"{identity}.fits"
            evidence_path = evidence_directory / f"{identity}.json"
            if not input_path.exists():
                _run(
                    [
                        sys.executable,
                        str(
                            root / "scripts/benchmark/generate_phase3_input.py"
                        ),
                        "--size",
                        str(size),
                        "--workload-class",
                        workload,
                        "--output",
                        str(input_path),
                    ]
                )
            _run(
                [
                    sys.executable,
                    str(
                        root / "scripts/benchmark/measure_phase3_detection.py"
                    ),
                    "--input",
                    str(input_path),
                    "--dataset-id",
                    identity,
                    "--workload-class",
                    workload,
                    "--executor",
                    executor,
                    "--workers",
                    str(args.workers),
                    "--tile-size",
                    str(tile_size),
                    "--warmups",
                    str(args.warmups),
                    "--repetitions",
                    str(args.repetitions),
                    "--output",
                    str(evidence_path),
                ]
            )
            evidence = load_evidence(evidence_path)
            if evidence.evidence_type != "benchmark":
                raise TypeError(
                    "matrix cell did not produce benchmark evidence"
                )
            measurements = tuple(
                item.complete.wall_seconds
                for item in evidence.measurements
                if not item.warmup
            )
            summaries.append(
                {
                    "dataset_id": identity,
                    "executor": executor,
                    "size_pixels": size,
                    "tile_size_pixels": tile_size,
                    "workload_class": workload,
                    "median_wall_seconds": statistics.median(measurements),
                    "minimum_wall_seconds": min(measurements),
                    "maximum_wall_seconds": max(measurements),
                    "maximum_peak_rss_bytes": max(
                        item.complete.peak_rss_bytes
                        for item in evidence.measurements
                    ),
                    "task_count": evidence.measurements[
                        -1
                    ].complete.dask_task_count,
                }
            )
    summary_path = output / "matrix-summary.json"
    summary_path.write_text(
        json.dumps(
            {"schema_version": 1, "cells": summaries},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(summary_path)


if __name__ == "__main__":
    main()
