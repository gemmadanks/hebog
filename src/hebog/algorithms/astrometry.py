# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Astropy WCS transforms and covariance-based beam deconvolution."""

from __future__ import annotations

from math import cos, isfinite, log, pi, sqrt

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms.measurement import (
    fitted_gaussian_integrated_flux_jy,
    gaussian_beam_solid_angle_steradians,
)
from hebog.data_models.astrometry import (
    CelestialCompactGaussianFit,
    GaussianDeconvolution,
    LocalTangentPlaneTransform,
)
from hebog.data_models.catalogues import (
    FluxMeasurement,
    GaussianShape,
    SkyPosition,
)
from hebog.data_models.fitting import ValidCompactGaussianFit
from hebog.data_models.images import ImageMetadata, RestoringBeam
from hebog.data_models.measurement import CompactMeasurementGeometry

_FINITE_DIFFERENCE_STEP_PIXELS = 1e-3
_FWHM_PER_SIGMA = 2.0 * sqrt(2.0 * log(2.0))


def _celestial_wcs(metadata: ImageMetadata) -> WCS:
    """Reconstruct an independent celestial WCS from serialized metadata."""
    header = fits.Header.fromstring(
        metadata.celestial_wcs.fits_header,
        sep="\n",
    )
    return WCS(header, relax=True).celestial


def local_tangent_plane_transform(
    metadata: ImageMetadata,
    position_xy: tuple[float, float],
) -> LocalTangentPlaneTransform:
    """Return the ICRS center and local east/north pixel Jacobian."""
    if metadata.celestial_wcs.coordinate_frame.lower() != "icrs":
        raise ValueError("compact astrometry requires an ICRS celestial WCS")
    x, y = position_xy
    wcs = _celestial_wcs(metadata)
    center = wcs.pixel_to_world(x, y).icrs
    step = _FINITE_DIFFERENCE_STEP_PIXELS
    columns: list[tuple[float, float]] = []
    for x_offset, y_offset in ((step, 0.0), (0.0, step)):
        plus = wcs.pixel_to_world(x + x_offset, y + y_offset).icrs
        minus = wcs.pixel_to_world(x - x_offset, y - y_offset).icrs
        plus_east, plus_north = center.spherical_offsets_to(plus)
        minus_east, minus_north = center.spherical_offsets_to(minus)
        columns.append(
            (
                (plus_east.degree - minus_east.degree) / (2.0 * step),
                (plus_north.degree - minus_north.degree) / (2.0 * step),
            )
        )
    jacobian = (
        (columns[0][0], columns[1][0]),
        (columns[0][1], columns[1][1]),
    )
    return LocalTangentPlaneTransform(
        position=SkyPosition(
            right_ascension_degrees=float(center.ra.degree % 360.0),
            declination_degrees=float(center.dec.degree),
            right_ascension_error_degrees=None,
            declination_error_degrees=None,
        ),
        jacobian_degrees_per_pixel=jacobian,
    )


def compact_geometry_at_pixel(
    metadata: ImageMetadata,
    position_xy: tuple[float, float],
) -> CompactMeasurementGeometry:
    """Derive reviewed local pixel and restoring-beam solid angles."""
    transform = local_tangent_plane_transform(metadata, position_xy)
    jacobian = np.asarray(
        transform.jacobian_degrees_per_pixel,
        dtype=np.float64,
    )
    pixel_area_square_degrees = abs(float(np.linalg.det(jacobian)))
    pixel_solid_angle = pixel_area_square_degrees * (pi / 180.0) ** 2
    beam_solid_angle = gaussian_beam_solid_angle_steradians(
        major_fwhm_degrees=metadata.beam.major_fwhm_degrees,
        minor_fwhm_degrees=metadata.beam.minor_fwhm_degrees,
    )
    inverse_jacobian = np.linalg.inv(jacobian)
    pixel_noise_covariance = (
        inverse_jacobian @ _sky_covariance(metadata.beam) @ inverse_jacobian.T
    )
    return CompactMeasurementGeometry(
        pixel_solid_angle_steradians=pixel_solid_angle,
        restoring_beam_solid_angle_steradians=beam_solid_angle,
        noise_correlation_covariance_pixels_squared=(
            float(pixel_noise_covariance[0, 0]),
            float(pixel_noise_covariance[0, 1]),
            float(pixel_noise_covariance[1, 1]),
        ),
    )


def _pixel_covariance(
    major_sigma_pixels: float,
    minor_sigma_pixels: float,
    angle_degrees: float,
) -> npt.NDArray[np.float64]:
    """Return `(x, y)` covariance for angle counterclockwise from +x."""
    angle = np.deg2rad(angle_degrees)
    major = np.asarray([np.cos(angle), np.sin(angle)], dtype=np.float64)
    minor = np.asarray([-np.sin(angle), np.cos(angle)], dtype=np.float64)
    return major_sigma_pixels**2 * np.outer(
        major, major
    ) + minor_sigma_pixels**2 * np.outer(minor, minor)


def _sky_covariance(
    shape: GaussianShape | RestoringBeam,
) -> npt.NDArray[np.float64]:
    """Return east/north sigma covariance for PA east of north."""
    angle = np.deg2rad(shape.position_angle_degrees)
    major = np.asarray([np.sin(angle), np.cos(angle)], dtype=np.float64)
    minor = np.asarray([np.cos(angle), -np.sin(angle)], dtype=np.float64)
    major_sigma = shape.major_fwhm_degrees / _FWHM_PER_SIGMA
    minor_sigma = shape.minor_fwhm_degrees / _FWHM_PER_SIGMA
    return major_sigma**2 * np.outer(major, major) + minor_sigma**2 * np.outer(
        minor, minor
    )


def _shape_from_sky_covariance(
    covariance: npt.NDArray[np.float64],
) -> GaussianShape:
    """Convert positive east/north covariance to ordered FWHM and PA."""
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    major_index = int(np.argmax(eigenvalues))
    minor_index = 1 - major_index
    major_vector = eigenvectors[:, major_index]
    if np.isclose(
        eigenvalues[major_index],
        eigenvalues[minor_index],
        rtol=1e-12,
        atol=0.0,
    ):
        position_angle = 0.0
    else:
        position_angle = float(
            np.rad2deg(np.arctan2(major_vector[0], major_vector[1])) % 180.0
        )
    return GaussianShape(
        major_fwhm_degrees=float(
            sqrt(eigenvalues[major_index]) * _FWHM_PER_SIGMA
        ),
        minor_fwhm_degrees=float(
            sqrt(eigenvalues[minor_index]) * _FWHM_PER_SIGMA
        ),
        position_angle_degrees=position_angle,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )


def deconvolve_gaussian_shapes(
    fitted_shape: GaussianShape,
    beam: RestoringBeam,
    *,
    relative_tolerance: float,
) -> GaussianDeconvolution:
    """Subtract beam covariance with explicit absence states."""
    if not isfinite(relative_tolerance) or not 0 < relative_tolerance < 1:
        raise ValueError("relative_tolerance must be finite and in (0, 1)")
    beam_covariance = _sky_covariance(beam)
    intrinsic = _sky_covariance(fitted_shape) - beam_covariance
    eigenvalues = np.linalg.eigvalsh(intrinsic)
    tolerance = relative_tolerance * float(
        np.max(np.linalg.eigvalsh(beam_covariance))
    )
    if float(np.max(eigenvalues)) <= tolerance:
        return GaussianDeconvolution(
            status="unresolved",
            shape=None,
            quality_flags=("unresolved",),
        )
    if float(np.min(eigenvalues)) <= tolerance:
        return GaussianDeconvolution(
            status="unresolved",
            shape=None,
            quality_flags=("marginal-deconvolution", "unresolved"),
        )
    return GaussianDeconvolution(
        status="resolved",
        shape=_shape_from_sky_covariance(intrinsic),
        quality_flags=("resolved",),
    )


def _position_with_errors(
    transform: LocalTangentPlaneTransform,
    fit: ValidCompactGaussianFit,
) -> SkyPosition:
    """Transform available centroid covariance to RA/Dec one-sigma errors."""
    uncertainty = fit.uncertainty
    if uncertainty is None:
        return transform.position
    pixel_covariance = np.asarray(
        [
            [
                uncertainty.centroid_covariance_xx_pixels_squared,
                uncertainty.centroid_covariance_xy_pixels_squared,
            ],
            [
                uncertainty.centroid_covariance_xy_pixels_squared,
                uncertainty.centroid_covariance_yy_pixels_squared,
            ],
        ],
        dtype=np.float64,
    )
    jacobian = np.asarray(transform.jacobian_degrees_per_pixel)
    tangent_covariance = jacobian @ pixel_covariance @ jacobian.T
    declination = transform.position.declination_degrees
    cosine_declination = abs(cos(np.deg2rad(declination)))
    if cosine_declination <= np.finfo(np.float64).eps:
        return transform.position
    return SkyPosition(
        right_ascension_degrees=transform.position.right_ascension_degrees,
        declination_degrees=declination,
        right_ascension_error_degrees=(
            float(sqrt(tangent_covariance[0, 0])) / cosine_declination
        ),
        declination_error_degrees=float(sqrt(tangent_covariance[1, 1])),
    )


def _extension_classification(
    geometric: GaussianDeconvolution,
    fit: ValidCompactGaussianFit,
    *,
    integrated_flux_jy: float,
    integrated_flux_error_jy: float | None,
    significance_sigma: float,
) -> GaussianDeconvolution:
    """Apply the ATLAS log flux-ratio significance rule to deconvolution."""
    if geometric.status != "resolved":
        return geometric
    uncertainty = fit.uncertainty
    if uncertainty is None:
        if "uncertainty-unavailable" not in fit.quality_flags:
            return geometric
        return GaussianDeconvolution(
            status="unavailable",
            shape=None,
            quality_flags=("deconvolution-uncertainty-unavailable",),
        )
    if integrated_flux_error_jy is None:
        raise ValueError("available fit uncertainty requires integrated error")
    parameters = fit.parameters
    flux_ratio = integrated_flux_jy / parameters.amplitude_jy_per_beam
    log_ratio_uncertainty = sqrt(
        (integrated_flux_error_jy / integrated_flux_jy) ** 2
        + (
            uncertainty.amplitude_error_jy_per_beam
            / parameters.amplitude_jy_per_beam
        )
        ** 2
    )
    if log(flux_ratio) > significance_sigma * log_ratio_uncertainty:
        return geometric
    return GaussianDeconvolution(
        status="unresolved",
        shape=None,
        quality_flags=("extension-not-significant", "unresolved"),
    )


def transform_compact_gaussian_fit(
    fit: ValidCompactGaussianFit,
    metadata: ImageMetadata,
    *,
    deconvolution_relative_tolerance: float = 1e-10,
    extension_significance_sigma: float = 5.0,
) -> CelestialCompactGaussianFit:
    """Transform a valid pixel fit into reviewed ICRS catalogue quantities."""
    if metadata.unit != "Jy/beam":
        raise ValueError("compact measurement requires image unit Jy/beam")
    if (
        not isfinite(extension_significance_sigma)
        or extension_significance_sigma <= 0
    ):
        raise ValueError(
            "extension_significance_sigma must be finite and positive"
        )
    parameters = fit.parameters
    transform = local_tangent_plane_transform(metadata, parameters.centroid_xy)
    jacobian = np.asarray(transform.jacobian_degrees_per_pixel)
    fitted_covariance = (
        jacobian
        @ _pixel_covariance(
            parameters.major_sigma_pixels,
            parameters.minor_sigma_pixels,
            parameters.major_axis_angle_degrees,
        )
        @ jacobian.T
    )
    fitted_shape = _shape_from_sky_covariance(fitted_covariance)
    geometric_deconvolution = deconvolve_gaussian_shapes(
        fitted_shape,
        metadata.beam,
        relative_tolerance=deconvolution_relative_tolerance,
    )
    geometry = compact_geometry_at_pixel(metadata, parameters.centroid_xy)
    uncertainty = fit.uncertainty
    integrated_flux = fitted_gaussian_integrated_flux_jy(
        amplitude_jy_per_beam=parameters.amplitude_jy_per_beam,
        major_sigma_pixels=parameters.major_sigma_pixels,
        minor_sigma_pixels=parameters.minor_sigma_pixels,
        geometry=geometry,
    )
    integrated_flux_error = (
        uncertainty.integrated_flux_error_jy
        * integrated_flux
        / parameters.integrated_flux_jy
        if uncertainty is not None
        else None
    )
    deconvolution = _extension_classification(
        geometric_deconvolution,
        fit,
        integrated_flux_jy=integrated_flux,
        integrated_flux_error_jy=integrated_flux_error,
        significance_sigma=extension_significance_sigma,
    )
    if deconvolution.status == "unresolved":
        reported_integrated_flux = parameters.amplitude_jy_per_beam
        reported_integrated_flux_error = (
            uncertainty.amplitude_error_jy_per_beam
            if uncertainty is not None
            else None
        )
    else:
        reported_integrated_flux = integrated_flux
        reported_integrated_flux_error = integrated_flux_error
    flux = FluxMeasurement(
        peak_flux_jy_per_beam=parameters.amplitude_jy_per_beam,
        peak_flux_error_jy_per_beam=(
            uncertainty.amplitude_error_jy_per_beam
            if uncertainty is not None
            else None
        ),
        integrated_flux_jy=reported_integrated_flux,
        integrated_flux_error_jy=reported_integrated_flux_error,
        local_rms_jy_per_beam=parameters.local_rms_jy_per_beam,
    )
    flags = set(fit.quality_flags)
    flags.add("shape-uncertainty-unavailable")
    flags.update(deconvolution.quality_flags)
    if uncertainty is None:
        flags.add("position-flux-uncertainty-unavailable")
    return CelestialCompactGaussianFit(
        pixel_fit=fit,
        position=_position_with_errors(transform, fit),
        flux=flux,
        fitted_shape=fitted_shape,
        deconvolution_status=deconvolution.status,
        deconvolved_shape=deconvolution.shape,
        quality_flags=tuple(sorted(flags)),
    )
