"""Tests for shared isolated-campaign runtime helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
    contract_set_sha256,
    dataset_by_identifier,
    dependency_inventory_sha256,
    failure_from_exception,
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


def test_contract_set_hashes_ordered_json_documents(tmp_path: Path) -> None:
    """The common contract identity preserves explicit document order."""
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps({"contract": 1}), encoding="utf-8")
    second.write_text(json.dumps({"contract": 2}), encoding="utf-8")

    assert contract_set_sha256([first, second]) != contract_set_sha256(
        [second, first]
    )
    with pytest.raises(ValueError, match="at least one"):
        contract_set_sha256([])


def test_dataset_resolution_and_identity_bind_the_complete_record() -> None:
    """Both isolated runners resolve the same governed dataset identity."""
    identifier = "phase4-transform-deconvolution-regression-384x512"
    dataset = dataset_by_identifier(_MANIFEST, identifier)

    identity = campaign_dataset_identity(dataset)

    assert identity.identifier == identifier
    assert identity.role == "regression"
    assert identity.shape_yx == (384, 512)
    with pytest.raises(ValueError, match="found 0"):
        dataset_by_identifier(_MANIFEST, "missing-dataset")


def test_failure_capture_uses_repr_for_an_empty_exception_message() -> None:
    """Even a blank implementation exception remains valid evidence."""
    failure = failure_from_exception(
        RuntimeError(),
        stage="candidate",
        traceback_text="traceback",
    )

    assert failure.message == "RuntimeError()"
    assert len(failure.traceback_sha256) == 64


def test_scientific_thresholds_and_dependencies_are_available() -> None:
    """Shared runtime provenance loads gates and installed distributions."""
    thresholds = phase_four_outlier_thresholds(
        _ROOT / "config/contracts/phase-4-scientific-gates.json"
    )

    assert thresholds.position_beams == 0.5
    assert len(dependency_inventory_sha256()) == 64
    assert load_dataset_manifest(_MANIFEST).datasets
