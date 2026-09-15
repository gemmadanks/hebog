# pyright: reportUnknownMemberType=false
"""Saved external finder result records and reproducible identity hashes.

Synthetic comparison campaigns store one ``result.json`` per finder run. The
comparison notebook reads those records; the hashing helpers identify source
trees and configurations for new comparison runs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

_SHA256_PATTERN = r"^[0-9a-f]{64}$"

ExternalFinderId = Literal[
    "hebog",
    "released-pybdsf",
    "pinned-pybdsf-master",
    "aegean",
]
ExternalRunMode = Literal["candidate", "operational", "controlled-background"]


class _ExternalRunModel(BaseModel):
    """Strict immutable base for unopened finder output records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ExternalRunArtifact(_ExternalRunModel):
    """One native or normalized product emitted by an isolated finder."""

    role: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    relative_path: str = Field(min_length=1)
    byte_count: int = Field(gt=0)
    sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        """Keep every emitted artifact within its result directory."""
        path = PurePosixPath(self.relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("external run artifact path must stay relative")
        if self.relative_path == "result.json":
            raise ValueError("result manifest cannot list itself")
        return self


class ExternalRunFailure(_ExternalRunModel):
    """One retained finder failure with a stable execution stage."""

    stage: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    exception_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    traceback: str = Field(min_length=1)


class ExternalRuntimeIdentity(_ExternalRunModel):
    """Exact isolated software and environment bound to one result."""

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    artifact_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    container_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dependency_inventory_sha256: str = Field(pattern=_SHA256_PATTERN)


class ExternalRunResult(_ExternalRunModel):
    """Raw one-realization record written before scientific evaluation."""

    schema_version: Literal[1]
    protocol_sha256: str = Field(pattern=_SHA256_PATTERN)
    execution_decision_sha256: str = Field(pattern=_SHA256_PATTERN)
    input_bundle_sha256: str = Field(pattern=_SHA256_PATTERN)
    dataset_identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    seed: int = Field(ge=0)
    finder_id: ExternalFinderId
    mode: ExternalRunMode
    runtime: ExternalRuntimeIdentity
    configuration_sha256: str = Field(pattern=_SHA256_PATTERN)
    status: Literal["success", "failure"]
    wall_seconds: float = Field(ge=0, allow_inf_nan=False)
    artifacts: tuple[ExternalRunArtifact, ...]
    failure: ExternalRunFailure | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        """Keep success products and retained failures unambiguous."""
        if tuple(item.role for item in self.artifacts) != tuple(
            sorted(item.role for item in self.artifacts)
        ):
            raise ValueError("external run artifacts must be role-sorted")
        if len({item.role for item in self.artifacts}) != len(self.artifacts):
            raise ValueError("external run artifact roles must be unique")
        if self.status == "success" and (
            self.failure is not None or not self.artifacts
        ):
            raise ValueError("successful external run requires artifacts")
        if self.status == "failure" and self.failure is None:
            raise ValueError("failed external run requires failure details")
        return self

    def canonical_json_bytes(self) -> bytes:
        """Serialize one raw run manifest deterministically."""
        document = json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        return f"{document}\n".encode()


def file_sha256(path: Path) -> str:
    """Hash one file without retaining it in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    """Hash a JSON-compatible configuration without path formatting drift."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def source_tree_sha256(repository_root: Path) -> str:
    """Hash every production Python source used by the isolated runners."""
    digest = hashlib.sha256()
    source_root = repository_root / "src" / "hebog"
    for path in sorted(source_root.rglob("*.py")):
        digest.update(path.relative_to(repository_root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_external_run_result(
    path: Path,
    *,
    verify_artifacts: bool = True,
) -> ExternalRunResult:
    """Load one raw result and optionally verify every output byte."""
    payload = path.read_bytes()
    result = ExternalRunResult.model_validate_json(payload)
    if payload != result.canonical_json_bytes():
        raise ValueError("external run manifest is not canonical JSON")
    if verify_artifacts:
        root = path.parent.resolve()
        for artifact in result.artifacts:
            artifact_path = root / artifact.relative_path
            if not artifact_path.resolve().is_relative_to(root):
                raise ValueError("external run artifact escapes result root")
            if artifact_path.stat().st_size != artifact.byte_count:
                raise ValueError("external run artifact byte count changed")
            if file_sha256(artifact_path) != artifact.sha256:
                raise ValueError("external run artifact checksum changed")
    return result
