"""Identity boundary for the fixture-only public-finder correction."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[3]
_REVIEW_COMMIT = "c3e76a71e1af5f01700fe015705fcc9d2e6352eb"
_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-identity-review.json"
)


def _load_review() -> dict[str, Any]:
    """Load the static non-executable identity review."""
    return json.loads(_REVIEW.read_text(encoding="utf-8"))


def _committed_bytes(path: str) -> bytes:
    """Read one identity from the exact frozen review revision."""
    return subprocess.run(
        ("git", "show", f"{_REVIEW_COMMIT}:{path}"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout


def _committed_sha256(path: str) -> str:
    """Hash one identity from the exact frozen review revision."""
    return hashlib.sha256(_committed_bytes(path)).hexdigest()


def test_public_correction_identity_review_is_non_executable() -> None:
    """The review freezes a candidate but authorizes no science execution."""
    review = _load_review()

    assert review["status"] == "ready-for-named-cumulative-replay-approval"
    assert set(review["authorization"].values()) == {False}  # type: ignore[union-attr]
    assert set(review["scientific_boundary"].values()) == {False}  # type: ignore[union-attr]
    assert review["required_next_decision"] == (
        "separate-named-approval-bound-to-this-review-for-one-complete-"
        "cumulative-replay-only"
    )
    viewed = review["viewed_development_boundary"]
    assert isinstance(viewed, dict)
    assert viewed["executable_protocol_frozen"] is False
    assert viewed["status"] == "viewed-development-execution-remains-closed"


def test_public_correction_identity_review_binds_exact_candidate() -> None:
    """The candidate and unchanged base configuration are unambiguous."""
    review = _load_review()
    candidate = review["candidate"]
    base = review["base_candidate"]
    assert isinstance(candidate, dict)
    assert isinstance(base, dict)

    assert candidate["commit"] == ("b1d59e5aaf778a5fed4ea662afeba2ee100424ff")
    assert candidate["tree"] == "4e16d9a03f971cd37e8b96f94e65cb3afa935f98"
    assert candidate["source_tree_sha256"] == (
        "2de6564e78f1a3664dd3fb18f696c747bfc3350fdd894164c4fafb07528d1ba9"
    )
    assert candidate["configuration_sha256"] == (base["configuration_sha256"])


def test_public_correction_identity_review_links_immutable_records() -> None:
    """Reviewed contracts and historical seams remain byte exact."""
    review = _load_review()
    candidate = review["candidate"]
    regression = review["closed_regression_boundary"]
    viewed = review["viewed_development_boundary"]
    assert isinstance(candidate, dict)
    assert isinstance(regression, dict)
    assert isinstance(viewed, dict)

    identities: list[dict[str, str]] = [
        cast(dict[str, str], candidate["pre_review"]),
        cast(dict[str, str], candidate["implementation_decision"]),
        cast(dict[str, str], candidate["correction_contract"]),
        cast(dict[str, str], regression["program"]),
        cast(dict[str, str], viewed["prior_scientific_review"]),
    ]
    identities.extend(
        cast(list[dict[str, str]], review["historical_invariants"])
    )
    for identity in identities:
        assert isinstance(identity, dict)
        assert _committed_sha256(identity["path"]) == identity["sha256"]

    pre_review_identity = cast(dict[str, str], candidate["pre_review"])
    pre_review = json.loads(_committed_bytes(pre_review_identity["path"]))
    assert (
        regression["baseline"]
        == (  # type: ignore[index]
            pre_review["binding_evidence"]["cumulative_regression_baseline"]
        )
    )
    assert (
        viewed["selected_population"]["sha256"]
        == (  # type: ignore[index]
            pre_review["binding_evidence"]["selected_public_population_sha256"]
        )
    )


def test_public_correction_identity_review_records_absent_outputs() -> None:
    """No replay or corrected viewed product existed at review time."""
    review = _load_review()
    regression = review["closed_regression_boundary"]
    viewed = review["viewed_development_boundary"]
    assert isinstance(regression, dict)
    assert isinstance(viewed, dict)

    assert regression["expected_output"]["state_at_review"] == "absent"  # type: ignore[index]
    for key in (
        "corrected_campaign",
        "corrected_analysis",
        "corrected_decision",
    ):
        assert viewed[key]["state_at_review"] == "absent"  # type: ignore[index]
