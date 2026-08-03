"""Generated-truth Phase 4 compact fitting and association matrix."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

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
from hebog.data_models.fitting import ValidCompactGaussianFit
from hebog.data_models.measurement import CompactMeasurementGeometry
from hebog.executors import SerialExecutor
from hebog.io import ImageWindow, ZarrProductSink
from hebog.stages.detection import DetectionStageConfig, run_detection_stage
from hebog.stages.fitting import run_compact_gaussian_fit_stage
from hebog.validation.contracts import load_phase_four_scientific_gates
from hebog.validation.datasets import (
    AssociationTruthGroup,
    DatasetRecord,
    SyntheticRecipe,
    generate_synthetic_window,
    load_dataset_manifest,
)

pytestmark = pytest.mark.equivalence

_ROOT = Path(__file__).parents[2]
_DATASET_ROOT = _ROOT / "config/datasets"


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
            minimum_island_pixels=6,
        ),
    )


def _fits(
    dataset: DatasetRecord, root: Path
) -> tuple[ValidCompactGaussianFit, ...]:
    """Run bounded detection, deblending, moments, and fit-all measurement."""
    source = _SyntheticImageSource(dataset.recipe)
    shape_yx = dataset.recipe.shape_yx
    manifest = plan_image_partitions(
        image_shape_yx=shape_yx,
        tile_core_shape_yx=(128, 128),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        root / "products.zarr",
        manifest,
        generation_id=dataset.identifier,
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


@pytest.mark.parametrize(
    "dataset_index",
    [
        pytest.param(
            0,
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "flat absolute tails are incompatible with ordinary "
                    "SNR-12 noise scatter; the reviewed validation statistic "
                    "requires amendment before held-out inspection"
                ),
            ),
        ),
        1,
    ],
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
            fitted_axis_fractional.extend(
                (
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
    for values, median_limit, tail_limit in gates:
        if not values:
            continue
        assert np.median(values) <= median_limit
        assert np.percentile(values, 95) <= tail_limit

    if unresolved_group_position_beams:
        group_gate = load_phase_four_scientific_gates(
            _ROOT / "config/contracts/phase-4-scientific-gates.json"
        ).unresolved_group
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
