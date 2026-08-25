"""Evaluate one sealed Phase 5 Rapthor membership experiment exactly once."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hebog.validation.contracts import (
    PhaseFiveRapthorComponentPopulation,
    PhaseFiveRapthorMembershipEvidence,
    load_phase_five_rapthor_profile,
)
from hebog.validation.rapthor_profile import (
    ComponentDecision,
    ComponentDecisionLane,
    decide_rapthor_profile_evidence,
)

_CONTRACT_PATH = Path("config/contracts/phase-5-rapthor-profile.json")


def _sha256(path: Path) -> str:
    """Return the exact byte identity of one governed artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_bindings(
    *,
    contract_path: Path,
    population_path: Path,
    population: PhaseFiveRapthorComponentPopulation,
    evidence: PhaseFiveRapthorMembershipEvidence,
) -> None:
    """Reject drift between pre-results, runtime, and contract identities."""
    contract = load_phase_five_rapthor_profile(contract_path)
    contract_sha256 = _sha256(contract_path)
    if (
        population.contract_sha256 != contract_sha256
        or evidence.contract_sha256 != contract_sha256
    ):
        raise ValueError("Rapthor profile contract SHA-256 changed")
    if evidence.population_sha256 != _sha256(population_path):
        raise ValueError("Rapthor component population SHA-256 changed")
    for record in (population, evidence):
        if record.dataset_id != contract.real_inputs.dataset_id:
            raise ValueError("Rapthor profile dataset identity changed")
        if record.software != contract.software:
            raise ValueError("Rapthor profile software identity changed")
        if record.verified_real_inputs != contract.real_inputs:
            raise ValueError("Rapthor profile input identity changed")
    if evidence.filtering_operation != contract.decision.filtering_operation:
        raise ValueError("Rapthor profile filtering operation changed")
    population_identifiers = tuple(
        item.identifier for item in population.components
    )
    for lane in evidence.lanes:
        if tuple(item.identifier for item in lane.components) != (
            population_identifiers
        ):
            raise ValueError(
                "membership lane differs from frozen component population"
            )


def evaluate(arguments: argparse.Namespace) -> None:
    """Validate bindings, decide the profile, and publish write-once JSON."""
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite Rapthor profile decision: "
            f"{arguments.output}"
        )
    population = PhaseFiveRapthorComponentPopulation.model_validate_json(
        arguments.population.read_text(encoding="utf-8")
    )
    evidence = PhaseFiveRapthorMembershipEvidence.model_validate_json(
        arguments.evidence.read_text(encoding="utf-8")
    )
    _verify_bindings(
        contract_path=arguments.contract,
        population_path=arguments.population,
        population=population,
        evidence=evidence,
    )
    contract = load_phase_five_rapthor_profile(arguments.contract)
    strata_by_identifier = {
        item.identifier: frozenset(item.strata)
        for item in population.components
    }
    lanes = tuple(
        ComponentDecisionLane(
            identifier=lane.identifier,
            components=tuple(
                ComponentDecision(
                    identifier=item.identifier,
                    retained=item.retained,
                    strata=strata_by_identifier[item.identifier],
                )
                for item in lane.components
            ),
        )
        for lane in evidence.lanes
    )
    decision = decide_rapthor_profile_evidence(
        lanes,
        required_strata=contract.decision.required_safety_strata,
        minimum_agreement=contract.decision.minimum_agreement,
    )
    document = {
        "schema_version": 1,
        "decision_id": "phase-5-rapthor-profile-decision",
        "status": "complete" if decision.selection.complete else "incomplete",
        "contract_sha256": _sha256(arguments.contract),
        "population_sha256": _sha256(arguments.population),
        "membership_evidence_sha256": _sha256(arguments.evidence),
        "selected_profile": decision.selection.selected_profile,
        "complete": decision.selection.complete,
        "overall": asdict(decision.selection.overall),
        "strata": [asdict(item) for item in decision.selection.strata],
        "missing_strata": decision.selection.missing_strata,
        "failed_strata": decision.selection.failed_strata,
        "disagreement_identifiers": (
            decision.selection.disagreement_identifiers
        ),
        "reference_comparisons": [
            asdict(item) for item in decision.reference_comparisons
        ],
        "qualification_opened": False,
        "cutover_authorized": False,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as output:
        output.write(
            (
                json.dumps(
                    document,
                    allow_nan=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode()
        )


def _parse_args() -> argparse.Namespace:
    """Parse the frozen population, sealed evidence, and output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=_CONTRACT_PATH)
    parser.add_argument("--population", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Run the write-once terminal evaluator."""
    evaluate(_parse_args())


if __name__ == "__main__":
    main()
