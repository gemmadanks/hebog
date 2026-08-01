"""Tests for deterministic serial background and RMS window statistics."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from hebog.algorithms.background import estimate_rms_window_statistics
from hebog.config import RmsWindowStatisticsConfig


def _config(*, minimum_samples: int = 6) -> RmsWindowStatisticsConfig:
    """Return one explicit robust-statistics policy for bounded windows."""
    return RmsWindowStatisticsConfig(
        clipping_sigma=3.0,
        maximum_iterations=10,
        minimum_samples=minimum_samples,
    )


def test_estimates_known_background_and_rms_for_a_window_batch() -> None:
    """Constant levels and symmetric noise have analytic statistics."""
    noise = np.tile(np.array([-1.0, 1.0]), 8).reshape(4, 4)
    windows = np.stack((4.0 + noise, np.full((4, 4), -3.0)))

    statistics = estimate_rms_window_statistics(
        windows,
        np.ones_like(windows, dtype=np.bool_),
        _config(),
    )

    np.testing.assert_allclose(statistics.background, (4.0, -3.0))
    np.testing.assert_allclose(statistics.rms, (1.0, 0.0))
    np.testing.assert_array_equal(statistics.available, (True, True))
    np.testing.assert_array_equal(statistics.valid_sample_count, (16, 16))
    np.testing.assert_array_equal(
        statistics.retained_sample_count,
        (16, 16),
    )
    with pytest.raises(ValueError, match="read-only"):
        statistics.rms[0] = 2.0


def test_clips_a_bright_outlier_without_biasing_symmetric_noise() -> None:
    """One source-like sample does not inflate its window's noise estimate."""
    window = np.concatenate(
        (np.tile(np.array([-2.0, 2.0]), 12), np.array([100.0]))
    ).reshape(1, 5, 5)

    statistics = estimate_rms_window_statistics(
        window,
        np.ones_like(window, dtype=np.bool_),
        _config(),
    )

    np.testing.assert_allclose(statistics.background, (0.0,))
    np.testing.assert_allclose(statistics.rms, (2.0,))
    np.testing.assert_array_equal(statistics.valid_sample_count, (25,))
    np.testing.assert_array_equal(statistics.retained_sample_count, (24,))


def test_excludes_masks_and_nonfinite_pixels_but_accepts_negative_values() -> (
    None
):
    """Validity is explicit; a negative sky level remains scientific data."""
    windows = np.array([[[-5.0, -3.0, -1.0], [999.0, np.nan, np.inf]]])
    valid_pixels = np.array(
        [[[True, True, True], [False, True, True]]],
        dtype=np.bool_,
    )

    statistics = estimate_rms_window_statistics(
        windows,
        valid_pixels,
        _config(minimum_samples=3),
    )

    np.testing.assert_allclose(statistics.background, (-3.0,))
    np.testing.assert_allclose(statistics.rms, (np.sqrt(8.0 / 3.0),))
    np.testing.assert_array_equal(statistics.valid_sample_count, (3,))
    np.testing.assert_array_equal(statistics.retained_sample_count, (3,))
    np.testing.assert_array_equal(statistics.available, (True,))


def test_marks_sparse_windows_unavailable_with_explicit_counts() -> None:
    """Interpolation can distinguish absent estimates from zero-valued RMS."""
    windows = np.array(
        [
            [[np.nan, np.nan], [np.nan, np.nan]],
            [[1.0, 2.0], [3.0, 4.0]],
        ]
    )
    valid_pixels = np.array(
        [
            [[True, True], [True, True]],
            [[True, True], [False, False]],
        ],
        dtype=np.bool_,
    )

    statistics = estimate_rms_window_statistics(
        windows,
        valid_pixels,
        _config(minimum_samples=3),
    )

    assert np.isnan(statistics.background).all()
    assert np.isnan(statistics.rms).all()
    np.testing.assert_array_equal(statistics.available, (False, False))
    np.testing.assert_array_equal(statistics.valid_sample_count, (0, 2))
    np.testing.assert_array_equal(statistics.retained_sample_count, (0, 2))


@given(
    offset=st.floats(
        min_value=-1e4,
        max_value=1e4,
        allow_nan=False,
        allow_infinity=False,
    ),
    scale=st.floats(
        min_value=1e-3,
        max_value=1e3,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_positive_affine_transform_preserves_window_statistics(
    offset: float,
    scale: float,
) -> None:
    """Offsets shift background and positive scaling scales RMS."""
    base = np.tile(np.array([-2.0, -1.0, 1.0, 2.0]), 4).reshape(1, 4, 4)
    valid_pixels = np.ones_like(base, dtype=np.bool_)
    reference = estimate_rms_window_statistics(
        base,
        valid_pixels,
        _config(),
    )

    transformed = estimate_rms_window_statistics(
        offset + scale * base,
        valid_pixels,
        _config(),
    )

    np.testing.assert_allclose(
        transformed.background,
        offset + scale * reference.background,
        rtol=1e-12,
        atol=1e-10,
    )
    np.testing.assert_allclose(
        transformed.rms,
        scale * reference.rms,
        rtol=1e-12,
        atol=1e-10,
    )
    np.testing.assert_array_equal(
        transformed.retained_sample_count,
        reference.retained_sample_count,
    )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"clipping_sigma": 0.0}, "clipping_sigma"),
        ({"clipping_sigma": float("nan")}, "clipping_sigma"),
        ({"maximum_iterations": True}, "maximum_iterations.*integer"),
        ({"maximum_iterations": 1.5}, "maximum_iterations.*integer"),
        ({"maximum_iterations": 0}, "maximum_iterations"),
        ({"minimum_samples": False}, "minimum_samples.*integer"),
        ({"minimum_samples": 2.5}, "minimum_samples.*integer"),
        ({"minimum_samples": 1}, "minimum_samples"),
    ],
)
def test_rejects_invalid_window_statistics_configuration(
    updates: dict[str, float | int],
    message: str,
) -> None:
    """Invalid clipping policies fail before any image work begins."""
    values: dict[str, float | int] = {
        "clipping_sigma": 3.0,
        "maximum_iterations": 10,
        "minimum_samples": 6,
    }
    values.update(updates)

    with pytest.raises(ValueError, match=message):
        RmsWindowStatisticsConfig(**values)  # type: ignore[arg-type]


def test_rejects_non_batched_or_misaligned_windows() -> None:
    """Window batches and their validity arrays must align exactly."""
    with pytest.raises(ValueError, match="three-dimensional"):
        estimate_rms_window_statistics(
            np.ones((3, 3)),
            np.ones((3, 3), dtype=np.bool_),
            _config(),
        )

    with pytest.raises(ValueError, match="same shape"):
        estimate_rms_window_statistics(
            np.ones((2, 3, 3)),
            np.ones((1, 3, 3), dtype=np.bool_),
            _config(),
        )


@pytest.mark.parametrize("shape", [(0, 2, 2), (1, 0, 2), (1, 2, 0)])
def test_rejects_empty_batches_or_windows(shape: tuple[int, int, int]) -> None:
    """Every submitted batch must contain non-empty scientific windows."""
    with pytest.raises(ValueError, match="non-empty"):
        estimate_rms_window_statistics(
            np.empty(shape),
            np.empty(shape, dtype=np.bool_),
            _config(),
        )
