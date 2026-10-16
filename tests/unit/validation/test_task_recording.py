"""Contracts of the profile's task recording, under every local executor."""

from __future__ import annotations

import pickle
import threading
import time
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager

import pytest

from hebog.executors import (
    Executor,
    SerialExecutor,
    TaskRequirement,
    ThreadExecutor,
)
from hebog.validation.task_recording import (
    RecordingExecutor,
    TaskRecord,
    TimedTask,
    ZarrIO,
    zarr_io_by_stage,
)

# Both of the thread pool's tasks wait here, so they provably overlap.
_BOTH_RUNNING = threading.Barrier(2, timeout=10.0)


def _square(value: int) -> int:
    return value * value


def _invert(value: int) -> int:
    return 1 // value


def _wait_for_the_other_task(value: int) -> int:
    _BOTH_RUNNING.wait()
    return value


@contextmanager
def _serial() -> Generator[Executor]:
    yield SerialExecutor()


@contextmanager
def _threads() -> Generator[Executor]:
    with ThreadExecutor(2) as executor:
        yield executor


_EXECUTORS = pytest.mark.parametrize(
    "open_executor",
    [pytest.param(_serial, id="serial"), pytest.param(_threads, id="threads")],
)


@_EXECUTORS
def test_results_are_the_wrapped_executors_with_one_record_per_task(
    open_executor: Callable[[], AbstractContextManager[Executor]],
) -> None:
    """The run sees the same results; each task is timed where it ran."""
    with open_executor() as inner:
        executor = RecordingExecutor(inner)
        before = time.time()
        results = executor.map_batches(
            _square,
            [1, 2, 3],
            requirement=TaskRequirement(memory_bytes=4_096),
        )
        after = time.time()

    assert results == [1, 4, 9]
    assert executor.capacity == inner.capacity
    assert [task.round for task in executor.tasks] == [
        "test_task_recording:_square"
    ] * 3
    for task in executor.tasks:
        assert before <= task.start <= task.stop <= after
        assert task.declared_bytes == 4_096
        assert task.io == ZarrIO()


def test_an_undeclared_round_records_no_declaration() -> None:
    executor = RecordingExecutor(SerialExecutor())

    executor.map_batches(_square, [5])

    assert executor.tasks[0].declared_bytes is None


def test_concurrent_tasks_are_recorded_overlapping() -> None:
    """A thread pool's two tasks run at once, and their records show it."""
    with ThreadExecutor(2) as inner:
        executor = RecordingExecutor(inner)
        executor.map_batches(_wait_for_the_other_task, [1, 2])

    first, second = executor.tasks
    assert max(first.start, second.start) < min(first.stop, second.stop)


def test_a_timed_task_crosses_a_process_boundary() -> None:
    """A Dask worker receives the task pickled, as every executor checks."""
    task = pickle.loads(pickle.dumps(TimedTask(_square)))

    output, start, stop, io = task(7)

    assert output == 49
    assert start <= stop
    assert io == ZarrIO()


def test_a_failing_task_raises_its_own_error_and_records_nothing() -> None:
    executor = RecordingExecutor(SerialExecutor())

    with pytest.raises(ZeroDivisionError):
        executor.map_batches(_invert, [0])

    assert executor.tasks == []


def test_zarr_io_adds_field_by_field() -> None:
    assert ZarrIO(1, 8, 2) + ZarrIO(3, 24, 0) == ZarrIO(4, 32, 2)


def test_io_is_attributed_to_every_stage_whose_call_holds_its_time() -> None:
    """A task's I/O counts where it started, as its task count does.

    Driver I/O counts at its own instant. Nested stages each count what
    their calls hold, so a parent includes its children's I/O.
    """
    tasks = (
        TaskRecord("r:f", 1.0, 30.0, None, ZarrIO(2, 16, 1)),
        TaskRecord("r:f", 12.0, 13.0, 64, ZarrIO(0, 0, 3)),
    )
    driver = ((11.0, ZarrIO(1, 8, 0)), (40.0, ZarrIO(5, 40, 0)))

    totals = zarr_io_by_stage(
        {
            ("run",): ((0.0, 20.0),),
            ("run", "late"): ((10.0, 15.0),),
            ("after",): ((35.0, 36.0), (39.0, 41.0)),
        },
        tasks,
        driver,
    )

    assert totals == {
        ("run",): ZarrIO(3, 24, 4),
        ("run", "late"): ZarrIO(1, 8, 3),
        ("after",): ZarrIO(5, 40, 0),
    }
