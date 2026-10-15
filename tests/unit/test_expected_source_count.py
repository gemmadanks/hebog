# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Unit tests for the source-count estimate a caller sizes memory from."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

import hebog
from hebog import (
    InvalidSourceFinderInputError,
    UnsupportedSourceFinderConfigurationError,
    expected_source_count,
)
from hebog.algorithms.source_count import (
    BLOCK_PIXELS,
    MINIMUM_BLOCK_SAMPLES,
    BlockNoise,
    block_noise,
    count_peaks,
    peak_threshold,
    reference_sigma,
)
from hebog.data_models.partitioning import ImageBounds
from hebog.io import FitsImageSource

_PEAK_SIGMA = 1.0


def _header() -> fits.Header:
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 100.0
    header["CRPIX2"] = 100.0
    header["CRVAL1"] = 210.0
    header["CRVAL2"] = 54.0
    header["CDELT1"] = -1.5 / 3600
    header["CDELT2"] = 1.5 / 3600
    header["CUNIT1"] = "deg"
    header["CUNIT2"] = "deg"
    header["RADESYS"] = "ICRS"
    header["BMAJ"] = 6.0 / 3600
    header["BMIN"] = 6.0 / 3600
    header["BPA"] = 0.0
    header["BUNIT"] = "JY/BEAM"
    header["RESTFRQ"] = 144e6
    return header


def _write(path: Path, plane: np.ndarray) -> Path:
    fits.PrimaryHDU(plane.astype(np.float32), header=_header()).writeto(path)
    return path


def _sources(
    plane: np.ndarray, positions: list[tuple[int, int]], peak: float
) -> np.ndarray:
    """Add point sources with a 4-pixel Gaussian beam at the positions."""
    y, x = np.mgrid[: plane.shape[0], : plane.shape[1]]
    for row, column in positions:
        plane = plane + peak * np.exp(
            -((y - row) ** 2 + (x - column) ** 2) / (2 * 1.7**2)
        )
    return plane


def _noise(shape: tuple[int, int], seed: int = 20261014) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(shape)


def test_the_estimate_is_exported_from_the_package() -> None:
    """A caller sizes its reservation from the public package alone."""
    assert hebog.expected_source_count is expected_source_count
    assert "expected_source_count" in hebog.__all__


def test_a_block_measures_its_clipped_noise() -> None:
    """A bright pixel is clipped away from the block's noise."""
    values = 2.0 * _noise((100, 100))
    values[50, 50] = 1_000.0

    noise = block_noise(values, np.ones(values.shape, dtype=bool))

    assert noise is not None
    assert noise.median == pytest.approx(0.0, abs=0.1)
    assert noise.sigma == pytest.approx(2.0, rel=0.05)


def test_a_block_without_enough_valid_pixels_has_no_noise() -> None:
    """Too few samples, or a spread of zero, measure nothing."""
    values = _noise((20, 20))
    valid = np.zeros(values.shape, dtype=bool)
    valid.flat[: MINIMUM_BLOCK_SAMPLES - 1] = True

    assert block_noise(values, valid) is None
    assert (
        block_noise(np.ones((20, 20)), np.ones((20, 20), dtype=bool)) is None
    )


def test_peaks_are_the_cores_valid_local_maxima_at_the_threshold() -> None:
    """The window's margin is neighbour only; invalid pixels are no one's.

    The core is the inner 4x4 of a 6x6 window. Its 5 counts at the
    threshold; its 9 is outranked by the margin's 10 beside it; its 7 is a
    maximum only because its higher neighbour is invalid; and its two
    equal 6s both count. The margin's own 10 is outside the core.
    """
    values = np.zeros((6, 6))
    valid = np.ones((6, 6), dtype=bool)
    values[1, 1] = 5.0
    values[1, 4] = 9.0
    values[0, 5] = 10.0
    values[3, 1] = 7.0
    values[4, 1] = 8.0
    valid[4, 1] = False
    values[4, 3] = values[4, 4] = 6.0

    peaks = count_peaks(values, valid, (slice(1, 5), slice(1, 5)), 5.0)

    assert peaks == 4


def test_an_invalid_pixel_is_never_a_peak() -> None:
    """A blank pixel's stored value is no measurement."""
    values = np.zeros((3, 3))
    values[1, 1] = 100.0
    valid = np.ones((3, 3), dtype=bool)
    valid[1, 1] = False

    assert count_peaks(values, valid, (slice(0, 3), slice(0, 3)), 1.0) == 0


def test_isolated_sources_are_counted_once_each(tmp_path: Path) -> None:
    """Ten point sources at 8 sigma on white noise are ten peaks."""
    positions = [(60 + 40 * k, 50 + 37 * k) for k in range(10)]
    image = _write(
        tmp_path / "image.fits",
        _sources(_noise((520, 520)), positions, 8.0),
    )

    assert expected_source_count(image, detection_threshold_sigma=5.0) == 10


def test_a_quiet_block_keeps_its_own_lower_noise(tmp_path: Path) -> None:
    """A primary-beam-corrected image is noisier towards its edges.

    The left block's noise is 1 and the other two blocks' 3, so the
    image's typical noise is 3. Six 7-sigma sources in the quiet block
    would be lost under it; under their own block's noise they all count,
    and a noisy one can show a second peak.
    """
    noise = _noise((BLOCK_PIXELS, 3 * BLOCK_PIXELS))
    noise[:, BLOCK_PIXELS:] *= 3.0
    positions = [(60 + 70 * k, 100 + 40 * k) for k in range(6)]
    without = _write(tmp_path / "without.fits", noise)
    with_sources = _write(
        tmp_path / "with.fits", _sources(noise, positions, 7.0)
    )

    added = expected_source_count(
        with_sources, detection_threshold_sigma=5.0
    ) - expected_source_count(without, detection_threshold_sigma=5.0)

    assert added >= 6


def test_a_peak_is_measured_from_its_blocks_median() -> None:
    """The threshold sits the detection threshold's noises above the median."""
    noise = BlockNoise(median=2.0, sigma=1.5)

    assert peak_threshold(noise, reference_sigma=4.0, detection_sigma=5.0) == (
        pytest.approx(9.5)
    )


def test_a_noisy_block_is_measured_against_the_typical_noise() -> None:
    """A bright source or a noisy edge inflates a block's spread.

    Its threshold uses the image's typical noise instead, so the faint
    sources beside a bright one are not lost.
    """
    noisy = BlockNoise(median=0.0, sigma=10.0)

    assert peak_threshold(noisy, reference_sigma=1.0, detection_sigma=5.0) == (
        pytest.approx(5.0)
    )


def test_the_typical_noise_is_the_median_of_the_blocks() -> None:
    """One bright block does not move it."""
    noises = [
        BlockNoise(0.0, 1.0),
        BlockNoise(0.0, 1.2),
        BlockNoise(0.0, 50.0),
    ]

    assert reference_sigma(noises) == pytest.approx(1.2)
    assert reference_sigma([]) is None


@pytest.mark.parametrize("fill", [np.nan, 0.0])
def test_an_image_without_measurable_noise_has_no_sources(
    tmp_path: Path, fill: float
) -> None:
    """Blank pixels, NaN or a repeated value, hold no peak."""
    image = _write(tmp_path / "image.fits", np.full((64, 64), fill))

    assert expected_source_count(image, detection_threshold_sigma=5.0) == 0


def test_the_image_is_read_in_bounded_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No read is wider than a block and the pixel either side of it."""
    image = _write(tmp_path / "image.fits", _noise((1_100, 700)))
    read = FitsImageSource.read_windows
    sizes: list[tuple[int, int]] = []

    def recording(
        source: FitsImageSource, bounds: tuple[ImageBounds, ...]
    ) -> object:
        bounds = tuple(bounds)
        sizes.extend(item.shape_yx for item in bounds)
        return read(source, bounds)

    monkeypatch.setattr(FitsImageSource, "read_windows", recording)

    expected_source_count(image, detection_threshold_sigma=5.0)

    assert sizes
    assert max(max(size) for size in sizes) <= BLOCK_PIXELS + 2


@pytest.mark.parametrize("threshold", [0.0, -1.0, float("nan"), float("inf")])
def test_an_impossible_threshold_is_refused(
    tmp_path: Path, threshold: float
) -> None:
    """A threshold no analysis runs with cannot size a reservation."""
    image = _write(tmp_path / "image.fits", _noise((32, 32)))

    with pytest.raises(ValueError, match="detection_threshold_sigma"):
        expected_source_count(image, detection_threshold_sigma=threshold)


def test_an_unsupported_image_is_refused_as_find_sources_refuses_it(
    tmp_path: Path,
) -> None:
    """A file that is not a continuum image raises the typed input error."""
    path = tmp_path / "image.fits"
    path.write_bytes(b"not a FITS file")

    with pytest.raises(InvalidSourceFinderInputError):
        expected_source_count(path, detection_threshold_sigma=5.0)


def test_an_image_find_sources_refuses_is_refused_before_it_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A beam the finder is not measured for is refused without a read.

    The estimate is of what ``find_sources`` publishes, so a caller falls
    back as soon as either refuses, without counting the image first.
    """
    header = _header()
    header["BMAJ"] = header["BMIN"] = 60.0 / 3600
    path = tmp_path / "image.fits"
    fits.PrimaryHDU(
        _noise((64, 64)).astype(np.float32), header=header
    ).writeto(path)

    def unexpected(*_: object) -> object:
        raise AssertionError("a refused image must not be read")

    monkeypatch.setattr(FitsImageSource, "read_windows", unexpected)

    with pytest.raises(UnsupportedSourceFinderConfigurationError):
        expected_source_count(path, detection_threshold_sigma=5.0)


def test_block_noise_is_a_plain_record() -> None:
    """The record holds only the two statistics."""
    assert BlockNoise(median=1.0, sigma=2.0) == BlockNoise(1.0, 2.0)
