"""Documentation routing and required-check failures are explicit contracts."""

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def ci() -> dict[str, Any]:
    return runpy.run_path(str(ROOT / "scripts/ci.py"))


@pytest.mark.parametrize(
    "paths, expected",
    [
        (("README.md",), True),
        (("LOG.md", "docs/how-to/index.md", "plans/work.md"), True),
        (("docs/assets/example.svg",), True),
        ((), False),
        (("README.md", "src/hebog/__init__.py"), False),
        (("pyproject.toml",), False),
        (("uv.lock",), False),
        (("mkdocs.yml",), False),
        ((".github/workflows/ci.yaml",), False),
        (("Dockerfile",), False),
        (("tests/unit/test_config.py",), False),
        (("notebooks/source_finder_demo.py",), False),
        (("docs/hook.py",), False),
        (("CHANGELOG.md",), False),
        (("AGENTS.md",), False),
        (("",), False),
        (("plans/unexpected.png",), False),
    ],
)
def test_docs_only_is_a_narrow_allow_list(
    ci: dict[str, Any], paths: tuple[str, ...], expected: bool
) -> None:
    assert ci["docs_only"](paths) is expected


@pytest.mark.parametrize("full", (False, True))
@pytest.mark.parametrize(
    "state", ("failure", "cancelled", "skipped", "unknown")
)
@pytest.mark.parametrize("name", ("changes", "docs", "tests"))
def test_required_gates_fail_closed(
    ci: dict[str, Any], full: bool, state: str, name: str
) -> None:
    results: dict[str, str] = dict.fromkeys(
        ("changes", "docs", "tests"), "success"
    )
    results[name] = state
    if name == "tests" and state == "skipped" and not full:
        ci["check_results"](
            results,
            full=full,
            required=("changes", "docs"),
            conditional=("tests",),
        )
    else:
        with pytest.raises(ValueError, match=name):
            ci["check_results"](
                results,
                full=full,
                required=("changes", "docs"),
                conditional=("tests",),
            )


@pytest.mark.parametrize("full", (False, True))
def test_missing_checks_cannot_pass(ci: dict[str, Any], full: bool) -> None:
    with pytest.raises(ValueError, match="tests"):
        ci["check_results"](
            {"changes": "success"},
            full=full,
            required=("changes",),
            conditional=("tests",),
        )


@pytest.mark.parametrize("full", (False, True))
def test_success_and_intentional_docs_skip(
    ci: dict[str, Any], full: bool
) -> None:
    ci["check_results"](
        {
            "changes": "success",
            "docs": "success",
            "tests": "success" if full else "skipped",
        },
        full=full,
        required=("changes", "docs"),
        conditional=("tests",),
    )


def test_merged_timings_use_the_slowest_measurement(
    ci: dict[str, Any], tmp_path: Path
) -> None:
    linux, windows = tmp_path / "linux.json", tmp_path / "windows.json"
    linux.write_text(json.dumps({"same": 2.0, "linux": 0.0}))
    windows.write_text(json.dumps({"same": 5.0, "windows": 1.0}))
    assert ci["merge_durations"]((linux, windows)) == {
        "same": 5.0,
        "linux": 0.0,
        "windows": 1.0,
    }
    assert ci["merge_durations"]((windows, linux)) == {
        "same": 5.0,
        "linux": 0.0,
        "windows": 1.0,
    }


@pytest.mark.parametrize(
    "payload",
    (
        [],
        {},
        {"": 1},
        {"test": -1},
        {"test": True},
        {"test": None},
        {"test": "1"},
        {"test": float("inf")},
        {"test": float("nan")},
    ),
)
def test_invalid_or_empty_timings_fail(
    ci: dict[str, Any], tmp_path: Path, payload: object
) -> None:
    path = tmp_path / "durations.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        ci["merge_durations"]((path,))


def test_absent_timing_artifacts_fail(ci: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="no measured"):
        ci["merge_durations"](())


@pytest.mark.parametrize("full", ("", "unknown", "False"))
def test_gate_cli_rejects_missing_or_malformed_routing(full: str) -> None:
    environment = os.environ | {"FULL_CI": full, "NEEDS_JSON": "{}"}
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci.py"),
            "gate",
            "--required",
            "changes",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "FULL_CI must be true or false" in result.stderr


@pytest.mark.parametrize(
    "change", ("docs", "code", "delete", "rename", "empty")
)
def test_routing_uses_the_entire_git_diff(tmp_path: Path, change: str) -> None:
    """Removed code and code renamed into docs still require full CI."""

    def git(*arguments: str) -> str:
        return subprocess.check_output(
            ["git", *arguments],
            cwd=tmp_path,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()

    def commit() -> None:
        git("add", ".")
        git(
            "-c",
            "user.name=CI test",
            "-c",
            "user.email=ci@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "test",
        )

    git("init", "-q")
    (tmp_path / "README.md").write_text("Before\n", encoding="utf-8")
    (tmp_path / "source.py").write_text("pass\n", encoding="utf-8")
    commit()
    base = git("rev-parse", "HEAD")
    if change == "docs":
        (tmp_path / "README.md").write_text("After\n", encoding="utf-8")
    elif change == "code":
        (tmp_path / "source.py").write_text("x = 1\n", encoding="utf-8")
    elif change == "delete":
        (tmp_path / "source.py").unlink()
    elif change == "rename":
        (tmp_path / "docs").mkdir()
        (tmp_path / "source.py").rename(tmp_path / "docs/source.md")
    if change != "empty":
        commit()
    output = tmp_path / "routing.txt"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci.py"),
            "changes",
            "--event",
            "pull_request",
            "--base",
            base,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert output.read_text().splitlines() == [
        "full=false" if change == "docs" else "full=true"
    ]


def test_pushes_always_run_full_ci(tmp_path: Path) -> None:
    output = tmp_path / "routing.txt"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci.py"),
            "changes",
            "--event",
            "push",
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert output.read_text().splitlines() == ["full=true"]


def test_missing_pr_base_fails_instead_of_skipping_tests(
    tmp_path: Path,
) -> None:
    output = tmp_path / "routing.txt"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci.py"),
            "changes",
            "--event",
            "pull_request",
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "requires --base" in result.stderr
    assert not output.exists()


def test_timing_cli_merges_nested_artifacts(tmp_path: Path) -> None:
    for name, seconds in (("linux", 2), ("windows", 5)):
        shard = tmp_path / name
        shard.mkdir()
        (shard / "durations.json").write_text(
            json.dumps({"test": seconds}), encoding="utf-8"
        )
    output = tmp_path / "merged/result.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci.py"),
            "durations",
            "--input",
            str(tmp_path),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
    )
    assert json.loads(output.read_text()) == {"test": 5}


@pytest.mark.parametrize(
    "event, paths, expected",
    (
        ("push", b"", "full=true"),
        ("pull_request", b"README.md\0docs/new name.md\0", "full=false"),
        ("pull_request", b"source.py\0docs/renamed.md\0", "full=true"),
        ("pull_request", b"", "full=true"),
    ),
)
def test_changes_cli_writes_a_routing_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    event: str,
    paths: bytes,
    expected: str,
) -> None:
    output = tmp_path / "github-output"
    commands: list[list[str]] = []

    def changed_paths(command: list[str]) -> bytes:
        commands.append(command)
        return paths

    monkeypatch.setattr(subprocess, "check_output", changed_paths)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ci",
            "changes",
            "--event",
            event,
            "--base",
            "base-sha",
            "--output",
            str(output),
        ],
    )
    runpy.run_path(str(ROOT / "scripts/ci.py"), run_name="__main__")
    assert output.read_text().splitlines() == [expected]
    assert commands == (
        []
        if event == "push"
        else [
            [
                "git",
                "diff",
                "--name-only",
                "--no-renames",
                "-z",
                "base-sha",
                "HEAD",
            ]
        ]
    )


@pytest.mark.parametrize("full", (False, True))
@pytest.mark.parametrize(
    "state", ("success", "skipped", "cancelled", "failure")
)
def test_gate_cli_observes_the_same_results_contract(
    monkeypatch: pytest.MonkeyPatch, full: bool, state: str
) -> None:
    monkeypatch.setenv("FULL_CI", str(full).lower())
    monkeypatch.setenv(
        "NEEDS_JSON",
        json.dumps(
            {"changes": {"result": "success"}, "tests": {"result": state}}
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["ci", "gate", "--required", "changes", "--conditional", "tests"],
    )
    if state == "success" or (state == "skipped" and not full):
        runpy.run_path(str(ROOT / "scripts/ci.py"), run_name="__main__")
    else:
        with pytest.raises(ValueError, match="tests"):
            runpy.run_path(str(ROOT / "scripts/ci.py"), run_name="__main__")


def test_timing_cli_publishes_the_merged_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shard = tmp_path / "shard"
    shard.mkdir()
    (shard / "durations.json").write_text('{"test": 5}', encoding="utf-8")
    output = tmp_path / "merged/durations.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["ci", "durations", "--input", str(shard), "--output", str(output)],
    )
    runpy.run_path(str(ROOT / "scripts/ci.py"), run_name="__main__")
    assert json.loads(output.read_text()) == {"test": 5}


@pytest.mark.parametrize("command", ("changes", "gate"))
def test_cli_routing_errors_fail_closed_in_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    if command == "changes":
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "ci",
                "changes",
                "--event",
                "pull_request",
                "--output",
                str(tmp_path / "output"),
            ],
        )
        with pytest.raises(SystemExit, match="2"):
            runpy.run_path(str(ROOT / "scripts/ci.py"), run_name="__main__")
    else:
        monkeypatch.setattr(
            sys, "argv", ["ci", "gate", "--required", "changes"]
        )
        monkeypatch.setenv("FULL_CI", "unknown")
        with pytest.raises(ValueError, match="FULL_CI"):
            runpy.run_path(str(ROOT / "scripts/ci.py"), run_name="__main__")
