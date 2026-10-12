"""Unit tests for execution policies and the shared executor contract.

Behaviour shared by every policy lives in the executor contract suite. These
tests cover the pieces each policy owns: budget validation, thread-pool
lifetime and bounded Dask submission, none of which needs a running
scheduler.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from concurrent.futures import CancelledError
from typing import Any

import pytest

from hebog.executors import (
    ExecutorAdmissionError,
    ExecutorCapacity,
    ExecutorPayloadError,
    SerialExecutor,
    TaskRequirement,
    ThreadExecutor,
)
from hebog.executors.base import (
    admitted_tasks_in_flight,
    call_with_retries,
    require_serializable_payloads,
)
from hebog.executors.threads import (
    _CallGuard,  # pyright: ignore[reportPrivateUsage]
)


def _square(value: int) -> int:
    """Return one square from a module-level serializable function."""
    return value**2


def _identity(value: object) -> object:
    """Return one payload unchanged for serialization checks."""
    return value


@pytest.mark.parametrize(
    "capacity",
    [
        {"worker_count": 0},
        {"threads_per_worker": 0},
        {"maximum_tasks_in_flight": -1},
        {"memory_bytes_per_worker": 0},
        {"worker_count": True},
    ],
)
def test_capacity_requires_a_positive_budget(
    capacity: dict[str, int],
) -> None:
    """An unusable budget is refused when it is declared."""
    fields: dict[str, int | None] = {
        "worker_count": 1,
        "threads_per_worker": 1,
        "maximum_tasks_in_flight": 1,
        "memory_bytes_per_worker": 1,
    }
    fields.update(capacity)

    with pytest.raises(ValueError, match="positive integer"):
        ExecutorCapacity(**fields)  # pyright: ignore[reportArgumentType]


def test_capacity_without_a_memory_budget_admits_any_working_set() -> None:
    """An undeclared memory budget is not silently treated as zero."""
    capacity = ExecutorCapacity(
        worker_count=1,
        threads_per_worker=2,
        maximum_tasks_in_flight=2,
    )

    capacity.admit(TaskRequirement(memory_bytes=2**40, threads=2))


def test_requirement_requires_a_positive_working_set() -> None:
    """A task declares a real working set or none at all."""
    with pytest.raises(ValueError, match="positive integer"):
        TaskRequirement(memory_bytes=0)


def test_admission_names_the_exceeded_budget() -> None:
    """An admission failure says what was needed and what was admitted."""
    capacity = ExecutorCapacity(
        worker_count=1,
        threads_per_worker=1,
        maximum_tasks_in_flight=1,
        memory_bytes_per_worker=100,
    )

    with pytest.raises(ExecutorAdmissionError, match="101 bytes"):
        capacity.admit(TaskRequirement(memory_bytes=101))


def test_serial_executor_declares_one_task_in_flight() -> None:
    """The reference executor runs exactly one batch at a time."""
    capacity = SerialExecutor().capacity

    assert capacity.maximum_tasks_in_flight == 1
    assert capacity.memory_bytes_per_worker is None


def test_serialization_failure_names_the_offending_batch() -> None:
    """A payload failure identifies the batch a caller must fix."""
    batches: list[object] = [1, lambda: None]

    with pytest.raises(ExecutorPayloadError, match="batch 1"):
        require_serializable_payloads(_identity, batches)


def test_retries_stop_at_the_configured_limit() -> None:
    """A task is attempted once more than its retry limit allows."""
    attempts: list[int] = []

    def always_fail(value: int) -> int:
        attempts.append(value)
        raise RuntimeError("batch failed")

    with pytest.raises(RuntimeError, match="batch failed"):
        call_with_retries(always_fail, 7, retry_limit=2)

    assert attempts == [7, 7, 7]


def test_thread_executor_requires_a_positive_thread_count() -> None:
    """A pool without threads cannot run the plan it is given."""
    with pytest.raises(ValueError, match="positive integer"):
        ThreadExecutor(0)


def test_thread_executor_releases_its_pool_when_closed() -> None:
    """The caller owns the pool, so closing it ends further work."""
    executor = ThreadExecutor(2)

    with executor:
        assert executor.map_batches(_square, [2, 3]) == [4, 9]

    executor.close()
    with pytest.raises(RuntimeError):
        executor.map_batches(_square, [2])


class _StubFuture:
    """One eagerly evaluated future whose settlement the test controls."""

    def __init__(self, value: object, error: Exception | None = None) -> None:
        """Evaluate eagerly so the stub needs no scheduler."""
        self.status = "error" if error is not None else "pending"
        self._value = value
        self._error = error

    def settle(self) -> None:
        """Mark this task finished, as waiting on a cluster would."""
        if self._error is None:
            self.status = "finished"

    def result(self) -> object:
        """Return the value this stub computed, or raise its failure."""
        if self._error is not None:
            raise self._error
        return self._value


class _StubClient:
    """Record the submission sequence of one caller-owned client."""

    def __init__(
        self,
        *,
        nthreads: int = 4,
        resources: tuple[dict[str, float], ...] = ({}, {}),
    ) -> None:
        """Describe two workers and start an empty submission log."""
        self.events: list[str] = []
        self.futures: list[_StubFuture] = []
        self.outstanding_at_submit: list[int] = []
        self.submitted_resources: list[dict[str, float] | None] = []
        self._nthreads = nthreads
        self._resources = resources

    def outstanding(self) -> int:
        """Return how many submitted tasks have not settled."""
        return sum(1 for future in self.futures if future.status == "pending")

    def scheduler_info(self) -> dict[str, Any]:
        """Report the budget a caller-owned cluster would report."""
        return {
            "workers": {
                f"tcp://worker-{index}": {
                    "nthreads": self._nthreads,
                    "memory_limit": memory_limit,
                    "resources": resources,
                }
                for index, (memory_limit, resources) in enumerate(
                    zip((2_000, 4_000), self._resources, strict=True), start=1
                )
            }
        }

    def submit(
        self,
        function: Callable[..., Any],
        *arguments: Any,
        **keywords: Any,
    ) -> _StubFuture:
        """Evaluate one task eagerly and record its submission."""
        self.submitted_resources.append(keywords.get("resources"))
        self.events.append(f"submit:{function.__name__}")
        self.outstanding_at_submit.append(self.outstanding())
        try:
            future = _StubFuture(function(*arguments))
        except Exception as error:
            future = _StubFuture(None, error)
        self.futures.append(future)
        return future


def _stub_executor(client: _StubClient, **keywords: Any) -> Any:
    """Build a Dask executor over the stub without importing a cluster."""
    from hebog.executors import DaskExecutor  # noqa: PLC0415

    return DaskExecutor(client, **keywords)  # pyright: ignore[reportArgumentType]


def test_dask_executor_reads_the_cluster_budget() -> None:
    """An undeclared budget comes from the caller's own cluster."""
    capacity = _stub_executor(_StubClient()).capacity

    assert capacity.worker_count == 2
    assert capacity.threads_per_worker == 4
    assert capacity.maximum_tasks_in_flight == 16
    assert capacity.memory_bytes_per_worker == 2_000


_NAMED_RESOURCES = (
    {"memory": 3_000.0, "cores": 4.0},
    {"memory": 5_000.0, "cores": 2.0},
)


def test_dask_executor_attaches_no_resources_unless_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller who names no resource gets Dask's default placement."""
    client = _StubClient()
    _patch_wait(monkeypatch, client)

    _stub_executor(client).map_batches(
        _square, [1, 2], requirement=TaskRequirement(memory_bytes=1_000)
    )

    assert client.submitted_resources == [None, None]


def test_dask_executor_declares_each_task_under_the_named_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every task asks Dask for its declared memory and threads."""
    client = _StubClient(resources=_NAMED_RESOURCES)
    _patch_wait(monkeypatch, client)
    executor = _stub_executor(
        client, memory_resource="memory", core_resource="cores"
    )

    results = executor.map_batches(
        _square,
        [1, 2, 3],
        requirement=TaskRequirement(memory_bytes=1_500, threads=2),
    )

    assert results == [1, 4, 9]
    assert client.submitted_resources == [{"memory": 1_500, "cores": 2}] * 3


def test_dask_executor_declares_one_core_for_an_undeclared_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A task without a requirement still occupies one named core."""
    client = _StubClient(resources=_NAMED_RESOURCES)
    _patch_wait(monkeypatch, client)
    executor = _stub_executor(
        client, memory_resource="memory", core_resource="cores"
    )

    executor.map_batches(_square, [1])

    assert client.submitted_resources == [{"cores": 1}]


def test_dask_executor_reads_its_budget_from_the_named_resources() -> None:
    """The admitted budget is what the workers declare, not their limits.

    A worker's thread count and memory limit include what other work, such
    as DP3, holds, so the named resources are the budget when they exist.
    """
    capacity = _stub_executor(
        _StubClient(resources=_NAMED_RESOURCES),
        memory_resource="memory",
        core_resource="cores",
    ).capacity

    assert capacity.worker_count == 2
    assert capacity.threads_per_worker == 2
    assert capacity.memory_bytes_per_worker == 3_000
    assert capacity.maximum_tasks_in_flight == 12


def test_dask_executor_counts_only_workers_declaring_every_resource() -> None:
    """A worker without the named resources never runs Hebog's tasks."""
    capacity = _stub_executor(
        _StubClient(resources=({"memory": 3_000.0, "cores": 4.0}, {})),
        memory_resource="memory",
        core_resource="cores",
    ).capacity

    assert capacity.worker_count == 1
    assert capacity.threads_per_worker == 4
    assert capacity.memory_bytes_per_worker == 3_000


def test_dask_executor_refuses_resources_no_worker_declares() -> None:
    """A task no worker could ever run fails at once instead of waiting."""
    client = _StubClient()
    executor = _stub_executor(client, memory_resource="hebog-memory")

    with pytest.raises(ExecutorAdmissionError, match="hebog-memory"):
        executor.map_batches(_square, [1])

    assert client.submitted_resources == []


def test_dask_executor_refuses_a_task_larger_than_its_workers_declare() -> (
    None
):
    """Admission compares a task with the memory the workers declare."""
    client = _StubClient(resources=_NAMED_RESOURCES)
    executor = _stub_executor(
        client, memory_resource="memory", core_resource="cores"
    )

    with pytest.raises(ExecutorAdmissionError, match="3000 bytes"):
        executor.map_batches(
            _square, [1], requirement=TaskRequirement(memory_bytes=3_001)
        )

    assert client.submitted_resources == []


@pytest.mark.parametrize(
    "resources",
    [({}, {}), ({"memory": 1_000.0}, {"memory": 1_499.0})],
    ids=["undeclared", "too-small"],
)
def test_dask_executor_checks_the_workers_under_a_declared_budget(
    resources: tuple[dict[str, float], ...],
) -> None:
    """A declared budget does not stand in for the workers' resources.

    The task fits the budget, but no worker declares enough memory for it,
    so Dask would hold it forever.
    """
    client = _StubClient(resources=resources)
    executor = _stub_executor(
        client,
        capacity=ExecutorCapacity(
            worker_count=2,
            threads_per_worker=4,
            maximum_tasks_in_flight=8,
            memory_bytes_per_worker=10_000,
        ),
        memory_resource="memory",
    )

    with pytest.raises(ExecutorAdmissionError, match="1500 memory"):
        executor.map_batches(
            _square, [1], requirement=TaskRequirement(memory_bytes=1_500)
        )

    assert client.submitted_resources == []


def test_dask_executor_bounds_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Submission never runs further ahead than the in-flight bound."""
    from hebog.executors import dask as dask_module  # noqa: PLC0415

    client = _StubClient()

    def record_wait(futures: Iterable[Any], **keywords: Any) -> None:
        del keywords
        client.events.append("wait")
        for future in futures:
            future.settle()

    monkeypatch.setattr(dask_module, "wait", record_wait)
    executor = _stub_executor(
        client,
        capacity=ExecutorCapacity(
            worker_count=1,
            threads_per_worker=1,
            maximum_tasks_in_flight=3,
        ),
    )

    results = executor.map_batches(_square, list(range(9)))

    assert results == [value**2 for value in range(9)]
    assert _peak_in_flight(client.events) <= 3


@pytest.mark.parametrize(
    ("memory_bytes", "expected"),
    [
        (None, 8),
        (1_000, 8),
        (4_000, 4),
        (6_000, 2),
        (20_000, 1),
    ],
)
def test_declared_working_set_narrows_the_in_flight_window(
    memory_bytes: int | None,
    expected: int,
) -> None:
    """Concurrency follows the whole admitted budget, within the bound."""
    capacity = ExecutorCapacity(
        worker_count=2,
        threads_per_worker=4,
        maximum_tasks_in_flight=8,
        memory_bytes_per_worker=10_000,
    )
    requirement = (
        None if memory_bytes is None else TaskRequirement(memory_bytes)
    )

    assert admitted_tasks_in_flight(capacity, requirement) == expected


@pytest.mark.parametrize(
    ("threads", "expected"),
    [(1, 8), (2, 4), (3, 2), (4, 2), (8, 1)],
)
def test_declared_threads_occupy_proportional_in_flight_slots(
    threads: int,
    expected: int,
) -> None:
    """A multi-threaded task takes several slots, a single-threaded one."""
    capacity = ExecutorCapacity(
        worker_count=2,
        threads_per_worker=4,
        maximum_tasks_in_flight=8,
    )

    assert (
        admitted_tasks_in_flight(
            capacity, TaskRequirement(memory_bytes=1, threads=threads)
        )
        == expected
    )


def test_undeclared_memory_budget_keeps_the_caller_bound() -> None:
    """Without an admitted budget the caller's bound is the only limit."""
    capacity = ExecutorCapacity(
        worker_count=1,
        threads_per_worker=2,
        maximum_tasks_in_flight=5,
    )

    assert admitted_tasks_in_flight(capacity, TaskRequirement(2**30)) == 5


@pytest.mark.parametrize(
    "build",
    [
        lambda: SerialExecutor(retry_limit=-1),
        lambda: ThreadExecutor(2, retry_limit=-1),
    ],
    ids=["serial", "threads"],
)
def test_executors_reject_a_negative_retry_limit(
    build: Callable[[], object],
) -> None:
    """A retry policy is a count, so a negative limit is refused."""
    with pytest.raises(ValueError, match="retry_limit"):
        build()


def test_dask_executor_rejects_a_negative_retry_limit() -> None:
    """The Dask policy validates its retry limit like the others."""
    with pytest.raises(ValueError, match="retry_limit"):
        _stub_executor(_StubClient(), retry_limit=-1)


def test_dask_executor_exposes_the_caller_owned_client() -> None:
    """The caller keeps the client Hebog submits to."""
    client = _StubClient()

    assert _stub_executor(client).client is client


def test_executors_package_rejects_an_unknown_name() -> None:
    """Only the optional Dask executor loads lazily by attribute."""
    import hebog.executors as executors_package  # noqa: PLC0415

    with pytest.raises(AttributeError, match="ClusterExecutor"):
        _ = executors_package.ClusterExecutor  # pyright: ignore[reportAttributeAccessIssue]


def _peak_in_flight(events: list[str]) -> int:
    """Return the most tasks outstanding at once in one submission log."""
    in_flight = 0
    peak = 0
    for event in events:
        in_flight += 1 if event.startswith("submit") else -1
        peak = max(peak, in_flight)
    return peak


def _stub_bounded_executor(client: _StubClient) -> Any:
    """Build one Dask executor with a small explicit in-flight bound."""
    return _stub_executor(
        client,
        capacity=ExecutorCapacity(
            worker_count=1,
            threads_per_worker=1,
            maximum_tasks_in_flight=3,
        ),
    )


def _patch_wait(
    monkeypatch: pytest.MonkeyPatch,
    client: _StubClient,
) -> None:
    """Settle only the futures the executor explicitly waits for."""
    from hebog.executors import dask as dask_module  # noqa: PLC0415

    def record_wait(futures: Iterable[Any], **keywords: Any) -> None:
        del keywords
        client.events.append("wait")
        for future in futures:
            future.settle()

    monkeypatch.setattr(dask_module, "wait", record_wait)


def _fail_first_batch(value: int) -> int:
    """Fail batch 0 and square every other batch."""
    if value == 0:
        raise RuntimeError("batch 0 failed")
    return value**2


def test_failed_dask_map_waits_for_every_task_it_submitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dask cannot stop a started task, so none is cancelled and left running.

    Only a wait proves a task has stopped: a cancelled task a worker has
    started keeps running, and writing, after the call returns.
    """
    client = _StubClient()
    _patch_wait(monkeypatch, client)

    with pytest.raises(RuntimeError, match="batch 0 failed"):
        _stub_bounded_executor(client).map_batches(
            _fail_first_batch, list(range(8))
        )

    # The window held three tasks when batch 0 failed; nothing more was
    # submitted, and the two still pending were waited for.
    assert [future.status for future in client.futures] == [
        "error",
        "finished",
        "finished",
    ]


def test_a_wait_the_client_cancels_keeps_the_failing_batch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Losing the scheduler while a failed call waits keeps its own error.

    The client cancels every future when it loses the scheduler, and a
    cancelled future counts as settled, so the batch failure propagates
    rather than the cancellation.
    """
    from distributed.client import FuturesCancelledError  # noqa: PLC0415

    from hebog.executors import dask as dask_module  # noqa: PLC0415

    client = _StubClient()

    def cancel_while_waiting(futures: Iterable[Any], **keywords: Any) -> None:
        del keywords
        pending = [future for future in futures if future.status == "pending"]
        for future in pending:
            future.status = "cancelled"
        if pending:
            raise FuturesCancelledError([])

    monkeypatch.setattr(dask_module, "wait", cancel_while_waiting)

    with pytest.raises(RuntimeError, match="batch 0 failed"):
        _stub_bounded_executor(client).map_batches(
            _fail_first_batch, list(range(8))
        )

    assert [future.status for future in client.futures] == [
        "error",
        "cancelled",
        "cancelled",
    ]


class _CallerDeadlineError(Exception):
    """A caller's deadline, raised in the thread that drives the call."""


_SLOW_LOG_LOCK = threading.Lock()
_SLOW_STARTED: list[int] = []
_SLOW_FINISHED: list[int] = []


def _logged_slow(value: int) -> int:
    """Record when one batch starts and ends, around a short wait."""
    with _SLOW_LOG_LOCK:
        _SLOW_STARTED.append(value)
    threading.Event().wait(0.05)
    with _SLOW_LOG_LOCK:
        _SLOW_FINISHED.append(value)
    return value


def test_a_task_orphaned_by_an_interrupted_submission_never_runs_late(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exception that reaches the driver inside ``submit`` leaves no task.

    A deadline the caller enforces by raising in the driving thread, as
    Prefect does, can arrive after the pool queued a task but before the
    driver holds its future. That task has either finished when the call
    raises, or never runs, so nothing writes after the caller cleans up.
    """
    _SLOW_STARTED.clear()
    _SLOW_FINISHED.clear()
    executor = ThreadExecutor(1)
    pool = executor._pool  # pyright: ignore[reportPrivateUsage]
    submit = pool.submit
    submissions: list[object] = []

    def submit_until_the_deadline(*arguments: Any, **keywords: Any) -> Any:
        future = submit(*arguments, **keywords)
        submissions.append(future)
        if len(submissions) == 2:
            raise _CallerDeadlineError
        return future

    monkeypatch.setattr(pool, "submit", submit_until_the_deadline)

    with executor:
        with pytest.raises(_CallerDeadlineError):
            executor.map_batches(_logged_slow, [0, 1, 2, 3])
        with _SLOW_LOG_LOCK:
            started_when_raised = sorted(_SLOW_STARTED)
            finished_when_raised = sorted(_SLOW_FINISHED)
        threading.Event().wait(0.3)

    assert started_when_raised == finished_when_raised
    assert sorted(_SLOW_STARTED) == started_when_raised


def test_a_dask_call_interrupted_while_waiting_still_waits_for_that_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deadline raised as the driver waits on a batch leaves none running.

    The batch being waited for is still in flight when the exception
    arrives, so the call waits for it as well as for the others before the
    exception propagates.
    """
    from hebog.executors import dask as dask_module  # noqa: PLC0415

    client = _StubClient()
    waits: list[int] = []

    def deadline_on_the_first_wait(
        futures: Iterable[Any], **keywords: Any
    ) -> None:
        del keywords
        waits.append(len(waits))
        if len(waits) == 1:
            raise _CallerDeadlineError
        for future in futures:
            future.settle()

    monkeypatch.setattr(dask_module, "wait", deadline_on_the_first_wait)

    with pytest.raises(_CallerDeadlineError):
        _stub_bounded_executor(client).map_batches(_square, list(range(8)))

    assert [future.status for future in client.futures] == ["finished"] * 3


def test_a_task_of_a_stopped_thread_call_never_runs() -> None:
    """Once a call has stopped, a task the pool still holds does nothing."""
    guard = _CallGuard()
    assert guard.run(_square, 3, 0) == 9
    guard.stop()

    with pytest.raises(CancelledError):
        guard.run(_square, 2, 0)
