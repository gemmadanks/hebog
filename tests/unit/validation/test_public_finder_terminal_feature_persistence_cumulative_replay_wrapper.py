# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
"""Contracts for the non-executable terminal-feature replay wrapper."""

from __future__ import annotations

import json
import runpy
from argparse import Namespace
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationResult,
    SourceHierarchyDiagnostics,
)
from hebog.validation.external_runners import file_sha256
from hebog.validation.parent_construction_association_evaluation import (
    ParentConstructionContinuumImageCompiler,
)

_ROOT = Path(__file__).parents[3]
_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_terminal_feature_"
    "persistence_cumulative_regressions.py"
)
_CONSUMED_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_terminal_parent_"
    "correction_cumulative_regressions.py"
)
_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-feature-"
    "persistence-implementation-decision.json"
)
_READINESS = (
    _ROOT / "config/contracts/phase-5-terminal-feature-persistence-"
    "readiness.json"
)
_REVISION = "3d080f78da09ada6753a4e5df898e1d5daa59597"
_SOURCE_TREE = (
    "a25d22d80f4e639e4543ee058acade6feda15105f6325dc909e69fcfb8f03924"
)
_CONFIGURATION = (
    "2d6ab6bbdd06f109f9703fb0b49f489933ddc00b391f681253693b38d0f4b1de"
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
            "public-finder-terminal-feature-persistence.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-terminal-feature-"
            "persistence-3d080f7"
        ),
        workers=2,
        closed_component_baseline_ledger=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
    )


def _association() -> SourceAssociationResult:
    """Return one minimal association with the prospective census."""
    return SourceAssociationResult(
        components=(
            DetectionComponentRecord(
                component_id="component-one",
                label_value=1,
                canonical_pixel_yx=(0, 0),
                centroid_yx=(0.0, 0.0),
                covariance_pixels_squared=None,
            ),
        ),
        edges=(),
        memberships=(
            CatalogueSourceMembership(
                source_id="source-one",
                component_ids=("component-one",),
            ),
        ),
        ambiguous_component_ids=(),
        hierarchy_diagnostics=SourceHierarchyDiagnostics(
            direct_component_count=1,
            catalogue_source_count=1,
            membership_size_histogram=((1, 1),),
            unattached_component_count=0,
            multiple_finest_feature_attachment_count=0,
            branched_lineage_count=0,
            no_common_convergence_count=0,
            unique_convergence_count=1,
            per_scale_feature_counts=((1, 1),),
            adjacent_scale_parent_edge_count=0,
            scale_aware_parent_candidate_count=0,
            persistent_parent_count=0,
            rejected_parent_ambiguity_count=0,
            per_scale_parent_candidate_counts=((1, 0),),
            terminal_cycle_candidate_count=1,
            terminal_cycle_parent_count=1,
            terminal_persistence_displaced_candidate_count=1,
            terminal_persistence_displaced_accepted_count=1,
        ),
    )


def _write_marker(
    wrapper: dict[str, Any],
    directory: Path,
    *,
    with_sidecar: bool,
) -> None:
    """Write one exact fixture marker and its optional sidecar."""
    directory.mkdir()
    artifacts: list[dict[str, object]] = []
    if with_sidecar:
        sidecar = directory / "source_association.json"
        sidecar.write_text(
            json.dumps(asdict(_association()), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifacts.append(
            {
                "role": "source-association-json",
                "relative_path": sidecar.name,
                "byte_count": sidecar.stat().st_size,
                "sha256": file_sha256(sidecar),
            }
        )
    marker = {
        "schema_version": 1,
        "input_id": directory.name,
        "configuration_sha256": wrapper["_CANDIDATE_CONFIGURATION_SHA256"],
        "source_tree_sha256": wrapper["_CANDIDATE_SOURCE_TREE_SHA256"],
        "artifacts": artifacts,
    }
    (directory / "complete.json").write_text(
        json.dumps(marker, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_wrapper_binds_exact_candidate_and_predecessor() -> None:
    """The wrapper names one candidate and one frozen predecessor."""
    wrapper = runpy.run_path(str(_WRAPPER))

    assert wrapper["_CANDIDATE_REVISION"] == _REVISION
    assert wrapper["_CANDIDATE_SOURCE_TREE_SHA256"] == _SOURCE_TREE
    assert wrapper["_CANDIDATE_CONFIGURATION_SHA256"] == _CONFIGURATION
    assert wrapper["_candidate_configuration_sha256"]() == _CONFIGURATION
    assert wrapper["_CONSUMED_WRAPPER_SHA256"] == file_sha256(
        _CONSUMED_WRAPPER
    )
    assert wrapper["_READINESS_SHA256"] == file_sha256(_READINESS)
    assert wrapper["_PROSPECTIVE_OUTPUT_PATH"] == _approved_arguments().output
    assert wrapper["_PROSPECTIVE_SCRATCH_PATH"] == (
        _approved_arguments().scratch
    )


def test_readiness_overlay_rebinds_only_candidate_evidence() -> None:
    """Historical readiness stays frozen behind the prospective overlay."""
    readiness = json.loads(_READINESS.read_text(encoding="utf-8"))
    assert readiness["status"] == "frozen-non-executable-overlay"
    assert readiness["parent_readiness"]["sha256"] == (
        "fb295c16b5a67618b242891dc048c4290b88ff8ceaecf81a7ad409b015f8c137"
    )
    assert not any(readiness["authorization"].values())
    for evidence in readiness["required_evidence"]:
        fields = evidence["required_fields"]
        assert fields["candidate_revision"] == _REVISION
        assert fields["candidate_source_tree_sha256"] == _SOURCE_TREE
        assert fields["candidate_configuration_sha256"] == _CONFIGURATION


def test_completed_sidecar_aggregate_verifies_exact_markers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The bounded ledger census accepts one exact Continuum sidecar."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_aggregate_completed_sidecars"].__globals__
    monkeypatch.setitem(globals_, "_EXPECTED_INPUT_COUNT", 2)
    monkeypatch.setitem(globals_, "_EXPECTED_CONTINUUM_COUNT", 1)
    products = tmp_path / "products"
    products.mkdir()
    _write_marker(wrapper, products / "compact-1", with_sidecar=False)
    _write_marker(wrapper, products / "continuum-1", with_sidecar=True)

    aggregate = wrapper["_aggregate_completed_sidecars"](tmp_path)

    assert aggregate["image_count"] == 1
    assert aggregate["displaced_candidate_count"] == 1
    assert aggregate["displaced_accepted_count"] == 1

    sidecar = products / "continuum-1" / "source_association.json"
    sidecar.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sidecar identity changed"):
        wrapper["_aggregate_completed_sidecars"](tmp_path)


def test_marker_rejects_unsafe_and_duplicate_sidecars(tmp_path: Path) -> None:
    """Marker paths cannot escape or alias the governed sidecar."""
    wrapper = runpy.run_path(str(_WRAPPER))
    directory = tmp_path / "continuum-1"
    _write_marker(wrapper, directory, with_sidecar=True)
    marker_path = directory / "complete.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    record = marker["artifacts"][0]
    record["relative_path"] = "../source_association.json"
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(ValueError, match="path is unsafe"):
        wrapper["_marker_sidecar"](directory)

    record["relative_path"] = "source_association.json"
    marker["artifacts"].append(dict(record))
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate associations"):
        wrapper["_marker_sidecar"](directory)


def test_static_seams_validate_sidecar_compile_and_ledger_census(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The three prospective seams compose after the exact predecessor."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper[
        "_install_terminal_feature_persistence_static_seams"
    ].__globals__
    events: list[str] = []

    def writer(*_args: object, **_kwargs: object) -> dict[str, Path]:
        sidecar = tmp_path / "association.json"
        sidecar.write_text(
            json.dumps(asdict(_association()), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {"source-association-json": sidecar}

    def installer(
        compiler_globals: dict[str, Any],
        _prospective: object,
        _configuration: str,
    ) -> None:
        compiler_globals["_continuum_image_observations"] = object.__new__(
            ParentConstructionContinuumImageCompiler
        )
        events.append("predecessor")

    frozen: dict[str, Any] = {
        "_write_continuum_products": writer,
        "_install_prospective_compiler": installer,
        "_canonical_json_bytes": lambda value: (
            json.dumps(value, sort_keys=True).encode() + b"\n"
        ),
    }
    monkeypatch.setitem(
        globals_,
        "_load_consumed_wrapper",
        lambda: {
            "_install_terminal_parent_static_seams": lambda _frozen: None
        },
    )

    def install(
        compiler_globals: dict[str, Any],
        *,
        association_path: object,
    ) -> None:
        assert callable(association_path)
        events.append("terminal-feature")
        compiler_globals["prospective"] = True

    monkeypatch.setitem(
        globals_, "install_terminal_feature_persistence_evaluation", install
    )
    monkeypatch.setitem(
        globals_,
        "_aggregate_completed_sidecars",
        lambda _scratch: {"image_count": 1600},
    )

    wrapper["_install_terminal_feature_persistence_static_seams"](frozen)

    assert frozen["_write_continuum_products"]()[
        "source-association-json"
    ].is_file()
    compiler_globals: dict[str, Any] = {}
    frozen["_install_prospective_compiler"](
        compiler_globals, SimpleNamespace(), _CONFIGURATION
    )
    assert events == ["predecessor", "terminal-feature"]
    ledger = json.loads(
        frozen["_canonical_json_bytes"](
            {"ledger_id": "phase-5-cumulative-regression-ledger"}
        )
    )
    assert ledger["terminal_feature_persistence_diagnostics"] == {
        "image_count": 1600
    }
    assert ledger["terminal_feature_persistence_provenance"] == {
        "evaluator_program_sha256": wrapper["_EVALUATOR_PROGRAM_SHA256"],
        "implementation_decision_sha256": wrapper[
            "_TERMINAL_FEATURE_IMPLEMENTATION_DECISION_SHA256"
        ],
        "pre_review_sha256": wrapper["_TERMINAL_FEATURE_PRE_REVIEW_SHA256"],
    }


def test_complete_verifier_is_no_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Complete verification proves seams without creating replay state."""
    wrapper = runpy.run_path(str(_WRAPPER))
    arguments = _approved_arguments()
    arguments.output = tmp_path / "ledger.json"
    arguments.scratch = tmp_path / "scratch"
    globals_ = wrapper[
        "verify_terminal_feature_persistence_replay_composition"
    ].__globals__
    monkeypatch.setitem(
        globals_, "_require_common_identities", lambda _arguments: "revision"
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
            "_install_terminal_parent_static_seams": lambda _frozen: None
        },
    )

    result = wrapper["verify_terminal_feature_persistence_replay_composition"](
        arguments, implementation_decision_path=_DECISION
    )

    assert result["status"] == "pass"
    assert result["verified_input_count"] == 2400
    assert result["verified_reference_run_count"] == 9600
    assert result["terminal_persistence_sidecar_validation_verified"] is True
    assert (
        result["terminal_persistence_evaluator_installation_verified"] is True
    )
    assert result["terminal_persistence_census_aggregation_verified"] is True
    assert not arguments.output.exists()
    assert not arguments.scratch.exists()


def test_replay_remains_closed_without_exact_execution_decision() -> None:
    """Implementation authority cannot bypass a later exact approval."""
    wrapper = runpy.run_path(str(_WRAPPER))

    with pytest.raises(ValueError, match="cumulative replay not authorized"):
        wrapper["run_authorized_replay"](
            _approved_arguments(),
            execution_decision_path=Path("missing-execution-decision.json"),
        )


def test_worker_reinstalls_same_terminal_feature_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spawned workers cannot fall back to the terminal-parent candidate."""
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
        "_install_terminal_feature_persistence_static_seams",
        lambda value: events.append("installed" if value is frozen else "bad"),
    )

    assert wrapper["_generate_candidate_product"]({"input_id": "c-1"}) == (
        "c-1"
    )
    assert events == ["installed"]


def test_invocation_rejects_namespace_drift() -> None:
    """The write-once output and worker count are exact identities."""
    wrapper = runpy.run_path(str(_WRAPPER))
    arguments = _approved_arguments()
    wrapper["_require_exact_invocation"](arguments)
    arguments.workers = 3
    with pytest.raises(ValueError, match="workers changed"):
        wrapper["_require_exact_invocation"](arguments)
