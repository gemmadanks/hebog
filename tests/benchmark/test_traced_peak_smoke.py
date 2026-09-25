"""Smoke run of the traced-peak measurement's complete path."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hebog.validation.evidence import (
    TRACED_PEAK_TOLERANCE_BYTES,
    TracedAllocationEvidence,
    load_evidence,
)

_ROOT = Path(__file__).parents[2]


@pytest.mark.benchmark
@pytest.mark.skipif(
    not hasattr(os, "wait4"), reason="process measurement needs os.wait4"
)
def test_smoke_tier_traces_repeated_runs_of_the_public_finder(
    tmp_path: Path,
) -> None:
    """Given the smoke case, two traced repetitions reproduce one peak.

    The peak is deterministic by construction, so two repetitions on the
    smallest case check both the measurement path and the property the
    envelope gate rests on.
    """
    completed = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "scripts/benchmark/measure_traced_peak.py"),
            "--tier",
            "smoke",
            "--repetitions",
            "2",
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
    assert case["admitted"] is True
    assert case["peak"]["repetitions"] == 2
    assert case["peak"]["reproduced"] is True
    evidence = load_evidence(Path(case["evidence"]))
    assert isinstance(evidence, TracedAllocationEvidence)
    peaks = [
        measurement.peak_traced_bytes for measurement in evidence.measurements
    ]
    assert max(peaks) - min(peaks) <= TRACED_PEAK_TOLERANCE_BYTES
    for measurement in evidence.measurements:
        assert (
            measurement.import_traced_bytes
            < measurement.finder_peak_traced_bytes
            <= measurement.peak_traced_bytes
        )
        assert measurement.peak_rss_bytes > 0
        assert measurement.traced_wall_seconds > 0
