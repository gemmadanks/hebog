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
from math import isclose, isfinite
from pathlib import Path
from statistics import median
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


class PhaseFiveFilterCandidateEvidence(_EvidenceModel):
    """Scientific and bounded-cost observations for one filter family."""

    family: Literal[
        "beam-aware-matched-filter",
        "undecimated-wavelet",
    ]
    measured_wall_seconds: tuple[float, ...] = Field(min_length=5)
    median_wall_seconds: float = Field(gt=0, allow_inf_nan=False)
    maximum_workspace_bytes: int = Field(ge=1)
    convolution_count_per_image: int = Field(ge=1)
    temporary_plane_count: int = Field(ge=1)
    maximum_halo_pixels: int = Field(ge=1)
    maximum_unit_flux_response_fractional_error: float = Field(
        ge=0,
        allow_inf_nan=False,
    )
    maximum_masked_response_fractional_error: float = Field(
        ge=0,
        allow_inf_nan=False,
    )
    maximum_edge_response_fractional_error: float = Field(
        ge=0,
        allow_inf_nan=False,
    )
    maximum_absolute_background_response_jy_per_beam: float = Field(
        ge=0,
        allow_inf_nan=False,
    )
    finite_truth_group_response_fraction: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    minimum_correlated_noise_gain: float = Field(gt=0, allow_inf_nan=False)
    maximum_correlated_noise_gain: float = Field(gt=0, allow_inf_nan=False)
    scientifically_adequate: bool

    @model_validator(mode="after")
    def validate_measurements(self) -> Self:
        """Bind summaries to finite measurements and ordered noise gains."""
        if not all(
            isfinite(value) and value > 0
            for value in self.measured_wall_seconds
        ):
            raise ValueError(
                "filter wall measurements must be finite and positive"
            )
        measured_median = float(median(self.measured_wall_seconds))
        if not isclose(
            self.median_wall_seconds,
            measured_median,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("filter median wall time must match measurements")
        if (
            self.minimum_correlated_noise_gain
            > self.maximum_correlated_noise_gain
        ):
            raise ValueError("correlated-noise gain bounds must be ordered")
        return self


class PhaseFiveFilterSelectionEvidence(_EvidenceDocument):
    """Reviewed development-only decision between the Phase 5 candidates."""

    evidence_type: Literal["phase-five-filter-selection"]
    subject: SoftwareIdentity
    environment_sha256: str = Field(pattern=_SHA256_PATTERN)
    candidates: tuple[PhaseFiveFilterCandidateEvidence, ...]
    selected_family: Literal[
        "beam-aware-matched-filter",
        "undecimated-wavelet",
    ]
    decision_rule: Literal[
        "all-analytic-gates-then-lowest-maintained-bounded-cost"
    ]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        """Require both candidates and scientific passage before selection."""
        families = tuple(item.family for item in self.candidates)
        if families != (
            "beam-aware-matched-filter",
            "undecimated-wavelet",
        ):
            raise ValueError(
                "filter candidates must be complete and canonical"
            )
        selected = next(
            item
            for item in self.candidates
            if item.family == self.selected_family
        )
        if not selected.scientifically_adequate:
            raise ValueError("selected filter must be scientifically adequate")
        return self


PhaseFiveFilterFamily: TypeAlias = Literal[
    "beam-aware-matched-filter",
    "undecimated-wavelet",
]


class PhaseFiveFilterReviewEndpointEvidence(_EvidenceModel):
    """One absolute or diagnostic Step 2B endpoint summary."""

    metric: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    population: Literal["analytic", "development", "regression"]
    stratum: str = Field(min_length=1)
    statistic: Literal[
        "fraction", "maximum", "mean", "median", "percentile-95"
    ]
    family: PhaseFiveFilterFamily
    sample_count: int = Field(ge=1)
    estimate: float = Field(allow_inf_nan=False)
    absolute_limit: float | None = Field(default=None, allow_inf_nan=False)
    absolute_direction: Literal["maximum", "minimum"] | None = None
    passed: bool | None = None

    @model_validator(mode="after")
    def validate_absolute_decision(self) -> Self:
        """Keep diagnostic and binding fields internally consistent."""
        decision_fields = (
            self.absolute_limit,
            self.absolute_direction,
            self.passed,
        )
        if any(item is None for item in decision_fields) != all(
            item is None for item in decision_fields
        ):
            raise ValueError(
                "absolute endpoint limit, direction, and decision must "
                "be supplied together"
            )
        if self.absolute_limit is not None:
            expected = (
                self.estimate <= self.absolute_limit
                if self.absolute_direction == "maximum"
                else self.estimate >= self.absolute_limit
            )
            if self.passed != expected:
                raise ValueError("absolute endpoint decision is incorrect")
        return self


class PhaseFiveFilterReviewPairedEndpointEvidence(_EvidenceModel):
    """One candidate-to-candidate Step 2B non-inferiority decision."""

    metric: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    population: Literal["analytic", "regression"]
    stratum: str = Field(min_length=1)
    statistic: Literal["fraction", "mean", "median", "percentile-95"]
    family: PhaseFiveFilterFamily
    reference_family: PhaseFiveFilterFamily
    sample_count: int = Field(ge=1)
    estimate_difference: float = Field(allow_inf_nan=False)
    upper_confidence_limit: float = Field(allow_inf_nan=False)
    margin: float = Field(gt=0, allow_inf_nan=False)
    passed: bool

    @model_validator(mode="after")
    def validate_paired_decision(self) -> Self:
        """Require the opposite candidate and the frozen upper-limit rule."""
        if self.family == self.reference_family:
            raise ValueError("paired endpoint requires the other candidate")
        if self.passed != (self.upper_confidence_limit <= self.margin):
            raise ValueError("paired endpoint decision is incorrect")
        return self


class PhaseFiveFilterReviewCandidateConclusion(_EvidenceModel):
    """Conjunctive science decision and structural cost for one candidate."""

    family: PhaseFiveFilterFamily
    passes_absolute: bool
    noninferior_to_other: bool
    bounded_cost: tuple[int, int, int]
    failed_absolute_endpoint_count: int = Field(ge=0)
    failed_paired_endpoint_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_cost_and_counts(self) -> Self:
        """Reject non-positive costs or inconsistent conclusions."""
        if any(value <= 0 for value in self.bounded_cost):
            raise ValueError("filter-review bounded costs must be positive")
        if self.passes_absolute != (
            self.failed_absolute_endpoint_count == 0
        ) or self.noninferior_to_other != (
            self.failed_paired_endpoint_count == 0
        ):
            raise ValueError("candidate conclusion disagrees with failures")
        return self


class PhaseFiveFilterReviewEvidence(_EvidenceDocument):
    """Completed non-qualification paired review for Phase 5 Step 2B."""

    evidence_type: Literal["phase-five-filter-paired-review"]
    subject: SoftwareIdentity
    environment_sha256: str = Field(pattern=_SHA256_PATTERN)
    protocol_sha256: str = Field(pattern=_SHA256_PATTERN)
    development_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    regression_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    analytic_case_count: int = Field(ge=1)
    development_image_count: int = Field(ge=1)
    regression_image_count: int = Field(ge=100)
    bootstrap_resamples: int = Field(ge=10_000)
    bootstrap_seed: int = Field(ge=0)
    endpoints: tuple[PhaseFiveFilterReviewEndpointEvidence, ...] = Field(
        min_length=1
    )
    paired_endpoints: tuple[
        PhaseFiveFilterReviewPairedEndpointEvidence, ...
    ] = Field(min_length=1)
    candidates: tuple[PhaseFiveFilterReviewCandidateConclusion, ...]
    decision: Literal[
        "select-matched-filter",
        "select-wavelet",
        "select-neither",
    ]
    selected_family: PhaseFiveFilterFamily | None
    step_three_authorized: bool
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_review_conclusion(self) -> Self:
        """Bind the final decision to all constituent scientific endpoints."""
        if self.status is not EvidenceStatus.REVIEWED:
            raise ValueError(
                "completed filter review evidence must be reviewed"
            )
        families: tuple[PhaseFiveFilterFamily, ...] = (
            "beam-aware-matched-filter",
            "undecimated-wavelet",
        )
        if tuple(item.family for item in self.candidates) != families:
            raise ValueError("filter-review candidates must be canonical")
        endpoint_keys = [
            (
                item.population,
                item.stratum,
                item.metric,
                item.statistic,
                item.family,
            )
            for item in self.endpoints
        ]
        paired_keys = [
            (
                item.population,
                item.stratum,
                item.metric,
                item.statistic,
                item.family,
            )
            for item in self.paired_endpoints
        ]
        if len(set(endpoint_keys)) != len(endpoint_keys) or len(
            set(paired_keys)
        ) != len(paired_keys):
            raise ValueError(
                "filter-review endpoint identities must be unique"
            )
        for candidate in self.candidates:
            absolute_failures = sum(
                item.family == candidate.family and item.passed is False
                for item in self.endpoints
            )
            paired_failures = sum(
                item.family == candidate.family and not item.passed
                for item in self.paired_endpoints
            )
            if (
                candidate.failed_absolute_endpoint_count != absolute_failures
                or candidate.failed_paired_endpoint_count != paired_failures
            ):
                raise ValueError(
                    "candidate conclusion disagrees with recorded endpoints"
                )
        eligible = tuple(
            item
            for item in self.candidates
            if item.passes_absolute and item.noninferior_to_other
        )
        expected_selected = (
            min(eligible, key=lambda item: item.bounded_cost).family
            if eligible
            else None
        )
        expected_decision = {
            None: "select-neither",
            "beam-aware-matched-filter": "select-matched-filter",
            "undecimated-wavelet": "select-wavelet",
        }[expected_selected]
        if (
            self.selected_family != expected_selected
            or self.decision != expected_decision
        ):
            raise ValueError(
                "filter-review decision disagrees with candidates"
            )
        if self.step_three_authorized != (self.selected_family is not None):
            raise ValueError("Step 3 authorization requires a selected family")
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
            "major-axis-only",
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
    fitted_position_angle_difference_degrees: float | None = Field(
        default=None,
        allow_inf_nan=False,
    )
    deconvolved_position_angle_difference_degrees: float | None = Field(
        default=None,
        allow_inf_nan=False,
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
            self.fitted_position_angle_difference_degrees,
            self.deconvolved_position_angle_difference_degrees,
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


class PhaseFourEndpointDecision(_EvidenceModel):
    """One reviewed paired non-inferiority endpoint decision."""

    endpoint_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    candidate_value: float | None = Field(default=None, allow_inf_nan=False)
    reference_value: float | None = Field(default=None, allow_inf_nan=False)
    positive_regression: float | None = Field(
        default=None, allow_inf_nan=False
    )
    practical_regression_margin: float = Field(gt=0, allow_inf_nan=False)
    upper_confidence_limit: float | None = Field(
        default=None,
        allow_inf_nan=False,
    )
    confidence_level: float = Field(gt=0, lt=1, allow_inf_nan=False)
    resamples: int = Field(ge=10_000)
    status: Literal["pass", "fail", "indeterminate"]
    reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        """Keep complete intervals distinct from failed-closed results."""
        values = (
            self.candidate_value,
            self.reference_value,
            self.positive_regression,
            self.upper_confidence_limit,
        )
        if self.status == "indeterminate":
            if self.reason is None:
                raise ValueError("indeterminate endpoint requires a reason")
            point_values = values[:3]
            if self.upper_confidence_limit is not None or (
                any(value is None for value in point_values)
                and any(value is not None for value in point_values)
            ):
                raise ValueError(
                    "indeterminate endpoint requires a complete point "
                    "estimate or no point estimate and no interval"
                )
            return self
        if any(value is None for value in values) or self.reason is not None:
            raise ValueError(
                "determinate endpoint requires complete values and no reason"
            )
        upper = self.upper_confidence_limit
        assert upper is not None
        if self.status == "pass" and not (
            upper <= self.practical_regression_margin
        ):
            raise ValueError("passing endpoint exceeds its practical margin")
        if self.status == "fail" and not (
            upper > self.practical_regression_margin
        ):
            raise ValueError("failed endpoint remains within its margin")
        return self


def _gate_thresholds_are_valid(
    comparator: Literal["minimum", "maximum", "interval"],
    minimum: float | None,
    maximum: float | None,
) -> bool:
    """Return whether a gate defines exactly the required thresholds."""
    if comparator == "minimum":
        return minimum is not None and maximum is None
    if comparator == "maximum":
        return maximum is not None and minimum is None
    return minimum is not None and maximum is not None


class PhaseFourGateDecision(_EvidenceModel):
    """One absolute science-gate result on the Hebog population."""

    gate_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    value: float | None = Field(default=None, allow_inf_nan=False)
    comparator: Literal["minimum", "maximum", "interval"]
    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    interval_lower: float | None = Field(default=None, allow_inf_nan=False)
    interval_upper: float | None = Field(default=None, allow_inf_nan=False)
    eligible_count: int = Field(ge=0)
    role: Literal["gate", "report-only"] = "gate"
    status: Literal["pass", "fail", "indeterminate"]
    reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_gate(self) -> Self:
        """Require the threshold shape implied by the comparator."""
        if not _gate_thresholds_are_valid(
            self.comparator,
            self.minimum,
            self.maximum,
        ):
            raise ValueError("gate comparator and thresholds disagree")
        if self.status == "indeterminate":
            if (
                self.interval_lower is not None
                or self.interval_upper is not None
                or self.reason is None
            ):
                raise ValueError(
                    "indeterminate gate cannot contain observed bounds and "
                    "requires an explanatory reason"
                )
            return self
        if self.value is None or self.reason is not None:
            raise ValueError("determinate gate requires a value and no reason")
        if self.comparator == "interval":
            if self.interval_lower is None or self.interval_upper is None:
                raise ValueError("interval gate requires both observed bounds")
            assert self.minimum is not None
            assert self.maximum is not None
            passed = (
                self.interval_lower >= self.minimum
                and self.interval_upper <= self.maximum
            )
        else:
            if (
                self.interval_lower is not None
                or self.interval_upper is not None
            ):
                raise ValueError("scalar gate cannot contain interval bounds")
            passed = (self.minimum is None or self.value >= self.minimum) and (
                self.maximum is None or self.value <= self.maximum
            )
        if (self.status == "pass") != passed:
            raise ValueError("gate status disagrees with its threshold")
        return self


class PhaseFourEnvelopeDecision(_EvidenceModel):
    """One named regression envelope protecting a stronger Hebog result."""

    envelope_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    absolute_gate_ids: tuple[str, ...] = Field(min_length=1)
    status: Literal["pass", "fail", "indeterminate"]

    @model_validator(mode="after")
    def validate_gate_ids(self) -> Self:
        """Require a canonical, non-empty set of constituent gates."""
        if self.absolute_gate_ids != tuple(
            sorted(set(self.absolute_gate_ids))
        ):
            raise ValueError("envelope gate identifiers must be canonical")
        return self


class PhaseFourImplementationOutcome(_EvidenceModel):
    """Failure summary for one implementation in the frozen campaign."""

    implementation_identifier: str = Field(
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    policy: Literal["qualification-fails", "record-and-continue"]
    failed_seeds: tuple[int, ...] = ()

    @model_validator(mode="after")
    def validate_seeds(self) -> Self:
        """Keep failure seeds non-negative, unique, and deterministic."""
        if self.failed_seeds != tuple(sorted(set(self.failed_seeds))) or any(
            seed < 0 for seed in self.failed_seeds
        ):
            raise ValueError("failed seeds must be canonical and non-negative")
        return self


class PhaseFourQualificationDecision(_EvidenceDocument):
    """Immutable one-look decision for the frozen Phase 4 campaign."""

    evidence_type: Literal["phase-4-qualification-decision"]
    source_campaign_run_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    source_campaign_sha256: str = Field(pattern=_SHA256_PATTERN)
    comparison_protocol_sha256: str = Field(pattern=_SHA256_PATTERN)
    scientific_gates_sha256: str = Field(pattern=_SHA256_PATTERN)
    candidate_identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    primary_reference_identifier: str = Field(
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    secondary_reference_identifier: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    implementation_outcomes: tuple[PhaseFourImplementationOutcome, ...] = (
        Field(min_length=2)
    )
    paired_endpoints: tuple[PhaseFourEndpointDecision, ...] = ()
    secondary_paired_endpoints: tuple[PhaseFourEndpointDecision, ...] = ()
    absolute_gates: tuple[PhaseFourGateDecision, ...] = ()
    stronger_hebog_envelopes: tuple[PhaseFourEnvelopeDecision, ...] = ()
    passed: bool
    failure_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_one_look(self) -> Self:
        """Make the aggregate decision follow every constituent result."""
        named_sequences = (
            (
                "implementation",
                [
                    item.implementation_identifier
                    for item in self.implementation_outcomes
                ],
            ),
            ("endpoint", [item.endpoint_id for item in self.paired_endpoints]),
            (
                "secondary endpoint",
                [item.endpoint_id for item in self.secondary_paired_endpoints],
            ),
            ("gate", [item.gate_id for item in self.absolute_gates]),
            (
                "envelope",
                [item.envelope_id for item in self.stronger_hebog_envelopes],
            ),
        )
        for description, identifiers in named_sequences:
            if len(set(identifiers)) != len(identifiers):
                raise ValueError(f"{description} identifiers must be unique")
        if self.failure_reasons != tuple(sorted(set(self.failure_reasons))):
            raise ValueError("failure reasons must be canonical")
        constituent_pass = (
            bool(self.paired_endpoints)
            and bool(self.absolute_gates)
            and bool(self.stronger_hebog_envelopes)
            and all(item.status == "pass" for item in self.paired_endpoints)
            and all(
                item.status == "pass"
                for item in self.absolute_gates
                if item.role == "gate"
            )
            and all(
                item.status == "pass" for item in self.stronger_hebog_envelopes
            )
            and not any(
                item.failed_seeds and item.policy == "qualification-fails"
                for item in self.implementation_outcomes
            )
        )
        if self.passed != constituent_pass:
            raise ValueError("overall decision disagrees with constituents")
        if self.passed == bool(self.failure_reasons):
            raise ValueError(
                "passing decisions cannot have failure reasons and failed "
                "decisions require them"
            )
        return self


def _expected_recovery_point_status(
    values: tuple[float | None, float | None, float | None],
    margin: float,
) -> Literal["pass", "fail", "indeterminate"]:
    """Derive a recovery point status from complete or absent values."""
    if all(value is None for value in values):
        return "indeterminate"
    if any(value is None for value in values):
        raise ValueError("recovery metric point values must be complete")
    regression = values[2]
    assert regression is not None
    return "pass" if regression <= margin else "fail"


def _expected_recovery_interval_status(
    upper: float | None,
    margin: float,
) -> Literal["pass", "fail", "indeterminate"]:
    """Derive an interval status from a finite limit or its absence."""
    if upper is None:
        return "indeterminate"
    return "pass" if upper <= margin else "fail"


def _combined_recovery_status(
    point: Literal["pass", "fail", "indeterminate"],
    interval: Literal["pass", "fail", "indeterminate"],
) -> Literal["pass", "fail", "indeterminate"]:
    """Combine conjunctive point and interval decisions."""
    if "fail" in {point, interval}:
        return "fail"
    if "indeterminate" in {point, interval}:
        return "indeterminate"
    return "pass"


class PhaseFourRecoveryMetricDecision(_EvidenceModel):
    """One independent Phase 4R metric comparison against one reference."""

    metric_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    stratum: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    reference_identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    candidate_value: float | None = Field(default=None, allow_inf_nan=False)
    reference_value: float | None = Field(default=None, allow_inf_nan=False)
    positive_regression: float | None = Field(
        default=None,
        allow_inf_nan=False,
    )
    practical_regression_margin: float = Field(ge=0, allow_inf_nan=False)
    point_status: Literal["pass", "fail", "indeterminate"]
    upper_confidence_limit: float | None = Field(
        default=None,
        allow_inf_nan=False,
    )
    interval_status: Literal["pass", "fail", "indeterminate", "not-evaluated"]
    status: Literal["pass", "fail", "indeterminate"]
    reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_metric_decision(self) -> Self:
        """Bind point, interval, and aggregate statuses to their values."""
        point_values = (
            self.candidate_value,
            self.reference_value,
            self.positive_regression,
        )
        expected_point = _expected_recovery_point_status(
            point_values,
            self.practical_regression_margin,
        )
        if self.point_status != expected_point:
            raise ValueError("metric point status disagrees with values")

        if self.interval_status == "not-evaluated":
            if self.upper_confidence_limit is not None:
                raise ValueError(
                    "unevaluated metric interval cannot contain a limit"
                )
            expected_status = self.point_status
        else:
            expected_interval = _expected_recovery_interval_status(
                self.upper_confidence_limit,
                self.practical_regression_margin,
            )
            if self.interval_status != expected_interval:
                raise ValueError(
                    "metric interval status disagrees with its limit"
                )
            expected_status = _combined_recovery_status(
                self.point_status,
                expected_interval,
            )
        if self.status != expected_status:
            raise ValueError("metric aggregate status disagrees with evidence")
        if (self.status == "indeterminate") != (self.reason is not None):
            raise ValueError(
                "only indeterminate metrics require an explanatory reason"
            )
        return self


class PhaseFourRecoveryDecision(_EvidenceDocument):
    """Immutable no-compensation Phase 4R campaign decision."""

    evidence_type: Literal["phase-4r-decision"]
    decision_stage: Literal["development", "regression", "qualification"]
    source_campaign_run_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    source_campaign_sha256: str = Field(pattern=_SHA256_PATTERN)
    comparison_protocol_sha256: str = Field(pattern=_SHA256_PATTERN)
    scientific_gates_sha256: str = Field(pattern=_SHA256_PATTERN)
    metric_registry_sha256: str = Field(pattern=_SHA256_PATTERN)
    candidate_identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    reference_identifiers: tuple[str, ...] = Field(min_length=2)
    implementation_outcomes: tuple[PhaseFourImplementationOutcome, ...] = (
        Field(min_length=3)
    )
    metric_decisions: tuple[PhaseFourRecoveryMetricDecision, ...] = Field(
        min_length=1
    )
    absolute_gates: tuple[PhaseFourGateDecision, ...] = Field(min_length=1)
    stronger_hebog_envelopes: tuple[PhaseFourEnvelopeDecision, ...] = Field(
        min_length=1
    )
    passed: bool
    failure_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_recovery_decision(self) -> Self:
        """Require a conjunctive decision with canonical unique identities."""
        if self.reference_identifiers != tuple(
            sorted(set(self.reference_identifiers))
        ):
            raise ValueError(
                "recovery reference identifiers must be canonical"
            )
        keys = [
            (item.metric_id, item.stratum, item.reference_identifier)
            for item in self.metric_decisions
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("recovery metric decision keys must be unique")
        if {
            item.reference_identifier for item in self.metric_decisions
        } != set(self.reference_identifiers):
            raise ValueError(
                "recovery decisions must cover every declared reference"
            )
        if self.failure_reasons != tuple(sorted(set(self.failure_reasons))):
            raise ValueError("recovery failure reasons must be canonical")
        constituent_pass = (
            all(item.status == "pass" for item in self.metric_decisions)
            and all(
                item.status == "pass"
                for item in self.absolute_gates
                if item.role == "gate"
            )
            and all(
                item.status == "pass" for item in self.stronger_hebog_envelopes
            )
            and not any(
                item.failed_seeds and item.policy == "qualification-fails"
                for item in self.implementation_outcomes
            )
        )
        if self.passed != constituent_pass:
            raise ValueError(
                "recovery decision disagrees with its constituents"
            )
        if self.passed == bool(self.failure_reasons):
            raise ValueError(
                "passing recovery cannot have reasons and failure requires "
                "them"
            )
        return self


EvidenceDocument: TypeAlias = (
    BenchmarkEvidence
    | PhaseFiveFilterSelectionEvidence
    | PhaseFiveFilterReviewEvidence
    | ScientificComparisonEvidence
    | CampaignImplementationEvidence
    | ScientificCampaignEvidence
    | PhaseFourQualificationDecision
    | PhaseFourRecoveryDecision
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
