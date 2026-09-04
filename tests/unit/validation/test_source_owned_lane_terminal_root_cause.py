"""Contracts for the completed source-owned lane root-cause review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-source-owned-lane-terminal-root-cause-review.json"
)


def _review() -> dict[str, Any]:
    value: object = json.loads(_REVIEW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_review_binds_the_failed_terminal_lane() -> None:
    """The diagnosis cannot drift away from its immutable failed evidence."""
    review = _review()
    terminal = review["binding_context"]["terminal_decision"]

    assert review["status"] == (
        "root-cause-complete-ready-for-test-first-successor"
    )
    assert terminal["status"] == "fail"
    assert terminal["failed_geometry_count"] == 6
    assert file_sha256(_ROOT / terminal["path"]) == terminal["file_sha256"]
    assert set(review["authorization"].values()) == {False}


def test_review_accounts_for_every_failure_without_rescoring() -> None:
    """Every observed family has a cause and the old result stays failed."""
    review = _review()
    accounting = review["failure_accounting"]
    governance = review["governance_correction"]

    assert accounting["all_six_failed_geometries_accounted_for"] is True
    assert accounting["unexplained_failure_count"] == 0
    assert governance["historical_result_immutable"] is True
    assert governance["no_retrospective_rescore"] is True


def test_review_corrects_split_semantics_without_hiding_reliability() -> None:
    """Truth fragmentation and remote false detections remain distinct."""
    review = _review()
    finding = review["causal_findings"]["split_endpoint"]
    correction = review["recommended_correction"]["development_evaluator"]

    assert finding["classification"] == (
        "confirmed-development-evaluator-semantic-defect-not-source-"
        "hierarchy-fragmentation"
    )
    assert finding["evidence"]["naive_split_images"] == 43
    assert finding["evidence"]["truth_linked_split_images"] == 0
    assert finding["evidence"]["unmatched_remote_source_rows"] == 58
    assert "Retain every unlinked row" in correction


def test_review_uses_estimator_geometry_not_an_outcome_tuned_radius() -> None:
    """The adaptive repair is derived from the existing fine footprint."""
    review = _review()
    finding = review["causal_findings"]["adaptive_background_guard"]
    correction = review["recommended_correction"]["adaptive_background"]

    assert finding["classification"] == (
        "confirmed-incomplete-estimator-footprint-protection"
    )
    assert "17 pixels" in finding["evidence"]
    assert "max(fine_window_shape_yx)//2" in correction
    assert "introduces no science threshold" in correction


def test_review_preserves_dual_pybdsf_and_incumbent_phase_five_gates() -> None:
    """Aspirational truth floors cannot weaken comparator parity."""
    gate = _review()["governance_correction"]["final_phase_5_gate"]

    assert "released and pinned-master PyBDSF" in gate
    assert "best-Hebog retention" in gate
    assert "unmatched-source reliability" in gate
    assert "No aggregate or aspirational absolute threshold can waive" in gate
