"""Architecture tests for inward dependency direction.

``LAYER_IMPORTS`` is the layering as one table: for every layer of the
``hebog`` package, a top-level module or subpackage, the other layers its
modules may import. Every import statement counts, at module scope, in a
function or under ``TYPE_CHECKING``. The table is acyclic, so it reads as one
direction, from ``adapters`` through ``pipeline`` and ``public_api`` to
``stages``, ``science`` and ``algorithms``, with ``data_models`` and
``config`` shared by every layer. No production layer may import
``hebog.validation``, which wheels exclude. An import outside the table is
allowed only by a named exemption, and each exemption must still match.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from functools import cache
from graphlib import TopologicalSorter
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).parents[2] / "src" / "hebog"

LAYER_IMPORTS: dict[str, frozenset[str]] = {
    # Development tooling, excluded from wheels, may use every production
    # layer but the entry point; no production row names it.
    "validation": frozenset(
        {
            "__init__",
            "adapters",
            "algorithms",
            "cli",
            "config",
            "data_models",
            "executors",
            "io",
            "pipeline",
            "public_api",
            "public_science",
            "resources",
            "science",
            "stages",
        }
    ),
    # The ``python -m hebog`` entry point runs the command line.
    "__main__": frozenset({"cli"}),
    "cli": frozenset({"__init__"}),
    # Adapters translate a consumer's names through the public API, the
    # shared records and the product files, never the composition.
    "adapters": frozenset(
        {"__init__", "config", "data_models", "executors", "io", "pipeline"}
    ),
    # The package initializer re-exports the public names.
    "__init__": frozenset({"config", "data_models", "pipeline"}),
    # The public entry point and its error types; it reaches the composition
    # only through a deferred import (``LAYER_EXEMPTIONS``).
    "pipeline": frozenset({"config", "data_models", "executors"}),
    # The outer I/O layer validates and admits input, calls the stage
    # sequence and publishes the products.
    "public_api": frozenset(
        {
            "algorithms",
            "config",
            "data_models",
            "executors",
            "io",
            "pipeline",
            "public_science",
            "science",
            "stages",
        }
    ),
    # Builds the terminal catalogues from the records the stages published.
    "public_science": frozenset(
        {"algorithms", "config", "data_models", "science"}
    ),
    # Apply the kernels tile by tile through the caller's executor, and
    # run the stages in order (``stages/composition.py``).
    "stages": frozenset(
        {"algorithms", "config", "data_models", "executors", "io", "science"}
    ),
    # The reviewed profile and configuration, the composition records and
    # the catalogue-row kernels, which import no stage, executor or io.
    "science": frozenset({"algorithms", "config", "data_models"}),
    "algorithms": frozenset({"config", "data_models"}),
    "executors": frozenset({"config", "data_models"}),
    "io": frozenset({"config", "data_models"}),
    # Shared by every layer, so they import none.
    "config": frozenset(),
    "data_models": frozenset(),
    # Packaged data, which public_api reads by name rather than imports.
    "resources": frozenset(),
}

LAYER_EXEMPTIONS: dict[tuple[str, str], str] = {
    ("io/__init__.py", "hebog.algorithms.astrometry"): (
        "The package re-exports the WCS the image metadata describes, so a "
        "reader of FitsImageSource takes both from hebog.io; no io module "
        "calls a kernel."
    ),
    ("pipeline.py", "hebog.public_api"): (
        "find_sources imports the implementation when called, so importing "
        "hebog loads no FITS, Zarr or scientific module; DEFERRED_IMPORTS "
        "keeps it deferred."
    ),
}
"""Imports outside ``LAYER_IMPORTS``, by module path and imported module."""

DEFERRED_IMPORTS: dict[tuple[str, str], str] = {
    ("pipeline.py", "hebog.public_api"): (
        "Importing hebog or hebog.pipeline loads no I/O or scientific code."
    ),
    ("executors/__init__.py", "hebog.executors.dask"): (
        "DaskExecutor loads distributed only when a caller asks for it."
    ),
}
"""Imports that may run only in a function or under ``TYPE_CHECKING``."""

WORKFLOW_PACKAGES = ("lsmtool", "prefect", "rapthor")
"""Packages no module of ``hebog`` imports, adapters included."""

SCHEDULER_PACKAGES = ("dask", "distributed")
SCHEDULER_LAYER = "executors"
"""The only layer that imports a scheduler package, but for exemptions."""

SCHEDULER_EXEMPTIONS: dict[tuple[str, str], str] = {
    ("validation/profile_cluster.py", "distributed"): (
        "The execution profiler's local cluster keeps every worker's clock "
        "offset at zero, which no executor option sets; wheels exclude "
        "hebog.validation and no production module imports it."
    ),
}
"""Scheduler imports outside ``SCHEDULER_LAYER``, by module and package."""

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


@dataclass(frozen=True, slots=True)
class _StaticImport:
    """One name an import statement binds, and whether it runs on import.

    ``name`` is the imported module, followed for a from-import by the name
    taken from it, so ``from hebog import validation`` names
    ``hebog.validation``. A relative import keeps its leading dots.
    """

    name: str
    line: int
    runs_on_import: bool


def _is_type_checking(test: ast.expr) -> bool:
    """Return whether an ``if`` test is ``TYPE_CHECKING``, however named."""
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


class _StaticImportVisitor(ast.NodeVisitor):
    """Collect every import statement in any scope of one module."""

    def __init__(self) -> None:
        self.imports: list[_StaticImport] = []
        self._deferred = False

    def _record(self, name: str, node: ast.Import | ast.ImportFrom) -> None:
        """Record one imported name at the current scope."""
        self.imports.append(
            _StaticImport(name, node.lineno, runs_on_import=not self._deferred)
        )

    def visit_Import(self, node: ast.Import) -> None:
        """Record each module an import statement names."""
        for alias in node.names:
            self._record(alias.name, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record each name a from-import takes, under its module."""
        module = "." * node.level + (node.module or "")
        separator = "" if module.endswith(".") else "."
        for alias in node.names:
            self._record(f"{module}{separator}{alias.name}", node)

    def _visit_deferred(self, nodes: list[ast.stmt]) -> None:
        """Visit statements that do not run while the module is imported."""
        deferred = self._deferred
        self._deferred = True
        for statement in nodes:
            self.visit(statement)
        self._deferred = deferred

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """A function body runs only when the function is called."""
        self._visit_deferred(node.body)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """A coroutine body runs only when the coroutine is awaited."""
        self._visit_deferred(node.body)

    def visit_If(self, node: ast.If) -> None:
        """A ``TYPE_CHECKING`` block never runs; its ``else`` does."""
        if not _is_type_checking(node.test):
            self.generic_visit(node)
            return
        self._visit_deferred(node.body)
        for statement in node.orelse:
            self.visit(statement)


def _static_imports(path: Path) -> list[_StaticImport]:
    """Return every import statement of one module, in any scope."""
    visitor = _StaticImportVisitor()
    visitor.visit(
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    )
    return visitor.imports


def _matches_prefix(module: str, prefix: str) -> bool:
    """Return whether an import is the prefix or one of its modules."""
    return module == prefix or module.startswith(f"{prefix}.")


def _relative_path(path: Path) -> str:
    """Return a module path relative to the package, as POSIX text."""
    return path.relative_to(PACKAGE_ROOT).as_posix()


def _layer_of_path(path: Path) -> str:
    """Return the layer one module of the package belongs to."""
    return path.relative_to(PACKAGE_ROOT).parts[0].removesuffix(".py")


def _package_layers() -> set[str]:
    """Return every layer the package holds a module in."""
    return {_layer_of_path(path) for path in PACKAGE_ROOT.rglob("*.py")}


def _imported_layer(name: str, layers: set[str]) -> str | None:
    """Return the ``hebog`` layer an imported name belongs to, if any.

    A name taken from the package itself that is not a layer, such as
    ``hebog.__version__``, belongs to the package initializer.
    """
    parts = name.split(".")
    if parts[0] != "hebog":
        return None
    if len(parts) > 1 and parts[1] in layers:
        return parts[1]
    return "__init__"


@cache
def _package_imports() -> tuple[tuple[Path, _StaticImport], ...]:
    """Return every import statement of every module of the package.

    The package is parsed once a test session; every rule reads this.
    """
    return tuple(
        (path, imported)
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        for imported in _static_imports(path)
    )


def _layer_table_violations() -> list[tuple[str, _StaticImport]]:
    """Return each import of another layer that ``LAYER_IMPORTS`` rejects."""
    layers = _package_layers()
    violations: list[tuple[str, _StaticImport]] = []
    for path, imported in _package_imports():
        layer = _layer_of_path(path)
        target = _imported_layer(imported.name, layers)
        if (
            target is not None
            and target != layer
            and target not in LAYER_IMPORTS[layer]
        ):
            violations.append((_relative_path(path), imported))
    return violations


def _is_exempt(module_path: str, imported: _StaticImport) -> bool:
    """Return whether a named exemption allows one rejected import."""
    return any(
        module_path == exempt_path and _matches_prefix(imported.name, prefix)
        for exempt_path, prefix in LAYER_EXEMPTIONS
    )


def test_layer_table_names_every_layer_once() -> None:
    """Every layer has a row, and every row and import names a layer."""
    assert set(LAYER_IMPORTS) == _package_layers()
    unknown = {
        f"{layer}: {target}"
        for layer, allowed in LAYER_IMPORTS.items()
        for target in allowed
        if target not in LAYER_IMPORTS or target == layer
    }
    assert unknown == set()


def test_layer_table_points_one_way() -> None:
    """The rows form no cycle, so each named edge forbids its reverse."""
    TopologicalSorter(LAYER_IMPORTS).prepare()

    assert "pipeline" in LAYER_IMPORTS["adapters"]
    assert "stages" in LAYER_IMPORTS["public_api"]
    assert "science" in LAYER_IMPORTS["stages"]
    assert "algorithms" in LAYER_IMPORTS["science"]


def test_no_production_layer_may_import_campaign_validation() -> None:
    """Wheels exclude ``hebog.validation``, so only it may use itself."""
    importers = sorted(
        layer
        for layer, allowed in LAYER_IMPORTS.items()
        if "validation" in allowed
    )

    assert importers == []


@pytest.mark.parametrize("layer", sorted(LAYER_IMPORTS))
def test_layer_imports_only_what_the_table_allows(layer: str) -> None:
    """Each layer imports only the layers its row names, or an exemption."""
    violations = [
        f"{module_path}:{imported.line}: {imported.name}"
        for module_path, imported in _layer_table_violations()
        if _layer_of_path(PACKAGE_ROOT / module_path) == layer
        and not _is_exempt(module_path, imported)
    ]

    assert violations == []


@pytest.mark.parametrize(("module_path", "prefix"), sorted(LAYER_EXEMPTIONS))
def test_layer_exemption_still_matches(module_path: str, prefix: str) -> None:
    """An exemption that no longer allows an import fails loudly."""
    assert any(
        exempt_path == module_path and _matches_prefix(imported.name, prefix)
        for exempt_path, imported in _layer_table_violations()
    ), "the exemption allows no import the table rejects; remove it"


@pytest.mark.parametrize(("module_path", "prefix"), sorted(DEFERRED_IMPORTS))
def test_deferred_import_stays_deferred(module_path: str, prefix: str) -> None:
    """A deferred import still exists and never runs on module import."""
    imports = [
        imported
        for imported in _static_imports(PACKAGE_ROOT / module_path)
        if _matches_prefix(imported.name, prefix)
    ]

    assert imports, "the deferred import must still exist"
    assert [
        imported.line for imported in imports if imported.runs_on_import
    ] == []


def test_package_imports_its_own_modules_by_absolute_name() -> None:
    """The layer table reads absolute names, so no import is relative."""
    relative = [
        f"{_relative_path(path)}:{imported.line}: {imported.name}"
        for path, imported in _package_imports()
        if imported.name.startswith(".")
    ]

    assert relative == []


@pytest.mark.parametrize("package", WORKFLOW_PACKAGES)
def test_no_module_imports_a_workflow_framework(package: str) -> None:
    """Rapthor, Prefect and LSMTool stay outside the package, adapters too."""
    violations = [
        f"{_relative_path(path)}:{imported.line}: {imported.name}"
        for path, imported in _package_imports()
        if _matches_prefix(imported.name, package)
    ]

    assert violations == []


def _scheduler_imports() -> list[tuple[str, _StaticImport]]:
    """Return every import of a scheduler package, by module path."""
    return [
        (_relative_path(path), imported)
        for path, imported in _package_imports()
        if any(
            _matches_prefix(imported.name, package)
            for package in SCHEDULER_PACKAGES
        )
    ]


def test_only_the_executors_import_a_scheduler() -> None:
    """Dask is reached through an executor, or a named exemption."""
    importers = {
        _layer_of_path(PACKAGE_ROOT / module_path)
        for module_path, imported in _scheduler_imports()
        if not any(
            module_path == exempt_path
            and _matches_prefix(imported.name, prefix)
            for exempt_path, prefix in SCHEDULER_EXEMPTIONS
        )
    }

    assert importers == {SCHEDULER_LAYER}


@pytest.mark.parametrize(
    ("module_path", "prefix"), sorted(SCHEDULER_EXEMPTIONS)
)
def test_scheduler_exemption_still_matches(
    module_path: str, prefix: str
) -> None:
    """A scheduler exemption that no longer allows an import fails loudly."""
    assert _layer_of_path(PACKAGE_ROOT / module_path) != SCHEDULER_LAYER
    assert any(
        exempt_path == module_path and _matches_prefix(imported.name, prefix)
        for exempt_path, imported in _scheduler_imports()
    ), "the exemption allows no scheduler import; remove it"


def test_static_imports_mark_deferred_and_relative_imports() -> None:
    """The import reader sees every scope and keeps a relative import."""
    source = """
from typing import TYPE_CHECKING
from hebog import validation
from . import sibling

if TYPE_CHECKING:
    from hebog.stages import detection
else:
    import hebog.science

def run() -> None:
    import hebog.public_api
"""
    visitor = _StaticImportVisitor()
    visitor.visit(ast.parse(source))

    assert visitor.imports == [
        _StaticImport("typing.TYPE_CHECKING", 2, runs_on_import=True),
        _StaticImport("hebog.validation", 3, runs_on_import=True),
        _StaticImport(".sibling", 4, runs_on_import=True),
        _StaticImport("hebog.stages.detection", 7, runs_on_import=False),
        _StaticImport("hebog.science", 9, runs_on_import=True),
        _StaticImport("hebog.public_api", 12, runs_on_import=False),
    ]


def _annotated_fields(path: Path) -> list[tuple[str, str, str]]:
    """Return every annotated class field of one module, as source text."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (node.name, item.target.id, ast.unparse(item.annotation))
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        for item in node.body
        if isinstance(item, ast.AnnAssign)
        and isinstance(item.target, ast.Name)
    ]


def test_composition_records_declare_no_image_sized_array() -> None:
    """The records the driver holds carry no plane, as ADR-008 requires.

    Every plane a pass writes stays in the generation it published to, where
    a later pass reads it by window, so a record that reaches the driver
    declares no array at all. This is the static half of that rule; the
    per-record fields it checks are what the terminal composition is made of.
    """
    fields = [
        field
        for module in ("models.py", "catalogue_rows.py")
        for field in _annotated_fields(PACKAGE_ROOT / "science" / module)
    ]
    assert fields, "the composition records must be readable"
    arrays = sorted(
        f"{class_name}.{field}: {annotation}"
        for class_name, field, annotation in fields
        if "ndarray" in annotation.lower()
    )

    assert arrays == []


def test_public_science_import_does_not_load_campaign_validation() -> None:
    """Runtime science imports no closed campaign package transitively."""
    program = (
        "import sys; import hebog.public_science; "
        "raise SystemExit(any(name == 'hebog.validation' or "
        "name.startswith('hebog.validation.') for name in sys.modules))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


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


def _constructed_names(path: Path) -> set[str]:
    """Return every callable name this module constructs in any scope."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    alias_visitor = _ImportAliasVisitor()
    alias_visitor.visit(tree)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _qualified_name(node.func, alias_visitor.aliases)
            if name is not None:
                names.add(name.rsplit(".", maxsplit=1)[-1])
    return names


@pytest.mark.parametrize(
    ("constructor", "permitted_module"),
    [
        ("LocalCluster", None),
        ("Client", None),
        ("ProcessPoolExecutor", None),
        ("ThreadPoolExecutor", "executors/threads.py"),
        ("Pool", None),
    ],
)
def test_library_never_creates_its_own_workers(
    constructor: str,
    permitted_module: str | None,
) -> None:
    """Only the caller's executor owns workers; stages never nest pools."""
    if permitted_module is not None:
        # Fail loudly if the exemption stops matching the module it names,
        # which would make this rule silently vacuous.
        assert constructor in _constructed_names(
            PACKAGE_ROOT / permitted_module
        )
    violations = [
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        # Module paths are compared as POSIX text so the rule reads the same
        # on every supported platform.
        if not path.relative_to(PACKAGE_ROOT)
        .as_posix()
        .startswith("validation/")
        and path.relative_to(PACKAGE_ROOT).as_posix() != permitted_module
        and constructor in _constructed_names(path)
    ]

    assert violations == []
