# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Analytic WCS, ellipse, deconvolution, and uncertainty tests."""

from __future__ import annotations

import numpy as np
import pytest
from astropy.wcs import WCS

from hebog.algorithms.astrometry import (
    compact_geometry_at_pixel,
    deconvolve_gaussian_shapes,
    local_tangent_plane_transform,
    transform_compact_gaussian_fit,
)
from hebog.data_models.astrometry import CelestialCompactGaussianFit
from hebog.data_models.catalogues import GaussianShape
from hebog.data_models.fitting import (
    FittedGaussianPixelParameters,
    GaussianFitDiagnostics,
    GaussianFitUncertainty,
    ValidCompactGaussianFit,
)
from hebog.data_models.images import CelestialWcs, ImageMetadata, RestoringBeam
from hebog.data_models.measurement import (
    GaussianMomentInitializer,
    MomentTarget,
    OwnedPixelPhotometry,
    ValidMomentMeasurement,
)

_FWHM_PER_SIGMA = 2.0 * np.sqrt(2.0 * np.log(2.0))


def _metadata(
    *,
    matrix_degrees_per_pixel: np.ndarray | None = None,
    reference_sky_degrees: tuple[float, float] = (359.99, -30.0),
    beam: RestoringBeam | None = None,
) -> ImageMetadata:
    """Return serialized two-axis TAN metadata around a pixel-center origin."""
    matrix = (
        np.asarray(matrix_degrees_per_pixel, dtype=np.float64)
        if matrix_degrees_per_pixel is not None
        else np.diag([-0.001, 0.001])
    )
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.crpix = [50.0, 40.0]
    wcs.wcs.crval = reference_sky_degrees
    wcs.wcs.cd = matrix
    header = wcs.to_header(relax=True).tostring(
        sep="\n",
        endcard=False,
        padding=False,
    )
    return ImageMetadata(
        shape_yx=(80, 100),
        unit="Jy/beam",
        beam=beam
        or RestoringBeam(
            major_fwhm_degrees=0.003,
            minor_fwhm_degrees=0.002,
            position_angle_degrees=90.0,
        ),
        celestial_wcs=CelestialWcs(
            fits_header=header,
            coordinate_frame="icrs",
        ),
        reference_frequency_hz=150_000_000.0,
    )


def _fit(
    *,
    centroid_xy: tuple[float, float] = (49.0, 39.0),
    major_sigma_pixels: float = 2.2,
    minor_sigma_pixels: float = 1.4,
    angle_degrees: float = 0.0,
    uncertainty: GaussianFitUncertainty | None = None,
) -> ValidCompactGaussianFit:
    """Return a valid pixel fit with optional formal position/flux errors."""
    target = MomentTarget(
        object_kind="deblended-region",
        object_id="island-00001-region-00001",
        island_id="island-00001",
        pixel_count=40,
    )
    moment = ValidMomentMeasurement(
        target=target,
        photometry=OwnedPixelPhotometry(
            peak_brightness_jy_per_beam=0.01,
            peak_position_xy=(49, 39),
            owned_pixel_integrated_flux_jy=0.02,
            local_rms_jy_per_beam=0.001,
            mean_brightness_jy_per_beam=0.003,
        ),
        initializer=GaussianMomentInitializer(
            amplitude_jy_per_beam=0.01,
            centroid_xy=centroid_xy,
            covariance_xx_pixels_squared=major_sigma_pixels**2,
            covariance_xy_pixels_squared=0.0,
            covariance_yy_pixels_squared=minor_sigma_pixels**2,
            major_sigma_pixels=major_sigma_pixels,
            minor_sigma_pixels=minor_sigma_pixels,
            major_axis_angle_degrees=angle_degrees,
        ),
    )
    return ValidCompactGaussianFit(
        moment=moment,
        parameters=FittedGaussianPixelParameters(
            amplitude_jy_per_beam=0.01,
            centroid_xy=centroid_xy,
            major_sigma_pixels=major_sigma_pixels,
            minor_sigma_pixels=minor_sigma_pixels,
            major_axis_angle_degrees=angle_degrees,
            integrated_flux_jy=0.02,
            local_rms_jy_per_beam=0.0015,
        ),
        uncertainty=uncertainty,
        diagnostics=GaussianFitDiagnostics(
            converged=True,
            function_evaluations=8,
            chi_squared=20.0,
            degrees_of_freedom=34,
            reduced_chi_squared=20.0 / 34.0,
            parameters_at_bound=False,
        ),
        quality_flags=(),
    )


def test_local_jacobian_handles_signed_unequal_rotated_wcs_and_ra_wrap() -> (
    None
):
    """Astropy supplies a local east/north Jacobian at zero-based centers."""
    angle = np.deg2rad(37.0)
    matrix = np.asarray(
        [
            [-0.00025 * np.cos(angle), -0.0003 * np.sin(angle)],
            [-0.00025 * np.sin(angle), 0.0003 * np.cos(angle)],
        ]
    )
    metadata = _metadata(matrix_degrees_per_pixel=matrix)

    transform = local_tangent_plane_transform(metadata, (49.0, 39.0))
    geometry = compact_geometry_at_pixel(metadata, (49.0, 39.0))

    assert 0 <= transform.position.right_ascension_degrees < 360
    assert transform.position.right_ascension_degrees == pytest.approx(359.99)
    assert transform.position.declination_degrees == pytest.approx(-30.0)
    np.testing.assert_allclose(
        np.asarray(transform.jacobian_degrees_per_pixel),
        matrix,
        rtol=0.0,
        atol=2e-10,
    )
    assert geometry.pixel_solid_angle_steradians == pytest.approx(
        abs(np.linalg.det(matrix)) * (np.pi / 180.0) ** 2,
        rel=1e-6,
    )
    correlation = geometry.noise_correlation_covariance_pixels_squared
    assert correlation is not None
    covariance = np.asarray(
        [[correlation[0], correlation[1]], [correlation[1], correlation[2]]]
    )
    assert np.linalg.det(covariance) > 0


def test_transform_uses_xy_centers_east_of_north_and_local_flux_area() -> None:
    """A fitted pixel ellipse becomes canonical ICRS shape and photometry."""
    uncertainty = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.0005,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.09,
        integrated_flux_error_jy=0.001,
    )
    metadata = _metadata(
        beam=RestoringBeam(
            major_fwhm_degrees=0.001,
            minor_fwhm_degrees=0.0008,
            position_angle_degrees=90.0,
        )
    )

    result = transform_compact_gaussian_fit(
        _fit(uncertainty=uncertainty), metadata
    )

    assert isinstance(result, CelestialCompactGaussianFit)
    assert result.fitted_shape.major_fwhm_degrees == pytest.approx(
        2.2 * _FWHM_PER_SIGMA * 0.001,
        rel=1e-6,
    )
    assert result.fitted_shape.minor_fwhm_degrees == pytest.approx(
        1.4 * _FWHM_PER_SIGMA * 0.001,
        rel=1e-6,
    )
    assert result.fitted_shape.position_angle_degrees == pytest.approx(90.0)
    assert result.position.right_ascension_error_degrees == pytest.approx(
        0.0002 / np.cos(np.deg2rad(-30.0)),
        rel=1e-5,
    )
    assert result.position.declination_error_degrees == pytest.approx(0.0003)
    assert result.flux.peak_flux_error_jy_per_beam == 0.0005
    assert result.flux.integrated_flux_error_jy == pytest.approx(
        0.001 * result.flux.integrated_flux_jy / 0.02
    )
    assert result.flux.local_rms_jy_per_beam == 0.0015
    assert result.fitted_shape.major_fwhm_error_degrees is None
    assert "shape-uncertainty-unavailable" in result.quality_flags


def test_covariance_beam_deconvolution_matches_aligned_analytic_truth() -> (
    None
):
    """Aligned Gaussian FWHM axes subtract in covariance squared."""
    fitted = GaussianShape(
        major_fwhm_degrees=5.0,
        minor_fwhm_degrees=4.0,
        position_angle_degrees=30.0,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )
    beam = RestoringBeam(
        major_fwhm_degrees=3.0,
        minor_fwhm_degrees=2.0,
        position_angle_degrees=30.0,
    )

    deconvolved = deconvolve_gaussian_shapes(
        fitted,
        beam,
        relative_tolerance=1e-10,
    )

    assert deconvolved.status == "resolved"
    assert deconvolved.shape is not None
    assert deconvolved.shape.major_fwhm_degrees == pytest.approx(4.0)
    assert deconvolved.shape.minor_fwhm_degrees == pytest.approx(np.sqrt(12.0))
    assert deconvolved.shape.position_angle_degrees == pytest.approx(30.0)


def test_deconvolution_distinguishes_unresolved_and_marginal() -> None:
    """No positive physical covariance is not represented by zero axes."""
    beam = RestoringBeam(3.0, 2.0, 0.0)
    unresolved_shape = GaussianShape(
        major_fwhm_degrees=2.9,
        minor_fwhm_degrees=1.9,
        position_angle_degrees=0.0,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )
    marginal_shape = GaussianShape(
        major_fwhm_degrees=3.5,
        minor_fwhm_degrees=1.9,
        position_angle_degrees=0.0,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )

    unresolved = deconvolve_gaussian_shapes(
        unresolved_shape, beam, relative_tolerance=1e-10
    )
    marginal = deconvolve_gaussian_shapes(
        marginal_shape, beam, relative_tolerance=1e-10
    )

    assert unresolved.status == "unresolved"
    assert unresolved.shape is None
    assert unresolved.quality_flags == ("unresolved",)
    assert marginal.status == "unresolved"
    assert marginal.shape is None
    assert marginal.quality_flags == (
        "marginal-deconvolution",
        "unresolved",
    )


def test_missing_formal_covariance_produces_null_errors_and_flag() -> None:
    """Unknown position and flux errors remain absent rather than zero."""
    result = transform_compact_gaussian_fit(_fit(), _metadata())

    assert result.position.right_ascension_error_degrees is None
    assert result.position.declination_error_degrees is None
    assert result.flux.peak_flux_error_jy_per_beam is None
    assert result.flux.integrated_flux_error_jy is None
    assert "position-flux-uncertainty-unavailable" in result.quality_flags


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), 1.0])
def test_deconvolution_rejects_invalid_relative_tolerance(
    value: float,
) -> None:
    """Marginal classification uses one explicit bounded tolerance."""
    shape = GaussianShape(
        major_fwhm_degrees=5.0,
        minor_fwhm_degrees=4.0,
        position_angle_degrees=0.0,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )
    with pytest.raises(ValueError, match="relative_tolerance"):
        deconvolve_gaussian_shapes(
            shape,
            RestoringBeam(3.0, 2.0, 0.0),
            relative_tolerance=value,
        )


def test_astrometry_rejects_wrong_unit_or_frame() -> None:
    """The reviewed compact scope never infers units or coordinate frames."""
    metadata = _metadata()
    wrong_unit = ImageMetadata(
        shape_yx=metadata.shape_yx,
        unit="K",
        beam=metadata.beam,
        celestial_wcs=metadata.celestial_wcs,
        reference_frequency_hz=metadata.reference_frequency_hz,
    )
    wrong_frame = ImageMetadata(
        shape_yx=metadata.shape_yx,
        unit=metadata.unit,
        beam=metadata.beam,
        celestial_wcs=CelestialWcs(
            fits_header=metadata.celestial_wcs.fits_header,
            coordinate_frame="galactic",
        ),
        reference_frequency_hz=metadata.reference_frequency_hz,
    )

    with pytest.raises(ValueError, match="Jy/beam"):
        transform_compact_gaussian_fit(_fit(), wrong_unit)
    with pytest.raises(ValueError, match="ICRS"):
        transform_compact_gaussian_fit(_fit(), wrong_frame)
