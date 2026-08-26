"""Fail-closed boundary for rebuilding deleted reference evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_FAILURE = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-reference-evidence-"
    "availability-failure.json"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-correction-reference-"
    "reconstruction-pre-review.json"
)


def _load(path: Path) -> dict[str, Any]:
    """Load one compact governance record."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_missing_reference_evidence_fails_without_science_or_output() -> None:
    """Approved cleanup must be represented as a non-scientific stop."""
    failure = _load(_FAILURE)

    assert failure["status"] == (
        "blocked-by-approved-reference-evidence-cleanup"
    )
    assert set(failure["authorization"].values()) == {False}
    assert failure["scientific_outcome"] == {
        "candidate_products_created": 0,
        "reference_products_verified": 0,
        "result_available": False,
    }
    preserved = failure["preserved_evidence"]
    assert preserved["cleanup_commit"] == (
        "fe92da13677e782341a1eb643c45ffdcae046287"
    )
    for name in (
        "progress",
        "recovery",
        "recovery_open_state",
        "recovery_request",
    ):
        record = preserved[name]
        assert file_sha256(_ROOT / record["path"]) == record["sha256"]
    reconstruction = (
        _ROOT / "benchmark-results/phase-5/viewed-reference-reconstruction"
    )
    assert not (reconstruction / "inputs").exists()
    assert not (reconstruction / "results").exists()
    replay = failure["replay_state"]
    assert replay["output_absent"] is True
    assert not (_ROOT / replay["output_path"]).exists()
    assert replay["prospective_scratch_absent"] is True
    assert not Path(replay["prospective_scratch_path"]).exists()


def test_pre_review_binds_historical_producer_and_no_action() -> None:
    """The recovery proposal is exact but grants no execution authority."""
    review = _load(_PRE_REVIEW)

    assert review["status"] == (
        "pre-reviewed-awaiting-reference-reconstruction-approval"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["review_basis"] == {
        "path": str(_FAILURE.relative_to(_ROOT)),
        "sha256": file_sha256(_FAILURE),
    }
    historical = review["historical_reconstruction"]
    commit = historical["execution_checkout_revision"]
    tree = subprocess.check_output(
        ("git", "show", "-s", "--format=%T", commit),
        cwd=_ROOT,
        text=True,
    ).strip()
    assert tree == historical["execution_checkout_tree"]
    program = historical["program"]
    content = subprocess.check_output(
        ("git", "show", f"{commit}:{program['path']}"),
        cwd=_ROOT,
    )
    assert hashlib.sha256(content).hexdigest() == program["sha256"]
    for name in ("retained_execution_decision", "retained_request"):
        record = historical[name]
        assert file_sha256(_ROOT / record["path"]) == record["sha256"]
    terminal = historical["retained_terminal"]
    assert file_sha256(_ROOT / terminal["path"]) == terminal["sha256"]
    request = _load(_ROOT / historical["retained_request"]["path"])
    assert len(request["images"]) == 4
    assert historical["candidate_runs"] == 0
    assert historical["input_count"] == 2400
    assert historical["reference_run_count"] == 9600


def test_reconstruction_uses_new_write_once_namespace() -> None:
    """A future recovery cannot overwrite the preserved historical seal."""
    review = _load(_PRE_REVIEW)
    prospective = review["prospective_reconstruction"]
    historical = review["historical_reconstruction"]

    assert review["preconditions"]["minimum_host_available_gib"] == 120
    assert review["preconditions"]["new_write_once_output_required"] is True
    assert prospective["write_once"] is True
    assert prospective["output_path"] != str(
        Path(historical["retained_terminal"]["path"]).parent
    )
    assert not (_ROOT / prospective["output_path"]).exists()
    assert not (_ROOT / prospective["staging_path"]).exists()
