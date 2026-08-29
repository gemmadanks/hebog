"""Contracts for the frozen source-reconstruction replay identity review."""

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
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "cumulative-replay-review.json"
)
_WRAPPER = (
    _ROOT
    / "scripts/validation/review_phase5_public_finder_source_reconstruction_"
    "cumulative_regressions.py"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "cumulative-replay-execution-decision.json"
)
_IMPLEMENTATION_REVISION = "6d0cceb4bfadad6a5e9b37df21410f4bfc902aa6"


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
            "public-finder-source-reconstruction.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-source-reconstruction-"
            "42c75f4"
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
    """The review binds every implementation and replay identity."""
    review = _load()
    implementation = cast(dict[str, Any], review["implementation"])
    wrapper = runpy.run_path(str(_WRAPPER))

    assert implementation["commit"] == _IMPLEMENTATION_REVISION
    assert (
        implementation["tree"]
        == subprocess.check_output(
            ("git", "rev-parse", f"{_IMPLEMENTATION_REVISION}^{{tree}}"),
            cwd=_ROOT,
            text=True,
        ).strip()
    )
    for name in (
        "implementation_decision",
        "pre_review",
        "readiness_contract",
    ):
        record = cast(dict[str, str], implementation[name])
        assert record["sha256"] == _committed_file_sha256(
            _IMPLEMENTATION_REVISION,
            record["path"],
        )
    wrapper_record = cast(dict[str, str], implementation["wrapper"])
    assert wrapper_record["sha256"] == _committed_file_sha256(
        _IMPLEMENTATION_REVISION,
        wrapper_record["path"],
    )
    for record in cast(
        dict[str, dict[str, str]], implementation["programs"]
    ).values():
        assert record["sha256"] == _committed_file_sha256(
            _IMPLEMENTATION_REVISION,
            record["path"],
        )
    expected = wrapper["_expected_execution_fields"](_approved_arguments())
    expected["wrapper_sha256"] = wrapper_record["sha256"]
    assert review["prospective_execution"] == expected


def test_review_records_complete_no_write_result() -> None:
    """All retained references passed without candidate submission."""
    verification = cast(dict[str, Any], _load()["no_write_verification"])

    assert verification == {
        "candidate_configuration_sha256": (
            "470e918db1a640d7393edc02de01fc57b50881b908bd6d5dac18a57709117bbb"
        ),
        "candidate_revision": "42c75f44b71800ae5fa1e0ebe1669caa7da59f85",
        "candidate_source_tree_sha256": (
            "1b67c7f6f768d6f83becc853a1ebd45b3996164cd2b87fdc0f71b9a3299e6bf1"
        ),
        "consumed_wrapper_sha256": (
            "79e8252cd06cca4959b794af231b6078c80a34f996ff5184ed7c8f4994029084"
        ),
        "cumulative_replay_started": False,
        "execution_checkout_revision": _IMPLEMENTATION_REVISION,
        "output_absent": True,
        "readiness_sha256": (
            "c70c4c32fab67b0e95958ca0628201ae52139aaa55343a78e9172cf762d47e43"
        ),
        "reference_reconstruction_sha256": (
            "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
        ),
        "scratch_absent": True,
        "status": "pass",
        "verified_input_count": 2400,
        "verified_reference_run_count": 9600,
    }


def test_named_approval_opens_only_the_exact_frozen_replay() -> None:
    """The new decision binds the review without opening later actions."""
    review = _load()
    authorization = cast(dict[str, bool], review["authorization"])

    assert authorization
    assert not any(authorization.values())
    assert review["required_next_decision"] == (
        "separate-named-approval-bound-to-this-review-for-one-complete-"
        "cumulative-replay-only"
    )
    wrapper = runpy.run_path(str(_WRAPPER))
    decision_value = json.loads(
        _EXECUTION_DECISION.read_text(encoding="utf-8")
    )
    assert isinstance(decision_value, dict)
    decision = cast(dict[str, Any], decision_value)
    assert decision["execution_authorized"] is True
    assert decision["cumulative_replay_authorized"] is True
    expected_fields = wrapper["_expected_execution_fields"](
        _approved_arguments()
    )
    expected_fields["wrapper_sha256"] = cast(
        dict[str, Any],
        review["prospective_execution"],
    )["wrapper_sha256"]
    for field, expected in expected_fields.items():
        assert decision[field] == expected
    assert decision["source_reconstruction_replay_identity_review"] == {
        "path": str(_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_REVIEW),
    }
    assert decision["prohibited_authorizations"] == dict.fromkeys(
        wrapper["_PROHIBITED_AUTHORIZATIONS"],
        False,
    )


def test_review_binds_reconstruction_and_closed_baseline() -> None:
    """The retained references and closed ledger remain exact inputs."""
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
        == (execution["closed_baseline_sha256"])
    )
