#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Apply frozen gates to the final Phase 5 qualification evidence."""

from __future__ import annotations

import argparse
import json
import runpy
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[2]
_CONTRACT_PATH = (
    _ROOT / "config/contracts/phase-5-final-qualification-evaluation.json"
)
_EVALUATOR_PATH = (
    "scripts/validation/evaluate_phase5_final_qualification_decision.py"
)
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_final_qualification_protocol.py")
)
_RECOVERY_PATH = (
    _ROOT / "scripts/validation/evaluate_phase5_external_recovery_decision.py"
)
_RECOVERY = runpy.run_path(str(_RECOVERY_PATH))
_ENDPOINT = runpy.run_path(
    str(
        _ROOT / "scripts/validation/"
        "evaluate_phase5_external_post_failure_decision.py"
    )
)
_TERMINAL = _ENDPOINT["_TERMINAL"]
_CONTINUUM_IMAGE_COUNT = 1688


def _install_closed_recovery_source_view() -> None:
    """Validate the inherited recovery contract against its frozen tree."""
    loader = _RECOVERY["load_recovery_evaluation_contract"]
    helpers = loader.__globals__["_HELPERS"]
    population_loader = helpers["load_recovery_population"]

    def historical_source_tree(_root: Path) -> str:
        return cast(str, population_loader.__globals__["_SOURCE_TREE_SHA256"])

    population_loader.__globals__["source_tree_sha256"] = (
        historical_source_tree
    )


def load_final_qualification_evaluation_contract(
    contract_path: Path,
    evaluator_path: Path,
) -> dict[str, Any]:
    """Validate the final composition and inherit unchanged endpoint gates."""
    document = _HELPERS["json_object"](contract_path)
    if (
        document.get("schema_version") != 1
        or document.get("contract_id")
        != "phase-5-final-qualification-evaluation"
        or document.get("status") != "frozen-before-qualification-output"
        or document.get("one_look_rule")
        != "one-terminal-look-no-tuning-rescoring-reconfirmation-or-adaptive-"
        "sample-size"
        or document.get("closed_compact_evidence_only") is not True
        or document.get("evaluator_path") != _EVALUATOR_PATH
        or document.get("evaluator_sha256")
        != _HELPERS["file_sha256"](evaluator_path)
    ):
        raise ValueError("final qualification evaluation identity is invalid")
    root = evaluator_path.parents[2]
    base_relative = (
        "config/contracts/phase-5-external-recovery-evaluation.json"
    )
    if document.get("base_evaluation_path") != base_relative or document.get(
        "base_evaluation_sha256"
    ) != _HELPERS["file_sha256"](root / base_relative):
        raise ValueError("final qualification evaluation ancestry changed")
    for identity_key, description in (
        ("analysis_compiler", "final compiler"),
        ("endpoint_registry", "final endpoint registry"),
    ):
        identity = document.get(identity_key)
        if not isinstance(identity, dict):
            raise ValueError("final qualification composition is incomplete")
        _HELPERS["require_bound_file"](
            root,
            identity,
            path_key="path",
            sha_key="sha256",
            description=description,
        )
    for path_key, sha_key, description in (
        ("protocol_path", "protocol_sha256", "final protocol"),
        (
            "population_contract_path",
            "population_contract_sha256",
            "final population",
        ),
    ):
        _HELPERS["require_bound_file"](
            root,
            document,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    _install_closed_recovery_source_view()
    base = _RECOVERY["load_recovery_evaluation_contract"](
        root / base_relative,
        _RECOVERY_PATH,
    )
    compatible = dict(base)
    compatible.update(document)
    compatible["population"] = {
        "image_count": 1688,
        "terminal_run_count": 8440,
        "binding_run_count": 5064,
        "continuum_image_count": 1688,
        "compact_blend_image_count": 0,
    }
    _HELPERS["load_final_qualification_population"](
        root / cast(str, document["population_contract_path"])
    )
    return compatible


def _compact_status(
    analysis: dict[str, Any],
    population: dict[str, Any],
) -> str:
    """Recompute the exact closed compact conjunction without rescoring."""
    compact = analysis.get("closed_compact_evidence")
    expected = population["compact_evidence"]["records"]
    if (
        not isinstance(compact, dict)
        or compact.get("status") != "pass"
        or compact.get("policy") != "bound-without-pooling-or-rescoring"
        or not isinstance(compact.get("records"), list)
    ):
        return "indeterminate"
    observed = compact["records"]
    if len(observed) != len(expected):
        return "indeterminate"
    for expected_record, observed_record in zip(
        expected, observed, strict=True
    ):
        if any(
            observed_record.get(key) != expected_record[key]
            for key in ("path", "sha256", "passed", "dataset_identifier")
        ):
            return "indeterminate"
        decision = _HELPERS["json_object"](_ROOT / expected_record["path"])
        if decision.get("passed") is not True:
            return "fail"
    return "pass"


def evaluate_final_qualification_analysis(
    analysis: dict[str, Any],
    contract: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[Any, tuple[Any, ...], str]:
    """Evaluate fresh Continuum endpoints and closed compact evidence."""
    compiler = cast(dict[str, Any], contract["analysis_compiler"])
    registry_identity = cast(dict[str, Any], contract["endpoint_registry"])
    support = analysis.get("observable_truth_support")
    if (
        analysis.get("analysis_id")
        != "phase-5-final-qualification-terminal-science"
        or analysis.get("compiler_sha256") != compiler["sha256"]
        or analysis.get("endpoint_registry_sha256")
        != registry_identity["sha256"]
        or analysis.get("protocol_sha256") != contract["protocol_sha256"]
        or analysis.get("execution_decision_sha256")
        != registry["execution_decision_sha256"]
        or not isinstance(support, list)
        or len(support) != _CONTINUUM_IMAGE_COUNT
        or analysis.get("scientific_outcomes_before_runtime") is not True
        or analysis.get("qualification_opened") is not True
        or analysis.get("cutover_authorized") is not False
    ):
        raise ValueError("final qualification compiled analysis changed")
    expected = _TERMINAL["_expected_continuum_endpoint_ids"](registry)
    if analysis.get("expected_continuum_endpoint_ids") != list(expected):
        raise ValueError("final qualification endpoint population changed")
    population = analysis.get("population_audit")
    endpoint_rows = analysis.get("continuum_endpoints")
    if not isinstance(population, dict) or not isinstance(endpoint_rows, list):
        raise ValueError("final qualification compiled populations are absent")
    audit = _TERMINAL["CampaignPopulationAudit"](
        **{
            key: population[key]
            for key in (
                "image_count",
                "terminal_run_count",
                "binding_run_count",
                "successful_binding_run_count",
                "failed_binding_run_count",
                "unavailable_binding_run_count",
                "unexpected_run_count",
            )
        }
    )
    evidence = tuple(
        _TERMINAL["_endpoint_evidence"](item) for item in endpoint_rows
    )
    endpoint_evaluator = _ENDPOINT["EndpointSpecificEvaluator"](
        cast(list[dict[str, Any]], contract["endpoint_power_priors"])
    )
    decisions = tuple(
        endpoint_evaluator(
            item,
            _TERMINAL["endpoint_policy"](
                contract,
                lane="continuum",
                metric_family=item.metric_family,
                position_population=item.position_population,
            ),
        )
        for item in evidence
    )
    continuum = _TERMINAL["evaluate_campaign"](
        audit,
        decisions,
        expected_endpoint_ids=expected,
        contract=contract,
    )
    population_contract = _HELPERS["load_final_qualification_population"](
        _ROOT / cast(str, contract["population_contract_path"])
    )
    compact_status = _compact_status(analysis, population_contract)
    statuses = {continuum.status, compact_status}
    if "fail" in statuses:
        status = "fail"
        reason = "continuum or closed compact qualification science failed"
    elif "underpowered" in statuses:
        status = "underpowered"
        reason = "a continuum qualification comparison is underpowered"
    elif "indeterminate" in statuses:
        status = "indeterminate"
        reason = "continuum or closed compact science is indeterminate"
    else:
        status = "pass"
        reason = "every continuum endpoint and closed compact gate passed"
    combined = _TERMINAL["CampaignDecision"](
        status=status,
        endpoint_count=continuum.endpoint_count + 1,
        expected_endpoint_count=continuum.expected_endpoint_count + 1,
        reason=reason,
    )
    return combined, decisions, compact_status


def _parse_args() -> argparse.Namespace:
    """Parse final analysis and write-once decision paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=_CONTRACT_PATH)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Evaluate one final analysis and publish one terminal decision."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite final decision: {arguments.output}"
        )
    contract = load_final_qualification_evaluation_contract(
        arguments.contract,
        Path(__file__),
    )
    analysis = _HELPERS["json_object"](arguments.analysis)
    registry_identity = cast(dict[str, Any], contract["endpoint_registry"])
    registry = _HELPERS["load_final_qualification_endpoint_registry"](
        _ROOT / cast(str, registry_identity["path"])
    )
    combined, endpoints, compact_status = (
        evaluate_final_qualification_analysis(
            analysis,
            contract,
            registry,
        )
    )
    decision = {
        "schema_version": 1,
        "decision_id": "phase-5-final-qualification-terminal-decision",
        "status": combined.status,
        "analysis_sha256": _HELPERS["file_sha256"](arguments.analysis),
        "contract_sha256": _HELPERS["file_sha256"](arguments.contract),
        "campaign": asdict(combined),
        "continuum_endpoints": [asdict(item) for item in endpoints],
        "compact_status": compact_status,
        "scientific_outcomes_before_runtime": True,
        "qualification_opened": True,
        "cutover_authorized": False,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as output:
        output.write(
            (
                json.dumps(decision, allow_nan=False, indent=2, sort_keys=True)
                + "\n"
            ).encode()
        )


if __name__ == "__main__":
    main()
