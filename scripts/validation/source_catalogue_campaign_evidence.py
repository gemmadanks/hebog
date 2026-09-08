"""Compile retained native measurements with the frozen cumulative rules.

This module is evaluation-only. It never imports a finder runner, changes a
scientific contract, generates an image, or starts a scheduler.
"""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import json
import runpy
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.validation import compile_phase5_external_campaign as compiler
from scripts.validation import evaluate_phase5_prospective_paired_cumulative
from scripts.validation.prepare_phase5_prospective_paired_evidence import (
    evaluate_prospective_cumulative_evidence,
)

from hebog.validation.diagnostic_retention import (
    _atomic_json,
    _verify_record_digest,
)
from hebog.validation.evidence import (
    CampaignImplementationIdentity,
    CampaignRealizationDiagnostic,
    EvidenceStatus,
    ScientificCampaignEvidence,
)
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.prospective_science_contract import (
    ProspectiveEndpointRegistry,
)


def load_cumulative_policy(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reuse the validated historical rules, not their consumed authority.

    The historical source view is scoped to its original protocol loader;
    it never substitutes the current candidate's identity or permits a run.
    """
    viewed = runpy.run_path(
        str(root / "scripts/validation/phase5_viewed_recovery_protocol.py")
    )
    viewed["_install_historical_source_view"]()
    registry = viewed["_HISTORICAL"]["load_post_failure_endpoint_registry"](
        root
        / "config/contracts"
        / "phase-5-external-post-failure-endpoint-registry.json"
    )
    protocol = viewed["load_viewed_recovery_protocol"](
        root / registry["protocol_path"]
    )
    return registry, protocol.model_dump(mode="json")


def retain_image_record(path: Path, record: dict[str, Any]) -> str:
    """Durably publish one complete image before any late aggregation."""
    if not record.get("input_id") or not record.get("finder_id"):
        raise ValueError("image record requires input and finder identities")
    _verify_record_digest(record)
    _atomic_json(path, record)
    return file_sha256(path)


def load_image_records(
    entries: Sequence[Mapping[str, str]],
    expected_keys: Sequence[tuple[str, str]],
) -> tuple[dict[str, Any], ...]:
    """Require the complete exact census, including explicit failed rows."""
    records: list[dict[str, Any]] = []
    for entry in entries:
        path = Path(entry["path"])
        if path.is_symlink() or file_sha256(path) != entry["sha256"]:
            raise ValueError("retained image bytes changed")
        record = json.loads(path.read_bytes())
        _verify_record_digest(record)
        records.append(record)
    keys = [(row["input_id"], row["finder_id"]) for row in records]
    if len(set(expected_keys)) != len(expected_keys) or sorted(keys) != sorted(
        expected_keys
    ):
        raise ValueError("retained image census is incomplete or duplicated")
    return tuple(sorted(records, key=lambda row: row["input_id"]))


def continuum_observations(
    records: Sequence[Mapping[str, Any]],
    specifications: Sequence[compiler.ContinuumEndpointSpec],
) -> dict[str, dict[str, tuple[compiler.EndpointObservation, ...]]]:
    """Rehydrate sufficient statistics without reopening scientific arrays."""
    grouped: dict[str, dict[str, list[compiler.EndpointObservation]]] = {}
    for record in records:
        if record["lane"] != "continuum":
            continue
        finder = record["finder_id"]
        rows = grouped.setdefault(
            finder, {spec.endpoint_id: [] for spec in specifications}
        )
        values = record["continuum_observations"]
        if set(values) != set(rows):
            raise ValueError("retained continuum endpoint identities changed")
        for endpoint_id, observation in values.items():
            if observation["image_key"] != record["input_id"]:
                raise ValueError("retained continuum image identity changed")
            rows[endpoint_id].append(
                compiler.EndpointObservation(**observation)
            )
    return {
        finder: {
            key: tuple(sorted(rows, key=lambda row: row.image_key))
            for key, rows in endpoints.items()
        }
        for finder, endpoints in grouped.items()
    }


def compile_continuum_records(  # noqa: PLR0913
    records: Sequence[Mapping[str, Any]],
    historical_registry: dict[str, Any],
    registry: ProspectiveEndpointRegistry,
    *,
    expected_image_count: int,
    resamples: int,
    seed: int,
    planning_deviations: Mapping[str, float],
) -> tuple[list[dict[str, object]], list[Any]]:
    """Evaluate actual incumbent observations, never structural zeros."""
    specs = compiler.expand_continuum_endpoint_specs(historical_registry)
    observations = continuum_observations(records, specs)
    prospective = {row.endpoint_id: row for row in registry.endpoints}
    evidence: list[dict[str, object]] = []
    compiled: list[Any] = []
    for specification in specs:
        endpoint = prospective[specification.endpoint_id]
        candidate = observations["current-hebog"][specification.endpoint_id]
        references: dict[str, Sequence[compiler.EndpointObservation]] = {
            identifier: observations[identifier][specification.endpoint_id]
            for identifier in endpoint.comparators
        }
        direction, absolute_statistic = compiler._continuum_policy(
            specification.metric_family
        )
        # Some old absolute-position endpoints were unpaired. The frozen
        # prospective registry makes their incumbent retention binding.
        paired_specification = replace(specification, paired=bool(references))
        result = compiler.compile_continuum_endpoint(
            paired_specification,
            candidate,
            references,
            expected_image_count=expected_image_count,
            desirable_direction=direction,
            absolute_decision_statistic=absolute_statistic,
            resamples=resamples,
            seed=seed,
        )
        compiled.append(result)
        comparisons = {row.reference_id: row for row in result.comparisons}
        evidence.extend(
            evaluate_phase5_prospective_paired_cumulative._comparison_evidence(
                endpoint,
                comparator,
                result.candidate_status,
                comparisons.get(comparator),
                planning_deviations,
            )
            for comparator in endpoint.comparators
        )
    return evidence, compiled


def compact_comparison_rows(
    registry: ProspectiveEndpointRegistry,
    decisions: Sequence[Mapping[str, Any]],
) -> list[dict[str, object]]:
    """Translate measured Phase 4R results for every frozen comparator."""
    indexed: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for decision in decisions:
        key = (
            decision["reference_identifier"],
            decision["metric_id"],
            decision["stratum"],
        )
        if key in indexed:
            raise ValueError("compact comparison is duplicated")
        indexed[key] = decision
    rows: list[dict[str, object]] = []
    for endpoint in registry.endpoints:
        if endpoint.lane != "compact" or endpoint.role != "binding":
            continue
        for identifier in endpoint.comparators:
            result = indexed.get(
                (identifier, endpoint.metric_family, endpoint.stratum)
            )
            rows.append(
                {
                    "candidate_available": result is not None
                    and result.get("candidate_value") is not None,
                    "comparator_available": result is not None
                    and result.get("reference_value") is not None,
                    "comparator_id": identifier,
                    "endpoint_id": endpoint.endpoint_id,
                    "observed_paired_standard_deviation": None,
                    "planning_paired_standard_deviation": None,
                    "positive_regression": result.get("positive_regression")
                    if result
                    else None,
                    "upper_confidence_limit": result.get(
                        "upper_confidence_limit"
                    )
                    if result
                    else None,
                }
            )
    return rows


def compile_compact_records(  # noqa: PLR0913
    records: Sequence[Mapping[str, Any]],
    historical_registry: dict[str, Any],
    *,
    repository_root: Path,
    implementations: Sequence[CampaignImplementationIdentity],
    captured_at: datetime,
    expected_image_count: int,
) -> tuple[dict[str, Any], ...]:
    """Use the original image-cluster BCa engine on retained diagnostics."""
    datasets, _ = compiler._dataset_maps(
        repository_root / historical_registry["compact_manifest_path"]
    )
    if len(datasets) != 1:
        raise ValueError("compact dataset census changed")
    dataset = compiler._phase_four_interval_dataset(
        next(iter(datasets.values()))
    )
    paths = tuple(
        repository_root / historical_registry[key]
        for key in (
            "phase_four_measurement_path",
            "phase_four_gates_path",
            "phase_four_registry_path",
            "phase_four_protocol_path",
        )
    )
    scientific_hash = compiler.contract_set_sha256(list(paths))
    metric_registry = compiler.load_phase_four_metric_registry(paths[2])
    protocol = compiler.load_paired_noninferiority_contract(paths[3])
    gates = compiler.load_phase_four_scientific_gates(paths[1])
    diagnostics: tuple[CampaignRealizationDiagnostic, ...] = tuple(
        CampaignRealizationDiagnostic.model_validate(row["compact_diagnostic"])
        for row in records
        if row["lane"] == "compact-blend"
    )
    by_identity = {row.identifier: row for row in implementations}
    output: list[dict[str, Any]] = []
    # The engine accepts two reference identities per campaign view. The
    # incumbent uses its real identifier, not a PyBDSF alias or equal bytes.
    for reference_ids in (
        ("released-pybdsf", "pinned-pybdsf-master"),
        ("aegean", "incumbent-hebog"),
    ):
        identifiers = ("current-hebog", *reference_ids)
        selected = tuple(
            sorted(
                (
                    row
                    for row in diagnostics
                    if row.implementation_identifier in identifiers
                ),
                key=lambda row: (
                    row.seed,
                    identifiers.index(row.implementation_identifier),
                ),
            )
        )
        for identifier in identifiers:
            seeds = [
                row.seed
                for row in selected
                if row.implementation_identifier == identifier
            ]
            if len(seeds) != expected_image_count or len(set(seeds)) != len(
                seeds
            ):
                raise ValueError("compact realization census changed")
        campaign = ScientificCampaignEvidence(
            schema_version=1,
            evidence_type="scientific-campaign",
            run_id="r6-native-compact-" + "-".join(reference_ids),
            captured_at=captured_at,
            status=EvidenceStatus.EXPLORATORY,
            dataset=compiler.campaign_dataset_identity(dataset),
            configuration_sha256=scientific_hash,
            comparison_protocol_sha256=canonical_sha256(
                protocol.model_dump(mode="json")
            ),
            implementations=tuple(by_identity[key] for key in identifiers),
            realizations=selected,
        )
        result = compiler.evaluate_phase_four_recovery(
            campaign,
            dataset,
            metric_registry,
            protocol,
            gates,
            stage="qualification",
            scientific_contract_set_sha256=scientific_hash,
            candidate_identifier="current-hebog",
            reference_identifiers=reference_ids,
            captured_at=captured_at,
        )
        output.append(result.model_dump(mode="json"))
    return tuple(output)


def compile_cumulative_decision(  # noqa: PLR0913
    *,
    records: Sequence[Mapping[str, Any]],
    registry: ProspectiveEndpointRegistry,
    historical_registry: dict[str, Any],
    compact_decisions: Sequence[Mapping[str, Any]],
    safety_results: Mapping[str, bool],
    expected_continuum_count: int,
    resamples: int,
    seed: int,
    planning_deviations: Mapping[str, float],
) -> dict[str, Any]:
    """Intersect all 1,187 comparisons and safety; objectives stay visible."""
    continuum_rows, continuum = compile_continuum_records(
        records,
        historical_registry,
        registry,
        expected_image_count=expected_continuum_count,
        resamples=resamples,
        seed=seed,
        planning_deviations=planning_deviations,
    )
    compact_rows = compact_comparison_rows(
        registry,
        [
            row
            for decision in compact_decisions
            for row in decision["metric_decisions"]
        ],
    )
    rows = [*compact_rows, *continuum_rows]
    if len(rows) != registry.counts.total_coprimary_comparisons:
        raise ValueError("cumulative comparison census changed")
    decision = evaluate_prospective_cumulative_evidence(
        registry=registry,
        comparisons=rows,
        safety_results=safety_results,
        absolute_objectives=(
            evaluate_phase5_prospective_paired_cumulative._objective_rows(
                registry, continuum
            )
        ),
    )
    return {
        **decision,
        "compact_decisions": list(compact_decisions),
        "continuum_endpoints": [asdict(row) for row in continuum],
        "structural_incumbent_equality_used": False,
        "previous_human_uncertainty_acceptance_transferred": False,
    }
