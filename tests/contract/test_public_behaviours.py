"""Executable specifications for frozen scheduler-independent behaviours."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

import pytest

from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.data_models import MaterializedProduct
from hebog.executors import SerialExecutor
from hebog.pipeline import find_sources

_NOT_IMPLEMENTED = pytest.mark.xfail(
    strict=True,
    reason="frozen Phase 0 behaviour awaiting its implementation phase",
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
    """Create a file-oriented request without performing I/O."""
    return SourceFinderRequest(
        image_path=tmp_path / "input.fits",
        output_directory=tmp_path / "products",
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
    )


@pytest.mark.contract
@_NOT_IMPLEMENTED
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
@_NOT_IMPLEMENTED
def test_threshold_increase_cannot_create_source(tmp_path: Path) -> None:
    """Detection membership is monotonic under increasing thresholds."""
    request = _request(tmp_path, run_id="threshold-monotonicity")
    baseline = find_sources(request, _config(), SerialExecutor())
    higher = find_sources(
        request,
        _config(
            detection_threshold_sigma=8.0,
            island_threshold_sigma=6.0,
        ),
        SerialExecutor(),
    )

    assert higher.source_count <= baseline.source_count


@pytest.mark.contract
@_NOT_IMPLEMENTED
def test_partition_choices_preserve_results() -> None:
    """Executor planning choices preserve deterministic scientific results."""
    pytest.fail(
        "partition manifests and multi-tile execution begin in Phase 1"
    )


@pytest.mark.contract
@_NOT_IMPLEMENTED
def test_large_request_respects_worker_memory_budget() -> None:
    """Large work remains bounded by admitted tile and batch memory."""
    pytest.fail("bounded partition execution begins in Phase 1")
