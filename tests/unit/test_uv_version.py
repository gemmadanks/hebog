"""Every file that installs uv names the one version CI pins."""

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# Each file that installs uv, and the pattern that captures each version it
# names. Every setup-uv step in a workflow must name a version, or setup-uv
# installs the latest uv.
UV_VERSION_PATTERNS = {
    ".github/workflows/ci.yaml": r'UV_VERSION: "([^"]+)"',
    ".github/workflows/portable-tests.yaml": r'UV_VERSION: "([^"]+)"',
    ".github/workflows/docs-pages.yaml": r'(?m)^\s+version: "([^"]+)"',
    ".github/workflows/release-please.yaml": r'(?m)^\s+version: "([^"]+)"',
    ".github/workflows/slow-tests.yaml": r'(?m)^\s+version: "([^"]+)"',
    ".pre-commit-config.yaml": (
        r"astral-sh/uv-pre-commit\n(?:\s*#.*\n)*\s*rev: (\S+)"
    ),
    ".readthedocs.yaml": r"asdf (?:install|global) uv (\S+)",
    "Dockerfile": r"ARG UV_VERSION=(\S+)",
}
SETUP_UV_VERSION_INPUTS = {
    ".github/workflows/ci.yaml": (
        r"(?m)^\s+version: \$\{\{ env\.UV_VERSION \}\}$"
    ),
    ".github/workflows/portable-tests.yaml": (
        r"(?m)^\s+version: \$\{\{ env\.UV_VERSION \}\}$"
    ),
    ".github/workflows/docs-pages.yaml": r'(?m)^\s+version: "',
    ".github/workflows/release-please.yaml": r'(?m)^\s+version: "',
    ".github/workflows/slow-tests.yaml": r'(?m)^\s+version: "',
}


def _text(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def test_every_file_that_installs_uv_names_one_version() -> None:
    """The workflows, hook, docs build and image agree on one uv version."""
    versions = {
        relative_path: re.findall(pattern, _text(relative_path))
        for relative_path, pattern in UV_VERSION_PATTERNS.items()
    }

    assert all(versions.values()), versions
    assert len({v for found in versions.values() for v in found}) == 1, (
        versions
    )


def test_every_setup_uv_step_names_the_pinned_version() -> None:
    """No workflow step falls back to the latest uv."""
    workflows = sorted((REPOSITORY_ROOT / ".github/workflows").glob("*.yaml"))
    installing = {
        workflow.relative_to(REPOSITORY_ROOT).as_posix(): workflow
        for workflow in workflows
        if "astral-sh/setup-uv@" in workflow.read_text(encoding="utf-8")
    }

    assert set(installing) == set(SETUP_UV_VERSION_INPUTS)
    for relative_path, version_input in SETUP_UV_VERSION_INPUTS.items():
        text = _text(relative_path)
        assert len(re.findall(version_input, text)) == text.count(
            "astral-sh/setup-uv@"
        ), relative_path
