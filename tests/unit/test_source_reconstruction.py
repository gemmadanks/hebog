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
    with pytest.raises(ValueError, match="match association"):
        replace(
            result,
            hierarchy_diagnostics=replace(
                diagnostics,
                direct_component_count=2,
                membership_size_histogram=((2, 1),),
            ),
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
