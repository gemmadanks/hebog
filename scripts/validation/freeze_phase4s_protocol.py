"""Freeze the reviewed Phase 4S paired non-inferiority protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from hebog.validation.contracts import PairedNoninferiorityContract

_POPULATIONS: dict[str, tuple[str, int]] = {
    "compact-completeness": ("association-truth-groups", 33),
    "catalogue-reliability": ("association-truth-groups", 33),
    "association-pair-precision": ("association-truth-groups", 33),
    "association-pair-recall": ("association-truth-groups", 33),
    "fitted-shape-availability": ("individually-resolvable-sources", 32),
    "deconvolution-classification-availability": (
        "individually-resolvable-sources",
        32,
    ),
    "resolved-deconvolved-shape-availability": (
        "clear-resolved-sources",
        8,
    ),
    "association-identity-availability": (
        "individually-resolvable-sources",
        32,
    ),
    "position-flux-uncertainty-availability": (
        "individually-resolvable-sources",
        32,
    ),
    "point-source-specificity": ("point-sources", 8),
    "clear-resolved-classification-recall": (
        "clear-resolved-sources",
        8,
    ),
    "catastrophic-outlier-fraction": (
        "individually-resolvable-sources",
        32,
    ),
    "unresolved-group-completeness": (
        "unresolved-association-groups",
        1,
    ),
}


def _document(template: Path) -> dict[str, object]:
    """Derive the exact reviewed protocol from the historical endpoint set."""
    document = cast(
        dict[str, object],
        json.loads(template.read_text(encoding="utf-8")),
    )
    document.update(
        {
            "contract_id": "phase-4s-paired-noninferiority",
            "realization_count": 800,
            "minimum_familywise_interval_exclusion_power": 0.9,
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
            "scientific_basis": [
                "https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/askapemu-source-finding-data-challenge/A6C846F3ABB0105F026E3BD6B6EB9D19",
                "https://adsabs.harvard.edu/pdf/1997PASP..109..166C",
                "https://arxiv.org/abs/1508.03150",
                "https://academic.oup.com/mnras/article/487/3/3971/5511783",
                "https://academic.oup.com/mnras/article/500/3/3821/5918002",
                "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html",
                "https://www.sciencedirect.com/science/article/pii/S0047259X12002175",
            ],
        }
    )
    resampling = cast(dict[str, object], document["resampling"])
    resampling["seed"] = 20260805
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
