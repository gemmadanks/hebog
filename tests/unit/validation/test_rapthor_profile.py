"""Contracts for the Phase 5 Rapthor profile decision."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from hebog.validation.contracts import load_phase_five_rapthor_profile
from hebog.validation.rapthor_profile import (
    ComponentDecision,
    decide_rapthor_profile,
)

_ROOT = Path(__file__).parents[3]
_CONTRACT = _ROOT / "config/contracts/phase-5-rapthor-profile.json"


def _decision(
    identifier: str,
    retained: bool,
    *strata: str,
) -> ComponentDecision:
    return ComponentDecision(
        identifier=identifier,
        retained=retained,
        strata=frozenset(strata),
    )


def test_rapthor_profile_contract_freezes_real_inputs_and_safety_strata() -> (
    None
):
    """Profile evidence uses exact pipeline identities and no compensation."""
    contract = load_phase_five_rapthor_profile(_CONTRACT)

    assert contract.status == "frozen-pre-results"
    assert contract.software.rapthor_commit == (
        "b1a64674b1022476cf052fc2d06ee3b16f031ecd"
    )
    assert contract.software.lsmtool_commit == (
        "3adf3d6f1f8c03db34e13a45a752f6f6dd7d7f4a"
    )
    assert tuple(
        reference.identifier for reference in contract.references
    ) == (
        "released-pybdsf-used-by-rapthor",
        "pinned-pybdsf-master",
    )
    assert all(
        reference.configuration.atrous_do for reference in contract.references
    )
    assert all(
        reference.configuration.threshold_pixel_sigma == 5.0
        and reference.configuration.threshold_island_sigma == 3.0
        for reference in contract.references
    )
    assert contract.decision.minimum_agreement == 0.995
    assert set(contract.decision.required_safety_strata) == {
        "apparent-sky",
        "bright-component",
        "crowded",
        "edge",
        "extended-associated",
        "masked-or-invalid-neighbour",
        "sparse",
        "true-sky",
    }
    inventory_path = _ROOT / contract.real_inputs.inventory_path
    assert hashlib.sha256(inventory_path.read_bytes()).hexdigest() == (
        contract.real_inputs.inventory_sha256
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert (
        contract.real_inputs.flat_noise_image_sha256
        == (inventory["inputs"]["flat_noise_image"]["sha256"])
    )
    assert (
        contract.real_inputs.true_sky_image_sha256
        == (inventory["inputs"]["true_sky_image"]["sha256"])
    )
    assert (
        contract.real_inputs.true_skymodel_sha256
        == inventory["inputs"]["true_skymodel"]["sha256"]
    )
    assert (
        contract.real_inputs.apparent_skymodel_sha256
        == inventory["inputs"]["apparent_skymodel"]["sha256"]
    )
    assert (
        contract.real_inputs.vertices_sha256
        == inventory["inputs"]["vertices"]["sha256"]
    )
    assert (
        contract.real_inputs.beam_measurement_set_sha256
        == inventory["inputs"]["beam_ms_0"]["sha256"]
    )
    revisions_path = _ROOT / "config/baselines/phase-0-starting-revisions.json"
    assert hashlib.sha256(revisions_path.read_bytes()).hexdigest() == (
        contract.software.starting_revisions_sha256
    )
    revisions = json.loads(revisions_path.read_text(encoding="utf-8"))
    assert (
        contract.software.rapthor_commit
        == (revisions["repositories"]["rapthor"]["commit"])
    )


def test_rapthor_profile_contract_rejects_gate_or_stratum_drift() -> None:
    """Neither the 99.5% gate nor an inconvenient safety lane can disappear."""
    contract = load_phase_five_rapthor_profile(_CONTRACT)
    payload = contract.model_dump(mode="json")
    payload["decision"]["minimum_agreement"] = 0.99

    with pytest.raises(ValidationError, match=r"agreement must remain 0\.995"):
        type(contract).model_validate(payload)

    payload = contract.model_dump(mode="json")
    payload["decision"]["required_safety_strata"].remove("crowded")
    with pytest.raises(ValidationError, match="safety strata"):
        type(contract).model_validate(payload)

    payload = contract.model_dump(mode="json")
    payload["references"][0]["configuration"]["threshold_pixel_sigma"] = 4.9
    with pytest.raises(ValidationError, match="thresholds must remain exact"):
        type(contract).model_validate(payload)


def test_rapthor_profile_selects_compact_only_when_every_lane_passes() -> None:
    """A crowded-lane disagreement cannot be hidden by overall agreement."""
    continuum = (
        _decision("a", True, "sparse"),
        _decision("b", True, "sparse"),
        _decision("c", True, "crowded"),
        _decision("d", False, "crowded"),
    )
    compact = (
        _decision("a", True, "sparse"),
        _decision("b", True, "sparse"),
        _decision("c", False, "crowded"),
        _decision("d", False, "crowded"),
    )

    decision = decide_rapthor_profile(
        continuum,
        compact,
        required_strata=("crowded", "sparse"),
        minimum_agreement=0.75,
    )

    assert decision.complete
    assert decision.overall.agreement == 0.75
    assert decision.selected_profile == "continuum"
    assert decision.failed_strata == ("crowded",)


def test_rapthor_profile_fails_closed_on_missing_or_changed_population() -> (
    None
):
    """Default safely on missing evidence and reject identity drift."""
    continuum = (_decision("a", True, "sparse"),)
    compact = (_decision("a", True, "sparse"),)

    incomplete = decide_rapthor_profile(
        continuum,
        compact,
        required_strata=("crowded", "sparse"),
        minimum_agreement=0.995,
    )

    assert not incomplete.complete
    assert incomplete.selected_profile == "continuum"
    assert incomplete.missing_strata == ("crowded",)

    with pytest.raises(ValueError, match="component identities differ"):
        decide_rapthor_profile(
            continuum,
            (_decision("b", True, "sparse"),),
            required_strata=("sparse",),
            minimum_agreement=0.995,
        )

    with pytest.raises(ValueError, match="component strata differ"):
        decide_rapthor_profile(
            continuum,
            (_decision("a", True, "crowded"),),
            required_strata=("sparse",),
            minimum_agreement=0.995,
        )


def test_rapthor_profile_rejects_ambiguous_inputs() -> None:
    """Malformed populations cannot produce an apparently safe decision."""
    with pytest.raises(ValueError, match="identifier must not be empty"):
        _decision("", True, "sparse")
    with pytest.raises(ValueError, match="strata must be non-empty"):
        _decision("a", True)

    repeated = (
        _decision("a", True, "sparse"),
        _decision("a", False, "sparse"),
    )
    with pytest.raises(ValueError, match="repeats component identifier"):
        decide_rapthor_profile(
            repeated,
            repeated,
            required_strata=("sparse",),
            minimum_agreement=0.995,
        )

    with pytest.raises(ValueError, match="between zero and one"):
        decide_rapthor_profile(
            (),
            (),
            required_strata=("sparse",),
            minimum_agreement=1.1,
        )
    for required_strata in ((), ("",)):
        with pytest.raises(ValueError, match="non-empty strings"):
            decide_rapthor_profile(
                (),
                (),
                required_strata=required_strata,
                minimum_agreement=0.995,
            )
    with pytest.raises(ValueError, match="must not contain duplicates"):
        decide_rapthor_profile(
            (),
            (),
            required_strata=("sparse", "sparse"),
            minimum_agreement=0.995,
        )


def test_rapthor_profile_selects_compact_for_complete_exact_agreement() -> (
    None
):
    """Complete per-stratum parity permits the narrower workflow profile."""
    continuum = (
        _decision("a", True, "sparse", "true-sky"),
        _decision("b", False, "crowded", "apparent-sky"),
    )

    decision = decide_rapthor_profile(
        continuum,
        continuum,
        required_strata=(
            "apparent-sky",
            "crowded",
            "sparse",
            "true-sky",
        ),
        minimum_agreement=0.995,
    )

    assert decision.complete
    assert decision.selected_profile == "compact"
    assert decision.failed_strata == ()
    assert decision.disagreement_identifiers == ()
