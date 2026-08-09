"""Tests for standard-practice irregular extended-position measurement."""

from __future__ import annotations

from typing import cast

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.extended_measurement import (
    measure_detected_segment_position,
)


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
