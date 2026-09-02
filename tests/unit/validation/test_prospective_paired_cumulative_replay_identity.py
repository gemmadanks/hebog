"""Frozen prospective paired replay identity-review tests."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT / "config/contracts/phase-5-prospective-paired-cumulative-replay-"
    "identity-review.json"
)
_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_prospective_paired_cumulative_replay.py"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-paired-cumulative-replay-"
    "execution-decision.json"
)


def _review() -> dict[str, Any]:
    """Load the exact non-executable identity review."""
    return cast(
        dict[str, Any], json.loads(_REVIEW.read_text(encoding="utf-8"))
    )


def _arguments(wrapper: dict[str, Any]) -> argparse.Namespace:
    """Build the exact invocation covered by the identity review."""
    return argparse.Namespace(
        current_root=wrapper["_CURRENT_ROOT"],
        incumbent_root=wrapper["_INCUMBENT_ROOT"],
        reference_reconstruction=wrapper["_REFERENCE_RECONSTRUCTION"],
        current_scratch=wrapper["_CURRENT_SCRATCH"],
        incumbent_scratch=wrapper["_INCUMBENT_SCRATCH"],
        output=wrapper["_OUTPUT"],
        workers=2,
        verify_only=True,
    )


def test_identity_review_binds_exact_programs_and_design() -> None:
    """Every mutable program and frozen design input is checksum-bound."""
    review = _review()
    for program in review["implementation"]["programs"]:
        assert file_sha256(_ROOT / program["path"]) == program["sha256"]
    for name in (
        "decision_contract",
        "endpoint_registry",
        "population",
        "power_audit",
        "tail_sentinels",
    ):
        evidence = review["design"][name]
        assert file_sha256(_ROOT / evidence["path"]) == evidence["sha256"]
    for name in ("approved_pre_review", "implementation_decision"):
        evidence = review["implementation"][name]
        assert file_sha256(_ROOT / evidence["path"]) == evidence["sha256"]


def test_identity_review_matches_the_complete_no_write_invocation() -> None:
    """The future authorization can name only the preflighted command."""
    review = _review()
    wrapper = runpy.run_path(str(_WRAPPER))
    expected = canonical_sha256(
        wrapper["_expected_execution_fields"](_arguments(wrapper))
    )

    assert review["expected_execution_sha256"] == expected
    assert review["no_write_verification"] == {
        "candidate_execution_started": False,
        "comparison_count": 1187,
        "current_task_count": 2400,
        "incumbent_task_count": 2400,
        "input_count": 2400,
        "output_absent": True,
        "reference_run_count": 9600,
        "scratch_absent": True,
        "sentinel_membership_count": 160,
        "sentinel_unique_input_count": 155,
        "status": "pass",
    }

    # The review records the state observed before execution. Runtime products
    # may legitimately exist after the one-use authorization is consumed, so
    # this durable identity test must not reinterpret current filesystem state.
    assert review["no_write_verification"]["scratch_absent"] is True
    assert review["no_write_verification"]["output_absent"] is True


def test_identity_review_is_non_executable_and_scientifically_fixed() -> None:
    """Freezing identities grants no replay or scientific authority."""
    review = _review()

    assert review["status"] == "ready-for-named-one-replay-approval"
    assert not any(review["authorization"].values())
    assert review["candidates"] == {
        "current": {
            "configuration_sha256": (
                "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
            ),
            "revision": "937737d811dd229d71dbcfdbda6cb5829de6faca",
            "source_tree_sha256": (
                "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
            ),
        },
        "selected_incumbent": {
            "configuration_sha256": (
                "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
            ),
            "revision": "85d580713664b962ae256a98b065849cf8eb9283",
            "source_tree_sha256": (
                "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
            ),
        },
    }


def test_execution_decision_consumes_only_the_named_replay_authority() -> None:
    """The new approval authorizes this replay but no adjacent activity."""
    decision = json.loads(_EXECUTION_DECISION.read_text(encoding="utf-8"))

    assert decision["identity_review"] == {
        "path": (
            "config/contracts/phase-5-prospective-paired-cumulative-replay-"
            "identity-review.json"
        ),
        "sha256": file_sha256(_REVIEW),
    }
    assert (
        decision["expected_execution_sha256"]
        == (_review()["expected_execution_sha256"])
    )
    assert decision["execution_authorized"] is True
    assert decision["cumulative_replay_authorized"] is True
    assert decision["evaluation_authorized"] is True
    assert not any(decision["prohibited_authorizations"].values())
