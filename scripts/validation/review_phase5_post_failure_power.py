#!/usr/bin/env python3
"""Prepare the prospective Phase 5 post-failure power pre-review."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict
from math import isfinite
from pathlib import Path
from typing import cast

from hebog.validation.phase_five_post_failure_power import (
    build_paired_power_priors,
    conservative_familywise_power,
    minimum_realization_count,
    prospective_joint_power,
)

_CLOSED_ANALYSIS_SHA256 = (
    "cf14518b03f1f6f23c4784b8a6276982319aeb95d5e1cf15d9f90176dcfa8967"
)
_CLOSED_POPULATION_SHA256 = (
    "c346549df25c8b7d7bdadc6791e590d0333c08d918bd9c530b27042025444768"
)
_EXPECTED_PAIRED_COMPARISON_COUNT = 226
_VARIANCE_INFLATION = 1.25
_ADVANTAGE_RETENTION = 0.5
_SELECTED_CONTINUUM_REALIZATION_COUNT = 1600
_GEOMETRY_COUNT = 4


def _sha256(path: Path) -> str:
    """Return the exact file digest used by this planning review."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_object(path: Path) -> dict[str, object]:
    """Load one JSON object."""
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, object], value)


def _number(value: object, *, label: str) -> float:
    """Return one finite JSON number."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be numeric")
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{label} must be finite")
    return converted


def _integer(value: object, *, label: str) -> int:
    """Return one positive JSON integer."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def build_review(repository_root: Path) -> dict[str, object]:
    """Build the auditable pre-review from immutable closed evidence."""
    analysis_path = (
        repository_root
        / "benchmark-results/phase-5/external-confirmation-analysis.json"
    )
    population_path = (
        repository_root
        / "config/contracts/phase-5-external-confirmation-population.json"
    )
    analysis_sha256 = _sha256(analysis_path)
    population_sha256 = _sha256(population_path)
    if analysis_sha256 != _CLOSED_ANALYSIS_SHA256:
        raise ValueError("closed confirmation analysis identity changed")
    if population_sha256 != _CLOSED_POPULATION_SHA256:
        raise ValueError("closed confirmation population identity changed")
    analysis = _json_object(analysis_path)
    population = _json_object(population_path)
    power_audit = population.get("power_audit")
    if not isinstance(power_audit, dict):
        raise ValueError("closed population lacks its power audit")
    typed_power_audit = cast(Mapping[str, object], power_audit)
    assumptions = typed_power_audit.get("continuum_assumptions")
    if not isinstance(assumptions, list):
        raise ValueError("closed population lacks continuum assumptions")
    typed_assumptions = cast(list[Mapping[str, object]], assumptions)
    priors = build_paired_power_priors(
        analysis,
        typed_assumptions,
        variance_inflation=_VARIANCE_INFLATION,
        advantage_retention=_ADVANTAGE_RETENTION,
    )
    if len(priors) != _EXPECTED_PAIRED_COMPARISON_COUNT:
        raise ValueError("closed paired comparison population changed")
    compact_power = _number(
        typed_power_audit.get("compact_familywise_power_lower_bound"),
        label="compact familywise power",
    )
    minimum_joint_power = _number(
        typed_power_audit.get("minimum_joint_power"),
        label="minimum joint power",
    )
    compact_count = _integer(
        typed_power_audit.get("compact_realization_count"),
        label="compact realization count",
    )
    minimum_count = minimum_realization_count(
        priors,
        compact_familywise_power=compact_power,
        minimum_joint_power=minimum_joint_power,
    )
    selected_count = _SELECTED_CONTINUUM_REALIZATION_COUNT
    if selected_count < minimum_count:
        raise ValueError("selected continuum population is underpowered")
    if selected_count % _GEOMETRY_COUNT:
        raise ValueError("selected population must balance all geometries")
    continuum_power = conservative_familywise_power(priors, selected_count)
    combined_power = prospective_joint_power(continuum_power, compact_power)
    maximum_bounds: dict[str, float] = defaultdict(float)
    for prior in priors:
        maximum_bounds[prior.metric_family] = max(
            maximum_bounds[prior.metric_family],
            prior.planning_paired_standard_deviation,
        )
    return {
        "schema_version": 1,
        "review_id": "phase-5-post-failure-power-pre-review",
        "status": "scientific-pre-review-recommends-fresh-evidence",
        "closed_evidence": {
            "analysis_path": str(analysis_path.relative_to(repository_root)),
            "analysis_sha256": analysis_sha256,
            "population_path": str(
                population_path.relative_to(repository_root)
            ),
            "population_sha256": population_sha256,
            "reuse_as_confirmation_authorized": False,
        },
        "planning_method": (
            "endpoint-reference-cluster-normal-planning-plus-"
            "conservative-union-lower-bound"
        ),
        "variance_rule": {
            "inflation": _VARIANCE_INFLATION,
            "family_floor_retained": True,
            "formula": (
                "max(closed-family-bound, inflation*closed-endpoint-sd)"
            ),
            "assumption_failure": (
                "observed-variance-above-endpoint-bound-makes-comparison-"
                "underpowered"
            ),
        },
        "expected_regression_rule": {
            "retained_fraction_of_favourable_closed_difference": (
                _ADVANTAGE_RETENTION
            ),
            "unfavourable_closed_difference": "plan-at-equality",
            "formula": "min(0, retention*closed-positive-regression)",
        },
        "population": {
            "paired_continuum_comparison_count": len(priors),
            "minimum_continuum_realization_count": minimum_count,
            "selected_continuum_realization_count": selected_count,
            "continuum_geometry_count": _GEOMETRY_COUNT,
            "continuum_realizations_per_geometry": (
                selected_count // _GEOMETRY_COUNT
            ),
            "compact_realization_count": compact_count,
            "total_realization_count": selected_count + compact_count,
        },
        "power": {
            "minimum_joint_power": minimum_joint_power,
            "continuum_familywise_power_lower_bound": continuum_power,
            "compact_familywise_power_lower_bound": compact_power,
            "combined_familywise_power_lower_bound": combined_power,
        },
        "maximum_endpoint_variance_bound_by_metric": dict(
            sorted(maximum_bounds.items())
        ),
        "paired_assumptions": [asdict(prior) for prior in priors],
        "authorization": {
            "fresh_population_frozen": False,
            "execution_authorized": False,
            "step_three_authorized": False,
            "optimization_authorized": False,
            "qualification_opened": False,
            "required_next_decision": (
                "named-scientific-approval-before-freezing-fresh-identities"
            ),
        },
    }


def main() -> None:
    """Write the ignored machine-readable pre-review atomically."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).parents[2],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "benchmark-results/phase-5/post-failure-power-pre-review.json"
        ),
    )
    arguments = parser.parse_args()
    root = arguments.repository_root.resolve()
    output = arguments.output
    if not output.is_absolute():
        output = root / output
    review = build_review(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    print(output)


if __name__ == "__main__":
    main()
