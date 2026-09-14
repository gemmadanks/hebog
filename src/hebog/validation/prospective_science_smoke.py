"""Frozen selection and fail-closed evaluation for the Phase 5 smoke lane."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.prospective_science_contract import (
    ProspectiveEndpointRegistry,
)
from hebog.validation.prospective_science_evaluator import (
    ProspectiveComparisonEvidence,
    evaluate_prospective_comparison,
)


def select_prospective_smoke_inputs(  # noqa: C901
    request_path: Path,
    population_path: Path,
) -> tuple[str, ...]:
    """Reproduce the exact result-neutral 128-input smoke population."""
    population: object = json.loads(
        population_path.read_text(encoding="utf-8")
    )
    if not isinstance(population, dict):
        raise ValueError("prospective smoke population is malformed")
    population_record = cast(dict[str, object], population)
    source: object = population_record.get("source_request")
    selection: object = population_record.get("selection")
    if not isinstance(source, dict) or not isinstance(selection, dict):
        raise ValueError("prospective smoke selection is incomplete")
    source_record = cast(dict[str, object], source)
    selection_record = cast(dict[str, object], selection)
    if file_sha256(request_path) != source_record.get("sha256"):
        raise ValueError("prospective smoke source request changed")
    request: object = json.loads(request_path.read_text(encoding="utf-8"))
    values: object = (
        cast(dict[str, object], request).get("inputs")
        if isinstance(request, dict)
        else None
    )
    if not isinstance(values, list):
        raise ValueError("prospective smoke source inputs are absent")
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("prospective smoke source input is malformed")
        lane = value.get("lane")
        dataset = value.get("dataset_identifier")
        input_id = value.get("input_id")
        if not all(
            isinstance(item, str) for item in (lane, dataset, input_id)
        ):
            raise ValueError("prospective smoke source identity is malformed")
        groups[(cast(str, lane), cast(str, dataset))].append(
            cast(str, input_id)
        )
    selected: list[str] = []
    for (lane, _dataset), identifiers in sorted(groups.items()):
        count = (
            selection_record.get("compact_count")
            if lane == "compact-blend"
            else selection_record.get("continuum_count_per_dataset")
        )
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("prospective smoke selection count is invalid")
        selected.extend(
            sorted(
                identifiers,
                key=lambda item: (
                    hashlib.sha256(item.encode()).hexdigest(),
                    item,
                ),
            )[:count]
        )
    result = tuple(sorted(selected))
    if len(result) != selection_record.get(
        "selected_input_count"
    ) or canonical_sha256(result) != selection_record.get(
        "selected_input_set_canonical_sha256"
    ):
        raise ValueError("prospective smoke selected input set changed")
    return result


def _comparison_by_reference(endpoint: Any) -> dict[str, Any]:
    """Index one compiled endpoint's exact paired evidence."""
    comparisons = getattr(endpoint, "comparisons", None)
    if not isinstance(comparisons, tuple):
        raise ValueError("prospective smoke comparisons are malformed")
    output = {item.reference_id: item for item in comparisons}
    if len(output) != len(comparisons):
        raise ValueError("prospective smoke comparison is duplicated")
    return output


def evaluate_prospective_science_smoke(  # noqa: PLR0913
    *,
    registry: ProspectiveEndpointRegistry,
    current_continuum: Sequence[Any],
    incumbent_paired_continuum: Sequence[Any],
    planning_deviation_by_family: Mapping[str, float],
    compact_product_identity_equal: bool,
    terminal_cycle_aggregate: Mapping[str, int],
) -> dict[str, object]:
    """Evaluate non-promotional science without relaxing the final gate."""
    current = {item.endpoint_id: item for item in current_continuum}
    incumbent = {item.endpoint_id: item for item in incumbent_paired_continuum}
    if len(current) != len(current_continuum) or len(incumbent) != len(
        incumbent_paired_continuum
    ):
        raise ValueError("prospective smoke endpoint is duplicated")
    decisions: list[dict[str, object]] = []
    for endpoint in registry.endpoints:
        if endpoint.lane != "continuum" or endpoint.role != "binding":
            continue
        if (
            endpoint.endpoint_id not in current
            or endpoint.endpoint_id not in incumbent
        ):
            raise ValueError(
                f"prospective smoke endpoint is absent: {endpoint.endpoint_id}"
            )
        current_row = current[endpoint.endpoint_id]
        incumbent_row = incumbent[endpoint.endpoint_id]
        references = _comparison_by_reference(current_row)
        incumbent_references = _comparison_by_reference(incumbent_row)
        for comparator in endpoint.comparators:
            if comparator == "incumbent-hebog":
                evidence = incumbent_references.get("pinned-pybdsf-master")
            else:
                evidence = references.get(comparator)
            available = evidence is not None and evidence.status == "success"
            successful = evidence if available else None
            decision = evaluate_prospective_comparison(
                ProspectiveComparisonEvidence(
                    endpoint_id=endpoint.endpoint_id,
                    comparator_id=comparator,
                    candidate_available=(
                        getattr(current_row, "candidate_status", None)
                        == "success"
                    ),
                    comparator_available=available,
                    positive_regression=(
                        successful.positive_regression
                        if successful is not None
                        else None
                    ),
                    upper_confidence_limit=(
                        successful.upper_confidence_limit
                        if successful is not None
                        else None
                    ),
                    practical_regression_margin=(
                        endpoint.practical_regression_margins[comparator]
                    ),
                    observed_paired_standard_deviation=(
                        successful.observed_paired_standard_deviation
                        if successful is not None
                        else None
                    ),
                    planning_paired_standard_deviation=(
                        planning_deviation_by_family[endpoint.metric_family]
                    ),
                )
            )
            decisions.append(asdict(decision))
    statuses = Counter(cast(str, item["status"]) for item in decisions)
    activation = terminal_cycle_aggregate.get(
        "terminal_cycle_unseeded_persistent_accepted_count", 0
    )
    terminal_failures = statuses["fail"] + statuses["indeterminate"]
    passed = (
        compact_product_identity_equal
        and activation > 0
        and terminal_failures == 0
    )
    incumbent_priors = [
        {
            "endpoint_id": item["endpoint_id"],
            "metric_family": next(
                endpoint.metric_family
                for endpoint in registry.endpoints
                if endpoint.endpoint_id == item["endpoint_id"]
            ),
            "observed_paired_standard_deviation": item[
                "observed_paired_standard_deviation"
            ],
        }
        for item in decisions
        if item["comparator_id"] == "incumbent-hebog"
    ]
    return {
        "schema_version": 1,
        "record_id": "phase-5-prospective-science-smoke",
        "status": "pass" if passed else "fail",
        "evidence_role": "viewed-development-diagnostic-non-promotional",
        "promotion_evidence": False,
        "compact_product_identity_equal": compact_product_identity_equal,
        "terminal_cycle_aggregate": dict(terminal_cycle_aggregate),
        "continuum_status_counts": dict(sorted(statuses.items())),
        "terminal_failure_count": terminal_failures,
        "incumbent_planning_priors": incumbent_priors,
        "decisions": decisions,
    }
