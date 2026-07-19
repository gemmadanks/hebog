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
    DatasetIdentity,
    EvidenceStatus,
    ExecutorKind,
    Measurement,
    ResourceAllocation,
    RuntimeMetrics,
    ScalabilityMetrics,
    ScientificComparisonEvidence,
    SoftwareIdentity,
    StageMetrics,
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
