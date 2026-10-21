# pyright: reportPrivateUsage=false
"""Options of the filter benchmark and LSMTool check runners."""

from __future__ import annotations

import argparse
import json
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from hebog.adapters import RapthorCompatibilityConfig
from hebog.validation.contracts import (
    PyBdsfMasterGate,
    load_performance_matrix,
)
from hebog.validation.evidence import ExecutorKind, ResourceAllocation

_ROOT = Path(__file__).parents[2]
_FILTER_BENCHMARK = runpy.run_path(
    str(_ROOT / "scripts/benchmark/measure_filter_skymodel.py")
)
_LSMTOOL_CHECK = runpy.run_path(
    str(_ROOT / "scripts/validation/check_lsmtool_filter.py")
)
_SCALING_PROFILE = _ROOT / "config/benchmarks/sector-scaling-profile.json"
_CHECK_INPUTS = (
    "--true-sky",
    "true.fits",
    "--flat-noise",
    "flat.fits",
    "--output",
    "check",
)


def _check_settings(*options: str) -> RapthorCompatibilityConfig:
    parse = cast(
        Callable[[list[str]], argparse.Namespace],
        _LSMTOOL_CHECK["_parse_args"],
    )
    compatibility = cast(
        Callable[[argparse.Namespace], RapthorCompatibilityConfig],
        _LSMTOOL_CHECK["_compatibility"],
    )
    return compatibility(parse([*_CHECK_INPUTS, *options]))


def _worker_command(finder: str, *options: str) -> list[str]:
    parse = cast(
        Callable[[list[str]], argparse.Namespace],
        _FILTER_BENCHMARK["_parse_args"],
    )
    command = cast(
        Callable[..., list[str]], _FILTER_BENCHMARK["_container_command"]
    )
    return command(
        parse(
            ["--label", "screening", "--container-image", "image", *options]
        ),
        Path("sector"),
        finder,
        beam_ms=False,
    )


def test_lsmtool_check_keeps_the_adapter_defaults() -> None:
    assert _check_settings() == RapthorCompatibilityConfig(
        threshpix=5.0, threshisl=3.0
    )


def test_lsmtool_check_runs_the_chosen_profile_and_background() -> None:
    settings = _check_settings(
        "--profile", "continuum", "--background", "estimated"
    )

    assert (settings.profile, settings.background) == (
        "continuum",
        "estimated",
    )


def test_filter_benchmark_names_the_image_it_measures() -> None:
    """A default image once measured a stale build of Hebog and Rapthor."""
    parse = cast(
        Callable[[list[str]], argparse.Namespace],
        _FILTER_BENCHMARK["_parse_args"],
    )

    with pytest.raises(SystemExit):
        parse(["--label", "screening"])


def test_filter_benchmark_runs_hebog_on_threads_by_default() -> None:
    assert "--dask-workers" not in _worker_command("hebog")


def test_filter_benchmark_gives_only_hebog_the_dask_workers() -> None:
    hebog = _worker_command("hebog", "--hebog-dask-workers", "4")
    pybdsf = _worker_command("bdsf", "--hebog-dask-workers", "4")

    assert hebog[hebog.index("--dask-workers") + 1] == "4"
    assert "--dask-workers" not in pybdsf


@pytest.mark.parametrize(
    "case_id", ["lotss-dr3-1312-dense-10000", "lotss-dr3-1312-15402"]
)
def test_filter_benchmark_measures_the_scaling_profile_sectors(
    case_id: str,
) -> None:
    case_of = cast(
        Callable[[str], tuple[Any, Path]], _FILTER_BENCHMARK["_case"]
    )
    profile = json.loads(_SCALING_PROFILE.read_text(encoding="utf-8"))

    case, dataset_manifest = case_of(case_id)

    assert case.case_id == case_id
    assert dataset_manifest == _ROOT / profile["dataset_manifest"]


_LADDER_CASES = (
    "lotss-dr3-1312-5000",
    "elais-n1-deep-north-3600-5000",
    "elais-n1-deep-central-5000",
)


@pytest.mark.parametrize("case_id", _LADDER_CASES)
def test_filter_benchmark_measures_the_source_count_ladder(
    case_id: str,
) -> None:
    """Every rung is one size, so only the sources change along it."""
    case_of = cast(
        Callable[[str], tuple[Any, Path]], _FILTER_BENCHMARK["_case"]
    )

    case, _ = case_of(case_id)

    assert case.case_id == case_id
    assert case.kind == "image"
    assert case.window.size == 5000


def test_filter_benchmark_lists_its_cases_when_given_an_unknown_one() -> None:
    case_of = cast(
        Callable[[str], tuple[Any, Path]], _FILTER_BENCHMARK["_case"]
    )

    with pytest.raises(ValueError, match="lotss-dr3-1312-15402"):
        case_of("lotss-dr3-1312-missing")


def _timed_run(
    finder_seconds: float,
    wall_seconds: float,
    *,
    warmup: bool = False,
    catalogue_rows: int = 12_000,
) -> dict[str, Any]:
    return {
        "finder_seconds": finder_seconds,
        "filter_sources_seconds": wall_seconds - finder_seconds,
        "wall_seconds": wall_seconds,
        "warmup": warmup,
        "catalogue_rows": catalogue_rows,
    }


def _master_gate() -> PyBdsfMasterGate:
    return load_performance_matrix(
        _ROOT / "config/benchmarks/phase-0-performance.json"
    ).pybdsf_master


def _compare() -> Callable[..., dict[str, Any]]:
    return cast(
        Callable[..., dict[str, Any]], _FILTER_BENCHMARK["_compare_phases"]
    )


def test_filter_benchmark_gates_the_finder_phase_and_reports_the_step() -> (
    None
):
    """The gate binds the source-finding span, which the finder controls.

    LSMTool's filtering is the same for either finder, so the complete step
    is reported beside the gate, never gated; warm-ups count for neither.
    """
    runs = {
        "hebog": [
            _timed_run(400.0, 800.0, warmup=True),
            *(_timed_run(40.0, 80.0) for _ in range(3)),
        ],
        "bdsf": [
            _timed_run(1.0, 2.0, warmup=True),
            *(_timed_run(100.0, 100.0) for _ in range(3)),
        ],
    }

    comparison = _compare()(runs, _master_gate(), resamples=50)

    assert comparison["phase"] == "finder"
    assert comparison["ratio"] == pytest.approx(0.4)
    assert comparison["master_source_count"] == 12_000
    assert comparison["sector_class"] == "dense"
    assert comparison["maximum_ratio"] == 0.5
    assert comparison["outcome"] == "pass"
    assert comparison["complete_step"]["ratio"] == pytest.approx(0.8)
    assert comparison["complete_step"]["upper_bound"] == pytest.approx(0.8)


def test_filter_benchmark_holds_a_sparse_sector_to_parity() -> None:
    """Where ``master`` finds fewer than 10,000 sources, keeping up passes.

    The same timings would fail a dense sector's limit of 0.50.
    """
    runs = {
        "hebog": [_timed_run(80.0, 100.0) for _ in range(3)],
        "bdsf": [
            _timed_run(100.0, 120.0, catalogue_rows=9_276) for _ in range(3)
        ],
    }

    comparison = _compare()(runs, _master_gate(), resamples=50)

    assert comparison["ratio"] == pytest.approx(0.8)
    assert comparison["master_source_count"] == 9_276
    assert comparison["sector_class"] == "sparse"
    assert comparison["maximum_ratio"] == 1.05
    assert comparison["outcome"] == "pass"


def test_filter_benchmark_refuses_a_sector_master_counts_differently() -> None:
    """A sector's class needs one source count from ``master``'s runs."""
    runs = {
        "hebog": [_timed_run(40.0, 80.0) for _ in range(2)],
        "bdsf": [
            _timed_run(100.0, 100.0, catalogue_rows=9_999),
            _timed_run(100.0, 100.0, catalogue_rows=10_000),
        ],
    }

    with pytest.raises(ValueError, match="9999, 10000"):
        _compare()(runs, _master_gate(), resamples=50)


@pytest.mark.parametrize(
    ("finder", "dask_workers", "executor", "workers", "threads"),
    (
        ("bdsf", None, ExecutorKind.EXTERNAL, 1, 4),
        ("hebog", None, ExecutorKind.LOCAL, 1, 4),
        ("hebog", 4, ExecutorKind.DASK, 4, 1),
    ),
)
def test_filter_benchmark_records_how_each_finder_used_its_cores(
    finder: str,
    dask_workers: int | None,
    executor: ExecutorKind,
    workers: int,
    threads: int,
) -> None:
    """Each finder's evidence names its own workers and threads.

    ``master`` and Rapthor's thread path run one process on every core;
    Hebog's Dask screening runs single-threaded worker processes, each
    admitted an equal share of the container's memory.
    """
    finder_resources = cast(
        Callable[..., ResourceAllocation],
        _FILTER_BENCHMARK["_finder_resources"],
    )

    resources = finder_resources(
        finder, cores=4, dask_workers=dask_workers, memory_bytes=16 * 2**30
    )

    assert resources.executor == executor
    assert resources.allocated_cpu_cores == 4
    assert resources.workers_per_node == workers
    assert resources.threads_per_worker == threads
    assert resources.worker_memory_limit_bytes * workers == 16 * 2**30
