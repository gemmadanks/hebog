"""BDD-style executable specifications for Rapthor-facing behaviours."""

from __future__ import annotations

import pytest

_NOT_IMPLEMENTED = pytest.mark.xfail(
    strict=True,
    reason="frozen Phase 0 behaviour awaiting its implementation phase",
)


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_rapthor_adapter_materialises_compatibility_products() -> None:
    """Given a sector, then both branch and filtered products are returned."""
    pytest.fail("Rapthor compatibility adapter implementation begins later")


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_empty_image_returns_compatible_products() -> None:
    """Given an empty image, then valid zero-source products are returned."""
    pytest.fail("end-to-end empty-image analysis begins in Phase 2")


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_invalid_metadata_fails_before_success() -> None:
    """Given corrupt metadata, then no successful result is published."""
    pytest.fail("pipeline-level metadata failure begins in Phase 2")


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_retry_reuses_valid_stage_products() -> None:
    """Given valid stage products, then retry does not recompute them."""
    pytest.fail("end-to-end stage reuse begins in Phase 6")


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_worker_loss_preserves_final_products() -> None:
    """Given worker loss, then final products remain deterministic."""
    pytest.fail("distributed worker recovery begins in Phase 6")


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_rapthor_can_fallback_to_pybdsf() -> None:
    """Given Hebog failure, then Rapthor can select its PyBDSF fallback."""
    pytest.fail("Rapthor backend integration begins in Phase 9")


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_dual_run_keeps_products_and_reports_separate() -> None:
    """Given dual-run mode, then products and reports retain provenance."""
    pytest.fail("Rapthor dual-run integration begins in Phase 9")
