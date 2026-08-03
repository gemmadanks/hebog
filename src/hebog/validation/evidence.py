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
    UncertaintyMetric,
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
        if (
            self.version is None
            and self.commit_sha is None
            and self.source_tree_sha256 is None
            and self.container_image_digest is None
        ):
            raise ValueError(
                "software identity requires version, commit_sha, "
                "source_tree_sha256, or container_image_digest"
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


class CampaignImplementationIdentity(_EvidenceModel):
    """One explicitly named candidate or reference campaign implementation."""

    identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    role: Literal["candidate", "reference"]
    execution_configuration_sha256: str = Field(pattern=_SHA256_PATTERN)
    software: SoftwareIdentity


class CatastrophicMetricDiagnostic(_EvidenceModel):
    """Independent catastrophic flags for every governed source metric."""

    position: bool
    peak_flux: bool
    integrated_flux: bool
    fitted_axis: bool
    deconvolved_axis: bool


class NormalizedResidualDiagnostic(_EvidenceModel):
    """One candidate-minus-truth residual divided by its reported error."""

    metric: UncertaintyMetric
    value: float = Field(allow_inf_nan=False)


class SourcePairDiagnostic(_EvidenceModel):
    """One matched or unmatched truth/candidate decision with raw metrics."""

    decision: Literal["matched", "unmatched-truth", "unmatched-candidate"]
    truth_identifier: str | None = Field(default=None, min_length=1)
    candidate_identifier: str | None = Field(default=None, min_length=1)
    truth_strata: tuple[str, ...] = ()
    candidate_deconvolution_status: (
        Literal[
            "resolved",
            "unresolved",
            "unavailable",
        ]
        | None
    ) = None
    candidate_quality_flags: tuple[str, ...] = ()
    classification_agrees: bool | None = None
    separation_beam_fwhm: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )
    peak_flux_fractional_difference: float | None = Field(
        default=None,
        allow_inf_nan=False,
    )
    integrated_flux_fractional_difference: float | None = Field(
        default=None,
        allow_inf_nan=False,
    )
    maximum_absolute_fitted_axis_fractional_difference: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )
    maximum_absolute_deconvolved_axis_fractional_difference: float | None = (
        Field(
            default=None,
            ge=0,
            allow_inf_nan=False,
        )
    )
    catastrophic: CatastrophicMetricDiagnostic | None = None
    gated_catastrophic: bool | None = None
    normalized_residuals: tuple[NormalizedResidualDiagnostic, ...] = ()

    def _validate_canonical_sequences(self) -> None:
        """Require deterministic strata, flags, and residual ordering."""
        if self.truth_strata != tuple(sorted(set(self.truth_strata))) or any(
            not stratum.strip() for stratum in self.truth_strata
        ):
            raise ValueError("truth strata must be non-empty and canonical")
        if self.candidate_quality_flags != tuple(
            sorted(set(self.candidate_quality_flags))
        ) or any(not flag.strip() for flag in self.candidate_quality_flags):
            raise ValueError(
                "candidate quality flags must be non-empty and canonical"
            )
        residual_metrics = [
            residual.metric for residual in self.normalized_residuals
        ]
        if residual_metrics != sorted(set(residual_metrics)):
            raise ValueError(
                "normalized residual metrics must be unique and canonical"
            )

    def _has_match_diagnostics(self) -> bool:
        """Return whether any truth/candidate comparison value is present."""
        numeric_values = (
            self.separation_beam_fwhm,
            self.peak_flux_fractional_difference,
            self.integrated_flux_fractional_difference,
            self.maximum_absolute_fitted_axis_fractional_difference,
            self.maximum_absolute_deconvolved_axis_fractional_difference,
        )
        return (
            any(value is not None for value in numeric_values)
            or self.classification_agrees is not None
            or self.catastrophic is not None
            or self.gated_catastrophic is not None
            or bool(self.normalized_residuals)
        )

    def _validate_matched(self) -> None:
        """Require all identifiers and core measurements for a match."""
        if self.truth_identifier is None or self.candidate_identifier is None:
            raise ValueError("matched source requires both identifiers")
        if not self.truth_strata:
            raise ValueError("matched source requires truth strata")
        if self.candidate_deconvolution_status is None:
            raise ValueError("matched source requires candidate status")
        if any(
            value is None
            for value in (
                self.separation_beam_fwhm,
                self.peak_flux_fractional_difference,
                self.integrated_flux_fractional_difference,
            )
        ):
            raise ValueError(
                "matched source requires position and flux metrics"
            )
        if self.catastrophic is None or self.gated_catastrophic is None:
            raise ValueError("matched source requires catastrophic decisions")

    def _validate_unmatched_truth(self) -> None:
        """Forbid candidate measurements on an unmatched truth row."""
        if (
            self.truth_identifier is None
            or not self.truth_strata
            or self.candidate_identifier is not None
            or self.candidate_deconvolution_status is not None
            or self.candidate_quality_flags
            or self._has_match_diagnostics()
        ):
            raise ValueError(
                "unmatched truth requires strata and cannot contain "
                "candidate measurements"
            )

    def _validate_unmatched_candidate(self) -> None:
        """Forbid truth or match measurements on an unmatched candidate."""
        if (
            self.truth_identifier is not None
            or self.candidate_identifier is None
            or self.truth_strata
            or self.candidate_deconvolution_status is None
            or self._has_match_diagnostics()
        ):
            raise ValueError(
                "unmatched candidate cannot contain truth or match "
                "measurements"
            )

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        """Keep match decisions and their available measurements consistent."""
        self._validate_canonical_sequences()
        if self.decision == "matched":
            self._validate_matched()
        elif self.decision == "unmatched-truth":
            self._validate_unmatched_truth()
        else:
            self._validate_unmatched_candidate()
        return self


class AssociationPairDiagnostic(_EvidenceModel):
    """One observable truth-group/candidate association decision."""

    decision: Literal[
        "matched",
        "unmatched-truth-group",
        "unmatched-candidate",
    ]
    truth_group_identifier: str | None = Field(default=None, min_length=1)
    candidate_identifier: str | None = Field(default=None, min_length=1)
    resolution_class: (
        Literal["individually-resolvable", "unresolved-blend"] | None
    ) = None
    truth_strata: tuple[str, ...] = ()
    separation_beam_fwhm: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )
    integrated_flux_fractional_difference: float | None = Field(
        default=None,
        allow_inf_nan=False,
    )

    def _validate_canonical_strata(self) -> None:
        """Require deterministic, non-empty truth strata when present."""
        if self.truth_strata != tuple(sorted(set(self.truth_strata))) or any(
            not stratum.strip() for stratum in self.truth_strata
        ):
            raise ValueError("association truth strata must be canonical")

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        """Keep group and candidate fields consistent with the decision."""
        self._validate_canonical_strata()
        has_measurements = (
            self.separation_beam_fwhm is not None
            or self.integrated_flux_fractional_difference is not None
        )
        if self.decision == "matched":
            if (
                self.truth_group_identifier is None
                or self.candidate_identifier is None
                or self.resolution_class is None
                or not self.truth_strata
                or self.separation_beam_fwhm is None
                or self.integrated_flux_fractional_difference is None
            ):
                raise ValueError(
                    "matched association requires complete group measurements"
                )
        elif self.decision == "unmatched-truth-group":
            if (
                self.truth_group_identifier is None
                or self.candidate_identifier is not None
                or self.resolution_class is None
                or not self.truth_strata
                or has_measurements
            ):
                raise ValueError(
                    "unmatched truth group requires only truth metadata"
                )
        elif (
            self.truth_group_identifier is not None
            or self.candidate_identifier is None
            or self.resolution_class is not None
            or self.truth_strata
            or has_measurements
        ):
            raise ValueError(
                "unmatched candidate cannot contain truth-group measurements"
            )
        return self


class CampaignFailure(_EvidenceModel):
    """Stable failure details for one implementation and realization."""

    stage: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    exception_type: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]*$")
    message: str = Field(min_length=1)
    traceback_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_message(self) -> Self:
        """Reject whitespace-only exception messages."""
        if not self.message.strip():
            raise ValueError("failure message must not be blank")
        return self


class CampaignRealizationDiagnostic(_EvidenceModel):
    """One implementation outcome for one shared campaign seed."""

    implementation_identifier: str = Field(
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    seed: int = Field(ge=0)
    status: Literal["success", "failure"]
    candidate_count: int | None = Field(default=None, ge=0)
    association_pairs: tuple[AssociationPairDiagnostic, ...] = ()
    source_pairs: tuple[SourcePairDiagnostic, ...] = ()
    failure: CampaignFailure | None = None

    @staticmethod
    def _require_unique(identifiers: list[str], description: str) -> None:
        """Reject repeated identities within one realization."""
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(f"{description} must be unique per realization")

    def _source_identifiers(self) -> tuple[list[str], list[str]]:
        """Return and validate source-level truth and candidate identities."""
        truth = [
            pair.truth_identifier
            for pair in self.source_pairs
            if pair.truth_identifier is not None
        ]
        candidate = [
            pair.candidate_identifier
            for pair in self.source_pairs
            if pair.candidate_identifier is not None
        ]
        self._require_unique(truth, "truth identifiers")
        self._require_unique(candidate, "candidate identifiers")
        return truth, candidate

    def _association_identifiers(self) -> tuple[list[str], list[str]]:
        """Return and validate group-level truth and candidate identities."""
        truth = [
            pair.truth_group_identifier
            for pair in self.association_pairs
            if pair.truth_group_identifier is not None
        ]
        candidate = [
            pair.candidate_identifier
            for pair in self.association_pairs
            if pair.candidate_identifier is not None
        ]
        self._require_unique(truth, "truth-group identifiers")
        self._require_unique(
            candidate,
            "association candidate identifiers",
        )
        return truth, candidate

    def _validate_success_rows(self) -> None:
        """Require complete, consistent candidate and association rows."""
        _, source_candidates = self._source_identifiers()
        _, association_candidates = self._association_identifiers()
        represented_candidates = (
            association_candidates
            if self.association_pairs
            else source_candidates
        )
        if len(represented_candidates) != self.candidate_count:
            raise ValueError(
                "candidate count must equal represented candidate rows"
            )
        if self.association_pairs and not set(source_candidates).issubset(
            association_candidates
        ):
            raise ValueError(
                "source-pair candidates must occur in association decisions"
            )
        association_matches = {
            (pair.truth_group_identifier, pair.candidate_identifier)
            for pair in self.association_pairs
            if pair.decision == "matched"
        }
        source_matches = {
            (pair.truth_identifier, pair.candidate_identifier)
            for pair in self.source_pairs
            if pair.decision == "matched"
        }
        if self.association_pairs and not source_matches.issubset(
            association_matches
        ):
            raise ValueError(
                "source matches must agree with association decisions"
            )

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        """Separate complete scored results from explicit failed runs."""
        if self.status == "failure":
            if (
                self.failure is None
                or self.candidate_count is not None
                or self.association_pairs
                or self.source_pairs
            ):
                raise ValueError(
                    "failed realization requires one failure and no "
                    "partial rows"
                )
            return self
        if self.failure is not None or self.candidate_count is None:
            raise ValueError(
                "successful realization requires a candidate count and no "
                "failure"
            )
        self._validate_success_rows()
        return self


class CampaignImplementationEvidence(_EvidenceDocument):
    """One isolated implementation shard from a same-image campaign."""

    evidence_type: Literal["scientific-campaign-implementation"]
    comparison_protocol_sha256: str = Field(pattern=_SHA256_PATTERN)
    implementation: CampaignImplementationIdentity
    wall_seconds: float = Field(ge=0, allow_inf_nan=False)
    realizations: tuple[CampaignRealizationDiagnostic, ...] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def validate_implementation_results(self) -> Self:
        """Require ordered unique seeds for this implementation."""
        if any(
            realization.implementation_identifier
            != self.implementation.identifier
            for realization in self.realizations
        ):
            raise ValueError(
                "implementation shard contains a different implementation"
            )
        seeds = [realization.seed for realization in self.realizations]
        if seeds != sorted(set(seeds)):
            raise ValueError(
                "implementation realization seeds must be unique and sorted"
            )
        successful_truth = [
            {
                pair.truth_identifier
                for pair in realization.source_pairs
                if pair.truth_identifier is not None
            }
            for realization in self.realizations
            if realization.status == "success"
        ]
        successful_groups = [
            {
                pair.truth_group_identifier
                for pair in realization.association_pairs
                if pair.truth_group_identifier is not None
            }
            for realization in self.realizations
            if realization.status == "success"
        ]
        if successful_truth and any(
            truth != successful_truth[0] for truth in successful_truth[1:]
        ):
            raise ValueError(
                "implementation shard truth identifiers differ by seed"
            )
        if successful_groups and any(
            groups != successful_groups[0] for groups in successful_groups[1:]
        ):
            raise ValueError(
                "implementation shard truth-group identifiers differ by seed"
            )
        return self


class ScientificCampaignEvidence(_EvidenceDocument):
    """Paired same-image scientific diagnostics across implementations."""

    evidence_type: Literal["scientific-campaign"]
    comparison_protocol_sha256: str = Field(pattern=_SHA256_PATTERN)
    implementations: tuple[CampaignImplementationIdentity, ...] = Field(
        min_length=2
    )
    realizations: tuple[CampaignRealizationDiagnostic, ...] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def validate_pairing(self) -> Self:
        """Require same-seed coverage and identical truth populations."""
        implementation_identifiers = [
            implementation.identifier
            for implementation in self.implementations
        ]
        if len(set(implementation_identifiers)) != len(
            implementation_identifiers
        ):
            raise ValueError(
                "campaign implementation identifiers must be unique"
            )
        if (
            sum(
                implementation.role == "candidate"
                for implementation in self.implementations
            )
            != 1
        ):
            raise ValueError("campaign requires exactly one candidate")
        if self.implementations[0].role != "candidate":
            raise ValueError("campaign candidate must be declared first")

        seeds = sorted({realization.seed for realization in self.realizations})
        expected_keys = [
            (seed, identifier)
            for seed in seeds
            for identifier in implementation_identifiers
        ]
        actual_keys = [
            (realization.seed, realization.implementation_identifier)
            for realization in self.realizations
        ]
        if actual_keys != expected_keys:
            raise ValueError(
                "every seed must contain every implementation exactly once"
            )

        for seed in seeds:
            successful_truth: list[set[str]] = []
            successful_groups: list[set[str]] = []
            for realization in self.realizations:
                if realization.seed != seed or realization.status != "success":
                    continue
                successful_truth.append(
                    {
                        pair.truth_identifier
                        for pair in realization.source_pairs
                        if pair.truth_identifier is not None
                    }
                )
                successful_groups.append(
                    {
                        pair.truth_group_identifier
                        for pair in realization.association_pairs
                        if pair.truth_group_identifier is not None
                    }
                )
            if successful_truth and any(
                truth != successful_truth[0] for truth in successful_truth[1:]
            ):
                raise ValueError(
                    "successful paired runs require identical truth "
                    "identifiers"
                )
            if successful_groups and any(
                groups != successful_groups[0]
                for groups in successful_groups[1:]
            ):
                raise ValueError(
                    "successful paired runs require identical truth-group "
                    "identifiers"
                )
        return self


EvidenceDocument: TypeAlias = (
    BenchmarkEvidence
    | ScientificComparisonEvidence
    | CampaignImplementationEvidence
    | ScientificCampaignEvidence
)

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
    """Load and validate one benchmark or scientific evidence document."""
    payload = path.read_text(encoding="utf-8")
    return _EVIDENCE_ADAPTER.validate_json(payload)
