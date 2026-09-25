"""Independent truth controls for spatial public RMS without bright sources."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from conftest import estimated_maps
from scipy.ndimage import gaussian_filter

from hebog import public_api
from hebog.config import SourceFinderConfig
from hebog.executors import SerialExecutor
from hebog.io import FitsImageSource

pytestmark = pytest.mark.integration


def _public_maps(
    image: np.ndarray, tmp_path: Path
) -> tuple[np.ndarray, np.ndarray]:
    """Exercise the exact public map boundary without catalogue fitting."""
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ("RA---TAN", "DEC--TAN")
    wcs.wcs.crpix = (1, 1)
    wcs.wcs.crval = (10, -30)
    wcs.wcs.cdelt = (-1 / 3600, 1 / 3600)
    header = wcs.to_header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = header["BMIN"] = 4 / 3600
    header["BPA"] = 0
    header["RESTFRQ"] = 150e6
    input_path = tmp_path / "noise.fits"
    fits.PrimaryHDU(image, header).writeto(input_path)
    source = FitsImageSource(input_path)
    metadata = source.metadata()
    sink, _ = public_api._estimate_background_rms(
        source,
        metadata,
        SourceFinderConfig(5.0, 3.0, 7),
        SerialExecutor(),
        tmp_path / "work",
        generation_id="noise-fixture",
    )
    return estimated_maps(sink, metadata.shape_yx)


@pytest.mark.parametrize("width", (18, 40, 80))
@pytest.mark.parametrize("correlation", (0.0, 1.0, 2.0))
@pytest.mark.parametrize(
    "centre_yx", ((110, 110), (256, 320), (8, 8), (503, 631))
)
def test_local_noise_is_resolved_without_a_bright_source(
    tmp_path: Path,
    width: int,
    correlation: float,
    centre_yx: tuple[int, int],
) -> None:
    """A fine-resolvable true noise patch must not need a source trigger."""
    yy, xx = np.mgrid[:512, :640]
    radius = (yy - centre_yx[0]) ** 2 + (xx - centre_yx[1]) ** 2
    truth = 1 + 3 * np.exp(-0.5 * radius / width**2)
    background = -2 + xx / 1024
    noise = np.random.default_rng(821).normal(size=xx.shape)
    if correlation:
        noise = gaussian_filter(noise, correlation)
    noise /= noise.std()
    estimated_background, estimated_rms = _public_maps(
        background + truth * noise, tmp_path
    )
    assert np.isfinite(estimated_rms).all()
    assert np.all(estimated_rms > 0)
    assert estimated_rms[centre_yx] > truth[centre_yx] / 2
    assert np.median(np.abs(estimated_rms / truth - 1)) < 0.25
    assert np.median(np.abs(estimated_background - background) / truth) < 0.2
    # Source masking must not discard a positive half of ordinary noise.
    normalized = (background + truth * noise - estimated_background) / (
        estimated_rms
    )
    assert np.mean(normalized > 5) < 0.001


@pytest.mark.parametrize("gradient", (False, True))
def test_local_noise_retains_flat_and_smooth_noise_fields(
    tmp_path: Path, gradient: bool
) -> None:
    """Resolving a patch must not destabilize ordinary background and RMS."""
    yy, xx = np.mgrid[:256, :384]
    truth = 0.5 + xx / 256 if gradient else np.ones(xx.shape)
    background = -1 + yy / 512
    noise = gaussian_filter(
        np.random.default_rng(822).normal(size=xx.shape), 1
    )
    noise /= noise.std()
    estimated_background, estimated_rms = _public_maps(
        background + truth * noise, tmp_path
    )
    assert np.median(np.abs(estimated_rms / truth - 1)) < 0.2
    assert np.median(np.abs(estimated_background - background) / truth) < 0.2
