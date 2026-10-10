"""Caller-owned persistent thread execution for one local process."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Generator, Iterable
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from contextlib import closing
from types import TracebackType
from typing import TypeVar

from hebog.executors.base import (
    ExecutorCapacity,
    TaskRequirement,
    admitted_tasks_in_flight,
    call_with_retries,
    reduce_in_canonical_order,
    require_serializable,
    require_serializable_payloads,
)

Input = TypeVar("Input")
Output = TypeVar("Output")


class _CallGuard:
    """Let one call's tasks start only while the call goes on.

    A task enters before it runs and leaves when it ends. Once the call
    stops, no task enters, and stopping waits for every task that entered.
    This covers a task whose future the driver never held: a caller's
    deadline, raised in the driving thread as Prefect raises it, can arrive
    inside ``submit`` after the pool queued the task.
    """

    def __init__(self) -> None:
        """Start with the call going on and no task running."""
        self._condition = threading.Condition()
        self._stopped = False
        self._running = 0

    def run(
        self,
        function: Callable[[Input], Output],
        batch: Input,
        retry_limit: int,
    ) -> Output:
        """Run one task, unless its call has stopped."""
        with self._condition:
            if self._stopped:
                raise CancelledError
            self._running += 1
        try:
            return call_with_retries(function, batch, retry_limit=retry_limit)
        finally:
            with self._condition:
                self._running -= 1
                self._condition.notify_all()

    def stop(self) -> None:
        """Start no more tasks, and return once none is running."""
        with self._condition:
            self._stopped = True
            self._condition.wait_for(lambda: self._running == 0)


class ThreadExecutor:
    """Run bounded batches on one persistent caller-owned thread pool.

    The pool exists for the lifetime of this executor, so tasks never create
    a nested pool and no stage starts threads of its own. Batches are
    submitted in input order within a bounded window and consumed in that
    same order, which keeps results, reductions and the propagated failure
    identical to the serial reference.
    """

    def __init__(
        self,
        thread_count: int,
        *,
        memory_bytes_per_worker: int | None = None,
        retry_limit: int = 0,
    ) -> None:
        """Create one pool the caller owns for the whole run."""
        self._capacity = ExecutorCapacity(
            worker_count=1,
            threads_per_worker=thread_count,
            maximum_tasks_in_flight=thread_count,
            memory_bytes_per_worker=memory_bytes_per_worker,
        )
        if retry_limit < 0:
            raise ValueError("retry_limit must not be negative")
        self._retry_limit = retry_limit
        self._pool = ThreadPoolExecutor(
            max_workers=self._capacity.threads_per_worker,
            thread_name_prefix="hebog-executor",
        )

    def __enter__(self) -> ThreadExecutor:
        """Return this executor for use inside a caller-owned scope."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the pool the caller opened."""
        del exception_type, exception, traceback
        self.close()

    def close(self) -> None:
        """Release the pool and abandon work that has not started."""
        self._pool.shutdown(wait=True, cancel_futures=True)

    @property
    def capacity(self) -> ExecutorCapacity:
        """Return the execution budget admitted by the caller."""
        return self._capacity

    def _results(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        requirement: TaskRequirement | None,
    ) -> Generator[Output]:
        """Yield results in input order from a bounded submission window."""
        self._capacity.admit(requirement)
        prepared = require_serializable_payloads(function, batches)
        limit = admitted_tasks_in_flight(self._capacity, requirement)
        guard = _CallGuard()
        pending: deque[Future[Output]] = deque()
        submitted = 0
        try:
            while True:
                while len(pending) < limit and submitted < len(prepared):
                    pending.append(
                        self._pool.submit(
                            guard.run,
                            function,
                            prepared[submitted],
                            self._retry_limit,
                        )
                    )
                    submitted += 1
                if not pending:
                    return
                yield pending.popleft().result()
        finally:
            # A failure, an abandoned reduction or the caller's deadline
            # cancels the batches that have not started, rather than running
            # work whose result nobody will read, and waits for those that
            # have: a task still running after the call returns could write
            # into storage its caller is already removing.
            for future in pending:
                future.cancel()
            guard.stop()

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[Output]:
        """Apply ``function`` to each batch and return ordered results."""
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
        # Closing settles the running batches when ``combine`` fails, rather
        # than whenever the suspended generator is collected.
        with closing(self._results(function, batches, requirement)) as results:
            return reduce_in_canonical_order(results, combine)
