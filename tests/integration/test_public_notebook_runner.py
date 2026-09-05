# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Synthetic end-to-end smoke for the exact public notebook runner."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits

_ROOT = Path(__file__).parents[2]
_RUNNER = runpy.run_path(
    str(_ROOT / "scripts/benchmark/run_phase5_public_finder_hebog.py")
)
_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)


def _header(shape_yx: tuple[int, int]) -> fits.Header:
    """Return one valid ICRS radio-continuum FITS header."""
    height, width = shape_yx
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = 4.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = width / 2 + 1
    header["CRPIX2"] = height / 2 + 1
    header["CRVAL1"] = 180.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["CUNIT1"] = "deg"
    header["CUNIT2"] = "deg"
    header["RESTFRQ"] = 150_000_000.0
    return header


def _geometry_matrix_image() -> np.ndarray[Any, np.dtype[np.float64]]:
    """Combine edge, multi-peak, elongated, invalid, and sparse geometry."""
    height, width = 96, 128
    y_pixels, x_pixels = np.mgrid[:height, :width]
    image = np.random.default_rng(31).normal(0.0, 0.12, (height, width))

    def gaussian(
        amplitude: float,
        y_center: float,
        x_center: float,
        y_sigma: float = 2.0,
        x_sigma: float = 2.0,
    ) -> np.ndarray[Any, np.dtype[np.float64]]:
        return amplitude * np.exp(
            -0.5
            * (
                ((y_pixels - y_center) / y_sigma) ** 2
                + ((x_pixels - x_center) / x_sigma) ** 2
            )
        )

    image += gaussian(4.0, 1.5, 2.0)
    for amplitude, x_center in ((3.8, 45.0), (3.5, 51.0), (3.2, 57.0)):
        image += gaussian(amplitude, 46.0, x_center)
    for y_center, x_center in ((72.0, 92.0), (75.0, 97.0), (78.0, 102.0)):
        image += gaussian(3.0, y_center, x_center, 3.0, 5.0)
    image += gaussian(2.8, 88.0, 15.0)
    image[18:23, 104:112] = np.nan
    return np.asarray(image, dtype=np.float64)


@pytest.mark.integration
def test_exact_notebook_runner_completes_geometry_matrix(
    tmp_path: Path,
) -> None:
    """The exact notebook path publishes aligned products for edge cases."""
    input_path = tmp_path / "input.fits"
    output = tmp_path / "result"
    image = _geometry_matrix_image()
    fits.PrimaryHDU(image, _header(image.shape)).writeto(input_path)

    result = cast(
        dict[str, object],
        _RUNNER["run_public_hebog"](
            input_path=input_path,
            output=output,
            case_id="synthetic-geometry-matrix",
            core=None,
            configuration_sha256=_CONFIGURATION_SHA256,
        ),
    )

    publication = np.asarray(
        fits.getdata(output / "segment_labels.fits")
    ).squeeze()
    measurement = np.asarray(
        fits.getdata(output / "component_labels.fits")
    ).squeeze()
    terminal = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert terminal == result
    assert np.any(publication > 0)
    assert not np.any((publication > 0) & (measurement <= 0))
    assert terminal["source_count"] >= 1
    assert terminal["component_count"] >= terminal["source_count"]
