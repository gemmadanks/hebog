"""Deterministic reference executor."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

Input = TypeVar("Input")
Output = TypeVar("Output")


class SerialExecutor:
    """Run batches serially for testing and scientific reference results."""

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
    ) -> list[Output]:
        """Apply ``function`` to each batch in input order."""
        return [function(batch) for batch in batches]
