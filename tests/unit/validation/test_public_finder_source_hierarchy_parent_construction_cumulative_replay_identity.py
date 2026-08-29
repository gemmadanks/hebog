"""Contracts for the frozen parent-construction replay identity review."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
from argparse import Namespace
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-cumulative-replay-review.json"
)
_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_source_hierarchy_"
    "parent_construction_cumulative_regressions.py"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-cumulative-replay-execution-decision.json"
)
_IMPLEMENTATION_REVISION = "af7040e477471a94c82745659d36a397fda27cba"
_IMPLEMENTATION_TREE = "158c6f531533ddb563e0b856431f94870843bc8b"


def _load() -> dict[str, Any]:
    """Load the non-executable identity review."""
    document = json.loads(_REVIEW.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return cast(dict[str, Any], document)


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
            "public-finder-source-hierarchy-parent-construction.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-source-hierarchy-"
            "parent-construction-5f2b098"
        ),
        workers=2,
        closed_component_baseline_ledger=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
    )


def _committed_file_sha256(revision: str, path: str) -> str:
    """Hash one exact committed file."""
    value = subprocess.run(
        ("git", "show", f"{revision}:{path}"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(value).hexdigest()


def test_review_freezes_exact_non_executable_composition() -> None:
    """The review binds the candidate, wrapper, programs, and readiness."""
    review = _load()
    implementation = cast(dict[str, Any], review["implementation"])
    wrapper = runpy.run_path(str(_WRAPPER))

    assert implementation["commit"] == _IMPLEMENTATION_REVISION
    assert implementation["tree"] == _IMPLEMENTATION_TREE
    for name in (
        "parent_implementation_decision",
        "parent_pre_review",
        "readiness_contract",
        "root_cause_implementation_decision",
        "root_cause_pre_review",
        "wrapper",
    ):
        record = cast(dict[str, str], implementation[name])
        assert record["sha256"] == _committed_file_sha256(
            _IMPLEMENTATION_REVISION, record["path"]
        )
    for record in cast(
        dict[str, dict[str, str]], implementation["programs"]
    ).values():
        assert record["sha256"] == _committed_file_sha256(
            _IMPLEMENTATION_REVISION, record["path"]
        )
    expected = wrapper["_expected_execution_fields"](_approved_arguments())
    expected["wrapper_sha256"] = implementation["wrapper"]["sha256"]
    assert review["prospective_execution"] == expected


def test_review_records_complete_no_write_result() -> None:
    """All retained references passed without candidate submission."""
    verification = cast(dict[str, Any], _load()["no_write_verification"])

    assert verification["status"] == "pass"
    assert verification["candidate_revision"] == (
        "5f2b09880dc10feb6ffaec50ffcf3c807a093416"
    )
    assert verification["verified_input_count"] == 2400
    assert verification["verified_reference_run_count"] == 9600
    assert verification["cumulative_replay_started"] is False
    assert verification["output_absent"] is True
    assert verification["scratch_absent"] is True
    assert verification["execution_checkout_revision"] == (
        _IMPLEMENTATION_REVISION
    )


def test_review_is_non_executable_and_requires_new_named_approval() -> None:
    """Identity freeze cannot be interpreted as replay authority."""
    review = _load()
    authorization = cast(dict[str, bool], review["authorization"])

    assert authorization
    assert not any(authorization.values())
    assert review["required_next_decision"] == (
        "separate-named-approval-bound-to-this-review-for-one-complete-"
        "cumulative-replay-only"
    )
    assert not _EXECUTION_DECISION.exists()


def test_review_binds_reconstruction_and_closed_baseline() -> None:
    """The retained reference terminal and closed ledger remain exact."""
    review = _load()
    reconstruction = cast(dict[str, Any], review["reconstruction"])
    completion = cast(dict[str, str], reconstruction["completion_review"])
    execution = cast(dict[str, Any], review["prospective_execution"])

    assert file_sha256(_ROOT / completion["path"]) == completion["sha256"]
    assert (
        file_sha256(_ROOT / reconstruction["path"] / "recovery.json")
        == reconstruction["recovery_sha256"]
    )
    assert (
        file_sha256(_ROOT / execution["closed_baseline_path"])
        == execution["closed_baseline_sha256"]
    )
