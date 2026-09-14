"""Prospective power planning after the closed Phase 5 campaign.

The closed campaign remains immutable.  This module uses its paired planning
summaries only as independent prior information for a new population.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import NormalDist
from typing import cast

_CONFIDENCE_LEVEL = 0.95
_MAXIMUM_REALIZATION_COUNT = 1_000_000


@dataclass(frozen=True, slots=True)
class PairedPowerPrior:
    """One endpoint/reference planning input for a fresh campaign."""

    endpoint_id: str
    reference_id: str
    metric_family: str
    practical_regression_margin: float
    planning_expected_regression: float
    planning_paired_standard_deviation: float
    closed_positive_regression: float
    closed_paired_standard_deviation: float


@dataclass(frozen=True, slots=True)
class _FamilyPolicy:
    """Validated legacy floor and unchanged scientific margin."""

    standard_deviation: float
    margin: float


@dataclass(frozen=True, slots=True)
class _PlanningControls:
    """Prospective safeguards applied to independent closed evidence."""

    variance_inflation: float
    advantage_retention: float


def _as_mapping(value: object, *, label: str) -> Mapping[str, object]:
    """Return one mapping or fail with its evidence label."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _as_sequence(value: object, *, label: str) -> Sequence[object]:
    """Return one non-string sequence or fail with its evidence label."""
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError(f"{label} must be an array")
    return cast(Sequence[object], value)


def _finite_float(value: object, *, label: str) -> float:
    """Return one finite numeric planning value."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be numeric")
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{label} must be finite")
    return converted


def _planning_controls(
    variance_inflation: float,
    advantage_retention: float,
) -> _PlanningControls:
    """Validate prospective safeguards applied to the closed evidence."""
    if not isfinite(variance_inflation) or variance_inflation <= 1.0:
        raise ValueError(
            "variance inflation must be finite and greater than one"
        )
    if (
        not isfinite(advantage_retention)
        or advantage_retention < 0.0
        or advantage_retention > 1.0
    ):
        raise ValueError("advantage retention must lie in [0, 1]")
    return _PlanningControls(
        variance_inflation=variance_inflation,
        advantage_retention=advantage_retention,
    )


def _family_policies(
    assumptions: Sequence[Mapping[str, object]],
) -> dict[str, _FamilyPolicy]:
    """Index validated legacy planning floors by metric family."""
    policies: dict[str, _FamilyPolicy] = {}
    for untyped in assumptions:
        assumption = _as_mapping(untyped, label="family assumption")
        metric_family = assumption.get("metric_family")
        if not isinstance(metric_family, str) or not metric_family:
            raise ValueError("family assumption must name a metric family")
        if metric_family in policies:
            raise ValueError("family assumptions contain a duplicate metric")
        standard_deviation = _finite_float(
            assumption.get("planning_paired_standard_deviation"),
            label="family planning standard deviation",
        )
        margin = _finite_float(
            assumption.get("practical_regression_margin"),
            label="family practical margin",
        )
        if standard_deviation <= 0.0 or margin <= 0.0:
            raise ValueError("family deviation and margin must be positive")
        policies[metric_family] = _FamilyPolicy(
            standard_deviation=standard_deviation,
            margin=margin,
        )
    return policies


def _paired_prior(
    endpoint_id: str,
    metric_family: str,
    comparison: Mapping[str, object],
    policy: _FamilyPolicy,
    controls: _PlanningControls,
) -> PairedPowerPrior:
    """Translate one successful closed comparison into a guarded prior."""
    reference_id = comparison.get("reference_id")
    if not isinstance(reference_id, str) or not reference_id:
        raise ValueError("closed comparison must name a reference")
    if comparison.get("status") != "success":
        raise ValueError(
            "closed paired comparison is unavailable: "
            f"{endpoint_id}/{reference_id}"
        )
    observed_deviation = _finite_float(
        comparison.get("observed_paired_standard_deviation"),
        label="closed paired standard deviation",
    )
    observed_regression = _finite_float(
        comparison.get("positive_regression"),
        label="closed positive regression",
    )
    if observed_deviation < 0.0:
        raise ValueError(
            "closed paired standard deviation must be non-negative"
        )
    return PairedPowerPrior(
        endpoint_id=endpoint_id,
        reference_id=reference_id,
        metric_family=metric_family,
        practical_regression_margin=policy.margin,
        planning_expected_regression=min(
            0.0,
            controls.advantage_retention * observed_regression,
        ),
        planning_paired_standard_deviation=max(
            policy.standard_deviation,
            controls.variance_inflation * observed_deviation,
        ),
        closed_positive_regression=observed_regression,
        closed_paired_standard_deviation=observed_deviation,
    )


def build_paired_power_priors(
    closed_analysis: Mapping[str, object],
    prior_family_assumptions: Sequence[Mapping[str, object]],
    *,
    variance_inflation: float,
    advantage_retention: float,
) -> tuple[PairedPowerPrior, ...]:
    """Build guarded endpoint priors from one independent closed campaign.

    The old family-level standard deviation remains a floor.  Each observed
    endpoint/reference deviation is inflated prospectively, and only the
    declared fraction of a favourable closed difference is retained.  An
    unfavourable closed difference is planned as equality rather than assumed
    to reverse in the new candidate.
    """
    controls = _planning_controls(
        variance_inflation,
        advantage_retention,
    )
    family_policies = _family_policies(prior_family_assumptions)
    endpoints = _as_sequence(
        closed_analysis.get("continuum_endpoints"),
        label="closed continuum endpoints",
    )
    priors: list[PairedPowerPrior] = []
    identities: set[tuple[str, str]] = set()
    for untyped_endpoint in endpoints:
        endpoint = _as_mapping(
            untyped_endpoint,
            label="closed continuum endpoint",
        )
        endpoint_id = endpoint.get("endpoint_id")
        metric_family = endpoint.get("metric_family")
        if not isinstance(endpoint_id, str) or not endpoint_id:
            raise ValueError("closed endpoint must have an identifier")
        if not isinstance(metric_family, str) or not metric_family:
            raise ValueError("closed endpoint must have a metric family")
        comparisons = _as_sequence(
            endpoint.get("comparisons"),
            label="closed paired comparisons",
        )
        if not comparisons:
            continue
        if metric_family not in family_policies:
            raise ValueError(
                f"closed paired metric lacks a family policy: {metric_family}"
            )
        policy = family_policies[metric_family]
        for untyped_comparison in comparisons:
            comparison = _as_mapping(
                untyped_comparison,
                label="closed paired comparison",
            )
            prior = _paired_prior(
                endpoint_id,
                metric_family,
                comparison,
                policy,
                controls,
            )
            reference_id = prior.reference_id
            identity = (endpoint_id, reference_id)
            if identity in identities:
                raise ValueError("closed paired comparison is duplicated")
            identities.add(identity)
            priors.append(prior)
    if not priors:
        raise ValueError("closed analysis contains no paired comparisons")
    return tuple(priors)


def conservative_familywise_power(
    priors: Sequence[PairedPowerPrior],
    realization_count: int,
) -> float:
    """Return the conservative union lower bound for paired comparisons."""
    if isinstance(realization_count, bool) or realization_count < 1:
        raise ValueError("realization count must be a positive integer")
    if not priors:
        raise ValueError("paired power planning requires at least one prior")
    critical = NormalDist().inv_cdf(_CONFIDENCE_LEVEL)
    total_failure = 0.0
    for prior in priors:
        standard_error = prior.planning_paired_standard_deviation / sqrt(
            realization_count
        )
        threshold = prior.practical_regression_margin - (
            critical * standard_error
        )
        power = NormalDist().cdf(
            (threshold - prior.planning_expected_regression) / standard_error
        )
        total_failure += 1.0 - power
    return max(0.0, 1.0 - total_failure)


def prospective_joint_power(
    continuum_familywise_power: float,
    compact_familywise_power: float,
) -> float:
    """Combine continuum and compact lower bounds conservatively."""
    if any(
        not isfinite(value) or value < 0.0 or value > 1.0
        for value in (continuum_familywise_power, compact_familywise_power)
    ):
        raise ValueError("familywise powers must lie in [0, 1]")
    return max(
        0.0,
        1.0
        - (1.0 - continuum_familywise_power)
        - (1.0 - compact_familywise_power),
    )


def minimum_realization_count(
    priors: Sequence[PairedPowerPrior],
    *,
    compact_familywise_power: float,
    minimum_joint_power: float,
) -> int:
    """Return the first continuum count meeting the joint power target."""
    if (
        not isfinite(minimum_joint_power)
        or minimum_joint_power <= 0.0
        or minimum_joint_power > 1.0
    ):
        raise ValueError("minimum joint power must lie in (0, 1]")
    prospective_joint_power(1.0, compact_familywise_power)
    if compact_familywise_power < minimum_joint_power:
        raise ValueError("compact power cannot support the joint target")
    for count in range(1, _MAXIMUM_REALIZATION_COUNT + 1):
        continuum = conservative_familywise_power(priors, count)
        if (
            prospective_joint_power(continuum, compact_familywise_power)
            >= minimum_joint_power
        ):
            return count
    raise ValueError("joint power target exceeds the planning search bound")
