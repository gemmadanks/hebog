# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Writing the inputs of a matched benchmark of Rapthor's filter step."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from hebog.io import FitsImageSource
from hebog.validation.filter_benchmark import (
    write_sector_inputs,
    wsclean_layout_hdu,
)
from hebog.validation.rapthor_agreement import emission_pixels

_SHAPE_YX = (80, 96)
_FREQUENCY_HZ = 144e6
_PIXEL_DEGREES = 1.5 / 3600


def _header() -> fits.Header:
    """Return a two-axis LoTSS-like header: frequency only in RESTFRQ."""
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 48.0
    header["CRPIX2"] = 40.0
    header["CRVAL1"] = 210.0
    header["CRVAL2"] = 54.0
    header["CDELT1"] = -_PIXEL_DEGREES
    header["CDELT2"] = _PIXEL_DEGREES
    header["CUNIT1"] = "deg"
    header["CUNIT2"] = "deg"
    header["RADESYS"] = "ICRS"
    header["BMAJ"] = 6.0 / 3600
    header["BMIN"] = 6.0 / 3600
    header["BPA"] = 0.0
    header["BUNIT"] = "JY/BEAM"
    header["RESTFRQ"] = _FREQUENCY_HZ
    return header


def _plane() -> np.ndarray:
    """Return unit-variance noise with two sources and one blank pixel."""
    generator = np.random.default_rng(20261013)
    plane = generator.standard_normal(_SHAPE_YX).astype(np.float32)
    y, x = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    for row, column, peak in ((20, 30, 40.0), (55, 70, 12.0)):
        plane += peak * np.exp(-((y - row) ** 2 + (x - column) ** 2) / 4.0)
    plane[0, 0] = np.nan
    return plane


def _degrees(line: str) -> tuple[float, float]:
    """Read a makesourcedb component's ``hh:mm:ss`` and ``+dd.mm.ss``."""
    _, _, right_ascension, declination, *_ = line.split(",")
    hours, minutes, seconds = (
        float(part) for part in right_ascension.split(":")
    )
    sign = -1.0 if declination.startswith("-") else 1.0
    degrees, arcminutes, arcseconds, fraction = declination.lstrip("+-").split(
        "."
    )
    return (
        15.0 * (hours + minutes / 60 + seconds / 3600),
        sign
        * (
            float(degrees)
            + float(arcminutes) / 60
            + float(f"{arcseconds}.{fraction}") / 3600
        ),
    )


def _image(tmp_path: Path) -> Path:
    path = tmp_path / "window.fits"
    fits.PrimaryHDU(_plane(), header=_header()).writeto(path)
    return path


def test_a_plane_is_laid_out_on_wscleans_four_axes() -> None:
    """RA, Dec, a one-channel frequency axis and a one-plane Stokes axis.

    PyBDSF reads the frequency from the axis, which LoTSS mosaics lack.
    """
    plane = _plane()

    hdu = wsclean_layout_hdu(plane, _header(), _FREQUENCY_HZ)

    data = np.asarray(hdu.data)
    assert data.shape == (1, 1, *_SHAPE_YX)
    np.testing.assert_array_equal(data[0, 0], plane)
    assert [hdu.header[f"CTYPE{axis}"] for axis in range(1, 5)] == [
        "RA---SIN",
        "DEC--SIN",
        "FREQ",
        "STOKES",
    ]
    assert hdu.header["CRVAL3"] == _FREQUENCY_HZ
    assert hdu.header["CRVAL4"] == 1.0
    assert hdu.header["BMAJ"] == pytest.approx(6.0 / 3600)
    assert hdu.header["BUNIT"] == "JY/BEAM"
    np.testing.assert_allclose(
        WCS(hdu.header).celestial.wcs_pix2world([[10.0, 20.0]], 0),
        WCS(_header()).celestial.wcs_pix2world([[10.0, 20.0]], 0),
    )


def test_a_sector_is_written_as_rapthor_reads_it(tmp_path: Path) -> None:
    """Two identical images Hebog reads, two lists, and a polygon.

    Every component lies on an island pixel: at least 3 sigma, connected
    to a 5-sigma peak.
    """
    inputs = write_sector_inputs(
        _image(tmp_path),
        tmp_path / "sector",
        island_sigma=3.0,
        peak_sigma=5.0,
        margin_fraction=0.05,
    )

    flat = inputs.flat_noise_image_path.read_bytes()
    assert flat == inputs.true_sky_image_path.read_bytes()
    metadata = FitsImageSource(inputs.true_sky_image_path).metadata()
    assert metadata.shape_yx == inputs.shape_yx == _SHAPE_YX
    assert metadata.reference_frequency_hz == _FREQUENCY_HZ

    island_pixels, _ = emission_pixels(
        _plane().astype(np.float64), floor_sigma=3.0, seed_sigma=5.0
    )
    true_lines = inputs.true_sky_model_path.read_text().splitlines()
    assert true_lines[0].startswith("FORMAT = Name, Type, Ra, Dec, I,")
    assert inputs.component_count == len(island_pixels) == len(true_lines) - 1
    assert (
        inputs.apparent_sky_model_path.read_text()
        == "\n".join(true_lines) + "\n"
    )
    names = [line.split(",")[0] for line in true_lines[1:]]
    assert len(set(names)) == len(names)
    x, y = (
        WCS(_header())
        .celestial.wcs_world2pix(
            [_degrees(line) for line in true_lines[1:]], 0
        )
        .T
    )
    written = set(
        zip(
            np.rint(y).astype(int).tolist(),
            np.rint(x).astype(int).tolist(),
            strict=True,
        )
    )
    expected = set(
        zip(
            island_pixels.rows.tolist(),
            island_pixels.columns.tolist(),
            strict=True,
        )
    )
    assert written == expected
    assert {(20, 30), (55, 70)} <= expected

    vertices = np.load(inputs.vertices_path)
    assert vertices.shape == (5, 2)
    np.testing.assert_array_equal(vertices[0], vertices[-1])
    corners = WCS(_header()).celestial.wcs_world2pix(vertices, 0)
    np.testing.assert_allclose(
        corners[:4],
        [[4.75, 3.95], [90.25, 3.95], [90.25, 75.05], [4.75, 75.05]],
        atol=1e-6,
    )
