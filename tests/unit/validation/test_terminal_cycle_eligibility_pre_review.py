"""Contracts for the terminal-cycle eligibility pre-review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-terminal-cycle-eligibility-"
    "pre-review.json"
)


def _load() -> dict[str, Any]:
    """Load the non-executable scientific pre-review."""
    return json.loads(_REVIEW.read_text(encoding="utf-8"))


def test_review_is_non_executable() -> None:
    """A terminal scientific failure cannot authorize its own repair."""
    review = _load()

    assert review["schema_version"] == 1
    assert review["review_id"] == (
        "phase-5-public-finder-terminal-cycle-eligibility-pre-review"
    )
    assert review["status"] == (
        "ready-for-named-terminal-cycle-eligibility-review"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-terminal-cycle-eligibility-pre-"
        "review-for-fixture-only-implementation"
    )


def test_review_binds_the_exact_terminal_failure() -> None:
    """The diagnosis remains bound to immutable terminal evidence."""
    context = _load()["binding_context"]

    assert context["terminal_feature_ledger"] == {
        "path": (
            "benchmark-results/phase-5/cumulative-regression-ledger-"
            "public-finder-terminal-feature-persistence.json"
        ),
        "sha256": (
            "a9b4d57ec7384eb1d625b9a030126f4ca5d45f0a83150b309d14b3536eeae8a6"
        ),
    }
    assert context["failed_candidate"] == {
        "configuration_sha256": (
            "2d6ab6bbdd06f109f9703fb0b49f489933ddc00b391f681253693b38d0f4b1de"
        ),
        "revision": "3d080f78da09ada6753a4e5df898e1d5daa59597",
        "source_tree_sha256": (
            "a25d22d80f4e639e4543ee058acade6feda15105f6325dc909e69fcfb8f03924"
        ),
    }
    assert context["terminal_product_set_sha256"] == (
        "cd66892ff1ca363cafd5bfe213626253645d2a976efb32f8ec935bb2e6e10748"
    )


def test_review_accounts_for_every_terminal_failure() -> None:
    """The next correction cannot hide an unrelated failed endpoint."""
    failure = _load()["causal_findings"]["confirmed_regression"]

    assert len(failure["failed_endpoint_ids"]) == 39
    assert len(set(failure["failed_endpoint_ids"])) == 39
    assert failure["continuum_status_counts"] == {
        "fail": 39,
        "indeterminate": 0,
        "pass": 93,
        "underpowered": 11,
    }
    assert failure["compact"] == {
        "like_semantics_regression_count": 0,
        "status": "pass",
    }
    assert failure["like_semantics_regression_count"] == 33
    assert failure["cumulative_science_regression_ready"] is False
    assert failure["all_required_endpoints_pass"] is False


def test_review_records_non_activation_before_inference() -> None:
    """Terminal telemetry separates observed facts from causal inference."""
    findings = _load()["causal_findings"]
    diagnostics = findings["confirmed_non_activation"]["diagnostics"]

    assert findings["confirmed_non_activation"]["classification"] == (
        "terminal-powered-cumulative-evidence"
    )
    assert diagnostics["terminal_cycle_candidate_count"] == 1211
    assert diagnostics["terminal_cycle_parent_count"] == 1211
    assert diagnostics["exact_feature_count"] == 4414
    assert diagnostics["displaced_candidate_count"] == 0
    assert diagnostics["displaced_accepted_count"] == 0
    assert findings["confirmed_algorithm_boundary"]["classification"] == (
        "code-path-inspection"
    )
    assert findings["unresolved_attribution"]["classification"] == (
        "must-be-separated-by-fixture-before-implementation"
    )


def test_recommended_rule_preserves_membership_and_science() -> None:
    """The proposal changes only eligibility for persisted cycle geometry."""
    design = _load()["recommended_design"]
    rejected = set(design["rejected_shortcuts"])

    assert design["no_new_fitted_numeric_thresholds"] is True
    assert (
        "existing direct component and measurement-owner identities"
        in (design["fixed_not_tuned"])
    )
    assert {
        "accepting an unseeded feature without adjacent-scale persistence",
        "turning an unseeded feature into a catalogue member",
        "accepting connected support as source membership",
        "accepting pairs paths or non-cycle bridges",
        "truth or reference-finder assisted grouping",
        "changing thresholds gates margins or measurement definitions",
    } <= rejected
    assert _load()["required_sequence"][-2:] == [
        "freeze-exact-non-executable-candidate-and-replay-identities",
        "obtain-new-exact-replay-approval-before-execution",
    ]
