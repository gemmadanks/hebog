# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Bounded FITS image input for radio-continuum planes."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import numpy as np
from astropy import units
from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import wcs_to_celestial_frame

from hebog.data_models.images import (
    CelestialWcs,
    ImageMetadata,
    RestoringBeam,
    SuppliedImageMetadata,
)
from hebog.io.base import ImageBounds, ImageWindow

_LOGICAL_DIMENSIONS = 2
_COMMON_IMAGE_UNIT_ALIASES = {
    "JY/BEAM": "Jy/beam",
    "JYBEAM-1": "Jy/beam",
}


class InvalidFitsImageError(ValueError):
    """A FITS input is missing required structural or physical metadata."""


class UnsupportedFitsImageError(InvalidFitsImageError):
    """A valid FITS input uses an image layout Hebog does not yet support."""


def _canonical_image_unit(unit_value: str, path: Path) -> str:
    """Validate BUNIT and normalize common case-insensitive radio aliases."""
    unit = unit_value.strip()
    compact_upper = "".join(unit.split()).upper()
    canonical = _COMMON_IMAGE_UNIT_ALIASES.get(compact_upper, unit)
    try:
        units.Unit(canonical)
    except ValueError as error:
        raise InvalidFitsImageError(
            f"FITS image has an invalid BUNIT {unit!r}: {path}"
        ) from error
    return canonical


def _restoring_beam(
    header: Any,
    path: Path,
    supplied: SuppliedImageMetadata | None,
) -> RestoringBeam:
    """Read restoring-beam keywords in degrees, filling only missing ones."""
    supplied_values = (
        (None, None, None)
        if supplied is None
        else (
            supplied.beam_major_fwhm_degrees,
            supplied.beam_minor_fwhm_degrees,
            supplied.beam_position_angle_degrees,
        )
    )
    raw_values: list[Any] = []
    for keyword, supplied_value in zip(
        ("BMAJ", "BMIN", "BPA"), supplied_values, strict=True
    ):
        header_value = header.get(keyword)
        if header_value is not None and supplied_value is not None:
            raise InvalidFitsImageError(
                f"supplied {keyword} duplicates the FITS header value: {path}"
            )
        raw_values.append(
            header_value if header_value is not None else supplied_value
        )
    if any(value is None for value in raw_values):
        raise InvalidFitsImageError(
            f"FITS image requires BMAJ, BMIN, and BPA restoring beam: {path}"
        )
    try:
        return RestoringBeam(*(float(value) for value in raw_values))
    except (TypeError, ValueError) as error:
        raise InvalidFitsImageError(
            f"FITS image has an invalid restoring beam: {path}"
        ) from error


def _celestial_wcs(header: Any, path: Path) -> tuple[WCS, CelestialWcs]:
    """Validate and serialize the celestial part of an image WCS."""
    try:
        image_wcs = WCS(header, relax=True)
        celestial_wcs = image_wcs.celestial
        if not celestial_wcs.has_celestial:
            raise ValueError("no celestial axes")
        frame = wcs_to_celestial_frame(celestial_wcs)
        celestial_header = celestial_wcs.to_header(relax=True).tostring(
            sep="\n",
            endcard=False,
            padding=False,
        )
    except (TypeError, ValueError) as error:
        raise InvalidFitsImageError(
            f"FITS image requires a valid two-axis celestial WCS: {path}"
        ) from error
    return image_wcs, CelestialWcs(
        fits_header=celestial_header,
        coordinate_frame=str(frame.name),
    )


def _positive_frequency_hz(raw_frequency: Any, path: Path) -> float:
    """Validate and normalize one candidate reference frequency."""
    try:
        frequency_hz = float(raw_frequency)
    except (TypeError, ValueError) as error:
        raise InvalidFitsImageError(
            f"FITS image requires a reference frequency: {path}"
        ) from error
    if not np.isfinite(frequency_hz) or frequency_hz <= 0:
        raise InvalidFitsImageError(
            "FITS image reference frequency must be finite and positive: "
            f"{path}"
        )
    return frequency_hz


def _header_reference_frequency_hz(
    header: Any,
    path: Path,
) -> float | None:
    """Read an optional RESTFRQ or RESTFREQ before WCS parsing."""
    raw_frequency = header.get("RESTFRQ", header.get("RESTFREQ"))
    if raw_frequency is None:
        return None
    return _positive_frequency_hz(raw_frequency, path)


def _wcs_reference_frequency_hz(image_wcs: WCS, path: Path) -> float | None:
    """Read reference frequency from the first explicit WCS frequency axis."""
    for axis_index, physical_type in enumerate(
        image_wcs.world_axis_physical_types
    ):
        if physical_type == "em.freq":
            axis_unit = image_wcs.world_axis_units[axis_index] or "Hz"
            raw_frequency = (
                float(image_wcs.wcs.crval[axis_index]) * units.Unit(axis_unit)
            ).to_value(units.Hz)
            return _positive_frequency_hz(raw_frequency, path)
    return None


def _reference_frequency_hz(
    header_frequency_hz: float | None,
    supplied: SuppliedImageMetadata | None,
    path: Path,
) -> float:
    """Use the header frequency, or a supplied one when the header has none."""
    supplied_frequency_hz = (
        None if supplied is None else supplied.reference_frequency_hz
    )
    if header_frequency_hz is not None and supplied_frequency_hz is not None:
        raise InvalidFitsImageError(
            "supplied reference frequency duplicates the FITS header value: "
            f"{path}"
        )
    frequency_hz = (
        header_frequency_hz
        if header_frequency_hz is not None
        else supplied_frequency_hz
    )
    if frequency_hz is None:
        raise InvalidFitsImageError(
            f"FITS image requires a reference frequency: {path}"
        )
    return frequency_hz


def _metadata(
    primary_hdu: Any,
    path: Path,
    supplied: SuppliedImageMetadata | None = None,
) -> ImageMetadata:
    """Validate one primary image HDU without loading its pixel plane."""
    raw_shape = primary_hdu.shape
    if not raw_shape:
        raise InvalidFitsImageError(
            f"FITS image contains no image data: {path}"
        )
    shape = tuple(int(dimension) for dimension in raw_shape)
    if len(shape) < _LOGICAL_DIMENSIONS:
        raise UnsupportedFitsImageError(
            f"FITS image must have at least two axes: {path}"
        )
    if any(dimension != 1 for dimension in shape[:-2]):
        raise UnsupportedFitsImageError(
            "FITS image has non-singleton leading axes; channel, Stokes, "
            f"and other cubes require an explicit contract: {path}"
        )
    shape_yx = (shape[-2], shape[-1])
    if min(shape_yx) < 1:
        raise InvalidFitsImageError(
            f"FITS image plane must be non-empty: {path}"
        )
    unit_value = primary_hdu.header.get("BUNIT")
    if not isinstance(unit_value, str) or not unit_value.strip():
        raise InvalidFitsImageError(
            f"FITS image requires a non-empty BUNIT: {path}"
        )
    unit = _canonical_image_unit(unit_value, path)
    header_frequency_hz = _header_reference_frequency_hz(
        primary_hdu.header,
        path,
    )
    beam = _restoring_beam(primary_hdu.header, path, supplied)
    image_wcs, celestial_wcs = _celestial_wcs(primary_hdu.header, path)
    if header_frequency_hz is None:
        header_frequency_hz = _wcs_reference_frequency_hz(image_wcs, path)
    return ImageMetadata(
        shape_yx=shape_yx,
        unit=unit,
        beam=beam,
        celestial_wcs=celestial_wcs,
        reference_frequency_hz=_reference_frequency_hz(
            header_frequency_hz, supplied, path
        ),
    )


@contextmanager
def _open_primary(path: Path) -> Generator[Any, None, None]:
    """Open one FITS file lazily and translate low-level read failures."""
    try:
        hdus = fits.open(path, mode="readonly", memmap=True)
    except (OSError, ValueError) as error:
        raise InvalidFitsImageError(
            f"cannot read FITS image {path}: {error}"
        ) from error
    try:
        yield hdus[0]
    finally:
        hdus.close()


class FitsImageSource:
    """Read validated logical image planes through bounded FITS sections.

    Optional supplied metadata fills keywords the header omits. It is part of
    the source, so every executor task that re-reads the header sees it.
    """

    def __init__(
        self,
        path: Path,
        supplied_metadata: SuppliedImageMetadata | None = None,
    ) -> None:
        """Retain the path and supplied metadata; open files only on use."""
        self._path = path
        self._supplied_metadata = supplied_metadata

    def metadata(self) -> ImageMetadata:
        """Return shape and unit without materialising the image plane."""
        with _open_primary(self._path) as primary_hdu:
            return _metadata(primary_hdu, self._path, self._supplied_metadata)

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one half-open global window into owned read-only arrays."""
        return self.read_windows((bounds,))[0]

    def read_windows(
        self,
        bounds_collection: Iterable[ImageBounds],
    ) -> tuple[ImageWindow, ...]:
        """Read bounded windows through one validated FITS open."""
        requested_bounds = tuple(bounds_collection)
        if not requested_bounds:
            return ()
        windows: list[ImageWindow] = []
        with _open_primary(self._path) as primary_hdu:
            metadata = _metadata(
                primary_hdu, self._path, self._supplied_metadata
            )
            leading_indices = (0,) * (len(primary_hdu.shape) - 2)
            for bounds in requested_bounds:
                bounds.require_inside(metadata.shape_yx)
                section = primary_hdu.section[
                    (
                        *leading_indices,
                        slice(bounds.y_start, bounds.y_stop),
                        slice(bounds.x_start, bounds.x_stop),
                    )
                ]
                values = np.array(section, dtype=np.float64, copy=True)
                valid_pixels = np.asarray(np.isfinite(values), dtype=np.bool_)
                values.setflags(write=False)
                valid_pixels.setflags(write=False)
                windows.append(
                    ImageWindow(
                        bounds=bounds,
                        values=values,
                        valid_pixels=valid_pixels,
                    )
                )
        return tuple(windows)


def celestial_wcs_from_metadata(metadata: ImageMetadata) -> WCS:
    """Reconstruct an independent Astropy WCS from serialized metadata."""
    header = fits.Header.fromstring(
        metadata.celestial_wcs.fits_header,
        sep="\n",
    )
    return WCS(header, relax=True).celestial
