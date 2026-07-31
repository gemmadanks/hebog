"""Versioned machine-readable scientific and performance evidence.

Evidence documents distinguish exploratory observations from reviewed release
evidence and distinguish unavailable instrumentation from measured zeroes.
External product readers and benchmark runners create these records; loading
this module never reads data or starts work.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from hebog.validation.comparison import (
    CatalogueComparisonReport,
    MaskComparisonReport,
    RmsComparisonReport,
)
from hebog.validation.datasets import DatasetRole

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_CONTAINER_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_COMMIT_PATTERN = r"^[0-9a-f]{40}$"
_MINIMUM_REVIEWED_REPETITIONS = 5

OptionalMetricName: TypeAlias = Literal[
    "array_copy_count",
    "array_copy_bytes",
    "dask_task_count",
    "transfer_bytes",
    "spill_bytes",
]


class EvidenceStatus(str, Enum):
    """Review status of an evidence document."""

    EXPLORATORY = "exploratory"
    REVIEWED = "reviewed"


class WorkloadClass(str, Enum):
    """Scientific work represented by a benchmark dataset."""

    EMPTY_SPARSE = "empty-or-sparse"
    NORMAL = "normal"
    DENSE_EXTENDED = "dense-or-extended"


class ExecutorKind(str, Enum):
    """Execution boundary used for a measured run."""

    SERIAL = "serial"
    LOCAL = "local"
    DASK = "dask"
    EXTERNAL = "external"


class _EvidenceModel(BaseModel):
    """Strict immutable base for evidence records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SoftwareIdentity(_EvidenceModel):
    """Exact software and dependency identity used by one run."""

    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    version: str | None = Field(default=None, min_length=1)
    commit_sha: str | None = Field(default=None, pattern=_COMMIT_PATTERN)
    source_tree_sha256: str | None = Field(
        default=None,
        pattern=_SHA256_PATTERN,
    )
    container_image_digest: str | None = Field(
        default=None,
        pattern=_CONTAINER_DIGEST_PATTERN,
    )
    dependency_inventory_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_revision(self) -> Self:
        """Require at least one independently useful revision identifier."""
        if self.version is None and self.commit_sha is None:
            raise ValueError(
                "software identity requires version or commit_sha"
            )
        return self


class DatasetIdentity(_EvidenceModel):
    """Governed dataset and workload identity for evidence."""

    identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    role: DatasetRole
    content_sha256: str = Field(pattern=_SHA256_PATTERN)
    shape_yx: tuple[int, int]
    workload_class: WorkloadClass

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        """Reject empty or negative logical image dimensions."""
        if any(dimension <= 0 for dimension in self.shape_yx):
            raise ValueError("shape_yx dimensions must be positive")
        return self


class ResourceAllocation(_EvidenceModel):
    """Admitted compute and storage topology for one measured run."""

    executor: ExecutorKind
    worker_nodes: int = Field(ge=1)
    workers_per_node: int = Field(ge=1)
    threads_per_worker: int = Field(ge=1)
    allocated_cpu_cores: int = Field(ge=1)
    node_memory_bytes: int = Field(ge=1)
    worker_memory_limit_bytes: int = Field(ge=1)
    reserved_headroom_per_node_bytes: int = Field(ge=0)
    storage_identifier: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_memory_admission(self) -> Self:
        """Keep aggregate worker limits within admitted node memory."""
        available_memory = (
            self.node_memory_bytes - self.reserved_headroom_per_node_bytes
        )
        admitted_worker_memory = (
            self.workers_per_node * self.worker_memory_limit_bytes
        )
        if available_memory <= 0:
            raise ValueError("reserved headroom must leave usable node memory")
        if admitted_worker_memory > available_memory:
            raise ValueError(
                "aggregate worker memory exceeds node memory after headroom"
            )
        return self


class StorageEvidence(_EvidenceModel):
    """Intermediate-store layout, policy, and observed footprint."""

    format_name: str = Field(min_length=1)
    library_name: str = Field(min_length=1)
    library_version: str = Field(min_length=1)
    backend_name: str = Field(min_length=1)
    chunk_shape_yx: tuple[int, int]
    shard_shape_yx: tuple[int, int] | None
    codec_pipeline: tuple[str, ...] = Field(min_length=1)
    fill_value: str = Field(min_length=1)
    missing_chunk_policy: Literal["error", "fill"]
    write_empty_chunks: bool
    object_count: int = Field(ge=1)
    stored_bytes: int = Field(ge=1)
    internal_concurrency: int = Field(ge=1)
    atomic_write_guarantee: str = Field(min_length=1)
    conditional_create: bool

    @model_validator(mode="after")
    def validate_storage_configuration(self) -> Self:
        """Require usable geometry and non-blank policy descriptions."""
        if any(dimension <= 0 for dimension in self.chunk_shape_yx):
            raise ValueError("storage chunk dimensions must be positive")
        if self.shard_shape_yx is not None and any(
            dimension <= 0 for dimension in self.shard_shape_yx
        ):
            raise ValueError("storage shard dimensions must be positive")
        descriptions = (
            self.format_name,
            self.library_name,
            self.library_version,
            self.backend_name,
            self.fill_value,
            self.atomic_write_guarantee,
            *self.codec_pipeline,
        )
        if any(not description.strip() for description in descriptions):
            raise ValueError("storage descriptions must not be blank")
        return self


class UnavailableMetric(_EvidenceModel):
    """One unavailable optional instrument and its explicit reason."""

    metric: OptionalMetricName
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reason(self) -> Self:
        """Reject whitespace-only explanations."""
        if not self.reason.strip():
            raise ValueError("unavailable metric reason must not be blank")
        return self


class RuntimeMetrics(_EvidenceModel):
    """Required timing/resource metrics with explicit unavailable values."""

    wall_seconds: float = Field(ge=0, allow_inf_nan=False)
    cpu_seconds: float = Field(ge=0, allow_inf_nan=False)
    peak_rss_bytes: int = Field(ge=0)
    array_copy_count: int | None = Field(ge=0)
    array_copy_bytes: int | None = Field(ge=0)
    dask_task_count: int | None = Field(ge=0)
    transfer_bytes: int | None = Field(ge=0)
    spill_bytes: int | None = Field(ge=0)
    unavailable_metrics: tuple[UnavailableMetric, ...] = ()

    @model_validator(mode="after")
    def validate_unavailable_metrics(self) -> Self:
        """Require one reason for every unavailable optional instrument."""
        metric_values: dict[OptionalMetricName, int | None] = {
            "array_copy_count": self.array_copy_count,
            "array_copy_bytes": self.array_copy_bytes,
            "dask_task_count": self.dask_task_count,
            "transfer_bytes": self.transfer_bytes,
            "spill_bytes": self.spill_bytes,
        }
        reason_names = [item.metric for item in self.unavailable_metrics]
        if len(set(reason_names)) != len(reason_names):
            raise ValueError("unavailable metric names must be unique")
        unavailable_reasons = {
            item.metric: item.reason for item in self.unavailable_metrics
        }
        for metric_name, value in metric_values.items():
            reason = unavailable_reasons.get(metric_name)
            if value is None and reason is None:
                raise ValueError(
                    f"{metric_name} is unavailable without a reason"
                )
            if value is not None and reason is not None:
                raise ValueError(
                    f"{metric_name} has both a value and unavailable reason"
                )
        return self


class StageMetrics(_EvidenceModel):
    """Metrics attributed to one named scientific or integration stage."""

    stage: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    metrics: RuntimeMetrics


class Measurement(_EvidenceModel):
    """One warm-up or measured complete-run repetition."""

    repetition_index: int = Field(ge=0)
    warmup: bool
    complete: RuntimeMetrics
    stages: tuple[StageMetrics, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_stages(self) -> Self:
        """Prevent ambiguous repeated stage metrics in one repetition."""
        names = [stage.stage for stage in self.stages]
        if len(set(names)) != len(names):
            raise ValueError("stage names must be unique within a measurement")
        return self


class ScalabilityMetrics(_EvidenceModel):
    """Topology and efficiency evidence required for multi-node runs."""

    logical_plane_count: int = Field(ge=1)
    tile_core_shape_yx: tuple[int, int]
    maximum_halo_yx: tuple[int, int]
    partition_count: int = Field(ge=1)
    graph_task_count: int = Field(ge=0)
    scheduler_overhead_seconds: float = Field(ge=0, allow_inf_nan=False)
    worker_occupancy_fraction: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    storage_throughput_bytes_per_second: float = Field(
        ge=0,
        allow_inf_nan=False,
    )
    retry_count: int = Field(ge=0)
    straggler_count: int = Field(ge=0)
    strong_scaling_efficiency: float = Field(ge=0, allow_inf_nan=False)
    weak_scaling_efficiency: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_geometry(self) -> Self:
        """Require positive tile cores and non-negative halos."""
        if any(dimension <= 0 for dimension in self.tile_core_shape_yx):
            raise ValueError("tile core dimensions must be positive")
        if any(dimension < 0 for dimension in self.maximum_halo_yx):
            raise ValueError("halo dimensions cannot be negative")
        return self


class _EvidenceDocument(_EvidenceModel):
    """Shared provenance required by every evidence document."""

    schema_version: Literal[1]
    run_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    captured_at: datetime
    status: EvidenceStatus
    dataset: DatasetIdentity
    configuration_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        """Require an unambiguous timezone-aware evidence timestamp."""
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must include a timezone")
        if self.captured_at.utcoffset() is None:
            raise ValueError("captured_at timezone must define a UTC offset")
        return self


class BenchmarkEvidence(_EvidenceDocument):
    """Versioned measurements for one exact implementation and environment."""

    evidence_type: Literal["benchmark"]
    subject: SoftwareIdentity
    related_software: tuple[SoftwareIdentity, ...] = ()
    environment_sha256: str = Field(pattern=_SHA256_PATTERN)
    resources: ResourceAllocation
    measurements: tuple[Measurement, ...] = Field(min_length=1)
    storage: StorageEvidence | None = None
    scalability: ScalabilityMetrics | None = None

    @model_validator(mode="after")
    def validate_benchmark_protocol(self) -> Self:
        """Enforce identity, ordering, and reviewed repetition requirements."""
        software_names = [
            self.subject.name,
            *(software.name for software in self.related_software),
        ]
        if len(set(software_names)) != len(software_names):
            raise ValueError("software identity names must be unique")

        repetition_indices = [
            measurement.repetition_index for measurement in self.measurements
        ]
        if len(set(repetition_indices)) != len(repetition_indices):
            raise ValueError("repetition indices must be unique")
        if repetition_indices != sorted(repetition_indices):
            raise ValueError(
                "measurements must be ordered by repetition index"
            )

        measured_repetition_seen = False
        for measurement in self.measurements:
            if measurement.warmup and measured_repetition_seen:
                raise ValueError(
                    "warm-up repetitions must precede measured repetitions"
                )
            measured_repetition_seen = (
                measured_repetition_seen or not measurement.warmup
            )

        if self.status is EvidenceStatus.REVIEWED:
            warmup_count = sum(
                measurement.warmup for measurement in self.measurements
            )
            measured_count = len(self.measurements) - warmup_count
            if warmup_count < 1:
                raise ValueError("reviewed evidence requires a warm-up")
            if measured_count < _MINIMUM_REVIEWED_REPETITIONS:
                raise ValueError(
                    "reviewed evidence requires five measured repetitions"
                )
            if self.resources.worker_nodes > 1 and self.scalability is None:
                raise ValueError(
                    "reviewed multi-node evidence requires scalability metrics"
                )
        return self


class ScientificComparisonEvidence(_EvidenceDocument):
    """Provenance and reports for one candidate/reference comparison."""

    evidence_type: Literal["scientific-comparison"]
    candidate: SoftwareIdentity
    reference: SoftwareIdentity
    candidate_product_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    reference_product_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    beam_fwhm_degrees: float = Field(gt=0, allow_inf_nan=False)
    maximum_separation_beams: float = Field(gt=0, allow_inf_nan=False)
    catalogue: CatalogueComparisonReport
    true_sky_rms: RmsComparisonReport
    flat_noise_rms: RmsComparisonReport
    mask: MaskComparisonReport


EvidenceDocument: TypeAlias = BenchmarkEvidence | ScientificComparisonEvidence

_EVIDENCE_ADAPTER: TypeAdapter[EvidenceDocument] = TypeAdapter(
    EvidenceDocument
)


def canonical_evidence_json(document: EvidenceDocument) -> str:
    """Serialize evidence deterministically with a final newline."""
    payload = document.model_dump(mode="json")
    return (
        json.dumps(
            payload,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def write_evidence(path: Path, document: EvidenceDocument) -> None:
    """Atomically write one validated evidence document."""
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        canonical_evidence_json(document),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def load_evidence(path: Path) -> EvidenceDocument:
    """Load and validate one benchmark or comparison evidence document."""
    payload = path.read_text(encoding="utf-8")
    return _EVIDENCE_ADAPTER.validate_json(payload)
