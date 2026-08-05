"""Bounded Hebog execution used by isolated scientific campaigns."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

import numpy as np

from hebog.algorithms.astrometry import compact_geometry_at_pixel
from hebog.algorithms.catalogue import complete_compact_catalogue
from hebog.algorithms.partitioning import plan_image_partitions
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
from hebog.data_models import ImageBounds
from hebog.data_models.catalogues import GaussianShape, SourceCatalogue
from hebog.data_models.images import ImageMetadata
from hebog.executors import SerialExecutor
from hebog.io import ImageWindow, ZarrProductSink
from hebog.stages.catalogue import run_compact_catalogue_stage
from hebog.stages.detection import DetectionStageConfig, run_detection_stage
from hebog.validation.comparison import CatalogueEllipse, CatalogueSource
from hebog.validation.datasets import (
    DatasetRecord,
    SyntheticRecipe,
    generate_synthetic_window,
)
from hebog.validation.materialization import synthetic_image_metadata

RecipeProcessor: TypeAlias = Callable[
    [SyntheticRecipe, DatasetRecord, Path],
    tuple[CatalogueSource, ...],
]


class _SyntheticImageSource:
    """Generate exact float64 windows without materializing a full plane."""

    def __init__(self, recipe: SyntheticRecipe) -> None:
        self._recipe = recipe

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return one generated window and its finite-pixel validity."""
        values = generate_synthetic_window(
            self._recipe,
            y_start=bounds.y_start,
            y_stop=bounds.y_stop,
            x_start=bounds.x_start,
            x_stop=bounds.x_stop,
        )
        return ImageWindow(
            bounds=bounds,
            values=np.asarray(values, dtype=np.float64),
            valid_pixels=np.isfinite(values),
        )

    def read_windows(
        self,
        bounds_collection: tuple[ImageBounds, ...],
    ) -> tuple[ImageWindow, ...]:
        """Return generated windows in request order."""
        return tuple(self.read_window(bounds) for bounds in bounds_collection)


def phase_four_candidate_configs() -> tuple[
    DetectionStageConfig,
    CompactDeblendConfig,
    CompactMomentConfig,
    CompactGaussianFitConfig,
    CompactCatalogueConfig,
]:
    """Return the frozen Phase 4 candidate scientific configuration."""
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
            point_estimator="correlated-gls",
            model_selection="beam-or-free",
            position_estimator="bounded-context-free",
        ),
        CompactCatalogueConfig(10_000, 1e-10, 5.0),
    )


def hebog_campaign_configuration() -> dict[str, object]:
    """Return the complete candidate policy used for evidence identity."""
    detection, deblend, moment, fit, catalogue = phase_four_candidate_configs()
    coarse = detection.background_rms.coarse
    adaptive = detection.background_rms.adaptive
    assert adaptive is not None
    statistics = coarse.statistics
    return {
        "adaptive_rms": {
            "candidate_threshold_sigma": adaptive.candidate_threshold_sigma,
            "influence_radius_pixels": adaptive.influence_radius_pixels,
            "step_yx": list(adaptive.grid.step_yx),
            "transition_width_pixels": adaptive.transition_width_pixels,
            "window_shape_yx": list(adaptive.grid.window_shape_yx),
        },
        "catalogue": {
            "deconvolution_axis_significance_sigma": (
                catalogue.deconvolution_axis_significance_sigma
            ),
            "deconvolution_relative_tolerance": (
                catalogue.deconvolution_relative_tolerance
            ),
            "extension_significance_sigma": (
                catalogue.extension_significance_sigma
            ),
            "maximum_catalogue_records": catalogue.maximum_catalogue_records,
        },
        "coarse_rms": {
            "maximum_batch_cells": coarse.maximum_batch_cells,
            "step_yx": list(coarse.step_yx),
            "window_shape_yx": list(coarse.window_shape_yx),
        },
        "deblending": {
            "maximum_batch_pixels": deblend.maximum_batch_pixels,
            "maximum_compact_bounds_pixels": (
                deblend.maximum_compact_bounds_pixels
            ),
            "maximum_compact_island_pixels": (
                deblend.maximum_compact_island_pixels
            ),
            "minimum_peak_separation_pixels": (
                deblend.minimum_peak_separation_pixels
            ),
            "minimum_peak_signal_to_noise": (
                deblend.minimum_peak_signal_to_noise
            ),
            "minimum_region_pixels": deblend.minimum_region_pixels,
            "minimum_saddle_depth_sigma": deblend.minimum_saddle_depth_sigma,
            "target_batch_pixels": deblend.target_batch_pixels,
        },
        "executor": "serial",
        "fitting": {
            "association_aperture_minimum_fixed_beam_model_fraction": (
                fit.association_aperture_minimum_fixed_beam_model_fraction
            ),
            "association_aperture_radius_sigma": (
                fit.association_aperture_radius_sigma
            ),
            "background_model": fit.background_model,
            "center_margin_pixels": fit.center_margin_pixels,
            "context_margin_pixels": fit.context_margin_pixels,
            "convergence_tolerance": fit.convergence_tolerance,
            "maximum_amplitude_factor": fit.maximum_amplitude_factor,
            "maximum_axis_ratio": fit.maximum_axis_ratio,
            "maximum_background_offset_sigma": (
                fit.maximum_background_offset_sigma
            ),
            "maximum_function_evaluations": fit.maximum_function_evaluations,
            "maximum_information_condition_number": (
                fit.maximum_information_condition_number
            ),
            "maximum_sigma_pixels": fit.maximum_sigma_pixels,
            "minimum_fit_pixels": fit.minimum_fit_pixels,
            "minimum_sigma_pixels": fit.minimum_sigma_pixels,
            "extension_significance_sigma": (fit.extension_significance_sigma),
            "maximum_gls_pixels": fit.maximum_gls_pixels,
            "model_selection": fit.model_selection,
            "pixel_support": fit.pixel_support,
            "point_estimator": fit.point_estimator,
            "position_estimator": fit.position_estimator,
        },
        "image_dtype": "float64",
        "moment": {
            "covariance_relative_tolerance": (
                moment.covariance_relative_tolerance
            ),
            "minimum_shape_pixels": moment.minimum_shape_pixels,
        },
        "rms_statistics": {
            "clipping_sigma": statistics.clipping_sigma,
            "maximum_iterations": statistics.maximum_iterations,
            "minimum_samples": statistics.minimum_samples,
        },
        "source_finder": {
            "detection_threshold_sigma": (
                detection.source_finder.detection_threshold_sigma
            ),
            "island_threshold_sigma": (
                detection.source_finder.island_threshold_sigma
            ),
            "minimum_island_pixels": (
                detection.source_finder.minimum_island_pixels
            ),
        },
        "tile_core_shape_yx": [128, 128],
    }


def _shape(shape: GaussianShape | None) -> CatalogueEllipse | None:
    """Translate one internal ellipse to the comparison record."""
    if shape is None:
        return None
    return CatalogueEllipse(
        major_fwhm_degrees=shape.major_fwhm_degrees,
        minor_fwhm_degrees=shape.minor_fwhm_degrees,
        position_angle_degrees=shape.position_angle_degrees,
        major_fwhm_error_degrees=shape.major_fwhm_error_degrees,
        minor_fwhm_error_degrees=shape.minor_fwhm_error_degrees,
        position_angle_error_degrees=shape.position_angle_error_degrees,
    )


def _comparison_sources(
    catalogue: SourceCatalogue,
    metadata: ImageMetadata,
) -> tuple[CatalogueSource, ...]:
    """Translate the internal catalogue without adapter round trips."""
    component_counts = {
        source.source_id: sum(
            component.source_id == source.source_id
            for component in catalogue.gaussian_components
        )
        for source in catalogue.sources
    }
    return tuple(
        CatalogueSource(
            identifier=source.source_id,
            right_ascension_degrees=source.position.right_ascension_degrees,
            declination_degrees=source.position.declination_degrees,
            peak_flux_jy_per_beam=source.flux.peak_flux_jy_per_beam,
            integrated_flux_jy=source.flux.integrated_flux_jy,
            association_integrated_flux_jy=(
                source.association_aperture_integrated_flux_jy
                if source.association_aperture_integrated_flux_jy is not None
                else (
                    source.flux.peak_flux_jy_per_beam
                    * source.fitted_shape.major_fwhm_degrees
                    * source.fitted_shape.minor_fwhm_degrees
                    / (
                        metadata.beam.major_fwhm_degrees
                        * metadata.beam.minor_fwhm_degrees
                    )
                    if source.fitted_shape is not None
                    else None
                )
            ),
            right_ascension_error_degrees=(
                source.position.right_ascension_error_degrees
            ),
            declination_error_degrees=(
                source.position.declination_error_degrees
            ),
            peak_flux_error_jy_per_beam=(
                source.flux.peak_flux_error_jy_per_beam
            ),
            integrated_flux_error_jy=source.flux.integrated_flux_error_jy,
            fitted_shape=_shape(source.fitted_shape),
            deconvolved_shape=_shape(source.deconvolved_shape),
            deconvolved_major_fwhm_degrees=(
                source.deconvolved_major_fwhm_degrees
            ),
            deconvolution_status=(
                "resolved"
                if source.deconvolved_shape is not None
                else "major-axis-only"
                if source.deconvolved_major_fwhm_degrees is not None
                else "unresolved"
                if "unresolved" in source.quality_flags
                else "unavailable"
            ),
            island_identifier=source.island_id,
            component_count=component_counts[source.source_id],
            quality_flags=source.quality_flags,
        )
        for source in catalogue.sources
    )


def process_hebog_recipe(
    recipe: SyntheticRecipe,
    dataset: DatasetRecord,
    directory: Path,
) -> tuple[CatalogueSource, ...]:
    """Run the complete bounded serial Hebog compact path for one image."""
    detection_config, deblend, moment, fit, catalogue_config = (
        phase_four_candidate_configs()
    )
    metadata = synthetic_image_metadata(dataset)
    source = _SyntheticImageSource(recipe)
    manifest = plan_image_partitions(
        image_shape_yx=recipe.shape_yx,
        tile_core_shape_yx=(128, 128),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        directory / "products.zarr",
        manifest,
        generation_id=f"{dataset.identifier}-{recipe.seed}",
    )
    executor = SerialExecutor()
    detection = run_detection_stage(
        source,
        manifest,
        detection_config,
        executor,
        sink,
    )
    geometry = compact_geometry_at_pixel(
        metadata,
        (recipe.shape_yx[1] / 2.0, recipe.shape_yx[0] / 2.0),
    )
    stage = run_compact_catalogue_stage(
        source,
        detection,
        deblend_config=deblend,
        moment_config=moment,
        fit_config=fit,
        catalogue_config=catalogue_config,
        geometry=geometry,
        metadata=metadata,
        executor=executor,
        sink=sink,
    )
    completed = complete_compact_catalogue(
        catalogue_id=f"{dataset.identifier}-{recipe.seed}",
        metadata=metadata,
        shards=stage.records,
        deferred_island_ids=tuple(
            item.island.island_id for item in stage.deferred_islands
        ),
        config=catalogue_config,
    )
    return _comparison_sources(completed.catalogue, metadata)
