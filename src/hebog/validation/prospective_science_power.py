"""Endpoint-complete design audit for the Phase 5 prospective contract.

The audit uses only assumptions frozen before the full candidate replay. It
does not infer future variance from a viewed confidence interval. Compact
cross-finder power reuses the reviewed Phase 4U/Phase 5 simultaneous lower
bound, while exact current/incumbent compact product equality is a structural
condition established in the smoke lane and rechecked over the full replay.
Continuum comparisons use the frozen family planning variances at the complete
1,600-realization replay size.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite, sqrt
from statistics import NormalDist
from typing import cast

from hebog.validation.prospective_science_contract import (
    ProspectiveEndpointRegistry,
)

_CONFIDENCE_LEVEL = 0.95
_MINIMUM_ENDPOINT_POWER = 0.90
_MINIMUM_JOINT_POWER = 0.90
_MINIMUM_REALIZATION_COUNT = 2
_FULL_COMPACT_COUNT = 800
_FULL_CONTINUUM_COUNT = 1600


@dataclass(frozen=True, slots=True)
class ProspectiveEndpointPower:
    """Prospective power evidence for one endpoint/comparator hypothesis."""

    endpoint_id: str
    comparator_id: str
    lane: str
    realization_count: int
    planning_expected_regression: float | None
    planning_paired_standard_deviation: float | None
    practical_regression_margin: float
    marginal_interval_exclusion_power_lower_bound: float
    adequately_powered: bool
    planning_source: str


def _normal_power(
    *,
    count: int,
    expected_regression: float,
    standard_deviation: float,
    margin: float,
) -> float:
    """Return one-sided upper-limit exclusion power at the frozen level."""
    values = (expected_regression, standard_deviation, margin)
    if count < _MINIMUM_REALIZATION_COUNT or not all(
        isfinite(value) for value in values
    ):
        raise ValueError("prospective power assumptions are invalid")
    if standard_deviation <= 0.0 or margin <= 0.0:
        raise ValueError("prospective power scales must be positive")
    standard_error = standard_deviation / sqrt(count)
    critical = NormalDist().inv_cdf(_CONFIDENCE_LEVEL)
    threshold = margin - critical * standard_error
    return NormalDist().cdf((threshold - expected_regression) / standard_error)


def _as_record(value: object, *, label: str) -> dict[str, object]:
    """Narrow one decoded JSON object or fail with a useful label."""
    if not isinstance(value, dict):
        raise ValueError(f"{label} is malformed")
    return cast(dict[str, object], value)


def _as_finite(value: object, *, label: str) -> float:
    """Return one finite non-boolean planning value."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
    ):
        raise ValueError(f"{label} is invalid")
    return float(value)


def _continuum_assumptions(
    protocol: dict[str, object],
) -> dict[str, tuple[float, float, float]]:
    """Index the exact frozen family planning assumptions."""
    audit = _as_record(protocol.get("power_audit"), label="power audit")
    raw = audit.get("continuum_assumptions")
    if not isinstance(raw, list):
        raise ValueError("Continuum power assumptions are absent")
    output: dict[str, tuple[float, float, float]] = {}
    for value in cast(list[object], raw):
        row = _as_record(value, label="Continuum power assumption")
        family = row.get("metric_family")
        if not isinstance(family, str) or family in output:
            raise ValueError("Continuum power family is invalid")
        output[family] = (
            _as_finite(
                row.get("planning_expected_regression"),
                label="planning expected regression",
            ),
            _as_finite(
                row.get("planning_paired_standard_deviation"),
                label="planning paired standard deviation",
            ),
            _as_finite(
                row.get("practical_regression_margin"),
                label="planning practical margin",
            ),
        )
    return output


def _power_row(  # noqa: PLR0913
    *,
    endpoint_id: str,
    comparator_id: str,
    lane: str,
    count: int,
    expected: float | None,
    deviation: float | None,
    margin: float,
    power: float,
    source: str,
) -> ProspectiveEndpointPower:
    """Build one validated endpoint audit row."""
    if not isfinite(power) or not 0.0 <= power <= 1.0:
        raise ValueError("prospective endpoint power is invalid")
    return ProspectiveEndpointPower(
        endpoint_id=endpoint_id,
        comparator_id=comparator_id,
        lane=lane,
        realization_count=count,
        planning_expected_regression=expected,
        planning_paired_standard_deviation=deviation,
        practical_regression_margin=margin,
        marginal_interval_exclusion_power_lower_bound=power,
        adequately_powered=power >= _MINIMUM_ENDPOINT_POWER,
        planning_source=source,
    )


def _compact_rows(
    registry: ProspectiveEndpointRegistry,
    *,
    cross_finder_power: float,
) -> list[ProspectiveEndpointPower]:
    """Reuse reviewed compact power and structural incumbent equality."""
    output: list[ProspectiveEndpointPower] = []
    for endpoint in registry.endpoints:
        if endpoint.lane != "compact" or endpoint.role != "binding":
            continue
        for comparator in endpoint.comparators:
            margin = endpoint.practical_regression_margins[comparator]
            if comparator == "incumbent-hebog":
                power = 1.0
                source = (
                    "smoke-proven-compact-product-identity-full-replay-"
                    "recheck-required"
                )
            else:
                power = 1.0 if margin == 0.0 else cross_finder_power
                source = (
                    "reviewed-phase-4u-phase-5-single-reference-"
                    "familywise-lower-bound"
                )
            output.append(
                _power_row(
                    endpoint_id=endpoint.endpoint_id,
                    comparator_id=comparator,
                    lane=endpoint.lane,
                    count=_FULL_COMPACT_COUNT,
                    expected=None,
                    deviation=None,
                    margin=margin,
                    power=power,
                    source=source,
                )
            )
    return output


def _continuum_rows(
    registry: ProspectiveEndpointRegistry,
    assumptions: dict[str, tuple[float, float, float]],
) -> list[ProspectiveEndpointPower]:
    """Calculate every full-replay Continuum endpoint/comparator power."""
    output: list[ProspectiveEndpointPower] = []
    for endpoint in registry.endpoints:
        if endpoint.lane != "continuum" or endpoint.role != "binding":
            continue
        family = endpoint.metric_family
        if family in {"absolute-mean-offset-x", "absolute-mean-offset-y"}:
            expected, deviation, frozen_margin = (0.0, 0.15, 0.05)
            source = "frozen-phase-4u-axis-mean-planning-assumption"
        else:
            try:
                expected, deviation, frozen_margin = assumptions[family]
            except KeyError as error:
                raise ValueError(
                    f"Continuum family lacks a frozen power prior: {family}"
                ) from error
            source = "frozen-phase-5-continuum-family-planning-assumption"
        for comparator in endpoint.comparators:
            margin = endpoint.practical_regression_margins[comparator]
            if margin != frozen_margin:
                raise ValueError(
                    "prospective Continuum margin differs from power design: "
                    f"{endpoint.endpoint_id}:{comparator}"
                )
            comparator_expected = (
                0.0 if comparator == "incumbent-hebog" else expected
            )
            power = _normal_power(
                count=_FULL_CONTINUUM_COUNT,
                expected_regression=comparator_expected,
                standard_deviation=deviation,
                margin=margin,
            )
            output.append(
                _power_row(
                    endpoint_id=endpoint.endpoint_id,
                    comparator_id=comparator,
                    lane=endpoint.lane,
                    count=_FULL_CONTINUUM_COUNT,
                    expected=comparator_expected,
                    deviation=deviation,
                    margin=margin,
                    power=power,
                    source=(
                        source
                        if comparator != "incumbent-hebog"
                        else f"{source}-at-incumbent-equality"
                    ),
                )
            )
    return output


def _union_lower_bound(rows: list[ProspectiveEndpointPower]) -> float:
    """Return a conservative simultaneous-pass lower bound."""
    return max(
        0.0,
        1.0
        - sum(
            1.0 - row.marginal_interval_exclusion_power_lower_bound
            for row in rows
        ),
    )


def build_prospective_power_audit(
    *,
    registry: ProspectiveEndpointRegistry,
    external_protocol: dict[str, object],
    smoke_record: dict[str, object],
) -> dict[str, object]:
    """Return an endpoint-complete pre-full-replay power audit."""
    if (
        smoke_record.get("status") != "pass"
        or smoke_record.get("promotion_evidence") is not False
        or smoke_record.get("compact_product_identity_equal") is not True
    ):
        raise ValueError("prospective power requires the passing smoke record")
    audit = _as_record(
        external_protocol.get("power_audit"), label="external power audit"
    )
    if audit.get("compact_realization_count") != _FULL_COMPACT_COUNT:
        raise ValueError("prospective compact realization count changed")
    cross_finder_power = _as_finite(
        audit.get("compact_single_reference_familywise_power_lower_bound"),
        label="compact single-reference familywise power",
    )
    assumptions = _continuum_assumptions(external_protocol)
    compact = _compact_rows(registry, cross_finder_power=cross_finder_power)
    continuum = _continuum_rows(registry, assumptions)
    rows = sorted(
        (*compact, *continuum),
        key=lambda item: (item.endpoint_id, item.comparator_id),
    )
    expected = registry.counts.total_coprimary_comparisons
    identities = {(item.endpoint_id, item.comparator_id) for item in rows}
    if len(rows) != expected or len(identities) != expected:
        raise ValueError("prospective power endpoint coverage differs")
    underpowered = tuple(
        f"{item.endpoint_id}:{item.comparator_id}"
        for item in rows
        if not item.adequately_powered
    )
    continuum_cross = [
        item for item in continuum if item.comparator_id != "incumbent-hebog"
    ]
    continuum_incumbent = [
        item for item in continuum if item.comparator_id == "incumbent-hebog"
    ]
    compact_cross_bound = _as_finite(
        audit.get("compact_familywise_power_lower_bound"),
        label="compact cross-finder familywise power",
    )
    continuum_cross_bound = _union_lower_bound(continuum_cross)
    continuum_incumbent_bound = _union_lower_bound(continuum_incumbent)
    joint_bound = max(
        0.0,
        1.0
        - (1.0 - compact_cross_bound)
        - (1.0 - continuum_cross_bound)
        - (1.0 - continuum_incumbent_bound),
    )
    passed = not underpowered and joint_bound >= _MINIMUM_JOINT_POWER
    return {
        "schema_version": 1,
        "audit_id": "phase-5-prospective-endpoint-power",
        "status": "pass" if passed else "fail",
        "candidate_full_replay_results_inspected": False,
        "smoke_result_role": "mechanism-and-compact-identity-condition-only",
        "minimum_endpoint_power": _MINIMUM_ENDPOINT_POWER,
        "minimum_joint_power": _MINIMUM_JOINT_POWER,
        "comparison_count": len(rows),
        "adequately_powered_comparison_count": len(rows) - len(underpowered),
        "underpowered_comparisons": list(underpowered),
        "all_endpoint_marginal_power_passed": not underpowered,
        "compact_cross_finder_familywise_power_lower_bound": (
            compact_cross_bound
        ),
        "continuum_cross_finder_familywise_power_lower_bound": (
            continuum_cross_bound
        ),
        "continuum_incumbent_familywise_power_lower_bound": (
            continuum_incumbent_bound
        ),
        "combined_familywise_power_lower_bound": joint_bound,
        "global_power_interpretation": (
            "conservative union lower bound across compact cross-finder, "
            "Continuum cross-finder, and Continuum incumbent families"
        ),
        "comparisons": [asdict(item) for item in rows],
    }
