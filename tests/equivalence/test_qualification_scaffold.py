"""Placeholder for the held-out scientific qualification suite."""

import pytest


@pytest.mark.equivalence
@pytest.mark.qualification
@pytest.mark.requires_data
@pytest.mark.skip(reason="Qualification datasets are a Phase 0 deliverable")
def test_qualification_harness_scaffold() -> None:
    """Keep the controlled qualification target valid during scaffolding."""
