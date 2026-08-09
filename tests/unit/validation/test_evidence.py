"""Tests for versioned benchmark and scientific evidence documents."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pytest
from pydantic import ValidationError

from hebog.validation.campaigns import compile_scientific_campaign
from hebog.validation.comparison import (
    CatalogueSource,
    compare_catalogues,
    compare_masks,
    compare_rms_maps,
)
from hebog.validation.datasets import DatasetRole
from hebog.validation.evidence import (
    AssociationPairDiagnostic,
    BenchmarkEvidence,
    CampaignFailure,
    CampaignImplementationEvidence,
    CampaignImplementationIdentity,
    CampaignRealizationDiagnostic,
    CatastrophicMetricDiagnostic,
    DatasetIdentity,
    EvidenceStatus,
    ExecutorKind,
    Measurement,
    NormalizedResidualDiagnostic,
    PhaseFiveAstrometryCandidateEvidence,
    PhaseFiveAstrometryCoverageEvidence,
    PhaseFiveAstrometryDevelopmentEvidence,
    PhaseFiveAstrometryDiagnostic,
    PhaseFiveAstrometryEndpointEvidence,
    PhaseFiveAstrometryEstimatorDiagnostic,
    PhaseFiveAstrometryFollowUpDevelopmentEvidence,
    PhaseFiveAstrometryFollowUpDiagnosticEvidence,
    PhaseFiveAstrometryFollowUpEndpointEvidence,
    PhaseFiveCorrectiveAReviewEvidence,
    PhaseFiveCorrectiveReviewEvidence,
    PhaseFiveCorrectiveRReviewEvidence,
    PhaseFiveFilterCandidateEvidence,
    PhaseFiveFilterFamily,
    PhaseFiveFilterReviewCandidateConclusion,
    PhaseFiveFilterReviewEndpointEvidence,
    PhaseFiveFilterReviewEvidence,
    PhaseFiveFilterReviewPairedEndpointEvidence,
    PhaseFiveFilterSelectionEvidence,
    PhaseFiveMeasurementDispositionDiagnostic,
    ResourceAllocation,
    RuntimeMetrics,
    ScalabilityMetrics,
    ScientificCampaignEvidence,
    ScientificComparisonEvidence,
    SoftwareIdentity,
    SourcePairDiagnostic,
    StageMetrics,
    StorageEvidence,
    UnavailableMetric,
    WorkloadClass,
    load_evidence,
    write_evidence,
)

SHA256 = "a" * 64


def _software(
    name: str,
    *,
    version: str | None = None,
    commit: str | None = None,
) -> SoftwareIdentity:
    """Return a complete software identity for evidence tests."""
    return SoftwareIdentity(
        name=name,
        version=version,
        commit_sha=commit,
        container_image_digest=f"sha256:{'b' * 64}",
        dependency_inventory_sha256="c" * 64,
    )


def _dataset() -> DatasetIdentity:
    """Return a governed development dataset identity."""
    return DatasetIdentity(
        identifier="synthetic-compact-field-128",
        role=DatasetRole.DEVELOPMENT,
        content_sha256="d" * 64,
        shape_yx=(128, 128),
        workload_class=WorkloadClass.NORMAL,
    )


def _runtime_metrics(*, wall_seconds: float = 1.0) -> RuntimeMetrics:
    """Return complete measured resource metrics."""
    return RuntimeMetrics(
        wall_seconds=wall_seconds,
        cpu_seconds=0.8,
        peak_rss_bytes=1024,
        array_copy_count=2,
        array_copy_bytes=512,
        dask_task_count=0,
        transfer_bytes=0,
        spill_bytes=0,
    )


def _measurement(index: int, *, warmup: bool) -> Measurement:
    """Return one complete benchmark repetition."""
    return Measurement(
        repetition_index=index,
        warmup=warmup,
        complete=_runtime_metrics(wall_seconds=1.0 + index / 10),
        stages=(
            StageMetrics(
                stage="source-finding",
                metrics=_runtime_metrics(wall_seconds=0.8 + index / 10),
            ),
        ),
    )


def _benchmark(
    *,
    status: EvidenceStatus = EvidenceStatus.EXPLORATORY,
    measurements: tuple[Measurement, ...] | None = None,
) -> BenchmarkEvidence:
    """Return a benchmark document with explicit provenance."""
    return BenchmarkEvidence(
        schema_version=1,
        evidence_type="benchmark",
        run_id="phase-0-pybdsf-release-001",
        captured_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        status=status,
        dataset=_dataset(),
        subject=_software("pybdsf", version="1.14.1", commit="e" * 40),
        related_software=(
            _software("rapthor", commit="f" * 40),
            _software("lsmtool", commit="1" * 40),
        ),
        configuration_sha256=SHA256,
        environment_sha256="2" * 64,
        resources=ResourceAllocation(
            executor=ExecutorKind.EXTERNAL,
            worker_nodes=1,
            workers_per_node=1,
            threads_per_worker=4,
            allocated_cpu_cores=4,
            node_memory_bytes=16 * 1024**3,
            worker_memory_limit_bytes=8 * 1024**3,
            reserved_headroom_per_node_bytes=4 * 1024**3,
            storage_identifier="local-ssd",
        ),
        measurements=measurements or (_measurement(0, warmup=True),),
    )


def test_evidence_round_trips_through_canonical_json(tmp_path: Path) -> None:
    """A written evidence document reloads with its exact typed meaning."""
    path = tmp_path / "benchmark.json"
    evidence = _benchmark()

    write_evidence(path, evidence)
    first_bytes = path.read_bytes()
    loaded = load_evidence(path)
    write_evidence(path, loaded)

    assert loaded == evidence
    assert path.read_bytes() == first_bytes
    assert first_bytes.endswith(b"\n")


def _phase_five_filter_candidate(
    family: Literal[
        "beam-aware-matched-filter",
        "undecimated-wavelet",
    ],
    *,
    scientifically_adequate: bool = True,
) -> PhaseFiveFilterCandidateEvidence:
    """Return one complete five-repetition filter-selection observation."""
    return PhaseFiveFilterCandidateEvidence(
        family=family,
        measured_wall_seconds=(1.0, 1.1, 0.9, 1.05, 0.95),
        median_wall_seconds=1.0,
        maximum_workspace_bytes=1024,
        convolution_count_per_image=9,
        temporary_plane_count=7,
        maximum_halo_pixels=34,
        maximum_unit_flux_response_fractional_error=0.01,
        maximum_masked_response_fractional_error=0.08,
        maximum_edge_response_fractional_error=0.07,
        maximum_absolute_background_response_jy_per_beam=0.0,
        finite_truth_group_response_fraction=1.0,
        minimum_correlated_noise_gain=1.1,
        maximum_correlated_noise_gain=2.0,
        scientifically_adequate=scientifically_adequate,
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "measured_wall_seconds",
            (1.0, 1.1, 0.0, 1.05, 0.95),
            "finite and positive",
        ),
        ("median_wall_seconds", 1.1, "must match measurements"),
        ("minimum_correlated_noise_gain", 3.0, "must be ordered"),
    ],
)
def test_phase_five_filter_candidate_rejects_invalid_summaries(
    field: str,
    value: object,
    message: str,
) -> None:
    """Candidate summaries remain derivable from valid observations."""
    candidate = _phase_five_filter_candidate("beam-aware-matched-filter")
    payload = candidate.model_dump(mode="python")
    payload[field] = value

    with pytest.raises(ValidationError, match=message):
        PhaseFiveFilterCandidateEvidence.model_validate(payload)


def _phase_five_selection_payload(
    candidates: tuple[PhaseFiveFilterCandidateEvidence, ...],
) -> dict[str, object]:
    """Return one complete selection evidence payload."""
    return {
        "schema_version": 1,
        "evidence_type": "phase-five-filter-selection",
        "run_id": "phase-five-filter-selection-development",
        "captured_at": datetime(2026, 8, 6, 9, 0, tzinfo=UTC),
        "status": EvidenceStatus.REVIEWED,
        "dataset": _dataset(),
        "configuration_sha256": SHA256,
        "subject": _software("hebog", commit="e" * 40),
        "environment_sha256": "2" * 64,
        "candidates": candidates,
        "selected_family": "beam-aware-matched-filter",
        "decision_rule": (
            "all-analytic-gates-then-lowest-maintained-bounded-cost"
        ),
        "qualification_opened": False,
    }


def test_phase_five_filter_selection_round_trips_and_requires_evidence(
    tmp_path: Path,
) -> None:
    """The development-only representation decision is machine-readable."""
    evidence = PhaseFiveFilterSelectionEvidence(
        schema_version=1,
        evidence_type="phase-five-filter-selection",
        run_id="phase-five-filter-selection-development",
        captured_at=datetime(2026, 8, 6, 9, 0, tzinfo=UTC),
        status=EvidenceStatus.REVIEWED,
        dataset=_dataset().model_copy(
            update={"identifier": "phase5-development-multiscale-1024"}
        ),
        configuration_sha256=SHA256,
        subject=_software("hebog", commit="e" * 40),
        environment_sha256="2" * 64,
        candidates=(
            _phase_five_filter_candidate("beam-aware-matched-filter"),
            _phase_five_filter_candidate("undecimated-wavelet"),
        ),
        selected_family="beam-aware-matched-filter",
        decision_rule=(
            "all-analytic-gates-then-lowest-maintained-bounded-cost"
        ),
        qualification_opened=False,
    )
    path = tmp_path / "phase-five-filter-selection.json"

    write_evidence(path, evidence)

    assert load_evidence(path) == evidence


def test_phase_five_filter_selection_rejects_inadequate_selected_family() -> (
    None
):
    """Measured speed cannot select a scientifically inadequate filter."""
    candidates = (
        _phase_five_filter_candidate(
            "beam-aware-matched-filter",
            scientifically_adequate=False,
        ),
        _phase_five_filter_candidate("undecimated-wavelet"),
    )
    payload = _phase_five_selection_payload(candidates)

    with pytest.raises(ValidationError, match="scientifically adequate"):
        PhaseFiveFilterSelectionEvidence.model_validate(payload)


def test_phase_five_filter_selection_requires_canonical_candidates() -> None:
    """Evidence always compares both candidates in the governed order."""
    candidates = (
        _phase_five_filter_candidate("undecimated-wavelet"),
        _phase_five_filter_candidate("beam-aware-matched-filter"),
    )

    with pytest.raises(ValidationError, match="complete and canonical"):
        PhaseFiveFilterSelectionEvidence.model_validate(
            _phase_five_selection_payload(candidates)
        )


def _phase_five_review_endpoint(
    family: Literal[
        "beam-aware-matched-filter",
        "undecimated-wavelet",
    ],
    *,
    passed: bool,
) -> PhaseFiveFilterReviewEndpointEvidence:
    """Return one binding absolute endpoint from the paired review."""
    return PhaseFiveFilterReviewEndpointEvidence(
        metric="response-fractional-error",
        population="analytic",
        stratum="overall",
        statistic="median",
        family=family,
        sample_count=84,
        estimate=0.08,
        absolute_limit=0.05,
        absolute_direction="maximum",
        passed=passed,
    )


def _phase_five_paired_endpoint(
    family: Literal[
        "beam-aware-matched-filter",
        "undecimated-wavelet",
    ],
) -> PhaseFiveFilterReviewPairedEndpointEvidence:
    """Return one exact non-inferiority endpoint from the paired review."""
    reference = (
        "undecimated-wavelet"
        if family == "beam-aware-matched-filter"
        else "beam-aware-matched-filter"
    )
    return PhaseFiveFilterReviewPairedEndpointEvidence(
        metric="response-fractional-error",
        population="analytic",
        stratum="overall",
        statistic="median",
        family=family,
        reference_family=reference,
        sample_count=84,
        estimate_difference=0.01,
        upper_confidence_limit=0.01,
        margin=0.02,
        passed=True,
    )


def _phase_five_review_evidence() -> PhaseFiveFilterReviewEvidence:
    """Return a valid fail-closed Step 2B review decision."""
    matched = "beam-aware-matched-filter"
    wavelet = "undecimated-wavelet"
    return PhaseFiveFilterReviewEvidence(
        schema_version=1,
        evidence_type="phase-five-filter-paired-review",
        run_id="phase-five-filter-paired-review-regression",
        captured_at=datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
        status=EvidenceStatus.REVIEWED,
        dataset=_dataset().model_copy(
            update={
                "identifier": "phase5-regression-multiscale-1024",
                "role": DatasetRole.REGRESSION,
            }
        ),
        configuration_sha256=SHA256,
        subject=_software("hebog", commit="e" * 40),
        environment_sha256="2" * 64,
        protocol_sha256="3" * 64,
        development_manifest_sha256="4" * 64,
        regression_manifest_sha256="5" * 64,
        analytic_case_count=84,
        development_image_count=10,
        regression_image_count=100,
        bootstrap_resamples=10_000,
        bootstrap_seed=20260806,
        endpoints=(
            _phase_five_review_endpoint(matched, passed=False),
            _phase_five_review_endpoint(wavelet, passed=False),
        ),
        paired_endpoints=(
            _phase_five_paired_endpoint(matched),
            _phase_five_paired_endpoint(wavelet),
        ),
        candidates=(
            PhaseFiveFilterReviewCandidateConclusion(
                family=matched,
                passes_absolute=False,
                noninferior_to_other=True,
                bounded_cost=(9, 7, 34),
                failed_absolute_endpoint_count=1,
                failed_paired_endpoint_count=0,
            ),
            PhaseFiveFilterReviewCandidateConclusion(
                family=wavelet,
                passes_absolute=False,
                noninferior_to_other=True,
                bounded_cost=(11, 9, 49),
                failed_absolute_endpoint_count=1,
                failed_paired_endpoint_count=0,
            ),
        ),
        decision="select-neither",
        selected_family=None,
        step_three_authorized=False,
        qualification_opened=False,
    )


def test_phase_five_filter_review_round_trips_select_neither(
    tmp_path: Path,
) -> None:
    """A completed inconclusive review is typed and keeps Step 3 blocked."""
    evidence = _phase_five_review_evidence()
    path = tmp_path / "phase-five-filter-paired-review.json"

    write_evidence(path, evidence)

    assert load_evidence(path) == evidence


def test_phase_five_filter_review_cannot_authorize_without_selection() -> None:
    """Fail-closed evidence cannot authorize Step 3 after selecting neither."""
    payload = _phase_five_review_evidence().model_dump(mode="python")
    payload["step_three_authorized"] = True

    with pytest.raises(ValidationError, match="authorization requires"):
        PhaseFiveFilterReviewEvidence.model_validate(payload)


def test_phase_five_filter_review_derives_candidate_failures() -> None:
    """Candidate conclusions must agree with their recorded endpoints."""
    payload = _phase_five_review_evidence().model_dump(mode="python")
    payload["candidates"][0]["passes_absolute"] = True

    with pytest.raises(ValidationError, match="candidate conclusion"):
        PhaseFiveFilterReviewEvidence.model_validate(payload)


def test_phase_five_corrective_review_requires_corrective_gate_passage() -> (
    None
):
    """A comparator result cannot authorize the residual continuum path."""
    matched_endpoint = _phase_five_review_endpoint(
        "beam-aware-matched-filter", passed=False
    )
    corrective_endpoint = PhaseFiveFilterReviewEndpointEvidence(
        metric="response-fractional-error",
        population="analytic",
        stratum="overall",
        statistic="median",
        family="residual-b3-atrous",
        sample_count=84,
        estimate=0.08,
        absolute_limit=0.05,
        absolute_direction="maximum",
        passed=False,
    )
    candidate_pairs: tuple[
        tuple[PhaseFiveFilterFamily, PhaseFiveFilterFamily], ...
    ] = (
        ("beam-aware-matched-filter", "residual-b3-atrous"),
        ("residual-b3-atrous", "beam-aware-matched-filter"),
    )
    paired = (
        PhaseFiveFilterReviewPairedEndpointEvidence(
            metric="response-fractional-error",
            population="analytic",
            stratum="overall",
            statistic="median",
            family=family,
            reference_family=reference,
            sample_count=84,
            estimate_difference=0.01,
            upper_confidence_limit=0.01,
            margin=0.02,
            passed=True,
        )
        for family, reference in candidate_pairs
    )
    evidence = PhaseFiveCorrectiveReviewEvidence(
        schema_version=1,
        evidence_type="phase-five-corrective-review",
        run_id="phase-five-corrective-review-regression",
        captured_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        status=EvidenceStatus.REVIEWED,
        dataset=_dataset().model_copy(update={"role": DatasetRole.REGRESSION}),
        configuration_sha256=SHA256,
        subject=_software("hebog", commit="e" * 40),
        environment_sha256="2" * 64,
        protocol_sha256="3" * 64,
        prior_decision_sha256="4" * 64,
        development_manifest_sha256="5" * 64,
        regression_manifest_sha256="6" * 64,
        analytic_case_count=84,
        development_image_count=10,
        regression_image_count=100,
        bootstrap_resamples=10_000,
        bootstrap_seed=20260806,
        endpoints=(matched_endpoint, corrective_endpoint),
        paired_endpoints=tuple(paired),
        candidates=(
            PhaseFiveFilterReviewCandidateConclusion(
                family="beam-aware-matched-filter",
                passes_absolute=False,
                noninferior_to_other=True,
                bounded_cost=(9, 7, 34),
                failed_absolute_endpoint_count=1,
                failed_paired_endpoint_count=0,
            ),
            PhaseFiveFilterReviewCandidateConclusion(
                family="residual-b3-atrous",
                passes_absolute=False,
                noninferior_to_other=True,
                bounded_cost=(12, 7, 14),
                failed_absolute_endpoint_count=1,
                failed_paired_endpoint_count=0,
            ),
        ),
        decision="reject-corrective",
        selected_family=None,
        step_three_authorized=False,
        qualification_opened=False,
    )
    corrective_r_payload = evidence.model_dump(mode="python")
    corrective_r_payload["evidence_type"] = "phase-five-corrective-r-review"
    corrective_r_payload["run_id"] = (
        "phase-five-corrective-r-review-regression"
    )
    corrective_r_payload["astrometry_diagnostics"] = (
        PhaseFiveAstrometryDiagnostic(
            family="residual-b3-atrous",
            stratum="overall",
            sample_count=100,
            mean_offset_xy_beams=(0.03, 0.04),
            bias_beams=0.05,
            centred_percentile_95_beams=0.2,
            radial_percentile_95_beams=0.21,
        ),
    )
    corrective_r_payload["measurement_dispositions"] = (
        PhaseFiveMeasurementDispositionDiagnostic(
            family="residual-b3-atrous",
            disposition="measured",
            count=500,
        ),
    )
    corrective_r = PhaseFiveCorrectiveRReviewEvidence.model_validate(
        corrective_r_payload
    )
    assert corrective_r.evidence_type == "phase-five-corrective-r-review"

    corrective_a_payload = corrective_r.model_dump(mode="python")
    corrective_a_payload["evidence_type"] = "phase-five-corrective-a-review"
    corrective_a_payload["run_id"] = (
        "phase-five-corrective-a-review-confirmation"
    )
    corrective_a_payload["astrometry_estimator_diagnostics"] = (
        PhaseFiveAstrometryEstimatorDiagnostic(
            family="residual-b3-atrous",
            stratum="overall",
            sample_count=600,
            available_count=600,
            model_assisted_count=590,
            fallback_count=10,
            median_uncertainty_beams=0.08,
            percentile_95_uncertainty_beams=0.14,
            percentile_95_error_to_uncertainty_ratio=1.9,
        ),
    )
    corrective_a = PhaseFiveCorrectiveAReviewEvidence.model_validate(
        corrective_a_payload
    )
    assert corrective_a.evidence_type == "phase-five-corrective-a-review"

    unavailable_payload = corrective_a.model_dump(mode="python")
    unavailable_payload["astrometry_estimator_diagnostics"][0][
        "available_count"
    ] = 601
    with pytest.raises(ValidationError, match="cannot exceed sample count"):
        PhaseFiveCorrectiveAReviewEvidence.model_validate(unavailable_payload)

    count_payload = corrective_a.model_dump(mode="python")
    count_payload["astrometry_estimator_diagnostics"][0]["fallback_count"] = 9
    with pytest.raises(ValidationError, match="must equal available count"):
        PhaseFiveCorrectiveAReviewEvidence.model_validate(count_payload)

    payload = evidence.model_dump(mode="python")
    payload["step_three_authorized"] = True

    with pytest.raises(ValidationError, match="passing corrective"):
        PhaseFiveCorrectiveReviewEvidence.model_validate(payload)


def test_phase_five_astrometry_evidence_is_fail_closed(tmp_path: Path) -> None:
    """Endpoint or coverage failures cannot authorize confirmation."""
    candidates = tuple(
        PhaseFiveAstrometryCandidateEvidence(
            candidate=candidate,
            covariance_scale=2.0,
            overall_percentile_95_beams=0.3,
            unavailable_fraction=0.0,
            model_unavailable_fraction=0.0,
            model_inadequate_fraction=0.0,
            failed_endpoint_count=1,
            failed_coverage_count=1,
            endpoints_pass=False,
            coverage_pass=False,
            model_admission_pass=True,
            eligible=False,
        )
        for candidate in (
            "direct-observable-pixel-centroid",
            "covariance-gated-model-assisted-centroid",
        )
    )
    evidence = PhaseFiveAstrometryDevelopmentEvidence(
        schema_version=1,
        evidence_type="phase-five-astrometry-development",
        run_id="phase-five-astrometry-development-selection",
        captured_at=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        status=EvidenceStatus.REVIEWED,
        dataset=_dataset(),
        configuration_sha256=SHA256,
        subject=_software("hebog", commit="e" * 40),
        environment_sha256="2" * 64,
        protocol_sha256="3" * 64,
        base_protocol_sha256="4" * 64,
        development_manifest_sha256="5" * 64,
        image_count=40,
        group_count=240,
        bootstrap_resamples=10_000,
        bootstrap_seed=20260809,
        endpoints=tuple(
            PhaseFiveAstrometryEndpointEvidence(
                candidate=candidate.candidate,
                stratum="overall",
                statistic="percentile-95",
                image_count=40,
                group_count=240,
                estimate_beams=0.3,
                upper_confidence_bound_beams=0.35,
                absolute_limit_beams=0.25,
                passed=False,
            )
            for candidate in candidates
        ),
        coverage=tuple(
            PhaseFiveAstrometryCoverageEvidence(
                candidate=candidate.candidate,
                stratum="overall",
                sample_count=240,
                covariance_positive_definite_fraction=1.0,
                level=0.68,
                empirical_coverage=0.5,
                maximum_absolute_error=0.1,
                passed=False,
            )
            for candidate in candidates
        ),
        candidates=candidates,
        decision="reject-astrometry-candidates",
        selected_candidate=None,
        confirmation_execution_authorized=False,
        step_two_c_p_execution_authorized=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )
    path = tmp_path / "astrometry.json"
    write_evidence(path, evidence)

    assert load_evidence(path) == evidence

    payload = evidence.model_dump(mode="python")
    payload["confirmation_execution_authorized"] = True
    with pytest.raises(ValidationError, match="selection is inconsistent"):
        PhaseFiveAstrometryDevelopmentEvidence.model_validate(payload)

    endpoint_payload = evidence.endpoints[0].model_dump(mode="python")
    endpoint_payload["passed"] = True
    with pytest.raises(ValidationError, match="endpoint decision"):
        PhaseFiveAstrometryEndpointEvidence.model_validate(endpoint_payload)

    coverage_payload = evidence.coverage[0].model_dump(mode="python")
    coverage_payload["level"] = 0.5
    with pytest.raises(ValidationError, match="level must be"):
        PhaseFiveAstrometryCoverageEvidence.model_validate(coverage_payload)

    candidate_payload = evidence.candidates[0].model_dump(mode="python")
    candidate_payload["eligible"] = True
    with pytest.raises(ValidationError, match="eligibility is inconsistent"):
        PhaseFiveAstrometryCandidateEvidence.model_validate(candidate_payload)

    inconsistent = evidence.model_dump(mode="python")
    inconsistent["candidates"][0]["failed_endpoint_count"] = 2
    with pytest.raises(ValidationError, match="disagrees with endpoints"):
        PhaseFiveAstrometryDevelopmentEvidence.model_validate(inconsistent)

    inconsistent = evidence.model_dump(mode="python")
    inconsistent["candidates"][0]["overall_percentile_95_beams"] = 0.31
    with pytest.raises(ValidationError, match="tail disagrees"):
        PhaseFiveAstrometryDevelopmentEvidence.model_validate(inconsistent)


def test_phase_five_astrometry_evidence_recomputes_positive_selection() -> (
    None
):
    """Eligible evidence applies the simple-candidate preference exactly."""
    candidates = (
        "direct-observable-pixel-centroid",
        "covariance-gated-model-assisted-centroid",
    )
    tails = dict(zip(candidates, (0.2, 0.19), strict=True))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "evidence_type": "phase-five-astrometry-development",
        "run_id": "phase-five-astrometry-development-selection",
        "captured_at": datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        "status": EvidenceStatus.REVIEWED,
        "dataset": _dataset(),
        "configuration_sha256": SHA256,
        "subject": _software("hebog", commit="e" * 40),
        "environment_sha256": "2" * 64,
        "protocol_sha256": "3" * 64,
        "base_protocol_sha256": "4" * 64,
        "development_manifest_sha256": "5" * 64,
        "image_count": 40,
        "group_count": 240,
        "bootstrap_resamples": 10_000,
        "bootstrap_seed": 20260809,
        "endpoints": [
            {
                "candidate": candidate,
                "stratum": "overall",
                "statistic": "percentile-95",
                "image_count": 40,
                "group_count": 240,
                "estimate_beams": tails[candidate],
                "upper_confidence_bound_beams": tails[candidate] + 0.01,
                "absolute_limit_beams": 0.25,
                "passed": True,
            }
            for candidate in candidates
        ],
        "coverage": [
            {
                "candidate": candidate,
                "stratum": "overall",
                "sample_count": 240,
                "covariance_positive_definite_fraction": 1.0,
                "level": 0.68,
                "empirical_coverage": 0.68,
                "maximum_absolute_error": 0.1,
                "passed": True,
            }
            for candidate in candidates
        ],
        "candidates": [
            {
                "candidate": candidate,
                "covariance_scale": 1.0,
                "overall_percentile_95_beams": tails[candidate],
                "unavailable_fraction": 0.0,
                "model_unavailable_fraction": 0.0,
                "model_inadequate_fraction": 0.0,
                "failed_endpoint_count": 0,
                "failed_coverage_count": 0,
                "endpoints_pass": True,
                "coverage_pass": True,
                "model_admission_pass": True,
                "eligible": True,
            }
            for candidate in candidates
        ],
        "decision": "select-direct",
        "selected_candidate": "direct-observable-pixel-centroid",
        "confirmation_execution_authorized": True,
        "step_two_c_p_execution_authorized": False,
        "step_three_authorized": False,
        "optimization_authorized": False,
        "qualification_opened": False,
    }

    direct = PhaseFiveAstrometryDevelopmentEvidence.model_validate(payload)
    assert direct.decision == "select-direct"

    payload["endpoints"][1]["estimate_beams"] = 0.17
    payload["endpoints"][1]["upper_confidence_bound_beams"] = 0.18
    payload["candidates"][1]["overall_percentile_95_beams"] = 0.17
    payload["decision"] = "select-model"
    payload["selected_candidate"] = "covariance-gated-model-assisted-centroid"
    model = PhaseFiveAstrometryDevelopmentEvidence.model_validate(payload)
    assert model.decision == "select-model"


def test_phase_five_astrometry_follow_up_evidence_awaits_human_review(
    tmp_path: Path,
) -> None:
    """Passing development remains exploratory and cannot open confirmation."""
    endpoint_specs: tuple[
        tuple[
            Literal[
                "availability",
                "absolute-mean-offset-x",
                "absolute-mean-offset-y",
                "radial-percentile-95",
            ],
            float,
            float,
            float,
            Literal["at-least", "at-most"],
        ],
        ...,
    ] = (
        ("availability", 1.0, 1.0, 1.0, "at-least"),
        ("absolute-mean-offset-x", 0.01, 0.03, 0.1, "at-most"),
        ("absolute-mean-offset-y", 0.02, 0.04, 0.1, "at-most"),
        ("radial-percentile-95", 0.25, 0.35, 0.5, "at-most"),
    )
    endpoints = tuple(
        PhaseFiveAstrometryFollowUpEndpointEvidence(
            candidate="original-pixel-detected-segment-centroid",
            stratum="overall",
            metric=metric,
            image_count=80,
            group_count=480,
            estimate=estimate,
            confidence_bound=confidence_bound,
            limit=limit,
            required_relation=relation,
            passed=True,
        )
        for metric, estimate, confidence_bound, limit, relation in (
            endpoint_specs
        )
    )
    evidence = PhaseFiveAstrometryFollowUpDevelopmentEvidence(
        schema_version=1,
        evidence_type="phase-five-astrometry-follow-up-development",
        run_id="phase-five-astrometry-follow-up-development",
        captured_at=datetime(2026, 8, 9, 14, 0, tzinfo=UTC),
        status=EvidenceStatus.EXPLORATORY,
        dataset=_dataset(),
        configuration_sha256=SHA256,
        subject=_software("hebog", commit="e" * 40),
        environment_sha256="2" * 64,
        protocol_sha256="3" * 64,
        base_protocol_sha256="4" * 64,
        development_manifest_sha256="5" * 64,
        image_count=80,
        group_count=480,
        bootstrap_resamples=10_000,
        bootstrap_seed=20260809,
        candidate="original-pixel-detected-segment-centroid",
        endpoints=endpoints,
        diagnostics=(
            PhaseFiveAstrometryFollowUpDiagnosticEvidence(
                stratum="overall",
                available_group_count=480,
                radial_median_beams=0.1,
                former_target_percentile_95_beams=0.3,
            ),
        ),
        failed_endpoint_count=0,
        eligible_for_human_review=True,
        decision="eligible-awaiting-human-review",
        independent_human_review_complete=False,
        confirmation_execution_authorized=False,
        step_two_c_p_execution_authorized=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )
    path = tmp_path / "follow-up.json"
    write_evidence(path, evidence)

    assert load_evidence(path) == evidence
    payload = evidence.model_dump(mode="python")
    payload["confirmation_execution_authorized"] = True
    with pytest.raises(ValidationError, match="confirmation remains sealed"):
        PhaseFiveAstrometryFollowUpDevelopmentEvidence.model_validate(payload)

    endpoint_payload = endpoints[1].model_dump(mode="python")
    endpoint_payload["passed"] = False
    with pytest.raises(ValidationError, match="endpoint decision"):
        PhaseFiveAstrometryFollowUpEndpointEvidence.model_validate(
            endpoint_payload
        )


def test_software_identity_can_record_an_uncommitted_source_tree() -> None:
    """Exploratory code is identified even before its commit exists."""
    identity = SoftwareIdentity(
        name="hebog",
        source_tree_sha256="4" * 64,
        dependency_inventory_sha256="5" * 64,
    )

    assert identity.source_tree_sha256 == "4" * 64


def test_software_identity_can_use_container_digest_without_commit() -> None:
    """Container images can identify software revisions without a commit."""
    identity = SoftwareIdentity(
        name="hebog",
        container_image_digest=f"sha256:{'6' * 64}",
        dependency_inventory_sha256="5" * 64,
    )

    assert identity.container_image_digest == f"sha256:{'6' * 64}"


def test_reviewed_benchmark_requires_warmup_and_five_measurements() -> None:
    """Exploratory timing cannot be labelled as reviewed release evidence."""
    insufficient = tuple(
        _measurement(index, warmup=index == 0) for index in range(5)
    )

    with pytest.raises(ValidationError, match="five measured repetitions"):
        _benchmark(
            status=EvidenceStatus.REVIEWED,
            measurements=insufficient,
        )

    sufficient = tuple(
        _measurement(index, warmup=index == 0) for index in range(6)
    )
    evidence = _benchmark(
        status=EvidenceStatus.REVIEWED,
        measurements=sufficient,
    )

    assert sum(not item.warmup for item in evidence.measurements) == 5


def test_benchmark_rejects_duplicate_stages_and_repetitions() -> None:
    """Every recorded stage and repetition remains unambiguous."""
    measurement = _measurement(0, warmup=True)
    duplicate_stage = measurement.model_dump(mode="json")
    duplicate_stage["stages"] *= 2

    with pytest.raises(ValidationError, match="stage names"):
        Measurement.model_validate(duplicate_stage)

    benchmark = _benchmark()
    duplicate_repetition = benchmark.model_dump(mode="json")
    duplicate_repetition["measurements"] *= 2

    with pytest.raises(ValidationError, match="repetition indices"):
        BenchmarkEvidence.model_validate(duplicate_repetition)


def test_unavailable_optional_metric_requires_a_reason() -> None:
    """Missing instrumentation is explicit rather than encoded as zero."""
    document = _runtime_metrics().model_dump(mode="json")
    document["array_copy_count"] = None

    with pytest.raises(ValidationError, match="array_copy_count"):
        RuntimeMetrics.model_validate(document)

    document["unavailable_metrics"] = [
        UnavailableMetric(
            metric="array_copy_count",
            reason="profiler does not expose copy counts",
        ).model_dump(mode="json")
    ]
    metrics = RuntimeMetrics.model_validate(document)

    assert metrics.array_copy_count is None
    assert isinstance(metrics.unavailable_metrics, tuple)


def test_evidence_requires_timezone_aware_capture_time() -> None:
    """Evidence timestamps cannot depend on the runner's local timezone."""
    document = _benchmark().model_dump(mode="json")
    document["captured_at"] = "2026-07-18T12:00:00"

    with pytest.raises(ValidationError, match="timezone"):
        BenchmarkEvidence.model_validate(document)


def test_warmups_must_precede_measured_repetitions() -> None:
    """A later warm-up cannot contaminate the measured sample sequence."""
    with pytest.raises(ValidationError, match="must precede"):
        _benchmark(
            measurements=(
                _measurement(0, warmup=False),
                _measurement(1, warmup=True),
            )
        )


def test_reviewed_multi_node_evidence_requires_scalability_metrics() -> None:
    """Multi-node release evidence cannot omit topology and efficiency."""
    measurements = tuple(
        _measurement(index, warmup=index == 0) for index in range(6)
    )
    document = _benchmark(
        status=EvidenceStatus.REVIEWED,
        measurements=measurements,
    ).model_dump(mode="json")
    document["resources"]["worker_nodes"] = 10

    with pytest.raises(ValidationError, match="scalability metrics"):
        BenchmarkEvidence.model_validate(document)

    document["scalability"] = ScalabilityMetrics(
        logical_plane_count=4,
        tile_core_shape_yx=(2048, 2048),
        maximum_halo_yx=(128, 128),
        partition_count=2400,
        graph_task_count=9600,
        scheduler_overhead_seconds=4.5,
        worker_occupancy_fraction=0.85,
        storage_throughput_bytes_per_second=2.0e9,
        retry_count=0,
        straggler_count=2,
        strong_scaling_efficiency=0.8,
        weak_scaling_efficiency=0.9,
    ).model_dump(mode="json")
    evidence = BenchmarkEvidence.model_validate(document)

    assert evidence.scalability is not None
    assert evidence.scalability.partition_count == 2400


def test_resource_allocation_preserves_memory_headroom() -> None:
    """Recorded worker limits cannot exceed memory admitted on each node."""
    document = _benchmark().resources.model_dump(mode="json")
    document["workers_per_node"] = 2

    with pytest.raises(ValidationError, match="aggregate worker memory"):
        ResourceAllocation.model_validate(document)


def _storage_evidence(**changes: object) -> StorageEvidence:
    """Return valid intermediate-store evidence for mutation tests."""
    document = StorageEvidence(
        format_name="zarr-v3",
        library_name="zarr",
        library_version="3.2.1",
        backend_name="local-store",
        chunk_shape_yx=(256, 256),
        shard_shape_yx=None,
        codec_pipeline=("bytes-little-endian", "zstd-1", "crc32c"),
        fill_value="0",
        missing_chunk_policy="error",
        write_empty_chunks=True,
        object_count=19,
        stored_bytes=4096,
        internal_concurrency=1,
        atomic_write_guarantee="not documented by LocalStore",
        conditional_create=False,
    ).model_dump(mode="python")
    document.update(changes)
    return StorageEvidence.model_validate(document)


def test_benchmark_records_intermediate_storage_configuration() -> None:
    """A store comparison retains layout, policy, and durability evidence."""
    storage = _storage_evidence(shard_shape_yx=(512, 512))

    evidence = _benchmark().model_copy(update={"storage": storage})

    assert evidence.storage == storage


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"chunk_shape_yx": (0, 256)}, "chunk dimensions"),
        ({"shard_shape_yx": (0, 512)}, "shard dimensions"),
        ({"codec_pipeline": ("",)}, "descriptions"),
        ({"internal_concurrency": 0}, "greater than or equal to 1"),
    ],
)
def test_storage_evidence_rejects_invalid_configuration(
    changes: dict[str, object],
    message: str,
) -> None:
    """Storage evidence rejects unusable geometry, policy, and resources."""
    with pytest.raises(ValidationError, match=message):
        _storage_evidence(**changes)


def test_scientific_comparison_evidence_round_trips(tmp_path: Path) -> None:
    """Analytic reports retain provenance in one machine-readable document."""
    reference_source = CatalogueSource(
        identifier="reference",
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=1.5,
    )
    candidate_source = CatalogueSource(
        identifier="candidate",
        right_ascension_degrees=10.001,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=0.98,
        integrated_flux_jy=1.45,
    )
    catalogue_report = compare_catalogues(
        (reference_source,),
        (candidate_source,),
        beam_fwhm_degrees=0.01,
        maximum_separation_beams=0.5,
    )
    rms_report = compare_rms_maps(
        np.array([[1.0, 2.0]]),
        np.array([[1.01, 1.98]]),
    )
    mask_report = compare_masks(
        np.array([[True, False]]),
        np.array([[True, False]]),
    )
    evidence = ScientificComparisonEvidence(
        schema_version=1,
        evidence_type="scientific-comparison",
        run_id="hebog-vs-pybdsf-release-001",
        captured_at=datetime(2026, 7, 18, 12, 30, tzinfo=UTC),
        status=EvidenceStatus.EXPLORATORY,
        dataset=_dataset(),
        candidate=_software("hebog", version="0.1.0", commit="3" * 40),
        reference=_software(
            "pybdsf",
            version="1.14.1",
            commit="e" * 40,
        ),
        candidate_product_manifest_sha256="4" * 64,
        reference_product_manifest_sha256="5" * 64,
        configuration_sha256=SHA256,
        beam_fwhm_degrees=0.01,
        maximum_separation_beams=0.5,
        catalogue=catalogue_report,
        true_sky_rms=rms_report,
        flat_noise_rms=rms_report,
        mask=mask_report,
    )
    path = tmp_path / "comparison.json"

    write_evidence(path, evidence)
    loaded = load_evidence(path)

    assert loaded == evidence
    assert isinstance(loaded, ScientificComparisonEvidence)


def _matched_source(
    candidate_identifier: str,
    *,
    truth_identifier: str = "truth-source-00001",
) -> SourcePairDiagnostic:
    """Return one fully explainable matched-source diagnostic."""
    return SourcePairDiagnostic(
        decision="matched",
        truth_identifier=truth_identifier,
        candidate_identifier=candidate_identifier,
        truth_strata=("shape-unresolved", "snr-10"),
        candidate_deconvolution_status="unresolved",
        candidate_quality_flags=("edge", "unresolved"),
        classification_agrees=True,
        separation_beam_fwhm=0.04,
        peak_flux_fractional_difference=0.02,
        integrated_flux_fractional_difference=0.02,
        maximum_absolute_fitted_axis_fractional_difference=0.03,
        maximum_absolute_deconvolved_axis_fractional_difference=None,
        fitted_position_angle_difference_degrees=2.0,
        deconvolved_position_angle_difference_degrees=None,
        catastrophic=CatastrophicMetricDiagnostic(
            position=False,
            peak_flux=False,
            integrated_flux=False,
            fitted_axis=False,
            deconvolved_axis=False,
        ),
        gated_catastrophic=False,
        normalized_residuals=(
            NormalizedResidualDiagnostic(metric="peak-flux", value=0.2),
            NormalizedResidualDiagnostic(
                metric="right-ascension",
                value=-0.1,
            ),
        ),
    )


def _campaign_evidence() -> ScientificCampaignEvidence:
    """Return a paired campaign with one captured reference failure."""
    implementations = (
        CampaignImplementationIdentity(
            identifier="hebog",
            role="candidate",
            execution_configuration_sha256="7" * 64,
            software=_software("hebog", version="0.1.0", commit="3" * 40),
        ),
        CampaignImplementationIdentity(
            identifier="pybdsf-release",
            role="reference",
            execution_configuration_sha256="8" * 64,
            software=_software(
                "pybdsf",
                version="1.14.1",
                commit="e" * 40,
            ),
        ),
        CampaignImplementationIdentity(
            identifier="pybdsf-master",
            role="reference",
            execution_configuration_sha256="9" * 64,
            software=_software("pybdsf", commit="f" * 40),
        ),
    )
    return ScientificCampaignEvidence(
        schema_version=1,
        evidence_type="scientific-campaign",
        run_id="phase-4-paired-campaign-001",
        captured_at=datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
        status=EvidenceStatus.EXPLORATORY,
        dataset=_dataset(),
        configuration_sha256=SHA256,
        comparison_protocol_sha256="4" * 64,
        implementations=implementations,
        realizations=(
            CampaignRealizationDiagnostic(
                implementation_identifier="hebog",
                seed=2026090152,
                status="success",
                candidate_count=1,
                association_pairs=(
                    AssociationPairDiagnostic(
                        decision="matched",
                        truth_group_identifier="truth-source-00001",
                        candidate_identifier="hebog-source-00001",
                        resolution_class="individually-resolvable",
                        truth_strata=("compact",),
                        separation_beam_fwhm=0.04,
                        integrated_flux_fractional_difference=0.02,
                    ),
                ),
                source_pairs=(_matched_source("hebog-source-00001"),),
            ),
            CampaignRealizationDiagnostic(
                implementation_identifier="pybdsf-release",
                seed=2026090152,
                status="success",
                candidate_count=1,
                association_pairs=(
                    AssociationPairDiagnostic(
                        decision="matched",
                        truth_group_identifier="truth-source-00001",
                        candidate_identifier="release-source-00001",
                        resolution_class="individually-resolvable",
                        truth_strata=("compact",),
                        separation_beam_fwhm=0.04,
                        integrated_flux_fractional_difference=0.02,
                    ),
                ),
                source_pairs=(_matched_source("release-source-00001"),),
            ),
            CampaignRealizationDiagnostic(
                implementation_identifier="pybdsf-master",
                seed=2026090152,
                status="failure",
                failure=CampaignFailure(
                    stage="atrous-gaussian-fitting",
                    exception_type="IndexError",
                    message=(
                        "index 2 is out of bounds for axis 0 with size 2"
                    ),
                    traceback_sha256="5" * 64,
                ),
            ),
        ),
    )


def _implementation_evidence(
    campaign: ScientificCampaignEvidence,
    implementation_index: int,
) -> CampaignImplementationEvidence:
    """Return one isolated shard from complete paired test evidence."""
    implementation = campaign.implementations[implementation_index]
    return CampaignImplementationEvidence(
        schema_version=1,
        evidence_type="scientific-campaign-implementation",
        run_id=f"{campaign.run_id}-{implementation.identifier}",
        captured_at=campaign.captured_at,
        status=campaign.status,
        dataset=campaign.dataset,
        configuration_sha256=campaign.configuration_sha256,
        comparison_protocol_sha256=campaign.comparison_protocol_sha256,
        implementation=implementation,
        wall_seconds=12.5,
        realizations=tuple(
            realization
            for realization in campaign.realizations
            if realization.implementation_identifier
            == implementation.identifier
        ),
    )


def test_scientific_campaign_evidence_round_trips_failures_and_rows(
    tmp_path: Path,
) -> None:
    """Paired evidence retains per-source detail and reference failures."""
    evidence = _campaign_evidence()
    path = tmp_path / "campaign.json"

    write_evidence(path, evidence)
    loaded = load_evidence(path)

    assert loaded == evidence
    assert isinstance(loaded, ScientificCampaignEvidence)
    assert loaded.realizations[-1].failure is not None
    assert loaded.realizations[0].source_pairs[0].normalized_residuals[0] == (
        NormalizedResidualDiagnostic(metric="peak-flux", value=0.2)
    )


def test_campaign_implementation_evidence_round_trips(
    tmp_path: Path,
) -> None:
    """An isolated reference environment emits one strict mergeable shard."""
    evidence = _implementation_evidence(_campaign_evidence(), 1)
    path = tmp_path / "release.json"

    write_evidence(path, evidence)
    loaded = load_evidence(path)

    assert loaded == evidence
    assert isinstance(loaded, CampaignImplementationEvidence)


def test_association_pair_requires_complete_group_measurements() -> None:
    """A matched unresolved group retains both governed paired metrics."""
    with pytest.raises(ValidationError, match="group measurements"):
        AssociationPairDiagnostic(
            decision="matched",
            truth_group_identifier="blend-00001",
            candidate_identifier="candidate-00001",
            resolution_class="unresolved-blend",
            truth_strata=("unresolved-blend",),
            separation_beam_fwhm=0.1,
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            {"truth_strata": ["unresolved-blend", "compact"]},
            "strata must be canonical",
        ),
        (
            {
                "decision": "unmatched-truth-group",
                "candidate_identifier": "candidate-00001",
                "separation_beam_fwhm": None,
                "integrated_flux_fractional_difference": None,
            },
            "requires only truth metadata",
        ),
        (
            {
                "decision": "unmatched-candidate",
                "separation_beam_fwhm": None,
                "integrated_flux_fractional_difference": None,
            },
            "unmatched candidate",
        ),
    ],
)
def test_association_pair_rejects_inconsistent_decisions(
    change: dict[str, object],
    message: str,
) -> None:
    """Association rows cannot hide or mislabel truth-group measurements."""
    document = (
        _campaign_evidence()
        .realizations[0]
        .association_pairs[0]
        .model_dump(mode="json")
    )
    document.update(change)

    with pytest.raises(ValidationError, match=message):
        AssociationPairDiagnostic.model_validate(document)


def test_campaign_compiler_pairs_isolated_failures_and_successes() -> None:
    """The compiler keeps a failed reference in the paired denominator."""
    campaign = _campaign_evidence()
    shards = tuple(
        _implementation_evidence(campaign, index) for index in range(3)
    )

    compiled = compile_scientific_campaign(
        run_id="phase-4-compiled-campaign",
        shards=shards,
    )

    assert compiled.implementations == campaign.implementations
    assert compiled.realizations[-1].status == "failure"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("too-few", "at least two"),
        ("reference-first", "candidate implementation shard must be first"),
        ("provenance", "provenance differs"),
        ("seeds", "seeds differ"),
    ],
)
def test_campaign_compiler_rejects_unpaired_shards(
    mutation: str,
    message: str,
) -> None:
    """Compilation fails closed on incomplete or drifting input."""
    campaign = _campaign_evidence()
    shards = [_implementation_evidence(campaign, index) for index in range(3)]
    if mutation == "too-few":
        shards = shards[:1]
    elif mutation == "reference-first":
        shards = shards[1:]
    elif mutation == "provenance":
        shards[1] = shards[1].model_copy(
            update={"configuration_sha256": "0" * 64}
        )
    else:
        changed = shards[1].realizations[0].model_copy(update={"seed": 1})
        shards[1] = shards[1].model_copy(update={"realizations": (changed,)})

    with pytest.raises(ValueError, match=message):
        compile_scientific_campaign(
            run_id="phase-4-invalid-campaign",
            shards=shards,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("implementation", "different implementation"),
        ("seed-order", "seeds must be unique and sorted"),
        ("truth", "truth identifiers differ by seed"),
        ("truth-group", "truth-group identifiers differ by seed"),
    ],
)
def test_implementation_shard_rejects_internal_drift(
    mutation: str,
    message: str,
) -> None:
    """An isolated shard cannot change identity or truth between seeds."""
    shard = _implementation_evidence(_campaign_evidence(), 0)
    first = shard.realizations[0].model_dump(mode="json")
    second = shard.realizations[0].model_dump(mode="json")
    second["seed"] += 1
    if mutation == "implementation":
        first["implementation_identifier"] = "different"
        document = shard.model_dump(mode="json")
        document["realizations"] = [first]
    elif mutation == "seed-order":
        second["seed"] -= 2
        document = shard.model_dump(mode="json")
        document["realizations"] = [first, second]
    elif mutation == "truth":
        second["source_pairs"][0]["truth_identifier"] = "different-truth"
        second["association_pairs"][0]["truth_group_identifier"] = (
            "different-truth"
        )
        document = shard.model_dump(mode="json")
        document["realizations"] = [first, second]
    else:
        first["source_pairs"] = []
        second["source_pairs"] = []
        second["association_pairs"][0]["truth_group_identifier"] = (
            "different-group"
        )
        document = shard.model_dump(mode="json")
        document["realizations"] = [first, second]

    with pytest.raises(ValidationError, match=message):
        CampaignImplementationEvidence.model_validate(document)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("candidate", "occur in association"),
        ("match", "agree with association"),
    ],
)
def test_realization_requires_source_and_association_consistency(
    mutation: str,
    message: str,
) -> None:
    """Individual diagnostics remain bound to their group-level match."""
    document = _campaign_evidence().realizations[0].model_dump(mode="json")
    if mutation == "candidate":
        document["source_pairs"][0]["candidate_identifier"] = "unrepresented"
    else:
        document["source_pairs"][0]["truth_identifier"] = "different-truth"

    with pytest.raises(ValidationError, match=message):
        CampaignRealizationDiagnostic.model_validate(document)


def test_campaign_requires_identical_paired_truth_groups() -> None:
    """Group non-inferiority cannot compare different truth populations."""
    document = _campaign_evidence().model_dump(mode="json")
    for realization in document["realizations"]:
        if realization["status"] == "success":
            realization["source_pairs"] = []
    document["realizations"][1]["association_pairs"][0][
        "truth_group_identifier"
    ] = "different-group"

    with pytest.raises(
        ValidationError,
        match="identical truth-group identifiers",
    ):
        ScientificCampaignEvidence.model_validate(document)


def test_campaign_requires_every_implementation_for_every_seed() -> None:
    """A nominally paired campaign cannot silently omit a failed reference."""
    document = _campaign_evidence().model_dump(mode="json")
    document["realizations"] = document["realizations"][:-1]

    with pytest.raises(
        ValidationError,
        match="every implementation exactly once",
    ):
        ScientificCampaignEvidence.model_validate(document)


def test_campaign_requires_identical_paired_truth() -> None:
    """Successful implementations must be compared on identical truth rows."""
    document = _campaign_evidence().model_dump(mode="json")
    document["realizations"][1]["source_pairs"][0]["truth_identifier"] = (
        "different-truth"
    )
    document["realizations"][1]["association_pairs"][0][
        "truth_group_identifier"
    ] = "different-truth"

    with pytest.raises(ValidationError, match="identical truth identifiers"):
        ScientificCampaignEvidence.model_validate(document)


def test_source_pair_rejects_match_fields_for_unmatched_truth() -> None:
    """Unmatched truth cannot retain a misleading candidate measurement."""
    document = _matched_source("candidate").model_dump(mode="json")
    document["decision"] = "unmatched-truth"
    document["candidate_identifier"] = None

    with pytest.raises(ValidationError, match="unmatched truth"):
        SourcePairDiagnostic.model_validate(document)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("truth_strata", ["snr-10", "shape-unresolved"], "truth strata"),
        (
            "candidate_quality_flags",
            ["unresolved", "edge"],
            "quality flags",
        ),
        (
            "normalized_residuals",
            [
                {"metric": "right-ascension", "value": 0.0},
                {"metric": "peak-flux", "value": 0.0},
            ],
            "residual metrics",
        ),
        ("truth_identifier", None, "both identifiers"),
        ("truth_strata", [], "requires truth strata"),
        ("candidate_deconvolution_status", None, "candidate status"),
        (
            "separation_beam_fwhm",
            None,
            "position and flux metrics",
        ),
        ("catastrophic", None, "catastrophic decisions"),
    ],
)
def test_matched_source_requires_canonical_complete_diagnostics(
    field: str,
    value: object,
    message: str,
) -> None:
    """Matched rows reject ambiguous ordering or incomplete measurements."""
    document = _matched_source("candidate").model_dump(mode="json")
    document[field] = value

    with pytest.raises(ValidationError, match=message):
        SourcePairDiagnostic.model_validate(document)


def test_unmatched_candidate_rejects_truth_measurements() -> None:
    """An extra candidate cannot be presented as a measured truth pair."""
    document = {
        "decision": "unmatched-candidate",
        "truth_identifier": "truth-source-00001",
        "candidate_identifier": "candidate-source-00001",
        "candidate_deconvolution_status": "unresolved",
    }

    with pytest.raises(ValidationError, match="unmatched candidate"):
        SourcePairDiagnostic.model_validate(document)


def test_unmatched_truth_requires_scientific_strata() -> None:
    """A missed truth source remains attributable to its governed stratum."""
    document = {
        "decision": "unmatched-truth",
        "truth_identifier": "truth-source-00001",
    }

    with pytest.raises(ValidationError, match="requires strata"):
        SourcePairDiagnostic.model_validate(document)


def test_realization_failure_cannot_publish_partial_candidate_rows() -> None:
    """A failed reference result is explicit rather than partially scored."""
    document = _campaign_evidence().realizations[0].model_dump(mode="json")
    document["status"] = "failure"
    document["failure"] = {
        "stage": "catalogue",
        "exception_type": "RuntimeError",
        "message": "failed",
        "traceback_sha256": "6" * 64,
    }

    with pytest.raises(ValidationError, match="failed realization"):
        CampaignRealizationDiagnostic.model_validate(document)


def test_campaign_failure_rejects_blank_message() -> None:
    """Captured failures retain a useful stable explanation."""
    with pytest.raises(ValidationError, match="message must not be blank"):
        CampaignFailure(
            stage="catalogue",
            exception_type="RuntimeError",
            message="   ",
            traceback_sha256="6" * 64,
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            {
                "failure": {
                    "stage": "catalogue",
                    "exception_type": "RuntimeError",
                    "message": "failed",
                    "traceback_sha256": "6" * 64,
                }
            },
            "successful realization",
        ),
        ({"status": "success", "candidate_count": None}, "successful"),
        (
            {
                "source_pairs": [
                    _matched_source("candidate").model_dump(mode="json"),
                    _matched_source("other-candidate").model_dump(mode="json"),
                ],
                "candidate_count": 2,
            },
            "truth identifiers",
        ),
        (
            {
                "source_pairs": [
                    _matched_source("candidate").model_dump(mode="json"),
                    _matched_source(
                        "candidate",
                        truth_identifier="truth-source-00002",
                    ).model_dump(mode="json"),
                ],
                "candidate_count": 2,
            },
            "candidate identifiers",
        ),
        ({"candidate_count": 2}, "candidate count"),
    ],
)
def test_realization_requires_complete_unambiguous_rows(
    change: dict[str, object],
    message: str,
) -> None:
    """Successful results have unique rows consistent with their count."""
    document = _campaign_evidence().realizations[0].model_dump(mode="json")
    document.update(change)

    with pytest.raises(ValidationError, match=message):
        CampaignRealizationDiagnostic.model_validate(document)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        ("duplicate-identifier", "identifiers must be unique"),
        ("second-candidate", "exactly one candidate"),
        ("reference-first", "candidate must be declared first"),
    ],
)
def test_campaign_requires_unambiguous_candidate_identity(
    mutate: str,
    message: str,
) -> None:
    """Campaign roles and identifiers cannot change the paired denominator."""
    document = _campaign_evidence().model_dump(mode="json")
    if mutate == "duplicate-identifier":
        document["implementations"][1]["identifier"] = "hebog"
    elif mutate == "second-candidate":
        document["implementations"][1]["role"] = "candidate"
    else:
        document["implementations"][0]["role"] = "reference"
        document["implementations"][1]["role"] = "candidate"

    with pytest.raises(ValidationError, match=message):
        ScientificCampaignEvidence.model_validate(document)
