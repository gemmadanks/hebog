"""Analytic Phase 4 truth in the canonical catalogue comparison view."""

from __future__ import annotations

import numpy as np

from hebog.algorithms.astrometry import (
    compact_geometry_at_pixel,
    deconvolve_gaussian_shapes,
    local_tangent_plane_transform,
)
from hebog.algorithms.measurement import fitted_gaussian_integrated_flux_jy
from hebog.data_models.catalogues import GaussianShape
from hebog.validation.comparison import CatalogueEllipse, CatalogueSource
from hebog.validation.datasets import DatasetRecord, SyntheticSource
from hebog.validation.materialization import synthetic_image_metadata

_FWHM_PER_SIGMA = 2.0 * np.sqrt(2.0 * np.log(2.0))


def _ellipse_from_pixel_covariance(
    covariance: np.ndarray,
    jacobian_degrees_per_pixel: np.ndarray,
) -> CatalogueEllipse:
    """Transform an analytic pixel covariance into a sky ellipse."""
    sky_covariance = (
        jacobian_degrees_per_pixel @ covariance @ jacobian_degrees_per_pixel.T
    )
    eigenvalues, eigenvectors = np.linalg.eigh(sky_covariance)
    major_index = int(np.argmax(eigenvalues))
    minor_index = 1 - major_index
    major_vector = eigenvectors[:, major_index]
    position_angle = (
        0.0
        if np.isclose(
            eigenvalues[major_index],
            eigenvalues[minor_index],
            rtol=1e-12,
        )
        else float(
            np.rad2deg(np.arctan2(major_vector[0], major_vector[1])) % 180.0
        )
    )
    return CatalogueEllipse(
        major_fwhm_degrees=float(
            np.sqrt(eigenvalues[major_index]) * _FWHM_PER_SIGMA
        ),
        minor_fwhm_degrees=float(
            np.sqrt(eigenvalues[minor_index]) * _FWHM_PER_SIGMA
        ),
        position_angle_degrees=position_angle,
    )


def phase_four_truth_source(
    source: SyntheticSource,
    dataset: DatasetRecord,
    *,
    identifier: str,
) -> CatalogueSource:
    """Transform one analytic emitter to the canonical Phase 4 truth view."""
    metadata = synthetic_image_metadata(dataset)
    centroid_xy = (source.x_pixel, source.y_pixel)
    transform = local_tangent_plane_transform(metadata, centroid_xy)
    angle = np.deg2rad(source.rotation_degrees_counterclockwise_from_x)
    major = np.asarray([np.cos(angle), np.sin(angle)])
    minor = np.asarray([-np.sin(angle), np.cos(angle)])
    pixel_covariance = source.major_sigma_pixels**2 * np.outer(
        major,
        major,
    ) + source.minor_sigma_pixels**2 * np.outer(minor, minor)
    fitted = _ellipse_from_pixel_covariance(
        pixel_covariance,
        np.asarray(transform.jacobian_degrees_per_pixel),
    )
    fitted_shape = GaussianShape(
        major_fwhm_degrees=fitted.major_fwhm_degrees,
        minor_fwhm_degrees=fitted.minor_fwhm_degrees,
        position_angle_degrees=fitted.position_angle_degrees,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )
    deconvolution = deconvolve_gaussian_shapes(
        fitted_shape,
        metadata.beam,
        relative_tolerance=1e-10,
    )
    deconvolved = (
        CatalogueEllipse(
            major_fwhm_degrees=deconvolution.shape.major_fwhm_degrees,
            minor_fwhm_degrees=deconvolution.shape.minor_fwhm_degrees,
            position_angle_degrees=(
                deconvolution.shape.position_angle_degrees
            ),
        )
        if deconvolution.shape is not None
        else None
    )
    deconvolved_major = deconvolution.major_axis_fwhm_degrees
    geometry = compact_geometry_at_pixel(metadata, centroid_xy)
    free_integrated_flux = fitted_gaussian_integrated_flux_jy(
        amplitude_jy_per_beam=source.peak_flux_jy_per_beam,
        major_sigma_pixels=source.major_sigma_pixels,
        minor_sigma_pixels=source.minor_sigma_pixels,
        geometry=geometry,
    )
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=transform.position.right_ascension_degrees,
        declination_degrees=transform.position.declination_degrees,
        peak_flux_jy_per_beam=source.peak_flux_jy_per_beam,
        integrated_flux_jy=(
            source.peak_flux_jy_per_beam
            if deconvolution.status == "unresolved"
            else free_integrated_flux
        ),
        fitted_shape=fitted,
        deconvolved_shape=deconvolved,
        deconvolved_major_fwhm_degrees=deconvolved_major,
        deconvolution_status=deconvolution.status,
        island_identifier=identifier,
        component_count=1,
        quality_flags=(
            deconvolution.quality_flags
            if deconvolution.status in {"major-axis-only", "unresolved"}
            else ()
        ),
    )
