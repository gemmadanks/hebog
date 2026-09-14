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
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    ResidualAtrousResult,
    SignificantAtrousReconstruction,
    build_residual_atrous_plan,
    build_scale_filter_bank,
    calibrated_scale_snrs,
    detect_residual_multiscale_islands,
    evaluate_residual_atrous,
    evaluate_scale_filter_bank,
    prepare_scale_filter_inputs,
)
from hebog.algorithms.multiscale_association import (
    ScaleDetectionPlane,
    build_scale_detection_plane,
    persistent_adjacent_scale_support,
)
from hebog.config import ResidualMultiscaleDetectionConfig
from hebog.science.models import (
    ContinuumCandidateProducts,
    ThresholdFilterResult,
)
from hebog.science.profile import ContinuumScienceProfile

CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS = 1.5
_IMAGE_DIMENSIONS = 2
_TRUNCATION_SIGMA = 4.0


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


def _retained_scale_detection_planes(
    atrous: ResidualAtrousResult,
    reconstruction: SignificantAtrousReconstruction,
    valid_pixels: npt.NDArray[np.bool_],
    *,
    minimum_support_fraction: float,
) -> tuple[ScaleDetectionPlane, ...]:
    """Build exact retained per-scale features for source hierarchy."""
    scale_snrs = calibrated_scale_snrs(
        atrous.responses,
        minimum_support_fraction=minimum_support_fraction,
    )
    return tuple(
        build_scale_detection_plane(
            scale_mask & reconstruction.support_mask,
            response.response_jy_per_beam,
            scale_snr,
            valid_pixels,
            scale_order=response.scale_order,
            nominal_scale_beam_fwhm=response.nominal_scale_beam_fwhm,
        )
        for response, scale_mask, scale_snr in zip(
            atrous.responses,
            reconstruction.significant_scale_masks,
            scale_snrs,
            strict=True,
        )
    )


def _initial_candidate_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    *,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
) -> ContinuumCandidateProducts:
    """Evaluate direct seeds and attach support without connected unions."""
    prepared = prepare_scale_filter_inputs(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
    )
    scales = tuple(
        zip(review.matrix.scale_orders, (1.0, 2.0, 4.0), strict=True)
    )
    minimum_support = review.matrix.support_fraction_bounds[0]
    matched = evaluate_scale_filter_bank(
        prepared,
        build_scale_filter_bank(
            beam,
            family="beam-aware-matched-filter",
            scales=scales,
            truncation_sigma=_TRUNCATION_SIGMA,
            noise_correlation=beam,
        ),
        minimum_support_fraction=minimum_support,
    )
    atrous = evaluate_residual_atrous(
        prepared,
        build_residual_atrous_plan(beam, noise_correlation=beam),
        minimum_support_fraction=minimum_support,
    )
    direct_detection = detect_residual_multiscale_islands(
        prepared,
        matched,
        atrous,
        beam,
        ResidualMultiscaleDetectionConfig(
            detection_threshold_sigma=review.matrix.detection_sigma,
            island_threshold_sigma=review.matrix.island_sigma,
            minimum_scale_support_fraction=minimum_support,
            minimum_island_area_beams=(
                review.corrections.minimum_island_area_beams
            ),
        ),
    )
    measurement_labels = assign_seeded_multiscale_support(
        direct_detection.component_labels,
        direct_detection.reconstruction.support_mask,
        prepared.scientifically_valid,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
    )
    labels = refine_multiscale_segment_labels(
        measurement_labels,
        direct_detection.combined_snr,
        direct_detection.reconstruction.support_mask,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        recovered_minimum_snr=review.matrix.island_sigma,
    )
    retained = np.asarray(labels > 0, dtype=np.bool_)
    labels.setflags(write=False)
    retained.setflags(write=False)
    detection = ThresholdFilterResult(
        combined_snr=direct_detection.combined_snr,
        retained_mask=retained,
        component_labels=labels,
        component_count=int(np.count_nonzero(np.unique(labels) > 0)),
    )
    significant_support = np.asarray(
        direct_detection.reconstruction.support_mask, dtype=np.bool_
    ).copy()
    significant_support.setflags(write=False)
    direct_labels = np.asarray(
        direct_detection.component_labels, dtype=np.int32
    ).copy()
    direct_labels.setflags(write=False)
    measurement_labels = np.asarray(measurement_labels, dtype=np.int32).copy()
    measurement_labels.setflags(write=False)
    return ContinuumCandidateProducts(
        detection=detection,
        direct_component_labels=direct_labels,
        measurement_component_labels=measurement_labels,
        position_signal_jy_per_beam=(
            prepared.residual_jy_per_beam
            + atrous.reconstructed_signal_jy_per_beam
        ),
        significant_multiscale_support=significant_support,
        scale_detection_planes=_retained_scale_detection_planes(
            atrous,
            direct_detection.reconstruction,
            prepared.scientifically_valid,
            minimum_support_fraction=minimum_support,
        ),
    )


def _publication_snr_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    *,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
) -> ContinuumCandidateProducts:
    """Publish refined support from original-pixel rather than filtered S/N."""
    products = _initial_candidate_products(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
        beam=beam,
        review=review,
    )
    direct_snr = _direct_snr(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
    )
    labels = refine_multiscale_segment_labels(
        products.measurement_component_labels,
        direct_snr,
        products.significant_multiscale_support,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        recovered_minimum_snr=review.matrix.island_sigma,
    )
    retained = np.asarray(labels > 0, dtype=np.bool_)
    labels.setflags(write=False)
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


def _direct_origin_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    *,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
) -> ContinuumCandidateProducts:
    """Refine publication from immutable direct-owner support only."""
    products = _publication_snr_products(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
        beam=beam,
        review=review,
    )
    direct_snr = _direct_snr(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
    )
    direct_publication_labels = refine_multiscale_segment_labels(
        products.direct_component_labels,
        direct_snr,
        products.significant_multiscale_support,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        recovered_minimum_snr=review.matrix.island_sigma,
    )
    direct_labels = np.asarray(products.direct_component_labels)
    measurement_labels = np.asarray(products.measurement_component_labels)
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
        np.int32, copy=False
    )
    retained = np.asarray(labels > 0, dtype=np.bool_)
    labels.setflags(write=False)
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


def evaluate_continuum_candidate_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    *,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
) -> ContinuumCandidateProducts:
    """Refine publication support using exact adjacent-scale persistence."""
    products = _direct_origin_products(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
        beam=beam,
        review=review,
    )
    direct_snr = _direct_snr(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
    )
    persistent_support = (
        persistent_adjacent_scale_support(products.scale_detection_planes)
        if products.scale_detection_planes
        else np.zeros(direct_snr.shape, dtype=np.bool_)
    )
    labels = refine_persistent_publication_labels(
        products.measurement_component_labels,
        products.detection.component_labels,
        direct_snr,
        persistent_support,
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
