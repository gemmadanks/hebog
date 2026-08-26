#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Evaluate one analysis produced by the qualification repair compiler."""

from __future__ import annotations

import argparse
import json
import runpy
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[2]
_REPAIR_COMPILER_RELATIVE = (
    "scripts/validation/compile_phase5_final_qualification_repair.py"
)
_REPAIR_COMPILER_PATH = _ROOT / _REPAIR_COMPILER_RELATIVE
_REPAIR = runpy.run_path(str(_REPAIR_COMPILER_PATH))
_FROZEN_EVALUATOR_RELATIVE = (
    "scripts/validation/evaluate_phase5_final_qualification_decision.py"
)
_FROZEN_EVALUATOR_PATH = _ROOT / _FROZEN_EVALUATOR_RELATIVE
_FROZEN = runpy.run_path(str(_FROZEN_EVALUATOR_PATH))
_FROZEN_COMPILER_SHA256 = (
    "c2b7f3ac3b072ba1c250cd27c917495cab3ba517cfb86a9102d06c763b66b165"
)
_FROZEN_EVALUATOR_SHA256 = (
    "558e29574287aef6bee348fb37c329b7dab2f115ff42c481d3a1019d3f713560"
)
_CONTRACT_PATH = (
    _ROOT / "config/contracts/phase-5-final-qualification-evaluation.json"
)
_REGISTRY_PATH = (
    _ROOT
    / "config/contracts/phase-5-final-qualification-endpoint-registry.json"
)
_ANALYSIS_RELATIVE = (
    "benchmark-results/phase-5/final-qualification-analysis.json"
)
_DECISION_RELATIVE = (
    "benchmark-results/phase-5/final-qualification-decision.json"
)


def load_repaired_analysis(
    path: Path,
    authorization_path: Path,
    authorization: dict[str, Any],
) -> dict[str, Any]:
    """Validate repair provenance before unchanged frozen scoring."""
    analysis = _REPAIR["json_object"](path)
    provenance = analysis.get("evaluation_repair")
    campaign = cast(dict[str, Any], authorization["campaign"])
    compiler = cast(dict[str, Any], authorization["repair_compiler"])
    review = cast(dict[str, Any], authorization["repair_identity_review"])
    expected_provenance = {
        "authorization_sha256": _REPAIR["file_sha256"](authorization_path),
        "compatibility_change": (
            "install-final-loaders-at-inherited-compatibility-seam"
        ),
        "frozen_compiler_sha256": _FROZEN_COMPILER_SHA256,
        "frozen_evaluator_sha256": _FROZEN_EVALUATOR_SHA256,
        "repair_compiler_sha256": compiler["sha256"],
        "repair_identity_review_sha256": review["sha256"],
        "science_or_gates_changed": False,
    }
    if (
        analysis.get("analysis_id")
        != "phase-5-final-qualification-terminal-science"
        or analysis.get("campaign_sha256") != campaign["sha256"]
        or provenance != expected_provenance
    ):
        raise ValueError("final qualification repair provenance changed")
    return cast(dict[str, Any], analysis)


def evaluate_repaired_analysis(
    analysis: dict[str, Any],
    contract: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[Any, tuple[Any, ...], str]:
    """Delegate all scientific decisions to the frozen pure evaluator."""
    return cast(
        tuple[Any, tuple[Any, ...], str],
        _FROZEN["evaluate_final_qualification_analysis"](
            analysis,
            contract,
            registry,
        ),
    )


def _canonical_json_bytes(value: object) -> bytes:
    """Serialize one finite deterministic evidence record."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _parse_args() -> argparse.Namespace:
    """Parse the separately approved repair authorization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Score the repaired analysis once using the frozen evaluator."""
    arguments = _parse_args()
    authorization = _REPAIR["load_repair_authorization"](
        arguments.authorization,
        _REPAIR_COMPILER_PATH,
        Path(__file__),
        _ROOT,
        stage="evaluate",
    )
    analysis_path = _ROOT / _ANALYSIS_RELATIVE
    analysis = load_repaired_analysis(
        analysis_path,
        arguments.authorization,
        authorization,
    )
    contract = _FROZEN["load_final_qualification_evaluation_contract"](
        _CONTRACT_PATH,
        _FROZEN_EVALUATOR_PATH,
    )
    registry = _FROZEN["_HELPERS"][
        "load_final_qualification_endpoint_registry"
    ](_REGISTRY_PATH)
    combined, endpoints, compact_status = evaluate_repaired_analysis(
        analysis, contract, registry
    )
    repair_review = cast(
        dict[str, Any], authorization["repair_identity_review"]
    )
    decision = {
        "schema_version": 1,
        "decision_id": "phase-5-final-qualification-terminal-decision",
        "status": combined.status,
        "analysis_sha256": _REPAIR["file_sha256"](analysis_path),
        "contract_sha256": _REPAIR["file_sha256"](_CONTRACT_PATH),
        "campaign": asdict(combined),
        "continuum_endpoints": [asdict(item) for item in endpoints],
        "compact_status": compact_status,
        "evaluation_repair": {
            "authorization_sha256": _REPAIR["file_sha256"](
                arguments.authorization
            ),
            "frozen_evaluator_sha256": _FROZEN_EVALUATOR_SHA256,
            "repair_evaluator_sha256": _REPAIR["file_sha256"](Path(__file__)),
            "repair_identity_review_sha256": repair_review["sha256"],
            "science_or_gates_changed": False,
        },
        "scientific_outcomes_before_runtime": True,
        "qualification_opened": True,
        "cutover_authorized": False,
    }
    output = _ROOT / _DECISION_RELATIVE
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(_canonical_json_bytes(decision))


if __name__ == "__main__":
    main()
