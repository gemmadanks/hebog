"""Versioned evidence for warm one-tile framework overhead measurements."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_COMMIT_PATTERN = r"^[0-9a-f]{40}$"

OverheadOperation: TypeAlias = Literal[
    "configuration",
    "fits-io",
    "partition-planning",
    "serial-dispatch",
    "local-dispatch",
    "dask-dispatch",
]


class _OverheadModel(BaseModel):
    """Strict immutable base for overhead evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class OverheadStatistics(_OverheadModel):
    """Repeated warm timings for one isolated framework operation."""

    operation: OverheadOperation
    method: str = Field(min_length=1)
    warmup_repetitions: int = Field(ge=1)
    measured_repetitions: int = Field(ge=5)
    minimum_seconds: float = Field(ge=0, allow_inf_nan=False)
    median_seconds: float = Field(ge=0, allow_inf_nan=False)
    percentile_95_seconds: float = Field(ge=0, allow_inf_nan=False)
    maximum_seconds: float = Field(ge=0, allow_inf_nan=False)
    budget_seconds: float = Field(gt=0, allow_inf_nan=False)
    within_budget: bool

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        """Require ordered statistics and a truthful budget result."""
        if not (
            self.minimum_seconds
            <= self.median_seconds
            <= self.percentile_95_seconds
            <= self.maximum_seconds
        ):
            raise ValueError("overhead statistics are not ordered")
        if self.within_budget != (
            self.percentile_95_seconds <= self.budget_seconds
        ):
            raise ValueError(
                "within_budget does not match the 95th percentile"
            )
        return self


class OverheadEnvironment(_OverheadModel):
    """Exact local environment used for an exploratory overhead probe."""

    python: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    machine: str = Field(min_length=1)
    cpu_count: int | None = Field(ge=1)
    node_memory_bytes: int = Field(ge=1)
    dependency_versions: dict[str, str]


class OverheadEvidence(_OverheadModel):
    """Complete warm one-tile overhead observation."""

    schema_version: Literal[1]
    status: Literal["exploratory"]
    captured_at: datetime
    source_commit: str = Field(pattern=_COMMIT_PATTERN)
    dataset_identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    dataset_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    shape_yx: tuple[int, int]
    performance_contract_sha256: str = Field(pattern=_SHA256_PATTERN)
    environment_sha256: str = Field(pattern=_SHA256_PATTERN)
    environment: OverheadEnvironment
    measurements: tuple[OverheadStatistics, ...]

    @model_validator(mode="after")
    def validate_document(self) -> Self:
        """Require timezone, geometry, and all six unique operations."""
        if (
            self.captured_at.tzinfo is None
            or self.captured_at.utcoffset() is None
        ):
            raise ValueError("captured_at must include a timezone")
        if any(dimension <= 0 for dimension in self.shape_yx):
            raise ValueError("shape_yx dimensions must be positive")
        operations = [item.operation for item in self.measurements]
        if len(set(operations)) != len(operations):
            raise ValueError("overhead operations must be unique")
        if set(operations) != {
            "configuration",
            "fits-io",
            "partition-planning",
            "serial-dispatch",
            "local-dispatch",
            "dask-dispatch",
        }:
            raise ValueError("overhead evidence requires all six operations")
        return self


def write_overhead_evidence(path: Path, evidence: OverheadEvidence) -> None:
    """Atomically write deterministic overhead evidence."""
    payload = (
        json.dumps(
            evidence.model_dump(mode="json"),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(payload, encoding="utf-8")
    temporary_path.replace(path)


def load_overhead_evidence(path: Path) -> OverheadEvidence:
    """Load and validate one overhead-evidence document."""
    return OverheadEvidence.model_validate_json(
        path.read_text(encoding="utf-8")
    )
