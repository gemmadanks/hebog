"""Contracts for the Phase 5 public multi-telescope comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from hebog.validation.contracts import load_phase_five_public_comparison
from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_CONTRACT = _ROOT / "config/contracts/phase-5-public-comparison.json"
_FINDER_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-execution-pre-review.json"
)


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


def test_public_finder_pre_review_is_exact_and_non_executable() -> None:
    """The next public gate freezes science design without opening finders."""
    review = json.loads(_FINDER_PRE_REVIEW.read_text(encoding="utf-8"))

    assert review["status"] == (
        "ready-for-named-public-finder-protocol-implementation-review"
    )
    assert review["candidate"] == {
        "configuration_sha256": (
            "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
        ),
        "final_qualification_decision_sha256": (
            "d4db4d7f240faf4c7d841b4586208a33fd81d13228a1215cebb75ddd11e63416"
        ),
        "revision": "90626641c8705ba9d55fdea02a705983528b8aa0",
        "source_tree_sha256": (
            "e4307246efa7db3ec941b3906f8ce443404b8b84cdc78aa89881e738850cdf8a"
        ),
    }
    assert review["population"] == {
        "hydra_image_count": 2,
        "hebog_run_count": 10,
        "sdc1_tile_count": 8,
        "selected_population_sha256": (
            "0a7c2b18d96ee47277072528949c5a64239f0c3053d5e7b33c03b36c194b7824"
        ),
    }
    assert review["runtime"] == {
        "dependency_inventory_sha256": (
            "d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2"
        ),
        "digest": (
            "sha256:132f1c3da7f353edc642e9bc2e6108aff8a1dbf6f9a5556f50144db864114363"
        ),
        "finder_id": "hebog",
        "image_id": (
            "e7f1ce9e9b26f6e29a14e75833bcec52e56b95ce58102f2905c3623f9902632c"
        ),
    }
    assert review["sdc1"]["binding_metric_limits"] == {
        "absolute-mean-offset-x": {"at_most": 0.1},
        "absolute-mean-offset-y": {"at_most": 0.1},
        "completeness": {"at_least": 0.9},
        "duplicate-fraction": {"at_most": 0.02},
        "integrated-flux-median": {"at_most": 0.1},
        "integrated-flux-p95": {"at_most": 0.25},
        "merge-fraction": {"at_most": 0.1},
        "position-p95": {"at_most": 0.5},
        "reliability": {"at_least": 0.95},
    }
    assert review["hydra"]["binding_metrics"] == []
    assert review["hydra"]["truth_policy"] == ("no-astronomical-ground-truth")
    assert set(review["authorization"].values()) == {False}
    for identity in review["tracked_identities"]:
        if identity["path"] == "src/hebog/validation/public_comparison.py":
            assert identity["sha256"] == (
                "3a3aa7c3118ebb7189e9bbc0363ee3eb04b4baf5f3c0fc08b95fc63a9369beac"
            )
            assert file_sha256(_ROOT / identity["path"]) != identity["sha256"]
        else:
            assert file_sha256(_ROOT / identity["path"]) == identity["sha256"]
