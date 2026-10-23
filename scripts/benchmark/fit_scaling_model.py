#!/usr/bin/env python3
"""Fit the one-sector scaling model and project the gate to the cluster.

This reads evidence already measured, under ``--results-root``, and runs
nothing timed (``hebog.validation.scaling_model`` holds the model):

- the matched container's source-count ladder at four cores and its core
  sweeps (``filter-skymodel/runs/<prefix>*/report.json``), with PyBDSF's
  logs of the sweeps' measured runs: the dense cell's, and a sparse
  sector's when one exists; a sweep point added later, such as two cores,
  is picked up when its report exists;
- Hebog's native stage profiles on single-threaded Dask workers
  (``profiles/runs/<label>/<case>/dask-<n>/<case>/case.json``): the dense
  cell at one to six workers, which converts native seconds to the
  container's and decomposes the serial term, the anchor's sweeps beside
  it, and the latest release's dense and sparse cells at four workers,
  between which the projection interpolates any ladder sector not
  profiled itself (``--ladder-profile``).

It projects both finders' finder parts on every ladder sector to the
cluster's node sizes, ``master`` on all of one node's cores and Hebog on
one to twelve nodes, the targets the gate sets, and the ratios Hebog
would reach with the dense and sparse cells' floors at the given targets
(``--floor-targets``). The JSON summary,
with every input's path and checksum, goes to
``<results-root>/one-sector-scaling/model/<label>.json``; an existing
summary is never replaced::

    uv run python scripts/benchmark/fit_scaling_model.py --label step4 \\
        --results-root ../hebog/benchmark-results
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hebog.validation.quick_benchmark import checkout_identity
from hebog.validation.quick_check import file_sha256, write_report
from hebog.validation.scaling_model import (
    FinderWork,
    HebogRun,
    MatchedRun,
    fit_capped_amdahl,
    fit_line,
    hebog_run,
    hebog_seconds,
    interpolate_runs,
    pybdsf_fit_seconds,
    round_tails,
    serial_term,
    time_targets,
    usable_cores,
    with_floor,
    work_from_cpu,
)
from hebog.validation.scaling_profile import fit_amdahl

_ROOT = Path(__file__).resolve().parents[2]
_DENSE = "elais-n1-deep-north-3600-5000"
_SPARSE = "lotss-dr3-1312-5000"
_ANCHOR = "lotss-dr3-1312-dense-10000"
# The cluster's node kinds (maintainer, 22 October): 96 cores with 747 GB
# and 192 with 747 or 1,494 GB; memory does not bind a 5,000² sector.
_NODE_CORES = (96, 192)
_MOST_NODES = 12
_TOP = 8  # driver stages and round tails listed per decomposition
_ASSUMPTIONS = (
    {
        "assumption": "Rosetta and the container slow both finders alike.",
        "evidence": "Only Hebog has a native measurement; its container "
        "time on one Dask worker is the factor below times its native "
        "time.",
        "effect": "Every projected ratio scales with Hebog's factor over "
        "master's; the cluster run decides.",
    },
    {
        "assumption": "Beyond about four local workers the container "
        "measures contention, not the finders.",
        "evidence": "Hebog's container time on 4 and 6 workers exceeds "
        "its native time times the factor (vm_contention below), while "
        "natively 6 workers still gain.",
        "effect": "Hebog is projected from native profiles, and master's "
        "plateau from its logs, which show the fitting phase, not the "
        "whole run, flat from 4 to 6 cores.",
    },
    {
        "assumption": "The native profiles' shape holds for Rapthor's "
        "settings.",
        "evidence": "The profiles run Hebog's estimated background, which "
        "the profiler cannot change, and the container Rapthor's zero "
        "background (24,194 and 23,921 sources on the dense cell). The "
        "factor is taken on one worker, so the level of every projection "
        "comes from the container's run of Rapthor's settings and only the "
        "curve's shape and the floor's share of the one-worker time from "
        "the profiles.",
        "effect": "Native floors and targets are in the profiles' "
        "settings, as the scaling profile measures them; a zero background "
        "that changes the floor's share moves every projected ratio.",
    },
    {
        "assumption": "Master's parallel parts use at most the cores its "
        "core sweep shows them using, on any node.",
        "evidence": "Its Gaussian fitting takes the same time on 4 and 6 "
        "cores (pybdsf_gaussian_fit_seconds): one bin of islands bounds "
        "it. Only the dense cell has a sweep.",
        "effect": "Without the cap master would be faster on a node; "
        "master_amdahl_seconds and the *_master_amdahl ratios and "
        "targets give that bound. A sector's cap never undercuts the "
        "cores its own run kept busy.",
    },
    {
        "assumption": "Master's serial and parallel work at four cores "
        "follow from its wall and CPU time.",
        "evidence": "CPU = s + p and wall = s + p/4; LSMTool's filtering "
        "is taken as one busy core.",
        "effect": "Uneven parallel work counts as serial, so master's "
        "Amdahl bound is slower than a perfect split.",
    },
    {
        "assumption": "Hebog's driver time and rounds move linearly with "
        "master's source count between the sparse and dense cells.",
        "evidence": "Native profiles exist for two 5,000² sectors of "
        "different fields; the ladder's noise-raised rungs were measured "
        "only on Rapthor's thread path, held by the interpreter lock.",
        "effect": "Intermediate rungs are interpolated, not measured.",
    },
    {
        "assumption": "Hebog's rounds keep the task time and longest task "
        "measured on four workers.",
        "evidence": "Rounds of objects split until each slot has two "
        "batches, so a node's slots shorten their longest tasks further; "
        "tile rounds already run one tile a task at 5,000². The profile "
        "merges a round's repeated invocations under one name, such as "
        "the true-sky and flat-noise background passes, keeping one "
        "longest task.",
        "effect": "The floor is neither bound: high by what more slots "
        "take off the object rounds' longest tasks, low by the longest "
        "tasks of repeated invocations.",
    },
    {
        "assumption": "Screening repetitions bound the inputs.",
        "evidence": "Two measured runs a point (the gate cell five); the "
        "medians are used and the spreads reported.",
        "effect": "Master's one-core runs differ by 15%, which moves its "
        "fitted serial and parallel split, not its plateau.",
    },
)


@dataclass(frozen=True, slots=True)
class _Sector:
    """One ladder sector's gate and its finders' medians."""

    case: str
    report: str
    sector_class: str
    limit: float
    master: MatchedRun
    measured_ratio: float


def _seconds(text: str) -> float:
    """Parse a finite, non-negative number of seconds."""
    value = float(text)
    if not math.isfinite(value) or value < 0.0:
        raise argparse.ArgumentTypeError(
            f"{text} is not a finite, non-negative number of seconds"
        )
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="summary file name")
    parser.add_argument(
        "--results-root",
        type=Path,
        default=_ROOT / "benchmark-results",
        help="the benchmark-results directory holding the evidence",
    )
    parser.add_argument("--ladder-prefix", default="step3-ladder-")
    parser.add_argument("--sweep-prefix", default=f"step3-sweep-{_DENSE}-")
    parser.add_argument(
        "--sparse-sweep-prefix",
        default=f"step4-sweep-{_SPARSE}-",
        help="a sparse sector's core sweep; when absent, sparse sectors "
        "take the dense cell's cap",
    )
    parser.add_argument(
        "--dense-profile", default=f"step3-{_DENSE}", help="1-6 workers"
    )
    parser.add_argument(
        "--anchor-profiles",
        nargs="*",
        default=[f"step3-{_ANCHOR}", "task74-stack"],
    )
    parser.add_argument("--dense-tip-profile", default="increment1-ab-tip-1")
    parser.add_argument(
        "--ladder-profile",
        default="step4-ladder-0.24.0",
        help="native profiles of ladder sectors, used in place of "
        "interpolating between the dense and sparse cells when present",
    )
    parser.add_argument(
        "--sparse-tip-profile",
        default=f"increment1-ab-{_SPARSE}-tip-1",
    )
    parser.add_argument(
        "--floor-targets",
        nargs=2,
        type=_seconds,
        default=[100.0, 40.0],
        metavar=("DENSE", "SPARSE"),
        help="native floors of the dense and sparse cells to project as a "
        "target scenario",
    )
    return parser.parse_args()


class _Inputs:
    """Load JSON and text evidence, recording each file's checksum and the
    identity of each native profile measured."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.files: list[dict[str, str]] = []
        self.identities: dict[str, dict[str, Any]] = {}

    def json(self, path: Path, role: str) -> Any:
        self._record(path, role)
        return json.loads(path.read_text("utf-8"))

    def text(self, path: Path, role: str) -> str:
        self._record(path, role)
        return path.read_text("utf-8")

    def _record(self, path: Path, role: str) -> None:
        self.files.append(
            {
                "path": path.relative_to(self.root).as_posix(),
                "sha256": file_sha256(path),
                "role": role,
            }
        )


def _measured(report: dict[str, Any], finder: str) -> list[dict[str, Any]]:
    return [run for run in report["runs"][finder] if not run["warmup"]]


def _matched_run(report: dict[str, Any], finder: str) -> MatchedRun:
    """Return one finder's medians from one matched report."""
    runs = _measured(report, finder)
    return MatchedRun(
        cores=int(report["configuration"]["cores"]),
        sources=int(report["comparison"]["master_source_count"]),
        finder_seconds=statistics.median(r["finder_seconds"] for r in runs),
        cpu_seconds=statistics.median(r["cpu_seconds"] for r in runs),
        filter_seconds=statistics.median(
            r["filter_sources_seconds"] for r in runs
        ),
    )


def _ladder(inputs: _Inputs, prefix: str) -> list[_Sector]:
    runs = inputs.root / "filter-skymodel" / "runs"
    sectors: list[_Sector] = []
    for path in sorted(runs.glob(f"{prefix}*/report.json")):
        report = inputs.json(path, "ladder report")
        comparison = report["comparison"]
        sectors.append(
            _Sector(
                case=str(report["configuration"]["case"]),
                report=path.relative_to(inputs.root).as_posix(),
                sector_class=str(comparison["sector_class"]),
                limit=float(comparison["maximum_ratio"]),
                master=_matched_run(report, "bdsf"),
                measured_ratio=float(comparison["ratio"]),
            )
        )
    return sorted(sectors, key=lambda sector: sector.master.sources)


def _sweep(inputs: _Inputs, prefix: str) -> list[dict[str, Any]]:
    """Return each core count's medians and master's fitting phases."""
    runs = inputs.root / "filter-skymodel" / "runs"
    points: list[dict[str, Any]] = []
    for path in sorted(runs.glob(f"{prefix}*-cores/report.json")):
        report = inputs.json(path, "core sweep report")
        fits: list[list[float]] = []
        for index, run in enumerate(report["runs"]["bdsf"]):
            logs = sorted(
                (path.parent / "runs" / f"{index:02d}-bdsf").glob(
                    "*-pb.fits.pybdsf.log"
                )
            )
            if not run["warmup"] and len(logs) == 1:
                fits.append(
                    pybdsf_fit_seconds(inputs.text(logs[0], "PyBDSF log"))
                )
        points.append(
            {
                "cores": int(report["configuration"]["cores"]),
                "hebog_dask_workers": report["configuration"][
                    "hebog_dask_workers"
                ],
                "master": _matched_run(report, "bdsf"),
                "hebog": _matched_run(report, "hebog"),
                "master_gaussian_fit_seconds": fits,
            }
        )
    return sorted(points, key=lambda point: point["cores"])


_PROFILE_IDENTITY = (
    "label",
    "commit_sha",
    "worktree_dirty",
    "source_tree_sha256",
    "hebog_version",
    "configuration_sha256",
    "with_flat_noise",
    "memory_budget_bytes",
)


def _profile_runs(
    inputs: _Inputs, label: str, case: str
) -> dict[int, HebogRun]:
    """Return a profile label's Dask runs of one case by worker count.

    Each run's summary, beside its case record, identifies the Hebog
    measured; both files' checksums join the inputs.
    """
    root = inputs.root / "profiles" / "runs" / label / case
    runs: dict[int, HebogRun] = {}
    for path in sorted(root.glob(f"dask-*/{case}/case.json")):
        summary = inputs.json(path.parents[1] / "summary.json", "profile")
        run = hebog_run(inputs.json(path, "native profile")["profile"])
        runs[run.workers] = run
        # Profiles before the flat-noise option lack its field: null.
        inputs.identities[summary["label"]] = {
            key: summary.get(key) for key in _PROFILE_IDENTITY
        }
    return runs


def _decomposition(runs: dict[int, HebogRun]) -> dict[str, Any]:
    """Return a sweep's Amdahl fit and each count's serial term."""
    fit = fit_amdahl([(n, run.wall_seconds) for n, run in runs.items()])
    most = runs[max(runs)]
    return {
        "wall_seconds": {str(n): run.wall_seconds for n, run in runs.items()},
        # The model's lower bound on the profiled counts, against the walls.
        "modelled_seconds": {
            str(n): hebog_seconds(run, n) for n, run in runs.items()
        },
        "amdahl": None if fit is None else fit.document(),
        "serial_terms": [
            serial_term(runs[1], run).document()
            for n, run in sorted(runs.items())
            if n > 1
        ],
        "floor_seconds": {
            str(n): run.floor_seconds for n, run in sorted(runs.items())
        },
        "driver_stages_at_most_workers": dict(
            sorted(
                most.driver_stage_seconds.items(), key=lambda item: -item[1]
            )[:_TOP]
        ),
        "round_tails_at_most_workers": dict(
            round_tails(most, most.workers)[:_TOP]
        ),
    }


def _run_summary(run: HebogRun, sources: int) -> dict[str, Any]:
    return {
        "master_sources": sources,
        "workers": run.workers,
        "wall_seconds": run.wall_seconds,
        "modelled_seconds": hebog_seconds(run, run.workers),
        "driver_seconds": run.driver_seconds,
        "task_seconds": run.task_seconds,
        "span_seconds": run.span_seconds,
        "floor_seconds": run.floor_seconds,
        "largest_longest_tasks": {
            item.name: item.longest_task_seconds
            for item in sorted(
                run.rounds, key=lambda item: -item.longest_task_seconds
            )[:_TOP]
        },
    }


def _sector_projection(
    sector: _Sector,
    run: HebogRun,
    cap: int | None,
    factor: float,
) -> dict[str, Any]:
    """Project one sector's ratio and targets to each node kind."""
    work = work_from_cpu(sector.master)
    capped = work_from_cpu(sector.master, cap)
    nodes: list[dict[str, Any]] = []
    for node_cores in _NODE_CORES:
        master = capped.seconds(node_cores)
        master_amdahl = work.seconds(node_cores)
        curve = [
            {
                "nodes": count,
                "cores": count * node_cores,
                "hebog_native_seconds": hebog_seconds(run, count * node_cores),
            }
            for count in range(1, _MOST_NODES + 1)
        ]
        for point in curve:
            container = factor * point["hebog_native_seconds"]
            point["ratio"] = container / master
            point["ratio_master_amdahl"] = container / master_amdahl
        targets = time_targets(
            run,
            master,
            limit=sector.limit,
            container_factor=factor,
            cores=node_cores,
        )
        strict = time_targets(
            run,
            master_amdahl,
            limit=sector.limit,
            container_factor=factor,
            cores=node_cores,
        )
        nodes.append(
            {
                "node_cores": node_cores,
                "master_seconds": master,
                "master_amdahl_seconds": master_amdahl,
                "curve": curve,
                "targets": targets.document(),
                "targets_master_amdahl": strict.document(),
                "driver_within_floor_target": run.driver_seconds
                <= targets.floor_target_seconds,
            }
        )
    return {
        "case": sector.case,
        "report": sector.report,
        "master_sources": sector.master.sources,
        "sector_class": sector.sector_class,
        "limit": sector.limit,
        "measured_ratio_threads_four_cores": sector.measured_ratio,
        "master_four_cores": {
            "finder_seconds": sector.master.finder_seconds,
            "work": capped.document(),
        },
        "hebog": _run_summary(run, sector.master.sources),
        "nodes": nodes,
    }


def _per_source(
    sectors: list[_Sector],
    runs: list[HebogRun],
    caps: list[int | None],
    factor: float,
) -> dict[str, Any]:
    """Return both finders' lines in the source count on each node kind.

    The dense crossover is the source count above which the lines put
    Hebog within the dense limit: ``factor (a_H + b_H N)`` against
    ``limit (a_M + b_M N)``, or ``None`` if Hebog grows too fast to cross.
    """
    dense_limit = min(sector.limit for sector in sectors)
    document: dict[str, Any] = {"dense_limit": dense_limit, "nodes": []}
    for node_cores in _NODE_CORES:
        master_intercept, master_slope = fit_line(
            [
                (
                    float(sector.master.sources),
                    work_from_cpu(sector.master, cap).seconds(node_cores),
                )
                for sector, cap in zip(sectors, caps, strict=True)
            ]
        )
        _, amdahl_slope = fit_line(
            [
                (
                    float(sector.master.sources),
                    work_from_cpu(sector.master).seconds(node_cores),
                )
                for sector in sectors
            ]
        )
        hebog_intercept, hebog_slope = fit_line(
            [
                (float(sector.master.sources), hebog_seconds(run, node_cores))
                for sector, run in zip(sectors, runs, strict=True)
            ]
        )
        approach = dense_limit * master_slope - factor * hebog_slope
        crossover = (
            (factor * hebog_intercept - dense_limit * master_intercept)
            / approach
            if approach > 0.0
            else None
        )
        document["nodes"].append(
            {
                "node_cores": node_cores,
                "master_container_seconds": master_intercept,
                "master_container_seconds_per_source": master_slope,
                "hebog_native_seconds": hebog_intercept,
                "hebog_native_seconds_per_source": hebog_slope,
                "hebog_native_seconds_per_source_target": dense_limit
                * master_slope
                / factor,
                "master_amdahl_container_seconds_per_source": amdahl_slope,
                "hebog_native_seconds_per_source_target_master_amdahl": (
                    dense_limit * amdahl_slope / factor
                ),
                "dense_crossover_sources": crossover,
            }
        )
    return document


def _master_fit(sweep: list[dict[str, Any]]) -> FinderWork | None:
    """Fit master's core sweep, or return ``None`` below two core counts."""
    points = [
        (point["cores"], point["master"].finder_seconds) for point in sweep
    ]
    if len({cores for cores, _ in points}) < 2:  # noqa: PLR2004 two terms
        return None
    return fit_capped_amdahl(points)


def _master_document(
    sweep: list[dict[str, Any]], fit: FinderWork | None
) -> dict[str, Any]:
    return {
        "core_sweep": [
            {
                "cores": point["cores"],
                "finder_seconds": point["master"].finder_seconds,
                "cpu_seconds": point["master"].cpu_seconds,
                "pybdsf_gaussian_fit_seconds": point[
                    "master_gaussian_fit_seconds"
                ],
                # The first phase fits the image's islands; the rest the
                # wavelet scales' residuals.
                "pybdsf_main_gaussian_fit_median_seconds": statistics.median(
                    phases[0]
                    for phases in point["master_gaussian_fit_seconds"]
                )
                if point["master_gaussian_fit_seconds"]
                else None,
            }
            for point in sweep
        ],
        "capped_amdahl": None if fit is None else fit.document(),
    }


def _container_factor(
    sweep: list[dict[str, Any]], native: dict[int, HebogRun]
) -> dict[str, Any]:
    """Return Hebog's container seconds over its native seconds.

    The factor is taken on one worker; at more workers the container's
    excess over the factor is the VM's contention.
    """
    container = {
        point["hebog_dask_workers"]: point["hebog"].finder_seconds
        for point in sweep
    }
    factor = container[1] / native[1].wall_seconds
    return {
        "factor": factor,
        "vm_contention": [
            {
                "workers": workers,
                "container_seconds": seconds,
                "native_seconds": native[workers].wall_seconds,
                "container_over_factor_times_native": seconds
                / (factor * native[workers].wall_seconds),
            }
            for workers, seconds in sorted(container.items())
            if workers in native
        ],
    }


def _floor_scenario(
    sectors: list[_Sector],
    runs: list[HebogRun],
    caps: list[int | None],
    factor: float,
    floors: tuple[float, float],
) -> dict[str, Any]:
    """Project every sector with the dense and sparse cells' floors set.

    A sector's floor moves linearly in the source count between the two
    cells' targets, with its task time unchanged.
    """
    dense_floor, sparse_floor = floors
    by_case = {sector.case: sector for sector in sectors}
    low, high = by_case[_SPARSE].master.sources, by_case[_DENSE].master.sources
    rows: list[dict[str, Any]] = []
    for sector, run, cap in zip(sectors, runs, caps, strict=True):
        weight = (sector.master.sources - low) / (high - low)
        floor = max(sparse_floor + weight * (dense_floor - sparse_floor), 0.0)
        lowered = with_floor(run, floor)
        work = work_from_cpu(sector.master)
        capped = work_from_cpu(sector.master, cap)
        rows.append(
            {
                "case": sector.case,
                "master_sources": sector.master.sources,
                "limit": sector.limit,
                "floor_seconds": floor,
                "nodes": [
                    {
                        "node_cores": node_cores,
                        "ratio": factor
                        * hebog_seconds(lowered, node_cores)
                        / capped.seconds(node_cores),
                        "ratio_master_amdahl": factor
                        * hebog_seconds(lowered, node_cores)
                        / work.seconds(node_cores),
                    }
                    for node_cores in _NODE_CORES
                ],
            }
        )
    return {
        "dense_floor_seconds": dense_floor,
        "sparse_floor_seconds": sparse_floor,
        "sectors": rows,
    }


def main() -> int:
    """Fit, project and write the summary."""
    args = _parse_args()
    results = args.results_root.resolve()
    inputs = _Inputs(results)
    sectors = _ladder(inputs, args.ladder_prefix)
    by_case = {sector.case: sector for sector in sectors}
    sweep = _sweep(inputs, args.sweep_prefix)
    sparse_sweep = _sweep(inputs, args.sparse_sweep_prefix)
    master_fit = _master_fit(sweep)
    if master_fit is None:
        raise SystemExit("the dense cell's core sweep needs two core counts")
    sparse_fit = _master_fit(sparse_sweep)
    # A sector's cap never undercuts the cores its own run kept busy.
    caps = [
        usable_cores(
            sector.master,
            sparse_fit.usable_cores
            if sparse_fit is not None and sector.sector_class == "sparse"
            else master_fit.usable_cores,
        )
        for sector in sectors
    ]
    dense_runs = _profile_runs(inputs, args.dense_profile, _DENSE)
    container = _container_factor(sweep, dense_runs)
    factor = container["factor"]

    dense_tip = _profile_runs(inputs, args.dense_tip_profile, _DENSE)
    sparse_tip = _profile_runs(inputs, args.sparse_tip_profile, _SPARSE)
    dense_run, sparse_run = (
        dense_tip[max(dense_tip)],
        sparse_tip[max(sparse_tip)],
    )
    dense_sources = by_case[_DENSE].master.sources
    sparse_sources = by_case[_SPARSE].master.sources
    sector_runs: list[HebogRun] = []
    for sector in sectors:
        measured = _profile_runs(inputs, args.ladder_profile, sector.case)
        sector_runs.append(
            measured[max(measured)]
            if measured
            else interpolate_runs(
                sparse_run,
                sparse_sources,
                dense_run,
                dense_sources,
                sector.master.sources,
            )
        )
    projections = [
        _sector_projection(sector, run, cap, factor)
        for sector, run, cap in zip(sectors, sector_runs, caps, strict=True)
    ]
    anchors = {
        label: _decomposition(_profile_runs(inputs, label, _ANCHOR))
        for label in args.anchor_profiles
    }
    checkout = checkout_identity(_ROOT)
    report = {
        "schema_version": 1,
        "label": args.label,
        "created_at": datetime.now(UTC).isoformat(),
        "commit_sha": checkout.commit_sha,
        "worktree_dirty": checkout.worktree_dirty,
        "source_tree_sha256": checkout.source_tree_sha256,
        "inputs": inputs.files,
        "native_profiles": inputs.identities,
        "assumptions": list(_ASSUMPTIONS),
        "container_factor": container,
        "master": {
            "dense": _master_document(sweep, master_fit),
            "sparse": _master_document(sparse_sweep, sparse_fit),
        },
        "hebog": {
            "dense_cell": _decomposition(dense_runs),
            "anchor": anchors,
            "projection_runs": {
                "dense": _run_summary(dense_run, dense_sources),
                "sparse": _run_summary(sparse_run, sparse_sources),
            },
        },
        "sectors": projections,
        "per_source": _per_source(sectors, sector_runs, caps, factor),
        "floor_scenario": _floor_scenario(
            sectors, sector_runs, caps, factor, tuple(args.floor_targets)
        ),
    }
    output = results / "one-sector-scaling" / "model" / f"{args.label}.json"
    write_report(output, report)
    _print_summary(report)
    print(f"\nSummary: {output}")
    return 0


def _print_summary(report: dict[str, Any]) -> None:
    factor = report["container_factor"]["factor"]
    print(f"container factor {factor:.2f}")
    print(f"master's dense fit {report['master']['dense']['capped_amdahl']}")
    for node in report["per_source"]["nodes"]:
        print(
            f"{node['node_cores']} cores: dense crossover "
            f"{node['dense_crossover_sources']} sources; Hebog "
            f"{1e3 * node['hebog_native_seconds_per_source']:.1f} ms a "
            f"source, target "
            f"{1e3 * node['hebog_native_seconds_per_source_target']:.1f}"
        )
    for sector in report["sectors"]:
        for node in sector["nodes"]:
            first, last = node["curve"][0], node["curve"][-1]
            targets = node["targets"]
            print(
                f"{sector['case']:<36} {sector['master_sources']:>6} "
                f"{node['node_cores']:>3} cores: master "
                f"{node['master_seconds']:6.0f} s, ratio "
                f"{first['ratio']:.2f} (1 node) {last['ratio']:.2f} "
                f"(12), master-Amdahl {first['ratio_master_amdahl']:.2f}; "
                f"floor {sector['hebog']['floor_seconds']:.0f} s "
                f"target {targets['floor_target_seconds']:.0f} s"
            )
    scenario = report["floor_scenario"]
    print(
        f"with floors of {scenario['dense_floor_seconds']:.0f} s (dense) and "
        f"{scenario['sparse_floor_seconds']:.0f} s (sparse) on 96 cores:"
    )
    for row in scenario["sectors"]:
        node = row["nodes"][0]
        print(
            f"  {row['master_sources']:>6} sources, limit {row['limit']}: "
            f"{node['ratio']:.2f} ({node['ratio_master_amdahl']:.2f})"
        )


if __name__ == "__main__":
    raise SystemExit(main())
