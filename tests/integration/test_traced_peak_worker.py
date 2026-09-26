# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Traced-peak worker contract over a complete FITS-to-products run."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits

from hebog.validation.traced_peak import load_traced_peak_record

_ROOT = Path(__file__).parents[2]
_WORKER = _ROOT / "scripts/benchmark/measure_traced_peak_worker.py"
_SETTINGS = {
    "detection_threshold_sigma": 5.0,
    "island_threshold_sigma": 3.0,
    "minimum_island_pixels": 7,
    "profile": "continuum",
}


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


def _one_source_image() -> npt.NDArray[np.float64]:
    """Return noise with one bright beam-shaped source near the centre."""
    y_pixels, x_pixels = np.mgrid[:96, :96]
    values = np.random.default_rng(20260925).normal(0.0, 1.0e-4, (96, 96))
    return values + 0.01 * np.exp(
        -(((x_pixels - 48.0) ** 2 + (y_pixels - 48.0) ** 2) / 8.0)
    )


@pytest.mark.integration
def test_worker_reports_both_traced_spans_of_a_complete_run(
    tmp_path: Path,
) -> None:
    """The peaks the runner depends on come from one real traced run.

    The worker is the only place the gate figure is produced, so its
    contract is exercised end to end: tracing covers the imports as well as
    the finder, the process peak is the larger span, and the record names
    the size limit this Hebog would have applied.
    """
    image = tmp_path / "image.fits"
    fits.PrimaryHDU(
        data=_one_source_image(), header=_header((96, 96))
    ).writeto(image)
    result = tmp_path / "result.json"

    subprocess.run(
        [
            sys.executable,
            str(_WORKER),
            "--input",
            str(image),
            "--output-directory",
            str(tmp_path / "products"),
            "--result",
            str(result),
            "--run-id",
            "traced-peak-worker-contract",
            "--settings",
            json.dumps(_SETTINGS),
        ],
        check=True,
        capture_output=True,
    )

    record = load_traced_peak_record(result)
    # Importing NumPy, Astropy, SciPy and Zarr holds tens of mebibytes, so a
    # floor this large is only reached when tracing covered the imports.
    assert record.import_traced_bytes > 10 * 2**20
    assert record.finder_peak_traced_bytes > record.import_traced_bytes
    assert record.public_size_limit_pixels == 3000
    assert record.source_count >= 1
    assert record.gaussian_component_count >= 1
    assert record.traced_wall_seconds > 0
    assert (tmp_path / "products").is_dir()


@pytest.mark.integration
def test_diagnostic_size_limit_governs_admission_inside_the_worker(
    tmp_path: Path,
) -> None:
    """The option really moves the envelope the traced run is admitted by.

    A raise candidate is measured by setting this limit above the public
    one, which cannot be checked cheaply. Setting it below the input's size
    checks the same mechanism on a small image: the limit reaches the public
    admission check in the worker's own process.
    """
    image = tmp_path / "image.fits"
    fits.PrimaryHDU(
        data=_one_source_image(), header=_header((96, 96))
    ).writeto(image)
    result = tmp_path / "result.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(_WORKER),
            "--input",
            str(image),
            "--output-directory",
            str(tmp_path / "products"),
            "--result",
            str(result),
            "--run-id",
            "traced-peak-diagnostic-limit",
            "--settings",
            json.dumps(_SETTINGS),
            "--diagnostic-size-limit",
            "32",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "SourceFinderImageTooLargeError" in completed.stderr
    assert "32 pixels per image dimension" in completed.stderr
    assert not result.exists()
