"""Small serializable scientific image metadata."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True, slots=True)
class RestoringBeam:
    """Elliptical restoring-beam full widths and position angle in degrees."""

    major_fwhm_degrees: float
    minor_fwhm_degrees: float
    position_angle_degrees: float

    def __post_init__(self) -> None:
        """Require finite positive ordered beam axes."""
        if not all(
            isfinite(value)
            for value in (
                self.major_fwhm_degrees,
                self.minor_fwhm_degrees,
                self.position_angle_degrees,
            )
        ):
            raise ValueError("restoring beam values must be finite")
        if self.major_fwhm_degrees <= 0 or self.minor_fwhm_degrees <= 0:
            raise ValueError("restoring beam axes must be positive")
        if self.minor_fwhm_degrees > self.major_fwhm_degrees:
            raise ValueError("restoring beam minor axis cannot exceed major")


@dataclass(frozen=True, slots=True)
class CelestialWcs:
    """Canonical FITS celestial-WCS cards and their coordinate-frame name."""

    fits_header: str
    coordinate_frame: str

    def __post_init__(self) -> None:
        """Require enough metadata to reconstruct and interpret the WCS."""
        if not self.fits_header or not self.coordinate_frame:
            raise ValueError(
                "celestial WCS header and coordinate frame must not be empty"
            )


@dataclass(frozen=True, slots=True)
class ImageMetadata:
    """Scientific metadata required to interpret one logical image plane."""

    shape_yx: tuple[int, int]
    unit: str
    beam: RestoringBeam
    celestial_wcs: CelestialWcs
    reference_frequency_hz: float
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None:
        """Reject unsupported versions and incomplete physical metadata."""
        if self.schema_version != 1:
            raise ValueError("unsupported image metadata schema version")
        if min(self.shape_yx) < 1:
            raise ValueError(
                "image metadata shape dimensions must be positive"
            )
        if not self.unit:
            raise ValueError("image metadata unit must not be empty")
        if (
            not isfinite(self.reference_frequency_hz)
            or self.reference_frequency_hz <= 0
        ):
            raise ValueError(
                "image metadata reference frequency must be finite and "
                "positive"
            )
