"""Compact scheduler-safe Gaussian fitting records."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal, TypeAlias

from hebog.data_models.measurement import (
    CompactMomentMeasurement,
    ValidMomentMeasurement,
)


@dataclass(frozen=True, slots=True)
class FittedGaussianPixelParameters:
    """One fitted Gaussian in global pixel coordinates and physical units."""

    amplitude_jy_per_beam: float
    centroid_xy: tuple[float, float]
    major_sigma_pixels: float
    minor_sigma_pixels: float
    major_axis_angle_degrees: float
    integrated_flux_jy: float
    local_rms_jy_per_beam: float


@dataclass(frozen=True, slots=True)
class GaussianFitUncertainty:
    """One-sigma position and flux covariance estimate for a fitted model."""

    amplitude_error_jy_per_beam: float
    centroid_covariance_xx_pixels_squared: float
    centroid_covariance_xy_pixels_squared: float
    centroid_covariance_yy_pixels_squared: float
    integrated_flux_error_jy: float
    integrated_flux_bias_correction_sigma: float = 0.0
    amplitude_integrated_flux_covariance_jy_squared_per_beam: float | None = (
        None
    )
    shape_parameter_covariance: (
        tuple[float, float, float, float, float, float] | None
    ) = None
    """Upper triangle for ordered major/minor sigma and angle in radians."""


@dataclass(frozen=True, slots=True)
class AssociationAperturePhotometry:
    """Mask-aware flux within a data-selected compact association aperture."""

    radius_sigma: float
    integrated_flux_jy: float
    visible_model_fraction: float
    retained_pixel_count: int
    aperture_model: Literal["restoring-beam", "selected-fit"]

    def __post_init__(self) -> None:
        """Require finite positive photometry and bounded visibility."""
        if not isfinite(self.radius_sigma) or self.radius_sigma <= 0:
            raise ValueError("aperture radius must be finite and positive")
        if (
            not isfinite(self.integrated_flux_jy)
            or self.integrated_flux_jy <= 0
        ):
            raise ValueError("aperture flux must be finite and positive")
        if (
            not isfinite(self.visible_model_fraction)
            or not 0 < self.visible_model_fraction <= 1
        ):
            raise ValueError("visible model fraction must be within (0, 1]")
        if self.retained_pixel_count <= 0:
            raise ValueError("aperture retained pixel count must be positive")
        if self.aperture_model not in {"restoring-beam", "selected-fit"}:
            raise ValueError("aperture model is not supported")


@dataclass(frozen=True, slots=True)
class GaussianPositionEstimate:
    """Centroid and covariance from an explicit position-only estimator."""

    centroid_xy: tuple[float, float]
    covariance_xx_pixels_squared: float
    covariance_xy_pixels_squared: float
    covariance_yy_pixels_squared: float
    estimator: Literal[
        "bounded-context-free",
        "bounded-context-truncation-refit",
    ] = "bounded-context-free"

    def __post_init__(self) -> None:
        """Require a finite centroid and positive-definite covariance."""
        values = (
            *self.centroid_xy,
            self.covariance_xx_pixels_squared,
            self.covariance_xy_pixels_squared,
            self.covariance_yy_pixels_squared,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("position estimate must be finite")
        if (
            self.covariance_xx_pixels_squared <= 0
            or self.covariance_yy_pixels_squared <= 0
            or self.covariance_xx_pixels_squared
            * self.covariance_yy_pixels_squared
            <= self.covariance_xy_pixels_squared**2
        ):
            raise ValueError(
                "position estimate covariance must be positive definite"
            )


@dataclass(frozen=True, slots=True)
class GaussianFitDiagnostics:
    """Bounded optimizer work and weighted-residual evidence."""

    converged: bool
    function_evaluations: int
    chi_squared: float
    degrees_of_freedom: int
    reduced_chi_squared: float | None
    parameters_at_bound: bool
    model_identity: Literal[
        "free-elliptical",
        "beam-constrained",
        "centroid-constrained-elliptical",
    ] = "free-elliptical"
    bound_parameters: tuple[str, ...] = ()
    relative_bound_distances: tuple[tuple[str, float], ...] = ()
    minimum_relative_bound_distance: float | None = None
    information_condition_number: float | None = None
    visible_model_fraction: float | None = None
    retained_pixel_count: int = 0
    retained_bounds_yx: tuple[int, int, int, int] | None = None
    fallback_reason: (
        Literal[
            "free-model-bound-contact",
            "free-model-ill-conditioned",
            "free-model-not-significantly-extended",
            "free-model-non-convergence",
            "free-model-invalid-result",
        ]
        | None
    ) = None
    point_estimator: Literal["diagonal-weighted", "correlated-gls"] = (
        "diagonal-weighted"
    )
    point_estimator_fallback_reason: (
        Literal[
            "correlation-model-unavailable",
            "correlation-factorization-failed",
            "retained-region-exceeds-gls-limit",
        ]
        | None
    ) = None
    rejected_model_identity: (
        Literal[
            "free-elliptical",
            "beam-constrained",
            "centroid-constrained-elliptical",
        ]
        | None
    ) = None
    rejected_model_bound_parameters: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GaussianComponentFit:
    """Independent free ellipse retained for component-catalogue semantics."""

    parameters: FittedGaussianPixelParameters
    uncertainty: GaussianFitUncertainty | None
    diagnostics: GaussianFitDiagnostics
    quality_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidCompactGaussianFit:
    """A converged fit retaining its independent moment oracle."""

    moment: ValidMomentMeasurement
    parameters: FittedGaussianPixelParameters
    uncertainty: GaussianFitUncertainty | None
    diagnostics: GaussianFitDiagnostics
    quality_flags: tuple[str, ...]
    position_estimate: GaussianPositionEstimate | None = None
    association_aperture: AssociationAperturePhotometry | None = None
    gaussian_component_fit: GaussianComponentFit | None = None
    status: Literal["valid"] = "valid"


@dataclass(frozen=True, slots=True)
class FailedCompactGaussianFit:
    """An attempted fit that did not yield acceptable parameters."""

    moment: ValidMomentMeasurement
    reason: Literal["fit-non-convergence", "fit-invalid-result"]
    diagnostics: GaussianFitDiagnostics
    quality_flags: tuple[str, ...]
    status: Literal["failed"] = "failed"


@dataclass(frozen=True, slots=True)
class UnavailableCompactGaussianFit:
    """A region whose measurement cannot initialize the fit-all path."""

    moment: CompactMomentMeasurement
    reason: Literal[
        "non-finite-owned-pixels",
        "non-positive-measurement",
        "singular-covariance",
        "underdetermined-region",
    ]
    quality_flags: tuple[str, ...]
    status: Literal["unavailable"] = "unavailable"


CompactGaussianFitResult: TypeAlias = (
    ValidCompactGaussianFit
    | FailedCompactGaussianFit
    | UnavailableCompactGaussianFit
)


@dataclass(frozen=True, slots=True)
class CompactIslandFitResult:
    """One parent measurement and all fit-all region outcomes."""

    island_measurement: CompactMomentMeasurement
    region_fits: tuple[CompactGaussianFitResult, ...]
