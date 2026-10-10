# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""The flat-noise branch: one run publishes the flat-noise image's RMS too.

Rapthor's PyBDSF path runs a second pass on the flat-noise image only to
publish its RMS map. Hebog estimates that image's background and RMS in the
same run as the true-sky analysis, and publishes the RMS in the same bundle.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits
from conftest import product_hashes

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.data_models import PublicSourceFindingDiagnostics
from hebog.executors import Executor, SerialExecutor
from hebog.io.materialization import read_diagnostics_product
from hebog.pipeline import InvalidSourceFinderInputError
from hebog.stages import composition

pytestmark = pytest.mark.integration

_SHAPE_YX = (81, 97)


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


def _flat_noise_image() -> np.ndarray:
    """Return compact sources on noise that is the same everywhere."""
    y_pixels, x_pixels = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    image = np.random.default_rng(7).normal(0.0, 1.0, _SHAPE_YX)
    for y, x, peak in ((40, 30, 40.0), (25, 70, 20.0), (60, 60, 12.0)):
        image += peak * np.exp(
            -((x_pixels - x) ** 2 + (y_pixels - y) ** 2) / 4.0
        )
    return np.asarray(image, dtype=np.float64)


def _true_sky_image(flat_noise: np.ndarray) -> np.ndarray:
    """Divide by a smooth primary beam, so the noise grows outwards."""
    y_pixels, x_pixels = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    centre_y, centre_x = (_SHAPE_YX[0] - 1) / 2, (_SHAPE_YX[1] - 1) / 2
    beam = np.exp(
        -((x_pixels - centre_x) ** 2 + (y_pixels - centre_y) ** 2)
        / (2.0 * 70.0**2)
    )
    return np.asarray(flat_noise / beam, dtype=np.float64)


def _write(path: Path, values: np.ndarray) -> Path:
    fits.PrimaryHDU(data=values, header=_header(values.shape)).writeto(path)
    return path


def _inputs(tmp_path: Path) -> tuple[Path, Path]:
    """Write the true-sky and flat-noise pair of one sector."""
    flat_noise = _flat_noise_image()
    return (
        _write(tmp_path / "true-sky.fits", _true_sky_image(flat_noise)),
        _write(tmp_path / "flat-noise.fits", flat_noise),
    )


def _config() -> SourceFinderConfig:
    return SourceFinderConfig(5.0, 3.0, 7)


def _data(path: Path) -> np.ndarray:
    return np.asarray(fits.getdata(path), dtype=np.float64)


def test_one_run_publishes_the_flat_noise_rms_beside_the_true_sky_products(
    tmp_path: Path, each_executor: Executor
) -> None:
    """The flat-noise RMS is its own; the true-sky products are unchanged.

    The flat-noise RMS equals the RMS a run on the flat-noise image alone
    publishes, and the catalogue, RMS and mask equal a run without the
    flat-noise image, under every executor.
    """
    true_sky, flat_noise = _inputs(tmp_path)
    paired = hebog.find_sources(
        SourceFinderRequest(
            true_sky,
            tmp_path / "paired",
            "sector-0",
            flat_noise_image_path=flat_noise,
        ),
        _config(),
        each_executor,
    )
    true_sky_alone = hebog.find_sources(
        SourceFinderRequest(true_sky, tmp_path / "true-sky", "sector-0"),
        _config(),
        SerialExecutor(),
    )
    flat_noise_alone = hebog.find_sources(
        SourceFinderRequest(flat_noise, tmp_path / "flat-noise", "sector-0"),
        _config(),
        SerialExecutor(),
    )

    assert paired.flat_noise_rms is not None
    assert paired.flat_noise_rms.product_role == "rms"
    assert paired.flat_noise_rms.scientific_status == "valid"
    np.testing.assert_array_equal(
        _data(paired.flat_noise_rms.path), _data(flat_noise_alone.rms.path)
    )
    assert product_hashes(paired)[:3] == product_hashes(true_sky_alone)[:3]
    # The noise grows outwards in the true-sky image and not in the other.
    assert not np.allclose(
        _data(paired.rms.path), _data(paired.flat_noise_rms.path)
    )


def test_a_run_without_a_flat_noise_image_publishes_no_flat_noise_rms(
    tmp_path: Path,
) -> None:
    """The flat-noise branch runs only when the caller asks for it."""
    true_sky, _ = _inputs(tmp_path)

    result = hebog.find_sources(
        SourceFinderRequest(true_sky, tmp_path / "products", "sector-0"),
        _config(),
        SerialExecutor(),
    )

    assert result.flat_noise_rms is None
    assert not (tmp_path / "products" / "flat-noise-rms.fits").exists()


def test_the_provenance_binds_the_flat_noise_input(tmp_path: Path) -> None:
    """A run with two inputs records the checksum of each."""
    true_sky, flat_noise = _inputs(tmp_path)

    result = hebog.find_sources(
        SourceFinderRequest(
            true_sky,
            tmp_path / "products",
            "sector-0",
            flat_noise_image_path=flat_noise,
        ),
        _config(),
        SerialExecutor(),
    )

    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    provenance = diagnostics.provenance
    assert provenance.flat_noise_input_sha256 == (
        hashlib.sha256(flat_noise.read_bytes()).hexdigest()
    )
    assert provenance.input_sha256 == (
        hashlib.sha256(true_sky.read_bytes()).hexdigest()
    )


@pytest.mark.parametrize("difference", ["shape", "grid"])
def test_a_flat_noise_image_on_another_grid_is_refused_before_any_product(
    tmp_path: Path, difference: str
) -> None:
    """The two images of a sector share one pixel grid, or the run stops."""
    true_sky, _ = _inputs(tmp_path)
    flat_noise = _flat_noise_image()
    if difference == "shape":
        flat_noise = flat_noise[:, :-1]
    header = _header(flat_noise.shape)
    if difference == "grid":
        header["CRVAL1"] = 181.0
    other = tmp_path / "other.fits"
    fits.PrimaryHDU(data=flat_noise, header=header).writeto(other)

    with pytest.raises(InvalidSourceFinderInputError, match="flat-noise"):
        hebog.find_sources(
            SourceFinderRequest(
                true_sky,
                tmp_path / "products",
                "sector-0",
                flat_noise_image_path=other,
            ),
            _config(),
            SerialExecutor(),
        )

    assert not (tmp_path / "products").exists()


def test_a_failed_flat_noise_branch_fails_the_run_and_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Either branch failing stops the run once both have stopped."""
    true_sky, flat_noise = _inputs(tmp_path)
    estimate = composition.estimate_background_rms

    def fail_on_the_flat_noise_image(*args: Any, **kwargs: Any) -> Any:
        if "flat-noise" in Path(args[4]).as_posix():
            raise RuntimeError("flat-noise estimate failed")
        return estimate(*args, **kwargs)

    monkeypatch.setattr(
        composition, "estimate_background_rms", fail_on_the_flat_noise_image
    )

    with pytest.raises(RuntimeError, match="flat-noise estimate failed"):
        hebog.find_sources(
            SourceFinderRequest(
                true_sky,
                tmp_path / "products",
                "sector-0",
                flat_noise_image_path=flat_noise,
            ),
            _config(),
            SerialExecutor(),
        )

    assert not (tmp_path / "products").exists()
    assert not any(tmp_path.glob(".products*"))
