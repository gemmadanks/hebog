"""Immutable scientific and execution configuration."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


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
