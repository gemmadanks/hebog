"""Evaluate every registered Phase 4R metric without compensation."""

from __future__ import annotations

import argparse
from pathlib import Path

from hebog.validation.campaign_runtime import (
    contract_set_sha256,
    dataset_by_identifier,
)
from hebog.validation.contracts import (
    load_paired_noninferiority_contract,
    load_phase_four_metric_registry,
    load_phase_four_scientific_gates,
)
from hebog.validation.evidence import (
    ScientificCampaignEvidence,
    load_evidence,
    write_evidence,
)
from hebog.validation.phase_four_recovery import (
    evaluate_phase_four_recovery,
)

_REFERENCE_COUNT = 2


def _parse_args() -> argparse.Namespace:
    """Parse frozen campaign, contract, and output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument(
        "--stage",
        required=True,
        choices=("development", "regression", "qualification"),
    )
    parser.add_argument(
        "--scientific-contract",
        required=True,
        action="append",
        type=Path,
    )
    parser.add_argument("--scientific-gates", required=True, type=Path)
    parser.add_argument("--metric-registry", required=True, type=Path)
    parser.add_argument("--comparison-protocol", required=True, type=Path)
    parser.add_argument("--candidate-id", default="hebog")
    parser.add_argument(
        "--reference-id",
        action="append",
        default=None,
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Validate immutable inputs and publish one Phase 4R decision."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite Phase 4R decision: {arguments.output}"
        )
    campaign = load_evidence(arguments.campaign)
    if not isinstance(campaign, ScientificCampaignEvidence):
        raise TypeError(
            "Phase 4R evaluator requires compiled campaign evidence"
        )
    references = tuple(
        sorted(arguments.reference_id or ("pybdsf-master", "pybdsf-release"))
    )
    if len(references) != _REFERENCE_COUNT:
        raise ValueError("Phase 4R requires exactly two reference IDs")
    decision = evaluate_phase_four_recovery(
        campaign,
        dataset_by_identifier(arguments.manifest, arguments.dataset_id),
        load_phase_four_metric_registry(arguments.metric_registry),
        load_paired_noninferiority_contract(arguments.comparison_protocol),
        load_phase_four_scientific_gates(arguments.scientific_gates),
        stage=arguments.stage,
        scientific_contract_set_sha256=contract_set_sha256(
            arguments.scientific_contract
        ),
        candidate_identifier=arguments.candidate_id,
        reference_identifiers=(references[0], references[1]),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(arguments.output, decision)


if __name__ == "__main__":
    main()
