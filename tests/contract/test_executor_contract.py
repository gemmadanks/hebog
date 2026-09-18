"""One executor contract suite for every supported execution policy.

The suite runs against the serial reference, a caller-owned persistent thread
pool and a caller-owned Dask client. Serial and thread parameters carry the
``contract`` marker and need no scheduler; the Dask parameter carries
``integration`` so the contract lane stays scheduler-free.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from hebog.executors import (
    Executor,
    ExecutorAdmissionError,
    ExecutorCapacity,
    ExecutorPayloadError,
    SerialExecutor,
    TaskRequirement,
    ThreadExecutor,
    reduce_in_canonical_order,
)

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

ADMITTED_MEMORY_BYTES = 1_000_000
CONCURRENT_THREAD_COUNT = 2


class ProbeError(RuntimeError):
    """Deterministic injected failure carrying its batch identity."""


@dataclass
class _Tracker:
    """Shared observations of the calls one executor actually made."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    active: int = 0
    peak_active: int = 0
    started: list[int] = field(default_factory=list[int])
    attempts: dict[int, int] = field(default_factory=dict[int, int])
    failing: frozenset[int] = frozenset()
    transient_failures: int = 0

    def reset(self) -> None:
        """Forget every observation so tests cannot depend on order."""
        with self.lock:
            self.active = 0
            self.peak_active = 0
            self.started = []
            self.attempts = {}
            self.failing = frozenset()
            self.transient_failures = 0

    def enter(self, value: int) -> int:
        """Record one started call and return its attempt number."""
        with self.lock:
            self.active += 1
            self.peak_active = max(self.peak_active, self.active)
            self.started.append(value)
            self.attempts[value] = self.attempts.get(value, 0) + 1
            return self.attempts[value]

    def leave(self) -> None:
        """Record one finished call."""
        with self.lock:
            self.active -= 1


TRACKER = _Tracker()


@pytest.fixture(autouse=True)
def reset_tracker() -> Iterator[None]:
    """Give every test an independent view of executor behaviour."""
    TRACKER.reset()
    yield
    TRACKER.reset()


def square(value: int) -> int:
    """Return one square without observing execution."""
    return value**2


def tracked_square(value: int) -> int:
    """Return one square while recording concurrency and ordering."""
    TRACKER.enter(value)
    try:
        # Long enough that a concurrent executor overlaps calls, short
        # enough to keep the suite inside the change-check budget.
        threading.Event().wait(0.02)
        return value**2
    finally:
        TRACKER.leave()


def inverted_delay_square(value: int) -> int:
    """Return one square, finishing later for earlier batches."""
    TRACKER.enter(value)
    try:
        threading.Event().wait(0.01 * (8 - value))
        return value**2
    finally:
        TRACKER.leave()


def fail_on_selected(value: int) -> int:
    """Fail deterministically for the batches the tracker selected."""
    TRACKER.enter(value)
    try:
        threading.Event().wait(0.01)
        if value in TRACKER.failing:
            raise ProbeError(f"batch {value} failed")
        return value**2
    finally:
        TRACKER.leave()


def fail_transiently(value: int) -> int:
    """Fail the configured number of early attempts, then succeed."""
    attempt = TRACKER.enter(value)
    try:
        if attempt <= TRACKER.transient_failures:
            raise ProbeError(f"batch {value} attempt {attempt} failed")
        return value**2
    finally:
        TRACKER.leave()


def label(value: int) -> str:
    """Return one non-commutative reduction element."""
    return f"[{value}]"


def concatenate(first: str, second: str) -> str:
    """Combine two labels without commuting them."""
    return first + second


def blend(first: float, second: float) -> float:
    """Combine two values without associating or commuting them."""
    return (first + 2.0 * second) / 3.0


def as_float(value: int) -> float:
    """Return one reduction element for the non-associative combine."""
    return float(value)


def open_lock(value: object) -> int:
    """Return a batch payload that no executor may serialize."""
    del value
    return 0


@contextmanager
def serial_executor() -> Generator[Executor, None, None]:
    """Yield the deterministic reference executor."""
    yield SerialExecutor(
        capacity=ExecutorCapacity(
            worker_count=1,
            threads_per_worker=1,
            maximum_tasks_in_flight=1,
            memory_bytes_per_worker=ADMITTED_MEMORY_BYTES,
        ),
        retry_limit=1,
    )


@contextmanager
def thread_executor() -> Generator[Executor, None, None]:
    """Yield one caller-owned persistent thread pool."""
    with ThreadExecutor(
        thread_count=CONCURRENT_THREAD_COUNT,
        memory_bytes_per_worker=ADMITTED_MEMORY_BYTES,
        retry_limit=1,
    ) as executor:
        yield executor


@contextmanager
def dask_executor() -> Generator[Executor, None, None]:
    """Yield one executor over a caller-owned local Dask client."""
    from distributed import Client, LocalCluster  # noqa: PLC0415

    from hebog.executors import DaskExecutor  # noqa: PLC0415

    cluster = LocalCluster(
        n_workers=1,
        threads_per_worker=CONCURRENT_THREAD_COUNT,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        yield DaskExecutor(
            client,
            capacity=ExecutorCapacity(
                worker_count=1,
                threads_per_worker=CONCURRENT_THREAD_COUNT,
                maximum_tasks_in_flight=CONCURRENT_THREAD_COUNT,
                memory_bytes_per_worker=ADMITTED_MEMORY_BYTES,
            ),
            retry_limit=1,
        )


@pytest.fixture(
    params=[
        pytest.param(serial_executor, id="serial", marks=pytest.mark.contract),
        pytest.param(
            thread_executor, id="threads", marks=pytest.mark.contract
        ),
        pytest.param(dask_executor, id="dask", marks=pytest.mark.integration),
    ]
)
def executor(
    request: pytest.FixtureRequest,
) -> Iterator[Executor]:
    """Yield each supported executor under one contract."""
    factory: Callable[[], AbstractContextManager[Executor]] = request.param
    with factory() as value:
        yield value


def test_executor_preserves_input_order(executor: Executor) -> None:
    """Results follow input order however the batches complete."""
    batches = list(range(8))

    results = executor.map_batches(inverted_delay_square, batches)

    assert results == [value**2 for value in batches]


def test_executor_reports_bounded_capacity(executor: Executor) -> None:
    """Every executor declares the budget its caller admitted."""
    capacity = executor.capacity

    assert capacity.worker_count >= 1
    assert capacity.threads_per_worker >= 1
    assert capacity.maximum_tasks_in_flight >= 1
    assert capacity.memory_bytes_per_worker == ADMITTED_MEMORY_BYTES


def test_executor_bounds_concurrent_tasks(executor: Executor) -> None:
    """No more tasks run at once than the declared in-flight bound."""
    executor.map_batches(tracked_square, list(range(8)))

    assert TRACKER.peak_active <= executor.capacity.maximum_tasks_in_flight


def test_executor_reduces_in_canonical_order(executor: Executor) -> None:
    """Reduction shape follows input index, not completion order."""
    batches = list(range(7))

    reduced = executor.reduce_batches(label, batches, concatenate)

    assert reduced == reduce_in_canonical_order(
        [label(value) for value in batches], concatenate
    )
    assert reduced == "[0][1][2][3][4][5][6]"


def test_executor_reduction_associates_like_the_reference(
    executor: Executor,
) -> None:
    """A non-associative combine gives the serial reference's value."""
    batches = list(range(6))

    reduced = executor.reduce_batches(as_float, batches, blend)

    assert reduced == reduce_in_canonical_order(
        [as_float(value) for value in batches], blend
    )


def test_executor_reduction_of_one_batch_is_its_mapped_value(
    executor: Executor,
) -> None:
    """A single batch reduces to its own mapped result."""
    assert executor.reduce_batches(label, [4], concatenate) == "[4]"


def test_executor_reduction_rejects_no_batches(executor: Executor) -> None:
    """An empty reduction has no identity and is refused."""
    with pytest.raises(ValueError, match="at least one batch"):
        executor.reduce_batches(label, [], concatenate)


def test_executor_raises_the_lowest_index_failure(
    executor: Executor,
) -> None:
    """Concurrent failures resolve to the first failing batch."""
    TRACKER.failing = frozenset({1, 5})

    with pytest.raises(ProbeError, match="batch 1 failed"):
        executor.map_batches(fail_on_selected, list(range(8)))


def test_executor_stops_submitting_after_a_failure(
    executor: Executor,
) -> None:
    """A failure cancels the remaining plan instead of running it."""
    TRACKER.failing = frozenset({0})

    with pytest.raises(ProbeError, match="batch 0 failed"):
        executor.map_batches(fail_on_selected, list(range(64)))

    assert len(TRACKER.started) <= (
        executor.capacity.maximum_tasks_in_flight
        # The failing batch may be retried up to the configured limit.
        + 1
    )


def test_executor_retries_a_transient_failure(executor: Executor) -> None:
    """An idempotent batch that fails once is retried and succeeds."""
    TRACKER.transient_failures = 1

    assert executor.map_batches(fail_transiently, [2, 3]) == [4, 9]
    assert TRACKER.attempts == {2: 2, 3: 2}


def test_executor_raises_when_retries_are_exhausted(
    executor: Executor,
) -> None:
    """Retries are bounded, so a persistent failure still propagates."""
    TRACKER.transient_failures = 5

    with pytest.raises(ProbeError, match="batch 2"):
        executor.map_batches(fail_transiently, [2])


def test_executor_rejects_an_unserializable_batch(
    executor: Executor,
) -> None:
    """A payload that cannot cross a worker boundary fails early."""
    with pytest.raises(ExecutorPayloadError, match="serializable"):
        executor.map_batches(open_lock, [threading.Lock()])

    assert TRACKER.started == []


def test_executor_rejects_a_requirement_above_the_budget(
    executor: Executor,
) -> None:
    """Admission refuses an oversized task before anything is submitted."""
    with pytest.raises(ExecutorAdmissionError, match="memory"):
        executor.map_batches(
            tracked_square,
            list(range(4)),
            requirement=TaskRequirement(
                memory_bytes=ADMITTED_MEMORY_BYTES + 1
            ),
        )

    assert TRACKER.started == []


def test_executor_rejects_a_requirement_above_the_thread_budget(
    executor: Executor,
) -> None:
    """A task needing more threads than one worker has is refused."""
    threads = executor.capacity.threads_per_worker + 1

    with pytest.raises(ExecutorAdmissionError, match="thread"):
        executor.map_batches(
            tracked_square,
            list(range(4)),
            requirement=TaskRequirement(memory_bytes=1, threads=threads),
        )


def test_executor_narrows_concurrency_to_a_declared_working_set(
    executor: Executor,
) -> None:
    """A task claiming most of the budget stops running beside another."""
    executor.map_batches(
        tracked_square,
        list(range(6)),
        requirement=TaskRequirement(
            memory_bytes=ADMITTED_MEMORY_BYTES // 2 + 1
        ),
    )

    assert TRACKER.peak_active == 1


def test_executor_narrows_concurrency_to_a_declared_thread_count(
    executor: Executor,
) -> None:
    """A task claiming every admitted thread stops running beside another."""
    executor.map_batches(
        tracked_square,
        list(range(6)),
        requirement=TaskRequirement(
            memory_bytes=1,
            threads=executor.capacity.threads_per_worker,
        ),
    )

    assert TRACKER.peak_active == 1


def test_executor_rejects_an_unserializable_combine(
    executor: Executor,
) -> None:
    """A reduction validates its combine before it maps anything."""
    with pytest.raises(ExecutorPayloadError, match="combine"):
        executor.reduce_batches(
            tracked_square,
            [1, 2, 3],
            lambda first, second: first + second,
        )

    assert TRACKER.started == []


def test_executor_runs_an_admitted_requirement(executor: Executor) -> None:
    """A task within the admitted budget runs unchanged."""
    results = executor.map_batches(
        square,
        [1, 2, 3],
        requirement=TaskRequirement(
            memory_bytes=ADMITTED_MEMORY_BYTES,
            threads=1,
        ),
    )

    assert results == [1, 4, 9]


def test_executor_agrees_with_the_serial_reference(
    executor: Executor,
) -> None:
    """Alternate executors reproduce the reference executor's results."""
    batches = list(range(9))
    reference = SerialExecutor()

    assert executor.map_batches(square, batches) == reference.map_batches(
        square, batches
    )
    assert executor.reduce_batches(
        label, batches, concatenate
    ) == reference.reduce_batches(label, batches, concatenate)
