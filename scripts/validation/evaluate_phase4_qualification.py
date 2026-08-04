"""Apply the frozen one-look decision to compiled Phase 4 evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from hebog.validation.campaign_runtime import (
    contract_set_sha256,
    dataset_by_identifier,
    require_reviewed_qualification_inputs,
)
from hebog.validation.contracts import (
    load_paired_noninferiority_contract,
    load_phase_four_scientific_gates,
)
from hebog.validation.evidence import (
    ScientificCampaignEvidence,
    load_evidence,
    write_evidence,
)
from hebog.validation.phase_four_decision import (
    evaluate_phase_four_qualification,
)


def _parse_args() -> argparse.Namespace:
    """Parse the immutable campaign and frozen contract paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument(
        "--scientific-contract",
        required=True,
        action="append",
        type=Path,
    )
    parser.add_argument("--scientific-gates", required=True, type=Path)
    parser.add_argument("--comparison-protocol", required=True, type=Path)
    parser.add_argument("--candidate-id", default="hebog")
    parser.add_argument("--primary-reference-id", default="pybdsf-release")
    parser.add_argument("--secondary-reference-id", default="pybdsf-master")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Validate all frozen inputs and publish exactly one decision."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite qualification decision: {arguments.output}"
        )
    campaign = load_evidence(arguments.campaign)
    if not isinstance(campaign, ScientificCampaignEvidence):
        raise TypeError(
            "one-look evaluator requires compiled campaign evidence"
        )
    dataset = dataset_by_identifier(arguments.manifest, arguments.dataset_id)
    require_reviewed_qualification_inputs(
        dataset,
        scientific_contracts=arguments.scientific_contract,
        scientific_gates=arguments.scientific_gates,
        comparison_protocol=arguments.comparison_protocol,
    )
    decision = evaluate_phase_four_qualification(
        campaign,
        dataset,
        load_paired_noninferiority_contract(arguments.comparison_protocol),
        load_phase_four_scientific_gates(arguments.scientific_gates),
        scientific_contract_set_sha256=contract_set_sha256(
            arguments.scientific_contract
        ),
        candidate_identifier=arguments.candidate_id,
        primary_reference_identifier=arguments.primary_reference_id,
        secondary_reference_identifier=arguments.secondary_reference_id,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(arguments.output, decision)


if __name__ == "__main__":
    main()
