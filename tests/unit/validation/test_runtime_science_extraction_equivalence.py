"""Differential regression for the phase-neutral runtime extraction."""

# pyright: reportMissingTypeStubs=false

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms.component_measurement import (
    ComponentMeasurements,
    measure_component_models,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    build_residual_atrous_plan,
)
from hebog.algorithms.multiscale_association import (
    persistent_adjacent_scale_support,
)
from hebog.config import SourceFinderConfig
from hebog.data_models.fitting import ValidCompactGaussianFit
from hebog.data_models.images import RestoringBeam
from hebog.science.catalogues import (
    build_hebog_reconstructed_source_catalogues as build_runtime_catalogues,
)
from hebog.science.configuration import source_finder_configs
from hebog.science.continuum import (
    CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS,
    evaluate_continuum_candidate_products,
)
from hebog.science.profile import (
    configured_science_profile,
    load_continuum_science_profile,
)
from hebog.validation.contracts import PhaseFiveCorrectiveAReview
from hebog.validation.products import (
    build_hebog_reconstructed_source_catalogues as build_campaign_catalogues,
)
from hebog.validation.publication_scale_persistence import (
    evaluate_publication_scale_persistence_candidate_products,
)

_ROOT = Path(__file__).parents[3]
_SHAPE = (65, 67)
_BEAM = BeamShapePixels(5.0, 4.0, 12.0)


def _gaussian(
    *,
    amplitude: float,
    center_xy: tuple[float, float],
    sigma_xy: tuple[float, float],
) -> npt.NDArray[np.float64]:
    """Return one exact axis-aligned analytic Gaussian."""
    y_grid, x_grid = np.mgrid[: _SHAPE[0], : _SHAPE[1]]
    center_x, center_y = center_xy
    sigma_x, sigma_y = sigma_xy
    return np.asarray(
        amplitude
        * np.exp(
            -0.5
            * (
                np.square((x_grid - center_x) / sigma_x)
                + np.square((y_grid - center_y) / sigma_y)
            )
        ),
        dtype=np.float64,
    )


def _case(name: str) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    """Return one selected morphology and its observable domain."""
    valid = np.ones(_SHAPE, dtype=np.bool_)
    if name == "empty":
        image = np.zeros(_SHAPE, dtype=np.float64)
    elif name == "compact":
        image = _gaussian(
            amplitude=12.0,
            center_xy=(33.0, 31.0),
            sigma_xy=(2.0, 2.5),
        )
    elif name == "extended":
        image = _gaussian(
            amplitude=12.0,
            center_xy=(33.0, 31.0),
            sigma_xy=(6.0, 5.0),
        )
    elif name == "edge":
        image = _gaussian(
            amplitude=15.0,
            center_xy=(3.0, 31.0),
            sigma_xy=(2.0, 2.5),
        )
    elif name == "invalid-pixels":
        image = _gaussian(
            amplitude=15.0,
            center_xy=(33.0, 31.0),
            sigma_xy=(5.0, 4.0),
        )
        valid[27:30, 35:39] = False
        valid[:3, :4] = False
    else:
        image = _gaussian(
            amplitude=12.0,
            center_xy=(33.0, 31.0),
            sigma_xy=(2.0, 2.5),
        )
    return np.where(valid, image, np.nan), valid


def _header() -> fits.Header:
    """Return the common celestial and restoring-beam metadata."""
    header = fits.Header()
    for key, value in {
        "NAXIS": 2,
        "NAXIS1": _SHAPE[1],
        "NAXIS2": _SHAPE[0],
        "CTYPE1": "RA---SIN",
        "CTYPE2": "DEC--SIN",
        "CRPIX1": 34.0,
        "CRPIX2": 33.0,
        "CRVAL1": 10.0,
        "CRVAL2": -30.0,
        "CDELT1": -1.0 / 3600.0,
        "CDELT2": 1.0 / 3600.0,
        "BMAJ": 5.0 / 3600.0,
        "BMIN": 4.0 / 3600.0,
        "BPA": 12.0,
    }.items():
        header[key] = value
    return header


def _assert_candidate_products_equal(campaign: Any, runtime: Any) -> None:
    """Compare every scientific plane and hierarchy input exactly."""
    for name in (
        "direct_component_labels",
        "measurement_component_labels",
        "position_signal_jy_per_beam",
        "significant_multiscale_support",
    ):
        np.testing.assert_array_equal(
            getattr(campaign, name), getattr(runtime, name)
        )
    campaign_detection = campaign.detection
    runtime_detection = runtime.detection
    for name in ("combined_snr", "retained_mask", "component_labels"):
        np.testing.assert_array_equal(
            getattr(campaign_detection, name),
            getattr(runtime_detection, name),
        )
    assert (
        campaign_detection.component_count == runtime_detection.component_count
    )
    campaign_scales = campaign.scale_detection_planes
    runtime_scales = runtime.scale_detection_planes
    assert len(campaign_scales) == len(runtime_scales)
    for campaign_scale, runtime_scale in zip(
        campaign_scales, runtime_scales, strict=True
    ):
        assert campaign_scale.scale_order == runtime_scale.scale_order
        assert campaign_scale.detections == runtime_scale.detections
        assert campaign_scale.origin_yx == runtime_scale.origin_yx
        np.testing.assert_array_equal(
            campaign_scale.component_labels,
            runtime_scale.component_labels,
        )


def _component_measurements(
    residual: npt.NDArray[np.float64],
    rms: npt.NDArray[np.float64],
    valid: npt.NDArray[np.bool_],
    candidate_products: Any,
    config: SourceFinderConfig,
) -> ComponentMeasurements:
    """Run the installed component measurement boundary once."""
    _, deblend_config, moment_config, fit_config, _ = source_finder_configs()
    return measure_component_models(
        residual,
        rms,
        valid & np.isfinite(rms) & (rms > 0.0),
        candidate_products.direct_component_labels,
        candidate_products.measurement_component_labels,
        WCS(_header(), relax=True).celestial,
        RestoringBeam(
            _BEAM.major_fwhm_pixels / 3600.0,
            _BEAM.minor_fwhm_pixels / 3600.0,
            _BEAM.position_angle_degrees,
        ),
        moment_config,
        replace(fit_config, integrated_flux_bias_correction_sigma=0.0),
        detection_sigma=config.detection_threshold_sigma,
        island_sigma=config.island_threshold_sigma,
        minimum_pixels=config.minimum_island_pixels,
        maximum_bounds_pixels=deblend_config.maximum_compact_bounds_pixels,
        atrous_plan=build_residual_atrous_plan(
            _BEAM,
            noise_correlation=_BEAM,
        ),
        minimum_support_fraction=0.5,
    )


@pytest.mark.parametrize(
    "case_name",
    (
        "empty",
        "compact",
        "extended",
        "edge",
        "invalid-pixels",
        "custom-threshold",
    ),
)
def test_runtime_science_matches_campaign_oracle_exactly(
    case_name: str,
) -> None:
    """Preserve detection, ownership, measurement, and catalogues."""
    image, valid = _case(case_name)
    background = np.where(valid, 0.0, np.nan)
    rms = np.where(valid, 1.0, np.nan)
    payload = (
        _ROOT / "src/hebog/resources/phase_5_continuum_review.json"
    ).read_bytes()
    campaign_review = PhaseFiveCorrectiveAReview.model_validate_json(payload)
    runtime_review = load_continuum_science_profile(payload)
    config = SourceFinderConfig(5.0, 3.0, 7)
    if case_name == "custom-threshold":
        config = SourceFinderConfig(8.0, 6.0, 7)
        campaign_review = campaign_review.model_copy(
            update={
                "matrix": campaign_review.matrix.model_copy(
                    update={"detection_sigma": 8.0, "island_sigma": 6.0}
                )
            }
        )
        runtime_review = configured_science_profile(runtime_review, config)
    campaign = evaluate_publication_scale_persistence_candidate_products(
        image,
        valid,
        background,
        rms,
        beam=_BEAM,
        review=campaign_review,
    )
    runtime = evaluate_continuum_candidate_products(
        image,
        valid,
        background,
        rms,
        beam=_BEAM,
        review=runtime_review,
    )
    _assert_candidate_products_equal(campaign, runtime)
    if case_name == "empty":
        return

    common_args = (
        image,
        background,
        valid,
    )
    measurements = _component_measurements(
        image - background,
        rms,
        valid,
        campaign,
        config,
    )
    assert measurements.measurement_support is not None
    assert measurements.fits
    assert all(
        isinstance(fitted, ValidCompactGaussianFit)
        for _, fitted in measurements.fits
    )
    assert measurements.compact_groups
    raw_persistent_support = persistent_adjacent_scale_support(
        campaign.scale_detection_planes
    )
    assert np.any(measurements.measurement_support & ~raw_persistent_support)
    campaign_catalogues = build_campaign_catalogues(
        *common_args,
        campaign.measurement_component_labels,
        campaign.direct_component_labels,
        campaign.significant_multiscale_support,
        campaign.scale_detection_planes,
        _header(),
        beam_major_fwhm_pixels=_BEAM.major_fwhm_pixels,
        beam_minor_fwhm_pixels=_BEAM.minor_fwhm_pixels,
        measurement_aperture_radius_beams=(
            CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
        ),
        position_signal_jy_per_beam=campaign.position_signal_jy_per_beam,
        component_measurements=measurements,
    )
    runtime_catalogues = build_runtime_catalogues(
        *common_args,
        runtime.measurement_component_labels,
        runtime.direct_component_labels,
        runtime.significant_multiscale_support,
        runtime.scale_detection_planes,
        _header(),
        beam_major_fwhm_pixels=_BEAM.major_fwhm_pixels,
        beam_minor_fwhm_pixels=_BEAM.minor_fwhm_pixels,
        measurement_aperture_radius_beams=(
            CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
        ),
        position_signal_jy_per_beam=runtime.position_signal_jy_per_beam,
        component_measurements=measurements,
    )
    campaign_components = [
        asdict(row) for row in campaign_catalogues.component_catalogue
    ]
    assert campaign_components == [
        asdict(row) for row in runtime_catalogues.component_catalogue
    ]
    assert [asdict(row) for row in campaign_catalogues.source_catalogue] == [
        asdict(row) for row in runtime_catalogues.source_catalogue
    ]
    assert campaign_catalogues.component_catalogue
    assert all(
        "original-pixel-gaussian-model" in row.quality_flags
        for row in campaign_catalogues.component_catalogue
    )
    assert campaign_catalogues.association == runtime_catalogues.association
    assert campaign_catalogues.measurement_dispositions
    assert (
        campaign_catalogues.measurement_dispositions
        == runtime_catalogues.measurement_dispositions
    )
    assert len(campaign_catalogues.support_stages) == len(
        runtime_catalogues.support_stages
    )
    for campaign_stage, runtime_stage in zip(
        campaign_catalogues.support_stages,
        runtime_catalogues.support_stages,
        strict=True,
    ):
        assert campaign_stage[0] == runtime_stage[0]
        np.testing.assert_array_equal(campaign_stage[1], runtime_stage[1])
    np.testing.assert_array_equal(
        dict(campaign_catalogues.support_stages)["persistent"],
        raw_persistent_support | measurements.measurement_support,
    )
