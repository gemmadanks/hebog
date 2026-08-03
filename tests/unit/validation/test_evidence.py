"""Tests for versioned benchmark and scientific evidence documents."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from hebog.validation.comparison import (
    CatalogueSource,
    compare_catalogues,
    compare_masks,
    compare_rms_maps,
)
from hebog.validation.datasets import DatasetRole
from hebog.validation.evidence import (
    BenchmarkEvidence,
    CampaignFailure,
    CampaignImplementationIdentity,
    CampaignRealizationDiagnostic,
    CatastrophicMetricDiagnostic,
    DatasetIdentity,
    EvidenceStatus,
    ExecutorKind,
    Measurement,
    NormalizedResidualDiagnostic,
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
            software=_software("hebog", version="0.1.0", commit="3" * 40),
        ),
        CampaignImplementationIdentity(
            identifier="pybdsf-release",
            role="reference",
            software=_software(
                "pybdsf",
                version="1.14.1",
                commit="e" * 40,
            ),
        ),
        CampaignImplementationIdentity(
            identifier="pybdsf-master",
            role="reference",
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
                source_pairs=(_matched_source("hebog-source-00001"),),
            ),
            CampaignRealizationDiagnostic(
                implementation_identifier="pybdsf-release",
                seed=2026090152,
                status="success",
                candidate_count=1,
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
