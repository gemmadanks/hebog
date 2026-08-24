# pyright: reportPrivateUsage=false
"""Prospective science corrections after the closed Phase 5 campaign."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np
import numpy.typing as npt

from hebog.algorithms.extended_measurement import (
    refine_multiscale_segment_labels,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    prepare_scale_filter_inputs,
    reconstruct_significant_atrous,
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
    position_signal_jy_per_beam: npt.NDArray[np.float64]


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
    return PostCampaignCandidateProducts(
        detection=refine_external_candidate_detection(
            detection,
            reconstruction.support_mask,
            beam,
        ),
        position_signal_jy_per_beam=(
            prepared.residual_jy_per_beam
            + atrous.reconstructed_signal_jy_per_beam
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
