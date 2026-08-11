"""Versioned performance, scalability, behaviour, and scientific contracts.

These records describe gates and test obligations. They do not select an
execution plan or import a scheduler, read science data, or run benchmarks.
"""

from __future__ import annotations

from enum import Enum
from math import isfinite
from pathlib import Path
from statistics import NormalDist
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.evidence import WorkloadClass

_MINIMUM_MATRIX_SIZE = 256
_MAXIMUM_MATRIX_SIZE = 100_000
_DASK_MEMORY_THRESHOLD_COUNT = 4
_PHASE_FOUR_ANALYTIC_FAILURE_CASE_COUNT = 6
_PAIRED_CONFIDENCE_LEVEL = 0.95
_PHASE_FIVE_SELECTED_MINIMUM_SUPPORT = 0.5
_PHASE_FIVE_SELECTED_TRUNCATION_SIGMA = 4.0
_PHASE_FIVE_SELECTED_CONVOLUTION_COUNT = 9
_PHASE_FIVE_SELECTED_TEMPORARY_PLANES = 7
_PHASE_FIVE_REVIEW_DETECTION_SIGMA = 5.0
_PHASE_FIVE_REVIEW_ISLAND_SIGMA = 3.0
_PHASE_FIVE_CORRECTIVE_MAXIMUM_HALO = 14
_PHASE_FIVE_EXTENDED_MAXIMUM_AXIS_BIAS_BEAMS = 0.1
_PHASE_FIVE_EXTENDED_MAXIMUM_RADIAL_P95_BEAMS = 0.5
_POWER_RECOMPUTATION_TOLERANCE = 1e-12
_PHASE_FIVE_REQUIRED_STRATA = {
    "above-compact-deblend-limit",
    "image-edge",
    "invalid-pixels",
    "morphology-artifact",
    "morphology-curved-filament",
    "morphology-diffuse",
    "morphology-filament",
    "morphology-mixed-compact-extended",
    "morphology-shell",
    "scale-1-beam",
    "scale-2-beam",
    "scale-4-beam",
    "tile-boundary",
    "tile-corner",
    "varying-noise",
}


class _ContractModel(BaseModel):
    """Strict immutable base for checked-in contract records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ExecutionBoundary(str, Enum):
    """A performance crossover that requires explicit bracketing cases."""

    DIRECT_TO_LOCAL = "direct-to-local"
    LOCAL_TO_DASK = "local-to-dask"
    DIRECT_TO_CHUNKED_STORAGE = "direct-to-chunked-storage"


class CrossoverProbe(_ContractModel):
    """Initial range in which an execution crossover must be measured."""

    boundary: ExecutionBoundary
    lower_size_pixels: int = Field(ge=1)
    upper_size_pixels: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Require a non-empty ordered probe interval."""
        if self.lower_size_pixels >= self.upper_size_pixels:
            raise ValueError("crossover probe bounds must be increasing")
        return self


class PreviousHebogGate(_ContractModel):
    """Statistical rule for comparing consecutive Hebog baselines."""

    schema_version: Literal[1]
    warmup_repetitions: int = Field(ge=1)
    minimum_measured_repetitions: int = Field(ge=5)
    confidence_level: float = Field(gt=0, lt=1)
    bootstrap_resamples: int = Field(ge=1_000)
    regression_ratio_lower_bound: float = Field(gt=1)


class OneTileOverheadBudget(_ContractModel):
    """Maximum framework overhead for a warm one-tile request."""

    configuration_seconds: float = Field(ge=0)
    fits_io_seconds: float = Field(ge=0)
    partition_planning_seconds: float = Field(ge=0)
    serial_dispatch_seconds: float = Field(ge=0)
    local_dispatch_seconds: float = Field(ge=0)
    dask_dispatch_seconds: float = Field(ge=0)


class PerformanceMatrixContract(_ContractModel):
    """Frozen logarithmic size and scientific-work performance matrix."""

    schema_version: Literal[1]
    matrix_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: Literal["frozen-provisional"]
    sizes_pixels: tuple[int, ...] = Field(min_length=2)
    workload_classes: tuple[WorkloadClass, ...]
    initial_crossover_probes: tuple[CrossoverProbe, ...]
    crossover_bracketing_rule: str = Field(min_length=1)
    released_pybdsf_maximum_ratio: float = Field(gt=0, le=1)
    master_pybdsf_exclusive_ratio_limit: float = Field(gt=0, le=1)
    previous_hebog: PreviousHebogGate
    one_tile_overhead_budget: OneTileOverheadBudget

    @model_validator(mode="after")
    def validate_matrix(self) -> Self:
        """Protect matrix coverage and comparison semantics."""
        if tuple(sorted(set(self.sizes_pixels))) != self.sizes_pixels:
            raise ValueError("performance sizes must be unique and increasing")
        if (
            self.sizes_pixels[0] != _MINIMUM_MATRIX_SIZE
            or self.sizes_pixels[-1] != _MAXIMUM_MATRIX_SIZE
        ):
            raise ValueError("performance matrix must span 256 to 100000")
        if set(self.workload_classes) != set(WorkloadClass):
            raise ValueError(
                "performance matrix must include every workload class"
            )
        if len(set(self.workload_classes)) != len(self.workload_classes):
            raise ValueError("performance workload classes must be unique")
        boundaries = [
            probe.boundary for probe in self.initial_crossover_probes
        ]
        if set(boundaries) != set(ExecutionBoundary):
            raise ValueError(
                "every execution boundary requires an initial probe"
            )
        if len(set(boundaries)) != len(boundaries):
            raise ValueError("execution boundary probes must be unique")
        return self


class StorageContract(_ContractModel):
    """Storage capabilities required by the extreme qualification case."""

    input: Literal["window-readable-fits-or-chunk-addressable"]
    intermediate: Literal["independently-retryable-chunks"]
    output: Literal["chunked-then-compatible-materialisation"]
    shared_storage_identifier: str = Field(min_length=1)
    normal_run_spill_fraction_limit: float = Field(ge=0, le=1)


class ResourceProfile(_ContractModel):
    """Representative admitted resources on one production node."""

    node_memory_bytes: int = Field(ge=1)
    workers_per_node: int = Field(ge=1)
    threads_per_worker: int = Field(ge=1)
    os_scheduler_headroom_bytes: int = Field(ge=0)
    concurrent_pipeline_reserve_bytes: int = Field(ge=0)
    worker_memory_limit_bytes: int = Field(ge=1)
    dask_target_fraction: float = Field(gt=0, lt=1)
    dask_spill_fraction: float = Field(gt=0, lt=1)
    dask_pause_fraction: float = Field(gt=0, lt=1)
    dask_terminate_fraction: float = Field(gt=0, le=1)
    spill_medium: Literal["worker-local-nvme"]

    @model_validator(mode="after")
    def validate_admission(self) -> Self:
        """Keep workers and Dask thresholds inside admitted memory."""
        admitted = (
            self.node_memory_bytes
            - self.os_scheduler_headroom_bytes
            - self.concurrent_pipeline_reserve_bytes
        )
        if admitted <= 0:
            raise ValueError("resource reserves must leave admitted memory")
        if self.workers_per_node * self.worker_memory_limit_bytes > admitted:
            raise ValueError("worker limits exceed admitted node memory")
        thresholds = (
            self.dask_target_fraction,
            self.dask_spill_fraction,
            self.dask_pause_fraction,
            self.dask_terminate_fraction,
        )
        if (
            tuple(sorted(thresholds)) != thresholds
            or len(set(thresholds)) != _DASK_MEMORY_THRESHOLD_COUNT
        ):
            raise ValueError(
                "Dask memory thresholds must be strictly increasing"
            )
        return self


class NodeScalingGate(_ContractModel):
    """Runtime and efficiency limits at one controlled topology."""

    worker_nodes: int = Field(ge=1)
    maximum_runtime_seconds: float = Field(gt=0)
    maximum_scheduler_overhead_fraction: float = Field(ge=0, lt=1)
    minimum_worker_occupancy_fraction: float = Field(ge=0, le=1)
    minimum_strong_scaling_efficiency: float | None = Field(default=None, gt=0)
    minimum_weak_scaling_efficiency: float | None = Field(default=None, gt=0)


class ScalabilityContract(_ContractModel):
    """Frozen contract for the 100,000-square qualification case."""

    schema_version: Literal[1]
    contract_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: Literal["frozen-provisional"]
    logical_shape_yx: tuple[int, int]
    input_planes: tuple[str, ...] = Field(min_length=1)
    output_planes: tuple[str, ...] = Field(min_length=1)
    maximum_live_float32_plane_equivalents: int = Field(ge=1)
    storage: StorageContract
    resource_profile: ResourceProfile
    candidate_tile_core_sizes: tuple[int, ...] = Field(min_length=1)
    maximum_halo_fraction_of_core: float = Field(gt=0, lt=0.5)
    maximum_worker_peak_fraction: float = Field(gt=0, lt=1)
    maximum_graph_tasks: int = Field(ge=1)
    node_gates: tuple[NodeScalingGate, ...]
    tile_batch_policy: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        """Protect the required geometry, topology matrix, and plane names."""
        if self.logical_shape_yx != (_MAXIMUM_MATRIX_SIZE,) * 2:
            raise ValueError(
                "scalability contract must describe 100000 square"
            )
        if len(set(self.input_planes)) != len(self.input_planes):
            raise ValueError("input plane names must be unique")
        if len(set(self.output_planes)) != len(self.output_planes):
            raise ValueError("output plane names must be unique")
        if tuple(sorted(set(self.candidate_tile_core_sizes))) != (
            self.candidate_tile_core_sizes
        ):
            raise ValueError(
                "candidate tile sizes must be unique and increasing"
            )
        nodes = tuple(gate.worker_nodes for gate in self.node_gates)
        if nodes != (1, 10, 50, 100, 200):
            raise ValueError("node gates must cover 1, 10, 50, 100, and 200")
        if self.node_gates[0].minimum_strong_scaling_efficiency is not None:
            raise ValueError(
                "one-node strong-scaling efficiency is the baseline"
            )
        return self


class BehaviourLane(str, Enum):
    """Executable lane owning an unimplemented public behaviour."""

    CONTRACT = "contract"
    ACCEPTANCE = "acceptance"


class PublicBehaviour(_ContractModel):
    """One frozen observable behaviour and its strict-xfail test."""

    identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    lane: BehaviourLane
    scenario: str = Field(min_length=1)
    test_id: str = Field(pattern=r"^test_[a-z0-9_]+$")
    expected_until_implemented: Literal["strict-xfail"]


class PublicBehaviourManifest(_ContractModel):
    """Frozen list of public behaviours that drive red-green-refactor work."""

    schema_version: Literal[1]
    manifest_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: Literal["frozen-provisional"]
    behaviours: tuple[PublicBehaviour, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_behaviours(self) -> Self:
        """Keep scenario and test ownership unambiguous."""
        identifiers = [behaviour.identifier for behaviour in self.behaviours]
        test_ids = [behaviour.test_id for behaviour in self.behaviours]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("public behaviour identifiers must be unique")
        if len(set(test_ids)) != len(test_ids):
            raise ValueError("public behaviour test IDs must be unique")
        return self


class MaskScientificGate(_ContractModel):
    """Minimum foreground-sensitive pixel metrics for one Phase 3 lane."""

    minimum_precision: float = Field(ge=0, le=1)
    minimum_recall: float = Field(ge=0, le=1)
    minimum_intersection_over_union: float = Field(ge=0, le=1)


class IslandScientificGate(_ContractModel):
    """Minimum object recovery and overlap metrics for one Phase 3 lane."""

    minimum_completeness: float = Field(ge=0, le=1)
    minimum_reliability: float = Field(ge=0, le=1)
    minimum_median_intersection_over_union: float = Field(ge=0, le=1)
    minimum_matched_intersection_over_union: float = Field(ge=0, le=1)
    maximum_split_count: int = Field(ge=0)
    maximum_merge_count: int = Field(ge=0)


class PhaseThreeLaneGate(_ContractModel):
    """Mask and connected-object gates for one governed dataset lane."""

    mask: MaskScientificGate
    islands: IslandScientificGate


class PhaseThreeScientificGates(_ContractModel):
    """Reviewed foreground-sensitive Phase 3 non-inferiority margins."""

    schema_version: Literal[1]
    contract_id: Literal["phase-3-scientific-gates"]
    status: Literal["reviewed-provisional"]
    confidence_level: float = Field(gt=0, lt=1)
    low_snr_threshold_crossings: Literal["report-only"]
    compact_reference: PhaseThreeLaneGate
    generated_regression: PhaseThreeLaneGate
    heldout_qualification: PhaseThreeLaneGate


class PhaseFourScopeContract(_ContractModel):
    """Supported scientific image and unit scope for compact measurement."""

    image_kind: Literal["mfs-stokes-i"]
    measurement_plane: Literal["background-subtracted-primary-beam-corrected"]
    brightness_unit: Literal["Jy/beam"]
    frequency_semantics: Literal["reference-frequency-only"]
    invalid_pixels: Literal["excluded-from-membership-and-measurement"]


class PhaseFourMeasurementSemantics(_ContractModel):
    """Frozen meanings for compact catalogue measurements."""

    pixel_solid_angle: Literal[
        "absolute-local-tangent-plane-jacobian-determinant"
    ]
    restoring_beam_solid_angle: Literal[
        "pi-major-fwhm-times-minor-fwhm-over-four-ln-two"
    ]
    island_integrated_flux: Literal[
        "owned-valid-pixel-sum-times-pixel-area-over-beam-area"
    ]
    island_local_rms: Literal["mean-rms-over-owned-valid-pixels"]
    island_mean_brightness: Literal[
        "mean-background-subtracted-brightness-over-owned-valid-pixels"
    ]
    component_peak_flux: Literal["fitted-gaussian-amplitude"]
    component_integrated_flux: Literal[
        "peak-for-unresolved-otherwise-peak-times-fitted-gaussian-area-over-beam-area"
    ]
    component_local_rms: Literal["bilinear-rms-map-at-fitted-centroid"]
    source_flux: Literal["associated-component-flux-for-compact-scope"]


class PhaseFourCoordinateContract(_ContractModel):
    """Pixel, celestial, shape, and uncertainty coordinate conventions."""

    celestial_frame: Literal["icrs"]
    pixel_origin: Literal["zero-based-pixel-centres"]
    pixel_coordinate_order: Literal["x-y"]
    transform: Literal["astropy-local-tangent-plane-jacobian"]
    position_angle: Literal["east-of-north-modulo-180"]
    uncertainty_interpretation: Literal["one-standard-deviation"]


class PhaseFourAssociationContract(_ContractModel):
    """Provisional compact component and source association policy."""

    region_membership: Literal["worker-local-watershed-labels"]
    compact_component_policy: Literal[
        "one-fitted-gaussian-per-deblended-region"
    ]
    compact_source_policy: Literal["one-source-per-deblended-region"]
    parent_policy: Literal["retain-reconciled-parent-island"]
    unsupported_region_policy: Literal["explicit-later-phase-deferral"]
    identifier_policy: Literal[
        "canonical-global-topology-and-association-order"
    ]
    truth_resolvability_policy: Literal["distinct-eligible-observed-maximum"]
    unresolved_truth_policy: Literal["explicit-group-centroid-and-total-flux"]
    joint_model_policy: Literal[
        "deferred-until-identifiability-and-reliability-evidence"
    ]


class PhaseFourFailureContract(_ContractModel):
    """Scientific absence and compatibility sentinel semantics."""

    unresolved_deconvolution: Literal[
        "null-shape-with-unresolved-quality-flag"
    ]
    compatibility_unresolved_shape: Literal["adapter-zero-axes-only"]
    unavailable_uncertainty: Literal["null-with-quality-flag"]
    invalid_measurement: Literal["typed-unavailable-result"]
    omitted_deferred_region: Literal["forbidden-in-complete-result"]


class PhaseFourFittingContract(_ContractModel):
    """Evidence order for nonlinear and selective fitting."""

    reference_policy: Literal["fit-all-admitted-compact-regions"]
    selective_policy: Literal["fit-all-reference-before-selection"]
    moment_policy: Literal["serial-oracle-and-fit-initializer"]
    implementation_selection: Literal[
        "established-library-science-and-complete-stage-evidence"
    ]


class PhaseFourEligibilityContract(_ContractModel):
    """Reference-selected populations and missing-value gate semantics."""

    population_selection: Literal["reference-or-injected-truth-only"]
    missing_candidate_value: Literal["counts-as-unavailable-not-excluded"]
    fitted_shape_eligibility: Literal["reference-fitted-shape-available"]
    deconvolved_shape_eligibility: Literal["reference-resolved-with-shape"]
    position_angle_eligibility: Literal[
        "eligible-reference-shape-axis-ratio-at-least-minimum"
    ]
    position_angle_minimum_axis_ratio: float = Field(gt=1)
    association_eligibility: Literal["reference-parent-association-declared"]
    uncertainty_eligibility: Literal["reference-compact-snr-at-least-10"]
    availability_reporting: Literal["required-for-every-gated-field"]


class PhaseFourMeasurementContract(_ContractModel):
    """Versioned Phase 4 compact measurement contract."""

    schema_version: Literal[2]
    contract_id: Literal["phase-4-measurement"]
    status: Literal["frozen-provisional", "reviewed-provisional"]
    scope: PhaseFourScopeContract
    measurements: PhaseFourMeasurementSemantics
    coordinates: PhaseFourCoordinateContract
    association: PhaseFourAssociationContract
    failures: PhaseFourFailureContract
    fitting: PhaseFourFittingContract
    eligibility: PhaseFourEligibilityContract
    required_analytic_failure_cases: tuple[
        Literal[
            "fit-non-convergence",
            "marginal-deconvolution",
            "non-finite-owned-pixels",
            "non-positive-measurement",
            "singular-covariance",
            "underdetermined-region",
        ],
        ...,
    ] = Field(min_length=6)
    scientific_basis: tuple[str, ...] = Field(min_length=4)
    qualification_policy: Literal["freeze-before-result-inspection"]
    human_scientific_review: Literal["required-before-stable-default"]

    @model_validator(mode="after")
    def validate_scientific_basis(self) -> Self:
        """Require distinct immutable primary-source links."""
        if (
            len(self.required_analytic_failure_cases)
            != _PHASE_FOUR_ANALYTIC_FAILURE_CASE_COUNT
            or len(set(self.required_analytic_failure_cases))
            != _PHASE_FOUR_ANALYTIC_FAILURE_CASE_COUNT
        ):
            raise ValueError(
                "every Phase 4 analytic failure case must appear exactly once"
            )
        if len(set(self.scientific_basis)) != len(self.scientific_basis):
            raise ValueError("scientific basis links must be unique")
        if not all(
            source.startswith("https://") for source in self.scientific_basis
        ):
            raise ValueError("scientific basis links must use HTTPS")
        return self


class PhaseFourCatalogueGate(_ContractModel):
    """Catalogue non-inferiority margins for one governed dataset lane."""

    detection_population: Literal["declared-compact-snr-at-least-10"]
    position_and_flux_population: Literal["isolated-compact-snr-at-least-10"]
    shape_population: Literal["eligible-compact-snr-at-least-10"]
    association_population: Literal[
        "declared-compact-associations-snr-at-least-10"
    ]
    outlier_population: Literal["matched-compact-snr-at-least-10"]
    absolute_median_policy: Literal["gate", "report-only"] = "gate"
    absolute_tail_policy: Literal["gate", "report-only"]
    minimum_completeness: float = Field(ge=0, le=1)
    minimum_reliability: float = Field(ge=0, le=1)
    maximum_median_position_beams: float = Field(ge=0)
    maximum_percentile_95_position_beams: float = Field(ge=0)
    maximum_median_peak_flux_fractional_difference: float = Field(ge=0)
    maximum_percentile_95_peak_flux_fractional_difference: float = Field(ge=0)
    maximum_median_integrated_flux_fractional_difference: float = Field(ge=0)
    maximum_percentile_95_integrated_flux_fractional_difference: float = Field(
        ge=0
    )
    maximum_median_fitted_axis_fractional_difference: float = Field(ge=0)
    maximum_percentile_95_fitted_axis_fractional_difference: float = Field(
        ge=0
    )
    maximum_median_deconvolved_axis_fractional_difference: float = Field(ge=0)
    maximum_percentile_95_deconvolved_axis_fractional_difference: float = (
        Field(ge=0)
    )
    maximum_median_position_angle_difference_degrees: float = Field(ge=0)
    maximum_percentile_95_position_angle_difference_degrees: float = Field(
        ge=0
    )
    minimum_point_source_specificity: float = Field(ge=0, le=1)
    minimum_clear_resolved_classification_recall: float = Field(ge=0, le=1)
    minimum_association_pair_precision: float = Field(ge=0, le=1)
    minimum_association_pair_recall: float = Field(ge=0, le=1)
    minimum_fitted_shape_availability: float = Field(ge=0, le=1)
    minimum_deconvolution_classification_availability: float = Field(
        ge=0, le=1
    )
    minimum_resolved_deconvolved_shape_availability: float = Field(ge=0, le=1)
    minimum_association_identity_availability: float = Field(ge=0, le=1)
    minimum_position_flux_uncertainty_availability: float = Field(ge=0, le=1)
    maximum_catastrophic_outlier_fraction: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_tail_margins(self) -> Self:
        """Keep every 95th-percentile ceiling no tighter than its median."""
        margin_pairs = (
            (
                self.maximum_median_position_beams,
                self.maximum_percentile_95_position_beams,
            ),
            (
                self.maximum_median_peak_flux_fractional_difference,
                self.maximum_percentile_95_peak_flux_fractional_difference,
            ),
            (
                self.maximum_median_integrated_flux_fractional_difference,
                self.maximum_percentile_95_integrated_flux_fractional_difference,
            ),
            (
                self.maximum_median_fitted_axis_fractional_difference,
                self.maximum_percentile_95_fitted_axis_fractional_difference,
            ),
            (
                self.maximum_median_deconvolved_axis_fractional_difference,
                self.maximum_percentile_95_deconvolved_axis_fractional_difference,
            ),
            (
                self.maximum_median_position_angle_difference_degrees,
                self.maximum_percentile_95_position_angle_difference_degrees,
            ),
        )
        if any(tail < median for median, tail in margin_pairs):
            raise ValueError(
                "95th-percentile catalogue margin cannot be tighter than "
                "median"
            )
        return self


class PhaseFourUncertaintyGate(_ContractModel):
    """Calibration gates for reported one-standard-deviation errors."""

    nominal_coverage: float = Field(gt=0, lt=1)
    maximum_absolute_coverage_difference: float = Field(gt=0, lt=1)
    maximum_absolute_mean_normalized_residual: float = Field(gt=0)
    minimum_normalized_residual_standard_deviation: float = Field(gt=0)
    maximum_normalized_residual_standard_deviation: float = Field(gt=0)
    minimum_samples_per_stratum: int = Field(ge=200)
    confidence_interval_level: float = Field(gt=0, lt=1)
    equivalence_rule: Literal["entire-confidence-interval-within-margins"]
    coverage_interval: Literal[
        "wilson-score",
        "cluster-robust-student-t",
    ]
    mean_interval: Literal[
        "student-t",
        "cluster-robust-student-t",
    ]
    dispersion_interval: Literal[
        "scipy-bca-bootstrap-fixed-seed",
        "cluster-percentile-bootstrap-fixed-seed",
    ]
    bootstrap_resamples: int = Field(ge=10_000)
    bootstrap_seed: int = Field(ge=0)
    insufficient_samples: Literal["report-only"]

    @model_validator(mode="after")
    def validate_standard_deviation_range(self) -> Self:
        """Require an increasing calibration-dispersion interval."""
        if (
            self.minimum_normalized_residual_standard_deviation
            >= self.maximum_normalized_residual_standard_deviation
        ):
            raise ValueError(
                "uncertainty standard-deviation bounds must be increasing"
            )
        return self


class PhaseFourUnresolvedGroupGate(_ContractModel):
    """Frozen-provisional margins for one observable unresolved group."""

    status: Literal["frozen-provisional", "reviewed-provisional"]
    population: Literal["declared-unresolved-association-groups"]
    minimum_completeness: float = Field(ge=0, le=1)
    maximum_median_position_beams: float = Field(ge=0)
    maximum_percentile_95_position_beams: float = Field(ge=0)
    maximum_median_integrated_flux_fractional_difference: float = Field(ge=0)
    maximum_percentile_95_integrated_flux_fractional_difference: float = Field(
        ge=0
    )

    @model_validator(mode="after")
    def validate_tail_margins(self) -> Self:
        """Require group tail ceilings to include their median ceilings."""
        if (
            self.maximum_percentile_95_position_beams
            < self.maximum_median_position_beams
            or self.maximum_percentile_95_integrated_flux_fractional_difference
            < self.maximum_median_integrated_flux_fractional_difference
        ):
            raise ValueError(
                "95th-percentile unresolved-group margin cannot be tighter "
                "than median"
            )
        return self


class PhaseFourOutlierDefinition(_ContractModel):
    """Observable thresholds for one catastrophic matched-row outlier."""

    position_beams: float = Field(gt=0)
    peak_flux_fractional_difference: float = Field(gt=0)
    integrated_flux_fractional_difference: float = Field(gt=0)
    fitted_axis_fractional_difference: float = Field(gt=0)
    deconvolved_axis_fractional_difference: float = Field(gt=0)


class PhaseFourExtensionClassification(_ContractModel):
    """Frozen uncertainty-aware point/extended classification policy."""

    method: Literal["integrated-to-peak-ratio-uncertainty"]
    significance_sigma: float = Field(ge=2.0, le=5.0)
    clear_resolved_minimum_area_ratio: float = Field(ge=2.0)
    clear_resolved_minimum_signal_to_noise: float = Field(ge=10.0)
    point_source_population: Literal["shape-unresolved"]
    clear_resolved_population: Literal["shape-clear-resolved"]
    marginal_resolved_population: Literal[
        "shape-marginal-resolved-report-only"
    ]
    marginal_resolved_integrated_flux_catastrophic_rate: Literal["report-only"]
    unresolved_integrated_flux: Literal["peak-flux-density"]
    resolved_integrated_flux_uncertainty: Literal["report-only"]
    missing_uncertainty: Literal[
        "geometric-noiseless-reference-otherwise-unavailable"
    ]


class PhaseFourScientificGates(_ContractModel):
    """Versioned Phase 4 catalogue and uncertainty margins."""

    schema_version: Literal[2]
    contract_id: Literal["phase-4-scientific-gates"]
    status: Literal["frozen-provisional", "reviewed-provisional"]
    confidence_level: float = Field(gt=0, lt=1)
    low_snr_threshold_crossings: Literal["report-only"]
    shape_uncertainty: Literal["report-only"]
    noisy_source_decision: Literal[
        "snr-stratified-confidence-intervals-and-catastrophic-rate"
    ]
    compact_reference: PhaseFourCatalogueGate
    generated_regression: PhaseFourCatalogueGate
    heldout_qualification: PhaseFourCatalogueGate
    extension_classification: PhaseFourExtensionClassification
    unresolved_group: PhaseFourUnresolvedGroupGate
    uncertainty: PhaseFourUncertaintyGate
    catastrophic_outlier: PhaseFourOutlierDefinition


class PhaseFiveScaleDefinition(_ContractModel):
    """Frozen scale sequence and beam-normalized reporting convention."""

    reference: Literal["restoring-beam-major-fwhm"]
    configured_orders: tuple[int, ...] = Field(min_length=1)
    nominal_fwhm_multipliers: tuple[float, ...] = Field(min_length=1)
    maximum_fwhm_multiplier: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_sequence(self) -> Self:
        """Require the governed three-level dyadic compatibility sequence."""
        if self.configured_orders != (1, 2, 3):
            raise ValueError("Phase 5 scale orders must be 1, 2, and 3")
        if self.nominal_fwhm_multipliers != (1.0, 2.0, 4.0):
            raise ValueError(
                "Phase 5 nominal scales must be 1, 2, and 4 beams"
            )
        if self.maximum_fwhm_multiplier != self.nominal_fwhm_multipliers[-1]:
            raise ValueError("maximum Phase 5 scale must equal the last scale")
        return self


class PhaseFiveFilteringContract(_ContractModel):
    """Algorithm-selection boundary and shared-product requirements."""

    family_selection: Literal["phase-5-step-2-evidence"]
    candidates: tuple[
        Literal["undecimated-wavelet", "beam-aware-matched-filter"], ...
    ]
    response_normalization: Literal[
        "unit-integrated-flux-response-in-jy-per-beam"
    ]
    background_rms_reuse: Literal["phase-2-products-no-recursive-estimation"]
    compact_residual_policy: Literal[
        "shared-input-no-complete-compact-pipeline-rerun"
    ]

    @model_validator(mode="after")
    def validate_candidates(self) -> Self:
        """Keep the evidence comparison complete and free of duplicates."""
        if self.candidates != (
            "beam-aware-matched-filter",
            "undecimated-wavelet",
        ):
            raise ValueError("Phase 5 filter candidates must be canonical")
        return self


class PhaseFiveValidityContract(_ContractModel):
    """Masked-support and image-edge semantics for every scale."""

    valid_pixels: Literal["finite-input-background-rms-and-positive-rms"]
    minimum_support_fraction: float = Field(gt=0, le=1)
    masked_support: Literal["renormalize-over-valid-support"]
    image_edge: Literal["renormalize-and-record-visible-support-fraction"]
    insufficient_support: Literal["typed-unavailable-scale-detection"]


class PhaseFiveAssociationContract(_ContractModel):
    """Cross-scale identity and compact-association meanings."""

    identity: Literal["canonical-global-overlap-flux-and-scale-provenance"]
    duplicate_policy: Literal[
        "one-selected-representation-retain-all-contributing-scales"
    ]
    compact_policy: Literal[
        "preserve-isolated-compact-measurement-without-multiscale-evidence"
    ]
    ambiguous_policy: Literal["typed-unresolved-association"]
    tile_policy: Literal["global-identity-independent-of-local-labels"]


class PhaseFiveFailureContract(_ContractModel):
    """Fail-closed semantics for incomplete extended work."""

    unsupported_scale: Literal["configuration-rejected-before-execution"]
    unavailable_measurement: Literal["typed-omission-with-reason"]
    ambiguous_association: Literal["typed-omission-with-reason"]
    deferred_island: Literal["must-reach-terminal-disposition"]
    incomplete_catalogue: Literal["publication-forbidden"]
    unknown_value: Literal["null-never-zero-or-nan-sentinel"]


class PhaseFiveCombinedCatalogueContract(_ContractModel):
    """Composition rules for compact and multiscale catalogue records."""

    catalogue_schema: Literal[
        "source-catalogue-version-2-plus-scale-provenance"
    ]
    compact_only: Literal["byte-identical-when-no-multiscale-evidence"]
    disposition_requirement: Literal[
        "every-accepted-or-deferred-island-has-one-terminal-disposition"
    ]
    reduction: Literal["bounded-canonical-shards-and-pairwise-tree"]
    scheduler_state: Literal["forbidden"]


class PhaseFiveMultiscaleContract(_ContractModel):
    """Versioned Phase 5 scale, ownership, and failure semantics."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-multiscale"]
    status: Literal["reviewed-development"]
    scope: Literal["mfs-stokes-i-rapthor-three-scale-profile"]
    scales: PhaseFiveScaleDefinition
    filtering: PhaseFiveFilteringContract
    validity: PhaseFiveValidityContract
    association: PhaseFiveAssociationContract
    failures: PhaseFiveFailureContract
    combined_catalogue: PhaseFiveCombinedCatalogueContract
    detection_threshold: Literal[
        "source-finder-detection-threshold-on-scale-normalized-response"
    ]
    island_threshold: Literal[
        "source-finder-island-threshold-on-scale-normalized-response"
    ]
    qualification_policy: Literal["freeze-before-result-inspection"]
    development_review: Literal["ai-scientific-review-recorded"]
    independent_human_review: Literal["required-before-cutover"]
    scientific_basis: tuple[str, ...] = Field(min_length=4)

    @model_validator(mode="after")
    def validate_basis(self) -> Self:
        """Keep literature provenance unique and externally resolvable."""
        if len(set(self.scientific_basis)) != len(self.scientific_basis):
            raise ValueError("Phase 5 scientific basis links must be unique")
        if any(
            not link.startswith("https://") for link in self.scientific_basis
        ):
            raise ValueError("Phase 5 scientific basis links must use HTTPS")
        return self


class PhaseFiveLaneGate(_ContractModel):
    """Absolute generated-truth requirements for one Phase 5 lane."""

    minimum_completeness: float = Field(ge=0, le=1)
    minimum_reliability: float = Field(ge=0, le=1)
    maximum_median_integrated_flux_fractional_error: float = Field(ge=0)
    maximum_percentile_95_integrated_flux_fractional_error: float = Field(ge=0)
    maximum_median_position_beams: float = Field(ge=0)
    maximum_percentile_95_position_beams: float = Field(ge=0)
    maximum_duplicate_fraction: float = Field(ge=0, le=1)
    minimum_mask_precision: float = Field(ge=0, le=1)
    minimum_mask_recall: float = Field(ge=0, le=1)
    minimum_mask_intersection_over_union: float = Field(ge=0, le=1)
    maximum_split_fraction: float = Field(ge=0, le=1)
    maximum_merge_fraction: float = Field(ge=0, le=1)
    minimum_rapthor_decision_agreement: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_tails(self) -> Self:
        """Require tail ceilings to contain their median ceilings."""
        if (
            self.maximum_percentile_95_integrated_flux_fractional_error
            < self.maximum_median_integrated_flux_fractional_error
            or self.maximum_percentile_95_position_beams
            < self.maximum_median_position_beams
        ):
            raise ValueError(
                "extended-error tail cannot be tighter than median"
            )
        return self


class PhaseFivePairedMargins(_ContractModel):
    """One-sided practical non-inferiority margins against each reference."""

    maximum_completeness_loss: float = Field(gt=0, lt=1)
    maximum_reliability_loss: float = Field(gt=0, lt=1)
    maximum_integrated_flux_error_increase: float = Field(gt=0)
    maximum_position_error_increase_beams: float = Field(gt=0)
    maximum_duplicate_fraction_increase: float = Field(gt=0, lt=1)
    maximum_mask_intersection_over_union_loss: float = Field(gt=0, lt=1)
    maximum_split_fraction_increase: float = Field(gt=0, lt=1)
    maximum_merge_fraction_increase: float = Field(gt=0, lt=1)
    maximum_rapthor_decision_disagreement_increase: float = Field(gt=0, lt=1)


class PhaseFiveQualificationDesign(_ContractModel):
    """Frozen one-look population and statistical-design requirements."""

    independent_unit: Literal["noise-seed-image"]
    minimum_noise_realizations: int = Field(ge=200)
    minimum_joint_power: float = Field(ge=0.8, lt=1)
    opening_rule: Literal["one-look-terminal-decision"]
    resampling: Literal["whole-image-fixed-seed-bootstrap"]
    bootstrap_resamples: int = Field(ge=10_000)
    bootstrap_seed: int = Field(ge=0)
    failure_policy: Literal["retain-denominator-and-fail-closed"]


class PhaseFiveComparisonContract(_ContractModel):
    """Dual-reference direction and conjunctive decision rule."""

    references: tuple[Literal["released-pybdsf", "pinned-pybdsf-master"], ...]
    rule: Literal["every-absolute-and-paired-gate-passes-no-compensation"]
    paired_interval: Literal["one-sided-95-percent-upper-regression-limit"]
    truth_oracle: Literal["analytic-and-injected-truth"]

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Require both exact references in canonical order."""
        if self.references != (
            "released-pybdsf",
            "pinned-pybdsf-master",
        ):
            raise ValueError("Phase 5 requires both PyBDSF references")
        return self


class PhaseFiveScientificGates(_ContractModel):
    """Reviewed scale-stratified Phase 5 absolute and paired gates."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-scientific-gates"]
    status: Literal["reviewed-development"]
    confidence_level: float = Field(gt=0, lt=1)
    threshold_crossings: Literal["report-only-curves"]
    governed_strata: tuple[str, ...] = Field(min_length=1)
    generated_regression: PhaseFiveLaneGate
    heldout_qualification: PhaseFiveLaneGate
    paired_margins: PhaseFivePairedMargins
    qualification: PhaseFiveQualificationDesign
    comparison: PhaseFiveComparisonContract

    @model_validator(mode="after")
    def validate_governance(self) -> Self:
        """Protect confidence level and the complete governed population."""
        if self.confidence_level != _PAIRED_CONFIDENCE_LEVEL:
            raise ValueError("Phase 5 confidence level must remain 0.95")
        if self.governed_strata != tuple(sorted(_PHASE_FIVE_REQUIRED_STRATA)):
            raise ValueError(
                "Phase 5 governed strata must be complete and canonical"
            )
        return self


class PhaseFiveFilterSelection(_ContractModel):
    """Reviewed development decision for the Phase 5 filter representation."""

    schema_version: Literal[1]
    decision_id: Literal["phase-5-filter-selection"]
    status: Literal["reviewed-development"]
    selected_family: Literal["beam-aware-matched-filter"]
    rejected_family: Literal["undecimated-wavelet"]
    selection_rule: Literal[
        "all-analytic-gates-then-lowest-maintained-bounded-cost"
    ]
    response_normalization: Literal[
        "unit-integrated-flux-response-in-jy-per-beam"
    ]
    minimum_support_fraction: float = Field(gt=0, le=1)
    support_amendment: Literal[
        "phase-5-step-2-edge-evidence-lowered-0.8-to-0.5"
    ]
    truncation_sigma: float = Field(ge=3, le=8)
    maximum_relative_kernel_tail: float = Field(gt=0, lt=1)
    halo_formula: Literal[
        "ceil-truncation-sigma-times-scale-times-beam-major-sigma-pixels"
    ]
    development_halo_pixels: tuple[int, int, int]
    dtype: Literal["float64"]
    convolution_backend: Literal["scipy-signal-fftconvolve"]
    convolution_reuse: Literal[
        "shared-prepared-inputs-no-persisted-response-planes"
    ]
    correlated_noise_model: Literal["restoring-beam-gaussian-covariance"]
    local_noise_propagation: Literal[
        "kernel-squared-rms-scaled-by-correlated-to-independent-gain"
    ]
    convolution_count_per_image: int = Field(ge=1)
    temporary_plane_count: int = Field(ge=1)
    measured_development_images: int = Field(ge=1)
    measured_repetitions: int = Field(ge=5)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lower_precision_authorized: Literal[False]
    native_code_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_selected_design(self) -> Self:
        """Protect the exact reviewed float64 matched-filter implementation."""
        if (
            self.minimum_support_fraction
            != _PHASE_FIVE_SELECTED_MINIMUM_SUPPORT
        ):
            raise ValueError("selected minimum support fraction must be 0.5")
        if self.truncation_sigma != _PHASE_FIVE_SELECTED_TRUNCATION_SIGMA:
            raise ValueError("selected truncation must remain four sigma")
        if self.development_halo_pixels != (9, 17, 34):
            raise ValueError(
                "development halos must match the selected scales"
            )
        if (
            self.convolution_count_per_image
            != _PHASE_FIVE_SELECTED_CONVOLUTION_COUNT
        ):
            raise ValueError("selected filter bank requires nine convolutions")
        if self.temporary_plane_count != _PHASE_FIVE_SELECTED_TEMPORARY_PLANES:
            raise ValueError("selected filter bank requires seven temporaries")
        return self


class PhaseFiveFilterReviewDataset(_ContractModel):
    """One frozen non-qualification population in the paired review."""

    role: Literal["development", "regression"]
    manifest: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_count: int = Field(ge=1)


class PhaseFiveFilterReviewMatrix(_ContractModel):
    """Candidate-neutral cases evaluated before the final filter choice."""

    scale_orders: tuple[int, ...]
    support_fraction_bounds: tuple[float, float]
    mask_geometries: tuple[str, ...] = Field(min_length=6)
    morphologies: tuple[str, ...] = Field(min_length=6)
    snr_levels: tuple[float, ...] = Field(min_length=4)
    noise_models: tuple[str, ...] = Field(min_length=2)
    detection_sigma: float = Field(gt=0)
    island_sigma: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_matrix(self) -> Self:
        """Keep scales, support, SNR, and thresholds predeclared."""
        if self.scale_orders != (1, 2, 3):
            raise ValueError("filter-review scales must be 1, 2, and 3")
        if self.support_fraction_bounds != (0.5, 1.0):
            raise ValueError("filter-review support fraction must span 0.5--1")
        if self.snr_levels != (5.0, 8.0, 15.0, 30.0):
            raise ValueError("filter-review SNR levels must remain canonical")
        if (
            self.detection_sigma != _PHASE_FIVE_REVIEW_DETECTION_SIGMA
            or self.island_sigma != _PHASE_FIVE_REVIEW_ISLAND_SIGMA
        ):
            raise ValueError("filter-review thresholds must remain 5/3 sigma")
        if tuple(sorted(set(self.mask_geometries))) != self.mask_geometries:
            raise ValueError("filter-review mask geometries must be canonical")
        if tuple(sorted(set(self.morphologies))) != self.morphologies:
            raise ValueError("filter-review morphologies must be canonical")
        if tuple(sorted(set(self.noise_models))) != self.noise_models:
            raise ValueError("filter-review noise models must be canonical")
        return self


class PhaseFiveFilterReviewAbsoluteGates(_ContractModel):
    """Absolute truth requirements shared by both filter candidates."""

    maximum_median_response_fractional_error: float = Field(ge=0)
    maximum_percentile_95_response_fractional_error: float = Field(ge=0)
    maximum_median_integrated_flux_fractional_error: float = Field(ge=0)
    maximum_percentile_95_integrated_flux_fractional_error: float = Field(ge=0)
    maximum_noise_std_fractional_error: float = Field(ge=0)
    minimum_support_availability: float = Field(ge=0, le=1)
    minimum_completeness: float = Field(ge=0, le=1)
    minimum_reliability: float = Field(ge=0, le=1)
    maximum_percentile_95_position_beams: float = Field(ge=0)
    minimum_mask_intersection_over_union: float = Field(ge=0, le=1)
    maximum_fragmentation_fraction: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_tails(self) -> Self:
        """Tail ceilings contain their corresponding median ceilings."""
        if (
            self.maximum_percentile_95_response_fractional_error
            < self.maximum_median_response_fractional_error
            or self.maximum_percentile_95_integrated_flux_fractional_error
            < self.maximum_median_integrated_flux_fractional_error
        ):
            raise ValueError(
                "filter-review tail cannot be tighter than median"
            )
        return self


class PhaseFiveFilterReviewPairedMargins(_ContractModel):
    """Practical one-sided candidate-to-candidate non-inferiority margins."""

    maximum_median_response_error_increase: float = Field(gt=0)
    maximum_percentile_95_response_error_increase: float = Field(gt=0)
    maximum_median_integrated_flux_error_increase: float = Field(gt=0)
    maximum_calibrated_snr_fractional_loss: float = Field(gt=0, lt=1)
    maximum_noise_std_error_increase: float = Field(gt=0)
    maximum_completeness_loss: float = Field(gt=0, lt=1)
    maximum_reliability_loss: float = Field(gt=0, lt=1)
    maximum_position_error_increase_beams: float = Field(gt=0)
    maximum_mask_intersection_over_union_loss: float = Field(gt=0, lt=1)
    maximum_fragmentation_fraction_increase: float = Field(gt=0, lt=1)


class PhaseFiveFilterReviewStatistics(_ContractModel):
    """Frozen exact and image-resampled comparison procedures."""

    confidence_level: float = Field(gt=0, lt=1)
    analytic_cases: Literal["exact-no-resampling"]
    generated_cases: Literal["whole-image-fixed-seed-bootstrap"]
    bootstrap_resamples: int = Field(ge=10_000)
    bootstrap_seed: int = Field(ge=0)
    interval: Literal["one-sided-upper-95-percent"]
    minimum_regression_images: int = Field(ge=100)


class PhaseFiveFilterReviewDecisionPolicy(_ContractModel):
    """Fail-closed ordering of science, cost, and optimization."""

    absolute_rule: Literal["every-gate-every-applicable-stratum"]
    paired_rule: Literal["non-inferior-to-other-candidate-no-compensation"]
    scientific_advantage: Literal["select-regardless-of-current-cost"]
    scientific_tie: Literal["lowest-bounded-structural-cost"]
    inconclusive: Literal["select-neither"]
    optimization: Literal["after-selection-only"]


class PhaseFiveFilterReview(_ContractModel):
    """Frozen Step 2B paired scientific representation review."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-filter-paired-review"]
    status: Literal["frozen-before-paired-results"]
    candidates: tuple[
        Literal["beam-aware-matched-filter", "undecimated-wavelet"], ...
    ]
    dataset_manifests: tuple[PhaseFiveFilterReviewDataset, ...]
    matrix: PhaseFiveFilterReviewMatrix
    binding_metrics: tuple[str, ...] = Field(min_length=10)
    diagnostic_metrics: tuple[str, ...] = Field(min_length=2)
    absolute_gates: PhaseFiveFilterReviewAbsoluteGates
    paired_margins: PhaseFiveFilterReviewPairedMargins
    statistical_design: PhaseFiveFilterReviewStatistics
    decision_policy: PhaseFiveFilterReviewDecisionPolicy
    step_three_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        """Protect candidates, populations, and complete metric governance."""
        if self.candidates != (
            "beam-aware-matched-filter",
            "undecimated-wavelet",
        ):
            raise ValueError("filter-review candidates must be canonical")
        if tuple(item.role for item in self.dataset_manifests) != (
            "development",
            "regression",
        ):
            raise ValueError(
                "filter review requires development and regression manifests"
            )
        expected_metrics = {
            "calibrated-response-snr",
            "completeness",
            "fragmentation-fraction",
            "integrated-flux-fractional-error",
            "mask-intersection-over-union",
            "noise-standard-deviation-error",
            "position-error-beams",
            "reliability",
            "response-fractional-error",
            "support-availability",
        }
        if set(self.binding_metrics) != expected_metrics or len(
            self.binding_metrics
        ) != len(expected_metrics):
            raise ValueError("filter-review binding metrics must be complete")
        if tuple(sorted(set(self.binding_metrics))) != self.binding_metrics:
            raise ValueError("filter-review binding metrics must be canonical")
        if (
            tuple(sorted(set(self.diagnostic_metrics)))
            != self.diagnostic_metrics
        ):
            raise ValueError(
                "filter-review diagnostic metrics must be canonical"
            )
        if (
            self.statistical_design.confidence_level
            != _PAIRED_CONFIDENCE_LEVEL
        ):
            raise ValueError("filter-review confidence level must remain 0.95")
        return self


class PhaseFiveCorrectiveResponseEndpoint(_ContractModel):
    """Candidate-neutral Step 2C response meaning at final output."""

    signal: Literal["final-reconstructed-signal"]
    truth: Literal["observable-valid-domain-truth"]
    statistic: Literal["integrated-original-pixel-signal"]
    truncation: Literal["reported-not-imputed"]


class PhaseFiveCorrectiveMeasurement(_ContractModel):
    """Frozen separation of detection, segmentation, and measurement."""

    mask: Literal["original-residual-seed-and-grow"]
    photometry: Literal["original-residual-pixels"]
    astrometry: Literal["original-residual-pixels"]
    wavelet_coefficients: Literal["detection-and-association-provenance-only"]


class PhaseFiveCorrectiveDesign(_ContractModel):
    """Scientifically familiar residual-wavelet corrective design."""

    compact_treatment: Literal["exclude-or-subtract-accepted-compact-emission"]
    wavelet: Literal["normalized-b3-spline-atrous"]
    noise: Literal["per-scale-correlated-local-rms"]
    support: Literal["per-scale-normalized-valid-support"]
    reconstruction: Literal["significant-adjacent-scale-support"]
    matched_filter_role: Literal[
        "known-template-seed-aid-and-governed-comparator"
    ]


class PhaseFiveCorrectiveBoundedImplementation(_ContractModel):
    """Frozen serial cost and storage boundaries for the corrective screen."""

    kernel: Literal["separable-sparse-b3-spline"]
    scale_dilations_pixels: tuple[int, ...]
    maximum_halo_pixels: int
    shared_adjacent_smoothings: Literal[True]
    durable_response_bank: Literal[False]
    dtype: Literal["float64"]
    optimization: Literal["profile-after-scientific-selection"]

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Protect the reviewed three-scale finite-halo construction."""
        if self.scale_dilations_pixels != (1, 2, 4):
            raise ValueError("corrective B3 dilations must be 1, 2, and 4")
        if self.maximum_halo_pixels != _PHASE_FIVE_CORRECTIVE_MAXIMUM_HALO:
            raise ValueError("corrective cumulative halo must be 14 pixels")
        return self


class PhaseFiveCorrectiveReview(_ContractModel):
    """Frozen Step 2C corrective continuum re-evaluation contract."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-corrective-review"]
    status: Literal["frozen-before-corrective-results"]
    prior_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[
        Literal["beam-aware-matched-filter", "residual-b3-atrous"], ...
    ]
    dataset_manifests: tuple[PhaseFiveFilterReviewDataset, ...]
    matrix: PhaseFiveFilterReviewMatrix
    binding_metrics: tuple[str, ...] = Field(min_length=10)
    diagnostic_metrics: tuple[str, ...] = Field(min_length=2)
    absolute_gates: PhaseFiveFilterReviewAbsoluteGates
    paired_margins: PhaseFiveFilterReviewPairedMargins
    statistical_design: PhaseFiveFilterReviewStatistics
    decision_policy: PhaseFiveFilterReviewDecisionPolicy
    response_endpoint: PhaseFiveCorrectiveResponseEndpoint
    final_measurement: PhaseFiveCorrectiveMeasurement
    corrective_design: PhaseFiveCorrectiveDesign
    bounded_implementation: PhaseFiveCorrectiveBoundedImplementation
    step_three_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_corrective_review(self) -> Self:
        """Freeze the prior populations, metrics, gates, and paired margins."""
        if self.candidates != (
            "beam-aware-matched-filter",
            "residual-b3-atrous",
        ):
            raise ValueError("corrective-review candidates must be canonical")
        expected_datasets = (
            (
                "development",
                "config/datasets/phase-5-development.json",
                "b3c9594efa0c39ce30f3b287988f3fca90f69c5ccb8507adc463b37fed0b8350",
                10,
            ),
            (
                "regression",
                "config/datasets/phase-5-regression.json",
                "7188b1c65b7d193e27f5bca3cf5b427874f97cea87fb206000a591460f95b85e",
                100,
            ),
        )
        observed_datasets = tuple(
            (item.role, item.manifest, item.manifest_sha256, item.image_count)
            for item in self.dataset_manifests
        )
        if observed_datasets != expected_datasets:
            raise ValueError(
                "corrective review requires unchanged Step 2B populations"
            )
        expected_metrics = {
            "calibrated-response-snr",
            "completeness",
            "fragmentation-fraction",
            "integrated-flux-fractional-error",
            "mask-intersection-over-union",
            "noise-standard-deviation-error",
            "position-error-beams",
            "reliability",
            "response-fractional-error",
            "support-availability",
        }
        if (
            set(self.binding_metrics) != expected_metrics
            or tuple(sorted(expected_metrics)) != self.binding_metrics
        ):
            raise ValueError("corrective-review metrics must remain canonical")
        expected_gates = {
            "maximum_median_response_fractional_error": 0.05,
            "maximum_percentile_95_response_fractional_error": 0.1,
            "maximum_median_integrated_flux_fractional_error": 0.1,
            "maximum_percentile_95_integrated_flux_fractional_error": 0.25,
            "maximum_noise_std_fractional_error": 0.15,
            "minimum_support_availability": 0.95,
            "minimum_completeness": 0.9,
            "minimum_reliability": 0.95,
            "maximum_percentile_95_position_beams": 0.25,
            "minimum_mask_intersection_over_union": 0.8,
            "maximum_fragmentation_fraction": 0.1,
        }
        expected_margins = {
            "maximum_median_response_error_increase": 0.02,
            "maximum_percentile_95_response_error_increase": 0.05,
            "maximum_median_integrated_flux_error_increase": 0.05,
            "maximum_calibrated_snr_fractional_loss": 0.1,
            "maximum_noise_std_error_increase": 0.05,
            "maximum_completeness_loss": 0.02,
            "maximum_reliability_loss": 0.02,
            "maximum_position_error_increase_beams": 0.05,
            "maximum_mask_intersection_over_union_loss": 0.05,
            "maximum_fragmentation_fraction_increase": 0.02,
        }
        if self.absolute_gates.model_dump() != expected_gates or (
            self.paired_margins.model_dump() != expected_margins
        ):
            raise ValueError(
                "corrective review requires unchanged Step 2B gates"
            )
        if (
            self.statistical_design.confidence_level
            != _PAIRED_CONFIDENCE_LEVEL
        ):
            raise ValueError("corrective-review confidence must remain 0.95")
        return self


class PhaseFiveCorrectiveRCorrections(_ContractModel):
    """Frozen Step 2C-R corrections to final-output semantics."""

    astrometry: Literal[
        "one-rms-excess-central-eighty-percent-original-pixel-estimator"
    ]
    astrometry_topology: Literal[
        "equal-centre-of-three-or-more-ten-percent-components"
    ]
    truncation_astrometry: Literal[
        "robust-except-noiseless-or-below-eight-sigma-observable-moment"
    ]
    association: Literal["three-beam-adjacent-scale-support-linkage"]
    artifact_disposition: Literal["known-artifact-control-not-photometric"]
    false_positive_control: Literal[
        "one-correlated-beam-or-direct-five-sigma-seed"
    ]
    astrometry_dilation_pixels: int
    association_distance_beams: float
    component_flux_fraction: float
    minimum_island_area_beams: float
    minimum_direct_seed_sigma: float

    @model_validator(mode="after")
    def validate_corrections(self) -> Self:
        """Keep all development-selected correction constants exact."""
        expected = (2, 3.0, 0.1, 1.0, 5.0)
        observed = (
            self.astrometry_dilation_pixels,
            self.association_distance_beams,
            self.component_flux_fraction,
            self.minimum_island_area_beams,
            self.minimum_direct_seed_sigma,
        )
        if observed != expected:
            raise ValueError("corrective-R constants must remain frozen")
        return self


class PhaseFiveCorrectiveRReview(_ContractModel):
    """Frozen Step 2C-R final-output correction review contract."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-corrective-r-review"]
    status: Literal["frozen-before-corrective-r-results"]
    prior_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[
        Literal["beam-aware-matched-filter", "residual-b3-atrous"], ...
    ]
    dataset_manifests: tuple[PhaseFiveFilterReviewDataset, ...]
    matrix: PhaseFiveFilterReviewMatrix
    binding_metrics: tuple[str, ...] = Field(min_length=10)
    diagnostic_metrics: tuple[str, ...] = Field(min_length=2)
    absolute_gates: PhaseFiveFilterReviewAbsoluteGates
    paired_margins: PhaseFiveFilterReviewPairedMargins
    statistical_design: PhaseFiveFilterReviewStatistics
    decision_policy: PhaseFiveFilterReviewDecisionPolicy
    response_endpoint: PhaseFiveCorrectiveResponseEndpoint
    final_measurement: PhaseFiveCorrectiveMeasurement
    corrective_design: PhaseFiveCorrectiveDesign
    bounded_implementation: PhaseFiveCorrectiveBoundedImplementation
    precheck_amendment: Literal[
        "retain-direct-five-sigma-islands-after-area-floor-failed-analytic"
    ]
    supersedes_failed_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corrections: PhaseFiveCorrectiveRCorrections
    step_three_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_inherited_review(self) -> Self:
        """Reuse every unchanged Step 2C population, metric, and gate check."""
        payload = self.model_dump(
            exclude={
                "precheck_amendment",
                "supersedes_failed_protocol_sha256",
                "corrections",
            }
        )
        payload["contract_id"] = "phase-5-corrective-review"
        payload["status"] = "frozen-before-corrective-results"
        PhaseFiveCorrectiveReview.model_validate(payload)
        return self


class PhaseFiveCorrectiveAEstimator(_ContractModel):
    """Frozen Step 2C-A model-assisted original-pixel estimator."""

    family: Literal[
        "local-rms-weighted-multigaussian-observable-centroid-shrinkage"
    ]
    pixel_domain: Literal["original-residual-pixels"]
    target: Literal["observable-valid-domain-flux-centroid"]
    peak_selection: Literal["beam-separated-original-pixel-local-maxima"]
    loss: Literal["soft-l1-local-rms-standardized"]
    fallback: Literal["step-2c-r-robust-observable-moment"]
    uncertainty: Literal["correlated-noise-moment-propagation"]
    peak_seed_sigma: float
    peak_separation_beams: float
    maximum_components: int
    fit_margin_beams: float
    component_centre_bound_beams: float
    minimum_sigma_minor_fwhm_divisor: float
    maximum_sigma_major_beams: float
    maximum_iterations: int
    model_weight: float
    maximum_normalized_cost: float
    maximum_model_moment_disagreement_beams: float

    @model_validator(mode="after")
    def validate_estimator(self) -> Self:
        """Keep every development-selected estimator constant exact."""
        expected = (6.0, 2.0, 6, 3.0, 1.0, 2.355, 3.0, 300, 0.5, 2.0, 1.0)
        observed = (
            self.peak_seed_sigma,
            self.peak_separation_beams,
            self.maximum_components,
            self.fit_margin_beams,
            self.component_centre_bound_beams,
            self.minimum_sigma_minor_fwhm_divisor,
            self.maximum_sigma_major_beams,
            self.maximum_iterations,
            self.model_weight,
            self.maximum_normalized_cost,
            self.maximum_model_moment_disagreement_beams,
        )
        if observed != expected:
            raise ValueError(
                "corrective-A estimator constants must remain frozen"
            )
        return self


class PhaseFiveCorrectiveAReview(_ContractModel):
    """Frozen independent Step 2C-A astrometry confirmation contract."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-corrective-a-review"]
    status: Literal["frozen-before-corrective-a-results"]
    prior_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[
        Literal["beam-aware-matched-filter", "residual-b3-atrous"], ...
    ]
    dataset_manifests: tuple[PhaseFiveFilterReviewDataset, ...]
    matrix: PhaseFiveFilterReviewMatrix
    binding_metrics: tuple[str, ...] = Field(min_length=10)
    diagnostic_metrics: tuple[str, ...] = Field(min_length=2)
    absolute_gates: PhaseFiveFilterReviewAbsoluteGates
    paired_margins: PhaseFiveFilterReviewPairedMargins
    statistical_design: PhaseFiveFilterReviewStatistics
    decision_policy: PhaseFiveFilterReviewDecisionPolicy
    response_endpoint: PhaseFiveCorrectiveResponseEndpoint
    final_measurement: PhaseFiveCorrectiveMeasurement
    corrective_design: PhaseFiveCorrectiveDesign
    bounded_implementation: PhaseFiveCorrectiveBoundedImplementation
    precheck_amendment: Literal[
        "retain-direct-five-sigma-islands-after-area-floor-failed-analytic"
    ]
    supersedes_failed_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corrections: PhaseFiveCorrectiveRCorrections
    supersedes_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    astrometry_estimator: PhaseFiveCorrectiveAEstimator
    confirmation_reuse: Literal["one-look-no-tuning-or-rescoring"]
    step_three_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_inherited_review(self) -> Self:
        """Preserve Step 2C-R semantics while replacing only astrometry."""
        observed_datasets = tuple(
            (item.role, item.manifest, item.manifest_sha256, item.image_count)
            for item in self.dataset_manifests
        )
        expected_datasets = (
            (
                "development",
                "config/datasets/phase-5-development.json",
                "b3c9594efa0c39ce30f3b287988f3fca90f69c5ccb8507adc463b37fed0b8350",
                10,
            ),
            (
                "regression",
                "config/datasets/phase-5-corrective-a-confirmation.json",
                "7576f8e6e373b12a42c9820ee381750c32208444682bde4a52a1311cccfc6011",
                100,
            ),
        )
        if observed_datasets != expected_datasets:
            raise ValueError("corrective-A datasets must remain frozen")
        payload = self.model_dump(
            exclude={
                "astrometry_estimator",
                "confirmation_reuse",
                "supersedes_protocol_sha256",
            }
        )
        payload["contract_id"] = "phase-5-corrective-r-review"
        payload["status"] = "frozen-before-corrective-r-results"
        payload["prior_decision_sha256"] = (
            "7d50397bc679b06dd856e9484675e4981eee55448c87acc96ff9d249e41d4684"
        )
        payload["dataset_manifests"] = (
            self.dataset_manifests[0].model_dump(mode="json"),
            {
                "role": "regression",
                "manifest": "config/datasets/phase-5-regression.json",
                "manifest_sha256": (
                    "7188b1c65b7d193e27f5bca3cf5b427874f97cea87fb206000a591460f95b85e"
                ),
                "image_count": 100,
            },
        )
        PhaseFiveCorrectiveRReview.model_validate(payload)
        return self


class PhaseFiveCorrectiveCandidateDecision(_ContractModel):
    """Conjunctive Step 2C outcome for one governed representation."""

    family: Literal["beam-aware-matched-filter", "residual-b3-atrous"]
    passes_absolute: Literal[False]
    noninferior_to_other: Literal[False]
    failed_absolute_endpoint_count: int = Field(ge=1)
    failed_paired_endpoint_count: int = Field(ge=1)
    bounded_cost: tuple[int, int, int]

    @model_validator(mode="after")
    def validate_cost(self) -> Self:
        """Require complete positive structural-cost diagnostics."""
        if any(value <= 0 for value in self.bounded_cost):
            raise ValueError("corrective-decision costs must be positive")
        return self


class PhaseFiveCorrectiveDecision(_ContractModel):
    """Reviewed fail-closed decision produced by the Step 2C review."""

    schema_version: Literal[1]
    decision_id: Literal["phase-5-corrective-decision"]
    status: Literal["reviewed-rejected"]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[PhaseFiveCorrectiveCandidateDecision, ...]
    decision: Literal["reject-corrective"]
    selected_family: None
    corrective_failure_domains: tuple[
        Literal[
            "artifact-flux",
            "astrometry",
            "fragmentation",
            "reliability",
        ],
        ...,
    ]
    named_review: Literal["codex-step-2c-governed-evidence-review"]
    review_scope: Literal[
        "technical-and-governed-development-regression-evidence"
    ]
    independent_human_scientific_review: Literal["still-required"]
    next_action: Literal[
        "redesign-measurement-association-and-false-positive-control"
    ]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_rejected_decision(self) -> Self:
        """Require both failed candidates and preserve all closed gates."""
        if tuple(item.family for item in self.candidates) != (
            "beam-aware-matched-filter",
            "residual-b3-atrous",
        ):
            raise ValueError(
                "corrective decision requires canonical candidates"
            )
        if self.corrective_failure_domains != (
            "artifact-flux",
            "astrometry",
            "fragmentation",
            "reliability",
        ):
            raise ValueError(
                "corrective failure domains must remain complete and canonical"
            )
        return self


class PhaseFiveCorrectiveRCandidateDecision(_ContractModel):
    """Conjunctive Step 2C-R result for one governed representation."""

    family: Literal["beam-aware-matched-filter", "residual-b3-atrous"]
    passes_absolute: bool
    noninferior_to_other: bool
    failed_absolute_endpoint_count: int = Field(ge=0)
    failed_paired_endpoint_count: int = Field(ge=0)
    bounded_cost: tuple[int, int, int]

    @model_validator(mode="after")
    def validate_cost(self) -> Self:
        """Require complete positive structural-cost diagnostics."""
        if any(value <= 0 for value in self.bounded_cost):
            raise ValueError("corrective-R decision costs must be positive")
        return self


class PhaseFiveCorrectiveRDecision(_ContractModel):
    """Reviewed fail-closed decision produced by the Step 2C-R review."""

    schema_version: Literal[1]
    decision_id: Literal["phase-5-corrective-r-decision"]
    status: Literal["reviewed-rejected"]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[PhaseFiveCorrectiveRCandidateDecision, ...]
    decision: Literal["reject-corrective-r"]
    selected_family: None
    corrective_failure_domains: tuple[Literal["astrometry-variance"], ...]
    named_review: Literal["codex-step-2c-r-governed-evidence-review"]
    review_scope: Literal[
        "technical-and-governed-development-regression-evidence"
    ]
    independent_human_scientific_review: Literal["still-required"]
    next_action: Literal["freeze-independent-astrometry-estimator-review"]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_rejected_decision(self) -> Self:
        """Bind the reviewed failure counts and sole residual domain."""
        expected = (
            ("beam-aware-matched-filter", False, False, 18, 9),
            ("residual-b3-atrous", False, True, 9, 0),
        )
        observed = tuple(
            (
                item.family,
                item.passes_absolute,
                item.noninferior_to_other,
                item.failed_absolute_endpoint_count,
                item.failed_paired_endpoint_count,
            )
            for item in self.candidates
        )
        if observed != expected:
            raise ValueError("corrective-R decision counts must remain exact")
        if self.corrective_failure_domains != ("astrometry-variance",):
            raise ValueError("corrective-R failure domain must remain exact")
        return self


class PhaseFiveCorrectiveACandidateDecision(_ContractModel):
    """Conjunctive Step 2C-A result for one governed representation."""

    family: Literal["beam-aware-matched-filter", "residual-b3-atrous"]
    passes_absolute: bool
    noninferior_to_other: bool
    failed_absolute_endpoint_count: int = Field(ge=0)
    failed_paired_endpoint_count: int = Field(ge=0)
    bounded_cost: tuple[int, int, int]

    @model_validator(mode="after")
    def validate_cost(self) -> Self:
        """Require complete positive structural-cost diagnostics."""
        if any(value <= 0 for value in self.bounded_cost):
            raise ValueError("corrective-A decision costs must be positive")
        return self


class PhaseFiveCorrectiveADecision(_ContractModel):
    """Reviewed fail-closed decision from the one-look Step 2C-A review."""

    schema_version: Literal[1]
    decision_id: Literal["phase-5-corrective-a-decision"]
    status: Literal["reviewed-rejected"]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[PhaseFiveCorrectiveACandidateDecision, ...]
    decision: Literal["reject-corrective-a"]
    selected_family: None
    corrective_failure_domains: tuple[
        Literal[
            "astrometry-curved-filament-variance",
            "astrometry-uncertainty-undercoverage",
        ],
        ...,
    ]
    named_review: Literal["codex-step-2c-a-one-look-governed-evidence-review"]
    review_scope: Literal[
        "technical-and-governed-independent-confirmation-evidence"
    ]
    independent_human_scientific_review: Literal[
        "required-before-any-further-astrometry-revision"
    ]
    next_action: Literal[
        "human-scientific-review-of-astrometry-endpoint-and-estimator"
    ]
    confirmation_reuse: Literal["closed-after-one-look"]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_rejected_decision(self) -> Self:
        """Bind the one-look counts and residual scientific concerns."""
        expected = (
            ("beam-aware-matched-filter", False, False, 14, 9),
            ("residual-b3-atrous", False, True, 5, 0),
        )
        observed = tuple(
            (
                item.family,
                item.passes_absolute,
                item.noninferior_to_other,
                item.failed_absolute_endpoint_count,
                item.failed_paired_endpoint_count,
            )
            for item in self.candidates
        )
        if observed != expected:
            raise ValueError("corrective-A decision counts must remain exact")
        expected_domains = (
            "astrometry-curved-filament-variance",
            "astrometry-uncertainty-undercoverage",
        )
        if self.corrective_failure_domains != expected_domains:
            raise ValueError("corrective-A failure domains must remain exact")
        return self


class PhaseFiveAstrometryHumanDecision(_ContractModel):
    """Human approval of the prospective Step 2C-H astrometry revision."""

    schema_version: Literal[1]
    decision_id: Literal["phase-5-astrometry-human-decision"]
    status: Literal["approved-prospective-revision"]
    prior_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pre_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: Literal["Gemma Danks"]
    review_source: Literal["interactive-project-owner-approval"]
    reviewed_on: Literal["2026-08-09"]
    decision: Literal["approve-recommendations-for-prospective-implementation"]
    approved_recommendations: tuple[
        Literal[
            "direct-group-median-and-p95-with-image-cluster-resampling",
            "observable-domain-flux-centroid-with-explicit-external-mappings",
            "direct-pixel-baseline-with-evidence-gated-model-assistance",
            "two-dimensional-correlated-noise-position-covariance",
            "morphology-stratified-coverage-validation",
            "fresh-development-and-confirmation-populations",
        ],
        ...,
    ]
    closed_confirmation_policy: Literal[
        "no-tuning-rescoring-or-reconfirmation"
    ]
    successor_protocol_freeze_authorized: Literal[True]
    development_execution_authorized: Literal[True]
    confirmation_execution_authorized: Literal[False]
    next_action: Literal[
        "freeze-successor-astrometry-development-and-confirmation-protocol"
    ]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_approval_scope(self) -> Self:
        """Require the complete approved recommendations in review order."""
        expected = (
            "direct-group-median-and-p95-with-image-cluster-resampling",
            "observable-domain-flux-centroid-with-explicit-external-mappings",
            "direct-pixel-baseline-with-evidence-gated-model-assistance",
            "two-dimensional-correlated-noise-position-covariance",
            "morphology-stratified-coverage-validation",
            "fresh-development-and-confirmation-populations",
        )
        if self.approved_recommendations != expected:
            raise ValueError(
                "approved astrometry recommendations must remain complete "
                "and ordered"
            )
        return self


class PhaseFiveAstrometryEndpointProtocol(_ContractModel):
    """Approved catalogue-level position estimand and resampling rule."""

    target: Literal["observable-valid-domain-flux-centroid"]
    observation_unit: Literal["eligible-astronomical-truth-group"]
    independent_unit: Literal["noise-seed-image"]
    statistics: tuple[Literal["median", "percentile-95"], ...]
    resampling: Literal["whole-image-cluster-bootstrap-retain-all-groups"]
    bootstrap_resamples: int
    bootstrap_seed: int
    confidence_level: float
    absolute_gate_rule: Literal[
        "point-estimate-with-one-sided-confidence-bound-reported"
    ]
    maximum_median_position_beams: float
    maximum_percentile_95_position_beams: float
    per_image_risk_metric: Literal["separate-report-only-maximum"]

    @model_validator(mode="after")
    def validate_endpoint(self) -> Self:
        """Keep the approved direct catalogue estimand exact."""
        observed = (
            self.statistics,
            self.bootstrap_resamples,
            self.bootstrap_seed,
            self.confidence_level,
            self.maximum_median_position_beams,
            self.maximum_percentile_95_position_beams,
        )
        expected = (
            ("median", "percentile-95"),
            10_000,
            20260809,
            0.95,
            0.1,
            0.25,
        )
        if observed != expected:
            raise ValueError(
                "astrometry endpoint constants must remain frozen"
            )
        return self


class PhaseFiveAstrometryUncertaintyProtocol(_ContractModel):
    """Two-dimensional correlated-noise uncertainty and coverage design."""

    covariance_shape: Literal["two-by-two"]
    covariance_coordinates: tuple[Literal["pixel", "sky"], ...]
    pixel_covariance_method: Literal[
        "delta-method-full-gaussian-beam-correlation"
    ]
    sky_transform: Literal["local-wcs-jacobian"]
    nonlinear_calibration: Literal["repeated-correlated-noise-injections"]
    calibration_statistic: Literal["mahalanobis-chi-square-two"]
    coverage_levels: tuple[float, ...]
    maximum_absolute_coverage_error: tuple[float, ...]
    require_positive_definite_fraction: float
    coverage_strata: tuple[
        Literal[
            "morphology",
            "signal-to-noise",
            "scale",
            "image-edge",
            "invalid-pixels",
            "truncation",
            "estimator-disposition",
        ],
        ...,
    ]

    @model_validator(mode="after")
    def validate_uncertainty(self) -> Self:
        """Require calibrated two-dimensional uncertainty without gaps."""
        if self.covariance_coordinates != ("pixel", "sky"):
            raise ValueError("astrometry covariance coordinates must be exact")
        if self.coverage_levels != (0.68, 0.95):
            raise ValueError("astrometry coverage levels must remain frozen")
        if self.maximum_absolute_coverage_error != (0.1, 0.05):
            raise ValueError(
                "astrometry coverage tolerances must remain frozen"
            )
        if self.require_positive_definite_fraction != 1.0:
            raise ValueError("every astrometry covariance must be positive")
        expected_strata = (
            "morphology",
            "signal-to-noise",
            "scale",
            "image-edge",
            "invalid-pixels",
            "truncation",
            "estimator-disposition",
        )
        if self.coverage_strata != expected_strata:
            raise ValueError("astrometry coverage strata must remain complete")
        return self


class PhaseFiveAstrometrySelectionProtocol(_ContractModel):
    """Development-only choice and model-admission policy."""

    selection_population: Literal["fresh-development-only"]
    absolute_and_coverage_rule: Literal[
        "every-endpoint-and-stratum-passes-no-compensation"
    ]
    preference: Literal["prefer-direct-unless-model-materially-improves-tail"]
    minimum_model_p95_improvement_beams: float
    maximum_model_unavailable_fraction: float
    maximum_model_inadequate_fraction: float
    confirmation_policy: Literal[
        "freeze-selected-estimator-before-one-look-confirmation"
    ]

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        """Protect the simple-baseline preference and model safeguards."""
        observed = (
            self.minimum_model_p95_improvement_beams,
            self.maximum_model_unavailable_fraction,
            self.maximum_model_inadequate_fraction,
        )
        if observed != (0.02, 0.01, 0.05):
            raise ValueError(
                "astrometry selection constants must remain frozen"
            )
        return self


class PhaseFiveAstrometryRevisionReview(_ContractModel):
    """Frozen successor astrometry development and confirmation design."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-astrometry-revision-review"]
    status: Literal["frozen-before-astrometry-development-results"]
    human_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    closed_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    closed_confirmation_policy: Literal[
        "no-tuning-rescoring-or-reconfirmation"
    ]
    dataset_manifests: tuple[PhaseFiveFilterReviewDataset, ...]
    estimator_candidates: tuple[
        Literal[
            "direct-observable-pixel-centroid",
            "covariance-gated-model-assisted-centroid",
        ],
        ...,
    ]
    endpoint: PhaseFiveAstrometryEndpointProtocol
    uncertainty: PhaseFiveAstrometryUncertaintyProtocol
    selection: PhaseFiveAstrometrySelectionProtocol
    external_position_mappings: tuple[
        Literal[
            "pybdsf-source-moment-centroid-where-semantically-aligned",
            "aegean-component-centre-compact-gaussian-scope-only",
            "no-aegean-irregular-island-position-binding",
        ],
        ...,
    ]
    development_execution_authorized: Literal[True]
    confirmation_execution_authorized: Literal[False]
    step_two_c_p_execution_authorized: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        """Bind fresh populations, candidates, and external semantics."""
        expected_datasets = (
            (
                "development",
                "config/datasets/phase-5-astrometry-development.json",
                40,
            ),
            (
                "regression",
                "config/datasets/phase-5-astrometry-confirmation.json",
                400,
            ),
        )
        observed_datasets = tuple(
            (item.role, item.manifest, item.image_count)
            for item in self.dataset_manifests
        )
        if observed_datasets != expected_datasets:
            raise ValueError("astrometry revision datasets must remain frozen")
        if self.estimator_candidates != (
            "direct-observable-pixel-centroid",
            "covariance-gated-model-assisted-centroid",
        ):
            raise ValueError(
                "astrometry estimator candidates must remain exact"
            )
        expected_mappings = (
            "pybdsf-source-moment-centroid-where-semantically-aligned",
            "aegean-component-centre-compact-gaussian-scope-only",
            "no-aegean-irregular-island-position-binding",
        )
        if self.external_position_mappings != expected_mappings:
            raise ValueError("external astrometry mappings must remain exact")
        return self


class PhaseFiveAstrometrySelectionCandidate(_ContractModel):
    """One development-only successor estimator conclusion."""

    candidate: Literal[
        "direct-observable-pixel-centroid",
        "covariance-gated-model-assisted-centroid",
    ]
    covariance_scale: float = Field(gt=0, allow_inf_nan=False)
    overall_percentile_95_beams: float = Field(ge=0, allow_inf_nan=False)
    unavailable_fraction: float = Field(ge=0, le=1, allow_inf_nan=False)
    model_unavailable_fraction: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    model_inadequate_fraction: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    failed_endpoint_count: int = Field(ge=1)
    failed_coverage_count: int = Field(ge=1)
    endpoints_pass: Literal[False]
    coverage_pass: Literal[False]
    model_admission_pass: bool
    eligible: Literal[False]


class PhaseFiveAstrometrySelectionDecision(_ContractModel):
    """Reviewed fail-closed result of successor astrometry development."""

    schema_version: Literal[1]
    decision_id: Literal["phase-5-astrometry-selection-decision"]
    status: Literal["reviewed-rejected"]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[PhaseFiveAstrometrySelectionCandidate, ...]
    decision: Literal["reject-astrometry-candidates"]
    selected_candidate: None
    confirmation_execution_authorized: Literal[False]
    step_two_c_p_execution_authorized: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]
    next_action: Literal[
        "human-scientific-review-before-another-estimator-revision"
    ]

    @model_validator(mode="after")
    def validate_rejection(self) -> Self:
        """Require both canonical estimators to fail without compensation."""
        if tuple(item.candidate for item in self.candidates) != (
            "direct-observable-pixel-centroid",
            "covariance-gated-model-assisted-centroid",
        ):
            raise ValueError(
                "astrometry selection candidates must remain exact"
            )
        return self


class PhaseFiveCompactPositionProtocol(_ContractModel):
    """Unchanged compact/component astrometry retained by Step 2C-HR."""

    position: Literal["fitted-gaussian-component-centre"]
    maximum_median_position_beams: float
    maximum_percentile_95_position_beams: float

    @model_validator(mode="after")
    def validate_compact_position(self) -> Self:
        """Prevent an extended-position revision weakening Phase 4."""
        if (
            self.maximum_median_position_beams,
            self.maximum_percentile_95_position_beams,
        ) != (0.1, 0.25):
            raise ValueError("compact position constants must remain frozen")
        return self


class PhaseFiveExtendedPositionProtocol(_ContractModel):
    """Explicit location products for one irregular extended source."""

    position: Literal["detected-segment-flux-centroid"]
    truth_target: Literal["noiseless-three-sigma-truth-segment-centroid"]
    peak_position: Literal["brightest-original-pixel"]
    host_position_claim: Literal[False]
    former_full_observable_target: Literal["diagnostic-only"]


class PhaseFiveSegmentEstimatorProtocol(_ContractModel):
    """Transparent original-pixel segment centroid implementation."""

    candidate: Literal["original-pixel-detected-segment-centroid"]
    detection_provenance: Literal["residual-b3-atrous"]
    measurement_pixels: Literal["original-background-subtracted"]
    support: Literal["accepted-b3-associated-original-pixel-segment"]
    weighting: Literal["signed-flux"]
    centroid_support_dilation_pixels: int
    peak_tie_breaking: Literal["row-major-first"]
    position_uncertainty: Literal[
        "unavailable-until-support-selection-calibrated"
    ]

    @model_validator(mode="after")
    def validate_estimator(self) -> Self:
        """Keep measurement and catalogue support identical."""
        if self.centroid_support_dilation_pixels != 0:
            raise ValueError("segment estimator constants must remain frozen")
        return self


class PhaseFiveExtendedPositionEndpointProtocol(_ContractModel):
    """Bias and repeatability gates for irregular segment locations."""

    observation_unit: Literal["eligible-astronomical-truth-group"]
    independent_unit: Literal["noise-seed-image"]
    resampling: Literal["whole-image-cluster-bootstrap-retain-all-groups"]
    bootstrap_resamples: int
    bootstrap_seed: int
    confidence_level: float
    availability_fraction: float
    maximum_absolute_axis_bias_beams: float
    maximum_radial_percentile_95_beams: float
    binding_rule: Literal[
        "one-sided-confidence-bound-passes-every-governed-stratum"
    ]
    radial_median: Literal["report-only"]

    @model_validator(mode="after")
    def validate_endpoint(self) -> Self:
        """Keep the resolution-based irregular-position gate fixed."""
        observed = (
            self.bootstrap_resamples,
            self.bootstrap_seed,
            self.confidence_level,
            self.availability_fraction,
            self.maximum_absolute_axis_bias_beams,
            self.maximum_radial_percentile_95_beams,
        )
        expected = (10_000, 20260809, 0.95, 1.0, 0.1, 0.5)
        if observed != expected:
            raise ValueError("extended endpoint constants must remain frozen")
        return self


class PhaseFiveAstrometryFollowUpReview(_ContractModel):
    """Frozen Step 2C-HR compact/extended position split."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-astrometry-follow-up-review"]
    status: Literal["frozen-before-follow-up-development-results"]
    prior_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    technical_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_detection_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    technical_review_author: Literal["Codex AI technical review"]
    independent_human_review_complete: Literal[False]
    closed_population_policy: Literal[
        "no-tuning-rescoring-confirmation-or-selection"
    ]
    dataset_manifests: tuple[PhaseFiveFilterReviewDataset, ...]
    compact_position: PhaseFiveCompactPositionProtocol
    extended_position: PhaseFiveExtendedPositionProtocol
    estimator: PhaseFiveSegmentEstimatorProtocol
    endpoint: PhaseFiveExtendedPositionEndpointProtocol
    governed_strata: tuple[str, ...]
    external_position_mappings: tuple[
        Literal[
            "pybdsf-source-moment-where-grouping-and-model-semantics-align",
            "aegean-component-centre-compact-gaussian-scope-only",
            "selavy-island-centroid-semantic-precedent",
            "profound-segment-centroid-semantic-precedent",
        ],
        ...,
    ]
    development_execution_authorized: Literal[True]
    confirmation_execution_authorized: Literal[False]
    step_two_c_p_execution_authorized: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        """Bind new populations, all strata, and product mappings."""
        expected_datasets = (
            (
                "development",
                "config/datasets/phase-5-astrometry-follow-up-development.json",
                80,
            ),
            (
                "regression",
                "config/datasets/phase-5-astrometry-follow-up-confirmation.json",
                400,
            ),
        )
        observed_datasets = tuple(
            (item.role, item.manifest, item.image_count)
            for item in self.dataset_manifests
        )
        if observed_datasets != expected_datasets:
            raise ValueError("follow-up datasets must remain frozen")
        if self.governed_strata != tuple(sorted(_PHASE_FIVE_REQUIRED_STRATA)):
            raise ValueError("follow-up governed strata must remain complete")
        expected_mappings = (
            "pybdsf-source-moment-where-grouping-and-model-semantics-align",
            "aegean-component-centre-compact-gaussian-scope-only",
            "selavy-island-centroid-semantic-precedent",
            "profound-segment-centroid-semantic-precedent",
        )
        if self.external_position_mappings != expected_mappings:
            raise ValueError("follow-up external mappings must remain exact")
        return self


class PhaseFiveAstrometryFollowUpDevelopmentDecision(_ContractModel):
    """Technical review of fresh irregular-position development evidence."""

    schema_version: Literal[1]
    decision_id: Literal["phase-5-astrometry-follow-up-development-decision"]
    status: Literal[
        "technical-review-complete-awaiting-human-scientific-review"
    ]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate: Literal["original-pixel-detected-segment-centroid"]
    image_count: Literal[80]
    group_count: Literal[480]
    endpoint_count: Literal[60]
    failed_endpoint_count: Literal[0]
    overall_availability_fraction: float
    overall_axis_bias_upper_bounds_beams: tuple[float, float]
    overall_radial_p95_beams: float
    overall_radial_p95_upper_bound_beams: float
    overall_radial_median_beams: float
    former_target_radial_p95_beams: float
    limiting_radial_strata: tuple[str, ...]
    limiting_radial_p95_upper_bound_beams: float
    decision: Literal["retain-candidate-for-human-review"]
    selected_candidate: Literal["original-pixel-detected-segment-centroid"]
    named_review: Literal["codex-step-2c-hr-development-evidence-review"]
    review_scope: Literal["technical-and-governed-fresh-development-evidence"]
    independent_human_scientific_review: Literal["still-required"]
    confirmation_execution_authorized: Literal[False]
    step_two_c_p_execution_authorized: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]
    next_action: Literal["named-human-scientific-review-before-confirmation"]

    @model_validator(mode="after")
    def validate_technical_decision(self) -> Self:
        """Require passing results while retaining every downstream gate."""
        metrics = (
            self.overall_availability_fraction,
            *self.overall_axis_bias_upper_bounds_beams,
            self.overall_radial_p95_beams,
            self.overall_radial_p95_upper_bound_beams,
            self.overall_radial_median_beams,
            self.former_target_radial_p95_beams,
            self.limiting_radial_p95_upper_bound_beams,
        )
        if not all(isfinite(item) and item >= 0 for item in metrics):
            raise ValueError(
                "development metrics must be finite and non-negative"
            )
        if (
            self.overall_availability_fraction != 1.0
            or max(self.overall_axis_bias_upper_bounds_beams)
            > _PHASE_FIVE_EXTENDED_MAXIMUM_AXIS_BIAS_BEAMS
            or self.overall_radial_p95_upper_bound_beams
            > _PHASE_FIVE_EXTENDED_MAXIMUM_RADIAL_P95_BEAMS
            or self.limiting_radial_p95_upper_bound_beams
            > _PHASE_FIVE_EXTENDED_MAXIMUM_RADIAL_P95_BEAMS
        ):
            raise ValueError("development gates must all pass")
        if (
            self.overall_radial_median_beams > self.overall_radial_p95_beams
            or self.overall_radial_p95_beams
            > self.overall_radial_p95_upper_bound_beams
        ):
            raise ValueError("radial development summaries must be ordered")
        expected_limiting = (
            "above-compact-deblend-limit",
            "morphology-shell",
            "tile-corner",
        )
        if self.limiting_radial_strata != expected_limiting:
            raise ValueError("limiting radial strata must remain exact")
        return self


class PhaseFiveAstrometryFollowUpHumanDecision(_ContractModel):
    """Named scientific approval of one-look segment-position confirmation."""

    schema_version: Literal[1]
    decision_id: Literal["phase-5-astrometry-follow-up-human-decision"]
    status: Literal["approved-confirmation-only"]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: Literal["Gemma Danks"]
    review_source: Literal["interactive-project-owner-approval"]
    reviewed_on: Literal["2026-08-09"]
    decision: Literal["approve-one-look-confirmation"]
    candidate: Literal["original-pixel-detected-segment-centroid"]
    approved_findings: tuple[str, ...]
    closed_confirmation_policy: Literal[
        "one-look-no-tuning-rescoring-or-reconfirmation"
    ]
    independent_human_scientific_review_complete: Literal[True]
    confirmation_execution_authorized: Literal[True]
    step_two_c_p_execution_authorized: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]
    next_action: Literal[
        "run-sealed-confirmation-once-and-review-before-external-comparison"
    ]

    @model_validator(mode="after")
    def validate_approval_scope(self) -> Self:
        """Require every reviewed safeguard and no downstream authority."""
        expected = (
            "compact-and-irregular-position-semantics-remain-distinct",
            "irregular-axis-0p10-and-radial-p95-0p50-gates",
            "narrow-shell-margin-accepted-for-confirmation",
            "position-uncertainty-remains-unavailable",
            "one-look-confirmation-without-tuning",
        )
        if self.approved_findings != expected:
            raise ValueError(
                "approved findings must remain complete and exact"
            )
        return self


class PhaseFiveAstrometryFollowUpConfirmationDecision(_ContractModel):
    """Reviewed one-look decision for the segment-position confirmation."""

    schema_version: Literal[1]
    decision_id: Literal["phase-5-astrometry-follow-up-confirmation-decision"]
    status: Literal["reviewed-passed"]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    human_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate: Literal["original-pixel-detected-segment-centroid"]
    image_count: Literal[400]
    group_count: Literal[2400]
    endpoint_count: Literal[60]
    failed_endpoint_count: Literal[0]
    overall_availability_fraction: float
    overall_axis_bias_upper_bounds_beams: tuple[float, float]
    overall_radial_p95_beams: float
    overall_radial_p95_upper_bound_beams: float
    overall_radial_median_beams: float
    former_target_radial_p95_beams: float
    limiting_radial_strata: tuple[str, ...]
    limiting_radial_p95_upper_bound_beams: float
    confirmation_result: Literal["pass-awaiting-reviewed-decision"]
    decision: Literal["confirm-candidate-for-external-comparison"]
    selected_candidate: Literal["original-pixel-detected-segment-centroid"]
    named_review: Literal["codex-step-2c-hr-confirmation-evidence-review"]
    review_scope: Literal["technical-and-governed-one-look-confirmation"]
    independent_human_scientific_review: Literal[
        "completed-before-confirmation"
    ]
    confirmation_reuse: Literal["closed-after-one-look"]
    step_two_c_p_protocol_freeze_authorized: Literal[True]
    step_two_c_p_execution_authorized: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]
    next_action: Literal[
        "freeze-external-comparison-protocol-before-generating-output"
    ]

    @model_validator(mode="after")
    def validate_confirmation_decision(self) -> Self:
        """Require every frozen confirmation gate and keep execution closed."""
        metrics = (
            self.overall_availability_fraction,
            *self.overall_axis_bias_upper_bounds_beams,
            self.overall_radial_p95_beams,
            self.overall_radial_p95_upper_bound_beams,
            self.overall_radial_median_beams,
            self.former_target_radial_p95_beams,
            self.limiting_radial_p95_upper_bound_beams,
        )
        if not all(isfinite(item) and item >= 0 for item in metrics):
            raise ValueError(
                "confirmation metrics must be finite and non-negative"
            )
        if (
            self.overall_availability_fraction != 1.0
            or max(self.overall_axis_bias_upper_bounds_beams)
            > _PHASE_FIVE_EXTENDED_MAXIMUM_AXIS_BIAS_BEAMS
            or self.overall_radial_p95_upper_bound_beams
            > _PHASE_FIVE_EXTENDED_MAXIMUM_RADIAL_P95_BEAMS
            or self.limiting_radial_p95_upper_bound_beams
            > _PHASE_FIVE_EXTENDED_MAXIMUM_RADIAL_P95_BEAMS
        ):
            raise ValueError("confirmation gates must all pass")
        if (
            self.overall_radial_median_beams > self.overall_radial_p95_beams
            or self.overall_radial_p95_beams
            > self.overall_radial_p95_upper_bound_beams
        ):
            raise ValueError("radial confirmation summaries must be ordered")
        expected_limiting = (
            "above-compact-deblend-limit",
            "morphology-shell",
            "tile-corner",
        )
        if self.limiting_radial_strata != expected_limiting:
            raise ValueError("limiting radial strata must remain exact")
        return self


class PhaseFiveExternalReference(_ContractModel):
    """One immutable Step 2C-P source-finder runtime."""

    finder_id: Literal[
        "released-pybdsf",
        "pinned-pybdsf-master",
        "aegean",
    ]
    version: str = Field(min_length=1)
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    artifact_type: Literal["pypi-sdist", "local-wheel", "pypi-wheel"]
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    container_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dependency_inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    comparison_scope: Literal[
        "binding-full-continuum",
        "binding-compact-blended-and-gaussian-like-catalogue",
    ]


class PhaseFiveExternalPopulation(_ContractModel):
    """One fresh seed-disjoint external-comparison population."""

    lane: Literal["continuum", "compact-blend"]
    manifest: str = Field(pattern=r"^config/datasets/[a-z0-9-]+\.json$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    role: Literal["regression"]
    image_count: Literal[600, 800]
    independent_unit: Literal["noise-seed-image"]
    geometry_policy: Literal[
        "reviewed-generator-geometries-new-noise-images-no-prior-results"
    ]


class PhaseFiveExternalMatcher(_ContractModel):
    """Finder-neutral truth association and like-product mapping."""

    truth_authority: Literal["analytic-and-injected-truth-first"]
    coordinate_system: Literal["zero-based-fits-pixel-centre-x-y"]
    compact_edge: Literal["centre-distance-at-most-half-restoring-beam-fwhm"]
    extended_edge: Literal[
        "minimum-support-overlap-at-least-0.1-or-centre-in-one-beam-dilation"
    ]
    primary_assignment: Literal[
        "maximum-cardinality-maximum-overlap-minimum-distance-stable-id"
    ]
    topology_rule: Literal[
        "retain-all-eligible-edges-after-primary-assignment"
    ]
    no_cross_finder_matching: Literal[True]
    hebog_compact_position: Literal["fitted-gaussian-component-centre"]
    hebog_extended_position: Literal["detected-segment-flux-centroid"]
    pybdsf_compact_position: Literal["gaussian-component-centre"]
    pybdsf_extended_position: Literal[
        "source-moment-only-when-grouping-and-model-semantics-align"
    ]
    aegean_position: Literal[
        "component-centre-compact-gaussian-and-mixed-scope-only"
    ]
    hebog_support: Literal["reconciled-detected-segment"]
    pybdsf_support: Literal["island-mask"]
    aegean_support: Literal["three-sigma-fitted-ellipse-union-proxy"]
    aegean_mask_metrics: Literal["unavailable-not-failure"]


class PhaseFiveExternalPybdsfConfiguration(_ContractModel):
    """Exact Rapthor-profile PyBDSF settings for both references."""

    threshold_pixel_sigma: float = Field(ge=5.0, le=5.0, allow_inf_nan=False)
    threshold_island_sigma: float = Field(ge=3.0, le=3.0, allow_inf_nan=False)
    threshold_type: Literal["hard"]
    mean_map: Literal["zero"]
    rms_map: Literal[True]
    rms_box: tuple[Literal[150], Literal[50]]
    adaptive_rms_box: Literal[True]
    rms_box_bright: tuple[Literal[35], Literal[7]]
    adaptive_threshold: float = Field(ge=75.0, le=75.0, allow_inf_nan=False)
    atrous_do: Literal[True]
    atrous_bdsm_do: Literal[True]
    atrous_jmax: Literal[3]
    atrous_lpf: Literal["b3"]
    atrous_sum: Literal[True]
    atrous_orig_isl: Literal[False]
    primary_background: Literal["finder-operational"]
    controlled_background_diagnostic: Literal[
        "same-frozen-mean-and-rms-via-rmsmean-map-filename"
    ]


class PhaseFiveExternalAegeanConfiguration(_ContractModel):
    """Exact blind Aegean primary and threshold-matched diagnostic."""

    mode: Literal["blind-source-finding"]
    primary_seedclip_sigma: float = Field(
        ge=5.0,
        le=5.0,
        allow_inf_nan=False,
    )
    primary_floodclip_sigma: float = Field(
        ge=4.0,
        le=4.0,
        allow_inf_nan=False,
    )
    threshold_matched_seedclip_sigma: float = Field(
        ge=5.0,
        le=5.0,
        allow_inf_nan=False,
    )
    threshold_matched_floodclip_sigma: float = Field(
        ge=3.0,
        le=3.0,
        allow_inf_nan=False,
    )
    covariance: Literal["enabled"]
    island_catalogue: Literal[True]
    cores: Literal[1]
    primary_background: Literal["finder-operational-internal-estimation"]
    controlled_background_diagnostic: Literal["same-frozen-background-and-rms"]


class PhaseFiveExternalPowerAssumption(_ContractModel):
    """Planning variance bound for one continuum endpoint family."""

    metric_family: Literal[
        "completeness",
        "reliability",
        "integrated-flux-median",
        "integrated-flux-p95",
        "position-median",
        "position-p95",
        "duplicate-fraction",
        "mask-precision",
        "mask-recall",
        "mask-iou",
        "split-fraction",
        "merge-fraction",
    ]
    practical_regression_margin: float = Field(gt=0, allow_inf_nan=False)
    planning_expected_regression: float = Field(allow_inf_nan=False)
    planning_paired_standard_deviation: float = Field(
        gt=0,
        allow_inf_nan=False,
    )
    comparison_count: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_alternative(self) -> Self:
        """Keep the planning alternative inside its practical margin."""
        if self.planning_expected_regression >= (
            self.practical_regression_margin
        ):
            raise ValueError("planning regression must be below margin")
        return self


class PhaseFiveExternalPowerAudit(_ContractModel):
    """Prospective joint-power audit across continuum and compact lanes."""

    method: Literal[
        "cluster-normal-planning-plus-conservative-union-lower-bound"
    ]
    confidence_level: float = Field(ge=0.95, le=0.95, allow_inf_nan=False)
    minimum_joint_power: float = Field(ge=0.9, le=0.9, allow_inf_nan=False)
    continuum_realization_count: Literal[600]
    continuum_assumptions: tuple[PhaseFiveExternalPowerAssumption, ...] = (
        Field(min_length=12, max_length=12)
    )
    continuum_familywise_power_lower_bound: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    compact_reviewed_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compact_realization_count: Literal[800]
    compact_single_reference_familywise_power_lower_bound: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    compact_reference_count: Literal[3]
    compact_familywise_power_lower_bound: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    combined_familywise_power_lower_bound: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    assumption_failure: Literal[
        "observed-variance-above-bound-makes-comparison-underpowered"
    ]

    @model_validator(mode="after")
    def validate_power(self) -> Self:
        """Recompute every conservative lower bound from frozen inputs."""
        expected_order = (
            "completeness",
            "reliability",
            "integrated-flux-median",
            "integrated-flux-p95",
            "position-median",
            "position-p95",
            "duplicate-fraction",
            "mask-precision",
            "mask-recall",
            "mask-iou",
            "split-fraction",
            "merge-fraction",
        )
        if (
            tuple(item.metric_family for item in self.continuum_assumptions)
            != expected_order
        ):
            raise ValueError("continuum power assumptions must be canonical")
        critical = NormalDist().inv_cdf(self.confidence_level)
        total_failure = 0.0
        for item in self.continuum_assumptions:
            standard_error = item.planning_paired_standard_deviation / (
                self.continuum_realization_count**0.5
            )
            threshold = (
                item.practical_regression_margin - critical * standard_error
            )
            power = NormalDist().cdf(
                (threshold - item.planning_expected_regression)
                / standard_error
            )
            total_failure += item.comparison_count * (1.0 - power)
        continuum = max(0.0, 1.0 - total_failure)
        compact = max(
            0.0,
            1.0
            - self.compact_reference_count
            * (
                1.0
                - self.compact_single_reference_familywise_power_lower_bound
            ),
        )
        combined = max(0.0, 1.0 - (1.0 - continuum) - (1.0 - compact))
        declared = (
            self.continuum_familywise_power_lower_bound,
            self.compact_familywise_power_lower_bound,
            self.combined_familywise_power_lower_bound,
        )
        calculated = (continuum, compact, combined)
        if any(
            abs(left - right) > _POWER_RECOMPUTATION_TOLERANCE
            for left, right in zip(declared, calculated, strict=True)
        ):
            raise ValueError("declared external-comparison power is stale")
        if combined < self.minimum_joint_power:
            raise ValueError("external-comparison power is below target")
        return self


class PhaseFiveExternalComparisonProtocol(_ContractModel):
    """Frozen pre-results Step 2C-P external source-finder protocol."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-external-comparison"]
    status: Literal["frozen-before-external-output"]
    confirmation_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    phase_five_scientific_gates_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    phase_four_scientific_gates_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    phase_four_metric_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate: Literal["residual-b3-original-pixel-measurement"]
    candidate_position: Literal["confirmed-detected-segment-centroid"]
    references: tuple[PhaseFiveExternalReference, ...] = Field(
        min_length=3,
        max_length=3,
    )
    populations: tuple[PhaseFiveExternalPopulation, ...] = Field(
        min_length=2,
        max_length=2,
    )
    pybdsf_configuration: PhaseFiveExternalPybdsfConfiguration
    aegean_configuration: PhaseFiveExternalAegeanConfiguration
    matcher: PhaseFiveExternalMatcher
    continuum_binding_metrics: tuple[str, ...] = Field(min_length=10)
    compact_binding_registry: Literal["phase-4r-metric-registry"]
    aegean_binding_scope: Literal[
        "compact-blended-gaussian-like-and-mixed-catalogue-products"
    ]
    aegean_diagnostic_scope: Literal[
        "diffuse-filament-shell-mask-and-multiscale-provenance"
    ]
    resampling: Literal[
        "paired-whole-image-fixed-seed-bca-one-sided-95-percent"
    ]
    bootstrap_resamples: Literal[50000]
    bootstrap_seed: Literal[20260810]
    decision_rule: Literal[
        "absolute-first-every-applicable-noninferiority-gate-no-compensation"
    ]
    incomplete_reference_policy: Literal[
        "comparison-unavailable-and-step-two-c-p-fails-closed"
    ]
    failure_denominator: Literal["retain-every-image"]
    one_look_rule: Literal[
        "one-terminal-look-no-tuning-rescoring-or-adaptive-sample-size"
    ]
    power_audit: PhaseFiveExternalPowerAudit
    public_cutout: Literal[
        "deferred-to-step-6-no-redistributable-checksum-bound-input-on-host"
    ]
    scientific_outcomes_before_runtime: Literal[True]
    execution_authorized: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]
    next_action: Literal[
        "implement-and-hash-runners-and-matcher-before-execution-review"
    ]

    @model_validator(mode="after")
    def validate_external_protocol(self) -> Self:
        """Require canonical references, populations, and metric families."""
        if tuple(item.finder_id for item in self.references) != (
            "released-pybdsf",
            "pinned-pybdsf-master",
            "aegean",
        ):
            raise ValueError("external reference order must remain canonical")
        reference_identities = tuple(
            (
                item.finder_id,
                item.version,
                item.source_revision,
                item.artifact_type,
                item.artifact_sha256,
                item.container_image_digest,
                item.dependency_inventory_sha256,
                item.comparison_scope,
            )
            for item in self.references
        )
        expected_reference_identities = (
            (
                "released-pybdsf",
                "1.14.1",
                "1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc",
                "pypi-sdist",
                "8d5113fecca19bb9f02a1a3e17aeb8f2d22c712cac9504e44271c4071f5434d2",
                "sha256:72454074489d5ed0d0ed08781ec11411a3e25ccf75e3378a924152176fa15b37",
                "8211043e9fca55d706d1e890e2bf0b630e228a854db0949258c498506975669f",
                "binding-full-continuum",
            ),
            (
                "pinned-pybdsf-master",
                "1.14.2.dev40+gc70103be3",
                "c70103be3ae9ae9908286f144e6ce956acc0ce5c",
                "local-wheel",
                "2f1fdfbecd39de93bad53e2a85258959e5114e1f049787ac15c763e8fc8f4d8d",
                "sha256:192964b32d50a6e960cf3710013ffa92d782ecf43a4d6def4309a7cb10911e73",
                "83574dd4c15d79f3cf2ac52fb8aa7b5bd2ff323c93343b2f1337eec938e8bf99",
                "binding-full-continuum",
            ),
            (
                "aegean",
                "2.3.5",
                "bb04f50a3ec117d180a79260c6a5c844f1d8dbbc",
                "pypi-wheel",
                "dda95cb525e229b60bc357d3e5fc454cac20f364ee8aa10b730c2f7223da428d",
                "sha256:b496d2907c13d083e7c87eda61a6a40057f92b5cb6e605330bcb1b6db27158b8",
                "346c1f32b0d78ce1d22f6d6ff20787a102d8491c14432865465596c9f41ba909",
                "binding-compact-blended-and-gaussian-like-catalogue",
            ),
        )
        if reference_identities != expected_reference_identities:
            raise ValueError("external reference identities must remain exact")
        if tuple(item.lane for item in self.populations) != (
            "continuum",
            "compact-blend",
        ):
            raise ValueError("external population order must remain canonical")
        population_identities = tuple(
            (item.lane, item.manifest, item.image_count)
            for item in self.populations
        )
        if population_identities != (
            (
                "continuum",
                "config/datasets/phase-5-external-continuum.json",
                600,
            ),
            (
                "compact-blend",
                "config/datasets/phase-5-external-compact-blend.json",
                800,
            ),
        ):
            raise ValueError(
                "external population identities must remain exact"
            )
        expected_metrics = (
            "completeness",
            "reliability",
            "integrated-flux-median",
            "integrated-flux-p95",
            "position-median",
            "position-p95",
            "duplicate-fraction",
            "mask-precision",
            "mask-recall",
            "mask-iou",
            "split-fraction",
            "merge-fraction",
        )
        if self.continuum_binding_metrics != expected_metrics:
            raise ValueError("continuum metrics must remain canonical")
        return self


class PhaseFiveExternalRunnerArtifact(_ContractModel):
    """One isolated runner bound by a reviewed execution decision."""

    relative_path: Literal[
        "scripts/benchmark/run_phase5_external_hebog.py",
        "scripts/benchmark/run_phase5_external_pybdsf.py",
        "scripts/benchmark/run_phase5_external_aegean.py",
    ]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PhaseFiveExternalExecutionDecision(_ContractModel):
    """Named one-look authorization bound to committed runner code."""

    schema_version: Literal[1]
    decision_id: Literal["phase-5-external-execution-decision"]
    status: Literal[
        "awaiting-reconstructed-runtime-approval",
        "reviewed-before-external-output",
    ]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hebog_container_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    hebog_dependency_inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pybdsf_ncores: int = Field(ge=1)
    runners: tuple[
        PhaseFiveExternalRunnerArtifact,
        PhaseFiveExternalRunnerArtifact,
        PhaseFiveExternalRunnerArtifact,
    ]
    named_review: str = Field(min_length=1)
    decision: Literal[
        "await-renewed-runtime-approval",
        "authorize-one-terminal-external-comparison",
    ]
    execution_authorized: bool
    one_look_opened: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]
    next_action: Literal[
        "execute-complete-frozen-comparison-once-without-opening-partial-results",
        "obtain-renewed-runtime-approval-before-campaign-preflight",
    ]

    @model_validator(mode="after")
    def validate_state_and_runner_order(self) -> Self:
        """Keep authorization state and entry points canonical."""
        pending = self.status == "awaiting-reconstructed-runtime-approval"
        expected_state = (
            (
                "await-renewed-runtime-approval",
                False,
                "obtain-renewed-runtime-approval-before-campaign-preflight",
            )
            if pending
            else (
                "authorize-one-terminal-external-comparison",
                True,
                "execute-complete-frozen-comparison-once-without-opening-"
                "partial-results",
            )
        )
        observed_state = (
            self.decision,
            self.execution_authorized,
            self.next_action,
        )
        if observed_state != expected_state:
            raise ValueError(
                "external execution authorization state is invalid"
            )
        if tuple(item.relative_path for item in self.runners) != (
            "scripts/benchmark/run_phase5_external_hebog.py",
            "scripts/benchmark/run_phase5_external_pybdsf.py",
            "scripts/benchmark/run_phase5_external_aegean.py",
        ):
            raise ValueError("external runner order must remain canonical")
        return self


class PhaseFiveFilterPairedCandidateDecision(_ContractModel):
    """Conjunctive Step 2B outcome for one existing representation."""

    family: Literal["beam-aware-matched-filter", "undecimated-wavelet"]
    passes_absolute: Literal[False]
    noninferior_to_other: Literal[False]
    failed_absolute_endpoint_count: int = Field(ge=1)
    failed_paired_endpoint_count: int = Field(ge=1)
    bounded_cost: tuple[int, int, int]

    @model_validator(mode="after")
    def validate_cost(self) -> Self:
        """Require a complete positive structural-cost diagnostic."""
        if any(value <= 0 for value in self.bounded_cost):
            raise ValueError("paired-decision bounded costs must be positive")
        return self


class PhaseFiveFilterPairedDecision(_ContractModel):
    """Reviewed fail-closed decision produced by the frozen Step 2B review."""

    schema_version: Literal[1]
    decision_id: Literal["phase-5-filter-paired-decision"]
    status: Literal["reviewed-inconclusive"]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_selection_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[PhaseFiveFilterPairedCandidateDecision, ...]
    decision: Literal["select-neither"]
    selected_family: None
    named_review: Literal["codex-step-2b-governed-evidence-review"]
    review_scope: Literal[
        "technical-and-governed-development-regression-evidence"
    ]
    independent_human_scientific_review: Literal["still-required"]
    next_action: Literal[
        "freeze-corrective-development-design-before-re-evaluation"
    ]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_inconclusive_decision(self) -> Self:
        """Require both canonical failed candidates and no authorization."""
        if tuple(item.family for item in self.candidates) != (
            "beam-aware-matched-filter",
            "undecimated-wavelet",
        ):
            raise ValueError("paired-decision candidates must be canonical")
        return self


class PairedResamplingProtocol(_ContractModel):
    """Predeclared interval construction for same-image comparisons."""

    method: Literal["scipy-bca-bootstrap"]
    resampling_unit: Literal["noise-seed-image"]
    paired: Literal[True]
    confidence_level: float = Field(gt=0, lt=1)
    alternative: Literal["less"]
    resamples: int = Field(ge=10_000)
    seed: int = Field(ge=0)
    degenerate_interval: Literal[
        "finite-point-mass-exact-otherwise-indeterminate-fail"
    ]


class PairedDecisionRule(_ContractModel):
    """Reviewed fail-closed decision rule for the final Phase 4 campaign."""

    regression_sign: Literal["positive-means-hebog-is-worse"]
    combination_rule: Literal["intersection-union-all-coprimary"]
    power_target_applies_to: Literal["interval-exclusion"]
    require_no_worse_point_estimate: Literal[False]
    require_upper_interval_within_margin: Literal[True]
    require_every_absolute_gate: Literal[True]
    require_stronger_hebog_regression_envelopes: Literal[True]
    multiplicity_adjustment: Literal[
        "none-intersection-union-controls-type-one-error"
    ]


class PairedReferenceFailurePolicy(_ContractModel):
    """Treatment of implementation failures without denominator deletion."""

    primary: Literal["qualification-fails"]
    secondary: Literal["record-and-continue"]
    candidate: Literal["qualification-fails"]
    failed_realization_denominator: Literal["retained"]


class PairedBinaryEndpoint(_ContractModel):
    """Design assumptions for a paired binary or rate endpoint."""

    endpoint_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    population: str = Field(min_length=1)
    desirable_direction: Literal["higher-is-better", "lower-is-better"]
    practical_regression_margin: float = Field(gt=0, lt=1)
    planning_expected_regression: float
    observations_per_realization: int = Field(ge=1)
    planning_discordance_probability: float = Field(gt=0, lt=1)
    planning_intracluster_correlation: float = Field(ge=0, lt=1)
    population_unit: (
        Literal[
            "association-truth-groups",
            "individually-resolvable-sources",
            "point-sources",
            "clear-resolved-sources",
            "unresolved-association-groups",
        ]
        | None
    ) = None
    assumption_verification: Literal[
        "required-on-independent-development-regression"
    ]

    @model_validator(mode="after")
    def validate_planning_alternative(self) -> Self:
        """Require an identifiable alternative inside the NI margin."""
        if (
            self.planning_expected_regression
            >= self.practical_regression_margin
        ):
            raise ValueError(
                "planning regression must be smaller than its practical margin"
            )
        if self.planning_discordance_probability <= (
            self.planning_expected_regression**2
        ):
            raise ValueError(
                "planning discordance must imply positive paired variance"
            )
        return self


class PairedContinuousEndpoint(_ContractModel):
    """Design assumptions for a realization-level paired statistic."""

    endpoint_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    population: str = Field(min_length=1)
    desirable_direction: Literal[
        "lower-is-better", "closer-to-ideal-is-better"
    ]
    ideal_value: float | None = None
    practical_regression_margin: float = Field(gt=0)
    planning_expected_regression: float
    planning_paired_standard_deviation: float = Field(gt=0)
    assumption_verification: Literal[
        "required-on-independent-development-regression"
    ]

    @model_validator(mode="after")
    def validate_endpoint(self) -> Self:
        """Bind ideal-distance metrics and an attainable alternative."""
        if (
            self.desirable_direction == "closer-to-ideal-is-better"
            and self.ideal_value is None
        ):
            raise ValueError("ideal-directed endpoint requires an ideal value")
        if (
            self.desirable_direction != "closer-to-ideal-is-better"
            and self.ideal_value is not None
        ):
            raise ValueError(
                "one-direction endpoint cannot define an ideal value"
            )
        if (
            self.planning_expected_regression
            >= self.practical_regression_margin
        ):
            raise ValueError(
                "planning regression must be smaller than its practical margin"
            )
        return self


class AbsoluteMeanPowerCheck(_ContractModel):
    """Planning assumptions for one absolute normalized-residual mean gate."""

    metric_id: Literal["snr-10-integrated-flux-uncertainty-bias"]
    population_unit: Literal["snr-10-point-sources"]
    observations_per_realization: int = Field(ge=1)
    planning_intracluster_correlation: float = Field(ge=0, lt=1)
    anticipated_mean_normalized_residual: float
    planning_standard_deviation: float = Field(gt=0)
    equivalence_margin: float = Field(gt=0)
    confidence_level: float = Field(gt=0, lt=1)
    minimum_interval_containment_power: float = Field(gt=0, lt=1)
    method: Literal["cluster-adjusted-normal-ci-containment"]

    @model_validator(mode="after")
    def validate_anticipated_mean(self) -> Self:
        """Require a scientifically attainable alternative inside the gate."""
        if abs(self.anticipated_mean_normalized_residual) >= (
            self.equivalence_margin
        ):
            raise ValueError(
                "anticipated absolute mean must lie inside margin"
            )
        return self


class PairedNoninferiorityContract(_ContractModel):
    """Draft same-image comparison and power contract for Phase 4 closure."""

    schema_version: Literal[1]
    contract_id: Literal[
        "phase-4-paired-noninferiority",
        "phase-4s-paired-noninferiority",
        "phase-4t-paired-noninferiority",
        "phase-4u-paired-noninferiority",
    ]
    status: Literal["draft-provisional", "reviewed"]
    primary_reference: Literal["released-pybdsf-used-by-rapthor"]
    secondary_reference: Literal["pinned-pybdsf-master"]
    realization_count: int = Field(ge=1)
    minimum_interval_exclusion_power: float = Field(gt=0, lt=1)
    minimum_familywise_interval_exclusion_power: float | None = Field(
        default=None,
        gt=0,
        lt=1,
    )
    resampling: PairedResamplingProtocol
    decision: PairedDecisionRule
    reference_failures: PairedReferenceFailurePolicy
    population_freeze: Literal[
        "review-before-seeds-truth-generator-and-revisions-are-frozen"
    ]
    stopping_rule: Literal[
        "one-final-look-no-adaptive-sample-size-or-post-inspection-tuning"
    ]
    infrastructure_resume: Literal["same-frozen-realizations-only"]
    binary_endpoints: tuple[PairedBinaryEndpoint, ...] = Field(min_length=1)
    continuous_endpoints: tuple[PairedContinuousEndpoint, ...] = Field(
        min_length=1
    )
    report_only_metrics: tuple[str, ...] = Field(min_length=1)
    planning_assumption_rule: Literal[
        "verify-on-independent-data-before-review-and-freeze"
    ]
    scientific_basis: tuple[str, ...] = Field(min_length=4)
    human_scientific_review: Literal[
        "required-before-freeze",
        "project-owner-waived-independent-human-review",
    ]
    expert_scientific_review: (
        Literal["ai-conducted-review-completed-before-freeze"] | None
    ) = None
    qualification_scope: (
        Literal["compact-single-scale-rapthor-used-behaviour"] | None
    ) = None
    controlled_residual_noise_injection: (
        Literal["not-available-recorded-limitation"] | None
    ) = None
    absolute_mean_power_checks: tuple[AbsoluteMeanPowerCheck, ...] = ()

    def _validate_phase4s(self) -> None:
        """Require every additional pre-opening Phase 4S declaration."""
        if any(
            endpoint.population_unit is None
            for endpoint in self.binary_endpoints
        ):
            raise ValueError(
                "Phase 4S binary endpoints require population units"
            )
        if self.minimum_familywise_interval_exclusion_power is None:
            raise ValueError("Phase 4S requires a familywise power target")
        if self.expert_scientific_review is None:
            raise ValueError("Phase 4S requires recorded expert review")
        if self.qualification_scope is None:
            raise ValueError("Phase 4S requires an explicit scope")
        if self.controlled_residual_noise_injection is None:
            raise ValueError("Phase 4S requires the residual-noise limitation")

    def _validate_compact_followup(self) -> None:
        """Require the retained absolute-uncertainty power question."""
        self._validate_phase4s()
        if len(self.absolute_mean_power_checks) != 1:
            raise ValueError(
                "compact follow-up requires one absolute mean power check"
            )

    @model_validator(mode="after")
    def validate_protocol(self) -> Self:
        """Protect endpoint ownership, interval alignment, and sources."""
        endpoint_ids = [
            endpoint.endpoint_id
            for endpoint in (
                *self.binary_endpoints,
                *self.continuous_endpoints,
            )
        ]
        if len(set(endpoint_ids)) != len(endpoint_ids):
            raise ValueError("paired endpoint identifiers must be unique")
        if self.resampling.confidence_level != _PAIRED_CONFIDENCE_LEVEL:
            raise ValueError("paired confidence level must remain 0.95")
        if len(set(self.report_only_metrics)) != len(self.report_only_metrics):
            raise ValueError("report-only metric identifiers must be unique")
        if len(set(self.scientific_basis)) != len(self.scientific_basis):
            raise ValueError("paired scientific basis links must be unique")
        if any(
            not link.startswith("https://") for link in self.scientific_basis
        ):
            raise ValueError("paired scientific basis links must use HTTPS")
        if self.contract_id == "phase-4s-paired-noninferiority":
            self._validate_phase4s()
        if self.contract_id in {
            "phase-4t-paired-noninferiority",
            "phase-4u-paired-noninferiority",
        }:
            self._validate_compact_followup()
        return self


class PhaseFourMetricDefinition(_ContractModel):
    """One direction-aware Phase 4R scientific comparison metric."""

    metric_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    domain: Literal[
        "robustness",
        "catalogue",
        "association",
        "classification",
        "position",
        "flux",
        "shape",
        "uncertainty",
    ]
    population: str = Field(min_length=1)
    statistic: Literal[
        "completion-rate",
        "rate",
        "median-absolute-error",
        "percentile-95-absolute-error",
        "maximum-absolute-bias",
        "maximum-absolute-coverage-departure",
        "maximum-absolute-dispersion-departure",
    ]
    unit: Literal[
        "fraction",
        "beam-fwhm",
        "fractional-error",
        "degrees",
        "normalized-residual",
    ]
    desirable_direction: Literal["higher-is-better", "lower-is-better"]
    ideal_value: float = Field(allow_inf_nan=False)
    absolute_role: Literal["gate", "report-only", "none"]
    stratification: Literal[
        "overall-only", "overall-and-applicable-governed-strata"
    ]
    primary_practical_regression_margin: float = Field(
        ge=0,
        allow_inf_nan=False,
    )
    secondary_practical_regression_margin: float = Field(
        ge=0,
        allow_inf_nan=False,
    )
    missingness: Literal["availability-gated-and-retained-values-conditional"]

    @model_validator(mode="after")
    def validate_direction_and_ideal(self) -> Self:
        """Bind rates and errors to their scientifically desirable ideal."""
        expected_ideal = (
            1.0 if self.desirable_direction == "higher-is-better" else 0.0
        )
        if self.ideal_value != expected_ideal:
            raise ValueError(
                "metric ideal must be one for higher-is-better and zero "
                "for lower-is-better"
            )
        if (
            self.primary_practical_regression_margin
            != self.secondary_practical_regression_margin
        ):
            raise ValueError(
                "both PyBDSF references must use the same practical margin"
            )
        return self


class PhaseFourMetricRegistry(_ContractModel):
    """Development-approved no-compensation metric registry for Phase 4R."""

    schema_version: Literal[1]
    registry_id: Literal["phase-4r-metric-registry"]
    status: Literal["approved-development", "reviewed-qualification"]
    comparison_rule: Literal[
        "every-metric-passes-no-compensation-or-weighted-score"
    ]
    reference_scope: Literal[
        "released-pybdsf-and-pinned-master-where-each-produces-the-metric"
    ]
    candidate_completion: Literal[
        "every-realization-required-reference-failure-retained"
    ]
    point_estimate_rule: Literal[
        "within-practical-margin-on-frozen-development-regression"
    ]
    qualification_rule: Literal[
        "one-sided-paired-upper-limit-within-practical-margin"
    ]
    governed_strata: tuple[str, ...] = Field(min_length=1)
    metrics: tuple[PhaseFourMetricDefinition, ...] = Field(min_length=1)
    human_scientific_review: Literal[
        "development-approved-qualification-review-still-required",
        "qualification-reviewed",
    ]

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        """Require canonical strata and one definition per metric."""
        expected_review = (
            "qualification-reviewed"
            if self.status == "reviewed-qualification"
            else "development-approved-qualification-review-still-required"
        )
        if self.human_scientific_review != expected_review:
            raise ValueError("metric registry status and review must agree")
        if self.governed_strata != tuple(sorted(set(self.governed_strata))):
            raise ValueError("governed metric strata must be canonical")
        metric_ids = [metric.metric_id for metric in self.metrics]
        if len(set(metric_ids)) != len(metric_ids):
            raise ValueError("metric identifiers must be unique")
        if "implementation-completion" not in metric_ids:
            raise ValueError("metric registry must include completion")
        return self


def load_performance_matrix(path: Path) -> PerformanceMatrixContract:
    """Load and validate a performance-matrix contract."""
    return PerformanceMatrixContract.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_scalability_contract(path: Path) -> ScalabilityContract:
    """Load and validate an extreme-image scalability contract."""
    return ScalabilityContract.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_public_behaviours(path: Path) -> PublicBehaviourManifest:
    """Load and validate the public-behaviour manifest."""
    return PublicBehaviourManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_three_scientific_gates(
    path: Path,
) -> PhaseThreeScientificGates:
    """Load frozen Phase 3 foreground-sensitive scientific margins."""
    return PhaseThreeScientificGates.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_four_measurement_contract(
    path: Path,
) -> PhaseFourMeasurementContract:
    """Load frozen Phase 4 compact measurement meanings."""
    return PhaseFourMeasurementContract.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_four_scientific_gates(
    path: Path,
) -> PhaseFourScientificGates:
    """Load frozen Phase 4 catalogue and uncertainty margins."""
    return PhaseFourScientificGates.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_paired_noninferiority_contract(
    path: Path,
) -> PairedNoninferiorityContract:
    """Load the Phase 4 paired non-inferiority and power contract."""
    return PairedNoninferiorityContract.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_four_metric_registry(path: Path) -> PhaseFourMetricRegistry:
    """Load the Phase 4R direction-aware no-compensation metric registry."""
    return PhaseFourMetricRegistry.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_multiscale_contract(
    path: Path,
) -> PhaseFiveMultiscaleContract:
    """Load frozen Phase 5 scale, ownership, and failure meanings."""
    return PhaseFiveMultiscaleContract.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_scientific_gates(
    path: Path,
) -> PhaseFiveScientificGates:
    """Load reviewed Phase 5 absolute and paired scientific gates."""
    return PhaseFiveScientificGates.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_filter_selection(
    path: Path,
) -> PhaseFiveFilterSelection:
    """Load the reviewed Phase 5 filter-family decision."""
    return PhaseFiveFilterSelection.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_filter_review(path: Path) -> PhaseFiveFilterReview:
    """Load the frozen Step 2B paired representation-review contract."""
    return PhaseFiveFilterReview.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_filter_paired_decision(
    path: Path,
) -> PhaseFiveFilterPairedDecision:
    """Load the reviewed fail-closed Step 2B representation decision."""
    return PhaseFiveFilterPairedDecision.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_corrective_review(
    path: Path,
) -> PhaseFiveCorrectiveReview:
    """Load the frozen Step 2C corrective continuum-review contract."""
    return PhaseFiveCorrectiveReview.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_corrective_r_review(
    path: Path,
) -> PhaseFiveCorrectiveRReview:
    """Load the frozen Step 2C-R final-output correction contract."""
    return PhaseFiveCorrectiveRReview.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_corrective_a_review(
    path: Path,
) -> PhaseFiveCorrectiveAReview:
    """Load the frozen independent Step 2C-A astrometry review."""
    return PhaseFiveCorrectiveAReview.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_corrective_decision(
    path: Path,
) -> PhaseFiveCorrectiveDecision:
    """Load the reviewed fail-closed Step 2C corrective decision."""
    return PhaseFiveCorrectiveDecision.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_corrective_r_decision(
    path: Path,
) -> PhaseFiveCorrectiveRDecision:
    """Load the reviewed fail-closed Step 2C-R decision."""
    return PhaseFiveCorrectiveRDecision.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_corrective_a_decision(
    path: Path,
) -> PhaseFiveCorrectiveADecision:
    """Load the reviewed fail-closed one-look Step 2C-A decision."""
    return PhaseFiveCorrectiveADecision.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_astrometry_human_decision(
    path: Path,
) -> PhaseFiveAstrometryHumanDecision:
    """Load the approved prospective Step 2C-H astrometry decision."""
    return PhaseFiveAstrometryHumanDecision.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_astrometry_revision_review(
    path: Path,
) -> PhaseFiveAstrometryRevisionReview:
    """Load the frozen successor Step 2C-H astrometry review."""
    return PhaseFiveAstrometryRevisionReview.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_astrometry_selection_decision(
    path: Path,
) -> PhaseFiveAstrometrySelectionDecision:
    """Load the reviewed successor astrometry development decision."""
    return PhaseFiveAstrometrySelectionDecision.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_astrometry_follow_up_review(
    path: Path,
) -> PhaseFiveAstrometryFollowUpReview:
    """Load the frozen Step 2C-HR position-semantics review."""
    return PhaseFiveAstrometryFollowUpReview.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_astrometry_follow_up_development_decision(
    path: Path,
) -> PhaseFiveAstrometryFollowUpDevelopmentDecision:
    """Load the technical review of fresh segment-position development."""
    return PhaseFiveAstrometryFollowUpDevelopmentDecision.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_astrometry_follow_up_human_decision(
    path: Path,
) -> PhaseFiveAstrometryFollowUpHumanDecision:
    """Load the named confirmation-only Step 2C-HR approval."""
    return PhaseFiveAstrometryFollowUpHumanDecision.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_follow_up_confirmation_decision(
    path: Path,
) -> PhaseFiveAstrometryFollowUpConfirmationDecision:
    """Load the reviewed Step 2C-HR one-look confirmation decision."""
    return PhaseFiveAstrometryFollowUpConfirmationDecision.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_external_comparison_protocol(
    path: Path,
) -> PhaseFiveExternalComparisonProtocol:
    """Load the frozen Step 2C-P external source-finder protocol."""
    return PhaseFiveExternalComparisonProtocol.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_phase_five_external_execution_decision(
    path: Path,
) -> PhaseFiveExternalExecutionDecision:
    """Load the reviewed one-look Step 2C-P execution authorization."""
    return PhaseFiveExternalExecutionDecision.model_validate_json(
        path.read_text(encoding="utf-8")
    )
