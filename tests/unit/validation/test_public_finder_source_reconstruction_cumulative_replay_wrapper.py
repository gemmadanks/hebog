"""Contracts for the non-executable source-reconstruction replay wrapper."""

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
    _ROOT
    / "scripts/validation/review_phase5_public_finder_source_reconstruction_"
    "cumulative_regressions.py"
)
_CONSUMED_WRAPPER = (
    _ROOT
    / "scripts/validation/review_phase5_public_finder_source_association_"
    "measurement_repair_cumulative_regressions.py"
)
_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "implementation-decision.json"
)
_READINESS = _ROOT / "config/contracts/phase-5-readiness.json"
_REVISION = "42c75f44b71800ae5fa1e0ebe1669caa7da59f85"
_SOURCE_TREE = (
    "1b67c7f6f768d6f83becc853a1ebd45b3996164cd2b87fdc0f71b9a3299e6bf1"
)
_CONFIGURATION = (
    "470e918db1a640d7393edc02de01fc57b50881b908bd6d5dac18a57709117bbb"
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
            "public-finder-source-reconstruction.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-source-reconstruction-"
            "42c75f4"
        ),
        workers=2,
        closed_component_baseline_ledger=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
    )


def test_wrapper_binds_clean_candidate_and_prospective_programs() -> None:
    """The wrapper composes only the approved candidate and evaluator."""
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


def test_readiness_is_prospectively_rebound_before_replay() -> None:
    """Final readiness requires the source-reconstruction evidence identity."""
    readiness = json.loads(_READINESS.read_text(encoding="utf-8"))
    evidence = {
        item["evidence_id"]: item for item in readiness["required_evidence"]
    }
    cumulative = evidence[
        "public-finder-source-reconstruction-cumulative-regression"
    ]
    assert cumulative["path"] == str(_approved_arguments().output)
    assert cumulative["required_fields"]["candidate_revision"] == _REVISION
    assert (
        cumulative["required_fields"]["candidate_source_tree_sha256"]
        == _SOURCE_TREE
    )
    assert (
        cumulative["required_fields"]["candidate_configuration_sha256"]
        == _CONFIGURATION
    )
    qualification = evidence[
        "public-finder-source-reconstruction-held-out-qualification"
    ]
    assert qualification["required_fields"]["candidate_revision"] == (
        _REVISION
    )


def test_fixture_verifier_is_no_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verification returns identities without creating replay state."""
    wrapper = runpy.run_path(str(_WRAPPER))
    arguments = _approved_arguments()
    globals_ = wrapper[
        "verify_source_reconstruction_replay_composition"
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

    result = wrapper["verify_source_reconstruction_replay_composition"](
        arguments,
        implementation_decision_path=_DECISION,
    )

    assert result["status"] == "pass"
    assert result["cumulative_replay_started"] is False
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


def test_composition_replaces_only_future_continuum_and_evaluator() -> None:
    """Compact and inherited frozen machinery stay unchanged."""
    wrapper = runpy.run_path(str(_WRAPPER))

    def candidate_configuration() -> str:
        return "old"

    def write_continuum_products() -> None:
        return None

    def install_prospective_compiler(_compiler: dict[str, Any]) -> None:
        return None

    frozen: dict[str, Any] = {
        "_CANDIDATE_REVISION": "old",
        "_candidate_configuration_sha256": candidate_configuration,
        "_write_compact_products": object(),
        "_write_continuum_products": write_continuum_products,
        "_install_prospective_compiler": install_prospective_compiler,
    }
    compact = frozen["_write_compact_products"]

    wrapper["_install_source_reconstruction_static_seams"](frozen)

    assert frozen["_CANDIDATE_REVISION"] == _REVISION
    assert frozen["_candidate_configuration_sha256"]() == _CONFIGURATION
    assert frozen["_write_compact_products"] is compact
    assert frozen["_install_prospective_compiler"] is not None
