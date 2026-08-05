"""Calculate the design-stage power of the Phase 4 paired protocol."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from hebog.validation.campaign_runtime import dataset_by_identifier
from hebog.validation.contracts import load_paired_noninferiority_contract
from hebog.validation.noninferiority import (
    audit_design_population,
    familywise_power_lower_bound,
    require_adequate_design_power,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--dataset-manifest", type=Path)
    parser.add_argument("--dataset-id")
    return parser


def main() -> None:
    """Validate a protocol and print its power estimates as canonical JSON."""
    arguments = _parser().parse_args()
    if (arguments.dataset_manifest is None) != (arguments.dataset_id is None):
        raise ValueError(
            "dataset manifest and dataset ID must be supplied together"
        )
    contract = load_paired_noninferiority_contract(arguments.contract)
    dataset = (
        dataset_by_identifier(
            arguments.dataset_manifest,
            arguments.dataset_id,
        )
        if arguments.dataset_manifest is not None
        and arguments.dataset_id is not None
        else None
    )
    estimates = require_adequate_design_power(contract, dataset=dataset)
    payload: dict[str, object] = {
        "contract_id": contract.contract_id,
        "minimum_interval_exclusion_power": (
            contract.minimum_interval_exclusion_power
        ),
        "power_target_applies_to": contract.decision.power_target_applies_to,
        "realization_count": contract.realization_count,
        "familywise_interval_exclusion_power_lower_bound": (
            familywise_power_lower_bound(estimates)
        ),
        "estimates": [asdict(estimate) for estimate in estimates],
    }
    if dataset is not None:
        payload["dataset_id"] = dataset.identifier
        payload["population_audits"] = [
            asdict(audit)
            for audit in audit_design_population(contract, dataset)
        ]
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
