"""Every benchmark runner identifies the source its run started from.

A run can outlast the change it measures. The traced-peak run
``m2-tier-15402`` started on a dirty tree, the change was committed while it
ran, and its report paired the commit read at the start with the clean tree
read at the end: a source that was never measured.
"""

from __future__ import annotations

import json
import runpy
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).parents[3]


@dataclass(frozen=True, slots=True)
class _Identity:
    commit_sha: str
    worktree_dirty: bool
    source_tree_sha256: str


_STARTED = _Identity(
    "a" * 40, worktree_dirty=True, source_tree_sha256="1" * 64
)
_MOVED_ON = _Identity(
    "b" * 40, worktree_dirty=False, source_tree_sha256="2" * 64
)


class _Checkout:
    """A checkout whose whole identity changes while a run measures it.

    Every value differs after the move, so a report that reads any of them
    after the run has started is recognisably late.
    """

    def __init__(self) -> None:
        self.identity = _STARTED

    def move_on(self) -> None:
        self.identity = _MOVED_ON

    def git(self, *arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return self.identity.commit_sha
        if arguments == ("status", "--porcelain"):
            return (
                " M src/hebog/pipeline.py"
                if self.identity.worktree_dirty
                else ""
            )
        raise AssertionError(f"unexpected git call: {arguments}")

    def source_tree_sha256(self, _package_root: Path) -> str:
        return self.identity.source_tree_sha256


@dataclass(frozen=True, slots=True)
class _Runner:
    script: str
    arguments: tuple[str, ...]
    case_function: str
    case_record: dict[str, Any]
    report: str


_FAILED_CASE: dict[str, Any] = {
    "case_id": "moved-on",
    "status": "failure",
    "error": "not run by this test",
}
_PROFILED_CASE: dict[str, Any] = {
    "case_id": "moved-on",
    "group": "real",
    "shape_yx": [512, 512],
    "megapixels": 0.262144,
    "profile": {
        "gaussian_component_count": 0,
        "source_count": 0,
        "process": {"peak_rss_bytes": 0},
    },
    "top_level_wall_seconds": {"find-sources": 1.0},
}
_RUNNERS = (
    pytest.param(
        _Runner(
            "measure_traced_peak.py",
            ("--tier", "smoke"),
            "_case_record",
            _FAILED_CASE,
            "report.json",
        ),
        id="traced-peak",
    ),
    pytest.param(
        _Runner(
            "quick_benchmark.py",
            ("--tier", "smoke", "--no-previous-release", "--no-reference"),
            "_run_case",
            _FAILED_CASE,
            "report.json",
        ),
        id="quick-benchmark",
    ),
    pytest.param(
        _Runner(
            "profile_complete_execution.py",
            (),
            "_run_case",
            _PROFILED_CASE,
            "summary.json",
        ),
        id="complete-execution-profile",
    ),
)


@pytest.mark.parametrize("runner", _RUNNERS)
def test_report_identifies_the_checkout_the_run_started_from(
    runner: _Runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a checkout that moves on mid-run, the report names its start.

    The commit, the dirty state and the source hash are one identity, so all
    three come from the same moment, before the first case runs.
    """
    checkout = _Checkout()
    script = _ROOT / "scripts/benchmark" / runner.script
    namespace: dict[str, Any] = runpy.run_path(str(script))["main"].__globals__

    def run_case(*_: object, **__: object) -> dict[str, Any]:
        checkout.move_on()
        return runner.case_record

    def prepare_case(*_: object, **__: object) -> object:
        return object()

    def machine_identity() -> dict[str, object]:
        # Physical memory needs POSIX os.sysconf; the identity is portable.
        return {}

    replacements: dict[str, Callable[..., object]] = {
        "_git": checkout.git,
        "source_tree_sha256": checkout.source_tree_sha256,
        "prepare_case": prepare_case,
        "machine_identity": machine_identity,
        runner.case_function: run_case,
    }
    for name, replacement in replacements.items():
        assert name in namespace, f"{runner.script} no longer defines {name}"
        monkeypatch.setitem(namespace, name, replacement)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "--output-root",
            str(tmp_path),
            "--label",
            "moved-on",
            *runner.arguments,
        ],
    )

    namespace["main"]()

    report = json.loads(
        (tmp_path / "runs" / "moved-on" / runner.report).read_text("utf-8")
    )
    assert checkout.identity == _MOVED_ON
    assert {field: report.get(field) for field in asdict(_STARTED)} == asdict(
        _STARTED
    )
