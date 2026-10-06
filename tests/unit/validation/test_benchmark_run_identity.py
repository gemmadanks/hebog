"""Every benchmark runner identifies the source its run started from.

A run can outlast the change it measures. The traced-peak run
``m2-tier-15402`` started on a dirty tree, the change was committed while it
ran, and its report paired the commit read at the start with the clean tree
read at the end: a source that was never measured. A commit between the reads
that identify the checkout as the run starts pairs them the same way.
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

from hebog.validation import quick_benchmark
from hebog.validation.quick_benchmark import CheckoutIdentity

_ROOT = Path(__file__).parents[3]

_COMMITTING = CheckoutIdentity(
    "a" * 40, worktree_dirty=True, source_tree_sha256="1" * 64
)
_STARTED = CheckoutIdentity(
    "b" * 40, worktree_dirty=False, source_tree_sha256="2" * 64
)
_MOVED_ON = CheckoutIdentity(
    "c" * 40, worktree_dirty=True, source_tree_sha256="3" * 64
)


class _Checkout:
    """A checkout that changes as a run identifies it, and again mid-run.

    A commit lands just after HEAD is first read, so the reads that identify
    the checkout straddle it. Every value differs after each change, so a
    report that mixes reads from either side of one is recognisable.
    """

    def __init__(self) -> None:
        self.identity = _COMMITTING

    def move_on(self) -> None:
        self.identity = _MOVED_ON

    def git(self, _repository_root: Path, *arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            commit_sha = self.identity.commit_sha
            if self.identity == _COMMITTING:
                self.identity = _STARTED
            return commit_sha
        if arguments == ("status", "--porcelain"):
            return (
                " M src/hebog/pipeline.py"
                if self.identity.worktree_dirty
                else ""
            )
        raise AssertionError(f"unexpected git call: {arguments}")

    def source_tree_sha256(self, _repository_root: Path) -> str:
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
    """Given a checkout that keeps changing, the report names its start.

    A commit lands between the reads that identify the checkout, and the
    checkout moves on again during the first case. The commit, the dirty
    state and the source hash are one identity, so all three come from the
    same state, before the first case runs.
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

    monkeypatch.setattr(quick_benchmark, "_git_output", checkout.git)
    monkeypatch.setattr(
        quick_benchmark, "source_tree_sha256", checkout.source_tree_sha256
    )
    replacements: dict[str, Callable[..., object]] = {
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
