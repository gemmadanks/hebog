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
from conftest import published_plane
from scipy.ndimage import gaussian_filter

from hebog import public_api
from hebog.config import SourceFinderConfig
from hebog.data_models.partitioning import ImageBounds
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
    plane = ImageBounds(0, image.shape[0], 0, image.shape[1])
    estimated_rms = np.asarray(
        scientific.background_rms_source.read_completed_window("rms", plane),
        dtype=np.float64,
    )
    estimated_background = np.asarray(
        scientific.background_rms_source.read_completed_window(
            "background", plane
        ),
        dtype=np.float64,
    )
    assert (
        np.median(
            np.abs(estimated_background[support] - background[support])
            / rms[support]
        )
        < 0.5
    )
    assert np.median(np.abs(estimated_rms[support] / rms[support] - 1)) < 0.25
    assert scientific.terminal is not None
    assert scientific.publication_source is not None
    recovered = (
        published_plane(
            scientific.publication_source, "retained-mask", np.bool_
        )
        & support
    )
    assert np.count_nonzero(recovered) / np.count_nonzero(support) >= 0.75
    if noisy_neighbourhood:
        assert estimated_rms[centre_y, 96] > 2.0
    assert estimated_background[centre_y, 256] < 0


@pytest.mark.integration
@pytest.mark.parametrize("shape_yx", ((800, 800), (640, 1024)))
def test_wide_extended_emission_keeps_its_noise_and_support(
    tmp_path: Path,
    shape_yx: tuple[int, int],
) -> None:
    """Noise over a source wider than the clean-cell reach stays the noise.

    The shorter side is at least 600 pixels, so the coarse grid is the
    unprotected clipped estimate, which over a bright extended source is
    mostly the source. The source is wider than twice the 75-pixel reach of
    the local-noise floor's clean cells, so its interior has no clean cell
    in reach (plan task 69). The published RMS over the emission above
    three times the noise must stay near the injected noise, and the
    retained mask must keep most of that emission.
    """
    height, columns = shape_yx
    centre_y, centre_x = height // 2, columns // 2
    yy, xx = np.mgrid[:height, :columns]
    rotation = np.deg2rad(30.0)
    major = np.cos(rotation) * (xx - centre_x) + np.sin(rotation) * (
        yy - centre_y
    )
    minor = -np.sin(rotation) * (xx - centre_x) + np.cos(rotation) * (
        yy - centre_y
    )
    # A disc narrower than the 150-pixel background box, so the background
    # does not absorb it, with bright knots along two arms out to a radius
    # of 180 pixels, as a nearby spiral galaxy appears: structure the
    # clipping cannot remove, so the coarse clipped estimate over the disc
    # is many times the noise, and a source wider than twice the reach.
    extended = 40.0 * np.exp(
        -0.5 * ((major / 45.0) ** 2 + (minor / 35.0) ** 2)
    )
    for index in range(16):
        angle = index * np.pi / 8
        radius = 30.0 + 10.0 * index
        knot_x = centre_x + radius * np.cos(angle)
        knot_y = centre_y + radius * np.sin(angle)
        extended = extended + 50.0 * np.exp(
            -0.5 * (((xx - knot_x) ** 2 + (yy - knot_y) ** 2) / 10.0**2)
        )
    compact = sum(
        peak * np.exp(-0.5 * (((xx - x) ** 2 + (yy - y) ** 2) / 2.0**2))
        for x, y, peak in (
            (centre_x, centre_y, 300.0),
            (centre_x + 55, centre_y - 20, 40.0),
            (centre_x - 250, centre_y + 150, 40.0),
        )
    )
    noise = gaussian_filter(
        np.random.default_rng(1069).normal(size=xx.shape), 1
    )
    noise /= noise.std()
    image = extended + compact + noise
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ("RA---TAN", "DEC--TAN")
    wcs.wcs.crpix = (centre_x + 1, centre_y + 1)
    wcs.wcs.crval = (10, -30)
    wcs.wcs.cdelt = (-1 / 3600, 1 / 3600)
    header = wcs.to_header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = header["BMIN"] = 4 / 3600
    header["BPA"] = 0
    header["RESTFRQ"] = 150e6
    input_path = tmp_path / "wide-extended-source.fits"
    fits.PrimaryHDU(image, header).writeto(input_path)
    source = FitsImageSource(input_path)
    scientific = public_api._analyse_image(
        SourceFinderRequest(input_path, tmp_path / "output", "wide-fixture"),
        source,
        source.metadata(),
        SerialExecutor(),
        tmp_path / "work",
        config=SourceFinderConfig(5.0, 3.0, 7),
        header=header,
    )
    support = extended >= 3.0
    plane = ImageBounds(0, image.shape[0], 0, image.shape[1])
    estimated_rms = np.asarray(
        scientific.background_rms_source.read_completed_window("rms", plane),
        dtype=np.float64,
    )
    # The noise is 1 everywhere; the coarse clipped estimate over the source
    # is several times that, and must not reach the published RMS.
    assert np.median(np.abs(estimated_rms[support] - 1.0)) < 0.25
    assert np.percentile(estimated_rms[support], 95) < 1.5
    assert scientific.terminal is not None
    assert scientific.publication_source is not None
    recovered = (
        published_plane(
            scientific.publication_source, "retained-mask", np.bool_
        )
        & support
    )
    # Before the floor (v0.18.0) the mask kept 0.74 and 0.80 of the support
    # on the two shapes; under the floor it keeps 0.4 or less.
    assert np.count_nonzero(recovered) / np.count_nonzero(support) >= 0.7
