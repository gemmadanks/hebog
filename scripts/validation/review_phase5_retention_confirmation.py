#!/usr/bin/env python3
"""Prepare the Phase 5 final retention-confirmation scientific pre-review."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import cast

from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.prospective_retention_extension import (
    balanced_confirmation_power,
    minimum_balanced_confirmation_count,
    stratified_percentile_regression,
)

_CLOSED_DECISION_SHA256 = (
    "5bced80488199696382233d8b0d513a83922d35cdee605c8e638798ef8f6faf4"
)
_CLOSED_RECORD_CANONICAL_SHA256 = (
    "170361b1fc232fa821ecf4ccff5fc74bf796c55695bdc1267415d4d109d7c0d9"
)
_SOURCE_REQUEST_SHA256 = (
    "7ba9be1b20ff0448e51729337acf2a7028cc0ec578c5e25106b9b34b07506df4"
)
_SHELL_ENDPOINTS = (
    "continuum--position-p95--above-compact-deblend-limit",
    "continuum--position-p95--morphology-shell",
    "continuum--position-p95--tile-corner",
)
_SCALE_ENDPOINT = "continuum--position-p95--scale-4-beam"
_FINDERS = (
    "current-hebog",
    "incumbent-hebog",
    "pinned-pybdsf-master",
    "released-pybdsf",
)
_BOOTSTRAP_RESAMPLES = 50_000
_BOOTSTRAP_SEEDS = (2026090401, 2026090402)
_VARIANCE_INFLATION = 1.25
_CONFIDENCE_LEVEL = 0.95
_MINIMUM_JOINT_POWER = 0.90
_POPULATION_INCREMENT_PER_GEOMETRY = 128
_CONTINUUM_INPUT_COUNT = 1_600
_GEOMETRY_COUNT = 4
_INPUTS_PER_GEOMETRY = 400


def _object(path: Path, *, label: str) -> dict[str, object]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is malformed")
    return cast(dict[str, object], value)


def _input_geometries(request: dict[str, object]) -> dict[str, str]:
    """Index the frozen dataset geometry for every Continuum input."""
    raw_inputs = request.get("inputs")
    if not isinstance(raw_inputs, list):
        raise ValueError("source request inputs are malformed")
    output: dict[str, str] = {}
    for untyped in cast(list[object], raw_inputs):
        if not isinstance(untyped, dict):
            raise ValueError("source request input is malformed")
        row = cast(dict[str, object], untyped)
        if row.get("lane") != "continuum":
            continue
        input_id = row.get("input_id")
        dataset = row.get("dataset_identifier")
        if (
            not isinstance(input_id, str)
            or not isinstance(dataset, str)
            or input_id in output
        ):
            raise ValueError("Continuum input identity is malformed")
        output[input_id] = dataset
    if len(output) != _CONTINUUM_INPUT_COUNT:
        raise ValueError("source request must contain 1,600 Continuum inputs")
    return output


def _summary_index(
    decision: dict[str, object],
) -> dict[tuple[str, str], dict[str, object]]:
    """Index the exact retained array-free realization summaries."""
    container = decision.get("array_free_endpoint_summaries")
    if not isinstance(container, dict):
        raise ValueError("closed endpoint summaries are absent")
    raw = cast(dict[str, object], container).get("summaries")
    if not isinstance(raw, list):
        raise ValueError("closed endpoint summary rows are malformed")
    output: dict[tuple[str, str], dict[str, object]] = {}
    for untyped in cast(list[object], raw):
        if not isinstance(untyped, dict):
            raise ValueError("closed endpoint summary is malformed")
        row = cast(dict[str, object], untyped)
        finder = row.get("finder_id")
        input_id = row.get("input_id")
        if not isinstance(finder, str) or not isinstance(input_id, str):
            raise ValueError("closed endpoint summary identity is malformed")
        key = (finder, input_id)
        if key in output:
            raise ValueError("closed endpoint summary is duplicated")
        output[key] = row
    expected = _CONTINUUM_INPUT_COUNT * len(_FINDERS)
    if len(output) != expected:
        raise ValueError("closed endpoint summary coverage is incomplete")
    return output


def _endpoint_values(
    summary: dict[str, object], endpoint_id: str
) -> tuple[float, ...]:
    """Return one successful finite array-free endpoint row."""
    endpoints = summary.get("endpoints")
    if not isinstance(endpoints, dict):
        raise ValueError("summary endpoint mapping is malformed")
    untyped = cast(dict[str, object], endpoints).get(endpoint_id)
    if not isinstance(untyped, dict):
        raise ValueError(f"summary endpoint is absent: {endpoint_id}")
    endpoint = cast(dict[str, object], untyped)
    raw = endpoint.get("values")
    if endpoint.get("status") != "success" or not isinstance(raw, list):
        raise ValueError(f"summary endpoint is unavailable: {endpoint_id}")
    values = tuple(float(item) for item in cast(list[object], raw))
    if not values:
        raise ValueError(f"summary endpoint is empty: {endpoint_id}")
    return values


def _validate_shell_aliases(
    summaries: dict[tuple[str, str], dict[str, object]],
) -> None:
    """Prove three registry endpoints are one exact evidence pattern."""
    for summary in summaries.values():
        rows = tuple(
            _endpoint_values(summary, endpoint_id)
            for endpoint_id in _SHELL_ENDPOINTS
        )
        if len(set(rows)) != 1:
            raise ValueError("shell endpoint aliases are not identical")


def _paired_rows(
    summaries: dict[tuple[str, str], dict[str, object]],
    geometries: dict[str, str],
    endpoint_id: str,
) -> tuple[
    dict[str, tuple[tuple[float, ...], ...]],
    dict[str, tuple[tuple[float, ...], ...]],
]:
    """Group exact current/incumbent rows by fixed image geometry."""
    candidate: defaultdict[str, list[tuple[float, ...]]] = defaultdict(list)
    incumbent: defaultdict[str, list[tuple[float, ...]]] = defaultdict(list)
    for input_id, geometry in sorted(geometries.items()):
        candidate[geometry].append(
            _endpoint_values(
                summaries[("current-hebog", input_id)], endpoint_id
            )
        )
        incumbent[geometry].append(
            _endpoint_values(
                summaries[("incumbent-hebog", input_id)], endpoint_id
            )
        )
    counts = {len(value) for value in candidate.values()}
    if len(candidate) != _GEOMETRY_COUNT or counts != {_INPUTS_PER_GEOMETRY}:
        raise ValueError("closed Continuum geometry balance changed")
    return (
        {key: tuple(value) for key, value in sorted(candidate.items())},
        {key: tuple(value) for key, value in sorted(incumbent.items())},
    )


def build_review(
    *,
    decision: dict[str, object],
    source_request: dict[str, object],
) -> dict[str, object]:
    """Build the compact, non-executable scientific pre-review."""
    if (
        decision.get("record_canonical_sha256")
        != _CLOSED_RECORD_CANONICAL_SHA256
        or decision.get("status") != "incomplete"
        or decision.get("comparison_status_counts")
        != {"pass": 1183, "underpowered": 4}
    ):
        raise ValueError("closed paired decision identity or status changed")
    summaries = _summary_index(decision)
    geometries = _input_geometries(source_request)
    _validate_shell_aliases(summaries)
    estimates = []
    for endpoint_id, seed in zip(
        (_SHELL_ENDPOINTS[1], _SCALE_ENDPOINT),
        _BOOTSTRAP_SEEDS,
        strict=True,
    ):
        candidate, incumbent = _paired_rows(summaries, geometries, endpoint_id)
        estimates.append(
            stratified_percentile_regression(
                endpoint_id=endpoint_id,
                candidate_by_stratum=candidate,
                incumbent_by_stratum=incumbent,
                percentile=95.0,
                resamples=_BOOTSTRAP_RESAMPLES,
                seed=seed,
            )
        )
    minimum = minimum_balanced_confirmation_count(
        estimates,
        variance_inflation=_VARIANCE_INFLATION,
        confidence_level=_CONFIDENCE_LEVEL,
        minimum_joint_power=_MINIMUM_JOINT_POWER,
    )
    minimum_per_geometry = minimum.selected_count_per_stratum
    selected_per_geometry = (
        (minimum_per_geometry + _POPULATION_INCREMENT_PER_GEOMETRY - 1)
        // _POPULATION_INCREMENT_PER_GEOMETRY
        * _POPULATION_INCREMENT_PER_GEOMETRY
    )
    selected = balanced_confirmation_power(
        estimates,
        selected_count_per_stratum=selected_per_geometry,
        variance_inflation=_VARIANCE_INFLATION,
        confidence_level=_CONFIDENCE_LEVEL,
        minimum_joint_power=_MINIMUM_JOINT_POWER,
    )
    if selected.joint_power_lower_bound < _MINIMUM_JOINT_POWER:
        raise ValueError("selected retention confirmation is underpowered")
    return {
        "schema_version": 1,
        "review_id": "phase-5-final-retention-confirmation-pre-review",
        "status": "awaiting-human-scientific-review",
        "closed_evidence": {
            "paired_decision_file_sha256": _CLOSED_DECISION_SHA256,
            "paired_decision_record_canonical_sha256": (
                _CLOSED_RECORD_CANONICAL_SHA256
            ),
            "source_request_sha256": _SOURCE_REQUEST_SHA256,
            "binding_comparison_counts": {
                "aegean_pass": 143,
                "dual_pybdsf_pass": 676,
                "incumbent_hebog_pass": 364,
                "incumbent_hebog_underpowered": 4,
                "fail": 0,
            },
            "binding_safety_all_passed": True,
            "scientific_interpretation": (
                "PyBDSF parity is demonstrated on the complete regression "
                "population. No material incumbent-Hebog regression is "
                "detected; final retention remains inconclusive for two "
                "distinct position-tail evidence patterns."
            ),
        },
        "root_cause": {
            "source_finding_defect_detected": False,
            "cause": (
                "The closed evaluator resampled four deliberately balanced "
                "Continuum geometries as one pooled mixture. That allowed "
                "geometry proportions to fluctuate even though the design "
                "fixed 400 images per geometry, adding composition variance "
                "to nonlinear pooled p95 position endpoints."
            ),
            "distinct_evidence_patterns": 2,
            "shell_alias_endpoint_ids": list(_SHELL_ENDPOINTS),
            "scale_endpoint_id": _SCALE_ENDPOINT,
            "post_result_sensitivity_role": (
                "planning-only; does not rescore or replace the closed verdict"
            ),
        },
        "planning_method": {
            "independent_unit": "whole-noise-seed-image",
            "fixed_design_stratum": "continuum-dataset-geometry",
            "statistic": "pooled-position-error-percentile-95",
            "resampling": "within-geometry-whole-image-bootstrap",
            "bootstrap_resamples": _BOOTSTRAP_RESAMPLES,
            "confidence_level": _CONFIDENCE_LEVEL,
            "practical_regression_margin_beams": 0.05,
            "variance_inflation": _VARIANCE_INFLATION,
            "unfavourable_closed_shift_retained_fraction": 1.0,
            "joint_power_bound": "conservative-union-lower-bound",
            "minimum_joint_power": _MINIMUM_JOINT_POWER,
        },
        "planning_estimates": [asdict(item) for item in estimates],
        "minimum_balanced_population": asdict(minimum),
        "selected_balanced_population": asdict(selected),
        "recommendations": {
            "source_finding_change_required": False,
            "closed_decision_remains_immutable_and_incomplete": True,
            "public_interface_work_may_proceed": True,
            "confirmation_population": (
                f"{selected.selected_realization_count} new seed-disjoint "
                f"Continuum images, exactly {selected_per_geometry} per "
                "frozen geometry, for current-versus-incumbent retention"
            ),
            "qualification_integration": (
                "Use the same new images as the required held-out public-API "
                "qualification; do not run a separate intermediate campaign."
            ),
            "pybdsf_scope": (
                "Run both frozen PyBDSF comparators on the prospectively "
                "selected 1600-image balanced qualification subset; the "
                f"additional {selected.selected_realization_count - 1600} "
                "images close only the two incumbent-retention patterns."
            ),
            "decision_rule": (
                "Phase 5 scientific evidence passes only if every held-out "
                "PyBDSF/Aegean gate passes and the stratified upper bound for "
                "both distinct retention patterns is at most 0.05 beams."
            ),
            "failure_action": (
                "A material held-out regression opens a new root-cause "
                "review; "
                "otherwise no further Phase 5 source-finder improvement is "
                "required."
            ),
        },
        "authorization": {
            "candidate_execution_authorized": False,
            "cutover_authorized": False,
            "fresh_qualification_authorized": False,
            "optimization_authorized": False,
            "release_authorized": False,
            "rescoring_authorized": False,
            "source_finding_change_authorized": False,
            "threshold_or_margin_tuning_authorized": False,
            "viewed_data_execution_authorized": False,
        },
    }


def main() -> None:
    """Validate closed evidence and write one deterministic pre-review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", required=True, type=Path)
    parser.add_argument("--source-request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if file_sha256(arguments.decision) != _CLOSED_DECISION_SHA256:
        raise ValueError("closed paired decision file identity changed")
    if file_sha256(arguments.source_request) != _SOURCE_REQUEST_SHA256:
        raise ValueError("source request identity changed")
    review = build_review(
        decision=_object(arguments.decision, label="closed paired decision"),
        source_request=_object(
            arguments.source_request, label="source request"
        ),
    )
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite retention review: {arguments.output}"
        )
    arguments.output.write_text(
        json.dumps(review, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(arguments.output)
    print(f"review_sha256={file_sha256(arguments.output)}")
    print(f"review_canonical_sha256={canonical_sha256(review)}")


if __name__ == "__main__":
    main()
