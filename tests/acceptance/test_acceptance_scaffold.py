"""BDD-style executable specifications for Rapthor-facing behaviours.

`config/contracts/phase-0-public-behaviours.json` names the test that holds
each behaviour; the scenarios here are strict-xfail placeholders.
"""

from __future__ import annotations

import pytest

_NOT_IMPLEMENTED = pytest.mark.xfail(
    strict=True,
    reason="the Rapthor adapter makes this pass (plan task 19)",
)


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_rapthor_adapter_materialises_compatibility_products() -> None:
    """Given a sector, then both branch and filtered products are returned."""
    pytest.fail("not implemented")


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_retry_reuses_valid_stage_products() -> None:
    """Given valid stage products, then retry does not recompute them."""
    pytest.fail("not implemented")


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_worker_loss_preserves_final_products() -> None:
    """Given worker loss, then final products remain deterministic."""
    pytest.fail("not implemented")


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_rapthor_can_fallback_to_pybdsf() -> None:
    """Given Hebog failure, then Rapthor can select its PyBDSF fallback."""
    pytest.fail("not implemented")


@pytest.mark.acceptance
@_NOT_IMPLEMENTED
def test_dual_run_keeps_products_and_reports_separate() -> None:
    """Given dual-run mode, then products and reports retain provenance."""
    pytest.fail("not implemented")
