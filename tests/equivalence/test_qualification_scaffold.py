"""Controlled-runner entry point for held-out scientific qualification."""

import pytest


@pytest.mark.equivalence
@pytest.mark.qualification
@pytest.mark.requires_data
@pytest.mark.skip(reason="Requires held-out data on an approved runner")
def test_qualification_harness_scaffold() -> None:
    """Keep the controlled qualification target explicit and isolated."""
