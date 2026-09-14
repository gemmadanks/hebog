#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportPrivateUsage=false
"""Prepare prospective paired Phase 5 decisions and bounded diagnostics.

This module is evaluation-only.  It deliberately contains no candidate
execution entry point and does not read a completed candidate result at import
time.  The future replay wrapper passes compiled paired evidence to the pure
functions below and retains only bounded, array-free scientific summaries.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from math import hypot, isfinite
from typing import cast

import numpy as np
import numpy.typing as npt

from hebog.validation import external_successor_compiler as successor
from hebog.validation.external_runners import canonical_sha256
from hebog.validation.prospective_science_contract import (
    ProspectiveEndpoint,
    ProspectiveEndpointRegistry,
)
from hebog.validation.prospective_science_power import (
    build_prospective_power_audit,
)

_SAFETY_INVARIANTS = (
    "finite-measurements",
    "product-validity",
    "schema-and-provenance-integrity",
    "serial-and-existing-dask-determinism",
    "write-once-publication",
)
_TAIL_SENTINELS = (
    "morphology-artifact",
    "morphology-shell",
    "scale-4-beam",
    "tile-corner",
    "varying-noise",
)
_COMPARISON_SECTIONS = {
    "aegean": "aegean_parity",
    "incumbent-hebog": "incumbent_retention",
    "pinned-pybdsf-master": "pybdsf_parity",
    "released-pybdsf": "pybdsf_parity",
}
_PAIR_WIDTH = 2


def build_aligned_prospective_power_audit(
    *,
    registry: ProspectiveEndpointRegistry,
    external_protocol: dict[str, object],
    smoke_record: dict[str, object],
) -> dict[str, object]:
    """Power the full design from immutable smoke prerequisites.

    The closed smoke's top-level status also depended on a legacy mechanism
    activation diagnostic.  The prospective contract uses the smoke only to
    establish compact identity and the absence of confirmed comparison
    failures.  This adapter checks those fields explicitly and never changes
    the stored smoke record.
    """
    if (
        smoke_record.get("promotion_evidence") is not False
        or smoke_record.get("compact_product_identity_equal") is not True
        or smoke_record.get("terminal_failure_count") != 0
    ):
        raise ValueError("prospective paired power prerequisites did not pass")
    aligned = {**smoke_record, "status": "pass"}
    audit = build_prospective_power_audit(
        registry=registry,
        external_protocol=external_protocol,
        smoke_record=aligned,
    )
    comparisons = cast(list[dict[str, object]], audit.pop("comparisons"))
    return {
        **audit,
        "immutable_smoke_status": smoke_record.get("status"),
        "smoke_prerequisite_rule": (
            "compact-identity-and-zero-confirmed-comparison-failures"
        ),
        "comparison_design_sha256": canonical_sha256(comparisons),
        "comparison_design_rows_retained": False,
    }


def _finite_optional(value: object, *, label: str) -> float | None:
    """Return one finite optional number without accepting booleans."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number or null")
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{label} must be a finite number or null")
    return converted


def _comparison_decision(  # noqa: C901
    endpoint: ProspectiveEndpoint,
    comparator_id: str,
    evidence: Mapping[str, object] | None,
) -> dict[str, object]:
    """Decide one frozen comparison independently of planning dispersion."""
    margin = endpoint.practical_regression_margins[comparator_id]
    if evidence is None:
        return {
            "endpoint_id": endpoint.endpoint_id,
            "comparator_id": comparator_id,
            "status": "underpowered",
            "passed": False,
            "positive_regression": None,
            "upper_confidence_limit": None,
            "practical_regression_margin": margin,
            "observed_paired_standard_deviation": None,
            "planning_paired_standard_deviation": None,
            "planning_variance_assumption_met": None,
            "assumption_deviations": ["comparison-evidence-is-missing"],
            "reason": "binding comparison evidence is missing",
        }
    candidate_available = evidence.get("candidate_available")
    comparator_available = evidence.get("comparator_available")
    if (
        type(candidate_available) is not bool
        or type(comparator_available) is not bool
    ):
        raise ValueError("comparison availability must be boolean")
    point = _finite_optional(
        evidence.get("positive_regression"), label="positive regression"
    )
    upper = _finite_optional(
        evidence.get("upper_confidence_limit"),
        label="upper confidence limit",
    )
    observed = _finite_optional(
        evidence.get("observed_paired_standard_deviation"),
        label="observed paired standard deviation",
    )
    planned = _finite_optional(
        evidence.get("planning_paired_standard_deviation"),
        label="planning paired standard deviation",
    )
    if observed is not None and observed < 0.0:
        raise ValueError(
            "observed paired standard deviation must be non-negative"
        )
    if planned is not None and planned <= 0.0:
        raise ValueError("planning paired standard deviation must be positive")
    planning_met = (
        observed <= planned
        if observed is not None and planned is not None
        else None
    )
    deviations: list[str] = []
    if planning_met is False:
        deviations.append(
            "observed-paired-standard-deviation-exceeds-planning-assumption"
        )
    elif planning_met is None:
        deviations.append("planning-variance-audit-unavailable")
    if not candidate_available:
        status = "fail"
        reason = "binding candidate evidence is unavailable"
    elif not comparator_available:
        status = "underpowered"
        reason = "binding comparator evidence is unavailable"
    elif point is None or upper is None:
        status = "indeterminate"
        reason = "paired point or confidence evidence is missing"
    elif upper <= margin:
        status = "pass"
        reason = "observed paired upper confidence limit is within margin"
    elif point > margin:
        status = "fail"
        reason = "paired point regression exceeds the practical margin"
    else:
        status = "underpowered"
        reason = "observed paired confidence interval crosses the margin"
    return {
        "endpoint_id": endpoint.endpoint_id,
        "comparator_id": comparator_id,
        "status": status,
        "passed": status == "pass",
        "positive_regression": point,
        "upper_confidence_limit": upper,
        "practical_regression_margin": margin,
        "observed_paired_standard_deviation": observed,
        "planning_paired_standard_deviation": planned,
        "planning_variance_assumption_met": planning_met,
        "assumption_deviations": deviations,
        "reason": reason,
    }


def _comparison_index(
    registry: ProspectiveEndpointRegistry,
    comparisons: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str], Mapping[str, object]]:
    """Validate comparison identity without requiring completeness."""
    expected = {
        (endpoint.endpoint_id, comparator)
        for endpoint in registry.endpoints
        if endpoint.role == "binding"
        for comparator in endpoint.comparators
    }
    indexed: dict[tuple[str, str], Mapping[str, object]] = {}
    for row in comparisons:
        endpoint_id = row.get("endpoint_id")
        comparator_id = row.get("comparator_id")
        if not isinstance(endpoint_id, str) or not isinstance(
            comparator_id, str
        ):
            raise ValueError("comparison identity is malformed")
        key = (endpoint_id, comparator_id)
        if key not in expected:
            raise ValueError("comparison identity is not frozen")
        if key in indexed:
            raise ValueError("comparison identity is duplicated")
        indexed[key] = row
    return indexed


def _absolute_objective_rows(
    registry: ProspectiveEndpointRegistry,
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Retain every numeric objective without letting it affect readiness."""
    expected = {
        endpoint.endpoint_id: endpoint
        for endpoint in registry.endpoints
        if endpoint.role == "longer-term-objective"
    }
    indexed: dict[str, Mapping[str, object]] = {}
    for row in rows:
        endpoint_id = row.get("endpoint_id")
        if not isinstance(endpoint_id, str) or endpoint_id not in expected:
            raise ValueError("absolute objective identity is not frozen")
        if endpoint_id in indexed:
            raise ValueError("absolute objective identity is duplicated")
        indexed[endpoint_id] = row
    output: list[dict[str, object]] = []
    for endpoint_id, endpoint in sorted(expected.items()):
        row = indexed.get(endpoint_id)
        if row is None:
            output.append(
                {
                    "endpoint_id": endpoint_id,
                    "metric_family": endpoint.metric_family,
                    "stratum": endpoint.stratum,
                    "candidate_status": "unavailable",
                    "candidate_value": None,
                    "objective_value": None,
                    "objective_passed": None,
                    "promotion_effect": "none-report-only",
                }
            )
            continue
        status = row.get("candidate_status")
        passed = row.get("objective_passed")
        if not isinstance(status, str) or (
            passed is not None and type(passed) is not bool
        ):
            raise ValueError("absolute objective evidence is malformed")
        output.append(
            {
                "endpoint_id": endpoint_id,
                "metric_family": endpoint.metric_family,
                "stratum": endpoint.stratum,
                "candidate_status": status,
                "candidate_value": _finite_optional(
                    row.get("candidate_value"), label="objective candidate"
                ),
                "objective_value": _finite_optional(
                    row.get("objective_value"), label="objective value"
                ),
                "objective_passed": passed,
                "promotion_effect": "none-report-only",
            }
        )
    return output


def evaluate_prospective_cumulative_evidence(
    *,
    registry: ProspectiveEndpointRegistry,
    comparisons: Sequence[Mapping[str, object]],
    safety_results: Mapping[str, bool],
    absolute_objectives: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Apply the frozen prospective intersection-union decision contract.

    Planning dispersion is reported separately and never changes a confidence
    decision.  Numeric absolute objectives remain visible but have no
    promotion effect.  Every expected comparator is emitted, including a
    fail-closed placeholder when its evidence is missing.
    """
    indexed = _comparison_index(registry, comparisons)
    sections: dict[str, list[dict[str, object]]] = {
        "aegean_parity": [],
        "incumbent_retention": [],
        "pybdsf_parity": [],
    }
    for endpoint in registry.endpoints:
        if endpoint.role != "binding":
            continue
        for comparator_id in endpoint.comparators:
            row = _comparison_decision(
                endpoint,
                comparator_id,
                indexed.get((endpoint.endpoint_id, comparator_id)),
            )
            sections[_COMPARISON_SECTIONS[comparator_id]].append(row)
    unknown_safety = set(safety_results).difference(_SAFETY_INVARIANTS)
    if unknown_safety:
        raise ValueError("binding safety identity is not frozen")
    safety = {
        invariant: safety_results.get(invariant, False)
        for invariant in _SAFETY_INVARIANTS
    }
    objectives = _absolute_objective_rows(registry, absolute_objectives)
    decisions = [row for values in sections.values() for row in values]
    statuses = Counter(cast(str, row["status"]) for row in decisions)
    planning_deviations = [
        {
            "endpoint_id": row["endpoint_id"],
            "comparator_id": row["comparator_id"],
            "deviations": row["assumption_deviations"],
        }
        for row in decisions
        if row["assumption_deviations"]
        and row["assumption_deviations"]
        != ["planning-variance-audit-unavailable"]
    ]
    has_failure = statuses["fail"] > 0 or not all(safety.values())
    has_incomplete = (
        statuses["underpowered"] > 0 or statuses["indeterminate"] > 0
    )
    status = (
        "fail" if has_failure else "incomplete" if has_incomplete else "pass"
    )
    return {
        "schema_version": 1,
        "record_id": "phase-5-prospective-paired-cumulative-decision",
        "status": status,
        "decision_rule": "intersection-union-every-coprimary-comparison",
        **sections,
        "binding_safety": safety,
        "longer_term_absolute_objectives": objectives,
        "comparison_status_counts": dict(sorted(statuses.items())),
        "planning_assumption_audit": {
            "role": "report-only-not-observed-data-gate",
            "deviation_count": len(planning_deviations),
            "deviations": planning_deviations,
        },
        "section_counts": {
            "aegean_parity": len(sections["aegean_parity"]),
            "binding_safety": len(safety),
            "incumbent_retention": len(sections["incumbent_retention"]),
            "longer_term_absolute_objectives": len(objectives),
            "pybdsf_parity": len(sections["pybdsf_parity"]),
        },
        "all_required_endpoints_pass": status == "pass",
        "cumulative_science_regression_ready": status == "pass",
        "fresh_qualification_execution_authorized": False,
        "cutover_authorized": False,
        "release_authorized": False,
    }


def _normalized_hierarchy_diagnostics(
    values: Mapping[str, object],
) -> dict[str, object]:
    """Validate bounded, JSON-native association-mechanism diagnostics."""
    output: dict[str, object] = {}
    for key, value in sorted(values.items()):
        if not key:
            raise ValueError("hierarchy diagnostic identity is empty")
        if type(value) is int:
            if value < 0:
                raise ValueError("hierarchy diagnostic count is negative")
            output[key] = value
            continue
        if isinstance(value, (list, tuple)):
            rows: list[list[int]] = []
            for item in value:
                if (
                    not isinstance(item, (list, tuple))
                    or len(item) != _PAIR_WIDTH
                    or any(type(part) is not int for part in item)
                    or any(cast(int, part) < 0 for part in item)
                ):
                    raise ValueError("hierarchy diagnostic row is malformed")
                rows.append([cast(int, item[0]), cast(int, item[1])])
            output[key] = rows
            continue
        raise ValueError("hierarchy diagnostic value is malformed")
    return output


def _mask_counts(
    truth_labels: npt.NDArray[np.int64],
    candidate_labels: npt.NDArray[np.int64],
) -> dict[str, int]:
    """Reduce two transient label planes to exact overlap counts."""
    truth_mask = truth_labels > 0
    candidate_mask = candidate_labels > 0
    return {
        "candidate_mask_pixels": int(np.count_nonzero(candidate_mask)),
        "intersection_mask_pixels": int(
            np.count_nonzero(truth_mask & candidate_mask)
        ),
        "truth_mask_pixels": int(np.count_nonzero(truth_mask)),
        "union_mask_pixels": int(
            np.count_nonzero(truth_mask | candidate_mask)
        ),
    }


def build_truth_linked_continuum_summary(  # noqa: C901, PLR0913
    *,
    input_id: str,
    dataset_identifier: str,
    seed: int,
    finder_id: str,
    truth: Sequence[successor.ContinuumTruthObject],
    catalogue: Sequence[successor.ContinuumCatalogueObject],
    truth_label_plane: npt.ArrayLike,
    candidate_label_plane: npt.ArrayLike,
    association_label_plane: npt.ArrayLike | None = None,
    beam_fwhm_pixels: float,
    source_member_counts: Mapping[str, int],
    hierarchy_diagnostics: Mapping[str, object],
) -> dict[str, object]:
    """Reduce one image to attributable, array-free sufficient statistics."""
    if not input_id or not dataset_identifier or not finder_id:
        raise ValueError("truth-linked summary identity is incomplete")
    if type(seed) is not int or seed < 0:
        raise ValueError("truth-linked summary seed is invalid")
    if not isfinite(beam_fwhm_pixels) or beam_fwhm_pixels <= 0.0:
        raise ValueError("beam FWHM must be finite and positive")
    truth_rows = tuple(truth)
    catalogue_rows = tuple(catalogue)
    if not truth_rows or len({item.identifier for item in truth_rows}) != len(
        truth_rows
    ):
        raise ValueError("truth group identity is empty or duplicated")
    candidate_ids = {item.identifier for item in catalogue_rows}
    if (
        len(candidate_ids) != len(catalogue_rows)
        or set(source_member_counts) != candidate_ids
        or any(
            type(value) is not int or value < 1
            for value in source_member_counts.values()
        )
    ):
        raise ValueError("source membership evidence does not match catalogue")
    truth_labels = successor._label_plane(
        truth_label_plane, name="truth label plane"
    )
    publication_labels = successor._label_plane(
        candidate_label_plane, name="candidate label plane"
    )
    association_labels = successor._label_plane(
        (
            candidate_label_plane
            if association_label_plane is None
            else association_label_plane
        ),
        name="candidate association label plane",
    )
    if (
        truth_labels.shape != publication_labels.shape
        or truth_labels.shape != association_labels.shape
    ):
        raise ValueError("truth and candidate label planes must share shape")
    native_supports = successor.native_support_objects(association_labels)
    associations = successor._association_context(
        truth_rows,
        catalogue_rows,
        successor._topology_support_objects(native_supports, catalogue_rows),
        label_planes=(truth_labels, association_labels),
        beam_fwhm_pixels=beam_fwhm_pixels,
    )
    groups: list[dict[str, object]] = []
    for truth_item in sorted(truth_rows, key=lambda item: item.identifier):
        primary_id = associations.primary.get(truth_item.identifier)
        primary = (
            associations.candidate_by_id[primary_id]
            if primary_id is not None
            else None
        )
        support_ids = tuple(
            sorted(
                {
                    edge.candidate_identifier
                    for edge in associations.support_edges
                    if edge.truth_identifier == truth_item.identifier
                }
            )
        )
        catalogue_count = associations.catalogue_truth_degrees[
            truth_item.identifier
        ]
        support_count = associations.support_truth_degrees[
            truth_item.identifier
        ]
        merged_count = sum(
            associations.support_candidate_degrees[item] > 1
            for item in support_ids
        )
        mechanisms: list[str] = []
        if primary is None:
            mechanisms.append("unmatched")
        if catalogue_count > 1:
            mechanisms.append("catalogue-duplicate")
        if support_count > 1:
            mechanisms.append("native-support-split")
        if merged_count:
            mechanisms.append("native-support-merge")
        if not mechanisms:
            mechanisms.append("one-to-one")
        measurable = (
            primary is not None
            and truth_item.catalogue_role == "astronomical-source"
        )
        flux_error = (
            abs(primary.integrated_flux_jy - truth_item.integrated_flux_jy)
            / truth_item.integrated_flux_jy
            if measurable and primary is not None
            else None
        )
        offset_x = (
            (primary.centre_xy[0] - truth_item.centre_xy[0]) / beam_fwhm_pixels
            if measurable and primary is not None
            else None
        )
        offset_y = (
            (primary.centre_xy[1] - truth_item.centre_xy[1]) / beam_fwhm_pixels
            if measurable and primary is not None
            else None
        )
        groups.append(
            {
                "truth_group_id": truth_item.identifier,
                "catalogue_role": truth_item.catalogue_role,
                "strata": list(truth_item.strata),
                "primary_candidate_id": primary_id,
                "primary_source_member_count": (
                    source_member_counts[primary_id]
                    if primary_id is not None
                    else None
                ),
                "catalogue_candidate_count": catalogue_count,
                "native_support_count": support_count,
                "merged_native_support_count": merged_count,
                "native_support_ids": list(support_ids),
                "association_mechanisms": mechanisms,
                "integrated_flux_fractional_error": flux_error,
                "offset_x_beams": offset_x,
                "offset_y_beams": offset_y,
                "position_error_beams": (
                    hypot(offset_x, offset_y)
                    if offset_x is not None and offset_y is not None
                    else None
                ),
            }
        )
    mask_counts = _mask_counts(truth_labels, publication_labels)
    record: dict[str, object] = {
        "schema_version": 1,
        "record_id": "phase-5-array-free-truth-linked-continuum-summary",
        "input_id": input_id,
        "dataset_identifier": dataset_identifier,
        "seed": seed,
        "finder_id": finder_id,
        "image_counts": {
            "candidate_catalogue_sources": len(catalogue_rows),
            "candidate_association_mask_pixels": int(
                np.count_nonzero(association_labels > 0)
            ),
            **mask_counts,
        },
        "unique_primary_candidate_count": len(
            set(associations.primary.values())
        ),
        "truth_groups": groups,
        "hierarchy_diagnostics": _normalized_hierarchy_diagnostics(
            hierarchy_diagnostics
        ),
        "array_planes_retained": False,
    }
    return {**record, "record_sha256": canonical_sha256(record)}


def build_array_free_endpoint_summary(
    *,
    input_id: str,
    finder_id: str,
    observations: Mapping[str, object],
) -> dict[str, object]:
    """Retain one realization's endpoint statistics without array planes."""
    if not input_id or not finder_id or not observations:
        raise ValueError("endpoint summary identity or observations are empty")
    endpoints: dict[str, dict[str, object]] = {}
    for endpoint_id, observation in sorted(observations.items()):
        if not endpoint_id:
            raise ValueError("endpoint observation identity is empty")
        image_key = getattr(observation, "image_key", None)
        status = getattr(observation, "status", None)
        reason = getattr(observation, "reason", None)
        values = getattr(observation, "values", None)
        if image_key != input_id or status not in {
            "success",
            "failed",
            "unavailable",
        }:
            raise ValueError("endpoint observation identity is malformed")
        if reason is not None and not isinstance(reason, str):
            raise ValueError("endpoint observation reason is malformed")
        if not isinstance(values, tuple):
            raise ValueError("endpoint observation values are malformed")
        normalized_values = [
            _finite_optional(value, label="endpoint observation value")
            for value in values
        ]
        if any(value is None for value in normalized_values):
            raise ValueError("endpoint observation value must not be null")
        if status != "success" and normalized_values:
            raise ValueError("failed endpoint observation retains values")
        endpoints[endpoint_id] = {
            "status": status,
            "reason": reason,
            "values": normalized_values,
        }
    record: dict[str, object] = {
        "schema_version": 1,
        "record_id": "phase-5-array-free-realization-endpoint-summary",
        "input_id": input_id,
        "finder_id": finder_id,
        "endpoints": endpoints,
        "array_planes_retained": False,
    }
    return {**record, "record_sha256": canonical_sha256(record)}


def select_result_neutral_tail_sentinels(  # noqa: C901, PLR0912
    *,
    request: Mapping[str, object],
    continuum_manifest: Mapping[str, object],
    count_per_dataset_and_sentinel: int,
) -> dict[str, object]:
    """Select bounded diagnostic sentinels without consulting results."""
    if (
        type(count_per_dataset_and_sentinel) is not int
        or count_per_dataset_and_sentinel < 1
    ):
        raise ValueError("sentinel count must be a positive integer")
    inputs_value = request.get("inputs")
    datasets_value = continuum_manifest.get("datasets")
    if not isinstance(inputs_value, list) or not isinstance(
        datasets_value, list
    ):
        raise ValueError("sentinel source population is malformed")
    continuum_inputs: dict[str, list[Mapping[str, object]]] = {}
    for value in inputs_value:
        if not isinstance(value, dict) or value.get("lane") != "continuum":
            continue
        dataset_id = value.get("dataset_identifier")
        input_id = value.get("input_id")
        seed = value.get("seed")
        if (
            not isinstance(dataset_id, str)
            or not isinstance(input_id, str)
            or type(seed) is not int
        ):
            raise ValueError("sentinel input identity is malformed")
        continuum_inputs.setdefault(dataset_id, []).append(value)
    strata_by_dataset: dict[str, dict[str, tuple[str, ...]]] = {}
    for value in datasets_value:
        if not isinstance(value, dict) or not isinstance(
            value.get("identifier"), str
        ):
            raise ValueError("sentinel dataset identity is malformed")
        strata_value = value.get("multiscale_group_strata")
        if not isinstance(strata_value, list):
            raise ValueError("sentinel truth strata are malformed")
        strata: dict[str, tuple[str, ...]] = {}
        for item in strata_value:
            if not isinstance(item, dict):
                raise ValueError("sentinel truth stratum is malformed")
            identifier = item.get("identifier")
            groups = item.get("group_identifiers")
            if not isinstance(identifier, str) or not isinstance(groups, list):
                raise ValueError("sentinel truth stratum is malformed")
            if any(not isinstance(group, str) for group in groups):
                raise ValueError("sentinel truth group is malformed")
            strata[identifier] = tuple(sorted(cast(list[str], groups)))
        strata_by_dataset[cast(str, value["identifier"])] = strata
    if set(continuum_inputs) != set(strata_by_dataset):
        raise ValueError("sentinel request and manifest datasets differ")
    memberships: list[dict[str, object]] = []
    for sentinel_id in _TAIL_SENTINELS:
        for dataset_id, values in sorted(continuum_inputs.items()):
            groups = strata_by_dataset[dataset_id].get(sentinel_id)
            if not groups:
                raise ValueError("sentinel truth stratum is absent")
            selected = sorted(
                values,
                key=lambda item: (
                    hashlib.sha256(
                        f"{sentinel_id}:{item['input_id']}".encode()
                    ).hexdigest(),
                    cast(str, item["input_id"]),
                ),
            )[:count_per_dataset_and_sentinel]
            if len(selected) != count_per_dataset_and_sentinel:
                raise ValueError("sentinel input population is incomplete")
            memberships.extend(
                {
                    "sentinel_id": sentinel_id,
                    "dataset_identifier": dataset_id,
                    "input_id": item["input_id"],
                    "seed": item["seed"],
                    "truth_group_ids": list(groups),
                }
                for item in selected
            )
    memberships.sort(
        key=lambda item: (
            cast(str, item["sentinel_id"]),
            cast(str, item["dataset_identifier"]),
            cast(str, item["input_id"]),
        )
    )
    return {
        "schema_version": 1,
        "record_id": "phase-5-prospective-paired-tail-sentinels",
        "evidence_role": "result-neutral-development-diagnostic",
        "candidate_results_inspected": False,
        "selection_method": (
            "sha256-sentinel-id-colon-input-id-then-input-id"
        ),
        "count_per_dataset_and_sentinel": (count_per_dataset_and_sentinel),
        "sentinel_ids": list(_TAIL_SENTINELS),
        "membership_count": len(memberships),
        "unique_input_count": len(
            {cast(str, item["input_id"]) for item in memberships}
        ),
        "memberships": memberships,
        "membership_sha256": canonical_sha256(memberships),
    }
