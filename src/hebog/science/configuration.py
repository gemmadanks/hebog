"""Current scientific configuration for installed source finding."""

from __future__ import annotations

from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    CompactDeblendConfig,
    CompactGaussianFitConfig,
    CompactMomentConfig,
    DetectionStageConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)


def source_finder_configs() -> tuple[
    DetectionStageConfig,
    CompactDeblendConfig,
    CompactMomentConfig,
    CompactGaussianFitConfig,
]:
    """Return the current source-finder scientific configuration."""
    statistics = RmsWindowStatisticsConfig(3.0, 10, 6)
    detection = DetectionStageConfig(
        background_rms=BackgroundRmsConfig(
            coarse=RmsGridConfig((150, 150), (50, 50), statistics, 32),
            adaptive=AdaptiveRmsConfig(
                grid=RmsGridConfig((35, 35), (7, 7), statistics, 32),
                candidate_threshold_sigma=75.0,
                influence_radius_pixels=75.0,
                transition_width_pixels=20.0,
            ),
            maximum_spatial_window_fraction=0.25,
            maximum_constant_map_pixels=1_000_000,
        ),
        source_finder=SourceFinderConfig(5.0, 3.0, 7),
    )
    return (
        detection,
        CompactDeblendConfig(
            5.0,
            2,
            # Judged at the true pass between two peaks, the highest level
            # at which one eight-connected part of the island holds both.
            # At 1.0 smooth extended emission in beam-correlated noise
            # splits on noise about twice as often as at 1.5 (`LOG.md`,
            # 3 October).
            1.5,
            7,
            100_000,
            250_000,
        ),
        CompactMomentConfig(3, 1e-12),
        CompactGaussianFitConfig(
            7,
            300,
            0.2,
            30.0,
            5.0,
            1.0,
            1e-8,
            30.0,
            component_extension_significance_sigma=1.5,
            integrated_flux_bias_correction_sigma=0.075,
            pixel_support="owned-region",
            # Beam-correlated GLS weighting amplifies pixel-independent
            # noise and lost most components on such images; diagonal
            # weighting is robust to either noise model.
            point_estimator="diagonal-weighted",
            model_selection="beam-or-free",
        ),
    )
