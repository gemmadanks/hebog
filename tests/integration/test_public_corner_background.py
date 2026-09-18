"""Independent noisy edge sources exercise the complete public map path."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits
from distributed import Client
from scipy.ndimage import gaussian_filter

from hebog import find_sources, public_api
from hebog.config import SourceFinderConfig
from hebog.data_models import SourceFinderRequest
from hebog.executors import DaskExecutor, SerialExecutor
from hebog.io import read_catalogue_fits_product


@pytest.mark.integration
@pytest.mark.parametrize("shape", ((512, 509), (599, 640)))
@pytest.mark.parametrize("seed", (2026981301, 2026981302))
def test_public_corner_sources_survive_background_estimation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shape: tuple[int, int],
    seed: int,
) -> None:
    """Real gradient/noise/invalid pixels cannot erase high-SNR corners."""
    y, x = np.indices(shape)
    mean = -2 + x / 1024 - y / 1536
    noise = gaussian_filter(np.random.default_rng(seed).normal(size=shape), 1)
    noise /= noise.std()
    centres = (
        (2.2, 1.8),
        (2.2, shape[1] - 2.3),
        (shape[0] - 2.7, 1.8),
        (shape[0] - 2.7, shape[1] - 2.3),
    )
    signal = sum(
        50 * np.exp(-0.5 * (((y - cy) / 4) ** 2 + ((x - cx) / 3) ** 2))
        for cy, cx in centres
    )
    image = mean + noise + signal
    image[0, 0] = np.nan
    header = fits.Header(
        {
            "BUNIT": "Jy/beam",
            "BMAJ": 4 / 3600,
            "BMIN": 4 / 3600,
            "BPA": 0.0,
            "RADESYS": "ICRS",
            "CTYPE1": "RA---TAN",
            "CTYPE2": "DEC--TAN",
            "CRPIX1": shape[1] / 2,
            "CRPIX2": shape[0] / 2,
            "CRVAL1": 180.0,
            "CRVAL2": -30.0,
            "CDELT1": -1 / 3600,
            "CDELT2": 1 / 3600,
            "RESTFRQ": 150e6,
        }
    )
    path = tmp_path / "corners.fits"
    fits.PrimaryHDU(image, header).writeto(path)
    original_estimator = public_api._estimate_background_rms
    maps: list[tuple[np.ndarray, np.ndarray]] = []

    def capture_maps(*args: Any, **kwargs: Any):
        result = original_estimator(*args, **kwargs)
        maps.append(result[1:])
        return result

    monkeypatch.setattr(public_api, "_estimate_background_rms", capture_maps)
    config = SourceFinderConfig(5.0, 3.0, 7)
    serial = find_sources(
        SourceFinderRequest(path, tmp_path / "serial", "corner-control"),
        config,
        SerialExecutor(),
    )
    background, rms = maps[0]
    mask = np.asarray(fits.getdata(serial.mask_path))
    assert np.isnan(background[0, 0]) and np.isnan(rms[0, 0])
    for cy, cx in centres:
        peak = (round(cy), round(cx))
        assert abs(background[peak] - mean[peak]) < 1.0
        assert 0.5 < rms[peak] < 1.5
        assert mask[peak] > 0
    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        distributed = find_sources(
            SourceFinderRequest(path, tmp_path / "dask", "corner-control"),
            config,
            DaskExecutor(client),
        )
    for expected, actual in zip(maps[0], maps[1], strict=True):
        np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(fits.getdata(distributed.mask_path), mask)
    assert read_catalogue_fits_product(distributed.catalogue) == (
        read_catalogue_fits_product(serial.catalogue)
    )
