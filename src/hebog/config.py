"""Immutable scientific and execution configuration."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral

_MINIMUM_RMS_SAMPLES = 2


@dataclass(frozen=True, slots=True)
class RmsWindowStatisticsConfig:
    """Robust-statistics policy for one batch of bounded RMS windows."""

    clipping_sigma: float
    maximum_iterations: int
    minimum_samples: int

    def __post_init__(self) -> None:
        """Require a finite clipping threshold and usable sample counts."""
        if not isfinite(self.clipping_sigma) or self.clipping_sigma <= 0:
            raise ValueError("clipping_sigma must be finite and positive")
        if isinstance(self.maximum_iterations, bool) or not isinstance(
            self.maximum_iterations,
            Integral,
        ):
            raise ValueError("maximum_iterations must be an integer")
        if self.maximum_iterations < 1:
            raise ValueError("maximum_iterations must be positive")
        if isinstance(self.minimum_samples, bool) or not isinstance(
            self.minimum_samples,
            Integral,
        ):
            raise ValueError("minimum_samples must be an integer")
        if self.minimum_samples < _MINIMUM_RMS_SAMPLES:
            raise ValueError("minimum_samples must be at least two")


@dataclass(frozen=True, slots=True)
class SourceFinderConfig:
    """Pipeline-neutral scientific thresholds for one image analysis.

    Thresholds are explicit because a value appropriate for one survey,
    image product, or pipeline stage is not a universal scientific default.
    Workflow-specific background, RMS, multiscale, and filtering choices
    belong to compatibility configuration at the adapter boundary until their
    scientific contracts are implemented.
    """

    detection_threshold_sigma: float
    island_threshold_sigma: float

    def __post_init__(self) -> None:
        """Validate finite, positive, ordered sigma thresholds."""
        if not isfinite(self.detection_threshold_sigma):
            raise ValueError("detection_threshold_sigma must be finite")
        if self.detection_threshold_sigma <= 0:
            raise ValueError("detection_threshold_sigma must be positive")
        if not isfinite(self.island_threshold_sigma):
            raise ValueError("island_threshold_sigma must be finite")
        if self.island_threshold_sigma <= 0:
            raise ValueError("island_threshold_sigma must be positive")
        if self.island_threshold_sigma >= self.detection_threshold_sigma:
            raise ValueError(
                "island_threshold_sigma must be lower than "
                "detection_threshold_sigma"
            )
