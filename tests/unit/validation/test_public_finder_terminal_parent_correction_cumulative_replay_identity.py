"""Contracts for the exact terminal-parent replay identity and authority."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
from argparse import Namespace
from pathlib import Path
from typing import Any, cast

from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_terminal_parent_"
    "correction_cumulative_regressions.py"
)
_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-parent-"
    "correction-cumulative-replay-review.json"
)
_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-parent-"
    "correction-cumulative-replay-execution-decision.json"
)
_COMPOSITION_REVISION = "1e8348baebaf11e26a51f66fb5cfd21e286b4875"
_CANDIDATE_REVISION = "85d580713664b962ae256a98b065849cf8eb9283"
_SOURCE_TREE = (
    "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
)
_CONFIGURATION = (
    "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
)


def _load(path: Path) -> dict[str, Any]:
    """Load one exact JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _approved_arguments() -> Namespace:
    """Return the exact no-write and replay invocation."""
    return Namespace(
        campaign=None,
        reference_reconstruction=Path(
            "benchmark-results/phase-5/"
            "viewed-reference-reconstruction-public-finder-correction"
        ),
        output=Path(
            "benchmark-results/phase-5/cumulative-regression-ledger-"
            "public-finder-terminal-parent-correction.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-terminal-parent-"
            "correction-85d5807"
        ),
        workers=2,
        closed_component_baseline_ledger=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
    )


def _committed_file_sha256(revision: str, path: str) -> str:
    """Hash one exact file from an immutable local commit."""
    value = subprocess.run(
        ("git", "show", f"{revision}:{path}"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(value).hexdigest()


def test_review_freezes_the_exact_committed_composition() -> None:
    """The review binds every executable program and readiness contract."""
    review = _load(_REVIEW)
    implementation = cast(dict[str, Any], review["implementation"])

    assert implementation["composition_commit"] == _COMPOSITION_REVISION
    assert implementation["candidate_boundary_commit"] == _CANDIDATE_REVISION
    for name in (
        "consumed_wrapper",
        "evaluator",
        "implementation_decision",
        "readiness",
        "scientific_review",
        "wrapper",
    ):
        record = cast(dict[str, str], implementation[name])
        assert record["sha256"] == _committed_file_sha256(
            _COMPOSITION_REVISION, record["path"]
        )


def test_review_records_the_complete_no_write_result() -> None:
    """All retained evidence and both executable seams passed before replay."""
    review = _load(_REVIEW)
    verification = cast(dict[str, Any], review["no_write_verification"])

    assert verification["status"] == "pass"
    assert verification["candidate_revision"] == _CANDIDATE_REVISION
    assert verification["candidate_source_tree_sha256"] == _SOURCE_TREE
    assert verification["candidate_configuration_sha256"] == _CONFIGURATION
    assert verification["verified_input_count"] == 2400
    assert verification["verified_reference_run_count"] == 9600
    assert verification["association_sidecar_persistence_verified"] is True
    assert (
        verification["sidecar_aware_evaluator_installation_verified"] is True
    )
    assert verification["cumulative_replay_started"] is False
    assert verification["output_absent"] is True
    assert verification["scratch_absent"] is True


def test_review_is_non_executable() -> None:
    """The identity review alone cannot open any scientific execution."""
    review = _load(_REVIEW)
    authorization = cast(dict[str, bool], review["authorization"])

    assert authorization
    assert not any(authorization.values())
    assert review["status"] == (
        "reviewed-before-terminal-parent-cumulative-replay"
    )


def test_exact_decision_opens_only_the_frozen_replay() -> None:
    """The user's authority is bound to one canonical execution identity."""
    wrapper = runpy.run_path(str(_WRAPPER))
    review = _load(_REVIEW)
    decision = _load(_DECISION)
    expected = canonical_sha256(
        wrapper["_expected_execution_fields"](_approved_arguments())
    )

    assert review["expected_execution_sha256"] == expected
    assert decision["expected_execution_sha256"] == expected
    assert decision["execution_authorized"] is True
    assert decision["cumulative_replay_authorized"] is True
    assert decision["identity_review"] == {
        "path": str(_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_REVIEW),
    }
    assert decision["prohibited_authorizations"] == dict.fromkeys(
        wrapper["_PROHIBITED_AUTHORIZATIONS"], False
    )
    assert not any(
        cast(dict[str, bool], decision["prohibited_authorizations"]).values()
    )
    assert review["authorization"]["cumulative_replay_authorized"] is False


def test_review_and_decision_bind_retained_evidence_and_namespaces() -> None:
    """Reference, baseline, population, workers, and paths remain exact."""
    review = _load(_REVIEW)
    decision = _load(_DECISION)
    arguments = _approved_arguments()

    assert review["candidate"] == {
        "configuration_sha256": _CONFIGURATION,
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _SOURCE_TREE,
    }
    assert decision["candidate_revision"] == _CANDIDATE_REVISION
    assert decision["candidate_source_tree_sha256"] == _SOURCE_TREE
    assert decision["candidate_configuration_sha256"] == _CONFIGURATION
    for document in (review, decision):
        assert document["reference_reconstruction_sha256"] == (
            "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
        )
        assert document["closed_baseline_sha256"] == (
            "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
        )
        assert document["output_path"] == str(arguments.output)
        assert document["scratch_path"] == str(arguments.scratch)
        assert document["workers"] == 2
