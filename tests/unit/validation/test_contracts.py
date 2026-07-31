"""Tests for frozen Phase 0 performance and behaviour contracts."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from hebog.validation.contracts import (
    PerformanceMatrixContract,
    ScalabilityContract,
    load_performance_matrix,
    load_public_behaviours,
    load_scalability_contract,
)

_ROOT = Path(__file__).parents[3]
_PERFORMANCE_PATH = _ROOT / "config/benchmarks/phase-0-performance.json"
_SCALABILITY_PATH = _ROOT / "config/benchmarks/phase-0-scalability.json"
_BEHAVIOURS_PATH = _ROOT / "config/contracts/phase-0-public-behaviours.json"


def test_checked_in_performance_matrix_covers_curve_and_workloads() -> None:
    """Every frozen size has all density classes and comparison rules."""
    matrix = load_performance_matrix(_PERFORMANCE_PATH)

    assert matrix.sizes_pixels[0] == 256
    assert matrix.sizes_pixels[-1] == 100_000
    assert len(matrix.sizes_pixels) >= 8
    assert len(matrix.workload_classes) == 3
    assert matrix.previous_hebog.minimum_measured_repetitions >= 5


def test_performance_matrix_rejects_a_missing_workload_class() -> None:
    """A fast sparse path cannot stand in for normal and dense work."""
    matrix = load_performance_matrix(_PERFORMANCE_PATH)
    payload = matrix.model_dump(mode="json")
    payload["workload_classes"] = payload["workload_classes"][:-1]

    with pytest.raises(ValidationError, match="every workload class"):
        PerformanceMatrixContract.model_validate(payload)


def test_checked_in_scalability_contract_freezes_required_topologies() -> None:
    """The 100k case owns explicit planes, memory, storage, and node gates."""
    contract = load_scalability_contract(_SCALABILITY_PATH)

    assert contract.logical_shape_yx == (100_000, 100_000)
    assert [gate.worker_nodes for gate in contract.node_gates] == [
        1,
        10,
        50,
        100,
        200,
    ]
    assert contract.resource_profile.node_memory_bytes == 512 * 1024**3
    assert contract.maximum_worker_peak_fraction == 0.75


def test_scalability_contract_rejects_overcommitted_worker_memory() -> None:
    """Concurrent pipeline and platform reserves constrain worker admission."""
    contract = load_scalability_contract(_SCALABILITY_PATH)
    payload = contract.model_dump(mode="json")
    payload["resource_profile"]["worker_memory_limit_bytes"] = 100 * 1024**3

    with pytest.raises(ValidationError, match="worker limits"):
        ScalabilityContract.model_validate(payload)


def test_every_public_behaviour_has_one_strict_xfail_owner() -> None:
    """Frozen behaviours start with a failing executable specification."""
    manifest = load_public_behaviours(_BEHAVIOURS_PATH)

    assert len(manifest.behaviours) == 11
    assert all(
        behaviour.expected_until_implemented == "strict-xfail"
        for behaviour in manifest.behaviours
    )
    assert len({item.test_id for item in manifest.behaviours}) == len(
        manifest.behaviours
    )


def test_public_behaviour_manifest_matches_executable_test_ids() -> None:
    """Every frozen behaviour names one collected executable test."""
    manifest = load_public_behaviours(_BEHAVIOURS_PATH)
    test_paths = (
        _ROOT / "tests/contract/test_public_behaviours.py",
        _ROOT / "tests/acceptance/test_acceptance_scaffold.py",
    )
    implemented_test_ids = {
        node.name
        for path in test_paths
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }

    assert implemented_test_ids == {
        behaviour.test_id for behaviour in manifest.behaviours
    }
