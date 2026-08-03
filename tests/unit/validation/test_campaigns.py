"""Tests for reproducible Phase 4 paired-campaign assembly."""

from __future__ import annotations

from pathlib import Path

from hebog.validation.campaigns import (
    diagnose_phase_four_realization,
    phase_four_truth_source,
)
from hebog.validation.comparison import CatalogueOutlierThresholds
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
