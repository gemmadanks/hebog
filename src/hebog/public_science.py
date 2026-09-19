# pyright: reportMissingTypeStubs=false
"""Configurable scientific composition behind the public source finder."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms.component_measurement import measure_component_models
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    build_residual_atrous_plan,
)
from hebog.config import SourceFinderConfig
from hebog.data_models.images import RestoringBeam
from hebog.science.catalogues import (
    build_hebog_reconstructed_source_catalogues,
)
from hebog.science.configuration import source_finder_configs
from hebog.science.continuum import (
    CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS,
    build_continuum_candidate_products,
    compact_deblend_config,
)
from hebog.science.models import (
    ContinuumProducts,
    TiledComponentTopology,
    TiledMultiscaleDetection,
    TiledSupportLabels,
)
from hebog.science.profile import ContinuumScienceProfile

_IMAGE_DIMENSIONS = 2


def _aligned_plane(
    values: npt.ArrayLike,
    *,
    name: str,
    shape: tuple[int, int] | None = None,
) -> npt.NDArray[np.float64]:
    """Return one aligned real two-dimensional public science plane."""
    plane = np.asarray(values)
    if (
        plane.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(plane.dtype, np.number)
        or np.iscomplexobj(plane)
        or (shape is not None and plane.shape != shape)
    ):
        raise ValueError(
            f"public source-finder {name} must be an aligned real "
            "two-dimensional plane"
        )
    return np.asarray(plane, dtype=np.float64)


def build_configured_continuum_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    header: fits.Header,
    *,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
    config: SourceFinderConfig,
    multiscale: TiledMultiscaleDetection,
    labels: TiledSupportLabels,
    topology: TiledComponentTopology,
) -> ContinuumProducts | None:
    """Build terminal products from the published tiled passes.

    The detection and support passes have already applied the caller's
    thresholds and island limits on their own cores, so an image whose
    admitted islands are all rejected publishes nothing.
    """
    image = _aligned_plane(image_jy_per_beam, name="image")
    background = _aligned_plane(
        background_jy_per_beam,
        name="background",
        shape=image.shape,
    )
    rms = _aligned_plane(rms_jy_per_beam, name="RMS", shape=image.shape)
    valid = np.isfinite(image) & np.isfinite(background) & np.isfinite(rms)
    if np.any(np.isfinite(image) != valid):
        raise ValueError(
            "public source-finder mean/RMS validity differs from image"
        )
    positive_rms = valid & (rms > 0.0)
    if not np.any(np.asarray(labels.component_labels) > 0):
        return None
    retained = build_continuum_candidate_products(
        positive_rms,
        multiscale=multiscale,
        labels=labels,
    )
    deblend_config = compact_deblend_config(config)
    _, _, moment_config, fit_config, _ = source_finder_configs()
    measurements = measure_component_models(
        image - background,
        rms,
        positive_rms,
        topology.direct_component_labels,
        topology.measurement_component_labels,
        WCS(header, relax=True).celestial,
        RestoringBeam(
            cast(float, header["BMAJ"]),
            cast(float, header["BMIN"]),
            cast(float, header["BPA"]) if "BPA" in header else 0.0,
        ),
        moment_config,
        replace(fit_config, integrated_flux_bias_correction_sigma=0.0),
        detection_sigma=config.detection_threshold_sigma,
        island_sigma=config.island_threshold_sigma,
        minimum_pixels=config.minimum_island_pixels,
        maximum_bounds_pixels=deblend_config.maximum_compact_bounds_pixels,
        atrous_plan=build_residual_atrous_plan(beam, noise_correlation=beam),
        minimum_support_fraction=review.matrix.support_fraction_bounds[0],
    )
    catalogues = build_hebog_reconstructed_source_catalogues(
        image,
        background,
        valid,
        topology.measurement_component_labels,
        topology.direct_component_labels,
        retained.significant_multiscale_support,
        retained.scale_detection_planes,
        header,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam.minor_fwhm_pixels,
        measurement_aperture_radius_beams=(
            CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
        ),
        position_signal_jy_per_beam=retained.position_signal_jy_per_beam,
        component_measurements=measurements,
    )
    valid.setflags(write=False)
    support_stages = tuple(
        sorted(
            (
                *catalogues.support_stages,
                ("direct", topology.direct_component_labels > 0),
                ("multiscale", retained.significant_multiscale_support),
                ("component-owner", topology.measurement_component_labels > 0),
                ("publication", retained.detection.retained_mask),
            ),
            key=lambda item: item[0],
        )
    )
    for _, mask in support_stages:
        mask.setflags(write=False)
    return ContinuumProducts(
        detection=retained.detection,
        measurement_component_labels=(topology.measurement_component_labels),
        catalogue=catalogues.source_catalogue,
        valid_pixels=valid,
        component_catalogue=catalogues.component_catalogue,
        source_association=catalogues.association,
        deblended_parent_count=topology.deblended_parent_count,
        deferred_deblend_parent_count=topology.deferred_parent_count,
        measurement_dispositions=catalogues.measurement_dispositions,
        support_stages=support_stages,
    )
