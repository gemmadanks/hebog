"""Tests for typed one-tile overhead evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from hebog.validation.overhead import (
    OverheadEnvironment,
    OverheadEvidence,
    OverheadOperation,
    OverheadStatistics,
    load_overhead_evidence,
    write_overhead_evidence,
)


def _statistic(operation: OverheadOperation) -> OverheadStatistics:
    """Return an ordered passing timing summary."""
    return OverheadStatistics(
        operation=operation,
        method="test method",
        warmup_repetitions=1,
        measured_repetitions=5,
        minimum_seconds=0.001,
        median_seconds=0.002,
        percentile_95_seconds=0.003,
        maximum_seconds=0.004,
        budget_seconds=0.01,
        within_budget=True,
    )


def _evidence() -> OverheadEvidence:
    """Return one complete overhead evidence record."""
    environment = OverheadEnvironment(
        python="3.14.0",
        platform="test-platform",
        machine="test-machine",
        cpu_count=8,
        node_memory_bytes=16 * 1024**3,
        dependency_versions={"hebog": "0.1.0"},
    )
    return OverheadEvidence(
        schema_version=1,
        status="exploratory",
        captured_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        source_commit="a" * 40,
        dataset_identifier="compact-reference-256",
        dataset_content_sha256="b" * 64,
        shape_yx=(256, 256),
        performance_contract_sha256="c" * 64,
        environment_sha256="d" * 64,
        environment=environment,
        measurements=tuple(
            _statistic(operation)
            for operation in (
                "configuration",
                "fits-io",
                "partition-planning",
                "serial-dispatch",
                "local-dispatch",
                "dask-dispatch",
            )
        ),
    )


def test_overhead_evidence_round_trips(tmp_path: Path) -> None:
    """All six operations retain their typed, canonical representation."""
    path = tmp_path / "overhead.json"

    write_overhead_evidence(path, _evidence())

    assert load_overhead_evidence(path) == _evidence()
    assert path.read_bytes().endswith(b"\n")


def test_overhead_statistic_rejects_an_incorrect_budget_result() -> None:
    """A failing 95th percentile cannot be labelled within budget."""
    document = _statistic("fits-io").model_dump(mode="json")
    document["percentile_95_seconds"] = 0.02

    with pytest.raises(ValidationError, match="within_budget"):
        OverheadStatistics.model_validate(document)


def test_overhead_evidence_requires_every_operation_once() -> None:
    """A partial probe cannot masquerade as complete Phase 0 evidence."""
    document = _evidence().model_dump(mode="json")
    document["measurements"].pop()

    with pytest.raises(ValidationError, match="all six operations"):
        OverheadEvidence.model_validate(document)
