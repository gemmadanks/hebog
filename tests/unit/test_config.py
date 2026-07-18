"""Tests for source-finder configuration."""

import pytest

from hebog import SourceFinderConfig


def test_default_thresholds_are_ordered() -> None:
    """The island threshold remains below the detection threshold."""
    config = SourceFinderConfig()

    assert config.island_sigma < config.detection_sigma


def test_rejects_inverted_thresholds() -> None:
    """Invalid detection and island thresholds fail immediately."""
    with pytest.raises(ValueError, match="island_sigma"):
        SourceFinderConfig(detection_sigma=3.0, island_sigma=5.0)
