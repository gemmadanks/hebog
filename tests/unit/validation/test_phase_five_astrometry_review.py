"""Tests for the prospective Phase 5 astrometry revision."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.contracts import (
    load_phase_five_astrometry_revision_review,
    load_phase_five_corrective_a_review,
)
from hebog.validation.datasets import WcsMetadata, load_dataset_manifest
from hebog.validation.phase_five_astrometry_review import (
    AstrometryCandidate,
    AstrometryCandidateResult,
    AstrometryGroupObservation,
    BootstrapDesign,
    cluster_bootstrap_statistic,
    compile_astrometry_development,
    covariance_gated_model_assistance,
    direct_observable_pixel_centroid,
    evaluate_astrometry_revision_image,
    local_wcs_jacobian,
    select_astrometry_candidate,
)

_ROOT = Path(__file__).parents[3]
_DEVELOPMENT = _ROOT / "config/datasets/phase-5-astrometry-development.json"
_BASE_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_REVISION_REVIEW = (
    _ROOT / "config/contracts/phase-5-astrometry-revision-review.json"
)


def _position_inputs() -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    BeamShapePixels,
    WcsMetadata,
]:
    """Return a symmetric source with rotated covariance and WCS."""
    y_grid, x_grid = np.indices((15, 15), dtype=np.float64)
    signal = np.exp(-0.5 * (((x_grid - 7.0) / 2.0) ** 2 + (y_grid - 7.0) ** 2))
    return (
        signal,
        np.full(signal.shape, 0.1),
        np.ones(signal.shape, dtype=np.bool_),
        BeamShapePixels(5.0, 3.0, 35.0),
        WcsMetadata(
            reference_pixel_xy=(7.0, 7.0),
            reference_sky_degrees=(180.0, -30.0),
            pixel_scale_degrees_xy=(-0.001, 0.002),
            rotation_degrees_counterclockwise=20.0,
        ),
    )


def test_direct_centroid_has_full_pixel_and_sky_covariance() -> None:
    """The baseline is a literal centroid with a rotated 2D covariance."""
    signal, rms, support, beam, wcs = _position_inputs()

    estimate = direct_observable_pixel_centroid(
        signal,
        rms,
        support,
        beam,
        wcs,
    )

    assert estimate.available is True
    assert estimate.position_xy_pixels == pytest.approx((7.0, 7.0))
    pixel_covariance = np.asarray(estimate.pixel_covariance)
    sky_covariance = np.asarray(estimate.sky_covariance_degrees)
    assert pixel_covariance.shape == (2, 2)
    assert sky_covariance.shape == (2, 2)
    assert pixel_covariance[0, 1] != pytest.approx(0.0)
    assert np.linalg.eigvalsh(pixel_covariance).min() > 0
    jacobian = local_wcs_jacobian(wcs)
    assert sky_covariance == pytest.approx(
        jacobian @ pixel_covariance @ jacobian.T
    )


def test_direct_covariance_scales_quadratically_with_rms() -> None:
    """The full correlated-noise propagation retains physical RMS units."""
    signal, rms, support, beam, wcs = _position_inputs()
    baseline = direct_observable_pixel_centroid(
        signal, rms, support, beam, wcs
    )
    doubled = direct_observable_pixel_centroid(
        signal, 2.0 * rms, support, beam, wcs
    )

    assert np.asarray(doubled.pixel_covariance) == pytest.approx(
        4.0 * np.asarray(baseline.pixel_covariance)
    )


def test_direct_centroid_rejects_misalignment_and_reports_unavailable() -> (
    None
):
    """Invalid shapes and non-positive supported flux fail explicitly."""
    signal, rms, support, beam, wcs = _position_inputs()

    with pytest.raises(ValueError, match="must align"):
        direct_observable_pixel_centroid(
            signal,
            rms[:-1],
            support,
            beam,
            wcs,
        )

    unavailable = direct_observable_pixel_centroid(
        np.zeros_like(signal),
        rms,
        support,
        beam,
        wcs,
    )

    assert unavailable.available is False
    assert np.isnan(unavailable.position_xy_pixels).all()
    fallback = covariance_gated_model_assistance(unavailable, (7.0, 7.0))
    assert fallback.available is False
    assert fallback.disposition == "model-unavailable-fallback"


def test_model_assistance_is_covariance_gated_and_falls_back() -> None:
    """Unavailable or inconsistent models cannot move catalogue position."""
    signal, rms, support, beam, wcs = _position_inputs()
    direct = direct_observable_pixel_centroid(signal, rms, support, beam, wcs)

    unavailable = covariance_gated_model_assistance(direct, None)
    inconsistent = covariance_gated_model_assistance(direct, (20.0, 20.0))
    consistent = covariance_gated_model_assistance(direct, (7.01, 6.99))

    assert unavailable.position_xy_pixels == direct.position_xy_pixels
    assert unavailable.disposition == "model-unavailable-fallback"
    assert inconsistent.position_xy_pixels == direct.position_xy_pixels
    assert inconsistent.disposition == "model-inadequate-fallback"
    assert consistent.position_xy_pixels == pytest.approx((7.01, 6.99))
    assert consistent.disposition == "model-assisted"
    assert (
        np.linalg.eigvalsh(np.asarray(consistent.pixel_covariance)).min() > 0
    )


def test_cluster_bootstrap_retains_groups_from_each_sampled_image() -> None:
    """Inference resamples images while retaining their complete group rows."""
    values = np.asarray((0.0, 2.0, 8.0, 10.0), dtype=np.float64)
    images = (("a", 1), ("a", 1), ("b", 2), ("b", 2))

    point, upper = cluster_bootstrap_statistic(
        values,
        images,
        BootstrapDesign(
            statistic="median",
            resamples=10_000,
            seed=20260809,
            confidence_level=0.95,
        ),
    )

    assert point == 5.0
    assert upper == 9.0


def test_cluster_bootstrap_handles_unequal_clusters_and_bad_rows() -> None:
    """Unequal image groups use the general path and malformed input fails."""
    values = np.asarray((0.1, 0.2, 0.3), dtype=np.float64)
    design = BootstrapDesign(
        statistic="percentile-95",
        resamples=100,
        seed=20260809,
        confidence_level=0.95,
    )

    point, upper = cluster_bootstrap_statistic(
        values,
        ("image-a", "image-a", "image-b"),
        design,
    )

    assert point == pytest.approx(0.29)
    assert upper >= point
    with pytest.raises(ValueError, match="aligned non-empty"):
        cluster_bootstrap_statistic(values, ("image-a",), design)
    with pytest.raises(ValueError, match="must be finite"):
        cluster_bootstrap_statistic(
            np.asarray((0.1, np.nan)),
            ("image-a", "image-b"),
            design,
        )


def test_selection_prefers_direct_without_material_model_improvement() -> None:
    """The complex estimator needs eligibility and a 0.02-beam tail gain."""
    direct = AstrometryCandidateResult(
        candidate="direct-observable-pixel-centroid",
        covariance_scale=1.0,
        overall_percentile_95_beams=0.2,
        unavailable_fraction=0.0,
        model_unavailable_fraction=0.0,
        model_inadequate_fraction=0.0,
        endpoints_pass=True,
        coverage_pass=True,
        model_admission_pass=True,
        eligible=True,
    )
    model = replace(
        direct,
        candidate="covariance-gated-model-assisted-centroid",
        overall_percentile_95_beams=0.19,
    )

    assert (
        select_astrometry_candidate(
            direct,
            model,
            minimum_model_improvement_beams=0.02,
        )
        == "direct-observable-pixel-centroid"
    )
    assert (
        select_astrometry_candidate(
            direct,
            replace(model, overall_percentile_95_beams=0.17),
            minimum_model_improvement_beams=0.02,
        )
        == "covariance-gated-model-assisted-centroid"
    )
    assert (
        select_astrometry_candidate(
            replace(direct, eligible=False),
            model,
            minimum_model_improvement_beams=0.02,
        )
        == "covariance-gated-model-assisted-centroid"
    )
    assert (
        select_astrometry_candidate(
            replace(direct, eligible=False),
            replace(model, eligible=False),
            minimum_model_improvement_beams=0.02,
        )
        is None
    )


def _observation(
    *,
    candidate: AstrometryCandidate,
    seed: int,
    group: str,
    error: float,
    mahalanobis_squared: float,
) -> AstrometryGroupObservation:
    """Build one minimal valid compiler observation."""
    disposition = (
        "direct"
        if candidate == "direct-observable-pixel-centroid"
        else "model-assisted"
    )
    return AstrometryGroupObservation(
        dataset_identifier="astrometry-development",
        seed=seed,
        candidate=candidate,
        group_identifier=group,
        morphology=("curved-filament" if group == "curve" else "shell"),
        scale_orders=(1, 2),
        maximum_snr=7.0 if group == "curve" else 25.0,
        available=True,
        position_xy_pixels=(10.0, 10.0),
        reference_position_xy_pixels=(10.0, 10.0),
        position_offset_xy_beams=(error, 0.0),
        position_error_beams=error,
        pixel_covariance=((1.0, 0.0), (0.0, 1.0)),
        sky_covariance_degrees=((1e-6, 0.0), (0.0, 1e-6)),
        covariance_positive_definite=True,
        mahalanobis_squared=mahalanobis_squared,
        touches_image_edge=group == "curve",
        intersects_invalid_pixels=group == "curve",
        truncated=group == "curve",
        estimator_disposition=disposition,
        model_available=disposition == "model-assisted",
        model_adequate=disposition == "model-assisted",
        model_normalized_cost=0.5 if disposition == "model-assisted" else None,
        governed_strata=(f"morphology-{group}",),
    )


def test_development_compiler_applies_endpoint_and_coverage_conjunction() -> (
    None
):
    """Direct endpoints and 2D coverage cannot compensate for each other."""
    protocol = load_phase_five_astrometry_revision_review(_REVISION_REVIEW)
    observations = tuple(
        _observation(
            candidate=candidate,
            seed=seed,
            group=group,
            error=0.05,
            mahalanobis_squared=1.0,
        )
        for candidate in protocol.estimator_candidates
        for seed in (1, 2)
        for group in ("curve", "shell")
    )

    summary = compile_astrometry_development(observations, protocol)

    assert summary.image_count == 2
    assert summary.group_count == 4
    assert summary.endpoints
    assert all(item.passed for item in summary.endpoints)
    assert summary.coverage
    assert any(not item.passed for item in summary.coverage)
    assert all(not item.eligible for item in summary.candidates)
    assert summary.selected_candidate is None
    assert summary.confirmation_execution_authorized is False

    with pytest.raises(ValueError, match="must not be empty"):
        compile_astrometry_development((), protocol)
    with pytest.raises(ValueError, match="missing astrometry candidate"):
        compile_astrometry_development(observations[:4], protocol)


def test_fresh_astrometry_image_compares_both_estimators() -> None:
    """One fresh image preserves B3 masks while replacing only astrometry."""
    dataset = load_dataset_manifest(_DEVELOPMENT).datasets[0]
    review = load_phase_five_corrective_a_review(_BASE_REVIEW)

    observations = evaluate_astrometry_revision_image(
        dataset,
        recipe_index=0,
        base_review=review,
    )

    assert {item.candidate for item in observations} == {
        "direct-observable-pixel-centroid",
        "covariance-gated-model-assisted-centroid",
    }
    assert {item.morphology for item in observations} >= {
        "curved-filament",
        "diffuse",
        "filament",
        "mixed-compact-extended",
        "shell",
    }
    available = tuple(item for item in observations if item.available)
    assert available
    assert all(item.covariance_positive_definite for item in available)
    assert all(np.isfinite(item.mahalanobis_squared) for item in available)
    assert all(item.position_error_beams is not None for item in available)
