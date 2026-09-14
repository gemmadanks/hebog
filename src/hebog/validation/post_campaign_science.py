# pyright: reportPrivateUsage=false
"""Prospective science corrections after the closed Phase 5 campaign."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np
import numpy.typing as npt

from hebog.algorithms.extended_measurement import (
    assign_seeded_multiscale_support,
    refine_multiscale_segment_labels,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    ResidualAtrousResult,
    ResidualMultiscaleDetectionConfig,
    SignificantAtrousReconstruction,
    calibrated_scale_snrs,
    detect_residual_multiscale_islands,
    prepare_scale_filter_inputs,
    reconstruct_significant_atrous,
)
from hebog.algorithms.multiscale_association import (
    ScaleDetectionPlane,
    build_scale_detection_plane,
)
from hebog.validation.campaigns import diagnose_phase_four_realization
from hebog.validation.comparison import (
    CatalogueOutlierThresholds,
    CatalogueSource,
)
from hebog.validation.contracts import PhaseFiveCorrectiveAReview
from hebog.validation.datasets import DatasetRecord, SyntheticRecipe
from hebog.validation.evidence import CampaignRealizationDiagnostic
from hebog.validation.phase_five_filter_review import (
    ThresholdFilterResult,
    _corrective_results,
)

CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS = 1.5


@dataclass(frozen=True, slots=True)
class PostCampaignCandidateProducts:
    """Refined detection plus regularized position-measurement signal."""

    detection: ThresholdFilterResult
    direct_component_labels: npt.NDArray[np.int32]
    measurement_component_labels: npt.NDArray[np.int32]
    position_signal_jy_per_beam: npt.NDArray[np.float64]
    significant_multiscale_support: npt.NDArray[np.bool_]
    scale_detection_planes: tuple[ScaleDetectionPlane, ...]


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
            nominal_scale_beam_fwhm=(response.nominal_scale_beam_fwhm),
        )
        for response, scale_mask, scale_snr in zip(
            atrous.responses,
            reconstruction.significant_scale_masks,
            scale_snrs,
            strict=True,
        )
    )


def refine_external_candidate_detection(
    detection: ThresholdFilterResult,
    significant_multiscale_support: npt.ArrayLike,
    beam: BeamShapePixels,
) -> ThresholdFilterResult:
    """Return a self-consistent result with reviewed multiscale boundaries."""
    component_labels = refine_multiscale_segment_labels(
        detection.component_labels,
        detection.combined_snr,
        significant_multiscale_support,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
    )
    retained_mask = np.asarray(component_labels > 0, dtype=np.bool_)
    component_labels.setflags(write=False)
    retained_mask.setflags(write=False)
    return replace(
        detection,
        retained_mask=retained_mask,
        component_labels=component_labels,
        component_count=int(np.count_nonzero(np.unique(component_labels) > 0)),
    )


def evaluate_post_campaign_candidate_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    *,
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveAReview,
) -> PostCampaignCandidateProducts:
    """Evaluate support and combine direct and denoised position weights."""
    prepared = prepare_scale_filter_inputs(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
    )
    _, atrous, detection = _corrective_results(
        prepared,
        beam,
        review,
        family="residual-b3-atrous",
    )
    if atrous is None:
        raise RuntimeError(
            "post-campaign candidate requires residual B3 evidence"
        )
    reconstruction = reconstruct_significant_atrous(
        atrous,
        detection_sigma=review.matrix.detection_sigma,
        island_sigma=review.matrix.island_sigma,
        minimum_support_fraction=review.matrix.support_fraction_bounds[0],
    )
    significant_support = np.asarray(
        reconstruction.support_mask,
        dtype=np.bool_,
    ).copy()
    significant_support.setflags(write=False)
    direct_labels = np.asarray(
        detection.component_labels,
        dtype=np.int32,
    ).copy()
    direct_labels.setflags(write=False)
    return PostCampaignCandidateProducts(
        detection=refine_external_candidate_detection(
            detection,
            reconstruction.support_mask,
            beam,
        ),
        direct_component_labels=direct_labels,
        measurement_component_labels=direct_labels,
        position_signal_jy_per_beam=(
            prepared.residual_jy_per_beam
            + atrous.reconstructed_signal_jy_per_beam
        ),
        significant_multiscale_support=significant_support,
        scale_detection_planes=_retained_scale_detection_planes(
            atrous,
            reconstruction,
            prepared.scientifically_valid,
            minimum_support_fraction=(
                review.matrix.support_fraction_bounds[0]
            ),
        ),
    )


def evaluate_public_finder_correction_candidate_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    *,
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveAReview,
) -> PostCampaignCandidateProducts:
    """Evaluate direct seeds and attach support without connected unions."""
    prepared = prepare_scale_filter_inputs(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
    )
    matched, atrous, _ = _corrective_results(
        prepared,
        beam,
        review,
        family="residual-b3-atrous",
    )
    if atrous is None:
        raise RuntimeError(
            "public-finder correction requires residual B3 evidence"
        )
    direct_detection = detect_residual_multiscale_islands(
        prepared,
        matched,
        atrous,
        beam,
        ResidualMultiscaleDetectionConfig(
            detection_threshold_sigma=review.matrix.detection_sigma,
            island_threshold_sigma=review.matrix.island_sigma,
            minimum_scale_support_fraction=(
                review.matrix.support_fraction_bounds[0]
            ),
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
        direct_detection.reconstruction.support_mask,
        dtype=np.bool_,
    ).copy()
    significant_support.setflags(write=False)
    direct_labels = np.asarray(
        direct_detection.component_labels,
        dtype=np.int32,
    ).copy()
    direct_labels.setflags(write=False)
    measurement_labels = np.asarray(
        measurement_labels,
        dtype=np.int32,
    ).copy()
    measurement_labels.setflags(write=False)
    return PostCampaignCandidateProducts(
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
            minimum_support_fraction=(
                review.matrix.support_fraction_bounds[0]
            ),
        ),
    )


def evaluate_post_campaign_candidate_detection(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    *,
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveAReview,
) -> ThresholdFilterResult:
    """Return only refined support for detection-level comparisons."""
    return evaluate_post_campaign_candidate_products(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
        beam=beam,
        review=review,
    ).detection


def diagnose_compact_component_realization(  # noqa: PLR0913
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    candidate: Sequence[CatalogueSource],
    *,
    implementation_identifier: str,
    outlier_thresholds: CatalogueOutlierThresholds,
    position_angle_minimum_axis_ratio: float,
    maximum_separation_beams: float = 0.5,
) -> CampaignRealizationDiagnostic:
    """Diagnose a fitted-component product without source canonicalization."""
    return diagnose_phase_four_realization(
        dataset,
        recipe,
        candidate,
        implementation_identifier=implementation_identifier,
        outlier_thresholds=outlier_thresholds,
        position_angle_minimum_axis_ratio=(position_angle_minimum_axis_ratio),
        maximum_separation_beams=maximum_separation_beams,
        catalogue_semantics="fitted-gaussian-component",
    )
