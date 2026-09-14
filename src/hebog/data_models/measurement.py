"""Compact scheduler-safe scientific measurement records."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal, TypeAlias

from hebog.data_models.partitioning import ImageBounds

_HALF_CIRCLE_DEGREES = 180.0


@dataclass(frozen=True, slots=True)
class CompactMeasurementGeometry:
    """Reviewed local solid angles and noise correlation for compact fits."""

    pixel_solid_angle_steradians: float
    restoring_beam_solid_angle_steradians: float
    restoring_beam_covariance_pixels_squared: (
        tuple[float, float, float] | None
    ) = None
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
        covariances = (
            (
                "restoring beam covariance",
                self.restoring_beam_covariance_pixels_squared,
            ),
            (
                "noise correlation covariance",
                self.noise_correlation_covariance_pixels_squared,
            ),
        )
        for name, covariance in covariances:
            if covariance is None:
                continue
            covariance_xx, covariance_xy, covariance_yy = covariance
            if not all(isfinite(value) for value in covariance):
                raise ValueError(f"{name} must be finite")
            if (
                covariance_xx <= 0
                or covariance_yy <= 0
                or covariance_xx * covariance_yy
                - covariance_xy * covariance_xy
                <= 0
            ):
                raise ValueError(f"{name} must be positive definite")


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


@dataclass(frozen=True, slots=True)
class ExtendedMeasurementGeometry:
    """Physical pixel/beam conversion and sampled restoring-beam shape."""

    pixel_solid_angle_steradians: float
    restoring_beam_solid_angle_steradians: float
    restoring_beam_major_fwhm_pixels: float
    restoring_beam_minor_fwhm_pixels: float
    restoring_beam_position_angle_degrees: float

    def __post_init__(self) -> None:
        """Require finite positive areas and an ordered sampled beam."""
        positive = (
            self.pixel_solid_angle_steradians,
            self.restoring_beam_solid_angle_steradians,
            self.restoring_beam_major_fwhm_pixels,
            self.restoring_beam_minor_fwhm_pixels,
        )
        if any(not isfinite(value) or value <= 0 for value in positive):
            raise ValueError(
                "extended measurement pixel and beam values must be finite "
                "and positive"
            )
        if (
            self.restoring_beam_minor_fwhm_pixels
            > self.restoring_beam_major_fwhm_pixels
        ):
            raise ValueError("restoring beam minor axis cannot exceed major")
        angle = self.restoring_beam_position_angle_degrees
        if not isfinite(angle) or not 0 <= angle < _HALF_CIRCLE_DEGREES:
            raise ValueError(
                "restoring beam position angle must be within [0, 180)"
            )

    @property
    def pixel_to_beam_area_ratio(self) -> float:
        """Return the conversion from summed Jy/beam pixels to Jy."""
        return (
            self.pixel_solid_angle_steradians
            / self.restoring_beam_solid_angle_steradians
        )


@dataclass(frozen=True, slots=True)
class ExtendedEmissionTarget:
    """Canonical exact support to measure before cross-scale association."""

    object_kind: Literal["deferred-island", "multiscale-detection"]
    object_id: str
    parent_island_id: str | None
    support_pixel_count: int
    bounds: ImageBounds

    def __post_init__(self) -> None:
        """Require a non-empty support that fits its reconciled bounds."""
        if self.object_kind not in {
            "deferred-island",
            "multiscale-detection",
        }:
            raise ValueError("extended measurement object kind is unsupported")
        if not self.object_id:
            raise ValueError("extended measurement object ID cannot be empty")
        if self.parent_island_id == "":
            raise ValueError("extended parent island ID cannot be empty")
        bounds_pixels = self.bounds.shape_yx[0] * self.bounds.shape_yx[1]
        if not 0 < self.support_pixel_count <= bounds_pixels:
            raise ValueError(
                "extended support pixel count must fit inside its bounds"
            )


@dataclass(frozen=True, slots=True)
class ExtendedMeasurementTruncation:
    """Observable aperture coverage and explicit truncation disposition."""

    status: Literal[
        "none",
        "image-edge",
        "invalid-pixels",
        "image-edge-and-invalid-pixels",
    ]
    observable_aperture_fraction: float

    def __post_init__(self) -> None:
        """Require a finite fraction of the in-image aperture."""
        if (
            not isfinite(self.observable_aperture_fraction)
            or not 0 <= self.observable_aperture_fraction <= 1
        ):
            raise ValueError(
                "observable aperture fraction must be finite and in [0, 1]"
            )
        invalid = self.observable_aperture_fraction < 1
        if invalid != (
            self.status in {"invalid-pixels", "image-edge-and-invalid-pixels"}
        ):
            raise ValueError(
                "truncation status must match observable aperture fraction"
            )


@dataclass(frozen=True, slots=True)
class ExtendedEmissionPhotometry:
    """Original-pixel aperture photometry and prepared field summaries."""

    peak_brightness_jy_per_beam: float
    integrated_flux_jy: float
    integrated_flux_error_jy: float
    local_rms_jy_per_beam: float
    mean_background_jy_per_beam: float
    aperture_pixel_count: int
    observable_aperture_pixel_count: int

    def __post_init__(self) -> None:
        """Require a finite positive measured flux and honest pixel counts."""
        positive = (
            self.peak_brightness_jy_per_beam,
            self.integrated_flux_jy,
            self.local_rms_jy_per_beam,
        )
        if any(not isfinite(value) or value <= 0 for value in positive):
            raise ValueError(
                "extended peak, integrated flux, and RMS must be positive"
            )
        if (
            not isfinite(self.integrated_flux_error_jy)
            or self.integrated_flux_error_jy < 0
        ):
            raise ValueError("extended flux error must be finite and >= 0")
        if not isfinite(self.mean_background_jy_per_beam):
            raise ValueError("extended mean background must be finite")
        if not (
            0
            < self.observable_aperture_pixel_count
            <= self.aperture_pixel_count
        ):
            raise ValueError(
                "observable aperture count must fit its declared aperture"
            )


@dataclass(frozen=True, slots=True)
class ExtendedMomentShape:
    """Brightness-weighted extended shape on exact accepted support."""

    covariance_xx_pixels_squared: float
    covariance_xy_pixels_squared: float
    covariance_yy_pixels_squared: float
    major_fwhm_pixels: float
    minor_fwhm_pixels: float
    position_angle_degrees: float

    def __post_init__(self) -> None:
        """Require a finite positive-definite ordered moment ellipse."""
        values = (
            self.covariance_xx_pixels_squared,
            self.covariance_xy_pixels_squared,
            self.covariance_yy_pixels_squared,
            self.major_fwhm_pixels,
            self.minor_fwhm_pixels,
            self.position_angle_degrees,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("extended shape values must be finite")
        if (
            self.covariance_xx_pixels_squared <= 0
            or self.covariance_yy_pixels_squared <= 0
            or self.covariance_xx_pixels_squared
            * self.covariance_yy_pixels_squared
            - self.covariance_xy_pixels_squared**2
            <= 0
        ):
            raise ValueError("extended shape covariance must be positive")
        if (
            self.minor_fwhm_pixels <= 0
            or self.major_fwhm_pixels < self.minor_fwhm_pixels
        ):
            raise ValueError(
                "extended shape axes must be positive and ordered"
            )
        if not 0 <= self.position_angle_degrees < _HALF_CIRCLE_DEGREES:
            raise ValueError(
                "extended shape position angle must be within [0, 180)"
            )


@dataclass(frozen=True, slots=True)
class MeasuredExtendedEmission:
    """Complete observable-domain extended measurement before association."""

    target: ExtendedEmissionTarget
    photometry: ExtendedEmissionPhotometry
    centroid_xy: tuple[float, float]
    peak_position_xy: tuple[int, int]
    shape: ExtendedMomentShape | None
    shape_status: Literal["available", "unavailable"]
    shape_unavailable_reason: (
        Literal[
            "underdetermined-support",
            "singular-covariance",
        ]
        | None
    )
    truncation: ExtendedMeasurementTruncation
    position_weight_kind: Literal[
        "direct-original-residual",
        "regularized-direct-plus-multiscale",
    ]
    flux_uncertainty_status: Literal[
        "available-correlated-beam-approximation"
    ] = "available-correlated-beam-approximation"
    position_uncertainty_status: Literal[
        "unavailable-support-selection-not-propagated"
    ] = "unavailable-support-selection-not-propagated"
    shape_uncertainty_status: Literal[
        "unavailable-support-selection-not-propagated"
    ] = "unavailable-support-selection-not-propagated"
    status: Literal["measured"] = "measured"

    def __post_init__(self) -> None:
        """Keep position and shape availability internally consistent."""
        if not all(
            isfinite(value) and value >= 0 for value in self.centroid_xy
        ):
            raise ValueError(
                "extended centroid must be finite and non-negative"
            )
        if min(self.peak_position_xy) < 0:
            raise ValueError("extended peak position must be non-negative")
        available = self.shape is not None
        if available != (self.shape_status == "available"):
            raise ValueError(
                "extended shape status must match shape availability"
            )
        if available != (self.shape_unavailable_reason is None):
            raise ValueError(
                "extended shape reason must match shape availability"
            )


@dataclass(frozen=True, slots=True)
class UnavailableExtendedEmission:
    """Extended target whose original pixels cannot support a measurement."""

    target: ExtendedEmissionTarget
    reason: Literal[
        "non-finite-support",
        "non-positive-support-flux",
        "non-positive-aperture-flux",
    ]
    truncation: ExtendedMeasurementTruncation
    centroid_xy: None = None
    peak_position_xy: None = None
    integrated_flux_jy: None = None
    flux_uncertainty_status: Literal["unavailable"] = "unavailable"
    position_uncertainty_status: Literal["unavailable"] = "unavailable"
    shape_uncertainty_status: Literal["unavailable"] = "unavailable"
    status: Literal["unavailable"] = "unavailable"


ExtendedEmissionMeasurementResult: TypeAlias = (
    MeasuredExtendedEmission | UnavailableExtendedEmission
)
