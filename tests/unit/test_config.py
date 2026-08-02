"""Tests for source-finder configuration."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hebog import SourceFinderConfig


def test_scientific_thresholds_are_explicit() -> None:
    """The public API does not silently select one survey's thresholds."""
    with pytest.raises(TypeError, match="detection_threshold_sigma"):
        SourceFinderConfig()  # type: ignore[call-arg]


def test_accepts_common_five_three_threshold_profile() -> None:
    """A common 5-sigma detection and 3-sigma island profile is valid."""
    config = SourceFinderConfig(
        detection_threshold_sigma=5.0,
        island_threshold_sigma=3.0,
        minimum_island_pixels=6,
    )

    assert config.detection_threshold_sigma == 5.0
    assert config.island_threshold_sigma == 3.0
    assert config.minimum_island_pixels == 6
    assert config.maximum_island_pixels is None


def test_rejects_inverted_thresholds() -> None:
    """Invalid detection and island thresholds fail immediately."""
    with pytest.raises(ValueError, match="island_threshold_sigma"):
        SourceFinderConfig(
            detection_threshold_sigma=3.0,
            island_threshold_sigma=5.0,
            minimum_island_pixels=6,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_rejects_non_finite_detection_threshold(value: float) -> None:
    """Detection thresholds must be real finite sigma values."""
    with pytest.raises(ValueError, match="must be finite"):
        SourceFinderConfig(
            detection_threshold_sigma=value,
            island_threshold_sigma=3.0,
            minimum_island_pixels=6,
        )


@pytest.mark.parametrize("value", [0.0, -1.0])
def test_rejects_non_positive_detection_threshold(value: float) -> None:
    """Detection thresholds must be strictly positive."""
    with pytest.raises(ValueError, match="must be positive"):
        SourceFinderConfig(
            detection_threshold_sigma=value,
            island_threshold_sigma=3.0,
            minimum_island_pixels=6,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_rejects_non_finite_island_threshold(value: float) -> None:
    """Island thresholds must be real finite sigma values."""
    with pytest.raises(ValueError, match="must be finite"):
        SourceFinderConfig(
            detection_threshold_sigma=5.0,
            island_threshold_sigma=value,
            minimum_island_pixels=6,
        )


@pytest.mark.parametrize("value", [0.0, -1.0])
def test_rejects_non_positive_island_threshold(value: float) -> None:
    """Island thresholds must be strictly positive."""
    with pytest.raises(ValueError, match="must be positive"):
        SourceFinderConfig(
            detection_threshold_sigma=5.0,
            island_threshold_sigma=value,
            minimum_island_pixels=6,
        )


@given(
    island_threshold_sigma=st.floats(
        min_value=1e-6,
        max_value=1e6,
        allow_nan=False,
        allow_infinity=False,
    ),
    separation=st.floats(
        min_value=1e-6,
        max_value=1e6,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_accepts_all_finite_ordered_positive_thresholds(
    island_threshold_sigma: float,
    separation: float,
) -> None:
    """Every finite positive ordered threshold pair is valid."""
    detection_threshold_sigma = island_threshold_sigma + separation

    config = SourceFinderConfig(
        detection_threshold_sigma=detection_threshold_sigma,
        island_threshold_sigma=island_threshold_sigma,
        minimum_island_pixels=1,
    )

    assert config.detection_threshold_sigma > config.island_threshold_sigma > 0


@given(
    detection_threshold_sigma=st.floats(
        min_value=1e-6,
        max_value=1e6,
        allow_nan=False,
        allow_infinity=False,
    ),
    excess=st.floats(
        min_value=0.0,
        max_value=1e6,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_rejects_every_finite_unordered_positive_threshold_pair(
    detection_threshold_sigma: float,
    excess: float,
) -> None:
    """Equal or inverted finite threshold pairs always violate the contract."""
    with pytest.raises(ValueError, match="island_threshold_sigma"):
        SourceFinderConfig(
            detection_threshold_sigma=detection_threshold_sigma,
            island_threshold_sigma=detection_threshold_sigma + excess,
            minimum_island_pixels=1,
        )


@pytest.mark.parametrize("value", [True, 0, -1, 1.5])
def test_rejects_invalid_minimum_island_pixels(value: object) -> None:
    """Island population cuts use explicit positive integer pixels."""
    with pytest.raises(ValueError, match="minimum_island_pixels"):
        SourceFinderConfig(
            detection_threshold_sigma=5.0,
            island_threshold_sigma=3.0,
            minimum_island_pixels=value,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("value", [True, 0, 5, 6.5])
def test_rejects_invalid_maximum_island_pixels(value: object) -> None:
    """A finite maximum must be an integer no smaller than the minimum."""
    with pytest.raises(ValueError, match="maximum_island_pixels"):
        SourceFinderConfig(
            detection_threshold_sigma=5.0,
            island_threshold_sigma=3.0,
            minimum_island_pixels=6,
            maximum_island_pixels=value,  # type: ignore[arg-type]
        )
