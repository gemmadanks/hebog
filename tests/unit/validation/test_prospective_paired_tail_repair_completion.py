"""Prospective paired tail-repair completion contracts."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from typing import Any

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[3]
_PROGRAM = (
    _ROOT / "scripts/validation/"
    "complete_phase5_prospective_paired_tail_repair_evaluation.py"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-tail-diagnostic-repair-implementation-"
    "decision.json"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-tail-diagnostic-repair-identity-review.json"
)


def _program() -> dict[str, Any]:
    return runpy.run_path(str(_PROGRAM))


def _arguments(program: dict[str, Any]) -> argparse.Namespace:
    return argparse.Namespace(
        repository_root=program["_ROOT"],
        reference_reconstruction=program["_REFERENCE_RECONSTRUCTION"],
        source_request=program["_SOURCE_REQUEST"],
        population=program["_POPULATION"],
        current_scratch=program["_CURRENT_SCRATCH"],
        incumbent_scratch=program["_INCUMBENT_SCRATCH"],
        reconstruction_record=program["_RECONSTRUCTION_RECORD"],
        output=program["_OUTPUT"],
        verify_only=True,
    )


def test_completion_binds_frozen_parent_and_exact_repair_programs() -> None:
    """Historical evidence and both repair layers are immutable inputs."""
    program = _program()

    for path_name, digest_name in (
        ("_PARENT_COMPLETION", "_PARENT_COMPLETION_SHA256"),
        ("_PARENT_EVALUATOR", "_PARENT_EVALUATOR_SHA256"),
        ("_REPAIRED_EVALUATOR", "_REPAIRED_EVALUATOR_SHA256"),
        ("_TAIL_REPAIR", "_TAIL_REPAIR_SHA256"),
        ("_REPAIR_PRE_REVIEW", "_REPAIR_PRE_REVIEW_SHA256"),
    ):
        assert file_sha256(program[path_name]) == program[digest_name]
    decision = json.loads(_IMPLEMENTATION_DECISION.read_text(encoding="utf-8"))
    assert decision["repair"]["completion_program"]["sha256"] == file_sha256(
        _PROGRAM
    )
    assert decision["repair"]["strict_partition_guard_preserved"] is True
    assert decision["authorization"]["evaluation_retry_authorized"] is False


def test_no_write_verification_delegates_complete_product_rehash(
    monkeypatch: Any,
) -> None:
    """The repair adds provenance after the frozen complete product check."""
    program = _program()
    verify = program["verify_products"]
    globals_ = verify.__globals__
    calls: list[argparse.Namespace] = []

    def parent_verify(arguments: argparse.Namespace) -> dict[str, object]:
        calls.append(arguments)
        return {
            "status": "pass",
            "evaluator_sha256": program["_PARENT_EVALUATOR_SHA256"],
            "input_count_per_candidate": 2400,
            "reference_run_count": 9600,
            "candidate_execution_started": False,
        }

    monkeypatch.setitem(globals_, "_verify_repair_evidence", lambda: None)
    monkeypatch.setitem(
        globals_,
        "_load_parent_completion",
        lambda: {"verify_products": parent_verify},
    )
    monkeypatch.setitem(
        globals_,
        "_load_repaired_evaluator",
        lambda: {
            "main": lambda: None,
            "_truth_linked_tail_record": lambda: None,
            "_ORIGINAL_TRUTH_LINKED_TAIL_RECORD": lambda: None,
        },
    )
    arguments = _arguments(program)

    result = verify(arguments)

    assert calls == [arguments]
    assert (
        result["parent_evaluator_sha256"]
        == program["_PARENT_EVALUATOR_SHA256"]
    )
    assert result["evaluator_sha256"] == program["_REPAIRED_EVALUATOR_SHA256"]
    assert result["tail_repair_sha256"] == program["_TAIL_REPAIR_SHA256"]
    assert result["candidate_execution_started"] is False


def test_completion_command_runs_only_repaired_evaluator() -> None:
    """Evaluation-only completion cannot call a candidate producer."""
    program = _program()
    command = program["_evaluator_command"](_arguments(program))

    assert command[1] == str(program["_REPAIRED_EVALUATOR"])
    assert "materialize" not in " ".join(command)
    assert command[-2:] == ["--output", str(program["_OUTPUT"])]


def test_execution_digest_binds_consumed_lineage_and_scientific_inputs() -> (
    None
):
    """A future authority cannot substitute prior decisions or input sets."""
    program = _program()
    fields = program["_expected_execution_fields"](
        _arguments(program),
        {"status": "pass"},
        implementation_revision="a" * 40,
    )

    assert (
        fields["failed_identity_review_sha256"]
        == program["_FAILED_IDENTITY_REVIEW_SHA256"]
    )
    assert (
        fields["failed_execution_decision_sha256"]
        == program["_FAILED_EXECUTION_DECISION_SHA256"]
    )
    assert fields["population_sha256"] == program["_POPULATION_SHA256"]
    assert fields["source_request_sha256"] == program["_SOURCE_REQUEST_SHA256"]
    assert (
        fields["reference_reconstruction_sha256"]
        == program["_REFERENCE_RECONSTRUCTION_SHA256"]
    )
    assert "identity_review_sha256" not in fields


def test_identity_review_is_exact_and_non_executable() -> None:
    """The frozen review grants no execution authority."""
    program = _program()
    review = json.loads(_IDENTITY_REVIEW.read_text(encoding="utf-8"))
    expected = canonical_sha256(
        program["_expected_execution_fields"](
            _arguments(program),
            review["verified_products"],
            implementation_revision=review["implementation_revision"],
        )
    )

    assert review["expected_execution_sha256"] == expected
    assert review["authorization"] == dict.fromkeys(
        (
            "candidate_execution_authorized",
            "cutover_authorized",
            "evaluation_authorized",
            "fresh_qualification_authorized",
            "optimization_authorized",
            "release_authorized",
            "rescoring_authorized",
            "scientific_change_authorized",
            "threshold_or_margin_tuning_authorized",
            "viewed_data_execution_authorized",
        ),
        False,
    )
    assert not program["_EXECUTION_DECISION"].exists()
