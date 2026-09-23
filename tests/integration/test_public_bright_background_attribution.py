"""Independent bright-emission and real-noise controls for public maps."""

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
from scipy.ndimage import gaussian_filter

from hebog import public_api
from hebog.config import SourceFinderConfig
from hebog.data_models.source_finding import SourceFinderRequest
from hebog.executors import SerialExecutor
from hebog.io import FitsImageSource


@pytest.mark.integration
@pytest.mark.parametrize("width", (10.0, 24.0))
@pytest.mark.parametrize("noisy_neighbourhood", (False, True))
@pytest.mark.parametrize(
    "shape_yx",
    (
        (384, 512),
        (150, 512),
        (599, 512),
        (600, 512),
        (599, 640),
        (600, 640),
    ),
)
def test_bright_halo_is_not_background_but_noise_inflation_is_retained(
    tmp_path: Path,
    width: float,
    noisy_neighbourhood: bool,
    shape_yx: tuple[int, int],
) -> None:
    """A known halo and independent noise patch have different attribution."""
    height, columns = shape_yx
    centre_y = height // 2
    yy, xx = np.mgrid[:height, :columns]
    radius_squared = (xx - 256) ** 2 + (yy - centre_y) ** 2
    background = -2.0 + xx / 1024
    rms = np.ones(xx.shape)
    if noisy_neighbourhood:
        rms += 3 * np.exp(
            -0.5 * (((xx - 96) / 35) ** 2 + ((yy - centre_y) / 35) ** 2)
        )
    noise = gaussian_filter(
        np.random.default_rng(619).normal(size=xx.shape), 1
    )
    noise /= noise.std()
    halo = 12 * np.exp(-0.5 * radius_squared / width**2)
    signal = halo + 1000 * np.exp(-0.5 * radius_squared / 2**2)
    image = signal + background + rms * noise
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ("RA---TAN", "DEC--TAN")
    wcs.wcs.crpix = (257, centre_y + 1)
    wcs.wcs.crval = (10, -30)
    wcs.wcs.cdelt = (-1 / 3600, 1 / 3600)
    header = wcs.to_header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = header["BMIN"] = 4 / 3600
    header["BPA"] = 0
    header["RESTFRQ"] = 150e6
    input_path = tmp_path / "independent-bright-halo.fits"
    fits.PrimaryHDU(image, header).writeto(input_path)
    source = FitsImageSource(input_path)
    scientific = public_api._analyse_image(
        SourceFinderRequest(input_path, tmp_path / "output", "bright-fixture"),
        source,
        source.metadata(),
        SerialExecutor(),
        tmp_path / "work",
        config=SourceFinderConfig(5.0, 3.0, 7),
        header=header,
    )
    support = halo >= 3 * rms
    estimated_rms = scientific.read_rms_window(
        (slice(0, image.shape[0]), slice(0, image.shape[1]))
    )
    assert (
        np.median(
            np.abs(scientific.background[support] - background[support])
            / rms[support]
        )
        < 0.5
    )
    assert np.median(np.abs(estimated_rms[support] / rms[support] - 1)) < 0.25
    assert scientific.terminal is not None
    recovered = scientific.terminal.detection.retained_mask & support
    assert np.count_nonzero(recovered) / np.count_nonzero(support) >= 0.75
    if noisy_neighbourhood:
        assert estimated_rms[centre_y, 96] > 2.0
    assert scientific.background[centre_y, 256] < 0
