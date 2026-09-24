# pyright: reportMissingTypeStubs=false
"""Current continuum detection and publication-support composition."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import numpy.typing as npt

from hebog.algorithms.multiscale_association import (
    ScaleDetectionRecords,
    scale_detections_from_islands,
)
from hebog.config import (
    CompactDeblendConfig,
    ResidualMultiscaleDetectionConfig,
    SourceFinderConfig,
)
from hebog.science.configuration import source_finder_configs
from hebog.science.models import (
    ThresholdFilterResult,
    TiledMultiscaleDetection,
    TiledSupportLabels,
)
from hebog.science.profile import ContinuumScienceProfile

CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS = 1.5


def compact_deblend_config(
    config: SourceFinderConfig,
) -> CompactDeblendConfig:
    """Return the reviewed deblending policy at the caller's threshold.

    A parent is deblended only where its peak clears the caller's detection
    threshold, so the reviewed minimum is lowered to just below it rather
    than to a second, independent threshold.
    """
    return replace(
        source_finder_configs()[1],
        minimum_peak_signal_to_noise=float(
            np.nextafter(config.detection_threshold_sigma, -np.inf)
        ),
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


def require_valid_scale_support(
    multiscale: TiledMultiscaleDetection,
    valid_pixels: npt.NDArray[np.bool_],
) -> None:
    """Reject published scale support outside the valid scientific domain.

    Raises:
        ValueError: If any scale claims a pixel the domain excludes.
    """
    for scale_mask in multiscale.significant_scale_masks:
        if scale_mask.shape != valid_pixels.shape or np.any(
            scale_mask & ~valid_pixels
        ):
            raise ValueError("scale support must be scientifically valid")


def retained_scale_detections(
    multiscale: TiledMultiscaleDetection,
    valid_pixels: npt.NDArray[np.bool_],
) -> tuple[ScaleDetectionRecords, ...]:
    """Describe the retained per-scale features from published records.

    The detection pass reconciled these features and published their labels,
    so this step names them without labelling a plane again.
    """
    require_valid_scale_support(multiscale, valid_pixels)
    return tuple(
        scale_detections_from_islands(
            islands,
            scale_order=scale_order,
            nominal_scale_beam_fwhm=nominal_beam_fwhm,
        )
        for scale_order, (islands, nominal_beam_fwhm) in enumerate(
            zip(
                multiscale.scale_islands_by_order,
                multiscale.scale_nominal_beam_fwhms,
                strict=True,
            ),
            start=1,
        )
    )


def build_continuum_detection(
    positive_rms_pixels: npt.NDArray[np.bool_],
    *,
    multiscale: TiledMultiscaleDetection,
    labels: TiledSupportLabels,
) -> ThresholdFilterResult:
    """Assemble the published detection from the tiled passes.

    Every decision it carries was taken on a tile core or on one owner's
    window: the detection pass published the seeds and support, and the
    support pass published the owner labels, the publication labels and the
    mask with island admission applied. No scale may claim a pixel with no
    usable local noise, which is what this step still checks.

    Raises:
        ValueError: If the mask and the publication labels disagree, or a
            scale claims a pixel outside the usable domain.
    """
    require_valid_scale_support(multiscale, positive_rms_pixels)
    # The published planes belong to the caller, so this record owns copies
    # rather than freezing arrays it did not create.
    publication_labels = np.array(
        labels.publication_labels,
        dtype=np.int32,
        copy=True,
    )
    retained_mask = np.array(labels.retained_mask, dtype=np.bool_, copy=True)
    if np.any(retained_mask != (publication_labels > 0)):
        raise ValueError(
            "published retained mask must agree with publication labels"
        )
    publication_labels.setflags(write=False)
    retained_mask.setflags(write=False)
    return ThresholdFilterResult(
        retained_mask=retained_mask,
        component_labels=publication_labels,
        component_count=int(
            np.count_nonzero(np.unique(labels.component_labels) > 0)
        ),
    )
