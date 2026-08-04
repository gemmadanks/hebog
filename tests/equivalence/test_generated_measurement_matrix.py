"""Generated-truth Phase 4 compact fitting and association matrix."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pytest

from hebog.algorithms.astrometry import transform_compact_gaussian_fit
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    CompactDeblendConfig,
    CompactGaussianFitConfig,
    CompactMomentConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)
from hebog.data_models import ImageBounds
from hebog.data_models.catalogues import GaussianShape
from hebog.data_models.fitting import (
    FittedGaussianPixelParameters,
    ValidCompactGaussianFit,
)
from hebog.data_models.images import ImageMetadata
from hebog.data_models.measurement import CompactMeasurementGeometry
from hebog.executors import SerialExecutor
from hebog.io import ImageWindow, ZarrProductSink
from hebog.stages.detection import DetectionStageConfig, run_detection_stage
from hebog.stages.fitting import run_compact_gaussian_fit_stage
from hebog.validation.comparison import (
    CatalogueEllipse,
    CatalogueMatch,
    CatalogueOutlierThresholds,
    CatalogueSource,
    compare_catalogues,
    evaluate_uncertainty_calibration,
    uncertainty_calibration_report,
)
from hebog.validation.contracts import (
    PhaseFourOutlierDefinition,
    load_phase_four_measurement_contract,
    load_phase_four_scientific_gates,
)
from hebog.validation.datasets import (
    AssociationTruthGroup,
    DatasetRecord,
    SyntheticRecipe,
    SyntheticSource,
    generate_synthetic_window,
    iter_dataset_recipes,
    load_dataset_manifest,
)
from hebog.validation.materialization import synthetic_image_metadata

pytestmark = pytest.mark.equivalence

_ROOT = Path(__file__).parents[2]
_DATASET_ROOT = _ROOT / "config/datasets"


def _catastrophic_metric_flags(
    match: CatalogueMatch,
    thresholds: PhaseFourOutlierDefinition,
) -> dict[str, bool]:
    """Expose every governed catastrophic comparison independently."""
    fitted_axis_values = tuple(
        abs(value)
        for value in (
            match.fitted_major_axis_fractional_difference,
            match.fitted_minor_axis_fractional_difference,
        )
        if value is not None
    )
    deconvolved_axis_values = tuple(
        abs(value)
        for value in (
            match.deconvolved_major_axis_fractional_difference,
            match.deconvolved_minor_axis_fractional_difference,
        )
        if value is not None
    )
    return {
        "position": match.separation_beam_fwhm > thresholds.position_beams,
        "peak-flux": (
            abs(match.peak_flux_fractional_difference)
            > thresholds.peak_flux_fractional_difference
        ),
        "integrated-flux": (
            abs(match.integrated_flux_fractional_difference)
            > thresholds.integrated_flux_fractional_difference
        ),
        "fitted-axis": (
            bool(fitted_axis_values)
            and max(fitted_axis_values)
            > thresholds.fitted_axis_fractional_difference
        ),
        "deconvolved-axis": (
            bool(deconvolved_axis_values)
            and max(deconvolved_axis_values)
            > thresholds.deconvolved_axis_fractional_difference
        ),
    }


def _is_gated_catastrophic(
    metric_flags: dict[str, bool],
    *,
    classification_stratum: str,
) -> bool:
    """Exclude only marginal-extension integrated flux from the gate."""
    return any(
        failed
        for metric, failed in metric_flags.items()
        if not (
            classification_stratum == "shape-marginal-resolved"
            and metric == "integrated-flux"
        )
    )


class _SyntheticImageSource:
    """Generate exact bounded windows from one governed recipe."""

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
            values=values,
            valid_pixels=np.isfinite(values),
        )

    def read_windows(
        self,
        bounds_collection: tuple[ImageBounds, ...],
    ) -> tuple[ImageWindow, ...]:
        """Generate several bounded windows without retaining the plane."""
        return tuple(self.read_window(bounds) for bounds in bounds_collection)


def _detection_config() -> DetectionStageConfig:
    """Use the frozen Rapthor compact threshold and RMS profile."""
    statistics = RmsWindowStatisticsConfig(
        clipping_sigma=3.0,
        maximum_iterations=10,
        minimum_samples=6,
    )
    return DetectionStageConfig(
        background_rms=BackgroundRmsConfig(
            coarse=RmsGridConfig(
                window_shape_yx=(150, 150),
                step_yx=(50, 50),
                statistics=statistics,
                maximum_batch_cells=32,
            ),
            adaptive=AdaptiveRmsConfig(
                grid=RmsGridConfig(
                    window_shape_yx=(35, 35),
                    step_yx=(7, 7),
                    statistics=statistics,
                    maximum_batch_cells=32,
                ),
                candidate_threshold_sigma=75.0,
                influence_radius_pixels=75.0,
                transition_width_pixels=20.0,
            ),
            maximum_spatial_window_fraction=0.25,
            maximum_constant_map_pixels=1_000_000,
        ),
        source_finder=SourceFinderConfig(
            detection_threshold_sigma=5.0,
            island_threshold_sigma=3.0,
            minimum_island_pixels=7,
        ),
    )


def _noise_correlation_covariance(
    dataset: DatasetRecord,
) -> tuple[float, float, float] | None:
    """Translate governed Gaussian correlation FWHM to pixel covariance."""
    correlation = dataset.recipe.noise_correlation
    if correlation is None:
        return None
    fwhm_to_sigma = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    major_variance = np.square(correlation.major_fwhm_pixels * fwhm_to_sigma)
    minor_variance = np.square(correlation.minor_fwhm_pixels * fwhm_to_sigma)
    angle = np.deg2rad(correlation.position_angle_degrees)
    cosine = np.cos(angle)
    sine = np.sin(angle)
    covariance_xx = major_variance * cosine**2 + minor_variance * sine**2
    covariance_yy = major_variance * sine**2 + minor_variance * cosine**2
    covariance_xy = (major_variance - minor_variance) * sine * cosine
    return (
        float(covariance_xx),
        float(covariance_xy),
        float(covariance_yy),
    )


def _fits(
    dataset: DatasetRecord,
    root: Path,
    recipe: SyntheticRecipe | None = None,
) -> tuple[ValidCompactGaussianFit, ...]:
    """Run bounded detection, deblending, moments, and fit-all measurement."""
    selected_recipe = recipe or dataset.recipe
    source = _SyntheticImageSource(selected_recipe)
    shape_yx = selected_recipe.shape_yx
    manifest = plan_image_partitions(
        image_shape_yx=shape_yx,
        tile_core_shape_yx=(128, 128),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        root / "products.zarr",
        manifest,
        generation_id=f"{dataset.identifier}-{selected_recipe.seed}",
    )
    detection = run_detection_stage(
        source,
        manifest,
        _detection_config(),
        SerialExecutor(),
        sink,
    )
    result = run_compact_gaussian_fit_stage(
        source,
        detection,
        deblend_config=CompactDeblendConfig(
            minimum_peak_signal_to_noise=5.0,
            minimum_peak_separation_pixels=2,
            minimum_saddle_depth_sigma=1.0,
            minimum_region_pixels=7,
            maximum_compact_island_pixels=100_000,
            maximum_compact_bounds_pixels=250_000,
            maximum_batch_pixels=500_000,
        ),
        moment_config=CompactMomentConfig(
            minimum_shape_pixels=3,
            covariance_relative_tolerance=1e-12,
        ),
        fit_config=CompactGaussianFitConfig(
            minimum_fit_pixels=7,
            maximum_function_evaluations=300,
            minimum_sigma_pixels=0.2,
            maximum_sigma_pixels=30.0,
            maximum_amplitude_factor=5.0,
            center_margin_pixels=1.0,
            convergence_tolerance=1e-8,
            maximum_axis_ratio=30.0,
        ),
        geometry=CompactMeasurementGeometry(
            pixel_solid_angle_steradians=1.0,
            restoring_beam_solid_angle_steradians=1.0,
            noise_correlation_covariance_pixels_squared=(
                _noise_correlation_covariance(dataset)
            ),
        ),
        executor=SerialExecutor(),
        sink=sink,
    )
    assert not result.deferred_islands
    return tuple(
        fit
        for island in result.records
        for fit in island.region_fits
        if isinstance(fit, ValidCompactGaussianFit)
    )


def _ellipse(shape: GaussianShape | None) -> CatalogueEllipse | None:
    """Translate an internal Gaussian ellipse to the comparison oracle."""
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


def _comparison_source(
    identifier: str,
    fit: ValidCompactGaussianFit,
    metadata: ImageMetadata,
    *,
    island_identifier: str,
) -> CatalogueSource:
    """Transform one valid pixel fit to canonical comparison quantities."""
    transformed = transform_compact_gaussian_fit(
        fit,
        metadata,
    )
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=(transformed.position.right_ascension_degrees),
        declination_degrees=transformed.position.declination_degrees,
        peak_flux_jy_per_beam=transformed.flux.peak_flux_jy_per_beam,
        integrated_flux_jy=transformed.flux.integrated_flux_jy,
        right_ascension_error_degrees=(
            transformed.position.right_ascension_error_degrees
        ),
        declination_error_degrees=(
            transformed.position.declination_error_degrees
        ),
        peak_flux_error_jy_per_beam=(
            transformed.flux.peak_flux_error_jy_per_beam
        ),
        integrated_flux_error_jy=(transformed.flux.integrated_flux_error_jy),
        fitted_shape=_ellipse(transformed.fitted_shape),
        deconvolved_shape=_ellipse(transformed.deconvolved_shape),
        deconvolved_major_fwhm_degrees=(
            transformed.deconvolved_major_fwhm_degrees
        ),
        deconvolution_status=transformed.deconvolution_status,
        island_identifier=island_identifier,
        component_count=1,
        quality_flags=transformed.quality_flags,
    )


def _truth_source(  # noqa: PLR0913
    identifier: str,
    measured_fit: ValidCompactGaussianFit,
    truth: SyntheticSource,
    dataset: DatasetRecord,
    metadata: ImageMetadata,
    *,
    island_identifier: str,
) -> CatalogueSource:
    """Transform exact analytic truth through the production WCS boundary."""
    parameters = FittedGaussianPixelParameters(
        amplitude_jy_per_beam=truth.peak_flux_jy_per_beam,
        centroid_xy=(truth.x_pixel, truth.y_pixel),
        major_sigma_pixels=truth.major_sigma_pixels,
        minor_sigma_pixels=truth.minor_sigma_pixels,
        major_axis_angle_degrees=(
            truth.rotation_degrees_counterclockwise_from_x
        ),
        integrated_flux_jy=(
            truth.peak_flux_jy_per_beam
            * 2.0
            * np.pi
            * truth.major_sigma_pixels
            * truth.minor_sigma_pixels
        ),
        local_rms_jy_per_beam=dataset.recipe.noise_rms,
    )
    exact_fit = replace(
        measured_fit,
        parameters=parameters,
        uncertainty=None,
        quality_flags=(),
    )
    return _comparison_source(
        identifier,
        exact_fit,
        metadata,
        island_identifier=island_identifier,
    )


@pytest.mark.parametrize(
    "dataset_index",
    [0, 1],
)
def test_generated_compact_fits_meet_truth_gates(
    dataset_index: int,
    tmp_path: Path,
) -> None:
    """High-SNR generated sources retain position, flux, and fitted shape."""
    datasets = load_dataset_manifest(
        _DATASET_ROOT / "phase-4-regression.json"
    ).datasets
    position_beams: list[float] = []
    unresolved_group_position_beams: list[float] = []
    peak_fractional: list[float] = []
    integrated_fractional: list[float] = []
    unresolved_group_integrated_fractional: list[float] = []
    fitted_axis_fractional: list[float] = []
    position_angle_degrees: list[float] = []
    catastrophic_count = 0
    scientific_gates = load_phase_four_scientific_gates(
        _ROOT / "config/contracts/phase-4-scientific-gates.json"
    )
    for dataset in (datasets[dataset_index],):
        fits = _fits(dataset, tmp_path / dataset.identifier)
        groups = dataset.association_truth_groups or tuple(
            AssociationTruthGroup(
                identifier=f"source-{index + 1:05d}",
                source_indices=(index,),
                resolution_class="individually-resolvable",
                reference_position_xy=(source.x_pixel, source.y_pixel),
                reference_integrated_brightness_jy_pixels_per_beam=(
                    source.peak_flux_jy_per_beam
                    * 2.0
                    * np.pi
                    * source.major_sigma_pixels
                    * source.minor_sigma_pixels
                ),
            )
            for index, source in enumerate(dataset.recipe.sources)
            if source.peak_flux_jy_per_beam / dataset.recipe.noise_rms >= 10.0
        )
        assert len(fits) == len(groups)
        unmatched = list(fits)
        for group in groups:
            selected = min(
                unmatched,
                key=lambda fit: np.hypot(
                    fit.parameters.centroid_xy[0]
                    - group.reference_position_xy[0],
                    fit.parameters.centroid_xy[1]
                    - group.reference_position_xy[1],
                ),
            )
            unmatched.remove(selected)
            separation = np.hypot(
                selected.parameters.centroid_xy[0]
                - group.reference_position_xy[0],
                selected.parameters.centroid_xy[1]
                - group.reference_position_xy[1],
            )
            normalized_separation = float(
                separation / dataset.beam.major_fwhm_pixels
            )
            integrated_difference = abs(
                selected.parameters.integrated_flux_jy
                / group.reference_integrated_brightness_jy_pixels_per_beam
                - 1.0
            )
            if group.resolution_class == "unresolved-blend":
                unresolved_group_position_beams.append(normalized_separation)
                unresolved_group_integrated_fractional.append(
                    integrated_difference
                )
                continue
            position_beams.append(normalized_separation)
            integrated_fractional.append(integrated_difference)
            truth = dataset.recipe.sources[group.source_indices[0]]
            peak_fractional.append(
                abs(
                    selected.parameters.amplitude_jy_per_beam
                    / truth.peak_flux_jy_per_beam
                    - 1.0
                )
            )
            axis_differences = (
                abs(
                    selected.parameters.major_sigma_pixels
                    / truth.major_sigma_pixels
                    - 1.0
                ),
                abs(
                    selected.parameters.minor_sigma_pixels
                    / truth.minor_sigma_pixels
                    - 1.0
                ),
            )
            fitted_axis_fractional.extend(axis_differences)
            outlier = scientific_gates.catastrophic_outlier
            catastrophic_count += int(
                normalized_separation > outlier.position_beams
                or peak_fractional[-1]
                > outlier.peak_flux_fractional_difference
                or integrated_fractional[-1]
                > outlier.integrated_flux_fractional_difference
                or max(axis_differences)
                > outlier.fitted_axis_fractional_difference
            )
            if truth.major_sigma_pixels / truth.minor_sigma_pixels >= 1.1:
                raw_angle = abs(
                    selected.parameters.major_axis_angle_degrees
                    - truth.rotation_degrees_counterclockwise_from_x
                )
                position_angle_degrees.append(
                    float(min(raw_angle, 180.0 - raw_angle))
                )

    gates = (
        (position_beams, 0.02, 0.1),
        (peak_fractional, 0.02, 0.05),
        (integrated_fractional, 0.05, 0.1),
        (fitted_axis_fractional, 0.05, 0.1),
        (position_angle_degrees, 3.0, 10.0),
    )
    if scientific_gates.generated_regression.absolute_tail_policy == "gate":
        for values, median_limit, tail_limit in gates:
            if not values:
                continue
            assert np.median(values) <= median_limit
            assert np.percentile(values, 95) <= tail_limit
    assert catastrophic_count / len(position_beams) <= (
        scientific_gates.generated_regression.maximum_catastrophic_outlier_fraction
    )

    if unresolved_group_position_beams:
        group_gate = scientific_gates.unresolved_group
        assert np.median(unresolved_group_position_beams) <= (
            group_gate.maximum_median_position_beams
        )
        assert np.percentile(unresolved_group_position_beams, 95) <= (
            group_gate.maximum_percentile_95_position_beams
        )
        assert np.median(unresolved_group_integrated_fractional) <= (
            group_gate.maximum_median_integrated_flux_fractional_difference
        )
        assert np.percentile(unresolved_group_integrated_fractional, 95) <= (
            group_gate.maximum_percentile_95_integrated_flux_fractional_difference
        )


@pytest.mark.slow
def test_correlated_noise_uncertainties_pass_regression_calibration(  # noqa: C901, PLR0912, PLR0915
    tmp_path: Path,
) -> None:
    """Every governed SNR stratum passes the reviewed interval decisions."""
    dataset = load_dataset_manifest(
        _DATASET_ROOT / "phase-4-regression.json"
    ).datasets[0]
    gates = load_phase_four_scientific_gates(
        _ROOT / "config/contracts/phase-4-scientific-gates.json"
    )
    metadata = synthetic_image_metadata(dataset)
    source_to_stratum = {
        source_index: stratum.identifier
        for stratum in dataset.validation_strata
        for source_index in stratum.source_indices
    }
    metrics = (
        "right-ascension",
        "declination",
        "peak-flux",
        "integrated-flux",
    )
    samples: dict[tuple[str, str], list[float]] = {
        (stratum.identifier, metric): []
        for stratum in dataset.validation_strata
        for metric in metrics
    }
    classification_by_source = {
        source_index: stratum.identifier
        for stratum in dataset.classification_strata
        for source_index in stratum.source_indices
    }
    classification_available = {
        stratum.identifier: 0 for stratum in dataset.classification_strata
    }
    classification_correct = {
        stratum.identifier: 0 for stratum in dataset.classification_strata
    }
    integrated_flux_by_shape: dict[str, list[float]] = {
        stratum.identifier: [] for stratum in dataset.classification_strata
    }
    catastrophic_by_shape = {
        stratum.identifier: 0 for stratum in dataset.classification_strata
    }
    matched_by_shape = {
        stratum.identifier: 0 for stratum in dataset.classification_strata
    }
    catastrophic_metric_counts = {
        "position": 0,
        "peak-flux": 0,
        "integrated-flux": 0,
        "fitted-axis": 0,
        "deconvolved-axis": 0,
    }
    marginal_integrated_flux_catastrophic_count = 0
    outlier = gates.catastrophic_outlier
    outlier_thresholds = CatalogueOutlierThresholds(
        position_beams=outlier.position_beams,
        peak_flux_fractional_difference=(
            outlier.peak_flux_fractional_difference
        ),
        integrated_flux_fractional_difference=(
            outlier.integrated_flux_fractional_difference
        ),
        fitted_axis_fractional_difference=(
            outlier.fitted_axis_fractional_difference
        ),
        deconvolved_axis_fractional_difference=(
            outlier.deconvolved_axis_fractional_difference
        ),
    )

    recipes = iter_dataset_recipes(dataset)
    for recipe in recipes:
        unmatched = list(
            _fits(dataset, tmp_path / str(recipe.seed), recipe=recipe)
        )
        for source_index, truth in enumerate(recipe.sources):
            if not unmatched:
                continue
            stratum = source_to_stratum[source_index]
            selected = min(
                unmatched,
                key=lambda fit: np.hypot(
                    fit.parameters.centroid_xy[0] - truth.x_pixel,
                    fit.parameters.centroid_xy[1] - truth.y_pixel,
                ),
            )
            separation = np.hypot(
                selected.parameters.centroid_xy[0] - truth.x_pixel,
                selected.parameters.centroid_xy[1] - truth.y_pixel,
            )
            if separation > 0.5 * dataset.beam.major_fwhm_pixels:
                continue
            unmatched.remove(selected)
            uncertainty = selected.uncertainty
            if uncertainty is None:
                continue
            identifier = f"{recipe.seed}-source-{source_index:05d}"
            reference_source = _truth_source(
                f"truth-{identifier}",
                selected,
                truth,
                dataset,
                metadata,
                island_identifier=identifier,
            )
            candidate_source = _comparison_source(
                f"candidate-{identifier}",
                selected,
                metadata,
                island_identifier=identifier,
            )
            comparison = compare_catalogues(
                (reference_source,),
                (candidate_source,),
                beam_fwhm_degrees=metadata.beam.major_fwhm_degrees,
                maximum_separation_beams=0.5,
                outlier_thresholds=outlier_thresholds,
                position_angle_minimum_axis_ratio=1.1,
            )
            assert len(comparison.matches) == 1
            match = comparison.matches[0]
            integrated_error = candidate_source.integrated_flux_error_jy
            assert integrated_error is not None
            residuals = {
                "right-ascension": (
                    selected.parameters.centroid_xy[0] - truth.x_pixel
                )
                / np.sqrt(uncertainty.centroid_covariance_xx_pixels_squared),
                "declination": (
                    selected.parameters.centroid_xy[1] - truth.y_pixel
                )
                / np.sqrt(uncertainty.centroid_covariance_yy_pixels_squared),
                "peak-flux": (
                    selected.parameters.amplitude_jy_per_beam
                    - truth.peak_flux_jy_per_beam
                )
                / uncertainty.amplitude_error_jy_per_beam,
                "integrated-flux": (
                    candidate_source.integrated_flux_jy
                    - reference_source.integrated_flux_jy
                )
                / integrated_error,
            }
            for metric, residual in residuals.items():
                samples[(stratum, metric)].append(residual)
            classification_stratum = classification_by_source[source_index]
            metric_flags = _catastrophic_metric_flags(match, outlier)
            matched_by_shape[classification_stratum] += 1
            catastrophic_by_shape[classification_stratum] += int(
                _is_gated_catastrophic(
                    metric_flags,
                    classification_stratum=classification_stratum,
                )
            )
            for metric, failed in metric_flags.items():
                catastrophic_metric_counts[metric] += int(failed)
            marginal_integrated_flux_catastrophic_count += int(
                classification_stratum == "shape-marginal-resolved"
                and metric_flags["integrated-flux"]
            )
            integrated_flux_by_shape[classification_stratum].append(
                residuals["integrated-flux"]
            )
            if candidate_source.deconvolution_status in {
                "resolved",
                "major-axis-only",
                "unresolved",
            }:
                classification_available[classification_stratum] += 1
                expected = (
                    "unresolved"
                    if classification_stratum == "shape-unresolved"
                    else "resolved"
                )
                observed = (
                    "resolved"
                    if candidate_source.deconvolution_status
                    in {"resolved", "major-axis-only"}
                    else candidate_source.deconvolution_status
                )
                classification_correct[classification_stratum] += int(
                    observed == expected
                )

    uncertainty_gate = gates.uncertainty
    regression_gate = gates.generated_regression
    failures: list[tuple[object, ...]] = []
    classification_eligibility = {
        stratum.identifier: len(recipes) * len(stratum.source_indices)
        for stratum in dataset.classification_strata
    }
    for stratum in dataset.validation_strata:
        eligible_count = len(recipes) * len(stratum.source_indices)
        for metric in metrics:
            report = uncertainty_calibration_report(
                metric,
                samples[(stratum.identifier, metric)],
                eligible_count=eligible_count,
                confidence_level=uncertainty_gate.confidence_interval_level,
                bootstrap_resamples=uncertainty_gate.bootstrap_resamples,
                bootstrap_seed=uncertainty_gate.bootstrap_seed,
            )
            minimum_availability = (
                regression_gate.minimum_position_flux_uncertainty_availability
            )
            if report.availability_fraction < minimum_availability:
                failures.append(
                    (
                        stratum.identifier,
                        metric,
                        "availability",
                        report.sample_count,
                        report.eligible_count,
                    )
                )
            decision = evaluate_uncertainty_calibration(
                report,
                minimum_samples=uncertainty_gate.minimum_samples_per_stratum,
                nominal_coverage=uncertainty_gate.nominal_coverage,
                maximum_absolute_coverage_difference=(
                    uncertainty_gate.maximum_absolute_coverage_difference
                ),
                maximum_absolute_mean=(
                    uncertainty_gate.maximum_absolute_mean_normalized_residual
                ),
                minimum_standard_deviation=(
                    uncertainty_gate.minimum_normalized_residual_standard_deviation
                ),
                maximum_standard_deviation=(
                    uncertainty_gate.maximum_normalized_residual_standard_deviation
                ),
            )
            if metric != "integrated-flux" and decision.status != "pass":
                failures.append(
                    (
                        stratum.identifier,
                        metric,
                        decision.failed_metrics,
                        report.sample_count,
                        report.coverage_fraction,
                        report.coverage_confidence_interval,
                        report.mean_normalized_residual,
                        report.mean_confidence_interval,
                        report.sample_standard_deviation,
                        report.dispersion_confidence_interval,
                    )
                )
    for stratum_identifier in ("shape-unresolved",):
        report = uncertainty_calibration_report(
            "integrated-flux",
            integrated_flux_by_shape[stratum_identifier],
            eligible_count=classification_eligibility.get(
                stratum_identifier,
                len(integrated_flux_by_shape[stratum_identifier]),
            ),
            confidence_level=uncertainty_gate.confidence_interval_level,
            bootstrap_resamples=uncertainty_gate.bootstrap_resamples,
            bootstrap_seed=uncertainty_gate.bootstrap_seed,
        )
        decision = evaluate_uncertainty_calibration(
            report,
            minimum_samples=uncertainty_gate.minimum_samples_per_stratum,
            nominal_coverage=uncertainty_gate.nominal_coverage,
            maximum_absolute_coverage_difference=(
                uncertainty_gate.maximum_absolute_coverage_difference
            ),
            maximum_absolute_mean=(
                uncertainty_gate.maximum_absolute_mean_normalized_residual
            ),
            minimum_standard_deviation=(
                uncertainty_gate.minimum_normalized_residual_standard_deviation
            ),
            maximum_standard_deviation=(
                uncertainty_gate.maximum_normalized_residual_standard_deviation
            ),
        )
        if decision.status != "pass":
            failures.append(
                (
                    stratum_identifier,
                    "integrated-flux",
                    decision.failed_metrics,
                    report.sample_count,
                    report.coverage_fraction,
                    report.coverage_confidence_interval,
                    report.mean_normalized_residual,
                    report.mean_confidence_interval,
                    report.sample_standard_deviation,
                    report.dispersion_confidence_interval,
                )
            )
    for stratum_identifier, minimum in (
        (
            "shape-unresolved",
            regression_gate.minimum_point_source_specificity,
        ),
        (
            "shape-clear-resolved",
            regression_gate.minimum_clear_resolved_classification_recall,
        ),
    ):
        available = classification_available[stratum_identifier]
        eligible = classification_eligibility[stratum_identifier]
        if available / eligible < (
            regression_gate.minimum_deconvolution_classification_availability
        ):
            failures.append(
                (stratum_identifier, "classification-availability")
            )
        accuracy = (
            classification_correct[stratum_identifier] / available
            if available
            else 0.0
        )
        if accuracy < minimum:
            failures.append((stratum_identifier, "classification-accuracy"))
    catastrophic_count = sum(catastrophic_by_shape.values())
    matched_count = sum(matched_by_shape.values())
    if catastrophic_count / matched_count > (
        regression_gate.maximum_catastrophic_outlier_fraction
    ):
        failures.append(
            (
                "all-shapes",
                "catastrophic-outlier-fraction",
                catastrophic_count,
                matched_count,
                catastrophic_by_shape,
                catastrophic_metric_counts,
                marginal_integrated_flux_catastrophic_count,
            )
        )
    assert not failures, "\n".join(str(failure) for failure in failures)


@pytest.mark.slow
def test_edge_source_uncertainty_availability_passes_regression(
    tmp_path: Path,
) -> None:
    """Every image side contributes to the powered availability decision."""
    dataset = load_dataset_manifest(
        _DATASET_ROOT / "phase-4-regression.json"
    ).datasets[2]
    gates = load_phase_four_scientific_gates(
        _ROOT / "config/contracts/phase-4-scientific-gates.json"
    )
    recipes = iter_dataset_recipes(dataset)
    available_count = 0
    matched_by_source = [0] * len(dataset.recipe.sources)
    available_by_source = [0] * len(dataset.recipe.sources)
    missing_seeds_by_source: list[list[int]] = [
        [] for _ in dataset.recipe.sources
    ]

    for recipe in recipes:
        unmatched = list(
            _fits(dataset, tmp_path / str(recipe.seed), recipe=recipe)
        )
        for source_index, truth in enumerate(recipe.sources):
            if not unmatched:
                missing_seeds_by_source[source_index].append(recipe.seed)
                continue
            selected = min(
                unmatched,
                key=lambda fit: np.hypot(
                    fit.parameters.centroid_xy[0] - truth.x_pixel,
                    fit.parameters.centroid_xy[1] - truth.y_pixel,
                ),
            )
            separation = np.hypot(
                selected.parameters.centroid_xy[0] - truth.x_pixel,
                selected.parameters.centroid_xy[1] - truth.y_pixel,
            )
            if separation > 0.5 * dataset.beam.major_fwhm_pixels:
                missing_seeds_by_source[source_index].append(recipe.seed)
                continue
            unmatched.remove(selected)
            matched_by_source[source_index] += 1
            available_count += int(selected.uncertainty is not None)
            available_by_source[source_index] += int(
                selected.uncertainty is not None
            )

    eligible_count = len(recipes) * len(dataset.recipe.sources)
    assert eligible_count >= gates.uncertainty.minimum_samples_per_stratum
    assert available_count / eligible_count >= (
        gates.generated_regression.minimum_position_flux_uncertainty_availability
    ), (matched_by_source, available_by_source, missing_seeds_by_source)


@pytest.mark.qualification
@pytest.mark.slow
def test_compact_flux_heldout_measurement_qualification(  # noqa: C901, PLR0912, PLR0915
    tmp_path: Path,
) -> None:
    """Run the third held-out campaign only after named scientific review."""
    dataset = load_dataset_manifest(
        _DATASET_ROOT / "phase-4-qualification.json"
    ).datasets[0]
    gates = load_phase_four_scientific_gates(
        _ROOT / "config/contracts/phase-4-scientific-gates.json"
    )
    measurement_contract = load_phase_four_measurement_contract(
        _ROOT / "config/contracts/phase-4-measurement.json"
    )
    if (
        gates.status != "reviewed-provisional"
        or measurement_contract.status != "reviewed-provisional"
    ):
        pytest.skip(
            "replacement qualification requires named scientific review"
        )
    metadata = synthetic_image_metadata(dataset)
    outlier = gates.catastrophic_outlier
    outlier_thresholds = CatalogueOutlierThresholds(
        position_beams=outlier.position_beams,
        peak_flux_fractional_difference=(
            outlier.peak_flux_fractional_difference
        ),
        integrated_flux_fractional_difference=(
            outlier.integrated_flux_fractional_difference
        ),
        fitted_axis_fractional_difference=(
            outlier.fitted_axis_fractional_difference
        ),
        deconvolved_axis_fractional_difference=(
            outlier.deconvolved_axis_fractional_difference
        ),
    )
    source_strata = {
        source_index: tuple(
            stratum.identifier
            for stratum in dataset.validation_strata
            if source_index in stratum.source_indices
        )
        for source_index in range(len(dataset.recipe.sources))
    }
    classification_by_source = {
        source_index: stratum.identifier
        for stratum in dataset.classification_strata
        for source_index in stratum.source_indices
    }
    metrics = (
        "right-ascension",
        "declination",
        "peak-flux",
        "integrated-flux",
    )
    uncertainty_samples: dict[tuple[str, str], list[float]] = {
        (stratum.identifier, metric): []
        for stratum in dataset.validation_strata
        for metric in metrics
    }
    absolute_metrics: dict[str, list[float]] = {
        "position-beams": [],
        "peak-flux": [],
        "integrated-flux": [],
        "fitted-axis": [],
        "deconvolved-axis": [],
    }
    group_position_beams: list[float] = []
    group_integrated_fractional: list[float] = []
    matched_group_count = 0
    candidate_count = 0
    matched_individual_count = 0
    catastrophic_count = 0
    marginal_matched_individual_count = 0
    marginal_integrated_flux_catastrophic_count = 0
    classification_available = {
        "shape-unresolved": 0,
        "shape-clear-resolved": 0,
    }
    classification_correct = {
        "shape-unresolved": 0,
        "shape-clear-resolved": 0,
    }
    resolved_shape_eligible_count = 0
    resolved_shape_available_count = 0

    recipes = iter_dataset_recipes(dataset)
    for recipe in recipes:
        fits = _fits(dataset, tmp_path / str(recipe.seed), recipe=recipe)
        candidate_count += len(fits)
        unmatched = list(fits)
        for group in dataset.association_truth_groups:
            if not unmatched:
                continue
            selected = min(
                unmatched,
                key=lambda fit: np.hypot(
                    fit.parameters.centroid_xy[0]
                    - group.reference_position_xy[0],
                    fit.parameters.centroid_xy[1]
                    - group.reference_position_xy[1],
                ),
            )
            separation = float(
                np.hypot(
                    selected.parameters.centroid_xy[0]
                    - group.reference_position_xy[0],
                    selected.parameters.centroid_xy[1]
                    - group.reference_position_xy[1],
                )
            )
            if separation > 0.5 * dataset.beam.major_fwhm_pixels:
                continue
            unmatched.remove(selected)
            matched_group_count += 1
            if group.resolution_class == "unresolved-blend":
                group_position_beams.append(
                    separation / dataset.beam.major_fwhm_pixels
                )
                group_integrated_fractional.append(
                    abs(
                        selected.parameters.integrated_flux_jy
                        / (
                            group.reference_integrated_brightness_jy_pixels_per_beam
                        )
                        - 1.0
                    )
                )
                continue

            source_index = group.source_indices[0]
            truth = recipe.sources[source_index]
            identifier = f"{recipe.seed}-{group.identifier}"
            reference_source = _truth_source(
                f"truth-{identifier}",
                selected,
                truth,
                dataset,
                metadata,
                island_identifier=group.identifier,
            )
            candidate_source = _comparison_source(
                f"candidate-{identifier}",
                selected,
                metadata,
                island_identifier=group.identifier,
            )
            pair = compare_catalogues(
                (reference_source,),
                (candidate_source,),
                beam_fwhm_degrees=metadata.beam.major_fwhm_degrees,
                maximum_separation_beams=0.5,
                outlier_thresholds=outlier_thresholds,
                position_angle_minimum_axis_ratio=1.1,
            )
            if not pair.matches:
                continue
            matched_individual_count += 1
            match = pair.matches[0]
            absolute_metrics["position-beams"].append(
                match.separation_beam_fwhm
            )
            absolute_metrics["peak-flux"].append(
                abs(match.peak_flux_fractional_difference)
            )
            absolute_metrics["integrated-flux"].append(
                abs(match.integrated_flux_fractional_difference)
            )
            fitted_axis_values = tuple(
                abs(value)
                for value in (
                    match.fitted_major_axis_fractional_difference,
                    match.fitted_minor_axis_fractional_difference,
                )
                if value is not None
            )
            if fitted_axis_values:
                absolute_metrics["fitted-axis"].append(max(fitted_axis_values))
            deconvolved_axis_values = tuple(
                abs(value)
                for value in (
                    match.deconvolved_major_axis_fractional_difference,
                    match.deconvolved_minor_axis_fractional_difference,
                )
                if value is not None
            )
            if deconvolved_axis_values:
                absolute_metrics["deconvolved-axis"].append(
                    max(deconvolved_axis_values)
                )
            classification_stratum = classification_by_source[source_index]
            metric_flags = _catastrophic_metric_flags(match, outlier)
            catastrophic_count += int(
                _is_gated_catastrophic(
                    metric_flags,
                    classification_stratum=classification_stratum,
                )
            )
            if classification_stratum == "shape-marginal-resolved":
                marginal_matched_individual_count += 1
                marginal_integrated_flux_catastrophic_count += int(
                    metric_flags["integrated-flux"]
                )
            if classification_stratum in classification_available and (
                candidate_source.deconvolution_status
                in {"resolved", "major-axis-only", "unresolved"}
            ):
                classification_available[classification_stratum] += 1
                expected_status = (
                    "unresolved"
                    if classification_stratum == "shape-unresolved"
                    else "resolved"
                )
                observed_status = (
                    "resolved"
                    if candidate_source.deconvolution_status
                    in {"resolved", "major-axis-only"}
                    else candidate_source.deconvolution_status
                )
                classification_correct[classification_stratum] += int(
                    observed_status == expected_status
                )
            if classification_stratum == "shape-clear-resolved":
                resolved_shape_eligible_count += 1
                resolved_shape_available_count += int(
                    candidate_source.deconvolution_status == "resolved"
                    and candidate_source.deconvolved_shape is not None
                )
            calibration = {
                item.metric: item.mean_normalized_residual
                for item in pair.uncertainty_calibration
            }
            for stratum_identifier in source_strata[source_index]:
                for metric in metrics:
                    sample = calibration.get(metric)
                    if sample is not None:
                        uncertainty_samples[
                            (stratum_identifier, metric)
                        ].append(sample)

    failures: list[tuple[str, str, object]] = []
    heldout_gate = gates.heldout_qualification
    group_truth_count = len(recipes) * len(dataset.association_truth_groups)
    completeness = matched_group_count / group_truth_count
    reliability = matched_group_count / candidate_count
    individual_eligible_count = len(recipes) * sum(
        group.resolution_class == "individually-resolvable"
        for group in dataset.association_truth_groups
    )
    fitted_shape_availability = (
        matched_individual_count / individual_eligible_count
    )
    classification_eligibility = {
        stratum.identifier: len(recipes) * len(stratum.source_indices)
        for stratum in dataset.classification_strata
        if stratum.identifier in classification_available
    }
    classification_availability = sum(classification_available.values()) / sum(
        classification_eligibility.values()
    )
    point_source_specificity = (
        classification_correct["shape-unresolved"]
        / classification_available["shape-unresolved"]
        if classification_available["shape-unresolved"]
        else 0.0
    )
    clear_resolved_recall = (
        classification_correct["shape-clear-resolved"]
        / classification_available["shape-clear-resolved"]
        if classification_available["shape-clear-resolved"]
        else 0.0
    )
    resolved_shape_availability = (
        resolved_shape_available_count / resolved_shape_eligible_count
    )
    catastrophic_outlier_fraction = (
        catastrophic_count / matched_individual_count
    )
    heldout_results = {
        "completeness": (
            completeness,
            heldout_gate.minimum_completeness,
            "minimum",
        ),
        "reliability": (
            reliability,
            heldout_gate.minimum_reliability,
            "minimum",
        ),
        "fitted-shape-availability": (
            fitted_shape_availability,
            heldout_gate.minimum_fitted_shape_availability,
            "minimum",
        ),
        "classification-availability": (
            classification_availability,
            heldout_gate.minimum_deconvolution_classification_availability,
            "minimum",
        ),
        "point-source-specificity": (
            point_source_specificity,
            heldout_gate.minimum_point_source_specificity,
            "minimum",
        ),
        "clear-resolved-recall": (
            clear_resolved_recall,
            heldout_gate.minimum_clear_resolved_classification_recall,
            "minimum",
        ),
        "resolved-shape-availability": (
            resolved_shape_availability,
            heldout_gate.minimum_resolved_deconvolved_shape_availability,
            "minimum",
        ),
        "catastrophic-outlier-fraction": (
            catastrophic_outlier_fraction,
            heldout_gate.maximum_catastrophic_outlier_fraction,
            "maximum",
        ),
    }
    for name, (observed, limit, direction) in heldout_results.items():
        passes = (
            observed >= limit if direction == "minimum" else observed <= limit
        )
        if not passes:
            failures.append(("heldout", name, (observed, limit)))

    group_gate = gates.unresolved_group
    unresolved_group_count = sum(
        group.resolution_class == "unresolved-blend"
        for group in dataset.association_truth_groups
    )
    unresolved_group_truth_count = len(recipes) * unresolved_group_count
    unresolved_group_completeness = (
        len(group_position_beams) / unresolved_group_truth_count
    )
    group_results = {
        "completeness": (
            unresolved_group_completeness,
            group_gate.minimum_completeness,
        ),
        "median-position-beams": (
            float(np.median(group_position_beams)),
            group_gate.maximum_median_position_beams,
        ),
        "percentile-95-position-beams": (
            float(np.percentile(group_position_beams, 95)),
            group_gate.maximum_percentile_95_position_beams,
        ),
        "median-integrated-flux-fractional-difference": (
            float(np.median(group_integrated_fractional)),
            group_gate.maximum_median_integrated_flux_fractional_difference,
        ),
        "percentile-95-integrated-flux-fractional-difference": (
            float(np.percentile(group_integrated_fractional, 95)),
            group_gate.maximum_percentile_95_integrated_flux_fractional_difference,
        ),
    }
    for name, (observed, limit) in group_results.items():
        passes = (
            observed >= limit if name == "completeness" else observed <= limit
        )
        if not passes:
            failures.append(("unresolved-group", name, (observed, limit)))

    uncertainty_evidence: list[dict[str, object]] = []
    uncertainty_gate = gates.uncertainty
    for stratum in dataset.validation_strata:
        eligible_count = len(recipes) * len(stratum.source_indices)
        for metric in metrics:
            report = uncertainty_calibration_report(
                metric,
                uncertainty_samples[(stratum.identifier, metric)],
                eligible_count=eligible_count,
                confidence_level=uncertainty_gate.confidence_interval_level,
                bootstrap_resamples=uncertainty_gate.bootstrap_resamples,
                bootstrap_seed=uncertainty_gate.bootstrap_seed,
            )
            decision = evaluate_uncertainty_calibration(
                report,
                minimum_samples=uncertainty_gate.minimum_samples_per_stratum,
                nominal_coverage=uncertainty_gate.nominal_coverage,
                maximum_absolute_coverage_difference=(
                    uncertainty_gate.maximum_absolute_coverage_difference
                ),
                maximum_absolute_mean=(
                    uncertainty_gate.maximum_absolute_mean_normalized_residual
                ),
                minimum_standard_deviation=(
                    uncertainty_gate.minimum_normalized_residual_standard_deviation
                ),
                maximum_standard_deviation=(
                    uncertainty_gate.maximum_normalized_residual_standard_deviation
                ),
            )
            if report.availability_fraction < (
                heldout_gate.minimum_position_flux_uncertainty_availability
            ):
                failures.append((stratum.identifier, metric, "availability"))
            gated_decision = (
                metric != "integrated-flux"
                or stratum.identifier == "shape-unresolved"
            )
            if gated_decision and decision.status != "pass":
                failures.append((stratum.identifier, metric, decision))
            uncertainty_evidence.append(
                {
                    "stratum": stratum.identifier,
                    "gated": gated_decision,
                    "report": asdict(report),
                    "decision": asdict(decision),
                }
            )

    evidence = {
        "schema_version": 2,
        "evidence_type": "phase-4-heldout-qualification",
        "dataset_identifier": dataset.identifier,
        "recipe_sha256": dataset.recipe_sha256,
        "realization_count": len(recipes),
        "group_truth_count": group_truth_count,
        "candidate_count": candidate_count,
        "matched_group_count": matched_group_count,
        "completeness": completeness,
        "reliability": reliability,
        "fitted_shape_availability": fitted_shape_availability,
        "classification_availability": classification_availability,
        "point_source_specificity": point_source_specificity,
        "clear_resolved_recall": clear_resolved_recall,
        "resolved_shape_availability": resolved_shape_availability,
        "catastrophic_outlier_fraction": catastrophic_outlier_fraction,
        "catastrophic_outlier_population": (
            "matched-compact-snr-at-least-10-with-marginal-integrated-flux-"
            "report-only"
        ),
        "marginal_integrated_flux_catastrophic_report_only": {
            "sample_count": marginal_matched_individual_count,
            "catastrophic_count": (
                marginal_integrated_flux_catastrophic_count
            ),
            "fraction": (
                marginal_integrated_flux_catastrophic_count
                / marginal_matched_individual_count
                if marginal_matched_individual_count
                else None
            ),
        },
        "unresolved_group": {
            "sample_count": len(group_position_beams),
            "truth_count": unresolved_group_truth_count,
            "completeness": unresolved_group_completeness,
            "median_position_beams": float(np.median(group_position_beams)),
            "percentile_95_position_beams": float(
                np.percentile(group_position_beams, 95)
            ),
            "median_integrated_flux_fractional_difference": float(
                np.median(group_integrated_fractional)
            ),
            "percentile_95_integrated_flux_fractional_difference": float(
                np.percentile(group_integrated_fractional, 95)
            ),
        },
        "absolute_noisy_metrics_report_only": {
            name: {
                "sample_count": len(values),
                "median": float(np.median(values)) if values else None,
                "percentile_95": (
                    float(np.percentile(values, 95)) if values else None
                ),
            }
            for name, values in absolute_metrics.items()
        },
        "uncertainty": uncertainty_evidence,
        "failures": [str(failure) for failure in failures],
    }
    configured_evidence_path = os.environ.get(
        "HEBOG_PHASE4_QUALIFICATION_EVIDENCE"
    )
    evidence_path = (
        Path(configured_evidence_path)
        if configured_evidence_path is not None
        else _ROOT / "benchmark-results/phase-4-qualification.json"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(evidence, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert not failures, failures
