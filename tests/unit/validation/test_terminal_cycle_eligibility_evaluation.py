# pyright: reportPrivateUsage=false
"""Prospective terminal-cycle eligibility evaluation contracts."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationResult,
    SourceHierarchyDiagnostics,
)
from hebog.validation.terminal_cycle_eligibility_evaluation import (
    TerminalCycleEligibilityContinuumImageCompiler,
    aggregate_terminal_cycle_eligibility,
    install_terminal_cycle_eligibility_evaluation,
    load_source_association,
    source_association_from_json,
)
from hebog.validation.terminal_feature_persistence_evaluation import (
    TerminalFeaturePersistenceContinuumImageCompiler,
)


def _association(*, multiplier: int = 1) -> SourceAssociationResult:
    """Return one source with non-zero prospective diagnostics."""
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
            terminal_cycle_candidate_count=3 * multiplier,
            terminal_cycle_parent_count=2 * multiplier,
            rejected_terminal_cycle_count=1 * multiplier,
            terminal_persistence_exact_feature_count=5 * multiplier,
            terminal_persistence_displaced_candidate_count=7 * multiplier,
            terminal_persistence_displaced_accepted_count=4 * multiplier,
            terminal_persistence_missing_child_count=2 * multiplier,
            terminal_persistence_ambiguous_child_count=1 * multiplier,
            terminal_persistence_conflict_count=1 * multiplier,
            terminal_cycle_pre_eligibility_candidate_count=4 * multiplier,
            terminal_cycle_unseeded_candidate_count=2 * multiplier,
            terminal_cycle_unseeded_persistent_accepted_count=1 * multiplier,
            terminal_cycle_unseeded_persistence_rejected_count=1 * multiplier,
        ),
    )


def _write(path: Path, association: SourceAssociationResult) -> None:
    """Write one canonical fixture sidecar."""
    path.write_text(
        json.dumps(asdict(association), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_parser_requires_and_retains_cycle_eligibility_diagnostics() -> None:
    """The prospective parser cannot silently default its new census."""
    association = _association()
    document = json.loads(json.dumps(asdict(association)))

    assert source_association_from_json(document) == association

    diagnostics = cast(dict[str, object], document["hierarchy_diagnostics"])
    diagnostics.pop("terminal_cycle_unseeded_candidate_count")
    with pytest.raises(ValueError, match="candidate_count must be an integer"):
        source_association_from_json(document)


def test_aggregate_is_bounded_canonical_and_additive(tmp_path: Path) -> None:
    """One aggregate retains only mechanism counts and image cardinality."""
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write(first, _association())
    _write(second, _association(multiplier=2))

    aggregate = aggregate_terminal_cycle_eligibility(
        (second, first),
        expected_image_count=2,
    )

    assert aggregate == {
        "image_count": 2,
        "pre_eligibility_candidate_count": 12,
        "schema_version": 1,
        "unseeded_candidate_count": 6,
        "unseeded_persistence_rejected_count": 3,
        "unseeded_persistent_accepted_count": 3,
    }


def test_aggregate_fails_closed_on_incomplete_or_duplicate_set(
    tmp_path: Path,
) -> None:
    """The aggregate cannot summarize incomplete or aliased evidence."""
    path = tmp_path / "association.json"
    _write(path, _association())

    with pytest.raises(ValueError, match="count differs"):
        aggregate_terminal_cycle_eligibility(
            (path,),
            expected_image_count=2,
        )
    with pytest.raises(ValueError, match="paths must be unique"):
        aggregate_terminal_cycle_eligibility(
            (path, path),
            expected_image_count=2,
        )
    with pytest.raises(ValueError, match="positive integer"):
        aggregate_terminal_cycle_eligibility((), expected_image_count=0)


def test_aggregate_requires_diagnostics_on_every_sidecar(
    tmp_path: Path,
) -> None:
    """A sidecar without the prospective census is inadmissible."""
    path = tmp_path / "association.json"
    _write(path, replace(_association(), hierarchy_diagnostics=None))

    with pytest.raises(ValueError, match="diagnostics are required"):
        aggregate_terminal_cycle_eligibility(
            (path,),
            expected_image_count=1,
        )


def test_loader_rejects_unreadable_sidecar(tmp_path: Path) -> None:
    """Malformed JSON cannot enter the prospective evaluator."""
    path = tmp_path / "association.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot be loaded"):
        load_source_association(path)


def test_compiler_validates_hebog_then_delegates_closed_science(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Only successful Hebog rows require eligibility diagnostics."""
    path = tmp_path / "association.json"
    _write(path, _association())
    compiler = object.__new__(TerminalCycleEligibilityContinuumImageCompiler)

    def association_path(_run: object) -> Path:
        return path

    compiler._association_path = association_path
    calls: list[str] = []

    def closed(*_args: object, **_kwargs: object) -> dict[str, object]:
        calls.append("closed")
        return {"science": "delegated"}

    monkeypatch.setattr(
        TerminalFeaturePersistenceContinuumImageCompiler,
        "__call__",
        closed,
    )
    hebog = SimpleNamespace(
        result=SimpleNamespace(status="success", finder_id="hebog")
    )
    reference = SimpleNamespace(
        result=SimpleNamespace(status="success", finder_id="released-pybdsf")
    )

    assert compiler(None, None, hebog, None, None, None, ()) == {
        "science": "delegated"
    }
    compiler(
        verified=None,
        campaign_input=None,
        run=reference,
        dataset=None,
        recipe=None,
        review=None,
        specifications=(),
    )
    assert calls == ["closed", "closed"]


def test_installer_requires_terminal_persistence_predecessor() -> None:
    """The prospective overlay layers only over its frozen predecessor."""
    current = object.__new__(TerminalFeaturePersistenceContinuumImageCompiler)

    def candidate_objects(*_args: object, **_kwargs: object) -> tuple[()]:
        return ()

    terminal: dict[str, object] = {
        "_continuum_image_observations": current,
        "_candidate_objects": candidate_objects,
    }

    def path(_run: object) -> Path:
        return Path("association.json")

    install_terminal_cycle_eligibility_evaluation(
        terminal,
        association_path=path,
    )

    assert isinstance(
        terminal["_continuum_image_observations"],
        TerminalCycleEligibilityContinuumImageCompiler,
    )
    with pytest.raises(ValueError, match="seam changed"):
        install_terminal_cycle_eligibility_evaluation(
            {"_continuum_image_observations": object()},
            association_path=path,
        )
