# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Bounded FITS image input for radio-continuum planes."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

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
# FITS WCS Paper III Stokes codes: I, Q, U, V, then circular and linear
# instrumental products.
_STOKES_NAMES = {
    1: "I",
    2: "Q",
    3: "U",
    4: "V",
    -1: "RR",
    -2: "LL",
    -3: "RL",
    -4: "LR",
    -5: "XX",
    -6: "YY",
    -7: "XY",
    -8: "YX",
}
# Primary linear-transform matrix keywords, in current and AIPS-era spelling.
_LINEAR_MATRIX_KEYWORD = re.compile(r"(PC|CD)(\d+_\d+|\d{6})")


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


def _brightness_unit(
    header: Any,
    path: Path,
    supplied: SuppliedImageMetadata | None,
) -> str:
    """Read BUNIT, or the supplied unit when the header has none."""
    header_value = header.get("BUNIT")
    if isinstance(header_value, str) and not header_value.strip():
        header_value = None
    supplied_value = None if supplied is None else supplied.brightness_unit
    if header_value is not None and supplied_value is not None:
        raise InvalidFitsImageError(
            f"supplied BUNIT duplicates the FITS header value: {path}"
        )
    unit_value = header_value if header_value is not None else supplied_value
    if unit_value is None:
        raise InvalidFitsImageError(
            "FITS image requires a non-empty BUNIT, or a supplied brightness "
            f"unit: {path}"
        )
    if not isinstance(unit_value, str):
        raise InvalidFitsImageError(
            f"FITS image has an invalid BUNIT {unit_value!r}: {path}"
        )
    return _canonical_image_unit(unit_value, path)


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
            "FITS image requires BMAJ, BMIN, and BPA restoring beam, or "
            f"supplied values for those it omits: {path}"
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


def _rotation_degrees(header: Any, axis: int, path: Path) -> float:
    """Read one axis's optional legacy ``CROTA`` rotation in degrees."""
    keyword = f"CROTA{axis}"
    try:
        rotation = float(header.get(keyword, 0.0))
    except (TypeError, ValueError) as error:
        raise InvalidFitsImageError(
            f"FITS image has an invalid {keyword}: {path}"
        ) from error
    if not np.isfinite(rotation):
        raise InvalidFitsImageError(
            f"FITS image has an invalid {keyword}: {path}"
        )
    return rotation


def _require_one_rotation(header: Any, image_wcs: WCS, path: Path) -> None:
    """Refuse a rotation that the WCS standard would silently discard.

    The standard reads ``CROTAi`` from the latitude axis only, and only when
    no ``PCi_j`` or ``CDi_j`` matrix is present. Astropy follows it without a
    warning, so a rotation given on the longitude axis alone, or beside a
    matrix, would be read as a different orientation and misplace every
    catalogue position. A zero rotation, or equal rotations on both axes as
    AIPS writes them, is unambiguous.
    """
    longitude_axis = image_wcs.wcs.lng + 1
    latitude_axis = image_wcs.wcs.lat + 1
    longitude = _rotation_degrees(header, longitude_axis, path)
    latitude = _rotation_degrees(header, latitude_axis, path)
    if longitude not in (0.0, latitude):
        raise InvalidFitsImageError(
            f"FITS image rotates its longitude axis (CROTA{longitude_axis} = "
            f"{longitude:g}) differently from its latitude axis "
            f"(CROTA{latitude_axis} = {latitude:g}); the WCS standard reads "
            f"only CROTA{latitude_axis}, so the orientation is ambiguous: "
            f"{path}"
        )
    if latitude != 0.0 and any(
        _LINEAR_MATRIX_KEYWORD.fullmatch(keyword) for keyword in header
    ):
        raise InvalidFitsImageError(
            f"FITS image gives both CROTA{latitude_axis} and a PC or CD "
            "matrix; the WCS standard ignores CROTA when a matrix is "
            f"present, so the orientation is ambiguous: {path}"
        )


def _require_total_intensity(image_wcs: WCS, path: Path) -> None:
    """Refuse a plane whose Stokes axis selects anything but Stokes I.

    The public finder measures total intensity; a Q, U, V or instrumental
    polarisation plane would be measured as if it were one. The value is the
    Stokes axis's world coordinate at the plane's single pixel, which also
    reads writers that encode the parameter through ``CRPIX`` rather than
    ``CRVAL``.
    """
    stokes_axes = [
        axis
        for axis, axis_type in enumerate(image_wcs.wcs.ctype)
        if axis_type.strip().upper() == "STOKES"
    ]
    if not stokes_axes:
        return
    world = image_wcs.wcs_pix2world([[0.0] * image_wcs.naxis], 0)[0]
    for axis in stokes_axes:
        code = round(float(world[axis]))
        if code != 1:
            name = _STOKES_NAMES.get(code, f"code {code}")
            raise UnsupportedFitsImageError(
                f"FITS image plane is Stokes {name}, and the public finder "
                f"measures Stokes I only: {path}"
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
            "FITS image requires a reference frequency in RESTFRQ, RESTFREQ "
            f"or a FREQ axis, or a supplied one: {path}"
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
    cube_axes = [
        f"{primary_hdu.header.get(f'CTYPE{axis}', 'untyped')} "
        f"(NAXIS{axis} = {dimension})"
        for axis, dimension in zip(
            range(len(shape), 2, -1), shape[:-2], strict=True
        )
        if dimension != 1
    ]
    if cube_axes:
        listed = ", ".join(cube_axes)
        raise UnsupportedFitsImageError(
            f"FITS image has non-singleton leading axes, {listed}; "
            "the public finder reads one plane, so channel, Stokes, and other "
            f"cubes require an explicit contract: {path}"
        )
    shape_yx = (shape[-2], shape[-1])
    if min(shape_yx) < 1:
        raise InvalidFitsImageError(
            f"FITS image plane must be non-empty: {path}"
        )
    unit = _brightness_unit(primary_hdu.header, path, supplied)
    header_frequency_hz = _header_reference_frequency_hz(
        primary_hdu.header,
        path,
    )
    beam = _restoring_beam(primary_hdu.header, path, supplied)
    image_wcs, celestial_wcs = _celestial_wcs(primary_hdu.header, path)
    _require_one_rotation(primary_hdu.header, image_wcs, path)
    _require_total_intensity(image_wcs, path)
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
        self._metadata: ImageMetadata | None = None
        self._open_files: dict[int, Any] = {}
        self._open_files_lock = threading.Lock()

    def __getstate__(self) -> dict[str, Any]:
        """Serialize the request to read a file, never what it once held.

        A worker opens the file itself, so neither an open file nor
        validated metadata travels with the source: an open file cannot
        cross a process, and metadata could go stale in transit.
        """
        return {
            "_path": self._path,
            "_supplied_metadata": self._supplied_metadata,
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore a source that has not yet read its file."""
        self.__init__(  # pyright: ignore[reportUnknownMemberType]
            state["_path"], state["_supplied_metadata"]
        )

    def _primary_hdu(self) -> Any:
        """Return this file's primary HDU, opening it once per thread.

        Opening a FITS file and parsing its header costs several times a
        bounded window read, and tiled stages read hundreds of windows per
        image. Each thread keeps its own open file, because worker threads
        share a source and a file cursor cannot be shared.

        Raises:
            InvalidFitsImageError: If the file cannot be opened.
        """
        thread = threading.get_ident()
        hdus = self._open_files.get(thread)
        if hdus is None:
            try:
                hdus = fits.open(self._path, mode="readonly", memmap=True)
            except (OSError, ValueError) as error:
                raise InvalidFitsImageError(
                    f"cannot read FITS image {self._path}: {error}"
                ) from error
            with self._open_files_lock:
                self._open_files[thread] = hdus
        return hdus[0]

    def close(self) -> None:
        """Release every file this source holds open.

        Worker threads each open the file, so one close frees them all. The
        source stays usable and opens the file again when it is next read.
        """
        with self._open_files_lock:
            open_files, self._open_files = self._open_files, {}
        for hdus in open_files.values():
            hdus.close()

    def __del__(self) -> None:
        """Release open files when the last reference goes away.

        Callers that simply drop a source, as scripts and workers do, would
        otherwise leave the file to the garbage collector, which reports it
        as an unclosed file.
        """
        self.close()

    def metadata(self) -> ImageMetadata:
        """Return shape and unit without materialising the image plane.

        A source validates one file once: tiled stages read hundreds of
        windows, and re-parsing the header and rebuilding both WCS objects
        for each of them costs more than reading the pixels.
        """
        if self._metadata is None:
            self._metadata = _metadata(
                self._primary_hdu(), self._path, self._supplied_metadata
            )
        return self._metadata

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
        metadata = self.metadata()
        primary_hdu = self._primary_hdu()
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
