"""Unit tests for execution policies and the shared executor contract.

Behaviour shared by every policy lives in the executor contract suite. These
tests cover the pieces each policy owns: budget validation, the canonical
reduction shape, thread-pool lifetime and bounded Dask submission, none of
which needs a running scheduler.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

import pytest

from hebog.executors import (
    ExecutorAdmissionError,
    ExecutorCapacity,
    ExecutorPayloadError,
    SerialExecutor,
    TaskRequirement,
    ThreadExecutor,
    reduce_in_canonical_order,
)
from hebog.executors.base import (
    admitted_tasks_in_flight,
    call_with_retries,
    require_serializable_payloads,
)


def _label(value: int) -> str:
    """Return one element that records how it was combined."""
    return str(value)


def _combine(first: str, second: str) -> str:
    """Record the association of one combine without commuting it."""
    return f"({first}+{second})"


def _square(value: int) -> int:
    """Return one square from a module-level serializable function."""
    return value**2


def _identity(value: object) -> object:
    """Return one payload unchanged for serialization checks."""
    return value


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (1, "0"),
        (2, "(0+1)"),
        (3, "((0+1)+2)"),
        (4, "((0+1)+(2+3))"),
        (5, "(((0+1)+(2+3))+4)"),
        (6, "(((0+1)+(2+3))+(4+5))"),
        (7, "((((0+1)+(2+3))+(4+5))+6)"),
        (8, "(((0+1)+(2+3))+((4+5)+(6+7)))"),
    ],
)
def test_canonical_reduction_pairs_by_position(
    count: int,
    expected: str,
) -> None:
    """The reduction tree is decided by input index alone."""
    values = [_label(value) for value in range(count)]

    assert reduce_in_canonical_order(values, _combine) == expected


def test_canonical_reduction_rejects_no_values() -> None:
    """A reduction without an identity element refuses to guess one."""
    with pytest.raises(ValueError, match="at least one batch"):
        reduce_in_canonical_order([], _combine)


def test_canonical_reduction_holds_one_value_per_level() -> None:
    """Reduction memory grows with the tree depth, not the batch count."""
    count = 64
    alive = 0
    peak = 0
    combines = 0

    def values() -> Iterator[str]:
        """Yield labels lazily so held accumulators can be counted."""
        nonlocal alive, peak
        for value in range(count):
            alive += 1
            peak = max(peak, alive)
            yield _label(value)

    def measure(first: str, second: str) -> str:
        """Combine two accumulators into one and record the count."""
        nonlocal alive, combines
        alive -= 1
        combines += 1
        return _combine(first, second)

    reduce_in_canonical_order(values(), measure)

    assert combines == count - 1
    assert peak <= count.bit_length()


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
        self.cancelled = False

    def settle(self) -> None:
        """Mark this task finished, as waiting on a cluster would."""
        if self._error is None:
            self.status = "finished"

    def result(self) -> object:
        """Return the value this stub computed, or raise its failure."""
        if self._error is not None:
            raise self._error
        return self._value

    def cancel(self) -> None:
        """Record that the executor released this task."""
        self.cancelled = True


class _StubClient:
    """Record the submission sequence of one caller-owned client."""

    def __init__(self, *, nthreads: int = 4) -> None:
        """Describe one worker and start an empty submission log."""
        self.events: list[str] = []
        self._nthreads = nthreads

    def scheduler_info(self) -> dict[str, Any]:
        """Report the budget a caller-owned cluster would report."""
        return {
            "workers": {
                "tcp://worker-1": {
                    "nthreads": self._nthreads,
                    "memory_limit": 2_000,
                },
                "tcp://worker-2": {
                    "nthreads": self._nthreads,
                    "memory_limit": 4_000,
                },
            }
        }

    def submit(
        self,
        function: Callable[..., Any],
        *arguments: Any,
        **keywords: Any,
    ) -> _StubFuture:
        """Evaluate one task eagerly and record its submission."""
        del keywords
        self.events.append(f"submit:{function.__name__}")
        # A real client resolves future arguments to their values before the
        # task runs, so combines see results rather than futures.
        values = [
            argument.result()
            if isinstance(argument, _StubFuture)
            else argument
            for argument in arguments
        ]
        try:
            return _StubFuture(function(*values))
        except Exception as error:
            return _StubFuture(None, error)


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


def test_dask_executor_bounds_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Submission never runs further ahead than the in-flight bound."""
    from hebog.executors import dask as dask_module  # noqa: PLC0415

    client = _StubClient()

    def record_wait(futures: Iterable[Any]) -> None:
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


def _sum_values(first: int, second: int) -> int:
    """Combine two mapped values on a worker."""
    return first + second


def _fail_to_combine(first: int, second: int) -> int:
    """Fail every combine so the reduction cannot finish."""
    del first, second
    raise RuntimeError("combine failed")


def _stub_reduction_executor(client: _StubClient) -> Any:
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

    def record_wait(futures: Iterable[Any]) -> None:
        client.events.append("wait")
        for future in futures:
            future.settle()

    monkeypatch.setattr(dask_module, "wait", record_wait)


def test_dask_reduction_counts_combines_against_the_in_flight_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mappers wait for in-flight combines instead of running past them."""
    client = _StubClient()
    _patch_wait(monkeypatch, client)

    reduced = _stub_reduction_executor(client).reduce_batches(
        _square, list(range(9)), _sum_values
    )

    assert reduced == sum(value**2 for value in range(9))
    # This stub never settles a combine, which is the worst case: every
    # combine keeps throttling mapper submission for the whole reduction.
    mappers = 0
    combines = 0
    mapper_submissions = 0
    for event in client.events:
        if event == f"submit:{_square.__name__}":
            # Either the window has room, or this is the single mapper that
            # is always admitted so the reduction cannot stall.
            assert mappers == 0 or mappers + combines < 3
            mappers += 1
            mapper_submissions += 1
        elif event.startswith("submit"):
            combines += 1
        else:
            mappers -= 1
    assert mapper_submissions == 9


def test_dask_reduction_stops_mapping_when_a_combine_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed combine cancels the plan instead of waiting for the value."""
    client = _StubClient()
    _patch_wait(monkeypatch, client)

    with pytest.raises(RuntimeError, match="combine failed"):
        _stub_reduction_executor(client).reduce_batches(
            _square, list(range(32)), _fail_to_combine
        )

    submitted = sum(
        1 for event in client.events if event == f"submit:{_square.__name__}"
    )
    assert submitted < 32
