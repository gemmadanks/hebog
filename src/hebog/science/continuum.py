# pyright: reportMissingTypeStubs=false
"""Current continuum detection and publication-support composition."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import numpy.typing as npt

from hebog.algorithms.extended_measurement import (
    assign_seeded_multiscale_support,
    refine_multiscale_segment_labels,
    refine_persistent_publication_labels,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.multiscale_association import (
    ScaleDetectionPlane,
    build_scale_detection_plane_from_islands,
)
from hebog.config import ResidualMultiscaleDetectionConfig
from hebog.science.models import (
    ContinuumCandidateProducts,
    ThresholdFilterResult,
    TiledMultiscaleDetection,
    TiledSupportTopology,
)
from hebog.science.profile import ContinuumScienceProfile

CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS = 1.5
_IMAGE_DIMENSIONS = 2


def _aligned_plane(
    values: npt.ArrayLike,
    *,
    name: str,
    shape: tuple[int, int] | None = None,
) -> npt.NDArray[np.float64]:
    """Return one aligned real two-dimensional science plane."""
    plane = np.asarray(values)
    if (
        plane.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(plane.dtype, np.number)
        or np.iscomplexobj(plane)
        or (shape is not None and plane.shape != shape)
    ):
        raise ValueError(
            f"continuum science {name} must be an aligned real "
            "two-dimensional plane"
        )
    return np.asarray(plane, dtype=np.float64)


def _direct_snr(
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
) -> npt.NDArray[np.float64]:
    """Return original-pixel signal to noise on the exact valid domain."""
    image = _aligned_plane(image_jy_per_beam, name="image")
    background = _aligned_plane(
        background_jy_per_beam, name="background", shape=image.shape
    )
    rms = _aligned_plane(rms_jy_per_beam, name="RMS", shape=image.shape)
    valid = np.asarray(valid_pixels)
    if valid.shape != image.shape or valid.dtype != np.bool_:
        raise ValueError(
            "continuum science validity must be one aligned boolean plane"
        )
    direct_snr = np.full(image.shape, -np.inf, dtype=np.float64)
    direct_valid = (
        valid
        & np.isfinite(image)
        & np.isfinite(background)
        & np.isfinite(rms)
        & (rms > 0)
    )
    np.divide(image - background, rms, out=direct_snr, where=direct_valid)
    return direct_snr


def _scientifically_valid(
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
) -> npt.NDArray[np.bool_]:
    """Return the exact domain the filtered detection pass ran over.

    This is the domain ``prepare_scale_filter_inputs`` forms on a task, so
    the pixels a later pass may attach support to are the pixels the tiled
    pass could have detected on.
    """
    image = _aligned_plane(image_jy_per_beam, name="image")
    background = _aligned_plane(
        background_jy_per_beam, name="background", shape=image.shape
    )
    rms = _aligned_plane(rms_jy_per_beam, name="RMS", shape=image.shape)
    valid = np.asarray(valid_pixels)
    if valid.shape != image.shape or valid.dtype != np.bool_:
        raise ValueError(
            "continuum science validity must be one aligned boolean plane"
        )
    return np.asarray(
        valid
        & np.isfinite(image)
        & np.isfinite(background)
        & np.isfinite(rms)
        & (rms > 0),
        dtype=np.bool_,
    )


def residual_detection_config(
    review: ContinuumScienceProfile,
) -> ResidualMultiscaleDetectionConfig:
    """Return the reviewed thresholds the tiled detection pass runs under."""
    return ResidualMultiscaleDetectionConfig(
        detection_threshold_sigma=review.matrix.detection_sigma,
        island_threshold_sigma=review.matrix.island_sigma,
        minimum_scale_support_fraction=(
            review.matrix.support_fraction_bounds[0]
        ),
        minimum_island_area_beams=review.corrections.minimum_island_area_beams,
    )


def _retained_scale_detection_planes(
    multiscale: TiledMultiscaleDetection,
    valid_pixels: npt.NDArray[np.bool_],
) -> tuple[ScaleDetectionPlane, ...]:
    """Describe the retained per-scale features from published support."""
    for scale_mask in multiscale.significant_scale_masks:
        if scale_mask.shape != valid_pixels.shape or np.any(
            scale_mask & ~valid_pixels
        ):
            raise ValueError("scale support must be scientifically valid")
    return tuple(
        build_scale_detection_plane_from_islands(
            scale_mask,
            islands,
            scale_order=scale_order,
            nominal_scale_beam_fwhm=nominal_beam_fwhm,
        )
        for scale_order, (scale_mask, islands, nominal_beam_fwhm) in enumerate(
            zip(
                multiscale.significant_scale_masks,
                multiscale.scale_islands_by_order,
                multiscale.scale_nominal_beam_fwhms,
                strict=True,
            ),
            start=1,
        )
    )


def _publication_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    *,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
    multiscale: TiledMultiscaleDetection,
    support: TiledSupportTopology,
) -> ContinuumCandidateProducts:
    """Attach bounded multiscale support and publish direct-owner support.

    Direct residual labels are authoritative identities. Multiscale support
    may enlarge an owner within a bounded recovery radius but never merges two
    identities, and publication is refined from immutable direct-owner support
    on original-pixel signal to noise rather than on the filtered evidence
    that promoted the seed.
    """
    scientifically_valid = _scientifically_valid(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
    )
    direct_labels = np.asarray(multiscale.detection_labels, dtype=np.int32)
    support_mask = np.asarray(multiscale.reconstruction_mask, dtype=np.bool_)
    measurement_labels = np.asarray(
        assign_seeded_multiscale_support(
            direct_labels,
            support_mask,
            scientifically_valid,
            beam_major_fwhm_pixels=beam.major_fwhm_pixels,
            support_component_labels=support.support_component_labels,
        ),
        dtype=np.int32,
    )
    direct_snr = _direct_snr(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
    )
    direct_publication_labels = refine_multiscale_segment_labels(
        direct_labels,
        direct_snr,
        support_mask,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        recovered_minimum_snr=review.matrix.island_sigma,
    )
    direct_support = direct_labels > 0
    if np.any(
        direct_support
        & ((measurement_labels <= 0) | (measurement_labels != direct_labels))
    ):
        raise ValueError(
            "direct support must be an exact subset of measurement ownership"
        )
    publication_support = (direct_publication_labels > 0) & (
        measurement_labels > 0
    )
    labels = np.where(publication_support, measurement_labels, 0).astype(
        np.int32,
        copy=False,
    )
    retained = np.asarray(labels > 0, dtype=np.bool_)
    labels.setflags(write=False)
    retained.setflags(write=False)
    significant_support = support_mask.copy()
    significant_support.setflags(write=False)
    owned_labels = direct_labels.copy()
    owned_labels.setflags(write=False)
    measurement_labels = measurement_labels.copy()
    measurement_labels.setflags(write=False)
    return ContinuumCandidateProducts(
        detection=ThresholdFilterResult(
            retained_mask=retained,
            component_labels=labels,
            component_count=int(np.count_nonzero(np.unique(labels) > 0)),
        ),
        direct_component_labels=owned_labels,
        measurement_component_labels=measurement_labels,
        position_signal_jy_per_beam=multiscale.position_signal_jy_per_beam,
        significant_multiscale_support=significant_support,
        scale_detection_planes=_retained_scale_detection_planes(
            multiscale,
            scientifically_valid,
        ),
    )


def evaluate_continuum_candidate_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    *,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
    multiscale: TiledMultiscaleDetection,
    support: TiledSupportTopology,
) -> ContinuumCandidateProducts:
    """Refine publication support using exact adjacent-scale persistence."""
    products = _publication_products(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
        beam=beam,
        review=review,
        multiscale=multiscale,
        support=support,
    )
    direct_snr = _direct_snr(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
    )
    labels = refine_persistent_publication_labels(
        products.measurement_component_labels,
        products.detection.component_labels,
        direct_snr,
        support.persistent_scale_support,
    )
    retained = np.asarray(labels > 0, dtype=np.bool_)
    retained.setflags(write=False)
    return replace(
        products,
        detection=replace(
            products.detection,
            retained_mask=retained,
            component_labels=labels,
            component_count=int(np.count_nonzero(np.unique(labels) > 0)),
        ),
    )
