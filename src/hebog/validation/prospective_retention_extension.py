"""Prospective power planning for a stratified retention confirmation.

The current Phase 5 population contains equal, fixed counts from four image
geometries.  This module estimates uncertainty by resampling whole images
within each geometry, so the bootstrap cannot introduce a population-mixture
change that was absent from the design.  Closed evidence is used only to plan
a new seed-disjoint population; it never changes the closed decision.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import NormalDist

import numpy as np
import numpy.typing as npt

_MINIMUM_RESAMPLES = 1_000
_MINIMUM_REALIZATIONS_PER_STRATUM = 2
_DEFAULT_MAXIMUM_COUNT_PER_STRATUM = 100_000
_BOOTSTRAP_BATCH_SIZE = 64
_PERCENT_SCALE = 100.0
_MINIMUM_ONE_SIDED_CONFIDENCE = 0.5


@dataclass(frozen=True, slots=True)
class StratifiedBootstrapEstimate:
    """Closed-data planning estimate for one nonlinear paired endpoint."""

    endpoint_id: str
    percentile: float
    realization_count: int
    stratum_counts: tuple[tuple[str, int], ...]
    positive_regression: float
    bootstrap_standard_error: float
    bootstrap_upper_sensitivity: float
    resamples: int
    seed: int


@dataclass(frozen=True, slots=True)
class ConfirmationEndpointPower:
    """Guarded prospective power for one retention evidence pattern."""

    endpoint_id: str
    planning_expected_regression: float
    planning_standard_error: float
    practical_regression_margin: float
    power: float


@dataclass(frozen=True, slots=True)
class BalancedConfirmationPlan:
    """Smallest balanced fresh population satisfying the joint power gate."""

    selected_count_per_stratum: int
    selected_realization_count: int
    variance_inflation: float
    confidence_level: float
    minimum_joint_power: float
    joint_power_lower_bound: float
    endpoint_powers: tuple[ConfirmationEndpointPower, ...]


def _validated_rows(
    values: Sequence[Sequence[float]],
    *,
    label: str,
) -> tuple[npt.NDArray[np.float64], ...]:
    """Return finite non-empty realization rows for one fixed stratum."""
    if len(values) < _MINIMUM_REALIZATIONS_PER_STRATUM:
        raise ValueError(
            f"{label} requires at least two independent realizations"
        )
    rows: list[npt.NDArray[np.float64]] = []
    for value in values:
        row = np.asarray(value, dtype=np.float64)
        if row.ndim != 1 or row.size == 0 or not np.all(np.isfinite(row)):
            raise ValueError(f"{label} must contain finite non-empty values")
        rows.append(row)
    return tuple(rows)


def _padded_rows(
    rows: Sequence[npt.NDArray[np.float64]],
) -> npt.NDArray[np.float64]:
    """Pad bounded per-image observations for vectorized resampling."""
    width = max(item.size for item in rows)
    output = np.full((len(rows), width), np.nan, dtype=np.float64)
    for index, row in enumerate(rows):
        output[index, : row.size] = row
    return output


def _point_percentile(
    rows_by_stratum: Sequence[Sequence[npt.NDArray[np.float64]]],
    percentile: float,
) -> float:
    """Return the governed percentile over all fixed-stratum observations."""
    values = np.concatenate(
        [row for stratum in rows_by_stratum for row in stratum]
    )
    return float(np.percentile(values, percentile))


def _validate_bootstrap_request(  # noqa: PLR0913
    *,
    endpoint_id: str,
    candidate_by_stratum: Mapping[str, Sequence[Sequence[float]]],
    incumbent_by_stratum: Mapping[str, Sequence[Sequence[float]]],
    percentile: float,
    resamples: int,
    seed: int,
) -> tuple[str, ...]:
    """Validate top-level controls and return canonical stratum names."""
    if not endpoint_id:
        raise ValueError("endpoint identity must not be empty")
    if not candidate_by_stratum:
        raise ValueError("stratified evidence requires at least one stratum")
    if set(candidate_by_stratum) != set(incumbent_by_stratum):
        raise ValueError("candidate and incumbent stratum identities differ")
    if not isfinite(percentile) or not 0.0 < percentile < _PERCENT_SCALE:
        raise ValueError("percentile must be finite and lie in (0, 100)")
    if (
        isinstance(resamples, bool)
        or type(resamples) is not int
        or resamples < _MINIMUM_RESAMPLES
    ):
        raise ValueError(
            f"stratified planning requires at least {_MINIMUM_RESAMPLES} "
            "resamples"
        )
    if isinstance(seed, bool) or type(seed) is not int or seed < 0:
        raise ValueError("bootstrap seed must be a non-negative integer")
    return tuple(sorted(candidate_by_stratum))


def stratified_percentile_regression(  # noqa: PLR0913
    *,
    endpoint_id: str,
    candidate_by_stratum: Mapping[str, Sequence[Sequence[float]]],
    incumbent_by_stratum: Mapping[str, Sequence[Sequence[float]]],
    percentile: float,
    resamples: int,
    seed: int,
) -> StratifiedBootstrapEstimate:
    """Estimate one paired percentile regression under a fixed design mix.

    Each bootstrap draw samples complete image rows independently within each
    named geometry.  The original number of images in every geometry remains
    fixed in every draw.  The returned percentile bound is a planning
    sensitivity summary, not a replacement BCa decision for closed evidence.
    """
    strata = _validate_bootstrap_request(
        endpoint_id=endpoint_id,
        candidate_by_stratum=candidate_by_stratum,
        incumbent_by_stratum=incumbent_by_stratum,
        percentile=percentile,
        resamples=resamples,
        seed=seed,
    )
    candidate_rows: list[tuple[npt.NDArray[np.float64], ...]] = []
    incumbent_rows: list[tuple[npt.NDArray[np.float64], ...]] = []
    stratum_counts: list[tuple[str, int]] = []
    for stratum in strata:
        if len(candidate_by_stratum[stratum]) != len(
            incumbent_by_stratum[stratum]
        ):
            raise ValueError(
                "candidate and incumbent paired realization counts differ"
            )
        candidate = _validated_rows(
            candidate_by_stratum[stratum],
            label=f"candidate stratum {stratum}",
        )
        incumbent = _validated_rows(
            incumbent_by_stratum[stratum],
            label=f"incumbent stratum {stratum}",
        )
        candidate_rows.append(candidate)
        incumbent_rows.append(incumbent)
        stratum_counts.append((stratum, len(candidate)))

    candidate_point = _point_percentile(candidate_rows, percentile)
    incumbent_point = _point_percentile(incumbent_rows, percentile)
    candidate_matrices = tuple(_padded_rows(rows) for rows in candidate_rows)
    incumbent_matrices = tuple(_padded_rows(rows) for rows in incumbent_rows)
    random = np.random.default_rng(seed)
    distribution = np.empty(resamples, dtype=np.float64)
    for start in range(0, resamples, _BOOTSTRAP_BATCH_SIZE):
        stop = min(start + _BOOTSTRAP_BATCH_SIZE, resamples)
        size = stop - start
        candidate_samples: list[npt.NDArray[np.float64]] = []
        incumbent_samples: list[npt.NDArray[np.float64]] = []
        for candidate, incumbent in zip(
            candidate_matrices,
            incumbent_matrices,
            strict=True,
        ):
            selected = random.integers(
                0,
                candidate.shape[0],
                size=(size, candidate.shape[0]),
            )
            candidate_samples.append(candidate[selected].reshape(size, -1))
            incumbent_samples.append(incumbent[selected].reshape(size, -1))
        candidate_values = np.concatenate(candidate_samples, axis=1)
        incumbent_values = np.concatenate(incumbent_samples, axis=1)
        distribution[start:stop] = np.nanpercentile(
            candidate_values,
            percentile,
            axis=1,
        ) - np.nanpercentile(
            incumbent_values,
            percentile,
            axis=1,
        )
    standard_error = float(np.std(distribution, ddof=1))
    if not isfinite(standard_error) or standard_error <= 0.0:
        raise ValueError(
            "stratified bootstrap standard error must be positive"
        )
    return StratifiedBootstrapEstimate(
        endpoint_id=endpoint_id,
        percentile=percentile,
        realization_count=sum(count for _, count in stratum_counts),
        stratum_counts=tuple(stratum_counts),
        positive_regression=candidate_point - incumbent_point,
        bootstrap_standard_error=standard_error,
        bootstrap_upper_sensitivity=float(
            np.quantile(distribution, percentile / _PERCENT_SCALE)
        ),
        resamples=resamples,
        seed=seed,
    )


def _endpoint_power(
    estimate: StratifiedBootstrapEstimate,
    *,
    selected_realization_count: int,
    practical_regression_margin: float,
    variance_inflation: float,
    confidence_level: float,
) -> ConfirmationEndpointPower:
    """Scale one guarded closed estimate to a fresh population size."""
    standard_error = (
        variance_inflation
        * estimate.bootstrap_standard_error
        * sqrt(estimate.realization_count / selected_realization_count)
    )
    expected = max(0.0, estimate.positive_regression)
    critical = NormalDist().inv_cdf(confidence_level)
    power = NormalDist().cdf(
        (practical_regression_margin - expected) / standard_error - critical
    )
    return ConfirmationEndpointPower(
        endpoint_id=estimate.endpoint_id,
        planning_expected_regression=expected,
        planning_standard_error=standard_error,
        practical_regression_margin=practical_regression_margin,
        power=power,
    )


def balanced_confirmation_power(  # noqa: PLR0913
    estimates: Sequence[StratifiedBootstrapEstimate],
    *,
    selected_count_per_stratum: int,
    practical_regression_margin: float = 0.05,
    variance_inflation: float,
    confidence_level: float,
    minimum_joint_power: float,
) -> BalancedConfirmationPlan:
    """Calculate guarded joint power at one balanced fresh sample size."""
    if not estimates:
        raise ValueError("confirmation planning requires endpoint estimates")
    if (
        not isfinite(practical_regression_margin)
        or practical_regression_margin <= 0.0
    ):
        raise ValueError("practical regression margin must be positive")
    if not isfinite(variance_inflation) or variance_inflation <= 1.0:
        raise ValueError("variance inflation must be greater than one")
    if (
        not isfinite(confidence_level)
        or not _MINIMUM_ONE_SIDED_CONFIDENCE < confidence_level < 1.0
    ):
        raise ValueError("confidence level must lie in (0.5, 1)")
    if (
        not isfinite(minimum_joint_power)
        or not 0.0 < minimum_joint_power < 1.0
    ):
        raise ValueError("minimum joint power must lie in (0, 1)")
    if (
        isinstance(selected_count_per_stratum, bool)
        or type(selected_count_per_stratum) is not int
        or selected_count_per_stratum < _MINIMUM_REALIZATIONS_PER_STRATUM
    ):
        raise ValueError("selected count per stratum must be at least two")
    counts = estimates[0].stratum_counts
    if any(estimate.stratum_counts != counts for estimate in estimates):
        raise ValueError("confirmation endpoints must share exact strata")
    if len({count for _, count in counts}) != 1:
        raise ValueError("closed confirmation evidence must be balanced")
    identities = {estimate.endpoint_id for estimate in estimates}
    if len(identities) != len(estimates):
        raise ValueError("confirmation endpoint identities must be unique")
    selected_total = selected_count_per_stratum * len(counts)
    endpoint_powers = tuple(
        _endpoint_power(
            estimate,
            selected_realization_count=selected_total,
            practical_regression_margin=practical_regression_margin,
            variance_inflation=variance_inflation,
            confidence_level=confidence_level,
        )
        for estimate in estimates
    )
    joint = max(
        0.0,
        1.0 - sum(1.0 - item.power for item in endpoint_powers),
    )
    return BalancedConfirmationPlan(
        selected_count_per_stratum=selected_count_per_stratum,
        selected_realization_count=selected_total,
        variance_inflation=variance_inflation,
        confidence_level=confidence_level,
        minimum_joint_power=minimum_joint_power,
        joint_power_lower_bound=joint,
        endpoint_powers=endpoint_powers,
    )


def minimum_balanced_confirmation_count(  # noqa: PLR0913
    estimates: Sequence[StratifiedBootstrapEstimate],
    *,
    practical_regression_margin: float = 0.05,
    variance_inflation: float,
    confidence_level: float,
    minimum_joint_power: float,
    maximum_count_per_stratum: int = _DEFAULT_MAXIMUM_COUNT_PER_STRATUM,
    require_solution: bool = True,
) -> BalancedConfirmationPlan:
    """Return the first balanced fresh count meeting a union power bound."""
    if (
        isinstance(maximum_count_per_stratum, bool)
        or type(maximum_count_per_stratum) is not int
        or maximum_count_per_stratum < _MINIMUM_REALIZATIONS_PER_STRATUM
    ):
        raise ValueError("maximum count per stratum must be at least two")
    last_plan: BalancedConfirmationPlan | None = None
    for selected_per_stratum in range(
        _MINIMUM_REALIZATIONS_PER_STRATUM,
        maximum_count_per_stratum + 1,
    ):
        last_plan = balanced_confirmation_power(
            estimates,
            selected_count_per_stratum=selected_per_stratum,
            practical_regression_margin=practical_regression_margin,
            variance_inflation=variance_inflation,
            confidence_level=confidence_level,
            minimum_joint_power=minimum_joint_power,
        )
        if last_plan.joint_power_lower_bound >= minimum_joint_power:
            return last_plan
    if require_solution:
        raise ValueError(
            "joint power target exceeds the planning search bound"
        )
    assert last_plan is not None
    return last_plan
