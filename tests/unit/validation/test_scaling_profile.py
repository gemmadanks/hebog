"""Contracts of the sector-scaling summary built from profile records."""

from __future__ import annotations

from typing import Any

import pytest

from hebog.validation.scaling_profile import (
    ScalingPoint,
    fit_amdahl,
    scaling_point,
    scaling_summary,
)

_ROOT = "find_sources"


def _record(
    workers: int,
    stage_walls: dict[str, float],
    *,
    idle: dict[str, float] | None = None,
    rounds: dict[str, tuple[int, float]] | None = None,
) -> dict[str, Any]:
    """Return a worker record whose root holds the given top-level stages."""
    idle = idle or {}
    total = sum(stage_walls.values())
    stages = [
        {"stage": [_ROOT], "wall_seconds": total, "driver_cpu_seconds": 1.0}
    ] + [
        {
            "stage": [_ROOT, name],
            "wall_seconds": wall,
            "driver_cpu_seconds": 0.5,
        }
        for name, wall in stage_walls.items()
    ]
    occupancy = [
        {
            "stage": [_ROOT],
            "task_count": 10,
            "task_seconds": 2.0 * total,
            "worker_occupancy": 0.5,
            "executor_idle_seconds": sum(idle.values()),
            "zarr_io": {
                "read_chunks": 4,
                "read_bytes": 4096,
                "written_chunks": 2,
            },
        }
    ] + [
        {
            "stage": [_ROOT, name],
            "task_count": 5,
            "task_seconds": wall,
            "worker_occupancy": 0.5,
            "executor_idle_seconds": idle.get(name, 0.0),
            "zarr_io": {
                "read_chunks": 0,
                "read_bytes": 0,
                "written_chunks": 0,
            },
        }
        for name, wall in stage_walls.items()
    ]
    return {
        "root_stage": _ROOT,
        "stages": stages,
        "executor": {"kind": "dask", "workers": workers},
        "process": {"peak_rss_bytes": 1_000 * workers},
        "tasks": {
            "count": 10,
            "task_seconds": 2.0 * total,
            "stages": occupancy,
            "rounds": [
                {"round": name, "task_count": count, "task_seconds": seconds}
                for name, (count, seconds) in (rounds or {}).items()
            ],
        },
    }


def test_amdahl_fit_recovers_the_serial_and_parallel_seconds() -> None:
    """A run of 10 serial and 90 parallel seconds is 10 + 90 / n."""
    fit = fit_amdahl([(n, 10.0 + 90.0 / n) for n in (1, 2, 4, 8, 12)])

    assert fit is not None
    assert fit.serial_seconds == pytest.approx(10.0)
    assert fit.parallel_seconds == pytest.approx(90.0)
    assert fit.serial_fraction == pytest.approx(0.1)
    assert fit.maximum_absolute_residual_seconds == pytest.approx(
        0.0, abs=1e-9
    )


def test_amdahl_needs_two_worker_counts() -> None:
    assert fit_amdahl([(1, 10.0)]) is None
    assert fit_amdahl([(4, 10.0), (4, 11.0)]) is None


def test_a_point_reads_the_root_and_top_level_stages() -> None:
    point = scaling_point(
        _record(
            2, {"a": 6.0, "b": 4.0}, idle={"b": 3.0}, rounds={"r": (7, 2.5)}
        )
    )

    assert point == ScalingPoint(
        workers=2,
        wall_seconds=10.0,
        driver_cpu_seconds=1.0,
        executor_idle_seconds=3.0,
        task_count=10,
        task_seconds=20.0,
        zarr_read_bytes=4096,
        zarr_written_chunks=2,
        peak_rss_bytes=2_000,
        largest_worker_peak_rss_bytes=None,
        stage_wall_seconds={"a": 6.0, "b": 4.0},
        stage_idle_seconds={"a": 0.0, "b": 3.0},
        round_task_seconds={"r": 2.5},
        round_task_counts={"r": 7},
    )


def test_summary_reports_speedup_efficiency_and_stage_efficiency() -> None:
    """Stage a scales perfectly; stage b keeps 4 serial seconds."""
    points = [
        scaling_point(
            _record(
                n,
                {"a": 8.0 / n, "b": 4.0 + 4.0 / n},
                idle={"b": 4.0},
                rounds={"r": (3, 2.0 * n)},
            )
        )
        for n in (1, 2, 4)
    ]

    summary = scaling_summary(points)

    curve = {row["workers"]: row for row in summary["curve"]}
    assert curve[1]["speedup"] == 1.0
    assert curve[4]["speedup"] == pytest.approx(16.0 / 7.0)
    assert curve[4]["efficiency"] == pytest.approx(16.0 / 28.0)
    assert curve[4]["executor_idle_fraction"] == pytest.approx(4.0 / 7.0)
    assert summary["amdahl"]["serial_seconds"] == pytest.approx(4.0)
    assert summary["amdahl"]["serial_fraction"] == pytest.approx(0.25)
    stages = {row["stage"]: row for row in summary["stages"]}
    assert stages["a"]["efficiency"]["4"] == pytest.approx(1.0)
    assert stages["b"]["efficiency"]["4"] == pytest.approx(8.0 / (4 * 5.0))
    assert stages["b"]["amdahl"]["serial_seconds"] == pytest.approx(4.0)
    # The serial terms rank stages by their fitted serial seconds.
    assert [row["stage"] for row in summary["serial_terms"]] == ["b", "a"]
    # Task time doubles with every doubling of workers: contention.
    (round_row,) = summary["rounds"]
    assert round_row["round"] == "r"
    assert round_row["task_seconds_inflation"] == pytest.approx(4.0)


def test_summary_refuses_points_of_mixed_or_repeated_worker_counts() -> None:
    point = scaling_point(_record(2, {"a": 1.0}))

    with pytest.raises(ValueError, match="worker count"):
        scaling_summary([point, point])
    with pytest.raises(ValueError, match="one worker"):
        scaling_summary([point])
