"""Traceability checks for accepted Phase 5 development defects."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).parents[3]
_REGISTRY = _ROOT / "config/contracts/phase-5-regression-fixtures.json"
_REQUIRED_DEFECT_IDS = frozenset(
    {
        "candidate-composition-binding",
        "compact-component-compiler-semantics",
        "compact-component-specific-bias",
        "compact-independent-free-ellipse",
        "compact-source-component-separation",
        "continuum-multiscale-refinement",
        "continuum-original-pixel-photometry",
        "continuum-regularized-position-signal",
        "continuum-reviewed-aperture",
        "edge-filter-support-renormalization",
        "evaluator-dual-accelerator-identity",
        "extended-segment-position-semantics",
        "fitless-detection-retention",
        "masked-filter-support-renormalization",
        "runtime-source-path-binding",
        "symmetric-valid-domain",
        "viewed-runtime-provenance",
    }
)
_CATEGORIES = frozenset(
    {
        "campaign-composition",
        "numerical-science",
        "product-semantics",
        "runtime-provenance",
    }
)


@pytest.fixture(scope="module")
def registry() -> dict[str, Any]:
    """Load the machine-readable defect-to-fixture registry."""
    return json.loads(_REGISTRY.read_text())


def test_registry_covers_every_accepted_defect_once(
    registry: dict[str, Any],
) -> None:
    """Every accepted defect remains explicitly represented."""
    assert registry["schema_version"] == 1
    assert registry["phase"] == 5
    assert registry["status"] == "development-regression"

    defects = registry["accepted_defects"]
    defect_ids = [defect["id"] for defect in defects]
    assert len(defect_ids) == len(set(defect_ids))
    assert frozenset(defect_ids) == _REQUIRED_DEFECT_IDS
    assert {defect["category"] for defect in defects} == _CATEGORIES


@pytest.mark.parametrize("required_key", ["root_cause", "invariant"])
def test_registry_records_explanatory_evidence(
    registry: dict[str, Any],
    required_key: str,
) -> None:
    """Each fixture records why it exists and what must remain true."""
    for defect in registry["accepted_defects"]:
        assert isinstance(defect[required_key], str)
        assert defect[required_key].strip()
        revision = defect["accepted_fix_revision"]
        assert len(revision) in {7, 40}
        assert all(character in "0123456789abcdef" for character in revision)


def test_every_registered_fixture_names_a_collected_test(
    registry: dict[str, Any],
) -> None:
    """Named regression fixtures must remain concrete pytest functions."""
    registered_node_ids: list[str] = []
    parsed_files: dict[Path, frozenset[str]] = {}
    for defect in registry["accepted_defects"]:
        node_ids = defect["regression_tests"]
        assert node_ids
        assert len(node_ids) == len(set(node_ids))
        registered_node_ids.extend(node_ids)
        for node_id in node_ids:
            relative_path, separator, test_name = node_id.partition("::")
            assert separator == "::"
            assert relative_path.startswith("tests/")
            assert test_name.startswith("test_")

            path = _ROOT / relative_path
            assert path.is_file(), node_id
            if path not in parsed_files:
                module = ast.parse(path.read_text())
                parsed_files[path] = frozenset(
                    node.name
                    for node in module.body
                    if isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef)
                    )
                )
            assert test_name in parsed_files[path], node_id

    assert len(registered_node_ids) == len(set(registered_node_ids))
