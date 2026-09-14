"""Contracts for the Phase 5 Rapthor profile decision."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from hebog.validation.contracts import (
    PhaseFiveRapthorComponentPopulation,
    PhaseFiveRapthorMembershipEvidence,
    load_phase_five_rapthor_profile,
)
from hebog.validation.rapthor_profile import (
    ComponentDecision,
    ComponentDecisionLane,
    decide_rapthor_profile,
    decide_rapthor_profile_evidence,
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


def _population_payload() -> dict[str, object]:
    contract = load_phase_five_rapthor_profile(_CONTRACT)
    return {
        "schema_version": 1,
        "population_id": "phase-5-rapthor-profile-components",
        "status": "frozen-pre-results",
        "contract_sha256": hashlib.sha256(_CONTRACT.read_bytes()).hexdigest(),
        "dataset_id": contract.real_inputs.dataset_id,
        "software": contract.software.model_dump(mode="json"),
        "verified_real_inputs": contract.real_inputs.model_dump(mode="json"),
        "components": [
            {
                "identifier": "scope:true/a",
                "strata": list(contract.decision.required_safety_strata),
            }
        ],
    }


def _evidence_payload(
    *, population_sha256: str = "1" * 64
) -> dict[str, object]:
    contract = load_phase_five_rapthor_profile(_CONTRACT)
    return {
        "schema_version": 1,
        "evidence_id": "phase-5-rapthor-profile-membership",
        "status": "sealed",
        "contract_sha256": hashlib.sha256(_CONTRACT.read_bytes()).hexdigest(),
        "population_sha256": population_sha256,
        "dataset_id": contract.real_inputs.dataset_id,
        "software": contract.software.model_dump(mode="json"),
        "verified_real_inputs": contract.real_inputs.model_dump(mode="json"),
        "filtering_operation": contract.decision.filtering_operation,
        "lanes": [
            {
                "identifier": identifier,
                "components": [
                    {"identifier": "scope:true/a", "retained": True}
                ],
            }
            for identifier in (
                "compact",
                "continuum",
                "released-pybdsf-used-by-rapthor",
                "pinned-pybdsf-master",
            )
        ],
    }


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


def test_membership_evidence_requires_canonical_four_lane_population() -> None:
    """The controlled-runner record cannot omit or mutate a comparator."""
    evidence = PhaseFiveRapthorMembershipEvidence.model_validate(
        _evidence_payload()
    )
    population = PhaseFiveRapthorComponentPopulation.model_validate(
        _population_payload()
    )

    assert population.status == "frozen-pre-results"
    assert tuple(lane.identifier for lane in evidence.lanes) == (
        "compact",
        "continuum",
        "released-pybdsf-used-by-rapthor",
        "pinned-pybdsf-master",
    )

    payload = _evidence_payload()
    payload["lanes"] = payload["lanes"][:-1]  # type: ignore[index]
    with pytest.raises(ValidationError, match="four canonical lanes"):
        PhaseFiveRapthorMembershipEvidence.model_validate(payload)

    payload = _evidence_payload()
    payload["lanes"][1]["components"][0]["identifier"] = (  # type: ignore[index]
        "scope:true/b"
    )
    with pytest.raises(ValidationError, match="component population"):
        PhaseFiveRapthorMembershipEvidence.model_validate(payload)

    population_payload = _population_payload()
    population_payload["components"][0]["strata"] = ["sparse", "edge"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="strata must be canonical"):
        PhaseFiveRapthorComponentPopulation.model_validate(population_payload)

    population_payload = _population_payload()
    population_payload["components"].append(  # type: ignore[union-attr]
        population_payload["components"][0]  # type: ignore[index]
    )
    with pytest.raises(ValidationError, match="identities must be canonical"):
        PhaseFiveRapthorComponentPopulation.model_validate(population_payload)

    payload = _evidence_payload()
    payload["lanes"][0]["components"].append(  # type: ignore[index]
        payload["lanes"][0]["components"][0]  # type: ignore[index]
    )
    with pytest.raises(ValidationError, match="identifiers must be canonical"):
        PhaseFiveRapthorMembershipEvidence.model_validate(payload)


def test_membership_evidence_reports_references_without_rescue() -> None:
    """Reference parity is reported but cannot rescue compact profile drift."""
    strata = frozenset(("crowded", "sparse"))
    lanes = (
        ComponentDecisionLane(
            identifier="compact",
            components=(ComponentDecision("a", False, strata),),
        ),
        ComponentDecisionLane(
            identifier="continuum",
            components=(ComponentDecision("a", True, strata),),
        ),
        ComponentDecisionLane(
            identifier="released-pybdsf-used-by-rapthor",
            components=(ComponentDecision("a", False, strata),),
        ),
        ComponentDecisionLane(
            identifier="pinned-pybdsf-master",
            components=(ComponentDecision("a", False, strata),),
        ),
    )

    decision = decide_rapthor_profile_evidence(
        lanes,
        required_strata=("crowded", "sparse"),
        minimum_agreement=0.995,
    )

    assert decision.selection.selected_profile == "continuum"
    assert tuple(
        (item.profile_identifier, item.reference_identifier)
        for item in decision.reference_comparisons
    ) == (
        ("compact", "released-pybdsf-used-by-rapthor"),
        ("compact", "pinned-pybdsf-master"),
        ("continuum", "released-pybdsf-used-by-rapthor"),
        ("continuum", "pinned-pybdsf-master"),
    )
    assert decision.reference_comparisons[0].overall.agreement == 1.0
    assert decision.reference_comparisons[2].overall.agreement == 0.0

    with pytest.raises(ValueError, match="four canonical lanes"):
        decide_rapthor_profile_evidence(
            lanes[:-1],
            required_strata=("crowded", "sparse"),
            minimum_agreement=0.995,
        )


def test_profile_evaluator_binds_contract_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    """The terminal compiler is write-once and rejects contract drift."""
    namespace = runpy.run_path(
        str(
            _ROOT
            / "scripts"
            / "validation"
            / "evaluate_phase5_rapthor_profile.py"
        )
    )
    population_path = tmp_path / "population.json"
    population_path.write_text(
        json.dumps(_population_payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    evidence_path = tmp_path / "membership.json"
    evidence_path.write_text(
        json.dumps(
            _evidence_payload(
                population_sha256=hashlib.sha256(
                    population_path.read_bytes()
                ).hexdigest()
            )
        ),
        encoding="utf-8",
    )
    output = tmp_path / "decision.json"
    arguments = SimpleNamespace(
        contract=_CONTRACT,
        population=population_path,
        evidence=evidence_path,
        output=output,
    )

    namespace["evaluate"](arguments)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["selected_profile"] == "compact"
    assert result["complete"] is True
    assert len(result["reference_comparisons"]) == 4

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        namespace["evaluate"](arguments)

    changed = _evidence_payload()
    changed["contract_sha256"] = "0" * 64
    changed_path = tmp_path / "changed.json"
    changed_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="contract SHA-256"):
        namespace["evaluate"](
            SimpleNamespace(
                contract=_CONTRACT,
                population=population_path,
                evidence=changed_path,
                output=tmp_path / "changed-decision.json",
            )
        )
