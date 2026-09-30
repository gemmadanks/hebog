"""Contracts of the traced-peak attribution diagnostic."""

from __future__ import annotations

import sys
import tracemalloc
import types
from collections.abc import Iterator
from functools import partial

import pytest

from hebog.executors import SerialExecutor, serial
from hebog.validation.traced_attribution import (
    TracedPeakTracker,
    serial_tasks_measured,
    wrap_module_functions,
)

_MEBIBYTE = 2**20


@pytest.fixture
def tracing() -> Iterator[None]:
    """Trace allocations for one test, as the attribution runner does."""
    tracemalloc.start(8)
    try:
        yield
    finally:
        tracemalloc.stop()


def _hold(size: int) -> bytearray:
    """Allocate one block of ``size`` bytes at a recognisable site."""
    return bytearray(size)


def _add(value: int, *, offset: int) -> int:
    """Return one executor task's result."""
    return value + offset


@pytest.mark.usefixtures("tracing")
def test_a_call_reports_its_inclusive_peak_and_what_it_began_holding() -> None:
    tracker = TracedPeakTracker()

    with tracker.span("pass"):
        held = _hold(_MEBIBYTE)
        with tracker.span("task"):
            temporary = _hold(3 * _MEBIBYTE)
            del temporary
        del held

    task = tracker.totals[("pass", "task")]
    whole = tracker.totals[("pass",)]
    assert 3 * _MEBIBYTE <= task.largest_own_bytes < 3.1 * _MEBIBYTE
    assert task.entry_at_peak_bytes - whole.entry_at_peak_bytes >= _MEBIBYTE
    # The task's peak is folded into the pass that ran it.
    assert whole.peak_bytes >= task.peak_bytes
    assert whole.largest_own_bytes >= 4 * _MEBIBYTE
    assert [item["path"] for item in tracker.documents()][:2] == [
        ["pass"],
        ["pass", "task"],
    ]


@pytest.mark.usefixtures("tracing")
def test_a_path_keeps_its_largest_call_and_what_that_call_began_with() -> None:
    tracker = TracedPeakTracker()

    with tracker.span("task"):
        first = _hold(2 * _MEBIBYTE)
        del first
    held = _hold(_MEBIBYTE)
    with tracker.span("task"):
        second = _hold(_MEBIBYTE // 2)
        del second
    del held

    totals = tracker.totals[("task",)]
    assert totals.calls == 2
    assert 2 * _MEBIBYTE <= totals.largest_own_bytes < 2.1 * _MEBIBYTE
    assert totals.largest_entry_bytes - totals.entry_at_peak_bytes >= (
        _MEBIBYTE
    )


def test_attribution_refuses_to_run_without_tracing() -> None:
    assert not tracemalloc.is_tracing()
    tracker = TracedPeakTracker()

    with (
        pytest.raises(RuntimeError, match="tracemalloc"),
        tracker.span("pass"),
    ):
        pass


@pytest.mark.usefixtures("tracing")
def test_the_largest_entry_below_a_prefix_names_what_it_held() -> None:
    """The site that holds memory between tasks is the one reported."""
    tracker = TracedPeakTracker(snapshot_within="pass", site_frames=1)

    with tracker.span("pass"):
        with tracker.span("task first"):
            pass
        held = _hold(4 * _MEBIBYTE)
        with tracker.span("round"), tracker.span("task second"):
            inside = _hold(8 * _MEBIBYTE)
            with tracker.span("helper inside the task"):
                pass
            del inside
        del held
    with tracker.span("elsewhere"), tracker.span("task elsewhere"):
        elsewhere = _hold(8 * _MEBIBYTE)
        del elsewhere

    # Only a task's start is snapshotted: the helper began holding more,
    # but inside the task, and "elsewhere" is outside the chosen call.
    assert tracker.largest_entry_path == ("pass", "round", "task second")
    largest = tracker.sites_at_largest_entry[0]
    assert largest["bytes"] >= 4 * _MEBIBYTE
    assert largest["site"][0].startswith("test_traced_attribution.py:")


@pytest.mark.usefixtures("tracing")
def test_every_serial_task_is_measured_under_the_pass_that_ran_it() -> None:
    tracker = TracedPeakTracker()
    original = serial.call_with_retries

    with serial_tasks_measured(tracker, serial), tracker.span("pass"):
        results = SerialExecutor().map_batches(
            partial(_add, offset=1), [1, 2, 3]
        )

    assert results == [2, 3, 4]
    assert tracker.totals[("pass", "task _add")].calls == 3
    assert serial.call_with_retries is original


@pytest.mark.usefixtures("tracing")
def test_a_function_is_measured_through_every_alias_in_the_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller that imported the function by name is measured too."""
    defining = types.ModuleType("hebog_probe_defining")
    exec("def double(value):\n    return 2 * value\n", defining.__dict__)
    caller = types.ModuleType("hebog_probe.caller")
    caller.__dict__["double"] = defining.__dict__["double"]
    monkeypatch.setitem(sys.modules, "hebog_probe.caller", caller)
    tracker = TracedPeakTracker()

    replaced = wrap_module_functions(tracker, defining, package="hebog_probe")

    assert replaced == 2
    assert caller.__dict__["double"](3) == 6
    assert tracker.totals[("double",)].calls == 1


@pytest.mark.usefixtures("tracing")
def test_every_function_a_module_defines_is_measured() -> None:
    module = types.ModuleType("probe")
    exec("def double(value):\n    return 2 * value\n", module.__dict__)
    module.__dict__["imported"] = _hold
    tracker = TracedPeakTracker()

    wrapped = wrap_module_functions(tracker, module)

    assert wrapped == 1
    assert module.__dict__["double"](4) == 8
    assert tracker.totals[("double",)].calls == 1
    assert module.__dict__["imported"] is _hold
