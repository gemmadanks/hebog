"""Dask execution using a scheduler client owned by the caller."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Generator, Iterable
from contextlib import suppress
from typing import Any, TypeVar, cast

from distributed import (
    Client,
    wait,  # pyright: ignore[reportUnknownVariableType]
)
from distributed.client import FuturesCancelledError

from hebog.executors.base import (
    ExecutorCapacity,
    TaskRequirement,
    admitted_tasks_in_flight,
    reduce_in_canonical_order,
    require_serializable,
    require_serializable_payloads,
)

Input = TypeVar("Input")
Output = TypeVar("Output")

# Enough runnable work to keep every admitted thread busy while one batch
# waits on storage, without publishing the whole plan to the scheduler.
_TASKS_IN_FLIGHT_PER_THREAD = 2


def _wait_for_submitted(futures: Iterable[Any]) -> None:
    """Return once no task behind ``futures`` can still be running.

    Dask cannot stop a task a worker has started, and a future does not say
    whether its task has started, so every pending task is waited for:
    cancelling one would leave it running unobserved. A future already
    settled, cancelled included, is not waited for again, and one the
    client cancels during the wait, as it does when it loses the scheduler,
    counts as settled, so the failure that started the wait propagates.
    """
    pending = [future for future in futures if future.status == "pending"]
    if pending:
        with suppress(FuturesCancelledError):
            wait(pending)


class _BoundedWindow:
    """Every task one executor call has in flight, and the bound on them.

    Mappers are held until their result is consumed, because an unconsumed
    result occupies worker memory. Reserved tasks are the combines a
    reduction submits from its fold rather than from the mapper loop; they
    are counted the same way, and because they depend only on work already
    submitted, waiting for one of them always makes progress.
    """

    def __init__(self, limit: int) -> None:
        """Bind one admitted in-flight bound."""
        self._limit = limit
        self.mappers: deque[Any] = deque()
        self._reserved: list[Any] = []

    def _live_reserved(self) -> int:
        """Drop settled combines, raise the first failure, count the rest."""
        remaining: list[Any] = []
        for future in self._reserved:
            if future.status == "error":
                future.result()
            if future.status == "pending":
                remaining.append(future)
        self._reserved = remaining
        return len(remaining)

    def has_room(self) -> bool:
        """Return whether one more task fits, raising a failed combine."""
        return len(self.mappers) + self._live_reserved() < self._limit

    def wait_for_reserved(self) -> bool:
        """Wait for one combine to settle; report whether any could."""
        if not self._reserved:
            return False
        wait(self._reserved, return_when="FIRST_COMPLETED")
        self._live_reserved()
        return True

    def reserve(self, future: Any) -> None:
        """Record one task submitted outside the mapper loop."""
        self._reserved.append(future)

    def release_reserved(self) -> None:
        """Wait for every combine still running, then release them all."""
        _wait_for_submitted(self._reserved)
        self._reserved = []


class DaskExecutor:
    """Submit coarse batches to an existing Dask client.

    Hebog never creates, resizes or closes the client. Submission stays
    within the admitted in-flight bound, results are consumed in input
    order, and reductions combine on workers so the driver gathers one
    value rather than one result per batch.
    """

    def __init__(
        self,
        client: Client,
        *,
        capacity: ExecutorCapacity | None = None,
        retry_limit: int = 0,
    ) -> None:
        """Bind one caller-owned client, budget and retry policy."""
        self._client = client
        self._declared_capacity = capacity
        if retry_limit < 0:
            raise ValueError("retry_limit must not be negative")
        self._retry_limit = retry_limit

    @property
    def client(self) -> Client:
        """Return the caller-owned client this executor submits to."""
        return self._client

    @property
    def capacity(self) -> ExecutorCapacity:
        """Return the declared budget, or the cluster's current one."""
        if self._declared_capacity is None:
            self._declared_capacity = self._cluster_capacity()
        return self._declared_capacity

    def _cluster_capacity(self) -> ExecutorCapacity:
        """Read the budget the caller's cluster currently reports."""
        information = cast(
            dict[str, Any],
            self._client.scheduler_info(),  # pyright: ignore[reportUnknownMemberType]
        )
        workers = cast(dict[str, Any], information.get("workers", {}))
        threads = [
            int(worker.get("nthreads", 1)) for worker in workers.values()
        ]
        memory = [
            int(worker["memory_limit"])
            for worker in workers.values()
            if worker.get("memory_limit")
        ]
        threads_per_worker = min(threads) if threads else 1
        total_threads = sum(threads) if threads else 1
        return ExecutorCapacity(
            worker_count=max(len(workers), 1),
            threads_per_worker=max(threads_per_worker, 1),
            maximum_tasks_in_flight=max(
                total_threads * _TASKS_IN_FLIGHT_PER_THREAD, 1
            ),
            memory_bytes_per_worker=min(memory) if memory else None,
        )

    def _submit(self, function: Callable[..., Any], *arguments: Any) -> Any:
        """Submit one task, letting Dask retry an idempotent failure."""
        return self._client.submit(  # pyright: ignore[reportUnknownMemberType]
            function,
            *arguments,
            pure=False,
            retries=self._retry_limit,
        )

    def _ordered_futures(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        requirement: TaskRequirement | None,
        *,
        window: _BoundedWindow | None = None,
    ) -> Generator[Any]:
        """Yield completed futures in input order, bounding submission.

        A reduction passes its own window, so its combines occupy the same
        bound as its mappers. When the window is full this loop consumes a
        mapper, or waits for a combine when no mapper is in flight; it never
        submits past the bound. Counting combines may raise, which stops
        the plan exactly as a failed mapper does.
        """
        self.capacity.admit(requirement)
        prepared = require_serializable_payloads(function, batches)
        if window is None:
            window = _BoundedWindow(
                admitted_tasks_in_flight(self.capacity, requirement)
            )
        submitted = 0
        try:
            while True:
                while submitted < len(prepared):
                    if not window.has_room():
                        # Free a slot by consuming the oldest mapper, or by
                        # waiting for a combine when none is in flight.
                        if window.mappers or not window.wait_for_reserved():
                            break
                        continue
                    window.mappers.append(
                        self._submit(function, prepared[submitted])
                    )
                    submitted += 1
                if not window.mappers:
                    return
                future = window.mappers.popleft()
                wait([future])
                if future.status == "error":
                    # Futures are consumed in input order, so the first
                    # failure observed is the first failing batch.
                    future.result()
                yield future
        finally:
            # Nothing more of the plan is submitted, and the call returns only
            # once no task it submitted can still be running, so none writes
            # into storage its caller is already removing. The in-flight
            # bound limits that wait.
            _wait_for_submitted(window.mappers)
            window.mappers.clear()

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[Output]:
        """Submit batches and gather their results in input order."""
        return [
            cast(Output, future.result())
            for future in self._ordered_futures(function, batches, requirement)
        ]

    def reduce_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        combine: Callable[[Output, Output], Output],
        *,
        requirement: TaskRequirement | None = None,
    ) -> Output:
        """Combine batch results on workers and gather one value.

        Combines are submitted to workers and occupy the same in-flight
        bound as the mappers, so a reduction never runs more tasks than the
        caller admitted. They are checked for failure as the reduction
        proceeds, so a failed combine stops submission instead of surfacing
        only when the final value is gathered. However the reduction ends,
        it waits for every mapper and combine it submitted and then releases
        them.
        """
        require_serializable(combine, name="combine")
        window = _BoundedWindow(
            admitted_tasks_in_flight(self.capacity, requirement)
        )

        def combine_on_worker(first: Any, second: Any) -> Any:
            """Submit one combine so intermediates stay on the cluster."""
            # A mapper was consumed to reach this fold, so the first combine
            # of a cascade always has room and each later one waits for an
            # earlier combine. Waiting stops when nothing can free a slot,
            # so a mistaken bound cannot hang the reduction.
            while not window.has_room() and window.wait_for_reserved():
                pass
            future = self._submit(combine, first, second)
            window.reserve(future)
            return future

        mapped = self._ordered_futures(
            function, batches, requirement, window=window
        )
        try:
            reduced = reduce_in_canonical_order(mapped, combine_on_worker)
            return cast(Output, reduced.result())
        finally:
            # A combine can fail while mappers run. Closing the generator
            # settles them now rather than whenever it is collected; the
            # combines are settled and released after them.
            mapped.close()
            window.release_reserved()
