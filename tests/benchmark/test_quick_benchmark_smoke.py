"""Smoke run of the quick benchmark's complete measurement path."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hebog.validation.evidence import BenchmarkEvidence, load_evidence

_ROOT = Path(__file__).parents[2]


@pytest.mark.benchmark
@pytest.mark.skipif(
    not hasattr(os, "wait4"), reason="process measurement needs os.wait4"
)
def test_smoke_tier_times_the_public_finder_in_fresh_processes(
    tmp_path: Path,
) -> None:
    """Given the smoke case, the runner writes a warm-up and five timings."""
    completed = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "scripts/benchmark/quick_benchmark.py"),
            "--tier",
            "smoke",
            "--no-previous-release",
            "--no-reference",
            "--output-root",
            str(tmp_path),
            "--label",
            "smoke",
        ],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads((tmp_path / "runs/smoke/report.json").read_text())
    (case,) = report["cases"]
    assert case["status"] == "success"
    assert case["hebog"]["repetitions"] == 5
    assert case["previous_release"] is None
    assert case["pybdsf_master"] is None
    evidence = load_evidence(Path(case["hebog"]["evidence"]))
    assert isinstance(evidence, BenchmarkEvidence)
    assert [item.warmup for item in evidence.measurements] == [True] + [
        False
    ] * 5
    for measurement in evidence.measurements:
        finder = measurement.stages[0].metrics
        assert 0 < finder.wall_seconds < measurement.complete.wall_seconds
        assert measurement.complete.peak_rss_bytes > 0
