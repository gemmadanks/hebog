"""Contracts for the Phase 5 final cumulative current-candidate replay."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_PREFIX = "phase-5-final-cumulative-current-replay"
_PRE_REVIEW = _ROOT / f"config/contracts/{_PREFIX}-pre-review.json"
_IMPLEMENTATION = (
    _ROOT / f"config/contracts/{_PREFIX}-implementation-decision.json"
)
_IDENTITY = _ROOT / f"config/contracts/{_PREFIX}-identity-review.json"
_DECISION = _ROOT / f"config/contracts/{_PREFIX}-execution-decision.json"
_FREEZER = (
    _ROOT
    / "scripts/validation/freeze_phase5_final_cumulative_current_replay.py"
)


def _object(path: Path) -> dict[str, Any]:
    """Load one JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_pre_review_keeps_every_scientific_gate_strict() -> None:
    """The long replay cannot weaken parity or incumbent retention."""
    review = _object(_PRE_REVIEW)

    assert review["status"] == (
        "approved-for-test-first-implementation-and-exact-replay-freeze"
    )
    assert review["population"] == {
        "compact_input_count": 800,
        "continuum_input_count": 1600,
        "input_count": 2400,
        "role": "cumulative-regression",
    }
    gates = review["final_science_gates"]
    assert gates["dual_pybdsf_parity_required"] is True
    assert gates["incumbent_retention_required"] is True
    assert gates["like_semantics_regression_allowed"] is False
    assert review["authorization"]["pybdsf_execution_authorized"] is False


def test_no_write_preflight_covers_all_product_and_reference_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise census and namespace checks without campaign outputs."""
    runner = importlib.import_module(
        "scripts.validation.run_phase5_final_cumulative_current_replay"
    )
    scratch = tmp_path / "scratch"
    output = tmp_path / runner._OUTPUT
    identity_path = tmp_path / runner._IDENTITY
    identity_path.parent.mkdir(parents=True)
    identity_path.write_text(json.dumps({"fixture": True}))
    monkeypatch.setattr(runner, "_SCRATCH", scratch)

    def source_identity(_root: Path) -> str:
        return str(runner._CANDIDATE_SOURCE_TREE_SHA256)

    monkeypatch.setattr(runner, "source_tree_sha256", source_identity)
    calls: list[str] = []

    def verify_static(_root: Path) -> None:
        calls.append("static")

    def verify_identity(_root: Path) -> dict[str, str]:
        calls.append("identity")
        return {"expected_execution_sha256": "a" * 64}

    monkeypatch.setattr(runner, "_verify_static_evidence", verify_static)
    monkeypatch.setattr(runner, "_verify_identity", verify_identity)
    tasks = tuple(
        {
            "candidate_revision": runner._CANDIDATE_REVISION,
            "source_tree_sha256": runner._CANDIDATE_SOURCE_TREE_SHA256,
            "configuration_sha256": runner._CANDIDATE_CONFIGURATION_SHA256,
        }
        for _ in range(2400)
    )
    references = SimpleNamespace(runs=tuple(range(9600)))

    def candidate_tasks(_arguments: object):
        return tasks

    def verified_reference(
        _root: Path,
        _record: Path,
    ) -> tuple[SimpleNamespace, dict[str, object]]:
        return references, {}

    def load_materializer(_root: Path):
        return {"_verified_reference": verified_reference}

    module = SimpleNamespace(
        _candidate_tasks=candidate_tasks,
        _load_materializer=load_materializer,
    )
    monkeypatch.setattr(runner, "_materializer_module", lambda: module)
    verification = runner.verify_no_write(
        repository_root=tmp_path,
        scratch=scratch,
        output=output,
        enforce_execution_root=False,
    )

    assert verification == {
        **verification,
        "status": "pass",
        "candidate_execution_started": False,
        "candidate_task_count": 2400,
        "reference_run_count": 9600,
        "process_payload_status": "not-requested",
    }
    assert calls == ["static", "identity"]
    assert not scratch.exists() and not output.exists()
    for field in (
        "candidate_revision",
        "source_tree_sha256",
        "configuration_sha256",
    ):
        original = tasks[0][field]
        tasks[0][field] = "changed"
        with pytest.raises(ValueError, match="task identity"):
            runner.verify_no_write(
                repository_root=tmp_path,
                scratch=scratch,
                output=output,
                enforce_execution_root=False,
            )
        tasks[0][field] = original
    references.runs = references.runs[:-1]
    with pytest.raises(ValueError, match="reference population"):
        runner.verify_no_write(
            repository_root=tmp_path,
            scratch=scratch,
            output=output,
            enforce_execution_root=False,
        )
    output.parent.mkdir(parents=True)
    output.write_text("preserve-terminal")
    with pytest.raises(FileExistsError, match="namespace"):
        runner.verify_no_write(
            repository_root=tmp_path,
            scratch=scratch,
            output=output,
            enforce_execution_root=False,
        )
    assert output.read_text() == "preserve-terminal"


@pytest.mark.integration
def test_frozen_replay_process_payload_is_importable_without_campaigns() -> (
    None
):
    """The real spawned target needs no scientific arrays or execution."""
    runner = importlib.import_module(
        "scripts.validation.run_phase5_final_cumulative_current_replay"
    )
    assert runner._verify_process_payload(
        ("candidate", "source", "config")
    ) == ("spawn-pass")


def test_identity_and_decision_authorize_only_one_current_replay() -> None:
    """Evaluation and reference execution remain separate stages."""
    identity = _object(_IDENTITY)
    decision = _object(_DECISION)

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert decision["status"] == (
        "authorized-for-one-final-cumulative-current-replay"
    )
    assert decision["identity_review_sha256"] == file_sha256(_IDENTITY)
    assert decision["authorization"] == {
        "candidate_execution_authorized": True,
        "cumulative_replay_authorized": True,
        "evaluation_authorized": False,
        "fresh_qualification_authorized": False,
        "pybdsf_execution_authorized": False,
        "release_authorized": False,
        "rescoring_authorized": False,
        "scientific_change_authorized": False,
        "threshold_or_margin_tuning_authorized": False,
        "viewed_data_execution_authorized": False,
    }


@pytest.mark.posix_frozen_record
def test_superseded_freezer_records_remain_write_once(
    tmp_path: Path,
) -> None:
    """The superseded draft remains immutable after its slow-test marker."""
    freezer = importlib.import_module(
        "scripts.validation.freeze_phase5_final_cumulative_current_replay"
    )
    arguments = argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)

    freezer.freeze_records(arguments)
    generated_implementation = _object(
        tmp_path / _IMPLEMENTATION.relative_to(_ROOT)
    )
    generated_identity = _object(tmp_path / _IDENTITY.relative_to(_ROOT))
    generated_decision = _object(tmp_path / _DECISION.relative_to(_ROOT))
    assert generated_implementation == _object(_IMPLEMENTATION)
    assert generated_identity != _object(_IDENTITY)
    assert generated_decision != _object(_DECISION)

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer.freeze_records(arguments)
