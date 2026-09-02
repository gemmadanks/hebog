"""Prospective paired evaluation-only completion tests."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[3]
_PROGRAM = (
    _ROOT
    / "scripts/validation/complete_phase5_prospective_paired_evaluation.py"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-paired-evaluation-"
    "completion-implementation-decision.json"
)


def _program() -> dict[str, Any]:
    """Load the completion program without executing its CLI."""
    return runpy.run_path(str(_PROGRAM))


def _arguments(program: dict[str, Any]) -> argparse.Namespace:
    """Build the program's exact fixed invocation."""
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


def test_completion_program_binds_the_unchanged_evaluator_and_repair() -> None:
    """The completion cannot substitute a new evaluator or repair program."""
    program = _program()

    assert file_sha256(program["_EVALUATOR"]) == program["_EVALUATOR_SHA256"]
    assert (
        file_sha256(program["_RECONSTRUCTION_PROGRAM"])
        == program["_RECONSTRUCTION_PROGRAM_SHA256"]
    )
    assert (
        file_sha256(program["_COMPLETION_PRE_REVIEW"])
        == program["_COMPLETION_PRE_REVIEW_SHA256"]
    )
    assert program["_CURRENT_PRODUCT_SET_SHA256"] == (
        "6bcb2959c56173d1a930eb14b3a794727649defc1b52dc1d9d70cd041d401014"
    )
    assert program["_INCUMBENT_RECONSTRUCTION_PRODUCT_SET_SHA256"] == (
        "ea12ce032d06c37cfeb70dcfd16d288bd68bc1ef19c010b8491b9ff66ae406e8"
    )
    assert program["_INCUMBENT_EVALUATOR_PRODUCT_SET_SHA256"] == (
        "8dbc9dff20c861b1f93f11781d079226a7ef68475838909496086229ddc9fe5d"
    )
    decision = json.loads(_IMPLEMENTATION_DECISION.read_text(encoding="utf-8"))
    assert decision["completion"]["program_sha256"] == file_sha256(_PROGRAM)
    assert (
        decision["completion"]["evaluator_sha256"]
        == program["_EVALUATOR_SHA256"]
    )
    assert decision["repair_boundary"]["candidate_execution_possible"] is False


def test_completion_invocation_rejects_namespace_drift() -> None:
    """Only the new incumbent namespace and absent paired output are valid."""
    program = _program()
    arguments = _arguments(program)

    program["_require_invocation"](arguments)
    arguments.incumbent_scratch = Path("different")
    with pytest.raises(ValueError, match="incumbent_scratch"):
        program["_require_invocation"](arguments)


def test_completion_rejects_hebog_imports_from_another_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A detached checkout cannot silently import another Hebog tree."""
    program = _program()
    require_origin = program["_require_import_origin"]

    monkeypatch.setattr(
        require_origin.__globals__["inspect"],
        "getsourcefile",
        lambda _value: "/different/checkout/external_runners.py",
    )

    with pytest.raises(ValueError, match="import origin"):
        require_origin()


def test_reconstruction_record_requires_complete_fixed_identity(
    tmp_path: Path,
) -> None:
    """A recovery record must bind the exact product and no science change."""
    program = _program()
    document: dict[str, object] = {
        "schema_version": 1,
        "status": "complete",
        "candidate_revision": program["_INCUMBENT_REVISION"],
        "candidate_source_tree_sha256": program[
            "_INCUMBENT_SOURCE_TREE_SHA256"
        ],
        "candidate_configuration_sha256": program[
            "_INCUMBENT_CONFIGURATION_SHA256"
        ],
        "execution_decision_sha256": program[
            "_RECONSTRUCTION_DECISION_SHA256"
        ],
        "reconstruction_program_sha256": program[
            "_RECONSTRUCTION_PROGRAM_SHA256"
        ],
        "reference_reconstruction_sha256": program[
            "_REFERENCE_RECONSTRUCTION_SHA256"
        ],
        "population_sha256": program["_POPULATION_SHA256"],
        "input_count": 2400,
        "compact_product_count": 800,
        "continuum_product_count": 1600,
        "product_set_sha256": program[
            "_INCUMBENT_RECONSTRUCTION_PRODUCT_SET_SHA256"
        ],
        "current_candidate_execution_started": False,
        "scientific_policy_changed": False,
    }
    document["record_canonical_sha256"] = canonical_sha256(document)
    path = tmp_path / "reconstruction.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    arguments = SimpleNamespace(reconstruction_record=path)

    assert (
        program["_verify_reconstruction_record"](arguments)
        == program["_INCUMBENT_RECONSTRUCTION_PRODUCT_SET_SHA256"]
    )
    document["scientific_policy_changed"] = True
    document["record_canonical_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in document.items()
            if key != "record_canonical_sha256"
        }
    )
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        program["_verify_reconstruction_record"](arguments)


def test_product_preflight_rehashes_both_candidates_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No-write verification checks both complete product sets and seams."""
    program = _program()
    verify = program["verify_products"]
    globals_ = verify.__globals__
    arguments = _arguments(program)
    identifiers = {f"input-{index}" for index in range(2400)}
    calls: list[Path] = []

    monkeypatch.setitem(globals_, "_require_import_origin", lambda: None)
    monkeypatch.setitem(globals_, "_require_invocation", lambda _args: None)
    monkeypatch.setitem(
        globals_, "_verify_static_evidence", lambda _args: None
    )
    monkeypatch.setitem(
        globals_,
        "_verify_reconstruction_record",
        lambda _args: "incumbent-reconstruction-products",
    )

    def verify_product_set(
        _identifiers: set[str],
        scratch: Path,
        **_identity: object,
    ) -> str:
        calls.append(scratch)
        return (
            program["_CURRENT_PRODUCT_SET_SHA256"]
            if scratch == arguments.current_scratch
            else program["_INCUMBENT_EVALUATOR_PRODUCT_SET_SHA256"]
        )

    materializer = {
        "_selected_inputs": lambda *_args: identifiers,
        "_verified_reference": lambda *_args: (
            SimpleNamespace(runs=(None,) * 9600),
            None,
        ),
    }
    evaluator = {
        "_SMOKE_EVALUATOR": Path("smoke.py"),
        "_load_materializer": lambda: materializer,
        "_compile_incumbent_pair": lambda: None,
        "compile_prospective_decision": lambda: None,
        "main": lambda: None,
    }
    monkeypatch.setattr(
        globals_["runpy"],
        "run_path",
        lambda path: (
            {"_verify_product_set": verify_product_set}
            if Path(path) == Path("smoke.py")
            else evaluator
        ),
    )
    monkeypatch.setitem(
        globals_, "file_sha256", lambda _path: "reconstruction-record"
    )

    result = verify(arguments)

    assert calls == [arguments.current_scratch, arguments.incumbent_scratch]
    assert result["candidate_execution_started"] is False
    assert result["incumbent_reconstruction_product_set_sha256"] == (
        "incumbent-reconstruction-products"
    )
    assert (
        result["incumbent_product_set_sha256"]
        == program["_INCUMBENT_EVALUATOR_PRODUCT_SET_SHA256"]
    )
    assert result["input_count_per_candidate"] == 2400
    assert result["reference_run_count"] == 9600


def test_completion_command_runs_only_the_unchanged_evaluator() -> None:
    """The completion command contains no candidate producer entry point."""
    program = _program()
    command = program["_evaluator_command"](_arguments(program))

    assert command[1] == str(program["_EVALUATOR"])
    assert "materialize" not in " ".join(command)
    assert command[-2:] == ["--output", str(program["_OUTPUT"])]


def test_execution_digest_is_not_circular_with_identity_review() -> None:
    """The decision binds the review hash outside its own execution digest."""
    program = _program()
    fields = program["_expected_execution_fields"](
        _arguments(program),
        {"status": "pass"},
        implementation_revision="revision",
    )

    assert fields["implementation_revision"] == "revision"
    assert "identity_review_sha256" not in fields


def test_completion_accepts_a_later_clean_authorization_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reviewed code may be followed by its review and decision commit."""
    program = _program()
    require_ancestor = program["_require_implementation_ancestor"]
    calls: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...], **_kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(require_ancestor.__globals__["subprocess"], "run", run)

    implementation = "a" * 40
    execution = "b" * 40
    assert require_ancestor(implementation, execution) == implementation
    assert calls == [
        ("git", "merge-base", "--is-ancestor", implementation, execution)
    ]


def test_completion_rejects_unrelated_implementation_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrelated reviewed implementation cannot authorize execution."""
    program = _program()
    require_ancestor = program["_require_implementation_ancestor"]
    monkeypatch.setattr(
        require_ancestor.__globals__["subprocess"],
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )

    with pytest.raises(ValueError, match="implementation revision"):
        require_ancestor("a" * 40, "b" * 40)
