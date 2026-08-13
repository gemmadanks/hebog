"""Tests for bounded external-campaign execution concurrency."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Barrier, Lock
from time import sleep
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from hebog.validation.campaign_parallel import (
    concurrent_campaign_request_model,
    finder_resource_lanes,
    run_parallel_lanes,
)


@dataclass(frozen=True, slots=True)
class _Run:
    identifier: str
    finder_id: str


def test_resource_lanes_keep_all_pybdsf_runs_serial() -> None:
    """Four-core PyBDSF legs share one lane; other finders share another."""
    runs = (
        _Run("hebog-1", "hebog"),
        _Run("release-1", "released-pybdsf"),
        _Run("aegean-1", "aegean"),
        _Run("master-1", "pinned-pybdsf-master"),
        _Run("hebog-2", "hebog"),
        _Run("release-2", "released-pybdsf"),
    )

    pybdsf, companion = finder_resource_lanes(runs)

    assert tuple(item.identifier for item in pybdsf) == (
        "release-1",
        "master-1",
        "release-2",
    )
    assert tuple(item.identifier for item in companion) == (
        "hebog-1",
        "aegean-1",
        "hebog-2",
    )


def test_parallel_lanes_accept_no_work() -> None:
    """An empty resumable campaign performs no execution or progress I/O."""
    assert run_parallel_lanes(((), ()), lambda _item: None) == 0


def test_parallel_lanes_overlap_but_preserve_lane_order() -> None:
    """Only independent lanes overlap; each resource lane remains ordered."""
    barrier = Barrier(2)
    lock = Lock()
    completed: list[str] = []

    def execute(item: str) -> None:
        if item.endswith("1"):
            barrier.wait(timeout=2.0)
        with lock:
            completed.append(item)

    count = run_parallel_lanes(
        (("pybdsf-1", "pybdsf-2"), ("companion-1", "companion-2")),
        execute,
    )

    assert count == 4
    assert completed.index("pybdsf-1") < completed.index("pybdsf-2")
    assert completed.index("companion-1") < completed.index("companion-2")


def test_parallel_lane_failure_stops_queued_work() -> None:
    """An infrastructure failure prevents either lane starting more work."""
    barrier = Barrier(2)
    lock = Lock()
    started: list[str] = []

    def execute(item: str) -> None:
        with lock:
            started.append(item)
        if item.endswith("1"):
            barrier.wait(timeout=2.0)
        if item == "pybdsf-1":
            raise RuntimeError("container failed")
        if item == "companion-1":
            sleep(0.05)

    with pytest.raises(RuntimeError, match="container failed"):
        run_parallel_lanes(
            (
                ("pybdsf-1", "pybdsf-2"),
                ("companion-1", "companion-2"),
            ),
            execute,
        )

    assert "pybdsf-2" not in started
    assert "companion-2" not in started


def test_progress_failure_stops_queued_work() -> None:
    """A failed progress sink stops both resource lanes fail-closed."""
    barrier = Barrier(2)
    lock = Lock()
    started: list[str] = []
    progress_calls = 0

    def execute(item: str) -> None:
        with lock:
            started.append(item)
        if item.endswith("1"):
            barrier.wait(timeout=2.0)
            sleep(0.05)

    def on_complete(_completed: int) -> None:
        nonlocal progress_calls
        with lock:
            progress_calls += 1
            if progress_calls == 1:
                raise RuntimeError("progress store failed")

    with pytest.raises(RuntimeError, match="progress store failed"):
        run_parallel_lanes(
            (("pybdsf-1", "pybdsf-2"), ("companion-1", "companion-2")),
            execute,
            on_complete=on_complete,
        )

    assert "pybdsf-2" not in started
    assert "companion-2" not in started


def test_concurrent_request_model_records_two_lane_execution() -> None:
    """The new request schema accepts the reviewed bound and rejects drift."""

    class HistoricalRequest(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        execution_concurrency: Literal[1]
        identity: str

    request_type = concurrent_campaign_request_model(HistoricalRequest)

    request = request_type.model_validate(
        {"execution_concurrency": 2, "identity": "campaign"}
    )
    assert request.model_dump()["execution_concurrency"] == 2
    for invalid in (1, 3):
        with pytest.raises(ValidationError, match="execution_concurrency"):
            request_type.model_validate(
                {"execution_concurrency": invalid, "identity": "campaign"}
            )
