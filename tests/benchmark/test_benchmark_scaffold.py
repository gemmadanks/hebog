"""Placeholder for the versioned performance regression suite."""

import pytest


@pytest.mark.benchmark
@pytest.mark.skip(reason="Benchmark harness is a Phase 0 deliverable")
def test_benchmark_harness_scaffold() -> None:
    """Keep the explicit benchmark target valid during scaffolding."""
