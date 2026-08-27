"""Contracts for the replacement correction replay identity freeze."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "repair-review.json"
)
_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_public_finder_correction_cumulative_regressions.py"
)
_EXECUTION_DECISION = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "execution-decision.json"
)
_EXECUTION_FAILURE = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "execution-failure.json"
)
_REFERENCE_REPAIR_PRE_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "reference-provenance-repair-pre-review.json"
)


def _load() -> dict[str, Any]:
    """Load the non-executable replacement review."""
    return json.loads(_REVIEW.read_text(encoding="utf-8"))


def test_replacement_review_is_exact_and_non_executable() -> None:
    """The identity freeze grants no replay or later lifecycle action."""
    review = _load()

    assert review["status"] == (
        "ready-for-named-public-finder-correction-cumulative-replay-approval"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "separate-named-approval-bound-to-this-review-for-one-complete-"
        "cumulative-replay-only"
    )
    assert review["rejected_composition"]["transferable_to_repair"] is False
    assert (
        review["population"]["viewed_public_products_opened_during_freeze"]
        is False
    )


def test_replacement_review_binds_live_programs_and_evidence() -> None:
    """Every unchanged program is live and changed artifacts remain in Git."""
    review = _load()
    records = [
        review["candidate"]["correction_contract"],
        review["closed_boundary"]["baseline"],
        review["dependency_runtime"]["uv_lock"],
        review["implementation"]["decision"],
        review["implementation"]["pre_review"],
        review["population"]["original_request"],
        *review["programs_and_contracts"].values(),
        review["rejected_composition"]["decision"],
        review["rejected_composition"]["identity_review"],
    ]
    for value in records:
        record = cast(dict[str, str], value)
        assert file_sha256(_ROOT / record["path"]) == record["sha256"]
    for name in ("wrapper", "wrapper_tests"):
        record = review["implementation"][name]
        content = subprocess.check_output(
            (
                "git",
                "show",
                f"{review['implementation']['commit']}:{record['path']}",
            ),
            cwd=_ROOT,
        )
        assert hashlib.sha256(content).hexdigest() == record["sha256"]
    recovery = review["population"]["reference_reconstruction"]
    assert (
        file_sha256(_ROOT / recovery["path"] / "recovery.json")
        == (recovery["recovery_sha256"])
    )
    implementation = review["implementation"]
    tree = subprocess.check_output(
        ("git", "rev-parse", f"{implementation['commit']}^{{tree}}"),
        cwd=_ROOT,
        text=True,
    ).strip()
    assert tree == implementation["tree"]


def test_replacement_review_is_the_predecessor_failed_composition() -> None:
    """The superseded review stays bound to its consumed failed execution."""
    review = _load()
    failure = json.loads(_EXECUTION_FAILURE.read_text(encoding="utf-8"))

    assert failure["bound_execution"]["repair_identity_review"]["sha256"] == (
        file_sha256(_REVIEW)
    )
    assert (
        failure["bound_execution"]["wrapper"]["sha256"]
        == review["implementation"]["wrapper"]["sha256"]
    )


def test_named_approval_is_bound_to_the_consumed_failed_composition() -> None:
    """The prior exact approval remains immutable and non-transferable."""
    decision = json.loads(_EXECUTION_DECISION.read_text(encoding="utf-8"))
    failure = json.loads(_EXECUTION_FAILURE.read_text(encoding="utf-8"))

    assert decision["repair_identity_review"] == {
        "path": str(_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_REVIEW),
    }
    assert decision["execution_authorized"] is True
    assert decision["cumulative_replay_authorized"] is True
    assert set(decision["prohibited_authorizations"].values()) == {False}
    assert failure["bound_execution"]["execution_decision"]["sha256"] == (
        file_sha256(_EXECUTION_DECISION)
    )


def test_replacement_review_records_absent_prospective_outputs() -> None:
    """The review records the no-output state at its freeze boundary."""
    review = _load()
    execution = review["prospective_execution"]

    assert _ROOT / execution["execution_decision"]["path"] == (
        _EXECUTION_DECISION
    )
    assert execution["output"]["state_at_review"] == "absent"
    for name in (
        "public-finder-correction-analysis.json",
        "public-finder-correction-comparison",
        "public-finder-correction-decision.json",
    ):
        assert not (_ROOT / "benchmark-results/phase-5" / name).exists()


def test_failed_execution_consumes_approval_without_opening_science() -> None:
    """The producer-source collision fails closed before reference science."""
    failure = json.loads(_EXECUTION_FAILURE.read_text(encoding="utf-8"))

    assert failure["status"] == "failed-before-reference-or-candidate-science"
    assert failure["bound_execution"]["execution_decision"]["sha256"] == (
        file_sha256(_EXECUTION_DECISION)
    )
    assert failure["bound_execution"]["repair_identity_review"]["sha256"] == (
        file_sha256(_REVIEW)
    )
    assert (
        failure["bound_execution"]["wrapper"]["sha256"]
        == _load()["implementation"]["wrapper"]["sha256"]
    )
    observed = failure["observed_execution"]
    assert observed["process_started"] is True
    assert observed["candidate_products_created"] == 0
    assert observed["reconstructed_inputs_opened"] == 0
    assert observed["reconstructed_reference_results_opened"] == 0
    assert observed["atomic_ledger_state"] == "absent"
    assert failure["scientific_outcome"]["available"] is False
    assert set(failure["authorization_boundary"].values()) == {False}
    assert failure["transfer_policy"] == {
        "authorization_consumed_by_process_start": True,
        "authorization_transferable_to_changed_wrapper": False,
        "rerun_authorized": False,
    }


def test_reference_provenance_repair_pre_review_is_non_executable() -> None:
    """The recommended repair preserves science and grants no execution."""
    review = json.loads(
        _REFERENCE_REPAIR_PRE_REVIEW.read_text(encoding="utf-8")
    )

    assert review["status"] == (
        "ready-for-named-reference-provenance-repair-implementation-approval"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["failed_execution"]["failure_record"]["sha256"] == (
        file_sha256(_EXECUTION_FAILURE)
    )
    assert (
        review["failed_execution"]["original_authorization_consumed"] is True
    )
    assert review["scientific_boundary"] == {
        "candidate_science_changed": False,
        "closed_baseline_sha256": (
            "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
        ),
        "compiler_or_evaluator_changed": False,
        "reference_evidence_changed": False,
        "scientific_outcome_available": False,
    }
    repair = review["prospective_repair"]
    assert repair["historical_reconstruction_producer_source_tree_sha256"] == (
        "b4176ce387fa1569cc86ca300bfa7de6462758a1068de46cd4a16616a6ec3adc"
    )
    assert (
        repair["prospective_scratch_path"]
        != review["failed_execution"]["scratch_path"]
    )
