"""Prospective Phase 5 non-inferiority decision tests."""

from __future__ import annotations

import json
from math import inf, nan
from pathlib import Path

import pytest

from hebog.validation.external_runners import file_sha256
from hebog.validation.prospective_science_evaluator import (
    ProspectiveComparisonEvidence,
    evaluate_prospective_comparison,
)

_ROOT = Path(__file__).parents[3]
_HISTORICAL_EVALUATORS = {
    "src/hebog/validation/noninferiority.py": (
        "edc4a357ebc99ff87f705b8b1b631416d6551659669f2e48dd677c0dcdef487a"
    ),
    "scripts/validation/evaluate_phase5_external_decision.py": (
        "df99e10a6fbbe7c4c1b9826c88b0d11908500c817e30aea7750bfc9d920cadab"
    ),
    "scripts/validation/review_phase5_cumulative_regressions.py": (
        "5d41d31ee79cd0d6d203cd774267fd504d06fe7662768486f99c31a7902b8a3f"
    ),
}


def _evidence(**changes: object) -> ProspectiveComparisonEvidence:
    values: dict[str, object] = {
        "endpoint_id": "continuum--reliability--overall",
        "comparator_id": "released-pybdsf",
        "candidate_available": True,
        "comparator_available": True,
        "positive_regression": 0.005,
        "upper_confidence_limit": 0.015,
        "practical_regression_margin": 0.02,
        "observed_paired_standard_deviation": 0.08,
        "planning_paired_standard_deviation": 0.06,
    }
    values.update(changes)
    return ProspectiveComparisonEvidence(**values)  # type: ignore[arg-type]


def test_historical_evaluators_remain_byte_unchanged() -> None:
    """The prospective repair cannot retrospectively change closed gates."""
    assert {
        path: file_sha256(_ROOT / path) for path in _HISTORICAL_EVALUATORS
    } == _HISTORICAL_EVALUATORS


def test_activation_decision_binds_exact_prerequisite_programs() -> None:
    """Human scope cannot silently drift to different prerequisites."""
    path = (
        _ROOT / "config/contracts/phase-5-prospective-science-activation-"
        "decision.json"
    )
    decision = json.loads(path.read_text(encoding="utf-8"))

    assert decision["authorization"] == {
        "cutover_authorized": False,
        "full_replay_authorized_only_after_all_activation_gates_pass": True,
        "optimization_authorized": False,
        "qualification_authorized": False,
        "release_authorized": False,
        "rescoring_authorized": False,
        "scientific_smoke_authorized": True,
        "threshold_or_photometric_tuning_authorized": False,
    }
    for artifact in decision["prerequisite_programs"]:
        assert file_sha256(_ROOT / artifact["path"]) == artifact["sha256"]
    amendment = decision["boundary_refinement_amendment"]
    assert amendment["closed_smoke_sha256"] == (
        "e3ac8e62b0d136078b2a4a15e7841b12f62c4381db7bb581d03a9468448b248c"
    )
    assert file_sha256(_ROOT / amendment["pre_review_path"]) == (
        "e92ac2893699bb0ff96347af6a691c654649fa6e152ef5dd588930f9f0cf82aa"
    )
    assert (_ROOT / amendment["implementation_decision_path"]).is_file()


def test_variance_above_plan_does_not_override_passing_interval() -> None:
    """Planning variance is an audited design assumption, not a gate."""
    decision = evaluate_prospective_comparison(_evidence())

    assert decision.status == "pass"
    assert decision.planning_variance_assumption_met is False
    assert decision.assumption_deviations == (
        "observed-paired-standard-deviation-exceeds-planning-assumption",
    )


def test_interval_crossing_margin_is_underpowered_despite_low_variance() -> (
    None
):
    """A favourable variance audit cannot make an inconclusive CI pass."""
    decision = evaluate_prospective_comparison(
        _evidence(
            positive_regression=0.005,
            upper_confidence_limit=0.025,
            observed_paired_standard_deviation=0.05,
        )
    )

    assert decision.status == "underpowered"
    assert decision.planning_variance_assumption_met is True


def test_point_regression_beyond_margin_is_a_confirmed_failure() -> None:
    """A materially worse point estimate cannot be called inconclusive."""
    decision = evaluate_prospective_comparison(
        _evidence(positive_regression=0.021, upper_confidence_limit=0.03)
    )

    assert decision.status == "fail"


def test_exact_upper_confidence_boundary_passes() -> None:
    """The frozen contract explicitly admits equality at the margin."""
    decision = evaluate_prospective_comparison(
        _evidence(upper_confidence_limit=0.02)
    )

    assert decision.status == "pass"


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({"candidate_available": False}, "fail"),
        ({"comparator_available": False}, "underpowered"),
        ({"positive_regression": None}, "indeterminate"),
        ({"upper_confidence_limit": None}, "indeterminate"),
        ({"observed_paired_standard_deviation": None}, "indeterminate"),
        ({"positive_regression": nan}, "indeterminate"),
        ({"upper_confidence_limit": inf}, "indeterminate"),
        ({"observed_paired_standard_deviation": nan}, "indeterminate"),
    ],
)
def test_missing_or_nonfinite_evidence_fails_closed(
    changes: dict[str, object], status: str
) -> None:
    """Unavailable evidence never establishes prospective parity."""
    decision = evaluate_prospective_comparison(_evidence(**changes))

    assert decision.status == status
    assert decision.passed is False


@pytest.mark.parametrize(
    "changes",
    [
        {"practical_regression_margin": -0.01},
        {"planning_paired_standard_deviation": 0.0},
        {"planning_paired_standard_deviation": inf},
        {"observed_paired_standard_deviation": -0.01},
    ],
)
def test_invalid_policy_or_dispersion_is_rejected(
    changes: dict[str, object],
) -> None:
    """Malformed prospective policies cannot produce a decision."""
    with pytest.raises(ValueError):
        evaluate_prospective_comparison(_evidence(**changes))
