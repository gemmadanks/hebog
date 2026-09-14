"""Behavioral contracts for the compact held-out sentinel tooling."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any, cast

import pytest

from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRole,
    iter_dataset_recipes,
)

_ROOT = Path(__file__).parents[3]
_POPULATION = _ROOT / "scripts/validation/phase5_compact_held_out_sentinel.py"
_COMPILER = (
    _ROOT / "scripts/validation/compile_phase5_compact_held_out_sentinel.py"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/evaluate_phase5_compact_held_out_sentinel.py"
)


def _program(path: Path) -> dict[str, Any]:
    """Load one script without invoking its command-line entry point."""
    return runpy.run_path(str(path))


def _all_seeds(manifest: DatasetManifest) -> tuple[int, ...]:
    """Return every realization seed in manifest order."""
    return tuple(
        recipe.seed
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    )


def test_population_is_exact_fresh_balanced_and_bounded() -> None:
    """The small sentinel must not quietly expand into another campaign."""
    population = _program(_POPULATION)
    manifest = population["build_manifest"]()
    audit = population["audit_manifest"](_ROOT, manifest)
    seeds = _all_seeds(manifest)

    assert manifest.manifest_id == "phase-5-compact-held-out-sentinel"
    assert len(manifest.datasets) == 42
    assert len(seeds) == 168
    assert seeds == tuple(range(2026970001, 2026970169))
    assert len(set(seeds)) == len(seeds)
    assert {dataset.role for dataset in manifest.datasets} == {
        DatasetRole.QUALIFICATION
    }
    assert {dataset.recipe.shape_yx for dataset in manifest.datasets} == {
        (384, 512),
        (512, 512),
    }
    assert audit == {
        "historical_manifest_count": 46,
        "historical_registry_canonical_sha256": (
            "47aca0c78cd75b2e336148baa89a2354a72900c19ea84b3145788c1de519c160"
        ),
        "historical_seed_count": 20917,
        "prospective_seed_count": 168,
        "seed_disjoint": True,
    }


def test_compact_guards_cover_the_declared_failure_modes() -> None:
    """Compact recipes must contain the geometry they claim to guard."""
    manifest = _program(_POPULATION)["build_manifest"]()
    compact = {
        dataset.identifier: dataset
        for dataset in manifest.datasets
        if "compact-guard" in dataset.identifier
    }

    assert len(compact) == 6
    assert sorted(len(item.recipe.sources) for item in compact.values()) == [
        1,
        1,
        1,
        2,
        2,
        3,
    ]
    assert any(item.recipe.shape_yx == (384, 512) for item in compact.values())
    assert any(item.recipe.invalid_rectangles for item in compact.values())
    assert any(
        source.x_pixel < 5 or source.y_pixel < 5
        for item in compact.values()
        for source in item.recipe.sources
    )
    three_peak = next(
        item for item in compact.values() if len(item.recipe.sources) == 3
    )
    assert all(
        248 <= value <= 264
        for source in three_peak.recipe.sources
        for value in (source.x_pixel, source.y_pixel)
    )


def _summary(
    *,
    cell_id: str,
    seed: int,
    finder_id: str,
    completeness: float = 1.0,
    reliability: float = 1.0,
) -> dict[str, object]:
    """Build one minimal finite compiled summary for evaluator tests."""
    return {
        "cell_id": cell_id,
        "dataset_identifier": f"dataset-{cell_id}",
        "finder_id": finder_id,
        "input_id": f"{cell_id}-seed-{seed}",
        "metrics": {
            "absolute-mean-offset-x": [0.01],
            "absolute-mean-offset-y": [0.01],
            "completeness": completeness,
            "duplicate-fraction": 0.0,
            "integrated-flux-median": [0.04],
            "integrated-flux-p95": [0.04],
            "mask-iou": 0.95,
            "mask-precision": 0.98,
            "mask-recall": 0.97,
            "merge-fraction": 0.0,
            "position-median": [0.02],
            "position-p95": [0.02],
            "reliability": reliability,
            "split-fraction": 0.0,
        },
        "product_valid": True,
        "ownership_valid": True,
        "schema_version": 1,
        "seed": seed,
    }


def _paired_cell(cell_id: str) -> list[dict[str, object]]:
    """Build four exact paired observations for one sentinel cell."""
    return [
        _summary(cell_id=cell_id, seed=seed, finder_id=finder)
        for seed in range(1, 5)
        for finder in ("current-hebog", "released-pybdsf")
    ]


def _equal_dask_rows() -> tuple[dict[str, bool], ...]:
    """Return the structured equality evidence expected by the runner."""
    return tuple({"equal": True} for _index in range(12))


def test_evaluator_rejects_one_cell_regression_without_pooling() -> None:
    """Good cells cannot compensate for a bad cell in the one-look result."""
    evaluator = _program(_EVALUATOR)
    summaries = _paired_cell("good") + _paired_cell("bad")
    for item in summaries:
        if item["cell_id"] == "bad" and item["finder_id"] == "current-hebog":
            item["metrics"] = {
                **cast(dict[str, object], item["metrics"]),
                "completeness": 0.5,
            }

    decision = evaluator["evaluate_summaries"](
        summaries,
        expected_cell_ids=("bad", "good"),
        realizations_per_cell=4,
        dask_comparisons=_equal_dask_rows(),
    )

    assert decision["status"] == "fail"
    assert decision["passed"] is False
    assert decision["cell_decisions"][0]["cell_id"] == "bad"
    assert (
        "completeness-pybdsf-parity"
        in decision["cell_decisions"][0]["failure_reasons"]
    )
    assert decision["pooling_used"] is False


def test_evaluator_reports_unavailable_conditional_metric_as_failure() -> None:
    """A complete miss must fail scientifically rather than crash the run."""
    evaluator = _program(_EVALUATOR)
    summaries = _paired_cell("missing")
    for item in summaries:
        cast(dict[str, object], item["metrics"])["position-p95"] = []

    decision = evaluator["evaluate_summaries"](
        summaries,
        expected_cell_ids=("missing",),
        realizations_per_cell=4,
        dask_comparisons=_equal_dask_rows(),
    )

    assert decision["status"] == "fail"
    assert decision["cell_decisions"][0]["metrics"]["position-p95"] == {
        "candidate_cell_median": None,
        "passed": False,
        "positive_regression": None,
        "practical_regression_margin": 0.05,
        "released_pybdsf_cell_median": None,
    }


def test_evaluator_rejects_unstructured_dask_equality_tokens() -> None:
    """A truthy fixture token cannot stand in for executor evidence."""
    evaluator = _program(_EVALUATOR)

    with pytest.raises(
        ValueError,
        match="all 12 existing-Dask comparisons must equal Serial",
    ):
        evaluator["evaluate_summaries"](
            _paired_cell("cell"),
            expected_cell_ids=("cell",),
            realizations_per_cell=4,
            dask_comparisons=tuple("equal" for _index in range(12)),
        )


def test_compiler_requires_every_exact_pair_and_no_extra_summary() -> None:
    """Compilation retains the denominator and rejects undeclared rows."""
    compiler = _program(_COMPILER)
    expected = tuple(
        (f"cell-seed-{seed}", finder)
        for seed in range(1, 5)
        for finder in ("current-hebog", "released-pybdsf")
    )
    summaries = _paired_cell("cell")

    assert compiler["compile_summaries"](
        summaries, expected_pairs=expected
    ) == tuple(summaries)
    with pytest.raises(ValueError, match="summary population is incomplete"):
        compiler["compile_summaries"](summaries[:-1], expected_pairs=expected)
    with pytest.raises(ValueError, match="summary population has extras"):
        compiler["compile_summaries"](
            [*summaries, _summary(cell_id="extra", seed=9, finder_id="x")],
            expected_pairs=expected,
        )
