# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Controlled Phase 3 topology comparison on the Rapthor reference image."""

from __future__ import annotations

import os
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
from hebog.stages.detection import DetectionStageConfig, run_detection_stage
from hebog.validation.comparison import (
    IslandComparisonReport,
    MaskComparisonReport,
    compare_island_labels,
    compare_masks,
)
from hebog.validation.products import load_mask_plane

pytestmark = [
    pytest.mark.equivalence,
    pytest.mark.requires_data,
    pytest.mark.slow,
    pytest.mark.filterwarnings("ignore::astropy.wcs.FITSFixedWarning"),
]


@dataclass(frozen=True, slots=True)
class _RepresentativeCandidate:
    """One controlled Hebog candidate retained for dual comparison."""

    mask: npt.NDArray[np.bool_]
    labels: npt.NDArray[np.int32]
    island_count: int


def _required_path(environment_name: str) -> Path:
    """Resolve one controlled input without embedding a private path."""
    value = os.environ.get(environment_name)
    if not value:
        pytest.skip(f"{environment_name} is not configured")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"{environment_name} is not a file: {path}")
    return path


def _configuration() -> DetectionStageConfig:
    """Return the frozen representative Phase 3 execution profile."""
    statistics = RmsWindowStatisticsConfig(3.0, 10, 6)
    return DetectionStageConfig(
        background_rms=BackgroundRmsConfig(
            coarse=RmsGridConfig(
                window_shape_yx=(150, 150),
                step_yx=(50, 50),
                statistics=statistics,
                maximum_batch_cells=64,
            ),
            adaptive=AdaptiveRmsConfig(
                grid=RmsGridConfig(
                    window_shape_yx=(35, 35),
                    step_yx=(7, 7),
                    statistics=statistics,
                    maximum_batch_cells=512,
                ),
                candidate_threshold_sigma=75.0,
                influence_radius_pixels=75.0,
                transition_width_pixels=20.0,
            ),
            maximum_spatial_window_fraction=0.25,
            maximum_constant_map_pixels=10_000_000,
        ),
        source_finder=SourceFinderConfig(
            detection_threshold_sigma=5.0,
            island_threshold_sigma=3.0,
            minimum_island_pixels=6,
        ),
    )


def _labels(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.int32]:
    """Apply the independent eight-connected object oracle."""
    labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(mask, structure=np.ones((3, 3), dtype=np.bool_)),
    )
    return np.asarray(labels, dtype=np.int32)


@pytest.fixture(scope="module")
def representative_candidate(
    tmp_path_factory: pytest.TempPathFactory,
) -> _RepresentativeCandidate:
    """Run the controlled representative candidate once."""
    source = FitsImageSource(
        _required_path("HEBOG_PHASE3_REPRESENTATIVE_FITS")
    )
    shape_yx = source.metadata().shape_yx
    manifest = plan_image_partitions(
        image_shape_yx=shape_yx,
        tile_core_shape_yx=(1000, 1000),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        tmp_path_factory.mktemp("phase3-representative") / "products.zarr",
        manifest,
        generation_id="phase-3-representative-equivalence",
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
    labels = _labels(mask)
    labels.setflags(write=False)
    return _RepresentativeCandidate(
        mask=mask,
        labels=labels,
        island_count=len(result.islands),
    )


def _require_reported_phase_three_scope(
    mask: MaskComparisonReport,
    islands: IslandComparisonReport,
) -> None:
    """Freeze compact matches while exposing deferred multiscale recovery."""
    assert mask.precision >= 0.95
    assert mask.recall < 0.5
    assert mask.intersection_over_union < 0.5
    assert islands.reference_count == 12
    assert islands.candidate_count == 7
    assert len(islands.matches) == 7
    assert len(islands.unmatched_reference_labels) == 5
    assert not islands.unmatched_candidate_labels
    assert islands.reliability == 1.0
    assert islands.median_matched_intersection_over_union is not None
    assert islands.minimum_matched_intersection_over_union is not None
    assert islands.median_matched_intersection_over_union >= 0.94
    assert islands.minimum_matched_intersection_over_union >= 0.77
    assert not islands.split_reference_labels
    assert not islands.merged_candidate_labels


@pytest.mark.parametrize(
    "environment_name",
    [
        pytest.param("HEBOG_PHASE3_RELEASE_MASK", id="release"),
        pytest.param("HEBOG_PHASE3_MASTER_MASK", id="master"),
    ],
)
def test_representative_mask_and_objects_meet_both_reference_gates(
    representative_candidate: _RepresentativeCandidate,
    environment_name: str,
) -> None:
    """The same candidate passes released and pinned-master products."""
    reference_mask = load_mask_plane(_required_path(environment_name))
    mask_report = compare_masks(reference_mask, representative_candidate.mask)
    island_report = compare_island_labels(
        _labels(reference_mask),
        representative_candidate.labels,
    )

    _require_reported_phase_three_scope(mask_report, island_report)
    assert (
        representative_candidate.island_count == island_report.candidate_count
    )


def test_representative_reference_divergence_is_reported() -> None:
    """Dual references are compared directly instead of choosing one."""
    release = load_mask_plane(_required_path("HEBOG_PHASE3_RELEASE_MASK"))
    master = load_mask_plane(_required_path("HEBOG_PHASE3_MASTER_MASK"))

    report = compare_masks(release, master)

    assert report.intersection_over_union >= 0.998
    assert report.false_positive_count == 2
    assert report.false_negative_count == 42
