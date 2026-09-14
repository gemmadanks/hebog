"""Prospective observed-data decisions for Phase 5 non-inferiority.

Planning dispersion is kept in the result as an assumption audit.  It never
overrides the confidence interval computed from the observed paired
realizations.  Historical Phase 4/5 evaluators intentionally do not import
this module and retain their original decision semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

ProspectiveDecisionStatus = Literal[
    "pass", "fail", "underpowered", "indeterminate"
]


@dataclass(frozen=True, slots=True)
class ProspectiveComparisonEvidence:
    """Observed paired evidence for one frozen endpoint and comparator."""

    endpoint_id: str
    comparator_id: str
    candidate_available: bool
    comparator_available: bool
    positive_regression: float | None
    upper_confidence_limit: float | None
    practical_regression_margin: float
    observed_paired_standard_deviation: float | None
    planning_paired_standard_deviation: float


@dataclass(frozen=True, slots=True)
class ProspectiveComparisonDecision:
    """Fail-closed decision plus a non-binding planning audit."""

    endpoint_id: str
    comparator_id: str
    status: ProspectiveDecisionStatus
    passed: bool
    positive_regression: float | None
    upper_confidence_limit: float | None
    practical_regression_margin: float
    observed_paired_standard_deviation: float | None
    planning_paired_standard_deviation: float
    planning_variance_assumption_met: bool | None
    assumption_deviations: tuple[str, ...]
    reason: str


def _validate_policy(evidence: ProspectiveComparisonEvidence) -> None:
    """Reject malformed frozen margins and design assumptions."""
    if not evidence.endpoint_id or not evidence.comparator_id:
        raise ValueError("prospective comparison identity is incomplete")
    if (
        not isfinite(evidence.practical_regression_margin)
        or evidence.practical_regression_margin < 0.0
    ):
        raise ValueError("prospective regression margin is invalid")
    if (
        not isfinite(evidence.planning_paired_standard_deviation)
        or evidence.planning_paired_standard_deviation <= 0.0
    ):
        raise ValueError("prospective planning dispersion is invalid")
    observed = evidence.observed_paired_standard_deviation
    if observed is not None and isfinite(observed) and observed < 0.0:
        raise ValueError("prospective observed dispersion is invalid")


def _decision(
    evidence: ProspectiveComparisonEvidence,
    *,
    status: ProspectiveDecisionStatus,
    planning_met: bool | None,
    deviations: tuple[str, ...] = (),
    reason: str,
) -> ProspectiveComparisonDecision:
    """Build one immutable decision without duplicating evidence fields."""
    return ProspectiveComparisonDecision(
        endpoint_id=evidence.endpoint_id,
        comparator_id=evidence.comparator_id,
        status=status,
        passed=status == "pass",
        positive_regression=evidence.positive_regression,
        upper_confidence_limit=evidence.upper_confidence_limit,
        practical_regression_margin=evidence.practical_regression_margin,
        observed_paired_standard_deviation=(
            evidence.observed_paired_standard_deviation
        ),
        planning_paired_standard_deviation=(
            evidence.planning_paired_standard_deviation
        ),
        planning_variance_assumption_met=planning_met,
        assumption_deviations=deviations,
        reason=reason,
    )


def evaluate_prospective_comparison(
    evidence: ProspectiveComparisonEvidence,
) -> ProspectiveComparisonDecision:
    """Decide one comparison from its observed paired confidence limit.

    A point estimate beyond the practical margin is a confirmed material
    regression.  Otherwise, a confidence interval that still crosses the
    margin is underpowered.  Equality at the upper-confidence boundary passes
    exactly as frozen in the Phase 5 prospective contract.
    """
    _validate_policy(evidence)
    if not evidence.candidate_available:
        return _decision(
            evidence,
            status="fail",
            planning_met=None,
            reason="binding candidate evidence is unavailable",
        )
    if not evidence.comparator_available:
        return _decision(
            evidence,
            status="underpowered",
            planning_met=None,
            reason="binding comparator evidence is unavailable",
        )
    regression_value = evidence.positive_regression
    upper_value = evidence.upper_confidence_limit
    observed_value = evidence.observed_paired_standard_deviation
    if (
        regression_value is None
        or upper_value is None
        or observed_value is None
        or not isfinite(regression_value)
        or not isfinite(upper_value)
        or not isfinite(observed_value)
    ):
        return _decision(
            evidence,
            status="indeterminate",
            planning_met=None,
            reason="paired evidence is missing or non-finite",
        )
    observed = float(observed_value)
    planning_met = observed <= evidence.planning_paired_standard_deviation
    deviations = (
        ()
        if planning_met
        else (
            "observed-paired-standard-deviation-exceeds-planning-assumption",
        )
    )
    upper = float(upper_value)
    regression = float(regression_value)
    margin = evidence.practical_regression_margin
    if upper <= margin:
        return _decision(
            evidence,
            status="pass",
            planning_met=planning_met,
            deviations=deviations,
            reason="observed paired upper confidence limit is within margin",
        )
    if regression > margin:
        return _decision(
            evidence,
            status="fail",
            planning_met=planning_met,
            deviations=deviations,
            reason="paired point regression exceeds the practical margin",
        )
    return _decision(
        evidence,
        status="underpowered",
        planning_met=planning_met,
        deviations=deviations,
        reason="observed paired confidence interval crosses the margin",
    )
