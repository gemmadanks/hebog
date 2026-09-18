"""Dask execution using a scheduler client owned by the caller."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Iterator
from typing import Any, TypeVar, cast

from distributed import (
    Client,
    wait,  # pyright: ignore[reportUnknownVariableType]
)

from hebog.executors.base import (
    ExecutorCapacity,
    TaskRequirement,
    admitted_tasks_in_flight,
    reduce_in_canonical_order,
    require_serializable_payloads,
)

Input = TypeVar("Input")
Output = TypeVar("Output")

# Enough runnable work to keep every admitted thread busy while one batch
# waits on storage, without publishing the whole plan to the scheduler.
_TASKS_IN_FLIGHT_PER_THREAD = 2


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
    ) -> Iterator[Any]:
        """Yield completed futures in input order, bounding submission."""
        self.capacity.admit(requirement)
        prepared = require_serializable_payloads(function, batches)
        limit = admitted_tasks_in_flight(self.capacity, requirement)
        pending: deque[Any] = deque()
        submitted = 0
        try:
            while True:
                while len(pending) < limit and submitted < len(prepared):
                    pending.append(self._submit(function, prepared[submitted]))
                    submitted += 1
                if not pending:
                    return
                future = pending.popleft()
                wait([future])
                if future.status == "error":
                    # Futures are consumed in input order, so the first
                    # failure observed is the first failing batch.
                    future.result()
                yield future
        finally:
            # Release the rest of the plan rather than running work whose
            # result no caller will read.
            for remaining in pending:
                remaining.cancel()

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
        """Combine batch results on workers and gather one value."""

        def combine_on_worker(first: Any, second: Any) -> Any:
            """Submit one combine so intermediates stay on the cluster."""
            return self._submit(combine, first, second)

        reduced = reduce_in_canonical_order(
            self._ordered_futures(function, batches, requirement),
            combine_on_worker,
        )
        return cast(Output, reduced.result())
