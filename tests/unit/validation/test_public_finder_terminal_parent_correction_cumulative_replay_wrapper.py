# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
"""Contracts for the fail-closed terminal-parent cumulative replay."""

from __future__ import annotations

import json
import runpy
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hebog.data_models.source_association import SourceAssociationResult
from hebog.validation.external_runners import file_sha256
from hebog.validation.parent_construction_association_evaluation import (
    ParentConstructionContinuumImageCompiler,
)

_ROOT = Path(__file__).parents[3]
_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_terminal_parent_"
    "correction_cumulative_regressions.py"
)
_CONSUMED_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_source_hierarchy_"
    "parent_construction_cumulative_regressions.py"
)
_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-parent-"
    "correction-implementation-decision.json"
)
_READINESS = _ROOT / "config/contracts/phase-5-readiness.json"
_REVISION = "85d580713664b962ae256a98b065849cf8eb9283"
_SOURCE_TREE = (
    "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
)
_CONFIGURATION = (
    "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
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
            "public-finder-terminal-parent-correction.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-terminal-parent-"
            "correction-85d5807"
        ),
        workers=2,
        closed_component_baseline_ledger=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
    )


def test_wrapper_binds_exact_candidate_and_frozen_predecessor() -> None:
    """The prospective wrapper binds one candidate and historical wrapper."""
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


def test_readiness_names_only_terminal_parent_candidate_evidence() -> None:
    """Readiness cannot accept a prior parent-construction candidate."""
    readiness = json.loads(_READINESS.read_text(encoding="utf-8"))
    evidence = {
        item["evidence_id"]: item for item in readiness["required_evidence"]
    }
    cumulative = evidence[
        "public-finder-terminal-parent-correction-cumulative-regression"
    ]
    assert cumulative["path"] == str(_approved_arguments().output)
    required = cumulative["required_fields"]
    assert required["candidate_revision"] == _REVISION
    assert required["candidate_source_tree_sha256"] == _SOURCE_TREE
    assert required["candidate_configuration_sha256"] == _CONFIGURATION
    qualification = evidence[
        "public-finder-terminal-parent-correction-held-out-qualification"
    ]
    assert qualification["required_fields"]["candidate_revision"] == (
        _REVISION
    )


@dataclass(frozen=True)
class _Products:
    source_association: SourceAssociationResult


def test_continuum_writer_persists_validated_association_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The exact writer publishes association evidence with every shard."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_install_terminal_parent_static_seams"].__globals__
    association = SourceAssociationResult(
        components=(),
        edges=(),
        memberships=(),
        ambiguous_component_ids=(),
    )

    def builder(*_args: object, **_kwargs: object) -> _Products:
        return _Products(source_association=association)

    def writer(
        *_args: object, output: Path, **_kwargs: object
    ) -> dict[str, Path]:
        writer.__globals__["build_post_correction_continuum_products"]()
        catalogue = output / "segment_catalogue.json"
        catalogue.write_text("[]\n", encoding="utf-8")
        return {"segment-catalogue-json": catalogue}

    frozen: dict[str, Any] = {
        "_write_continuum_products": writer,
        "_install_prospective_compiler": lambda *_args: None,
        "_canonical_json_bytes": lambda value: (
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
        ),
    }
    monkeypatch.setitem(
        globals_,
        "_load_consumed_wrapper",
        lambda: {
            "_install_parent_construction_static_seams": lambda _frozen: None
        },
    )
    monkeypatch.setitem(
        globals_,
        "build_public_finder_source_reconstruction_continuum_products",
        builder,
    )

    wrapper["_install_terminal_parent_static_seams"](frozen)
    result = frozen["_write_continuum_products"](output=tmp_path)

    path = result["source-association-json"]
    assert path == tmp_path / "source_association.json"
    assert (
        wrapper["source_association_from_json"](
            json.loads(path.read_text(encoding="utf-8"))
        )
        == association
    )


def test_compiler_installer_composes_predecessor_then_sidecar_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compilation installs the verified sidecar-aware evaluator last."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_install_terminal_parent_static_seams"].__globals__
    events: list[str] = []

    def previous_installer(
        compiler_globals: dict[str, Any],
        _prospective: object,
        _configuration: str,
    ) -> None:
        compiler_globals["_continuum_image_observations"] = object()
        events.append("predecessor")

    frozen: dict[str, Any] = {
        "_write_continuum_products": lambda **_kwargs: {},
        "_install_prospective_compiler": previous_installer,
        "_canonical_json_bytes": lambda _value: b"{}\n",
    }
    monkeypatch.setitem(
        globals_,
        "_load_consumed_wrapper",
        lambda: {
            "_install_parent_construction_static_seams": lambda _frozen: None
        },
    )

    def install(
        compiler_globals: dict[str, Any],
        *,
        association_path: object,
    ) -> None:
        assert callable(association_path)
        compiler_globals["_continuum_image_observations"] = (
            ParentConstructionContinuumImageCompiler
        )
        events.append("association")

    monkeypatch.setitem(
        globals_,
        "install_parent_construction_association_evaluation",
        install,
    )

    wrapper["_install_terminal_parent_static_seams"](frozen)
    compiler_globals: dict[str, Any] = {}
    frozen["_install_prospective_compiler"](
        compiler_globals,
        SimpleNamespace(),
        _CONFIGURATION,
    )

    assert events == ["predecessor", "association"]
    assert compiler_globals["_continuum_image_observations"] is (
        ParentConstructionContinuumImageCompiler
    )


def test_association_artifact_path_fails_closed_on_missing_or_duplicate() -> (
    None
):
    """Evaluation accepts exactly one explicit association artifact."""
    wrapper = runpy.run_path(str(_WRAPPER))
    resolve = wrapper["_association_artifact_path"]
    directory = Path("candidate")
    missing = SimpleNamespace(
        directory=directory,
        result=SimpleNamespace(artifacts=()),
    )
    artifact = SimpleNamespace(
        role="source-association-json",
        relative_path="source_association.json",
    )

    with pytest.raises(ValueError, match="exactly one"):
        resolve(missing)
    with pytest.raises(ValueError, match="exactly one"):
        resolve(
            SimpleNamespace(
                directory=directory,
                result=SimpleNamespace(artifacts=(artifact, artifact)),
            )
        )
    assert (
        resolve(
            SimpleNamespace(
                directory=directory,
                result=SimpleNamespace(artifacts=(artifact,)),
            )
        )
        == directory / "source_association.json"
    )


def test_complete_verifier_is_no_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify retained evidence without creating replay state."""
    wrapper = runpy.run_path(str(_WRAPPER))
    arguments = _approved_arguments()
    arguments.output = tmp_path / "ledger.json"
    arguments.scratch = tmp_path / "scratch"
    globals_ = wrapper["verify_terminal_parent_replay_composition"].__globals__
    monkeypatch.setitem(
        globals_,
        "_require_common_identities",
        lambda _arguments: "execution-revision",
    )
    monkeypatch.setitem(
        globals_,
        "_verify_reference_reconstruction",
        lambda _arguments: SimpleNamespace(
            reference_reconstruction_sha256="a" * 64,
            inputs=tuple(range(2400)),
            runs=tuple(range(9600)),
        ),
    )
    frozen: dict[str, Any] = {
        "main": lambda: None,
        "_generate_candidate_product": lambda _task: "candidate",
        "_write_continuum_products": lambda **_kwargs: {},
        "_install_prospective_compiler": lambda *_args: None,
        "_canonical_json_bytes": lambda _value: b"{}\n",
    }
    monkeypatch.setitem(
        globals_,
        "_load_source_association_composition",
        lambda: (
            {
                "_install_source_association_composition": (
                    lambda *_args, **_kwargs: None
                )
            },
            {},
            frozen,
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_load_consumed_wrapper",
        lambda: {
            "_install_parent_construction_static_seams": lambda _frozen: None
        },
    )

    result = wrapper["verify_terminal_parent_replay_composition"](
        arguments,
        implementation_decision_path=_DECISION,
    )

    assert result["status"] == "pass"
    assert result["verified_input_count"] == 2400
    assert result["verified_reference_run_count"] == 9600
    assert result["association_sidecar_persistence_verified"] is True
    assert result["sidecar_aware_evaluator_installation_verified"] is True
    assert not arguments.output.exists()
    assert not arguments.scratch.exists()


def test_replay_remains_closed_without_exact_execution_decision() -> None:
    """Broad implementation authority cannot bypass the exact freeze."""
    wrapper = runpy.run_path(str(_WRAPPER))

    with pytest.raises(ValueError, match="cumulative replay not authorized"):
        wrapper["run_authorized_replay"](
            _approved_arguments(),
            execution_decision_path=Path("missing-execution-decision.json"),
        )


def test_worker_reinstalls_the_same_terminal_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spawned workers cannot fall back to an earlier candidate writer."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_generate_candidate_product"].__globals__
    frozen: dict[str, Any] = {
        "_generate_candidate_product": lambda task: task["input_id"]
    }
    events: list[str] = []
    monkeypatch.setitem(
        globals_,
        "_load_source_association_composition",
        lambda: ({}, {}, frozen),
    )
    monkeypatch.setitem(
        globals_,
        "_install_terminal_parent_static_seams",
        lambda value: events.append("installed" if value is frozen else "bad"),
    )

    result = wrapper["_generate_candidate_product"]({"input_id": "c-1"})

    assert result == "c-1"
    assert events == ["installed"]
