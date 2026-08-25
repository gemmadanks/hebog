"""Freeze boundary for the approved final Phase 5 qualification design."""

from __future__ import annotations

import json
import runpy
from collections.abc import Callable
from pathlib import Path

import pytest

from hebog.validation.datasets import DatasetManifest, iter_dataset_recipes
from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_SCRIPT = (
    _ROOT
    / "scripts/validation/freeze_phase5_final_qualification_population.py"
)


def _source_identity(expected: str) -> Callable[[Path], str]:
    """Return one deterministic source-tree identity stand-in."""

    def source_tree_sha256(_: Path) -> str:
        return expected

    return source_tree_sha256


def _seeds(document: dict[str, object]) -> set[int]:
    """Return every independent seed in one manifest document."""
    manifest = DatasetManifest.model_validate(document)
    return {
        recipe.seed
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }


def test_final_qualification_freezer_builds_only_approved_continuum() -> None:
    """The approved design has four fresh qualification geometries."""
    namespace = runpy.run_path(str(_SCRIPT))
    build = namespace["build_final_qualification_documents"]
    build.__globals__["source_tree_sha256"] = _source_identity(
        namespace["_CANDIDATE_SOURCE_TREE_SHA256"]
    )

    manifest, freeze = build(
        repository_root=_ROOT,
        continuum_template_path=(
            _ROOT / "config/datasets/phase-5-external-recovery-continuum.json"
        ),
        power_review_path=(
            _ROOT
            / "benchmark-results/phase-5/viewed-recovery-power-review.json"
        ),
        compact_qualification_path=(
            _ROOT / "benchmark-results/phase-4u/qualification-decision.json"
        ),
        compact_regression_path=(
            _ROOT / "benchmark-results/phase-5/"
            "phase-4-compact-regression-58074cc-decision.json"
        ),
    )
    loaded = DatasetManifest.model_validate(manifest)
    seeds = _seeds(manifest)
    historical: set[int] = set()
    for path in sorted((_ROOT / "config/datasets").glob("*.json")):
        if path.name == "phase-5-final-qualification-continuum.json":
            continue
        previous = DatasetManifest.model_validate_json(path.read_bytes())
        historical.update(
            recipe.seed
            for dataset in previous.datasets
            for recipe in iter_dataset_recipes(dataset)
        )

    assert loaded.manifest_id == "phase-5-final-qualification-continuum"
    assert len(loaded.datasets) == 4
    assert {dataset.role.value for dataset in loaded.datasets} == {
        "qualification"
    }
    assert {
        len(dataset.noise_realization_seeds) + 1 for dataset in loaded.datasets
    } == {422}
    assert len(seeds) == 1688
    assert historical.isdisjoint(seeds)
    assert freeze["scientific_approval"] == {
        "reviewer": "Gemma Danks",
        "approved_on": "2026-08-25",
        "scope": (
            "final-qualification-population-freeze-with-closed-compact-"
            "evidence-only-no-execution"
        ),
    }
    assert freeze["candidate"]["revision"] == (
        "90626641c8705ba9d55fdea02a705983528b8aa0"
    )
    assert freeze["population"]["image_count"] == 1688
    assert freeze["population"]["geometry_count"] == 4
    assert freeze["compact_evidence"]["fresh_compact_lane_required"] is False
    assert freeze["execution_authorized"] is False
    assert freeze["qualification_opened"] is False
    assert freeze["finder_output_generated"] is False


def test_final_qualification_freezer_matches_frozen_identities() -> None:
    """The generated manifest and immutable freeze cannot drift."""
    namespace = runpy.run_path(str(_SCRIPT))
    build = namespace["build_final_qualification_documents"]
    build.__globals__["source_tree_sha256"] = _source_identity(
        namespace["_CANDIDATE_SOURCE_TREE_SHA256"]
    )
    manifest, freeze = build(
        repository_root=_ROOT,
        continuum_template_path=(
            _ROOT / "config/datasets/phase-5-external-recovery-continuum.json"
        ),
        power_review_path=(
            _ROOT
            / "benchmark-results/phase-5/viewed-recovery-power-review.json"
        ),
        compact_qualification_path=(
            _ROOT / "benchmark-results/phase-4u/qualification-decision.json"
        ),
        compact_regression_path=(
            _ROOT / "benchmark-results/phase-5/"
            "phase-4-compact-regression-58074cc-decision.json"
        ),
    )
    manifest_path = (
        _ROOT / "config/datasets/phase-5-final-qualification-continuum.json"
    )
    expected_manifest = (
        json.dumps(
            manifest,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    assert manifest_path.read_text(encoding="utf-8") == expected_manifest

    freeze_path = (
        _ROOT / "config/contracts/phase-5-final-qualification-population.json"
    )
    checked_freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert freeze["population"]["manifest_sha256"] == file_sha256(
        manifest_path
    )
    assert checked_freeze["generator"]["sha256"] == file_sha256(_SCRIPT)
    assert file_sha256(freeze_path) == (
        "4a52f55114962d24d6371b166d393c3421a74156fa1c48305931fb39a631e5ac"
    )


def test_final_qualification_freezer_fails_closed_on_evidence_drift(
    tmp_path: Path,
) -> None:
    """Power, compact, and candidate identity changes require new review."""
    namespace = runpy.run_path(str(_SCRIPT))
    build = namespace["build_final_qualification_documents"]
    build.__globals__["source_tree_sha256"] = _source_identity("0" * 64)
    arguments = {
        "repository_root": _ROOT,
        "continuum_template_path": (
            _ROOT / "config/datasets/phase-5-external-recovery-continuum.json"
        ),
        "power_review_path": (
            _ROOT
            / "benchmark-results/phase-5/viewed-recovery-power-review.json"
        ),
        "compact_qualification_path": (
            _ROOT / "benchmark-results/phase-4u/qualification-decision.json"
        ),
        "compact_regression_path": (
            _ROOT / "benchmark-results/phase-5/"
            "phase-4-compact-regression-58074cc-decision.json"
        ),
    }
    with pytest.raises(ValueError, match="approved candidate source tree"):
        build(**arguments)

    build.__globals__["source_tree_sha256"] = _source_identity(
        namespace["_CANDIDATE_SOURCE_TREE_SHA256"]
    )
    compact = json.loads(arguments["compact_regression_path"].read_text())
    compact["passed"] = False
    changed = tmp_path / "compact.json"
    changed.write_text(json.dumps(compact), encoding="utf-8")
    arguments["compact_regression_path"] = changed
    with pytest.raises(ValueError, match="compact evidence changed"):
        build(**arguments)
