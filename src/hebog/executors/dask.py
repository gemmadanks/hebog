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
        # Distributed's annotations leave parts of these generic methods
        # unknown; the executor protocol and cast preserve our typed boundary.
        futures = self.client.map(  # pyright: ignore[reportUnknownMemberType]
            function,
            list(batches),
            pure=False,
        )
        gather = cast(
            Callable[[object], object],
            self.client.gather,  # pyright: ignore[reportUnknownMemberType]
        )
        gathered = gather(futures)
        return cast(list[Output], gathered)
