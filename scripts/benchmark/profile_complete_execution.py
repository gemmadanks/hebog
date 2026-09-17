#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
"""Profile complete source-finding runs by stage, across size and density.

Cases come from ``config/benchmarks/complete-execution-profile.json``. The
``ladder`` group is a generated grid of noise-only and dense images at 512,
1,024 and 2,048 pixels per side with the same source density at every size
(``build_profile_datasets.py``); the ``real`` group holds LoTSS-DR3 and SDC1
cut-outs. Each case runs ``profile_complete_execution_worker.py`` once in a
fresh single-thread process, and with ``--cprofile`` a second time under
``cProfile``.

The summary fits every top-level stage's wall time on the ladder as
``fixed + a * megapixels + b * components + c * megapixels * components``, so
image size, source count and per-source work over the whole image are
separated, and reports how far each real case lies from that model.
``--summarise-existing`` rebuilds the summary of a completed run. A profile
is diagnostic: it ranks costs to decide what to optimize and never
establishes a speedup, which needs the quick benchmark.
Results go under ``benchmark-results/profiles/runs/<label>``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

import hebog
from hebog.io import FitsImageSource
from hebog.validation.quick_benchmark import (
    SINGLE_THREAD_ENVIRONMENT,
    machine_identity,
    run_measured_process,
    source_tree_sha256,
    worker_environment,
)
from hebog.validation.quick_check import (
    HebogSettings,
    QuickCheckCase,
    file_sha256,
    prepare_case,
    write_report,
)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIGURATION = (
    _ROOT / "config/benchmarks/complete-execution-profile.json"
)
_DEFAULT_OUTPUT = _ROOT / "benchmark-results/profiles"
_WORKER = _ROOT / "scripts/benchmark/profile_complete_execution_worker.py"
_PUBLIC_LIMIT = 1024
_ROOT_STAGE = "find_sources"
_STARTUP_STAGE = "process start-up and imports"
_OTHER_STAGE = "other find_sources work"
_MODEL_TERMS = 4


class _ProfileCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group: Literal["ladder", "real"]
    case: QuickCheckCase


class _ProfileConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    dataset_manifest: str = Field(min_length=1)
    hebog: HebogSettings
    cases: tuple[_ProfileCase, ...] = Field(min_length=1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--configuration", type=Path, default=_DEFAULT_CONFIGURATION
    )
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--label", required=True, help="run directory name")
    parser.add_argument("--cases", nargs="+", help="run only these case IDs")
    parser.add_argument(
        "--cprofile",
        action="store_true",
        help="also run each case under cProfile",
    )
    parser.add_argument(
        "--summarise-existing",
        action="store_true",
        help="rebuild the summary of the completed run named by --label",
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


def _run_worker(
    command: list[str], result: Path, *, cprofile: Path | None
) -> dict[str, Any]:
    arguments = [*command, "--result", str(result)]
    if cprofile is not None:
        arguments += ["--cprofile", str(cprofile)]
    usage = run_measured_process(
        arguments, environment=worker_environment(os.environ)
    )
    record = cast(dict[str, Any], json.loads(result.read_text("utf-8")))
    record["process"] = {
        "wall_seconds": usage.wall_seconds,
        "cpu_seconds": usage.cpu_seconds,
        "peak_rss_bytes": usage.peak_rss_bytes,
    }
    return record


def _top_level_stages(profile: dict[str, Any]) -> dict[str, float]:
    """Return process wall seconds split into start-up and public stages."""
    stages = {tuple(item["stage"]): item for item in profile["stages"]}
    root = stages[(_ROOT_STAGE,)]
    split = {
        path[1]: float(item["wall_seconds"])
        for path, item in stages.items()
        if len(path) == 2  # noqa: PLR2004
    }
    split[_OTHER_STAGE] = float(root["self_wall_seconds"])
    split[_STARTUP_STAGE] = float(profile["process"]["wall_seconds"]) - float(
        root["wall_seconds"]
    )
    return split


def _run_case(
    item: _ProfileCase,
    *,
    configuration: _ProfileConfiguration,
    args: argparse.Namespace,
    run_root: Path,
) -> dict[str, Any]:
    case = item.case
    prepared = prepare_case(
        case,
        dataset_manifest=_ROOT / configuration.dataset_manifest,
        repository_root=_ROOT,
        inputs_root=args.output_root.resolve() / "inputs",
        allow_download=args.allow_download,
    )
    shape_yx = (
        FitsImageSource(prepared.input_path, prepared.supplied_metadata)
        .metadata()
        .shape_yx
    )
    print(f"{case.case_id} {shape_yx}", flush=True)
    command = [
        sys.executable,
        str(_WORKER),
        "--input",
        str(prepared.input_path),
        "--settings",
        configuration.hebog.model_dump_json(),
    ]
    supplied = getattr(case, "supplied_metadata", None)
    if supplied is not None:
        command += ["--supplied-metadata", json.dumps(supplied)]
    if max(shape_yx) > _PUBLIC_LIMIT:
        command += ["--diagnostic-size-limit", str(max(shape_yx))]
    case_root = run_root / case.case_id
    case_root.mkdir(parents=True)
    profile = _run_worker(command, case_root / "profile.json", cprofile=None)
    record: dict[str, Any] = {
        "case_id": case.case_id,
        "group": item.group,
        "input_path": str(prepared.input_path),
        "input_sha256": prepared.input_sha256,
        "shape_yx": list(shape_yx),
        "megapixels": shape_yx[0] * shape_yx[1] / 1e6,
        "profile": profile,
        "top_level_wall_seconds": _top_level_stages(profile),
        "cprofile": None,
    }
    if args.cprofile:
        profiled = _run_worker(
            command,
            case_root / "cprofile.json",
            cprofile=case_root / "profile.pstats",
        )
        record["cprofile"] = {
            "wall_seconds": profiled["process"]["wall_seconds"],
            "top_self_time": profiled["cprofile"]["top_self_time"],
            "statistics": profiled["cprofile"]["statistics"],
        }
    write_report(case_root / "case.json", record)
    return record


def _model_terms(record: dict[str, Any]) -> list[float]:
    megapixels = float(record["megapixels"])
    components = float(record["profile"]["gaussian_component_count"])
    return [1.0, megapixels, components, megapixels * components]


def _size_density_model(
    records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Fit each stage on the ladder against image size and components.

    The interaction term is the cost of work repeated per component over the
    whole image, which grows with the square of image size at fixed density.
    """
    ladder = [record for record in records if record["group"] == "ladder"]
    design = np.array([_model_terms(record) for record in ladder])
    if len(ladder) < _MODEL_TERMS or (
        np.linalg.matrix_rank(design) < _MODEL_TERMS
    ):
        return None
    stages = sorted(
        {
            stage
            for record in ladder
            for stage in record["top_level_wall_seconds"]
        }
    )
    coefficients: dict[str, dict[str, float]] = {}
    for stage in [*stages, "total"]:
        seconds = np.array(
            [
                sum(record["top_level_wall_seconds"].values())
                if stage == "total"
                else record["top_level_wall_seconds"].get(stage, 0.0)
                for record in ladder
            ]
        )
        solution, *_ = np.linalg.lstsq(design, seconds, rcond=None)
        coefficients[stage] = {
            "fixed_seconds": float(solution[0]),
            "seconds_per_megapixel": float(solution[1]),
            "seconds_per_component": float(solution[2]),
            "seconds_per_megapixel_component": float(solution[3]),
            "maximum_absolute_residual_seconds": float(
                np.max(np.abs(seconds - design @ solution))
            ),
        }
    total = coefficients["total"]
    real = [
        {
            "case_id": record["case_id"],
            "megapixels": record["megapixels"],
            "components": record["profile"]["gaussian_component_count"],
            "measured_seconds": sum(record["top_level_wall_seconds"].values()),
            "ladder_model_seconds": float(
                np.dot(
                    _model_terms(record),
                    [
                        total["fixed_seconds"],
                        total["seconds_per_megapixel"],
                        total["seconds_per_component"],
                        total["seconds_per_megapixel_component"],
                    ],
                )
            ),
        }
        for record in records
        if record["group"] == "real"
    ]
    return {"stages": coefficients, "real_cases": real}


def _print_summary(records: list[dict[str, Any]]) -> None:
    for record in records:
        split = record["top_level_wall_seconds"]
        total = sum(split.values())
        profile = record["profile"]
        print(
            f"\n{record['case_id']} {record['shape_yx']}: {total:.1f} s, "
            f"{profile['gaussian_component_count']} components, peak RSS "
            f"{profile['process']['peak_rss_bytes'] / 2**20:.0f} MiB"
        )
        for stage, seconds in sorted(split.items(), key=lambda row: -row[1]):
            print(f"  {seconds:7.2f} s {100 * seconds / total:5.1f}%  {stage}")


def main() -> int:
    args = _parse_args()
    configuration = _ProfileConfiguration.model_validate_json(
        args.configuration.read_text(encoding="utf-8")
    )
    selected = set(cast(list[str], args.cases or []))
    unknown = selected - {item.case.case_id for item in configuration.cases}
    if unknown:
        raise SystemExit(f"unknown case IDs: {sorted(unknown)}")
    run_root = args.output_root.resolve() / "runs" / args.label
    started = time.perf_counter()
    if args.summarise_existing:
        records = [
            cast(dict[str, Any], json.loads(path.read_text("utf-8")))
            for item in configuration.cases
            if (path := run_root / item.case.case_id / "case.json").exists()
            and (not selected or item.case.case_id in selected)
        ]
    elif run_root.exists():
        raise SystemExit(f"run directory already exists: {run_root}")
    else:
        records = [
            _run_case(
                item,
                configuration=configuration,
                args=args,
                run_root=run_root,
            )
            for item in configuration.cases
            if not selected or item.case.case_id in selected
        ]
    report: dict[str, Any] = {
        "schema_version": 1,
        "label": args.label,
        "created_at": datetime.now(UTC).isoformat(),
        "hebog_version": hebog.__version__,
        "commit_sha": _git("rev-parse", "HEAD"),
        "worktree_dirty": bool(_git("status", "--porcelain")),
        "source_tree_sha256": source_tree_sha256(_ROOT / "src/hebog"),
        "configuration_sha256": file_sha256(args.configuration),
        "machine": machine_identity(),
        "thread_environment": dict(SINGLE_THREAD_ENVIRONMENT),
        "executor": "serial",
        "elapsed_seconds": time.perf_counter() - started,
        "size_density_model": _size_density_model(records),
        "cases": [
            {key: value for key, value in record.items() if key != "profile"}
            | {
                "components": record["profile"]["gaussian_component_count"],
                "sources": record["profile"]["source_count"],
                "peak_rss_bytes": record["profile"]["process"][
                    "peak_rss_bytes"
                ],
            }
            for record in records
        ],
    }
    if args.summarise_existing:
        (run_root / "summary.json").unlink(missing_ok=True)
    write_report(run_root / "summary.json", report)
    _print_summary(records)
    print(f"\nSummary: {run_root / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
