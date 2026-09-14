"""Analytic contracts for deterministic multiscale source reconstruction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import numpy as np
import pytest

from hebog.algorithms.multiscale_association import (
    ScaleDetectionPlane,
    build_scale_detection_plane,
)
from hebog.algorithms.source_association import (
    _apply_scale_aware_parent_groups,  # pyright: ignore[reportPrivateUsage]
    _apply_terminal_cycle_groups,  # pyright: ignore[reportPrivateUsage]
    _isolated_sibling_feature_pairs,  # pyright: ignore[reportPrivateUsage]
    _ScaleAwareParentEvidence,  # pyright: ignore[reportPrivateUsage]
    _TerminalCycleEvidence,  # pyright: ignore[reportPrivateUsage]
    associate_components_by_multiscale_hierarchy,
    build_detection_component_records,
)
from hebog.data_models.multiscale import ScaleDetection
from hebog.data_models.source_association import DetectionComponentRecord


def _plane(
    scale_order: int,
    entries: Sequence[tuple[str, Sequence[tuple[int, int]]]],
    *,
    shape: tuple[int, int] = (15, 15),
    origin_yx: tuple[int, int] = (0, 0),
) -> ScaleDetectionPlane:
    """Build one exact undilated scale-support plane."""
    labels = np.zeros(shape, dtype=np.int32)
    detections: list[ScaleDetection] = []
    for label_value, (identifier, pixels) in enumerate(entries, start=1):
        ordered = tuple(sorted(pixels))
        for pixel in ordered:
            labels[pixel] = label_value
        ys = tuple(item[0] + origin_yx[0] for item in ordered)
        xs = tuple(item[1] + origin_yx[1] for item in ordered)
        detections.append(
            ScaleDetection(
                detection_id=identifier,
                parent_island_id=None,
                scale_order=scale_order,
                nominal_scale_beam_fwhm=float(2 ** (scale_order - 1)),
                support_pixel_count=len(ordered),
                valid_support_fraction=1.0,
                bounds_yx=(min(ys), max(ys) + 1, min(xs), max(xs) + 1),
                canonical_pixel_yx=(ys[0], xs[0]),
                peak_response_jy_per_beam=1.0,
                peak_signal_to_noise=5.0,
                touches_image_edge=False,
            )
        )
    return ScaleDetectionPlane(
        scale_order=scale_order,
        component_labels=labels,
        detections=tuple(detections),
        origin_yx=origin_yx,
    )


def _components(
    pixels: tuple[tuple[int, int], ...],
    *,
    labels: tuple[int, ...] | None = None,
    shape: tuple[int, int] = (15, 15),
    origin_yx: tuple[int, int] = (0, 0),
) -> tuple[np.ndarray, tuple[DetectionComponentRecord, ...]]:
    """Return immutable direct owners and their stable records."""
    values = labels or tuple(range(1, len(pixels) + 1))
    owner_labels = np.zeros(shape, dtype=np.int32)
    for label_value, pixel in zip(values, pixels, strict=True):
        owner_labels[pixel] = label_value
    records = build_detection_component_records(
        owner_labels,
        np.asarray(owner_labels > 0, dtype=np.float64),
        np.ones(shape, dtype=np.bool_),
        origin_yx=origin_yx,
    )
    return owner_labels, records


@pytest.mark.parametrize(
    ("adjacency", "expected"),
    (
        (
            {"feature-a": {"feature-b"}, "feature-b": {"feature-a"}},
            (frozenset(("feature-a", "feature-b")),),
        ),
        (
            {
                "feature-a": {"feature-b"},
                "feature-b": {"feature-a", "feature-c"},
                "feature-c": {"feature-b"},
            },
            (),
        ),
        (
            {
                "feature-a": {"feature-b", "feature-c"},
                "feature-b": {"feature-a", "feature-c"},
                "feature-c": {"feature-a", "feature-b"},
            },
            (),
        ),
    ),
    ids=("isolated-pair", "chain", "crowded-cycle"),
)
def test_sibling_pair_geometry_requires_mutual_uniqueness(
    adjacency: dict[str, set[str]],
    expected: tuple[frozenset[str], ...],
) -> None:
    """Only a symmetric isolated pair may enter persistence testing."""
    assert _isolated_sibling_feature_pairs(adjacency) == expected


def _displaced_terminal_cycle_fixture(
    *,
    ambiguous_first_child: bool = False,
    disconnected_first_child: bool = False,
) -> tuple[
    np.ndarray,
    tuple[DetectionComponentRecord, ...],
    tuple[ScaleDetectionPlane, ScaleDetectionPlane],
    np.ndarray,
]:
    """Return one terminal cycle with bounded preceding-scale drift."""
    terminal_pixels = ((10, 10), (10, 34), (34, 10), (34, 34))
    preceding_pixels = ((9, 9), (9, 35), (35, 9), (35, 35))
    labels, records = _components(terminal_pixels, shape=(49, 49))
    preceding_entries: list[tuple[str, Sequence[tuple[int, int]]]] = [
        (f"scale-displaced-child-{index}", (pixel,))
        for index, pixel in enumerate(preceding_pixels, start=1)
    ]
    if ambiguous_first_child:
        preceding_entries.append(
            ("scale-displaced-child-ambiguous", ((9, 11),))
        )
    preceding = _plane(
        2,
        preceding_entries,
        shape=labels.shape,
    )
    terminal = _plane(
        3,
        tuple(
            (f"scale-displaced-parent-{index}", (pixel,))
            for index, pixel in enumerate(terminal_pixels, start=1)
        ),
        shape=labels.shape,
    )
    significant = np.zeros(labels.shape, dtype=np.bool_)
    for index, (preceding_pixel, terminal_pixel) in enumerate(
        zip(preceding_pixels, terminal_pixels, strict=True)
    ):
        if disconnected_first_child and index == 0:
            continue
        y0 = min(preceding_pixel[0], terminal_pixel[0])
        y1 = max(preceding_pixel[0], terminal_pixel[0]) + 1
        x0 = min(preceding_pixel[1], terminal_pixel[1])
        x1 = max(preceding_pixel[1], terminal_pixel[1]) + 1
        significant[y0:y1, x0:x1] = True
    if not disconnected_first_child:
        # Keep every lobe in one retained support component. This exercises
        # the bounded-envelope rejection for distant, non-overlapping pairs
        # instead of rejecting them earlier by component identity alone.
        significant[9:36, 9:36] = True
    if ambiguous_first_child:
        significant[9:11, 9:12] = True
    return labels, records, (preceding, terminal), significant


def _unseeded_terminal_cycle_fixture(
    *,
    direct_owner_count: int = 3,
    unseeded_feature_is_persistent: bool = True,
) -> tuple[
    np.ndarray,
    tuple[DetectionComponentRecord, ...],
    tuple[ScaleDetectionPlane, ScaleDetectionPlane],
]:
    """Return a four-feature cycle with only three direct owners."""
    pixels = ((10, 10), (10, 30), (30, 10), (30, 30))
    labels, records = _components(
        pixels[:direct_owner_count],
        shape=(41, 41),
    )
    preceding_pixels = pixels if unseeded_feature_is_persistent else pixels[:3]
    preceding = _plane(
        2,
        tuple(
            (f"scale-unseeded-child-{index}", (pixel,))
            for index, pixel in enumerate(preceding_pixels, start=1)
        ),
        shape=labels.shape,
    )
    terminal = _plane(
        3,
        tuple(
            (f"scale-unseeded-parent-{index}", (pixel,))
            for index, pixel in enumerate(pixels, start=1)
        ),
        shape=labels.shape,
    )
    return labels, records, (preceding, terminal)


@pytest.mark.parametrize("offset", ((0, 0), (0, 5), (5, 5)))
def test_multipeak_shell_uses_one_explicit_common_parent(
    offset: tuple[int, int],
) -> None:
    """Curved centre, boundary, and corner fragments share a coarse ring."""
    oy, ox = offset
    pixels = ((2 + oy, 2 + ox), (2 + oy, 6 + ox), (6 + oy, 4 + ox))
    labels, records = _components(pixels)
    fine = _plane(
        1,
        tuple(
            (f"scale-shell-fine-{index}", (pixel,))
            for index, pixel in enumerate(pixels, start=1)
        ),
    )
    ring = tuple(
        (y + oy, x + ox)
        for y, x in (
            (2, 2),
            (2, 3),
            (2, 4),
            (2, 5),
            (2, 6),
            (3, 2),
            (3, 6),
            (4, 2),
            (4, 6),
            (5, 2),
            (5, 6),
            (6, 2),
            (6, 3),
            (6, 4),
            (6, 5),
            (6, 6),
        )
    )
    coarse = _plane(2, (("scale-shell-parent", ring),))
    persistent = _plane(3, (("scale-shell-persistent", ring),))

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine, coarse, persistent),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert len(result.memberships) == 1
    assert len(result.memberships[0].component_ids) == 3
    assert result.ambiguous_component_ids == ()
    np.testing.assert_array_equal(labels > 0, np.isin(labels, (1, 2, 3)))


def test_filaments_follow_support_not_centroid_chords() -> None:
    """Common-parent paths may curve and need no straight bright chord."""
    pixels = ((2, 2), (7, 7), (12, 12))
    labels, records = _components(pixels)
    fine = _plane(
        1,
        tuple(
            (f"scale-filament-fine-{index}", (pixel,))
            for index, pixel in enumerate(pixels, start=1)
        ),
    )
    curved = tuple(
        [(2, x) for x in range(2, 8)]
        + [(y, 7) for y in range(3, 13)]
        + [(12, x) for x in range(8, 13)]
    )
    parent = _plane(2, (("scale-filament-parent", curved),))
    persistent = _plane(3, (("scale-filament-persistent", curved),))

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine, parent, persistent),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [3]


def test_three_lobe_artifact_uses_one_common_parent() -> None:
    """Three separated peaks compose only through their explicit feature."""
    pixels = ((4, 2), (7, 7), (4, 12))
    labels, records = _components(pixels)
    fine = _plane(
        1,
        tuple(
            (f"scale-artifact-fine-{index}", (pixel,))
            for index, pixel in enumerate(pixels, start=1)
        ),
    )
    parent_support = tuple(
        [(4, x) for x in range(2, 13)] + [(y, 7) for y in range(5, 8)]
    )
    parent = _plane(2, (("scale-artifact-parent", parent_support),))
    persistent = _plane(3, (("scale-artifact-persistent", parent_support),))

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine, parent, persistent),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [3]


@pytest.mark.parametrize("scale_order", (1, 4))
def test_single_scale_feature_retains_one_source(scale_order: int) -> None:
    """Isolated scale-one and scale-four detections remain one source."""
    labels, records = _components(((6, 6),))
    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (_plane(scale_order, (("scale-single", ((6, 6),)),)),),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert len(result.memberships) == 1
    assert result.memberships[0].component_ids == (records[0].component_id,)


def test_nearby_sources_with_no_significant_bridge_remain_separate() -> None:
    """Proximity and a faint bridge cannot manufacture a parent."""
    pixels = ((7, 5), (7, 9))
    labels, records = _components(pixels)
    fine = _plane(
        1,
        (
            ("scale-nearby-left", (pixels[0],)),
            ("scale-nearby-right", (pixels[1],)),
        ),
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine,),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert len(result.memberships) == 2


def test_hierarchy_is_tile_shape_and_partition_origin_invariant() -> None:
    """A bounded view reproduces the same global source membership."""
    full_pixels = ((6, 6), (6, 10))
    full_labels, full_records = _components(full_pixels)
    full_parent = tuple((6, x) for x in range(6, 11))
    full = associate_components_by_multiscale_hierarchy(
        full_records,
        full_labels,
        (_plane(1, (("scale-global-parent", full_parent),)),),
        np.ones(full_labels.shape, dtype=np.bool_),
    )

    origin = (4, 5)
    local_pixels = ((2, 1), (2, 5))
    local_labels, local_records = _components(
        local_pixels,
        shape=(5, 7),
        origin_yx=origin,
    )
    local_parent = tuple((2, x) for x in range(1, 6))
    bounded = associate_components_by_multiscale_hierarchy(
        local_records,
        local_labels,
        (
            _plane(
                1,
                (("scale-global-parent", local_parent),),
                shape=local_labels.shape,
                origin_yx=origin,
            ),
        ),
        np.ones(local_labels.shape, dtype=np.bool_),
    )

    assert bounded.memberships == full.memberships


def test_ambiguous_transitive_bridge_fails_closed() -> None:
    """A component with two possible parents cannot bridge two sources."""
    pixels = ((7, 2), (7, 7), (7, 12))
    labels, records = _components(pixels)
    fine = _plane(
        1,
        (
            ("scale-chain-fine-1", (pixels[0],)),
            ("scale-chain-fine-2", ((7, 7), (8, 7))),
            ("scale-chain-fine-3", ((7, 12), (8, 12))),
        ),
    )
    parents = _plane(
        2,
        (
            ("scale-chain-left-parent", tuple((7, x) for x in range(2, 8))),
            ("scale-chain-right-parent", tuple((8, x) for x in range(7, 13))),
        ),
    )
    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine, parents),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert len(result.memberships) == 3
    assert len(result.ambiguous_component_ids) == 1


def test_multiple_finest_features_use_one_persistent_common_convergence() -> (
    None
):
    """One owner crossing fine features may still have one source parent."""
    labels = np.zeros((9, 15), dtype=np.int32)
    labels[4, 2:7] = 1
    labels[4, 11] = 2
    records = build_detection_component_records(
        labels,
        np.asarray(labels > 0, dtype=np.float64),
        np.ones(labels.shape, dtype=np.bool_),
    )
    fine = _plane(
        1,
        (
            ("scale-expanded-left-a", ((4, 2), (4, 3))),
            ("scale-expanded-left-b", ((4, 5), (4, 6))),
            ("scale-expanded-right", ((4, 11),)),
        ),
        shape=labels.shape,
    )
    convergence = _plane(
        2,
        (("scale-expanded-convergence", tuple((4, x) for x in range(2, 12))),),
        shape=labels.shape,
    )
    persistent = _plane(
        3,
        (("scale-expanded-persistent", tuple((4, x) for x in range(2, 12))),),
        shape=labels.shape,
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine, convergence, persistent),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [2]
    assert result.ambiguous_component_ids == ()
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.direct_component_count == 2
    assert diagnostics.catalogue_source_count == 1
    assert diagnostics.membership_size_histogram == ((2, 1),)
    assert diagnostics.multiple_finest_feature_attachment_count == 1
    assert diagnostics.unique_convergence_count == 1


def test_terminal_coarse_bridge_does_not_merge_independent_sources() -> None:
    """A bridge appearing only at the terminal scale is not corroborated."""
    pixels = ((4, 2), (4, 12))
    labels, records = _components(pixels)
    fine = _plane(
        1,
        (
            ("scale-bridge-left-fine", (pixels[0],)),
            ("scale-bridge-right-fine", (pixels[1],)),
        ),
        shape=labels.shape,
    )
    separated = _plane(
        2,
        (
            ("scale-bridge-left-mid", tuple((4, x) for x in range(2, 5))),
            ("scale-bridge-right-mid", tuple((4, x) for x in range(10, 13))),
        ),
        shape=labels.shape,
    )
    terminal_bridge = _plane(
        3,
        (("scale-terminal-bridge", tuple((4, x) for x in range(2, 13))),),
        shape=labels.shape,
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine, separated, terminal_bridge),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [1, 1]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.unique_convergence_count == 0
    assert diagnostics.catalogue_source_count == 2


def test_persistent_two_feature_envelopes_do_not_invent_one_source() -> None:
    """Two nearby persistent features remain conservatively independent."""
    pixels = ((10, 5), (10, 15))
    labels, records = _components(pixels, shape=(21, 21))
    middle = _plane(
        2,
        (
            ("scale-pair-left-middle", ((10, 5),)),
            ("scale-pair-right-middle", ((10, 15),)),
        ),
        shape=labels.shape,
    )
    coarse = _plane(
        3,
        (
            ("scale-pair-left-coarse", ((10, 5),)),
            ("scale-pair-right-coarse", ((10, 15),)),
        ),
        shape=labels.shape,
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (middle, coarse),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [1, 1]


def test_persistent_connected_sibling_envelopes_construct_one_parent() -> None:
    """Repeated isolated sibling geometry plus signal support is a parent."""
    pixels = ((10, 5), (10, 15))
    labels, records = _components(pixels, shape=(21, 21))
    planes = tuple(
        _plane(
            scale_order,
            tuple(
                (f"scale-sibling-{scale_order}-{index}", (pixel,))
                for index, pixel in enumerate(pixels, start=1)
            ),
            shape=labels.shape,
        )
        for scale_order in (2, 3)
    )
    significant = np.zeros(labels.shape, dtype=np.bool_)
    significant[10, 5:16] = True

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert [len(item.component_ids) for item in result.memberships] == [2]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.scale_aware_parent_candidate_count == 2
    assert diagnostics.persistent_parent_count == 1
    assert diagnostics.connected_support_candidate_count == 1


@pytest.mark.parametrize(
    ("pixels", "shape"),
    (
        (((10, 5), (10, 17)), (23, 23)),
        (((10, 0), (10, 12)), (23, 23)),
    ),
    ids=("interior", "clipped-image-edge"),
)
def test_persistent_feature_influence_recovers_one_displaced_component(
    pixels: tuple[tuple[int, int], tuple[int, int]],
    shape: tuple[int, int],
) -> None:
    """A persistent feature may recover one B3-bounded displaced owner."""
    labels, records = _components(pixels, shape=shape)
    planes = tuple(
        _plane(
            scale_order,
            ((f"scale-influence-{scale_order}", (pixels[0],)),),
            shape=labels.shape,
        )
        for scale_order in (2, 3)
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=labels > 0,
    )

    assert [len(item.component_ids) for item in result.memberships] == [2]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.persistent_feature_influence_candidate_count == 1
    assert diagnostics.persistent_feature_influence_parent_count == 1


def test_feature_influence_requires_an_unresolved_displaced_owner() -> None:
    """Two independently resolved components may not be merged by reach."""
    pixels = ((10, 5), (10, 17))
    labels, records = _components(pixels, shape=(23, 23))
    planes = tuple(
        _plane(
            scale_order,
            tuple(
                (f"scale-resolved-{scale_order}-{index}", (pixel,))
                for index, pixel in enumerate(pixels, start=1)
            ),
            shape=labels.shape,
        )
        for scale_order in (2, 3)
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=labels > 0,
    )

    assert [len(item.component_ids) for item in result.memberships] == [1, 1]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.persistent_feature_influence_candidate_count == 0
    assert diagnostics.persistent_feature_influence_parent_count == 0


def test_feature_influence_requires_adjacent_scale_persistence() -> None:
    """A single coarse feature cannot recover a displaced component."""
    pixels = ((10, 5), (10, 17))
    labels, records = _components(pixels, shape=(23, 23))
    coarse = _plane(
        3,
        (("scale-one-look-coarse", (pixels[0],)),),
        shape=labels.shape,
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (coarse,),
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=labels > 0,
    )

    assert [len(item.component_ids) for item in result.memberships] == [1, 1]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.persistent_feature_influence_candidate_count == 0


def test_feature_influence_rejects_a_multiply_parented_child() -> None:
    """A child shared by two parent features cannot corroborate either."""
    pixels = ((10, 5), (10, 17))
    labels, records = _components(pixels, shape=(23, 23))
    child = _plane(
        2,
        (("scale-branched-child", ((10, 5), (10, 6))),),
        shape=labels.shape,
    )
    parents = _plane(
        3,
        (
            ("scale-branched-parent-anchor", ((10, 5),)),
            ("scale-branched-parent-empty", ((10, 6),)),
        ),
        shape=labels.shape,
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (child, parents),
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=labels > 0,
    )

    assert [len(item.component_ids) for item in result.memberships] == [1, 1]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.persistent_feature_influence_candidate_count == 0


def test_feature_influence_cannot_cross_an_invalid_gap() -> None:
    """A B3 influence relationship cannot propagate through invalid data."""
    pixels = ((10, 5), (10, 17))
    labels, records = _components(pixels, shape=(23, 23))
    planes = tuple(
        _plane(
            scale_order,
            ((f"scale-invalid-influence-{scale_order}", (pixels[0],)),),
            shape=labels.shape,
        )
        for scale_order in (2, 3)
    )
    valid = np.ones(labels.shape, dtype=np.bool_)
    valid[:, 11] = False

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        valid,
        significant_multiscale_support=labels > 0,
    )

    assert [len(item.component_ids) for item in result.memberships] == [1, 1]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.persistent_feature_influence_candidate_count == 0


def test_feature_influence_rejects_a_crowded_component_chain() -> None:
    """A three-owner influence neighbourhood cannot manufacture a pair."""
    pixels = ((10, 5), (10, 17), (10, 29))
    labels, records = _components(pixels, shape=(23, 35))
    planes = tuple(
        _plane(
            scale_order,
            (
                (f"scale-crowded-{scale_order}-left", (pixels[0],)),
                (f"scale-crowded-{scale_order}-right", (pixels[2],)),
            ),
            shape=labels.shape,
        )
        for scale_order in (2, 3)
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=labels > 0,
    )

    assert [len(item.component_ids) for item in result.memberships] == [
        1,
        1,
        1,
    ]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.persistent_feature_influence_candidate_count == 0


def test_feature_influence_cannot_partially_overlap_an_existing_source() -> (
    None
):
    """A recovered pair cannot split or extend one established source."""
    established = frozenset(("component-a", "component-c"))
    displaced_pair = frozenset(("component-a", "component-b"))
    evidence = _ScaleAwareParentEvidence(
        groups=(displaced_pair,),
        candidate_count=1,
        rejected_ambiguity_count=0,
        per_scale_candidate_counts=((3, 1),),
        accepted_candidate_occurrences=((displaced_pair, 1),),
        self_corroborated_groups=frozenset((displaced_pair,)),
        feature_influence_candidate_count=1,
    )

    groups, applied = _apply_scale_aware_parent_groups(
        (established, frozenset(("component-b",))),
        evidence,
    )

    assert groups == (established, frozenset(("component-b",)))
    assert applied.groups == ()
    assert applied.self_corroborated_groups == frozenset()
    assert applied.rejected_ambiguity_count == 1


def test_feature_influence_diagnostics_reject_impossible_counts() -> None:
    """Published influence parents cannot exceed observed candidates."""
    labels, records = _components(((5, 5),))
    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (_plane(1, (("scale-diagnostic", ((5, 5),)),)),),
        np.ones(labels.shape, dtype=np.bool_),
    )
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None

    with pytest.raises(
        ValueError,
        match="persistent feature influence parents exceed candidates",
    ):
        replace(
            diagnostics,
            persistent_feature_influence_candidate_count=0,
            persistent_feature_influence_parent_count=1,
        )


def test_persistent_sibling_geometry_requires_one_support_component() -> None:
    """Repeated envelopes cannot merge disconnected nearby detections."""
    pixels = ((10, 5), (10, 15))
    labels, records = _components(pixels, shape=(21, 21))
    planes = tuple(
        _plane(
            scale_order,
            tuple(
                (f"scale-disconnected-{scale_order}-{index}", (pixel,))
                for index, pixel in enumerate(pixels, start=1)
            ),
            shape=labels.shape,
        )
        for scale_order in (2, 3)
    )
    significant = labels > 0

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert [len(item.component_ids) for item in result.memberships] == [1, 1]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.scale_aware_parent_candidate_count == 2
    assert diagnostics.persistent_parent_count == 0
    assert diagnostics.connected_support_candidate_count == 0


@pytest.mark.parametrize(
    "pixels",
    (
        ((7, 3), (7, 11)),
        ((3, 3), (7, 7), (11, 11)),
    ),
    ids=("two-lobe", "curved-path"),
)
def test_connected_support_does_not_conflate_islands_with_sources(
    pixels: tuple[tuple[int, int], ...],
) -> None:
    """Persistent emission alone cannot promote pairs or paths to sources."""
    labels, records = _components(pixels)
    fine = _plane(
        1,
        tuple(
            (f"scale-persistent-{index}", (pixel,))
            for index, pixel in enumerate(pixels, start=1)
        ),
    )
    significant = np.zeros(labels.shape, dtype=np.bool_)
    if len(pixels) == 2:
        significant[7, 3:12] = True
    else:
        significant[3:8, 3] = True
        significant[7, 3:8] = True
        significant[7:12, 7] = True
        significant[11, 7:12] = True

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine,),
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    membership_sizes = [len(item.component_ids) for item in result.memberships]
    assert membership_sizes == [1] * len(pixels)
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.connected_support_candidate_count == 1
    assert diagnostics.rejected_connected_support_ambiguity_count == 0


def test_uncorroborated_terminal_envelope_overlap_remains_separate() -> None:
    """A terminal cycle without persistent constituents cannot merge."""
    pixels = ((10, 20), (20, 10), (20, 30), (30, 20))
    labels, records = _components(pixels, shape=(41, 41))
    terminal = _plane(
        3,
        tuple(
            (f"scale-geometry-terminal-{index}", (pixel,))
            for index, pixel in enumerate(pixels, start=1)
        ),
        shape=labels.shape,
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (terminal,),
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=np.zeros(
            labels.shape,
            dtype=np.bool_,
        ),
    )

    assert [len(item.component_ids) for item in result.memberships] == [1] * 4
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.scale_aware_parent_candidate_count == 1
    assert diagnostics.persistent_parent_count == 0
    assert diagnostics.connected_support_candidate_count == 0
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 0
    assert diagnostics.rejected_terminal_cycle_count == 1


def test_connected_support_cannot_change_an_exact_group() -> None:
    """Support cannot split one exact source or manufacture another."""
    pixels = ((4, 2), (4, 7), (4, 12))
    labels, records = _components(pixels)
    fine = _plane(
        1,
        tuple(
            (f"scale-conflict-{index}", (pixel,))
            for index, pixel in enumerate(pixels, start=1)
        ),
    )
    exact_parent = _plane(
        2,
        (
            ("scale-conflict-left-parent", tuple((4, x) for x in range(2, 8))),
            ("scale-conflict-right", (pixels[2],)),
        ),
    )
    persistent_parent = _plane(
        3,
        (
            (
                "scale-conflict-left-persistent",
                tuple((4, x) for x in range(2, 8)),
            ),
            ("scale-conflict-right-persistent", (pixels[2],)),
        ),
    )
    significant = np.zeros(labels.shape, dtype=np.bool_)
    significant[4, 7:13] = True

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine, exact_parent, persistent_parent),
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert sorted(len(item.component_ids) for item in result.memberships) == [
        1,
        2,
    ]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.connected_support_candidate_count == 1
    assert diagnostics.rejected_connected_support_ambiguity_count == 0


def test_connected_support_rejects_invalid_or_misaligned_evidence() -> None:
    """Persistent support is a validated scientific input, not a hint."""
    labels, records = _components(((4, 4),))
    plane = _plane(1, (("scale-support", ((4, 4),)),))
    valid = np.ones(labels.shape, dtype=np.bool_)
    invalid_support = np.zeros(labels.shape, dtype=np.bool_)
    invalid_support[3, 3] = True
    valid[3, 3] = False

    with pytest.raises(ValueError, match=r"significant.*valid"):
        associate_components_by_multiscale_hierarchy(
            records,
            labels,
            (plane,),
            valid,
            significant_multiscale_support=invalid_support,
        )
    with pytest.raises(ValueError, match="aligned boolean"):
        associate_components_by_multiscale_hierarchy(
            records,
            labels,
            (plane,),
            np.ones(labels.shape, dtype=np.bool_),
            significant_multiscale_support=np.zeros((2, 2)),
        )


def test_unseeded_persistent_support_is_ignored() -> None:
    """A support island without multiple direct owners creates no parent."""
    labels, records = _components(((3, 3), (11, 11)))
    fine = _plane(
        1,
        (
            ("scale-unseeded-left", ((3, 3),)),
            ("scale-unseeded-right", ((11, 11),)),
        ),
    )
    significant = np.zeros(labels.shape, dtype=np.bool_)
    significant[6:9, 6:9] = True

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine,),
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert [len(item.component_ids) for item in result.memberships] == [1, 1]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.connected_support_candidate_count == 0


def test_persistent_support_does_not_override_ambiguous_lineage() -> None:
    """Connected emission cannot promote a hierarchy-ambiguous owner."""
    labels = np.zeros((9, 11), dtype=np.int32)
    labels[4, 2:4] = 1
    labels[4, 8] = 2
    records = build_detection_component_records(
        labels,
        np.asarray(labels > 0, dtype=np.float64),
        np.ones(labels.shape, dtype=np.bool_),
    )
    fine = _plane(
        1,
        (
            ("scale-ambiguous-first", ((4, 2),)),
            ("scale-ambiguous-second", ((4, 3),)),
            ("scale-ambiguous-other", ((4, 8),)),
        ),
        shape=labels.shape,
    )
    significant = np.zeros(labels.shape, dtype=np.bool_)
    significant[4, 2:9] = True

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine,),
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert [len(item.component_ids) for item in result.memberships] == [1, 1]
    assert len(result.ambiguous_component_ids) == 1
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.connected_support_candidate_count == 1
    assert diagnostics.rejected_connected_support_ambiguity_count == 1


def test_disconnected_direct_component_fails_parent_construction() -> None:
    """One direct identity may not span disconnected support parents."""
    labels = np.zeros((11, 11), dtype=np.int32)
    labels[2, 2] = 1
    labels[8, 8] = 1
    records = build_detection_component_records(
        labels,
        np.asarray(labels > 0, dtype=np.float64),
        np.ones(labels.shape, dtype=np.bool_),
    )
    plane = _plane(
        1,
        (("scale-disconnected-owner", ((2, 2), (8, 8))),),
        shape=labels.shape,
    )

    with pytest.raises(ValueError, match=r"one connected support parent"):
        associate_components_by_multiscale_hierarchy(
            records,
            labels,
            (plane,),
            np.ones(labels.shape, dtype=np.bool_),
            significant_multiscale_support=np.zeros(
                labels.shape,
                dtype=np.bool_,
            ),
        )


def test_persistent_cycle_supported_envelopes_construct_one_parent() -> None:
    """A four-lobe parent must recur at adjacent B3 footprint scales."""
    pixels = ((10, 20), (20, 10), (20, 30), (30, 20))
    labels, records = _components(pixels, shape=(41, 41))
    planes = tuple(
        _plane(
            scale_order,
            tuple(
                (f"scale-ring-{scale_order}-{index}", (pixel,))
                for index, pixel in enumerate(pixels, start=1)
            ),
            shape=labels.shape,
        )
        for scale_order in (2, 3)
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [4]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.scale_aware_parent_candidate_count == 2
    assert diagnostics.persistent_parent_count == 0
    assert diagnostics.rejected_parent_ambiguity_count == 2
    assert diagnostics.terminal_cycle_parent_count == 1


def test_terminal_cycle_with_persistent_features_constructs_parent() -> None:
    """A final-scale cycle may use constituents persistent from scale two."""
    pixels = ((10, 10), (10, 30), (30, 10), (30, 30))
    labels, records = _components(pixels, shape=(41, 41))
    planes = tuple(
        _plane(
            scale_order,
            tuple(
                (f"scale-terminal-{scale_order}-{index}", (pixel,))
                for index, pixel in enumerate(pixels, start=1)
            ),
            shape=labels.shape,
        )
        for scale_order in (2, 3)
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [4]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.per_scale_parent_candidate_counts == ((2, 0), (3, 1))
    assert diagnostics.persistent_parent_count == 0
    assert diagnostics.rejected_parent_ambiguity_count == 1
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 1
    assert diagnostics.rejected_terminal_cycle_count == 0


def test_nonpersistent_unseeded_cycle_feature_rejects_parent() -> None:
    """Unseeded geometry still requires independent persistence."""
    labels, records, planes = _unseeded_terminal_cycle_fixture(
        unseeded_feature_is_persistent=False,
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [1] * 3
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 0
    assert diagnostics.rejected_terminal_cycle_count == 1
    assert diagnostics.terminal_cycle_pre_eligibility_candidate_count == 1
    assert diagnostics.terminal_cycle_unseeded_candidate_count == 1
    assert diagnostics.terminal_cycle_unseeded_persistent_accepted_count == 0
    assert diagnostics.terminal_cycle_unseeded_persistence_rejected_count == 1


def test_unseeded_cycle_cannot_lower_direct_member_requirement() -> None:
    """Persistent geometry cannot become a catalogue member."""
    labels, records, planes = _unseeded_terminal_cycle_fixture(
        direct_owner_count=2,
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [1, 1]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.terminal_cycle_pre_eligibility_candidate_count == 1
    assert diagnostics.terminal_cycle_candidate_count == 0
    assert diagnostics.terminal_cycle_parent_count == 0
    assert diagnostics.terminal_cycle_unseeded_candidate_count == 0


def test_persistent_unseeded_cycle_feature_corroborates_seeded_parent() -> (
    None
):
    """Persistent geometry may corroborate but never join membership."""
    labels, records, planes = _unseeded_terminal_cycle_fixture()

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [3]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 1
    assert diagnostics.rejected_terminal_cycle_count == 0
    assert diagnostics.terminal_cycle_pre_eligibility_candidate_count == 1
    assert diagnostics.terminal_cycle_unseeded_candidate_count == 1
    assert diagnostics.terminal_cycle_unseeded_persistent_accepted_count == 1
    assert diagnostics.terminal_cycle_unseeded_persistence_rejected_count == 0


def test_terminal_cycle_accepts_unique_displaced_persistent_children() -> None:
    """A bounded one-pixel scale drift preserves a terminal-cycle parent."""
    labels, records, planes, significant = _displaced_terminal_cycle_fixture()

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert [len(item.component_ids) for item in result.memberships] == [4]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 1
    assert diagnostics.rejected_terminal_cycle_count == 0
    assert diagnostics.terminal_persistence_exact_feature_count == 0
    assert diagnostics.terminal_persistence_displaced_candidate_count == 4
    assert diagnostics.terminal_persistence_displaced_accepted_count == 4
    assert diagnostics.terminal_persistence_missing_child_count == 0
    assert diagnostics.terminal_persistence_ambiguous_child_count == 0
    assert diagnostics.terminal_persistence_conflict_count == 0


def test_displaced_child_requires_same_connected_support() -> None:
    """Envelope overlap alone cannot corroborate a disconnected child."""
    labels, records, planes, significant = _displaced_terminal_cycle_fixture(
        disconnected_first_child=True
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert [len(item.component_ids) for item in result.memberships] == [1] * 4
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 0
    assert diagnostics.rejected_terminal_cycle_count == 1
    assert diagnostics.terminal_persistence_displaced_candidate_count == 3
    assert diagnostics.terminal_persistence_displaced_accepted_count == 3
    assert diagnostics.terminal_persistence_missing_child_count == 1
    assert diagnostics.terminal_persistence_ambiguous_child_count == 0
    assert (
        diagnostics.terminal_cycle_missing_child_resilience_candidate_count
        == 1
    )
    assert (
        diagnostics.terminal_cycle_missing_child_resilience_parent_count == 0
    )
    assert (
        diagnostics.terminal_cycle_missing_child_resilience_rejected_count == 1
    )


def test_one_missing_owned_child_does_not_veto_exclusive_terminal_cycle() -> (
    None
):
    """One missing child cannot split an otherwise persistent source graph."""
    terminal_pixels = ((10, 10), (10, 34), (34, 10), (34, 34))
    labels, records = _components(terminal_pixels, shape=(49, 49))
    preceding = _plane(
        2,
        tuple(
            (f"scale-one-missing-child-{index}", (pixel,))
            for index, pixel in enumerate(terminal_pixels[1:], start=2)
        ),
        shape=labels.shape,
    )
    terminal = _plane(
        3,
        tuple(
            (f"scale-one-missing-parent-{index}", (pixel,))
            for index, pixel in enumerate(terminal_pixels, start=1)
        ),
        shape=labels.shape,
    )
    significant = np.zeros(labels.shape, dtype=np.bool_)
    significant[9:36, 9:36] = True

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (preceding, terminal),
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert [len(item.component_ids) for item in result.memberships] == [4]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 1
    assert diagnostics.rejected_terminal_cycle_count == 0
    assert diagnostics.terminal_persistence_missing_child_count == 1
    assert (
        diagnostics.terminal_cycle_missing_child_resilience_candidate_count
        == 1
    )
    assert (
        diagnostics.terminal_cycle_missing_child_resilience_parent_count == 1
    )
    assert (
        diagnostics.terminal_cycle_missing_child_resilience_rejected_count == 0
    )


def test_multiply_owned_missing_child_rejects_terminal_cycle() -> None:
    """A missing feature with two direct owners is not an exclusive lobe."""
    direct_pixels = ((10, 10), (10, 11), (10, 34), (34, 10), (34, 34))
    labels, records = _components(direct_pixels, shape=(49, 49))
    preceding = _plane(
        2,
        tuple(
            (f"scale-multiply-owned-child-{index}", (pixel,))
            for index, pixel in enumerate(direct_pixels[2:], start=2)
        ),
        shape=labels.shape,
    )
    terminal = _plane(
        3,
        (
            ("scale-multiply-owned-parent-1", direct_pixels[:2]),
            ("scale-multiply-owned-parent-2", (direct_pixels[2],)),
            ("scale-multiply-owned-parent-3", (direct_pixels[3],)),
            ("scale-multiply-owned-parent-4", (direct_pixels[4],)),
        ),
        shape=labels.shape,
    )
    significant = np.zeros(labels.shape, dtype=np.bool_)
    significant[9:36, 9:36] = True

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (preceding, terminal),
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert sorted(len(item.component_ids) for item in result.memberships) == [
        1,
        1,
        1,
        2,
    ]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 0
    assert (
        diagnostics.terminal_cycle_missing_child_resilience_candidate_count
        == 1
    )
    assert (
        diagnostics.terminal_cycle_missing_child_resilience_parent_count == 0
    )
    assert (
        diagnostics.terminal_cycle_missing_child_resilience_rejected_count == 1
    )


def test_displaced_child_requires_mutual_uniqueness() -> None:
    """Two corroborated children for one lobe reject the whole parent."""
    labels, records, planes, significant = _displaced_terminal_cycle_fixture(
        ambiguous_first_child=True
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert [len(item.component_ids) for item in result.memberships] == [1] * 4
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 0
    assert diagnostics.rejected_terminal_cycle_count == 1
    assert diagnostics.terminal_persistence_displaced_candidate_count == 5
    assert diagnostics.terminal_persistence_displaced_accepted_count == 3
    assert diagnostics.terminal_persistence_missing_child_count == 0
    assert diagnostics.terminal_persistence_ambiguous_child_count == 1


def test_displaced_evidence_cannot_create_a_terminal_pair() -> None:
    """Mutual displaced children do not turn a nearby pair into a source."""
    terminal_pixels = ((10, 10), (10, 30))
    preceding_pixels = ((9, 9), (9, 31))
    labels, records = _components(terminal_pixels, shape=(41, 41))
    planes = (
        _plane(
            2,
            tuple(
                (f"scale-pair-child-{index}", (pixel,))
                for index, pixel in enumerate(preceding_pixels, start=1)
            ),
            shape=labels.shape,
        ),
        _plane(
            3,
            tuple(
                (f"scale-pair-parent-{index}", (pixel,))
                for index, pixel in enumerate(terminal_pixels, start=1)
            ),
            shape=labels.shape,
        ),
    )
    significant = np.zeros(labels.shape, dtype=np.bool_)
    significant[9:11, 9:11] = True
    significant[9:11, 30:32] = True

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert [len(item.component_ids) for item in result.memberships] == [1, 1]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.terminal_cycle_candidate_count == 0
    assert diagnostics.terminal_persistence_displaced_candidate_count == 0
    assert diagnostics.terminal_persistence_displaced_accepted_count == 0


def test_persistent_unseeded_terminal_feature_accepts_displaced_cycle() -> (
    None
):
    """A uniquely displaced unseeded feature may corroborate geometry."""
    terminal_pixels = ((10, 10), (10, 30), (30, 10), (30, 30))
    preceding_pixels = ((9, 9), (9, 31), (31, 9), (31, 31))
    labels, records = _components(terminal_pixels[:3], shape=(41, 41))
    planes = (
        _plane(
            2,
            tuple(
                (f"scale-unseeded-child-{index}", (pixel,))
                for index, pixel in enumerate(preceding_pixels, start=1)
            ),
            shape=labels.shape,
        ),
        _plane(
            3,
            tuple(
                (f"scale-unseeded-parent-{index}", (pixel,))
                for index, pixel in enumerate(terminal_pixels, start=1)
            ),
            shape=labels.shape,
        ),
    )
    significant = np.zeros(labels.shape, dtype=np.bool_)
    for preceding_pixel, terminal_pixel in zip(
        preceding_pixels,
        terminal_pixels,
        strict=True,
    ):
        significant[
            min(preceding_pixel[0], terminal_pixel[0]) : max(
                preceding_pixel[0], terminal_pixel[0]
            )
            + 1,
            min(preceding_pixel[1], terminal_pixel[1]) : max(
                preceding_pixel[1], terminal_pixel[1]
            )
            + 1,
        ] = True

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert [len(item.component_ids) for item in result.memberships] == [3]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 1
    assert diagnostics.terminal_persistence_displaced_accepted_count == 4
    assert diagnostics.terminal_cycle_unseeded_candidate_count == 1
    assert diagnostics.terminal_cycle_unseeded_persistent_accepted_count == 1


def test_displaced_terminal_parent_cannot_override_partial_group() -> None:
    """A valid displaced cycle cannot absorb members from another parent."""
    terminal_pixels = ((20, 20), (20, 40), (40, 20), (40, 40))
    earlier_cycle_pixels = ((20, 20), (20, 16), (16, 20))
    direct_pixels = (*terminal_pixels, *earlier_cycle_pixels[1:])
    labels, records = _components(direct_pixels, shape=(61, 61))
    fine = _plane(
        1,
        tuple(
            (f"scale-conflicting-fine-{index}", (pixel,))
            for index, pixel in enumerate(earlier_cycle_pixels, start=1)
        ),
        shape=labels.shape,
    )
    preceding_pixels = (
        earlier_cycle_pixels[0],
        earlier_cycle_pixels[1],
        earlier_cycle_pixels[2],
        (19, 41),
        (41, 19),
        (41, 41),
    )
    preceding = _plane(
        2,
        tuple(
            (f"scale-conflicting-child-{index}", (pixel,))
            for index, pixel in enumerate(preceding_pixels, start=1)
        ),
        shape=labels.shape,
    )
    terminal = _plane(
        3,
        tuple(
            (f"scale-conflicting-terminal-{index}", (pixel,))
            for index, pixel in enumerate(terminal_pixels, start=1)
        ),
        shape=labels.shape,
    )
    significant = np.zeros(labels.shape, dtype=np.bool_)
    significant[16:21, 16:21] = True
    for child, parent in zip(
        preceding_pixels[3:],
        terminal_pixels[1:],
        strict=True,
    ):
        significant[
            min(child[0], parent[0]) : max(child[0], parent[0]) + 1,
            min(child[1], parent[1]) : max(child[1], parent[1]) + 1,
        ] = True

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine, preceding, terminal),
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )

    assert sorted(len(item.component_ids) for item in result.memberships) == [
        1,
        1,
        1,
        3,
    ]
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 0
    assert diagnostics.rejected_terminal_cycle_count == 1
    assert diagnostics.terminal_persistence_exact_feature_count == 1
    assert diagnostics.terminal_persistence_displaced_candidate_count == 3
    assert diagnostics.terminal_persistence_displaced_accepted_count == 3
    assert diagnostics.terminal_persistence_conflict_count == 1


def test_missing_child_resilience_reports_final_conflict_rejection() -> None:
    """Resilience telemetry counts only parents surviving reconciliation."""
    incumbent = (
        frozenset(("component-a", "component-b", "component-c")),
        frozenset(("component-d",)),
    )
    resilient_parent = frozenset(
        ("component-a", "component-d", "component-e", "component-f")
    )
    groups, evidence = _apply_terminal_cycle_groups(
        incumbent,
        _TerminalCycleEvidence(
            groups=(resilient_parent,),
            candidate_count=1,
            rejected_count=0,
            missing_child_resilience_candidate_count=1,
            missing_child_resilience_parent_count=1,
            missing_child_resilience_rejected_count=0,
            missing_child_resilience_groups=(resilient_parent,),
        ),
    )

    assert groups == incumbent
    assert evidence.accepted_parent_count == 0
    assert evidence.conflict_count == 1
    assert evidence.missing_child_resilience_parent_count == 0
    assert evidence.missing_child_resilience_rejected_count == 1


def test_transitive_envelope_chain_fails_closed() -> None:
    """Pairwise transitive proximity cannot manufacture a common parent."""
    pixels = tuple((10, x) for x in (4, 14, 24, 34))
    labels, records = _components(pixels, shape=(21, 39))
    middle = _plane(
        2,
        tuple(
            (f"scale-chain-{index}", (pixel,))
            for index, pixel in enumerate(pixels, start=1)
        ),
        shape=labels.shape,
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (middle,),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [1] * 4
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.scale_aware_parent_candidate_count == 0
    assert diagnostics.terminal_persistence_displaced_candidate_count == 0
    assert diagnostics.terminal_persistence_displaced_accepted_count == 0


def test_invalid_gap_blocks_scale_aware_parent_construction() -> None:
    """A complete invalid barrier prevents envelope parent evidence."""
    pixels = ((15, 15), (25, 15), (15, 25), (25, 25))
    labels, records = _components(pixels, shape=(41, 41))
    valid = np.ones(labels.shape, dtype=np.bool_)
    valid[:, 20] = False
    planes = tuple(
        _plane(
            scale_order,
            tuple(
                (f"scale-gap-{scale_order}-{index}", (pixel,))
                for index, pixel in enumerate(pixels, start=1)
            ),
            shape=labels.shape,
        )
        for scale_order in (2, 3)
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        valid,
    )

    assert [len(item.component_ids) for item in result.memberships] == [1] * 4
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.persistent_parent_count == 0


def test_scale_aware_parent_rejects_support_on_an_invalid_pixel() -> None:
    """Scale-feature evidence itself may not occupy invalid support."""
    pixels = ((10, 10), (10, 20), (20, 15))
    labels, records = _components(pixels, shape=(31, 31))
    plane = _plane(
        2,
        tuple(
            (f"scale-invalid-{index}", (pixel,))
            for index, pixel in enumerate(pixels, start=1)
        ),
        shape=labels.shape,
    )
    valid = np.ones(labels.shape, dtype=np.bool_)
    valid[pixels[0]] = False
    labels[pixels[0]] = 0
    records = tuple(record for record in records if record.label_value != 1)

    with pytest.raises(ValueError, match=r"scale support.*valid"):
        associate_components_by_multiscale_hierarchy(
            records,
            labels,
            (plane,),
            valid,
        )


def test_unreviewed_scale_has_no_constructed_parent_envelope() -> None:
    """Scales beyond the fixed three-stage B3 plan remain fail-closed."""
    pixels = ((10, 20), (20, 10), (20, 30), (30, 20))
    labels, records = _components(pixels, shape=(41, 41))
    unreviewed = _plane(
        4,
        tuple(
            (f"scale-unreviewed-{index}", (pixel,))
            for index, pixel in enumerate(pixels, start=1)
        ),
        shape=labels.shape,
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (unreviewed,),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert [len(item.component_ids) for item in result.memberships] == [1] * 4
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.per_scale_parent_candidate_counts == ((4, 0),)


def test_multiple_finest_features_without_convergence_fail_closed() -> None:
    """One direct owner cannot invent a parent for disjoint lineages."""
    labels = np.zeros((7, 11), dtype=np.int32)
    labels[3, 2:9] = 1
    records = build_detection_component_records(
        labels,
        np.asarray(labels > 0, dtype=np.float64),
        np.ones(labels.shape, dtype=np.bool_),
    )
    fine = _plane(
        1,
        (
            ("scale-no-parent-left", ((3, 2), (3, 3))),
            ("scale-no-parent-right", ((3, 7), (3, 8))),
        ),
        shape=labels.shape,
    )

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine,),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert len(result.memberships) == 1
    assert result.ambiguous_component_ids == (records[0].component_id,)
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.multiple_finest_feature_attachment_count == 1
    assert diagnostics.no_common_convergence_count == 1


def test_direct_owner_without_scale_feature_is_counted_as_unattached() -> None:
    """A missing feature remains an observable fail-closed singleton."""
    labels, records = _components(((3, 3),))
    empty = _plane(1, (), shape=labels.shape)

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (empty,),
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert len(result.memberships) == 1
    assert result.ambiguous_component_ids == ()
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.unattached_component_count == 1
    assert diagnostics.per_scale_feature_counts == ((1, 0),)


def test_hierarchy_diagnostics_reject_inconsistent_counts() -> None:
    """Serializable activation evidence cannot drift from its partition."""
    labels, records = _components(((3, 3),))
    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (_plane(1, (("scale-diagnostic", ((3, 3),)),)),),
        np.ones(labels.shape, dtype=np.bool_),
    )
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None

    with pytest.raises(ValueError, match="non-negative"):
        replace(diagnostics, unattached_component_count=-1)
    with pytest.raises(ValueError, match="requires direct"):
        replace(diagnostics, direct_component_count=0)
    with pytest.raises(ValueError, match="requires catalogue"):
        replace(diagnostics, catalogue_source_count=0)
    with pytest.raises(ValueError, match="canonical"):
        replace(diagnostics, membership_size_histogram=((0, 1),))
    with pytest.raises(ValueError, match="count sources"):
        replace(diagnostics, membership_size_histogram=((1, 2),))
    with pytest.raises(ValueError, match="count components"):
        replace(diagnostics, membership_size_histogram=((2, 1),))
    with pytest.raises(ValueError, match="scale counts"):
        replace(diagnostics, per_scale_feature_counts=((1, 1), (1, 1)))
    with pytest.raises(ValueError, match="scale counts"):
        replace(diagnostics, per_scale_feature_counts=((0, 1),))
    with pytest.raises(ValueError, match="exceeds source"):
        replace(diagnostics, unique_convergence_count=2)
    with pytest.raises(ValueError, match="non-negative"):
        replace(diagnostics, rejected_parent_ambiguity_count=-1)
    with pytest.raises(ValueError, match=r"candidate counts.*canonical"):
        replace(
            diagnostics,
            per_scale_parent_candidate_counts=((1, 0), (1, 0)),
        )
    with pytest.raises(ValueError, match=r"candidate scales.*match"):
        replace(diagnostics, per_scale_parent_candidate_counts=((2, 0),))
    with pytest.raises(ValueError, match=r"candidate counts.*match total"):
        replace(diagnostics, scale_aware_parent_candidate_count=1)
    with pytest.raises(ValueError, match="persistent parents exceed"):
        replace(diagnostics, persistent_parent_count=1)
    with pytest.raises(ValueError, match="connected-support outcomes"):
        replace(
            diagnostics,
            rejected_connected_support_ambiguity_count=1,
        )
    with pytest.raises(ValueError, match="terminal-cycle outcomes"):
        replace(
            diagnostics,
            terminal_cycle_parent_count=1,
        )
    with pytest.raises(ValueError, match="displaced persistence"):
        replace(
            diagnostics,
            terminal_persistence_displaced_accepted_count=1,
        )
    with pytest.raises(ValueError, match="conflicts exceed"):
        replace(
            diagnostics,
            terminal_persistence_conflict_count=1,
        )
    with pytest.raises(ValueError, match="exceed pre-eligibility"):
        replace(
            diagnostics,
            terminal_cycle_candidate_count=2,
            terminal_cycle_pre_eligibility_candidate_count=1,
        )
    with pytest.raises(ValueError, match=r"unseeded.*exceed pre-eligibility"):
        replace(
            diagnostics,
            terminal_cycle_pre_eligibility_candidate_count=1,
            terminal_cycle_unseeded_candidate_count=2,
            terminal_cycle_unseeded_persistent_accepted_count=2,
        )
    with pytest.raises(ValueError, match="outcomes must match"):
        replace(
            diagnostics,
            terminal_cycle_pre_eligibility_candidate_count=1,
            terminal_cycle_unseeded_candidate_count=1,
        )
    with pytest.raises(ValueError, match="match association"):
        replace(
            result,
            hierarchy_diagnostics=replace(
                diagnostics,
                direct_component_count=2,
                membership_size_histogram=((2, 1),),
            ),
        )


def test_missing_child_resilience_diagnostics_reject_impossible_counts() -> (
    None
):
    """Accepted or rejected resilient parents cannot exceed candidates."""
    labels, records = _components(((3, 3),))
    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (_plane(1, (("scale-resilience-diagnostic", ((3, 3),)),)),),
        np.ones(labels.shape, dtype=np.bool_),
    )
    diagnostics = result.hierarchy_diagnostics
    assert diagnostics is not None

    with pytest.raises(
        ValueError,
        match="missing-child resilience outcomes exceed candidates",
    ):
        replace(
            diagnostics,
            terminal_cycle_missing_child_resilience_parent_count=1,
        )


def test_hierarchy_is_component_label_and_plane_order_invariant() -> None:
    """Only global component and scale-feature identities affect grouping."""
    pixels = ((4, 3), (4, 8))
    original, records = _components(pixels, labels=(9, 2))
    permuted, permuted_records = _components(pixels, labels=(31, 7))
    fine = _plane(
        1,
        (
            ("scale-noise-left", (pixels[0],)),
            ("scale-noise-right", (pixels[1],)),
        ),
    )
    coarse = _plane(
        2,
        (("scale-noise-parent", tuple((4, x) for x in range(3, 9))),),
    )

    first = associate_components_by_multiscale_hierarchy(
        records,
        original,
        (fine, coarse),
        np.ones(original.shape, dtype=np.bool_),
    )
    second = associate_components_by_multiscale_hierarchy(
        permuted_records,
        permuted,
        (coarse, fine),
        np.ones(permuted.shape, dtype=np.bool_),
    )

    assert first.memberships == second.memberships
    assert first.ambiguous_component_ids == second.ambiguous_component_ids


def test_invalid_gap_and_unparented_crowded_seeds_remain_singletons() -> None:
    """Neither masked gaps nor proximity alone create source membership."""
    pixels = ((3, 3), (3, 5), (3, 7), (3, 9), (3, 11))
    labels, records = _components(pixels)
    fine = _plane(
        1,
        tuple(
            (f"scale-crowded-{index}", (pixel,))
            for index, pixel in enumerate(pixels, start=1)
        ),
    )
    valid = np.ones(labels.shape, dtype=np.bool_)
    valid[:, 6] = False

    result = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        (fine,),
        valid,
    )

    assert len(result.memberships) == len(pixels)
    assert result.ambiguous_component_ids == ()


def test_scale_detection_plane_uses_exact_undilated_support() -> None:
    """The hierarchy adapter retains exact features and physical rankings."""
    support = np.zeros((5, 7), dtype=np.bool_)
    support[0, 1:3] = True
    support[3:5, 5] = True
    response = np.where(support, 2.0, 0.0)
    snr = np.where(support, 6.0, -np.inf)

    plane = build_scale_detection_plane(
        support,
        response,
        snr,
        np.ones(support.shape, dtype=np.bool_),
        scale_order=2,
        nominal_scale_beam_fwhm=2.0,
        origin_yx=(10, 20),
    )

    assert plane.scale_order == 2
    assert len(plane.detections) == 2
    assert tuple(item.canonical_pixel_yx for item in plane.detections) == (
        (10, 21),
        (13, 25),
    )
    assert tuple(item.support_pixel_count for item in plane.detections) == (
        2,
        2,
    )
    assert all(item.peak_signal_to_noise == 6.0 for item in plane.detections)
    assert all(
        item.peak_response_jy_per_beam == 2.0 for item in plane.detections
    )
    assert plane.detections[0].touches_image_edge
    assert plane.detections[1].touches_image_edge


def test_scale_detection_plane_rejects_invalid_support() -> None:
    """Scale features cannot cross invalid pixels or invent rankings."""
    support = np.zeros((3, 3), dtype=np.bool_)
    support[1, 1] = True
    valid = np.ones(support.shape, dtype=np.bool_)
    valid[1, 1] = False

    with pytest.raises(ValueError, match="scientifically valid"):
        build_scale_detection_plane(
            support,
            np.ones(support.shape),
            np.ones(support.shape),
            valid,
            scale_order=1,
            nominal_scale_beam_fwhm=1.0,
        )
