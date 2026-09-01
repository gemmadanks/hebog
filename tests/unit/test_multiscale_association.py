"""Analytic contracts for deterministic Phase 5 scale association."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.multiscale_association import (
    ScaleDetectionPlane,
    associate_adjacent_scale_detections,
    persistent_adjacent_scale_support,
)
from hebog.data_models.multiscale import ScaleDetection


def _plane(
    scale_order: int,
    entries: Sequence[tuple[str, Sequence[tuple[int, int]]]],
    *,
    shape: tuple[int, int] = (8, 8),
    ranking: tuple[float, float, float] = (8.0, 0.002, 1.0),
    origin_yx: tuple[int, int] = (0, 0),
) -> ScaleDetectionPlane:
    """Build one exact-support plane with label-local ordering."""
    labels = np.zeros(shape, dtype=np.int32)
    detections: list[ScaleDetection] = []
    y_origin, x_origin = origin_yx
    peak_signal_to_noise, peak_response, valid_support_fraction = ranking
    for label_value, (detection_id, pixels) in enumerate(entries, start=1):
        ordered_pixels = tuple(sorted(pixels))
        for y_pixel, x_pixel in ordered_pixels:
            labels[y_pixel - y_origin, x_pixel - x_origin] = label_value
        y_pixels = tuple(pixel[0] for pixel in ordered_pixels)
        x_pixels = tuple(pixel[1] for pixel in ordered_pixels)
        detections.append(
            ScaleDetection(
                detection_id=detection_id,
                parent_island_id=None,
                scale_order=scale_order,
                nominal_scale_beam_fwhm=float(2 ** (scale_order - 1)),
                support_pixel_count=len(ordered_pixels),
                valid_support_fraction=valid_support_fraction,
                bounds_yx=(
                    min(y_pixels),
                    max(y_pixels) + 1,
                    min(x_pixels),
                    max(x_pixels) + 1,
                ),
                canonical_pixel_yx=ordered_pixels[0],
                peak_response_jy_per_beam=peak_response,
                peak_signal_to_noise=peak_signal_to_noise,
                touches_image_edge=False,
            )
        )
    return ScaleDetectionPlane(
        scale_order=scale_order,
        component_labels=labels,
        detections=tuple(detections),
        origin_yx=origin_yx,
    )


def test_repeated_detection_over_three_scales_forms_one_association() -> None:
    """Adjacent exact-support edges retain all contributing provenance."""
    common = ((2, 2), (2, 3), (3, 2), (3, 3))
    planes = tuple(
        _plane(
            order,
            ((f"scale-detection-000{order}", common),),
            ranking=(7.0 + order, 0.002, 1.0),
        )
        for order in (1, 2, 3)
    )

    associations = associate_adjacent_scale_detections(planes)

    assert len(associations) == 1
    association = associations[0]
    assert association.scale_detection_ids == (
        "scale-detection-0001",
        "scale-detection-0002",
        "scale-detection-0003",
    )
    assert association.contributing_scale_orders == (1, 2, 3)
    assert association.selected_scale_detection_id == "scale-detection-0003"
    assert association.relationship == "extended-only"
    assert association.compact_source_ids == ()
    assert association.schema_version == 2


def test_persistent_support_excludes_single_scale_features() -> None:
    """Only exact features participating across adjacent scales persist."""
    fine = _plane(
        1,
        (
            ("fine-persistent", ((2, 2), (2, 3))),
            ("fine-single", ((6, 6),)),
        ),
    )
    coarse = _plane(
        2,
        (("coarse-persistent", ((2, 3), (3, 3))),),
    )

    support = persistent_adjacent_scale_support((coarse, fine))

    assert support[2, 2]
    assert support[2, 3]
    assert support[3, 3]
    assert not support[6, 6]
    assert not support.flags.writeable


def test_persistent_support_requires_planes_and_may_be_empty() -> None:
    """Missing planes fail closed and non-overlapping scales return empty."""
    with pytest.raises(ValueError, match="requires a scale detection plane"):
        persistent_adjacent_scale_support(())

    first = _plane(1, (("first", ((1, 1),)),))
    second = _plane(2, (("second", ((6, 6),)),))

    support = persistent_adjacent_scale_support((first, second))

    assert not support.any()


def test_adjacent_coarse_support_can_join_same_scale_fragments() -> None:
    """Same-scale fragments merge only through an adjacent-scale path."""
    fine = _plane(
        1,
        (
            ("scale-detection-left", ((2, 1), (2, 2))),
            ("scale-detection-right", ((2, 4), (2, 5))),
        ),
    )
    bridge = _plane(
        2,
        (
            (
                "scale-detection-bridge",
                ((2, 2), (2, 3), (2, 4)),
            ),
        ),
    )

    associations = associate_adjacent_scale_detections((fine, bridge))

    assert len(associations) == 1
    assert set(associations[0].scale_detection_ids) == {
        "scale-detection-left",
        "scale-detection-right",
        "scale-detection-bridge",
    }


def test_redundant_cross_scale_paths_do_not_duplicate_associations() -> None:
    """A closed overlap cycle remains one canonical graph component."""
    pixels = ((1, 1), (1, 2))
    associations = associate_adjacent_scale_detections(
        (
            _plane(1, (("scale-detection-fine", pixels),)),
            _plane(
                2,
                (
                    ("scale-detection-middle-left", (pixels[0],)),
                    ("scale-detection-middle-right", (pixels[1],)),
                ),
            ),
            _plane(3, (("scale-detection-coarse", pixels),)),
        )
    )

    assert len(associations) == 1
    assert len(associations[0].scale_detection_ids) == 4


def test_without_adjacent_bridge_same_scale_fragments_remain_separate() -> (
    None
):
    """Bounding-box proximity is not association evidence."""
    fine = _plane(
        1,
        (
            ("scale-detection-left", ((2, 1), (2, 2))),
            ("scale-detection-right", ((2, 4), (2, 5))),
        ),
    )
    nonoverlapping = _plane(
        2,
        (("scale-detection-away", ((4, 2), (4, 3), (4, 4))),),
    )

    associations = associate_adjacent_scale_detections((fine, nonoverlapping))

    assert len(associations) == 3
    assert all(len(item.scale_detection_ids) == 1 for item in associations)


def test_nonadjacent_scales_do_not_associate_even_with_exact_overlap() -> None:
    """A skipped configured scale cannot create an association edge."""
    support = ((1, 1), (1, 2))

    associations = associate_adjacent_scale_detections(
        (
            _plane(1, (("scale-detection-fine", support),)),
            _plane(3, (("scale-detection-coarse", support),)),
        )
    )

    assert len(associations) == 2


def test_overlapping_bounds_without_exact_support_do_not_associate() -> None:
    """Bounding boxes cannot join spatially interleaved disjoint supports."""
    associations = associate_adjacent_scale_detections(
        (
            _plane(
                1,
                (("scale-detection-diagonal", ((1, 1), (2, 2))),),
            ),
            _plane(
                2,
                (("scale-detection-antidiagonal", ((1, 2), (2, 1))),),
            ),
        )
    )

    assert len(associations) == 2


def test_associations_are_invariant_to_plane_and_local_label_order() -> None:
    """Task completion and ephemeral component labels cannot change output."""
    fine_entries = (
        ("scale-detection-alpha", ((1, 1), (1, 2))),
        ("scale-detection-beta", ((5, 5), (5, 6))),
    )
    coarse_entries = (
        ("scale-detection-gamma", ((1, 2), (2, 2))),
        ("scale-detection-delta", ((4, 5), (5, 5))),
    )
    first = associate_adjacent_scale_detections(
        (_plane(1, fine_entries), _plane(2, coarse_entries))
    )
    second = associate_adjacent_scale_detections(
        (
            _plane(2, tuple(reversed(coarse_entries))),
            _plane(1, tuple(reversed(fine_entries))),
        )
    )

    assert second == first


def test_equal_scientific_scores_use_finer_scale_representative() -> None:
    """The reviewed representative tie-break is deterministic."""
    support = ((0, 0), (0, 1))

    (association,) = associate_adjacent_scale_detections(
        (
            _plane(1, (("scale-detection-fine", support),)),
            _plane(2, (("scale-detection-coarse", support),)),
        )
    )

    assert association.selected_scale_detection_id == "scale-detection-fine"


@pytest.mark.parametrize(
    (
        "fine_response",
        "coarse_response",
        "fine_support_fraction",
        "coarse_support_fraction",
        "expected",
    ),
    [
        (
            0.001,
            0.002,
            1.0,
            1.0,
            "scale-detection-coarse",
        ),
        (
            0.002,
            0.002,
            0.7,
            0.9,
            "scale-detection-coarse",
        ),
    ],
)
def test_representative_uses_response_then_support_fraction(
    fine_response: float,
    coarse_response: float,
    fine_support_fraction: float,
    coarse_support_fraction: float,
    expected: str,
) -> None:
    """Every scientific representative criterion precedes stable ties."""
    support = ((1, 1), (1, 2))
    (association,) = associate_adjacent_scale_detections(
        (
            _plane(
                1,
                (("scale-detection-fine", support),),
                ranking=(8.0, fine_response, fine_support_fraction),
            ),
            _plane(
                2,
                (("scale-detection-coarse", support),),
                ranking=(8.0, coarse_response, coarse_support_fraction),
            ),
        )
    )

    assert association.selected_scale_detection_id == expected


def test_nonzero_tile_origin_preserves_global_support_geometry() -> None:
    """Global detection bounds are validated against local bounded labels."""
    (association,) = associate_adjacent_scale_detections(
        (
            _plane(
                1,
                (("scale-detection-offset", ((10, 20), (10, 21))),),
                shape=(4, 4),
                origin_yx=(10, 20),
            ),
        )
    )

    assert association.scale_detection_ids == ("scale-detection-offset",)


def test_empty_scale_inputs_have_no_associations() -> None:
    """Scientifically empty bounded work has one canonical empty result."""
    empty_plane = ScaleDetectionPlane(
        scale_order=1,
        component_labels=np.zeros((3, 3), dtype=np.int32),
        detections=(),
    )

    assert associate_adjacent_scale_detections(()) == ()
    assert associate_adjacent_scale_detections((empty_plane,)) == ()


@pytest.mark.parametrize(
    ("scale_order", "labels", "origin", "message"),
    [
        (0, np.zeros((2, 2), dtype=np.int32), (0, 0), "positive"),
        (1, np.zeros(2, dtype=np.int32), (0, 0), "two-dimensional"),
        (1, np.zeros((2, 2), dtype=np.float64), (0, 0), "integers"),
        (1, np.zeros((2, 2), dtype=np.int32), (-1, 0), "non-negative"),
        (1, np.asarray([[-1]], dtype=np.int32), (0, 0), "non-negative"),
        (
            1,
            np.asarray([[2**32]], dtype=np.uint64),
            (0, 0),
            "signed 32-bit",
        ),
    ],
)
def test_scale_plane_rejects_noncanonical_storage(
    scale_order: int,
    labels: object,
    origin: tuple[int, int],
    message: str,
) -> None:
    """Invalid local storage fails before association work begins."""
    with pytest.raises(ValueError, match=message):
        ScaleDetectionPlane(
            scale_order=scale_order,
            component_labels=cast(npt.NDArray[np.int32], labels),
            detections=(),
            origin_yx=origin,
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("shape", "same shape"),
        ("support-count", "support pixel count"),
        ("duplicate-id", "detection IDs must be unique"),
        ("label-coverage", "cover every detection"),
        ("scale-order", "scale order must match"),
        ("bounds", "bounds must match"),
        ("duplicate-scale", "plane orders must be unique"),
        ("origin", "same origin"),
    ],
)
def test_invalid_support_provenance_fails_closed(
    change: str,
    message: str,
) -> None:
    """Contradictory bounded support cannot produce an association."""
    first = _plane(
        1,
        (("scale-detection-shared", ((1, 1), (1, 2))),),
    )
    second = _plane(
        2,
        (("scale-detection-second", ((1, 2), (2, 2))),),
    )
    if change == "shape":
        second = _plane(
            2,
            (("scale-detection-second", ((1, 2), (2, 2))),),
            shape=(9, 8),
        )
    elif change == "support-count":
        changed_detection = second.detections[0].model_copy(
            update={"support_pixel_count": 3}
        )
        second = ScaleDetectionPlane(
            scale_order=2,
            component_labels=second.component_labels,
            detections=(changed_detection,),
        )
    elif change == "duplicate-id":
        second = _plane(
            2,
            (("scale-detection-shared", ((1, 2), (2, 2))),),
        )
    elif change == "label-coverage":
        changed_labels = second.component_labels.copy()
        changed_labels[1, 2] = 2
        second = ScaleDetectionPlane(
            scale_order=2,
            component_labels=changed_labels,
            detections=second.detections,
        )
    elif change == "scale-order":
        changed_detection = second.detections[0].model_copy(
            update={"scale_order": 3}
        )
        second = ScaleDetectionPlane(
            scale_order=2,
            component_labels=second.component_labels,
            detections=(changed_detection,),
        )
    elif change == "bounds":
        changed_detection = second.detections[0].model_copy(
            update={"bounds_yx": (1, 3, 1, 3)}
        )
        second = ScaleDetectionPlane(
            scale_order=2,
            component_labels=second.component_labels,
            detections=(changed_detection,),
        )
    elif change == "duplicate-scale":
        second = _plane(
            1,
            (("scale-detection-second", ((1, 2), (2, 2))),),
        )
    else:
        second = _plane(
            2,
            (("scale-detection-second", ((2, 2), (3, 2))),),
            origin_yx=(1, 0),
        )

    with pytest.raises(ValueError, match=message):
        associate_adjacent_scale_detections((first, second))


def test_canonical_pixel_must_belong_to_exact_support() -> None:
    """A bounding-box-contained but unsupported reference fails closed."""
    plane = _plane(
        1,
        (
            (
                "scale-detection-gap",
                ((1, 1), (1, 2), (2, 1)),
            ),
        ),
    )
    changed_detection = plane.detections[0].model_copy(
        update={"canonical_pixel_yx": (2, 2)}
    )
    changed = ScaleDetectionPlane(
        scale_order=1,
        component_labels=plane.component_labels,
        detections=(changed_detection,),
    )

    with pytest.raises(ValueError, match="canonical pixel"):
        associate_adjacent_scale_detections((changed,))
