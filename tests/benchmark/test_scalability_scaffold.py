"""Placeholder for large-image and multi-node scalability qualification."""

import pytest


@pytest.mark.benchmark
@pytest.mark.scalability
@pytest.mark.slow
@pytest.mark.requires_data
@pytest.mark.skip(reason="Scalability harness is a Phase 0 deliverable")
def test_scalability_harness_scaffold() -> None:
    """Keep the controlled scalability target valid during scaffolding."""
