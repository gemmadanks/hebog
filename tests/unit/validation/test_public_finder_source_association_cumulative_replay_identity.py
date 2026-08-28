"""Contracts for the frozen source-association replay identity review."""

from __future__ import annotations

import json
import runpy
import subprocess
from argparse import Namespace
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-source-association-cumulative-"
    "replay-review.json"
)
_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_public_finder_source_association_cumulative_regressions.py"
)
_EXECUTION_DECISION = (
    _ROOT
    / "config/contracts/phase-5-public-finder-source-association-cumulative-"
    "replay-execution-decision.json"
)


def _load() -> dict[str, Any]:
    """Load the replacement identity review."""
    value = json.loads(_REVIEW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _approved_arguments() -> Namespace:
    """Return the exact prospective no-write and replay invocation."""
    return Namespace(
        campaign=None,
        reference_reconstruction=Path(
            "benchmark-results/phase-5/"
            "viewed-reference-reconstruction-public-finder-correction"
        ),
        output=Path(
            "benchmark-results/phase-5/cumulative-regression-ledger-"
            "public-finder-source-association.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-source-association-"
            "26e639a"
        ),
        workers=2,
        closed_component_baseline_ledger=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
    )


def test_review_freezes_exact_implementation_and_prospective_execution() -> (
    None
):
    """The review binds the immutable implementation and every replay field."""
    review = _load()
    implementation = cast(dict[str, Any], review["implementation"])
    wrapper = runpy.run_path(str(_WRAPPER))

    assert implementation["commit"] == (
        "1b511ed3aa2024855e931889b46643bd4f142c63"
    )
    tree = subprocess.check_output(
        ("git", "rev-parse", f"{implementation['commit']}^{{tree}}"),
        cwd=_ROOT,
        text=True,
    ).strip()
    assert tree == implementation["tree"]
    assert implementation["wrapper"] == {
        "path": str(_WRAPPER.relative_to(_ROOT)),
        "sha256": file_sha256(_WRAPPER),
    }
    assert review["prospective_execution"] == wrapper[
        "_expected_execution_fields"
    ](_approved_arguments())


def test_review_records_complete_no_write_result() -> None:
    """The full retained reference population passed without replay."""
    review = _load()
    verification = cast(dict[str, Any], review["no_write_verification"])

    assert verification == {
        "candidate_consumer_source_tree_sha256": (
            "34fecf302e7c6a9722dd15b8d843d316a4e4e7a1be3df2610a2d45b0a5dfb893"
        ),
        "execution_checkout_revision": (
            "1b511ed3aa2024855e931889b46643bd4f142c63"
        ),
        "output_absent": True,
        "reference_producer_source_tree_sha256": (
            "b4176ce387fa1569cc86ca300bfa7de6462758a1068de46cd4a16616a6ec3adc"
        ),
        "reference_reconstruction_sha256": (
            "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
        ),
        "scratch_absent": True,
        "status": "pass",
        "verified_input_count": 2400,
        "verified_reference_run_count": 9600,
    }
    assert verification["output_absent"] is True
    assert verification["scratch_absent"] is True


def test_review_remains_non_executable_and_requires_named_approval() -> None:
    """Identity freezing opens no execution or later lifecycle authority."""
    review = _load()
    authorization = cast(dict[str, bool], review["authorization"])

    assert authorization
    assert not any(authorization.values())
    assert review["required_next_decision"] == (
        "separate-named-approval-bound-to-this-review-for-one-complete-"
        "cumulative-replay-only"
    )


def test_execution_decision_binds_exact_review_and_replay_boundary() -> None:
    """The named approval opens one exact replay and nothing later."""
    wrapper = runpy.run_path(str(_WRAPPER))
    decision = json.loads(_EXECUTION_DECISION.read_text(encoding="utf-8"))
    arguments = _approved_arguments()

    wrapper["_validate_execution_decision"](decision, arguments)
    assert decision["source_association_replay_identity_review"] == {
        "path": str(_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_REVIEW),
    }
    assert decision["execution_authorized"] is True
    assert decision["cumulative_replay_authorized"] is True
    assert decision["prohibited_authorizations"] == dict.fromkeys(
        wrapper["_PROHIBITED_AUTHORIZATIONS"], False
    )
    prospective = _load()["prospective_execution"]
    for field, expected in prospective.items():
        assert decision[field] == expected
