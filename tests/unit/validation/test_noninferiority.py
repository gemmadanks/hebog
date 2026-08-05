"""Tests for the Phase 4 paired non-inferiority design."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from pydantic import ValidationError

from hebog.validation.contracts import (
    PairedContinuousEndpoint,
    PairedNoninferiorityContract,
    load_paired_noninferiority_contract,
)
from hebog.validation.datasets import load_dataset_manifest
from hebog.validation.noninferiority import (
    audit_design_population,
    audit_planning_standard_deviation,
    calculate_absolute_gate_design_power,
    calculate_absolute_mean_equivalence_power,
    calculate_design_power,
    familywise_power_lower_bound,
    planned_paired_standard_deviation,
    require_adequate_design_power,
)

_ROOT = Path(__file__).parents[3]
_CONTRACT_PATH = _ROOT / "config/contracts/phase-4-paired-noninferiority.json"
_PHASE4S_CONTRACT_PATH = (
    _ROOT / "config/contracts/phase-4s-paired-noninferiority.json"
)
_REPLACEMENT_PATH = (
    _ROOT / "config/datasets/phase-4r-qualification-replacement.json"
)
_PHASE4S_PATH = _ROOT / "config/datasets/phase-4s-qualification.json"
_PHASE4T_CONTRACT_PATH = (
    _ROOT / "config/contracts/phase-4t-paired-noninferiority.json"
)
_PHASE4T_PATH = _ROOT / "config/datasets/phase-4t-qualification.json"
_PHASE4U_CONTRACT_PATH = (
    _ROOT / "config/contracts/phase-4u-paired-noninferiority.json"
)
_PHASE4U_PATH = _ROOT / "config/datasets/phase-4u-qualification.json"

_POPULATION_UNITS = {
    "compact-completeness": "association-truth-groups",
    "catalogue-reliability": "association-truth-groups",
    "association-pair-precision": "association-truth-groups",
    "association-pair-recall": "association-truth-groups",
    "fitted-shape-availability": "individually-resolvable-sources",
    "deconvolution-classification-availability": (
        "individually-resolvable-sources"
    ),
    "resolved-deconvolved-shape-availability": "clear-resolved-sources",
    "association-identity-availability": "individually-resolvable-sources",
    "position-flux-uncertainty-availability": (
        "individually-resolvable-sources"
    ),
    "point-source-specificity": "point-sources",
    "clear-resolved-classification-recall": "clear-resolved-sources",
    "catastrophic-outlier-fraction": "individually-resolvable-sources",
    "unresolved-group-completeness": "unresolved-association-groups",
}


def _contract_with_population_units() -> PairedNoninferiorityContract:
    """Return the historical protocol with explicit population meanings."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    for endpoint in payload["binary_endpoints"]:
        endpoint["population_unit"] = _POPULATION_UNITS[
            endpoint["endpoint_id"]
        ]
    return PairedNoninferiorityContract.model_validate(payload)


def _change_confidence_level(payload: dict[str, Any]) -> None:
    """Replace the predeclared one-sided confidence level."""
    payload["resampling"]["confidence_level"] = 0.9


def _duplicate_report_only_metric(payload: dict[str, Any]) -> None:
    """Give one report-only metric two entries."""
    metrics = payload["report_only_metrics"]
    metrics.append(metrics[0])


def _duplicate_scientific_basis(payload: dict[str, Any]) -> None:
    """Give one statistical reference two entries."""
    links = payload["scientific_basis"]
    links.append(links[0])


def _use_insecure_scientific_basis(payload: dict[str, Any]) -> None:
    """Replace one statistical reference with an insecure URL."""
    payload["scientific_basis"][0] = "http://example.invalid"


_INVALID_PROTOCOL_MUTATIONS: tuple[
    tuple[Callable[[dict[str, Any]], None], str], ...
] = (
    (_change_confidence_level, "confidence level"),
    (_duplicate_report_only_metric, "report-only metric identifiers"),
    (_duplicate_scientific_basis, "scientific basis links must be unique"),
    (_use_insecure_scientific_basis, "must use HTTPS"),
)


def test_checked_in_protocol_is_powered_and_fail_closed() -> None:
    """The final campaign design can test every declared paired endpoint."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)

    assert contract.status == "reviewed"
    assert contract.realization_count == 600
    assert contract.resampling.resampling_unit == "noise-seed-image"
    assert contract.resampling.degenerate_interval == (
        "finite-point-mass-exact-otherwise-indeterminate-fail"
    )
    assert contract.decision.combination_rule == (
        "intersection-union-all-coprimary"
    )
    assert contract.decision.require_no_worse_point_estimate is False
    assert contract.decision.require_every_absolute_gate is True
    assert contract.reference_failures.primary == "qualification-fails"
    assert contract.reference_failures.secondary == "record-and-continue"

    estimates = require_adequate_design_power(contract)

    assert len(estimates) == len(contract.binary_endpoints) + len(
        contract.continuous_endpoints
    )
    assert min(item.interval_exclusion_power for item in estimates) >= 0.9


def test_departure_endpoints_do_not_apply_the_scientific_ideal_twice() -> None:
    """An absolute departure is lower-is-better with a zero implicit ideal."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    endpoints = {
        endpoint.endpoint_id: endpoint
        for endpoint in contract.continuous_endpoints
    }

    for endpoint_id in (
        "uncertainty-normalized-bias",
        "uncertainty-one-sigma-coverage",
        "uncertainty-normalized-dispersion",
    ):
        endpoint = endpoints[endpoint_id]
        assert endpoint.desirable_direction == "lower-is-better"
        assert endpoint.ideal_value is None


def test_power_uses_effective_clustered_sample_size() -> None:
    """Within-image correlation reduces binary endpoint information."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    endpoint = next(
        item
        for item in contract.binary_endpoints
        if item.endpoint_id == "point-source-specificity"
    )

    estimate = next(
        item
        for item in calculate_design_power(contract)
        if item.endpoint_id == endpoint.endpoint_id
    )
    expected = (
        contract.realization_count
        * endpoint.observations_per_realization
        / (
            1
            + (endpoint.observations_per_realization - 1)
            * endpoint.planning_intracluster_correlation
        )
    )

    assert estimate.effective_sample_size == pytest.approx(expected)
    assert estimate.interval_exclusion_power == pytest.approx(
        0.945,
        abs=0.002,
    )
    assert estimate.no_worse_point_probability == pytest.approx(0.5)
    assert estimate.combined_decision_probability == pytest.approx(
        estimate.interval_exclusion_power
    )


def test_absolute_mean_power_accounts_for_image_clustering() -> None:
    """Eight point sources per image power the retained uncertainty gate."""
    powered = calculate_absolute_mean_equivalence_power(
        realization_count=800,
        observations_per_realization=8,
        planning_intracluster_correlation=0.02,
        anticipated_mean=0.1062,
        planning_standard_deviation=1.0,
        equivalence_margin=0.15,
        confidence_level=0.95,
    )
    underpowered = calculate_absolute_mean_equivalence_power(
        realization_count=800,
        observations_per_realization=4,
        planning_intracluster_correlation=0.02,
        anticipated_mean=0.1062,
        planning_standard_deviation=1.0,
        equivalence_margin=0.15,
        confidence_level=0.95,
    )

    assert powered.effective_sample_size == pytest.approx(6400 / 1.14)
    assert powered.interval_containment_power > 0.9
    assert underpowered.interval_containment_power < 0.9


@pytest.mark.parametrize(
    ("update", "message"),
    (
        ({"realization_count": 0}, "sample counts"),
        ({"planning_intracluster_correlation": 1.0}, "correlation"),
        ({"planning_standard_deviation": 0.0}, "scales"),
        ({"confidence_level": 1.0}, "confidence level"),
    ),
)
def test_absolute_mean_power_rejects_invalid_designs(
    update: dict[str, float | int],
    message: str,
) -> None:
    """A malformed absolute design cannot produce plausible power."""
    arguments: dict[str, float | int] = {
        "realization_count": 800,
        "observations_per_realization": 8,
        "planning_intracluster_correlation": 0.02,
        "anticipated_mean": 0.1062,
        "planning_standard_deviation": 1.0,
        "equivalence_margin": 0.15,
        "confidence_level": 0.95,
    }
    arguments.update(update)

    with pytest.raises(ValueError, match=message):
        calculate_absolute_mean_equivalence_power(**arguments)  # type: ignore[arg-type]


def test_population_audit_uses_frozen_manifest_counts() -> None:
    """Power cannot assume more groups than the qualification contains."""
    contract = _contract_with_population_units()
    dataset = load_dataset_manifest(_REPLACEMENT_PATH).datasets[0]

    audits = {
        item.endpoint_id: item
        for item in audit_design_population(contract, dataset)
    }

    assert audits["compact-completeness"].observed_count == 13
    assert audits["compact-completeness"].declared_count == 33
    assert audits["compact-completeness"].matched is False
    assert audits["point-source-specificity"].observed_count == 4
    assert audits["point-source-specificity"].declared_count == 8
    assert audits["point-source-specificity"].matched is False


def test_manifest_matched_point_population_exposes_underpowered_design() -> (
    None
):
    """Corrected group counts reveal the replacement design's power gap."""
    contract = _contract_with_population_units()
    dataset = load_dataset_manifest(_REPLACEMENT_PATH).datasets[0]
    payload = contract.model_dump(mode="json")
    observed = {
        item.endpoint_id: item.observed_count
        for item in audit_design_population(contract, dataset)
    }
    for endpoint in payload["binary_endpoints"]:
        endpoint["observations_per_realization"] = observed[
            endpoint["endpoint_id"]
        ]
    corrected = PairedNoninferiorityContract.model_validate(payload)

    point_power = next(
        item
        for item in calculate_design_power(corrected)
        if item.endpoint_id == "point-source-specificity"
    )

    assert point_power.interval_exclusion_power == pytest.approx(
        0.7686,
        abs=0.002,
    )
    with pytest.raises(ValueError, match="point-source-specificity"):
        require_adequate_design_power(corrected, dataset=dataset)


def test_familywise_power_uses_a_conservative_union_bound() -> None:
    """Marginal endpoint power is not mislabeled as joint campaign power."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    estimates = calculate_design_power(contract)[:3]

    joint = familywise_power_lower_bound(estimates)

    assert joint == pytest.approx(
        max(
            0.0,
            1.0
            - sum(1.0 - item.interval_exclusion_power for item in estimates),
        )
    )
    assert joint < min(item.interval_exclusion_power for item in estimates)


def test_phase4s_protocol_is_manifest_and_jointly_powered() -> None:
    """The new unseen decision has adequate marginal and joint power."""
    contract = load_paired_noninferiority_contract(_PHASE4S_CONTRACT_PATH)
    dataset = load_dataset_manifest(_PHASE4S_PATH).datasets[0]

    estimates = require_adequate_design_power(contract, dataset=dataset)

    assert contract.contract_id == "phase-4s-paired-noninferiority"
    assert contract.realization_count == 800
    assert contract.minimum_familywise_interval_exclusion_power == 0.9
    assert all(
        endpoint.population_unit is not None
        for endpoint in contract.binary_endpoints
    )
    assert min(item.interval_exclusion_power for item in estimates) >= 0.9
    assert familywise_power_lower_bound(estimates) >= 0.9


def test_phase4s_power_check_enforces_the_joint_target() -> None:
    """Marginally powered endpoints cannot hide an underpowered decision."""
    contract = load_paired_noninferiority_contract(_PHASE4S_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    payload["realization_count"] = 600
    underpowered = PairedNoninferiorityContract.model_validate(payload)

    with pytest.raises(ValueError, match="familywise"):
        require_adequate_design_power(underpowered)


def test_phase4t_protocol_powers_paired_and_absolute_decisions() -> None:
    """The fresh population powers both retained decision families."""
    contract = load_paired_noninferiority_contract(_PHASE4T_CONTRACT_PATH)
    dataset = load_dataset_manifest(_PHASE4T_PATH).datasets[0]

    paired = require_adequate_design_power(contract, dataset=dataset)
    absolute = calculate_absolute_gate_design_power(contract)

    assert contract.contract_id == "phase-4t-paired-noninferiority"
    assert familywise_power_lower_bound(paired) >= 0.9
    assert len(absolute) == 1
    assert absolute[0].interval_containment_power >= 0.9


def test_phase4t_absolute_power_check_fails_closed() -> None:
    """A smaller point population cannot pass only on paired power."""
    contract = load_paired_noninferiority_contract(_PHASE4T_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    payload["absolute_mean_power_checks"][0][
        "observations_per_realization"
    ] = 4
    underpowered = PairedNoninferiorityContract.model_validate(payload)

    with pytest.raises(ValueError, match="absolute mean gates"):
        require_adequate_design_power(underpowered)


def test_phase4u_protocol_powers_varied_blend_qualification() -> None:
    """The unseen blend population retains paired and absolute power."""
    contract = load_paired_noninferiority_contract(_PHASE4U_CONTRACT_PATH)
    dataset = load_dataset_manifest(_PHASE4U_PATH).datasets[0]

    paired = require_adequate_design_power(contract, dataset=dataset)
    absolute = calculate_absolute_gate_design_power(contract)

    assert contract.contract_id == "phase-4u-paired-noninferiority"
    assert familywise_power_lower_bound(paired) >= 0.9
    assert len(absolute) == 1
    assert absolute[0].interval_containment_power >= 0.9


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("population-unit", "population units"),
        ("familywise-power", "familywise power"),
        ("expert-review", "expert review"),
        ("scope", "explicit scope"),
        ("residual-noise", "residual-noise limitation"),
    ),
)
def test_phase4s_protocol_requires_every_preopening_declaration(
    mutation: str,
    message: str,
) -> None:
    """The frozen protocol cannot omit a reviewed Phase 4S safeguard."""
    contract = load_paired_noninferiority_contract(_PHASE4S_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    if mutation == "population-unit":
        payload["binary_endpoints"][0]["population_unit"] = None
    elif mutation == "familywise-power":
        payload["minimum_familywise_interval_exclusion_power"] = None
    elif mutation == "expert-review":
        payload["expert_scientific_review"] = None
    elif mutation == "scope":
        payload["qualification_scope"] = None
    else:
        payload["controlled_residual_noise_injection"] = None

    with pytest.raises(ValidationError, match=message):
        PairedNoninferiorityContract.model_validate(payload)


def test_binary_planning_bound_is_expressed_on_the_realization_scale() -> None:
    """Discordance and ICC combine into the auditable paired-rate scale."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    endpoint = next(
        item
        for item in contract.binary_endpoints
        if item.endpoint_id == "point-source-specificity"
    )

    observed = planned_paired_standard_deviation(endpoint)
    expected = (
        (
            endpoint.planning_discordance_probability
            - endpoint.planning_expected_regression**2
        )
        * (
            1
            + (endpoint.observations_per_realization - 1)
            * endpoint.planning_intracluster_correlation
        )
        / endpoint.observations_per_realization
    ) ** 0.5

    assert observed == pytest.approx(expected)


def test_assumption_audit_fails_an_underestimated_paired_dispersion() -> None:
    """Regression evidence cannot silently exceed a planning variance."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    endpoint = contract.continuous_endpoints[0]

    audit = audit_planning_standard_deviation(
        endpoint,
        candidate_value=0.04,
        reference_value=0.05,
        bootstrap_regressions=np.asarray((-0.2, 0.0, 0.2)),
        realization_count=200,
    )

    assert audit.endpoint_id == endpoint.endpoint_id
    assert audit.positive_means_candidate_worse == pytest.approx(-0.01)
    assert audit.observed_paired_standard_deviation > (
        audit.planning_paired_standard_deviation
    )
    assert audit.planning_bound_verified is False


@pytest.mark.parametrize(
    ("endpoint_id", "candidate", "reference", "expected_regression"),
    (
        ("compact-completeness", 0.9, 0.8, -0.1),
        ("catastrophic-outlier-fraction", 0.01, 0.02, -0.01),
    ),
)
def test_assumption_audit_normalizes_binary_endpoint_direction(
    endpoint_id: str,
    candidate: float,
    reference: float,
    expected_regression: float,
) -> None:
    """Positive always means worse for higher- and lower-is-better rates."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    endpoint = next(
        item
        for item in contract.binary_endpoints
        if item.endpoint_id == endpoint_id
    )

    audit = audit_planning_standard_deviation(
        endpoint,
        candidate_value=candidate,
        reference_value=reference,
        bootstrap_regressions=np.zeros(3),
        realization_count=200,
    )

    assert audit.positive_means_candidate_worse == pytest.approx(
        expected_regression
    )
    assert audit.planning_bound_verified is True


def test_assumption_audit_supports_a_raw_ideal_endpoint() -> None:
    """A future raw metric compares absolute distance from its ideal."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    payload = contract.continuous_endpoints[0].model_dump(mode="json")
    payload["desirable_direction"] = "closer-to-ideal-is-better"
    payload["ideal_value"] = 0.5
    endpoint = PairedContinuousEndpoint.model_validate(payload)

    audit = audit_planning_standard_deviation(
        endpoint,
        candidate_value=0.4,
        reference_value=0.3,
        bootstrap_regressions=np.zeros(3),
        realization_count=200,
    )

    assert audit.positive_means_candidate_worse == pytest.approx(-0.1)


@pytest.mark.parametrize(
    ("realization_count", "regressions", "message"),
    (
        (1, np.zeros(2), "at least two realizations"),
        (2, np.zeros(1), "at least two resamples"),
        (2, np.zeros((2, 1)), "at least two resamples"),
        (2, np.asarray((0.0, np.nan)), "must be finite"),
    ),
)
def test_assumption_audit_rejects_invalid_empirical_samples(
    realization_count: int,
    regressions: npt.NDArray[np.float64],
    message: str,
) -> None:
    """A malformed or undersized bootstrap cannot verify a planning bound."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)

    with pytest.raises(ValueError, match=message):
        audit_planning_standard_deviation(
            contract.continuous_endpoints[0],
            candidate_value=0.0,
            reference_value=0.0,
            bootstrap_regressions=regressions,
            realization_count=realization_count,
        )


def test_power_check_names_an_underpowered_endpoint() -> None:
    """A plausible-looking but underpowered design cannot be frozen."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    payload["realization_count"] = 200
    underpowered = PairedNoninferiorityContract.model_validate(payload)

    with pytest.raises(ValueError, match="point-source-specificity"):
        require_adequate_design_power(underpowered)


def test_protocol_rejects_duplicate_endpoint_ownership() -> None:
    """One metric cannot silently receive two different margins."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    payload["continuous_endpoints"][0]["endpoint_id"] = payload[
        "binary_endpoints"
    ][0]["endpoint_id"]

    with pytest.raises(ValidationError, match="endpoint identifiers"):
        PairedNoninferiorityContract.model_validate(payload)


def test_protocol_rejects_an_unattainable_planning_alternative() -> None:
    """The assumed regression must remain inside its practical margin."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    endpoint = payload["binary_endpoints"][0]
    endpoint["planning_expected_regression"] = endpoint[
        "practical_regression_margin"
    ]

    with pytest.raises(ValidationError, match="planning regression"):
        PairedNoninferiorityContract.model_validate(payload)


def test_protocol_rejects_nonpositive_paired_binary_variance() -> None:
    """Discordance must contain more information than the assumed effect."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    endpoint = payload["binary_endpoints"][0]
    endpoint["planning_expected_regression"] = 0.1
    endpoint["practical_regression_margin"] = 0.2

    with pytest.raises(ValidationError, match="positive paired variance"):
        PairedNoninferiorityContract.model_validate(payload)


@pytest.mark.parametrize(
    (
        "desirable_direction",
        "ideal_value",
        "expected_message",
    ),
    (
        ("closer-to-ideal-is-better", None, "requires an ideal value"),
        ("lower-is-better", 0.0, "cannot define an ideal value"),
    ),
)
def test_protocol_binds_ideal_values_to_distance_endpoints(
    desirable_direction: str,
    ideal_value: float | None,
    expected_message: str,
) -> None:
    """Only ideal-directed metrics may carry a scientific target value."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    endpoint = payload["continuous_endpoints"][0]
    endpoint["desirable_direction"] = desirable_direction
    endpoint["ideal_value"] = ideal_value

    with pytest.raises(ValidationError, match=expected_message):
        PairedNoninferiorityContract.model_validate(payload)


def test_protocol_rejects_unattainable_continuous_alternative() -> None:
    """Continuous planning effects must also be inside their NI margins."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    endpoint = payload["continuous_endpoints"][0]
    endpoint["planning_expected_regression"] = endpoint[
        "practical_regression_margin"
    ]

    with pytest.raises(ValidationError, match="planning regression"):
        PairedNoninferiorityContract.model_validate(payload)


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    _INVALID_PROTOCOL_MUTATIONS,
)
def test_protocol_rejects_ambiguous_analysis_governance(
    mutation: Callable[[dict[str, Any]], None],
    expected_message: str,
) -> None:
    """Confidence, metric ownership, and sources remain unambiguous."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    mutation(payload)

    with pytest.raises(ValidationError, match=expected_message):
        PairedNoninferiorityContract.model_validate(payload)


def test_combined_power_includes_the_stricter_interval_when_underpowered() -> (
    None
):
    """The reported joint probability uses the stricter active threshold."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    payload["realization_count"] = 10
    small = PairedNoninferiorityContract.model_validate(payload)

    estimate = next(
        item
        for item in calculate_design_power(small)
        if item.endpoint_id == "point-source-specificity"
    )

    assert estimate.combined_decision_probability == pytest.approx(
        estimate.interval_exclusion_power
    )
    assert (
        estimate.combined_decision_probability
        < estimate.no_worse_point_probability
    )
