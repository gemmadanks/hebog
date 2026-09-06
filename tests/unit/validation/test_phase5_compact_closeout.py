"""Contracts for the bounded Phase 5 closeout progression."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256, source_tree_sha256

_ROOT = Path(__file__).parents[3]
_RISK_ACCEPTANCE = (
    _ROOT
    / "config/contracts/phase-5-cumulative-retention-risk-acceptance.json"
)
_PRODUCTION_AUDIT = (
    _ROOT / "config/contracts/phase-5-production-candidate-audit.json"
)
_SENTINEL_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-compact-held-out-sentinel-pre-review.json"
)
_CANDIDATE = {
    "configuration_sha256": (
        "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
    ),
    "revision": "95cfc76ded56556dc3ad6894410962d34f0d5604",
    "source_tree_sha256": (
        "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
    ),
}


def _document(path: Path) -> dict[str, Any]:
    """Load one checked-in closeout contract."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_risk_acceptance_preserves_the_incomplete_terminal_result() -> None:
    """Human acceptance cannot silently turn uncertainty into a pass."""
    acceptance = _document(_RISK_ACCEPTANCE)
    evidence = acceptance["terminal_evidence"]

    assert acceptance["status"] == (
        "accepted-for-phase-5-progression-with-disclosure"
    )
    assert evidence["status"] == "incomplete"
    assert evidence["cumulative_science_regression_ready"] is False
    assert evidence["all_required_endpoints_pass"] is False
    assert evidence["comparison_status_counts"] == {
        "fail": 0,
        "pass": 1183,
        "underpowered": 4,
    }
    assert acceptance["skipped_confirmation"]["image_count"] == 4608
    assert acceptance["claims"]["fully_powered_incumbent_retention"] is False
    assert not any(acceptance["execution_authorizations"].values())


def test_production_audit_freezes_exact_candidate() -> None:
    """Only a clean exact public path may advance to held-out design."""
    audit = _document(_PRODUCTION_AUDIT)

    assert audit["candidate"] == _CANDIDATE
    assert source_tree_sha256(_ROOT) == _CANDIDATE["source_tree_sha256"]
    assert audit["status"] == "pass-no-release-blocking-defects"
    assert audit["decision"] == {
        "candidate_identity_unchanged": True,
        "held_out_design_may_proceed": True,
        "release_blocking_finding_count": 0,
        "source_change_required": False,
    }
    assert audit["release_blocking_findings"] == []
    assert {
        item["finding_id"] for item in audit["deferred_non_blocking_findings"]
    } == {
        "curated-scientific-composition-digest",
        "production-science-validation-namespace",
    }
    assert not any(audit["execution_authorizations"].values())


def test_compact_sentinel_is_fresh_bounded_and_non_executable() -> None:
    """The final check is a bounded sentinel rather than a new campaign."""
    review = _document(_SENTINEL_REVIEW)
    population = review["population"]
    execution = review["execution_budget"]

    assert review["candidate"] == _CANDIDATE
    assert review["status"] == "prospectively-designed-non-executable"
    assert population["role"] == "qualification"
    assert population["image_shapes_yx"] == [[384, 512], [512, 512]]
    assert population["maximum_image_shape_yx"] == [512, 512]
    assert population["known_risk_image_count"] == 144
    assert population["compact_guard_image_count"] == 24
    assert population["image_count"] == 168
    assert population["noise_realizations_per_cell"] == 4
    assert population["seed_range"] == [2026970001, 2026970168]
    assert population["seed_audit"]["seed_disjoint"] is True
    assert execution == {
        "caller_owned_dask_comparisons": 12,
        "current_hebog_serial_executions": 168,
        "maximum_completion_window_hours": 8,
        "minimum_free_disk_gib": 8,
        "released_pybdsf_executions": 168,
        "total_finder_executions": 348,
        "worker_concurrency": 2,
    }
    assert review["claim_boundary"]["standalone_powered_parity_claim"] is False
    assert review["decision_policy"]["pooling_may_hide_failure"] is False
    assert not any(review["execution_authorizations"].values())


def test_compact_sentinel_binds_the_acceptance_and_audit() -> None:
    """Changing the progression rationale requires a replacement review."""
    review = _document(_SENTINEL_REVIEW)

    for binding in review["progression_bindings"]:
        path = _ROOT / binding["path"]
        assert file_sha256(path) == binding["sha256"]
