"""Executor protocol and the execution contract every policy must meet.

One contract governs the serial reference, a caller-owned thread pool and a
caller-owned Dask client: results follow input order, submission and gathering
stay bounded, reductions combine in one partition-independent tree, payloads
must be serializable, idempotent tasks may be retried, the first failing batch
by index propagates and the remaining plan is cancelled.
"""

from __future__ import annotations

import pickle
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from numbers import Integral
from typing import Protocol, TypeVar

Input = TypeVar("Input")
Output = TypeVar("Output")
Value = TypeVar("Value")


class ExecutorAdmissionError(ValueError):
    """One task declared more resource than the caller admitted."""


class ExecutorPayloadError(ValueError):
    """One task payload cannot cross a worker boundary."""


def _positive_count(value: int, name: str) -> int:
    """Return one validated positive count, rejecting booleans."""
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be a positive integer")
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


@dataclass(frozen=True, slots=True)
class ExecutorCapacity:
    """The execution budget the caller admitted for one source finder.

    ``memory_bytes_per_worker`` is the working set one task may hold. It is
    ``None`` when the caller has declared no budget, in which case memory
    admission is not enforced and a stage needing a budget must say so.
    """

    worker_count: int
    threads_per_worker: int
    maximum_tasks_in_flight: int
    memory_bytes_per_worker: int | None = None

    def __post_init__(self) -> None:
        """Require a positive, bounded and explicit execution budget."""
        _positive_count(self.worker_count, "worker_count")
        _positive_count(self.threads_per_worker, "threads_per_worker")
        _positive_count(
            self.maximum_tasks_in_flight, "maximum_tasks_in_flight"
        )
        if self.memory_bytes_per_worker is not None:
            _positive_count(
                self.memory_bytes_per_worker, "memory_bytes_per_worker"
            )

    def admit(self, requirement: TaskRequirement | None) -> None:
        """Raise before submission when one task exceeds the budget."""
        if requirement is None:
            return
        admitted = self.memory_bytes_per_worker
        if admitted is not None and requirement.memory_bytes > admitted:
            raise ExecutorAdmissionError(
                f"task requires {requirement.memory_bytes} bytes of memory "
                f"but {admitted} bytes are admitted per worker"
            )
        if requirement.threads > self.threads_per_worker:
            raise ExecutorAdmissionError(
                f"task requires {requirement.threads} threads but "
                f"{self.threads_per_worker} threads are admitted per worker"
            )


@dataclass(frozen=True, slots=True)
class TaskRequirement:
    """One task's declared peak working set and thread requirement."""

    memory_bytes: int
    threads: int = 1

    def __post_init__(self) -> None:
        """Require a positive declared working set and thread count."""
        _positive_count(self.memory_bytes, "memory_bytes")
        _positive_count(self.threads, "threads")


def admitted_tasks_in_flight(
    capacity: ExecutorCapacity,
    requirement: TaskRequirement | None,
) -> int:
    """Return how many declared tasks may run at once within the budget.

    A declared working set narrows the in-flight window so concurrent tasks
    fit the admitted memory. It never widens it: the caller's in-flight bound
    remains the ceiling, and a narrower window changes scheduling only, never
    ownership or results.
    """
    limit = capacity.maximum_tasks_in_flight
    admitted = capacity.memory_bytes_per_worker
    if requirement is None or admitted is None:
        return limit
    per_worker = admitted // requirement.memory_bytes
    return max(1, min(limit, per_worker * capacity.worker_count))


def require_serializable_payloads(
    function: Callable[[Input], Output],
    batches: Iterable[Input],
) -> list[Input]:
    """Return materialized batches once every payload can be serialized.

    Every executor validates before submitting anything, so an unserializable
    payload fails the same way on the serial reference as on a cluster,
    instead of surfacing only when a worker is a separate process.
    """
    materialized = list(batches)
    for name, payload in (
        ("function", function),
        *(
            (f"batch {index}", batch)
            for index, batch in enumerate(materialized)
        ),
    ):
        try:
            pickle.dumps(payload)
        except Exception as error:
            raise ExecutorPayloadError(
                f"executor {name} payload is not serializable"
            ) from error
    return materialized


def call_with_retries(
    function: Callable[[Input], Output],
    batch: Input,
    *,
    retry_limit: int,
) -> Output:
    """Call one idempotent task, retrying up to ``retry_limit`` times."""
    attempt = 0
    while True:
        try:
            return function(batch)
        except Exception:
            if attempt >= retry_limit:
                raise
            attempt += 1


def reduce_in_canonical_order(
    values: Iterable[Value],
    combine: Callable[[Value, Value], Value],
) -> Value:
    """Combine values in one partition-independent binary tree.

    Values are consumed in index order and combined as adjacent pairs of
    equal height, so the association is decided by position alone. Every
    executor uses this shape, which keeps floating-point summation and
    non-commutative merges identical whatever the completion order is. At
    most one accumulator per tree level is held, so a reduction never holds
    one value per batch.
    """
    carry: list[tuple[int, Value]] = []
    for value in values:
        level = 0
        current = value
        while carry and carry[-1][0] == level:
            previous = carry.pop()[1]
            current = combine(previous, current)
            level += 1
        carry.append((level, current))
    if not carry:
        raise ValueError("a reduction requires at least one batch")
    result = carry[0][1]
    for _, value in carry[1:]:
        result = combine(result, value)
    return result


class Executor(Protocol):
    """Execute coarse batches without exposing scheduler-specific objects."""

    @property
    def capacity(self) -> ExecutorCapacity:
        """Return the execution budget admitted by the caller."""
        ...

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[Output]:
        """Apply ``function`` to each batch and return ordered results."""
        ...

    def reduce_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        combine: Callable[[Output, Output], Output],
        *,
        requirement: TaskRequirement | None = None,
    ) -> Output:
        """Map batches and combine them without gathering every result.

        ``combine`` must be deterministic; it need not be commutative or
        associative, because the reduction tree is fixed by input order.
        """
        ...
