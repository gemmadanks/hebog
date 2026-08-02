# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Generated-truth Phase 3 detection matrix and held-out qualification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
import numpy.typing as npt
import pytest
from scipy import ndimage

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)
from hebog.data_models import ImageBounds
from hebog.executors import SerialExecutor
from hebog.io import ImageWindow, ZarrProductSink
from hebog.stages.detection import DetectionStageConfig, run_detection_stage
from hebog.validation.comparison import (
    IslandComparisonReport,
    IslandPopulationReport,
    MaskComparisonReport,
    aggregate_island_comparisons,
    compare_island_labels,
    compare_masks,
)
from hebog.validation.contracts import (
    PhaseThreeLaneGate,
    load_phase_three_scientific_gates,
)
from hebog.validation.datasets import (
    DatasetRecord,
    SyntheticRecipe,
    generate_synthetic_image,
    generate_synthetic_window,
    load_dataset_manifest,
)

_ROOT = Path(__file__).parents[2]
_DATASET_ROOT = _ROOT / "config/datasets"
_GATES = load_phase_three_scientific_gates(
    _ROOT / "config/contracts/phase-3-scientific-gates.json"
)
_DETECTION_THRESHOLD = 5.0
_ISLAND_THRESHOLD = 3.0
_MINIMUM_ISLAND_PIXELS = 6


class _SyntheticImageSource:
    """Generate exact governed windows without retaining a complete plane."""

    def __init__(self, recipe: SyntheticRecipe) -> None:
        self._recipe = recipe

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return one deterministic generated source window."""
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
            valid_pixels=np.ones(values.shape, dtype=np.bool_),
        )


@dataclass(frozen=True, slots=True)
class _GeneratedCaseReport:
    """Foreground metrics plus report-only low-SNR threshold crossings."""

    dataset_id: str
    mask: MaskComparisonReport
    islands: IslandComparisonReport
    strong_signal_islands: IslandComparisonReport
    low_snr_source_count: int
    low_snr_detected_count: int


def _configuration() -> DetectionStageConfig:
    """Return the frozen Phase 3 generated-image execution profile."""
    statistics = RmsWindowStatisticsConfig(3.0, 10, 6)
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
            maximum_constant_map_pixels=2048 * 2048,
        ),
        source_finder=SourceFinderConfig(
            detection_threshold_sigma=_DETECTION_THRESHOLD,
            island_threshold_sigma=_ISLAND_THRESHOLD,
            minimum_island_pixels=_MINIMUM_ISLAND_PIXELS,
        ),
    )


def _labels(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.int32]:
    """Return independent eight-connected labels for one mask."""
    labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(
            mask,
            structure=np.ones((3, 3), dtype=np.bool_),
        ),
    )
    return np.asarray(labels, dtype=np.int32)


def _analytic_truth(
    recipe: SyntheticRecipe,
) -> tuple[npt.NDArray[np.bool_], npt.NDArray[np.int32]]:
    """Apply frozen thresholds to the noiseless analytic emission only."""
    noiseless = recipe.model_copy(update={"background": 0.0, "noise_rms": 0.0})
    signal = generate_synthetic_image(noiseless)
    normalized = signal / recipe.noise_rms
    membership = normalized >= _ISLAND_THRESHOLD
    raw_labels = _labels(np.asarray(membership, dtype=np.bool_))
    component_count = int(np.max(raw_labels, initial=0))
    accepted = np.zeros(component_count + 1, dtype=np.int32)
    next_label = 1
    for label in range(1, component_count + 1):
        selected = raw_labels == label
        if (
            np.count_nonzero(selected) >= _MINIMUM_ISLAND_PIXELS
            and np.max(normalized[selected]) > _DETECTION_THRESHOLD
        ):
            accepted[label] = next_label
            next_label += 1
    labels = accepted[raw_labels]
    return np.asarray(labels > 0, dtype=np.bool_), labels


def _candidate_mask(
    dataset: DatasetRecord,
    root: Path,
) -> npt.NDArray[np.bool_]:
    """Run the complete bounded detection stage for one governed recipe."""
    shape_yx = dataset.recipe.shape_yx
    tile_size = min(512, max(96, shape_yx[0] // 4))
    manifest = plan_image_partitions(
        image_shape_yx=shape_yx,
        tile_core_shape_yx=(tile_size, tile_size),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        root / "products.zarr",
        manifest,
        generation_id=dataset.identifier,
    )
    result = run_detection_stage(
        _SyntheticImageSource(dataset.recipe),
        manifest,
        _configuration(),
        SerialExecutor(),
        sink,
    )
    mask = np.zeros(shape_yx, dtype=np.bool_)
    records = {
        chunk.tile_id: chunk
        for chunk in result.generation.chunks
        if chunk.product_name == "source-filtering-mask"
    }
    for tile in manifest.tiles:
        bounds = tile.core_bounds
        mask[
            bounds.y_start : bounds.y_stop,
            bounds.x_start : bounds.x_stop,
        ] = sink.read_chunk(records[tile.tile_id])
    return mask


def _run_case(dataset: DatasetRecord, root: Path) -> _GeneratedCaseReport:
    """Build exact foreground reports and count report-only low-SNR cases."""
    truth_mask, truth_labels = _analytic_truth(dataset.recipe)
    candidate = _candidate_mask(dataset, root)
    low_snr = tuple(
        source
        for source in dataset.recipe.sources
        if source.peak_flux_jy_per_beam / dataset.recipe.noise_rms
        <= _DETECTION_THRESHOLD
    )
    low_snr_detected = sum(
        bool(candidate[round(source.y_pixel), round(source.x_pixel)])
        for source in low_snr
    )
    candidate_labels = _labels(candidate)
    low_candidate_labels = {
        int(candidate_labels[round(source.y_pixel), round(source.x_pixel)])
        for source in low_snr
        if candidate_labels[round(source.y_pixel), round(source.x_pixel)] > 0
    }
    strong_signal_valid = ~np.isin(
        candidate_labels,
        tuple(sorted(low_candidate_labels)),
    )
    return _GeneratedCaseReport(
        dataset_id=dataset.identifier,
        mask=compare_masks(truth_mask, candidate),
        islands=compare_island_labels(truth_labels, candidate_labels),
        strong_signal_islands=compare_island_labels(
            truth_labels,
            candidate_labels,
            valid_mask=strong_signal_valid,
        ),
        low_snr_source_count=len(low_snr),
        low_snr_detected_count=low_snr_detected,
    )


def _require_gates(
    report: _GeneratedCaseReport,
    gates: PhaseThreeLaneGate,
) -> None:
    """Apply only the margins frozen before held-out result inspection."""
    assert report.mask.precision >= gates.mask.minimum_precision
    assert report.mask.recall >= gates.mask.minimum_recall
    assert (
        report.mask.intersection_over_union
        >= gates.mask.minimum_intersection_over_union
    )
    islands = report.strong_signal_islands
    assert islands.completeness >= gates.islands.minimum_completeness
    assert islands.reliability >= gates.islands.minimum_reliability
    assert islands.median_matched_intersection_over_union is not None
    assert islands.minimum_matched_intersection_over_union is not None
    assert (
        islands.median_matched_intersection_over_union
        >= gates.islands.minimum_median_intersection_over_union
    )
    assert (
        islands.minimum_matched_intersection_over_union
        >= gates.islands.minimum_matched_intersection_over_union
    )
    assert (
        len(islands.split_reference_labels)
        <= gates.islands.maximum_split_count
    )
    assert (
        len(islands.merged_candidate_labels)
        <= gates.islands.maximum_merge_count
    )


@pytest.mark.equivalence
def test_generated_development_and_regression_matrix_meets_frozen_gates(
    tmp_path: Path,
) -> None:
    """SNR, blend, edge, boundary, and density cases pass as a population."""
    datasets = tuple(
        load_dataset_manifest(_DATASET_ROOT / name).datasets[0]
        for name in (
            "phase-3-development.json",
            "phase-3-regression.json",
        )
    )
    reports = tuple(
        _run_case(dataset, tmp_path / dataset.identifier)
        for dataset in datasets
    )

    for report in reports:
        _require_gates(report, _GATES.generated_regression)
    population: IslandPopulationReport = aggregate_island_comparisons(
        tuple(report.strong_signal_islands for report in reports),
        confidence_level=_GATES.confidence_level,
    )
    assert population.case_count == 2
    assert population.completeness_confidence_interval is not None
    assert population.reliability_confidence_interval is not None
    assert population.completeness >= 0.9
    assert population.reliability >= 0.9
    assert sum(report.low_snr_source_count for report in reports) == 3
    assert 0 <= sum(report.low_snr_detected_count for report in reports) <= 3


@pytest.mark.qualification
def test_heldout_detection_matrix_meets_frozen_qualification_gates(
    tmp_path: Path,
) -> None:
    """Inspect the frozen held-out result only in the qualification lane."""
    dataset = load_dataset_manifest(
        _DATASET_ROOT / "phase-3-qualification.json"
    ).datasets[0]

    report = _run_case(dataset, tmp_path / dataset.identifier)

    _require_gates(report, _GATES.heldout_qualification)
    assert report.low_snr_source_count == 1
    assert 0 <= report.low_snr_detected_count <= 1
