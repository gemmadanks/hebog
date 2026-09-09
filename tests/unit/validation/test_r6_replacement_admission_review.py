"""Review invariants use committed code, never campaign output directories."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT / "config/contracts/phase-5-r6-replacement-admission-review.json"
)


def _review() -> dict[str, Any]:
    return json.loads(_REVIEW.read_bytes())


def _historical(revision: str, relative: str) -> bytes:
    return subprocess.check_output(
        ("git", "show", f"{revision}:{relative}"), cwd=_ROOT
    )


def test_reuse_review_is_not_execution_or_a_transferred_verdict() -> None:
    review = _review()
    assert review["status"] == (
        "prospective-reuse-review-complete-admission-pending"
    )
    assert review["execution_identity"] is None
    assert review["finder_execution_started"] is False
    assert not any(review["authorizations"].values())
    assert review["admission"]["execution_admitted"] is False
    evidence = review["closed_evidence"]
    for key in (
        "old_candidate_records_reusable",
        "old_dask_comparisons_reusable",
        "old_verdict_reusable",
    ):
        assert evidence[key] is False
    assert "current-hebog" not in evidence["reusable_records"]
    work = review["prospective_work"]
    assert (
        sum(evidence["reusable_records"].values())
        == (work["reused_comparator_records"])
        == 8000
    )
    assert (
        work["current_serial_captures"]
        == (work["new_current_evaluation_records"])
        == 2400
    )
    assert work["total_evaluation_records"] == 8000 + 2400
    assert work["existing_dask_comparisons"] == 12
    assert work["workers"] == 2
    assert all(
        work[key] == 0
        for key in (
            "incumbent_executions",
            "pybdsf_executions",
            "aegean_executions",
        )
    )
    rules = review["frozen_rules"]
    assert rules["binding_comparisons"] == 1187
    assert rules["safety_checks"] == 5
    assert rules["bootstrap_resamples"] == 50000
    assert rules["bootstrap_seed"] == 20260810
    assert rules["compact_inputs"] == 800
    assert rules["continuum_inputs"] == 1600
    assert rules["truth"] == "independent-analytic-injected"
    assert rules["previous_uncertainty_acceptance_transfers"] is False
    assert rules["scientific_failure_is_terminal"] is True


def test_review_binds_documents_and_unchanged_comparator_programs() -> None:
    review = _review()
    for relative, expected in review["documents"].items():
        assert hashlib.sha256((_ROOT / relative).read_bytes()).hexdigest() == (
            expected
        )
    contracts = _ROOT / "config/contracts"
    candidate = json.loads(
        (
            contracts / "phase-5-r6-estimator-repair-identity-review.json"
        ).read_bytes()
    )
    continuation = json.loads(
        (
            contracts
            / "phase-5-r6-evaluation-continuation-identity-review.json"
        ).read_bytes()
    )
    assert (
        review["candidate_revision"]
        == (candidate["algorithm_candidate"]["revision"])
    )
    assert (
        review["reference_evaluator_revision"]
        == (continuation["implementation_revision"])
    )
    for relative, expected in review["unchanged_programs"].items():
        for field in ("candidate_revision", "reference_evaluator_revision"):
            payload = _historical(review[field], relative)
            assert hashlib.sha256(payload).hexdigest() == expected


def test_native_readers_are_unchanged_despite_hebog_estimator_repairs() -> (
    None
):
    review = _review()
    definitions: list[dict[str, str]] = []
    for field in ("candidate_revision", "reference_evaluator_revision"):
        tree = ast.parse(
            _historical(review[field], "src/hebog/validation/products.py")
        )
        definitions.append(
            {
                node.name: ast.dump(node, include_attributes=False)
                for node in tree.body
                if isinstance(node, ast.FunctionDef)
            }
        )
    for name in review["unchanged_products_reader_definitions"]:
        assert definitions[0][name] == definitions[1][name]
    # Reuse is deliberately narrower than claiming unchanged science.
    assert (
        definitions[0]["_reconstructed_source_rows"]
        != (definitions[1]["_reconstructed_source_rows"])
    )


def test_provisional_budget_exposes_space_and_time_admission_gaps() -> None:
    review = _review()
    budget = review["admission"]
    capture = review["closed_evidence"]["old_current_capture_bytes"]
    allowance = capture * budget["capture_growth_factor"] + sum(
        budget[key]
        for key in (
            "diagnostic_budget_bytes",
            "working_budget_bytes",
            "reserved_headroom_bytes",
        )
    )
    assert budget["provisional_free_bytes"] >= allowance
    assert budget["free_bytes_observed"] < budget["provisional_free_bytes"]
    assert (
        budget["planning_total_hours"][1]
        > (budget["final_campaign_budget_hours"])
    )
    assert budget["estimate_is_guarantee"] is False
    assert budget["final_campaign_budget_proven"] is False
