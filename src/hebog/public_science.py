# pyright: reportMissingTypeStubs=false
"""Configurable scientific composition behind the public source finder."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.algorithms.component_topology import deblend_component_topology
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import SourceFinderConfig
from hebog.validation.contracts import PhaseFiveCorrectiveAReview
from hebog.validation.hebog_campaign import (
    phase_five_corrected_candidate_configs,
)
from hebog.validation.post_campaign_science import (
    CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS,
    PostCampaignCandidateProducts,
)
from hebog.validation.products import (
    build_hebog_reconstructed_source_catalogues,
)
from hebog.validation.public_finder_correction import (
    PublicFinderCorrectionContinuumProducts,
)
from hebog.validation.publication_scale_persistence import (
    evaluate_publication_scale_persistence_candidate_products,
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


def _execution_review(
    review: PhaseFiveCorrectiveAReview,
    config: SourceFinderConfig,
) -> PhaseFiveCorrectiveAReview:
    """Apply caller thresholds without changing frozen review evidence."""
    matrix = review.matrix.model_copy(
        update={
            "detection_sigma": config.detection_threshold_sigma,
            "island_sigma": config.island_threshold_sigma,
        }
    )
    return review.model_copy(update={"matrix": matrix})


def _retain_configured_islands(
    products: PostCampaignCandidateProducts,
    config: SourceFinderConfig,
) -> PostCampaignCandidateProducts | None:
    """Apply caller pixel-count limits to terminal direct-island identity."""
    direct = np.asarray(products.direct_component_labels, dtype=np.int32)
    component_sizes = np.bincount(direct.ravel())
    accepted = component_sizes >= config.minimum_island_pixels
    accepted[0] = False
    if config.maximum_island_pixels is not None:
        accepted &= component_sizes <= config.maximum_island_pixels
    if not np.any(accepted):
        return None

    def retain(labels: npt.ArrayLike) -> npt.NDArray[np.int32]:
        label_plane = np.asarray(labels, dtype=np.int32)
        if (
            np.any(label_plane < 0)
            or int(np.max(label_plane)) >= accepted.size
        ):
            raise ValueError("public source-finder labels are inconsistent")
        retained = np.where(accepted[label_plane], label_plane, 0).astype(
            np.int32,
            copy=False,
        )
        retained.setflags(write=False)
        return retained

    direct_labels = retain(products.direct_component_labels)
    measurement_labels = retain(products.measurement_component_labels)
    publication_labels = retain(products.detection.component_labels)
    retained_mask = np.asarray(publication_labels > 0, dtype=np.bool_)
    retained_mask.setflags(write=False)
    return replace(
        products,
        detection=replace(
            products.detection,
            retained_mask=retained_mask,
            component_labels=publication_labels,
            component_count=int(np.count_nonzero(accepted)),
        ),
        direct_component_labels=direct_labels,
        measurement_component_labels=measurement_labels,
    )


def build_configured_continuum_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    header: fits.Header,
    *,
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveAReview,
    config: SourceFinderConfig,
) -> PublicFinderCorrectionContinuumProducts | None:
    """Build terminal products using caller thresholds and island limits."""
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
    products = evaluate_publication_scale_persistence_candidate_products(
        image,
        valid,
        background,
        rms,
        beam=beam,
        review=_execution_review(review, config),
    )
    retained = _retain_configured_islands(products, config)
    if retained is None:
        return None
    normalized = np.full(image.shape, np.nan, dtype=np.float64)
    positive_rms = valid & (rms > 0.0)
    np.divide(
        image - background,
        rms,
        out=normalized,
        where=positive_rms,
    )
    deblend_config = replace(
        phase_five_corrected_candidate_configs()[1],
        minimum_peak_signal_to_noise=float(
            np.nextafter(config.detection_threshold_sigma, -np.inf)
        ),
    )
    topology = deblend_component_topology(
        normalized,
        retained.direct_component_labels,
        retained.measurement_component_labels,
        valid,
        deblend_config,
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
    )
    valid.setflags(write=False)
    return PublicFinderCorrectionContinuumProducts(
        detection=retained.detection,
        measurement_component_labels=(topology.measurement_component_labels),
        catalogue=catalogues.source_catalogue,
        valid_pixels=valid,
        component_catalogue=catalogues.component_catalogue,
        source_association=catalogues.association,
        deblended_parent_count=topology.deblended_parent_count,
        deferred_deblend_parent_count=topology.deferred_parent_count,
    )
