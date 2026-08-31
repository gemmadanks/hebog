"""Prospective Phase 5 scientific smoke-lane tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hebog.validation.external_runners import file_sha256
from hebog.validation.prospective_science_contract import (
    ProspectiveEndpoint,
    ProspectiveEndpointCounts,
    ProspectiveEndpointRegistry,
)
from hebog.validation.prospective_science_smoke import (
    evaluate_prospective_science_smoke,
    select_prospective_smoke_inputs,
)

_ROOT = Path(__file__).parents[3]
_REQUEST = (
    _ROOT / "benchmark-results/phase-5/external-post-failure-comparison/"
    "campaign-request.json"
)
_POPULATION = (
    _ROOT
    / "config/contracts/phase-5-prospective-science-smoke-population.json"
)


def _registry() -> ProspectiveEndpointRegistry:
    endpoint = ProspectiveEndpoint(
        endpoint_id="continuum--reliability--overall",
        lane="continuum",
        metric_family="reliability",
        stratum="overall",
        role="binding",
        desirable_direction="higher-is-better",
        unit="fraction",
        population="accepted catalogue sources",
        statistic="rate",
        value_kind="scalar",
        comparators=("incumbent-hebog", "released-pybdsf"),
        practical_regression_margins={
            "incumbent-hebog": 0.02,
            "released-pybdsf": 0.02,
        },
        cross_finder_applicability="all-listed-comparators-binding",
        missing_output_outcome=(
            "candidate-fail-comparator-underpowered-global-fail"
        ),
        absolute_policy="report-not-compatibility-blocker",
    )
    # Construct without the full-registry cardinality validator for a focused
    # evaluator unit test. The frozen production registry has separate tests.
    return ProspectiveEndpointRegistry.model_construct(
        schema_version=1,
        registry_id="phase-5-prospective-science-endpoint-registry",
        status="frozen-before-candidate-results",
        source_bindings=(),
        counts=ProspectiveEndpointCounts(
            total_endpoints=1,
            compact_binding_endpoints=0,
            continuum_binding_endpoints=1,
            continuum_objective_endpoints=0,
            pybdsf_endpoints_per_reference=1,
            aegean_endpoints=0,
            incumbent_retention_endpoints=1,
            total_coprimary_comparisons=2,
        ),
        endpoints=(endpoint,),
    )


def _endpoint(reference_id: str, upper: float) -> SimpleNamespace:
    comparison = SimpleNamespace(
        reference_id=reference_id,
        status="success",
        positive_regression=0.005,
        upper_confidence_limit=upper,
        observed_paired_standard_deviation=0.03,
    )
    return SimpleNamespace(
        endpoint_id="continuum--reliability--overall",
        candidate_status="success",
        comparisons=(comparison,),
    )


def test_frozen_smoke_selection_is_reproducible_and_balanced() -> None:
    """The result-neutral rule resolves the exact same 128 inputs."""
    selected = select_prospective_smoke_inputs(
        _REQUEST,
        _POPULATION,
    )

    assert len(selected) == 128
    assert len({item for item in selected if "compact-blend" in item}) == 64
    continuum = [item for item in selected if "continuum" in item]
    assert len(continuum) == 64
    assert {
        dataset: sum(dataset in item for item in continuum)
        for dataset in (
            "continuum-1",
            "continuum-2",
            "continuum-3",
            "continuum-4",
        )
    } == {
        "continuum-1": 16,
        "continuum-2": 16,
        "continuum-3": 16,
        "continuum-4": 16,
    }


def test_smoke_passes_with_activation_identity_and_no_confirmed_loss() -> None:
    """Underpowered diagnostics may continue; failures may not."""
    record = evaluate_prospective_science_smoke(
        registry=_registry(),
        current_continuum=(_endpoint("released-pybdsf", 0.025),),
        incumbent_paired_continuum=(_endpoint("pinned-pybdsf-master", 0.015),),
        planning_deviation_by_family={"reliability": 0.08},
        compact_product_identity_equal=True,
        terminal_cycle_aggregate={
            "terminal_cycle_unseeded_persistent_accepted_count": 2
        },
    )

    assert record["status"] == "pass"
    assert record["promotion_evidence"] is False
    assert record["continuum_status_counts"] == {
        "pass": 1,
        "underpowered": 1,
    }


def test_smoke_fails_on_confirmed_regression_or_absent_activation() -> None:
    """Material regression and a dormant correction both stop a replay."""
    record = evaluate_prospective_science_smoke(
        registry=_registry(),
        current_continuum=(_endpoint("released-pybdsf", 0.03),),
        incumbent_paired_continuum=(
            SimpleNamespace(
                endpoint_id="continuum--reliability--overall",
                candidate_status="success",
                comparisons=(
                    SimpleNamespace(
                        reference_id="pinned-pybdsf-master",
                        status="success",
                        positive_regression=0.03,
                        upper_confidence_limit=0.04,
                        observed_paired_standard_deviation=0.03,
                    ),
                ),
            ),
        ),
        planning_deviation_by_family={"reliability": 0.08},
        compact_product_identity_equal=True,
        terminal_cycle_aggregate={
            "terminal_cycle_unseeded_persistent_accepted_count": 0
        },
    )

    assert record["status"] == "fail"
    assert record["terminal_failure_count"] == 1


@pytest.mark.parametrize(
    ("population_value", "message"),
    [
        ([], "population is malformed"),
        ({}, "selection is incomplete"),
    ],
)
def test_smoke_selector_rejects_malformed_population(
    tmp_path: Path, population_value: object, message: str
) -> None:
    """Malformed population metadata fails before any result selection."""
    population = tmp_path / "population.json"
    population.write_text(json.dumps(population_value), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        select_prospective_smoke_inputs(_REQUEST, population)


def test_smoke_selector_rejects_request_or_count_drift(tmp_path: Path) -> None:
    """Source bytes, sample sizes, and selected identities remain frozen."""
    population = json.loads(_POPULATION.read_text(encoding="utf-8"))
    population["source_request"]["sha256"] = "changed"
    changed_source = tmp_path / "changed-source.json"
    changed_source.write_text(json.dumps(population), encoding="utf-8")
    with pytest.raises(ValueError, match="source request changed"):
        select_prospective_smoke_inputs(_REQUEST, changed_source)

    population = json.loads(_POPULATION.read_text(encoding="utf-8"))
    population["selection"]["compact_count"] = 0
    changed_count = tmp_path / "changed-count.json"
    changed_count.write_text(json.dumps(population), encoding="utf-8")
    with pytest.raises(ValueError, match="selection count is invalid"):
        select_prospective_smoke_inputs(_REQUEST, changed_count)

    population["selection"]["compact_count"] = 64
    population["selection"]["selected_input_count"] = 127
    changed_set = tmp_path / "changed-set.json"
    changed_set.write_text(json.dumps(population), encoding="utf-8")
    with pytest.raises(ValueError, match="selected input set changed"):
        select_prospective_smoke_inputs(_REQUEST, changed_set)


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        (None, "source inputs are absent"),
        (["bad"], "source input is malformed"),
        ([{"lane": "continuum"}], "source identity is malformed"),
    ],
)
def test_smoke_selector_rejects_malformed_request_inputs(
    tmp_path: Path, inputs: object, message: str
) -> None:
    """Selection never guesses malformed request identities."""
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"inputs": inputs}), encoding="utf-8")
    population = json.loads(_POPULATION.read_text(encoding="utf-8"))
    population["source_request"]["sha256"] = file_sha256(request)
    population_path = tmp_path / "population.json"
    population_path.write_text(json.dumps(population), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        select_prospective_smoke_inputs(request, population_path)


def test_smoke_rejects_duplicated_or_missing_compiled_endpoints() -> None:
    """Compiled endpoint coverage is exact before decisions are attempted."""
    endpoint = _endpoint("released-pybdsf", 0.01)
    with pytest.raises(ValueError, match="endpoint is duplicated"):
        evaluate_prospective_science_smoke(
            registry=_registry(),
            current_continuum=(endpoint, endpoint),
            incumbent_paired_continuum=(
                _endpoint("pinned-pybdsf-master", 0.01),
            ),
            planning_deviation_by_family={"reliability": 0.08},
            compact_product_identity_equal=True,
            terminal_cycle_aggregate={
                "terminal_cycle_unseeded_persistent_accepted_count": 1
            },
        )
    with pytest.raises(ValueError, match="endpoint is absent"):
        evaluate_prospective_science_smoke(
            registry=_registry(),
            current_continuum=(),
            incumbent_paired_continuum=(),
            planning_deviation_by_family={"reliability": 0.08},
            compact_product_identity_equal=True,
            terminal_cycle_aggregate={
                "terminal_cycle_unseeded_persistent_accepted_count": 1
            },
        )


def test_smoke_rejects_malformed_or_duplicated_comparisons() -> None:
    """Reference comparisons must be tuple-shaped and uniquely identified."""
    malformed = SimpleNamespace(
        endpoint_id="continuum--reliability--overall",
        candidate_status="success",
        comparisons=[],
    )
    with pytest.raises(ValueError, match="comparisons are malformed"):
        evaluate_prospective_science_smoke(
            registry=_registry(),
            current_continuum=(malformed,),
            incumbent_paired_continuum=(malformed,),
            planning_deviation_by_family={"reliability": 0.08},
            compact_product_identity_equal=True,
            terminal_cycle_aggregate={
                "terminal_cycle_unseeded_persistent_accepted_count": 1
            },
        )
    comparison = _endpoint("released-pybdsf", 0.01)
    duplicated = SimpleNamespace(
        endpoint_id=comparison.endpoint_id,
        candidate_status="success",
        comparisons=(comparison.comparisons[0], comparison.comparisons[0]),
    )
    with pytest.raises(ValueError, match="comparison is duplicated"):
        evaluate_prospective_science_smoke(
            registry=_registry(),
            current_continuum=(duplicated,),
            incumbent_paired_continuum=(duplicated,),
            planning_deviation_by_family={"reliability": 0.08},
            compact_product_identity_equal=True,
            terminal_cycle_aggregate={
                "terminal_cycle_unseeded_persistent_accepted_count": 1
            },
        )
