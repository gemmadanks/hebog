"""Tests for source-finder configuration."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hebog import SourceFinderConfig


def test_default_thresholds_are_ordered() -> None:
    """The island threshold remains below the detection threshold."""
    config = SourceFinderConfig()

    assert config.island_sigma < config.detection_sigma


def test_rejects_inverted_thresholds() -> None:
    """Invalid detection and island thresholds fail immediately."""
    with pytest.raises(ValueError, match="island_sigma"):
        SourceFinderConfig(detection_sigma=3.0, island_sigma=5.0)


@given(
    island_sigma=st.floats(
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
    island_sigma: float,
    separation: float,
) -> None:
    """Every finite positive ordered threshold pair is valid."""
    detection_sigma = island_sigma + separation

    config = SourceFinderConfig(
        detection_sigma=detection_sigma,
        island_sigma=island_sigma,
    )

    assert config.detection_sigma > config.island_sigma > 0


@given(
    detection_sigma=st.floats(
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
    detection_sigma: float,
    excess: float,
) -> None:
    """Equal or inverted finite threshold pairs always violate the contract."""
    with pytest.raises(ValueError, match="island_sigma"):
        SourceFinderConfig(
            detection_sigma=detection_sigma,
            island_sigma=detection_sigma + excess,
        )
