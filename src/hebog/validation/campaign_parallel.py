"""Bounded resource lanes for governed external-campaign execution."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, create_model


class FinderRun(Protocol):
    """Minimum run identity required for resource partitioning."""

    @property
    def finder_id(self) -> str:
        """Return the governed finder identity."""
        ...


RunT = TypeVar("RunT", bound=FinderRun)
ItemT = TypeVar("ItemT")

_PYBDSF_FINDERS = frozenset({"released-pybdsf", "pinned-pybdsf-master"})


def finder_resource_lanes(
    runs: Sequence[RunT],
) -> tuple[tuple[RunT, ...], tuple[RunT, ...]]:
    """Partition ordered runs into one PyBDSF and one companion lane.

    Every four-core PyBDSF invocation remains serial. Hebog and Aegean use a
    separate serial lane, allowing the two independent resource classes to
    overlap without running two PyBDSF containers concurrently.
    """
    pybdsf = tuple(item for item in runs if item.finder_id in _PYBDSF_FINDERS)
    companion = tuple(
        item for item in runs if item.finder_id not in _PYBDSF_FINDERS
    )
    return pybdsf, companion


def run_parallel_lanes(
    lanes: Sequence[Sequence[ItemT]],
    execute: Callable[[ItemT], None],
    *,
    on_complete: Callable[[int], None] | None = None,
) -> int:
    """Execute independent ordered lanes with fail-closed cancellation.

    The first failure prevents either lane from starting another item. A task
    already executing in the other lane is allowed to finish, leaving only
    complete resumable products in private staging.
    """
    active_lanes = tuple(tuple(lane) for lane in lanes if lane)
    if not active_lanes:
        return 0
    stop = Event()
    counter_lock = Lock()
    completed = 0

    def consume(lane: tuple[ItemT, ...]) -> None:
        nonlocal completed
        for item in lane:
            if stop.is_set():
                return
            try:
                execute(item)
                with counter_lock:
                    completed += 1
                    current = completed
                    if on_complete is not None:
                        on_complete(current)
            except BaseException:
                stop.set()
                raise

    with ThreadPoolExecutor(
        max_workers=len(active_lanes),
        thread_name_prefix="hebog-campaign",
    ) as executor:
        futures = tuple(
            executor.submit(consume, lane) for lane in active_lanes
        )
        for future in futures:
            future.result()
    return completed


def concurrent_campaign_request_model(
    historical_model: type[BaseModel],
) -> type[BaseModel]:
    """Extend one frozen request model with the reviewed two-lane bound."""
    return create_model(
        f"Concurrent{historical_model.__name__}",
        __base__=historical_model,
        execution_concurrency=(Literal[2], ...),
    )
