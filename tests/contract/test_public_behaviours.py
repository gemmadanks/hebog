# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Executable specifications for frozen scheduler-independent behaviours.

`config/contracts/phase-0-public-behaviours.json` names the test that holds
each behaviour; an unimplemented one is a strict-xfail placeholder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from hebog import SourceFinderConfig, SourceFinderRequest, SourceFinderResult
from hebog.data_models import MaterializedProduct
from hebog.executors import SerialExecutor
from hebog.io import read_catalogue_fits_product
from hebog.pipeline import find_sources

_SHAPE_YX = (64, 64)
_BEAM_FWHM_PIXELS = 4.0
_NOISE_JY_PER_BEAM = 1e-3
# Pixel x, y and peak signal-to-noise ratio of the two sources: one far
# above every threshold these tests use, and one between the default
# five-sigma detection threshold and the raised eight-sigma one.
_BRIGHT_SOURCE = (20.0, 20.0, 30.0)
_NEAR_THRESHOLD_SOURCE = (44.0, 40.0, 6.5)


class _ExpectedResult(Protocol):
    """Pipeline-neutral products from one scientific image analysis."""

    run_id: str
    catalogue: MaterializedProduct
    rms: MaterializedProduct
    mask: MaterializedProduct
    diagnostics: MaterializedProduct
    catalogue_path: Path
    rms_path: Path
    mask_path: Path
    diagnostics_path: Path
    source_count: int
    gaussian_component_count: int
    island_count: int
    schema_version: int


def _header() -> fits.Header:
    """Return a celestial header with a four-pixel circular beam."""
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = _BEAM_FWHM_PIXELS / 3600.0
    header["BMIN"] = _BEAM_FWHM_PIXELS / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = 33.0
    header["CRPIX2"] = 33.0
    header["CRVAL1"] = 180.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["RESTFRQ"] = 150_000_000.0
    return header


def _image() -> npt.NDArray[np.float64]:
    """Return seeded white noise under two beam-shaped point sources.

    Noise covers every pixel, so no region of the image is constant.
    """
    sigma_pixels = _BEAM_FWHM_PIXELS / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    y_pixels, x_pixels = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    image = np.random.default_rng(20261005).normal(
        0.0, _NOISE_JY_PER_BEAM, _SHAPE_YX
    )
    for x, y, signal_to_noise in (_BRIGHT_SOURCE, _NEAR_THRESHOLD_SOURCE):
        squared_distance = (x_pixels - x) ** 2 + (y_pixels - y) ** 2
        image += (
            signal_to_noise
            * _NOISE_JY_PER_BEAM
            * np.exp(-0.5 * squared_distance / sigma_pixels**2)
        )
    return image


def _request(tmp_path: Path, run_id: str = "contract") -> SourceFinderRequest:
    """Create a request for the two-source radio-continuum image."""
    image_path = tmp_path / f"{run_id}.fits"
    fits.PrimaryHDU(_image(), _header()).writeto(image_path)
    return SourceFinderRequest(
        image_path=image_path,
        output_directory=tmp_path / f"products-{run_id}",
        run_id=run_id,
    )


def _config(
    *,
    detection_threshold_sigma: float = 5.0,
    island_threshold_sigma: float = 3.0,
) -> SourceFinderConfig:
    """Create an explicit scientific threshold profile."""
    return SourceFinderConfig(
        detection_threshold_sigma=detection_threshold_sigma,
        island_threshold_sigma=island_threshold_sigma,
        minimum_island_pixels=7,
    )


def _source_pixels(result: SourceFinderResult) -> npt.NDArray[np.float64]:
    """Return each published source's pixel x, y, one row per source."""
    sources = read_catalogue_fits_product(result.catalogue).sources
    sky = np.asarray(
        [
            (
                source.position.right_ascension_degrees,
                source.position.declination_degrees,
            )
            for source in sources
        ],
        dtype=np.float64,
    ).reshape(-1, 2)
    x_pixels, y_pixels = cast(
        "tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]",
        WCS(_header()).world_to_pixel_values(sky[:, 0], sky[:, 1]),
    )
    return np.column_stack((x_pixels, y_pixels))


def _published_near(
    source_pixels: npt.NDArray[np.float64], x: float, y: float
) -> bool:
    """Return whether a published source lies within half a beam of x, y."""
    distances = np.hypot(source_pixels[:, 0] - x, source_pixels[:, 1] - y)
    return bool(np.any(distances <= 0.5 * _BEAM_FWHM_PIXELS))


@pytest.mark.contract
def test_valid_request_materialises_versioned_products(tmp_path: Path) -> None:
    """A successful result exposes every frozen product as plain metadata."""
    result = find_sources(
        _request(tmp_path),
        _config(),
        SerialExecutor(),
    )
    expected = cast("_ExpectedResult", result)

    assert expected.catalogue_path.is_file()
    assert expected.rms_path.is_file()
    assert expected.mask_path.is_file()
    assert expected.diagnostics_path.is_file()
    assert expected.run_id == "contract"
    assert expected.schema_version == 3
    assert (
        expected.catalogue.product_role,
        expected.rms.product_role,
        expected.mask.product_role,
        expected.diagnostics.product_role,
    ) == (
        "source-catalogue",
        "rms",
        "source-filtering-mask",
        "diagnostics",
    )
    source_pixels = _source_pixels(result)
    assert len(source_pixels) == expected.source_count
    assert _published_near(source_pixels, *_BRIGHT_SOURCE[:2])
    assert expected.gaussian_component_count >= expected.source_count
    assert expected.island_count >= 1
    mask = np.asarray(fits.getdata(expected.mask_path), dtype=np.bool_)
    assert mask[int(_BRIGHT_SOURCE[1]), int(_BRIGHT_SOURCE[0])]


@pytest.mark.contract
def test_threshold_increase_cannot_create_source(
    tmp_path: Path,
) -> None:
    """Higher caller-owned thresholds publish no source the lower ones lack.

    The near-threshold source is published only under the lower thresholds,
    so the two catalogues being compared differ.
    """
    reference = find_sources(
        _request(tmp_path, run_id="reference-thresholds"),
        _config(),
        SerialExecutor(),
    )

    higher = find_sources(
        _request(tmp_path, run_id="higher-thresholds"),
        _config(
            detection_threshold_sigma=8.0,
            island_threshold_sigma=6.0,
        ),
        SerialExecutor(),
    )

    reference_pixels = _source_pixels(reference)
    higher_pixels = _source_pixels(higher)
    assert _published_near(reference_pixels, *_NEAR_THRESHOLD_SOURCE[:2])
    assert not _published_near(higher_pixels, *_NEAR_THRESHOLD_SOURCE[:2])
    assert _published_near(higher_pixels, *_BRIGHT_SOURCE[:2])
    assert all(
        _published_near(reference_pixels, x, y) for x, y in higher_pixels
    )
    assert higher.source_count < reference.source_count


@pytest.mark.contract
@pytest.mark.xfail(
    strict=True,
    reason="no stage declares its memory yet (plan task 17)",
)
def test_large_request_respects_worker_memory_budget() -> None:
    """Large work remains bounded by admitted tile and batch memory."""
    pytest.fail("no stage declares a task's memory requirement")
