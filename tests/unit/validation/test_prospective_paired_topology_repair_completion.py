"""Prospective paired source-union topology completion contracts."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import runpy
from pathlib import Path
from typing import Any

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_PROGRAM = (
    _ROOT / "scripts/validation/"
    "complete_phase5_prospective_paired_topology_repair_evaluation.py"
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
        verify_tail=True,
    )


def test_completion_binds_parent_repaired_programs_and_review() -> None:
    """Every inherited and replacement evaluation program is immutable."""
    program = _program()

    for path_name, digest_name in (
        ("_PARENT_COMPLETION", "_PARENT_COMPLETION_SHA256"),
        ("_PARENT_EVALUATOR", "_PARENT_EVALUATOR_SHA256"),
        ("_REPAIRED_EVALUATOR", "_REPAIRED_EVALUATOR_SHA256"),
        ("_PARENT_PREPARER", "_PARENT_PREPARER_SHA256"),
        ("_PREPARER", "_PREPARER_SHA256"),
        ("_SOURCE_UNION_TAIL", "_SOURCE_UNION_TAIL_SHA256"),
        ("_PRE_REVIEW", "_PRE_REVIEW_SHA256"),
    ):
        assert file_sha256(program[path_name]) == program[digest_name]


def test_product_verification_delegates_full_rehash_and_adds_repair(
    monkeypatch: Any,
) -> None:
    """The new completion retains the prior complete product verifier."""
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

    monkeypatch.setitem(
        globals_,
        "_load_parent_completion",
        lambda: {"verify_products": parent_verify},
    )
    monkeypatch.setitem(
        globals_, "_load_repaired_evaluator", lambda: {"main": lambda: None}
    )
    arguments = _arguments(program)

    result = verify(arguments)

    assert calls == [arguments]
    assert result["evaluator_sha256"] == program["_REPAIRED_EVALUATOR_SHA256"]
    assert (
        result["source_union_preparer_sha256"] == program["_PREPARER_SHA256"]
    )
    assert (
        result["source_union_tail_sha256"]
        == program["_SOURCE_UNION_TAIL_SHA256"]
    )
    assert result["candidate_execution_started"] is False


def test_completion_command_cannot_run_a_candidate() -> None:
    """Evaluation completion invokes only the repaired evaluator."""
    program = _program()
    command = program["_evaluator_command"](_arguments(program))

    assert command[1] == str(program["_REPAIRED_EVALUATOR"])
    assert "materialize" not in " ".join(command)
    assert command[-2:] == ["--output", str(program["_OUTPUT"])]


def test_execution_identity_includes_real_tail_and_consumed_failure() -> None:
    """A future run cannot omit the smoke or substitute failed lineage."""
    program = _program()
    tail = {
        "status": "pass",
        "summary_count": 4,
        "summaries_sha256": "a" * 64,
    }
    fields = program["_expected_execution_fields"](
        _arguments(program),
        {"status": "pass"},
        tail,
        implementation_revision="b" * 40,
    )

    assert fields["tail_verification"] == tail
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


def test_authorized_completion_verifies_tail_before_authority(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """No publication command runs until the exact real tail passes."""
    program = _program()
    complete = program["run_authorized_completion"]
    globals_ = complete.__globals__
    output = tmp_path / "decision.json"
    arguments = _arguments(program)
    arguments.output = output
    events: list[str] = []

    monkeypatch.setitem(
        globals_,
        "verify_products",
        lambda _arguments: events.append("products") or {},
    )
    monkeypatch.setitem(
        globals_, "verify_tail", lambda _arguments: events.append("tail") or {}
    )
    monkeypatch.setitem(
        globals_,
        "_validate_authority",
        lambda *_arguments: events.append("authority"),
    )

    def run(*_arguments: object, **_keywords: object) -> None:
        events.append("evaluation")
        output.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(globals_["subprocess"], "run", run)

    complete(arguments)

    assert events == ["products", "tail", "authority", "evaluation"]
