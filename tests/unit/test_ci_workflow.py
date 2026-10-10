# pyright: reportMissingTypeStubs=false
"""The sharded workflow keeps the full matrix and existing required gates."""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> dict[str, Any]:
    return yaml.safe_load(
        (ROOT / f".github/workflows/{name}.yaml").read_text(encoding="utf-8")
    )


def test_every_matrix_environment_has_a_complete_shard_plan() -> None:
    jobs = _workflow("ci")["jobs"]
    environments = jobs["portable"]["strategy"]["matrix"]["include"]
    assert {(row["os"], row["python"]) for row in environments} == {
        ("ubuntu-latest", "3.12"),
        ("ubuntu-latest", "3.13"),
        ("ubuntu-latest", "3.14"),
        ("macos-14", "3.14"),
        ("windows-latest", "3.14"),
    }
    assert len(environments) == 5
    for row in (*environments, jobs["lowest-shards"]["with"]):
        groups = json.loads(row["groups"])
        assert groups == list(range(1, row["splits"] + 1))
        assert row["workers"] == (2 if row["os"] == "macos-14" else 4)
    assert [
        (row["os"], row["python"]) for row in environments if row["coverage"]
    ] == [("ubuntu-latest", "3.14")]
    assert jobs["lowest-shards"]["with"]["lowest"] is True


def test_coverage_is_enforced_after_combining_the_shards() -> None:
    shard = _workflow("portable-tests")["jobs"]["shard"]
    assert "--cov-fail-under=0" in shard["env"]["COVERAGE_ARGS"]
    assert "--cov-branch" in shard["env"]["COVERAGE_ARGS"]
    steps = _workflow("ci")["jobs"]["coverage"]["steps"]
    commands = [step["run"] for step in steps if "run" in step]
    combined = next(
        command for command in commands if "coverage combine" in command
    )
    assert combined.splitlines() == [
        "uv run coverage combine coverage-data",
        "uv run coverage report",
        "uv run coverage xml",
    ]
    download = next(
        step
        for step in steps
        if step.get("uses", "").startswith("actions/download-artifact@")
    )
    assert download["with"]["pattern"] == "coverage-*"
    upload = next(
        step
        for step in shard["steps"]
        if step.get("name") == "Upload branch coverage"
    )
    assert upload["with"]["include-hidden-files"] is True
    assert upload["with"]["if-no-files-found"] == "error"


def test_docs_only_still_requires_lint_docs_and_stable_gates() -> None:
    jobs = _workflow("ci")["jobs"]
    final = jobs["package"]
    assert final["name"] == "Package smoke test"
    assert final["if"] == "${{ always() }}"
    command = final["steps"][-1]["run"].split()
    required = command[
        command.index("--required") + 1 : command.index("--conditional")
    ]
    assert set(required) == {
        "changes",
        "pre-commit",
        "docs",
        "test",
        "lowest-dependencies",
        "coverage",
        "container",
    }
    conditional = command[command.index("--conditional") + 1 :]
    assert set(conditional) == {
        "scientific-validation",
        "quick-benchmark-smoke",
        "notebooks",
        "package-build",
        "timings",
    }
    assert set(final["needs"]) == set(required) | set(conditional)
    assert "if" not in jobs["docs"] and "if" not in jobs["pre-commit"]
    for name in ("test", "lowest-dependencies", "coverage", "container"):
        assert jobs[name]["if"] == "${{ always() }}"
    for name in ("portable", "lowest-shards", "unit", *conditional):
        assert jobs[name]["if"] == "needs.changes.outputs.full == 'true'"


def test_shards_consume_one_snapshot_and_upload_reports_on_failure() -> None:
    steps = _workflow("portable-tests")["jobs"]["shard"]["steps"]
    assert not any(
        step.get("uses", "").startswith("actions/cache/") for step in steps
    )
    snapshot = next(
        step
        for step in steps
        if step.get("uses", "").startswith("actions/download-artifact@")
    )
    assert snapshot["with"]["name"] == "ci-duration-baseline"
    command = next(
        step["run"] for step in steps if step["name"] == "Run portable tests"
    )
    for option in (
        "--durations=50",
        "--junitxml=",
        "--clean-durations",
        "--splitting-algorithm least_duration",
        "--no-sync",
    ):
        assert option in command
    upload = next(
        step
        for step in steps
        if step["name"].startswith("Upload test results")
    )
    assert upload["if"] == "${{ !cancelled() }}"
    cache_save = next(
        step
        for step in _workflow("ci")["jobs"]["timings"]["steps"]
        if step.get("uses", "").startswith("actions/cache/save@")
    )
    assert cache_save["if"] == "github.event_name == 'push'"


@pytest.mark.parametrize("splits", (1, 2, 4))
def test_duration_shards_select_every_selected_test_once(
    tmp_path: Path, splits: int
) -> None:
    """Exercise the real plugin with markers, parameters and a doctest."""
    (tmp_path / "test_sample.py").write_text(
        '"""Example.\n\n>>> 1 + 1\n2\n"""\n'
        "import pytest\n"
        '@pytest.mark.parametrize("value", range(12))\n'
        "def test_value(value):\n    assert value >= 0\n"
        "@pytest.mark.slow\n"
        "def test_long():\n    assert False\n",
        encoding="utf-8",
    )
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\nmarkers = slow: excluded\n", encoding="utf-8"
    )
    timings = tmp_path / "durations.json"
    timings.write_text(
        json.dumps(
            {
                "test_sample.py::test_value[0]": 100,
                "test_sample.py::test_value[1]": 100,
            }
        ),
        encoding="utf-8",
    )
    base = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--collect-only",
        "--doctest-modules",
        "-m",
        "not slow",
        "--durations-path",
        str(timings),
        "--splitting-algorithm",
        "least_duration",
    ]

    def collect(arguments: list[str]) -> list[str]:
        result = subprocess.run(
            [*base, *arguments],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return [
            line
            for line in result.stdout.splitlines()
            if line.startswith("test_sample.py::")
        ]

    whole = collect([])
    shards = [
        collect(["--splits", str(splits), "--group", str(group)])
        for group in range(1, splits + 1)
    ]
    assert len(whole) == 13
    assert all(shards)
    assert Counter(test for shard in shards for test in shard) == Counter(
        whole
    )
    assert all(count == 1 for count in Counter(whole).values())
