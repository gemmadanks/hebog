"""Contracts for the adaptive-background development pre-review."""

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
    / "scripts/validation/review_phase5_adaptive_background_development.py"
)
_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-adaptive-background-development-pre-review.json"
)


def _review() -> dict[str, Any]:
    """Load the checked-in review as one JSON object."""
    value: object = json.loads(_REVIEW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_checked_in_review_is_the_deterministic_generator_output() -> None:
    """The reviewed bytes must describe the pure prospective design."""
    program = runpy.run_path(str(_PROGRAM))

    assert program["build_review"](_ROOT) == _review()


def test_review_is_non_executable_and_does_not_open_qualification() -> None:
    """Planning cannot silently authorize science or consume held-out data."""
    review = _review()

    assert review["status"] == "awaiting-human-scientific-review"
    assert set(review["authorization"].values()) == {False}
    assert review["population"]["role"] == "development"
    assert review["qualification_boundary"]["qualification_opened"] is False
    assert review["comparators"]["pybdsf_execution_required"] is False


def test_review_freezes_the_bounded_factorial_and_execution_count() -> None:
    """The lane stays small while covering each declared risk dimension."""
    review = _review()
    population = review["population"]

    assert population["image_shape_yx"] == [512, 512]
    assert population["geometry_cell_count"] == 12
    assert population["matrix_cell_count"] == 36
    assert population["noise_realizations_per_cell"] == 4
    assert population["image_count"] == 144
    assert population["candidate_executions"] == 144
    assert population["coarse_control_executions"] == 144
    assert population["existing_dask_invariance_reexecutions"] == 12
    assert population["total_finder_executions"] == 300
    assert population["full_replay_candidate_work_fraction"] == pytest.approx(
        0.125
    )
    assert population["seed_audit"]["seed_disjoint"] is True


def test_review_keeps_hard_truth_safety_separate_from_comparison_margins() -> (
    None
):
    """A practical trade-off cannot waive catastrophic self-absorption."""
    policy = _review()["decision_policy"]
    floors = policy["hard_truth_safety_floors"]
    margins = policy["paired_adaptive_vs_coarse_margins"]

    assert floors == {
        "completeness_minimum": 1.0,
        "integrated_flux_absolute_fractional_error_median_maximum": 0.1,
        "integrated_flux_absolute_fractional_error_p95_maximum": 0.25,
        "mask_iou_cell_median_minimum": 0.75,
        "mask_iou_image_minimum": 0.6,
        "split_fraction_maximum": 0.25,
        "support_recall_cell_median_minimum": 0.9,
        "support_recall_image_minimum": 0.75,
    }
    assert margins == {
        "completeness": 0.02,
        "integrated_flux_absolute_fractional_error": 0.05,
        "mask_iou": 0.05,
        "split_fraction": 0.02,
        "support_recall": 0.05,
    }
    assert policy["trade_off_rule"]["hard_floor_waiver_allowed"] is False
    assert policy["pass_claim"] == (
        "development-risk-closed-not-qualification-or-release-readiness"
    )


def test_review_binds_the_known_coverage_gap_and_exact_candidate() -> None:
    """A different trigger or candidate requires a different review."""
    review = _review()
    gap = review["known_coverage_gap"]
    candidate = review["candidate_binding"]

    assert gap["adaptive_trigger_sigma"] == 75.0
    assert gap["brightest_component_sigma_range"] == pytest.approx(
        [22.62, 29.12]
    )
    assert gap["shell_component_sigma_range"] == pytest.approx(
        [6.1248, 10.0352]
    )
    assert gap["existing_population_crosses_trigger"] is False
    assert candidate["revision"] == (
        "937737d811dd229d71dbcfdbda6cb5829de6faca"
    )
    assert candidate["configuration_sha256"] == (
        "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
    )


def test_review_binds_its_generator_and_pure_design_module() -> None:
    """Edits to either prospective program require a new review identity."""
    bindings = _review()["evidence_bindings"]

    for binding_id in ("design_module", "review_program"):
        binding = bindings[binding_id]
        assert file_sha256(_ROOT / binding["path"]) == binding["sha256"]


def test_seed_audit_rejects_a_historical_seed() -> None:
    """A checked-in historical realization cannot become development truth."""
    program = runpy.run_path(str(_PROGRAM))

    with pytest.raises(ValueError, match="overlap historical"):
        program["_historical_seed_audit"](_ROOT, (0,))


def test_public_binding_rejects_a_different_candidate() -> None:
    """The lane cannot silently run a replacement scientific candidate."""
    program = runpy.run_path(str(_PROGRAM))
    identity = json.loads(
        (
            _ROOT
            / "config/contracts/phase-5-public-interface-identity-review.json"
        ).read_text(encoding="utf-8")
    )
    identity["algorithm_candidate"]["revision"] = "0" * 40

    with pytest.raises(ValueError, match="candidate identity changed"):
        program["_validate_public_identity"](identity)


def test_public_binding_rejects_missing_nested_evidence() -> None:
    """Malformed provenance fails clearly rather than reaching execution."""
    program = runpy.run_path(str(_PROGRAM))

    with pytest.raises(
        ValueError, match="candidate identity must be a mapping"
    ):
        program["_validate_public_identity"]({})


def test_review_writer_emits_canonical_json(tmp_path: Path) -> None:
    """A fresh path receives exactly one sorted, finite JSON document."""
    program = runpy.run_path(str(_PROGRAM))
    review = program["build_review"](_ROOT)
    output = tmp_path / "review.json"

    program["write_review"](output, review)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert output.read_text(encoding="utf-8").endswith("\n")


def test_review_writer_refuses_to_overwrite() -> None:
    """The prospective review has write-once publication semantics."""
    program = runpy.run_path(str(_PROGRAM))

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        program["write_review"](_REVIEW, program["build_review"](_ROOT))
