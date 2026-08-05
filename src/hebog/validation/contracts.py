"""Versioned performance, scalability, behaviour, and scientific contracts.

These records describe gates and test obligations. They do not select an
execution plan or import a scheduler, read science data, or run benchmarks.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.evidence import WorkloadClass

_MINIMUM_MATRIX_SIZE = 256
_MAXIMUM_MATRIX_SIZE = 100_000
_DASK_MEMORY_THRESHOLD_COUNT = 4
_PHASE_FOUR_ANALYTIC_FAILURE_CASE_COUNT = 6
_PAIRED_CONFIDENCE_LEVEL = 0.95


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
    coverage_interval: Literal["wilson-score"]
    mean_interval: Literal["student-t"]
    dispersion_interval: Literal["scipy-bca-bootstrap-fixed-seed"]
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


class PairedNoninferiorityContract(_ContractModel):
    """Draft same-image comparison and power contract for Phase 4 closure."""

    schema_version: Literal[1]
    contract_id: Literal[
        "phase-4-paired-noninferiority",
        "phase-4s-paired-noninferiority",
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
