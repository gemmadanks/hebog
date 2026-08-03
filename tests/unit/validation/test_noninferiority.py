"""Tests for the Phase 4 paired non-inferiority design."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hebog.validation.contracts import (
    PairedNoninferiorityContract,
    load_paired_noninferiority_contract,
)
from hebog.validation.noninferiority import (
    calculate_design_power,
    require_adequate_design_power,
)

_ROOT = Path(__file__).parents[3]
_CONTRACT_PATH = _ROOT / "config/contracts/phase-4-paired-noninferiority.json"


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

    assert contract.status == "draft-provisional"
    assert contract.realization_count == 600
    assert contract.resampling.resampling_unit == "noise-seed-image"
    assert contract.resampling.degenerate_interval == "indeterminate-fail"
    assert contract.decision.combination_rule == (
        "intersection-union-all-coprimary"
    )
    assert contract.decision.require_no_worse_point_estimate is True
    assert contract.decision.require_every_absolute_gate is True
    assert contract.reference_failures.primary == "qualification-fails"
    assert contract.reference_failures.secondary == "record-and-continue"

    estimates = require_adequate_design_power(contract)

    assert len(estimates) == len(contract.binary_endpoints) + len(
        contract.continuous_endpoints
    )
    assert min(item.interval_exclusion_power for item in estimates) >= 0.9


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
    ("endpoint_index", "ideal_value", "expected_message"),
    (
        (4, None, "requires an ideal value"),
        (0, 0.0, "cannot define an ideal value"),
    ),
)
def test_protocol_binds_ideal_values_to_distance_endpoints(
    endpoint_index: int,
    ideal_value: float | None,
    expected_message: str,
) -> None:
    """Only ideal-directed metrics may carry a scientific target value."""
    contract = load_paired_noninferiority_contract(_CONTRACT_PATH)
    payload = contract.model_dump(mode="json")
    payload["continuous_endpoints"][endpoint_index]["ideal_value"] = (
        ideal_value
    )

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
