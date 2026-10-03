# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""Analytic compact watershed deblending and admission tests."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import numpy as np
import numpy.typing as npt
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from scipy import ndimage

from hebog.algorithms.deblending import (
    CompactIslandPixels,
    deblend_compact_batch,
    deblend_compact_island,
    extract_island_membership,
    plan_compact_deblend_batches,
)
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactDeblendConfig
from hebog.data_models import ImageBounds
from hebog.stages.deblending import (
    WorkerLocalDeblendedIsland,
    WorkerLocalRegionBatch,
)


def _config(**replacements: object) -> CompactDeblendConfig:
    """Return one explicit compact-region and memory policy."""
    values: dict[str, object] = {
        "minimum_peak_signal_to_noise": 5.0,
        "minimum_peak_separation_pixels": 1,
        "minimum_saddle_depth_sigma": 2.0,
        "minimum_region_pixels": 1,
        "maximum_compact_island_pixels": 64,
        "maximum_compact_bounds_pixels": 128,
        "target_batch_pixels": 64,
        "maximum_batch_pixels": 256,
    }
    if (
        "maximum_batch_pixels" in replacements
        and "target_batch_pixels" not in replacements
    ):
        values["target_batch_pixels"] = replacements["maximum_batch_pixels"]
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


def _read_only(values: np.ndarray) -> np.ndarray:
    """Return one immutable array for worker-local contract tests."""
    values.setflags(write=False)
    return values


def _worker_local_island() -> WorkerLocalDeblendedIsland:
    """Construct one internally consistent exact measurement handoff."""
    compact = _compact_island(np.full((2, 2), 6.0))
    result = deblend_compact_island(compact, _config())
    return WorkerLocalDeblendedIsland(
        island=compact.island,
        array_bounds=compact.island.bounds,
        regions=result.regions,
        physical_residual=_read_only(np.full((2, 2), 0.006, dtype=np.float64)),
        rms=_read_only(np.full((2, 2), 0.001, dtype=np.float64)),
        valid_pixels=_read_only(np.ones((2, 2), dtype=np.bool_)),
        region_labels=result.region_labels,
    )


@pytest.mark.parametrize(
    ("replacements", "message"),
    [
        ({"minimum_peak_signal_to_noise": 0.0}, "peak_signal"),
        ({"minimum_peak_separation_pixels": True}, "peak_separation"),
        ({"minimum_saddle_depth_sigma": -1.0}, "saddle_depth"),
        ({"minimum_region_pixels": 0}, "region_pixels"),
        ({"maximum_compact_island_pixels": 0}, "island_pixels"),
        ({"maximum_compact_bounds_pixels": 0}, "bounds_pixels"),
        ({"target_batch_pixels": 0}, "target_batch_pixels"),
        ({"maximum_batch_pixels": 0}, "batch_pixels"),
        (
            {
                "target_batch_pixels": 300,
                "maximum_batch_pixels": 256,
            },
            "target_batch_pixels",
        ),
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


def test_intensity_watershed_keeps_two_dimensional_peaks() -> None:
    """Two beam-scale peaks retain balanced basins before saddle review."""
    yy, xx = np.mgrid[:33, :33]
    normalized = 10.0 * np.exp(
        -((yy - 16) ** 2 + (xx - 12) ** 2) / 8.0
    ) + 9.5 * np.exp(-((yy - 16) ** 2 + (xx - 20) ** 2) / 8.0)
    membership = normalized >= 2.5
    compact = _compact_island(normalized, membership=membership)

    result = deblend_compact_island(
        compact,
        _config(
            minimum_peak_separation_pixels=2,
            minimum_saddle_depth_sigma=1.0,
            minimum_region_pixels=7,
            maximum_compact_island_pixels=2_000,
            maximum_compact_bounds_pixels=2_000,
            target_batch_pixels=2_000,
            maximum_batch_pixels=2_000,
        ),
        marker_partition="intensity-watershed",
    )

    assert result.status == "deblended"
    assert len(result.regions) == 2
    assert min(region.pixel_count for region in result.regions) >= 30
    np.testing.assert_array_equal(result.region_labels > 0, membership)


def test_a_weaker_peak_is_judged_at_the_lowest_point_on_the_way() -> None:
    """The pass between two peaks, wherever it lies, decides the split.

    Halfway between these peaks the profile has climbed back to within 0.3
    of the weaker one, so a saddle taken there merged them. The pass, 2.5
    below the weaker peak, clears the 2.0 cut, and each region keeps the
    pixels that rise to its own peak.
    """
    compact = _compact_island(np.array([[6.0, 3.5, 5.6, 5.7, 5.8, 5.9, 8.0]]))

    result = deblend_compact_island(
        compact, _config(), marker_partition="intensity-watershed"
    )

    assert tuple(region.peak_position_yx for region in result.regions) == (
        (0, 0),
        (0, 6),
    )
    assert tuple(region.pixel_count for region in result.regions) == (2, 5)


@pytest.mark.parametrize("bounds_origin_yx", [(0, 0), (3, 5)])
def test_a_marker_heads_its_own_basin_beside_an_equal_neighbour(
    bounds_origin_yx: tuple[int, int],
) -> None:
    """The brighter peak still speaks for a group that a marker joined.

    The 7.0 marker's equal left neighbour is no marker, because the 8.0
    pixel beside it is higher, and climbs to the 9.0 peak. Had the marker
    followed it, both peaks would share one basin, the group would have
    been judged by the 7.0 peak, and the 8.5 peak, 2.5 above the 6.0 pass,
    would have absorbed both.
    """
    compact = _compact_island(
        np.array([[9.0, 8.0, 7.0, 7.0, 6.5, 6.0, 8.5, 6.0]]),
        bounds_origin_yx=bounds_origin_yx,
    )

    result = deblend_compact_island(
        compact, _config(), marker_partition="intensity-watershed"
    )

    origin_y, origin_x = bounds_origin_yx
    assert tuple(region.peak_position_yx for region in result.regions) == (
        (origin_y, origin_x),
        (origin_y, origin_x + 6),
    )
    assert tuple(region.pixel_count for region in result.regions) == (5, 3)


def test_every_pixel_belongs_to_the_end_of_its_ascent() -> None:
    """A pixel several steps from its peak belongs to that peak.

    The 3.0 pixel climbs through 5.0 and 6.0 to the 8.0 peak, not to the
    9.0 peak beside its 4.0 neighbour; a single pointer jump would leave it
    at 6.0, in a basin of its own.
    """
    result = deblend_compact_island(
        _compact_island(np.array([[9.0, 4.0, 3.0, 5.0, 6.0, 8.0]])),
        _config(),
        marker_partition="intensity-watershed",
    )

    assert tuple(region.pixel_count for region in result.regions) == (2, 4)


def test_basins_without_a_peak_join_each_other_before_a_peak() -> None:
    """Two bumps below the peak threshold flood together first.

    The 4.0 and 4.5 bumps meet across 3.0, above the 2.0 and 1.0 saddles
    to the peaks, so they join each other and then, together, the 9.0
    peak across 2.0.
    """
    result = deblend_compact_island(
        _compact_island(np.array([[9.0, 2.0, 4.0, 3.0, 4.5, 1.0, 8.0]])),
        _config(),
        marker_partition="intensity-watershed",
    )

    assert tuple(region.pixel_count for region in result.regions) == (5, 2)


@pytest.mark.parametrize(
    ("depth", "peaks", "pixel_counts"),
    [(2.0, ((2, 0), (2, 4)), (9, 7)), (3.0, ((2, 0),), (16,))],
)
def test_peaks_are_judged_where_they_first_meet_as_the_island_floods(
    depth: float,
    peaks: tuple[tuple[int, int], ...],
    pixel_counts: tuple[int, ...],
) -> None:
    """A pass through a third basin outranks a lower direct contact.

    On this ring the 7.2 peak joins the 10.0 peak across a 7.0 saddle. The
    8.0 peak meets that group first across the 6.0 saddle beside the 7.2
    peak, exactly 2.0 below it, so it stays apart at a 2.0 cut; its direct
    contact with the 10.0 peak, at 4.0, comes too late to matter. Taken
    lowest first, the 7.2 peak would have joined the 8.0 peak and both the
    10.0 one. At a 3.0 cut the 8.0 peak joins too, and that late contact
    then closes the ring within one group.
    """
    normalized = np.full((5, 5), -1.0)
    ring = {
        (2, 0): 10.0,
        (1, 0): 9.0,
        (0, 0): 8.0,
        (0, 1): 7.0,
        (0, 2): 7.2,
        (0, 3): 6.0,
        (0, 4): 7.0,
        (1, 4): 7.5,
        (2, 4): 8.0,
        (3, 4): 7.0,
        (4, 4): 6.0,
        (4, 3): 5.0,
        (4, 2): 4.0,
        (4, 1): 5.0,
        (4, 0): 6.0,
        (3, 0): 8.0,
    }
    for position, value in ring.items():
        normalized[position] = value

    result = deblend_compact_island(
        _compact_island(normalized, membership=normalized > 0.0),
        _config(minimum_saddle_depth_sigma=depth),
        marker_partition="intensity-watershed",
    )

    assert tuple(region.peak_position_yx for region in result.regions) == peaks
    assert (
        tuple(region.pixel_count for region in result.regions) == pixel_counts
    )


def test_an_equal_neighbour_goes_to_the_first_in_row_major_order() -> None:
    """A pixel between two equal neighbours climbs toward the first."""
    result = deblend_compact_island(
        _compact_island(np.array([[7.0, 5.0, 3.0, 5.0, 7.0]])),
        _config(),
        marker_partition="intensity-watershed",
    )

    assert tuple(region.pixel_count for region in result.regions) == (3, 2)


def _eight_connected(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.int32]:
    """Label the eight-connected components of one boolean plane."""
    components, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(mask, structure=np.ones((3, 3), dtype=np.bool_)),
    )
    return components


def _pass_between(
    normalized: npt.NDArray[np.float64],
    membership: npt.NDArray[np.bool_],
    first: tuple[int, int],
    second: tuple[int, int],
) -> float:
    """Return the highest level whose island component holds both pixels."""
    levels = np.unique(normalized[membership])
    low, high = 0, levels.size - 1
    while low < high:
        middle = (low + high + 1) // 2
        components = _eight_connected(
            membership & (normalized >= levels[middle])
        )
        if components[first] != 0 and components[first] == components[second]:
            low = middle
        else:
            high = middle - 1
    return float(levels[low])


@settings(max_examples=60, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_two_peaks_split_exactly_when_the_weaker_clears_their_pass(
    seed: int,
) -> None:
    """The split agrees with an independent level-set pass on noisy blends.

    Two Gaussians of random height, width and position sit on smooth noise.
    The pass between their peaks is the highest level at which one
    eight-connected component of the island above it holds both.
    """
    generator = np.random.default_rng(seed)
    y, x = np.mgrid[:24, :24]
    normalized = np.asarray(
        ndimage.gaussian_filter(generator.normal(size=(24, 24)), 1.5),
        dtype=np.float64,
    ) * generator.uniform(0.0, 8.0)
    for _ in range(2):
        centre_y, centre_x = generator.uniform(4.0, 20.0, size=2)
        sigma = generator.uniform(1.0, 4.0)
        normalized = normalized + generator.uniform(6.0, 40.0) * np.exp(
            -((y - centre_y) ** 2 + (x - centre_x) ** 2) / (2.0 * sigma**2)
        )
    components = _eight_connected(normalized >= 3.0)
    membership = components == components.flat[np.argmax(normalized)]
    peaks = tuple(
        (int(peak_y), int(peak_x))
        for peak_y, peak_x in np.argwhere(
            membership
            & (normalized > 5.0)
            & (
                normalized
                == ndimage.maximum_filter(
                    np.where(membership, normalized, -np.inf), size=3
                )
            )
        )
    )
    assume(len(peaks) == 2)
    weaker, stronger = sorted(peaks, key=lambda peak: normalized[peak])
    depth = normalized[weaker] - _pass_between(
        normalized, membership, weaker, stronger
    )

    result = deblend_compact_island(
        _compact_island(normalized, membership=membership),
        _config(
            minimum_region_pixels=1,
            maximum_compact_island_pixels=1_000,
            maximum_compact_bounds_pixels=1_000,
            maximum_batch_pixels=1_000,
        ),
        marker_partition="intensity-watershed",
    )

    expected = {weaker, stronger} if depth >= 2.0 else {stronger}
    assert {region.peak_position_yx for region in result.regions} == expected


def test_an_island_part_without_a_peak_fails_closed() -> None:
    """Every accepted pixel needs a peak to flood from; none is invented."""
    normalized = np.array([[8.0, 3.0, 9.0, 0.0, 4.0]])

    with pytest.raises(ValueError, match="did not assign every island pixel"):
        deblend_compact_island(
            _compact_island(normalized, membership=normalized >= 3.0),
            _config(),
            marker_partition="intensity-watershed",
        )


def test_undersized_watershed_child_merges_before_fitting() -> None:
    """A promoted peak cannot create a region too small for its fit model."""
    compact = _compact_island(
        np.array([[6.0, 5.0, 4.0, 3.0, 3.0, 4.0, 5.0, 8.0]])
    )

    result = deblend_compact_island(
        compact,
        _config(minimum_region_pixels=5),
    )

    assert result.status == "single-region"
    assert result.regions[0].pixel_count == compact.island.pixel_count
    np.testing.assert_array_equal(
        result.region_labels > 0,
        compact.island_membership,
    )


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


def test_multiple_peaks_do_not_let_a_masked_hole_flood_the_island() -> None:
    """Non-members are high barriers, not competing watershed markers."""
    normalized = np.full((5, 5), 3.0)
    normalized[0, 0] = 8.0
    normalized[4, 4] = 7.0
    membership = np.ones(normalized.shape, dtype=np.bool_)
    membership[2, 2] = False
    compact = _compact_island(normalized, membership=membership)

    result = deblend_compact_island(compact, _config())

    np.testing.assert_array_equal(result.region_labels > 0, membership)
    assert sum(region.pixel_count for region in result.regions) == 24


def test_region_bounds_cannot_replace_exact_watershed_membership() -> None:
    """Overlapping summary rectangles contain pixels owned by other regions."""
    normalized = np.full((5, 5), 3.0)
    normalized[0, 0] = 8.0
    normalized[4, 4] = 7.0

    result = deblend_compact_island(
        _compact_island(normalized),
        _config(),
    )

    assert result.status == "deblended"
    first, second = result.regions
    assert first.bounds == ImageBounds(0, 5, 0, 5)
    assert first.pixel_count == 22
    assert second.bounds == ImageBounds(3, 5, 3, 5)
    first_box = np.ones(first.bounds.shape_yx, dtype=np.bool_)
    exact_first = result.region_labels == first.region_label
    assert np.count_nonzero(first_box) == 25
    assert np.count_nonzero(exact_first) == first.pixel_count
    assert np.any(first_box & (result.region_labels == second.region_label))


def test_extracts_one_parent_from_a_window_with_nested_islands() -> None:
    """A boolean product window may contain a second disconnected island."""
    accepted = np.zeros((7, 7), dtype=np.bool_)
    accepted[[0, -1], :] = True
    accepted[:, [0, -1]] = True
    accepted[3, 3] = True
    target = replace(
        _compact_island(np.full((7, 7), 6.0)).island,
        pixel_count=24,
        peak_position_yx=(0, 0),
        first_pixel_yx=(0, 0),
    )

    membership = extract_island_membership(target, accepted)

    expected = np.array(accepted, copy=True)
    expected[3, 3] = False
    np.testing.assert_array_equal(membership, expected)
    assert not membership.flags.writeable


def test_island_membership_extraction_rejects_ambiguous_windows() -> None:
    """Malformed mask windows cannot select the wrong connected component."""
    target = _compact_island(np.full((2, 2), 6.0)).island
    valid = np.ones((2, 2), dtype=np.bool_)

    with pytest.raises(ValueError, match="two-dimensional"):
        extract_island_membership(target, np.ones(4, dtype=np.bool_))
    with pytest.raises(TypeError, match="boolean"):
        extract_island_membership(target, np.ones((2, 2), dtype=np.uint8))
    with pytest.raises(ValueError, match="match island bounds"):
        extract_island_membership(target, np.ones((1, 2), dtype=np.bool_))
    with pytest.raises(ValueError, match="outside its bounds"):
        extract_island_membership(
            replace(target, first_pixel_yx=(3, 3)),
            valid,
        )
    absent = np.array(valid, copy=True)
    absent[0, 0] = False
    with pytest.raises(ValueError, match="absent from the mask"):
        extract_island_membership(target, absent)
    with pytest.raises(ValueError, match="disagrees with island"):
        extract_island_membership(replace(target, pixel_count=3), valid)


def test_worker_local_region_contract_rejects_misaligned_arrays() -> None:
    """A processor never receives ambiguous shapes, dtypes, or ownership."""
    item = _worker_local_island()

    with pytest.raises(ValueError, match="match bounds"):
        replace(
            item,
            physical_residual=_read_only(np.ones((1, 2), dtype=np.float64)),
        )
    with pytest.raises(TypeError, match="physical residual"):
        replace(
            item,
            physical_residual=_read_only(np.ones((2, 2), dtype=np.float32)),
        )
    with pytest.raises(TypeError, match="RMS"):
        replace(
            item,
            rms=_read_only(np.ones((2, 2), dtype=np.float32)),
        )
    with pytest.raises(TypeError, match="validity"):
        replace(
            item,
            valid_pixels=_read_only(np.ones((2, 2), dtype=np.uint8)),
        )
    with pytest.raises(TypeError, match="labels"):
        replace(
            item,
            region_labels=_read_only(np.ones((2, 2), dtype=np.int64)),
        )
    with pytest.raises(ValueError, match="read-only"):
        replace(
            item,
            physical_residual=np.ones((2, 2), dtype=np.float64),
        )


def test_worker_local_region_contract_rejects_invalid_science() -> None:
    """Invalid measurement pixels fail before a future moment or fit kernel."""
    item = _worker_local_island()
    invalid_validity = np.ones((2, 2), dtype=np.bool_)
    invalid_validity[0, 0] = False
    nonfinite = np.ones((2, 2), dtype=np.float64)
    nonfinite[0, 0] = np.nan
    nonpositive_rms = np.ones((2, 2), dtype=np.float64)
    nonpositive_rms[0, 0] = 0.0

    with pytest.raises(ValueError, match="invalid pixel"):
        replace(
            item,
            valid_pixels=_read_only(invalid_validity),
        )
    with pytest.raises(ValueError, match="scientifically invalid"):
        replace(
            item,
            physical_residual=_read_only(nonfinite),
        )
    with pytest.raises(ValueError, match="scientifically invalid"):
        replace(
            item,
            rms=_read_only(nonpositive_rms),
        )


def test_worker_local_region_contract_binds_summaries_and_memory() -> None:
    """Exact labels, compact summaries, and admitted bytes cannot diverge."""
    item = _worker_local_island()
    wrong_labels = np.full((2, 2), 2, dtype=np.int32)
    wrong_parent = replace(item.regions[0], island_id="island-other")
    wrong_count = replace(item.regions[0], pixel_count=3)

    assert item.array_byte_count == 4 * (8 + 8 + 1 + 4)
    batch = WorkerLocalRegionBatch(
        islands=(item,),
        admitted_bounds_pixel_count=4,
    )
    assert batch.array_byte_count == item.array_byte_count
    with pytest.raises(ValueError, match="summaries disagree"):
        replace(item, region_labels=_read_only(wrong_labels))
    with pytest.raises(ValueError, match="parent identities"):
        replace(item, regions=(wrong_parent,))
    with pytest.raises(ValueError, match="pixel counts"):
        replace(item, regions=(wrong_count,))
    with pytest.raises(ValueError, match="admitted bounds"):
        replace(batch, admitted_bounds_pixel_count=3)
    with pytest.raises(ValueError, match="must contain island"):
        replace(item, array_bounds=ImageBounds(0, 1, 0, 1))


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


def test_planner_targets_parallel_batches_below_the_hard_memory_limit() -> (
    None
):
    """Small islands fill execution targets without lowering admission."""
    islands = tuple(
        _compact_island(
            np.full((2, 2), 6.0),
            island_id=f"island-{index:05d}",
            global_label=index,
        ).island
        for index in range(1, 5)
    )

    plan = plan_compact_deblend_batches(
        islands,
        _config(
            maximum_compact_bounds_pixels=16,
            target_batch_pixels=8,
            maximum_batch_pixels=32,
        ),
    )

    assert tuple(batch.estimated_pixel_count for batch in plan.batches) == (
        8,
        8,
    )


def test_planner_rejects_duplicate_island_identities() -> None:
    """Ambiguous compact work cannot produce duplicate region identities."""
    island = _compact_island(np.full((2, 2), 6.0)).island

    with pytest.raises(ValueError, match="unique"):
        plan_compact_deblend_batches((island, island), _config())


def test_planner_accounts_for_clipped_fit_context() -> None:
    """Expanded fit pixels count against bounds and batch admission limits."""
    edge = _compact_island(
        np.full((2, 2), 6.0),
        bounds_origin_yx=(0, 0),
    ).island

    plan = plan_compact_deblend_batches(
        (edge,),
        _config(maximum_compact_bounds_pixels=25),
        context_margin_pixels=3,
        image_shape_yx=(20, 20),
    )

    assert plan.batches[0].estimated_pixel_count == 25
    with pytest.raises(ValueError, match="logical image shape"):
        plan_compact_deblend_batches(
            (edge,),
            _config(),
            context_margin_pixels=3,
        )


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
