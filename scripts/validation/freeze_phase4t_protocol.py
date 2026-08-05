"""Freeze the reviewed Phase 4T paired and absolute-power protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from hebog.validation.contracts import PairedNoninferiorityContract

_POPULATIONS: dict[str, tuple[str, int]] = {
    "compact-completeness": ("association-truth-groups", 49),
    "catalogue-reliability": ("association-truth-groups", 49),
    "association-pair-precision": ("association-truth-groups", 49),
    "association-pair-recall": ("association-truth-groups", 49),
    "fitted-shape-availability": ("individually-resolvable-sources", 48),
    "deconvolution-classification-availability": (
        "individually-resolvable-sources",
        48,
    ),
    "resolved-deconvolved-shape-availability": (
        "clear-resolved-sources",
        8,
    ),
    "association-identity-availability": (
        "individually-resolvable-sources",
        48,
    ),
    "position-flux-uncertainty-availability": (
        "individually-resolvable-sources",
        48,
    ),
    "point-source-specificity": ("point-sources", 32),
    "clear-resolved-classification-recall": (
        "clear-resolved-sources",
        8,
    ),
    "catastrophic-outlier-fraction": (
        "individually-resolvable-sources",
        48,
    ),
    "unresolved-group-completeness": (
        "unresolved-association-groups",
        1,
    ),
}


def _document(template: Path) -> dict[str, object]:
    """Derive the Phase 4T protocol from the reviewed endpoint family."""
    document = cast(
        dict[str, object],
        json.loads(template.read_text(encoding="utf-8")),
    )
    document.update(
        {
            "contract_id": "phase-4t-paired-noninferiority",
            "realization_count": 800,
            "human_scientific_review": (
                "project-owner-waived-independent-human-review"
            ),
            "expert_scientific_review": (
                "ai-conducted-review-completed-before-freeze"
            ),
            "qualification_scope": (
                "compact-single-scale-rapthor-used-behaviour"
            ),
            "controlled_residual_noise_injection": (
                "not-available-recorded-limitation"
            ),
            "absolute_mean_power_checks": [
                {
                    "metric_id": ("snr-10-integrated-flux-uncertainty-bias"),
                    "population_unit": "snr-10-point-sources",
                    "observations_per_realization": 8,
                    "planning_intracluster_correlation": 0.02,
                    "anticipated_mean_normalized_residual": 0.1062,
                    "planning_standard_deviation": 1.0,
                    "equivalence_margin": 0.15,
                    "confidence_level": 0.95,
                    "minimum_interval_containment_power": 0.9,
                    "method": "cluster-adjusted-normal-ci-containment",
                }
            ],
        }
    )
    resampling = cast(dict[str, object], document["resampling"])
    resampling["seed"] = 20260806
    binary_endpoints = cast(
        list[dict[str, object]], document["binary_endpoints"]
    )
    for endpoint in binary_endpoints:
        endpoint_id = cast(str, endpoint["endpoint_id"])
        population_unit, count = _POPULATIONS[endpoint_id]
        endpoint["population_unit"] = population_unit
        endpoint["observations_per_realization"] = count
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
