"""Govern the prospective source-association replay composition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)
from hebog.validation.public_finder_correction import (
    public_finder_source_association_candidate_configuration,
)

_ROOT = Path(__file__).parents[3]
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-replay-"
    "composition-pre-review.json"
)


def _load() -> dict[str, Any]:
    """Load the static non-executable pre-review."""
    return json.loads(_PRE_REVIEW.read_text(encoding="utf-8"))


def test_replay_composition_pre_review_is_non_executable() -> None:
    """The packet recommends a minimal repair but grants no authority."""
    review = _load()

    assert review["schema_version"] == 1
    assert review["status"] == (
        "ready-for-named-replay-composition-implementation-review"
    )
    assert set(review["authorization"].values()) == {False}  # type: ignore[union-attr]
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-pre-review-for-fixture-and-no-write-"
        "implementation-and-non-executable-identity-freezing-only"
    )


def test_replay_composition_binds_exact_candidate_and_inputs() -> None:
    """The prospective seam uses the live candidate and immutable evidence."""
    review = _load()
    candidate = cast(dict[str, Any], review["candidate"])
    configuration = public_finder_source_association_candidate_configuration(
        _ROOT / "config/contracts/phase-5-corrective-a-review.json",
        _ROOT / "config/contracts/phase-5-public-finder-correction.json",
        _ROOT / "config/contracts/phase-5-public-finder-source-association-"
        "pre-review.json",
        _ROOT / "config/contracts/phase-5-public-finder-source-association-"
        "implementation-decision.json",
    )

    assert candidate["revision"] == (
        "26e639ace9d39b039eb7c3114427277c91809591"
    )
    assert source_tree_sha256(_ROOT) == candidate["source_tree_sha256"]
    assert (
        canonical_sha256(configuration) == (candidate["configuration_sha256"])
    )
    identities = [
        review["source_association_identity_review"],
        review["current_wrapper"],
        review["historical_replay"],
        review["non_transferable_authorization"]["execution_decision"],
        review["runtime_identity_registry"],
        *review["unchanged_dependencies"],
    ]
    for identity in identities:
        assert file_sha256(_ROOT / identity["path"]) == identity["sha256"]


def test_replay_composition_changes_only_candidate_binding_seams() -> None:
    """Population, evidence, scoring, and runtime dependencies stay frozen."""
    review = _load()
    repair = cast(dict[str, Any], review["prospective_repair"])
    boundary = cast(dict[str, Any], review["closed_boundary"])

    assert repair["allowed_changes"] == [
        "replace-candidate-revision-source-tree-and-configuration-bindings",
        "select-public-finder-source-association-candidate-configuration",
        "bind-source-association-pre-review-and-implementation-decision",
        "publish-to-a-new-write-once-ledger-path",
        "freeze-new-wrapper-and-non-executable-composition-identities",
    ]
    assert boundary["compact_image_count"] == 800
    assert boundary["continuum_image_count"] == 1600
    assert boundary["workers"] == 2
    assert boundary["reference_reconstruction_sha256"] == (
        "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
    )
    assert boundary["closed_baseline_sha256"] == (
        "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
    )
    assert (
        file_sha256(
            _ROOT
            / "benchmark-results/phase-5/cumulative-regression-ledger-public-"
            "finder-correction.json"
        )
        == boundary["failed_correction_ledger_sha256"]
    )
    assert boundary["required_result"] == (
        "cumulative_science_regression_ready=true-with-no-like-semantics-"
        "regression"
    )
    assert set(review["scientific_scope"].values()) == {False}  # type: ignore[union-attr]


def test_replay_composition_requires_fail_closed_checks() -> None:
    """Implementation approval must still precede executable identities."""
    review = _load()
    validation = cast(dict[str, Any], review["required_validation"])

    assert validation["fixture_only"] is True
    assert validation["complete_no_write_preflight"] is True
    assert validation["viewed_scientific_products_opened"] is False
    assert validation["executable_identity_review_created"] is False
    assert validation["cumulative_replay_started"] is False
    assert "old-execution-decision-reuse" in validation["fail_closed_cases"]
    assert "candidate-configuration-drift" in validation["fail_closed_cases"]
    assert (
        "reference-or-runtime-identity-drift"
        in validation["fail_closed_cases"]
    )
