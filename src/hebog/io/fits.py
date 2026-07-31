# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Bounded FITS image input for radio-continuum planes."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import numpy as np
from astropy import units
from astropy.io import fits

from hebog.io.base import ImageBounds, ImageMetadata, ImageWindow

_LOGICAL_DIMENSIONS = 2


class InvalidFitsImageError(ValueError):
    """A FITS input is missing required structural or physical metadata."""


class UnsupportedFitsImageError(InvalidFitsImageError):
    """A valid FITS input uses an image layout Hebog does not yet support."""


def _metadata(primary_hdu: Any, path: Path) -> ImageMetadata:
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
    unit = unit_value.strip()
    try:
        units.Unit(unit)
    except ValueError as error:
        raise InvalidFitsImageError(
            f"FITS image has an invalid BUNIT {unit!r}: {path}"
        ) from error
    return ImageMetadata(shape_yx=shape_yx, unit=unit)


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
    """Read validated logical image planes through bounded FITS sections."""

    def __init__(self, path: Path) -> None:
        """Retain only the path; opening and pixel access remain explicit."""
        self._path = path

    def metadata(self) -> ImageMetadata:
        """Return shape and unit without materialising the image plane."""
        with _open_primary(self._path) as primary_hdu:
            return _metadata(primary_hdu, self._path)

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one half-open global window into owned read-only arrays."""
        with _open_primary(self._path) as primary_hdu:
            metadata = _metadata(primary_hdu, self._path)
            bounds.require_inside(metadata.shape_yx)
            leading_indices = (0,) * (len(primary_hdu.shape) - 2)
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
        return ImageWindow(
            bounds=bounds,
            values=values,
            valid_pixels=valid_pixels,
        )
