"""Calculate the design-stage power of the Phase 4 paired protocol."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from hebog.validation.contracts import load_paired_noninferiority_contract
from hebog.validation.noninferiority import require_adequate_design_power


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    return parser


def main() -> None:
    """Validate a protocol and print its power estimates as canonical JSON."""
    arguments = _parser().parse_args()
    contract = load_paired_noninferiority_contract(arguments.contract)
    estimates = require_adequate_design_power(contract)
    payload: dict[str, object] = {
        "contract_id": contract.contract_id,
        "minimum_interval_exclusion_power": (
            contract.minimum_interval_exclusion_power
        ),
        "power_target_applies_to": contract.decision.power_target_applies_to,
        "realization_count": contract.realization_count,
        "estimates": [asdict(estimate) for estimate in estimates],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
