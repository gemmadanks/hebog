# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""The calibration runner records the point estimator a run used."""

from __future__ import annotations

import runpy
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits

import hebog
from hebog.data_models import SourceFindingDiagnostics
from hebog.executors import SerialExecutor
from hebog.science import configuration, continuum

_ROOT = Path(__file__).parents[2]
_RUNNER = runpy.run_path(
    str(
        _ROOT
        / "scripts"
        / "validation"
        / "measure_component_uncertainty_calibration.py"
    )
)
_NOISE_RMS = 1e-4
_BEAM_FWHM_PIXELS = 4.0


def _header(shape_yx: tuple[int, int]) -> fits.Header:
    """Return one valid ICRS radio-continuum FITS header."""
    height, width = shape_yx
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = _BEAM_FWHM_PIXELS / 3600.0
    header["BMIN"] = _BEAM_FWHM_PIXELS / 3600.0
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


def _two_beam_sized_sources() -> npt.NDArray[np.float64]:
    """Return white noise with two isolated beam-sized sources."""
    size = 128
    y_pixels, x_pixels = np.mgrid[:size, :size]
    image = np.random.default_rng(3).normal(0.0, _NOISE_RMS, (size, size))
    sigma = _BEAM_FWHM_PIXELS / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    for y_center, x_center, snr in ((40.0, 40.0, 30.0), (90.0, 80.0, 50.0)):
        image += (
            snr
            * _NOISE_RMS
            * np.exp(
                -0.5
                * ((x_pixels - x_center) ** 2 + (y_pixels - y_center) ** 2)
                / sigma**2
            )
        )
    return np.asarray(image, dtype=np.float64)


@pytest.mark.integration
def test_runner_reads_the_point_estimator_back_from_the_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorded estimator is the one each published fit reports.

    The installed estimator is diagonal-weighted, so a request the override
    failed to reach would read back as that rather than as the request.
    """
    # The runner replaces these module attributes; restore them afterwards.
    for module in (configuration, continuum):
        monkeypatch.setattr(
            module,
            "source_finder_configs",
            module.source_finder_configs,
        )
    use_point_estimator: Callable[[str], None] = _RUNNER[
        "_use_point_estimator"
    ]
    point_estimators_run: Callable[
        [Path], tuple[Counter[str], Counter[str]]
    ] = _RUNNER["_point_estimators_run"]
    image_path = tmp_path / "image.fits"
    image = _two_beam_sized_sources()
    fits.PrimaryHDU(data=image, header=_header(image.shape)).writeto(
        image_path
    )

    use_point_estimator("correlated-gls")
    result = hebog.find_sources(
        hebog.SourceFinderRequest(image_path, tmp_path / "products", "gls"),
        hebog.SourceFinderConfig(5.0, 3.0, 7),
        SerialExecutor(),
    )
    estimators, fallbacks = point_estimators_run(result.diagnostics_path)

    assert result.gaussian_component_count == 2
    assert estimators == Counter({"correlated-gls": 2})
    assert fallbacks == Counter()


@pytest.mark.integration
def test_runner_refuses_diagnostics_without_dispositions(
    tmp_path: Path,
) -> None:
    """Reading back needs the public run's per-component dispositions."""
    point_estimators_run: Callable[[Path], object] = _RUNNER[
        "_point_estimators_run"
    ]
    path = tmp_path / "diagnostics.json"
    path.write_bytes(
        SourceFindingDiagnostics(
            run_id="population-summary",
            source_count=0,
            gaussian_component_count=0,
            island_count=0,
            rms_scientific_status="valid",
        ).canonical_json_bytes()
    )

    with pytest.raises(TypeError, match="not a public run's diagnostics"):
        point_estimators_run(path)
