"""Independent regression cases for Phase 4 scientific recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from hebog.validation.campaign_runtime import phase_four_outlier_thresholds
from hebog.validation.campaigns import diagnose_phase_four_realization
from hebog.validation.datasets import (
    iter_dataset_recipes,
    load_dataset_manifest,
)
from hebog.validation.hebog_campaign import process_hebog_recipe

_ROOT = Path(__file__).parents[2]
_PAIRED_REGRESSION = _ROOT / "config/datasets/phase-4-paired-regression.json"
_SCIENTIFIC_GATES = _ROOT / "config/contracts/phase-4-scientific-gates.json"
_UNDERSIZED_BLEND_CHILD_SEEDS = (
    2026100024,
    2026100064,
    2026100165,
    2026100180,
)


@pytest.mark.equivalence
@pytest.mark.parametrize("seed", _UNDERSIZED_BLEND_CHILD_SEEDS)
def test_unresolved_blend_does_not_leave_an_unfit_watershed_child(
    seed: int,
    tmp_path: Path,
) -> None:
    """A fit-capable parent remains complete after conservative deblending."""
    dataset = load_dataset_manifest(_PAIRED_REGRESSION).datasets[0]
    recipes = {recipe.seed: recipe for recipe in iter_dataset_recipes(dataset)}

    candidates = process_hebog_recipe(
        recipes[seed],
        dataset,
        tmp_path / f"seed-{seed}",
    )

    assert candidates


@pytest.mark.equivalence
@pytest.mark.parametrize(
    ("seed", "truth_identifier", "expected_status"),
    (
        (2026100200, "source-00013", "unresolved"),
        (2026100155, "source-00009", "resolved"),
    ),
)
def test_high_confidence_extension_policy_separates_point_and_clear_truth(
    seed: int,
    truth_identifier: str,
    expected_status: str,
    tmp_path: Path,
) -> None:
    """The independent worst-margin examples remain correctly classified."""
    dataset = load_dataset_manifest(_PAIRED_REGRESSION).datasets[0]
    recipe = next(
        recipe
        for recipe in iter_dataset_recipes(dataset)
        if recipe.seed == seed
    )
    candidates = process_hebog_recipe(
        recipe,
        dataset,
        tmp_path / f"seed-{seed}",
    )
    diagnostic = diagnose_phase_four_realization(
        dataset,
        recipe,
        candidates,
        implementation_identifier="hebog",
        outlier_thresholds=phase_four_outlier_thresholds(_SCIENTIFIC_GATES),
        maximum_separation_beams=0.5,
        position_angle_minimum_axis_ratio=1.1,
    )

    pair = next(
        pair
        for pair in diagnostic.source_pairs
        if pair.truth_identifier == truth_identifier
    )

    assert pair.candidate_deconvolution_status == expected_status
