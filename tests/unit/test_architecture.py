"""Architecture tests for inward dependency direction."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).parents[2] / "src" / "hebog"

OUTER_DEPENDENCIES = (
    "dask",
    "distributed",
    "hebog.adapters",
    "hebog.executors",
    "hebog.io",
    "lsmtool",
    "prefect",
    "rapthor",
)

CORE_LAYER_RULES = {
    "algorithms": OUTER_DEPENDENCIES,
    "data_models": OUTER_DEPENDENCIES,
}


def _imported_modules(path: Path) -> set[str]:
    """Return statically declared imports from one Python module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _matches_prefix(module: str, prefix: str) -> bool:
    """Return whether an import is the prefix or one of its modules."""
    return module == prefix or module.startswith(f"{prefix}.")


@pytest.mark.parametrize(("layer", "forbidden"), CORE_LAYER_RULES.items())
def test_core_layers_do_not_depend_on_outer_layers(
    layer: str,
    forbidden: tuple[str, ...],
) -> None:
    """Scientific core dependencies point towards domain and array code."""
    violations: list[str] = []
    for path in sorted((PACKAGE_ROOT / layer).rglob("*.py")):
        for module in sorted(_imported_modules(path)):
            if any(_matches_prefix(module, prefix) for prefix in forbidden):
                relative_path = path.relative_to(PACKAGE_ROOT)
                violations.append(f"{relative_path}: {module}")

    assert violations == []
