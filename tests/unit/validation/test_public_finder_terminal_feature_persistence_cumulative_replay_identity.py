"""Exact non-executable terminal-feature replay identity contracts."""

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
    _ROOT / "scripts/validation/review_phase5_public_finder_terminal_feature_"
    "persistence_cumulative_regressions.py"
)
_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-feature-"
    "persistence-cumulative-replay-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-feature-"
    "persistence-cumulative-replay-execution-decision.json"
)
_COMPOSITION_REVISION = "7a5cd54b403c13eaa70bb57d3d1684966122e928"
_CANDIDATE_REVISION = "3d080f78da09ada6753a4e5df898e1d5daa59597"
_SOURCE_TREE = (
    "a25d22d80f4e639e4543ee058acade6feda15105f6325dc909e69fcfb8f03924"
)
_CONFIGURATION = (
    "2d6ab6bbdd06f109f9703fb0b49f489933ddc00b391f681253693b38d0f4b1de"
)


def _load(path: Path) -> dict[str, Any]:
    """Load one exact JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _arguments() -> Namespace:
    """Return the exact future no-write and replay invocation."""
    return Namespace(
        campaign=None,
        reference_reconstruction=Path(
            "benchmark-results/phase-5/"
            "viewed-reference-reconstruction-public-finder-correction"
        ),
        output=Path(
            "benchmark-results/phase-5/cumulative-regression-ledger-"
            "public-finder-terminal-feature-persistence.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-terminal-feature-"
            "persistence-3d080f7"
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


def test_review_freezes_exact_committed_composition() -> None:
    """Every source, wrapper, evaluator, and readiness byte is bound."""
    review = _load(_REVIEW)
    implementation = cast(dict[str, Any], review["implementation"])

    assert implementation["composition_commit"] == _COMPOSITION_REVISION
    assert implementation["candidate_boundary_commit"] == (_CANDIDATE_REVISION)
    for name in (
        "candidate_program",
        "consumed_wrapper",
        "evaluator",
        "implementation_decision",
        "pre_review",
        "readiness",
        "wrapper",
    ):
        record = cast(dict[str, str], implementation[name])
        assert record["sha256"] == _committed_file_sha256(
            _COMPOSITION_REVISION, record["path"]
        )


def test_review_records_complete_no_write_result() -> None:
    """All retained evidence and prospective seams passed before freeze."""
    review = _load(_REVIEW)
    verification = cast(dict[str, Any], review["no_write_verification"])

    assert verification["status"] == "pass"
    assert verification["candidate_revision"] == _CANDIDATE_REVISION
    assert verification["candidate_source_tree_sha256"] == _SOURCE_TREE
    assert verification["candidate_configuration_sha256"] == _CONFIGURATION
    assert verification["verified_input_count"] == 2400
    assert verification["verified_reference_run_count"] == 9600
    assert verification["cumulative_replay_started"] is False
    assert verification["output_absent"] is True
    assert verification["scratch_absent"] is True
    for field in (
        "terminal_persistence_census_aggregation_verified",
        "terminal_persistence_evaluator_installation_verified",
        "terminal_persistence_sidecar_validation_verified",
    ):
        assert verification[field] is True


def test_review_binds_future_canonical_execution_identity() -> None:
    """A later decision must name every exact frozen execution field."""
    wrapper = runpy.run_path(str(_WRAPPER))
    review = _load(_REVIEW)

    expected = canonical_sha256(
        wrapper["_expected_execution_fields"](_arguments())
    )
    assert review["expected_execution_sha256"] == expected
    assert review["candidate"] == {
        "configuration_sha256": _CONFIGURATION,
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _SOURCE_TREE,
    }


def test_review_stays_non_executable_while_exact_decision_opens_replay() -> (
    None
):
    """Only the separately approved decision opens the exact replay."""
    wrapper = runpy.run_path(str(_WRAPPER))
    review = _load(_REVIEW)
    decision = _load(_EXECUTION_DECISION)
    authorization = cast(dict[str, bool], review["authorization"])
    expected = canonical_sha256(
        wrapper["_expected_execution_fields"](_arguments())
    )

    assert authorization
    assert not any(authorization.values())
    assert review["status"] == (
        "reviewed-before-terminal-feature-persistence-cumulative-replay"
    )
    assert decision["expected_execution_sha256"] == expected
    assert decision["execution_authorized"] is True
    assert decision["cumulative_replay_authorized"] is True
    assert decision["evaluation_authorized"] is True
    assert decision["process_bug_retries_authorized"] is True
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
