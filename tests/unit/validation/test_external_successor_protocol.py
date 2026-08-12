"""Contracts for the composed Step 2C-PF successor one-look protocol."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

_ROOT = Path(__file__).parents[3]


def _sha256(path: Path) -> str:
    """Hash one small reviewed repository artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _script(relative_path: str) -> dict[str, Any]:
    """Load one script without invoking its command-line entry point."""
    return runpy.run_path(str(_ROOT / relative_path))


def test_successor_loaders_validate_new_population_and_approved_decision() -> (
    None
):
    """Expose only the named-approved unopened successor population."""
    module = _script(
        "scripts/validation/phase5_external_successor_protocol.py"
    )
    protocol = module["load_successor_protocol"](
        _ROOT / "config/contracts/phase-5-external-successor-comparison.json"
    )
    decision = module["load_successor_execution_decision"](
        _ROOT
        / "config/contracts/phase-5-external-successor-execution-decision.json"
    )

    assert tuple(item.manifest for item in protocol.populations) == (
        "config/datasets/phase-5-external-successor-continuum.json",
        "config/datasets/phase-5-external-successor-compact-blend.json",
    )
    assert decision.execution_authorized is True
    assert decision.one_look_opened is False
    assert "200d1076aae8e833" in decision.named_review
    assert decision.source_tree_sha256 == (
        "d50be758d788967cf13912190b9de43e021d7e9f4325c2b7e5180f89c29516fd"
    )
    assert tuple(item.relative_path for item in decision.runners) == (
        "scripts/benchmark/run_phase5_external_successor_hebog.py",
        "scripts/benchmark/run_phase5_external_successor_pybdsf.py",
        "scripts/benchmark/run_phase5_external_successor_aegean.py",
    )


def test_successor_protocol_rejects_ignored_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A checksum-valid document cannot smuggle an unused policy field."""
    module = _script(
        "scripts/validation/phase5_external_successor_protocol.py"
    )
    path = (
        _ROOT / "config/contracts/phase-5-external-successor-comparison.json"
    )
    original = module["json_object"](path)
    unexpected = cast(
        dict[str, Any],
        {**original, "adaptive_sample_size": True},
    )

    def json_with_unexpected_field(_path: Path) -> dict[str, Any]:
        """Return the deliberately invalid in-memory protocol."""
        return unexpected

    monkeypatch.setitem(
        module["load_successor_protocol"].__globals__,
        "json_object",
        json_with_unexpected_field,
    )

    with pytest.raises(ValueError, match="protocol fields changed"):
        module["load_successor_protocol"](path)


def test_successor_composition_binds_closed_mechanics_and_new_kernel() -> None:
    """The compiler registry verifies both immutable layers explicitly."""
    module = _script(
        "scripts/validation/compile_phase5_external_successor_campaign.py"
    )
    registry = module["load_successor_composition"](
        _ROOT
        / "config/contracts/phase-5-external-successor-endpoint-registry.json",
        _ROOT
        / "scripts/validation/compile_phase5_external_successor_campaign.py",
    )

    composition = cast(dict[str, object], registry["successor_composition"])
    assert composition["terminal_compiler_sha256"] == (
        "7a0558916ac003b71a781337dc710c99c359899c4d77f88486c1c206916b43f6"
    )
    assert composition["science_kernel_sha256"] == (
        "8e38de3b4347faee9636b89d03f8cdcdd77e39fd1e087d2b44454e5fd7063c55"
    )
    assert registry["continuum_manifest_sha256"] == (
        "906a3e8bcc5bbc775418c30b5da08559e1425fbae74dd05fd9b2e96f69df7c46"
    )


def test_successor_evaluator_recomputes_unchanged_gates() -> None:
    """The composed evaluator accepts no changed scientific threshold."""
    module = _script(
        "scripts/validation/evaluate_phase5_external_successor_decision.py"
    )
    contract = module["load_successor_evaluation_contract"](
        _ROOT / "config/contracts/phase-5-external-successor-evaluation.json",
        _ROOT
        / "scripts/validation/evaluate_phase5_external_successor_decision.py",
    )

    assert contract["failure_policy"] == (
        "absolute-first-retain-denominator-incomplete-reference-fails-closed"
    )
    assert contract["one_look_rule"] == (
        "one-terminal-look-no-tuning-rescoring-reconfirmation-or-adaptive-"
        "sample-size"
    )
    assert contract["population"] == {
        "binding_run_count": 5000,
        "compact_blend_image_count": 800,
        "continuum_image_count": 600,
        "image_count": 1400,
        "terminal_run_count": 7000,
    }


def test_successor_launcher_rejects_pending_authorization_before_inspection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No container or staging boundary opens before named approval."""
    module = _script(
        "scripts/benchmark/run_phase5_external_successor_campaign.py"
    )

    def unexpected_inspection(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("container inspection must remain closed")

    def pending_decision(_path: Path) -> SimpleNamespace:
        """Return one explicit non-authorized synthetic decision."""
        return SimpleNamespace(execution_authorized=False)

    monkeypatch.setitem(
        module["_HELPERS"],
        "load_successor_execution_decision",
        pending_decision,
    )
    monkeypatch.setattr(
        module["_TERMINAL"]["subprocess"],
        "run",
        unexpected_inspection,
    )
    with pytest.raises(
        ValueError,
        match="successor external comparison execution is not authorized",
    ):
        module["preflight_successor_campaign"](
            repository_root=_ROOT,
            output=tmp_path / "campaign",
            images={
                "hebog": "unused",
                "released-pybdsf": "unused",
                "pinned-pybdsf-master": "unused",
                "aegean": "unused",
            },
        )
    assert not (tmp_path / "campaign").exists()


def test_successor_launcher_expands_the_complete_frozen_population() -> None:
    """The compatibility view retains all 1,400 inputs and 7,000 legs."""
    module = _script(
        "scripts/benchmark/run_phase5_external_successor_campaign.py"
    )
    protocol = module["_HELPERS"]["load_successor_protocol"](
        _ROOT / "config/contracts/phase-5-external-successor-comparison.json"
    )

    inputs, runs = module["_TERMINAL"]["_population_requests"](
        _ROOT,
        protocol,
    )

    assert len(inputs) == 1400
    assert len(runs) == 7000
    assert len({item.seed for item in inputs}) == 1400


def test_successor_freeze_records_named_approval_and_no_write_preflight() -> (
    None
):
    """The review binds the approved identities and exact preflight request."""
    review = json.loads(
        (
            _ROOT / "config/contracts/"
            "phase-5-external-successor-preflight-review.json"
        ).read_text(encoding="utf-8")
    )

    assert review["status"] == "approved-no-write-preflight-passed"
    assert review["execution_authorized"] is True
    assert review["one_look_opened"] is False
    assert review["closed_campaign_reuse_authorized"] is False
    assert review["population"]["image_count"] == 1400
    assert review["population"]["terminal_run_count"] == 7000
    assert review["technical_review"]["preflight_status"] == "pass-no-write"
    assert len(review["technical_review"]["preflight_request_sha256"]) == 64
    assert review["runtime"]["hebog"]["container_image_digest"] == (
        "sha256:d0c1319072c3716811ed51452fe83d92be8f8d2b62a11795678f31037b7b1f68"
    )
    assert review["runtime"]["hebog"]["source_tree_sha256"] == (
        "d50be758d788967cf13912190b9de43e021d7e9f4325c2b7e5180f89c29516fd"
    )
    for prefix in (
        "compiler",
        "endpoint_registry",
        "evaluation_contract",
        "evaluator",
        "launcher",
        "protocol",
        "protocol_verifier",
        "science_kernel",
    ):
        identity = review["protocol"]
        assert (
            _sha256(_ROOT / identity[f"{prefix}_path"])
            == identity[f"{prefix}_sha256"]
        )
    authorization = review["authorization"]
    assert (
        _sha256(_ROOT / authorization["execution_decision_path"])
        == (authorization["execution_decision_sha256"])
    )
    population = review["population"]
    assert (
        _sha256(_ROOT / population["population_contract_path"])
        == (population["population_contract_sha256"])
    )
