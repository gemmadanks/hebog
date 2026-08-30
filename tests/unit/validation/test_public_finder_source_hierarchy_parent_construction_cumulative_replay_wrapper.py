"""Contracts for the non-executable parent-construction replay wrapper."""

from __future__ import annotations

import json
import runpy
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_source_hierarchy_"
    "parent_construction_cumulative_regressions.py"
)
_CONSUMED_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_source_"
    "reconstruction_cumulative_regressions.py"
)
_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-implementation-decision.json"
)
_READINESS = _ROOT / "config/contracts/phase-5-readiness.json"
_REVISION = "5f2b09880dc10feb6ffaec50ffcf3c807a093416"
_SOURCE_TREE = (
    "a7ef1887bcaeb15abf48722d45de33f81d8be65d58fde19861bf0ece90b4dba8"
)
_CONFIGURATION = (
    "88634678d7b24c9d9d47a5ba714c66fcc627c8a201b9639b133e326cd1c72484"
)


def _approved_arguments() -> Namespace:
    """Return the exact prospective no-write invocation."""
    return Namespace(
        campaign=None,
        reference_reconstruction=Path(
            "benchmark-results/phase-5/"
            "viewed-reference-reconstruction-public-finder-correction"
        ),
        output=Path(
            "benchmark-results/phase-5/cumulative-regression-ledger-"
            "public-finder-source-hierarchy-parent-construction.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-source-hierarchy-"
            "parent-construction-5f2b098"
        ),
        workers=2,
        closed_component_baseline_ledger=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
    )


def test_wrapper_binds_exact_candidate_and_consumed_wrapper() -> None:
    """The wrapper names the approved candidate and immediate predecessor."""
    wrapper = runpy.run_path(str(_WRAPPER))

    assert wrapper["_CANDIDATE_REVISION"] == _REVISION
    assert wrapper["_CANDIDATE_SOURCE_TREE_SHA256"] == _SOURCE_TREE
    assert wrapper["_CANDIDATE_CONFIGURATION_SHA256"] == _CONFIGURATION
    assert wrapper["_candidate_configuration_sha256"]() == _CONFIGURATION
    assert wrapper["_CONSUMED_WRAPPER_SHA256"] == file_sha256(
        _CONSUMED_WRAPPER
    )
    assert wrapper["_PROSPECTIVE_OUTPUT_PATH"] == _approved_arguments().output
    assert wrapper["_PROSPECTIVE_SCRATCH_PATH"] == (
        _approved_arguments().scratch
    )


def test_readiness_supersedes_the_parent_construction_candidate() -> None:
    """The failed historical candidate cannot satisfy current readiness."""
    readiness = json.loads(_READINESS.read_text(encoding="utf-8"))
    evidence = {
        item["evidence_id"]: item for item in readiness["required_evidence"]
    }
    assert (
        "public-finder-source-hierarchy-parent-construction-cumulative-"
        "regression"
    ) not in evidence
    assert (
        "public-finder-source-hierarchy-parent-construction-held-out-"
        "qualification"
    ) not in evidence


def test_fixture_verifier_is_no_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verification returns identities without creating replay state."""
    wrapper = runpy.run_path(str(_WRAPPER))
    arguments = _approved_arguments()
    arguments.output = tmp_path / "ledger.json"
    arguments.scratch = tmp_path / "scratch"
    globals_ = wrapper[
        "verify_parent_construction_replay_composition"
    ].__globals__

    def require_common_identities(_arguments: Namespace) -> str:
        return "execution-revision"

    def verify_reference_reconstruction(
        _arguments: Namespace,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            reference_reconstruction_sha256="a" * 64,
            inputs=tuple(range(4)),
            runs=tuple(range(16)),
        )

    monkeypatch.setitem(
        globals_,
        "_require_common_identities",
        require_common_identities,
    )
    monkeypatch.setitem(
        globals_,
        "_verify_reference_reconstruction",
        verify_reference_reconstruction,
    )

    result = wrapper["verify_parent_construction_replay_composition"](
        arguments,
        implementation_decision_path=_DECISION,
    )

    assert result["status"] == "pass"
    assert result["cumulative_replay_started"] is False
    assert result["execution_delegation_verified"] is True
    assert result["verified_input_count"] == 4
    assert result["verified_reference_run_count"] == 16
    assert not arguments.output.exists()
    assert not arguments.scratch.exists()


def test_replay_remains_closed_without_separate_exact_decision() -> None:
    """Implementation approval cannot become cumulative replay authority."""
    wrapper = runpy.run_path(str(_WRAPPER))

    with pytest.raises(ValueError, match="cumulative replay not authorized"):
        wrapper["run_authorized_replay"](
            _approved_arguments(),
            execution_decision_path=Path("missing-execution-decision.json"),
        )


def test_authorized_replay_traverses_source_reconstruction_predecessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Execution descends through measurement repair to source association."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["run_authorized_replay"].__globals__
    events: list[str] = []
    frozen: dict[str, Any] = {"main": lambda: events.append("main")}
    current = {"_load_frozen_replay": lambda: frozen}

    def install_source_association(
        current_wrapper: dict[str, Any],
        frozen_wrapper: dict[str, Any],
        provenance: dict[str, object],
        *,
        verified_reference: object,
    ) -> None:
        assert current_wrapper is current
        assert frozen_wrapper is frozen
        assert provenance == {"execution": "authorized"}
        assert verified_reference == "verified-reference"
        events.append("source-association")

    source_association = {
        "_load_current_wrapper": lambda: current,
        "_install_source_association_composition": install_source_association,
    }
    measurement_repair = {
        "_load_consumed_wrapper": lambda: source_association,
    }
    source_reconstruction = {
        "_load_consumed_wrapper": lambda: measurement_repair,
    }

    def authorize(
        _arguments: Namespace,
        _decision: Path,
    ) -> dict[str, object]:
        return {"execution": "authorized"}

    def verify_reference(_arguments: Namespace) -> str:
        return "verified-reference"

    def install_parent(frozen_wrapper: dict[str, Any]) -> None:
        events.append("parent" if frozen_wrapper is frozen else "wrong-frozen")

    monkeypatch.setitem(
        globals_,
        "_authorize_replay",
        authorize,
    )
    monkeypatch.setitem(
        globals_,
        "_verify_reference_reconstruction",
        verify_reference,
    )
    monkeypatch.setitem(
        globals_,
        "_load_consumed_wrapper",
        lambda: source_reconstruction,
    )
    monkeypatch.setitem(
        globals_,
        "_install_parent_construction_static_seams",
        install_parent,
    )

    wrapper["run_authorized_replay"](
        _approved_arguments(),
        execution_decision_path=Path("authorized-decision.json"),
    )

    assert events == ["source-association", "parent", "main"]


def test_candidate_worker_reuses_the_verified_composition_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spawned workers resolve the same frozen replay as the parent process."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_generate_candidate_product"].__globals__
    task = {"input_id": "continuum-0001"}

    def generate(value: dict[str, object]) -> str:
        return "candidate-product" if value is task else "wrong-task"

    frozen: dict[str, Any] = {"_generate_candidate_product": generate}
    events: list[str] = []

    def load_composition() -> tuple[
        dict[str, Any], dict[str, Any], dict[str, Any]
    ]:
        return {}, {}, frozen

    def install_parent(frozen_wrapper: dict[str, Any]) -> None:
        events.append("parent" if frozen_wrapper is frozen else "wrong-frozen")

    monkeypatch.setitem(
        globals_,
        "_load_source_association_composition",
        load_composition,
    )
    monkeypatch.setitem(
        globals_,
        "_install_parent_construction_static_seams",
        install_parent,
    )

    result = wrapper["_generate_candidate_product"](task)

    assert result == "candidate-product"
    assert events == ["parent"]


def test_composition_preserves_compact_and_overlays_parent_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the candidate identity and future Continuum builder change."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_install_parent_construction_static_seams"].__globals__

    def consumed_installer(frozen: dict[str, Any]) -> None:
        frozen["consumed_installed"] = True

    monkeypatch.setitem(
        globals_,
        "_load_consumed_wrapper",
        lambda: {
            "_install_source_reconstruction_static_seams": (consumed_installer)
        },
    )

    def write_continuum_products() -> None:
        return None

    compact = object()
    frozen: dict[str, Any] = {
        "_write_compact_products": compact,
        "_write_continuum_products": write_continuum_products,
    }

    wrapper["_install_parent_construction_static_seams"](frozen)

    assert frozen["consumed_installed"] is True
    assert frozen["_CANDIDATE_REVISION"] == _REVISION
    assert frozen["_candidate_configuration_sha256"]() == _CONFIGURATION
    assert frozen["_write_compact_products"] is compact


def test_parent_decision_authorizes_identity_freeze_but_not_replay() -> None:
    """The exact implementation approval cannot open scientific execution."""
    decision = json.loads(_DECISION.read_text(encoding="utf-8"))
    authorization = decision["authorization"]

    assert authorization["candidate_identity_freeze_authorized"] is True
    assert authorization["replay_identity_freeze_authorized"] is True
    assert authorization["cumulative_replay_authorized"] is False
    assert authorization["viewed_data_execution_authorized"] is False
    assert authorization["campaign_execution_authorized"] is False
