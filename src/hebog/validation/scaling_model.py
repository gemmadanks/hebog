"""Model one sector's finder time on a cluster from local measurements.

Rapthor gives PyBDSF ``master`` every core of one node, and the gate holds
Hebog's finder part to a fraction of ``master``'s there. Neither the
cluster nor its node sizes are available locally, so this module fits each
finder's work to the local evidence and projects it:

- **Hebog** is modelled from a native stage profile on single-threaded
  Dask workers. A run is its driver time, when no task runs, and its rounds
  of independent tasks, each with summed and longest task seconds ``W_r``
  and ``L_r``. On ``c`` cores a round takes at least ``max(W_r / c, L_r)``,
  so :func:`hebog_seconds` is ``D + sum_r max(W_r / c, L_r)``: a lower
  bound that tends to the run's floor, ``D + sum_r L_r``, which no number
  of cores shortens. The profile merges a round's invocations under one
  name, so the floor is low by the longest tasks of a round's repeats.
- **PyBDSF** is modelled from the matched container's reports.
  :func:`work_from_cpu` splits one run's finder part into serial and
  parallel seconds from its wall and CPU time, and
  :func:`fit_capped_amdahl` fits a core sweep to
  ``s + p / min(c, m)``, where ``m`` is the most cores the sweep shows the
  finder using.

Both fits are plain records; :func:`time_targets` turns a gate's limit into
the time, floor and busy cores Hebog may use. Units are seconds throughout.
Nothing here runs at import.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

import numpy as np

_STAGE_DEPTH = 2  # (root, stage): the root's direct children
_PYBDSF_TIME = re.compile(
    r"^\w{3} (?P<time>\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})::"
    r".*(?P<event>Number of islands found|Total number of Gaussians fit)"
)


@dataclass(frozen=True, slots=True)
class TaskRound:
    """One round of independent tasks: summed and longest task seconds."""

    name: str
    task_seconds: float
    longest_task_seconds: float


@dataclass(frozen=True, slots=True)
class HebogRun:
    """One native profile of Hebog on single-threaded Dask workers.

    ``driver_seconds`` is the time no task ran (the executor's idle time);
    ``driver_stage_seconds`` splits it by top-level stage, the driver timers.
    """

    workers: int
    wall_seconds: float
    driver_seconds: float
    rounds: tuple[TaskRound, ...]
    driver_stage_seconds: Mapping[str, float] = field(
        default_factory=dict[str, float]
    )

    @property
    def task_seconds(self) -> float:
        """Return the summed task time of every round."""
        return sum(item.task_seconds for item in self.rounds)

    @property
    def span_seconds(self) -> float:
        """Return the summed longest task of every round."""
        return sum(item.longest_task_seconds for item in self.rounds)

    @property
    def floor_seconds(self) -> float:
        """Return the driver time and span, which no core count shortens."""
        return self.driver_seconds + self.span_seconds


@dataclass(frozen=True, slots=True)
class SerialTerm:
    """What keeps a run on ``workers`` above ``W(1) / workers``.

    ``serial_seconds`` is the wall time beyond the one-worker task time
    shared evenly. It splits into the driver's time with no task running,
    contention (the growth of summed task time with workers, shared by
    them) and the rounds' tails, when some workers wait for the round's
    last tasks.
    """

    workers: int
    serial_seconds: float
    driver_seconds: float
    contention_seconds: float
    tail_seconds: float

    def document(self) -> dict[str, float | int]:
        """Return one JSON-serializable decomposition."""
        return {
            "workers": self.workers,
            "serial_seconds": self.serial_seconds,
            "driver_seconds": self.driver_seconds,
            "contention_seconds": self.contention_seconds,
            "tail_seconds": self.tail_seconds,
        }


@dataclass(frozen=True, slots=True)
class MatchedRun:
    """One finder's medians on one sector in the matched container.

    ``cpu_seconds`` counts the finder and LSMTool's filtering, which runs on
    one core for ``filter_seconds``; ``sources`` is ``master``'s count for
    the sector, the gate's measure of density.
    """

    cores: int
    sources: int
    finder_seconds: float
    cpu_seconds: float
    filter_seconds: float


@dataclass(frozen=True, slots=True)
class FinderWork:
    """A finder's serial and parallel seconds, ``s + p / min(c, m)``.

    ``usable_cores`` (``m``) is the most cores the parallel work uses;
    ``None`` means every core helps (Amdahl's law).
    """

    serial_seconds: float
    parallel_seconds: float
    usable_cores: int | None = None

    def seconds(self, cores: int) -> float:
        """Return the finder's time on ``cores``."""
        if cores < 1:
            raise ValueError("a finder needs a core")
        used = (
            cores
            if self.usable_cores is None
            else min(cores, self.usable_cores)
        )
        return self.serial_seconds + self.parallel_seconds / used

    def document(self) -> dict[str, float | int | None]:
        """Return one JSON-serializable fit."""
        return {
            "serial_seconds": self.serial_seconds,
            "parallel_seconds": self.parallel_seconds,
            "usable_cores": self.usable_cores,
        }


@dataclass(frozen=True, slots=True)
class TimeTargets:
    """What a gate's limit allows Hebog on some cores, in native seconds.

    ``budget_seconds`` is the most time Hebog may take;
    ``floor_target_seconds`` the most its driver time and longest tasks may
    take with all of its task time shared across the cores added to them,
    a conservative target, since :func:`hebog_seconds` adds only the share
    each round's longest task does not cover; ``busy_cores`` the cores it
    must keep busy on average to finish its task time within the budget.
    ``reachable`` is false when the task time alone exceeds the budget, so
    no serial cut meets the limit and the work itself must fall.
    """

    budget_seconds: float
    floor_target_seconds: float
    busy_cores: float
    reachable: bool

    def document(self) -> dict[str, float | bool]:
        """Return one JSON-serializable set of targets."""
        return {
            "budget_seconds": self.budget_seconds,
            "floor_target_seconds": self.floor_target_seconds,
            "busy_cores": self.busy_cores,
            "reachable": self.reachable,
        }


def hebog_run(record: Mapping[str, Any]) -> HebogRun:
    """Read one profile worker record of a Dask run.

    Raises:
        ValueError: If the tasks ran on threads, whose rounds share the
            interpreter lock and so do not bound a worker's time.
    """
    executor = record["executor"]
    if executor["kind"] != "dask":
        raise ValueError("the model reads profiles on Dask workers only")
    root = str(record["root_stage"])
    stages = {tuple(item["stage"]): item for item in record["stages"]}
    tasks = record["tasks"]
    occupancy = {tuple(item["stage"]): item for item in tasks["stages"]}
    return HebogRun(
        workers=int(executor["workers"]),
        wall_seconds=float(stages[(root,)]["wall_seconds"]),
        driver_seconds=float(occupancy[(root,)]["executor_idle_seconds"]),
        rounds=tuple(
            TaskRound(
                str(item["round"]),
                float(item["task_seconds"]),
                float(item["longest_task_seconds"]),
            )
            for item in tasks["rounds"]
        ),
        driver_stage_seconds={
            path[1]: float(item["executor_idle_seconds"])
            for path, item in occupancy.items()
            if len(path) == _STAGE_DEPTH and path[0] == root
        },
    )


def hebog_seconds(run: HebogRun, cores: int) -> float:
    """Return the run's time on ``cores``: ``D + sum_r max(W_r / c, L_r)``."""
    if cores < 1:
        raise ValueError("a run needs a core")
    return run.driver_seconds + sum(
        max(item.task_seconds / cores, item.longest_task_seconds)
        for item in run.rounds
    )


def round_tails(run: HebogRun, cores: int) -> list[tuple[str, float]]:
    """Return the rounds whose longest task outlasts their share of the cores.

    Each round's tail is ``max(W_r / c, L_r) - W_r / c``, largest first.
    """
    tails = [
        (item.name, item.longest_task_seconds - item.task_seconds / cores)
        for item in run.rounds
    ]
    return sorted(
        ((name, tail) for name, tail in tails if tail > 0.0),
        key=lambda pair: -pair[1],
    )


def serial_term(one_worker: HebogRun, run: HebogRun) -> SerialTerm:
    """Split the run's time beyond ``W(1) / n`` into its causes.

    Raises:
        ValueError: If ``one_worker`` did not run on one worker.
    """
    if one_worker.workers != 1:
        raise ValueError("the serial term is measured against one worker")
    workers = run.workers
    shared = run.task_seconds / workers
    return SerialTerm(
        workers=workers,
        serial_seconds=run.wall_seconds - one_worker.task_seconds / workers,
        driver_seconds=run.driver_seconds,
        contention_seconds=(run.task_seconds - one_worker.task_seconds)
        / workers,
        tail_seconds=run.wall_seconds - run.driver_seconds - shared,
    )


def with_floor(run: HebogRun, floor_seconds: float) -> HebogRun:
    """Return the run with its floor scaled to ``floor_seconds``.

    Driver time and every round's longest task scale by one factor and the
    task time stays, which is how a target floor is projected.
    """
    scale = floor_seconds / run.floor_seconds
    return replace(
        run,
        driver_seconds=run.driver_seconds * scale,
        rounds=tuple(
            replace(
                item, longest_task_seconds=item.longest_task_seconds * scale
            )
            for item in run.rounds
        ),
    )


def interpolate_runs(
    sparse: HebogRun,
    sparse_sources: int,
    dense: HebogRun,
    dense_sources: int,
    sources: int,
) -> HebogRun:
    """Return a run for ``sources``, linear between two profiled sectors.

    Driver time and each round's summed and longest task seconds move
    linearly with the source count, a round missing from one run counting
    as zero there, and none falls below zero.

    Raises:
        ValueError: If both runs have the same source count.
    """
    if sparse_sources == dense_sources:
        raise ValueError("interpolation needs two source counts")
    weight = (sources - sparse_sources) / (dense_sources - sparse_sources)

    def between(low: float, high: float) -> float:
        return max(low + weight * (high - low), 0.0)

    sparse_rounds = {item.name: item for item in sparse.rounds}
    dense_rounds = {item.name: item for item in dense.rounds}
    names = list(dense_rounds) + [
        name for name in sparse_rounds if name not in dense_rounds
    ]
    empty = TaskRound("", 0.0, 0.0)
    return HebogRun(
        workers=dense.workers,
        wall_seconds=between(sparse.wall_seconds, dense.wall_seconds),
        driver_seconds=between(sparse.driver_seconds, dense.driver_seconds),
        rounds=tuple(
            TaskRound(
                name,
                between(
                    sparse_rounds.get(name, empty).task_seconds,
                    dense_rounds.get(name, empty).task_seconds,
                ),
                between(
                    sparse_rounds.get(name, empty).longest_task_seconds,
                    dense_rounds.get(name, empty).longest_task_seconds,
                ),
            )
            for name in names
        ),
    )


def work_from_cpu(
    run: MatchedRun, usable_cores: int | None = None
) -> FinderWork:
    """Split a run's finder part into serial and parallel seconds.

    With wall ``T = s + p / c`` and CPU ``C = s + p`` on ``c`` cores,
    ``p = (C - T) c / (c - 1)``, where ``c`` is the run's cores or, if
    fewer, the ``usable_cores`` the parallel work can use, which the
    returned work keeps. The finder's CPU is the run's less LSMTool's
    filtering, taken as one busy core; work spread unevenly over the cores
    counts as serial.

    Raises:
        ValueError: If the run's parallel work had fewer than two cores, or
            its finder's CPU time is outside ``[T, c T]``: below its wall
            time it waited more than it computed, and above ``c`` times it
            kept more cores busy than it could use, so either split would
            give negative work.
    """
    cores = run.cores if usable_cores is None else min(run.cores, usable_cores)
    if cores < 2:  # noqa: PLR2004 one core cannot separate the terms
        raise ValueError("separating the work needs at least two cores")
    finder_cpu = run.cpu_seconds - run.filter_seconds
    if finder_cpu < run.finder_seconds:
        raise ValueError("the finder's CPU time is below its wall time")
    if finder_cpu > cores * run.finder_seconds:
        raise ValueError(
            f"the finder kept more than {cores} cores busy on average"
        )
    parallel = (finder_cpu - run.finder_seconds) * cores / (cores - 1)
    return FinderWork(finder_cpu - parallel, parallel, usable_cores)


def usable_cores(run: MatchedRun, cap: int | None) -> int | None:
    """Return ``cap``, raised to the cores the run kept busy on average.

    A cap fitted to one sector's core sweep may undercut another sector
    whose CPU time shows more cores busy; its own CPU time then sets the
    least the run used, rounded up. ``None`` (every core) stays.
    """
    if cap is None:
        return None
    busy = (run.cpu_seconds - run.filter_seconds) / run.finder_seconds
    return max(cap, math.ceil(busy))


def fit_capped_amdahl(points: Sequence[tuple[int, float]]) -> FinderWork:
    """Fit ``(cores, seconds)`` to ``s + p / min(c, m)`` by least squares.

    Each core count above the smallest, and no cap, is tried as ``m``, so
    every fit keeps two distinct terms; fits with negative terms, beyond
    roundoff, are refused. Of equally good fits the one using the most
    cores wins, since points beyond the cap cannot tell caps apart and the
    larger is the faster finder.

    Raises:
        ValueError: If the points hold fewer than two core counts, or no
            fit has non-negative terms, as when more cores take longer.
    """
    counts = sorted({cores for cores, _ in points})
    if len(counts) < 2:  # noqa: PLR2004 two terms
        raise ValueError("the fit needs two core counts")
    seconds = np.array([value for _, value in points])
    tolerance = 1e-9 * float(np.sum(seconds**2))
    # A term that rounds just below zero is zero: least squares returns
    # -1e-14 s of serial work for a wholly parallel sweep.
    roundoff = 1e-9 * float(np.max(np.abs(seconds)))
    candidates: list[int | None] = [None, *reversed(counts[1:])]
    fits: list[tuple[float, FinderWork]] = []
    for cap in candidates:
        used = [
            cores if cap is None else min(cores, cap) for cores, _ in points
        ]
        design = np.array([(1.0, 1.0 / count) for count in used])
        solution, *_ = np.linalg.lstsq(design, seconds, rcond=None)
        serial, parallel = float(solution[0]), float(solution[1])
        if serial < -roundoff or parallel < -roundoff:
            continue
        serial, parallel = max(serial, 0.0), max(parallel, 0.0)
        residual = float(np.sum((seconds - design @ solution) ** 2))
        fits.append((residual, FinderWork(serial, parallel, cap)))
    if not fits:
        raise ValueError("no fit has non-negative serial and parallel work")
    best = min(residual for residual, _ in fits)
    return next(fit for residual, fit in fits if residual <= best + tolerance)


def fit_line(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """Return the least-squares ``(intercept, slope)`` through the points."""
    slope, intercept = np.polyfit(
        [x for x, _ in points], [y for _, y in points], 1
    )
    return float(intercept), float(slope)


def pybdsf_fit_seconds(log_text: str) -> list[float]:
    """Return each Gaussian-fitting phase's seconds from a PyBDSF log.

    A phase runs from ``Number of islands found`` to the next ``Total
    number of Gaussians fit``; an island search with no fit after it, as in
    the RMS-only run, is skipped. The log's timestamps resolve seconds.
    """
    phases: list[float] = []
    started: datetime | None = None
    for line in log_text.splitlines():
        match = _PYBDSF_TIME.match(line)
        if match is None:
            continue
        moment = datetime.strptime(match["time"], "%d-%m-%Y %H:%M:%S")
        if match["event"].startswith("Number"):
            started = moment
        elif started is not None:
            phases.append((moment - started).total_seconds())
            started = None
    return phases


def time_targets(
    run: HebogRun,
    master_seconds: float,
    *,
    limit: float,
    container_factor: float,
    cores: int,
) -> TimeTargets:
    """Return what ``limit`` times ``master``'s time allows the run.

    ``master_seconds`` is measured in the matched container and the run
    natively; ``container_factor`` converts native seconds to the
    container's, assumed to slow both finders alike. A run whose floor
    meets ``floor_target_seconds`` takes at most the budget, since no round
    takes longer than its longest task plus its share of the cores, so its
    ratio is at most ``limit``; when rounds are bound by their longest
    tasks it is below.
    """
    budget = limit * master_seconds / container_factor
    floor_target = budget - run.task_seconds / cores
    return TimeTargets(
        budget_seconds=budget,
        floor_target_seconds=floor_target,
        busy_cores=run.task_seconds / budget,
        reachable=floor_target > 0.0,
    )
