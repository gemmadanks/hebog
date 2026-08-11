#!/usr/bin/env python3
"""Apply the frozen fail-closed Phase 5 external decision rules.

This script is deliberately a decision boundary, not a raw-product analysis
compiler. The latter must be frozen and checksum-bound before the one-look
campaign can run; this evaluator then consumes only its strict endpoint
evidence and cannot reinterpret source-finder products after results exist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from math import isclose, isfinite
from pathlib import Path
from typing import Literal, cast

FinderStatus = Literal["success", "failed", "unavailable"]
DecisionStatus = Literal["pass", "fail", "indeterminate", "underpowered"]
PositionPopulation = Literal[
    "not-applicable",
    "compact-component",
    "irregular-segment",
]
Direction = Literal["higher-is-better", "lower-is-better"]
Relation = Literal["at-least", "at-most"]
AbsoluteDecisionStatistic = Literal[
    "point-estimate",
    "one-sided-95-percent-upper-confidence-limit",
]
_COMPACT_POSITION_MEDIAN_LIMIT = 0.1
_COMPACT_POSITION_P95_LIMIT = 0.25
_IRREGULAR_POSITION_AXIS_BIAS_LIMIT = 0.1
_IRREGULAR_POSITION_P95_LIMIT = 0.5


@dataclass(frozen=True, slots=True)
class ReferenceComparisonEvidence:
    """Compiled paired evidence for one binding external reference."""

    reference_id: str
    status: FinderStatus
    reference_value: float | None
    positive_regression: float | None
    upper_confidence_limit: float | None
    observed_paired_standard_deviation: float | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class EndpointEvidence:
    """One complete, compiler-produced scientific endpoint."""

    endpoint_id: str
    lane: Literal["continuum", "compact-blend"]
    metric_family: str
    stratum: str
    position_population: PositionPopulation
    image_count: int
    candidate_status: FinderStatus
    candidate_value: float | None
    absolute_decision_value: float | None
    comparisons: tuple[ReferenceComparisonEvidence, ...]
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class EndpointPolicy:
    """Frozen gate and power policy for one endpoint identity."""

    lane: Literal["continuum", "compact-blend"]
    metric_family: str
    position_population: PositionPopulation
    expected_image_count: int
    desirable_direction: Direction
    absolute_relation: Relation
    absolute_limit: float
    absolute_decision_statistic: AbsoluteDecisionStatistic
    practical_regression_margin: float
    planning_paired_standard_deviation: float
    binding_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReferenceDecision:
    """Decision for one paired reference comparison."""

    reference_id: str
    status: DecisionStatus
    upper_confidence_limit: float | None
    practical_regression_margin: float
    observed_paired_standard_deviation: float | None
    planning_paired_standard_deviation: float
    reason: str


@dataclass(frozen=True, slots=True)
class EndpointDecision:
    """Absolute-first terminal decision for one endpoint."""

    endpoint_id: str
    candidate_value: float | None
    absolute_decision_value: float | None
    absolute_limit: float
    absolute_relation: Relation
    absolute_passed: bool | None
    comparisons: tuple[ReferenceDecision, ...]
    status: DecisionStatus
    reason: str


@dataclass(frozen=True, slots=True)
class CampaignPopulationAudit:
    """Completeness counts from the terminal raw campaign manifest."""

    image_count: int
    terminal_run_count: int
    binding_run_count: int
    successful_binding_run_count: int
    failed_binding_run_count: int
    unavailable_binding_run_count: int
    unexpected_run_count: int


@dataclass(frozen=True, slots=True)
class CampaignDecision:
    """Combined fail-closed result across the exact endpoint registry."""

    status: DecisionStatus
    endpoint_count: int
    expected_endpoint_count: int
    reason: str


def _file_sha256(path: Path) -> str:
    """Hash one immutable file without loading large content at once."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_file_sha256(
    root: Path,
    document: dict[str, object],
    *,
    path_key: str,
    sha_key: str,
    description: str,
) -> None:
    """Reject any drift in one checksum-bound upstream input."""
    relative = document.get(path_key)
    expected = document.get(sha_key)
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise ValueError(f"{description} identity is incomplete")
    observed = _file_sha256(root / relative)
    if observed != expected:
        raise ValueError(f"{description} checksum changed")


def _json_object(path: Path) -> dict[str, object]:
    """Load one JSON object used to recompute the evaluation policy."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"scientific input must be an object: {path}")
    return cast(dict[str, object], value)


def load_evaluation_contract(
    contract_path: Path,
    evaluator_path: Path,
) -> dict[str, object]:
    """Load the policy and verify its evaluator and upstream identities."""
    value = json.loads(contract_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("external evaluation contract must be an object")
    document = cast(dict[str, object], value)
    if (
        document.get("schema_version") != 1
        or document.get("contract_id") != "phase-5-external-evaluation"
        or document.get("status") != "frozen-before-campaign-output"
    ):
        raise ValueError("external evaluation contract identity is invalid")
    expected_evaluator = document.get("evaluator_sha256")
    if expected_evaluator != _file_sha256(evaluator_path):
        raise ValueError("external decision evaluator checksum changed")
    root = evaluator_path.parents[2]
    _require_file_sha256(
        root,
        document,
        path_key="protocol_path",
        sha_key="protocol_sha256",
        description="external protocol",
    )
    _require_file_sha256(
        root,
        document,
        path_key="phase_five_scientific_gates_path",
        sha_key="phase_five_scientific_gates_sha256",
        description="scientific gate",
    )
    _require_file_sha256(
        root,
        document,
        path_key="phase_four_scientific_gates_path",
        sha_key="phase_four_scientific_gates_sha256",
        description="compact scientific gate",
    )
    _require_file_sha256(
        root,
        document,
        path_key="phase_four_metric_registry_path",
        sha_key="phase_four_metric_registry_sha256",
        description="compact metric registry",
    )
    _require_file_sha256(
        root,
        document,
        path_key="compact_decision_engine_path",
        sha_key="compact_decision_engine_sha256",
        description="compact decision engine",
    )
    _require_file_sha256(
        root,
        document,
        path_key="astrometry_follow_up_path",
        sha_key="astrometry_follow_up_sha256",
        description="astrometry follow-up",
    )
    _validate_contract_constants(document, root)
    return document


def _validate_contract_constants(
    document: dict[str, object], root: Path
) -> None:
    """Keep the reviewed population, mappings, and failure policy exact."""
    expected_counts = {
        "image_count": 1400,
        "terminal_run_count": 7000,
        "binding_run_count": 5000,
        "continuum_image_count": 600,
        "compact_blend_image_count": 800,
    }
    population = document.get("population")
    if not isinstance(population, dict) or any(
        population.get(key) != expected
        for key, expected in expected_counts.items()
    ):
        raise ValueError("external evaluation population changed")
    if document.get("failure_policy") != (
        "absolute-first-retain-denominator-incomplete-reference-fails-closed"
    ):
        raise ValueError("external evaluation failure policy changed")
    if document.get("evaluator_path") != (
        "scripts/validation/evaluate_phase5_external_decision.py"
    ):
        raise ValueError("external decision evaluator path changed")
    _validate_metric_policies(document, root)
    position = document.get("position_mapping")
    decision_statistics = document.get("position_decision_statistics")
    if not isinstance(position, dict):
        raise ValueError("external position mapping is absent")
    if not isinstance(decision_statistics, dict):
        raise ValueError("external position decision statistics are absent")
    compact = position.get("compact-component")
    irregular = position.get("irregular-segment")
    if (
        not isinstance(compact, dict)
        or compact.get("position-median") != _COMPACT_POSITION_MEDIAN_LIMIT
        or compact.get("position-p95") != _COMPACT_POSITION_P95_LIMIT
        or not isinstance(irregular, dict)
        or irregular.get("position-median") != "report-only"
        or irregular.get("absolute-mean-offset-x")
        != _IRREGULAR_POSITION_AXIS_BIAS_LIMIT
        or irregular.get("absolute-mean-offset-y")
        != _IRREGULAR_POSITION_AXIS_BIAS_LIMIT
        or irregular.get("position-p95") != _IRREGULAR_POSITION_P95_LIMIT
    ):
        raise ValueError("external position population mapping changed")
    if decision_statistics != {
        "compact-component": {
            "position-median": "point-estimate",
            "position-p95": "point-estimate",
        },
        "irregular-segment": {
            "absolute-mean-offset-x": (
                "one-sided-95-percent-upper-confidence-limit"
            ),
            "absolute-mean-offset-y": (
                "one-sided-95-percent-upper-confidence-limit"
            ),
            "position-median": "report-only",
            "position-p95": ("one-sided-95-percent-upper-confidence-limit"),
        },
    }:
        raise ValueError("external position decision statistic changed")
    compiler = document.get("analysis_compiler")
    if not isinstance(compiler, dict) or compiler.get("status") != (
        "required-before-campaign-execution"
    ):
        raise ValueError("raw scientific compiler policy changed")


def _validate_metric_policies(document: dict[str, object], root: Path) -> None:
    """Recompute thresholds, margins, and variance bounds upstream."""
    protocol = _json_object(root / cast(str, document["protocol_path"]))
    gates = _json_object(
        root / cast(str, document["phase_five_scientific_gates_path"])
    )
    follow_up = _json_object(
        root / cast(str, document["astrometry_follow_up_path"])
    )
    metrics = document.get("continuum_metrics")
    if not isinstance(metrics, dict):
        raise ValueError("continuum metric policies are absent")
    expected_metric_ids = tuple(
        cast(list[str], protocol["continuum_binding_metrics"])
    )
    if set(metrics) != set(expected_metric_ids):
        raise ValueError("continuum metric policy set changed")
    power_audit = cast(dict[str, object], protocol["power_audit"])
    assumptions = {
        cast(str, item["metric_family"]): cast(dict[str, object], item)
        for item in cast(
            list[dict[str, object]],
            power_audit["continuum_assumptions"],
        )
    }
    generated = cast(dict[str, object], gates["generated_regression"])
    margins = cast(dict[str, object], gates["paired_margins"])
    absolute_keys = {
        "completeness": "minimum_completeness",
        "reliability": "minimum_reliability",
        "integrated-flux-median": (
            "maximum_median_integrated_flux_fractional_error"
        ),
        "integrated-flux-p95": (
            "maximum_percentile_95_integrated_flux_fractional_error"
        ),
        "duplicate-fraction": "maximum_duplicate_fraction",
        "mask-precision": "minimum_mask_precision",
        "mask-recall": "minimum_mask_recall",
        "mask-iou": "minimum_mask_intersection_over_union",
        "split-fraction": "maximum_split_fraction",
        "merge-fraction": "maximum_merge_fraction",
    }
    margin_keys = {
        "completeness": "maximum_completeness_loss",
        "reliability": "maximum_reliability_loss",
        "integrated-flux-median": "maximum_integrated_flux_error_increase",
        "integrated-flux-p95": "maximum_integrated_flux_error_increase",
        "position-median": "maximum_position_error_increase_beams",
        "position-p95": "maximum_position_error_increase_beams",
        "duplicate-fraction": "maximum_duplicate_fraction_increase",
        "mask-precision": "maximum_mask_intersection_over_union_loss",
        "mask-recall": "maximum_mask_intersection_over_union_loss",
        "mask-iou": "maximum_mask_intersection_over_union_loss",
        "split-fraction": "maximum_split_fraction_increase",
        "merge-fraction": "maximum_merge_fraction_increase",
    }
    higher = {
        "completeness",
        "reliability",
        "mask-precision",
        "mask-recall",
        "mask-iou",
    }
    for metric_id in expected_metric_ids:
        metric = metrics.get(metric_id)
        if not isinstance(metric, dict):
            raise ValueError("continuum metric policy is malformed")
        assumption = assumptions.get(metric_id)
        if assumption is None:
            raise ValueError("continuum power assumption is absent")
        direction = (
            "higher-is-better" if metric_id in higher else "lower-is-better"
        )
        relation = "at-least" if metric_id in higher else "at-most"
        if (
            metric.get("desirable_direction") != direction
            or metric.get("absolute_relation") != relation
            or metric.get("practical_regression_margin")
            != assumption["practical_regression_margin"]
            or metric.get("practical_regression_margin")
            != margins[margin_keys[metric_id]]
            or metric.get("planning_paired_standard_deviation")
            != assumption["planning_paired_standard_deviation"]
            or metric.get("absolute_decision_statistic") != "point-estimate"
        ):
            raise ValueError("continuum metric policy differs from protocol")
        absolute_key = absolute_keys.get(metric_id)
        if (
            absolute_key is not None
            and metric.get("absolute_limit") != (generated[absolute_key])
        ):
            raise ValueError("continuum absolute gate differs from protocol")
    position = cast(dict[str, object], document["position_mapping"])
    compact = cast(dict[str, object], position["compact-component"])
    irregular = cast(dict[str, object], position["irregular-segment"])
    follow_compact = cast(dict[str, object], follow_up["compact_position"])
    follow_endpoint = cast(dict[str, object], follow_up["endpoint"])
    if (
        compact["position-median"]
        != generated["maximum_median_position_beams"]
        or compact["position-p95"]
        != generated["maximum_percentile_95_position_beams"]
        or compact["position-median"]
        != follow_compact["maximum_median_position_beams"]
        or compact["position-p95"]
        != follow_compact["maximum_percentile_95_position_beams"]
        or irregular["position-median"] != follow_endpoint["radial_median"]
        or irregular["absolute-mean-offset-x"]
        != follow_endpoint["maximum_absolute_axis_bias_beams"]
        or irregular["absolute-mean-offset-y"]
        != follow_endpoint["maximum_absolute_axis_bias_beams"]
        or irregular["position-p95"]
        != follow_endpoint["maximum_radial_percentile_95_beams"]
    ):
        raise ValueError("external position mapping differs from review")


def _position_absolute_policy(
    contract: dict[str, object],
    metric_family: str,
    position_population: PositionPopulation,
) -> tuple[object, object]:
    """Resolve a binding position limit without converting diagnostics."""
    mapping = cast(dict[str, object], contract["position_mapping"])
    statistics = cast(
        dict[str, object], contract["position_decision_statistics"]
    )
    population_mapping = mapping.get(position_population)
    population_statistics = statistics.get(position_population)
    if not isinstance(population_mapping, dict) or not isinstance(
        population_statistics, dict
    ):
        raise ValueError("position population mapping is unavailable")
    absolute_limit = population_mapping.get(metric_family)
    decision_statistic = population_statistics.get(metric_family)
    if absolute_limit == "report-only" or decision_statistic == "report-only":
        raise ValueError(
            "irregular radial position median remains report-only"
        )
    return absolute_limit, decision_statistic


def endpoint_policy(
    contract: dict[str, object],
    *,
    lane: Literal["continuum", "compact-blend"],
    metric_family: str,
    position_population: PositionPopulation,
) -> EndpointPolicy:
    """Resolve one policy, including the explicit position-population gate."""
    if lane != "continuum":
        raise ValueError(
            "compact endpoints remain governed by the frozen Phase 4 engine"
        )
    metrics = contract.get("continuum_metrics")
    if not isinstance(metrics, dict):
        raise ValueError("continuum metric policies are absent")
    untyped = metrics.get(metric_family)
    if not isinstance(untyped, dict):
        raise ValueError(f"unknown continuum metric family: {metric_family}")
    metric = cast(dict[str, object], untyped)
    is_position = metric_family in {"position-median", "position-p95"}
    if is_position != (position_population != "not-applicable"):
        raise ValueError("position population is inconsistent with metric")
    if is_position:
        absolute_limit, absolute_decision_statistic = (
            _position_absolute_policy(
                contract,
                metric_family,
                position_population,
            )
        )
    else:
        absolute_limit = metric.get("absolute_limit")
        absolute_decision_statistic = metric.get("absolute_decision_statistic")
    references = contract.get("binding_references")
    population = cast(dict[str, object], contract["population"])
    if not isinstance(references, dict):
        raise ValueError("binding reference policy is absent")
    lane_references = references.get(lane)
    if not isinstance(lane_references, list):
        raise ValueError("continuum binding references are absent")
    numeric = (
        absolute_limit,
        metric.get("practical_regression_margin"),
        metric.get("planning_paired_standard_deviation"),
    )
    if not all(isinstance(item, (int, float)) for item in numeric):
        raise ValueError("continuum numeric policy is incomplete")
    if absolute_decision_statistic not in {
        "point-estimate",
        "one-sided-95-percent-upper-confidence-limit",
    }:
        raise ValueError("continuum absolute decision statistic is invalid")
    return EndpointPolicy(
        lane=lane,
        metric_family=metric_family,
        position_population=position_population,
        expected_image_count=cast(int, population["continuum_image_count"]),
        desirable_direction=cast(Direction, metric["desirable_direction"]),
        absolute_relation=cast(Relation, metric["absolute_relation"]),
        absolute_limit=float(cast(float, absolute_limit)),
        absolute_decision_statistic=cast(
            AbsoluteDecisionStatistic,
            absolute_decision_statistic,
        ),
        practical_regression_margin=float(
            cast(float, metric["practical_regression_margin"])
        ),
        planning_paired_standard_deviation=float(
            cast(float, metric["planning_paired_standard_deviation"])
        ),
        binding_references=tuple(cast(list[str], lane_references)),
    )


def _comparison_decision(
    evidence: ReferenceComparisonEvidence,
    policy: EndpointPolicy,
    candidate_value: float,
) -> ReferenceDecision:
    """Apply availability, variance, and one-sided margin gates in order."""
    if evidence.status != "success":
        return ReferenceDecision(
            reference_id=evidence.reference_id,
            status="indeterminate",
            upper_confidence_limit=None,
            practical_regression_margin=policy.practical_regression_margin,
            observed_paired_standard_deviation=None,
            planning_paired_standard_deviation=(
                policy.planning_paired_standard_deviation
            ),
            reason=evidence.reason or "binding reference unavailable",
        )
    values = (
        evidence.reference_value,
        evidence.positive_regression,
        evidence.upper_confidence_limit,
        evidence.observed_paired_standard_deviation,
    )
    if any(value is None or not isfinite(value) for value in values):
        return ReferenceDecision(
            reference_id=evidence.reference_id,
            status="indeterminate",
            upper_confidence_limit=None,
            practical_regression_margin=policy.practical_regression_margin,
            observed_paired_standard_deviation=None,
            planning_paired_standard_deviation=(
                policy.planning_paired_standard_deviation
            ),
            reason="binding reference evidence is incomplete or non-finite",
        )
    observed = cast(float, evidence.observed_paired_standard_deviation)
    upper = cast(float, evidence.upper_confidence_limit)
    reference = cast(float, evidence.reference_value)
    declared_regression = cast(float, evidence.positive_regression)
    expected_regression = (
        reference - candidate_value
        if policy.desirable_direction == "higher-is-better"
        else candidate_value - reference
    )
    if not isclose(
        declared_regression,
        expected_regression,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        return ReferenceDecision(
            reference_id=evidence.reference_id,
            status="indeterminate",
            upper_confidence_limit=upper,
            practical_regression_margin=policy.practical_regression_margin,
            observed_paired_standard_deviation=observed,
            planning_paired_standard_deviation=(
                policy.planning_paired_standard_deviation
            ),
            reason="paired point regression has the wrong direction",
        )
    if observed > policy.planning_paired_standard_deviation:
        return ReferenceDecision(
            reference_id=evidence.reference_id,
            status="underpowered",
            upper_confidence_limit=upper,
            practical_regression_margin=policy.practical_regression_margin,
            observed_paired_standard_deviation=observed,
            planning_paired_standard_deviation=(
                policy.planning_paired_standard_deviation
            ),
            reason="observed paired variance exceeds the planning bound",
        )
    passed = upper <= policy.practical_regression_margin
    return ReferenceDecision(
        reference_id=evidence.reference_id,
        status="pass" if passed else "fail",
        upper_confidence_limit=upper,
        practical_regression_margin=policy.practical_regression_margin,
        observed_paired_standard_deviation=observed,
        planning_paired_standard_deviation=(
            policy.planning_paired_standard_deviation
        ),
        reason=(
            "paired upper confidence limit is within the margin"
            if passed
            else "paired upper confidence limit exceeds the margin"
        ),
    )


def _absolute_decision(
    evidence: EndpointEvidence,
    policy: EndpointPolicy,
    candidate: float,
) -> tuple[float | None, bool | None, str | None]:
    """Validate and apply the distinct absolute decision statistic."""
    absolute_value = evidence.absolute_decision_value
    if absolute_value is None or not isfinite(absolute_value):
        return (
            None,
            None,
            ("absolute decision statistic is incomplete or non-finite"),
        )
    if policy.absolute_decision_statistic == "point-estimate" and not isclose(
        absolute_value,
        candidate,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        return (
            absolute_value,
            None,
            "point-estimate absolute decision value differs",
        )
    if (
        policy.absolute_decision_statistic
        == "one-sided-95-percent-upper-confidence-limit"
        and absolute_value < candidate
    ):
        return (
            absolute_value,
            None,
            "absolute upper confidence limit is below its point estimate",
        )
    passed = (
        absolute_value >= policy.absolute_limit
        if policy.absolute_relation == "at-least"
        else absolute_value <= policy.absolute_limit
    )
    return absolute_value, passed, None


def _candidate_precondition(
    evidence: EndpointEvidence,
    policy: EndpointPolicy,
) -> EndpointDecision | None:
    """Validate endpoint identity, population, and candidate availability."""
    if (
        evidence.lane != policy.lane
        or evidence.metric_family != policy.metric_family
        or evidence.position_population != policy.position_population
    ):
        raise ValueError("endpoint evidence identity differs from policy")
    if evidence.image_count != policy.expected_image_count:
        return EndpointDecision(
            endpoint_id=evidence.endpoint_id,
            candidate_value=evidence.candidate_value,
            absolute_decision_value=evidence.absolute_decision_value,
            absolute_limit=policy.absolute_limit,
            absolute_relation=policy.absolute_relation,
            absolute_passed=None,
            comparisons=(),
            status="indeterminate",
            reason="endpoint population is incomplete",
        )
    if evidence.candidate_status != "success":
        return EndpointDecision(
            endpoint_id=evidence.endpoint_id,
            candidate_value=None,
            absolute_decision_value=None,
            absolute_limit=policy.absolute_limit,
            absolute_relation=policy.absolute_relation,
            absolute_passed=None,
            comparisons=(),
            status="indeterminate",
            reason=evidence.reason or "candidate endpoint unavailable",
        )
    candidate = evidence.candidate_value
    if candidate is None or not isfinite(candidate):
        return EndpointDecision(
            endpoint_id=evidence.endpoint_id,
            candidate_value=None,
            absolute_decision_value=None,
            absolute_limit=policy.absolute_limit,
            absolute_relation=policy.absolute_relation,
            absolute_passed=None,
            comparisons=(),
            status="indeterminate",
            reason="candidate endpoint is incomplete or non-finite",
        )
    return None


def evaluate_endpoint(
    evidence: EndpointEvidence,
    policy: EndpointPolicy,
) -> EndpointDecision:
    """Evaluate one endpoint without compensation or reference omission."""
    precondition = _candidate_precondition(evidence, policy)
    if precondition is not None:
        return precondition
    candidate = cast(float, evidence.candidate_value)
    absolute_value, absolute_passed, absolute_reason = _absolute_decision(
        evidence,
        policy,
        candidate,
    )
    if absolute_reason is not None:
        return EndpointDecision(
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
    assert absolute_value is not None
    assert absolute_passed is not None
    if not absolute_passed:
        return EndpointDecision(
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
    by_reference = {item.reference_id: item for item in evidence.comparisons}
    if len(by_reference) != len(evidence.comparisons) or set(
        by_reference
    ) != set(policy.binding_references):
        return EndpointDecision(
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
    comparisons = tuple(
        _comparison_decision(by_reference[reference], policy, candidate)
        for reference in policy.binding_references
    )
    statuses = {item.status for item in comparisons}
    if "underpowered" in statuses:
        status: DecisionStatus = "underpowered"
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
    return EndpointDecision(
        endpoint_id=evidence.endpoint_id,
        candidate_value=candidate,
        absolute_decision_value=absolute_value,
        absolute_limit=policy.absolute_limit,
        absolute_relation=policy.absolute_relation,
        absolute_passed=True,
        comparisons=comparisons,
        status=status,
        reason=reason,
    )


def _population_is_complete(
    audit: CampaignPopulationAudit,
    contract: dict[str, object],
) -> bool:
    """Check exact terminal and binding raw-result counts."""
    population = cast(dict[str, object], contract["population"])
    return (
        audit.image_count == population["image_count"]
        and audit.terminal_run_count == population["terminal_run_count"]
        and audit.binding_run_count == population["binding_run_count"]
        and audit.successful_binding_run_count
        == population["binding_run_count"]
        and audit.failed_binding_run_count == 0
        and audit.unavailable_binding_run_count == 0
        and audit.unexpected_run_count == 0
    )


def evaluate_campaign(
    audit: CampaignPopulationAudit,
    endpoints: tuple[EndpointDecision, ...],
    *,
    expected_endpoint_ids: tuple[str, ...],
    contract: dict[str, object],
) -> CampaignDecision:
    """Combine exact populations and all endpoint decisions without scores."""
    if not _population_is_complete(audit, contract):
        return CampaignDecision(
            status="indeterminate",
            endpoint_count=len(endpoints),
            expected_endpoint_count=len(expected_endpoint_ids),
            reason="terminal raw campaign population is incomplete",
        )
    identifiers = tuple(item.endpoint_id for item in endpoints)
    if (
        not expected_endpoint_ids
        or len(set(identifiers)) != len(identifiers)
        or len(set(expected_endpoint_ids)) != len(expected_endpoint_ids)
        or set(identifiers) != set(expected_endpoint_ids)
    ):
        return CampaignDecision(
            status="indeterminate",
            endpoint_count=len(endpoints),
            expected_endpoint_count=len(expected_endpoint_ids),
            reason="scientific endpoint population is incomplete",
        )
    statuses = {item.status for item in endpoints}
    if "fail" in statuses:
        status: DecisionStatus = "fail"
        reason = "at least one binding scientific endpoint failed"
    elif "underpowered" in statuses:
        status = "underpowered"
        reason = "at least one binding endpoint is underpowered"
    elif "indeterminate" in statuses:
        status = "indeterminate"
        reason = "at least one binding endpoint is indeterminate"
    else:
        status = "pass"
        reason = "every absolute and paired scientific endpoint passed"
    return CampaignDecision(
        status=status,
        endpoint_count=len(endpoints),
        expected_endpoint_count=len(expected_endpoint_ids),
        reason=reason,
    )


def _parse_args() -> argparse.Namespace:
    """Parse the future compiler output and immutable contract paths."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        type=Path,
        default=root / "config/contracts/phase-5-external-evaluation.json",
    )
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Reject unbound analysis until its compiler is frozen and implemented."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite external decision: {arguments.output}"
        )
    contract = load_evaluation_contract(arguments.contract, Path(__file__))
    compiler = cast(dict[str, object], contract["analysis_compiler"])
    if compiler.get("sha256") is None:
        raise RuntimeError(
            "raw-product scientific compiler must be frozen before campaign "
            "evaluation"
        )
    analysis = json.loads(arguments.analysis.read_text(encoding="utf-8"))
    if not isinstance(analysis, dict):
        raise ValueError("external analysis must be an object")
    if analysis.get("compiler_sha256") != compiler["sha256"]:
        raise ValueError("external analysis compiler checksum differs")
    raise NotImplementedError(
        "analysis ingestion opens only after the raw compiler is frozen"
    )


if __name__ == "__main__":
    main()
