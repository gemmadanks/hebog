"""Summarise how one sector's run scales with its executor's workers.

``scripts/benchmark/profile_scaling.py`` profiles one case at several worker
counts under one executor (plan task 73) and reads each profile worker
record into a :class:`ScalingPoint`. :func:`scaling_summary` then reports:

- the curve: the run's wall time, speedup and parallel efficiency at every
  count, beside the time no task ran (the executor idle time, which more
  workers cannot shorten) and the run's summed task time;
- the serial share, by fitting Amdahl's law ``T(n) = s + p / n`` to the
  curve, for the run and for each top-level stage;
- each top-level stage's parallel efficiency ``W(1) / (n W(n))``, and the
  serial terms, the stages ranked by their fitted serial seconds;
- each round's task-time inflation, its summed task time at the most
  workers over that at one: tasks that take longer when more run at once
  contend for something, such as the interpreter lock or slower cores.

The run's time is its root stage's wall time, so process start-up and
imports are left out. Nothing here runs at import.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

_STAGE_DEPTH = 2  # (root, stage): the root's direct children


@dataclass(frozen=True, slots=True)
class AmdahlFit:
    """A run's fitted serial and parallel seconds, ``T(n) = s + p / n``."""

    serial_seconds: float
    parallel_seconds: float
    maximum_absolute_residual_seconds: float

    @property
    def serial_fraction(self) -> float:
        """Return the serial share of the fitted one-worker time."""
        total = self.serial_seconds + self.parallel_seconds
        return self.serial_seconds / total if total else 0.0

    def document(self) -> dict[str, float]:
        """Return one JSON-serializable fit."""
        return {
            "serial_seconds": self.serial_seconds,
            "parallel_seconds": self.parallel_seconds,
            "serial_fraction": self.serial_fraction,
            "maximum_absolute_residual_seconds": (
                self.maximum_absolute_residual_seconds
            ),
        }


@dataclass(frozen=True, slots=True)
class ScalingPoint:
    """One profiled run of one case at one worker count.

    Stage and round mappings are keyed by the top-level stage's name and the
    round's name. ``largest_worker_peak_rss_bytes`` is a Dask worker
    process's; it is ``None`` when the tasks ran in the driver's process.
    """

    workers: int
    wall_seconds: float
    driver_cpu_seconds: float
    executor_idle_seconds: float
    task_count: int
    task_seconds: float
    zarr_read_bytes: int
    zarr_written_chunks: int
    peak_rss_bytes: int
    largest_worker_peak_rss_bytes: int | None
    stage_wall_seconds: Mapping[str, float]
    stage_idle_seconds: Mapping[str, float]
    round_task_seconds: Mapping[str, float]
    round_task_counts: Mapping[str, int]


def fit_amdahl(points: Sequence[tuple[int, float]]) -> AmdahlFit | None:
    """Fit ``(workers, seconds)`` to ``s + p / n`` by least squares.

    Returns ``None`` unless the points hold two distinct worker counts.
    """
    if len({workers for workers, _ in points}) < 2:  # noqa: PLR2004 two terms
        return None
    design = np.array([(1.0, 1.0 / workers) for workers, _ in points])
    seconds = np.array([seconds for _, seconds in points])
    solution, *_ = np.linalg.lstsq(design, seconds, rcond=None)
    return AmdahlFit(
        serial_seconds=float(solution[0]),
        parallel_seconds=float(solution[1]),
        maximum_absolute_residual_seconds=float(
            np.max(np.abs(seconds - design @ solution))
        ),
    )


def scaling_point(record: Mapping[str, Any]) -> ScalingPoint:
    """Read one profile worker record, with its process usage."""
    root = str(record["root_stage"])
    stages = {tuple(item["stage"]): item for item in record["stages"]}
    tasks = record["tasks"]
    occupancy = {tuple(item["stage"]): item for item in tasks["stages"]}
    root_occupancy = occupancy[(root,)]
    return ScalingPoint(
        workers=int(record["executor"]["workers"]),
        wall_seconds=float(stages[(root,)]["wall_seconds"]),
        driver_cpu_seconds=float(stages[(root,)]["driver_cpu_seconds"]),
        executor_idle_seconds=float(root_occupancy["executor_idle_seconds"]),
        task_count=int(tasks["count"]),
        task_seconds=float(tasks["task_seconds"]),
        zarr_read_bytes=int(root_occupancy["zarr_io"]["read_bytes"]),
        zarr_written_chunks=int(root_occupancy["zarr_io"]["written_chunks"]),
        peak_rss_bytes=int(record["process"]["peak_rss_bytes"]),
        largest_worker_peak_rss_bytes=record["executor"].get(
            "largest_worker_peak_rss_bytes"
        ),
        stage_wall_seconds={
            path[1]: float(item["wall_seconds"])
            for path, item in stages.items()
            if len(path) == _STAGE_DEPTH and path[0] == root
        },
        stage_idle_seconds={
            path[1]: float(item["executor_idle_seconds"])
            for path, item in occupancy.items()
            if len(path) == _STAGE_DEPTH and path[0] == root
        },
        round_task_seconds={
            item["round"]: float(item["task_seconds"])
            for item in tasks["rounds"]
        },
        round_task_counts={
            item["round"]: int(item["task_count"]) for item in tasks["rounds"]
        },
    )


def _fit_document(fit: AmdahlFit | None) -> dict[str, float] | None:
    return None if fit is None else fit.document()


def _curve_row(point: ScalingPoint, base: ScalingPoint) -> dict[str, Any]:
    """Return one worker count's row of the curve."""
    return {
        "workers": point.workers,
        "wall_seconds": point.wall_seconds,
        "speedup": base.wall_seconds / point.wall_seconds,
        "efficiency": base.wall_seconds / (point.workers * point.wall_seconds),
        "executor_idle_seconds": point.executor_idle_seconds,
        "executor_idle_fraction": point.executor_idle_seconds
        / point.wall_seconds,
        "driver_cpu_seconds": point.driver_cpu_seconds,
        "task_count": point.task_count,
        "task_seconds": point.task_seconds,
        "zarr_read_bytes": point.zarr_read_bytes,
        "zarr_written_chunks": point.zarr_written_chunks,
        "peak_rss_bytes": point.peak_rss_bytes,
        "largest_worker_peak_rss_bytes": point.largest_worker_peak_rss_bytes,
    }


def _stage_row(name: str, ordered: Sequence[ScalingPoint]) -> dict[str, Any]:
    """Return one top-level stage's wall time, efficiency and serial fit."""
    walls = {
        point.workers: point.stage_wall_seconds[name]
        for point in ordered
        if name in point.stage_wall_seconds
    }
    return {
        "stage": name,
        "wall_seconds": {str(n): wall for n, wall in walls.items()},
        "executor_idle_seconds": {
            str(point.workers): point.stage_idle_seconds.get(name, 0.0)
            for point in ordered
        },
        "efficiency": {
            str(n): walls[1] / (n * wall) if wall > 0 else None
            for n, wall in walls.items()
        },
        "amdahl": _fit_document(fit_amdahl(list(walls.items()))),
    }


def _round_row(name: str, ordered: Sequence[ScalingPoint]) -> dict[str, Any]:
    """Return one round's task time at every count and its inflation."""
    base, most = ordered[0], ordered[-1]
    seconds = base.round_task_seconds[name]
    return {
        "round": name,
        "task_count": base.round_task_counts[name],
        "mean_task_seconds_one_worker": seconds
        / max(base.round_task_counts[name], 1),
        "task_seconds": {
            str(point.workers): point.round_task_seconds.get(name)
            for point in ordered
        },
        "task_seconds_inflation": (
            most.round_task_seconds.get(name, 0.0) / seconds
            if seconds > 0
            else None
        ),
    }


def scaling_summary(points: Sequence[ScalingPoint]) -> dict[str, Any]:
    """Return one case's curve under one executor.

    Raises:
        ValueError: If two points share a worker count or none has one
            worker, the baseline every speedup is measured against.
    """
    ordered = sorted(points, key=lambda point: point.workers)
    counts = [point.workers for point in ordered]
    if len(set(counts)) != len(counts):
        raise ValueError("each worker count must be profiled once")
    if not ordered or ordered[0].workers != 1:
        raise ValueError("the curve needs a run on one worker")
    base, most = ordered[0], ordered[-1]
    fits = {
        name: fit_amdahl(
            [
                (point.workers, point.stage_wall_seconds[name])
                for point in ordered
                if name in point.stage_wall_seconds
            ]
        )
        for name in base.stage_wall_seconds
    }
    serial_terms = [
        {
            "stage": name,
            "serial_seconds": 0.0 if fit is None else fit.serial_seconds,
            "executor_idle_seconds_at_most_workers": (
                most.stage_idle_seconds.get(name, 0.0)
            ),
        }
        for name, fit in sorted(
            fits.items(),
            key=lambda item: (
                -(0.0 if item[1] is None else item[1].serial_seconds)
            ),
        )
    ]
    return {
        "curve": [_curve_row(point, base) for point in ordered],
        "amdahl": _fit_document(
            fit_amdahl(
                [(point.workers, point.wall_seconds) for point in ordered]
            )
        ),
        "stages": [
            _stage_row(name, ordered) for name in base.stage_wall_seconds
        ],
        "serial_terms": serial_terms,
        "rounds": [
            _round_row(name, ordered)
            for name in sorted(
                base.round_task_seconds,
                key=lambda name: -base.round_task_seconds[name],
            )
        ],
    }
