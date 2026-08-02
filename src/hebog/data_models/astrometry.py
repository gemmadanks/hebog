"""Compact celestial transformation and beam-deconvolution records."""

from __future__ import annotations

from dataclasses import dataclass
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
    """Resolved shape or explicit absence after beam covariance removal."""

    status: Literal["resolved", "unresolved", "unavailable"]
    shape: GaussianShape | None
    quality_flags: tuple[
        Literal["resolved", "unresolved", "marginal-deconvolution"],
        ...,
    ]


@dataclass(frozen=True, slots=True)
class CelestialCompactGaussianFit:
    """One valid compact fit transformed to reviewed catalogue meanings."""

    pixel_fit: ValidCompactGaussianFit
    position: SkyPosition
    flux: FluxMeasurement
    fitted_shape: GaussianShape
    deconvolution_status: Literal["resolved", "unresolved", "unavailable"]
    deconvolved_shape: GaussianShape | None
    quality_flags: tuple[str, ...]
