"""Contracts for the Phase 5 public multi-telescope comparison."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hebog.validation.contracts import load_phase_five_public_comparison

_ROOT = Path(__file__).parents[3]
_CONTRACT = _ROOT / "config/contracts/phase-5-public-comparison.json"


def test_public_comparison_freezes_two_complementary_telescope_lanes() -> None:
    """Truth and real-survey evidence remain distinct and reproducible."""
    contract = load_phase_five_public_comparison(_CONTRACT)

    assert contract.status == "proposed-before-human-review-and-acquisition"
    assert tuple(dataset.dataset_id for dataset in contract.datasets) == (
        "ska-sdc1-mid-band2-1000h",
        "askap-emu-pilot-hydra-2x2",
    )
    assert {dataset.telescope_family for dataset in contract.datasets} == {
        "askap",
        "simulated-ska-mid",
    }
    assert contract.datasets[0].evidence_role == "truth-bearing-challenge"
    assert contract.datasets[1].evidence_role == "real-survey-diagnostic"
    assert contract.datasets[0].truth_policy == "official-revealed-truth"
    assert contract.datasets[1].truth_policy == "no-astronomical-ground-truth"
    assert contract.datasets[1].comparators == (
        "aegean",
        "caesar",
        "profound",
        "pybdsf",
        "selavy",
    )
    assert not contract.human_scientific_review_complete
    assert not contract.artifact_checksums_frozen
    assert not contract.execution_authorized
    assert not contract.qualification_opened


def test_public_comparison_rejects_truth_or_compensation_drift() -> None:
    """A finder consensus cannot replace truth or hide a failed lane."""
    contract = load_phase_five_public_comparison(_CONTRACT)
    payload = contract.model_dump(mode="json")
    payload["datasets"][1]["truth_policy"] = "official-revealed-truth"

    with pytest.raises(ValidationError, match="canonical public datasets"):
        type(contract).model_validate(payload)

    payload = contract.model_dump(mode="json")
    payload["datasets"][0]["artifacts"] = payload["datasets"][0]["artifacts"][
        :-1
    ]
    with pytest.raises(ValidationError, match="canonical public datasets"):
        type(contract).model_validate(payload)

    payload = contract.model_dump(mode="json")
    payload["decision"]["cross_lane_compensation"] = True
    with pytest.raises(ValidationError):
        type(contract).model_validate(payload)


def test_public_comparison_rejects_missing_finder_or_artifact() -> None:
    """The ASKAP cross-finder context and SKA truth inputs are mandatory."""
    contract = load_phase_five_public_comparison(_CONTRACT)
    payload = contract.model_dump(mode="json")
    payload["datasets"][1]["comparators"].remove("selavy")

    with pytest.raises(ValidationError, match="canonical public datasets"):
        type(contract).model_validate(payload)


def test_public_comparison_rejects_metric_population_drift() -> None:
    """Truth gates and diagnostic populations remain ordered and scoped."""
    contract = load_phase_five_public_comparison(_CONTRACT)
    payload = contract.model_dump(mode="json")
    payload["datasets"][0]["diagnostic_metrics"].reverse()

    with pytest.raises(ValidationError, match="diagnostic metrics"):
        type(contract).model_validate(payload)

    payload = contract.model_dump(mode="json")
    payload["datasets"][0]["binding_metrics"].remove("astrometry")
    with pytest.raises(ValidationError, match="SDC1 binding metrics"):
        type(contract).model_validate(payload)

    payload = contract.model_dump(mode="json")
    payload["datasets"][1]["binding_metrics"] = ["catalogue-completeness"]
    with pytest.raises(ValidationError, match="cannot be binding"):
        type(contract).model_validate(payload)
