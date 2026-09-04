# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Executable specifications for frozen scheduler-independent behaviours."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

import numpy as np
import pytest
from astropy.io import fits

from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.data_models import MaterializedProduct
from hebog.executors import SerialExecutor
from hebog.pipeline import (
    UnsupportedSourceFinderConfigurationError,
    find_sources,
)

_PHASE_SIX = pytest.mark.xfail(
    strict=True,
    reason="distributed scale qualification begins in Phase 6",
)


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


def _request(tmp_path: Path, run_id: str = "contract") -> SourceFinderRequest:
    """Create a request for one valid empty radio-continuum image."""
    image_path = tmp_path / f"{run_id}.fits"
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = 4.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = 9.0
    header["CRPIX2"] = 9.0
    header["CRVAL1"] = 180.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["RESTFRQ"] = 150_000_000.0
    fits.PrimaryHDU(np.zeros((16, 16)), header).writeto(image_path)
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
    assert expected.schema_version == 2
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
    assert (
        min(
            expected.source_count,
            expected.gaussian_component_count,
            expected.island_count,
        )
        >= 0
    )


@pytest.mark.contract
def test_threshold_increase_cannot_create_source(
    tmp_path: Path,
) -> None:
    """The preview rejects an unevaluated threshold instead of detecting."""
    request = _request(tmp_path, run_id="unqualified-thresholds")

    with pytest.raises(
        UnsupportedSourceFinderConfigurationError,
        match="frozen Phase 5",
    ):
        find_sources(
            request,
            _config(
                detection_threshold_sigma=8.0,
                island_threshold_sigma=6.0,
            ),
            SerialExecutor(),
        )

    assert not request.output_directory.exists()


@pytest.mark.contract
@_PHASE_SIX
def test_partition_choices_preserve_results() -> None:
    """Executor planning choices preserve deterministic scientific results."""
    pytest.fail("end-to-end executor invariance begins in Phase 6")


@pytest.mark.contract
@_PHASE_SIX
def test_large_request_respects_worker_memory_budget() -> None:
    """Large work remains bounded by admitted tile and batch memory."""
    pytest.fail(
        "end-to-end distributed memory qualification begins in Phase 6"
    )
