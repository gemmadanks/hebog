"""Tests for the pre-results Phase 5 external scientific decision."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).parents[3]
_EVALUATOR = _ROOT / "scripts/validation/evaluate_phase5_external_decision.py"
_CONTRACT = _ROOT / "config/contracts/phase-5-external-evaluation.json"


@pytest.fixture(scope="module")
def evaluator() -> dict[str, Any]:
    """Load the decision script without invoking its command line."""
    return runpy.run_path(str(_EVALUATOR))


@pytest.fixture(scope="module")
def contract(evaluator: dict[str, Any]) -> dict[str, Any]:
    """Load and checksum-verify the immutable evaluator contract."""
    return evaluator["load_evaluation_contract"](_CONTRACT, _EVALUATOR)


def _comparison(  # noqa: PLR0913
    evaluator: dict[str, Any],
    reference_id: str,
    *,
    status: str = "success",
    reference_value: float = 0.31,
    positive_regression: float = -0.01,
    upper: float = 0.01,
    observed_standard_deviation: float = 0.1,
) -> Any:
    return evaluator["ReferenceComparisonEvidence"](
        reference_id=reference_id,
        status=status,
        reference_value=reference_value if status == "success" else None,
        positive_regression=positive_regression
        if status == "success"
        else None,
        upper_confidence_limit=upper if status == "success" else None,
        observed_paired_standard_deviation=(
            observed_standard_deviation if status == "success" else None
        ),
        reason=None if status == "success" else "reference output absent",
    )


def _position_evidence(  # noqa: PLR0913
    evaluator: dict[str, Any],
    *,
    population: str,
    value: float,
    absolute_decision_value: float | None = None,
    image_count: int = 600,
    reference_status: str = "success",
    observed_standard_deviation: float = 0.1,
) -> Any:
    comparisons = tuple(
        _comparison(
            evaluator,
            reference,
            status=reference_status,
            positive_regression=value - 0.31,
            observed_standard_deviation=observed_standard_deviation,
        )
        for reference in ("released-pybdsf", "pinned-pybdsf-master")
    )
    return evaluator["EndpointEvidence"](
        endpoint_id=f"position-p95:{population}:overall",
        lane="continuum",
        metric_family="position-p95",
        stratum="overall",
        position_population=population,
        image_count=image_count,
        candidate_status="success",
        candidate_value=value,
        absolute_decision_value=(
            value
            if absolute_decision_value is None
            else absolute_decision_value
        ),
        comparisons=comparisons,
    )


def test_position_gate_is_machine_explicit_by_science_population(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """Compact astrometry stays at 0.25 while segment location uses 0.50."""
    evaluate = evaluator["evaluate_endpoint"]
    policy = evaluator["endpoint_policy"]

    compact = evaluate(
        _position_evidence(
            evaluator,
            population="compact-component",
            value=0.24,
        ),
        policy(
            contract,
            lane="continuum",
            metric_family="position-p95",
            position_population="compact-component",
        ),
    )
    irregular = evaluate(
        _position_evidence(
            evaluator,
            population="irregular-segment",
            value=0.30,
        ),
        policy(
            contract,
            lane="continuum",
            metric_family="position-p95",
            position_population="irregular-segment",
        ),
    )

    assert compact.absolute_limit == pytest.approx(0.25)
    assert irregular.absolute_limit == pytest.approx(0.50)
    assert compact.status == "pass"
    assert irregular.status == "pass"


def test_irregular_radial_median_remains_report_only(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """The 0.10 axis-bias limit is not recast as a radial-median gate."""
    with pytest.raises(ValueError, match="report-only"):
        evaluator["endpoint_policy"](
            contract,
            lane="continuum",
            metric_family="position-median",
            position_population="irregular-segment",
        )


def test_irregular_axis_bias_is_absolute_only(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """Signed-axis bias has its own confidence bound and no paired proxy."""
    policy = evaluator["endpoint_policy"](
        contract,
        lane="continuum",
        metric_family="absolute-mean-offset-x",
        position_population="irregular-segment",
    )
    evidence = evaluator["EndpointEvidence"](
        endpoint_id="continuum--absolute-mean-offset-x--overall",
        lane="continuum",
        metric_family="absolute-mean-offset-x",
        stratum="overall",
        position_population="irregular-segment",
        image_count=600,
        candidate_status="success",
        candidate_value=0.02,
        absolute_decision_value=0.04,
        comparisons=(),
    )

    decision = evaluator["evaluate_endpoint"](evidence, policy)

    assert policy.binding_references == ()
    assert policy.absolute_limit == pytest.approx(0.10)
    assert decision.status == "pass"


def test_registry_expansion_matches_compiler_binding_count(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """The decision layer independently expands all 143 binding identities."""
    registry_identity = contract["endpoint_registry"]
    registry = evaluator["_json_object"](_ROOT / registry_identity["path"])

    identifiers = evaluator["_expected_continuum_endpoint_ids"](registry)

    assert len(identifiers) == 143
    assert len(set(identifiers)) == 143
    assert "continuum--absolute-mean-offset-x--overall" in identifiers
    assert "continuum--position-median--overall" not in identifiers


def test_compiled_analysis_identity_binds_protocol_and_authorization_state(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """Correct endpoint rows cannot be detached from the approved campaign."""
    registry_identity = contract["endpoint_registry"]
    registry = evaluator["_json_object"](_ROOT / registry_identity["path"])
    expected = evaluator["_expected_continuum_endpoint_ids"](registry)
    compiler = contract["analysis_compiler"]
    analysis: dict[str, Any] = {
        "schema_version": 1,
        "analysis_id": "phase-5-external-terminal-science",
        "status": "compiled-terminal-science",
        "compiler_sha256": compiler["sha256"],
        "endpoint_registry_sha256": registry_identity["sha256"],
        "protocol_sha256": contract["protocol_sha256"],
        "execution_decision_sha256": registry["execution_decision_sha256"],
        "expected_continuum_endpoint_ids": list(expected),
        "continuum_diagnostics": [{} for _ in range(15)],
        "compact": {
            "source_manifest_role": "regression",
            "phase_four_interval_engine_mode": "qualification-bca",
        },
        "scientific_outcomes_before_runtime": True,
        "step_three_authorized": False,
        "optimization_authorized": False,
        "qualification_opened": False,
    }

    assert (
        evaluator["_validate_compiled_analysis_identity"](
            analysis, contract, registry
        )
        == expected
    )

    changed: dict[str, Any] = {
        **analysis,
        "protocol_sha256": "0" * 64,
    }
    with pytest.raises(ValueError, match="analysis identity"):
        evaluator["_validate_compiled_analysis_identity"](
            changed, contract, registry
        )


def test_absolute_failure_cannot_be_compensated(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """Good paired comparisons cannot excuse an irregular absolute failure."""
    evidence = _position_evidence(
        evaluator,
        population="irregular-segment",
        value=0.51,
    )
    decision = evaluator["evaluate_endpoint"](
        evidence,
        evaluator["endpoint_policy"](
            contract,
            lane="continuum",
            metric_family="position-p95",
            position_population="irregular-segment",
        ),
    )

    assert decision.absolute_passed is False
    assert decision.status == "fail"
    assert "absolute" in decision.reason


def test_higher_is_better_metric_still_requires_every_paired_gate(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """Completeness uses its lower absolute bound and both references."""
    policy = evaluator["endpoint_policy"](
        contract,
        lane="continuum",
        metric_family="completeness",
        position_population="not-applicable",
    )
    evidence = evaluator["EndpointEvidence"](
        endpoint_id="completeness:overall",
        lane="continuum",
        metric_family="completeness",
        stratum="overall",
        position_population="not-applicable",
        image_count=600,
        candidate_status="success",
        candidate_value=0.95,
        absolute_decision_value=0.95,
        comparisons=(
            _comparison(
                evaluator,
                "released-pybdsf",
                reference_value=0.96,
                positive_regression=0.01,
                upper=0.021,
                observed_standard_deviation=0.05,
            ),
            _comparison(
                evaluator,
                "pinned-pybdsf-master",
                reference_value=0.96,
                positive_regression=0.01,
                observed_standard_deviation=0.05,
            ),
        ),
    )

    decision = evaluator["evaluate_endpoint"](evidence, policy)

    assert decision.absolute_relation == "at-least"
    assert decision.absolute_passed is True
    assert decision.status == "fail"
    assert decision.comparisons[0].status == "fail"


def test_unavailable_reference_fails_closed(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """A missing binding reference is indeterminate, never silently dropped."""
    evidence = _position_evidence(
        evaluator,
        population="irregular-segment",
        value=0.30,
        reference_status="unavailable",
    )
    decision = evaluator["evaluate_endpoint"](
        evidence,
        evaluator["endpoint_policy"](
            contract,
            lane="continuum",
            metric_family="position-p95",
            position_population="irregular-segment",
        ),
    )

    assert decision.status == "indeterminate"
    assert "unavailable" in decision.reason


def test_candidate_and_reference_sets_cannot_be_silently_reduced(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """Candidate failure and a missing named reference remain indeterminate."""
    policy = evaluator["endpoint_policy"](
        contract,
        lane="continuum",
        metric_family="position-p95",
        position_population="irregular-segment",
    )
    candidate_failed = _position_evidence(
        evaluator,
        population="irregular-segment",
        value=0.30,
    )
    candidate_failed = evaluator["EndpointEvidence"](
        endpoint_id=candidate_failed.endpoint_id,
        lane=candidate_failed.lane,
        metric_family=candidate_failed.metric_family,
        stratum=candidate_failed.stratum,
        position_population=candidate_failed.position_population,
        image_count=candidate_failed.image_count,
        candidate_status="failed",
        candidate_value=None,
        absolute_decision_value=None,
        comparisons=candidate_failed.comparisons,
        reason="candidate failed",
    )
    missing_reference = _position_evidence(
        evaluator,
        population="irregular-segment",
        value=0.30,
    )
    missing_reference = evaluator["EndpointEvidence"](
        endpoint_id=missing_reference.endpoint_id,
        lane=missing_reference.lane,
        metric_family=missing_reference.metric_family,
        stratum=missing_reference.stratum,
        position_population=missing_reference.position_population,
        image_count=missing_reference.image_count,
        candidate_status="success",
        candidate_value=missing_reference.candidate_value,
        absolute_decision_value=(missing_reference.absolute_decision_value),
        comparisons=missing_reference.comparisons[:1],
    )

    assert (
        evaluator["evaluate_endpoint"](candidate_failed, policy).status
        == "indeterminate"
    )
    missing = evaluator["evaluate_endpoint"](missing_reference, policy)
    assert missing.status == "indeterminate"
    assert "reference population" in missing.reason


def test_nonfinite_evidence_and_incomplete_raw_counts_fail_closed(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """NaN statistics and a lost binding run cannot reach a pass."""
    policy = evaluator["endpoint_policy"](
        contract,
        lane="continuum",
        metric_family="position-p95",
        position_population="irregular-segment",
    )
    candidate_nan = _position_evidence(
        evaluator,
        population="irregular-segment",
        value=float("nan"),
    )
    reference_nan = _position_evidence(
        evaluator,
        population="irregular-segment",
        value=0.30,
    )
    reference_nan = evaluator["EndpointEvidence"](
        endpoint_id=reference_nan.endpoint_id,
        lane=reference_nan.lane,
        metric_family=reference_nan.metric_family,
        stratum=reference_nan.stratum,
        position_population=reference_nan.position_population,
        image_count=reference_nan.image_count,
        candidate_status=reference_nan.candidate_status,
        candidate_value=reference_nan.candidate_value,
        absolute_decision_value=(reference_nan.absolute_decision_value),
        comparisons=(
            _comparison(
                evaluator,
                "released-pybdsf",
                upper=float("nan"),
            ),
            reference_nan.comparisons[1],
        ),
    )

    assert (
        evaluator["evaluate_endpoint"](candidate_nan, policy).status
        == "indeterminate"
    )
    reference_decision = evaluator["evaluate_endpoint"](reference_nan, policy)
    assert reference_decision.status == "indeterminate"
    assert reference_decision.comparisons[0].status == "indeterminate"

    incomplete = evaluator["CampaignPopulationAudit"](
        image_count=1400,
        terminal_run_count=7000,
        binding_run_count=5000,
        successful_binding_run_count=4999,
        failed_binding_run_count=1,
        unavailable_binding_run_count=0,
        unexpected_run_count=0,
    )
    campaign = evaluator["evaluate_campaign"](
        incomplete,
        (reference_decision,),
        expected_endpoint_ids=(reference_decision.endpoint_id,),
        contract=contract,
    )
    assert campaign.status == "indeterminate"
    assert "raw campaign population" in campaign.reason


def test_compiler_cannot_invert_the_paired_regression_direction(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """The candidate/reference values determine the point-regression sign."""
    policy = evaluator["endpoint_policy"](
        contract,
        lane="continuum",
        metric_family="position-p95",
        position_population="irregular-segment",
    )
    evidence = _position_evidence(
        evaluator,
        population="irregular-segment",
        value=0.30,
    )
    evidence = evaluator["EndpointEvidence"](
        endpoint_id=evidence.endpoint_id,
        lane=evidence.lane,
        metric_family=evidence.metric_family,
        stratum=evidence.stratum,
        position_population=evidence.position_population,
        image_count=evidence.image_count,
        candidate_status=evidence.candidate_status,
        candidate_value=evidence.candidate_value,
        absolute_decision_value=evidence.absolute_decision_value,
        comparisons=(
            _comparison(
                evaluator,
                "released-pybdsf",
                positive_regression=0.01,
            ),
            evidence.comparisons[1],
        ),
    )

    decision = evaluator["evaluate_endpoint"](evidence, policy)

    assert decision.status == "indeterminate"
    assert "direction" in decision.comparisons[0].reason


def test_irregular_absolute_gate_uses_its_upper_confidence_bound(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """A passing radial-p95 point cannot hide an upper bound above 0.50."""
    policy = evaluator["endpoint_policy"](
        contract,
        lane="continuum",
        metric_family="position-p95",
        position_population="irregular-segment",
    )
    evidence = _position_evidence(
        evaluator,
        population="irregular-segment",
        value=0.49,
        absolute_decision_value=0.51,
    )

    decision = evaluator["evaluate_endpoint"](evidence, policy)

    assert policy.absolute_decision_statistic == (
        "one-sided-95-percent-upper-confidence-limit"
    )
    assert decision.candidate_value == pytest.approx(0.49)
    assert decision.absolute_decision_value == pytest.approx(0.51)
    assert decision.status == "fail"


def test_excess_paired_variance_is_underpowered(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """Observed variance above its frozen planning bound cannot pass."""
    evidence = _position_evidence(
        evaluator,
        population="irregular-segment",
        value=0.30,
        observed_standard_deviation=0.251,
    )
    decision = evaluator["evaluate_endpoint"](
        evidence,
        evaluator["endpoint_policy"](
            contract,
            lane="continuum",
            metric_family="position-p95",
            position_population="irregular-segment",
        ),
    )

    assert decision.status == "underpowered"
    assert "variance" in decision.reason


def test_incomplete_population_fails_closed(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """All 600 Continuum images remain in every binding denominator."""
    evidence = _position_evidence(
        evaluator,
        population="irregular-segment",
        value=0.30,
        image_count=599,
    )
    decision = evaluator["evaluate_endpoint"](
        evidence,
        evaluator["endpoint_policy"](
            contract,
            lane="continuum",
            metric_family="position-p95",
            position_population="irregular-segment",
        ),
    )

    assert decision.status == "indeterminate"
    assert "population" in decision.reason


def test_campaign_requires_exact_terminal_and_endpoint_populations(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """Passing endpoints do not excuse missing raw or endpoint rows."""
    policy = evaluator["endpoint_policy"](
        contract,
        lane="continuum",
        metric_family="position-p95",
        position_population="irregular-segment",
    )
    endpoint = evaluator["evaluate_endpoint"](
        _position_evidence(
            evaluator,
            population="irregular-segment",
            value=0.30,
        ),
        policy,
    )
    complete = evaluator["CampaignPopulationAudit"](
        image_count=1400,
        terminal_run_count=7000,
        binding_run_count=5000,
        successful_binding_run_count=5000,
        failed_binding_run_count=0,
        unavailable_binding_run_count=0,
        unexpected_run_count=0,
    )
    decide = evaluator["evaluate_campaign"]

    passed = decide(
        complete,
        (endpoint,),
        expected_endpoint_ids=(endpoint.endpoint_id,),
        contract=contract,
    )
    missing = decide(
        complete,
        (),
        expected_endpoint_ids=(endpoint.endpoint_id,),
        contract=contract,
    )
    duplicate_registry = decide(
        complete,
        (endpoint,),
        expected_endpoint_ids=(endpoint.endpoint_id, endpoint.endpoint_id),
        contract=contract,
    )

    assert passed.status == "pass"
    assert missing.status == "indeterminate"
    assert "endpoint population" in missing.reason
    assert duplicate_registry.status == "indeterminate"


def test_compact_decision_recomputes_exact_selected_aegean_rows(
    evaluator: dict[str, Any], contract: dict[str, Any]
) -> None:
    """A detached or altered Aegean subset cannot pass the conjunction."""
    registry_identity = contract["endpoint_registry"]
    registry: dict[str, Any] = json.loads(
        (_ROOT / registry_identity["path"]).read_text(encoding="utf-8")
    )
    applicable: list[str] = registry["compact"]["aegean_applicable_metric_ids"]
    applicable_keys = [
        (applicable[index % len(applicable)], f"stratum-{index:03d}")
        for index in range(143)
    ]
    other_keys = [
        ("deconvolution-classification-availability", f"other-{index:03d}")
        for index in range(82)
    ]
    all_keys = [*applicable_keys, *other_keys]

    def rows(reference: str) -> list[dict[str, str]]:
        return [
            {
                "reference_identifier": reference,
                "metric_id": metric_id,
                "stratum": stratum,
                "status": "pass",
            }
            for metric_id, stratum in all_keys
        ]

    selected = rows("aegean")[:143]
    compact: dict[str, Any] = {
        "status": "pass",
        "phase_four_pybdsf_decision": {
            "passed": True,
            "metric_decisions": [
                *rows("released-pybdsf"),
                *rows("pinned-pybdsf-master"),
            ],
        },
        "phase_four_aegean_decision": {
            "metric_decisions": selected,
            "implementation_outcomes": [
                {
                    "implementation_identifier": "aegean",
                    "failed_seeds": [],
                }
            ],
        },
        "aegean_binding_metric_decisions": selected,
    }

    assert evaluator["_compact_decision_status"](compact, registry) == "pass"

    detached: dict[str, Any] = {
        **compact,
        "aegean_binding_metric_decisions": [*selected],
    }
    detached["aegean_binding_metric_decisions"][0] = {
        **selected[0],
        "status": "fail",
    }
    assert (
        evaluator["_compact_decision_status"](detached, registry)
        == "indeterminate"
    )


def test_contract_refuses_evaluator_or_upstream_drift(
    evaluator: dict[str, Any], tmp_path: Path
) -> None:
    """The rules are bound to their code and frozen scientific inputs."""
    document = _CONTRACT.read_text(encoding="utf-8")
    changed = tmp_path / "contract.json"
    changed.write_text(
        document.replace(
            '"phase_five_scientific_gates_sha256": "',
            '"phase_five_scientific_gates_sha256": "0',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="scientific gate checksum"):
        evaluator["load_evaluation_contract"](changed, _EVALUATOR)


def test_cli_refuses_analysis_not_emitted_by_frozen_compiler(
    evaluator: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The decision CLI cannot ingest an unreviewed hand-built summary."""
    analysis = tmp_path / "analysis.json"
    analysis.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "decision.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(_EVALUATOR),
            "--contract",
            str(_CONTRACT),
            "--analysis",
            str(analysis),
            "--output",
            str(output),
        ],
    )

    with pytest.raises(ValueError, match="compiler checksum differs"):
        evaluator["main"]()

    assert not output.exists()
    output.write_text("reserved\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        evaluator["main"]()
