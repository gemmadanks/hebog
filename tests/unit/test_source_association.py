"""Analytic contracts for conservative component-to-source association."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from hebog.algorithms.source_association import (
    associate_detection_components,
    build_detection_component_records,
    reduce_source_associations,
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


def _associate(
    labels: np.ndarray,
    records: tuple[DetectionComponentRecord, ...],
    *,
    significant: np.ndarray | None = None,
    combined_snr: np.ndarray | None = None,
):
    """Apply the frozen three-sigma complete-link rule."""
    if significant is None:
        significant = np.ones(labels.shape, dtype=np.bool_)
    if combined_snr is None:
        combined_snr = np.full(labels.shape, 4.0)
    return associate_detection_components(
        records,
        labels,
        significant,
        combined_snr,
        np.ones(labels.shape, dtype=np.bool_),
        island_threshold_sigma=3.0,
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


def test_continuous_broad_components_form_one_catalogue_source() -> None:
    """Supported broad fragments group without modifying owner labels."""
    labels = _labels()
    before = labels.copy()

    result = _associate(labels, _records(labels))

    assert len(result.edges) == 1
    assert len(result.memberships) == 1
    assert len(result.memberships[0].component_ids) == 2
    assert result.memberships[0].source_id.startswith("source-associated-")
    np.testing.assert_array_equal(labels, before)


def test_single_component_forms_one_singleton_source() -> None:
    """A component never disappears merely because no edge is possible."""
    labels = _labels(values=(9,))

    result = _associate(labels, _records(labels))

    assert result.edges == ()
    assert len(result.memberships) == 1
    assert result.memberships[0].component_ids == (
        result.components[0].component_id,
    )


def test_high_dynamic_range_fragments_use_normalized_continuity() -> None:
    """Association is unchanged by a large component-amplitude contrast."""
    labels = _labels()
    signal = np.where(labels == 9, 1000.0, np.where(labels == 2, 1.0, 0.0))
    records = tuple(
        replace(
            record,
            covariance_pixels_squared=((1.0, 0.0), (0.0, 16.0)),
        )
        for record in build_detection_component_records(
            labels,
            signal,
            np.ones(labels.shape, dtype=np.bool_),
        )
    )

    result = _associate(labels, records)

    assert len(result.edges) == 1
    assert len(result.memberships) == 1


def test_filament_fragments_require_directional_extent() -> None:
    """A long transverse axis cannot justify separation along the join."""
    labels = _labels()
    broad_along_join = _records(labels)
    broad_across_join = tuple(
        replace(
            record,
            covariance_pixels_squared=((16.0, 0.0), (0.0, 1.0)),
        )
        for record in broad_along_join
    )

    assert len(_associate(labels, broad_along_join).memberships) == 1
    assert len(_associate(labels, broad_across_join).memberships) == 2


def test_low_saddle_neighbours_remain_distinct() -> None:
    """Distance and broad shapes cannot compensate for weak continuity."""
    labels = _labels()
    combined_snr = np.full(labels.shape, 4.0)
    combined_snr[:, 8] = 2.99

    result = _associate(
        labels,
        _records(labels),
        combined_snr=combined_snr,
    )

    assert result.edges == ()
    assert sorted(len(item.component_ids) for item in result.memberships) == [
        1,
        1,
    ]


def test_disconnected_double_lobes_are_not_a_physical_object_claim() -> None:
    """Disconnected support remains separate despite favourable geometry."""
    labels = _labels()
    significant = labels > 0

    result = _associate(
        labels,
        _records(labels),
        significant=significant,
    )

    assert result.edges == ()
    assert len(result.memberships) == 2


def test_invalid_pixel_breaks_association_continuity() -> None:
    """A mask gap cannot create an association edge."""
    labels = _labels()
    valid = np.ones(labels.shape, dtype=np.bool_)
    valid[:, 8] = False

    result = associate_detection_components(
        _records(labels),
        labels,
        np.ones(labels.shape, dtype=np.bool_),
        np.full(labels.shape, 4.0),
        valid,
        island_threshold_sigma=3.0,
    )

    assert result.edges == ()
    assert len(result.memberships) == 2


def test_unavailable_component_shape_remains_separate() -> None:
    """Association fails closed when either directional size is absent."""
    labels = _labels()
    records = _records(labels)
    records = (replace(records[0], covariance_pixels_squared=None), records[1])

    result = _associate(labels, records)

    assert result.edges == ()
    assert len(result.memberships) == 2


def test_complete_link_rejects_transitive_bridge_chain() -> None:
    """Two local edges cannot merge endpoints lacking their own edge."""
    labels = _labels(values=(9, 2, 14))
    records = _records(labels)

    result = _associate(labels, records)

    assert len(result.edges) == 2
    assert sorted(len(item.component_ids) for item in result.memberships) == [
        1,
        2,
    ]


def test_reducer_is_order_and_duplicate_evidence_invariant() -> None:
    """Executor completion order cannot change source membership."""
    labels = _labels(values=(9, 2, 14))
    records = _records(labels)
    result = _associate(labels, records)

    reversed_result = reduce_source_associations(
        tuple(reversed(records)),
        tuple(reversed(result.edges)) + result.edges,
    )

    assert reversed_result == result


def test_reducer_rejects_disagreeing_or_unknown_edge_evidence() -> None:
    """Retry evidence is idempotent only when its science values agree."""
    labels = _labels()
    records = _records(labels)
    result = _associate(labels, records)
    edge = result.edges[0]
    with pytest.raises(ValueError, match="disagree"):
        reduce_source_associations(
            records,
            (edge, replace(edge, saddle_margin_sigma=2.0)),
        )
    with pytest.raises(ValueError, match="unknown"):
        reduce_source_associations(
            records,
            (
                SourceAssociationEdge(
                    first_component_id=edge.first_component_id,
                    second_component_id="component-unknown",
                    saddle_margin_sigma=1.0,
                    normalized_separation=0.5,
                ),
            ),
        )


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


def test_association_rejects_invalid_planes_threshold_and_origin() -> None:
    """Graph construction requires aligned scientific evidence."""
    labels = _labels(values=(9,))
    records = _records(labels)
    valid = np.ones(labels.shape, dtype=np.bool_)
    with pytest.raises(ValueError, match="labels"):
        _associate(labels.astype(np.float64), records)
    with pytest.raises(ValueError, match="signal"):
        associate_detection_components(
            records,
            labels,
            valid,
            np.ones(labels.shape, dtype=np.complex128),
            valid,
            island_threshold_sigma=3.0,
        )
    with pytest.raises(ValueError, match="significant"):
        associate_detection_components(
            records,
            labels,
            np.ones((2, 2), dtype=np.bool_),
            np.ones(labels.shape),
            valid,
            island_threshold_sigma=3.0,
        )
    with pytest.raises(ValueError, match="threshold"):
        associate_detection_components(
            records,
            labels,
            valid,
            np.ones(labels.shape),
            valid,
            island_threshold_sigma=0.0,
        )
    with pytest.raises(ValueError, match="origin"):
        associate_detection_components(
            records,
            labels,
            valid,
            np.ones(labels.shape),
            valid,
            island_threshold_sigma=3.0,
            origin_yx=(-1, 0),
        )


@pytest.mark.parametrize(
    ("records", "message"),
    [
        ((), "records"),
        (
            (
                DetectionComponentRecord(
                    component_id="component-a",
                    label_value=1,
                    canonical_pixel_yx=(1, 1),
                    centroid_yx=(1.0, 1.0),
                    covariance_pixels_squared=None,
                ),
                DetectionComponentRecord(
                    component_id="component-a",
                    label_value=2,
                    canonical_pixel_yx=(2, 2),
                    centroid_yx=(2.0, 2.0),
                    covariance_pixels_squared=None,
                ),
            ),
            "unique",
        ),
    ],
)
def test_association_rejects_missing_or_ambiguous_component_records(
    records: tuple[DetectionComponentRecord, ...],
    message: str,
) -> None:
    """Every positive owner must have one unambiguous stable record."""
    labels = np.ones((3, 3), dtype=np.int32)

    with pytest.raises(ValueError, match=message):
        _associate(labels, records)
