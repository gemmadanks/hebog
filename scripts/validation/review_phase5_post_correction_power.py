#!/usr/bin/env python3
"""Plan a powered fresh campaign from the passing cumulative science view."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from math import ceil
from pathlib import Path
from typing import cast

from hebog.validation.external_runners import source_tree_sha256
from hebog.validation.phase_five_post_failure_power import (
    build_paired_power_priors,
    conservative_familywise_power,
    minimum_realization_count,
    prospective_joint_power,
)

_ROOT = Path(__file__).parents[2]
_CONFIRMATION_POPULATION = (
    _ROOT / "config/contracts/phase-5-external-confirmation-population.json"
)
_POST_FAILURE_POPULATION = (
    _ROOT / "config/contracts/phase-5-external-post-failure-population.json"
)
_CONFIRMATION_POPULATION_SHA256 = (
    "c346549df25c8b7d7bdadc6791e590d0333c08d918bd9c530b27042025444768"
)
_POST_FAILURE_POPULATION_SHA256 = (
    "42c3d07c2aeb74caf00f6e888a9cf3c6cecda3f05decb820db7e18cb646d87fd"
)
_VARIANCE_INFLATION = 1.25
_ADVANTAGE_RETENTION = 0.5
_POPULATION_SAFETY_FACTOR = 1.10
_POPULATION_SAFETY_NUMERATOR = 11
_POPULATION_SAFETY_DENOMINATOR = 10
_GEOMETRY_COUNT = 4
_MINIMUM_CONTINUUM_COUNT = 1600


def _sha256(path: Path) -> str:
    """Return one exact file identity."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_object(path: Path) -> dict[str, object]:
    """Load one JSON object or fail clearly."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, object], value)


def _git_revision(root: Path) -> str:
    """Return the clean revision whose source identity the ledger binds."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=root,
        text=True,
    )
    if status:
        raise ValueError("power review requires a clean source checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        text=True,
    ).strip()


def _selected_realization_count(minimum_count: int) -> int:
    """Add a fixed safety buffer and balance all four geometries."""
    if minimum_count < 1:
        raise ValueError("minimum realization count must be positive")
    buffered = max(
        _MINIMUM_CONTINUUM_COUNT,
        (
            _POPULATION_SAFETY_NUMERATOR * minimum_count
            + _POPULATION_SAFETY_DENOMINATOR
            - 1
        )
        // _POPULATION_SAFETY_DENOMINATOR,
    )
    return ceil(buffered / _GEOMETRY_COUNT) * _GEOMETRY_COUNT


def _validate_ledger(
    ledger: dict[str, object],
    *,
    root: Path,
) -> list[dict[str, object]]:
    """Require the clean candidate and a regression-ready science view."""
    if ledger.get("status") not in {"pass", "pass-pending-power-review"}:
        raise ValueError("cumulative ledger has not passed scientific review")
    if ledger.get("cumulative_science_regression_ready") is not True:
        raise ValueError("cumulative science regressions remain unresolved")
    if ledger.get("like_semantics_compact_regressions") != []:
        raise ValueError("compact cumulative regressions remain")
    if ledger.get("like_semantics_continuum_regressions") != []:
        raise ValueError("Continuum cumulative regressions remain")
    if ledger.get("candidate_revision") != _git_revision(root):
        raise ValueError("cumulative candidate revision differs from checkout")
    if ledger.get("candidate_source_tree_sha256") != source_tree_sha256(root):
        raise ValueError("cumulative candidate source identity changed")
    endpoints = ledger.get("prospective_continuum_analysis")
    if not isinstance(endpoints, list) or not endpoints:
        raise ValueError("cumulative ledger lacks raw Continuum analysis")
    endpoint_values = cast(list[object], endpoints)
    if not all(isinstance(item, dict) for item in endpoint_values):
        raise ValueError("cumulative Continuum analysis is malformed")
    return cast(list[dict[str, object]], endpoint_values)


def build_review(
    repository_root: Path,
    cumulative_ledger_path: Path,
) -> dict[str, object]:
    """Build an exact endpoint-level fresh-population power review."""
    root = repository_root.resolve()
    if _sha256(_CONFIRMATION_POPULATION) != (_CONFIRMATION_POPULATION_SHA256):
        raise ValueError("governed Continuum family assumptions changed")
    if _sha256(_POST_FAILURE_POPULATION) != (_POST_FAILURE_POPULATION_SHA256):
        raise ValueError("governed post-failure power policy changed")
    ledger = _json_object(cumulative_ledger_path)
    endpoints = _validate_ledger(ledger, root=root)
    confirmation = _json_object(_CONFIRMATION_POPULATION)
    post_failure = _json_object(_POST_FAILURE_POPULATION)
    confirmation_power = cast(dict[str, object], confirmation["power_audit"])
    post_failure_power = cast(dict[str, object], post_failure["power_audit"])
    priors = build_paired_power_priors(
        {"continuum_endpoints": endpoints},
        cast(
            list[dict[str, object]],
            confirmation_power["continuum_assumptions"],
        ),
        variance_inflation=_VARIANCE_INFLATION,
        advantage_retention=_ADVANTAGE_RETENTION,
    )
    compact_power = float(
        cast(float, post_failure_power["compact_familywise_power_lower_bound"])
    )
    minimum_joint_power = float(
        cast(float, post_failure_power["minimum_joint_power"])
    )
    minimum_count = minimum_realization_count(
        priors,
        compact_familywise_power=compact_power,
        minimum_joint_power=minimum_joint_power,
    )
    selected_count = _selected_realization_count(minimum_count)
    continuum_power = conservative_familywise_power(priors, selected_count)
    joint_power = prospective_joint_power(continuum_power, compact_power)
    if joint_power < minimum_joint_power:
        raise ValueError("buffered fresh population remains underpowered")
    return {
        "schema_version": 1,
        "review_id": "phase-5-post-correction-power-review",
        "status": "ready-for-named-scientific-freeze-review",
        "cumulative_ledger": {
            "path": str(cumulative_ledger_path.relative_to(root)),
            "sha256": _sha256(cumulative_ledger_path),
            "candidate_revision": ledger["candidate_revision"],
            "candidate_source_tree_sha256": ledger[
                "candidate_source_tree_sha256"
            ],
            "candidate_configuration_sha256": ledger[
                "candidate_configuration_sha256"
            ],
        },
        "planning": {
            "method": (
                "endpoint-reference-cluster-normal-planning-plus-"
                "conservative-union-lower-bound"
            ),
            "paired_comparison_count": len(priors),
            "variance_inflation": _VARIANCE_INFLATION,
            "advantage_retention": _ADVANTAGE_RETENTION,
            "population_safety_factor": _POPULATION_SAFETY_FACTOR,
            "geometry_count": _GEOMETRY_COUNT,
            "minimum_continuum_realization_count": minimum_count,
            "selected_continuum_realization_count": selected_count,
            "continuum_realizations_per_geometry": (
                selected_count // _GEOMETRY_COUNT
            ),
            "compact_realization_count": int(
                cast(int, post_failure_power["compact_realization_count"])
            ),
        },
        "power": {
            "minimum_joint_power": minimum_joint_power,
            "continuum_familywise_power_lower_bound": continuum_power,
            "compact_familywise_power_lower_bound": compact_power,
            "combined_familywise_power_lower_bound": joint_power,
        },
        "paired_assumptions": [asdict(item) for item in priors],
        "authorization": {
            "fresh_population_frozen": False,
            "execution_authorized": False,
            "step_three_authorized": False,
            "qualification_opened": False,
            "required_next_decision": (
                "named-scientific-approval-before-freezing-fresh-identities"
            ),
        },
    }


def main() -> None:
    """Write the ignored machine-readable review atomically."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    ledger = arguments.ledger.resolve()
    output = arguments.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite power review: {output}")
    review = build_review(_ROOT, ledger)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(review, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    planning = cast(dict[str, object], review["planning"])
    power = cast(dict[str, object], review["power"])
    print(output)
    print(
        "selected_continuum_realizations="
        f"{planning['selected_continuum_realization_count']}"
    )
    print(
        "combined_familywise_power_lower_bound="
        f"{power['combined_familywise_power_lower_bound']}"
    )


if __name__ == "__main__":
    main()
