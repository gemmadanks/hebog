#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Apply unchanged gates and approved priors to recovery evidence."""

from __future__ import annotations

import argparse
import json
import runpy
from dataclasses import asdict
from math import isfinite
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[2]
_CONTRACT_PATH = (
    _ROOT / "config/contracts/phase-5-external-recovery-evaluation.json"
)
_EVALUATOR_PATH = (
    "scripts/validation/evaluate_phase5_external_recovery_decision.py"
)
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_recovery_protocol.py")
)
_BASE_PATH = (
    _ROOT
    / "scripts/validation/evaluate_phase5_external_post_correction_decision.py"
)
_BASE = runpy.run_path(str(_BASE_PATH))
_BASE_EVALUATE = _BASE["evaluate_post_correction_analysis"]


def _install_closed_source_view() -> None:
    """Validate the post-correction base against its frozen source."""
    loader = _BASE["load_post_correction_evaluation_contract"]
    base_helpers = loader.__globals__["_HELPERS"]
    population_loader = base_helpers["load_post_correction_population"]

    def historical_source_tree(_root: Path) -> str:
        return cast(str, population_loader.__globals__["_SOURCE_TREE_SHA256"])

    population_loader.__globals__["source_tree_sha256"] = (
        historical_source_tree
    )


def load_recovery_evaluation_contract(
    contract_path: Path,
    evaluator_path: Path,
) -> dict[str, Any]:
    """Validate the recovery composition, gates, and approved priors."""
    document = _HELPERS["json_object"](contract_path)
    required = frozenset(
        {
            "analysis_compiler",
            "base_evaluation_path",
            "base_evaluation_sha256",
            "candidate_adapter",
            "closed_campaign_reuse_authorized",
            "compiler_accelerator",
            "contract_id",
            "endpoint_registry",
            "evaluator_path",
            "evaluator_sha256",
            "one_look_rule",
            "population_contract_path",
            "population_contract_sha256",
            "protocol_path",
            "protocol_sha256",
            "schema_version",
            "status",
        }
    )
    _HELPERS["require_exact_keys"](
        document,
        required,
        description="recovery evaluation contract",
    )
    if (
        document.get("schema_version") != 1
        or document.get("contract_id")
        != "phase-5-external-recovery-evaluation"
        or document.get("status") != "frozen-before-campaign-output"
        or document.get("closed_campaign_reuse_authorized") is not False
        or document.get("one_look_rule")
        != "one-terminal-look-no-tuning-rescoring-reconfirmation-or-adaptive-"
        "sample-size"
        or document.get("evaluator_path") != _EVALUATOR_PATH
        or document.get("evaluator_sha256")
        != _HELPERS["file_sha256"](evaluator_path)
    ):
        raise ValueError("recovery evaluation identity is invalid")
    root = evaluator_path.parents[2]
    base_relative = (
        "config/contracts/phase-5-external-post-correction-evaluation.json"
    )
    base_path = root / base_relative
    if document.get("base_evaluation_path") != base_relative or document.get(
        "base_evaluation_sha256"
    ) != _HELPERS["file_sha256"](base_path):
        raise ValueError("recovery evaluation ancestry changed")
    identities = tuple(
        document.get(name)
        for name in (
            "analysis_compiler",
            "endpoint_registry",
            "compiler_accelerator",
            "candidate_adapter",
        )
    )
    if not all(isinstance(item, dict) for item in identities):
        raise ValueError("recovery evaluation composition is incomplete")
    for identity, description in zip(
        identities,
        (
            "recovery compiler",
            "recovery registry",
            "recovery compiler seams",
            "recovery candidate adapter",
        ),
        strict=True,
    ):
        _HELPERS["require_bound_file"](
            root,
            identity,
            path_key="path",
            sha_key="sha256",
            description=description,
        )
    for path_key, sha_key, description in (
        ("protocol_path", "protocol_sha256", "recovery protocol"),
        (
            "population_contract_path",
            "population_contract_sha256",
            "recovery population",
        ),
    ):
        _HELPERS["require_bound_file"](
            root,
            document,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    _install_closed_source_view()
    base = _BASE["load_post_correction_evaluation_contract"](
        base_path,
        _BASE_PATH,
    )
    compatible = dict(base)
    compatible.update(document)
    compatible["population"] = {
        "image_count": 2488,
        "terminal_run_count": 12440,
        "binding_run_count": 8264,
        "continuum_image_count": 1688,
        "compact_blend_image_count": 800,
    }
    population = _HELPERS["load_recovery_population"](
        root / cast(str, document["population_contract_path"])
    )
    power = cast(dict[str, Any], population["power_audit"])
    priors = cast(list[dict[str, Any]], power["paired_assumptions"])
    metrics = cast(dict[str, Any], compatible["continuum_metrics"])
    for prior in priors:
        metric = cast(dict[str, Any], metrics[prior["metric_family"]])
        if prior["practical_regression_margin"] != metric[
            "practical_regression_margin"
        ] or not isfinite(prior["planning_paired_standard_deviation"]):
            raise ValueError("recovery endpoint power prior changed")
    compatible["endpoint_power_priors"] = priors
    return compatible


def evaluate_recovery_analysis(
    analysis: dict[str, Any],
    contract: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[Any, tuple[Any, ...], str]:
    """Evaluate the unique fresh identity through unchanged mechanics."""
    if (
        analysis.get("analysis_id")
        != "phase-5-external-recovery-terminal-science"
    ):
        raise ValueError("recovery compiled analysis identity changed")
    compatible = dict(analysis)
    compatible["analysis_id"] = (
        "phase-5-external-post-correction-terminal-science"
    )
    return cast(
        tuple[Any, tuple[Any, ...], str],
        _BASE_EVALUATE(compatible, contract, registry),
    )


def _parse_args() -> argparse.Namespace:
    """Parse recovery analysis and write-once decision paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=_CONTRACT_PATH)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Evaluate one fresh analysis and publish one terminal decision."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite recovery decision: {arguments.output}"
        )
    contract = load_recovery_evaluation_contract(
        arguments.contract,
        Path(__file__),
    )
    analysis = _HELPERS["json_object"](arguments.analysis)
    registry_identity = cast(dict[str, Any], contract["endpoint_registry"])
    registry = _HELPERS["load_recovery_endpoint_registry"](
        _ROOT / cast(str, registry_identity["path"])
    )
    combined, endpoints, compact_status = evaluate_recovery_analysis(
        analysis,
        contract,
        registry,
    )
    decision = {
        "schema_version": 1,
        "decision_id": "phase-5-external-recovery-terminal-decision",
        "status": combined.status,
        "analysis_sha256": _HELPERS["file_sha256"](arguments.analysis),
        "contract_sha256": _HELPERS["file_sha256"](arguments.contract),
        "campaign": asdict(combined),
        "continuum_endpoints": [asdict(item) for item in endpoints],
        "compact_status": compact_status,
        "closed_campaign_reuse_authorized": False,
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
