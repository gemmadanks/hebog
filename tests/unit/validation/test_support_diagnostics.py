from __future__ import annotations

import numpy as np
import pytest

from hebog.validation.support_diagnostics import (
    compare_support_component,
    rank_reference_support_disagreements,
    summarize_support_component_evidence,
    summarize_support_pixels,
)


def _label_planes() -> tuple[np.ndarray, np.ndarray]:
    reference = np.asarray(
        [
            [0, 7, 7, 0],
            [0, 7, 7, 0],
            [0, 7, 0, 9],
        ],
        dtype=np.int32,
    )
    candidate = np.asarray(
        [
            [0, 2, 5, 0],
            [0, 2, 5, 0],
            [0, 0, 5, 8],
        ],
        dtype=np.int32,
    )
    return candidate, reference


def test_compare_support_component_reports_fragmented_overlap() -> None:
    candidate, reference = _label_planes()

    comparison = compare_support_component(candidate, reference, 7)

    assert comparison.summary.reference_label == 7
    assert comparison.summary.candidate_labels == (2, 5)
    assert comparison.summary.fragment_count == 2
    assert comparison.summary.reference_pixel_count == 5
    assert comparison.summary.candidate_pixel_count == 5
    assert comparison.summary.intersection_pixel_count == 4
    assert comparison.summary.reference_only_pixel_count == 1
    assert comparison.summary.candidate_only_pixel_count == 1
    assert comparison.summary.precision == pytest.approx(0.8)
    assert comparison.summary.recall == pytest.approx(0.8)
    assert comparison.summary.intersection_over_union == pytest.approx(2 / 3)
    assert comparison.bounds_yx_half_open == (0, 3, 1, 3)


def test_rank_reference_disagreements_prioritizes_fragmentation() -> None:
    candidate, reference = _label_planes()

    ranked = rank_reference_support_disagreements(candidate, reference)

    assert [item.reference_label for item in ranked] == [7, 9]
    assert ranked[0].candidate_labels == (2, 5)
    assert ranked[1].candidate_labels == (8,)


def test_compare_support_component_reports_unmatched_reference() -> None:
    candidate = np.zeros((2, 3), dtype=np.int16)
    reference = np.asarray([[0, 4, 4], [0, 4, 0]], dtype=np.int16)

    comparison = compare_support_component(candidate, reference, 4)

    assert comparison.summary.candidate_labels == ()
    assert comparison.summary.candidate_pixel_count == 0
    assert comparison.summary.reference_only_pixel_count == 3
    assert comparison.summary.precision is None
    assert comparison.summary.recall == 0.0
    assert comparison.summary.intersection_over_union == 0.0
    assert comparison.bounds_yx_half_open == (0, 2, 1, 3)


def test_summarize_support_component_evidence_separates_pixel_roles() -> None:
    candidate, reference = _label_planes()
    comparison = compare_support_component(candidate, reference, 7)
    background = np.ones(reference.shape, dtype=np.float64)
    rms = np.ones(reference.shape, dtype=np.float64)
    residual = np.asarray(
        [
            [0.0, 3.0, 4.0, 0.0],
            [0.0, 5.0, 6.0, 0.0],
            [0.0, 2.0, 10.0, 0.0],
        ]
    )
    image = background + residual

    evidence = summarize_support_component_evidence(
        comparison,
        candidate,
        reference,
        image=image,
        background=background,
        rms=rms,
        beam_area_pixels=2.0,
    )

    assert evidence.common.pixel_count == 4
    assert evidence.common.valid_pixel_count == 4
    assert evidence.common.residual_flux_jy == pytest.approx(9.0)
    assert evidence.common.direct_snr_median == pytest.approx(4.5)
    assert evidence.common.at_least_3_sigma_pixel_count == 4
    assert evidence.common.at_least_5_sigma_pixel_count == 2
    assert evidence.reference_only.pixel_count == 1
    assert evidence.reference_only.raw_flux_jy == pytest.approx(1.5)
    assert evidence.reference_only.background_flux_jy == pytest.approx(0.5)
    assert evidence.reference_only.residual_flux_jy == pytest.approx(1.0)
    assert evidence.reference_only.direct_snr_median == pytest.approx(2.0)
    assert evidence.candidate_only.pixel_count == 1
    assert evidence.candidate_only.direct_snr_maximum == pytest.approx(10.0)


@pytest.mark.parametrize(
    ("candidate", "reference", "message"),
    [
        (
            np.zeros((2, 2), dtype=np.int16),
            np.zeros((3, 2), dtype=np.int16),
            "same shape",
        ),
        (
            np.zeros(2, dtype=np.int16),
            np.zeros(2, dtype=np.int16),
            "two-dimensional",
        ),
        (
            np.zeros((2, 2), dtype=np.float64),
            np.zeros((2, 2), dtype=np.int16),
            "integer label",
        ),
        (
            np.asarray([[0, -1], [0, 0]], dtype=np.int16),
            np.zeros((2, 2), dtype=np.int16),
            "non-negative",
        ),
    ],
)
def test_compare_support_component_rejects_invalid_label_planes(
    candidate: np.ndarray,
    reference: np.ndarray,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        compare_support_component(candidate, reference, 1)


def test_compare_support_component_rejects_missing_reference_label() -> None:
    candidate, reference = _label_planes()

    with pytest.raises(ValueError, match="reference label 12 is absent"):
        compare_support_component(candidate, reference, 12)


def test_compare_support_component_rejects_nonpositive_reference_label() -> (
    None
):
    candidate, reference = _label_planes()

    with pytest.raises(ValueError, match="reference_label must be positive"):
        compare_support_component(candidate, reference, 0)


def test_rank_reference_disagreements_handles_empty_and_disjoint_planes() -> (
    None
):
    empty = np.zeros((2, 3), dtype=np.int16)
    assert rank_reference_support_disagreements(empty, empty) == ()

    candidate = np.asarray([[3, 0, 0], [0, 0, 0]], dtype=np.int16)
    reference = np.asarray([[0, 0, 0], [0, 4, 4]], dtype=np.int16)
    ranked = rank_reference_support_disagreements(candidate, reference)

    assert len(ranked) == 1
    assert ranked[0].reference_label == 4
    assert ranked[0].candidate_labels == ()
    assert ranked[0].recall == 0.0


def test_evidence_rejects_invalid_beam_area_and_plane_shape() -> None:
    candidate, reference = _label_planes()
    comparison = compare_support_component(candidate, reference, 7)
    plane = np.ones(reference.shape, dtype=np.float64)

    with pytest.raises(ValueError, match="beam_area_pixels"):
        summarize_support_component_evidence(
            comparison,
            candidate,
            reference,
            image=plane,
            background=plane,
            rms=plane,
            beam_area_pixels=0.0,
        )
    with pytest.raises(ValueError, match="same shape"):
        summarize_support_component_evidence(
            comparison,
            candidate,
            reference,
            image=np.ones((1, 1), dtype=np.float64),
            background=plane,
            rms=plane,
            beam_area_pixels=2.0,
        )


def test_summarize_support_pixels_handles_no_valid_pixels() -> None:
    mask = np.asarray([[True, False]], dtype=np.bool_)
    invalid = np.asarray([[np.nan, 1.0]])

    evidence = summarize_support_pixels(
        mask,
        image=invalid,
        background=np.zeros((1, 2)),
        rms=np.ones((1, 2)),
        beam_area_pixels=2.0,
    )

    assert evidence.pixel_count == 1
    assert evidence.valid_pixel_count == 0
    assert evidence.beam_area_count == 0.5
    assert evidence.raw_flux_jy is None
    assert evidence.direct_snr_median is None
    assert evidence.at_least_3_sigma_pixel_count == 0


def test_summarize_support_pixels_rejects_non_plane_mask() -> None:
    with pytest.raises(ValueError, match="two-dimensional"):
        summarize_support_pixels(
            np.ones(2, dtype=np.bool_),
            image=np.ones(2),
            background=np.ones(2),
            rms=np.ones(2),
            beam_area_pixels=1.0,
        )
