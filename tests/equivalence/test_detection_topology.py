# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Phase 3 mask and object equivalence with both PyBDSF references."""

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
from hebog.executors import SerialExecutor
from hebog.io import FitsImageSource, ZarrProductSink
from hebog.stages.detection import (
    DetectionStageConfig,
    DetectionStageResult,
    run_detection_stage,
)
from hebog.validation.comparison import (
    IslandComparisonReport,
    MaskComparisonReport,
    compare_island_labels,
    compare_masks,
)
from hebog.validation.contracts import (
    PhaseThreeLaneGate,
    load_phase_three_scientific_gates,
)
from hebog.validation.products import load_mask_plane

pytestmark = pytest.mark.equivalence

_ROOT = Path(__file__).parents[2]
_REFERENCE_ROOT = _ROOT / "tests/data/pybdsf/pybdsf-compact-reference-256"
_GATES = load_phase_three_scientific_gates(
    _ROOT / "config/contracts/phase-3-scientific-gates.json"
)


@dataclass(frozen=True, slots=True)
class _CompactCandidate:
    """Module-scoped candidate products retained for dual comparison."""

    result: DetectionStageResult
    mask: npt.NDArray[np.bool_]
    labels: npt.NDArray[np.int32]


def _configuration() -> DetectionStageConfig:
    """Return the frozen Rapthor compact thresholds and RMS geometry."""
    statistics = RmsWindowStatisticsConfig(3.0, 10, 6)
    return DetectionStageConfig(
        background_rms=BackgroundRmsConfig(
            coarse=RmsGridConfig(
                window_shape_yx=(150, 150),
                step_yx=(50, 50),
                statistics=statistics,
                maximum_batch_cells=16,
            ),
            adaptive=AdaptiveRmsConfig(
                grid=RmsGridConfig(
                    window_shape_yx=(35, 35),
                    step_yx=(7, 7),
                    statistics=statistics,
                    maximum_batch_cells=16,
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
            profile="compact",
        ),
    )


def _label(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.int32]:
    """Apply the independently established eight-connected object oracle."""
    labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(
            mask,
            structure=np.ones((3, 3), dtype=np.bool_),
        ),
    )
    return np.asarray(labels, dtype=np.int32)


@pytest.fixture(scope="module")
def compact_candidate(
    tmp_path_factory: pytest.TempPathFactory,
) -> _CompactCandidate:
    """Run the compact Phase 3 path once for both exact references."""
    source = FitsImageSource(_REFERENCE_ROOT / "input.fits")
    shape_yx = source.metadata().shape_yx
    manifest = plan_image_partitions(
        image_shape_yx=shape_yx,
        tile_core_shape_yx=(128, 128),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        tmp_path_factory.mktemp("phase3-compact") / "products.zarr",
        manifest,
        generation_id="phase-3-compact-equivalence",
    )
    result = run_detection_stage(
        source,
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
    mask.setflags(write=False)
    labels = _label(mask)
    labels.setflags(write=False)
    return _CompactCandidate(result=result, mask=mask, labels=labels)


def _require_gates(
    mask_report: MaskComparisonReport,
    island_report: IslandComparisonReport,
    gates: PhaseThreeLaneGate,
) -> None:
    """Apply frozen foreground-sensitive Phase 3 margins."""
    assert mask_report.precision >= gates.mask.minimum_precision
    assert mask_report.recall >= gates.mask.minimum_recall
    assert (
        mask_report.intersection_over_union
        >= gates.mask.minimum_intersection_over_union
    )
    assert island_report.completeness >= gates.islands.minimum_completeness
    assert island_report.reliability >= gates.islands.minimum_reliability
    assert island_report.median_matched_intersection_over_union is not None
    assert island_report.minimum_matched_intersection_over_union is not None
    assert (
        island_report.median_matched_intersection_over_union
        >= gates.islands.minimum_median_intersection_over_union
    )
    assert (
        island_report.minimum_matched_intersection_over_union
        >= gates.islands.minimum_matched_intersection_over_union
    )
    assert (
        len(island_report.split_reference_labels)
        <= gates.islands.maximum_split_count
    )
    assert (
        len(island_report.merged_candidate_labels)
        <= gates.islands.maximum_merge_count
    )


@pytest.mark.parametrize("reference", ["release", "master"])
def test_compact_mask_and_objects_meet_both_reference_gates(
    compact_candidate: _CompactCandidate,
    reference: str,
) -> None:
    """The governed compact mask passes both exact PyBDSF comparisons."""
    reference_mask = load_mask_plane(
        _REFERENCE_ROOT / reference / "source_filter_mask.fits"
    )
    mask_report = compare_masks(reference_mask, compact_candidate.mask)
    island_report = compare_island_labels(
        _label(reference_mask),
        compact_candidate.labels,
    )

    _require_gates(mask_report, island_report, _GATES.compact_reference)
    assert mask_report.true_positive_count == 177
    assert mask_report.false_positive_count == 1
    assert mask_report.false_negative_count == 1
    # Sampling every pixel center as a sky-model position is an independent
    # retained/rejected decision population for LSMTool's mask selection.
    assert mask_report.agreement_fraction >= 0.995
    assert island_report.reference_count == island_report.candidate_count == 3
    assert len(compact_candidate.result.islands) == 3
    assert compact_candidate.result.adaptive_candidate_positions_yx == (
        (128.0, 128.0),
    )
    assert (
        compact_candidate.result.background_rms_grids.adaptive_protected_pixel_count
        == 0
    )


def test_reference_branches_do_not_diverge_for_compact_topology() -> None:
    """Released and pinned-master masks are identical on the governed case."""
    release = load_mask_plane(
        _REFERENCE_ROOT / "release/source_filter_mask.fits"
    )
    master = load_mask_plane(
        _REFERENCE_ROOT / "master/source_filter_mask.fits"
    )

    report = compare_masks(release, master)

    assert report.false_positive_count == report.false_negative_count == 0
    assert report.intersection_over_union == 1.0
