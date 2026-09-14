#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Apply unchanged gates and exact endpoint priors to fresh evidence."""

from __future__ import annotations

import argparse
import json
import runpy
from dataclasses import asdict, replace
from math import isfinite
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[2]
_CONFIRMATION_EVALUATOR_PATH = (
    _ROOT
    / "scripts/validation/evaluate_phase5_external_confirmation_decision.py"
)
_CONTRACT_PATH = (
    _ROOT / "config/contracts/phase-5-external-post-failure-evaluation.json"
)
_EVALUATOR_PATH = (
    "scripts/validation/evaluate_phase5_external_post_failure_decision.py"
)
_CONFIRMATION = runpy.run_path(str(_CONFIRMATION_EVALUATOR_PATH))
_TERMINAL = _CONFIRMATION["_TERMINAL"]
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_post_failure_protocol.py")
)
_CONTINUUM_IMAGE_COUNT = 1600


class EndpointSpecificEvaluator:
    """Apply one predeclared variance bound per endpoint and reference."""

    def __init__(
        self,
        priors: list[dict[str, Any]],
    ) -> None:
        self._priors = {
            (item["endpoint_id"], item["reference_id"]): item
            for item in priors
        }
        if len(self._priors) != len(priors):
            raise ValueError("endpoint-specific power priors are duplicated")

    def __call__(  # noqa: C901, PLR0912
        self,
        evidence: Any,
        policy: Any,
    ) -> Any:
        """Evaluate one endpoint with exact reference-specific bounds."""
        if not evidence.comparisons:
            return _TERMINAL["evaluate_endpoint"](evidence, policy)
        precondition = _TERMINAL["_candidate_precondition"](
            evidence,
            policy,
        )
        if precondition is not None:
            return precondition
        candidate = cast(float, evidence.candidate_value)
        absolute_value, absolute_passed, absolute_reason = _TERMINAL[
            "_absolute_decision"
        ](evidence, policy, candidate)
        endpoint_decision = _TERMINAL["EndpointDecision"]
        if absolute_reason is not None:
            return endpoint_decision(
                endpoint_id=evidence.endpoint_id,
                candidate_value=candidate,
                absolute_decision_value=absolute_value,
                absolute_limit=policy.absolute_limit,
                absolute_relation=policy.absolute_relation,
                absolute_passed=None,
                comparisons=(),
                status="indeterminate",
                reason=absolute_reason,
            )
        if absolute_value is None or absolute_passed is None:
            raise ValueError("absolute endpoint decision is incomplete")
        if not absolute_passed:
            return endpoint_decision(
                endpoint_id=evidence.endpoint_id,
                candidate_value=candidate,
                absolute_decision_value=absolute_value,
                absolute_limit=policy.absolute_limit,
                absolute_relation=policy.absolute_relation,
                absolute_passed=False,
                comparisons=(),
                status="fail",
                reason="candidate failed the absolute truth gate",
            )
        by_reference = {
            item.reference_id: item for item in evidence.comparisons
        }
        if len(by_reference) != len(evidence.comparisons) or set(
            by_reference
        ) != set(policy.binding_references):
            return endpoint_decision(
                endpoint_id=evidence.endpoint_id,
                candidate_value=candidate,
                absolute_decision_value=absolute_value,
                absolute_limit=policy.absolute_limit,
                absolute_relation=policy.absolute_relation,
                absolute_passed=True,
                comparisons=(),
                status="indeterminate",
                reason="binding reference population is incomplete",
            )
        comparisons: list[Any] = []
        for reference_id in policy.binding_references:
            prior = self._priors.get((evidence.endpoint_id, reference_id))
            if prior is None:
                raise ValueError("endpoint-specific power prior is absent")
            if (
                prior["metric_family"] != evidence.metric_family
                or prior["practical_regression_margin"]
                != policy.practical_regression_margin
            ):
                raise ValueError("endpoint-specific power prior changed")
            specific_policy = replace(
                policy,
                planning_paired_standard_deviation=prior[
                    "planning_paired_standard_deviation"
                ],
            )
            comparisons.append(
                _TERMINAL["_comparison_decision"](
                    by_reference[reference_id],
                    specific_policy,
                    candidate,
                )
            )
        statuses = {item.status for item in comparisons}
        if "underpowered" in statuses:
            status = "underpowered"
            reason = "at least one paired comparison has excess variance"
        elif "indeterminate" in statuses:
            status = "indeterminate"
            reason = "at least one binding reference is unavailable"
        elif "fail" in statuses:
            status = "fail"
            reason = "at least one paired non-inferiority gate failed"
        else:
            status = "pass"
            reason = "absolute and every paired gate passed"
        return endpoint_decision(
            endpoint_id=evidence.endpoint_id,
            candidate_value=candidate,
            absolute_decision_value=absolute_value,
            absolute_limit=policy.absolute_limit,
            absolute_relation=policy.absolute_relation,
            absolute_passed=True,
            comparisons=tuple(comparisons),
            status=status,
            reason=reason,
        )


def load_post_failure_evaluation_contract(
    contract_path: Path,
    evaluator_path: Path,
) -> dict[str, Any]:
    """Verify composition, unchanged gates, and all exact power priors."""
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
        ),
        description="post-failure evaluation contract",
    )
    if (
        document.get("schema_version") != 1
        or document.get("contract_id")
        != "phase-5-external-post-failure-evaluation"
        or document.get("status") != "frozen-before-campaign-output"
        or document.get("closed_campaign_reuse_authorized") is not False
        or document.get("one_look_rule")
        != "one-terminal-look-no-tuning-rescoring-reconfirmation-or-adaptive-"
        "sample-size"
        or document.get("evaluator_path") != _EVALUATOR_PATH
        or document.get("evaluator_sha256")
        != _HELPERS["file_sha256"](evaluator_path)
    ):
        raise ValueError("post-failure evaluation identity is invalid")
    root = evaluator_path.parents[2]
    base_path = (
        root / "config/contracts/phase-5-external-confirmation-evaluation.json"
    )
    if (
        document.get("base_evaluation_path")
        != "config/contracts/phase-5-external-confirmation-evaluation.json"
        or document.get("base_evaluation_sha256")
        != _HELPERS["file_sha256"](base_path)
    ):
        raise ValueError("post-failure evaluation ancestry changed")
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
        raise ValueError("post-failure evaluation composition is incomplete")
    for identity, description in zip(
        identities,
        (
            "post-failure compiler",
            "post-failure registry",
            "compiler accelerator",
            "observable measurement",
            "observable compiler",
        ),
        strict=True,
    ):
        _HELPERS["require_exact_keys"](
            identity,
            frozenset({"path", "sha256", "status"}),
            description="post-failure evaluation artifact",
        )
        _HELPERS["require_bound_file"](
            root,
            identity,
            path_key="path",
            sha_key="sha256",
            description=description,
        )
    for path_key, sha_key, description in (
        ("protocol_path", "protocol_sha256", "post-failure protocol"),
        (
            "population_contract_path",
            "population_contract_sha256",
            "post-failure population contract",
        ),
    ):
        _HELPERS["require_bound_file"](
            root,
            document,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    registry = cast(dict[str, Any], identities[1])
    _HELPERS["load_post_failure_endpoint_registry"](
        root / cast(str, registry["path"])
    )
    population = _HELPERS["load_post_failure_population"](
        root / cast(str, document["population_contract_path"])
    )
    base = _CONFIRMATION["load_confirmation_evaluation_contract"](
        base_path,
        _CONFIRMATION_EVALUATOR_PATH,
    )
    compatible = dict(base)
    compatible.update(document)
    compatible["population"] = {
        "image_count": 2400,
        "terminal_run_count": 12000,
        "binding_run_count": 8000,
        "continuum_image_count": 1600,
        "compact_blend_image_count": 800,
    }
    power = cast(dict[str, Any], population["power_audit"])
    priors = cast(list[dict[str, Any]], power["paired_assumptions"])
    metrics = cast(dict[str, Any], compatible["continuum_metrics"])
    for prior in priors:
        metric = cast(dict[str, Any], metrics[prior["metric_family"]])
        if (
            prior["practical_regression_margin"]
            != metric["practical_regression_margin"]
        ):
            raise ValueError("endpoint-specific practical margin changed")
        if not isfinite(prior["planning_paired_standard_deviation"]):
            raise ValueError("endpoint-specific variance bound is invalid")
    compatible["endpoint_power_priors"] = priors
    return compatible


def evaluate_post_failure_analysis(
    analysis: dict[str, Any],
    contract: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[Any, tuple[Any, ...], str]:
    """Evaluate the unique fresh identity through exact prior mechanics."""
    compiler = cast(dict[str, Any], contract["analysis_compiler"])
    registry_identity = cast(dict[str, Any], contract["endpoint_registry"])
    accelerator = cast(dict[str, Any], contract["compiler_accelerator"])
    measurement = cast(dict[str, Any], contract["observable_measurement"])
    observable_compiler = cast(dict[str, Any], contract["observable_compiler"])
    support = analysis.get("observable_truth_support")
    if (
        analysis.get("analysis_id")
        != "phase-5-external-post-failure-terminal-science"
        or analysis.get("closed_campaign_reuse_authorized") is not False
        or analysis.get("successor_science_kernel_sha256")
        != "8e38de3b4347faee9636b89d03f8cdcdd77e39fd1e087d2b44454e5fd7063c55"
        or analysis.get("compiler_accelerator_sha256") != accelerator["sha256"]
        or analysis.get("observable_measurement_sha256")
        != measurement["sha256"]
        or analysis.get("observable_compiler_sha256")
        != observable_compiler["sha256"]
        or analysis.get("compiler_sha256") != compiler["sha256"]
        or analysis.get("endpoint_registry_sha256")
        != registry_identity["sha256"]
        or not isinstance(support, list)
        or len(support) != _CONTINUUM_IMAGE_COUNT
    ):
        raise ValueError("post-failure compiled analysis identity changed")
    compatible = dict(analysis)
    compatible["analysis_id"] = "phase-5-external-terminal-science"
    globals_ = _TERMINAL["evaluate_compiled_analysis"].__globals__
    original = globals_["evaluate_endpoint"]
    globals_["evaluate_endpoint"] = EndpointSpecificEvaluator(
        cast(list[dict[str, Any]], contract["endpoint_power_priors"])
    )
    try:
        return cast(
            tuple[Any, tuple[Any, ...], str],
            _TERMINAL["evaluate_compiled_analysis"](
                compatible,
                contract,
                registry,
            ),
        )
    finally:
        globals_["evaluate_endpoint"] = original


def _parse_args() -> argparse.Namespace:
    """Parse post-failure analysis and write-once decision paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=_CONTRACT_PATH)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Evaluate one post-failure analysis and publish one decision."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite post-failure decision: {arguments.output}"
        )
    contract = load_post_failure_evaluation_contract(
        arguments.contract,
        Path(__file__),
    )
    analysis = _HELPERS["json_object"](arguments.analysis)
    registry_identity = cast(dict[str, Any], contract["endpoint_registry"])
    registry = _HELPERS["load_post_failure_endpoint_registry"](
        _ROOT / cast(str, registry_identity["path"])
    )
    combined, endpoints, compact_status = evaluate_post_failure_analysis(
        analysis,
        contract,
        registry,
    )
    decision = {
        "schema_version": 1,
        "decision_id": "phase-5-external-post-failure-terminal-decision",
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
