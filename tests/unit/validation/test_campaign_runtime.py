"""Tests for shared isolated-campaign runtime helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

from hebog.validation.campaign_runtime import (
    canonical_sha256,
    dependency_inventory_sha256,
    phase_four_outlier_thresholds,
)
from hebog.validation.datasets import load_dataset_manifest

_ROOT = Path(__file__).parents[3]
_MANIFEST = _ROOT / "config/datasets/phase-4-regression.json"


def test_canonical_hash_ignores_json_presentation() -> None:
    """Shared shard identity depends on values rather than whitespace."""
    value = {"b": [2, 3], "a": 1}
    canonical = b'{"a":1,"b":[2,3]}'

    assert canonical_sha256(value) == hashlib.sha256(canonical).hexdigest()


def test_scientific_thresholds_and_dependencies_are_available() -> None:
    """Shared runtime provenance loads gates and installed distributions."""
    thresholds = phase_four_outlier_thresholds(
        _ROOT / "config/contracts/phase-4-scientific-gates.json"
    )

    assert thresholds.position_beams == 0.5
    assert len(dependency_inventory_sha256()) == 64
    assert load_dataset_manifest(_MANIFEST).datasets
