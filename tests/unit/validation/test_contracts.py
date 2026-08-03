"""Tests for versioned performance, behaviour, and scientific contracts."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hebog.validation.contracts import (
    PerformanceMatrixContract,
    PhaseFourScientificGates,
    ScalabilityContract,
    load_performance_matrix,
    load_phase_four_measurement_contract,
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

    assert contract.status == "frozen-provisional"
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


def test_phase_four_gates_freeze_role_specific_catalogue_margins() -> None:
    """Phase 4 has explicit provisional shape and uncertainty questions."""
    gates = load_phase_four_scientific_gates(_PHASE_FOUR_GATES_PATH)

    assert gates.status == "frozen-provisional"
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
    assert gates.extension_classification.significance_sigma == 2.0
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
