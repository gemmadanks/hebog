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
    )

    assert config.detection_threshold_sigma == 5.0
    assert config.island_threshold_sigma == 3.0


def test_rejects_inverted_thresholds() -> None:
    """Invalid detection and island thresholds fail immediately."""
    with pytest.raises(ValueError, match="island_threshold_sigma"):
        SourceFinderConfig(
            detection_threshold_sigma=3.0,
            island_threshold_sigma=5.0,
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
        )
