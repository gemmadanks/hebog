# pyright: reportUnknownMemberType=false
"""Fail-closed execution boundary for isolated Phase 5 finder runners."""

from __future__ import annotations

import hashlib
import json
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.contracts import (
    PhaseFiveExternalComparisonProtocol,
    PhaseFiveExternalExecutionDecision,
    load_phase_five_external_comparison_protocol,
    load_phase_five_external_execution_decision,
)
from hebog.validation.materialization import (
    ExternalInputBundle,
    load_external_input_bundle,
)

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_RUNNER_PATHS = {
    "hebog": "scripts/benchmark/run_phase5_external_hebog.py",
    "released-pybdsf": "scripts/benchmark/run_phase5_external_pybdsf.py",
    "pinned-pybdsf-master": (
        "scripts/benchmark/run_phase5_external_pybdsf.py"
    ),
    "aegean": "scripts/benchmark/run_phase5_external_aegean.py",
}

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


@dataclass(frozen=True, slots=True)
class AuthorizedExternalRun:
    """Validated immutable inputs made available to one runner."""

    protocol: PhaseFiveExternalComparisonProtocol
    decision: PhaseFiveExternalExecutionDecision
    input_bundle: ExternalInputBundle
    protocol_path: Path
    decision_path: Path
    input_bundle_path: Path
    protocol_sha256: str
    decision_sha256: str
    input_bundle_sha256: str

    def artifact_path(self, role: Literal["image", "mean", "rms"]) -> Path:
        """Resolve one checksum-verified common input artifact."""
        artifact = next(
            item for item in self.input_bundle.artifacts if item.role == role
        )
        return self.input_bundle_path.parent / artifact.relative_path


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


def authorize_external_run(
    *,
    protocol_path: Path,
    execution_decision_path: Path,
    input_bundle_path: Path,
    runner_path: Path,
    finder_id: ExternalFinderId,
) -> AuthorizedExternalRun:
    """Open no input unless named review binds the exact committed runner."""
    protocol = load_phase_five_external_comparison_protocol(protocol_path)
    decision = load_phase_five_external_execution_decision(
        execution_decision_path
    )
    input_bundle = load_external_input_bundle(
        input_bundle_path,
        verify_artifacts=True,
    )
    protocol_sha256 = file_sha256(protocol_path)
    if decision.protocol_sha256 != protocol_sha256:
        raise ValueError("external execution decision does not bind protocol")
    if input_bundle.protocol_sha256 != protocol_sha256:
        raise ValueError("external input does not bind protocol")
    repository_root = protocol_path.resolve().parents[2]
    expected_runner = _RUNNER_PATHS[finder_id]
    resolved_runner = runner_path.resolve()
    if resolved_runner != (repository_root / expected_runner).resolve():
        raise ValueError("unexpected external runner path")
    artifact = next(
        (
            item
            for item in decision.runners
            if item.relative_path == expected_runner
        ),
        None,
    )
    if artifact is None or artifact.sha256 != file_sha256(resolved_runner):
        raise ValueError("external runner checksum is not authorized")
    if decision.source_tree_sha256 != source_tree_sha256(repository_root):
        raise ValueError("external source tree checksum is not authorized")
    return AuthorizedExternalRun(
        protocol=protocol,
        decision=decision,
        input_bundle=input_bundle,
        protocol_path=protocol_path,
        decision_path=execution_decision_path,
        input_bundle_path=input_bundle_path,
        protocol_sha256=protocol_sha256,
        decision_sha256=file_sha256(execution_decision_path),
        input_bundle_sha256=file_sha256(input_bundle_path),
    )


def _artifact(directory: Path, role: str, path: Path) -> ExternalRunArtifact:
    """Capture one output only when it remains inside the staging root."""
    resolved_directory = directory.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_directory):
        raise ValueError("external output artifact escapes staging directory")
    return ExternalRunArtifact(
        role=role,
        relative_path=resolved_path.relative_to(resolved_directory).as_posix(),
        byte_count=resolved_path.stat().st_size,
        sha256=file_sha256(resolved_path),
    )


def execute_external_run(  # noqa: PLR0913
    authorized: AuthorizedExternalRun,
    *,
    finder_id: ExternalFinderId,
    mode: ExternalRunMode,
    runtime: ExternalRuntimeIdentity,
    configuration: object,
    output_directory: Path,
    operation: Callable[[Path], dict[str, Path]],
    failure_stage: str,
) -> Path:
    """Run once, retain failures, and atomically publish a raw result."""
    if output_directory.exists():
        raise FileExistsError(
            f"refusing to overwrite external result: {output_directory}"
        )
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with TemporaryDirectory(
        prefix=f".{output_directory.name}-",
        dir=output_directory.parent,
    ) as temporary:
        staging = Path(temporary)
        try:
            with TemporaryDirectory(
                prefix="finder-products-",
                dir=staging,
            ) as product_temporary:
                product_staging = Path(product_temporary)
                output_paths = operation(product_staging)
                relative_outputs = {
                    role: path.resolve().relative_to(product_staging.resolve())
                    for role, path in output_paths.items()
                }
                product_root = staging / "artifacts"
                product_staging.rename(product_root)
            artifacts = tuple(
                _artifact(staging, role, product_root / relative_path)
                for role, relative_path in sorted(relative_outputs.items())
            )
            status: Literal["success", "failure"] = "success"
            failure = None
        except Exception as error:  # retained scientific denominator
            status = "failure"
            artifacts = ()
            failure = ExternalRunFailure(
                stage=failure_stage,
                exception_type=type(error).__name__,
                message=str(error) or repr(error),
                traceback=traceback.format_exc(),
            )
        result = ExternalRunResult(
            schema_version=1,
            protocol_sha256=authorized.protocol_sha256,
            execution_decision_sha256=authorized.decision_sha256,
            input_bundle_sha256=authorized.input_bundle_sha256,
            dataset_identifier=(authorized.input_bundle.dataset_identifier),
            seed=authorized.input_bundle.seed,
            finder_id=finder_id,
            mode=mode,
            runtime=runtime,
            configuration_sha256=canonical_sha256(configuration),
            status=status,
            wall_seconds=time.perf_counter() - started,
            artifacts=artifacts,
            failure=failure,
        )
        result_path = staging / "result.json"
        result_path.write_bytes(result.canonical_json_bytes())
        staging.rename(output_directory)
    return output_directory / "result.json"


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
