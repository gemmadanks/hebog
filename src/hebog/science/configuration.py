"""Current scientific configuration for installed source finding."""

from __future__ import annotations

from dataclasses import replace

from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    CompactCatalogueConfig,
    CompactDeblendConfig,
    CompactGaussianFitConfig,
    CompactMomentConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)
from hebog.stages.detection import DetectionStageConfig


def source_finder_configs() -> tuple[
    DetectionStageConfig,
    CompactDeblendConfig,
    CompactMomentConfig,
    CompactGaussianFitConfig,
    CompactCatalogueConfig,
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
            1.0,
            7,
            100_000,
            250_000,
            8_000,
            500_000,
        ),
        CompactMomentConfig(3, 1e-12),
        replace(
            CompactGaussianFitConfig(
                7,
                300,
                0.2,
                30.0,
                5.0,
                1.0,
                1e-8,
                30.0,
                background_model="fixed-zero",
                pixel_support="owned-region",
                # Beam-correlated GLS weighting amplifies pixel-independent
                # noise and lost most components on such images; diagonal
                # weighting is robust to either noise model.
                point_estimator="diagonal-weighted",
                model_selection="beam-or-free",
                position_estimator="bounded-context-free",
            ),
            position_estimator="selected-model",
            component_extension_significance_sigma=1.5,
            integrated_flux_bias_correction_sigma=0.075,
            association_aperture_radius_sigma=1.5,
        ),
        CompactCatalogueConfig(10_000, 1e-10, 5.0),
    )
