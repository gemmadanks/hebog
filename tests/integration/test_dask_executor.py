"""Integration tests for execution on a local Dask scheduler."""

import threading
import time
from collections import defaultdict

import pytest
from distributed import Client, LocalCluster, get_worker

from hebog.executors import (
    DaskExecutor,
    ExecutorCapacity,
    SerialExecutor,
    TaskRequirement,
)

_WORKER_THREADS = 3
_TASK_SECONDS = 0.2
_INTERVALS_LOCK = threading.Lock()
_INTERVALS: list[tuple[str, float, float]] = []


def _square(value: int) -> int:
    """Return the square of an integer in a worker-safe function."""
    return value**2


@pytest.mark.integration
def test_dask_executor_matches_serial_executor() -> None:
    """The Dask and serial executors preserve ordering and results."""
    inputs = [3, 1, 2]
    expected = SerialExecutor().map_batches(_square, inputs)

    cluster = LocalCluster(
        n_workers=1,
        threads_per_worker=1,
        processes=False,
        dashboard_address=":0",
    )
    with cluster, Client(cluster) as client:
        actual = DaskExecutor(client).map_batches(_square, inputs)

    assert actual == expected


def _record_interval(value: int) -> int:
    """Record which worker ran this task, and when, around a short wait."""
    started = time.monotonic()
    time.sleep(_TASK_SECONDS)
    with _INTERVALS_LOCK:
        _INTERVALS.append((get_worker().address, started, time.monotonic()))
    return value


def _most_tasks_at_once_on_one_worker() -> int:
    """Return the most recorded tasks that overlapped on any one worker."""
    by_worker: defaultdict[str, list[tuple[float, int]]] = defaultdict(list)
    for address, started, finished in _INTERVALS:
        by_worker[address] += [(started, 1), (finished, -1)]
    most = 0
    for events in by_worker.values():
        running = 0
        # A task ending at the instant another starts does not overlap it.
        for _, change in sorted(
            events, key=lambda event: (event[0], event[1])
        ):
            running += change
            most = max(most, running)
    return most


@pytest.mark.integration
@pytest.mark.parametrize(
    ("memory_resource", "core_resource", "shares_a_worker"),
    [
        pytest.param(None, None, True, id="unnamed"),
        pytest.param("memory", "cores", False, id="named"),
    ],
)
def test_named_memory_keeps_tasks_from_sharing_a_worker_past_its_memory(
    memory_resource: str | None,
    core_resource: str | None,
    shares_a_worker: bool,
) -> None:
    """Dask places a task only where the memory it declares is still free.

    Each worker has three threads but declares memory for one 60-byte task.
    The budget is declared without memory, so the in-flight window does not
    narrow and only the resource annotations can keep a second task off a
    busy worker; without them, the control shows Dask filling every thread.
    """
    _INTERVALS.clear()
    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=_WORKER_THREADS,
        processes=False,
        resources={"memory": 100, "cores": _WORKER_THREADS},
        dashboard_address=":0",
    )
    with cluster, Client(cluster) as client:
        executor = DaskExecutor(
            client,
            capacity=ExecutorCapacity(
                worker_count=2,
                threads_per_worker=_WORKER_THREADS,
                maximum_tasks_in_flight=2 * _WORKER_THREADS,
            ),
            memory_resource=memory_resource,
            core_resource=core_resource,
        )
        results = executor.map_batches(
            _record_interval,
            list(range(2 * _WORKER_THREADS)),
            requirement=TaskRequirement(memory_bytes=60),
        )

    assert results == list(range(2 * _WORKER_THREADS))
    assert (_most_tasks_at_once_on_one_worker() > 1) is shares_a_worker
