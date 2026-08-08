"""Tests for versioned performance, behaviour, and scientific contracts."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import hebog.validation.contracts as contract_models
from hebog.validation.contracts import (
    PerformanceMatrixContract,
    PhaseFourMetricRegistry,
    PhaseFourScientificGates,
    ScalabilityContract,
    load_performance_matrix,
    load_phase_four_measurement_contract,
    load_phase_four_metric_registry,
    load_phase_four_scientific_gates,
    load_phase_three_scientific_gates,
    load_public_behaviours,
    load_scalability_contract,
)

_ROOT = Path(__file__).parents[3]
_PERFORMANCE_PATH = _ROOT / "config/benchmarks/phase-0-performance.json"
_SCALABILITY_PATH = _ROOT / "config/benchmarks/phase-0-scalability.json"
_BEHAVIOURS_PATH = _ROOT / "config/contracts/phase-0-public-behaviours.json"
_PHASE_THREE_GATES_PATH = (
    _ROOT / "config/contracts/phase-3-scientific-gates.json"
)
_PHASE_FOUR_MEASUREMENT_PATH = (
    _ROOT / "config/contracts/phase-4-measurement.json"
)
_PHASE_FOUR_GATES_PATH = (
    _ROOT / "config/contracts/phase-4-scientific-gates.json"
)
_PHASE_FOUR_T_GATES_PATH = (
    _ROOT / "config/contracts/phase-4t-scientific-gates.json"
)
_PHASE_FOUR_METRICS_PATH = (
    _ROOT / "config/contracts/phase-4r-metric-registry.json"
)
_PHASE_FIVE_MULTISCALE_PATH = (
    _ROOT / "config/contracts/phase-5-multiscale.json"
)
_PHASE_FIVE_GATES_PATH = (
    _ROOT / "config/contracts/phase-5-scientific-gates.json"
)
_PHASE_FIVE_FILTER_SELECTION_PATH = (
    _ROOT / "config/contracts/phase-5-filter-selection.json"
)
_PHASE_FIVE_FILTER_REVIEW_PATH = (
    _ROOT / "config/contracts/phase-5-filter-paired-review.json"
)
_PHASE_FIVE_FILTER_PAIRED_DECISION_PATH = (
    _ROOT / "config/contracts/phase-5-filter-paired-decision.json"
)
_PHASE_FIVE_CORRECTIVE_REVIEW_PATH = (
    _ROOT / "config/contracts/phase-5-corrective-review.json"
)
_PHASE_FIVE_CORRECTIVE_DECISION_PATH = (
    _ROOT / "config/contracts/phase-5-corrective-decision.json"
)
_PHASE_FIVE_CORRECTIVE_R_REVIEW_PATH = (
    _ROOT / "config/contracts/phase-5-corrective-r-review.json"
)
_PHASE_FIVE_CORRECTIVE_R_DECISION_PATH = (
    _ROOT / "config/contracts/phase-5-corrective-r-decision.json"
)
_PHASE_FIVE_CORRECTIVE_A_REVIEW_PATH = (
    _ROOT / "config/contracts/phase-5-corrective-a-review.json"
)
_PHASE_FIVE_CORRECTIVE_A_DECISION_PATH = (
    _ROOT / "config/contracts/phase-5-corrective-a-decision.json"
)


def _duplicate_failure_case(payload: dict[str, Any]) -> None:
    """Make two analytic failure-case identifiers collide."""
    cases = payload["required_analytic_failure_cases"]
    cases[0] = cases[1]


def _repeat_failure_case(payload: dict[str, Any]) -> None:
    """Append a seventh duplicate analytic failure case."""
    cases = payload["required_analytic_failure_cases"]
    cases.append(cases[0])


def _duplicate_scientific_basis(payload: dict[str, Any]) -> None:
    """Make two scientific-basis links collide."""
    links = payload["scientific_basis"]
    links[0] = links[1]


def _use_insecure_scientific_basis(payload: dict[str, Any]) -> None:
    """Replace one scientific-basis link with an insecure URL."""
    payload["scientific_basis"][0] = "http://example.invalid/paper"


_INVALID_MEASUREMENT_MUTATIONS: tuple[
    tuple[Callable[[dict[str, Any]], None], str], ...
] = (
    (_duplicate_failure_case, "analytic failure case"),
    (_repeat_failure_case, "analytic failure case"),
    (_duplicate_scientific_basis, "basis links must be unique"),
    (_use_insecure_scientific_basis, "must use HTTPS"),
)

_INVALID_PHASE_FIVE_MULTISCALE_MUTATIONS: tuple[
    tuple[Callable[[dict[str, Any]], None], str], ...
] = (
    (
        lambda payload: payload["scales"].update(configured_orders=[1, 2]),
        "scale orders",
    ),
    (
        lambda payload: payload["scales"].update(
            nominal_fwhm_multipliers=[1.0, 2.0, 3.0]
        ),
        "nominal scales",
    ),
    (
        lambda payload: payload["scales"].update(maximum_fwhm_multiplier=3.0),
        "maximum Phase 5 scale",
    ),
    (
        lambda payload: payload["filtering"].update(
            candidates=[
                "undecimated-wavelet",
                "beam-aware-matched-filter",
            ]
        ),
        "filter candidates",
    ),
    (_duplicate_scientific_basis, "basis links must be unique"),
    (_use_insecure_scientific_basis, "must use HTTPS"),
)

_INVALID_PHASE_FIVE_GATE_MUTATIONS: tuple[
    tuple[Callable[[dict[str, Any]], None], str], ...
] = (
    (
        lambda payload: payload.update(confidence_level=0.9),
        "confidence level",
    ),
    (
        lambda payload: payload.update(governed_strata=["scale-1-beam"]),
        "governed strata",
    ),
    (
        lambda payload: payload["comparison"].update(
            references=["released-pybdsf"]
        ),
        "both PyBDSF references",
    ),
)


def test_checked_in_performance_matrix_covers_curve_and_workloads() -> None:
    """Every frozen size has all density classes and comparison rules."""
    matrix = load_performance_matrix(_PERFORMANCE_PATH)

    assert matrix.sizes_pixels[0] == 256
    assert matrix.sizes_pixels[-1] == 100_000
    assert len(matrix.sizes_pixels) >= 8
    assert len(matrix.workload_classes) == 3
    assert matrix.previous_hebog.minimum_measured_repetitions >= 5


def test_performance_matrix_rejects_a_missing_workload_class() -> None:
    """A fast sparse path cannot stand in for normal and dense work."""
    matrix = load_performance_matrix(_PERFORMANCE_PATH)
    payload = matrix.model_dump(mode="json")
    payload["workload_classes"] = payload["workload_classes"][:-1]

    with pytest.raises(ValidationError, match="every workload class"):
        PerformanceMatrixContract.model_validate(payload)


def test_checked_in_scalability_contract_freezes_required_topologies() -> None:
    """The 100k case owns explicit planes, memory, storage, and node gates."""
    contract = load_scalability_contract(_SCALABILITY_PATH)

    assert contract.logical_shape_yx == (100_000, 100_000)
    assert [gate.worker_nodes for gate in contract.node_gates] == [
        1,
        10,
        50,
        100,
        200,
    ]
    assert contract.resource_profile.node_memory_bytes == 512 * 1024**3
    assert contract.maximum_worker_peak_fraction == 0.75


def test_scalability_contract_rejects_overcommitted_worker_memory() -> None:
    """Concurrent pipeline and platform reserves constrain worker admission."""
    contract = load_scalability_contract(_SCALABILITY_PATH)
    payload = contract.model_dump(mode="json")
    payload["resource_profile"]["worker_memory_limit_bytes"] = 100 * 1024**3

    with pytest.raises(ValidationError, match="worker limits"):
        ScalabilityContract.model_validate(payload)


def test_every_public_behaviour_has_one_strict_xfail_owner() -> None:
    """Frozen behaviours start with a failing executable specification."""
    manifest = load_public_behaviours(_BEHAVIOURS_PATH)

    assert len(manifest.behaviours) == 11
    assert all(
        behaviour.expected_until_implemented == "strict-xfail"
        for behaviour in manifest.behaviours
    )
    assert len({item.test_id for item in manifest.behaviours}) == len(
        manifest.behaviours
    )


def test_public_behaviour_manifest_matches_executable_test_ids() -> None:
    """Every frozen behaviour names one collected executable test."""
    manifest = load_public_behaviours(_BEHAVIOURS_PATH)
    test_paths = (
        _ROOT / "tests/contract/test_public_behaviours.py",
        _ROOT / "tests/acceptance/test_acceptance_scaffold.py",
    )
    implemented_test_ids = {
        node.name
        for path in test_paths
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }

    assert implemented_test_ids == {
        behaviour.test_id for behaviour in manifest.behaviours
    }


def test_phase_three_gates_are_foreground_sensitive_and_role_specific() -> (
    None
):
    """Compact, generated, and held-out lanes freeze reviewed mask margins."""
    gates = load_phase_three_scientific_gates(_PHASE_THREE_GATES_PATH)

    assert gates.status == "reviewed-provisional"
    assert gates.confidence_level == 0.95
    assert gates.low_snr_threshold_crossings == "report-only"
    assert gates.compact_reference.mask.minimum_intersection_over_union > 0.9
    assert gates.compact_reference.islands.minimum_completeness == 1.0
    assert gates.heldout_qualification.mask.minimum_precision >= 0.8


def test_phase_four_measurement_contract_freezes_scientific_meanings() -> None:
    """Measurement inputs, outputs, failures, and ownership are explicit."""
    contract = load_phase_four_measurement_contract(
        _PHASE_FOUR_MEASUREMENT_PATH
    )

    assert contract.status == "reviewed-provisional"
    assert contract.schema_version == 2
    assert contract.scope.image_kind == "mfs-stokes-i"
    assert contract.scope.brightness_unit == "Jy/beam"
    assert contract.measurements.island_integrated_flux.startswith(
        "owned-valid-pixel-sum"
    )
    assert contract.measurements.pixel_solid_angle.startswith(
        "absolute-local-tangent-plane"
    )
    assert contract.measurements.restoring_beam_solid_angle.startswith(
        "pi-major-fwhm"
    )
    assert contract.measurements.component_integrated_flux.startswith(
        "peak-for-unresolved"
    )
    assert contract.coordinates.pixel_origin == "zero-based-pixel-centres"
    assert contract.coordinates.position_angle == "east-of-north-modulo-180"
    assert contract.association.region_membership == (
        "worker-local-watershed-labels"
    )
    assert contract.association.compact_source_policy == (
        "one-source-per-deblended-region"
    )
    assert contract.association.truth_resolvability_policy == (
        "distinct-eligible-observed-maximum"
    )
    assert contract.association.unresolved_truth_policy == (
        "explicit-group-centroid-and-total-flux"
    )
    assert contract.association.joint_model_policy == (
        "deferred-until-identifiability-and-reliability-evidence"
    )
    assert contract.failures.unresolved_deconvolution == (
        "null-shape-with-unresolved-quality-flag"
    )
    assert contract.failures.unavailable_uncertainty == (
        "null-with-quality-flag"
    )
    assert contract.fitting.selective_policy == (
        "fit-all-reference-before-selection"
    )
    assert contract.eligibility.population_selection == (
        "reference-or-injected-truth-only"
    )
    assert contract.eligibility.missing_candidate_value == (
        "counts-as-unavailable-not-excluded"
    )
    assert contract.eligibility.position_angle_minimum_axis_ratio == 1.1
    assert contract.eligibility.availability_reporting == (
        "required-for-every-gated-field"
    )
    assert set(contract.required_analytic_failure_cases) == {
        "fit-non-convergence",
        "marginal-deconvolution",
        "non-finite-owned-pixels",
        "non-positive-measurement",
        "singular-covariance",
        "underdetermined-region",
    }
    assert contract.human_scientific_review == "required-before-stable-default"
    assert len(contract.scientific_basis) >= 4


def test_phase_five_contract_freezes_multiscale_meanings() -> None:
    """Scale, ownership, failure, and combined-product semantics are fixed."""
    contract = contract_models.load_phase_five_multiscale_contract(
        _PHASE_FIVE_MULTISCALE_PATH
    )

    assert contract.status == "reviewed-development"
    assert contract.schema_version == 1
    assert contract.scales.reference == "restoring-beam-major-fwhm"
    assert contract.scales.configured_orders == (1, 2, 3)
    assert contract.scales.nominal_fwhm_multipliers == (1.0, 2.0, 4.0)
    assert contract.scales.maximum_fwhm_multiplier == 4.0
    assert contract.filtering.family_selection == "phase-5-step-2-evidence"
    assert contract.filtering.background_rms_reuse == (
        "phase-2-products-no-recursive-estimation"
    )
    assert contract.validity.minimum_support_fraction == 0.5
    assert contract.failures.incomplete_catalogue == "publication-forbidden"
    assert contract.association.identity == (
        "canonical-global-overlap-flux-and-scale-provenance"
    )
    assert contract.combined_catalogue.compact_only == (
        "byte-identical-when-no-multiscale-evidence"
    )
    assert contract.qualification_policy == "freeze-before-result-inspection"
    assert contract.development_review == "ai-scientific-review-recorded"
    assert contract.independent_human_review == "required-before-cutover"


@pytest.mark.parametrize(
    ("mutation", "message"),
    _INVALID_PHASE_FIVE_MULTISCALE_MUTATIONS,
)
def test_phase_five_contract_rejects_changed_scientific_meanings(
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    """The reviewed scale and provenance meanings cannot drift."""
    contract = contract_models.load_phase_five_multiscale_contract(
        _PHASE_FIVE_MULTISCALE_PATH
    )
    payload = contract.model_dump(mode="json")
    mutation(payload)

    with pytest.raises(ValidationError, match=message):
        type(contract).model_validate(payload)


def test_phase_five_gates_are_scale_stratified_and_conjunctive() -> None:
    """Use absolute truth and both compatibility references."""
    gates = contract_models.load_phase_five_scientific_gates(
        _PHASE_FIVE_GATES_PATH
    )

    assert gates.status == "reviewed-development"
    assert gates.confidence_level == 0.95
    assert gates.qualification.minimum_noise_realizations == 400
    assert gates.qualification.minimum_joint_power == 0.9
    assert gates.qualification.opening_rule == "one-look-terminal-decision"
    assert gates.comparison.references == (
        "released-pybdsf",
        "pinned-pybdsf-master",
    )
    assert gates.comparison.rule == (
        "every-absolute-and-paired-gate-passes-no-compensation"
    )
    assert gates.threshold_crossings == "report-only-curves"
    assert set(gates.governed_strata) >= {
        "above-compact-deblend-limit",
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
    }
    assert gates.heldout_qualification.minimum_completeness >= 0.9
    assert gates.heldout_qualification.minimum_reliability >= 0.95
    assert gates.heldout_qualification.maximum_duplicate_fraction <= 0.02
    assert gates.heldout_qualification.minimum_rapthor_decision_agreement == (
        0.995
    )
    assert gates.paired_margins.maximum_completeness_loss <= 0.02
    assert gates.paired_margins.maximum_integrated_flux_error_increase <= 0.05


@pytest.mark.parametrize(
    ("mutation", "message"),
    _INVALID_PHASE_FIVE_GATE_MUTATIONS,
)
def test_phase_five_gates_reject_incomplete_governance(
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    """Confidence, strata, and both references remain binding."""
    gates = contract_models.load_phase_five_scientific_gates(
        _PHASE_FIVE_GATES_PATH
    )
    payload = gates.model_dump(mode="json")
    mutation(payload)

    with pytest.raises(ValidationError, match=message):
        type(gates).model_validate(payload)


def test_phase_five_gates_reject_a_tail_tighter_than_its_median() -> None:
    """Extended error tails cannot be numerically tighter than medians."""
    gates = contract_models.load_phase_five_scientific_gates(
        _PHASE_FIVE_GATES_PATH
    )
    payload = gates.model_dump(mode="json")
    payload["generated_regression"][
        "maximum_median_integrated_flux_fractional_error"
    ] = 0.3
    payload["generated_regression"][
        "maximum_percentile_95_integrated_flux_fractional_error"
    ] = 0.2

    with pytest.raises(ValidationError, match="extended-error tail"):
        type(gates).model_validate(payload)


def test_phase_five_filter_selection_freezes_the_bounded_float64_design() -> (
    None
):
    """The development decision fixes the smallest adequate representation."""
    decision = contract_models.load_phase_five_filter_selection(
        _PHASE_FIVE_FILTER_SELECTION_PATH
    )

    assert decision.status == "reviewed-development"
    assert decision.selected_family == "beam-aware-matched-filter"
    assert decision.rejected_family == "undecimated-wavelet"
    assert decision.minimum_support_fraction == 0.5
    assert decision.truncation_sigma == 4.0
    assert decision.dtype == "float64"
    assert decision.convolution_backend == "scipy-signal-fftconvolve"
    assert decision.development_halo_pixels == (9, 17, 34)
    assert decision.convolution_count_per_image == 9
    assert decision.temporary_plane_count == 7
    assert decision.lower_precision_authorized is False
    assert decision.native_code_authorized is False
    assert decision.qualification_opened is False


def test_phase_five_filter_selection_rejects_unreviewed_drift() -> None:
    """Candidate, precision, and support semantics cannot change silently."""
    decision = contract_models.load_phase_five_filter_selection(
        _PHASE_FIVE_FILTER_SELECTION_PATH
    )
    payload = decision.model_dump(mode="json")
    payload["selected_family"] = "undecimated-wavelet"

    with pytest.raises(ValidationError):
        type(decision).model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("minimum_support_fraction", 0.6, "minimum support"),
        ("truncation_sigma", 3.0, "four sigma"),
        ("development_halo_pixels", [9, 17, 35], "development halos"),
        ("convolution_count_per_image", 10, "nine convolutions"),
        ("temporary_plane_count", 8, "seven temporaries"),
    ],
)
def test_phase_five_filter_selection_rejects_cost_or_support_drift(
    field: str,
    value: object,
    message: str,
) -> None:
    """The selected bank cannot silently exceed its reviewed bounds."""
    decision = contract_models.load_phase_five_filter_selection(
        _PHASE_FIVE_FILTER_SELECTION_PATH
    )
    payload = decision.model_dump(mode="json")
    payload[field] = value

    with pytest.raises(ValidationError, match=message):
        type(decision).model_validate(payload)


def test_phase_five_filter_review_freezes_science_first_selection() -> None:
    """The paired review precedes Step 3 and any candidate optimization."""
    review = contract_models.load_phase_five_filter_review(
        _PHASE_FIVE_FILTER_REVIEW_PATH
    )

    assert review.status == "frozen-before-paired-results"
    assert review.candidates == (
        "beam-aware-matched-filter",
        "undecimated-wavelet",
    )
    assert tuple(item.role for item in review.dataset_manifests) == (
        "development",
        "regression",
    )
    assert review.matrix.scale_orders == (1, 2, 3)
    assert review.matrix.support_fraction_bounds == (0.5, 1.0)
    assert review.matrix.snr_levels == (5.0, 8.0, 15.0, 30.0)
    assert "integrated-flux-fractional-error" in review.binding_metrics
    assert "calibrated-response-snr" in review.binding_metrics
    assert review.absolute_gates.minimum_completeness == 0.9
    assert review.absolute_gates.minimum_reliability == 0.95
    assert review.paired_margins.maximum_completeness_loss == 0.02
    assert review.statistical_design.bootstrap_resamples == 10_000
    assert review.decision_policy.inconclusive == "select-neither"
    assert review.decision_policy.optimization == "after-selection-only"
    assert review.step_three_authorized is False
    assert review.qualification_opened is False


_INVALID_PHASE_FIVE_FILTER_REVIEW_MUTATIONS: tuple[
    tuple[Callable[[dict[str, Any]], None], str], ...
] = (
    (
        lambda payload: payload.update(
            {"candidates": ["undecimated-wavelet"]}
        ),
        "candidates",
    ),
    (
        lambda payload: payload["matrix"].update(
            {"support_fraction_bounds": [0.6, 1.0]}
        ),
        "support fraction",
    ),
    (
        lambda payload: payload["matrix"].update({"scale_orders": [1, 2]}),
        "scales",
    ),
    (
        lambda payload: payload["matrix"].update(
            {"snr_levels": [5.0, 8.0, 15.0, 31.0]}
        ),
        "SNR levels",
    ),
    (
        lambda payload: payload["matrix"].update({"detection_sigma": 4.5}),
        "thresholds",
    ),
    (
        lambda payload: payload["matrix"]["mask_geometries"].reverse(),
        "mask geometries",
    ),
    (
        lambda payload: payload["matrix"]["morphologies"].reverse(),
        "morphologies",
    ),
    (
        lambda payload: payload["matrix"]["noise_models"].reverse(),
        "noise models",
    ),
    (
        lambda payload: payload["dataset_manifests"].reverse(),
        "development and regression",
    ),
    (
        lambda payload: payload["absolute_gates"].update(
            {"maximum_median_response_fractional_error": 0.2}
        ),
        "tail cannot be tighter",
    ),
    (
        lambda payload: payload["binding_metrics"].__setitem__(
            -1, "calibrated-response-snr"
        ),
        "binding metrics must be complete",
    ),
    (
        lambda payload: payload["binding_metrics"].reverse(),
        "binding metrics must be canonical",
    ),
    (
        lambda payload: payload["diagnostic_metrics"].reverse(),
        "diagnostic metrics must be canonical",
    ),
    (
        lambda payload: payload["statistical_design"].update(
            {"confidence_level": 0.9}
        ),
        "confidence level",
    ),
    (
        lambda payload: payload.update({"step_three_authorized": True}),
        "False",
    ),
)


@pytest.mark.parametrize(
    ("mutation", "message"),
    _INVALID_PHASE_FIVE_FILTER_REVIEW_MUTATIONS,
)
def test_phase_five_filter_review_rejects_post_hoc_drift(
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    """Candidate, population, support, and sequencing cannot drift."""
    review = contract_models.load_phase_five_filter_review(
        _PHASE_FIVE_FILTER_REVIEW_PATH
    )
    payload = review.model_dump(mode="json")
    mutation(payload)

    with pytest.raises(ValidationError, match=message):
        type(review).model_validate(payload)


def test_phase_five_filter_paired_decision_blocks_step_three() -> None:
    """The completed review records no scientifically eligible candidate."""
    decision = contract_models.load_phase_five_filter_paired_decision(
        _PHASE_FIVE_FILTER_PAIRED_DECISION_PATH
    )

    assert decision.status == "reviewed-inconclusive"
    assert decision.decision == "select-neither"
    assert decision.selected_family is None
    assert tuple(item.family for item in decision.candidates) == (
        "beam-aware-matched-filter",
        "undecimated-wavelet",
    )
    assert all(not item.passes_absolute for item in decision.candidates)
    assert decision.step_three_authorized is False
    assert decision.optimization_authorized is False
    assert decision.qualification_opened is False
    assert decision.independent_human_scientific_review == "still-required"


def test_phase_five_filter_paired_decision_rejects_false_authorization() -> (
    None
):
    """An inconclusive decision cannot silently authorize implementation."""
    decision = contract_models.load_phase_five_filter_paired_decision(
        _PHASE_FIVE_FILTER_PAIRED_DECISION_PATH
    )
    payload = decision.model_dump(mode="json")
    payload["step_three_authorized"] = True

    with pytest.raises(ValidationError):
        type(decision).model_validate(payload)


def test_phase_five_corrective_review_freezes_amended_endpoint_semantics() -> (
    None
):
    """Step 2C must be frozen before evaluating the corrective candidate."""
    review = contract_models.load_phase_five_corrective_review(
        _PHASE_FIVE_CORRECTIVE_REVIEW_PATH
    )

    assert review.status == "frozen-before-corrective-results"
    assert review.prior_decision_sha256 == (
        "d2b3f5f4fc51b32b93bd29f0e08047e8bd60c60b64f5f046e2031bc0eb1c3594"
    )
    assert review.candidates == (
        "beam-aware-matched-filter",
        "residual-b3-atrous",
    )
    assert review.matrix.detection_sigma == 5.0
    assert review.matrix.island_sigma == 3.0
    assert review.response_endpoint.signal == "final-reconstructed-signal"
    assert review.response_endpoint.truth == "observable-valid-domain-truth"
    assert review.final_measurement.mask == "original-residual-seed-and-grow"
    assert review.final_measurement.photometry == "original-residual-pixels"
    assert review.final_measurement.astrometry == "original-residual-pixels"
    assert review.corrective_design.wavelet == "normalized-b3-spline-atrous"
    assert review.corrective_design.compact_treatment == (
        "exclude-or-subtract-accepted-compact-emission"
    )
    assert review.corrective_design.matched_filter_role == (
        "known-template-seed-aid-and-governed-comparator"
    )
    assert review.bounded_implementation.maximum_halo_pixels == 14
    assert review.bounded_implementation.durable_response_bank is False
    assert review.absolute_gates.minimum_mask_intersection_over_union == 0.8
    assert review.paired_margins.maximum_completeness_loss == 0.02
    assert review.step_three_authorized is False
    assert review.qualification_opened is False


def test_phase_five_corrective_review_rejects_gate_or_measurement_drift() -> (
    None
):
    """Corrective staging cannot weaken a gate or measure wavelet pixels."""
    review = contract_models.load_phase_five_corrective_review(
        _PHASE_FIVE_CORRECTIVE_REVIEW_PATH
    )
    gate_payload = review.model_dump(mode="json")
    gate_payload["absolute_gates"]["minimum_reliability"] = 0.9
    measurement_payload = review.model_dump(mode="json")
    measurement_payload["final_measurement"]["photometry"] = (
        "wavelet-coefficients"
    )

    with pytest.raises(ValidationError, match="unchanged Step 2B gates"):
        type(review).model_validate(gate_payload)
    with pytest.raises(ValidationError):
        type(review).model_validate(measurement_payload)


def test_phase_five_corrective_decision_keeps_step_three_closed() -> None:
    """The reviewed Step 2C failure identifies the next frozen redesign."""
    decision = contract_models.load_phase_five_corrective_decision(
        _PHASE_FIVE_CORRECTIVE_DECISION_PATH
    )

    assert decision.status == "reviewed-rejected"
    assert decision.decision == "reject-corrective"
    assert decision.selected_family is None
    assert tuple(item.family for item in decision.candidates) == (
        "beam-aware-matched-filter",
        "residual-b3-atrous",
    )
    assert decision.candidates[1].failed_absolute_endpoint_count == 23
    assert decision.candidates[1].failed_paired_endpoint_count == 8
    assert decision.candidates[1].bounded_cost == (21, 7, 38)
    assert decision.next_action == (
        "redesign-measurement-association-and-false-positive-control"
    )
    assert decision.step_three_authorized is False
    assert decision.optimization_authorized is False
    assert decision.qualification_opened is False


def test_phase_five_corrective_r_review_freezes_all_four_corrections() -> None:
    """Step 2C-R rules and unchanged gates precede replacement results."""
    review = contract_models.load_phase_five_corrective_r_review(
        _PHASE_FIVE_CORRECTIVE_R_REVIEW_PATH
    )

    assert review.status == "frozen-before-corrective-r-results"
    assert review.prior_decision_sha256 == (
        "7d50397bc679b06dd856e9484675e4981eee55448c87acc96ff9d249e41d4684"
    )
    assert review.corrections.astrometry_dilation_pixels == 2
    assert review.corrections.association_distance_beams == 3.0
    assert review.corrections.component_flux_fraction == 0.1
    assert review.corrections.minimum_island_area_beams == 1.0
    assert review.corrections.minimum_direct_seed_sigma == 5.0
    assert review.supersedes_failed_protocol_sha256 == (
        "57a8e1171bd1e555dc262ccc35f59aa3b271c0ae5c43ea4fc896f9cc6dc77e22"
    )
    assert review.absolute_gates.minimum_reliability == 0.95
    assert review.absolute_gates.maximum_percentile_95_position_beams == 0.25
    assert review.paired_margins.maximum_position_error_increase_beams == 0.05
    assert review.step_three_authorized is False
    assert review.qualification_opened is False


def test_phase_five_corrective_r_review_rejects_correction_drift() -> None:
    """A result run cannot retune a frozen correction constant."""
    review = contract_models.load_phase_five_corrective_r_review(
        _PHASE_FIVE_CORRECTIVE_R_REVIEW_PATH
    )
    payload = review.model_dump(mode="json")
    payload["corrections"]["minimum_island_area_beams"] = 0.75

    with pytest.raises(ValidationError, match="constants must remain frozen"):
        type(review).model_validate(payload)


def test_phase_five_corrective_r_decision_keeps_step_three_closed() -> None:
    """Only astrometry variance remains, but the absolute rule is binding."""
    decision = contract_models.load_phase_five_corrective_r_decision(
        _PHASE_FIVE_CORRECTIVE_R_DECISION_PATH
    )

    assert decision.status == "reviewed-rejected"
    assert decision.decision == "reject-corrective-r"
    assert decision.selected_family is None
    assert decision.candidates[1].failed_absolute_endpoint_count == 9
    assert decision.candidates[1].failed_paired_endpoint_count == 0
    assert decision.candidates[1].noninferior_to_other is True
    assert decision.corrective_failure_domains == ("astrometry-variance",)
    assert decision.step_three_authorized is False
    assert decision.optimization_authorized is False
    assert decision.qualification_opened is False


def test_phase_five_corrective_a_review_freezes_independent_estimator() -> (
    None
):
    """The final astrometry protocol precedes confirmation results."""
    review = contract_models.load_phase_five_corrective_a_review(
        _PHASE_FIVE_CORRECTIVE_A_REVIEW_PATH
    )

    assert review.status == "frozen-before-corrective-a-results"
    assert review.prior_decision_sha256 == (
        "6727657ff039b1ccf0ab88c169df0f02cf1b080b6ca1ca4b7059f49d0640340d"
    )
    assert review.dataset_manifests[1].manifest == (
        "config/datasets/phase-5-corrective-a-confirmation.json"
    )
    assert review.dataset_manifests[1].manifest_sha256 == (
        "7576f8e6e373b12a42c9820ee381750c32208444682bde4a52a1311cccfc6011"
    )
    estimator = review.astrometry_estimator
    assert estimator.peak_seed_sigma == 6.0
    assert estimator.peak_separation_beams == 2.0
    assert estimator.maximum_components == 6
    assert estimator.model_weight == 0.5
    assert estimator.maximum_normalized_cost == 2.0
    assert estimator.maximum_model_moment_disagreement_beams == 1.0
    assert review.absolute_gates.maximum_percentile_95_position_beams == 0.25
    assert review.paired_margins.maximum_position_error_increase_beams == 0.05
    assert review.confirmation_reuse == "one-look-no-tuning-or-rescoring"
    assert review.step_three_authorized is False
    assert review.qualification_opened is False


def test_phase_five_corrective_a_review_rejects_estimator_drift() -> None:
    """Confirmation cannot silently retune a development-selected constant."""
    review = contract_models.load_phase_five_corrective_a_review(
        _PHASE_FIVE_CORRECTIVE_A_REVIEW_PATH
    )
    payload = review.model_dump(mode="json")
    payload["astrometry_estimator"]["model_weight"] = 0.6

    with pytest.raises(ValidationError, match="estimator constants"):
        type(review).model_validate(payload)

    payload = review.model_dump(mode="json")
    payload["dataset_manifests"][1]["manifest_sha256"] = "0" * 64

    with pytest.raises(ValidationError, match="datasets must remain frozen"):
        type(review).model_validate(payload)


def test_phase_five_corrective_a_decision_requires_human_review() -> None:
    """The failed one-look confirmation cannot be tuned or rescored."""
    decision = contract_models.load_phase_five_corrective_a_decision(
        _PHASE_FIVE_CORRECTIVE_A_DECISION_PATH
    )

    assert decision.status == "reviewed-rejected"
    assert decision.decision == "reject-corrective-a"
    assert decision.selected_family is None
    assert decision.candidates[1].failed_absolute_endpoint_count == 5
    assert decision.candidates[1].failed_paired_endpoint_count == 0
    assert decision.candidates[1].noninferior_to_other is True
    assert decision.corrective_failure_domains == (
        "astrometry-curved-filament-variance",
        "astrometry-uncertainty-undercoverage",
    )
    assert decision.independent_human_scientific_review == (
        "required-before-any-further-astrometry-revision"
    )
    assert decision.step_three_authorized is False
    assert decision.optimization_authorized is False
    assert decision.qualification_opened is False


def test_phase_five_corrective_a_decision_rejects_record_drift() -> None:
    """The closed one-look result cannot change counts or failure domains."""
    decision = contract_models.load_phase_five_corrective_a_decision(
        _PHASE_FIVE_CORRECTIVE_A_DECISION_PATH
    )

    payload = decision.model_dump(mode="json")
    payload["candidates"][1]["failed_absolute_endpoint_count"] = 4
    with pytest.raises(ValidationError, match="counts must remain exact"):
        type(decision).model_validate(payload)

    payload = decision.model_dump(mode="json")
    payload["corrective_failure_domains"].reverse()
    with pytest.raises(ValidationError, match="domains must remain exact"):
        type(decision).model_validate(payload)

    payload = decision.model_dump(mode="json")
    payload["candidates"][1]["bounded_cost"][0] = 0
    with pytest.raises(ValidationError, match="costs must be positive"):
        type(decision).model_validate(payload)


def test_phase_four_gates_freeze_role_specific_catalogue_margins() -> None:
    """Phase 4 has explicit provisional shape and uncertainty questions."""
    gates = load_phase_four_scientific_gates(_PHASE_FOUR_GATES_PATH)

    assert gates.status == "reviewed-provisional"
    assert gates.confidence_level == 0.95
    assert gates.low_snr_threshold_crossings == "report-only"
    assert gates.shape_uncertainty == "report-only"
    assert gates.noisy_source_decision == (
        "snr-stratified-confidence-intervals-and-catastrophic-rate"
    )
    assert gates.compact_reference.absolute_tail_policy == "gate"
    assert gates.generated_regression.absolute_tail_policy == "report-only"
    assert gates.heldout_qualification.absolute_tail_policy == "report-only"
    assert gates.unresolved_group.status == "reviewed-provisional"
    assert gates.unresolved_group.population == (
        "declared-unresolved-association-groups"
    )
    assert gates.unresolved_group.maximum_median_position_beams == 0.1
    assert gates.unresolved_group.maximum_percentile_95_position_beams == 0.2
    assert (
        gates.unresolved_group.maximum_median_integrated_flux_fractional_difference
        == 0.1
    )
    assert (
        gates.unresolved_group.maximum_percentile_95_integrated_flux_fractional_difference
        == 0.2
    )
    assert gates.compact_reference.minimum_completeness == 1.0
    assert gates.compact_reference.minimum_association_pair_precision == 1.0
    assert gates.compact_reference.minimum_association_pair_recall == 1.0
    assert gates.compact_reference.minimum_fitted_shape_availability == 1.0
    assert (
        gates.compact_reference.minimum_position_flux_uncertainty_availability
        == 1.0
    )
    assert gates.compact_reference.position_and_flux_population == (
        "isolated-compact-snr-at-least-10"
    )
    assert gates.heldout_qualification.association_population == (
        "declared-compact-associations-snr-at-least-10"
    )
    assert (
        gates.generated_regression.maximum_catastrophic_outlier_fraction < 0.01
    )
    assert gates.heldout_qualification.minimum_point_source_specificity >= 0.95
    assert (
        gates.heldout_qualification.minimum_clear_resolved_classification_recall
        >= 0.95
    )
    assert gates.extension_classification.method == (
        "integrated-to-peak-ratio-uncertainty"
    )
    assert gates.extension_classification.significance_sigma == 5.0
    assert (
        gates.extension_classification.clear_resolved_minimum_area_ratio == 3.0
    )
    assert (
        gates.extension_classification.clear_resolved_minimum_signal_to_noise
        == 25.0
    )
    assert (
        gates.extension_classification.resolved_integrated_flux_uncertainty
        == "report-only"
    )
    assert (
        gates.extension_classification.marginal_resolved_population.endswith(
            "report-only"
        )
    )
    assert (
        gates.extension_classification.marginal_resolved_integrated_flux_catastrophic_rate
        == "report-only"
    )
    assert gates.uncertainty.minimum_samples_per_stratum >= 200
    assert gates.uncertainty.confidence_interval_level == 0.95
    assert gates.uncertainty.equivalence_rule == (
        "entire-confidence-interval-within-margins"
    )
    assert gates.uncertainty.coverage_interval == "wilson-score"
    assert gates.uncertainty.mean_interval == "student-t"
    assert gates.uncertainty.dispersion_interval == (
        "scipy-bca-bootstrap-fixed-seed"
    )
    assert gates.uncertainty.bootstrap_resamples >= 10_000


def test_phase4t_gates_change_only_generated_distribution_roles() -> None:
    """The confirmation retains uncertainty limits while fixing raw roles."""
    historical = load_phase_four_scientific_gates(_PHASE_FOUR_GATES_PATH)
    confirmation = load_phase_four_scientific_gates(_PHASE_FOUR_T_GATES_PATH)

    assert confirmation.compact_reference.absolute_median_policy == "gate"
    assert (
        confirmation.generated_regression.absolute_median_policy
        == "report-only"
    )
    assert (
        confirmation.heldout_qualification.absolute_median_policy
        == "report-only"
    )
    historical_uncertainty = historical.uncertainty.model_dump(mode="json")
    confirmation_uncertainty = confirmation.uncertainty.model_dump(mode="json")
    for method in (
        "coverage_interval",
        "mean_interval",
        "dispersion_interval",
    ):
        historical_uncertainty.pop(method)
        confirmation_uncertainty.pop(method)
    assert confirmation_uncertainty == historical_uncertainty
    assert (
        confirmation.uncertainty.coverage_interval
        == "cluster-robust-student-t"
    )
    assert confirmation.uncertainty.mean_interval == "cluster-robust-student-t"
    assert confirmation.uncertainty.dispersion_interval == (
        "cluster-percentile-bootstrap-fixed-seed"
    )
    assert confirmation.catastrophic_outlier == historical.catastrophic_outlier
    assert confirmation.extension_classification == (
        historical.extension_classification
    )


def test_phase_four_recovery_registry_forbids_metric_compensation() -> None:
    """Every absolute and tail metric is independently comparison-gated."""
    registry = load_phase_four_metric_registry(_PHASE_FOUR_METRICS_PATH)

    assert registry.status == "reviewed-qualification"
    assert registry.human_scientific_review == "qualification-reviewed"
    assert registry.comparison_rule == (
        "every-metric-passes-no-compensation-or-weighted-score"
    )
    assert registry.point_estimate_rule == (
        "within-practical-margin-on-frozen-development-regression"
    )
    assert len(registry.metrics) == 35
    assert all(
        metric.primary_practical_regression_margin
        == metric.secondary_practical_regression_margin
        for metric in registry.metrics
    )
    assert {
        metric.metric_id
        for metric in registry.metrics
        if metric.absolute_role == "report-only"
    } == {
        "median-deconvolved-axis",
        "median-deconvolved-position-angle",
        "median-fitted-axis",
        "median-fitted-position-angle",
        "median-integrated-flux",
        "median-peak-flux",
        "median-position",
        "percentile-95-position",
        "percentile-95-peak-flux",
        "percentile-95-integrated-flux",
        "percentile-95-fitted-axis",
        "percentile-95-deconvolved-axis",
        "percentile-95-fitted-position-angle",
        "percentile-95-deconvolved-position-angle",
    }
    completion = next(
        metric
        for metric in registry.metrics
        if metric.metric_id == "implementation-completion"
    )
    assert completion.primary_practical_regression_margin == 0.0


def test_phase_four_recovery_registry_rejects_duplicate_metrics() -> None:
    """A metric cannot be counted twice in the conjunctive decision."""
    registry = load_phase_four_metric_registry(_PHASE_FOUR_METRICS_PATH)
    payload = registry.model_dump(mode="json")
    payload["metrics"].append(payload["metrics"][0])

    with pytest.raises(ValidationError, match="metric identifiers"):
        PhaseFourMetricRegistry.model_validate(payload)


def test_phase_four_recovery_registry_binds_direction_to_ideal() -> None:
    """Rate and error directions cannot silently reverse comparison signs."""
    registry = load_phase_four_metric_registry(_PHASE_FOUR_METRICS_PATH)
    payload = registry.model_dump(mode="json")
    payload["metrics"][0]["ideal_value"] = 0.0

    with pytest.raises(ValidationError, match="metric ideal"):
        PhaseFourMetricRegistry.model_validate(payload)


def test_phase_four_recovery_registry_uses_one_dual_reference_margin() -> None:
    """A looser secondary-reference comparison cannot be hidden in config."""
    registry = load_phase_four_metric_registry(_PHASE_FOUR_METRICS_PATH)
    payload = registry.model_dump(mode="json")
    payload["metrics"][0]["secondary_practical_regression_margin"] = 0.1

    with pytest.raises(ValidationError, match="both PyBDSF references"):
        PhaseFourMetricRegistry.model_validate(payload)


def test_phase_four_recovery_registry_requires_canonical_strata() -> None:
    """Duplicate or reordered strata cannot change report ownership."""
    registry = load_phase_four_metric_registry(_PHASE_FOUR_METRICS_PATH)
    payload = registry.model_dump(mode="json")
    payload["governed_strata"] = list(reversed(payload["governed_strata"]))

    with pytest.raises(ValidationError, match="strata must be canonical"):
        PhaseFourMetricRegistry.model_validate(payload)


def test_phase_four_recovery_registry_requires_completion() -> None:
    """Scientific accuracy cannot compensate for an implementation failure."""
    registry = load_phase_four_metric_registry(_PHASE_FOUR_METRICS_PATH)
    payload = registry.model_dump(mode="json")
    payload["metrics"] = [
        metric
        for metric in payload["metrics"]
        if metric["metric_id"] != "implementation-completion"
    ]

    with pytest.raises(ValidationError, match="include completion"):
        PhaseFourMetricRegistry.model_validate(payload)


def test_phase_four_gates_reject_percentiles_tighter_than_medians() -> None:
    """Tail gates cannot be numerically stricter than their medians."""
    gates = load_phase_four_scientific_gates(_PHASE_FOUR_GATES_PATH)
    payload = gates.model_dump(mode="json")
    payload["generated_regression"][
        "maximum_median_fitted_axis_fractional_difference"
    ] = 0.2
    payload["generated_regression"][
        "maximum_percentile_95_fitted_axis_fractional_difference"
    ] = 0.1

    with pytest.raises(ValidationError, match="95th-percentile"):
        PhaseFourScientificGates.model_validate(payload)


def test_phase_four_group_gates_reject_a_tighter_tail() -> None:
    """Unresolved-group tail gates cannot be tighter than their medians."""
    gates = load_phase_four_scientific_gates(_PHASE_FOUR_GATES_PATH)
    payload = gates.model_dump(mode="json")
    payload["unresolved_group"]["maximum_median_position_beams"] = 0.3

    with pytest.raises(ValidationError, match="unresolved-group margin"):
        PhaseFourScientificGates.model_validate(payload)


@pytest.mark.parametrize(
    ("mutation", "message"),
    _INVALID_MEASUREMENT_MUTATIONS,
)
def test_phase_four_measurement_rejects_ambiguous_governance(
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    """Failure cases and scientific sources are unique and immutable."""
    contract = load_phase_four_measurement_contract(
        _PHASE_FOUR_MEASUREMENT_PATH
    )
    payload = contract.model_dump(mode="json")
    mutation(payload)

    with pytest.raises(ValidationError, match=message):
        type(contract).model_validate(payload)


def test_phase_four_uncertainty_gate_requires_increasing_dispersion() -> None:
    """A calibration interval cannot have reversed or equal bounds."""
    gates = load_phase_four_scientific_gates(_PHASE_FOUR_GATES_PATH)
    payload = gates.model_dump(mode="json")
    payload["uncertainty"][
        "minimum_normalized_residual_standard_deviation"
    ] = payload["uncertainty"][
        "maximum_normalized_residual_standard_deviation"
    ]

    with pytest.raises(ValidationError, match="bounds must be increasing"):
        PhaseFourScientificGates.model_validate(payload)
