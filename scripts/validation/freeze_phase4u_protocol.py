"""Freeze the reviewed Phase 4U paired and absolute-power protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from hebog.validation.contracts import PairedNoninferiorityContract

_POPULATION_COUNTS = {
    "compact-completeness": 54,
    "catalogue-reliability": 54,
    "association-pair-precision": 54,
    "association-pair-recall": 54,
    "fitted-shape-availability": 48,
    "deconvolution-classification-availability": 48,
    "resolved-deconvolved-shape-availability": 8,
    "association-identity-availability": 48,
    "position-flux-uncertainty-availability": 48,
    "point-source-specificity": 32,
    "clear-resolved-classification-recall": 8,
    "catastrophic-outlier-fraction": 48,
    "unresolved-group-completeness": 6,
}


def _document(template: Path) -> dict[str, object]:
    """Derive Phase 4U without changing endpoints or absolute limits."""
    document = cast(
        dict[str, object],
        json.loads(template.read_text(encoding="utf-8")),
    )
    document["contract_id"] = "phase-4u-paired-noninferiority"
    resampling = cast(dict[str, object], document["resampling"])
    resampling["seed"] = 20260807
    endpoints = cast(list[dict[str, object]], document["binary_endpoints"])
    for endpoint in endpoints:
        endpoint_id = cast(str, endpoint["endpoint_id"])
        endpoint["observations_per_realization"] = _POPULATION_COUNTS[
            endpoint_id
        ]
        endpoint["planning_intracluster_correlation"] = 0.02
    validated = PairedNoninferiorityContract.model_validate(document)
    return cast(dict[str, object], validated.model_dump(mode="json"))


def _parse_args() -> argparse.Namespace:
    """Parse the immutable protocol derivation paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Write the canonical protocol without replacing a frozen file."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite frozen protocol: {arguments.output}"
        )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(
            _document(arguments.template),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
