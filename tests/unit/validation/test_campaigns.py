# pyright: reportPrivateUsage=false
"""Tests for reproducible Phase 4 paired-campaign assembly."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hebog.validation.campaigns import (
    _association_truth_source,
    _source_strata,
    diagnose_phase_four_realization,
    phase_four_truth_source,
)
from hebog.validation.comparison import (
    CatalogueOutlierThresholds,
    CatalogueSource,
)
from hebog.validation.datasets import (
    iter_dataset_recipes,
    load_dataset_manifest,
)

_ROOT = Path(__file__).parents[3]


def test_realization_diagnostics_retain_unmatched_association_group() -> None:
    """Group gates remain paired even when one unresolved blend is missed."""
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4-regression.json"
    ).datasets[1]
    recipe = iter_dataset_recipes(dataset)[0]
    candidates = tuple(
        phase_four_truth_source(
            recipe.sources[group.source_indices[0]],
            dataset,
            identifier=f"candidate-{group.identifier}",
        )
        for group in dataset.association_truth_groups
        if group.resolution_class == "individually-resolvable"
    )

    result = diagnose_phase_four_realization(
        dataset,
        recipe,
        candidates,
        implementation_identifier="hebog",
        outlier_thresholds=CatalogueOutlierThresholds(
            position_beams=0.5,
            peak_flux_fractional_difference=0.5,
            integrated_flux_fractional_difference=0.5,
            fitted_axis_fractional_difference=0.5,
            deconvolved_axis_fractional_difference=1.0,
        ),
        position_angle_minimum_axis_ratio=1.1,
    )

    assert result.status == "success"
    assert result.candidate_count == len(candidates)
    assert any(
        pair.decision == "unmatched-truth-group"
        and pair.resolution_class == "unresolved-blend"
        for pair in result.association_pairs
    )
    assert len(result.source_pairs) == len(candidates)


def test_association_uses_fitted_total_before_canonicalization() -> None:
    """Group flux uses fit evidence; individual rows keep peak-as-total."""
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4-regression.json"
    ).datasets[1]
    recipe = iter_dataset_recipes(dataset)[0]
    candidates: list[CatalogueSource] = []
    for group in dataset.association_truth_groups:
        truth = _association_truth_source(group, recipe, dataset)
        candidates.append(
            replace(
                truth,
                identifier=f"candidate-{group.identifier}",
                integrated_flux_jy=0.5 * truth.integrated_flux_jy,
                association_integrated_flux_jy=truth.integrated_flux_jy,
            )
        )

    result = diagnose_phase_four_realization(
        dataset,
        recipe,
        candidates,
        implementation_identifier="hebog",
        outlier_thresholds=CatalogueOutlierThresholds(
            position_beams=0.5,
            peak_flux_fractional_difference=0.5,
            integrated_flux_fractional_difference=0.5,
            fitted_axis_fractional_difference=0.5,
            deconvolved_axis_fractional_difference=1.0,
        ),
        position_angle_minimum_axis_ratio=1.1,
    )

    blend = next(
        item
        for item in result.association_pairs
        if item.resolution_class == "unresolved-blend"
    )
    assert blend.integrated_flux_fractional_difference == 0.0


def test_source_diagnostics_do_not_union_conflicting_shape_strata() -> None:
    """One source receives only its governed extension classification."""
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4r-qualification-replacement.json"
    ).datasets[0]
    group = next(
        item
        for item in dataset.association_truth_groups
        if item.source_indices == (5,)
    )

    strata = _source_strata(dataset, group)

    assert "shape-marginal-resolved" in strata
    assert "shape-clear-resolved" not in strata
