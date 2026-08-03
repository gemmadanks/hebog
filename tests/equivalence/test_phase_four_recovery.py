"""Independent regression cases for Phase 4 scientific recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from hebog.validation.datasets import (
    iter_dataset_recipes,
    load_dataset_manifest,
)
from hebog.validation.hebog_campaign import process_hebog_recipe

_ROOT = Path(__file__).parents[2]
_PAIRED_REGRESSION = _ROOT / "config/datasets/phase-4-paired-regression.json"
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
