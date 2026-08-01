"""Analytic compact watershed deblending and admission tests."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from hebog.algorithms.deblending import (
    CompactIslandPixels,
    deblend_compact_batch,
    deblend_compact_island,
    plan_compact_deblend_batches,
)
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactDeblendConfig
from hebog.data_models import ImageBounds


def _config(**replacements: object) -> CompactDeblendConfig:
    """Return one explicit compact-region and memory policy."""
    values: dict[str, object] = {
        "minimum_peak_signal_to_noise": 5.0,
        "minimum_peak_separation_pixels": 1,
        "minimum_saddle_depth_sigma": 2.0,
        "maximum_compact_island_pixels": 64,
        "maximum_compact_bounds_pixels": 128,
        "maximum_batch_pixels": 256,
    }
    values.update(replacements)
    return CompactDeblendConfig(**values)  # type: ignore[arg-type]


def _compact_island(
    normalized: np.ndarray,
    *,
    membership: np.ndarray | None = None,
    bounds_origin_yx: tuple[int, int] = (0, 0),
    island_id: str = "island-00001",
    global_label: int = 1,
) -> CompactIslandPixels:
    """Construct one internally consistent analytic compact island."""
    normalized = np.asarray(normalized, dtype=np.float64)
    selected = (
        np.asarray(membership, dtype=np.bool_)
        if membership is not None
        else np.ones(normalized.shape, dtype=np.bool_)
    )
    y_start, x_start = bounds_origin_yx
    bounds = ImageBounds(
        y_start,
        y_start + normalized.shape[0],
        x_start,
        x_start + normalized.shape[1],
    )
    peak_local = np.unravel_index(
        np.argmax(np.where(selected, normalized, -np.inf)),
        normalized.shape,
    )
    first_local = tuple(np.argwhere(selected)[0])
    island = DetectedIsland(
        island_id=island_id,
        global_label=global_label,
        pixel_count=int(np.count_nonzero(selected)),
        bounds=bounds,
        peak_signal_to_noise=float(normalized[peak_local]),
        peak_position_yx=(
            y_start + int(peak_local[0]),
            x_start + int(peak_local[1]),
        ),
        first_pixel_yx=(
            y_start + int(first_local[0]),
            x_start + int(first_local[1]),
        ),
        touches_image_edge=False,
    )
    return CompactIslandPixels(
        island=island,
        normalized_residual=normalized,
        island_membership=selected,
    )


@pytest.mark.parametrize(
    ("replacements", "message"),
    [
        ({"minimum_peak_signal_to_noise": 0.0}, "peak_signal"),
        ({"minimum_peak_separation_pixels": True}, "peak_separation"),
        ({"minimum_saddle_depth_sigma": -1.0}, "saddle_depth"),
        ({"maximum_compact_island_pixels": 0}, "island_pixels"),
        ({"maximum_compact_bounds_pixels": 0}, "bounds_pixels"),
        ({"maximum_batch_pixels": 0}, "batch_pixels"),
        (
            {
                "maximum_compact_bounds_pixels": 20,
                "maximum_batch_pixels": 10,
            },
            "admit one compact",
        ),
    ],
)
def test_rejects_invalid_compact_deblend_configuration(
    replacements: dict[str, object],
    message: str,
) -> None:
    """Peak and memory policy has no hidden or unbounded fallback."""
    with pytest.raises(ValueError, match=message):
        _config(**replacements)


def test_single_peak_preserves_exact_membership_and_global_properties() -> (
    None
):
    """One compact peak remains one region without inventing a source."""
    normalized = np.array([[0.0, 3.0, 0.0], [3.0, 8.0, 4.0], [0.0, 3.0, 0.0]])
    membership = normalized >= 3.0
    compact = _compact_island(
        normalized,
        membership=membership,
        bounds_origin_yx=(10, 20),
    )

    result = deblend_compact_island(compact, _config())

    assert result.status == "single-region"
    assert result.island_id == compact.island.island_id
    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.region_id == "island-00001-region-001"
    assert region.pixel_count == compact.island.pixel_count
    assert region.peak_position_yx == (11, 21)
    assert region.first_pixel_yx == (10, 21)
    np.testing.assert_array_equal(result.region_labels > 0, membership)
    assert not result.region_labels.flags.writeable


@pytest.mark.parametrize("strong_peak", [7.0, 12.0, 30.0])
def test_deep_saddle_splits_close_pairs_across_flux_ratios(
    strong_peak: float,
) -> None:
    """The weaker prominent peak survives a range of compact flux ratios."""
    compact = _compact_island(
        np.array([[6.0, 5.0, 4.0, 3.0, 3.0, 4.0, 5.0, strong_peak]])
    )

    result = deblend_compact_island(compact, _config())

    assert result.status == "deblended"
    assert len(result.regions) == 2
    assert tuple(region.peak_position_yx for region in result.regions) == (
        (0, 0),
        (0, 7),
    )
    assert sum(region.pixel_count for region in result.regions) == 8
    assert set(np.unique(result.region_labels)) == {1, 2}


def test_shallow_saddle_merges_the_weaker_watershed_basin() -> None:
    """A local maximum below the explicit prominence cut is not deblended."""
    compact = _compact_island(np.array([[6.0, 5.5, 5.5, 5.5, 5.5, 5.5, 7.0]]))

    result = deblend_compact_island(compact, _config())

    assert result.status == "single-region"
    assert len(result.regions) == 1
    assert result.regions[0].peak_position_yx == (0, 6)


def test_equal_peaks_and_saddle_ties_are_lexicographically_stable() -> None:
    """Equal marker heights use global row-major order deterministically."""
    compact = _compact_island(
        np.array([[7.0, 5.0, 3.0, 5.0, 7.0]]),
        bounds_origin_yx=(4, 9),
    )

    first = deblend_compact_island(compact, _config())
    second = deblend_compact_island(compact, _config())

    assert first.regions == second.regions
    np.testing.assert_array_equal(first.region_labels, second.region_labels)
    assert tuple(region.peak_position_yx for region in first.regions) == (
        (4, 9),
        (4, 13),
    )


def test_subthreshold_noise_peak_does_not_create_a_region() -> None:
    """A local maximum must be strictly above the configured peak cut."""
    compact = _compact_island(np.array([[8.0, 4.0, 4.9, 4.0, 3.0]]))

    result = deblend_compact_island(compact, _config())

    assert result.status == "single-region"
    assert len(result.regions) == 1


def test_masked_holes_and_equal_peak_plateau_preserve_membership() -> None:
    """Invalid holes stay unassigned and one plateau has one stable marker."""
    normalized = np.array([[7.0, 7.0, 4.0], [4.0, 4.0, 4.0], [4.0, 4.0, 4.0]])
    membership = np.ones(normalized.shape, dtype=np.bool_)
    membership[2, 2] = False
    compact = _compact_island(
        normalized,
        membership=membership,
        bounds_origin_yx=(3, 8),
    )

    result = deblend_compact_island(compact, _config())

    assert result.status == "single-region"
    assert result.regions[0].peak_position_yx == (3, 8)
    np.testing.assert_array_equal(result.region_labels > 0, membership)


def test_exact_peak_threshold_has_no_eligible_marker() -> None:
    """The compact marker boundary remains strict like detection seeds."""
    compact = _compact_island(np.array([[5.0, 4.0, 3.0]]))

    with pytest.raises(ValueError, match="no eligible"):
        deblend_compact_island(compact, _config())


def test_planner_batches_compact_bounds_and_preserves_deferrals() -> None:
    """Extended islands are explicit Phase 5 inputs, never silently dropped."""
    first = _compact_island(
        np.full((2, 2), 6.0),
        global_label=1,
        island_id="island-00001",
    ).island
    second = _compact_island(
        np.full((2, 3), 6.0),
        global_label=2,
        island_id="island-00002",
    ).island
    too_many_pixels = replace(
        _compact_island(
            np.full((3, 4), 6.0),
            global_label=3,
            island_id="island-00003",
        ).island,
        pixel_count=11,
    )
    sparse_large_bounds = replace(
        _compact_island(
            np.full((3, 4), 6.0),
            global_label=4,
            island_id="island-00004",
        ).island,
        pixel_count=2,
    )
    config = _config(
        maximum_compact_island_pixels=10,
        maximum_compact_bounds_pixels=8,
        maximum_batch_pixels=8,
    )

    plan = plan_compact_deblend_batches(
        (sparse_large_bounds, second, too_many_pixels, first),
        config,
    )

    assert tuple(
        tuple(island.island_id for island in batch.islands)
        for batch in plan.batches
    ) == (("island-00001",), ("island-00002",))
    assert tuple(batch.estimated_pixel_count for batch in plan.batches) == (
        4,
        6,
    )
    assert tuple(
        (item.island.island_id, item.reason) for item in plan.deferred_islands
    ) == (
        ("island-00003", "island-pixel-limit"),
        ("island-00004", "bounds-pixel-limit"),
    )


def test_planner_rejects_duplicate_island_identities() -> None:
    """Ambiguous compact work cannot produce duplicate region identities."""
    island = _compact_island(np.full((2, 2), 6.0)).island

    with pytest.raises(ValueError, match="unique"):
        plan_compact_deblend_batches((island, island), _config())


def test_valid_batch_returns_results_in_caller_order() -> None:
    """A coarse executor batch preserves deterministic requested ordering."""
    first = _compact_island(np.full((2, 2), 6.0))
    second = _compact_island(
        np.full((2, 2), 7.0),
        island_id="island-00002",
        global_label=2,
    )

    results = deblend_compact_batch((second, first), _config())

    assert tuple(result.island_id for result in results) == (
        "island-00002",
        "island-00001",
    )


def test_batch_rejects_work_above_the_admitted_bounds_budget() -> None:
    """A caller cannot bypass the planner with an oversized batch."""
    first = _compact_island(np.full((2, 3), 6.0))
    second = _compact_island(
        np.full((2, 3), 7.0),
        island_id="island-00002",
        global_label=2,
    )

    with pytest.raises(ValueError, match="batch exceeds"):
        deblend_compact_batch(
            (first, second),
            _config(
                maximum_compact_bounds_pixels=8,
                maximum_batch_pixels=8,
            ),
        )


def test_rejects_membership_or_value_contract_mismatch() -> None:
    """Bounds, boolean membership, counts, and finite values fail closed."""
    compact = _compact_island(np.full((2, 3), 6.0))
    wrong_count = CompactIslandPixels(
        island=replace(compact.island, pixel_count=5),
        normalized_residual=compact.normalized_residual,
        island_membership=compact.island_membership,
    )
    nonfinite = np.array(compact.normalized_residual, copy=True)
    nonfinite[0, 0] = np.nan

    with pytest.raises(ValueError, match="disagrees"):
        deblend_compact_island(wrong_count, _config())
    with pytest.raises(ValueError, match="finite"):
        deblend_compact_island(
            replace(compact, normalized_residual=nonfinite),
            _config(),
        )

    with pytest.raises(TypeError, match="boolean"):
        deblend_compact_island(
            replace(
                compact,
                island_membership=np.ones(
                    compact.island_membership.shape,
                    dtype=np.int8,
                ),
            ),
            _config(),
        )


def test_rejects_bounds_above_compact_kernel_admission() -> None:
    """The kernel independently enforces planner region-memory limits."""
    compact = _compact_island(np.full((3, 4), 6.0))

    with pytest.raises(ValueError, match="bounds exceed"):
        deblend_compact_island(
            compact,
            _config(
                maximum_compact_bounds_pixels=8,
                maximum_batch_pixels=8,
            ),
        )
