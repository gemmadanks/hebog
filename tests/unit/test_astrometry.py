# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Analytic WCS, ellipse, deconvolution, and uncertainty tests."""

from __future__ import annotations

import pickle
from dataclasses import fields, replace

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms import astrometry
from hebog.algorithms.astrometry import (
    celestial_wcs_from_header_text,
    compact_geometries_from_wcs,
    compact_geometry_at_pixel,
    compact_geometry_from_wcs,
    deconvolve_gaussian_shapes,
    local_tangent_plane_transform,
    local_tangent_plane_transform_from_wcs,
    local_tangent_plane_transforms_from_wcs,
    moment_equivalent_gaussian_shape,
    restoring_beam_in_icrs,
    restoring_beams_in_icrs,
    transform_compact_fit_at_tangent,
)
from hebog.data_models.astrometry import (
    CelestialCompactGaussianFit,
    LocalTangentPlaneTransform,
)
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


def _transform(
    fit: ValidCompactGaussianFit,
    metadata: ImageMetadata,
    **policy: float,
) -> CelestialCompactGaussianFit:
    """Transform one fit at the tangent plane of its published position."""
    return transform_compact_fit_at_tangent(
        fit,
        metadata.beam,
        local_tangent_plane_transform(metadata, fit.parameters.centroid_xy),
        **policy,
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
    restoring_beam = geometry.restoring_beam_covariance_pixels_squared
    assert correlation is not None
    assert restoring_beam is not None
    assert restoring_beam == pytest.approx(correlation)
    covariance = np.asarray(
        [[correlation[0], correlation[1]], [correlation[1], correlation[2]]]
    )
    assert np.linalg.det(covariance) > 0


_ZENITHAL_REFERENCE_PIXEL = 1000.0


def _zenithal_wcs(
    projection: str,
    reference_sky_degrees: tuple[float, float],
    pixel_scale_degrees: float,
) -> WCS:
    """Return an ICRS zenithal WCS whose reference is pixel (1000, 1000)."""
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = [f"RA---{projection}", f"DEC--{projection}"]
    wcs.wcs.crpix = [_ZENITHAL_REFERENCE_PIXEL + 1.0] * 2
    wcs.wcs.crval = reference_sky_degrees
    wcs.wcs.cdelt = [-pixel_scale_degrees, pixel_scale_degrees]
    wcs.wcs.radesys = "ICRS"
    return wcs


def _zenithal_stretches(
    projection: str, plane_radius_radians: float
) -> tuple[float, float]:
    """Return the sky's radial and tangential stretch of the plane, sorted.

    A plane radius ``r`` lies ``atan(r)`` from the reference for TAN and
    ``asin(r)`` for SIN, so a radial step is stretched by the derivative of
    that angle and a tangential one by the angle's sine over ``r``.
    """
    if projection == "TAN":
        cosine = 1.0 / np.hypot(1.0, plane_radius_radians)
        stretches = (cosine**2, cosine)
    else:
        stretches = (1.0 / np.sqrt(1.0 - plane_radius_radians**2), 1.0)
    return (min(stretches), max(stretches))


@pytest.mark.parametrize("batched", (False, True), ids=("single", "batched"))
@pytest.mark.parametrize(
    ("projection", "reference_sky_degrees", "pixel_scale_arcsec"),
    (
        # The beam-sampling study's geometry.
        ("SIN", (180.0, 45.0), 1.5),
        ("SIN", (359.9, 60.0), 0.1),
        ("TAN", (12.3, -30.0), 6.0),
        ("TAN", (250.0, 85.0), 60.0),
    ),
)
def test_local_jacobian_matches_the_projection_to_round_off(
    projection: str,
    reference_sky_degrees: tuple[float, float],
    pixel_scale_arcsec: float,
    batched: bool,
) -> None:
    """The finite difference is good to 1e-9 of the scale on any platform.

    Zenithal projections stretch the sky by known factors of the plane
    radius, so the Jacobian's singular values are known at every pixel, and
    at the reference pixel it is the CD matrix itself. A step of 1e-3 pixel
    was 2e-8 out on the study geometry and up to 1e-6 at 0.1 arcsec pixels,
    by amounts that differed between Linux and macOS.
    """
    scale = pixel_scale_arcsec / 3600.0
    wcs = _zenithal_wcs(projection, reference_sky_degrees, scale)
    reference = _ZENITHAL_REFERENCE_PIXEL
    positions = (
        (reference, reference),
        (reference + 0.5, reference - 0.25),
        (reference + 700.0, reference - 300.0),
        (0.0, 0.0),
        (2 * reference, 2 * reference),
    )

    transforms = (
        local_tangent_plane_transforms_from_wcs(wcs, positions)
        if batched
        else tuple(
            local_tangent_plane_transform_from_wcs(wcs, position)
            for position in positions
        )
    )

    np.testing.assert_allclose(
        np.asarray(transforms[0].jacobian_degrees_per_pixel) / scale,
        ((-1.0, 0.0), (0.0, 1.0)),
        rtol=0.0,
        atol=1e-9,
    )
    for (x, y), transform in zip(positions, transforms, strict=True):
        plane_radius = np.hypot(x - reference, y - reference) * np.deg2rad(
            scale
        )
        stretches = np.linalg.svd(
            np.asarray(transform.jacobian_degrees_per_pixel) / scale,
            compute_uv=False,
        )
        np.testing.assert_allclose(
            np.sort(stretches),
            _zenithal_stretches(projection, plane_radius),
            rtol=1e-9,
        )


_ENTRY_POINTS = ("single", "batched", "empty-batch")


def _tangent_transforms(
    wcs: WCS, entry_point: str
) -> tuple[LocalTangentPlaneTransform, ...]:
    """Return the transforms at the origin through one entry point.

    An empty batch converts nothing but still checks the pixel scale, as
    the beam rotation checks the frame.
    """
    if entry_point == "single":
        return (local_tangent_plane_transform_from_wcs(wcs, (0.0, 0.0)),)
    positions = ((0.0, 0.0),) if entry_point == "batched" else ()
    return local_tangent_plane_transforms_from_wcs(wcs, positions)


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_local_jacobian_refuses_a_pixel_scale_that_underflows(
    entry_point: str,
) -> None:
    """A zero scale has no step in pixels, so it is refused."""
    wcs = _zenithal_wcs("SIN", (10.0, 20.0), 1e-300)

    with pytest.raises(ValueError, match="finite, positive pixel scale"):
        _tangent_transforms(wcs, entry_point)


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_local_jacobian_refuses_a_pixel_scale_that_overflows(
    entry_point: str,
) -> None:
    """An infinite scale makes a zero step, so it is refused, not divided by.

    NumPy reports the overflow while Astropy squares the scale matrix.
    """
    wcs = _zenithal_wcs("SIN", (10.0, 20.0), 1e200)

    with (
        pytest.warns(RuntimeWarning, match="overflow"),
        pytest.raises(ValueError, match="finite, positive pixel scale"),
    ):
        _tangent_transforms(wcs, entry_point)


def test_moment_shape_uses_explicit_local_wcs_covariance() -> None:
    """A non-square local Jacobian maps pixel moments into sky axes."""
    transform = local_tangent_plane_transform(_metadata(), (50.0, 40.0))

    shape = moment_equivalent_gaussian_shape(
        np.diag((9.0, 4.0)),
        transform,
    )

    assert shape.major_fwhm_degrees == pytest.approx(
        3.0 * _FWHM_PER_SIGMA * 0.001
    )
    assert shape.minor_fwhm_degrees == pytest.approx(
        2.0 * _FWHM_PER_SIGMA * 0.001
    )


def test_moment_shape_preserves_a_circular_covariance() -> None:
    """An isotropic moment remains circular under a square local WCS."""
    transform = local_tangent_plane_transform(_metadata(), (50.0, 40.0))

    shape = moment_equivalent_gaussian_shape(np.eye(2) * 4.0, transform)

    assert shape.major_fwhm_degrees == pytest.approx(
        2.0 * _FWHM_PER_SIGMA * 0.001
    )
    assert shape.minor_fwhm_degrees == pytest.approx(shape.major_fwhm_degrees)


@pytest.mark.parametrize("east_per_north_pixel", (-1e-12, 1e-12))
def test_moment_shape_reads_a_north_axis_as_zero_on_either_side(
    east_per_north_pixel: float,
) -> None:
    """A major axis a round-off either side of north is 0, never 180."""
    transform = replace(
        local_tangent_plane_transform(_metadata(), (50.0, 40.0)),
        jacobian_degrees_per_pixel=(
            (-0.001, east_per_north_pixel),
            (0.0, 0.001),
        ),
    )

    shape = moment_equivalent_gaussian_shape(np.diag((4.0, 9.0)), transform)

    assert shape.position_angle_degrees == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize(
    "covariance",
    (
        np.ones(3),
        np.asarray(((1.0, np.nan), (np.nan, 1.0))),
        np.asarray(((1.0, 0.5), (0.0, 1.0))),
        np.asarray(((1.0, 0.0), (0.0, 0.0))),
    ),
)
def test_moment_shape_rejects_ambiguous_covariance(
    covariance: np.ndarray,
) -> None:
    """Malformed or singular moments never become catalogue ellipses."""
    transform = local_tangent_plane_transform(_metadata(), (50.0, 40.0))

    with pytest.raises(ValueError, match="moment covariance"):
        moment_equivalent_gaussian_shape(covariance, transform)

    with pytest.raises(ValueError, match="celestial WCS"):
        local_tangent_plane_transform_from_wcs(WCS(), (0.0, 0.0))


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

    result = _transform(_fit(uncertainty=uncertainty), metadata)

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
        0.0002,
        rel=1e-5,
    )
    assert result.position.declination_error_degrees == pytest.approx(0.0003)
    assert result.fitted_flux.peak_flux_error_jy_per_beam == 0.0005
    assert result.fitted_flux.integrated_flux_error_jy == pytest.approx(
        0.001 * result.fitted_flux.integrated_flux_jy / 0.02
    )
    assert result.fitted_flux.local_rms_jy_per_beam == 0.0015
    assert result.fitted_shape.major_fwhm_error_degrees is None
    assert "shape-uncertainty-unavailable" in result.quality_flags


def test_transform_applies_integrated_flux_bias_correction() -> None:
    """A recorded calibration shifts total flux without changing its error."""
    uncertainty = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.0005,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.09,
        integrated_flux_error_jy=0.001,
        integrated_flux_bias_correction_sigma=0.075,
    )
    uncorrected = _transform(
        _fit(
            uncertainty=replace(
                uncertainty,
                integrated_flux_bias_correction_sigma=0.0,
            )
        ),
        _metadata(),
    )

    corrected = _transform(
        _fit(uncertainty=uncertainty),
        _metadata(),
    )
    uncorrected_error = uncorrected.fitted_flux.integrated_flux_error_jy
    assert uncorrected_error is not None

    assert corrected.fitted_flux.integrated_flux_error_jy == pytest.approx(
        uncorrected_error
    )
    assert corrected.fitted_flux.integrated_flux_jy == pytest.approx(
        uncorrected.fitted_flux.integrated_flux_jy - 0.075 * uncorrected_error
    )
    assert corrected.fitted_flux.peak_flux_jy_per_beam == (
        uncorrected.fitted_flux.peak_flux_jy_per_beam
    )
    assert "fitted-integrated-flux-bias-corrected" in (corrected.quality_flags)


def test_transform_rejects_non_positive_bias_corrected_flux() -> None:
    """A malformed external fit cannot publish a non-positive total."""
    uncertainty = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.0005,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.09,
        integrated_flux_error_jy=0.1,
        integrated_flux_bias_correction_sigma=0.49,
    )

    with pytest.raises(ValueError, match="non-positive flux"):
        _transform(
            _fit(uncertainty=uncertainty),
            _metadata(),
        )


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


@pytest.mark.parametrize("position_angle_degrees", (0.0, 37.0, 89.0, 143.0))
@pytest.mark.parametrize(
    "intrinsic_axes",
    ((0.3, 0.2), (1.5, 0.4), (4.0, 3.0)),
)
def test_deconvolution_is_rotation_invariant_across_resolution_scales(
    position_angle_degrees: float,
    intrinsic_axes: tuple[float, float],
) -> None:
    """Aligned beam removal recovers continuous sizes and sky angles."""
    beam = RestoringBeam(3.0, 2.0, position_angle_degrees)
    intrinsic_major, intrinsic_minor = intrinsic_axes
    fitted = GaussianShape(
        major_fwhm_degrees=np.hypot(beam.major_fwhm_degrees, intrinsic_major),
        minor_fwhm_degrees=np.hypot(beam.minor_fwhm_degrees, intrinsic_minor),
        position_angle_degrees=position_angle_degrees,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )

    result = deconvolve_gaussian_shapes(
        fitted,
        beam,
        relative_tolerance=1e-10,
    )

    assert result.status == "resolved"
    assert result.shape is not None
    assert result.shape.major_fwhm_degrees == pytest.approx(intrinsic_major)
    assert result.shape.minor_fwhm_degrees == pytest.approx(intrinsic_minor)
    assert result.shape.position_angle_degrees == pytest.approx(
        position_angle_degrees
    )


def test_deconvolution_distinguishes_unresolved_and_marginal() -> None:
    """One positive physical axis remains identifiable without an ellipse."""
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
    assert marginal.status == "major-axis-only"
    assert marginal.shape is None
    assert marginal.major_axis_fwhm_degrees == pytest.approx(
        np.sqrt(3.5**2 - 3.0**2)
    )
    assert marginal.quality_flags == (
        "major-axis-only",
        "marginal-deconvolution",
    )


def test_axis_uncertainty_censors_only_unidentified_minor_axis() -> None:
    """A significant major axis does not publish a noisy minor ellipse."""
    uncertainty = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.00005,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.04,
        integrated_flux_error_jy=0.0001,
        shape_parameter_covariance=(
            0.05**2,
            0.0,
            0.0,
            0.5**2,
            0.0,
            np.deg2rad(0.5) ** 2,
        ),
    )

    result = _transform(
        _fit(uncertainty=uncertainty),
        _metadata(),
        extension_significance_sigma=2.0,
        deconvolution_axis_significance_sigma=2.0,
    )

    assert result.deconvolution_status == "major-axis-only"
    assert result.deconvolved_shape is None
    assert result.deconvolved_major_fwhm_degrees is not None
    assert result.deconvolved_major_fwhm_degrees > 0
    assert "major-axis-only" in result.quality_flags
    assert "minor-axis-not-significant" in result.quality_flags


def test_missing_formal_covariance_produces_null_errors_and_flag() -> None:
    """Unknown position and flux errors remain absent rather than zero."""
    result = _transform(_fit(), _metadata())

    assert result.position.right_ascension_error_degrees is None
    assert result.position.declination_error_degrees is None
    assert result.fitted_flux.peak_flux_error_jy_per_beam is None
    assert result.fitted_flux.integrated_flux_error_jy is None
    assert "position-flux-uncertainty-unavailable" in result.quality_flags


@pytest.mark.parametrize("angle", (0.0, 89.99999, 179.99999))
def test_fitted_shape_errors_follow_native_covariance_across_pa_wrap(
    angle: float,
) -> None:
    """Position-angle wrapping must not amplify a local covariance."""
    uncertainty = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.00005,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.04,
        integrated_flux_error_jy=0.0001,
        shape_parameter_covariance=(0.05**2, 0.0, 0.0, 0.03**2, 0.0, 0.01**2),
    )
    result = _transform(
        _fit(angle_degrees=angle, uncertainty=uncertainty),
        _metadata(),
    )
    assert result.fitted_shape.major_fwhm_error_degrees == pytest.approx(
        _FWHM_PER_SIGMA * 0.001 * 0.05,
        rel=1e-4,
    )
    assert result.fitted_shape.minor_fwhm_error_degrees == pytest.approx(
        _FWHM_PER_SIGMA * 0.001 * 0.03,
        rel=1e-4,
    )
    assert result.fitted_shape.position_angle_error_degrees == pytest.approx(
        np.rad2deg(0.01),
        rel=1e-4,
    )


@pytest.mark.parametrize(
    "case", ("circular", "invalid-covariance", "large-error")
)
def test_native_shape_error_boundary_remains_explicit(case: str) -> None:
    """Unidentified angles and invalid propagated variances are unavailable."""
    covariance = (0.0025, 0.0, 0.0, 0.0009, 0.0, 0.0001)
    if case == "invalid-covariance":
        covariance = (-1.0, 0.0, 0.0, -1.0, 0.0, -1.0)
    elif case == "large-error":
        covariance = (0.0025, 0.0, 0.0, 1e10, 0.0, 0.0001)
    uncertainty = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.001,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.04,
        integrated_flux_error_jy=0.001,
        shape_parameter_covariance=covariance,
    )
    fitted = _fit(
        major_sigma_pixels=2.2,
        minor_sigma_pixels=2.2 if case == "circular" else 1.4,
        uncertainty=uncertainty,
    )
    shape = GaussianShape(
        major_fwhm_degrees=2.2 * _FWHM_PER_SIGMA * 0.001,
        minor_fwhm_degrees=fitted.parameters.minor_sigma_pixels
        * _FWHM_PER_SIGMA
        * 0.001,
        position_angle_degrees=90.0,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )
    projected = astrometry._fitted_shape_with_errors(  # pyright: ignore[reportPrivateUsage]
        shape, fitted, np.eye(2) * 0.001
    )
    if case in {"circular", "invalid-covariance"}:
        assert projected == shape
    else:
        assert projected.major_fwhm_error_degrees is not None
        assert projected.minor_fwhm_error_degrees is not None
        assert np.isfinite(projected.major_fwhm_error_degrees)
        assert np.isfinite(projected.minor_fwhm_error_degrees)


def test_extension_requires_two_sigma_flux_ratio_significance() -> None:
    """Noisy positive deconvolution is not evidence of physical extension."""
    uncertain = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.01,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.04,
        integrated_flux_error_jy=0.02,
    )

    result = _transform(
        _fit(uncertainty=uncertain),
        _metadata(),
        extension_significance_sigma=2.0,
    )

    assert result.deconvolution_status == "unresolved"
    assert result.deconvolved_shape is None
    assert "extension-not-significant" in result.quality_flags
    # An unresolved fit still publishes its fitted total, never its peak.
    assert "flux" not in {
        field.name for field in fields(CelestialCompactGaussianFit)
    }
    assert result.fitted_flux.integrated_flux_jy > (
        result.fitted_flux.peak_flux_jy_per_beam
    )
    assert result.fitted_flux.integrated_flux_error_jy != (
        result.fitted_flux.peak_flux_error_jy_per_beam
    )


def test_default_extension_policy_requires_five_sigma() -> None:
    """Catalogue extension is a high-confidence morphology decision."""
    uncertainty = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.0025,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.04,
        integrated_flux_error_jy=0.005,
    )

    result = _transform(
        _fit(uncertainty=uncertainty),
        _metadata(),
    )

    assert result.deconvolution_status == "unresolved"
    assert result.deconvolved_shape is None
    assert "extension-not-significant" in result.quality_flags


def test_extension_ratio_uses_amplitude_integral_covariance() -> None:
    """Shared amplitude uncertainty is not counted twice in an area ratio."""
    uncertainty = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.0025,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.04,
        integrated_flux_error_jy=0.005,
        amplitude_integrated_flux_covariance_jy_squared_per_beam=1.25e-5,
        shape_parameter_covariance=(
            0.01**2,
            0.0,
            0.0,
            0.01**2,
            0.0,
            np.deg2rad(0.1) ** 2,
        ),
    )

    result = _transform(
        _fit(uncertainty=uncertainty),
        _metadata(),
    )

    assert result.deconvolution_status == "resolved"
    assert result.deconvolved_shape is not None
    assert "extension-not-significant" not in result.quality_flags


def test_geometrically_unresolved_fit_remains_unresolved() -> None:
    """The significance rule preserves an already beam-compatible shape."""
    uncertainty = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.0001,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.04,
        integrated_flux_error_jy=0.0002,
    )

    result = _transform(
        _fit(
            major_sigma_pixels=1.0,
            minor_sigma_pixels=0.8,
            uncertainty=uncertainty,
        ),
        _metadata(),
    )

    assert result.deconvolution_status == "unresolved"
    assert result.quality_flags.count("unresolved") == 1
    assert "extension-not-significant" not in result.quality_flags
    assert result.fitted_flux.integrated_flux_jy != (
        result.fitted_flux.peak_flux_jy_per_beam
    )


def test_significant_extension_retains_fitted_total_flux_and_shape() -> None:
    """A clear integrated-to-peak excess retains resolved measurements."""
    precise = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.00005,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.04,
        integrated_flux_error_jy=0.0001,
        shape_parameter_covariance=(
            0.01**2,
            0.0,
            0.0,
            0.01**2,
            0.0,
            np.deg2rad(0.1) ** 2,
        ),
    )

    result = _transform(
        _fit(uncertainty=precise),
        _metadata(),
        extension_significance_sigma=2.0,
    )

    assert result.deconvolution_status == "resolved"
    assert result.deconvolved_shape is not None
    assert (
        result.fitted_flux.integrated_flux_jy
        > result.fitted_flux.peak_flux_jy_per_beam
    )


def test_missing_shape_covariance_makes_deconvolution_unavailable() -> None:
    """Flux evidence alone cannot make an intrinsic ellipse identifiable."""
    uncertainty = GaussianFitUncertainty(
        amplitude_error_jy_per_beam=0.00005,
        centroid_covariance_xx_pixels_squared=0.04,
        centroid_covariance_xy_pixels_squared=0.0,
        centroid_covariance_yy_pixels_squared=0.04,
        integrated_flux_error_jy=0.0001,
    )

    result = _transform(
        _fit(uncertainty=uncertainty),
        _metadata(),
        extension_significance_sigma=2.0,
    )

    assert result.deconvolution_status == "unavailable"
    assert result.deconvolved_shape is None
    assert result.deconvolved_major_fwhm_degrees is None
    assert "deconvolution-uncertainty-unavailable" in result.quality_flags


def test_missing_candidate_uncertainty_makes_classification_unavailable() -> (
    None
):
    """A noisy candidate without flux errors cannot claim extension."""
    fit = replace(_fit(), quality_flags=("uncertainty-unavailable",))

    result = _transform(fit, _metadata())

    assert result.deconvolution_status == "unavailable"
    assert result.deconvolved_shape is None
    assert "deconvolution-uncertainty-unavailable" in result.quality_flags


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_transform_rejects_invalid_extension_significance(
    value: float,
) -> None:
    """The catalogue boundary uses an explicit positive finite sigma rule."""
    with pytest.raises(ValueError, match="extension_significance_sigma"):
        _transform(
            _fit(),
            _metadata(),
            extension_significance_sigma=value,
        )


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


def test_astrometry_rejects_a_frame_other_than_icrs() -> None:
    """The reviewed compact scope never infers a coordinate frame."""
    metadata = _metadata()
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

    with pytest.raises(ValueError, match="ICRS"):
        _transform(_fit(), wrong_frame)


def test_header_text_rebuilds_a_bit_identical_celestial_wcs() -> None:
    """Task payloads carry header text because a WCS is not exact.

    Astropy pickles a :class:`~astropy.wcs.WCS` through a FITS header it
    formats itself, which perturbs the inverse transform in its last bits.
    The second assertion keeps that reason honest: if Astropy ever pickles a
    WCS exactly, this test fails and the workaround can go.
    """
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = 96
    header["NAXIS2"] = 48
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 48.5
    header["CRPIX2"] = 24.5
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    expected = WCS(header, relax=True).celestial
    sky = expected.wcs_pix2world(
        np.asarray([[0.0, 0.0], [10.5, 20.25], [95.0, 47.0]]), 0
    )

    rebuilt = celestial_wcs_from_header_text(
        pickle.loads(pickle.dumps(header.tostring()))
    )
    cycled = pickle.loads(pickle.dumps(expected))

    np.testing.assert_array_equal(
        rebuilt.wcs_world2pix(sky, 0), expected.wcs_world2pix(sky, 0)
    )
    assert not np.array_equal(
        cycled.wcs_world2pix(sky, 0), expected.wcs_world2pix(sky, 0)
    )


def _fk5_celestial_wcs() -> WCS:
    """Return an FK5 WCS, so the beam rotation does real work."""
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.crpix = [50.0, 40.0]
    wcs.wcs.crval = [83.0, -5.0]
    wcs.wcs.cd = np.diag([-0.001, 0.001])
    wcs.wcs.equinox = 2000.0
    wcs.wcs.radesys = "FK5"
    return wcs


def _sample_positions() -> tuple[tuple[float, float], ...]:
    """Return positions spread across the plane, including its corners."""
    generator = np.random.default_rng(11)
    scattered = zip(
        generator.uniform(1.0, 99.0, 24),
        generator.uniform(1.0, 79.0, 24),
        strict=True,
    )
    return (
        (0.0, 0.0),
        (99.0, 79.0),
        (49.5, 39.5),
        *((float(x), float(y)) for x, y in scattered),
    )


def test_batched_tangent_transforms_equal_one_call_each() -> None:
    """Batching only amortises Astropy's per-call frame machinery.

    Astropy applies the same element-wise transform to one coordinate or to
    many, so the batch must agree exactly, not approximately.
    """
    wcs = _fk5_celestial_wcs()
    positions = _sample_positions()

    batched = local_tangent_plane_transforms_from_wcs(wcs, positions)

    assert len(batched) == len(positions)
    assert batched == tuple(
        local_tangent_plane_transform_from_wcs(wcs, position)
        for position in positions
    )


def test_batched_beam_rotations_equal_one_call_each() -> None:
    """The FK5 beam rotation must agree exactly across the batch."""
    wcs = _fk5_celestial_wcs()
    beam = RestoringBeam(
        major_fwhm_degrees=0.004,
        minor_fwhm_degrees=0.002,
        position_angle_degrees=37.0,
    )
    positions = _sample_positions()

    batched = restoring_beams_in_icrs(beam, wcs, positions)

    assert {rotated.position_angle_degrees for rotated in batched} != {
        beam.position_angle_degrees
    }, "an FK5 WCS must actually rotate the beam"
    assert batched == tuple(
        restoring_beam_in_icrs(beam, wcs, position) for position in positions
    )


def test_batched_geometries_equal_one_call_each() -> None:
    """The composed geometry must agree exactly across the batch."""
    wcs = _fk5_celestial_wcs()
    beam = RestoringBeam(
        major_fwhm_degrees=0.004,
        minor_fwhm_degrees=0.002,
        position_angle_degrees=37.0,
    )
    positions = _sample_positions()

    assert compact_geometries_from_wcs(beam, wcs, positions) == tuple(
        compact_geometry_from_wcs(beam, wcs, position)
        for position in positions
    )


def test_batched_astrometry_of_no_positions_is_empty() -> None:
    """A batch with no objects converts no coordinates."""
    wcs = _fk5_celestial_wcs()
    beam = RestoringBeam(
        major_fwhm_degrees=0.004,
        minor_fwhm_degrees=0.002,
        position_angle_degrees=37.0,
    )

    assert local_tangent_plane_transforms_from_wcs(wcs, ()) == ()
    assert restoring_beams_in_icrs(beam, wcs, ()) == ()
    assert compact_geometries_from_wcs(beam, wcs, ()) == ()


def test_batched_astrometry_requires_a_celestial_wcs() -> None:
    """A batch must fail closed exactly as one position does."""
    beam = RestoringBeam(
        major_fwhm_degrees=0.004,
        minor_fwhm_degrees=0.002,
        position_angle_degrees=37.0,
    )
    with pytest.raises(ValueError, match="celestial"):
        local_tangent_plane_transforms_from_wcs(WCS(), ((0.0, 0.0),))
    with pytest.raises(ValueError, match="celestial"):
        restoring_beams_in_icrs(beam, WCS(), ((0.0, 0.0),))


def test_batched_beam_rotation_rejects_an_unsupported_frame() -> None:
    """An unsupported frame fails closed even when the batch is empty.

    The frame is a property of the WCS, not of the objects in one batch, so
    an empty batch must not be a way to pass an unsupported one.
    """
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["GLON-TAN", "GLAT-TAN"]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.crpix = [50.0, 40.0]
    wcs.wcs.crval = [120.0, 30.0]
    wcs.wcs.cd = np.diag([-0.001, 0.001])
    beam = RestoringBeam(
        major_fwhm_degrees=0.004,
        minor_fwhm_degrees=0.002,
        position_angle_degrees=37.0,
    )

    with pytest.raises(ValueError, match="ICRS or FK5"):
        restoring_beams_in_icrs(beam, wcs, ())
    with pytest.raises(ValueError, match="ICRS or FK5"):
        restoring_beams_in_icrs(beam, wcs, ((10.0, 10.0),))


@pytest.mark.parametrize("declination", (0.0, -30.0, 45.0, 60.0, 85.0))
def test_position_errors_are_great_circle_angles(declination: float) -> None:
    """One pixel uncertainty gives one sky error, wherever the field points.

    `E_RA` is a great-circle angle, so the same pixel covariance under the same
    pixel scale must give the same error at every declination. Dividing by
    cos(dec) to report an error on the RA coordinate would scale this by
    1/cos(dec), which is what pinned PyBDSF `c70103be3` does not do and what
    Rapthor's fixed 2-arcsecond astrometry cut does not expect.
    """
    result = _transform(
        _fit(
            uncertainty=GaussianFitUncertainty(
                amplitude_error_jy_per_beam=0.0005,
                centroid_covariance_xx_pixels_squared=0.25,
                centroid_covariance_xy_pixels_squared=0.0,
                centroid_covariance_yy_pixels_squared=0.25,
                integrated_flux_error_jy=0.001,
            )
        ),
        _metadata(reference_sky_degrees=(180.0, declination)),
    )

    assert result.position.right_ascension_error_degrees == pytest.approx(
        0.0005, rel=1e-4
    )
    assert result.position.declination_error_degrees == pytest.approx(
        0.0005, rel=1e-4
    )
