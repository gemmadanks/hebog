"""Contracts for the Phase 5 final retention-confirmation pre-review."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any, cast

import pytest

from hebog.validation.prospective_retention_extension import (
    StratifiedBootstrapEstimate,
    balanced_confirmation_power,
    minimum_balanced_confirmation_count,
)

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-final-retention-confirmation-pre-review.json"
)
_PROGRAM = _ROOT / "scripts/validation/review_phase5_retention_confirmation.py"


def _review() -> dict[str, Any]:
    value = json.loads(_REVIEW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _estimate(value: dict[str, Any]) -> StratifiedBootstrapEstimate:
    return StratifiedBootstrapEstimate(
        endpoint_id=value["endpoint_id"],
        percentile=value["percentile"],
        realization_count=value["realization_count"],
        stratum_counts=tuple(
            (stratum, count) for stratum, count in value["stratum_counts"]
        ),
        positive_regression=value["positive_regression"],
        bootstrap_standard_error=value["bootstrap_standard_error"],
        bootstrap_upper_sensitivity=value["bootstrap_upper_sensitivity"],
        resamples=value["resamples"],
        seed=value["seed"],
    )


def test_pre_review_freezes_no_execution_or_scientific_change() -> None:
    """Planning evidence cannot authorize a run or alter source science."""
    review = _review()

    assert review["status"] == "awaiting-human-scientific-review"
    assert set(review["authorization"].values()) == {False}
    assert review["recommendations"]["source_finding_change_required"] is False
    assert (
        review["recommendations"][
            "closed_decision_remains_immutable_and_incomplete"
        ]
        is True
    )
    assert review["root_cause"]["source_finding_defect_detected"] is False


def test_pre_review_power_recomputes_and_rounds_up() -> None:
    """The selected balanced population clears the unchanged joint gate."""
    review = _review()
    method = review["planning_method"]
    estimates = tuple(_estimate(item) for item in review["planning_estimates"])
    minimum = minimum_balanced_confirmation_count(
        estimates,
        practical_regression_margin=method[
            "practical_regression_margin_beams"
        ],
        variance_inflation=method["variance_inflation"],
        confidence_level=method["confidence_level"],
        minimum_joint_power=method["minimum_joint_power"],
    )
    selected_count = review["selected_balanced_population"][
        "selected_count_per_stratum"
    ]
    selected = balanced_confirmation_power(
        estimates,
        selected_count_per_stratum=selected_count,
        practical_regression_margin=method[
            "practical_regression_margin_beams"
        ],
        variance_inflation=method["variance_inflation"],
        confidence_level=method["confidence_level"],
        minimum_joint_power=method["minimum_joint_power"],
    )

    assert minimum.selected_count_per_stratum == 1142
    assert selected_count == 1152
    assert selected.joint_power_lower_bound == pytest.approx(
        review["selected_balanced_population"]["joint_power_lower_bound"]
    )
    assert selected.joint_power_lower_bound >= 0.90


def test_review_program_binds_closed_evidence_identity() -> None:
    """The generator cannot silently consume a different terminal result."""
    program = runpy.run_path(str(_PROGRAM))
    review = _review()

    assert (
        program["_CLOSED_DECISION_SHA256"]
        == review["closed_evidence"]["paired_decision_file_sha256"]
    )
    assert (
        program["_CLOSED_RECORD_CANONICAL_SHA256"]
        == review["closed_evidence"]["paired_decision_record_canonical_sha256"]
    )
    assert (
        program["_SOURCE_REQUEST_SHA256"]
        == review["closed_evidence"]["source_request_sha256"]
    )


def test_review_rejects_any_changed_closed_verdict() -> None:
    """A different terminal result cannot reuse this scientific review."""
    program = runpy.run_path(str(_PROGRAM))

    with pytest.raises(ValueError, match="identity or status changed"):
        program["build_review"](
            decision={"status": "pass"},
            source_request={},
        )


def test_shell_alias_audit_detects_one_divergent_registry_view() -> None:
    """The three shell labels collapse only while their payloads are exact."""
    program = runpy.run_path(str(_PROGRAM))
    endpoint_ids = program["_SHELL_ENDPOINTS"]
    summaries = {
        ("current-hebog", "input"): {
            "endpoints": {
                endpoint_id: {
                    "status": "success",
                    "values": [1.0],
                }
                for endpoint_id in endpoint_ids
            }
        }
    }
    program["_validate_shell_aliases"](summaries)
    summaries[("current-hebog", "input")]["endpoints"][endpoint_ids[-1]][
        "values"
    ] = [2.0]

    with pytest.raises(ValueError, match="aliases are not identical"):
        program["_validate_shell_aliases"](summaries)
