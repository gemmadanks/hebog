# pyright: reportMissingTypeStubs=false
"""Current continuum detection and publication-support composition."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

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
from hebog.science.models import TiledMultiscaleDetection
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


def retained_scale_detections(
    multiscale: TiledMultiscaleDetection,
) -> tuple[ScaleDetectionRecords, ...]:
    """Describe the retained per-scale features from published records.

    The detection pass reconciled these features and published their labels,
    so this step names them without labelling a plane again, and without
    holding one: the cores that wrote the scale masks already required them to
    lie inside the domain their own estimate covers.
    """
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
