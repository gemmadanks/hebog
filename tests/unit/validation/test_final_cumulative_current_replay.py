"""Contracts for the Phase 5 final cumulative current-candidate replay."""

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


@pytest.mark.slow
def test_no_write_preflight_covers_all_products_and_process_seam() -> None:
    """The candidate runner checks its full shape before creating data."""
    runner = importlib.import_module(
        "scripts.validation.run_phase5_final_cumulative_current_replay"
    )
    verification = runner.verify_no_write(
        repository_root=_ROOT,
        scratch=Path(runner._SCRATCH),
        output=_ROOT / runner._OUTPUT,
        enforce_execution_root=False,
        verify_process_pool=True,
    )

    assert verification == {
        **verification,
        "status": "pass",
        "candidate_execution_started": False,
        "candidate_task_count": 2400,
        "reference_run_count": 9600,
        "process_payload_status": "spawn-pass",
    }


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
