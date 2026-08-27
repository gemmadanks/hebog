"""Non-executable identity boundary for public source association."""

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
_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "identity-review.json"
)


def _load() -> dict[str, Any]:
    """Load the exact static identity review."""
    return json.loads(_REVIEW.read_text(encoding="utf-8"))


def test_identity_review_freezes_candidate_without_execution() -> None:
    """The review binds one candidate and leaves every execution closed."""
    review = _load()
    candidate = cast(dict[str, Any], review["candidate"])

    assert review["schema_version"] == 1
    assert review["status"] == (
        "ready-for-separate-replay-composition-pre-review"
    )
    assert set(review["authorization"].values()) == {False}  # type: ignore[union-attr]
    assert candidate == {
        "commit": "26e639ace9d39b039eb7c3114427277c91809591",
        "configuration_sha256": (
            "78dbb230cbb726cbbe02b74f2e7fe96bc42801e2102bf15f0580c0643befe946"
        ),
        "implementation_decision": {
            "path": (
                "config/contracts/phase-5-public-finder-source-association-"
                "implementation-decision.json"
            ),
            "sha256": (
                "6a495cfcb54ec01e5a7290b6c28edf7b7fffe89f88318c5b6f3e135e70a15553"
            ),
        },
        "pre_review": {
            "path": (
                "config/contracts/phase-5-public-finder-source-association-"
                "pre-review.json"
            ),
            "sha256": (
                "9af42348896e0449e007fe2318648f66122313d600137f8f5ec525ebaec1cc3c"
            ),
        },
        "source_tree_sha256": (
            "34fecf302e7c6a9722dd15b8d843d316a4e4e7a1be3df2610a2d45b0a5dfb893"
        ),
        "tree": "251c44c0435e8cade4423a22e2fd5ab755bcbdce",
    }


def test_identity_review_binds_live_source_configuration_and_files() -> None:
    """Source, configuration, implementation, and fixtures are byte exact."""
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

    assert source_tree_sha256(_ROOT) == candidate["source_tree_sha256"]
    assert canonical_sha256(configuration) == candidate["configuration_sha256"]
    identities = [
        candidate["pre_review"],
        candidate["implementation_decision"],
        *review["candidate_artifacts"],
        *review["historical_invariants"],
        *review["validation_artifacts"],
    ]
    for identity in identities:
        assert file_sha256(_ROOT / identity["path"]) == identity["sha256"]


def test_identity_review_records_closed_science_and_incompatible_wrapper() -> (
    None
):
    """A prior failed replay cannot authorize this changed candidate."""
    review = _load()
    candidate = cast(dict[str, Any], review["candidate"])
    regression = cast(dict[str, Any], review["closed_regression_boundary"])
    replay = cast(dict[str, Any], review["replay_boundary"])
    wrapper = cast(dict[str, Any], replay["current_wrapper"])

    assert regression["failed_correction"]["sha256"] == (
        "1ac6deb24e4bfc1928318c95437d45acac6ac1f94621b53d45175e0f41bd9797"
    )
    assert regression["baseline"]["sha256"] == (
        "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
    )
    assert wrapper["bound_revision"] != candidate["commit"]
    assert (
        wrapper["bound_source_tree_sha256"] != candidate["source_tree_sha256"]
    )
    assert (
        wrapper["bound_configuration_sha256"]
        != (candidate["configuration_sha256"])
    )
    assert replay["executable_composition_frozen"] is False
    assert not (_ROOT / replay["candidate_output"]["path"]).exists()


def test_identity_review_preserves_scientific_and_viewed_boundaries() -> None:
    """Identity freezing makes no new scientific or public-data claim."""
    review = _load()

    assert set(review["scientific_boundary"].values()) == {False}  # type: ignore[union-attr]
    viewed = cast(dict[str, Any], review["viewed_development_boundary"])
    assert viewed["executable_protocol_frozen"] is False
    assert viewed["status"] == "viewed-development-execution-remains-closed"
    for name in (
        "corrected_campaign",
        "corrected_analysis",
        "corrected_decision",
    ):
        assert viewed[name]["state_at_review"] == "absent"
