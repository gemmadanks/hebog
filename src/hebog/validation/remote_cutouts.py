# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Stream bounded cut-outs from large remote FITS images.

Public survey mosaics are gigabytes, but a validation case needs only a small
window. These helpers read the primary header and then one contiguous block of
rows through HTTP range requests, keeping only the requested columns of each
row. Transfer scales with ``rows * image width``; memory and disk scale with
the cut-out.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits

FITS_BLOCK_BYTES = 2880
_CARD_BYTES = 80
_MAXIMUM_HEADER_BLOCKS = 64
_BIG_ENDIAN_TYPES = {-32: ">f4", -64: ">f8"}
_IMAGE_DIMENSIONS = 2

RangeOpener = Callable[[str, int, int], BinaryIO]
"""Open bytes ``first`` to ``last`` inclusive of a resource as a stream."""


def open_http_range(url: str, first: int, last: int) -> BinaryIO:
    """Open one inclusive HTTP byte range, refusing a full-body response."""
    request = urllib.request.Request(
        url,
        headers={
            "Range": f"bytes={first}-{last}",
            "User-Agent": "hebog-validation",
        },
    )
    response = urllib.request.urlopen(request, timeout=120)
    if response.status != 206:  # noqa: PLR2004 - HTTP Partial Content
        response.close()
        raise OSError(f"server ignored the byte range for {url}")
    return cast(BinaryIO, response)


def read_primary_header(
    url: str,
    open_range: RangeOpener = open_http_range,
) -> tuple[fits.Header, int]:
    """Return the primary header and the byte offset of its data unit."""
    with open_range(
        url, 0, _MAXIMUM_HEADER_BLOCKS * FITS_BLOCK_BYTES - 1
    ) as stream:
        payload = stream.read(_MAXIMUM_HEADER_BLOCKS * FITS_BLOCK_BYTES)
    for card_start in range(0, len(payload), _CARD_BYTES):
        if payload[card_start : card_start + 8] == b"END     ":
            header_bytes = card_start + _CARD_BYTES
            data_offset = (
                -(-header_bytes // FITS_BLOCK_BYTES) * FITS_BLOCK_BYTES
            )
            header = fits.Header.fromstring(
                payload[:header_bytes].decode("ascii")
            )
            return header, data_offset
    raise ValueError(f"no FITS END card in the first header blocks of {url}")


def crop_row_block(  # noqa: PLR0913
    stream: BinaryIO,
    *,
    row_count: int,
    image_width: int,
    x_start: int,
    x_stop: int,
    big_endian_type: str,
) -> npt.NDArray[np.float32 | np.float64]:
    """Keep columns ``x_start:x_stop`` from consecutive full-width rows."""
    item_bytes = np.dtype(big_endian_type).itemsize
    row_bytes = image_width * item_bytes
    rows = np.empty((row_count, x_stop - x_start), dtype=big_endian_type)
    for row_index in range(row_count):
        row = stream.read(row_bytes)
        if len(row) != row_bytes:
            raise OSError("remote FITS row block ended early")
        rows[row_index] = np.frombuffer(row, dtype=big_endian_type)[
            x_start:x_stop
        ]
    return rows.astype(rows.dtype.newbyteorder("="))


def cutout_header(
    header: fits.Header,
    *,
    x_start: int,
    y_start: int,
    shape_yx: tuple[int, int],
) -> fits.Header:
    """Shift the WCS reference pixel into one cut-out's pixel frame."""
    shifted = header.copy()
    shifted["NAXIS2"], shifted["NAXIS1"] = shape_yx
    shifted["CRPIX1"] = float(cast(float, header["CRPIX1"])) - x_start
    shifted["CRPIX2"] = float(cast(float, header["CRPIX2"])) - y_start
    return shifted


def fetch_remote_cutout(  # noqa: PLR0913
    url: str,
    destination: Path,
    *,
    x_start: int,
    y_start: int,
    size: int,
    open_range: RangeOpener = open_http_range,
) -> str:
    """Write one square cut-out of a remote FITS image plane and hash it.

    Only ``float32`` or ``float64`` primary images whose axes beyond the two
    spatial axes are singletons (as in PyBDSF RMS and mask maps) are
    supported; the cut-out keeps those singleton axes. The destination must
    not exist; the file is written to a sibling temporary path and renamed
    into place when complete.
    """
    if destination.exists():
        raise FileExistsError(destination)
    header, data_offset = read_primary_header(url, open_range)
    axis_count = int(cast(int, header.get("NAXIS", 0)))
    extra_axes = [
        int(cast(int, header[f"NAXIS{axis}"]))
        for axis in range(_IMAGE_DIMENSIONS + 1, axis_count + 1)
    ]
    if axis_count < _IMAGE_DIMENSIONS or any(size != 1 for size in extra_axes):
        raise ValueError(f"remote cut-outs need one image plane: {url}")
    width = int(cast(int, header["NAXIS1"]))
    height = int(cast(int, header["NAXIS2"]))
    if not (
        x_start >= 0
        and y_start >= 0
        and x_start + size <= width
        and y_start + size <= height
        and size > 0
    ):
        raise ValueError(f"cut-out window lies outside {url}")
    big_endian_type = _BIG_ENDIAN_TYPES.get(int(cast(int, header["BITPIX"])))
    if big_endian_type is None:
        raise ValueError(f"remote cut-outs need a floating-point image: {url}")
    row_bytes = width * np.dtype(big_endian_type).itemsize
    first = data_offset + y_start * row_bytes
    last = first + size * row_bytes - 1
    with open_range(url, first, last) as stream:
        values = crop_row_block(
            stream,
            row_count=size,
            image_width=width,
            x_start=x_start,
            x_stop=x_start + size,
            big_endian_type=big_endian_type,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.partial")
    fits.PrimaryHDU(
        data=values.reshape((1,) * len(extra_axes) + values.shape),
        header=cutout_header(
            header, x_start=x_start, y_start=y_start, shape_yx=(size, size)
        ),
    ).writeto(partial, overwrite=True)
    digest = hashlib.sha256(partial.read_bytes()).hexdigest()
    os.replace(partial, destination)
    return digest
