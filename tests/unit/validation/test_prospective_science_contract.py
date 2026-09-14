"""Prospective all-check parity and Hebog-retention contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hebog.validation.prospective_science_contract import (
    ProspectiveEndpointRegistry,
    ProspectiveScienceDecisionContract,
    build_prospective_endpoint_registry,
    load_prospective_endpoint_registry,
    load_prospective_science_contract,
    verify_prospective_contract_sources,
)

_ROOT = Path(__file__).parents[3]
_REGISTRY = (
    _ROOT
    / "config/contracts/phase-5-prospective-science-endpoint-registry.json"
)
_CONTRACT = (
    _ROOT
    / "config/contracts/phase-5-prospective-science-decision-contract.json"
)
_METRIC_REGISTRY = _ROOT / "config/contracts/phase-4r-metric-registry.json"
_SOURCE_REGISTRY = (
    _ROOT / "config/contracts/phase-5-external-endpoint-registry.json"
)


def _load() -> tuple[
    ProspectiveEndpointRegistry,
    ProspectiveScienceDecisionContract,
]:
    """Load the exact frozen registry and decision contract."""
    registry = load_prospective_endpoint_registry(_REGISTRY)
    contract = load_prospective_science_contract(
        _CONTRACT,
        endpoint_registry=registry,
    )
    return registry, contract


def test_registry_covers_every_binding_comparison_without_compensation() -> (
    None
):
    """Every governed endpoint receives every applicable comparator."""
    registry, _ = _load()

    assert registry.counts.total_endpoints == 383
    assert registry.counts.compact_binding_endpoints == 225
    assert registry.counts.continuum_binding_endpoints == 143
    assert registry.counts.continuum_objective_endpoints == 15
    assert registry.counts.pybdsf_endpoints_per_reference == 338
    assert registry.counts.aegean_endpoints == 143
    assert registry.counts.incumbent_retention_endpoints == 368
    assert registry.counts.total_coprimary_comparisons == 1187

    identifiers = tuple(
        endpoint.endpoint_id for endpoint in registry.endpoints
    )
    assert identifiers == tuple(sorted(identifiers))
    assert len(identifiers) == len(set(identifiers))
    binding = tuple(
        endpoint
        for endpoint in registry.endpoints
        if endpoint.role == "binding"
    )
    assert all(
        "incumbent-hebog" in endpoint.comparators for endpoint in binding
    )

    mask_precision = next(
        endpoint
        for endpoint in registry.endpoints
        if endpoint.endpoint_id == "continuum--mask-precision--overall"
    )
    assert mask_precision.comparators == (
        "incumbent-hebog",
        "pinned-pybdsf-master",
        "released-pybdsf",
    )
    assert mask_precision.practical_regression_margins == {
        "incumbent-hebog": 0.05,
        "pinned-pybdsf-master": 0.05,
        "released-pybdsf": 0.05,
    }


def test_frozen_registry_is_reproducible_from_bound_topology() -> None:
    """The write-once builder deterministically reproduces every endpoint."""
    registry = load_prospective_endpoint_registry(_REGISTRY)
    compact = tuple(
        endpoint
        for endpoint in registry.endpoints
        if endpoint.lane == "compact"
    )
    incumbent_topology = {
        "prospective_compact": {
            "phase_four_pybdsf_decision": {
                "metric_decisions": [
                    {
                        "metric_id": endpoint.metric_family,
                        "reference_identifier": "released-pybdsf",
                        "stratum": endpoint.stratum,
                    }
                    for endpoint in compact
                ]
            },
            "aegean_binding_metric_decisions": [
                {
                    "metric_id": endpoint.metric_family,
                    "stratum": endpoint.stratum,
                }
                for endpoint in compact
                if "aegean" in endpoint.comparators
            ],
        }
    }
    rebuilt = build_prospective_endpoint_registry(
        source_registry=json.loads(
            _SOURCE_REGISTRY.read_text(encoding="utf-8")
        ),
        metric_registry=json.loads(
            _METRIC_REGISTRY.read_text(encoding="utf-8")
        ),
        incumbent_ledger=incumbent_topology,
        source_bindings=tuple(
            binding.model_dump(mode="json")
            for binding in registry.source_bindings
        ),
    )

    assert rebuilt == registry


def test_cross_finder_inapplicability_does_not_waive_hebog_retention() -> None:
    """Irregular-centroid offsets remain binding against the one incumbent."""
    registry, _ = _load()

    offset = next(
        endpoint
        for endpoint in registry.endpoints
        if endpoint.endpoint_id == "continuum--absolute-mean-offset-x--overall"
    )
    assert offset.comparators == ("incumbent-hebog",)
    assert offset.desirable_direction == "lower-is-better"
    assert offset.unit == "restoring-beam-fwhm"
    assert offset.practical_regression_margins == {"incumbent-hebog": 0.05}
    assert offset.cross_finder_applicability == (
        "not-applicable-irregular-segment-centroid-semantics"
    )

    objective = next(
        endpoint
        for endpoint in registry.endpoints
        if endpoint.endpoint_id == "continuum--position-median--overall"
    )
    assert objective.role == "longer-term-objective"
    assert objective.comparators == ()
    assert objective.absolute_policy == "report-not-compatibility-blocker"


def test_contract_freezes_whole_incumbent_and_paired_evidence() -> None:
    """Retention cannot become a synthetic best-per-endpoint envelope."""
    _, contract = _load()

    assert contract.status == "frozen-for-human-scientific-review"
    assert contract.active is False
    assert contract.incumbent.candidate_revision == (
        "85d580713664b962ae256a98b065849cf8eb9283"
    )
    assert contract.incumbent.source_tree_sha256 == (
        "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
    )
    assert contract.incumbent.configuration_sha256 == (
        "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
    )
    assert contract.incumbent.ledger.sha256 == (
        "e2ee663f4eade383518eabbafda5cd33bfe9808b4a9b37492a77337738b611db"
    )
    assert contract.incumbent.selection_rule == (
        "one-whole-closed-candidate-no-endpoint-envelope"
    )
    assert contract.incumbent.realization_evidence == (
        "exact-paired-reexecution-required-no-preserved-raw-incumbent-products"
    )
    assert contract.decision.combination_rule == (
        "intersection-union-every-coprimary-comparison"
    )
    assert contract.decision.underpowered_outcome == (
        "parity-or-retention-not-demonstrated"
    )
    assert contract.decision.planning_variance_role == (
        "design-and-assumption-audit-only-not-observed-data-gate"
    )
    assert contract.authorization.execution_authorized is False
    assert contract.authorization.replay_identity_freeze_authorized is False


def test_contract_preserves_history_and_checks_source_hashes() -> None:
    """Prospective policy cannot mutate or rescore any closed decision."""
    _, contract = _load()

    assert len(contract.historical_ledgers) == 9
    assert contract.historical_policy == (
        "immutable-original-gates-no-retrospective-rescoring"
    )
    assert contract.absolute_policy.numeric_science_targets == (
        "report-as-longer-term-objectives"
    )
    assert contract.absolute_policy.binding_safety_invariants == (
        "finite-measurements",
        "product-validity",
        "schema-and-provenance-integrity",
        "serial-and-existing-dask-determinism",
        "write-once-publication",
    )
    verify_prospective_contract_sources(contract, root=_ROOT)


def test_registry_and_contract_fail_closed_on_policy_drift(
    tmp_path: Path,
) -> None:
    """Omitted endpoints and synthetic incumbent selection fail loading."""
    registry_document = json.loads(_REGISTRY.read_text(encoding="utf-8"))
    registry_document["endpoints"] = registry_document["endpoints"][:-1]
    changed_registry = tmp_path / "registry.json"
    changed_registry.write_text(
        json.dumps(registry_document), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="endpoint counts differ"):
        load_prospective_endpoint_registry(changed_registry)

    registry = load_prospective_endpoint_registry(_REGISTRY)
    contract_document = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    contract_document["incumbent"]["selection_rule"] = (
        "best-historical-value-per-endpoint"
    )
    changed_contract = tmp_path / "contract.json"
    changed_contract.write_text(
        json.dumps(contract_document), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="whole closed candidate"):
        load_prospective_science_contract(
            changed_contract,
            endpoint_registry=registry,
        )

    contract_document = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    contract_document["decision"]["planning_variance_role"] = (
        "observed-data-pass-fail-gate"
    )
    changed_contract = tmp_path / "changed-decision.json"
    changed_contract.write_text(
        json.dumps(contract_document), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="planning_variance_role"):
        load_prospective_science_contract(
            changed_contract,
            endpoint_registry=registry,
        )


def test_contract_rejects_unsafe_bound_paths(tmp_path: Path) -> None:
    """Evidence bindings cannot escape the repository root."""
    registry = load_prospective_endpoint_registry(_REGISTRY)
    contract_document = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    contract_document["committed_source_bindings"][0]["path"] = (
        "../outside.json"
    )
    changed_contract = tmp_path / "unsafe-path.json"
    changed_contract.write_text(
        json.dumps(contract_document), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="repository-relative"):
        load_prospective_science_contract(
            changed_contract,
            endpoint_registry=registry,
        )
