"""Tests for standard-practice irregular extended-position measurement."""

from __future__ import annotations

from typing import cast

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.extended_measurement import (
    clean_detected_segment_labels,
    expand_detected_segment_labels,
    measure_detected_segment_position,
    refine_multiscale_segment_labels,
)


def test_segment_cleanup_removes_only_sub_beam_protrusions() -> None:
    """A three-pixel opening removes one-pixel noise without relabelling."""
    labels = np.zeros((9, 11), dtype=np.int32)
    labels[2:7, 2:7] = 4
    labels[4, 7:10] = 4
    labels[2:7, 8:11] = 9

    cleaned = clean_detected_segment_labels(labels)

    assert np.all(cleaned[2:7, 2:7] == 4)
    assert np.all(cleaned[2:7, 8:11] == 9)
    assert np.all(cleaned[4, 7:8] == 0)
    assert set(np.unique(cleaned)) == {0, 4, 9}


def test_multiscale_refinement_uses_scale_support() -> None:
    """Dense, high-SNR, and adjacent-scale pixels define final support."""
    labels = np.zeros((11, 13), dtype=np.int32)
    labels[3:8, 2:7] = 4
    labels[5, 7:10] = 4
    labels[3:8, 10:13] = 9
    combined_snr = np.zeros(labels.shape, dtype=np.float64)
    combined_snr[labels > 0] = 4.0
    combined_snr[5, 7] = 6.0
    reconstruction = np.zeros(labels.shape, dtype=np.bool_)
    reconstruction[4:7, 7:10] = True

    refined = refine_multiscale_segment_labels(
        labels,
        combined_snr,
        reconstruction,
        beam_major_fwhm_pixels=4.0,
    )

    assert np.all(refined[4:7, 3:6] == 4)
    assert np.all(refined[4:7, 10:12] == 9)
    assert refined[3, 2] == 0
    assert refined[5, 7] == 4
    assert refined[4, 8] == 4
    assert refined[4, 9] == 9
    assert refined[3, 7] == 0
    assert set(np.unique(refined)) == {0, 4, 9}


def test_multiscale_refinement_rejects_ambiguous_evidence() -> None:
    """Refinement requires aligned calibrated planes and a finite beam."""
    labels = np.ones((5, 5), dtype=np.int32)
    snr = np.ones((5, 5), dtype=np.float64)
    support = np.ones((5, 5), dtype=np.bool_)

    with pytest.raises(ValueError, match="aligned"):
        refine_multiscale_segment_labels(
            labels,
            snr[:-1],
            support,
            beam_major_fwhm_pixels=3.0,
        )
    with pytest.raises(ValueError, match="boolean"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support.astype(np.int8),
            beam_major_fwhm_pixels=3.0,
        )
    with pytest.raises(ValueError, match="positive"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=np.nan,
        )
    with pytest.raises(ValueError, match="neighbors"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=3.0,
            core_minimum_neighbors=True,
        )
    with pytest.raises(ValueError, match="neighbors"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=3.0,
            core_minimum_neighbors=10,
        )
    with pytest.raises(ValueError, match="neighbors"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=3.0,
            core_minimum_neighbors=5.5,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="boundary minimum"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=3.0,
            boundary_minimum_snr=0.0,
        )
    with pytest.raises(ValueError, match="recovery radius"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=3.0,
            recovery_radius_beams=-0.1,
        )

    empty = refine_multiscale_segment_labels(
        np.zeros(labels.shape, dtype=np.int32),
        snr,
        support,
        beam_major_fwhm_pixels=3.0,
    )
    assert not empty.any()


def test_expanded_segment_labels_assign_overlap_to_nearest_support() -> None:
    """Measurement apertures are bounded, valid, and never double-counted."""
    labels = np.zeros((7, 9), dtype=np.int32)
    labels[3, 2] = 3
    labels[3, 6] = 8
    valid = np.ones(labels.shape, dtype=np.bool_)
    valid[3, 4] = False

    expanded = expand_detected_segment_labels(
        labels,
        valid,
        radius_pixels=2,
    )

    assert expanded[3, 2] == 3
    assert expanded[3, 6] == 8
    assert expanded[3, 3] == 3
    assert expanded[3, 5] == 8
    assert expanded[3, 4] == 0
    assert expanded[0, 0] == 0


def test_segment_label_transforms_reject_ambiguous_planes() -> None:
    """Morphology and aperture ownership require exact label contracts."""
    with pytest.raises(ValueError, match="integer label"):
        clean_detected_segment_labels(np.ones((3, 3), dtype=np.float64))
    negative = np.zeros((3, 3), dtype=np.int32)
    negative[1, 1] = -1
    with pytest.raises(ValueError, match="non-negative"):
        clean_detected_segment_labels(negative)
    with pytest.raises(ValueError, match="aligned"):
        expand_detected_segment_labels(
            np.ones((3, 3), dtype=np.int32),
            np.ones((2, 3), dtype=np.bool_),
            radius_pixels=2,
        )
    with pytest.raises(ValueError, match="non-negative integer"):
        expand_detected_segment_labels(
            np.ones((3, 3), dtype=np.int32),
            np.ones((3, 3), dtype=np.bool_),
            radius_pixels=-1,
        )
    with pytest.raises(ValueError, match="non-negative integer"):
        expand_detected_segment_labels(
            np.ones((3, 3), dtype=np.int32),
            np.ones((3, 3), dtype=np.bool_),
            radius_pixels=True,
        )
    with pytest.raises(ValueError, match="aligned"):
        expand_detected_segment_labels(
            np.ones((3, 3), dtype=np.int32),
            np.ones((3, 3), dtype=np.int8),
            radius_pixels=1,
        )

    empty = expand_detected_segment_labels(
        np.zeros((3, 3), dtype=np.int32),
        np.ones((3, 3), dtype=np.bool_),
        radius_pixels=1,
    )
    assert not empty.any()


def test_detected_segment_position_uses_only_original_supported_pixels() -> (
    None
):
    """The catalogue centroid and peak share the exact accepted segment."""
    signal = np.asarray(
        (
            (100.0, 1.0, 0.0),
            (0.0, 2.0, 3.0),
            (0.0, 0.0, 3.0),
        )
    )
    support = np.asarray(
        (
            (False, True, False),
            (False, True, True),
            (False, False, True),
        )
    )

    estimate = measure_detected_segment_position(signal, support)

    assert estimate.available is True
    assert estimate.centroid_xy == pytest.approx((5.0 / 3.0, 11.0 / 9.0))
    assert estimate.peak_position_xy == (2, 1)
    assert estimate.support_pixel_count == 4
    assert estimate.integrated_weight == pytest.approx(9.0)
    assert estimate.unavailable_reason is None


def test_detected_segment_peak_ties_use_row_major_first() -> None:
    """Equal maxima have deterministic global y-then-x ownership."""
    signal = np.asarray(((0.0, 4.0), (4.0, 0.0)))
    support = np.ones(signal.shape, dtype=np.bool_)

    estimate = measure_detected_segment_position(signal, support)

    assert estimate.peak_position_xy == (1, 0)


def test_detected_segment_position_reports_typed_unavailability() -> None:
    """Empty and non-positive segments do not emit invented coordinates."""
    signal = np.ones((2, 2), dtype=np.float64)

    empty = measure_detected_segment_position(
        signal, np.zeros(signal.shape, dtype=np.bool_)
    )
    nonpositive = measure_detected_segment_position(
        -signal, np.ones(signal.shape, dtype=np.bool_)
    )

    assert empty.available is False
    assert empty.centroid_xy is None
    assert empty.peak_position_xy is None
    assert empty.unavailable_reason == "empty-finite-support"
    assert nonpositive.available is False
    assert nonpositive.unavailable_reason == "nonpositive-segment-flux"


def test_detected_segment_position_rejects_bad_array_contract() -> None:
    """Only aligned two-dimensional numeric pixels enter the estimator."""
    with pytest.raises(ValueError, match="aligned two-dimensional"):
        measure_detected_segment_position(
            np.ones((2, 2)), np.ones((2, 1), dtype=np.bool_)
        )
    with pytest.raises(ValueError, match="boolean"):
        measure_detected_segment_position(
            np.ones((2, 2)),
            cast(
                npt.NDArray[np.bool_],
                np.ones((2, 2), dtype=np.int64),
            ),
        )
