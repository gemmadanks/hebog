# pyright: reportMissingTypeStubs=false
"""Configurable scientific composition behind the public source finder."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.algorithms.component_measurement import (
    reconcile_component_measurements,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
)
from hebog.algorithms.source_association import HierarchyOverlaps
from hebog.science.catalogues import (
    build_hebog_reconstructed_source_catalogues,
)
from hebog.science.continuum import (
    CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS,
    build_continuum_candidate_products,
)
from hebog.science.models import (
    ContinuumProducts,
    TiledComponentFits,
    TiledComponentTopology,
    TiledMultiscaleDetection,
    TiledSupportLabels,
)

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
    multiscale: TiledMultiscaleDetection,
    labels: TiledSupportLabels,
    topology: TiledComponentTopology,
    component_fits: TiledComponentFits,
    hierarchy_overlaps: HierarchyOverlaps,
    persistent_scale_support: npt.NDArray[np.bool_],
) -> ContinuumProducts | None:
    """Build terminal products from the published tiled passes.

    Every threshold and island limit has already been applied by the passes
    that published these records, so this step takes no configuration: an
    image whose admitted islands are all rejected publishes nothing.
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
    measurements = reconcile_component_measurements(
        np.array(
            component_fits.measurement_support,
            dtype=np.bool_,
            copy=True,
        ),
        parents=component_fits.parents,
        features=component_fits.features,
    )
    catalogues = build_hebog_reconstructed_source_catalogues(
        image,
        background,
        valid,
        topology.measurement_component_labels,
        topology.direct_component_labels,
        retained.scale_detections,
        header,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam.minor_fwhm_pixels,
        measurement_aperture_radius_beams=(
            CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
        ),
        position_signal_jy_per_beam=retained.position_signal_jy_per_beam,
        component_measurements=measurements,
        hierarchy_overlaps=hierarchy_overlaps,
        persistent_scale_support=persistent_scale_support,
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
