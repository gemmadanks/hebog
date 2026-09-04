# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Exercise the installed public API without importing the source checkout."""

from __future__ import annotations

import hashlib
import tempfile
from importlib.resources import files
from pathlib import Path

import numpy as np
from astropy.io import fits

import hebog
from hebog.executors import SerialExecutor

_PROFILE_SHA256 = (
    "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
)


def _header() -> fits.Header:
    """Return a minimal qualified radio-continuum image header."""
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = 4.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = 9.0
    header["CRPIX2"] = 9.0
    header["CRVAL1"] = 180.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["RESTFRQ"] = 150_000_000.0
    return header


def main() -> None:
    """Verify the wheel contains and can execute its frozen public profile."""
    profile = (
        files("hebog.resources")
        .joinpath("phase_5_continuum_review.json")
        .read_bytes()
    )
    if hashlib.sha256(profile).hexdigest() != _PROFILE_SHA256:
        raise RuntimeError("installed scientific profile identity is wrong")

    with tempfile.TemporaryDirectory(prefix="hebog-public-api-") as temporary:
        root = Path(temporary)
        input_path = root / "image.fits"
        output_path = root / "products"
        fits.PrimaryHDU(
            np.zeros((16, 16), dtype=np.float64),
            _header(),
        ).writeto(input_path)
        result = hebog.find_sources(
            hebog.SourceFinderRequest(
                image_path=input_path,
                output_directory=output_path,
                run_id="installed-wheel-smoke",
            ),
            hebog.SourceFinderConfig(5.0, 3.0, 7),
            SerialExecutor(),
        )
        products = (
            result.catalogue,
            result.rms,
            result.mask,
            result.diagnostics,
        )
        if not all(product.path.is_file() for product in products):
            raise RuntimeError("installed public API did not publish products")
        if (result.source_count, result.island_count) != (0, 0):
            raise RuntimeError(
                "blank installed-wheel smoke image is not empty"
            )


if __name__ == "__main__":
    main()
