#!/usr/bin/env python3
"""Evaluate one compiled Phase 5 public-finder analysis exactly once."""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[2]
_PROTOCOL_PATH = _ROOT / "config/contracts/phase-5-public-finder-protocol.json"
_DECISION_PATH = (
    _ROOT / "config/contracts/phase-5-public-finder-execution-decision.json"
)
_ANALYSIS_PATH = (
    _ROOT / "benchmark-results/phase-5/public-finder-analysis.json"
)
_CAMPAIGN_PATH = (
    _ROOT / "benchmark-results/phase-5/public-finder-comparison/campaign.json"
)
_OUTPUT_PATH = _ROOT / "benchmark-results/phase-5/public-finder-decision.json"
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_public_finder_protocol.py")
)
_SDC1_POPULATION_COUNT = 9
_HEBOG_RUN_COUNT = 10


def evaluate_public_finder_analysis(
    analysis: dict[str, Any],
) -> dict[str, object]:
    """Apply the frozen terminal rule with science before runtime."""
    endpoint_value = analysis.get("sdc1_endpoints")
    if (
        not isinstance(endpoint_value, list)
        or len(cast(list[object], endpoint_value)) != _SDC1_POPULATION_COUNT
    ):
        raise ValueError("public SDC1 endpoint populations are incomplete")
    endpoints = cast(list[dict[str, Any]], endpoint_value)
    endpoint_pass = all(item.get("passed") is True for item in endpoints)
    run_pass = (
        analysis.get("successful_hebog_run_count")
        == analysis.get("expected_hebog_run_count")
        == _HEBOG_RUN_COUNT
    )
    hydra_pass = analysis.get("hydra_diagnostics_complete") is True
    status = "pass" if endpoint_pass and run_pass and hydra_pass else "fail"
    return {
        "status": status,
        "scientific": {
            "sdc1_all_binding_endpoints_passed": endpoint_pass,
            "sdc1_population_count": len(endpoints),
            "hydra_diagnostics_complete": hydra_pass,
            "hydra_binding": False,
        },
        "execution": {
            "all_hebog_runs_successful": run_pass,
            "successful_hebog_run_count": analysis.get(
                "successful_hebog_run_count"
            ),
            "expected_hebog_run_count": analysis.get(
                "expected_hebog_run_count"
            ),
        },
        "scientific_outcomes_interpreted_before_runtime": True,
        "public_evidence_opened": status == "pass",
        "cutover_authorized": False,
        "release_authorized": False,
    }


def _parse_args() -> argparse.Namespace:
    """Parse the exact separately authorized evaluation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path, default=_DECISION_PATH)
    parser.add_argument("--analysis", type=Path, default=_ANALYSIS_PATH)
    parser.add_argument("--output", type=Path, default=_OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    """Reject pending authority, then score one complete analysis once."""
    arguments = _parse_args()
    decision = _HELPERS["load_public_finder_execution_decision"](
        arguments.authorization
    )
    if not decision["evaluation_authorized"]:
        raise ValueError("public finder evaluation is not authorized")
    if (
        arguments.authorization.resolve() != _DECISION_PATH.resolve()
        or arguments.analysis.resolve() != _ANALYSIS_PATH.resolve()
        or arguments.output.resolve() != _OUTPUT_PATH.resolve()
    ):
        raise ValueError("public finder evaluation path changed")
    analysis = _HELPERS["json_object"](arguments.analysis)
    authorization_sha256 = _HELPERS["file_sha256"](arguments.authorization)
    if (
        analysis.get("analysis_id")
        != "phase-5-public-finder-terminal-analysis"
        or analysis.get("protocol_sha256")
        != _HELPERS["file_sha256"](_PROTOCOL_PATH)
        or analysis.get("execution_decision_sha256") != authorization_sha256
        or analysis.get("identity_review_sha256")
        != decision["identity_review"]["sha256"]
        or analysis.get("campaign_sha256")
        != _HELPERS["file_sha256"](_CAMPAIGN_PATH)
    ):
        raise ValueError("public finder analysis provenance changed")
    result = evaluate_public_finder_analysis(analysis)
    terminal = {
        "schema_version": 1,
        "decision_id": "phase-5-public-finder-terminal-decision",
        "analysis_sha256": _HELPERS["file_sha256"](arguments.analysis),
        "protocol_sha256": _HELPERS["file_sha256"](_PROTOCOL_PATH),
        **result,
        "runtime": analysis.get("runtime"),
    }
    _HELPERS["write_once_json"](arguments.output, terminal)


if __name__ == "__main__":
    main()
