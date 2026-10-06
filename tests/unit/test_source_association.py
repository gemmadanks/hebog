"""Analytic contracts for conservative component-to-source association."""

from __future__ import annotations

from dataclasses import replace
from itertools import pairwise

import numpy as np
import pytest

from hebog.algorithms.source_association import (
    build_detection_component_record,
    build_detection_component_records,
    constrain_source_memberships,
)
from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationEdge,
    SourceAssociationResult,
)


def _labels(*, values: tuple[int, ...] = (9, 2)) -> np.ndarray:
    """Return separated compact component supports on one bounded plane."""
    labels = np.zeros((9, 25), dtype=np.int32)
    centres = (4, 12, 20)
    for value, centre_x in zip(values, centres[: len(values)], strict=True):
        labels[3:6, centre_x - 1 : centre_x + 2] = value
    return labels


def _records(labels: np.ndarray) -> tuple[DetectionComponentRecord, ...]:
    """Return deliberately broad reviewed component shapes."""
    records = build_detection_component_records(
        labels,
        np.where(labels > 0, 1.0, 0.0),
        np.ones(labels.shape, dtype=np.bool_),
    )
    return tuple(
        replace(
            record,
            covariance_pixels_squared=((1.0, 0.0), (0.0, 16.0)),
        )
        for record in records
    )


def _proposed_association(labels: np.ndarray) -> SourceAssociationResult:
    """Return a hierarchy proposal that joins every component in one source."""
    components = tuple(
        sorted(_records(labels), key=lambda item: item.component_id)
    )
    component_ids = tuple(item.component_id for item in components)
    return SourceAssociationResult(
        components=components,
        edges=tuple(
            SourceAssociationEdge(first, second, 1.0, 0.5)
            for first, second in pairwise(component_ids)
        ),
        memberships=(
            CatalogueSourceMembership("source-proposed", component_ids),
        ),
    )


def test_component_records_are_stable_under_label_permutation() -> None:
    """Local label integers cannot become persistent component identity."""
    labels = _labels()
    permuted = np.where(labels == 9, 7, np.where(labels == 2, 31, 0))
    signal = np.where(labels > 0, 1.0, 0.0)

    original = build_detection_component_records(
        labels,
        signal,
        np.ones(labels.shape, dtype=np.bool_),
    )
    reordered = build_detection_component_records(
        permuted,
        signal,
        np.ones(labels.shape, dtype=np.bool_),
    )

    assert tuple(item.component_id for item in original) == tuple(
        item.component_id for item in reordered
    )
    assert tuple(item.canonical_pixel_yx for item in original) == (
        (3, 3),
        (3, 11),
    )
    assert not original[0].component_labels_are_identity
    with pytest.raises(ValueError, match="canonical pixel"):
        replace(original[0], canonical_pixel_yx=(-1, 0))


def test_compact_constraints_keep_components_and_edges_in_any_order() -> None:
    """A constrained component stands alone; the evidence is unchanged."""
    labels = _labels(values=(9, 2, 31))
    records = _records(labels)
    original = _proposed_association(labels)
    constrained = constrain_source_memberships(original, (frozenset((9,)),))
    singleton = next(
        row.component_id for row in records if row.label_value == 9
    )
    assert (singleton,) in tuple(
        row.component_ids for row in constrained.memberships
    )
    assert constrained.components == original.components
    assert constrained.edges == original.edges
    assert constrain_source_memberships(constrained, ()) == constrained
    order_one = constrain_source_memberships(
        original,
        (frozenset((9,)), frozenset((2, 31))),
    )
    order_two = constrain_source_memberships(
        original,
        (frozenset((31, 2)), frozenset((9,))),
    )
    assert order_one == order_two


def test_unconstrained_hierarchy_remainder_does_not_merge_components() -> None:
    """Missing compact/morphology evidence cannot identify independent rows."""
    labels = _labels(values=(9, 2, 31))
    original = _proposed_association(labels)
    assert len(original.memberships) < len(original.components)
    result = constrain_source_memberships(original, (frozenset((31,)),))
    assert {row.component_ids for row in result.memberships} == {
        (component.component_id,) for component in original.components
    }


@pytest.mark.parametrize(
    "groups",
    (
        (frozenset[int](),),
        (frozenset((9,)), frozenset((9,))),
        (frozenset((999,)),),
    ),
)
def test_compact_constraints_reject_invalid_component_claims(
    groups: tuple[frozenset[int], ...],
) -> None:
    """A constraint group is nonempty, disjoint and names known labels."""
    labels = _labels()
    with pytest.raises(ValueError, match="compact model group"):
        constrain_source_memberships(_proposed_association(labels), groups)


def test_association_models_reject_noncanonical_scientific_records() -> None:
    """Array-free evidence fails closed before it can cross executors."""
    component = DetectionComponentRecord(
        component_id="component-a",
        label_value=1,
        canonical_pixel_yx=(1, 1),
        centroid_yx=(1.0, 1.0),
        covariance_pixels_squared=((1.0, 0.0), (0.0, 1.0)),
    )
    with pytest.raises(ValueError, match="canonical domain"):
        replace(component, component_id="Component A")
    with pytest.raises(ValueError, match="label value"):
        replace(component, label_value=0)
    with pytest.raises(ValueError, match="centroid"):
        replace(component, centroid_yx=(float("inf"), 1.0))
    with pytest.raises(ValueError, match="positive definite"):
        replace(
            component,
            covariance_pixels_squared=((1.0, 1.0), (0.0, 1.0)),
        )

    with pytest.raises(ValueError, match="ordered"):
        SourceAssociationEdge("component-b", "component-a", 1.0, 0.5)
    with pytest.raises(ValueError, match="saddle"):
        SourceAssociationEdge("component-a", "component-b", -1.0, 0.5)
    with pytest.raises(ValueError, match="separation"):
        SourceAssociationEdge("component-a", "component-b", 1.0, 1.1)
    with pytest.raises(ValueError, match="canonical"):
        CatalogueSourceMembership("source-a", ("component-b", "component-a"))

    membership = CatalogueSourceMembership("source-a", ("component-a",))
    with pytest.raises(ValueError, match="unknown"):
        SourceAssociationResult(
            components=(component,),
            edges=(
                SourceAssociationEdge(
                    "component-a",
                    "component-b",
                    1.0,
                    0.5,
                ),
            ),
            memberships=(membership,),
        )
    with pytest.raises(ValueError, match="partition"):
        SourceAssociationResult(
            components=(component,),
            edges=(),
            memberships=(),
        )


def test_component_geometry_does_not_depend_on_the_plane_around_it() -> None:
    """The same component measured in a bigger plane gives the same record.

    Component geometry is computed in the image's pixel frame, so padding
    the plane and moving the tile origin to match changes which pixels are
    visited and nothing about the result. This is what lets each component
    be measured in its own window instead of over the whole image.
    """
    generator = np.random.default_rng(2026091904)
    labels = np.zeros((12, 15), dtype=np.int32)
    labels[3:8, 4:11] = np.where(generator.random((5, 7)) < 0.85, 5, 0)
    labels[3, 4] = 5
    signal = generator.uniform(0.1, 2.0, labels.shape)

    tight = build_detection_component_records(
        labels,
        signal,
        np.ones(labels.shape, dtype=np.bool_),
        origin_yx=(40, 70),
    )

    padded_labels = np.zeros((30, 40), dtype=np.int32)
    padded_signal = np.zeros(padded_labels.shape, dtype=np.float64)
    padded_labels[9:21, 6:21] = labels
    padded_signal[9:21, 6:21] = signal
    padded = build_detection_component_records(
        padded_labels,
        padded_signal,
        np.ones(padded_labels.shape, dtype=np.bool_),
        origin_yx=(31, 64),
    )

    assert len(tight) == 1
    assert padded[0].centroid_yx == tight[0].centroid_yx
    assert padded[0].covariance_pixels_squared == (
        tight[0].covariance_pixels_squared
    )
    assert padded[0].canonical_pixel_yx == tight[0].canonical_pixel_yx


def test_one_component_described_from_its_pixels_matches_its_window() -> None:
    """Pixels restored to raster order describe a component bit for bit.

    A component too wide to read at once is described from the pixels each
    core returns. The fixture covers a covariance, a centroid with too few
    positive pixels for one, and a component with no positive signal at all,
    whose centroid is the mean of its support.
    """
    rng = np.random.default_rng(20260926)
    labels = np.zeros((23, 31), dtype=np.int32)
    labels[2:9, 3:14] = 1
    labels[12:14, 20:22] = 2
    labels[15:21, 2:9] = 3
    signal = rng.normal(0.3, 1.0, labels.shape)
    signal[12:14, 20:22] = (-1.0, 2.0)
    signal[15:21, 2:9] = -0.5
    signal[4, 5] = np.nan
    origin_yx = (40, 7)
    width = 100

    expected = build_detection_component_records(
        labels,
        signal,
        np.ones(labels.shape, dtype=np.bool_),
        origin_yx=origin_yx,
    )
    described: list[DetectionComponentRecord] = []
    for label_value in (1, 2, 3):
        rows, columns = np.nonzero(labels == label_value)
        described.append(
            build_detection_component_record(
                label_value,
                (rows + origin_yx[0]) * width + columns + origin_yx[1],
                signal[rows, columns],
                image_width=width,
            )
        )

    assert tuple(
        sorted(described, key=lambda item: item.canonical_pixel_yx)
    ) == (expected)
    assert {
        record.label_value: record.covariance_pixels_squared is None
        for record in expected
    } == {1: False, 2: True, 3: True}


@pytest.mark.parametrize(
    ("raster_indices", "signal", "message"),
    (
        ((), (), "non-empty"),
        ((3, 4), (1.0,), "aligned"),
        ((4, 3), (1.0, 1.0), "ascending raster order"),
        ((3, 3), (1.0, 1.0), "ascending raster order"),
    ),
    ids=("empty", "misaligned", "descending", "repeated"),
)
def test_a_component_described_from_pixels_needs_them_all_in_order(
    raster_indices: tuple[int, ...], signal: tuple[float, ...], message: str
) -> None:
    """Pixels out of raster order would name the wrong first pixel."""
    with pytest.raises(ValueError, match=message):
        build_detection_component_record(
            1,
            np.asarray(raster_indices, dtype=np.int64),
            np.asarray(signal, dtype=np.float64),
            image_width=10,
        )
