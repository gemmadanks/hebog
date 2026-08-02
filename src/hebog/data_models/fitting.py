"""Compact scheduler-safe Gaussian fitting records."""

from __future__ import annotations

from dataclasses import dataclass
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
    """Formal independent-pixel one-sigma position and flux uncertainty."""

    amplitude_error_jy_per_beam: float
    centroid_covariance_xx_pixels_squared: float
    centroid_covariance_xy_pixels_squared: float
    centroid_covariance_yy_pixels_squared: float
    integrated_flux_error_jy: float


@dataclass(frozen=True, slots=True)
class GaussianFitDiagnostics:
    """Bounded optimizer work and weighted-residual evidence."""

    converged: bool
    function_evaluations: int
    chi_squared: float
    degrees_of_freedom: int
    reduced_chi_squared: float | None
    parameters_at_bound: bool


@dataclass(frozen=True, slots=True)
class ValidCompactGaussianFit:
    """A converged fit retaining its independent moment oracle."""

    moment: ValidMomentMeasurement
    parameters: FittedGaussianPixelParameters
    uncertainty: GaussianFitUncertainty | None
    diagnostics: GaussianFitDiagnostics
    quality_flags: tuple[str, ...]
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
