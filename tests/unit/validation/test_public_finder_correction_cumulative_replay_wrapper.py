"""Contracts for the non-executable correction cumulative-replay wrapper."""

from __future__ import annotations

import json
import runpy
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_public_finder_correction_cumulative_regressions.py"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-public-finder-correction-cumulative-replay-repair-"
    "implementation-decision.json"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-public-finder-correction-cumulative-replay-repair-pre-review.json"
)


def _arguments(tmp_path: Path) -> Namespace:
    """Return one prospective write-once replay invocation."""
    return Namespace(
        campaign=None,
        reference_reconstruction=tmp_path / "references",
        output=tmp_path / "ledger.json",
        scratch=tmp_path / "scratch",
        workers=2,
        closed_component_baseline_ledger=tmp_path / "baseline.json",
    )


def test_named_repair_approval_authorizes_no_replay() -> None:
    """Implementation approval cannot open the cumulative replay."""
    decision = json.loads(_IMPLEMENTATION_DECISION.read_text(encoding="utf-8"))

    assert decision["pre_review"] == {
        "path": (
            "config/contracts/phase-5-public-finder-correction-cumulative-"
            "replay-repair-pre-review.json"
        ),
        "sha256": (
            "e198df128900bf991c979764fc67dbda8a9b0a682be30f92bf70703122c1f162"
        ),
    }
    assert file_sha256(_PRE_REVIEW) == decision["pre_review"]["sha256"]
    assert decision["authorization"]["implementation_authorized"] is True
    assert decision["authorization"]["identity_freeze_authorized"] is True
    assert decision["authorization"]["cumulative_replay_authorized"] is False
    assert (
        decision["authorization"]["public_development_execution_authorized"]
        is False
    )


def test_wrapper_installs_only_the_approved_candidate_seams() -> None:
    """The wrapper keeps frozen machinery but selects correction science."""
    wrapper = runpy.run_path(str(_WRAPPER))
    frozen = wrapper["_load_frozen_replay"]()
    compact = frozen["_write_compact_products"]
    compiler = frozen["_COMPILER_PATH"]
    evaluator = frozen["_EVALUATOR_PATH"]
    provenance = {"execution_decision_sha256": "a" * 64}

    wrapper["_install_repair_composition"](frozen, provenance)

    assert frozen["_CANDIDATE_REVISION"] == (
        "b1d59e5aaf778a5fed4ea662afeba2ee100424ff"
    )
    assert frozen["_candidate_configuration_sha256"]() == (
        "65c8876dcdb484bd5a82b3520e065ea6bf33cf24cfdd33b592c6c859231c62f0"
    )
    writer_globals = frozen["_write_continuum_products"].__globals__
    assert (
        writer_globals["build_post_correction_continuum_products"].__name__
        == "build_public_finder_correction_continuum_products"
    )
    assert frozen["_write_compact_products"] is compact
    assert frozen["_COMPILER_PATH"] == compiler
    assert frozen["_EVALUATOR_PATH"] == evaluator
    assert frozen["_CLOSED_COMPONENT_BASELINE_LEDGER_SHA256"] == (
        "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
    )
    runtime = frozen["_candidate_runtime_identity"](
        frozen["_CANDIDATE_REVISION"]
    )
    assert runtime.name == "hebog-source-overlay"
    assert runtime.source_revision == frozen["_CANDIDATE_REVISION"]
    assert runtime.container_image_digest == (
        "sha256:1a83f64948460a46dd6f6c5e9434d155fd9b2ae45f97db849d5288f350dca8d1"
    )


def test_wrapper_loads_frozen_program_without_ambient_repository_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installed-package test environment still loads the bound script."""
    wrapper = runpy.run_path(str(_WRAPPER))
    monkeypatch.setattr(
        sys,
        "path",
        [entry for entry in sys.path if entry != str(_ROOT)],
    )

    frozen = wrapper["_load_frozen_replay"]()

    assert frozen["_CANDIDATE_REVISION"] == (
        "c184acf7f55f936442285835b4601a6ac193fe2a"
    )


def test_wrapper_adds_explicit_overlay_provenance_only_to_ledger() -> None:
    """Legacy marker serialization stays exact while the ledger is honest."""
    wrapper = runpy.run_path(str(_WRAPPER))
    frozen = wrapper["_load_frozen_replay"]()
    provenance = {
        "candidate_source_overlay_revision": (
            "b1d59e5aaf778a5fed4ea662afeba2ee100424ff"
        )
    }
    wrapper["_install_repair_composition"](frozen, provenance)
    serialize = frozen["_canonical_json_bytes"]

    marker = json.loads(serialize({"schema_version": 1}))
    ledger = json.loads(
        serialize(
            {
                "ledger_id": "phase-5-cumulative-regression-ledger",
                "schema_version": 1,
            }
        )
    )

    assert "replay_repair_provenance" not in marker
    assert ledger["replay_repair_provenance"] == provenance


def test_wrapper_refuses_absent_execution_decision_before_loading_replay(
    tmp_path: Path,
) -> None:
    """Implementation state fails before a source manifest can be opened."""
    wrapper = runpy.run_path(str(_WRAPPER))
    called = False

    def forbidden() -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    wrapper["run_authorized_replay"].__globals__["_load_frozen_replay"] = (
        forbidden
    )

    with pytest.raises(ValueError, match="not authorized"):
        wrapper["run_authorized_replay"](
            _arguments(tmp_path),
            execution_decision_path=tmp_path / "missing.json",
        )

    assert called is False


@pytest.mark.parametrize(
    "field",
    (
        "candidate_revision",
        "candidate_source_tree_sha256",
        "candidate_configuration_sha256",
        "base_review_sha256",
        "closed_baseline_sha256",
        "compiler_sha256",
        "correction_contract_sha256",
        "dependency_lock_sha256",
        "endpoint_registry_sha256",
        "evaluation_contract_sha256",
        "evaluator_sha256",
        "reference_reconstruction_sha256",
        "reference_verifier_sha256",
        "viewed_request_sha256",
    ),
)
def test_wrapper_rejects_identity_drift(field: str, tmp_path: Path) -> None:
    """Every approved science and environment identity fails closed."""
    wrapper = runpy.run_path(str(_WRAPPER))
    document = {
        **wrapper["_expected_execution_fields"](_arguments(tmp_path)),
        "cumulative_replay_authorized": True,
        "execution_authorized": True,
        "prohibited_authorizations": {
            "campaign_execution_authorized": False,
            "cutover_authorized": False,
            "fresh_qualification_authorized": False,
            "optimization_authorized": False,
            "public_development_execution_authorized": False,
            "release_authorized": False,
            "rescoring_authorized": False,
            "tuning_authorized": False,
        },
        "repair_identity_review": {
            "path": "config/contracts/pending-review.json",
            "sha256": "f" * 64,
        },
        "status": "reviewed-before-public-finder-correction-cumulative-replay",
    }
    document[field] = "0" * 64

    with pytest.raises(ValueError, match="identity changed"):
        wrapper["_validate_execution_decision"](
            document,
            _arguments(tmp_path),
        )
