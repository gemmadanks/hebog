"""Contracts for the version-8 public cumulative candidate stage."""

from __future__ import annotations

import argparse
import importlib
import json
import runpy
from pathlib import Path
from typing import Any, cast

import pytest

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[3]
_RUNNER = (
    _ROOT
    / "scripts/validation/run_phase5_public_owner_domain_cumulative_replay.py"
)
_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_public_owner_domain_cumulative_replay.py"
)
_PREFIX = "phase-5-public-owner-domain-cumulative-replay"
_IMPLEMENTATION = (
    _ROOT / f"config/contracts/{_PREFIX}-implementation-decision.json"
)
_IDENTITY = _ROOT / f"config/contracts/{_PREFIX}-identity-review.json"
_DECISION = _ROOT / f"config/contracts/{_PREFIX}-execution-decision.json"
_FAST_TERMINAL = (
    _ROOT
    / "benchmark-results/phase-5/public-owner-domain-fast-lane-decision.json"
)
_CANDIDATE = {
    "configuration_sha256": (
        "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
    ),
    "revision": "95cfc76ded56556dc3ad6894410962d34f0d5604",
    "source_tree_sha256": (
        "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
    ),
}


def _object(path: Path) -> dict[str, Any]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_runner_targets_fresh_version_eight_namespace() -> None:
    """The cumulative stage must not reuse the consumed version-7 output."""
    runner = runpy.run_path(str(_RUNNER))
    expected = runner["_expected_execution"]()

    assert runner["_CANDIDATE"] == _CANDIDATE
    assert expected == {
        "candidate_executions": 2400,
        "candidate_revision": _CANDIDATE["revision"],
        "candidate_source_tree_sha256": _CANDIDATE["source_tree_sha256"],
        "configuration_sha256": _CANDIDATE["configuration_sha256"],
        "execution_root": (
            "/private/tmp/hebog-phase5-public-owner-domain-cumulative-replay"
        ),
        "output": (
            "benchmark-results/phase-5/"
            "public-owner-domain-cumulative-product-set.json"
        ),
        "pybdsf_executions": 0,
        "reference_run_count": 9600,
        "scratch": (
            "/private/tmp/hebog-phase5-public-owner-domain-cumulative-95cfc76"
        ),
        "workers": 2,
    }


def test_runner_restores_the_validated_predecessor_state() -> None:
    """The scoped bindings must not contaminate the proven predecessor."""
    predecessor = importlib.import_module(
        "scripts.validation."
        "run_phase5_final_cumulative_current_replay_validated_retry"
    )
    base = importlib.import_module(
        "scripts.validation.run_phase5_final_cumulative_current_replay"
    )
    previous_expected = base._expected_execution()
    previous_identity = predecessor._IDENTITY
    runner = runpy.run_path(str(_RUNNER))

    current_expected = runner["_expected_execution"]()

    assert current_expected["candidate_revision"] == _CANDIDATE["revision"]
    assert base._expected_execution() == previous_expected
    assert previous_identity == predecessor._IDENTITY


def test_identity_binds_fast_pass_and_retained_references() -> None:
    """The frozen candidate must descend from the exact passing fast lane."""
    identity = _object(_IDENTITY)

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["candidate"] == _CANDIDATE
    assert identity["fast_terminal"] == {
        "path": str(_FAST_TERMINAL.relative_to(_ROOT)),
        "sha256": (
            "a274888dab12bd5a1623310b35ba3f9a90ff14f9fd5249d118cd2a1c8b778348"
        ),
        "status": "pass",
    }
    assert identity["expected_execution_sha256"] == canonical_sha256(
        identity["expected_execution"]
    )
    assert identity["expected_execution"]["pybdsf_executions"] == 0
    assert identity["expected_execution"]["reference_run_count"] == 9600


def test_decision_authorizes_only_one_current_candidate_stage() -> None:
    """Replay authority must not authorize evaluation or new references."""
    runner = runpy.run_path(str(_RUNNER))
    identity = _object(_IDENTITY)
    decision = _object(_DECISION)

    assert decision["status"] == (
        "authorized-for-one-public-owner-domain-cumulative-replay"
    )
    assert decision["authorization"] == runner["_EXPECTED_AUTHORIZATION"]
    assert decision["identity_review_sha256"] == file_sha256(_IDENTITY)
    assert decision["expected_execution_sha256"] == canonical_sha256(
        identity["expected_execution"]
    )
    assert decision["authorization"]["candidate_execution_authorized"] is True
    assert decision["authorization"]["cumulative_replay_authorized"] is True
    assert decision["authorization"]["evaluation_authorized"] is False
    assert decision["authorization"]["pybdsf_execution_authorized"] is False
    assert decision["authorization"]["fresh_qualification_authorized"] is False


def test_bounded_plan_covers_all_products_without_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Fast verification must cover the complete shape before execution."""
    runner = runpy.run_path(str(_RUNNER))
    scratch = tmp_path / "candidate"
    output = tmp_path / "product-set.json"
    with runner["_configured_runner"]() as configured:
        base = configured["base"]
        validated = configured["validated"]
        with monkeypatch.context() as scoped:
            identity = {"expected_execution_sha256": "expected-execution"}
            task = {
                "candidate_revision": _CANDIDATE["revision"],
                "source_tree_sha256": _CANDIDATE["source_tree_sha256"],
                "configuration_sha256": _CANDIDATE["configuration_sha256"],
            }

            def no_op(_root: Path) -> None:
                return None

            def retained_source(_root: Path) -> str:
                return _CANDIDATE["source_tree_sha256"]

            def retained_identity(_root: Path) -> dict[str, str]:
                return identity

            def candidate_tasks(
                _root: Path, _scratch: Path
            ) -> tuple[dict[str, str], ...]:
                return (task,) * 2400

            def process_payload(_value: object) -> str:
                return "spawn-pass"

            scoped.setattr(base, "_SCRATCH", scratch)
            scoped.setattr(base, "_OUTPUT", output)
            scoped.setattr(base, "_verify_static_evidence", no_op)
            scoped.setattr(
                validated,
                "source_tree_sha256",
                retained_source,
            )
            scoped.setattr(validated, "_verify_process_review", no_op)
            scoped.setattr(validated, "_verify_identity", retained_identity)
            scoped.setattr(
                validated,
                "_verified_candidate_tasks",
                candidate_tasks,
            )
            scoped.setattr(
                validated,
                "_verify_process_payload",
                process_payload,
            )

            verification = validated.verify_no_write(
                repository_root=_ROOT,
                scratch=scratch,
                output=output,
                enforce_execution_root=False,
                verify_process_pool=True,
            )

    assert verification == {
        "candidate_execution_started": False,
        "candidate_task_count": 2400,
        "expected_execution_sha256": "expected-execution",
        "identity_review_sha256": file_sha256(_IDENTITY),
        "process_payload_status": "spawn-pass",
        "reference_run_count": 9600,
        "reference_verification_count": 1,
        "status": "pass",
    }
    assert not scratch.exists()
    assert not output.exists()


def test_freezer_reproduces_all_records(tmp_path: Path) -> None:
    """The exact cumulative records must reproduce byte for byte."""
    freezer = runpy.run_path(str(_FREEZER))
    arguments = argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)

    freezer["freeze_records"](arguments)

    for path in (_IMPLEMENTATION, _IDENTITY, _DECISION):
        reproduced = tmp_path / path.relative_to(_ROOT)
        assert reproduced.read_bytes() == path.read_bytes()

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_records"](arguments)
