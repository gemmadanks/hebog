"""Architecture tests for inward dependency direction."""

from __future__ import annotations

import ast
import subprocess
import sys
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

PUBLIC_CORE_MODULE_RULES = {
    "config.py": OUTER_DEPENDENCIES,
    "pipeline.py": (
        "dask",
        "distributed",
        "hebog.adapters",
        "hebog.executors.dask",
        "hebog.executors.serial",
        "hebog.io",
        "lsmtool",
        "prefect",
        "rapthor",
    ),
}

FORBIDDEN_IMPORT_CALLS = {
    "atexit.register",
    "builtins.input",
    "builtins.open",
    "builtins.print",
    "dask.compute",
    "dask.delayed",
    "dask.persist",
    "distributed.Client",
    "distributed.LocalCluster",
    "json.load",
    "logging.basicConfig",
    "numpy.load",
    "os.chdir",
    "os.mkdir",
    "os.makedirs",
    "os.popen",
    "os.remove",
    "os.rename",
    "os.replace",
    "os.rmdir",
    "os.system",
    "os.unlink",
    "pathlib.Path.chmod",
    "pathlib.Path.exists",
    "pathlib.Path.glob",
    "pathlib.Path.is_dir",
    "pathlib.Path.is_file",
    "pathlib.Path.iterdir",
    "pathlib.Path.mkdir",
    "pathlib.Path.open",
    "pathlib.Path.read_bytes",
    "pathlib.Path.read_text",
    "pathlib.Path.rename",
    "pathlib.Path.replace",
    "pathlib.Path.resolve",
    "pathlib.Path.rglob",
    "pathlib.Path.rmdir",
    "pathlib.Path.stat",
    "pathlib.Path.touch",
    "pathlib.Path.unlink",
    "pathlib.Path.write_bytes",
    "pathlib.Path.write_text",
    "prefect.flow",
    "prefect.task",
    "signal.signal",
    "socket.create_connection",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.run",
    "urllib.request.urlopen",
}

FORBIDDEN_ORCHESTRATION_METHODS = {
    "compute",
    "gather",
    "persist",
    "submit",
}

FORBIDDEN_IMPORT_IO_METHODS = {
    "chmod",
    "exists",
    "glob",
    "is_dir",
    "is_file",
    "iterdir",
    "mkdir",
    "open",
    "read_bytes",
    "read_text",
    "rename",
    "resolve",
    "rglob",
    "rmdir",
    "stat",
    "touch",
    "unlink",
    "write_bytes",
    "write_text",
}


class _ImportAliasVisitor(ast.NodeVisitor):
    """Collect names bound by imports that execute at module scope."""

    def __init__(self) -> None:
        self.aliases: dict[str, str] = {
            "input": "builtins.input",
            "open": "builtins.open",
            "print": "builtins.print",
        }

    def visit_Import(self, node: ast.Import) -> None:
        """Record the name bound by an absolute import."""
        for alias in node.names:
            bound_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
            self.aliases[bound_name] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record names bound by a from-import."""
        if node.module is None:
            return
        for alias in node.names:
            bound_name = alias.asname or alias.name
            self.aliases[bound_name] = f"{node.module}.{alias.name}"

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Skip imports that occur only when a function is called."""
        del node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Skip imports that occur only when a coroutine is called."""
        del node

    def visit_Lambda(self, node: ast.Lambda) -> None:
        """Skip deferred lambda bodies."""
        del node

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Avoid treating class-namespace imports as module bindings."""
        del node


def _qualified_name(
    node: ast.expr,
    aliases: dict[str, str],
) -> str | None:
    """Resolve a syntactic callable name through module import aliases."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        owner_node = (
            node.value.func if isinstance(node.value, ast.Call) else node.value
        )
        owner = _qualified_name(owner_node, aliases)
        return f"{owner}.{node.attr}" if owner is not None else node.attr
    return None


class _ImportScopeCallVisitor(ast.NodeVisitor):
    """Find forbidden calls that execute while a module is imported."""

    def __init__(self, aliases: dict[str, str]) -> None:
        self.aliases = aliases
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        """Record forbidden boundaries and inspect eager call arguments."""
        name = _qualified_name(node.func, self.aliases)
        if name is not None:
            leaf_name = name.rsplit(".", maxsplit=1)[-1]
            if (
                name in FORBIDDEN_IMPORT_CALLS
                or leaf_name in FORBIDDEN_ORCHESTRATION_METHODS
                or leaf_name in FORBIDDEN_IMPORT_IO_METHODS
            ):
                self.violations.append(f"line {node.lineno}: {name}")
        self.generic_visit(node)

    def _visit_definition_expressions(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """Inspect decorators and defaults but not deferred function bodies."""
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Inspect only expressions evaluated while defining a function."""
        self._visit_definition_expressions(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Inspect only expressions evaluated while defining a coroutine."""
        self._visit_definition_expressions(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        """A lambda body is deferred until the lambda is called."""
        for default in node.args.defaults:
            self.visit(default)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Inspect eager class construction while skipping method bodies."""
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        for statement in node.body:
            self.visit(statement)


def _import_scope_side_effects(source: str) -> list[str]:
    """Return forbidden import-scope calls from Python source text."""
    tree = ast.parse(source)
    alias_visitor = _ImportAliasVisitor()
    alias_visitor.visit(tree)
    call_visitor = _ImportScopeCallVisitor(alias_visitor.aliases)
    call_visitor.visit(tree)
    return call_visitor.violations


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


@pytest.mark.parametrize(
    ("module_name", "forbidden"),
    PUBLIC_CORE_MODULE_RULES.items(),
)
def test_public_core_does_not_import_outer_implementations(
    module_name: str,
    forbidden: tuple[str, ...],
) -> None:
    """Configuration and pipeline composition stay adapter-independent."""
    modules = _imported_modules(PACKAGE_ROOT / module_name)
    violations = sorted(
        module
        for module in modules
        if any(_matches_prefix(module, prefix) for prefix in forbidden)
    )

    assert violations == []


def test_import_scope_analyzer_rejects_io_and_orchestration() -> None:
    """The architecture gate recognizes aliased eager boundary calls."""
    source = """
from distributed import Client as SchedulerClient
from pathlib import Path

TEXT = Path("input.txt").read_text()
CLIENT = SchedulerClient()
"""

    assert _import_scope_side_effects(source) == [
        "line 5: pathlib.Path.read_text",
        "line 6: distributed.Client",
    ]


def test_import_scope_analyzer_allows_deferred_boundary_calls() -> None:
    """I/O and execution remain permitted behind explicit callable APIs."""
    source = """
from pathlib import Path

def load(path: Path) -> str:
    return path.read_text()
"""

    assert _import_scope_side_effects(source) == []


def test_package_modules_have_no_import_scope_side_effects() -> None:
    """Importing library modules cannot start work or touch science data."""
    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if path.name == "__main__.py":
            continue
        source = path.read_text(encoding="utf-8")
        for violation in _import_scope_side_effects(source):
            relative_path = path.relative_to(PACKAGE_ROOT)
            violations.append(f"{relative_path}: {violation}")

    assert violations == []


def test_public_pipeline_import_does_not_load_distributed() -> None:
    """The scheduler-independent API does not eagerly import Dask runtime."""
    program = (
        "import sys; import hebog.pipeline; "
        "raise SystemExit(bool({'dask', 'distributed'} & sys.modules.keys()))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
