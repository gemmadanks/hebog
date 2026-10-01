# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Traced-peak attribution runner contract over a complete run."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits

_ROOT = Path(__file__).parents[2]
_RUNNER = _ROOT / "scripts/benchmark/attribute_traced_peak.py"
_SETTINGS = {
    "detection_threshold_sigma": 5.0,
    "island_threshold_sigma": 3.0,
    "minimum_island_pixels": 7,
    "profile": "continuum",
}

pytestmark = pytest.mark.integration


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


def _two_source_image() -> npt.NDArray[np.float64]:
    """Return noise with two bright beam-shaped sources."""
    y_pixels, x_pixels = np.mgrid[:192, :192]
    values = np.random.default_rng(20260929).normal(0.0, 1.0e-4, (192, 192))
    for y, x in ((48.0, 60.0), (140.0, 120.0)):
        values += 0.01 * np.exp(
            -(((x_pixels - x) ** 2 + (y_pixels - y) ** 2) / 8.0)
        )
    return values


def test_the_peak_is_attributed_to_passes_tasks_and_call_sites(
    tmp_path: Path,
) -> None:
    """One traced run names where its peak lies and what the pass held.

    The run's own call is the outermost measured path, so its peak is the
    largest; each serial task nests under the pass that submitted it; and
    the largest entry inside the multiscale pass is reduced to call sites.
    """
    image = tmp_path / "image.fits"
    fits.PrimaryHDU(
        data=_two_source_image(), header=_header((192, 192))
    ).writeto(image)
    result = tmp_path / "attribution.json"

    subprocess.run(
        [
            sys.executable,
            str(_RUNNER),
            "--input",
            str(image),
            "--result",
            str(result),
            "--settings",
            json.dumps(_SETTINGS),
            "--frames",
            "4",
        ],
        check=True,
        capture_output=True,
    )

    record = cast(dict[str, Any], json.loads(result.read_text("utf-8")))
    assert record["source_count"] == 2
    assert record["import_bytes"] > 0
    spans = record["spans"]
    assert spans[0]["path"] == ["find_sources"]
    assert all(span["peak_bytes"] <= spans[0]["peak_bytes"] for span in spans)
    task_paths = [
        span["path"] for span in spans if span["path"][-1][:5] == "task "
    ]
    assert any("detect_multiscale_products" in path for path in task_paths)
    largest = record["largest_entry"]
    assert "detect_multiscale_products" in largest["path"][:-1]
    assert largest["bytes"] > record["import_bytes"]
    assert largest["sites"]
    assert all(site["bytes"] > 0 for site in largest["sites"])
