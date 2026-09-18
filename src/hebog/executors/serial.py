"""Deterministic reference executor."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import TypeVar

from hebog.executors.base import (
    ExecutorCapacity,
    TaskRequirement,
    call_with_retries,
    reduce_in_canonical_order,
    require_serializable,
    require_serializable_payloads,
)

Input = TypeVar("Input")
Output = TypeVar("Output")

_SERIAL_CAPACITY = ExecutorCapacity(
    worker_count=1,
    threads_per_worker=1,
    maximum_tasks_in_flight=1,
)


class SerialExecutor:
    """Run batches serially for testing and scientific reference results.

    This executor defines the behaviour every other policy must reproduce:
    input ordering, the canonical reduction tree, payload validation, retry
    of idempotent tasks and the first failing batch by index.
    """

    def __init__(
        self,
        *,
        capacity: ExecutorCapacity | None = None,
        retry_limit: int = 0,
    ) -> None:
        """Bind the caller's admitted budget and retry policy."""
        self._capacity = capacity or _SERIAL_CAPACITY
        if retry_limit < 0:
            raise ValueError("retry_limit must not be negative")
        self._retry_limit = retry_limit

    @property
    def capacity(self) -> ExecutorCapacity:
        """Return the execution budget admitted by the caller."""
        return self._capacity

    def _results(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        requirement: TaskRequirement | None,
    ) -> Iterator[Output]:
        """Yield admitted, validated results in input order."""
        self._capacity.admit(requirement)
        for batch in require_serializable_payloads(function, batches):
            yield call_with_retries(
                function, batch, retry_limit=self._retry_limit
            )

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[Output]:
        """Apply ``function`` to each batch in input order."""
        return list(self._results(function, batches, requirement))

    def reduce_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        combine: Callable[[Output, Output], Output],
        *,
        requirement: TaskRequirement | None = None,
    ) -> Output:
        """Map batches and combine them in the canonical reduction tree."""
        require_serializable(combine, name="combine")
        return reduce_in_canonical_order(
            self._results(function, batches, requirement), combine
        )
