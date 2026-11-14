"""Dask execution using a scheduler client owned by the caller."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import suppress
from typing import Any, TypeVar, cast

from distributed import (
    Client,
    wait,  # pyright: ignore[reportUnknownVariableType]
)
from distributed.client import FuturesCancelledError

from hebog.executors.base import (
    ExecutorAdmissionError,
    ExecutorCapacity,
    TaskRequirement,
    admitted_tasks_in_flight,
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


class DaskExecutor:
    """Submit coarse batches to an existing Dask client.

    Hebog never creates, resizes or closes the client. Submission stays
    within the admitted in-flight bound, a task is submitted whenever one
    finishes, and results are returned in input order.

    ``memory_resource`` and ``core_resource`` name Dask worker resources
    the caller declared, for example with ``dask worker --resources
    "memory=4e9,cores=4"``. Each named resource is attached to every task:
    its declared memory in bytes and its threads, one when it declares
    none. Dask then starts a task only on a worker with that much of each
    still free, so tasks are not co-located past the memory a worker
    declares. Named resources are also the admitted budget, because a
    worker's thread count and memory limit include what other work holds.
    """

    def __init__(
        self,
        client: Client,
        *,
        capacity: ExecutorCapacity | None = None,
        retry_limit: int = 0,
        memory_resource: str | None = None,
        core_resource: str | None = None,
    ) -> None:
        """Bind one caller-owned client, budget, retry policy and resources."""
        self._client = client
        self._declared_capacity = capacity
        if retry_limit < 0:
            raise ValueError("retry_limit must not be negative")
        self._retry_limit = retry_limit
        self._memory_resource = memory_resource
        self._core_resource = core_resource

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

    def _workers(self) -> list[dict[str, Any]]:
        """Return what the caller's cluster reports of each current worker."""
        information = cast(
            dict[str, Any],
            self._client.scheduler_info(),  # pyright: ignore[reportUnknownMemberType]
        )
        return list(
            cast(dict[str, Any], information.get("workers", {})).values()
        )

    def _cluster_capacity(self) -> ExecutorCapacity:
        """Read the budget the caller's cluster currently reports.

        Raises:
            ExecutorAdmissionError: If no worker declares every named
                resource, since Dask would hold Hebog's tasks forever.
        """
        named = [
            name
            for name in (self._memory_resource, self._core_resource)
            if name is not None
        ]
        workers = [
            worker
            for worker in self._workers()
            if all(name in worker.get("resources", {}) for name in named)
        ]
        if named and not workers:
            raise ExecutorAdmissionError(
                f"no worker declares the resources {', '.join(named)} "
                "that Hebog's tasks are told to request"
            )
        threads = [
            int(worker["resources"][self._core_resource])
            if self._core_resource is not None
            else int(worker.get("nthreads", 1))
            for worker in workers
        ]
        memory = [
            int(worker["resources"][self._memory_resource])
            if self._memory_resource is not None
            else int(worker["memory_limit"])
            for worker in workers
            if self._memory_resource is not None or worker.get("memory_limit")
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

    def _task_resources(
        self, requirement: TaskRequirement | None
    ) -> dict[str, int] | None:
        """Return what one task asks of the named worker resources."""
        resources: dict[str, int] = {}
        if self._memory_resource is not None and requirement is not None:
            resources[self._memory_resource] = requirement.memory_bytes
        if self._core_resource is not None:
            resources[self._core_resource] = (
                1 if requirement is None else requirement.threads
            )
        return resources or None

    def _require_a_worker_for(self, resources: dict[str, int] | None) -> None:
        """Refuse a task no current worker declares enough resources for.

        Dask would hold such a task until a worker that could run it joins,
        which may never happen, so it fails before anything is submitted.

        Raises:
            ExecutorAdmissionError: If no worker declares at least the
                task's amount of every named resource.
        """
        if resources is None:
            return
        if not any(
            all(
                worker.get("resources", {}).get(name, 0) >= amount
                for name, amount in resources.items()
            )
            for worker in self._workers()
        ):
            requested = ", ".join(
                f"{amount} {name}" for name, amount in resources.items()
            )
            raise ExecutorAdmissionError(
                f"no worker declares the {requested} one task requests"
            )

    def _submit(
        self,
        function: Callable[..., Any],
        batch: Any,
        resources: dict[str, int] | None,
    ) -> Any:
        """Submit one task, letting Dask retry an idempotent failure."""
        return self._client.submit(  # pyright: ignore[reportUnknownMemberType]
            function,
            batch,
            pure=False,
            retries=self._retry_limit,
            resources=resources,
        )

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[Output]:
        """Submit batches and gather their results in input order.

        No more tasks are in flight than the admitted bound, and each task
        that finishes, whichever it is, makes room for the next batch. A
        failure stops submission; once every task in flight has settled,
        the failure of the earliest batch is raised, as the serial
        reference would raise it.
        """
        self.capacity.admit(requirement)
        prepared = require_serializable_payloads(function, batches)
        limit = admitted_tasks_in_flight(self.capacity, requirement)
        resources = self._task_resources(requirement)
        self._require_a_worker_for(resources)
        # Each future stays in flight until it has settled, so an exception
        # that reaches the driver while it waits, as a caller's deadline
        # does, still waits for every task below.
        in_flight: dict[Any, int] = {}
        results: dict[int, Output] = {}
        submitted = 0
        try:
            while submitted < len(prepared) or in_flight:
                while len(in_flight) < limit and submitted < len(prepared):
                    future = self._submit(
                        function, prepared[submitted], resources
                    )
                    in_flight[future] = submitted
                    submitted += 1
                # A task the client cancels, as it does when it loses the
                # scheduler, has settled too; it fails below as a batch would.
                with suppress(FuturesCancelledError):
                    wait(list(in_flight), return_when="FIRST_COMPLETED")
                finished = [
                    future
                    for future in in_flight
                    if future.status != "pending"
                ]
                if any(future.status != "finished" for future in finished):
                    _wait_for_submitted(in_flight)
                    # Every batch before the failing one was submitted, so
                    # the earliest failure among them is the serial one.
                    min(
                        (
                            future
                            for future in in_flight
                            if future.status != "finished"
                        ),
                        key=in_flight.__getitem__,
                    ).result()
                for future in finished:
                    results[in_flight.pop(future)] = cast(
                        Output, future.result()
                    )
            return [results[index] for index in range(len(prepared))]
        finally:
            # Nothing more of the plan is submitted, and the call returns only
            # once no task it submitted can still be running, so none writes
            # into storage its caller is already removing. The in-flight
            # bound limits that wait.
            _wait_for_submitted(in_flight)
