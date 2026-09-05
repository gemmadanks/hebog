"""Contracts for the validated final cumulative current replay."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_PREFIX = (
    "phase-5-final-cumulative-current-replay-"
    "validated-retry-type-clean-single-scan-canonical"
)
_PROCESS_REVIEW = (
    _ROOT / "config/contracts/phase-5-final-cumulative-current-replay-"
    "preflight-efficiency-review-canonical.json"
)
_TYPE_CLEAN_REVIEW = (
    _ROOT / "config/contracts/phase-5-final-cumulative-current-replay-"
    "type-clean-review-canonical.json"
)
_SINGLE_SCAN_REVIEW = (
    _ROOT / "config/contracts/phase-5-final-cumulative-current-replay-"
    "single-scan-execution-review-canonical.json"
)
_JSON_FORMAT_REVIEW = (
    _ROOT / "config/contracts/phase-5-final-cumulative-current-replay-"
    "json-format-review.json"
)
_IMPLEMENTATION = (
    _ROOT / f"config/contracts/{_PREFIX}-implementation-decision.json"
)
_IDENTITY = _ROOT / f"config/contracts/{_PREFIX}-identity-review.json"
_DECISION = _ROOT / f"config/contracts/{_PREFIX}-execution-decision.json"


def _object(path: Path) -> dict[str, Any]:
    """Load one JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _runner() -> Any:
    """Load the process-safe successor runner."""
    return importlib.import_module(
        "scripts.validation."
        "run_phase5_final_cumulative_current_replay_validated_retry"
    )


def test_process_review_proves_the_predecessor_never_executed() -> None:
    """Only duplicate read-only work is eligible for this successor."""
    review = _object(_PROCESS_REVIEW)

    assert review["status"] == (
        "approved-process-only-preflight-efficiency-repair"
    )
    assert review["diagnosis"] == {
        **review["diagnosis"],
        "candidate_execution_started": False,
        "governed_output_existed": False,
        "governed_scratch_existed": False,
        "scientific_effect": "none",
    }


def test_bounded_no_write_gate_checks_shape_without_real_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fast iteration covers all branches without hashing retained data."""
    runner = _runner()
    base = runner._base()
    identity = {
        "expected_execution_sha256": "expected-execution",
    }
    task = {
        "candidate_revision": base._CANDIDATE_REVISION,
        "source_tree_sha256": base._CANDIDATE_SOURCE_TREE_SHA256,
        "configuration_sha256": base._CANDIDATE_CONFIGURATION_SHA256,
    }

    def verify_static(_root: Path) -> None:
        return None

    def verify_reviews(_root: Path) -> None:
        return None

    def verify_identity(_root: Path) -> dict[str, str]:
        return identity

    def candidate_tasks(
        _root: Path, _scratch: Path
    ) -> tuple[dict[str, str], ...]:
        return (task,) * 2400

    def verify_process(_value: tuple[str, str, str]) -> str:
        return "spawn-pass"

    monkeypatch.setattr(base, "_verify_static_evidence", verify_static)
    monkeypatch.setattr(runner, "_verify_process_review", verify_reviews)
    monkeypatch.setattr(runner, "_verify_identity", verify_identity)
    monkeypatch.setattr(runner, "_verified_candidate_tasks", candidate_tasks)
    monkeypatch.setattr(runner, "_verify_process_payload", verify_process)

    verification = runner.verify_no_write(
        repository_root=_ROOT,
        scratch=Path(base._SCRATCH),
        output=_ROOT / base._OUTPUT,
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


@pytest.mark.slow
def test_exact_no_write_preflight_hashes_retained_evidence_once() -> None:
    """The immutable gate validates all products and the real process seam."""
    runner = _runner()
    base = runner._base()
    verification = runner.verify_no_write(
        repository_root=_ROOT,
        scratch=Path(base._SCRATCH),
        output=_ROOT / base._OUTPUT,
        enforce_execution_root=False,
        verify_process_pool=True,
    )

    assert verification == {
        **verification,
        "status": "pass",
        "candidate_execution_started": False,
        "candidate_task_count": 2400,
        "reference_run_count": 9600,
        "reference_verification_count": 1,
        "process_payload_status": "spawn-pass",
    }


def test_identity_and_decision_preserve_science_and_one_use_scope() -> None:
    """The successor changes only preflight work, not the replay science."""
    runner = _runner()
    base = runner._base()
    identity = _object(_IDENTITY)
    decision = _object(_DECISION)

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["expected_execution"] == base._expected_execution()
    assert decision["status"] == (
        "authorized-for-one-final-cumulative-current-replay"
    )
    assert decision["identity_review_sha256"] == file_sha256(_IDENTITY)
    assert decision["process_review_sha256"] == file_sha256(_PROCESS_REVIEW)
    assert decision["type_clean_review_sha256"] == file_sha256(
        _TYPE_CLEAN_REVIEW
    )
    assert decision["single_scan_review_sha256"] == file_sha256(
        _SINGLE_SCAN_REVIEW
    )
    assert decision["json_format_review_sha256"] == file_sha256(
        _JSON_FORMAT_REVIEW
    )
    assert decision["authorization"] == base._EXPECTED_AUTHORIZATION


def test_authorized_run_carries_one_verified_plan_into_materialization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Execution must not discard and reconstruct its verified task plan."""
    runner = _runner()
    base = runner._base()
    task: dict[str, Any] = {"input_id": "compact-example"}
    calls: list[str] = []
    published: list[dict[str, object]] = []

    def verified_plan(
        **_arguments: object,
    ) -> tuple[dict[str, object], tuple[dict[str, Any], ...]]:
        calls.append("verify")
        return {"status": "pass"}, (task,)

    def require_authority(_root: Path) -> None:
        calls.append("authority")

    def materialize(
        tasks: tuple[dict[str, Any], ...],
        _scratch: Path,
        *,
        workers: int,
    ) -> None:
        assert tasks == (task,)
        assert workers == 2
        calls.append("materialize")

    def product_set(_root: Path) -> str:
        calls.append("rehash")
        return "sealed-products"

    def publish(_path: Path, record: dict[str, object]) -> None:
        calls.append("publish")
        published.append(record)

    monkeypatch.setattr(runner, "_verified_plan", verified_plan)
    monkeypatch.setattr(runner, "_require_authority", require_authority)
    monkeypatch.setattr(runner, "_materialize_verified_tasks", materialize)
    monkeypatch.setattr(base, "_product_set_sha256", product_set)
    monkeypatch.setattr(base, "_publish", publish)

    runner.run_authorized_replay(
        repository_root=_ROOT, output=tmp_path / "product-set.json"
    )

    assert calls == ["verify", "authority", "materialize", "rehash", "publish"]
    assert len(published) == 1
    assert published[0]["candidate_product_set_sha256"] == "sealed-products"


def test_freezer_rebuilds_exact_records_and_refuses_collision(
    tmp_path: Path,
) -> None:
    """The successor freezer is deterministic and write-once."""
    freezer = importlib.import_module(
        "scripts.validation."
        "freeze_phase5_final_cumulative_current_replay_validated_retry"
    )
    arguments = argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)

    freezer.freeze_records(arguments)
    for path in (_IMPLEMENTATION, _IDENTITY, _DECISION):
        relative = path.relative_to(_ROOT)
        assert _object(tmp_path / relative) == _object(path)

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer.freeze_records(arguments)
