"""Design-stage power calculations for paired non-inferiority campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import numpy.typing as npt

from hebog.validation.contracts import (
    PairedBinaryEndpoint,
    PairedContinuousEndpoint,
    PairedNoninferiorityContract,
)

_STANDARD_NORMAL = NormalDist()
_MINIMUM_SAMPLE_COUNT = 2


@dataclass(frozen=True, slots=True)
class PairedDesignPower:
    """Approximate power for one predeclared endpoint."""

    endpoint_id: str
    effective_sample_size: float
    standard_error: float
    interval_exclusion_power: float
    no_worse_point_probability: float
    combined_decision_probability: float


@dataclass(frozen=True, slots=True)
class PairedPlanningAssumptionAudit:
    """Empirical regression check of one paired design variance bound."""

    endpoint_id: str
    candidate_value: float
    reference_value: float
    positive_means_candidate_worse: float
    planning_paired_standard_deviation: float
    observed_paired_standard_deviation: float
    planning_bound_verified: bool


PairedEndpoint = PairedBinaryEndpoint | PairedContinuousEndpoint


def planned_paired_standard_deviation(endpoint: PairedEndpoint) -> float:
    """Return a planning bound on the per-realization paired statistic.

    Binary endpoint inputs are easier to review as discordance, cluster size,
    and within-image correlation. This conversion expresses their combined
    implication on the same scale as an empirical whole-image bootstrap.
    Continuous endpoints already declare that paired standard deviation.
    """
    if isinstance(endpoint, PairedContinuousEndpoint):
        return endpoint.planning_paired_standard_deviation
    design_effect = 1 + (endpoint.observations_per_realization - 1) * (
        endpoint.planning_intracluster_correlation
    )
    paired_variance = endpoint.planning_discordance_probability - (
        endpoint.planning_expected_regression**2
    )
    return float(
        (
            paired_variance
            * design_effect
            / endpoint.observations_per_realization
        )
        ** 0.5
    )


def _positive_regression(
    endpoint: PairedEndpoint,
    *,
    candidate_value: float,
    reference_value: float,
) -> float:
    """Normalize one endpoint so positive means candidate regression."""
    if isinstance(endpoint, PairedBinaryEndpoint):
        if endpoint.desirable_direction == "higher-is-better":
            return reference_value - candidate_value
        return candidate_value - reference_value
    if endpoint.desirable_direction == "lower-is-better":
        return candidate_value - reference_value
    assert endpoint.ideal_value is not None
    return abs(candidate_value - endpoint.ideal_value) - abs(
        reference_value - endpoint.ideal_value
    )


def audit_planning_standard_deviation(
    endpoint: PairedEndpoint,
    *,
    candidate_value: float,
    reference_value: float,
    bootstrap_regressions: npt.NDArray[np.float64],
    realization_count: int,
) -> PairedPlanningAssumptionAudit:
    """Compare a bootstrap-equivalent paired SD with its planning bound.

    The bootstrap samples whole images and recomputes the aggregate endpoint.
    Its standard error is multiplied by the square root of the independent
    realization count to recover the per-realization scale used for design
    power. This avoids inventing candidate-to-candidate identities for
    catalogue reliability and remains valid for nonlinear aggregate metrics.
    """
    if realization_count < _MINIMUM_SAMPLE_COUNT:
        raise ValueError("assumption audit requires at least two realizations")
    regressions = np.asarray(bootstrap_regressions, dtype=np.float64)
    if regressions.ndim != 1 or regressions.size < _MINIMUM_SAMPLE_COUNT:
        raise ValueError("assumption audit requires at least two resamples")
    if not np.all(np.isfinite(regressions)):
        raise ValueError("bootstrap regressions must be finite")
    observed = float(np.std(regressions, ddof=1) * realization_count**0.5)
    planned = planned_paired_standard_deviation(endpoint)
    return PairedPlanningAssumptionAudit(
        endpoint_id=endpoint.endpoint_id,
        candidate_value=candidate_value,
        reference_value=reference_value,
        positive_means_candidate_worse=_positive_regression(
            endpoint,
            candidate_value=candidate_value,
            reference_value=reference_value,
        ),
        planning_paired_standard_deviation=planned,
        observed_paired_standard_deviation=observed,
        planning_bound_verified=observed <= planned,
    )


def _decision_probabilities(
    *,
    expected_regression: float,
    practical_margin: float,
    standard_error: float,
    confidence_level: float,
) -> tuple[float, float, float]:
    """Return interval-only, directional, and combined normal power."""
    critical_value = _STANDARD_NORMAL.inv_cdf(confidence_level)
    interval_threshold = practical_margin - critical_value * standard_error
    interval_power = _STANDARD_NORMAL.cdf(
        (interval_threshold - expected_regression) / standard_error
    )
    no_worse_power = _STANDARD_NORMAL.cdf(
        -expected_regression / standard_error
    )
    combined_threshold = min(0.0, interval_threshold)
    combined_power = _STANDARD_NORMAL.cdf(
        (combined_threshold - expected_regression) / standard_error
    )
    return interval_power, no_worse_power, combined_power


def calculate_design_power(
    contract: PairedNoninferiorityContract,
) -> tuple[PairedDesignPower, ...]:
    """Calculate normal-approximation power for a reviewed campaign design.

    Binary endpoint variance uses the paired discordance probability. Its
    effective sample size applies the usual equal-cluster design effect so
    sources sharing one generated image are not treated as independent.
    Continuous inputs are precomputed realization-level paired statistics.
    These calculations plan the final sample; the final decision uses the
    predeclared paired cluster bootstrap instead of this approximation.
    """
    confidence_level = contract.resampling.confidence_level
    estimates: list[PairedDesignPower] = []
    for endpoint in contract.binary_endpoints:
        cluster_size = endpoint.observations_per_realization
        design_effect = 1 + (cluster_size - 1) * (
            endpoint.planning_intracluster_correlation
        )
        effective_sample_size = (
            contract.realization_count * cluster_size / design_effect
        )
        paired_variance = endpoint.planning_discordance_probability - (
            endpoint.planning_expected_regression**2
        )
        standard_error = (paired_variance / effective_sample_size) ** 0.5
        powers = _decision_probabilities(
            expected_regression=endpoint.planning_expected_regression,
            practical_margin=endpoint.practical_regression_margin,
            standard_error=standard_error,
            confidence_level=confidence_level,
        )
        estimates.append(
            PairedDesignPower(
                endpoint_id=endpoint.endpoint_id,
                effective_sample_size=effective_sample_size,
                standard_error=standard_error,
                interval_exclusion_power=powers[0],
                no_worse_point_probability=powers[1],
                combined_decision_probability=powers[0],
            )
        )
    for endpoint in contract.continuous_endpoints:
        effective_sample_size = float(contract.realization_count)
        standard_error = (
            endpoint.planning_paired_standard_deviation
            / effective_sample_size**0.5
        )
        powers = _decision_probabilities(
            expected_regression=endpoint.planning_expected_regression,
            practical_margin=endpoint.practical_regression_margin,
            standard_error=standard_error,
            confidence_level=confidence_level,
        )
        estimates.append(
            PairedDesignPower(
                endpoint_id=endpoint.endpoint_id,
                effective_sample_size=effective_sample_size,
                standard_error=standard_error,
                interval_exclusion_power=powers[0],
                no_worse_point_probability=powers[1],
                combined_decision_probability=powers[0],
            )
        )
    return tuple(estimates)


def require_adequate_design_power(
    contract: PairedNoninferiorityContract,
) -> tuple[PairedDesignPower, ...]:
    """Return estimates only when every endpoint reaches the power target."""
    estimates = calculate_design_power(contract)
    underpowered = [
        item.endpoint_id
        for item in estimates
        if item.interval_exclusion_power
        < contract.minimum_interval_exclusion_power
    ]
    if underpowered:
        joined = ", ".join(underpowered)
        raise ValueError(f"underpowered paired endpoints: {joined}")
    return estimates
