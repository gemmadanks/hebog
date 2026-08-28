"""Contracts for the frozen measurement-repair replay identity review."""

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
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-cumulative-replay-review.json"
)
_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_public_finder_source_association_measurement_repair_"
    "cumulative_regressions.py"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-cumulative-replay-execution-decision.json"
)


def _load() -> dict[str, Any]:
    """Load the replacement non-executable identity review."""
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
            "public-finder-source-association-measurement-repair.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-source-association-"
            "measurement-repair-6184a32"
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
    """The review binds the clean implementation and every replay field."""
    review = _load()
    implementation = cast(dict[str, Any], review["implementation"])
    wrapper = runpy.run_path(str(_WRAPPER))

    assert implementation["commit"] == (
        "9cc00fb339b12fb00695b0799f828a5afba8ee16"
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
    for name in (
        "implementation_decision",
        "pre_review",
        "readiness_contract",
    ):
        record = cast(dict[str, str], implementation[name])
        assert file_sha256(_ROOT / record["path"]) == record["sha256"]
    assert review["prospective_execution"] == wrapper[
        "_expected_execution_fields"
    ](_approved_arguments())

    reconstruction = cast(dict[str, Any], review["reconstruction"])
    completion = cast(dict[str, str], reconstruction["completion_review"])
    assert file_sha256(_ROOT / completion["path"]) == completion["sha256"]
    assert file_sha256(
        _ROOT / reconstruction["path"] / "recovery.json"
    ) == reconstruction["recovery_sha256"]


def test_review_records_complete_no_write_result() -> None:
    """The full retained reference population passed without replay."""
    verification = cast(dict[str, Any], _load()["no_write_verification"])

    assert verification == {
        "candidate_configuration_sha256": (
            "78dbb230cbb726cbbe02b74f2e7fe96bc42801e2102bf15f0580c0643befe946"
        ),
        "candidate_revision": "6184a32648eee637f0aca03ab2ec0249bd0510f0",
        "candidate_source_tree_sha256": (
            "517d56e19a5d58eb386d96bdb181d36afb574ad018222f870cc8434c398044ff"
        ),
        "consumed_wrapper_sha256": (
            "bfc1d6d0d255b9fd7e7b43f910e9c2665d9083de572bce7b64afee66c473f357"
        ),
        "cumulative_replay_started": False,
        "execution_checkout_revision": (
            "9cc00fb339b12fb00695b0799f828a5afba8ee16"
        ),
        "measurement_repair_sha256": (
            "a3c53daac3dbae03bd6b3f62488cd46de541d79d9c6c903d34ce7951334d690b"
        ),
        "output_absent": True,
        "readiness_contract_sha256": (
            "cef14d0130b264ddfc5e4277455820cae5436aa578b0ddb798a103ce9421321f"
        ),
        "reference_reconstruction_sha256": (
            "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
        ),
        "scratch_absent": True,
        "status": "pass",
        "verified_input_count": 2400,
        "verified_reference_run_count": 9600,
    }


def test_review_remains_non_executable_and_requires_named_approval() -> None:
    """Identity freezing opens no replay or later lifecycle authority."""
    review = _load()
    authorization = cast(dict[str, bool], review["authorization"])

    assert authorization
    assert not any(authorization.values())
    assert review["required_next_decision"] == (
        "separate-named-approval-bound-to-this-review-for-one-complete-"
        "cumulative-replay-only"
    )
    assert not _EXECUTION_DECISION.exists()
