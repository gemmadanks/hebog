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
    require_reviewed_qualification_inputs,
)
from hebog.validation.datasets import load_dataset_manifest

_ROOT = Path(__file__).parents[3]
_MANIFEST = _ROOT / "config/datasets/phase-4-regression.json"
_FINAL_MANIFEST = _ROOT / "config/datasets/phase-4-final-qualification.json"
_MEASUREMENT = _ROOT / "config/contracts/phase-4-measurement.json"
_GATES = _ROOT / "config/contracts/phase-4-scientific-gates.json"
_REGISTRY = _ROOT / "config/contracts/phase-4r-metric-registry.json"
_PROTOCOL = _ROOT / "config/contracts/phase-4-paired-noninferiority.json"


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


def test_qualification_requires_every_reviewed_scientific_input() -> None:
    """An unopened population cannot run against provisional governance."""
    dataset = load_dataset_manifest(_FINAL_MANIFEST).datasets[0]

    require_reviewed_qualification_inputs(
        dataset,
        scientific_contracts=[_MEASUREMENT, _GATES],
        scientific_gates=_GATES,
        comparison_protocol=_PROTOCOL,
    )

    with pytest.raises(ValueError, match="measurement and gate contracts"):
        require_reviewed_qualification_inputs(
            dataset,
            scientific_contracts=[_GATES],
            scientific_gates=_GATES,
            comparison_protocol=_PROTOCOL,
        )


def test_phase4r_qualification_requires_the_reviewed_metric_registry() -> None:
    """Phase 4R cannot open without its named-review metric contract."""
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4r-qualification.json"
    ).datasets[0]

    require_reviewed_qualification_inputs(
        dataset,
        scientific_contracts=[_MEASUREMENT, _GATES, _REGISTRY],
        scientific_gates=_GATES,
        comparison_protocol=_PROTOCOL,
    )

    with pytest.raises(ValueError, match="metric registry"):
        require_reviewed_qualification_inputs(
            dataset,
            scientific_contracts=[_MEASUREMENT, _GATES],
            scientific_gates=_GATES,
            comparison_protocol=_PROTOCOL,
        )


def test_phase4r_qualification_rejects_development_only_registry(
    tmp_path: Path,
) -> None:
    """Development approval cannot silently authorize held-out execution."""
    payload = json.loads(_REGISTRY.read_text(encoding="utf-8"))
    payload["status"] = "approved-development"
    payload["human_scientific_review"] = (
        "development-approved-qualification-review-still-required"
    )
    registry = tmp_path / "metric-registry.json"
    registry.write_text(json.dumps(payload), encoding="utf-8")
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4r-qualification.json"
    ).datasets[0]

    with pytest.raises(ValueError, match="registry must be reviewed"):
        require_reviewed_qualification_inputs(
            dataset,
            scientific_contracts=[_MEASUREMENT, _GATES, registry],
            scientific_gates=_GATES,
            comparison_protocol=_PROTOCOL,
        )


def test_regression_runs_do_not_require_reviewed_qualification_inputs() -> (
    None
):
    """Viewable planning evidence remains usable before named review."""
    dataset = load_dataset_manifest(_MANIFEST).datasets[0]

    require_reviewed_qualification_inputs(
        dataset,
        scientific_contracts=[],
        scientific_gates=Path("not-read-for-regression.json"),
        comparison_protocol=Path("not-read-for-regression.json"),
    )


def test_qualification_rejects_a_provisional_protocol(
    tmp_path: Path,
) -> None:
    """Protocol status fails closed before recipe iteration."""
    protocol = json.loads(_PROTOCOL.read_text(encoding="utf-8"))
    protocol["status"] = "draft-provisional"
    provisional = tmp_path / "protocol.json"
    provisional.write_text(json.dumps(protocol), encoding="utf-8")
    dataset = load_dataset_manifest(_FINAL_MANIFEST).datasets[0]

    with pytest.raises(ValueError, match="paired protocol must be reviewed"):
        require_reviewed_qualification_inputs(
            dataset,
            scientific_contracts=[_MEASUREMENT, _GATES],
            scientific_gates=_GATES,
            comparison_protocol=provisional,
        )


@pytest.mark.parametrize("source", (_MEASUREMENT, _GATES))
def test_qualification_rejects_a_provisional_scientific_contract(
    source: Path,
    tmp_path: Path,
) -> None:
    """Both scientific contracts must have named review before opening."""
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["status"] = "frozen-provisional"
    provisional = tmp_path / source.name
    provisional.write_text(json.dumps(payload), encoding="utf-8")
    contracts = [
        provisional if path == source else path
        for path in (_MEASUREMENT, _GATES)
    ]
    dataset = load_dataset_manifest(_FINAL_MANIFEST).datasets[0]

    with pytest.raises(ValueError, match="scientific contracts"):
        require_reviewed_qualification_inputs(
            dataset,
            scientific_contracts=contracts,
            scientific_gates=(provisional if source == _GATES else _GATES),
            comparison_protocol=_PROTOCOL,
        )


def test_qualification_binds_the_executed_gate_document(
    tmp_path: Path,
) -> None:
    """Threshold extraction must use the gate included in provenance."""
    payload = json.loads(_GATES.read_text(encoding="utf-8"))
    payload["catastrophic_outlier"]["position_beams"] = 0.75
    different_gates = tmp_path / "gates.json"
    different_gates.write_text(json.dumps(payload), encoding="utf-8")
    dataset = load_dataset_manifest(_FINAL_MANIFEST).datasets[0]

    with pytest.raises(ValueError, match="executed gate contract"):
        require_reviewed_qualification_inputs(
            dataset,
            scientific_contracts=[_MEASUREMENT, _GATES],
            scientific_gates=different_gates,
            comparison_protocol=_PROTOCOL,
        )
