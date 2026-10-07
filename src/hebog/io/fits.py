# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Bounded FITS image input for radio-continuum planes."""

from __future__ import annotations

import math
import re
import threading
import weakref
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
from hebog.io.pixel_validity import valid_input_pixels, validity_read_bounds

_LOGICAL_DIMENSIONS = 2
_COMMON_IMAGE_UNIT_ALIASES = {
    "JY/BEAM": "Jy/beam",
    "JYBEAM-1": "Jy/beam",
}
# Stokes codes of FITS WCS Paper I (Greisen & Calabretta 2002, table 7): I,
# Q, U, V, then circular and linear instrumental products.
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
# Stokes codes are integers; a world value may differ from one only by the
# rounding of the world transform.
_STOKES_CODE_TOLERANCE = 1e-6
# Celestial axis types whose frame Astropy names correctly.
_CELESTIAL_AXIS_TYPES = frozenset({("RA", "DEC"), ("GLON", "GLAT")})
# Primary linear-transform matrix keywords, in current and AIPS-era spelling.
_LINEAR_MATRIX_KEYWORD = re.compile(r"(PC|CD)(\d+_\d+|\d{6})")
# Numeric keywords of the primary WCS: the linear transform, the projection
# parameters in current and AIPS-era spelling, and the equinox that names the
# frame.
_WCS_NUMBER_KEYWORD = re.compile(
    r"(CRVAL|CRPIX|CDELT|CROTA|PROJP)\d+|PV\d+_\d+|LONPOLE|LATPOLE|EQUINOX|"
    r"EPOCH|" + _LINEAR_MATRIX_KEYWORD.pattern
)


class InvalidFitsImageError(ValueError):
    """A FITS input is missing required structural or physical metadata."""


class UnsupportedFitsImageError(InvalidFitsImageError):
    """A valid FITS input uses an image layout Hebog does not yet support."""


def _header_value(header: Any, keyword: str, path: Path) -> Any:
    """Read one optional card, refusing a value Astropy cannot parse.

    Text written without its quotes is the usual case: Astropy raises for
    it, where a caller needs to be told which card is at fault.
    """
    try:
        return header.get(keyword)
    except fits.VerifyError as error:
        raise InvalidFitsImageError(
            f"FITS image has a {keyword} card that cannot be parsed: {path}"
        ) from error


def _card_number(card: Any, path: Path) -> float | None:
    """Read one card that must hold a finite number, if it has a value.

    Returns ``None`` when the card has no value. Astropy and wcslib raise no
    error for a card that holds anything else: wcslib warns and reads the
    keyword's default in its place, and ``float`` reads a logical as one.
    Text, a logical, a complex value and a value Astropy cannot parse, such
    as ``NAN`` or a number followed by its unit, are therefore refused.
    """
    keyword = card.rawkeyword
    try:
        value = card.rawvalue
    except fits.VerifyError as error:
        raise InvalidFitsImageError(
            f"FITS image has a {keyword} card that is not a finite number: "
            f"{path}"
        ) from error
    if isinstance(value, fits.Undefined):
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
    ):
        raise InvalidFitsImageError(
            f"FITS image has a {keyword} card that is not a finite number, "
            f"{value!r}: {path}"
        )
    return float(value)


def _header_number(header: Any, keyword: str, path: Path) -> float | None:
    """Read the card of one numeric keyword, if the header has it."""
    if keyword not in header:
        return None
    return _card_number(header.cards[keyword], path)


def _float_value(card: Any) -> float | None:
    """Return the value of a card that holds a float, however it is spelled."""
    try:
        value = card.rawvalue
    except fits.VerifyError:
        return None
    return value if isinstance(value, float) and math.isfinite(value) else None


def _wcs_header(header: Any, path: Path) -> Any:
    """Return the header with each float written as wcslib reads it.

    wcslib parses the header text itself, and does not read every card as
    Astropy does. It warns and uses a keyword's default for a card it cannot
    read as a number, so a ``CRVAL1`` of ``'180.0'`` would place every
    source at right ascension zero; such a card of the WCS is refused. It
    stops reading a FITS ``D`` exponent at the letter, so ``1.8D2`` would be
    1.8; each float is therefore rewritten as Python prints it, which both
    libraries read as the float Astropy parsed. Astropy's own card
    formatting keeps 20 characters, which would shorten a double-precision
    ``CDELT``.

    Every card keeps its place and its own value, so wcslib still reads a
    repeated keyword as it did. A record-valued card holds text, and wcslib
    does not read a ``HIERARCH`` card; both stay as written.
    """
    cards: list[Any] = []
    for card in header.cards:
        keyword = card.rawkeyword
        if _WCS_NUMBER_KEYWORD.fullmatch(keyword):
            number = _card_number(card, path)
            if number is None:
                raise InvalidFitsImageError(
                    f"FITS image has a {keyword} card with no value: {path}"
                )
        else:
            number = _float_value(card)
        if number is None or str(card).startswith("HIERARCH"):
            cards.append(card)
        else:
            cards.append(
                fits.Card.fromstring(
                    f"{keyword:<8}= {repr(number).upper():>20}"
                )
            )
    return fits.Header(cards)


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
    header_value = _header_value(header, "BUNIT", path)
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
    if header_value is not None:
        return _canonical_image_unit(unit_value, path)
    try:
        return _canonical_image_unit(unit_value, path)
    except InvalidFitsImageError as error:
        raise InvalidFitsImageError(
            f"supplied brightness unit {unit_value!r} is not a unit: {path}"
        ) from error


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
        header_value = _header_number(header, keyword, path)
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


def _pixel_scaling(header: Any, path: Path) -> tuple[float, float, int | None]:
    """Read how stored pixels encode physical ones: scale, zero and blank.

    A physical value is ``BZERO + BSCALE * stored``, and a stored integer
    equal to ``BLANK`` is no pixel at all, so each card must be the number
    it should be. FITS gives ``BLANK`` no meaning on floating-point pixels,
    where NaN is the invalid value, so it is not read there.
    """
    scale = _header_number(header, "BSCALE", path)
    zero = _header_number(header, "BZERO", path)
    blank = None
    if header["BITPIX"] > 0:
        blank = _header_value(header, "BLANK", path)
        if blank is not None and (
            isinstance(blank, bool) or not isinstance(blank, int)
        ):
            raise InvalidFitsImageError(
                "FITS image has a BLANK card that is not an integer, "
                f"{blank!r}: {path}"
            )
    return (
        1.0 if scale is None else scale,
        0.0 if zero is None else zero,
        blank,
    )


def _require_readable_pixels(primary_hdu: Any, path: Path) -> None:
    """Refuse pixels that cannot be read as their header describes.

    A file that ends early still opens, and would fail only when a window
    reached the missing bytes. FITS pixels are stored in order, so a file
    that holds its last pixel holds them all.
    """
    _pixel_scaling(primary_hdu.header, path)
    last_pixel = tuple(slice(size - 1, size) for size in primary_hdu.shape)
    try:
        primary_hdu.section[last_pixel]
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise InvalidFitsImageError(
            "FITS image is truncated or unreadable: its last pixel cannot "
            f"be read: {path}"
        ) from error


def _celestial_wcs(header: Any, path: Path) -> tuple[WCS, CelestialWcs]:
    """Validate and serialize the celestial part of an image WCS.

    Only equatorial and Galactic axes are read. Astropy names the frame of
    other celestial axes wrongly or not at all: ecliptic ``ELON``/``ELAT``
    axes come back as ICRS, so their longitudes would be published as right
    ascensions.
    """
    wcs_header = _wcs_header(header, path)
    try:
        image_wcs = WCS(wcs_header, relax=True)
        celestial_wcs = image_wcs.celestial
        if not celestial_wcs.has_celestial:
            raise ValueError("no celestial axes")
    except (TypeError, ValueError) as error:
        raise InvalidFitsImageError(
            f"FITS image requires a valid two-axis celestial WCS: {path}"
        ) from error
    axis_types = (celestial_wcs.wcs.lngtyp, celestial_wcs.wcs.lattyp)
    if axis_types not in _CELESTIAL_AXIS_TYPES:
        raise UnsupportedFitsImageError(
            f"FITS image has {'/'.join(axis_types)} celestial axes, and the "
            f"finder reads RA/DEC or GLON/GLAT axes only: {path}"
        )
    try:
        frame = wcs_to_celestial_frame(celestial_wcs)
        celestial_header = celestial_wcs.to_header(relax=True).tostring(
            sep="\n",
            endcard=False,
            padding=False,
        )
    except (TypeError, ValueError) as error:
        raise InvalidFitsImageError(
            "FITS image has a celestial frame Astropy cannot name, RADESYS "
            f"{header.get('RADESYS')!r}: {path}"
        ) from error
    return image_wcs, CelestialWcs(
        fits_header=celestial_header,
        coordinate_frame=str(frame.name),
    )


def _require_one_rotation(header: Any, image_wcs: WCS, path: Path) -> None:
    """Refuse a rotation that the WCS standard would silently discard.

    The standard reads ``CROTAi`` from the latitude axis only, and only when
    no ``PCi_j`` or ``CDi_j`` matrix is present. Astropy follows it without a
    warning, so a rotation given on the longitude axis alone, or beside a
    matrix, would be read as a different orientation and misplace every
    catalogue position. A zero rotation, a rotation on the latitude axis
    alone, as AIPS and Obit write it, and equal rotations on both axes are
    unambiguous.
    """
    longitude_axis = image_wcs.wcs.lng + 1
    latitude_axis = image_wcs.wcs.lat + 1
    longitude = _header_number(header, f"CROTA{longitude_axis}", path) or 0.0
    latitude = _header_number(header, f"CROTA{latitude_axis}", path) or 0.0
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
        value = float(world[axis])
        if (
            not np.isfinite(value)
            or abs(value - round(value)) > _STOKES_CODE_TOLERANCE
        ):
            raise InvalidFitsImageError(
                f"FITS image has a Stokes axis value of {value:g}, which is "
                f"not a Stokes parameter code: {path}"
            )
        code = round(value)
        if code != 1:
            name = _STOKES_NAMES.get(code, f"code {code}")
            raise UnsupportedFitsImageError(
                f"FITS image plane is Stokes {name}, and the public finder "
                f"measures Stokes I only: {path}"
            )


def _positive_frequency_hz(frequency_hz: float, path: Path) -> float:
    """Validate one candidate reference frequency."""
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
    for keyword in ("RESTFRQ", "RESTFREQ"):
        frequency_hz = _header_number(header, keyword, path)
        if frequency_hz is not None:
            return _positive_frequency_hz(frequency_hz, path)
    return None


def _wcs_reference_frequency_hz(image_wcs: WCS, path: Path) -> float | None:
    """Read reference frequency from the first explicit WCS frequency axis."""
    for axis_index, physical_type in enumerate(
        image_wcs.world_axis_physical_types
    ):
        if physical_type == "em.freq":
            axis_unit = image_wcs.world_axis_units[axis_index] or "Hz"
            frequency_hz: Any = (
                float(image_wcs.wcs.crval[axis_index]) * units.Unit(axis_unit)
            ).to_value(units.Hz)
            return _positive_frequency_hz(float(frequency_hz), path)
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
    if not isinstance(primary_hdu, fits.PrimaryHDU):
        raise InvalidFitsImageError(
            f"FITS file does not begin with a standard image: {path}"
        )
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
    header = primary_hdu.header
    cube_axes = [
        f"{_header_value(header, f'CTYPE{axis}', path) or 'untyped'} "
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
    _require_readable_pixels(primary_hdu, path)
    unit = _brightness_unit(header, path, supplied)
    header_frequency_hz = _header_reference_frequency_hz(header, path)
    beam = _restoring_beam(header, path, supplied)
    image_wcs, celestial_wcs = _celestial_wcs(header, path)
    _require_one_rotation(header, image_wcs, path)
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


def _close_open_files(
    open_files: dict[int, Any], lock: threading.Lock
) -> None:
    """Close and forget every open file in ``open_files``."""
    with lock:
        held = list(open_files.values())
        open_files.clear()
    for hdus in held:
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
        self._metadata: ImageMetadata | None = None
        self._open_files: dict[int, Any] = {}
        self._open_files_lock = threading.Lock()
        # A caller that simply drops a source, as scripts and workers do,
        # would otherwise leave its files to the garbage collector. Dask
        # also keeps sources in reference cycles, whose objects the
        # collector finalizes in no defined order; it runs weakref callbacks
        # before any finalizer, so the files close before they could be
        # finalized and reported unclosed.
        weakref.finalize(
            self, _close_open_files, self._open_files, self._open_files_lock
        )

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
                # Stored values are read as they are and scaled window by
                # window in ``read_windows``. Astropy cannot map pixels it
                # scales itself, scales 16-bit ones in single precision and
                # skips a ``BLANK`` of zero.
                # Astropy leaves a file it opened itself to the collector
                # when it refuses the header, so the source opens the file
                # and closes it on that failure; the HDU list closes it
                # otherwise.
                file = self._path.open("rb")
                try:
                    hdus = fits.open(
                        file,
                        mode="readonly",
                        memmap=True,
                        do_not_scale_image_data=True,
                    )
                except BaseException:
                    file.close()
                    raise
            # Astropy raises whatever a malformed BITPIX or NAXIS card
            # first breaks, not one error for a file it cannot open.
            except (KeyError, OSError, TypeError, ValueError) as error:
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
        _close_open_files(self._open_files, self._open_files_lock)

    def header(self) -> fits.Header:
        """Return the primary header as the finder reads it.

        Each float holds the number Astropy parsed, written so that wcslib
        reads the same one. A WCS built from this header is therefore the
        transform that :meth:`metadata` validates, which one built from the
        file's own header text need not be. The header is the caller's own
        copy.

        Raises:
            InvalidFitsImageError: If the file cannot be opened, or a
                numeric WCS card is not a number.
        """
        return _wcs_header(self._primary_hdu().header, self._path).copy()

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
        """Read bounded windows through one validated FITS open.

        A pixel is valid under the rule of :mod:`hebog.io.pixel_validity`:
        finite, and in no 3x3 square of one repeated value. The rule looks
        at the pixels up to two away, so each window is read two pixels
        wider on every side inside the image, and only the window is kept.
        """
        requested_bounds = tuple(bounds_collection)
        if not requested_bounds:
            return ()
        windows: list[ImageWindow] = []
        metadata = self.metadata()
        primary_hdu = self._primary_hdu()
        scale, zero, blank = _pixel_scaling(primary_hdu.header, self._path)
        leading_indices = (0,) * (len(primary_hdu.shape) - 2)
        for bounds in requested_bounds:
            bounds.require_inside(metadata.shape_yx)
            read = validity_read_bounds(bounds, metadata.shape_yx)
            stored = primary_hdu.section[
                (
                    *leading_indices,
                    slice(read.y_start, read.y_stop),
                    slice(read.x_start, read.x_stop),
                )
            ]
            read_values = np.array(stored, dtype=np.float64, copy=True)
            if (scale, zero) != (1.0, 0.0):
                read_values = zero + scale * read_values
            if blank is not None:
                read_values[stored == blank] = np.nan
            del stored
            valid_pixels = valid_input_pixels(
                read_values, bounds, metadata.shape_yx
            )
            y_offset = bounds.y_start - read.y_start
            x_offset = bounds.x_start - read.x_start
            height, width = bounds.shape_yx
            # The read is this call's own array, so a window that is the
            # whole read, or whole rows of it, is kept without a copy; any
            # other is copied out so it does not hold the margin's memory.
            values = np.ascontiguousarray(
                read_values[
                    y_offset : y_offset + height,
                    x_offset : x_offset + width,
                ]
            )
            del read_values
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
