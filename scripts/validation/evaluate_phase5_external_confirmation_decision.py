#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Apply unchanged gates to one compiled confirmation campaign."""

from __future__ import annotations

import argparse
import json
import runpy
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[2]
_SUCCESSOR_EVALUATOR_PATH = (
    _ROOT / "scripts/validation/evaluate_phase5_external_successor_decision.py"
)
_CONTRACT_PATH = (
    _ROOT / "config/contracts/phase-5-external-confirmation-evaluation.json"
)
_EVALUATOR_PATH = (
    "scripts/validation/evaluate_phase5_external_confirmation_decision.py"
)
_SUCCESSOR = runpy.run_path(str(_SUCCESSOR_EVALUATOR_PATH))
_TERMINAL = _SUCCESSOR["_TERMINAL"]
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_confirmation_protocol.py")
)


def load_confirmation_evaluation_contract(
    contract_path: Path,
    evaluator_path: Path,
) -> dict[str, Any]:
    """Verify confirmation composition and every inherited gate value."""
    document = _HELPERS["json_object"](contract_path)
    _HELPERS["require_exact_keys"](
        document,
        frozenset(
            {
                "analysis_compiler",
                "base_evaluation_path",
                "base_evaluation_sha256",
                "closed_campaign_reuse_authorized",
                "compiler_accelerator",
                "contract_id",
                "endpoint_registry",
                "evaluator_path",
                "evaluator_sha256",
                "one_look_rule",
                "protocol_path",
                "protocol_sha256",
                "schema_version",
                "status",
            }
        ),
        description="confirmation evaluation contract",
    )
    if (
        document.get("schema_version") != 1
        or document.get("contract_id")
        != "phase-5-external-confirmation-evaluation"
        or document.get("status") != "frozen-before-campaign-output"
        or document.get("closed_campaign_reuse_authorized") is not False
        or document.get("one_look_rule")
        != "one-terminal-look-no-tuning-rescoring-reconfirmation-or-adaptive-"
        "sample-size"
        or document.get("evaluator_path") != _EVALUATOR_PATH
        or document.get("evaluator_sha256")
        != _HELPERS["file_sha256"](evaluator_path)
    ):
        raise ValueError("confirmation evaluation identity is invalid")
    root = evaluator_path.parents[2]
    base_path = (
        root / "config/contracts/phase-5-external-successor-evaluation.json"
    )
    if (
        document.get("base_evaluation_path")
        != "config/contracts/phase-5-external-successor-evaluation.json"
        or document.get("base_evaluation_sha256")
        != _HELPERS["file_sha256"](base_path)
    ):
        raise ValueError("confirmation evaluation ancestry changed")
    identities = tuple(
        document.get(name)
        for name in (
            "analysis_compiler",
            "endpoint_registry",
            "compiler_accelerator",
        )
    )
    if not all(isinstance(item, dict) for item in identities):
        raise ValueError("confirmation evaluation composition is incomplete")
    for identity, description in zip(
        identities,
        (
            "confirmation compiler",
            "confirmation registry",
            "compiler accelerator",
        ),
        strict=True,
    ):
        _HELPERS["require_exact_keys"](
            identity,
            frozenset({"path", "sha256", "status"}),
            description="confirmation evaluation artifact",
        )
        _HELPERS["require_bound_file"](
            root,
            identity,
            path_key="path",
            sha_key="sha256",
            description=description,
        )
    for path_key, sha_key, description in (
        ("protocol_path", "protocol_sha256", "confirmation protocol"),
    ):
        _HELPERS["require_bound_file"](
            root,
            document,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    registry = cast(dict[str, Any], identities[1])
    _HELPERS["load_confirmation_endpoint_registry"](
        root / cast(str, registry["path"])
    )
    base = _SUCCESSOR["load_successor_evaluation_contract"](
        base_path,
        _SUCCESSOR_EVALUATOR_PATH,
    )
    compatible = dict(base)
    compatible.update(document)
    return compatible


def evaluate_confirmation_analysis(
    analysis: dict[str, Any],
    contract: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[Any, tuple[Any, ...], str]:
    """Evaluate the unique confirmation identity through unchanged gates."""
    compiler = cast(dict[str, Any], contract["analysis_compiler"])
    registry_identity = cast(dict[str, Any], contract["endpoint_registry"])
    accelerator = cast(dict[str, Any], contract["compiler_accelerator"])
    if (
        analysis.get("analysis_id")
        != "phase-5-external-confirmation-terminal-science"
        or analysis.get("closed_campaign_reuse_authorized") is not False
        or analysis.get("successor_science_kernel_sha256")
        != "8e38de3b4347faee9636b89d03f8cdcdd77e39fd1e087d2b44454e5fd7063c55"
        or analysis.get("compiler_accelerator_sha256") != accelerator["sha256"]
        or analysis.get("compiler_sha256") != compiler["sha256"]
        or analysis.get("endpoint_registry_sha256")
        != registry_identity["sha256"]
    ):
        raise ValueError("confirmation compiled analysis identity changed")
    compatible = dict(analysis)
    compatible["analysis_id"] = "phase-5-external-terminal-science"
    return cast(
        tuple[Any, tuple[Any, ...], str],
        _TERMINAL["evaluate_compiled_analysis"](
            compatible,
            contract,
            registry,
        ),
    )


def _parse_args() -> argparse.Namespace:
    """Parse confirmation analysis and write-once decision paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=_CONTRACT_PATH)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Evaluate one confirmation analysis and publish one decision."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite confirmation decision: {arguments.output}"
        )
    contract = load_confirmation_evaluation_contract(
        arguments.contract,
        Path(__file__),
    )
    analysis = _HELPERS["json_object"](arguments.analysis)
    registry_identity = cast(dict[str, Any], contract["endpoint_registry"])
    registry = _HELPERS["load_confirmation_endpoint_registry"](
        _ROOT / cast(str, registry_identity["path"])
    )
    combined, endpoints, compact_status = evaluate_confirmation_analysis(
        analysis,
        contract,
        registry,
    )
    decision = {
        "schema_version": 1,
        "decision_id": "phase-5-external-confirmation-terminal-decision",
        "status": combined.status,
        "analysis_sha256": _HELPERS["file_sha256"](arguments.analysis),
        "contract_sha256": _HELPERS["file_sha256"](arguments.contract),
        "campaign": asdict(combined),
        "continuum_endpoints": [asdict(item) for item in endpoints],
        "compact_status": compact_status,
        "closed_campaign_reuse_authorized": False,
        "scientific_outcomes_before_runtime": True,
        "step_three_authorized": False,
        "optimization_authorized": False,
        "qualification_opened": False,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as output:
        output.write(
            (
                json.dumps(
                    decision,
                    allow_nan=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode()
        )


if __name__ == "__main__":
    main()
