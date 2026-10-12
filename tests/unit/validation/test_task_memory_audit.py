"""Unit tests for the task memory audit's tracing and its document."""

from __future__ import annotations

import tracemalloc
from collections.abc import Iterator

import pytest

from hebog import analysis_memory_bytes
from hebog.executors import TaskRequirement
from hebog.validation.task_memory_audit import (
    RoundAudit,
    TaskMemoryAuditExecutor,
    audit_document,
    round_name,
)

_MEBIBYTE = 1024 * 1024


def allocate_mebibytes(count: int) -> int:
    """Hold ``count`` mebibytes for the length of one task."""
    held = bytearray(count * _MEBIBYTE)
    return len(held)


@pytest.fixture
def tracing() -> Iterator[None]:
    """Trace allocations for one test, restoring the state it found."""
    already = tracemalloc.is_tracing()
    if not already:
        tracemalloc.start()
    yield
    if not already:
        tracemalloc.stop()


@pytest.mark.usefixtures("tracing")
def test_each_task_is_measured_apart() -> None:
    """A round's peak is its largest task, not the sum of its tasks."""
    executor = TaskMemoryAuditExecutor()

    executor.map_batches(
        allocate_mebibytes,
        [1, 4, 2],
        requirement=TaskRequirement(memory_bytes=8 * _MEBIBYTE),
    )

    audit = executor.rounds["test_task_memory_audit:allocate_mebibytes"]
    assert audit.task_count == 3
    assert 4 * _MEBIBYTE <= audit.largest_task_peak_bytes < 5 * _MEBIBYTE
    assert audit.declared_bytes == 8 * _MEBIBYTE
    assert audit.load is not None and 0.5 <= audit.load < 0.625


@pytest.mark.usefixtures("tracing")
def test_a_task_holding_more_than_declared_reads_a_load_above_one() -> None:
    """An under-declared round is visible in the document."""
    executor = TaskMemoryAuditExecutor()
    executor.map_batches(
        allocate_mebibytes, [2], requirement=TaskRequirement(_MEBIBYTE)
    )

    document = audit_document(
        executor, image_shape_yx=(64, 64), source_count=0
    )

    assert document["largest_round_load"] > 1
    assert document["rounds"][0]["round"].endswith(":allocate_mebibytes")
    assert document["undeclared_rounds"] == []


@pytest.mark.usefixtures("tracing")
def test_an_undeclared_round_is_named() -> None:
    """A round without a requirement has no load and is listed."""
    executor = TaskMemoryAuditExecutor()
    executor.map_batches(allocate_mebibytes, [1])

    document = audit_document(
        executor, image_shape_yx=(64, 64), source_count=0
    )

    assert document["undeclared_rounds"] == [
        "test_task_memory_audit:allocate_mebibytes"
    ]
    assert document["largest_round_load"] is None
    assert document["rounds"][0]["load"] is None


@pytest.mark.usefixtures("tracing")
def test_the_analysis_peak_is_measured_between_tasks() -> None:
    """What the analysis holds while no task runs is its own peak."""
    executor = TaskMemoryAuditExecutor()
    held = bytearray(3 * _MEBIBYTE)
    executor.map_batches(
        allocate_mebibytes, [1], requirement=TaskRequirement(_MEBIBYTE * 8)
    )
    del held
    executor.record_analysis_peak()

    document = audit_document(
        executor, image_shape_yx=(100, 100), source_count=7
    )

    stated = analysis_memory_bytes((100, 100), expected_sources=7)
    assert executor.analysis_peak_bytes >= 3 * _MEBIBYTE
    assert document["analysis"]["stated_bytes"] == stated
    assert document["analysis"]["load"] == pytest.approx(
        executor.analysis_peak_bytes / stated
    )


def test_rounds_are_listed_undeclared_first_then_by_load() -> None:
    """The round that most needs attention leads the document."""
    executor = TaskMemoryAuditExecutor()
    executor.rounds = {
        "a:idle": RoundAudit(1, 0, 100),
        "b:busy": RoundAudit(1, 90, 100),
        "c:undeclared": RoundAudit(1, 10, None),
        "d:light": RoundAudit(1, 10, 100),
    }

    document = audit_document(
        executor, image_shape_yx=(10, 10), source_count=0
    )

    assert [entry["round"] for entry in document["rounds"]] == [
        "c:undeclared",
        "b:busy",
        "d:light",
        "a:idle",
    ]
    assert document["largest_round_load"] == 0.9


def test_an_audit_refuses_to_run_without_tracing() -> None:
    """Without tracing every peak would read zero and pass vacuously."""
    if tracemalloc.is_tracing():
        pytest.skip("this test needs tracing off")

    with pytest.raises(RuntimeError, match="tracemalloc"):
        TaskMemoryAuditExecutor().map_batches(allocate_mebibytes, [1])


def test_a_round_is_named_by_its_module_and_function() -> None:
    """Rounds of one stage stay apart, and a partial names its function."""
    from functools import partial  # noqa: PLC0415

    assert round_name(partial(allocate_mebibytes, 1)) == (
        "test_task_memory_audit:allocate_mebibytes"
    )
    assert RoundAudit().load is None
