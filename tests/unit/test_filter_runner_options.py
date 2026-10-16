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
        parse(["--label", "screening", *options]),
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


def test_filter_benchmark_lists_its_cases_when_given_an_unknown_one() -> None:
    case_of = cast(
        Callable[[str], tuple[Any, Path]], _FILTER_BENCHMARK["_case"]
    )

    with pytest.raises(ValueError, match="lotss-dr3-1312-15402"):
        case_of("lotss-dr3-1312-missing")
