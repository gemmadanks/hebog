"""Contracts for the Phase 5 hierarchy-activation root-cause review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-source-reconstruction-root-"
    "cause-pre-review.json"
)


def _load() -> dict[str, Any]:
    """Load the non-executable root-cause review."""
    return json.loads(_REVIEW.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    """Return the hexadecimal SHA-256 of one evidence file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_review_is_non_executable() -> None:
    """A root-cause conclusion cannot grant implementation or execution."""
    review = _load()

    assert review["schema_version"] == 1
    assert review["review_id"] == (
        "phase-5-public-finder-source-reconstruction-root-cause-pre-review"
    )
    assert review["status"] == (
        "ready-for-named-hierarchy-activation-repair-review"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-root-cause-pre-review-for-fixture-only-"
        "repair"
    )


def test_review_binds_exact_terminal_and_prior_ledgers() -> None:
    """The diagnosis remains inseparable from both terminal comparisons."""
    context = _load()["binding_context"]

    for name in ("terminal_ledger", "prior_terminal_ledger"):
        evidence = context[name]
        assert _sha256(_ROOT / evidence["path"]) == evidence["sha256"]
    assert context["candidate"] == {
        "configuration_sha256": (
            "470e918db1a640d7393edc02de01fc57b50881b908bd6d5dac18a57709117bbb"
        ),
        "product_set_sha256": (
            "0d8c2d0bb783aa812c520667ca71a557bae08d3a4a234ba70d7589c1285aa3c7"
        ),
        "revision": "42c75f44b71800ae5fa1e0ebe1669caa7da59f85",
        "source_tree_sha256": (
            "1b67c7f6f768d6f83becc853a1ebd45b3996164cd2b87fdc0f71b9a3299e6bf1"
        ),
    }


def test_review_records_terminal_scientific_invariance() -> None:
    """A dormant correction cannot be described as a near gate crossing."""
    science = _load()["terminal_science"]

    assert science["status"] == "fail"
    assert science["cumulative_science_regression_ready"] is False
    assert science["compact"] == {
        "like_semantics_regression_count": 0,
        "status": "pass",
    }
    continuum = science["continuum"]
    assert continuum["status_counts"] == {
        "fail": 44,
        "indeterminate": 0,
        "pass": 89,
        "underpowered": 10,
    }
    assert continuum["like_semantics_regression_count"] == 37
    assert continuum["status_transition_count_vs_prior"] == 0
    assert continuum["overall_duplicate_fraction"] == 0.2529464285714285
    assert continuum["overall_split_fraction"] == 0.2529464285714285


def test_review_distinguishes_confirmed_and_hypothetical_causes() -> None:
    """Only the reproduced ownership-plane defect is a confirmed cause."""
    causes = _load()["causal_findings"]

    assert causes["confirmed_primary_defect"]["classification"] == (
        "confirmed-by-code-trace-and-controlled-analytic-reproduction"
    )
    assert causes["exact_overlap_scale_shift"]["classification"] == (
        "plausible-secondary-hypothesis-not-yet-reproduced"
    )
    assert causes["ultimate_root_overmerge"]["classification"] == (
        "prospective-safety-risk-not-observed-cause"
    )
    assert causes["mask_support"]["classification"] == (
        "prior-primary-hypothesis-refuted-for-this-population"
    )
    assert causes["evaluator_and_adapter"]["classification"] == (
        "excluded-as-primary-cause"
    )


def test_controlled_reproduction_exposes_attachment_ambiguity() -> None:
    """Expanded ownership loses a valid unique-parent association."""
    reproduction = _load()["causal_findings"]["controlled_reproduction"]

    assert reproduction["observed_with_expanded_measurement_labels"] == {
        "ambiguous_component_count": 1,
        "membership_sizes": [1, 1],
    }
    expected = {"ambiguous_component_count": 0, "membership_sizes": [2]}
    assert reproduction["observed_with_direct_seed_labels"] == expected
    assert reproduction["expected"] == expected


def test_repair_separates_identity_from_measurement_ownership() -> None:
    """The fix must preserve both scientific label semantics explicitly."""
    repair = _load()["recommended_repair"]

    assert repair["identity_separation"] == {
        "direct_component_labels": (
            "immutable hierarchy attachment and component identity"
        ),
        "measurement_component_labels": (
            "connected recovered support ownership for masks and source "
            "measurement"
        ),
    }
    assert repair["no_new_numeric_thresholds"] is True
    assert repair["scope"] == (
        "source-hierarchy-activation-and-observability-only"
    )


def test_repair_requires_activation_telemetry_and_overmerge_controls() -> None:
    """Another replay must make activation observable and fail closed."""
    review = _load()
    telemetry = set(review["recommended_repair"]["activation_telemetry"])
    safety = set(review["test_first_matrix"]["safety"])

    assert {
        "catalogue-source-count",
        "membership-size-histogram",
        "multiple-finest-feature-attachment-count",
        "branched-lineage-count",
        "unique-convergence-count",
    } <= telemetry
    assert {
        "two-independent-sources-with-a-real-coarse-bridge",
        "crowded-many-seed-field",
        "multiple-common-ancestor-candidates",
        "scale-shift-without-exact-overlap",
    } <= safety


def test_review_requires_separate_replay_approval() -> None:
    """Named repair approval can never silently authorize a replay."""
    review = _load()

    assert review["allowed_after_separate_approval"] == [
        "test-first-direct-seed-hierarchy-attachment-repair",
        "fixture-only-hierarchy-activation-and-safety-validation",
        "compact-hierarchy-activation-telemetry",
        "serial-and-existing-dask-invariance-validation",
        "non-executable-candidate-and-replay-identity-freeze",
    ]
    assert review["required_sequence"][-2:] == [
        "freeze-exact-non-executable-candidate-and-replay-identities",
        "obtain-separate-exact-approval-before-any-cumulative-replay",
    ]
