# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Astropy WCS transforms and covariance-based beam deconvolution."""

from __future__ import annotations

from dataclasses import replace
from math import cos, isfinite, log, pi, sqrt

import numpy as np
import numpy.typing as npt
from astropy import units as u
from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import wcs_to_celestial_frame

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
_SHAPE_AXIS_PARAMETER_COUNT = 2


def celestial_wcs_from_metadata(metadata: ImageMetadata) -> WCS:
    """Reconstruct an independent celestial WCS from serialized metadata."""
    header = fits.Header.fromstring(
        metadata.celestial_wcs.fits_header,
        sep="\n",
    )
    return WCS(header, relax=True).celestial


def local_tangent_plane_transform(
    metadata: ImageMetadata,
    position_xy: tuple[float, float],
    *,
    celestial_wcs: WCS | None = None,
) -> LocalTangentPlaneTransform:
    """Return the ICRS center and local east/north pixel Jacobian.

    ICRS and FK5 inputs are both transformed to ICRS through Astropy's frame
    tie, matching :func:`restoring_beam_in_icrs`.
    """
    if metadata.celestial_wcs.coordinate_frame.lower() not in {"icrs", "fk5"}:
        raise ValueError(
            "compact astrometry requires an ICRS or FK5 celestial WCS"
        )
    wcs = (
        celestial_wcs
        if celestial_wcs is not None
        else celestial_wcs_from_metadata(metadata)
    )
    return local_tangent_plane_transform_from_wcs(wcs, position_xy)


def local_tangent_plane_transform_from_wcs(
    celestial_wcs: WCS,
    position_xy: tuple[float, float],
) -> LocalTangentPlaneTransform:
    """Return the ICRS tangent transform from an explicit celestial WCS."""
    if not celestial_wcs.has_celestial:
        raise ValueError("astrometry requires a celestial WCS")
    x, y = position_xy
    wcs = celestial_wcs.celestial
    step = _FINITE_DIFFERENCE_STEP_PIXELS
    # One conversion for the centre and the four finite-difference
    # neighbours together. Converting them one at a time builds five sky
    # coordinates and five frame transforms per measured source, which
    # costs more than everything else in the catalogue.
    sampled = wcs.pixel_to_world(
        np.asarray([x, x + step, x - step, x, x], dtype=np.float64),
        np.asarray([y, y, y, y + step, y - step], dtype=np.float64),
    ).icrs
    center = sampled[0]
    east, north = center.spherical_offsets_to(sampled[1:])
    columns: list[tuple[float, float]] = []
    for plus, minus in ((0, 1), (2, 3)):
        columns.append(
            (
                (east[plus].degree - east[minus].degree) / (2.0 * step),
                (north[plus].degree - north[minus].degree) / (2.0 * step),
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


def moment_equivalent_gaussian_shape(
    covariance_pixels_squared: npt.ArrayLike,
    transform: LocalTangentPlaneTransform,
) -> GaussianShape:
    """Transform one positive pixel moment covariance into a sky ellipse."""
    covariance = np.asarray(covariance_pixels_squared, dtype=np.float64)
    if covariance.shape != (_SHAPE_AXIS_PARAMETER_COUNT,) * 2 or not np.all(
        np.isfinite(covariance)
    ):
        raise ValueError("moment covariance must be one finite 2-by-2 matrix")
    if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1e-14):
        raise ValueError("moment covariance must be symmetric")
    eigenvalues = np.linalg.eigvalsh(covariance)
    if float(np.min(eigenvalues)) <= 0.0:
        raise ValueError("moment covariance must be positive definite")
    jacobian = np.asarray(
        transform.jacobian_degrees_per_pixel,
        dtype=np.float64,
    )
    sky_covariance = jacobian @ covariance @ jacobian.T
    sky_eigenvalues = np.linalg.eigvalsh(sky_covariance)
    if (
        not np.all(np.isfinite(sky_covariance))
        or float(np.min(sky_eigenvalues)) <= 0.0
    ):
        raise ValueError("transformed moment covariance must be positive")
    shape = _shape_from_sky_covariance(sky_covariance)
    position_angle = shape.position_angle_degrees
    if np.isclose(position_angle, 180.0, rtol=0.0, atol=1e-6):
        position_angle = 0.0
    return GaussianShape(
        major_fwhm_degrees=shape.major_fwhm_degrees,
        minor_fwhm_degrees=shape.minor_fwhm_degrees,
        position_angle_degrees=position_angle,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )


def compact_geometry_at_pixel(
    metadata: ImageMetadata,
    position_xy: tuple[float, float],
    *,
    celestial_wcs: WCS | None = None,
    transform: LocalTangentPlaneTransform | None = None,
) -> CompactMeasurementGeometry:
    """Derive reviewed local pixel and restoring-beam solid angles."""
    local_transform = (
        transform
        if transform is not None
        else local_tangent_plane_transform(
            metadata,
            position_xy,
            celestial_wcs=celestial_wcs,
        )
    )
    return compact_geometry_from_transform(metadata.beam, local_transform)


def compact_geometry_from_transform(
    beam: RestoringBeam,
    transform: LocalTangentPlaneTransform,
) -> CompactMeasurementGeometry:
    """Derive local measurement geometry without unrelated spectral data."""
    jacobian = np.asarray(
        transform.jacobian_degrees_per_pixel,
        dtype=np.float64,
    )
    pixel_area_square_degrees = abs(float(np.linalg.det(jacobian)))
    pixel_solid_angle = pixel_area_square_degrees * (pi / 180.0) ** 2
    beam_solid_angle = gaussian_beam_solid_angle_steradians(
        major_fwhm_degrees=beam.major_fwhm_degrees,
        minor_fwhm_degrees=beam.minor_fwhm_degrees,
    )
    inverse_jacobian = np.linalg.inv(jacobian)
    pixel_noise_covariance = (
        inverse_jacobian @ _sky_covariance(beam) @ inverse_jacobian.T
    )
    covariance_values = (
        float(pixel_noise_covariance[0, 0]),
        float(pixel_noise_covariance[0, 1]),
        float(pixel_noise_covariance[1, 1]),
    )
    return CompactMeasurementGeometry(
        pixel_solid_angle_steradians=pixel_solid_angle,
        restoring_beam_solid_angle_steradians=beam_solid_angle,
        restoring_beam_covariance_pixels_squared=covariance_values,
        noise_correlation_covariance_pixels_squared=covariance_values,
    )


def restoring_beam_in_icrs(
    beam: RestoringBeam,
    celestial_wcs: WCS,
    position_xy: tuple[float, float],
) -> RestoringBeam:
    """Rotate a native equatorial FITS beam PA into local ICRS axes.

    FK5 equinox precession rotates local north along with the coordinates.
    Transform a one-arcsecond directional offset using Astropy, preserving
    the angular beam axes. ICRS returns the original beam without arithmetic.
    This boundary supports ICRS/FK5, not frames with non-rotational geometry.
    """
    if not celestial_wcs.has_celestial:
        raise ValueError("beam geometry requires a celestial WCS")
    frame = wcs_to_celestial_frame(celestial_wcs)
    if frame.name == "icrs":
        return beam
    if frame.name != "fk5":
        raise ValueError("beam geometry requires an ICRS or FK5 celestial WCS")
    center = celestial_wcs.celestial.pixel_to_world(*position_xy)
    direction = center.directional_offset_by(
        beam.position_angle_degrees * u.deg, 1.0 * u.arcsec
    )
    return replace(
        beam,
        position_angle_degrees=float(
            center.icrs.position_angle(direction.icrs).deg % 180.0
        ),
    )


def compact_geometry_from_wcs(
    beam: RestoringBeam,
    celestial_wcs: WCS,
    position_xy: tuple[float, float],
) -> CompactMeasurementGeometry:
    """Transform native beam and pixels into the same ICRS tangent basis."""
    return compact_geometry_from_transform(
        restoring_beam_in_icrs(beam, celestial_wcs, position_xy),
        local_tangent_plane_transform_from_wcs(celestial_wcs, position_xy),
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
        major_fwhm = float(sqrt(float(np.max(eigenvalues))) * _FWHM_PER_SIGMA)
        return GaussianDeconvolution(
            status="major-axis-only",
            shape=None,
            quality_flags=("major-axis-only", "marginal-deconvolution"),
            major_axis_fwhm_degrees=major_fwhm,
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
    position_estimate = fit.position_estimate
    if position_estimate is not None:
        xx = position_estimate.covariance_xx_pixels_squared
        xy = position_estimate.covariance_xy_pixels_squared
        yy = position_estimate.covariance_yy_pixels_squared
    else:
        uncertainty = fit.uncertainty
        if uncertainty is None:
            return transform.position
        xx = uncertainty.centroid_covariance_xx_pixels_squared
        xy = uncertainty.centroid_covariance_xy_pixels_squared
        yy = uncertainty.centroid_covariance_yy_pixels_squared
    pixel_covariance = np.asarray([[xx, xy], [xy, yy]], dtype=np.float64)
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
    if geometric.status in {"unresolved", "unavailable"}:
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
    log_ratio_variance = (
        integrated_flux_error_jy / integrated_flux_jy
    ) ** 2 + (
        uncertainty.amplitude_error_jy_per_beam
        / parameters.amplitude_jy_per_beam
    ) ** 2
    amplitude_integrated_covariance = (
        uncertainty.amplitude_integrated_flux_covariance_jy_squared_per_beam
    )
    if amplitude_integrated_covariance is not None:
        log_ratio_variance -= (
            2.0
            * amplitude_integrated_covariance
            / (parameters.amplitude_jy_per_beam * integrated_flux_jy)
        )
    log_ratio_uncertainty = sqrt(max(0.0, log_ratio_variance))
    if log(flux_ratio) > significance_sigma * log_ratio_uncertainty:
        return geometric
    return GaussianDeconvolution(
        status="unresolved",
        shape=None,
        quality_flags=("extension-not-significant", "unresolved"),
    )


def _shape_parameter_covariance(
    values: tuple[float, float, float, float, float, float],
) -> npt.NDArray[np.float64]:
    """Expand the stored upper triangle for major/minor sigma and angle."""
    (
        major_variance,
        axis_covariance,
        major_angle,
        minor_variance,
        minor_angle,
        angle_variance,
    ) = values
    return np.asarray(
        (
            (major_variance, axis_covariance, major_angle),
            (axis_covariance, minor_variance, minor_angle),
            (major_angle, minor_angle, angle_variance),
        ),
        dtype=np.float64,
    )


def _intrinsic_eigenvalues(
    parameters: npt.NDArray[np.float64],
    jacobian: npt.NDArray[np.float64],
    beam: RestoringBeam,
) -> npt.NDArray[np.float64]:
    """Return ordered intrinsic sky variances for pixel-shape parameters."""
    pixel_covariance = _pixel_covariance(
        float(parameters[0]),
        float(parameters[1]),
        float(np.rad2deg(parameters[2])),
    )
    intrinsic = jacobian @ pixel_covariance @ jacobian.T - _sky_covariance(
        beam
    )
    return np.asarray(np.linalg.eigvalsh(intrinsic), dtype=np.float64)


def _fitted_shape_with_errors(
    shape: GaussianShape,
    fit: ValidCompactGaussianFit,
    jacobian: npt.NDArray[np.float64],
) -> GaussianShape:
    """Propagate the native marginal shape covariance through the WCS.

    The three-parameter numerical derivative follows the existing intrinsic
    axis uncertainty calculation. PA differences are taken modulo 180
    degrees. A circular ellipse has no identifiable PA or ordered-axis
    derivative, so its shape uncertainties remain explicitly unavailable.
    """
    uncertainty = fit.uncertainty
    if uncertainty is None or uncertainty.shape_parameter_covariance is None:
        return shape
    if np.isclose(
        shape.major_fwhm_degrees, shape.minor_fwhm_degrees, rtol=1e-12, atol=0
    ):
        return shape
    covariance = _shape_parameter_covariance(
        uncertainty.shape_parameter_covariance
    )
    parameters = np.array(
        (
            fit.parameters.major_sigma_pixels,
            fit.parameters.minor_sigma_pixels,
            np.deg2rad(fit.parameters.major_axis_angle_degrees),
        )
    )

    def projected(values: np.ndarray) -> np.ndarray:
        ellipse = _shape_from_sky_covariance(
            jacobian
            @ _pixel_covariance(
                float(values[0]),
                float(values[1]),
                float(np.rad2deg(values[2])),
            )
            @ jacobian.T
        )
        return np.array(
            (
                ellipse.major_fwhm_degrees,
                ellipse.minor_fwhm_degrees,
                ellipse.position_angle_degrees,
            )
        )

    gradient = np.empty((3, 3))
    for index in range(3):
        step = max(
            abs(parameters[index]) * 1e-6,
            np.sqrt(max(0.0, covariance[index, index])) * 1e-4,
            1e-8,
        )
        lower, upper = parameters.copy(), parameters.copy()
        lower[index] -= step
        upper[index] += step
        denominator = 2 * step
        if index < _SHAPE_AXIS_PARAMETER_COUNT and lower[index] <= 0:
            lower[index] = parameters[index]
            denominator = step
        difference = projected(upper) - projected(lower)
        difference[2] = (difference[2] + 90) % 180 - 90
        gradient[:, index] = difference / denominator
    variances = np.einsum("ij,jk,ik->i", gradient, covariance, gradient)
    if not np.all(np.isfinite(variances)) or np.any(variances < 0):
        return shape
    errors = np.sqrt(variances)
    return shape.model_copy(
        update={
            "major_fwhm_error_degrees": float(errors[0]),
            "minor_fwhm_error_degrees": float(errors[1]),
            "position_angle_error_degrees": float(errors[2]),
        }
    )


def _axis_significance_classification(  # noqa: PLR0913
    deconvolution: GaussianDeconvolution,
    fit: ValidCompactGaussianFit,
    jacobian: npt.NDArray[np.float64],
    beam: RestoringBeam,
    *,
    significance_sigma: float,
    relative_tolerance: float,
) -> GaussianDeconvolution:
    """Censor axes not separated significantly from the restoring beam."""
    if deconvolution.status in {"unresolved", "unavailable"}:
        return deconvolution
    uncertainty = fit.uncertainty
    if uncertainty is None:
        return deconvolution
    if uncertainty.shape_parameter_covariance is None:
        return GaussianDeconvolution(
            status="unavailable",
            shape=None,
            quality_flags=("deconvolution-uncertainty-unavailable",),
        )
    covariance = _shape_parameter_covariance(
        uncertainty.shape_parameter_covariance
    )
    parameters = np.asarray(
        (
            fit.parameters.major_sigma_pixels,
            fit.parameters.minor_sigma_pixels,
            np.deg2rad(fit.parameters.major_axis_angle_degrees),
        ),
        dtype=np.float64,
    )
    eigenvalues = _intrinsic_eigenvalues(parameters, jacobian, beam)
    gradient = np.empty((2, 3), dtype=np.float64)
    for parameter_index in range(3):
        standard_deviation = sqrt(
            max(0.0, float(covariance[parameter_index, parameter_index]))
        )
        step = max(
            abs(float(parameters[parameter_index])) * 1e-6,
            standard_deviation * 1e-4,
            1e-8,
        )
        lower = parameters.copy()
        upper = parameters.copy()
        lower[parameter_index] -= step
        upper[parameter_index] += step
        if (
            parameter_index < _SHAPE_AXIS_PARAMETER_COUNT
            and lower[parameter_index] <= 0
        ):
            lower[parameter_index] = parameters[parameter_index]
            denominator = step
        else:
            denominator = 2.0 * step
        gradient[:, parameter_index] = (
            _intrinsic_eigenvalues(upper, jacobian, beam)
            - _intrinsic_eigenvalues(lower, jacobian, beam)
        ) / denominator
    eigenvalue_variances = np.einsum(
        "ij,jk,ik->i",
        gradient,
        covariance,
        gradient,
        optimize=True,
    )
    eigenvalue_errors = np.sqrt(np.maximum(0.0, eigenvalue_variances))
    beam_scale = float(np.max(np.linalg.eigvalsh(_sky_covariance(beam))))
    tolerance = relative_tolerance * beam_scale

    def significant(index: int) -> bool:
        value = float(eigenvalues[index])
        error = float(eigenvalue_errors[index])
        return value > tolerance and (
            error == 0.0 or value > significance_sigma * error
        )

    if not significant(1):
        return GaussianDeconvolution(
            status="unresolved",
            shape=None,
            quality_flags=("major-axis-not-significant", "unresolved"),
        )
    if not significant(0):
        return GaussianDeconvolution(
            status="major-axis-only",
            shape=None,
            quality_flags=("major-axis-only", "minor-axis-not-significant"),
            major_axis_fwhm_degrees=(
                float(sqrt(float(eigenvalues[1])) * _FWHM_PER_SIGMA)
            ),
        )
    return deconvolution


def transform_compact_gaussian_fit(  # noqa: PLR0913
    fit: ValidCompactGaussianFit,
    metadata: ImageMetadata,
    *,
    deconvolution_relative_tolerance: float = 1e-10,
    extension_significance_sigma: float = 5.0,
    deconvolution_axis_significance_sigma: float = 5.0,
    celestial_wcs: WCS | None = None,
) -> CelestialCompactGaussianFit:
    """Transform a valid pixel fit into reviewed ICRS catalogue quantities."""
    if metadata.unit != "Jy/beam":
        raise ValueError("compact measurement requires image unit Jy/beam")
    position_xy = (
        fit.position_estimate.centroid_xy
        if fit.position_estimate is not None
        else fit.parameters.centroid_xy
    )
    transform = local_tangent_plane_transform(
        metadata, position_xy, celestial_wcs=celestial_wcs
    )
    return transform_compact_fit_at_tangent(
        fit,
        metadata.beam,
        transform,
        deconvolution_relative_tolerance=deconvolution_relative_tolerance,
        extension_significance_sigma=extension_significance_sigma,
        deconvolution_axis_significance_sigma=deconvolution_axis_significance_sigma,
    )


def transform_compact_fit_at_tangent(  # noqa: PLR0913
    fit: ValidCompactGaussianFit,
    beam: RestoringBeam,
    transform: LocalTangentPlaneTransform,
    *,
    deconvolution_relative_tolerance: float = 1e-10,
    extension_significance_sigma: float = 5.0,
    deconvolution_axis_significance_sigma: float = 5.0,
) -> CelestialCompactGaussianFit:
    """Project a Jy/beam fit using an explicit local celestial transform."""
    if (
        not isfinite(extension_significance_sigma)
        or extension_significance_sigma <= 0
    ):
        raise ValueError(
            "extension_significance_sigma must be finite and positive"
        )
    if (
        not isfinite(deconvolution_axis_significance_sigma)
        or deconvolution_axis_significance_sigma <= 0
    ):
        raise ValueError(
            "deconvolution_axis_significance_sigma must be finite and positive"
        )
    parameters = fit.parameters
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
    fitted_shape = _fitted_shape_with_errors(
        _shape_from_sky_covariance(fitted_covariance), fit, jacobian
    )
    geometric_deconvolution = deconvolve_gaussian_shapes(
        fitted_shape,
        beam,
        relative_tolerance=deconvolution_relative_tolerance,
    )
    geometry = compact_geometry_from_transform(beam, transform)
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
    if uncertainty is not None and integrated_flux_error is not None:
        integrated_flux -= (
            uncertainty.integrated_flux_bias_correction_sigma
            * integrated_flux_error
        )
        if integrated_flux <= 0.0:
            raise ValueError(
                "integrated-flux bias correction produced non-positive flux"
            )
    deconvolution = _extension_classification(
        geometric_deconvolution,
        fit,
        integrated_flux_jy=integrated_flux,
        integrated_flux_error_jy=integrated_flux_error,
        significance_sigma=extension_significance_sigma,
    )
    deconvolution = _axis_significance_classification(
        deconvolution,
        fit,
        jacobian,
        beam,
        significance_sigma=deconvolution_axis_significance_sigma,
        relative_tolerance=deconvolution_relative_tolerance,
    )
    fitted_flux = FluxMeasurement(
        peak_flux_jy_per_beam=parameters.amplitude_jy_per_beam,
        peak_flux_error_jy_per_beam=(
            uncertainty.amplitude_error_jy_per_beam
            if uncertainty is not None
            else None
        ),
        integrated_flux_jy=integrated_flux,
        integrated_flux_error_jy=integrated_flux_error,
        local_rms_jy_per_beam=parameters.local_rms_jy_per_beam,
    )
    if deconvolution.status == "unresolved":
        flux = FluxMeasurement(
            peak_flux_jy_per_beam=fitted_flux.peak_flux_jy_per_beam,
            peak_flux_error_jy_per_beam=(
                fitted_flux.peak_flux_error_jy_per_beam
            ),
            integrated_flux_jy=fitted_flux.peak_flux_jy_per_beam,
            integrated_flux_error_jy=(fitted_flux.peak_flux_error_jy_per_beam),
            local_rms_jy_per_beam=fitted_flux.local_rms_jy_per_beam,
        )
    else:
        flux = fitted_flux
    flags = set(fit.quality_flags)
    if fitted_shape.major_fwhm_error_degrees is None:
        flags.add("shape-uncertainty-unavailable")
    flags.update(deconvolution.quality_flags)
    if uncertainty is None:
        flags.add("position-flux-uncertainty-unavailable")
    elif uncertainty.integrated_flux_bias_correction_sigma > 0.0:
        flags.add("fitted-integrated-flux-bias-corrected")
    return CelestialCompactGaussianFit(
        pixel_fit=fit,
        position=_position_with_errors(transform, fit),
        flux=flux,
        fitted_flux=fitted_flux,
        fitted_shape=fitted_shape,
        deconvolution_status=deconvolution.status,
        deconvolved_shape=deconvolution.shape,
        deconvolved_major_fwhm_degrees=(deconvolution.major_axis_fwhm_degrees),
        quality_flags=tuple(sorted(flags)),
    )
