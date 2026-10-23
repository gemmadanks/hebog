"""Contracts of the one-sector scaling model, against analytic truth."""

from __future__ import annotations

from typing import Any

import pytest

from hebog.validation.scaling_model import (
    FinderWork,
    HebogRun,
    MatchedRun,
    TaskRound,
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

_ROOT = "find_sources"


def _run(
    workers: int, driver: float, rounds: dict[str, tuple[float, float]]
) -> HebogRun:
    """Return a run whose rounds map names to (summed, longest) seconds."""
    return HebogRun(
        workers=workers,
        wall_seconds=0.0,
        driver_seconds=driver,
        rounds=tuple(
            TaskRound(name, summed, longest)
            for name, (summed, longest) in rounds.items()
        ),
    )


def test_hebog_time_is_driver_time_plus_each_rounds_bound() -> None:
    """A round takes its share of the cores or its longest task."""
    run = _run(4, 10.0, {"wide": (120.0, 2.0), "narrow": (12.0, 6.0)})

    assert hebog_seconds(run, 1) == pytest.approx(10.0 + 132.0)
    assert hebog_seconds(run, 4) == pytest.approx(10.0 + 30.0 + 6.0)
    assert hebog_seconds(run, 1_000) == pytest.approx(10.0 + 2.0 + 6.0)
    assert run.task_seconds == pytest.approx(132.0)
    assert run.span_seconds == pytest.approx(8.0)
    assert run.floor_seconds == pytest.approx(18.0)


def test_hebog_time_needs_a_core() -> None:
    with pytest.raises(ValueError, match="core"):
        hebog_seconds(_run(1, 0.0, {}), 0)


def test_round_tails_rank_the_rounds_too_narrow_for_the_cores() -> None:
    run = _run(4, 0.0, {"wide": (120.0, 2.0), "narrow": (12.0, 6.0)})

    assert round_tails(run, 4) == [("narrow", pytest.approx(3.0))]
    assert round_tails(run, 1) == []


def test_serial_term_splits_into_driver_contention_and_tails() -> None:
    """At n workers, wall - W(1)/n is driver + contention + tails."""
    one = HebogRun(1, 110.0, 10.0, (TaskRound("r", 100.0, 1.0),))
    four = HebogRun(4, 50.0, 12.0, (TaskRound("r", 120.0, 1.5),))

    term = serial_term(one, four)

    assert term.serial_seconds == pytest.approx(50.0 - 25.0)
    assert term.driver_seconds == pytest.approx(12.0)
    assert term.contention_seconds == pytest.approx(20.0 / 4)
    assert term.tail_seconds == pytest.approx(50.0 - 12.0 - 30.0)
    assert (
        term.driver_seconds + term.contention_seconds + term.tail_seconds
    ) == pytest.approx(term.serial_seconds)
    assert term.document()["workers"] == 4


def test_serial_term_needs_a_one_worker_run() -> None:
    two = HebogRun(2, 1.0, 0.0, ())
    with pytest.raises(ValueError, match="one worker"):
        serial_term(two, two)


def test_interpolation_is_linear_in_sources_and_never_negative() -> None:
    sparse = _run(4, 10.0, {"r": (100.0, 2.0), "only": (4.0, 1.0)})
    dense = _run(4, 30.0, {"r": (300.0, 6.0)})

    middle = interpolate_runs(sparse, 1_000, dense, 3_000, 2_000)
    beyond = interpolate_runs(sparse, 1_000, dense, 3_000, -9_000)

    assert middle.driver_seconds == pytest.approx(20.0)
    assert {
        item.name: (item.task_seconds, item.longest_task_seconds)
        for item in middle.rounds
    } == {
        "r": (pytest.approx(200.0), pytest.approx(4.0)),
        "only": (pytest.approx(2.0), pytest.approx(0.5)),
    }
    assert beyond.driver_seconds == 0.0
    assert all(item.task_seconds >= 0.0 for item in beyond.rounds)


def test_a_run_with_a_lower_floor_keeps_its_task_time() -> None:
    """Driver time and longest tasks scale together to the new floor."""
    run = _run(4, 30.0, {"a": (100.0, 10.0), "b": (50.0, 20.0)})

    lowered = with_floor(run, 30.0)

    assert lowered.floor_seconds == pytest.approx(30.0)
    assert lowered.driver_seconds == pytest.approx(15.0)
    assert [item.longest_task_seconds for item in lowered.rounds] == [
        pytest.approx(5.0),
        pytest.approx(10.0),
    ]
    assert lowered.task_seconds == pytest.approx(run.task_seconds)


def test_interpolation_needs_two_source_counts() -> None:
    run = _run(4, 1.0, {})
    with pytest.raises(ValueError, match="source counts"):
        interpolate_runs(run, 5, run, 5, 5)


def test_cpu_time_separates_serial_and_parallel_work() -> None:
    """On 4 cores, 100 s serial and 400 s parallel take 200 s of wall."""
    run = MatchedRun(
        cores=4,
        sources=10,
        finder_seconds=100.0 + 400.0 / 4,
        cpu_seconds=100.0 + 400.0 + 30.0,
        filter_seconds=30.0,
    )

    work = work_from_cpu(run)

    assert work.serial_seconds == pytest.approx(100.0)
    assert work.parallel_seconds == pytest.approx(400.0)
    assert work.usable_cores is None
    assert work.seconds(8) == pytest.approx(150.0)


def test_cpu_time_separates_work_capped_below_the_cores_given() -> None:
    """100 s serial and 400 s parallel on at most 2 of 4 cores: 300 s."""
    run = MatchedRun(
        cores=4,
        sources=10,
        finder_seconds=100.0 + 400.0 / 2,
        cpu_seconds=100.0 + 400.0,
        filter_seconds=0.0,
    )

    work = work_from_cpu(run, usable_cores=2)

    assert work.serial_seconds == pytest.approx(100.0)
    assert work.parallel_seconds == pytest.approx(400.0)
    assert work.usable_cores == 2
    assert work.seconds(192) == pytest.approx(300.0)


def test_cpu_time_cannot_separate_work_capped_at_one_core() -> None:
    with pytest.raises(ValueError, match="two cores"):
        work_from_cpu(MatchedRun(4, 10, 5.0, 5.0, 0.0), usable_cores=1)


@pytest.mark.parametrize(
    ("cores", "usable_cores"), [(4, None), (4, 2)], ids=["cores", "cap"]
)
def test_cpu_time_beyond_the_usable_cores_is_refused(
    cores: int, usable_cores: int | None
) -> None:
    """500 s of CPU in 100 s of wall needs five busy cores."""
    run = MatchedRun(cores, 10, 100.0, 530.0, 30.0)

    with pytest.raises(ValueError, match="busy"):
        work_from_cpu(run, usable_cores)


def test_a_cap_rises_to_the_cores_a_run_kept_busy() -> None:
    """A cap from another sector's sweep cannot undercut this run's CPU."""
    run = MatchedRun(4, 10, 248.0, 724.5, 73.5)  # 2.6 cores busy

    assert usable_cores(run, None) is None
    assert usable_cores(run, 2) == 3
    assert usable_cores(run, 4) == 4
    work = work_from_cpu(run, usable_cores(run, 2))
    assert work.serial_seconds >= 0.0


def test_cpu_time_below_wall_time_is_refused() -> None:
    """A finder that waited more than it computed has no parallel work."""
    with pytest.raises(ValueError, match="CPU"):
        work_from_cpu(MatchedRun(4, 10, 100.0, 120.0, 30.0))


def test_cpu_time_cannot_separate_work_on_one_core() -> None:
    with pytest.raises(ValueError, match="two cores"):
        work_from_cpu(MatchedRun(1, 10, 5.0, 5.0, 0.0))


def test_capped_amdahl_recovers_the_cores_a_finder_can_use() -> None:
    """500 s serial and 1,800 s parallel, using at most 4 cores."""
    truth = FinderWork(500.0, 1_800.0, usable_cores=4)

    fit = fit_capped_amdahl([(c, truth.seconds(c)) for c in (1, 2, 4, 6)])

    assert fit.serial_seconds == pytest.approx(500.0)
    assert fit.parallel_seconds == pytest.approx(1_800.0)
    assert fit.usable_cores == 4
    assert fit.seconds(192) == pytest.approx(950.0)


def test_capped_amdahl_keeps_amdahl_when_every_core_helps() -> None:
    truth = FinderWork(100.0, 900.0, usable_cores=None)

    fit = fit_capped_amdahl([(c, truth.seconds(c)) for c in (1, 2, 4, 6)])

    assert fit.usable_cores is None
    assert fit.serial_seconds == pytest.approx(100.0)
    assert fit.parallel_seconds == pytest.approx(900.0)


def test_capped_amdahl_takes_the_most_cores_the_data_allow() -> None:
    """Without a 2-core point, caps of 2 and 4 fit 1, 4 and 6 alike, but a
    cap of 2 needs negative serial work; with equal fits the larger wins."""
    points = [(1, 2_300.0), (4, 950.0), (6, 950.0)]

    fit = fit_capped_amdahl(points)

    assert fit.usable_cores == 4
    assert fit.serial_seconds == pytest.approx(500.0)


def test_capped_amdahl_fits_two_core_counts_above_one() -> None:
    """With 2 and 4 cores, a cap at 4 and no cap are the same fit."""
    fit = fit_capped_amdahl([(2, 60.0), (4, 35.0)])

    assert fit.usable_cores is None
    assert fit.document() == {
        "serial_seconds": pytest.approx(10.0),
        "parallel_seconds": pytest.approx(100.0),
        "usable_cores": None,
    }


@pytest.mark.parametrize(("serial", "parallel"), [(0.0, 100.0), (100.0, 0.0)])
def test_capped_amdahl_keeps_a_term_that_rounds_below_zero(
    serial: float, parallel: float
) -> None:
    """A wholly parallel or wholly serial sweep fits with one term zero."""
    fit = fit_capped_amdahl([(c, serial + parallel / c) for c in (1, 2, 4, 6)])

    assert fit.serial_seconds == pytest.approx(serial, abs=1e-9)
    assert fit.parallel_seconds == pytest.approx(parallel, abs=1e-9)
    assert fit.serial_seconds >= 0.0
    assert fit.parallel_seconds >= 0.0


def test_capped_amdahl_refuses_runs_slower_on_more_cores() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        fit_capped_amdahl([(1, 10.0), (2, 20.0), (4, 40.0)])


def test_finder_time_needs_a_core() -> None:
    with pytest.raises(ValueError, match="core"):
        FinderWork(1.0, 1.0).seconds(0)


def test_capped_amdahl_needs_two_core_counts() -> None:
    with pytest.raises(ValueError, match="two core counts"):
        fit_capped_amdahl([(4, 1.0), (4, 2.0)])


def test_line_fit_recovers_intercept_and_slope() -> None:
    assert fit_line([(n, 34.0 + 0.0367 * n) for n in (1, 5, 9)]) == (
        pytest.approx(34.0),
        pytest.approx(0.0367),
    )


def test_targets_hold_hebog_to_the_limit_on_the_given_cores() -> None:
    """A run whose floor meets its target sits on the limit at most."""
    work = 960.0
    master_seconds, factor, cores = 1_000.0, 2.0, 96
    probe = _run(4, 0.0, {"r": (work, 0.0)})

    targets = time_targets(
        probe, master_seconds, limit=0.5, container_factor=factor, cores=cores
    )
    on_target = _run(4, targets.floor_target_seconds, {"r": (work, 0.0)})

    assert targets.document() == {
        "budget_seconds": pytest.approx(250.0),
        "floor_target_seconds": pytest.approx(240.0),
        "busy_cores": pytest.approx(3.84),
        "reachable": True,
    }
    assert factor * hebog_seconds(on_target, cores) / master_seconds == (
        pytest.approx(0.5)
    )


def test_targets_are_conservative_when_rounds_are_span_bound() -> None:
    """A round bound by its longest task adds nothing beyond the floor."""
    probe = _run(4, 10.0, {"r": (960.0, 20.0)})

    targets = time_targets(
        probe, 1_000.0, limit=0.5, container_factor=2.0, cores=96
    )
    on_target = with_floor(probe, targets.floor_target_seconds)

    assert targets.floor_target_seconds == pytest.approx(240.0)
    assert 2.0 * hebog_seconds(on_target, 96) / 1_000.0 < 0.5


def test_targets_flag_a_limit_the_cpu_alone_exceeds() -> None:
    probe = _run(4, 0.0, {"r": (96_000.0, 0.0)})

    targets = time_targets(
        probe, 1_000.0, limit=0.5, container_factor=2.0, cores=96
    )

    assert targets.floor_target_seconds < 0.0
    assert not targets.reachable


_LOG = """\
Fri 23-10-2026 03:55:40:: INFO: Total number of Gaussians fit to image: 9
Fri 23-10-2026 03:55:42:: INFO: Minimum number of pixels per island: 6
Fri 23-10-2026 03:55:49:: INFO: Number of islands found: 21367
Fri 23-10-2026 04:05:35:: INFO: Total number of Gaussians fit to image: 25060
Fri 23-10-2026 04:06:10:: INFO: Number of islands found: 1662
Fri 23-10-2026 04:08:08:: INFO: Total number of Gaussians fit to image: 1738
Sat 24-10-2026 23:59:59:: INFO: Number of islands found: 3
Sun 25-10-2026 00:00:09:: INFO: Total number of Gaussians fit to image: 3
"""


def test_pybdsf_log_gives_each_gaussian_fitting_phase() -> None:
    assert pybdsf_fit_seconds(_LOG) == [586.0, 118.0, 10.0]


def _round(name: str, count: int, summed: float, longest: float) -> Any:
    return {
        "round": name,
        "task_count": count,
        "task_seconds": summed,
        "longest_task_seconds": longest,
    }


def test_a_run_reads_a_profile_record() -> None:
    record: dict[str, Any] = {
        "root_stage": _ROOT,
        "executor": {"kind": "dask", "workers": 4},
        "stages": [
            {"stage": [_ROOT], "wall_seconds": 400.0},
            {"stage": [_ROOT, "catalogue FITS write"], "wall_seconds": 15.0},
        ],
        "tasks": {
            "stages": [
                {"stage": [_ROOT], "executor_idle_seconds": 80.0},
                {
                    "stage": [_ROOT, "catalogue FITS write"],
                    "executor_idle_seconds": 15.0,
                },
            ],
            "rounds": [_round("fits", 12, 240.0, 35.0)],
        },
    }

    assert hebog_run(record) == HebogRun(
        workers=4,
        wall_seconds=400.0,
        driver_seconds=80.0,
        rounds=(TaskRound("fits", 240.0, 35.0),),
        driver_stage_seconds={"catalogue FITS write": 15.0},
    )


def test_a_run_refuses_a_thread_profile() -> None:
    """Threads share the interpreter lock, so their rounds do not bound
    the time single-threaded workers take."""
    record: dict[str, Any] = {
        "root_stage": _ROOT,
        "executor": {"kind": "threads", "workers": 4},
        "stages": [],
        "tasks": {"stages": [], "rounds": []},
    }
    with pytest.raises(ValueError, match="Dask"):
        hebog_run(record)
