"""Compare every task's traced working set with the memory it declares.

Each round of a public run declares the memory its tasks hold, as a
``TaskRequirement`` (``hebog.stages.task_memory``), and
``hebog.analysis_memory_bytes`` states what the analysis itself holds in the
process that runs it. ``scripts/benchmark/audit_task_memory.py`` runs one
serial analysis under :class:`TaskMemoryAuditExecutor` and records, for every
round, its largest traced task peak beside its declaration, and the
analysis's largest traced peak between tasks beside the statement for the
sources it published.

A round's *load* is its peak over its declaration and must stay at most one.
A cost measured on an anchor and declared with a quarter of headroom reads at
most 0.8 there, so a load near one on a new input says the round's cost needs
measuring again. Tracing must be running before the analysis starts.
"""

from __future__ import annotations

import tracemalloc
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, TypeVar

from hebog import analysis_memory_bytes
from hebog.executors import SerialExecutor, TaskRequirement

Input = TypeVar("Input")
Output = TypeVar("Output")


def round_name(function: Callable[..., Any]) -> str:
    """Name a round by the module and function its tasks run.

    Examples:
        >>> round_name(round_name)
        'task_memory_audit:round_name'
    """
    task = getattr(function, "func", function)
    module = str(getattr(task, "__module__", "")).rsplit(".", 1)[-1]
    return f"{module}:{getattr(task, '__qualname__', repr(task))}"


@dataclass(slots=True)
class RoundAudit:
    """Every task one round ran, its largest peak and its declaration."""

    task_count: int = 0
    largest_task_peak_bytes: int = 0
    declared_bytes: int | None = None

    @property
    def load(self) -> float | None:
        """Return the largest peak over the declaration, if one was made."""
        if self.declared_bytes is None:
            return None
        return self.largest_task_peak_bytes / self.declared_bytes


class TaskMemoryAuditExecutor(SerialExecutor):
    """The serial reference, tracing each task apart from the analysis.

    Each batch runs as its own call, so ``tracemalloc``'s peak above what the
    run held when the task began is that task's working set, and the peak
    between two tasks is what the analysis holds there.
    """

    def __init__(self) -> None:
        """Start with no round observed."""
        super().__init__()
        self.rounds: dict[str, RoundAudit] = {}
        self.analysis_peak_bytes = 0

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[Output]:
        """Run each batch alone, recording its peak beside the declaration.

        Raises:
            RuntimeError: If ``tracemalloc`` is not tracing.
        """
        if not tracemalloc.is_tracing():
            raise RuntimeError(
                "a memory audit needs tracemalloc to be tracing"
            )
        audit = self.rounds.setdefault(round_name(function), RoundAudit())
        if requirement is not None:
            audit.declared_bytes = max(
                audit.declared_bytes or 0, requirement.memory_bytes
            )
        results: list[Output] = []
        for batch in batches:
            self.record_analysis_peak()
            held, _ = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            results += super().map_batches(
                function, [batch], requirement=requirement
            )
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            audit.task_count += 1
            audit.largest_task_peak_bytes = max(
                audit.largest_task_peak_bytes, peak - held
            )
        return results

    def record_analysis_peak(self) -> None:
        """Fold in the analysis's peak since the last task ended.

        Call it once more after the analysis returns, so the work after its
        last task is counted.
        """
        _, peak = tracemalloc.get_traced_memory()
        self.analysis_peak_bytes = max(self.analysis_peak_bytes, peak)


def audit_document(
    executor: TaskMemoryAuditExecutor,
    *,
    image_shape_yx: tuple[int, int],
    source_count: int,
) -> dict[str, Any]:
    """Return one JSON-serializable audit, the most loaded round first.

    The analysis is compared with the reservation for the sources it
    published, as a caller that expected exactly those would have made.
    """
    stated = analysis_memory_bytes(
        image_shape_yx, expected_sources=source_count
    )
    # An undeclared round is the worst finding, so it sorts first.
    rounds = sorted(
        executor.rounds.items(),
        key=lambda item: (
            -float("inf") if item[1].load is None else -item[1].load,
            item[0],
        ),
    )
    return {
        "analysis": {
            "peak_bytes": executor.analysis_peak_bytes,
            "stated_bytes": stated,
            "load": executor.analysis_peak_bytes / stated,
        },
        "undeclared_rounds": [
            name for name, audit in rounds if audit.declared_bytes is None
        ],
        "largest_round_load": max(
            (audit.load for _, audit in rounds if audit.load is not None),
            default=None,
        ),
        "rounds": [
            {
                "round": name,
                "task_count": audit.task_count,
                "largest_task_peak_bytes": audit.largest_task_peak_bytes,
                "declared_bytes": audit.declared_bytes,
                "load": audit.load,
            }
            for name, audit in rounds
        ],
    }
