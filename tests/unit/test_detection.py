"""Analytic tests for bounded two-threshold source detection."""

from __future__ import annotations

import numpy as np
import pytest

from hebog.algorithms.detection import detect_threshold_masks
from hebog.config import SourceFinderConfig


def _config(
    *,
    detection_threshold_sigma: float = 5.0,
    island_threshold_sigma: float = 3.0,
) -> SourceFinderConfig:
    """Return the explicit compact-detection profile used by tests."""
    return SourceFinderConfig(
        detection_threshold_sigma=detection_threshold_sigma,
        island_threshold_sigma=island_threshold_sigma,
        minimum_island_pixels=1,
    )


def test_exact_threshold_boundaries_are_explicit() -> None:
    """Island membership is inclusive while detection seeds are strict."""
    normalized = np.array([[3.0, 5.0, np.nextafter(5.0, np.inf)]])
    background = np.full(normalized.shape, -2.0)
    rms = np.full(normalized.shape, 0.5)
    image = background + normalized * rms

    result = detect_threshold_masks(
        image,
        np.ones(image.shape, dtype=np.bool_),
        background,
        rms,
        _config(),
    )

    np.testing.assert_array_equal(
        result.island_membership,
        [[True, True, True]],
    )
    np.testing.assert_array_equal(
        result.detection_seeds,
        [[False, False, True]],
    )
    np.testing.assert_array_equal(result.normalized_residual, normalized)


def test_invalid_and_non_positive_rms_pixels_are_never_detected() -> None:
    """Invalid values and unusable RMS fail scientifically closed."""
    image = np.full((2, 4), 100.0)
    background = np.zeros_like(image)
    rms = np.array([[1.0, 0.0, -1.0, np.nan], [1.0, 1.0, 1.0, 1.0]])
    valid = np.array(
        [[True, True, True, True], [False, True, True, True]],
        dtype=np.bool_,
    )
    image[1, 1] = np.nan
    background[1, 2] = np.inf
    image[1, 3] = -100.0

    result = detect_threshold_masks(
        image,
        valid,
        background,
        rms,
        _config(),
    )

    expected = np.array(
        [[True, False, False, False], [False, False, False, False]]
    )
    np.testing.assert_array_equal(result.island_membership, expected)
    np.testing.assert_array_equal(result.detection_seeds, expected)
    assert np.isnan(result.normalized_residual[0, 1:]).all()
    assert np.isnan(result.normalized_residual[1, :3]).all()
    assert result.normalized_residual[1, 3] == -100.0
    assert result.valid_pixel_count == 2


def test_positive_affine_transform_preserves_threshold_masks() -> None:
    """Scaling image, background, and RMS together preserves topology."""
    image = np.array([[2.0, 4.0, 8.0], [3.0, 5.0, 10.0]])
    background = np.full(image.shape, 2.0)
    rms = np.full(image.shape, 1.0)
    valid = np.ones(image.shape, dtype=np.bool_)
    original = detect_threshold_masks(
        image,
        valid,
        background,
        rms,
        _config(),
    )

    scale = 7.5
    offset = -3.25
    transformed = detect_threshold_masks(
        image * scale + offset,
        valid,
        background * scale + offset,
        rms * scale,
        _config(),
    )

    np.testing.assert_array_equal(
        transformed.island_membership,
        original.island_membership,
    )
    np.testing.assert_array_equal(
        transformed.detection_seeds,
        original.detection_seeds,
    )


def test_detection_and_island_thresholds_have_distinct_monotonicity() -> None:
    """Detection seeds and membership shrink under their own threshold."""
    image = np.arange(9, dtype=np.float64).reshape(3, 3)
    background = np.zeros_like(image)
    rms = np.ones_like(image)
    valid = np.ones(image.shape, dtype=np.bool_)
    baseline = detect_threshold_masks(
        image,
        valid,
        background,
        rms,
        _config(detection_threshold_sigma=5.0, island_threshold_sigma=2.0),
    )
    higher_detection = detect_threshold_masks(
        image,
        valid,
        background,
        rms,
        _config(detection_threshold_sigma=7.0, island_threshold_sigma=2.0),
    )
    higher_island = detect_threshold_masks(
        image,
        valid,
        background,
        rms,
        _config(detection_threshold_sigma=5.0, island_threshold_sigma=4.0),
    )

    assert np.all(~higher_detection.detection_seeds | baseline.detection_seeds)
    np.testing.assert_array_equal(
        higher_detection.island_membership,
        baseline.island_membership,
    )
    assert np.all(
        ~higher_island.island_membership | baseline.island_membership
    )
    np.testing.assert_array_equal(
        higher_island.detection_seeds,
        baseline.detection_seeds,
    )


def test_detection_outputs_are_read_only() -> None:
    """Callers cannot accidentally change reviewed mask membership."""
    result = detect_threshold_masks(
        np.full((2, 2), 10.0),
        np.ones((2, 2), dtype=np.bool_),
        np.zeros((2, 2)),
        np.ones((2, 2)),
        _config(),
    )

    assert not result.island_membership.flags.writeable
    assert not result.detection_seeds.flags.writeable
    assert not result.normalized_residual.flags.writeable


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"valid_pixels": np.ones((2, 3), dtype=np.bool_)}, "same shape"),
        ({"background": np.zeros((2, 3))}, "same shape"),
        ({"rms": np.ones((2, 3))}, "same shape"),
        ({"valid_pixels": np.ones((2, 2), dtype=np.int8)}, "boolean"),
        ({"valid_pixels": np.ones((4,), dtype=np.bool_)}, "two-dimensional"),
        ({"image": np.ones((4,))}, "two-dimensional"),
        ({"image": np.ones((2, 2), dtype=np.bool_)}, "real numeric"),
        ({"image": np.ones((2, 2), dtype=np.complex128)}, "real numeric"),
    ],
)
def test_detection_rejects_invalid_array_contracts(
    replacement: dict[str, np.ndarray],
    message: str,
) -> None:
    """Tile arrays cannot broadcast or coerce invalid validity metadata."""
    arguments = {
        "image": np.ones((2, 2)),
        "valid_pixels": np.ones((2, 2), dtype=np.bool_),
        "background": np.zeros((2, 2)),
        "rms": np.ones((2, 2)),
    }
    arguments.update(replacement)

    with pytest.raises((TypeError, ValueError), match=message):
        detect_threshold_masks(**arguments, config=_config())
