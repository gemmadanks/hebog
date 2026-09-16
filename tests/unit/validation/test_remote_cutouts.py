# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""Bounded cut-outs streamed from remote FITS images."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
import pytest
from astropy.io import fits

from hebog.validation import remote_cutouts
from hebog.validation.remote_cutouts import (
    fetch_remote_cutout,
    open_http_range,
    require_requested_range,
)


def _fits_bytes(values: np.ndarray) -> bytes:
    """Serialise one small 2-D radio image with a simple WCS."""
    header = fits.Header()
    header["BUNIT"] = "JY/BEAM"
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 5.0
    header["CRPIX2"] = 4.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = 20.0
    header["CDELT1"] = -0.001
    header["CDELT2"] = 0.001
    buffer = io.BytesIO()
    fits.PrimaryHDU(data=values, header=header).writeto(buffer)
    return buffer.getvalue()


class _RangeServer:
    """In-memory byte-range opener that records requested ranges."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.ranges: list[tuple[int, int]] = []

    def __call__(self, url: str, first: int, last: int) -> BinaryIO:
        del url
        self.ranges.append((first, last))
        return io.BytesIO(self.payload[first : last + 1])


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_cutout_matches_local_slice_and_shifts_wcs(
    tmp_path: Path,
    dtype: type[np.floating],
) -> None:
    """Only the window's rows are requested and its sky frame is kept."""
    values = np.arange(9 * 11, dtype=dtype).reshape(9, 11)
    server = _RangeServer(_fits_bytes(values))
    destination = tmp_path / "cutout.fits"

    digest = fetch_remote_cutout(
        "https://example.invalid/image.fits",
        destination,
        x_start=3,
        y_start=2,
        size=4,
        open_range=server,
    )

    with fits.open(destination) as hdus:
        header = hdus[0].header
        np.testing.assert_array_equal(hdus[0].data, values[2:6, 3:7])
    assert (header["NAXIS1"], header["NAXIS2"]) == (4, 4)
    assert (header["CRPIX1"], header["CRPIX2"]) == (2.0, 2.0)
    assert len(digest) == 64
    item = np.dtype(dtype).itemsize
    first_row = server.ranges[1][0]
    assert server.ranges[1][1] - first_row + 1 == 4 * 11 * item
    assert not (tmp_path / ".cutout.fits.partial").exists()


def test_cutout_keeps_singleton_axes_of_pybdsf_maps(tmp_path: Path) -> None:
    """PyBDSF RMS and mask maps carry two trailing singleton FITS axes."""
    values = np.arange(36, dtype=np.float32).reshape(1, 1, 6, 6)
    server = _RangeServer(_fits_bytes(values))
    destination = tmp_path / "rms.fits"

    fetch_remote_cutout(
        "u", destination, x_start=1, y_start=2, size=3, open_range=server
    )

    with fits.open(destination) as hdus:
        np.testing.assert_array_equal(hdus[0].data, values[:, :, 2:5, 1:4])


def test_rejects_non_singleton_extra_axes(tmp_path: Path) -> None:
    """A spectral cube is not one image plane."""
    server = _RangeServer(_fits_bytes(np.zeros((2, 6, 6), dtype=np.float32)))

    with pytest.raises(ValueError, match="one image plane"):
        fetch_remote_cutout(
            "u",
            tmp_path / "c.fits",
            x_start=0,
            y_start=0,
            size=2,
            open_range=server,
        )


def test_rejects_windows_outside_the_image_and_existing_output(
    tmp_path: Path,
) -> None:
    """A cut-out never wraps, truncates or replaces an earlier result."""
    server = _RangeServer(_fits_bytes(np.zeros((6, 6), dtype=np.float32)))
    destination = tmp_path / "cutout.fits"

    with pytest.raises(ValueError, match="outside"):
        fetch_remote_cutout(
            "u", destination, x_start=4, y_start=0, size=4, open_range=server
        )
    destination.write_bytes(b"earlier")
    with pytest.raises(FileExistsError):
        fetch_remote_cutout(
            "u", destination, x_start=0, y_start=0, size=4, open_range=server
        )


def test_rejects_integer_images_and_truncated_rows(tmp_path: Path) -> None:
    """Masks stored as integers and short responses fail clearly."""
    integers = _RangeServer(_fits_bytes(np.zeros((6, 6), dtype=np.int16)))
    with pytest.raises(ValueError, match="floating-point"):
        fetch_remote_cutout(
            "u",
            tmp_path / "a.fits",
            x_start=0,
            y_start=0,
            size=2,
            open_range=integers,
        )

    payload = _fits_bytes(np.zeros((6, 6), dtype=np.float32))

    def truncated(url: str, first: int, last: int) -> BinaryIO:
        del url
        stop = last + 1 if first == 0 else min(last + 1, first + 10)
        return io.BytesIO(payload[first:stop])

    with pytest.raises(OSError, match="ended early"):
        fetch_remote_cutout(
            "u",
            tmp_path / "b.fits",
            x_start=0,
            y_start=2,
            size=2,
            open_range=truncated,
        )


def test_rejects_a_resource_without_a_fits_header(tmp_path: Path) -> None:
    """An HTML error page or truncated file is not mistaken for an image."""
    server = _RangeServer(b"<html>not found</html>".ljust(2880))

    with pytest.raises(ValueError, match="END card"):
        fetch_remote_cutout(
            "u",
            tmp_path / "d.fits",
            x_start=0,
            y_start=0,
            size=1,
            open_range=server,
        )


@pytest.mark.parametrize(
    "content_range",
    [
        None,
        "bytes 0-99/1000",
        "bytes 10-98/1000",
        "bytes */1000",
        "rows 10-99",
    ],
)
def test_partial_responses_must_cover_exactly_the_requested_bytes(
    content_range: str | None,
) -> None:
    """A 206 for other bytes would decode as valid-looking wrong rows."""
    with pytest.raises(OSError, match="byte range"):
        require_requested_range(content_range, 10, 99, "u")


def test_partial_response_for_the_requested_bytes_is_accepted() -> None:
    """The total size may be known or unknown."""
    require_requested_range("bytes 10-99/1000", 10, 99, "u")
    require_requested_range("bytes 10-99/*", 10, 99, "u")


class _Response(io.BytesIO):
    """Minimal HTTP response carrying a status and headers."""

    def __init__(self, status: int, content_range: str | None) -> None:
        super().__init__(b"payload")
        self.status = status
        self.headers = (
            {} if content_range is None else {"Content-Range": content_range}
        )


@pytest.mark.parametrize(
    ("status", "content_range", "accepted"),
    [
        (206, "bytes 10-99/1000", True),
        (206, "bytes 0-89/1000", False),
        (200, None, False),
    ],
)
def test_http_opener_checks_status_and_returned_range(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    content_range: str | None,
    accepted: bool,
) -> None:
    """Only a partial response for exactly the requested bytes is read."""
    response = _Response(status, content_range)
    requests: list[str] = []

    def urlopen(request: Any, timeout: float) -> _Response:
        del timeout
        requests.append(request.get_header("Range"))
        return response

    monkeypatch.setattr(remote_cutouts.urllib.request, "urlopen", urlopen)

    if accepted:
        assert open_http_range("https://example.invalid/a", 10, 99) is response
    else:
        with pytest.raises(OSError, match="range"):
            open_http_range("https://example.invalid/a", 10, 99)
        assert response.closed
    assert requests == ["bytes=10-99"]
