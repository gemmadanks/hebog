"""Contracts for the terminal-feature persistence pre-review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-terminal-feature-persistence-"
    "pre-review.json"
)


def _load() -> dict[str, Any]:
    """Load the non-executable scientific pre-review."""
    return json.loads(_REVIEW.read_text(encoding="utf-8"))


def test_review_is_non_executable() -> None:
    """A terminal scientific diagnosis cannot authorize its own repair."""
    review = _load()

    assert review["schema_version"] == 1
    assert review["review_id"] == (
        "phase-5-public-finder-terminal-feature-persistence-pre-review"
    )
    assert review["status"] == (
        "ready-for-named-terminal-feature-persistence-review"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-terminal-feature-persistence-pre-"
        "review-for-fixture-only-implementation"
    )


def test_review_binds_the_exact_terminal_failure() -> None:
    """The proposed repair remains bound to immutable terminal evidence."""
    context = _load()["binding_context"]
    terminal = context["terminal_parent_ledger"]

    assert terminal == {
        "path": (
            "benchmark-results/phase-5/cumulative-regression-ledger-"
            "public-finder-terminal-parent-correction.json"
        ),
        "sha256": (
            "e2ee663f4eade383518eabbafda5cd33bfe9808b4a9b37492a77337738b611db"
        ),
    }
    assert context["failed_candidate"] == {
        "configuration_sha256": (
            "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
        ),
        "revision": "85d580713664b962ae256a98b065849cf8eb9283",
        "source_tree_sha256": (
            "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
        ),
    }
    assert context["terminal_product_set_sha256"] == (
        "de69d4edfe49e8b6048b59a9ad24a5532823ae78fd05daf54ab09115636fb143"
    )


def test_review_accounts_for_every_terminal_failure() -> None:
    """The correction cannot hide an unrelated failed endpoint."""
    failure = _load()["causal_findings"]["confirmed_remaining_failure"]

    assert len(failure["failed_endpoint_ids"]) == 35
    assert len(set(failure["failed_endpoint_ids"])) == 35
    assert failure["continuum_status_counts"] == {
        "fail": 35,
        "indeterminate": 0,
        "pass": 96,
        "underpowered": 12,
    }
    assert failure["compact"] == {
        "like_semantics_regression_count": 0,
        "status": "pass",
    }
    assert failure["like_semantics_regression_count"] == 30
    assert failure["cumulative_science_regression_ready"] is False
    assert failure["all_required_endpoints_pass"] is False


def test_review_separates_confirmed_facts_from_unresolved_attribution() -> (
    None
):
    """Implementation requires a red fixture, not inference from scores."""
    findings = _load()["causal_findings"]

    assert findings["confirmed_effect"]["classification"] == (
        "terminal-powered-cumulative-evidence"
    )
    assert findings["confirmed_remaining_failure"]["classification"] == (
        "terminal-powered-cumulative-evidence"
    )
    assert findings["confirmed_algorithm_boundary"]["classification"] == (
        "code-path-inspection"
    )
    assert findings["unresolved_attribution"]["classification"] == (
        "must-be-separated-by-fixture-before-implementation"
    )


def test_recommended_rule_is_bounded_and_fail_closed() -> None:
    """The proposal changes persistence evidence without tuning science."""
    design = _load()["recommended_design"]
    rejected = set(design["rejected_shortcuts"])

    assert design["no_new_fitted_numeric_thresholds"] is True
    assert (
        "mutual uniqueness and whole-group fail-closed reconciliation"
        in (design["fixed_not_tuned"])
    )
    assert {
        "accepting every terminal cycle without persistence",
        "using connected significant support as source membership",
        "accepting terminal pairs or paths",
        "truth or PyBDSF assisted grouping",
        "changing thresholds gates margins or aperture definitions",
    } <= rejected
    assert _load()["required_sequence"][-2:] == [
        "freeze-exact-non-executable-candidate-and-replay-identities",
        "bind-the-existing-broad-replay-intent-to-those-new-exact-identities-"
        "before-execution",
    ]
