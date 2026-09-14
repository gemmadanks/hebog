#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Apply unchanged gates and approved priors to post-correction evidence."""

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
    _ROOT / "config/contracts/phase-5-external-post-correction-evaluation.json"
)
_EVALUATOR_PATH = (
    "scripts/validation/evaluate_phase5_external_post_correction_decision.py"
)
_HELPERS = runpy.run_path(
    str(
        _ROOT
        / "scripts/validation/phase5_external_post_correction_protocol.py"
    )
)
_BASE_PATH = (
    _ROOT
    / "scripts/validation/evaluate_phase5_external_post_failure_decision.py"
)
_BASE = runpy.run_path(str(_BASE_PATH))
_BASE_EVALUATE = _BASE["evaluate_post_failure_analysis"]


def _install_historical_source_view() -> None:
    """Validate the closed base against its frozen source identity."""
    base_loader = _BASE["load_post_failure_evaluation_contract"]
    base_helpers = base_loader.__globals__["_HELPERS"]
    population_loader = base_helpers["load_post_failure_population"]
    population_loader.__globals__["source_tree_sha256"] = lambda _root: (
        population_loader.__globals__["_SOURCE_TREE_SHA256"]
    )


def load_post_correction_evaluation_contract(
    contract_path: Path,
    evaluator_path: Path,
) -> dict[str, Any]:
    """Validate fresh composition, unchanged gates, and approved priors."""
    document = _HELPERS["json_object"](contract_path)
    required = frozenset(
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
            "observable_compiler",
            "observable_measurement",
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
        description="post-correction evaluation contract",
    )
    if (
        document.get("schema_version") != 1
        or document.get("contract_id")
        != "phase-5-external-post-correction-evaluation"
        or document.get("status") != "frozen-before-campaign-output"
        or document.get("closed_campaign_reuse_authorized") is not False
        or document.get("one_look_rule")
        != "one-terminal-look-no-tuning-rescoring-reconfirmation-or-adaptive-"
        "sample-size"
        or document.get("evaluator_path") != _EVALUATOR_PATH
        or document.get("evaluator_sha256")
        != _HELPERS["file_sha256"](evaluator_path)
    ):
        raise ValueError("post-correction evaluation identity is invalid")
    root = evaluator_path.parents[2]
    base_path = (
        root / "config/contracts/phase-5-external-post-failure-evaluation.json"
    )
    if (
        document.get("base_evaluation_path")
        != "config/contracts/phase-5-external-post-failure-evaluation.json"
        or document.get("base_evaluation_sha256")
        != _HELPERS["file_sha256"](base_path)
    ):
        raise ValueError("post-correction evaluation ancestry changed")
    identities = tuple(
        document.get(name)
        for name in (
            "analysis_compiler",
            "endpoint_registry",
            "compiler_accelerator",
            "observable_measurement",
            "observable_compiler",
        )
    )
    if not all(isinstance(item, dict) for item in identities):
        raise ValueError(
            "post-correction evaluation composition is incomplete"
        )
    for identity, description in zip(
        identities,
        (
            "post-correction compiler",
            "post-correction registry",
            "compiler accelerator",
            "observable measurement",
            "observable compiler",
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
        ("protocol_path", "protocol_sha256", "post-correction protocol"),
        (
            "population_contract_path",
            "population_contract_sha256",
            "post-correction population",
        ),
    ):
        _HELPERS["require_bound_file"](
            root,
            document,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    registry_identity = cast(dict[str, Any], identities[1])
    _HELPERS["load_post_correction_endpoint_registry"](
        root / cast(str, registry_identity["path"])
    )
    _install_historical_source_view()
    base = _BASE["load_post_failure_evaluation_contract"](
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
    population = _HELPERS["load_post_correction_population"](
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
            raise ValueError("post-correction endpoint power prior changed")
    compatible["endpoint_power_priors"] = priors
    return compatible


def evaluate_post_correction_analysis(
    analysis: dict[str, Any],
    contract: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[Any, tuple[Any, ...], str]:
    """Evaluate the unique fresh identity through exact prior mechanics."""
    if (
        analysis.get("analysis_id")
        != "phase-5-external-post-correction-terminal-science"
    ):
        raise ValueError("post-correction compiled analysis identity changed")
    compatible = dict(analysis)
    compatible["analysis_id"] = (
        "phase-5-external-post-failure-terminal-science"
    )
    _BASE_EVALUATE.__globals__["_CONTINUUM_IMAGE_COUNT"] = 1688
    return cast(
        tuple[Any, tuple[Any, ...], str],
        _BASE_EVALUATE(compatible, contract, registry),
    )


def _parse_args() -> argparse.Namespace:
    """Parse post-correction analysis and write-once decision paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=_CONTRACT_PATH)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Evaluate one fresh analysis and publish one terminal decision."""
    arguments = _parse_args()
    if arguments.output.exists():
        message = (
            "refusing to overwrite post-correction decision: "
            f"{arguments.output}"
        )
        raise FileExistsError(message)
    contract = load_post_correction_evaluation_contract(
        arguments.contract,
        Path(__file__),
    )
    analysis = _HELPERS["json_object"](arguments.analysis)
    registry_identity = cast(dict[str, Any], contract["endpoint_registry"])
    registry = _HELPERS["load_post_correction_endpoint_registry"](
        _ROOT / cast(str, registry_identity["path"])
    )
    combined, endpoints, compact_status = evaluate_post_correction_analysis(
        analysis,
        contract,
        registry,
    )
    decision = {
        "schema_version": 1,
        "decision_id": "phase-5-external-post-correction-terminal-decision",
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
