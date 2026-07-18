"""Validate raw PyBDSF campaigns and compile governed benchmark evidence."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.datasets import DatasetRole
from hebog.validation.evidence import (
    BenchmarkEvidence,
    DatasetIdentity,
    EvidenceStatus,
    ExecutorKind,
    Measurement,
    ResourceAllocation,
    RuntimeMetrics,
    SoftwareIdentity,
    StageMetrics,
    UnavailableMetric,
    WorkloadClass,
)

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_CONTAINER_DIGEST_PATTERN = rf"^sha256:{_SHA256_PATTERN[1:]}"
_COMMIT_PATTERN = r"^[0-9a-f]{40}$"
_SHA256_HEX_LENGTH = 64
_EXPECTED_ARTIFACT_NAMES = {
    "apparent_sky.txt",
    "diagnostics.json",
    "flat_noise_rms.fits",
    "source_catalog.fits",
    "source_filter_mask.fits",
    "true_sky.txt",
    "true_sky_rms.fits",
}


def _canonical_sha256(value: object) -> str:
    """Hash one JSON-compatible value using canonical separators."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    """Hash a file without retaining it in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class _RawModel(BaseModel):
    """Strict immutable base for runner-owned raw records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class _RawArtifact(_RawModel):
    """One output emitted by a raw reference run."""

    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256_PATTERN)


class _RawMetrics(_RawModel):
    """Direct measurements captured around one synchronous call."""

    wall_seconds: float = Field(ge=0, allow_inf_nan=False)
    cpu_seconds: float = Field(ge=0, allow_inf_nan=False)
    peak_rss_bytes: int = Field(ge=0)
    system_seconds: float = Field(ge=0, allow_inf_nan=False)
    user_seconds: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_cpu_total(self) -> Self:
        """Detect a corrupt CPU total while allowing timer rounding."""
        component_total = self.user_seconds + self.system_seconds
        if not math.isclose(
            self.cpu_seconds,
            component_total,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError(
                "cpu_seconds does not equal user plus system time"
            )
        return self


class _RawStage(_RawModel):
    """One instrumented call in a raw run."""

    stage: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    metrics: _RawMetrics


class _RawDataset(_RawModel):
    """Input-plane identity captured inside the reference container."""

    identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    flat_noise_sha256: str = Field(pattern=_SHA256_PATTERN)
    true_sky_sha256: str = Field(pattern=_SHA256_PATTERN)

    @property
    def content_sha256(self) -> str:
        """Return a stable identity for one or two distinct input planes."""
        if self.flat_noise_sha256 == self.true_sky_sha256:
            return self.flat_noise_sha256
        return _canonical_sha256(
            {
                "flat_noise_sha256": self.flat_noise_sha256,
                "true_sky_sha256": self.true_sky_sha256,
            }
        )


class _RawEnvironment(_RawModel):
    """Stable runtime facts reported from the isolated container."""

    cpu_count: int | None = Field(ge=1)
    machine: str = Field(min_length=1)
    node_memory_bytes: int = Field(ge=1)
    platform: str = Field(min_length=1)
    python: str = Field(min_length=1)


class _RawSoftwareIdentity(_RawModel):
    """Software identity emitted by the runner."""

    commit: str = Field(pattern=_COMMIT_PATTERN)
    version: str | None = Field(default=None, min_length=1)


class _RawSoftware(_RawModel):
    """Exact reference and compatibility-layer revisions."""

    bdsf: _RawSoftwareIdentity
    lsmtool: _RawSoftwareIdentity
    rapthor: _RawSoftwareIdentity


class _RawRun(_RawModel):
    """Complete output contract of one isolated runner invocation."""

    schema_version: Literal[1]
    artifacts: dict[str, _RawArtifact]
    captured_at: datetime
    complete: _RawMetrics
    configuration: dict[str, object]
    configuration_sha256: str = Field(pattern=_SHA256_PATTERN)
    container_image_digest: str = Field(pattern=_CONTAINER_DIGEST_PATTERN)
    dataset: _RawDataset
    dependency_inventory: tuple[dict[str, object], ...]
    dependency_inventory_sha256: str = Field(pattern=_SHA256_PATTERN)
    environment: _RawEnvironment
    environment_sha256: str = Field(pattern=_SHA256_PATTERN)
    instrumentation: dict[str, str]
    ncores: int = Field(ge=1)
    reference: Literal["release", "master"]
    repetition_index: int = Field(ge=0)
    software: _RawSoftware
    stages: tuple[_RawStage, ...] = Field(min_length=1)
    warmup: bool

    @model_validator(mode="after")
    def validate_canonical_digests(self) -> Self:
        """Bind captured objects to their declared canonical hashes."""
        if set(self.artifacts) != _EXPECTED_ARTIFACT_NAMES:
            raise ValueError("raw run does not contain the standard products")
        checks = (
            (
                "configuration",
                self.configuration_sha256,
                _canonical_sha256(self.configuration),
            ),
            (
                "dependency inventory",
                self.dependency_inventory_sha256,
                _canonical_sha256(self.dependency_inventory),
            ),
            (
                "environment",
                self.environment_sha256,
                _canonical_sha256(self.environment.model_dump(mode="json")),
            ),
        )
        for name, declared, observed in checks:
            if declared != observed:
                raise ValueError(f"{name} SHA-256 does not match its content")
        return self


class _BaselineIndex(_RawModel):
    """Matched campaign index written after all repetitions pass."""

    schema_version: Literal[1]
    container_image: str = Field(min_length=1)
    container_image_digest: str = Field(pattern=_CONTAINER_DIGEST_PATTERN)
    dataset_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    input_sha256: dict[str, str] = Field(default_factory=dict)
    ncores: int = Field(ge=1)
    reference: Literal["release", "master"]
    repetitions: int = Field(ge=1)
    runs: tuple[str, ...] = Field(min_length=1)
    scientific_identity_normalization: dict[str, str] = Field(
        default_factory=dict
    )
    warmups: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_protocol(self) -> Self:
        """Keep run paths bounded, unique, and consistent with counts."""
        if len(self.runs) != self.warmups + self.repetitions:
            raise ValueError("run count does not match campaign protocol")
        if len(set(self.runs)) != len(self.runs):
            raise ValueError("campaign run paths must be unique")
        for run_path in self.runs:
            path = PurePosixPath(run_path)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("campaign run paths must stay relative")
        for digest in self.input_sha256.values():
            if len(digest) != _SHA256_HEX_LENGTH or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("campaign input SHA-256 is invalid")
        return self


def _load_raw_runs(
    directory: Path, index: _BaselineIndex
) -> tuple[_RawRun, ...]:
    """Load every raw run referenced by a validated campaign index."""
    return tuple(
        _RawRun.model_validate_json(
            (directory / relative_path).read_text(encoding="utf-8")
        )
        for relative_path in index.runs
    )


def _validate_run_identity(
    index: _BaselineIndex,
    first: _RawRun,
    run: _RawRun,
    expected_index: int,
) -> None:
    """Require a raw repetition to match its index and its peers."""
    if run.repetition_index != expected_index:
        raise ValueError("raw repetition index does not match run order")
    if run.warmup != (expected_index < index.warmups):
        raise ValueError("raw warm-up flag does not match campaign protocol")
    indexed_fields = {
        "reference": index.reference,
        "ncores": index.ncores,
        "container_image_digest": index.container_image_digest,
    }
    for field, expected in indexed_fields.items():
        if getattr(run, field) != expected:
            raise ValueError(f"raw {field!r} does not match campaign index")
    if run.dataset.identifier != index.dataset_id:
        raise ValueError("raw dataset does not match campaign index")
    stable_fields = (
        "configuration_sha256",
        "container_image_digest",
        "dataset",
        "dependency_inventory_sha256",
        "environment_sha256",
        "ncores",
        "reference",
        "software",
    )
    for field in stable_fields:
        if getattr(run, field) != getattr(first, field):
            raise ValueError(f"raw campaign field {field!r} changed")


def _validate_artifacts(repetition_directory: Path, run: _RawRun) -> None:
    """Verify raw artifact sizes and hashes against files on disk."""
    for artifact_name, artifact in run.artifacts.items():
        artifact_path = repetition_directory / artifact_name
        if artifact_path.stat().st_size != artifact.bytes:
            raise ValueError(f"artifact byte size changed: {artifact_path}")
        if _file_sha256(artifact_path) != artifact.sha256:
            raise ValueError(f"artifact SHA-256 changed: {artifact_path}")


def _scientific_artifact_sha256(path: Path, *, normalize_history: bool) -> str:
    """Hash an artifact, optionally excluding LSMTool history comments."""
    if not normalize_history:
        return _file_sha256(path)
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("#")
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _validate_artifact_repeatability(
    directory: Path,
    index: _BaselineIndex,
    runs: tuple[_RawRun, ...],
) -> None:
    """Require stable products after declared metadata normalization."""
    artifact_names = set(runs[0].artifacts)
    normalized_names = set(index.scientific_identity_normalization)
    if not normalized_names.issubset(artifact_names):
        raise ValueError("normalized artifact is absent from raw products")
    for run in runs[1:]:
        if set(run.artifacts) != artifact_names:
            raise ValueError("raw artifact names changed between repetitions")
    for name in artifact_names:
        identities = {
            _scientific_artifact_sha256(
                (directory / relative_path).parent / name,
                normalize_history=name in normalized_names,
            )
            for relative_path in index.runs
        }
        if len(identities) != 1:
            raise ValueError(f"raw artifact {name!r} changed scientifically")


def _load_campaign(
    directory: Path,
) -> tuple[_BaselineIndex, tuple[_RawRun, ...]]:
    """Load a campaign and verify every referenced product and identity."""
    index = _BaselineIndex.model_validate_json(
        (directory / "baseline-index.json").read_text(encoding="utf-8")
    )
    runs = _load_raw_runs(directory, index)
    first = runs[0]
    for expected_index, (relative_path, run) in enumerate(
        zip(index.runs, runs, strict=True)
    ):
        repetition_directory = (directory / relative_path).parent
        _validate_run_identity(index, first, run, expected_index)
        _validate_artifacts(repetition_directory, run)
    _validate_artifact_repeatability(directory, index, runs)
    return index, runs


def _runtime_metrics(raw: _RawMetrics) -> RuntimeMetrics:
    """Translate raw external metrics without fabricating copy counters."""
    copy_reason = "external PyBDSF does not expose array-copy instrumentation"
    return RuntimeMetrics(
        wall_seconds=raw.wall_seconds,
        cpu_seconds=raw.cpu_seconds,
        peak_rss_bytes=raw.peak_rss_bytes,
        array_copy_count=None,
        array_copy_bytes=None,
        dask_task_count=0,
        transfer_bytes=0,
        spill_bytes=0,
        unavailable_metrics=(
            UnavailableMetric(
                metric="array_copy_count",
                reason=copy_reason,
            ),
            UnavailableMetric(
                metric="array_copy_bytes",
                reason=copy_reason,
            ),
        ),
    )


def _dataset_content_sha256(
    index: _BaselineIndex, dataset: _RawDataset
) -> str:
    """Bind auxiliary scientific inputs when a campaign supplies them."""
    if not index.input_sha256:
        return dataset.content_sha256
    image_digests = {
        "flat_noise_image": dataset.flat_noise_sha256,
        "true_sky_image": dataset.true_sky_sha256,
    }
    for name, digest in image_digests.items():
        if index.input_sha256.get(name) != digest:
            raise ValueError(f"campaign input {name!r} does not match raw run")
    if (
        set(index.input_sha256) == set(image_digests)
        and dataset.flat_noise_sha256 == dataset.true_sky_sha256
    ):
        return dataset.content_sha256
    return _canonical_sha256(index.input_sha256)


@dataclass(frozen=True)
class BaselineEvidenceMetadata:
    """Governance metadata supplied when raw measurements are compiled."""

    run_id: str
    dataset_role: DatasetRole
    shape_yx: tuple[int, int]
    workload_class: WorkloadClass
    status: EvidenceStatus = EvidenceStatus.REVIEWED
    storage_identifier: str = "host-bind-mounted-local-volume"


def compile_pybdsf_benchmark_evidence(
    campaign_directory: Path,
    metadata: BaselineEvidenceMetadata,
) -> BenchmarkEvidence:
    """Compile one validated raw campaign into versioned evidence."""
    index, runs = _load_campaign(campaign_directory)
    first = runs[0]
    dependency_sha = first.dependency_inventory_sha256
    container_digest = first.container_image_digest

    def software_identity(
        name: str, identity: _RawSoftwareIdentity
    ) -> SoftwareIdentity:
        return SoftwareIdentity(
            name=name,
            version=identity.version,
            commit_sha=identity.commit,
            container_image_digest=container_digest,
            dependency_inventory_sha256=dependency_sha,
        )

    measurements = tuple(
        Measurement(
            repetition_index=run.repetition_index,
            warmup=run.warmup,
            complete=_runtime_metrics(run.complete),
            stages=tuple(
                StageMetrics(
                    stage=stage.stage,
                    metrics=_runtime_metrics(stage.metrics),
                )
                for stage in run.stages
            ),
        )
        for run in runs
    )
    return BenchmarkEvidence(
        schema_version=1,
        evidence_type="benchmark",
        run_id=metadata.run_id,
        captured_at=min(run.captured_at for run in runs),
        status=metadata.status,
        dataset=DatasetIdentity(
            identifier=index.dataset_id,
            role=metadata.dataset_role,
            content_sha256=_dataset_content_sha256(index, first.dataset),
            shape_yx=metadata.shape_yx,
            workload_class=metadata.workload_class,
        ),
        subject=software_identity("pybdsf", first.software.bdsf),
        related_software=(
            software_identity("lsmtool", first.software.lsmtool),
            software_identity("rapthor", first.software.rapthor),
        ),
        configuration_sha256=first.configuration_sha256,
        environment_sha256=first.environment_sha256,
        resources=ResourceAllocation(
            executor=ExecutorKind.EXTERNAL,
            worker_nodes=1,
            workers_per_node=1,
            threads_per_worker=index.ncores,
            allocated_cpu_cores=index.ncores,
            node_memory_bytes=first.environment.node_memory_bytes,
            worker_memory_limit_bytes=first.environment.node_memory_bytes,
            reserved_headroom_per_node_bytes=0,
            storage_identifier=metadata.storage_identifier,
        ),
        measurements=measurements,
    )
