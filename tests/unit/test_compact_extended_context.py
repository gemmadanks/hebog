"""Analytic contracts for compact/extended spatial context."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.multiscale_association import (
    CompactSourcePlane,
    ScaleDetectionPlane,
    associate_adjacent_scale_detections,
    associate_compact_source_context,
)
from hebog.data_models.multiscale import (
    CompactSourceSupport,
    ScaleDetection,
)


def _scale_plane(
    scale_order: int,
    entries: Sequence[tuple[str, Sequence[tuple[int, int]]]],
    *,
    shape: tuple[int, int] = (9, 10),
    origin_yx: tuple[int, int] = (0, 0),
) -> ScaleDetectionPlane:
    """Build one bounded exact-support scale plane."""
    labels = np.zeros(shape, dtype=np.int32)
    detections: list[ScaleDetection] = []
    y_origin, x_origin = origin_yx
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
                valid_support_fraction=1.0,
                bounds_yx=(
                    min(y_pixels),
                    max(y_pixels) + 1,
                    min(x_pixels),
                    max(x_pixels) + 1,
                ),
                canonical_pixel_yx=ordered_pixels[0],
                peak_response_jy_per_beam=0.002,
                peak_signal_to_noise=8.0,
                touches_image_edge=False,
            )
        )
    return ScaleDetectionPlane(
        scale_order=scale_order,
        component_labels=labels,
        detections=tuple(detections),
        origin_yx=origin_yx,
    )


def _compact_plane(
    entries: Sequence[
        tuple[
            str,
            str,
            Sequence[tuple[int, int]],
            tuple[float, float],
        ]
    ],
    *,
    shape: tuple[int, int] = (9, 10),
    origin_yx: tuple[int, int] = (0, 0),
) -> CompactSourcePlane:
    """Build one bounded exact-support compact-source plane."""
    labels = np.zeros(shape, dtype=np.int32)
    sources: list[CompactSourceSupport] = []
    y_origin, x_origin = origin_yx
    for label_value, (
        source_id,
        island_id,
        pixels,
        reference_position_yx,
    ) in enumerate(entries, start=1):
        ordered_pixels = tuple(sorted(pixels))
        for y_pixel, x_pixel in ordered_pixels:
            labels[y_pixel - y_origin, x_pixel - x_origin] = label_value
        y_pixels = tuple(pixel[0] for pixel in ordered_pixels)
        x_pixels = tuple(pixel[1] for pixel in ordered_pixels)
        sources.append(
            CompactSourceSupport(
                source_id=source_id,
                island_id=island_id,
                support_pixel_count=len(ordered_pixels),
                bounds_yx=(
                    min(y_pixels),
                    max(y_pixels) + 1,
                    min(x_pixels),
                    max(x_pixels) + 1,
                ),
                reference_position_yx=reference_position_yx,
                gaussian_component_ids=(f"gaussian-{source_id}",),
            )
        )
    return CompactSourcePlane(
        source_labels=labels,
        sources=tuple(sources),
        origin_yx=origin_yx,
    )


def _associate(
    planes: tuple[ScaleDetectionPlane, ...],
    compact_plane: CompactSourcePlane,
    *,
    beam_major_fwhm_pixels: float = 4.0,
):
    """Run both deterministic association stages."""
    associations = associate_adjacent_scale_detections(planes)
    return associate_compact_source_context(
        planes,
        associations,
        compact_plane,
        beam_major_fwhm_pixels=beam_major_fwhm_pixels,
    )


def test_extended_fragments_merge_while_compact_sources_remain_distinct() -> (
    None
):
    """One extended association may contain several separate source IDs."""
    fine = _scale_plane(
        1,
        (
            ("scale-detection-left", ((3, 2),)),
            ("scale-detection-right", ((3, 6),)),
        ),
    )
    coarse = _scale_plane(
        2,
        (
            (
                "scale-detection-bridge",
                ((3, 2), (3, 3), (3, 4), (3, 5), (3, 6)),
            ),
        ),
    )
    compact = _compact_plane(
        (
            (
                "source-compact-left",
                "island-compact-shared",
                ((3, 3),),
                (3.0, 3.0),
            ),
            (
                "source-compact-right",
                "island-compact-shared",
                ((3, 5),),
                (3.0, 5.0),
            ),
        )
    )

    context = _associate((fine, coarse), compact)

    assert len(context.associations) == 1
    association = context.associations[0]
    assert len(association.scale_detection_ids) == 3
    assert association.compact_source_ids == (
        "source-compact-left",
        "source-compact-right",
    )
    assert association.relationship == "contains-compact-support"
    assert tuple(edge.compact_source_id for edge in context.edges) == (
        "source-compact-left",
        "source-compact-right",
    )
    assert all(
        edge.relationship == "contains-compact-support"
        for edge in context.edges
    )


def test_one_compact_source_can_contextualize_separate_extended_sources() -> (
    None
):
    """Many-to-many context never merges distinct extended identities."""
    scale = _scale_plane(
        1,
        (
            ("scale-detection-left", ((4, 2),)),
            ("scale-detection-right", ((4, 6),)),
        ),
    )
    compact = _compact_plane(
        (
            (
                "source-compact-middle",
                "island-compact-middle",
                ((4, 4),),
                (4.0, 4.0),
            ),
        )
    )

    context = _associate((scale,), compact)

    assert len(context.associations) == 2
    assert len({item.association_id for item in context.associations}) == 2
    assert all(
        item.compact_source_ids == ("source-compact-middle",)
        for item in context.associations
    )
    assert all(
        item.relationship == "overlaps-compact-support"
        for item in context.associations
    )
    assert len(context.edges) == 2


def test_exact_overlap_is_spatial_not_a_physical_host_claim() -> None:
    """Overlap without a contained reference retains projected context."""
    scale = _scale_plane(
        1,
        (("scale-detection-projection", ((2, 2), (2, 3))),),
    )
    compact = _compact_plane(
        (
            (
                "source-compact-projection",
                "island-compact-projection",
                ((2, 3), (2, 4)),
                (2.0, 4.0),
            ),
        )
    )

    context = _associate((scale,), compact, beam_major_fwhm_pixels=2.0)

    assert context.associations[0].relationship == ("overlaps-compact-support")
    assert context.edges[0].relationship == "overlaps-compact-support"


def test_mixed_per_source_context_retains_exact_edge_relationships() -> None:
    """One aggregate overlap does not erase individual containment evidence."""
    scale = _scale_plane(
        1,
        (
            (
                "scale-detection-mixed",
                ((2, 2), (2, 3), (2, 4), (2, 5)),
            ),
        ),
    )
    compact = _compact_plane(
        (
            (
                "source-contained",
                "island-contained",
                ((2, 2),),
                (2.0, 2.0),
            ),
            (
                "source-overlapping",
                "island-overlapping",
                ((2, 5), (2, 6)),
                (2.0, 6.0),
            ),
        )
    )

    context = _associate((scale,), compact)

    assert context.associations[0].relationship == ("overlaps-compact-support")
    assert tuple(edge.relationship for edge in context.edges) == (
        "contains-compact-support",
        "overlaps-compact-support",
    )


def test_half_beam_context_is_bounded_and_does_not_grow_science_support() -> (
    None
):
    """Only the reviewed half-beam dilation creates adjacency evidence."""
    scale = _scale_plane(
        1,
        (("scale-detection-adjacent", ((4, 2),)),),
    )
    nearby = _compact_plane(
        (
            (
                "source-nearby",
                "island-nearby",
                ((4, 4),),
                (4.0, 4.0),
            ),
        )
    )
    distant = _compact_plane(
        (
            (
                "source-distant",
                "island-distant",
                ((4, 5),),
                (4.0, 5.0),
            ),
        )
    )

    adjacent_context = _associate((scale,), nearby)
    distant_context = _associate((scale,), distant)

    assert adjacent_context.edges[0].relationship == (
        "overlaps-compact-support"
    )
    assert distant_context.edges == ()
    assert distant_context.associations[0].relationship == "extended-only"
    assert scale.component_labels[4, 2] == 1
    assert np.count_nonzero(scale.component_labels) == 1


def test_compact_context_is_invariant_to_input_and_local_label_order() -> None:
    """Stable edge evidence does not depend on bounded task ordering."""
    scale_entries = (
        ("scale-detection-alpha", ((1, 1),)),
        ("scale-detection-beta", ((6, 7),)),
    )
    compact_entries = (
        (
            "source-alpha",
            "island-alpha",
            ((1, 2),),
            (1.0, 2.0),
        ),
        (
            "source-beta",
            "island-beta",
            ((6, 6),),
            (6.0, 6.0),
        ),
    )
    first_scale = _scale_plane(1, scale_entries)
    second_scale = _scale_plane(1, tuple(reversed(scale_entries)))
    first_associations = associate_adjacent_scale_detections((first_scale,))
    second_associations = tuple(
        reversed(associate_adjacent_scale_detections((second_scale,)))
    )

    first = associate_compact_source_context(
        (first_scale,),
        first_associations,
        _compact_plane(compact_entries),
        beam_major_fwhm_pixels=4.0,
    )
    second = associate_compact_source_context(
        (second_scale,),
        second_associations,
        _compact_plane(tuple(reversed(compact_entries))),
        beam_major_fwhm_pixels=4.0,
    )

    assert second == first


def test_compact_context_uses_global_coordinates_on_shifted_tile_edge() -> (
    None
):
    """A nonzero bounded origin cannot change edge adjacency evidence."""
    scale = _scale_plane(
        1,
        (("scale-detection-offset", ((10, 20),)),),
        shape=(4, 5),
        origin_yx=(10, 20),
    )
    compact = _compact_plane(
        (
            (
                "source-offset",
                "island-offset",
                ((10, 21),),
                (10.0, 21.0),
            ),
        ),
        shape=(4, 5),
        origin_yx=(10, 20),
    )

    context = _associate(
        (scale,),
        compact,
        beam_major_fwhm_pixels=2.0,
    )

    assert context.edges[0].compact_source_id == "source-offset"
    assert context.edges[0].relationship == "overlaps-compact-support"


def test_conflicting_extended_support_ownership_fails_closed() -> None:
    """Non-adjacent exact overlap cannot be resolved by stable ID order."""
    support = ((3, 3),)
    planes = (
        _scale_plane(1, (("scale-detection-fine", support),)),
        _scale_plane(3, (("scale-detection-coarse", support),)),
    )
    associations = associate_adjacent_scale_detections(planes)

    with pytest.raises(ValueError, match="conflicting exact support"):
        associate_compact_source_context(
            planes,
            associations,
            _compact_plane(()),
            beam_major_fwhm_pixels=4.0,
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("missing-detection", "claim every scale detection"),
        ("duplicate-detection", "claimed by one association"),
        ("duplicate-association", "association IDs must be unique"),
        ("unknown-detection", "unknown scale detection"),
        ("wrong-orders", "contributing scale orders"),
        ("precontextualized", "must be extended-only"),
    ],
)
def test_contradictory_association_provenance_fails_closed(
    change: str,
    message: str,
) -> None:
    """Compact context accepts only a complete unambiguous scale graph."""
    scale = _scale_plane(
        1,
        (
            ("scale-detection-alpha", ((1, 1),)),
            ("scale-detection-beta", ((6, 7),)),
        ),
    )
    associations = list(associate_adjacent_scale_detections((scale,)))
    if change == "missing-detection":
        associations.pop()
    elif change == "duplicate-detection":
        associations[1] = associations[1].model_copy(
            update={
                "scale_detection_ids": associations[0].scale_detection_ids,
                "selected_scale_detection_id": (
                    associations[0].selected_scale_detection_id
                ),
            }
        )
    elif change == "duplicate-association":
        associations[1] = associations[1].model_copy(
            update={"association_id": associations[0].association_id}
        )
    elif change == "unknown-detection":
        associations[0] = associations[0].model_copy(
            update={
                "scale_detection_ids": ("scale-detection-unknown",),
                "selected_scale_detection_id": "scale-detection-unknown",
            }
        )
    elif change == "wrong-orders":
        associations[0] = associations[0].model_copy(
            update={"contributing_scale_orders": (2,)}
        )
    else:
        associations[0] = associations[0].model_copy(
            update={
                "compact_source_ids": ("source-existing",),
                "relationship": "contains-compact-support",
            }
        )

    with pytest.raises(ValueError, match=message):
        associate_compact_source_context(
            (scale,),
            tuple(associations),
            _compact_plane(()),
            beam_major_fwhm_pixels=4.0,
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("shape", "same shape"),
        ("origin", "same origin"),
        ("count", "support pixel count"),
        ("bounds", "bounds must match"),
        ("label-coverage", "cover every source"),
        ("duplicate-source", "source IDs must be unique"),
        ("reference", "reference position must be within"),
    ],
)
def test_invalid_compact_support_provenance_fails_closed(
    change: str,
    message: str,
) -> None:
    """Exact compact supports and reference positions are governed inputs."""
    scale = _scale_plane(
        1,
        (("scale-detection-alpha", ((2, 2),)),),
    )
    associations = associate_adjacent_scale_detections((scale,))
    compact = _compact_plane(
        (
            (
                "source-alpha",
                "island-alpha",
                ((2, 3),),
                (2.0, 3.0),
            ),
        )
    )
    if change == "shape":
        compact = _compact_plane(
            (
                (
                    "source-alpha",
                    "island-alpha",
                    ((2, 3),),
                    (2.0, 3.0),
                ),
            ),
            shape=(10, 10),
        )
    elif change == "origin":
        compact = _compact_plane(
            (
                (
                    "source-alpha",
                    "island-alpha",
                    ((3, 4),),
                    (3.0, 4.0),
                ),
            ),
            shape=(9, 10),
            origin_yx=(1, 1),
        )
    elif change == "count":
        compact = CompactSourcePlane(
            source_labels=compact.source_labels,
            sources=(
                compact.sources[0].model_copy(
                    update={"support_pixel_count": 2}
                ),
            ),
        )
    elif change == "bounds":
        compact = CompactSourcePlane(
            source_labels=compact.source_labels,
            sources=(
                compact.sources[0].model_copy(
                    update={"bounds_yx": (2, 4, 3, 4)}
                ),
            ),
        )
    elif change == "label-coverage":
        compact = CompactSourcePlane(
            source_labels=np.zeros(
                compact.source_labels.shape, dtype=np.int32
            ),
            sources=compact.sources,
        )
    elif change == "duplicate-source":
        labels = compact.source_labels.copy()
        labels[4, 4] = 2
        duplicate = compact.sources[0].model_copy(
            update={
                "support_pixel_count": 1,
                "bounds_yx": (4, 5, 4, 5),
                "reference_position_yx": (4.0, 4.0),
            }
        )
        compact = CompactSourcePlane(
            source_labels=labels,
            sources=(compact.sources[0], duplicate),
        )
    elif change == "reference":
        compact = CompactSourcePlane(
            source_labels=compact.source_labels,
            sources=(
                compact.sources[0].model_copy(
                    update={"reference_position_yx": (30.0, 30.0)}
                ),
            ),
        )

    with pytest.raises(ValueError, match=message):
        associate_compact_source_context(
            (scale,),
            associations,
            compact,
            beam_major_fwhm_pixels=4.0,
        )


@pytest.mark.parametrize(
    ("labels", "origin", "message"),
    [
        (np.zeros(3, dtype=np.int32), (0, 0), "two-dimensional"),
        (np.zeros((2, 2), dtype=np.float64), (0, 0), "integers"),
        (np.asarray([[-1]], dtype=np.int32), (0, 0), "non-negative"),
        (np.zeros((2, 2), dtype=np.int32), (-1, 0), "non-negative"),
        (
            np.asarray([[2**32]], dtype=np.uint64),
            (0, 0),
            "signed 32-bit",
        ),
    ],
)
def test_compact_plane_rejects_noncanonical_storage(
    labels: object,
    origin: tuple[int, int],
    message: str,
) -> None:
    """Invalid bounded storage fails before association work begins."""
    with pytest.raises(ValueError, match=message):
        CompactSourcePlane(
            source_labels=cast(npt.NDArray[np.int32], labels),
            sources=(),
            origin_yx=origin,
        )


@pytest.mark.parametrize("beam", [0.0, np.nan, np.inf, True])
def test_context_requires_a_finite_positive_beam(beam: object) -> None:
    """Adjacency must have explicit valid beam geometry."""
    scale = _scale_plane(
        1,
        (("scale-detection-alpha", ((2, 2),)),),
    )
    associations = associate_adjacent_scale_detections((scale,))

    with pytest.raises(ValueError, match="beam major FWHM"):
        associate_compact_source_context(
            (scale,),
            associations,
            _compact_plane(()),
            beam_major_fwhm_pixels=cast(float, beam),
        )


def test_empty_context_has_no_edges_and_does_not_mutate_inputs() -> None:
    """Empty compact evidence preserves extended-only associations exactly."""
    scale = _scale_plane(
        1,
        (("scale-detection-alpha", ((2, 2),)),),
    )
    associations = associate_adjacent_scale_detections((scale,))

    context = associate_compact_source_context(
        (scale,),
        associations,
        _compact_plane(()),
        beam_major_fwhm_pixels=4.0,
    )

    assert context.associations == associations
    assert context.edges == ()


def test_empty_scale_context_is_canonical_and_rejects_orphan_association() -> (
    None
):
    """No-scale work is empty, while a scale-free association is invalid."""
    compact = _compact_plane(())

    context = associate_compact_source_context(
        (),
        (),
        compact,
        beam_major_fwhm_pixels=4.0,
    )

    assert context.associations == ()
    assert context.edges == ()

    scale = _scale_plane(
        1,
        (("scale-detection-orphan", ((2, 2),)),),
    )
    associations = associate_adjacent_scale_detections((scale,))
    with pytest.raises(ValueError, match="require scale detection planes"):
        associate_compact_source_context(
            (),
            associations,
            compact,
            beam_major_fwhm_pixels=4.0,
        )


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"bounds_yx": (-1, 1, 0, 1)}, "bounds must be increasing"),
        ({"bounds_yx": (1, 1, 0, 1)}, "bounds must be increasing"),
        (
            {"reference_position_yx": (np.nan, 0.0)},
            "reference position must be finite",
        ),
        (
            {"reference_position_yx": (-0.6, 0.0)},
            "reference position must be finite",
        ),
    ],
)
def test_compact_source_support_rejects_invalid_geometry(
    update: dict[str, object],
    message: str,
) -> None:
    """The scheduler-safe compact input cannot carry ambiguous geometry."""
    fields: dict[str, object] = {
        "source_id": "source-alpha",
        "island_id": "island-alpha",
        "support_pixel_count": 1,
        "bounds_yx": (0, 1, 0, 1),
        "reference_position_yx": (0.0, 0.0),
        "gaussian_component_ids": ("gaussian-alpha",),
    }
    fields.update(update)

    with pytest.raises(ValueError, match=message):
        CompactSourceSupport.model_validate(fields)
