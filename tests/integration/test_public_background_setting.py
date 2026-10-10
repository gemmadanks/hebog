# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""The background setting: Hebog's estimate, or PyBDSF's zero mean map.

LSMTool runs PyBDSF with ``mean_map="zero"``, which leaves its RMS map
estimated and its background zero. The ``zero`` setting does the same, so
plan task 21 can measure both against Rapthor's retained components.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.executors import Executor
from hebog.io.materialization import read_catalogue_fits_product

pytestmark = pytest.mark.integration

_OFFSET_JY_PER_BEAM = 0.5
_PEAK_JY_PER_BEAM = 30.0


def _header(shape_yx: tuple[int, int]) -> fits.Header:
    height, width = shape_yx
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"], header["CTYPE2"] = "RA---TAN", "DEC--TAN"
    header["CRPIX1"], header["CRPIX2"] = width / 2 + 1, height / 2 + 1
    header["CRVAL1"], header["CRVAL2"] = 180.0, -30.0
    header["CDELT1"], header["CDELT2"] = -1.0 / 3600.0, 1.0 / 3600.0
    header["CUNIT1"] = header["CUNIT2"] = "deg"
    header["RESTFRQ"] = 150_000_000.0
    return header


def _offset_image(path: Path) -> Path:
    """One compact source on noise with a constant positive background."""
    y_pixels, x_pixels = np.mgrid[:96, :96]
    image = np.random.default_rng(11).normal(0.0, 1.0, (96, 96))
    image += _OFFSET_JY_PER_BEAM
    sigma = 4.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    image += _PEAK_JY_PER_BEAM * np.exp(
        -((x_pixels - 48) ** 2 + (y_pixels - 48) ** 2) / (2.0 * sigma**2)
    )
    fits.PrimaryHDU(data=image, header=_header(image.shape)).writeto(path)
    return path


def _peak(result: hebog.SourceFinderResult) -> float:
    catalogue = read_catalogue_fits_product(result.catalogue)
    assert len(catalogue.gaussian_components) == 1
    return catalogue.gaussian_components[0].flux.peak_flux_jy_per_beam


def test_a_zero_background_keeps_the_offset_and_the_rms(
    tmp_path: Path, each_executor: Executor
) -> None:
    """Zero subtracts nothing; the RMS is the same as with the estimate.

    The estimate removes the offset, so the fitted peak is the injected one.
    With zero, the offset stays under the source, and the fit, which holds
    its own background at zero, takes it into the Gaussian: the peak rises
    by at least the offset.
    """
    image = _offset_image(tmp_path / "image.fits")
    estimated = hebog.find_sources(
        SourceFinderRequest(image, tmp_path / "estimated", "run"),
        SourceFinderConfig(5.0, 3.0, 7),
        each_executor,
    )
    zero = hebog.find_sources(
        SourceFinderRequest(image, tmp_path / "zero", "run"),
        SourceFinderConfig(5.0, 3.0, 7, background="zero"),
        each_executor,
    )

    assert _peak(estimated) == pytest.approx(_PEAK_JY_PER_BEAM, rel=0.03)
    assert _peak(zero) - _peak(estimated) >= _OFFSET_JY_PER_BEAM
    np.testing.assert_array_equal(
        fits.getdata(zero.rms.path), fits.getdata(estimated.rms.path)
    )
    assert (
        zero.diagnostics.content_sha256 != estimated.diagnostics.content_sha256
    )
