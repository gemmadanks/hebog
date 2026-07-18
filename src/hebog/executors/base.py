"""Executor protocol kept independent of Dask implementation details."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, TypeVar

Input = TypeVar("Input")
Output = TypeVar("Output")


class Executor(Protocol):
    """Execute coarse batches without exposing scheduler-specific objects."""

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
    ) -> list[Output]:
        """Apply ``function`` to each batch and return ordered results."""
        ...
