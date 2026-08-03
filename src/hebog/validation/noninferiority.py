"""Design-stage power calculations for paired non-inferiority campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

from hebog.validation.contracts import PairedNoninferiorityContract

_STANDARD_NORMAL = NormalDist()


@dataclass(frozen=True, slots=True)
class PairedDesignPower:
    """Approximate power for one predeclared endpoint."""

    endpoint_id: str
    effective_sample_size: float
    standard_error: float
    interval_exclusion_power: float
    no_worse_point_probability: float
    combined_decision_probability: float


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
                combined_decision_probability=powers[2],
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
                combined_decision_probability=powers[2],
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
