"""Integration tests for the maintained Hebog campaign runner."""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.comparison import CatalogueSource
from hebog.validation.datasets import (
    DatasetRecord,
    SyntheticRecipe,
    load_dataset_manifest,
)

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).parents[2]


def test_hebog_campaign_runs_the_complete_compact_path(tmp_path: Path) -> None:
    """One governed image produces comparison-ready candidate records."""
    namespace: dict[str, Any] = runpy.run_path(
        str(_ROOT / "scripts/benchmark/run_phase4_hebog_campaign.py")
    )
    process_recipe: Callable[
        [SyntheticRecipe, DatasetRecord, Path],
        tuple[CatalogueSource, ...],
    ] = namespace["_process_recipe"]
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4-development.json"
    ).datasets[0]

    candidates = process_recipe(dataset.recipe, dataset, tmp_path)

    assert len(candidates) == 3
    assert tuple(source.identifier for source in candidates) == tuple(
        sorted(source.identifier for source in candidates)
    )
    assert all(source.fitted_shape is not None for source in candidates)
    assert all(source.component_count == 1 for source in candidates)
