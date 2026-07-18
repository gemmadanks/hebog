"""Executable specifications for frozen scheduler-independent behaviours."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

import pytest

from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.executors import SerialExecutor
from hebog.pipeline import find_sources

_NOT_IMPLEMENTED = pytest.mark.xfail(
    strict=True,
    reason="frozen Phase 0 behaviour awaiting its implementation phase",
)


class _ExpectedResult(Protocol):
    """Frozen product view expected from a successful public result."""

    catalogue_path: Path
    true_sky_rms_path: Path
    flat_noise_rms_path: Path
    mask_path: Path
    filtered_true_sky_path: Path
    filtered_apparent_sky_path: Path
    diagnostics_path: Path
    schema_version: int


def _request(tmp_path: Path, run_id: str = "contract") -> SourceFinderRequest:
    """Create a file-oriented request without performing I/O."""
    return SourceFinderRequest(
        image_path=tmp_path / "input.fits",
        output_directory=tmp_path / "products",
        run_id=run_id,
    )


@pytest.mark.contract
@_NOT_IMPLEMENTED
def test_valid_request_materialises_versioned_products(tmp_path: Path) -> None:
    """A successful result exposes every frozen product as plain metadata."""
    result = find_sources(
        _request(tmp_path),
        SourceFinderConfig(),
        SerialExecutor(),
    )
    expected = cast("_ExpectedResult", result)

    assert expected.catalogue_path.is_file()
    assert expected.true_sky_rms_path.is_file()
    assert expected.flat_noise_rms_path.is_file()
    assert expected.mask_path.is_file()
    assert expected.filtered_true_sky_path.is_file()
    assert expected.filtered_apparent_sky_path.is_file()
    assert expected.diagnostics_path.is_file()
    assert expected.schema_version >= 1


@pytest.mark.contract
@_NOT_IMPLEMENTED
def test_threshold_increase_cannot_create_source(tmp_path: Path) -> None:
    """Detection membership is monotonic under increasing thresholds."""
    request = _request(tmp_path, run_id="threshold-monotonicity")
    baseline = find_sources(request, SourceFinderConfig(), SerialExecutor())
    higher = find_sources(
        request,
        SourceFinderConfig(detection_sigma=8.0, island_sigma=6.0),
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
