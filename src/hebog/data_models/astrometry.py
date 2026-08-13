"""Compact celestial transformation and beam-deconvolution records."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from hebog.data_models.catalogues import (
    FluxMeasurement,
    GaussianShape,
    SkyPosition,
)
from hebog.data_models.fitting import ValidCompactGaussianFit


@dataclass(frozen=True, slots=True)
class LocalTangentPlaneTransform:
    """ICRS center and local east/north Jacobian for pixel `(x, y)`."""

    position: SkyPosition
    jacobian_degrees_per_pixel: tuple[
        tuple[float, float],
        tuple[float, float],
    ]


@dataclass(frozen=True, slots=True)
class GaussianDeconvolution:
    """Identifiable axes or explicit absence after beam removal."""

    status: Literal[
        "resolved",
        "major-axis-only",
        "unresolved",
        "unavailable",
    ]
    shape: GaussianShape | None
    quality_flags: tuple[
        Literal[
            "deconvolution-uncertainty-unavailable",
            "extension-not-significant",
            "major-axis-not-significant",
            "major-axis-only",
            "marginal-deconvolution",
            "minor-axis-not-significant",
            "resolved",
            "unresolved",
        ],
        ...,
    ]
    major_axis_fwhm_degrees: float | None = None

    def __post_init__(self) -> None:
        """Keep full, one-axis, and absent states unambiguous."""
        if self.status == "resolved":
            if self.shape is None or self.major_axis_fwhm_degrees is not None:
                raise ValueError("resolved deconvolution requires an ellipse")
        elif self.status == "major-axis-only":
            if (
                self.shape is not None
                or self.major_axis_fwhm_degrees is None
                or not isfinite(self.major_axis_fwhm_degrees)
                or self.major_axis_fwhm_degrees <= 0
            ):
                raise ValueError(
                    "major-axis-only deconvolution requires one positive axis"
                )
        elif (
            self.shape is not None or self.major_axis_fwhm_degrees is not None
        ):
            raise ValueError("absent deconvolution cannot contain an axis")


@dataclass(frozen=True, slots=True)
class CelestialCompactGaussianFit:
    """One valid compact fit transformed to reviewed catalogue meanings."""

    pixel_fit: ValidCompactGaussianFit
    position: SkyPosition
    flux: FluxMeasurement
    fitted_flux: FluxMeasurement
    fitted_shape: GaussianShape
    deconvolution_status: Literal[
        "resolved",
        "major-axis-only",
        "unresolved",
        "unavailable",
    ]
    deconvolved_shape: GaussianShape | None
    deconvolved_major_fwhm_degrees: float | None
    quality_flags: tuple[str, ...]
