"""Tests for the frozen Phase 4 one-look decision evaluator."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
    dataset_by_identifier,
)
from hebog.validation.comparison import (
    BinomialConfidenceInterval,
    NumericConfidenceInterval,
    UncertaintyCalibrationReport,
    UncertaintyMetric,
)
from hebog.validation.contracts import (
    PairedNoninferiorityContract,
    PhaseFourScientificGates,
    load_paired_noninferiority_contract,
    load_phase_four_scientific_gates,
)
from hebog.validation.datasets import (
    DatasetRecord,
    DatasetRole,
    iter_dataset_recipes,
)
from hebog.validation.evidence import (
    AssociationPairDiagnostic,
    CampaignFailure,
    CampaignImplementationIdentity,
    CampaignRealizationDiagnostic,
    CatastrophicMetricDiagnostic,
    DatasetIdentity,
    EvidenceStatus,
    NormalizedResidualDiagnostic,
    PhaseFourEndpointDecision,
    PhaseFourEnvelopeDecision,
    PhaseFourGateDecision,
    PhaseFourImplementationOutcome,
    PhaseFourQualificationDecision,
    ScientificCampaignEvidence,
    SoftwareIdentity,
    SourcePairDiagnostic,
    WorkloadClass,
    load_evidence,
    write_evidence,
)
from hebog.validation.phase_four_decision import (
    EndpointStatistic,
    distribution_gate_decisions,
    evaluate_phase_four_qualification,
    paired_bca_upper_limits,
    paired_endpoint_decisions,
)

_ROOT = Path(__file__).parents[3]
_SHA256 = "a" * 64


def _protocol() -> PairedNoninferiorityContract:
    """Load the reviewed protocol used by the final evaluator."""
    return load_paired_noninferiority_contract(
        _ROOT / "config/contracts/phase-4-paired-noninferiority.json"
    )


def _mean_statistic(values: np.ndarray) -> EndpointStatistic:
    """Return a vectorized one-endpoint statistic over sampled indices."""

    def statistic(sampled_indices: np.ndarray, axis: int = -1) -> np.ndarray:
        selected = values[np.asarray(sampled_indices, dtype=np.int64)]
        means = np.mean(selected, axis=axis)
        return np.asarray(means)[np.newaxis, ...]

    return statistic


def test_paired_bca_interval_returns_a_finite_one_sided_upper_limit() -> None:
    """The maintained evaluator uses the reviewed SciPy BCa construction."""
    values = np.asarray((-0.04, -0.02, -0.01, 0.01, 0.02, 0.03))

    point, upper = paired_bca_upper_limits(
        _mean_statistic(values),
        realization_count=len(values),
        resampling=_protocol().resampling,
    )

    assert point.shape == (1,)
    assert upper.shape == (1,)
    assert np.isfinite(upper[0])
    assert upper[0] >= point[0]


def test_paired_bca_interval_uses_an_exact_finite_point_mass() -> None:
    """Exact equality has the reviewed zero-width confidence interval."""
    values = np.zeros(6, dtype=np.float64)

    _, upper = paired_bca_upper_limits(
        _mean_statistic(values),
        realization_count=len(values),
        resampling=_protocol().resampling,
    )

    assert upper[0] == 0.0


@pytest.mark.parametrize(
    ("exceptional_value", "complete_distribution"),
    ((1e-15, True), (np.nan, True), (0.0, False)),
    ids=(
        "near-point-mass",
        "non-finite-distribution",
        "incomplete-distribution",
    ),
)
def test_paired_bca_interval_rejects_a_nonexact_distribution(
    monkeypatch: pytest.MonkeyPatch,
    exceptional_value: float,
    complete_distribution: bool,
) -> None:
    """An undefined nonexact BCa bound continues to fail closed."""

    def fake_bootstrap(*args: object, **kwargs: object) -> SimpleNamespace:
        del args, kwargs
        resamples = _protocol().resampling.resamples
        distribution = np.zeros(
            resamples if complete_distribution else resamples - 1,
            dtype=np.float64,
        )
        distribution[-1] = exceptional_value
        return SimpleNamespace(
            confidence_interval=SimpleNamespace(
                low=np.asarray([np.nan]),
                high=np.asarray([np.nan]),
            ),
            bootstrap_distribution=distribution[np.newaxis, :],
        )

    monkeypatch.setattr(
        "hebog.validation.phase_four_decision.bootstrap",
        fake_bootstrap,
    )
    values = np.zeros(6, dtype=np.float64)

    _, upper = paired_bca_upper_limits(
        _mean_statistic(values),
        realization_count=len(values),
        resampling=_protocol().resampling,
    )

    assert not np.isfinite(upper[0])


def _matched_source(
    truth_identifier: str,
    *,
    deconvolved_axis: float | None,
) -> SourcePairDiagnostic:
    """Return a source row deliberately lacking both orientation fields."""
    return SourcePairDiagnostic(
        decision="matched",
        truth_identifier=truth_identifier,
        candidate_identifier=f"candidate-{truth_identifier}",
        truth_strata=("snr-10",),
        candidate_deconvolution_status=(
            "resolved" if deconvolved_axis is not None else "unresolved"
        ),
        classification_agrees=True,
        separation_beam_fwhm=0.01,
        peak_flux_fractional_difference=0.01,
        integrated_flux_fractional_difference=0.01,
        maximum_absolute_fitted_axis_fractional_difference=0.02,
        maximum_absolute_deconvolved_axis_fractional_difference=(
            deconvolved_axis
        ),
        catastrophic=CatastrophicMetricDiagnostic(
            position=False,
            peak_flux=False,
            integrated_flux=False,
            fitted_axis=False,
            deconvolved_axis=False,
        ),
        gated_catastrophic=False,
    )


def test_absolute_shape_gates_fail_closed_without_position_angles() -> None:
    """Old campaign rows cannot silently pass the frozen orientation gates."""
    dataset = dataset_by_identifier(
        _ROOT / "config/datasets/phase-4-final-qualification.json",
        "phase4-final-paired-qualification-512",
    )
    gates = load_phase_four_scientific_gates(
        _ROOT / "config/contracts/phase-4-scientific-gates.json"
    )
    realization = SimpleNamespace(
        source_pairs=(
            _matched_source("source-00001", deconvolved_axis=None),
            _matched_source("source-00009", deconvolved_axis=0.03),
        )
    )

    decisions = distribution_gate_decisions(
        (realization,),  # type: ignore[arg-type]
        dataset,
        gates.heldout_qualification,
    )
    by_identifier = {item.gate_id: item for item in decisions}

    assert by_identifier["median-fitted-position-angle"].status == (
        "indeterminate"
    )
    assert by_identifier["median-deconvolved-position-angle"].status == (
        "indeterminate"
    )
    assert by_identifier["percentile-95-fitted-position-angle"].role == (
        "report-only"
    )


def _passing_decision() -> PhaseFourQualificationDecision:
    """Return the smallest internally consistent one-look decision."""
    return PhaseFourQualificationDecision(
        schema_version=1,
        evidence_type="phase-4-qualification-decision",
        run_id="campaign-decision",
        captured_at=datetime(2026, 8, 4, tzinfo=UTC),
        status=EvidenceStatus.EXPLORATORY,
        dataset=DatasetIdentity(
            identifier="phase4-final",
            role=DatasetRole.QUALIFICATION,
            content_sha256=_SHA256,
            shape_yx=(512, 512),
            workload_class=WorkloadClass.NORMAL,
        ),
        configuration_sha256=_SHA256,
        source_campaign_run_id="campaign",
        source_campaign_sha256=_SHA256,
        comparison_protocol_sha256=_SHA256,
        scientific_gates_sha256=_SHA256,
        candidate_identifier="hebog",
        primary_reference_identifier="pybdsf-release",
        implementation_outcomes=(
            PhaseFourImplementationOutcome(
                implementation_identifier="hebog",
                policy="qualification-fails",
            ),
            PhaseFourImplementationOutcome(
                implementation_identifier="pybdsf-release",
                policy="qualification-fails",
            ),
        ),
        paired_endpoints=(
            PhaseFourEndpointDecision(
                endpoint_id="completeness",
                candidate_value=1.0,
                reference_value=1.0,
                positive_regression=0.0,
                practical_regression_margin=0.005,
                upper_confidence_limit=0.001,
                confidence_level=0.95,
                resamples=50_000,
                status="pass",
            ),
        ),
        absolute_gates=(
            PhaseFourGateDecision(
                gate_id="completeness",
                value=1.0,
                comparator="minimum",
                minimum=0.99,
                eligible_count=19_800,
                status="pass",
            ),
        ),
        stronger_hebog_envelopes=(
            PhaseFourEnvelopeDecision(
                envelope_id="complete-group-recovery",
                absolute_gate_ids=("completeness",),
                status="pass",
            ),
        ),
        passed=True,
    )


def test_one_look_decision_round_trips_as_strict_evidence(
    tmp_path: Path,
) -> None:
    """The final result has a loadable immutable machine-readable schema."""
    decision = _passing_decision()
    path = tmp_path / "decision.json"

    write_evidence(path, decision)

    assert load_evidence(path) == decision


def test_required_implementation_failure_forces_the_decision_to_fail() -> None:
    """A failed Hebog seed cannot be silently removed from the denominator."""
    document = _passing_decision().model_dump(mode="json")
    document["implementation_outcomes"][0]["failed_seeds"] = [2026080401]
    document["passed"] = False
    document["failure_reasons"] = ["required-implementation-failed:hebog"]

    decision = PhaseFourQualificationDecision.model_validate(document)

    assert decision.passed is False
    assert decision.implementation_outcomes[0].failed_seeds == (2026080401,)


def test_absolute_gate_failure_forces_the_decision_to_fail() -> None:
    """A co-primary absolute gate cannot be offset by other passing results."""
    document = _passing_decision().model_dump(mode="json")
    document["absolute_gates"][0]["value"] = 0.98
    document["absolute_gates"][0]["status"] = "fail"
    document["passed"] = False
    document["failure_reasons"] = ["absolute-gate-fail:completeness"]

    decision = PhaseFourQualificationDecision.model_validate(document)

    assert decision.passed is False
    assert decision.absolute_gates[0].status == "fail"


def test_report_only_tail_does_not_change_the_one_look_decision() -> None:
    """Reported individual-source tails remain outside the frozen gate set."""
    document = _passing_decision().model_dump(mode="json")
    document["absolute_gates"].append(
        {
            "gate_id": "percentile-95-position",
            "value": 0.2,
            "comparator": "maximum",
            "minimum": None,
            "maximum": 0.1,
            "interval_lower": None,
            "interval_upper": None,
            "eligible_count": 19_800,
            "role": "report-only",
            "status": "fail",
            "reason": None,
        }
    )

    decision = PhaseFourQualificationDecision.model_validate(document)

    assert decision.passed is True


def _software(name: str) -> SoftwareIdentity:
    """Return a fixed synthetic implementation identity."""
    return SoftwareIdentity(
        name=name,
        version="1.0.0",
        commit_sha="b" * 40,
        dependency_inventory_sha256="c" * 64,
    )


def _successful_realization(
    implementation_identifier: str,
    seed: int,
    dataset: DatasetRecord,
) -> CampaignRealizationDiagnostic:
    """Build a complete, scientifically passing synthetic realization."""
    truth_groups = dataset.association_truth_groups
    clear_indices = {
        index
        for stratum in dataset.classification_strata
        if stratum.identifier == "shape-clear-resolved"
        for index in stratum.source_indices
    }
    clear_identifiers = {
        group.identifier
        for group in truth_groups
        if set(group.source_indices).issubset(clear_indices)
    }
    associations = tuple(
        AssociationPairDiagnostic(
            decision="matched",
            truth_group_identifier=group.identifier,
            candidate_identifier=f"candidate-{group.identifier}",
            resolution_class=group.resolution_class,
            truth_strata=(group.resolution_class,),
            separation_beam_fwhm=0.01,
            integrated_flux_fractional_difference=0.01,
        )
        for group in truth_groups
    )
    sources = tuple(
        SourcePairDiagnostic(
            decision="matched",
            truth_identifier=group.identifier,
            candidate_identifier=f"candidate-{group.identifier}",
            truth_strata=("snr-10",),
            candidate_deconvolution_status=(
                "resolved"
                if group.identifier in clear_identifiers
                else "unresolved"
            ),
            candidate_quality_flags=(
                ()
                if group.identifier in clear_identifiers
                else ("unresolved",)
            ),
            classification_agrees=True,
            separation_beam_fwhm=0.01,
            peak_flux_fractional_difference=0.01,
            integrated_flux_fractional_difference=0.01,
            maximum_absolute_fitted_axis_fractional_difference=0.02,
            maximum_absolute_deconvolved_axis_fractional_difference=(
                0.03 if group.identifier in clear_identifiers else None
            ),
            fitted_position_angle_difference_degrees=1.0,
            deconvolved_position_angle_difference_degrees=(
                1.0 if group.identifier in clear_identifiers else None
            ),
            catastrophic=CatastrophicMetricDiagnostic(
                position=False,
                peak_flux=False,
                integrated_flux=False,
                fitted_axis=False,
                deconvolved_axis=False,
            ),
            gated_catastrophic=False,
            normalized_residuals=(
                NormalizedResidualDiagnostic(
                    metric="declination",
                    value=-0.5,
                ),
                NormalizedResidualDiagnostic(
                    metric="integrated-flux",
                    value=0.5,
                ),
                NormalizedResidualDiagnostic(
                    metric="peak-flux",
                    value=-0.5,
                ),
                NormalizedResidualDiagnostic(
                    metric="right-ascension",
                    value=0.5,
                ),
            ),
        )
        for group in truth_groups
        if group.resolution_class == "individually-resolvable"
    )
    return CampaignRealizationDiagnostic(
        implementation_identifier=implementation_identifier,
        seed=seed,
        status="success",
        candidate_count=len(associations),
        association_pairs=associations,
        source_pairs=sources,
    )


def _synthetic_campaign_inputs() -> tuple[
    ScientificCampaignEvidence,
    DatasetRecord,
    PairedNoninferiorityContract,
    PhaseFourScientificGates,
    str,
]:
    """Return a two-image qualification campaign without opening its images."""
    dataset = dataset_by_identifier(
        _ROOT / "config/datasets/phase-4-final-qualification.json",
        "phase4-final-paired-qualification-512",
    ).model_copy(update={"noise_realization_seeds": (2026110002, 2026110003)})
    protocol = _protocol().model_copy(update={"realization_count": 3})
    loaded_gates = load_phase_four_scientific_gates(
        _ROOT / "config/contracts/phase-4-scientific-gates.json"
    )
    gates = loaded_gates.model_copy(
        update={
            "uncertainty": loaded_gates.uncertainty.model_copy(
                update={"minimum_samples_per_stratum": 1}
            )
        }
    )
    configuration_sha256 = "d" * 64
    implementations = (
        CampaignImplementationIdentity(
            identifier="hebog",
            role="candidate",
            execution_configuration_sha256="e" * 64,
            software=_software("hebog"),
        ),
        CampaignImplementationIdentity(
            identifier="pybdsf-release",
            role="reference",
            execution_configuration_sha256="f" * 64,
            software=_software("pybdsf"),
        ),
        CampaignImplementationIdentity(
            identifier="pybdsf-master",
            role="reference",
            execution_configuration_sha256="1" * 64,
            software=_software("pybdsf"),
        ),
    )
    realization_seeds = tuple(
        recipe.seed for recipe in iter_dataset_recipes(dataset)
    )
    realizations = tuple(
        _successful_realization(implementation.identifier, seed, dataset)
        for seed in realization_seeds
        for implementation in implementations
    )
    campaign = ScientificCampaignEvidence(
        schema_version=1,
        evidence_type="scientific-campaign",
        run_id="synthetic-final-campaign",
        captured_at=datetime(2026, 8, 4, tzinfo=UTC),
        status=EvidenceStatus.EXPLORATORY,
        dataset=campaign_dataset_identity(dataset),
        configuration_sha256=configuration_sha256,
        comparison_protocol_sha256=canonical_sha256(
            protocol.model_dump(mode="json")
        ),
        implementations=implementations,
        realizations=realizations,
    )
    return campaign, dataset, protocol, gates, configuration_sha256


def _passing_uncertainty_report(
    metric: UncertaintyMetric,
    samples: Any,
    *,
    eligible_count: int,
    **_: object,
) -> UncertaintyCalibrationReport:
    """Return a cheap calibrated report for evaluator orchestration tests."""
    sample_count = len(samples)
    return UncertaintyCalibrationReport(
        metric=metric,
        eligible_count=eligible_count,
        sample_count=sample_count,
        availability_fraction=sample_count / eligible_count,
        within_one_sigma_count=sample_count,
        coverage_fraction=0.68,
        mean_normalized_residual=0.0,
        sample_standard_deviation=1.0,
        coverage_confidence_interval=BinomialConfidenceInterval(
            confidence_level=0.95,
            lower=0.65,
            upper=0.72,
        ),
        mean_confidence_interval=NumericConfidenceInterval(
            confidence_level=0.95,
            lower=-0.05,
            upper=0.05,
        ),
        dispersion_confidence_interval=NumericConfidenceInterval(
            confidence_level=0.95,
            lower=0.9,
            upper=1.1,
        ),
    )


def test_complete_one_look_evaluator_applies_every_decision_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One call combines every reviewed decision family."""
    campaign, dataset, protocol, gates, configuration = (
        _synthetic_campaign_inputs()
    )

    def interval_stub(
        statistic: EndpointStatistic,
        *,
        realization_count: int,
        resampling: object,
    ) -> tuple[np.ndarray, np.ndarray]:
        del resampling
        point = statistic(np.arange(realization_count, dtype=np.int64))
        return point, np.zeros_like(point)

    monkeypatch.setattr(
        "hebog.validation.phase_four_decision.paired_bca_upper_limits",
        interval_stub,
    )
    monkeypatch.setattr(
        "hebog.validation.phase_four_decision.uncertainty_calibration_report",
        _passing_uncertainty_report,
    )

    decision = evaluate_phase_four_qualification(
        campaign,
        dataset,
        protocol,
        gates,
        scientific_contract_set_sha256=configuration,
        captured_at=datetime(2026, 8, 4, tzinfo=UTC),
    )

    assert decision.passed is True
    assert len(decision.paired_endpoints) == 20
    assert len(decision.secondary_paired_endpoints) == 20
    assert all(item.status == "pass" for item in decision.paired_endpoints)
    assert all(
        item.status == "pass"
        for item in decision.absolute_gates
        if item.role == "gate"
    )
    assert all(
        item.status == "pass" for item in decision.stronger_hebog_envelopes
    )


def test_candidate_failure_is_retained_and_fails_closed() -> None:
    """A candidate failure yields one decision without scoring survivors."""
    campaign, dataset, protocol, gates, configuration = (
        _synthetic_campaign_inputs()
    )
    realizations = list(campaign.realizations)
    realizations[0] = CampaignRealizationDiagnostic(
        implementation_identifier="hebog",
        seed=dataset.recipe.seed,
        status="failure",
        failure=CampaignFailure(
            stage="source-finding",
            exception_type="RuntimeError",
            message="synthetic failure",
            traceback_sha256="2" * 64,
        ),
    )
    failed_campaign = campaign.model_copy(
        update={"realizations": tuple(realizations)}
    )

    decision = evaluate_phase_four_qualification(
        failed_campaign,
        dataset,
        protocol,
        gates,
        scientific_contract_set_sha256=configuration,
        captured_at=datetime(2026, 8, 4, tzinfo=UTC),
    )

    assert decision.passed is False
    assert decision.implementation_outcomes[0].failed_seeds == (
        dataset.recipe.seed,
    )
    assert all(
        item.status == "indeterminate" for item in decision.paired_endpoints
    )
    assert decision.absolute_gates == ()


def test_exact_equal_endpoint_passes_with_its_point_interval() -> None:
    """Exact equality passes when zero lies inside the practical margin."""
    campaign, dataset, protocol, _, _ = _synthetic_campaign_inputs()
    candidate = tuple(
        item
        for item in campaign.realizations
        if item.implementation_identifier == "hebog"
    )
    reference = tuple(
        item
        for item in campaign.realizations
        if item.implementation_identifier == "pybdsf-release"
    )

    decisions = paired_endpoint_decisions(
        candidate,
        reference,
        dataset,
        protocol,
    )
    completeness = decisions[0]

    assert completeness.status == "pass"
    assert completeness.candidate_value == 1.0
    assert completeness.reference_value == 1.0
    assert completeness.positive_regression == 0.0
    assert completeness.upper_confidence_limit == 0.0


def test_one_look_evaluator_rejects_provenance_drift() -> None:
    """A campaign cannot be rescored under a different scientific contract."""
    campaign, dataset, protocol, gates, _ = _synthetic_campaign_inputs()

    with pytest.raises(ValueError, match="contract set changed"):
        evaluate_phase_four_qualification(
            campaign,
            dataset,
            protocol,
            gates,
            scientific_contract_set_sha256="3" * 64,
        )
