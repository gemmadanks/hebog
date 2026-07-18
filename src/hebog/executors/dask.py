"""Dask execution using a scheduler client owned by the caller."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeVar, cast

from distributed import Client

Input = TypeVar("Input")
Output = TypeVar("Output")


@dataclass(slots=True)
class DaskExecutor:
    """Submit coarse batches to an existing Dask client."""

    client: Client

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
    ) -> list[Output]:
        """Submit batches and gather their results in input order."""
        futures = self.client.map(function, list(batches), pure=False)
        return cast(list[Output], self.client.gather(futures))
