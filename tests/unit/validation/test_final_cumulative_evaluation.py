"""Contracts for the final Phase 5 cumulative evaluation-only stage."""

from __future__ import annotations

import argparse
import importlib
import json
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_EVALUATOR = (
    _ROOT / "scripts/validation/evaluate_phase5_final_cumulative_current.py"
)
_COMPLETION = (
    _ROOT / "scripts/validation/complete_phase5_final_cumulative_evaluation.py"
)
_FREEZER = (
    _ROOT / "scripts/validation/freeze_phase5_final_cumulative_evaluation.py"
)
_IDENTITY = (
    _ROOT / "config/contracts/phase-5-final-cumulative-evaluation-"
    "identity-review.json"
)
_DECISION = (
    _ROOT / "config/contracts/phase-5-final-cumulative-evaluation-"
    "execution-decision.json"
)


def _completion() -> Any:
    """Import the evaluation-only completion wrapper."""
    return importlib.import_module(
        "scripts.validation.complete_phase5_final_cumulative_evaluation"
    )


def _arguments(module: Any, output: Path) -> argparse.Namespace:
    """Build one evaluation-only invocation."""
    return argparse.Namespace(
        repository_root=_ROOT,
        reference_reconstruction=module._REFERENCE_RECONSTRUCTION,
        source_request=module._SOURCE_REQUEST,
        population=module._POPULATION,
        current_scratch=module._CURRENT_SCRATCH,
        incumbent_scratch=module._INCUMBENT_SCRATCH,
        reconstruction_record=module._RECONSTRUCTION_RECORD,
        product_seal=module._PRODUCT_SEAL,
        output=output,
        verify_only=True,
        smoke_only=False,
    )


def test_final_evaluator_changes_only_the_current_candidate_identity() -> None:
    """The terminal repair stack and decision semantics stay unchanged."""
    overlay = runpy.run_path(str(_EVALUATOR))
    evaluator = overlay["load_final_evaluator"]()

    assert (
        file_sha256(overlay["_PARENT_EVALUATOR"])
        == overlay["_PARENT_EVALUATOR_SHA256"]
    )
    assert evaluator["_CURRENT_REVISION"] == overlay["_CURRENT_REVISION"]
    assert (
        evaluator["_CURRENT_SOURCE_TREE_SHA256"]
        == overlay["_CURRENT_SOURCE_TREE_SHA256"]
    )
    assert (
        evaluator["_CURRENT_CONFIGURATION_SHA256"]
        == overlay["_CURRENT_CONFIGURATION_SHA256"]
    )
    assert callable(evaluator["_truth_linked_tail_record"])
    assert Path(evaluator["__file__"]).resolve() == _EVALUATOR.resolve()


def test_final_evaluator_exposes_raw_parent_product_verifier_seams() -> None:
    """The inherited verifier can dispatch through the thin final overlay."""
    overlay = runpy.run_path(str(_EVALUATOR))

    assert callable(overlay["_load_materializer"])
    assert Path(overlay["_SMOKE_EVALUATOR"]).name == (
        "evaluate_phase5_prospective_science_smoke.py"
    )


def test_bounded_smoke_reaches_decision_summary_and_atomic_tail(
    tmp_path: Path,
) -> None:
    """A short preflight exercises the historically fragile final seams."""
    module = _completion()

    record = module.run_bounded_terminal_smoke(tmp_path)

    assert record["status"] == "pass"
    assert record["all_required_endpoints_pass"] is True
    assert record["cumulative_science_regression_ready"] is True
    assert record["section_counts"] == {
        "aegean_parity": 143,
        "binding_safety": 5,
        "incumbent_retention": 368,
        "longer_term_absolute_objectives": 15,
        "pybdsf_parity": 676,
    }
    assert record["terminal_publication_status"] == "pass"


def test_product_verifier_binds_seal_and_delegates_complete_rehash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact seal is required before inherited product verification."""
    module = _completion()
    arguments = _arguments(module, module._OUTPUT)
    calls: list[argparse.Namespace] = []

    def verify_products(value: argparse.Namespace) -> dict[str, object]:
        calls.append(value)
        return module._expected_parent_products()

    parent = {"verify_products": verify_products}
    monkeypatch.setattr(module, "_load_parent_completion", lambda: parent)

    verified = module.verify_products(arguments)

    assert calls == [arguments]
    assert verified["candidate_product_seal_sha256"] == file_sha256(
        arguments.product_seal
    )
    assert verified["current_product_set_sha256"] == (
        module._CURRENT_PRODUCT_SET_SHA256
    )


def test_completion_invokes_only_the_evaluator() -> None:
    """Evaluation authority cannot execute candidates or comparators."""
    module = _completion()
    command = module._evaluator_command(_arguments(module, module._OUTPUT))

    assert command[1] == str(module._EVALUATOR)
    assert "materialize" not in " ".join(command)
    assert command[-2:] == ["--output", str(module._OUTPUT)]


def test_freezer_records_are_exact_non_executable_then_one_use() -> None:
    """The user authority is separated from the scientific identity."""
    identity = json.loads(_IDENTITY.read_text(encoding="utf-8"))
    decision = json.loads(_DECISION.read_text(encoding="utf-8"))

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert (
        decision["status"] == "authorized-for-one-final-cumulative-evaluation"
    )
    assert decision["identity_review_sha256"] == canonical_sha256(identity)
    assert decision["authorization"]["evaluation_authorized"] is True
    assert {
        value
        for key, value in decision["authorization"].items()
        if key != "evaluation_authorized"
    } == {False}


def test_freezer_writes_once(tmp_path: Path) -> None:
    """Frozen evaluation records cannot be overwritten."""
    freezer = runpy.run_path(str(_FREEZER))
    arguments = argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)

    freezer["freeze_records"](arguments)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_records"](arguments)
