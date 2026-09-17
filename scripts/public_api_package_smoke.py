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
from hebog.io import read_catalogue_fits_product, read_diagnostics_product

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
        .joinpath("reviewed_continuum_profile.json")
        .read_bytes()
    )
    if hashlib.sha256(profile).hexdigest() != _PROFILE_SHA256:
        raise RuntimeError("installed scientific profile identity is wrong")

    with tempfile.TemporaryDirectory(prefix="hebog-public-api-") as temporary:
        root = Path(temporary)
        y, x = np.indices((49, 65))
        noise = np.random.default_rng(613).normal(size=x.shape)
        source = 40 * np.exp(-0.5 * ((x - 37.2) ** 2 + (y - 22.8) ** 2) / 3)
        for name, image, config in (
            ("blank", np.zeros((16, 16)), hebog.SourceFinderConfig(5, 3, 7)),
            (
                "all-nan",
                np.full((16, 16), np.nan),
                hebog.SourceFinderConfig(5, 3, 7),
            ),
            (
                "continuum",
                source + noise - 2,
                hebog.SourceFinderConfig(5, 3, 7),
            ),
            (
                "compact",
                source + noise - 2,
                hebog.SourceFinderConfig(5, 3, 7, profile="compact"),
            ),
            ("custom", source + noise - 2, hebog.SourceFinderConfig(6, 4, 7)),
        ):
            input_path = root / f"{name}.fits"
            fits.PrimaryHDU(image, _header()).writeto(input_path)
            result = hebog.find_sources(
                hebog.SourceFinderRequest(input_path, root / name, name),
                config,
                SerialExecutor(),
            )
            _check_products(
                result, image.shape, empty=name in {"blank", "all-nan"}
            )
            print(f"Installed public workflow: {name} passed")


def _check_products(
    result: hebog.SourceFinderResult,
    shape: tuple[int, ...],
    *,
    empty: bool,
) -> None:
    """Read all four installed products and verify their bound identities."""
    for product in (
        result.catalogue,
        result.rms,
        result.mask,
        result.diagnostics,
    ):
        if (
            hashlib.sha256(product.path.read_bytes()).hexdigest()
            != product.content_sha256
        ):
            raise RuntimeError("installed product identity does not match")
    catalogue = read_catalogue_fits_product(result.catalogue)
    diagnostics = read_diagnostics_product(result.diagnostics)
    if (
        len(catalogue.sources) != result.source_count
        or diagnostics.run_id != result.run_id
    ):
        raise RuntimeError("installed product run identity does not match")
    for path in (result.rms_path, result.mask_path):
        if np.asarray(fits.getdata(path)).shape != shape:
            raise RuntimeError("installed image product has the wrong shape")
    if empty:
        if result.source_count != 0 or catalogue.gaussian_components:
            raise RuntimeError("empty installed-wheel control has sources")
        if result.rms.scientific_status != "unavailable":
            raise RuntimeError("empty installed-wheel control invents noise")
    elif result.source_count != 1 or len(catalogue.gaussian_components) != 1:
        raise RuntimeError("installed-wheel control lost its isolated source")


if __name__ == "__main__":
    main()
