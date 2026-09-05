"""Contracts for the terminal source-support-linkage root-cause review."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any, cast

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_PROGRAM = (
    _ROOT
    / "scripts/validation/review_phase5_source_support_linkage_terminal.py"
)
_REVIEW = (
    _ROOT / "config/contracts/phase-5-source-owned-source-support-linkage-"
    "terminal-root-cause-review.json"
)


def _review() -> dict[str, Any]:
    """Load the checked-in review object."""
    value: object = json.loads(_REVIEW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_review_binds_the_terminal_failure_without_authority() -> None:
    """The viewed result remains failed and cannot authorize a rescore."""
    review = _review()
    terminal = review["binding_context"]["terminal_decision"]

    assert review["status"] == (
        "root-cause-complete-ready-for-prospective-replication"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["no_retrospective_rescore"] is True
    assert terminal["status"] == "fail"
    assert terminal["failed_geometry_count"] == 1
    assert file_sha256(_ROOT / terminal["path"]) == terminal["sha256"]


def test_review_accounts_for_the_single_tail_and_linkage_failure() -> None:
    """All binding failures have explicit causal and exclusion evidence."""
    review = _review()
    failure = review["terminal_failure"]
    findings = review["causal_findings"]

    assert failure["binding_failures"] == [
        "integrated-flux-paired-margin",
        "split-fraction-paired-margin",
    ]
    assert failure["tail_adverse_movements"]["flux"] == pytest.approx(
        0.053766446176525706
    )
    assert failure["tail_support_gain"] == pytest.approx(0.11641221374045796)
    assert failure["paired_cell_medians"]["boundary"] == {
        "completeness": 0.0,
        "flux": pytest.approx(-0.005115927460168999),
        "mask": pytest.approx(0.013448843792993936),
        "split": 0.0,
        "support": pytest.approx(-0.051526717557251855),
    }
    assert findings["truth_linkage_boundary_graze"]["classification"] == (
        "confirmed-validation-only-fragmentation-false-positive"
    )
    assert findings["single_realization_flux_tail"]["classification"] == (
        "stochastic-boundary-tail-not-systematic-cell-regression"
    )


def test_repair_keeps_margins_and_final_comparators_strict() -> None:
    """A robust fast statistic cannot weaken Phase 5 scientific parity."""
    repair = _review()["prospective_repair"]

    assert repair["source_finding_science_changed"] is False
    assert repair["truth_linkage"] == {
        "basis": "existing-public-minimum-island-pixels",
        "minimum_truth_overlap_pixels": 7,
    }
    assert repair["unchanged_numeric_margins"] == {
        "completeness": 0.02,
        "flux": 0.05,
        "mask": 0.05,
        "split": 0.02,
        "support": 0.05,
    }
    assert (
        "geometries and trigger cohorts are never pooled"
        in repair["systematic_regression_rule"]
    )
    assert "released PyBDSF" in repair["final_gate_unchanged"]
    assert "pinned-master PyBDSF" in repair["final_gate_unchanged"]


def test_replication_is_fresh_and_precedes_long_work() -> None:
    """The next evidence is seed-disjoint and remains a fast gate."""
    review = _review()
    population = review["replication_population"]

    assert population == {
        "cell_count": 36,
        "disjoint_from_frozen_qualification": True,
        "disjoint_from_viewed_development": True,
        "first_seed": 2026952001,
        "geometry_count": 12,
        "input_count": 144,
        "last_seed": 2026952144,
        "role": "development",
        "seeds_per_cell": 4,
    }
    assert review["required_sequence"][4:7] == [
        "run-144-image-replication-lane",
        "open-cumulative-dual-pybdsf-replay-only-if-replication-passes",
        "open-fresh-held-out-qualification-only-if-cumulative-parity-passes",
    ]


def test_review_writer_is_write_once(tmp_path: Path) -> None:
    """The review writer never mutates an existing governance record."""
    program = runpy.run_path(str(_PROGRAM))
    output = tmp_path / "review.json"
    review = _review()

    program["write_review"](output, review)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    with pytest.raises(FileExistsError):
        program["write_review"](output, review)
