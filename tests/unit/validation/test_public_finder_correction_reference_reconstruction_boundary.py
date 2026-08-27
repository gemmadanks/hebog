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
_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-correction-reference-"
    "reconstruction-decision.json"
)
_PREFLIGHT = (
    _ROOT / "config/contracts/phase-5-public-finder-correction-reference-"
    "reconstruction-preflight.json"
)
_COMPLETION_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-correction-reference-"
    "reconstruction-review.json"
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
    assert replay["prospective_scratch_absent"] is True


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


def test_reconstruction_used_the_new_write_once_namespace() -> None:
    """The completed recovery did not overwrite the historical seal."""
    review = _load(_PRE_REVIEW)
    prospective = review["prospective_reconstruction"]
    historical = review["historical_reconstruction"]

    assert review["preconditions"]["minimum_host_available_gib"] == 120
    assert review["preconditions"]["new_write_once_output_required"] is True
    assert prospective["write_once"] is True
    assert prospective["output_path"] != str(
        Path(historical["retained_terminal"]["path"]).parent
    )
    assert (_ROOT / prospective["output_path"] / "recovery.json").is_file()
    assert not (_ROOT / prospective["staging_path"]).exists()


def test_named_approval_authorizes_only_one_reference_reconstruction() -> None:
    """The exact approval opens no replay or later lifecycle action."""
    decision = _load(_DECISION)

    assert decision["status"] == (
        "approved-before-reference-reconstruction-preflight"
    )
    assert decision["pre_review"] == {
        "path": str(_PRE_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_PRE_REVIEW),
    }
    authorization = decision["authorization"]
    assert authorization["complete_no_write_preflight_authorized"] is True
    assert authorization["reference_reconstruction_authorized"] is True
    assert {
        value
        for key, value in authorization.items()
        if key
        not in {
            "complete_no_write_preflight_authorized",
            "reference_reconstruction_authorized",
        }
    } == {False}
    assert decision["preconditions"] == {
        "complete_no_write_preflight_required": True,
        "identities_must_remain_exact": True,
        "maximum_reconstruction_executions": 1,
        "minimum_host_available_gib": 120,
        "output_and_staging_must_be_absent": True,
    }


def test_named_approval_binds_historical_program_population_and_runtimes() -> (
    None
):
    """Every approved reconstruction identity matches retained evidence."""
    decision = _load(_DECISION)
    producer = decision["historical_producer"]

    assert producer["decision"]["sha256"] == file_sha256(
        _ROOT / producer["decision"]["path"]
    )
    content = subprocess.check_output(
        (
            "git",
            "show",
            f"{producer['commit']}:{producer['program']['path']}",
        ),
        cwd=_ROOT,
    )
    assert hashlib.sha256(content).hexdigest() == producer["program"]["sha256"]
    assert decision["population"] == {
        "candidate_run_count": 0,
        "input_count": 2400,
        "reference_run_count": 9600,
        "retained_request": {
            "path": (
                "benchmark-results/phase-5/viewed-reference-reconstruction/"
                "recovery-request.json"
            ),
            "sha256": file_sha256(
                _ROOT
                / "benchmark-results/phase-5/viewed-reference-reconstruction/"
                "recovery-request.json"
            ),
        },
    }
    retained = _load(
        _ROOT / decision["population"]["retained_request"]["path"]
    )["images"]
    approved = {
        item["finder_id"]: item for item in decision["runtime_identities"]
    }
    assert set(approved) == set(retained)
    for finder_id, runtime in retained.items():
        assert approved[finder_id]["image"] == runtime["image"]
        assert approved[finder_id]["image_id"] == runtime["image_id"]
        assert approved[finder_id]["digest"] == runtime["digest"]


def test_completed_reconstruction_is_terminal_and_write_once() -> None:
    """The consumed approval has one sealed output and no staging state."""
    execution = _load(_DECISION)["prospective_execution"]

    terminal = _ROOT / execution["output_path"] / "recovery.json"
    assert terminal.is_file()
    assert not (_ROOT / execution["staging_path"]).exists()


def test_completion_review_binds_the_verified_terminal() -> None:
    """The replay consumer can bind only the completely verified recovery."""
    review = _load(_COMPLETION_REVIEW)

    assert review["status"] == "verified-reference-reconstruction-terminal"
    assert set(review["authorization"].values()) == {False}
    assert review["approved_reconstruction"] == {
        "decision": {
            "path": str(_DECISION.relative_to(_ROOT)),
            "sha256": file_sha256(_DECISION),
        },
        "maximum_executions": 1,
    }
    terminal = review["terminal"]
    root = _ROOT / terminal["path"]
    assert file_sha256(root / "recovery.json") == terminal["recovery_sha256"]
    assert (
        file_sha256(root / "recovery-request.json")
        == (terminal["request_sha256"])
    )
    assert review["verification"]["verified_input_count"] == 2400
    assert review["verification"]["verified_reference_run_count"] == 9600
    assert review["verification"]["candidate_runs_executed"] == 0
    assert review["verification"]["terminal_identity_exact"] is True
    assert review["replay_state"]["cumulative_replay_authorized"] is False


def test_preflight_stops_before_execution_when_storage_is_insufficient() -> (
    None
):
    """A failed storage gate leaves the single execution unconsumed."""
    preflight = _load(_PREFLIGHT)

    assert preflight["status"] == "blocked-insufficient-host-storage"
    assert preflight["authorization_decision"] == {
        "path": str(_DECISION.relative_to(_ROOT)),
        "sha256": file_sha256(_DECISION),
    }
    assert preflight["preflight_checks"] == {
        "clean_historical_checkout": True,
        "decision_identity_exact": True,
        "host_storage_passed": False,
        "output_and_staging_absent": True,
        "population_identity_exact": True,
        "program_identity_exact": True,
        "runtime_image_count": 4,
        "runtime_images_exact": True,
    }
    state = preflight["execution_state"]
    assert state["authorized_execution_consumed"] is False
    assert state["input_materializations_started"] == 0
    assert state["reference_runs_started"] == 0
    assert state["candidate_runs_started"] == 0
    assert state["output_absent"] is True
    assert state["staging_absent"] is True
    assert state["output_absent"] is True
    assert state["staging_absent"] is True
    assert (
        preflight["storage"]["observed_available_gib"]
        < (preflight["storage"]["minimum_available_gib"])
    )
    assert set(preflight["authorization"].values()) == {False}
