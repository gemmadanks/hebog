"""Build and import the project package in a clean environment."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def run(
    command: list[str],
    *,
    environment: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> None:
    """Run a smoke-test command."""
    subprocess.run(
        command,
        check=True,
        cwd=REPOSITORY_ROOT if cwd is None else cwd,
        env=environment,
    )


def package_module_name() -> str:
    """Return the importable module configured for the uv build backend."""
    pyproject_path = REPOSITORY_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    module_name = pyproject["tool"]["uv"]["build-backend"]["module-name"]

    if not isinstance(module_name, str) or not module_name:
        msg = "[tool.uv.build-backend].module-name must be a non-empty string"
        raise ValueError(msg)

    return module_name


def check_wheel_contents(wheel: Path, module_name: str) -> None:
    """Require the licence and exclude repository-only validation tooling."""
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
        msg = f"wheel does not contain the licence file: {wheel}"
        raise RuntimeError(msg)
    excluded = f"{module_name}/validation/"
    if any(name.startswith(excluded) for name in names):
        msg = f"wheel contains repository-only tooling {excluded}: {wheel}"
        raise RuntimeError(msg)


def main() -> None:
    """Build, install, and verify the wheel's top-level import."""
    module_name = package_module_name()

    with tempfile.TemporaryDirectory(prefix="package-smoke-") as temporary_dir:
        temporary_path = Path(temporary_dir)
        distribution_dir = temporary_path / "dist"
        virtual_environment = temporary_path / "venv"

        run(["uv", "build", "--out-dir", str(distribution_dir)])

        wheels = list(distribution_dir.glob("*.whl"))
        if len(wheels) != 1:
            msg = (
                f"expected one wheel in {distribution_dir}, "
                f"found {len(wheels)}"
            )
            raise RuntimeError(msg)
        check_wheel_contents(wheels[0], module_name)

        run(
            [
                "uv",
                "venv",
                "--python",
                sys.executable,
                str(virtual_environment),
            ]
        )

        python_executable = virtual_environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )

        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python_executable),
                str(wheels[0]),
            ]
        )

        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PACKAGE_SMOKE_MODULE"] = module_name
        run(
            [
                "uv",
                "run",
                "--no-project",
                "--python",
                str(python_executable),
                "python",
                "-c",
                (
                    "import importlib, os; "
                    "module = importlib.import_module("
                    "os.environ['PACKAGE_SMOKE_MODULE']); "
                    "print(f'Imported {module.__name__} successfully')"
                ),
            ],
            environment=environment,
            cwd=temporary_path,
        )
        run(
            [
                str(python_executable),
                str(REPOSITORY_ROOT / "scripts/public_api_package_smoke.py"),
            ],
            environment=environment,
            cwd=temporary_path,
        )


if __name__ == "__main__":
    main()
