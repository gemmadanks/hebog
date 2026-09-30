"""Attribute a serial run's traced peak to its passes, tasks and call sites.

``scripts/benchmark/attribute_traced_peak.py`` is the runner. It is a
diagnostic beside ``just traced-peak``, not a replacement: the gate figure
comes only from that harness, whose worker imports nothing but the public
API. Here the process also holds this module, the wrappers and their
records, which the peaks include.

``tracemalloc`` keeps one process-wide peak, so nested calls share it: each
measured call saves its caller's peak so far, resets it, and folds its own
peak back in when it ends, which gives every call and its callers their
inclusive peaks. In a serial run every executor task is a call in this
process, so a task's peak splits into what was already held when it began,
its *entry*, and what the task itself allocated on top. The largest entry
of a chosen pass is where what the run holds between tasks is greatest, and
a snapshot there names the call sites that hold it.
"""

from __future__ import annotations

import functools
import inspect
import sys
import tracemalloc
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

TASK_PREFIX = "task "
"""The name prefix of a call that is one executor task.

A task begins between other tasks, so what the run holds at its start is
what the pass keeps across tiles rather than any tile's working set.
"""


@dataclass(slots=True)
class _Frame:
    """One measured call still running."""

    entry_bytes: int
    peak_bytes: int


@dataclass(slots=True)
class SpanTotals:
    """Every call of one measured path, and its largest peak."""

    calls: int = 0
    peak_bytes: int = 0
    entry_at_peak_bytes: int = 0
    largest_entry_bytes: int = 0
    largest_own_bytes: int = 0

    def document(self) -> dict[str, int]:
        """Return one JSON-serializable record."""
        return {
            "calls": self.calls,
            "peak_bytes": self.peak_bytes,
            "entry_at_peak_bytes": self.entry_at_peak_bytes,
            "largest_entry_bytes": self.largest_entry_bytes,
            "largest_own_bytes": self.largest_own_bytes,
        }


@dataclass(slots=True)
class TracedPeakTracker:
    """Record ``tracemalloc``'s inclusive peak inside nested calls.

    Calls are grouped by their path of enclosing names, so a task is kept
    apart from the pass that ran it. For each path the tracker keeps its
    largest peak and what was held when that call began, the largest entry
    of any call, and the most any call allocated on top of its entry.

    ``snapshot_within`` names a call: whenever an executor task, a call
    named ``task …``, nested at any depth inside one of that name begins
    holding more than any earlier such task did, a snapshot is taken
    and reduced at once to its ``site_limit`` largest call sites, so the
    last reduction shows what was held at that call's largest entry. A
    snapshot is itself traced memory, so it is never kept, and the peak is
    reset after it so that no measured peak includes it. Tracing must
    already be running.
    """

    snapshot_within: str | None = None
    site_limit: int = 40
    site_frames: int = 3
    totals: dict[tuple[str, ...], SpanTotals] = field(
        default_factory=dict[tuple[str, ...], SpanTotals]
    )
    sites_at_largest_entry: list[dict[str, Any]] = field(
        default_factory=list[dict[str, Any]]
    )
    largest_entry_path: tuple[str, ...] | None = None
    largest_entry_bytes: int = 0
    _path: tuple[str, ...] = ()
    _stack: list[_Frame] = field(default_factory=list[_Frame])

    @contextmanager
    def span(self, name: str) -> Generator[None]:
        """Measure one call of ``name`` under the active call.

        Raises:
            RuntimeError: If ``tracemalloc`` is not tracing.
        """
        if not tracemalloc.is_tracing():
            raise RuntimeError("attribution needs tracemalloc to be tracing")
        current, peak = tracemalloc.get_traced_memory()
        if self._stack:
            self._stack[-1].peak_bytes = max(self._stack[-1].peak_bytes, peak)
        parent = self._path
        path = (*parent, name)
        self._take_snapshot_if_largest(path, current)
        tracemalloc.reset_peak()
        frame = _Frame(entry_bytes=current, peak_bytes=current)
        self._stack.append(frame)
        self._path = path
        try:
            yield
        finally:
            _, peak = tracemalloc.get_traced_memory()
            self._stack.pop()
            self._path = parent
            frame.peak_bytes = max(frame.peak_bytes, peak)
            totals = self.totals.setdefault(path, SpanTotals())
            totals.calls += 1
            if frame.peak_bytes > totals.peak_bytes:
                totals.peak_bytes = frame.peak_bytes
                totals.entry_at_peak_bytes = frame.entry_bytes
            totals.largest_entry_bytes = max(
                totals.largest_entry_bytes, frame.entry_bytes
            )
            totals.largest_own_bytes = max(
                totals.largest_own_bytes, frame.peak_bytes - frame.entry_bytes
            )
            if self._stack:
                self._stack[-1].peak_bytes = max(
                    self._stack[-1].peak_bytes, frame.peak_bytes
                )
            tracemalloc.reset_peak()

    def _take_snapshot_if_largest(
        self, path: tuple[str, ...], entry_bytes: int
    ) -> None:
        """Snapshot a call inside the chosen one that begins holding most."""
        if (
            not path[-1].startswith(TASK_PREFIX)
            or self.snapshot_within not in path[:-1]
            or entry_bytes <= self.largest_entry_bytes
        ):
            return
        self.sites_at_largest_entry = top_allocation_sites(
            tracemalloc.take_snapshot(),
            limit=self.site_limit,
            frames=self.site_frames,
        )
        self.largest_entry_path = path
        self.largest_entry_bytes = entry_bytes

    def wrap(self, function: Callable[..., Any], name: str) -> Any:
        """Return ``function`` measured as ``name``."""

        @functools.wraps(function)
        def measured(*args: Any, **kwargs: Any) -> Any:
            with self.span(name):
                return function(*args, **kwargs)

        return measured

    def documents(self) -> list[dict[str, Any]]:
        """Return every path's totals, largest peak first, then by path."""
        return [
            {"path": list(path), **totals.document()}
            for path, totals in sorted(
                self.totals.items(),
                key=lambda item: (-item[1].peak_bytes, item[0]),
            )
        ]


def wrap_module_functions(
    tracker: TracedPeakTracker, module: ModuleType, *, package: str = "hebog"
) -> int:
    """Measure every function a module defines, wherever it is bound.

    A function imported into another module keeps a binding there, and the
    code may call either, so the defining module's binding and every
    binding of the same function in the loaded ``package`` modules are
    replaced, and a call through an alias is measured under the function's
    own name. Returns the number of bindings replaced.
    """
    wrappers = {
        function: tracker.wrap(function, name)
        for name, function in vars(module).items()
        if inspect.isfunction(function)
        and function.__module__ == module.__name__
    }
    scope = [module] + [
        loaded
        for loaded_name, loaded in list(sys.modules.items())
        if loaded is not module
        and (loaded_name == package or loaded_name.startswith(f"{package}."))
    ]
    replaced = 0
    for owner in scope:
        for attribute, value in list(vars(owner).items()):
            if inspect.isfunction(value) and value in wrappers:
                setattr(owner, attribute, wrappers[value])
                replaced += 1
    return replaced


@contextmanager
def serial_tasks_measured(
    tracker: TracedPeakTracker, serial_module: ModuleType
) -> Generator[None]:
    """Measure every serial executor task as a call named by its function.

    The serial executor runs each batch through ``call_with_retries``, so
    replacing that binding measures every task wherever a pass submits it.
    A task is named ``task <function>``, its partial's function if it is
    one, and nests under the pass that submitted it.
    """
    original: Callable[..., Any] = serial_module.call_with_retries

    def measured_call(
        function: Callable[[Any], Any], batch: Any, *, retry_limit: int
    ) -> Any:
        name = getattr(function, "func", function).__name__
        with tracker.span(f"{TASK_PREFIX}{name}"):
            return original(function, batch, retry_limit=retry_limit)

    setattr(serial_module, "call_with_retries", measured_call)  # noqa: B010
    try:
        yield
    finally:
        setattr(serial_module, "call_with_retries", original)  # noqa: B010


def top_allocation_sites(
    snapshot: tracemalloc.Snapshot, *, limit: int, frames: int
) -> list[dict[str, Any]]:
    """Return the call sites holding most traced memory in a snapshot.

    Sites are grouped by their innermost ``frames`` frames inside the
    ``hebog`` package where it has any, so a site names the Hebog code
    that made the allocation rather than the library that performed it.
    A frame is named by its file name alone, whichever separator the
    platform's paths use, so a report carries no machine's directories.
    """
    statistics = snapshot.statistics("traceback")
    sites: dict[tuple[str, ...], list[int]] = {}
    for statistic in statistics:
        named = [
            (frame.filename.replace("\\", "/"), frame.lineno)
            for frame in statistic.traceback
        ]
        in_hebog = [frame for frame in named if "/hebog/" in frame[0]]
        chosen = (in_hebog or named)[-frames:]
        key = tuple(
            f"{filename.rsplit('/', 1)[-1]}:{lineno}"
            for filename, lineno in chosen
        )
        totals = sites.setdefault(key, [0, 0])
        totals[0] += statistic.size
        totals[1] += statistic.count
    return [
        {"site": list(site), "bytes": size, "count": count}
        for site, (size, count) in sorted(
            sites.items(), key=lambda item: -item[1][0]
        )[:limit]
    ]
