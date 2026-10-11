# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Bright sources that chain across the image are refined in bounded reads.

The background estimate refines the noise around each bright candidate, and
candidates whose influence boxes overlap merge into one region, which a
lattice of them spreads over the whole image. The region's fine cells are
estimated in blocks that each read a bounded context, and the products must
equal those of one read of the whole region under every executor.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from conftest import product_hashes

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.data_models import (
    BrightRegionCounts,
    PublicSourceFindingDiagnostics,
)
from hebog.executors import Executor, SerialExecutor
from hebog.io import read_diagnostics_product
from hebog.pipeline import SourceFinderResult
from hebog.stages import background as background_stage

pytestmark = pytest.mark.integration

# Under the 1,000,000-pixel read admission, so that one read of the whole
# region, the reference, is admitted too.
_SHAPE_YX = (960, 1024)
_BEAM_FWHM_PIXELS = 4.0
# Public refinement merges candidates less than 165 pixels apart: each
# reaches its 75-pixel influence radius and a 7-pixel fine step around it.
# Sources 150 pixels apart chain into one region over the image's 64 tiles.
_CENTRES = tuple(
    (float(y), float(x))
    for y in range(30, _SHAPE_YX[0], 150)
    for x in range(62, _SHAPE_YX[1], 150)
)


def _image() -> npt.NDArray[np.float64]:
    """Return unit noise with a lattice of 200-sigma compact sources."""
    yy, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]].astype(np.float64)
    sigma = _BEAM_FWHM_PIXELS / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    image = np.random.default_rng(53).normal(0.0, 1.0, _SHAPE_YX)
    for y, x in _CENTRES:
        image += 200.0 * np.exp(
            -((yy - y) ** 2 + (xx - x) ** 2) / (2.0 * sigma**2)
        )
    return image


def _header() -> fits.Header:
    """Return one valid ICRS header with a four-pixel beam."""
    height, width = _SHAPE_YX
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


def _find_sources(
    image_path: Path, output_directory: Path, executor: Executor
) -> SourceFinderResult:
    """Run the public finder on the shared input into one directory."""
    return hebog.find_sources(
        SourceFinderRequest(image_path, output_directory, "bright-lattice"),
        SourceFinderConfig(5.0, 3.0, 7),
        executor,
    )


def _bright_regions(result: SourceFinderResult) -> BrightRegionCounts:
    """Return what one run's diagnostics record about bright regions."""
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    return diagnostics.bright_regions


@pytest.fixture(scope="module")
def lattice(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write the shared lattice image once."""
    path = tmp_path_factory.mktemp("bright-lattice") / "image.fits"
    fits.PrimaryHDU(data=_image(), header=_header()).writeto(path)
    return path


@pytest.fixture(scope="module")
def whole_region(
    lattice: Path, tmp_path_factory: pytest.TempPathFactory
) -> SourceFinderResult:
    """Publish the products of one read of the whole chained region."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            background_stage, "_PROTECTED_CONTEXT_CELLS", 10**6
        )
        return _find_sources(
            lattice,
            tmp_path_factory.mktemp("whole") / "products",
            SerialExecutor(),
        )


@pytest.fixture(scope="module")
def bounded(
    lattice: Path, tmp_path_factory: pytest.TempPathFactory
) -> SourceFinderResult:
    """Publish the serial products of the bounded blocks."""
    return _find_sources(
        lattice,
        tmp_path_factory.mktemp("bounded") / "products",
        SerialExecutor(),
    )


def test_bounded_blocks_publish_the_whole_region_products(
    whole_region: SourceFinderResult, bounded: SourceFinderResult
) -> None:
    """Given a lattice that chains, bounded reads change no product.

    When the lattice is refined in blocks, then the catalogue, RMS and mask
    are those of one read of the whole region, and the diagnostics record
    every candidate and a largest read well inside the image.
    """
    assert product_hashes(bounded)[:3] == product_hashes(whole_region)[:3]
    whole = _bright_regions(whole_region)
    assert whole == BrightRegionCounts(
        candidate_count=len(_CENTRES),
        largest_read_pixels=_SHAPE_YX[0] * _SHAPE_YX[1],
    )
    blocks = _bright_regions(bounded)
    assert blocks.candidate_count == len(_CENTRES)
    assert 0 < blocks.largest_read_pixels < whole.largest_read_pixels
    assert bounded.source_count == len(_CENTRES)


def test_every_executor_publishes_the_bounded_products(
    tmp_path: Path,
    lattice: Path,
    bounded: SourceFinderResult,
    each_executor: Executor,
) -> None:
    """Blocks of a chained region give identical products on any executor."""
    result = _find_sources(lattice, tmp_path / "products", each_executor)

    assert product_hashes(result) == product_hashes(bounded)
