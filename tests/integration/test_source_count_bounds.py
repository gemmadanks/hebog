# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""The source-count estimate bounds what ``find_sources`` publishes.

A caller reserves ``analysis_memory_bytes`` for the estimate before the
analysis runs (Rapthor's native task does, plan task 77), so an estimate
below the published count would reserve too little.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.executors import SerialExecutor

pytestmark = pytest.mark.integration

_SHAPE_YX = (256, 256)
# A 4-arcsecond beam on 1-arcsecond pixels, as a Gaussian sigma in pixels.
_BEAM_SIGMA_PIXELS = 4.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))


def _header() -> fits.Header:
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"], header["CTYPE2"] = "RA---TAN", "DEC--TAN"
    header["CRPIX1"], header["CRPIX2"] = 129.0, 129.0
    header["CRVAL1"], header["CRVAL2"] = 180.0, -30.0
    header["CDELT1"], header["CDELT2"] = -1.0 / 3600.0, 1.0 / 3600.0
    header["CUNIT1"] = header["CUNIT2"] = "deg"
    header["RESTFRQ"] = 150_000_000.0
    return header


def _crowded_image(path: Path) -> Path:
    """Compact sources from 5 to 40 sigma, close pairs and a wide source."""
    y, x = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    generator = np.random.default_rng(20261014)
    image = generator.normal(0.0, 1.0, _SHAPE_YX)

    def add(row: float, column: float, peak: float, sigma: float) -> None:
        nonlocal image
        image += peak * np.exp(
            -((x - column) ** 2 + (y - row) ** 2) / (2.0 * sigma**2)
        )

    for index in range(24):
        row, column = 20 + 30 * (index // 6), 20 + 40 * (index % 6)
        add(row, column, 5.0 + 1.5 * index, _BEAM_SIGMA_PIXELS)
    for index in range(4):
        # Pairs 1.5 beams apart, which deblending splits.
        row, column = 160 + 20 * index, 30
        add(row, column, 20.0, _BEAM_SIGMA_PIXELS)
        add(row, column + 6.0, 12.0, _BEAM_SIGMA_PIXELS)
    add(200.0, 180.0, 8.0, 15.0)
    fits.PrimaryHDU(data=image, header=_header()).writeto(path)
    return path


@pytest.mark.parametrize("profile", ["continuum", "compact"])
@pytest.mark.parametrize("background", ["estimated", "zero"])
def test_the_estimate_bounds_the_published_sources(
    tmp_path: Path, profile: str, background: str
) -> None:
    """Given a crowded image, when it is analysed, no more sources publish.

    Every profile and background Rapthor can choose is covered.
    """
    image = _crowded_image(tmp_path / "image.fits")

    estimate = hebog.expected_source_count(
        image, detection_threshold_sigma=5.0
    )
    result = hebog.find_sources(
        SourceFinderRequest(image, tmp_path / "products", "estimate"),
        SourceFinderConfig(
            5.0,
            3.0,
            6,
            profile=profile,  # pyright: ignore[reportArgumentType]
            background=background,  # pyright: ignore[reportArgumentType]
        ),
        SerialExecutor(),
    )

    assert 0 < result.source_count <= estimate
