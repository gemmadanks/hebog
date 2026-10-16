"""Time every executor task where it runs, with the Zarr chunks it moves.

The complete-execution profile times stages in the driver.
:class:`RecordingExecutor` wraps the executor a run is given and sends each
task to it inside a :class:`TimedTask`, which reads the wall clock
(``time.time``) where the task runs: inline under the serial reference, on
a pool thread, or in a Dask worker process. Every process on one host reads
the same clock, so each task's interval can be set beside the driver's stage
calls whichever executor ran it, and no scheduler's own task records are
needed.

Each task also counts the Zarr chunks it reads, with their decoded bytes,
and the chunks it writes; the store is not sharded, so each written chunk is
one chunk file. The counters wrap two ``ZarrProductSink`` methods once per
process: the check every chunk read passes through, and ``write_chunk``.
Counts are kept per thread, so concurrent tasks on a thread pool count only
their own chunks, and I/O on a thread outside any task, which is the
driver's, is kept as timestamped events (:func:`drain_driver_zarr_io`).
Wrapping replaces class attributes in the measuring process only; no Hebog
code changes, and nothing here runs at import.
"""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import numpy as np

from hebog.executors import Executor, ExecutorCapacity, TaskRequirement
from hebog.io import ZarrProductSink
from hebog.validation.task_memory_audit import round_name

Input = TypeVar("Input")
Output = TypeVar("Output")


@dataclass(frozen=True, slots=True)
class ZarrIO:
    """Zarr chunks read, their decoded bytes, and chunks written."""

    read_chunks: int = 0
    read_bytes: int = 0
    written_chunks: int = 0

    def __add__(self, other: ZarrIO) -> ZarrIO:
        """Return the field-by-field sum."""
        return ZarrIO(
            self.read_chunks + other.read_chunks,
            self.read_bytes + other.read_bytes,
            self.written_chunks + other.written_chunks,
        )


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """One task's round, wall-clock interval, declaration and Zarr I/O.

    ``start`` and ``stop`` are ``time.time`` seconds read where the task ran;
    ``declared_bytes`` is the memory its round declared, if it declared any.
    """

    round: str
    start: float
    stop: float
    declared_bytes: int | None
    io: ZarrIO


class _Counts(threading.local):
    """The current thread's running task count, or none outside a task."""

    task: ZarrIO | None = None


_COUNTS = _Counts()
_DRIVER_IO: list[tuple[float, ZarrIO]] = []
_DRIVER_IO_LOCK = threading.Lock()
_INSTALL_LOCK = threading.Lock()
_installed = False


def _count(io: ZarrIO) -> None:
    """Add I/O to the running task's count, or record it as the driver's."""
    if _COUNTS.task is not None:
        _COUNTS.task += io
        return
    with _DRIVER_IO_LOCK:
        _DRIVER_IO.append((time.time(), io))


def install_zarr_io_counters() -> None:
    """Count this process's Zarr chunk reads and writes, once.

    Every chunk a sink reads, whether one tile or a row block of them,
    passes its own ``_require_values_match_record`` check, so wrapping that
    check counts each chunk read once with its decoded bytes.
    """
    global _installed  # noqa: PLW0603 one installation per process
    with _INSTALL_LOCK:
        if _installed:
            return
        check = ZarrProductSink._require_values_match_record  # pyright: ignore[reportPrivateUsage]
        write = ZarrProductSink.write_chunk

        @functools.wraps(check)
        def counted_check(values: Any, record: Any) -> Any:
            checked = check(values, record)
            _count(ZarrIO(read_chunks=1, read_bytes=int(checked.nbytes)))
            return checked

        @functools.wraps(write)
        def counted_write(sink: ZarrProductSink, **arguments: Any) -> Any:
            written = write(sink, **arguments)
            _count(ZarrIO(written_chunks=1))
            return written

        ZarrProductSink._require_values_match_record = staticmethod(  # pyright: ignore[reportAttributeAccessIssue, reportPrivateUsage]
            counted_check
        )
        ZarrProductSink.write_chunk = counted_write  # pyright: ignore[reportAttributeAccessIssue]
        _installed = True


def drain_driver_zarr_io() -> tuple[tuple[float, ZarrIO], ...]:
    """Return and forget this process's Zarr I/O outside any task.

    Each event is the ``time.time`` it ended and what it moved.
    """
    with _DRIVER_IO_LOCK:
        events = tuple(_DRIVER_IO)
        _DRIVER_IO.clear()
    return events


@dataclass(frozen=True, slots=True)
class TimedTask(Generic[Input, Output]):
    """One round's function, timed and counted where it runs.

    It is sent to the executor in place of the function, so it must cross
    a process boundary as the function does; a Dask worker installs its own
    counters on its first task.
    """

    function: Callable[[Input], Output]

    def __call__(self, batch: Input) -> tuple[Output, float, float, ZarrIO]:
        """Run the function once and return its output and measurements.

        Returns:
            The output, the ``time.time`` the task started and stopped, and
            the Zarr I/O it did on its own thread.
        """
        install_zarr_io_counters()
        enclosing = _COUNTS.task
        _COUNTS.task = ZarrIO()
        start = time.time()
        try:
            output = self.function(batch)
            stop = time.time()
            io = _COUNTS.task
        finally:
            _COUNTS.task = enclosing
        return output, start, stop, io


class RecordingExecutor:
    """Record every task another executor runs, leaving its results alone.

    The wrapped executor keeps its admission, ordering, retry and failure
    contract; only its tasks change, each returning its measurements beside
    its output. Records are kept in input order, round by round, for the
    rounds that complete.
    """

    def __init__(self, executor: Executor) -> None:
        """Wrap one executor the caller owns and count this process's I/O."""
        install_zarr_io_counters()
        self._executor = executor
        self.tasks: list[TaskRecord] = []

    @property
    def capacity(self) -> ExecutorCapacity:
        """Return the wrapped executor's budget."""
        return self._executor.capacity

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[Output]:
        """Run the batches on the wrapped executor, recording each task."""
        measured = self._executor.map_batches(
            TimedTask(function), batches, requirement=requirement
        )
        name = round_name(function)
        declared = None if requirement is None else requirement.memory_bytes
        outputs: list[Output] = []
        for output, start, stop, io in measured:
            self.tasks.append(TaskRecord(name, start, stop, declared, io))
            outputs.append(output)
        return outputs


def zarr_io_by_stage(
    stage_intervals: Mapping[tuple[str, ...], Sequence[tuple[float, float]]],
    tasks: Sequence[TaskRecord],
    driver_io: Sequence[tuple[float, ZarrIO]],
) -> dict[tuple[str, ...], ZarrIO]:
    """Attribute task and driver Zarr I/O to the stages that held it.

    A task's I/O counts in every stage one of whose calls holds the task's
    start, as its task count does, and a driver event in every stage one of
    whose calls holds its instant; a call holds both of its ends. Nested
    stages are counted independently, so a parent includes its children.
    """
    events = [(task.start, task.io) for task in tasks] + list(driver_io)
    instants = np.array([instant for instant, _ in events], float)
    totals: dict[tuple[str, ...], ZarrIO] = {}
    for stage, calls in sorted(stage_intervals.items()):
        held = np.zeros(instants.size, bool)
        for start, stop in calls:
            held |= (instants >= start) & (instants <= stop)
        totals[stage] = sum(
            (
                io
                for (_, io), inside in zip(events, held, strict=True)
                if inside
            ),
            ZarrIO(),
        )
    return totals
