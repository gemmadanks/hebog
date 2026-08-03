"""Compact scheduler-safe scientific measurement records."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal, TypeAlias


@dataclass(frozen=True, slots=True)
class CompactMeasurementGeometry:
    """Reviewed local solid angles and noise correlation for compact fits."""

    pixel_solid_angle_steradians: float
    restoring_beam_solid_angle_steradians: float
    noise_correlation_covariance_pixels_squared: (
        tuple[float, float, float] | None
    ) = None

    def __post_init__(self) -> None:
        """Require explicit finite positive pixel and beam solid angles."""
        if (
            not isfinite(self.pixel_solid_angle_steradians)
            or self.pixel_solid_angle_steradians <= 0
        ):
            raise ValueError("pixel solid angle must be finite and positive")
        if (
            not isfinite(self.restoring_beam_solid_angle_steradians)
            or self.restoring_beam_solid_angle_steradians <= 0
        ):
            raise ValueError("beam solid angle must be finite and positive")
        covariance = self.noise_correlation_covariance_pixels_squared
        if covariance is not None:
            covariance_xx, covariance_xy, covariance_yy = covariance
            if not all(isfinite(value) for value in covariance):
                raise ValueError("noise correlation covariance must be finite")
            if (
                covariance_xx <= 0
                or covariance_yy <= 0
                or covariance_xx * covariance_yy
                - covariance_xy * covariance_xy
                <= 0
            ):
                raise ValueError(
                    "noise correlation covariance must be positive definite"
                )


@dataclass(frozen=True, slots=True)
class MomentTarget:
    """Canonical island or deblended-region measurement identity."""

    object_kind: Literal["island", "deblended-region"]
    object_id: str
    island_id: str
    pixel_count: int


@dataclass(frozen=True, slots=True)
class OwnedPixelPhotometry:
    """Finite owned-pixel photometry distinct from a fitted Gaussian."""

    peak_brightness_jy_per_beam: float
    peak_position_xy: tuple[int, int]
    owned_pixel_integrated_flux_jy: float
    local_rms_jy_per_beam: float
    mean_brightness_jy_per_beam: float


@dataclass(frozen=True, slots=True)
class GaussianMomentInitializer:
    """Brightness-weighted pixel-space initializer for nonlinear fitting."""

    amplitude_jy_per_beam: float
    centroid_xy: tuple[float, float]
    covariance_xx_pixels_squared: float
    covariance_xy_pixels_squared: float
    covariance_yy_pixels_squared: float
    major_sigma_pixels: float
    minor_sigma_pixels: float
    major_axis_angle_degrees: float


@dataclass(frozen=True, slots=True)
class ValidMomentMeasurement:
    """Complete owned-pixel photometry and nonsingular shape initializer."""

    target: MomentTarget
    photometry: OwnedPixelPhotometry
    initializer: GaussianMomentInitializer
    status: Literal["valid"] = "valid"


@dataclass(frozen=True, slots=True)
class ShapeUnavailableMomentMeasurement:
    """Valid photometry whose pixel support cannot define a 2-D ellipse."""

    target: MomentTarget
    photometry: OwnedPixelPhotometry
    reason: Literal["underdetermined-region", "singular-covariance"]
    status: Literal["shape-unavailable"] = "shape-unavailable"


@dataclass(frozen=True, slots=True)
class UnavailableMomentMeasurement:
    """A target for which valid photometry cannot be reported."""

    target: MomentTarget
    reason: Literal[
        "non-finite-owned-pixels",
        "non-positive-measurement",
    ]
    status: Literal["unavailable"] = "unavailable"


CompactMomentMeasurement: TypeAlias = (
    ValidMomentMeasurement
    | ShapeUnavailableMomentMeasurement
    | UnavailableMomentMeasurement
)
