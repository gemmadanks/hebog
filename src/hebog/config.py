"""Immutable scientific and execution configuration."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral
from typing import Literal

_MINIMUM_RMS_SAMPLES = 2
_MINIMUM_SHAPE_PIXELS = 3
_MINIMUM_GAUSSIAN_FIT_PIXELS = 7


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
    candidate_threshold_sigma: float
    influence_radius_pixels: float
    transition_width_pixels: float

    def __post_init__(self) -> None:
        """Require finite positive radii and a contained transition zone."""
        if (
            not isfinite(self.candidate_threshold_sigma)
            or self.candidate_threshold_sigma <= 0
        ):
            raise ValueError(
                "candidate_threshold_sigma must be finite and positive"
            )
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
    Island-size cuts are likewise explicit pixel counts; a compatibility
    adapter may derive them from reviewed beam metadata before constructing
    this scheduler-independent configuration.
    Workflow-specific background, RMS, multiscale, and filtering choices
    belong to compatibility configuration at the adapter boundary until their
    scientific contracts are implemented.
    """

    detection_threshold_sigma: float
    island_threshold_sigma: float
    minimum_island_pixels: int
    maximum_island_pixels: int | None = None

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
        if (
            isinstance(self.minimum_island_pixels, bool)
            or not isinstance(self.minimum_island_pixels, Integral)
            or self.minimum_island_pixels < 1
        ):
            raise ValueError(
                "minimum_island_pixels must be a positive integer"
            )
        maximum = self.maximum_island_pixels
        if maximum is not None and (
            isinstance(maximum, bool)
            or not isinstance(maximum, Integral)
            or maximum < self.minimum_island_pixels
        ):
            raise ValueError(
                "maximum_island_pixels must be an integer no smaller than "
                "minimum_island_pixels"
            )


@dataclass(frozen=True, slots=True)
class CompactDeblendConfig:
    """Peak, saddle, and admitted-memory policy for compact deblending."""

    minimum_peak_signal_to_noise: float
    minimum_peak_separation_pixels: int
    minimum_saddle_depth_sigma: float
    minimum_region_pixels: int
    maximum_compact_island_pixels: int
    maximum_compact_bounds_pixels: int
    maximum_batch_pixels: int

    def __post_init__(self) -> None:
        """Require explicit finite science cuts and bounded region costs."""
        if (
            not isfinite(self.minimum_peak_signal_to_noise)
            or self.minimum_peak_signal_to_noise <= 0
        ):
            raise ValueError(
                "minimum_peak_signal_to_noise must be finite and positive"
            )
        if (
            isinstance(self.minimum_peak_separation_pixels, bool)
            or not isinstance(self.minimum_peak_separation_pixels, Integral)
            or self.minimum_peak_separation_pixels < 1
        ):
            raise ValueError(
                "minimum_peak_separation_pixels must be a positive integer"
            )
        if (
            not isfinite(self.minimum_saddle_depth_sigma)
            or self.minimum_saddle_depth_sigma < 0
        ):
            raise ValueError(
                "minimum_saddle_depth_sigma must be finite and non-negative"
            )
        if (
            isinstance(self.minimum_region_pixels, bool)
            or not isinstance(self.minimum_region_pixels, Integral)
            or self.minimum_region_pixels < 1
        ):
            raise ValueError(
                "minimum_region_pixels must be a positive integer"
            )
        for value, name in (
            (
                self.maximum_compact_island_pixels,
                "maximum_compact_island_pixels",
            ),
            (
                self.maximum_compact_bounds_pixels,
                "maximum_compact_bounds_pixels",
            ),
            (self.maximum_batch_pixels, "maximum_batch_pixels"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")
        if self.maximum_batch_pixels < self.maximum_compact_bounds_pixels:
            raise ValueError(
                "maximum_batch_pixels must admit one compact bounds region"
            )


@dataclass(frozen=True, slots=True)
class CompactMomentConfig:
    """Numerical availability policy for compact moment ellipses."""

    minimum_shape_pixels: int
    covariance_relative_tolerance: float

    def __post_init__(self) -> None:
        """Require enough pixels for 2-D shape and a strict tolerance."""
        if (
            isinstance(self.minimum_shape_pixels, bool)
            or not isinstance(self.minimum_shape_pixels, Integral)
            or self.minimum_shape_pixels < _MINIMUM_SHAPE_PIXELS
        ):
            raise ValueError("minimum_shape_pixels must be an integer >= 3")
        if (
            not isfinite(self.covariance_relative_tolerance)
            or not 0 < self.covariance_relative_tolerance < 1
        ):
            raise ValueError(
                "covariance_relative_tolerance must be finite and in (0, 1)"
            )


@dataclass(frozen=True, slots=True)
class CompactGaussianFitConfig:
    """Explicit bounded nonlinear policy for one compact Gaussian fit."""

    minimum_fit_pixels: int
    maximum_function_evaluations: int
    minimum_sigma_pixels: float
    maximum_sigma_pixels: float
    maximum_amplitude_factor: float
    center_margin_pixels: float
    convergence_tolerance: float
    maximum_axis_ratio: float
    maximum_background_offset_sigma: float = 3.0
    context_margin_pixels: int = 8
    extension_significance_sigma: float = 5.0
    maximum_information_condition_number: float = 1e8
    background_model: Literal["fitted-offset", "fixed-zero"] = "fitted-offset"
    pixel_support: Literal["bounded-context", "owned-region"] = (
        "bounded-context"
    )
    point_estimator: Literal["diagonal-weighted", "correlated-gls"] = (
        "diagonal-weighted"
    )
    maximum_gls_pixels: int = 512
    model_selection: Literal["free-only", "beam-or-free"] = "free-only"
    position_estimator: Literal["selected-model", "bounded-context-free"] = (
        "selected-model"
    )
    association_aperture_radius_sigma: float = 3.0

    def __post_init__(self) -> None:
        """Validate scientific parameter bounds and finite work limits."""
        if (
            isinstance(self.minimum_fit_pixels, bool)
            or not isinstance(self.minimum_fit_pixels, Integral)
            or self.minimum_fit_pixels < _MINIMUM_GAUSSIAN_FIT_PIXELS
        ):
            raise ValueError("minimum_fit_pixels must be an integer >= 7")
        if (
            isinstance(self.maximum_function_evaluations, bool)
            or not isinstance(self.maximum_function_evaluations, Integral)
            or self.maximum_function_evaluations < 1
        ):
            raise ValueError(
                "maximum_function_evaluations must be a positive integer"
            )
        if (
            not isfinite(self.minimum_sigma_pixels)
            or not isfinite(self.maximum_sigma_pixels)
            or self.minimum_sigma_pixels <= 0
            or self.maximum_sigma_pixels <= self.minimum_sigma_pixels
        ):
            raise ValueError("sigma bounds must be finite, positive, ordered")
        if (
            not isfinite(self.maximum_amplitude_factor)
            or self.maximum_amplitude_factor <= 1
        ):
            raise ValueError("maximum_amplitude_factor must exceed one")
        if (
            not isfinite(self.center_margin_pixels)
            or self.center_margin_pixels < 0
        ):
            raise ValueError("center_margin_pixels must be finite and >= 0")
        if (
            not isfinite(self.convergence_tolerance)
            or not 0 < self.convergence_tolerance < 1
        ):
            raise ValueError(
                "convergence_tolerance must be finite and in (0, 1)"
            )
        if (
            not isfinite(self.maximum_axis_ratio)
            or self.maximum_axis_ratio <= 1
        ):
            raise ValueError("maximum_axis_ratio must be finite and > 1")
        if (
            not isfinite(self.maximum_background_offset_sigma)
            or self.maximum_background_offset_sigma <= 0
        ):
            raise ValueError(
                "maximum_background_offset_sigma must be finite and positive"
            )
        if (
            isinstance(self.context_margin_pixels, bool)
            or not isinstance(self.context_margin_pixels, Integral)
            or self.context_margin_pixels < 0
        ):
            raise ValueError(
                "context_margin_pixels must be a non-negative integer"
            )
        self._validate_selection_policy()

    def _validate_selection_policy(self) -> None:
        """Validate extension evidence and identifiability thresholds."""
        if self.background_model not in {"fitted-offset", "fixed-zero"}:
            raise ValueError("background_model is not a supported policy")
        if self.pixel_support not in {"bounded-context", "owned-region"}:
            raise ValueError("pixel_support is not a supported policy")
        if self.point_estimator not in {
            "diagonal-weighted",
            "correlated-gls",
        }:
            raise ValueError("point_estimator is not a supported policy")
        if self.model_selection not in {"free-only", "beam-or-free"}:
            raise ValueError("model_selection is not a supported policy")
        if self.position_estimator not in {
            "selected-model",
            "bounded-context-free",
        }:
            raise ValueError("position_estimator is not a supported policy")
        if (
            not isfinite(self.association_aperture_radius_sigma)
            or self.association_aperture_radius_sigma <= 0
        ):
            raise ValueError(
                "association_aperture_radius_sigma must be finite and positive"
            )
        if (
            isinstance(self.maximum_gls_pixels, bool)
            or not isinstance(self.maximum_gls_pixels, Integral)
            or self.maximum_gls_pixels < _MINIMUM_GAUSSIAN_FIT_PIXELS
        ):
            raise ValueError("maximum_gls_pixels must be an integer >= 7")
        if (
            not isfinite(self.extension_significance_sigma)
            or self.extension_significance_sigma <= 0
        ):
            raise ValueError(
                "extension_significance_sigma must be finite and positive"
            )
        if (
            not isfinite(self.maximum_information_condition_number)
            or self.maximum_information_condition_number <= 1
        ):
            raise ValueError(
                "maximum_information_condition_number must be finite and "
                "greater than one"
            )


@dataclass(frozen=True, slots=True)
class CompactCatalogueConfig:
    """Bounded compact catalogue assembly and deconvolution policy."""

    maximum_catalogue_records: int
    deconvolution_relative_tolerance: float
    extension_significance_sigma: float
    deconvolution_axis_significance_sigma: float = 5.0

    def __post_init__(self) -> None:
        """Require an explicit population cap and numerical policies."""
        if (
            isinstance(self.maximum_catalogue_records, bool)
            or not isinstance(self.maximum_catalogue_records, Integral)
            or self.maximum_catalogue_records < 1
        ):
            raise ValueError(
                "maximum_catalogue_records must be a positive integer"
            )
        if (
            not isfinite(self.deconvolution_relative_tolerance)
            or not 0 < self.deconvolution_relative_tolerance < 1
        ):
            raise ValueError(
                "deconvolution_relative_tolerance must be finite and in (0, 1)"
            )
        if (
            not isfinite(self.extension_significance_sigma)
            or self.extension_significance_sigma <= 0
        ):
            raise ValueError(
                "extension_significance_sigma must be finite and positive"
            )
        if (
            not isfinite(self.deconvolution_axis_significance_sigma)
            or self.deconvolution_axis_significance_sigma <= 0
        ):
            raise ValueError(
                "deconvolution_axis_significance_sigma must be finite and "
                "positive"
            )
