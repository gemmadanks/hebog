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


def _validate_positive_shape(
    values: tuple[int, int],
    name: str,
) -> None:
    """Require exactly two positive non-boolean integer dimensions."""
    expected_dimensions = 2
    if len(values) != expected_dimensions or any(
        isinstance(value, bool) or not isinstance(value, Integral) or value < 1
        for value in values
    ):
        raise ValueError(f"{name} dimensions must be positive integers")


@dataclass(frozen=True, slots=True)
class RmsGridConfig:
    """Window geometry and bounded-batch policy for one RMS grid."""

    window_shape_yx: tuple[int, int]
    step_yx: tuple[int, int]
    statistics: RmsWindowStatisticsConfig
    maximum_batch_cells: int

    def __post_init__(self) -> None:
        """Require meaningful windows and an explicit positive batch bound."""
        _validate_positive_shape(self.window_shape_yx, "window shape")
        _validate_positive_shape(self.step_yx, "step")
        if any(
            step > window
            for step, window in zip(
                self.step_yx,
                self.window_shape_yx,
                strict=True,
            )
        ):
            raise ValueError(
                "RMS grid step cannot exceed its window dimension"
            )
        if (
            isinstance(self.maximum_batch_cells, bool)
            or not isinstance(self.maximum_batch_cells, Integral)
            or self.maximum_batch_cells < 1
        ):
            raise ValueError("maximum_batch_cells must be a positive integer")


@dataclass(frozen=True, slots=True)
class AdaptiveRmsConfig:
    """Fine-grid and deterministic blend policy around bright candidates."""

    grid: RmsGridConfig
    influence_radius_pixels: float
    transition_width_pixels: float

    def __post_init__(self) -> None:
        """Require finite positive radii and a contained transition zone."""
        if (
            not isfinite(self.influence_radius_pixels)
            or self.influence_radius_pixels <= 0
        ):
            raise ValueError(
                "influence_radius_pixels must be finite and positive"
            )
        if (
            not isfinite(self.transition_width_pixels)
            or self.transition_width_pixels <= 0
            or self.transition_width_pixels > self.influence_radius_pixels
        ):
            raise ValueError(
                "transition_width_pixels must be finite, positive, and no "
                "larger than influence_radius_pixels"
            )


@dataclass(frozen=True, slots=True)
class BackgroundRmsConfig:
    """Complete coarse, adaptive, interpolation, and memory policy."""

    coarse: RmsGridConfig
    adaptive: AdaptiveRmsConfig | None
    maximum_spatial_window_fraction: float
    maximum_constant_map_pixels: int

    def __post_init__(self) -> None:
        """Validate automatic constant-map fallback and its memory bound."""
        if (
            not isfinite(self.maximum_spatial_window_fraction)
            or not 0 < self.maximum_spatial_window_fraction <= 1
        ):
            raise ValueError(
                "maximum_spatial_window_fraction must be finite and in (0, 1]"
            )
        if (
            isinstance(self.maximum_constant_map_pixels, bool)
            or not isinstance(self.maximum_constant_map_pixels, Integral)
            or self.maximum_constant_map_pixels < 1
        ):
            raise ValueError(
                "maximum_constant_map_pixels must be a positive integer"
            )


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
