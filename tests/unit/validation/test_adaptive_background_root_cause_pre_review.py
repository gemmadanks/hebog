"""Contracts for the adaptive-background scientific root-cause review."""

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
    / "scripts/validation/review_phase5_adaptive_background_root_cause.py"
)
_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-adaptive-background-root-cause-pre-review.json"
)


def _review() -> dict[str, Any]:
    """Load the checked-in non-executable review."""
    value: object = json.loads(_REVIEW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_review_is_non_executable_and_requires_named_scientific_review() -> (
    None
):
    """Diagnosis cannot authorize a scientific change or another run."""
    review = _review()

    assert review["schema_version"] == 1
    assert review["review_id"] == (
        "phase-5-adaptive-background-root-cause-pre-review"
    )
    assert review["status"] == (
        "ready-for-named-adaptive-background-correction-review"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-review-for-test-first-fixture-only-"
        "scientific-correction"
    )


def test_review_binds_terminal_result_and_frozen_candidate() -> None:
    """The causal claims stay attached to their exact failed experiment."""
    review = _review()
    context = review["binding_context"]
    terminal = context["terminal_decision"]

    assert file_sha256(_ROOT / terminal["path"]) == terminal["sha256"]
    assert terminal["sha256"] == (
        "ff415f064f4ea7daa9254338041e52ad15d41b84edf692602092134850218026"
    )
    assert terminal["canonical_sha256"] == (
        "4f6e37241ee58420c30f8416c784e6c57efbd6e55eae32c1e878757116d865ab"
    )
    assert context["candidate"] == {
        "configuration_sha256": (
            "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
        ),
        "revision": "937737d811dd229d71dbcfdbda6cb5829de6faca",
        "source_tree_sha256": (
            "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
        ),
    }


def test_trigger_contrast_localizes_the_adaptive_regression() -> None:
    """Inactive controls are exact while every active result changes."""
    evidence = _review()["paired_evidence"]

    assert evidence["input_count"] == 144
    assert evidence["active_input_count"] == 90
    assert evidence["inactive_input_count"] == 54
    assert evidence["inactive_exact_candidate_control_matches"] == 54
    assert evidence["active_exact_candidate_control_matches"] == 0
    assert evidence["trigger_counts"] == {
        "above": {"active": 48, "images": 48},
        "below": {"active": 0, "images": 48},
        "boundary": {"active": 42, "images": 48},
    }


def test_source_contamination_signature_is_morphology_dependent() -> None:
    """The retained sentinels show the predicted bright-source absorption."""
    signature = _review()["paired_evidence"]["active_signature"]

    assert signature["background_error_increase_median_rms"] == pytest.approx(
        0.333530
    )
    assert signature["background_error_vs_support_loss_correlation"] == (
        pytest.approx(0.874107)
    )
    assert signature["background_error_vs_flux_error_correlation"] == (
        pytest.approx(0.957040)
    )
    assert signature["rms_error_vs_support_loss_correlation"] == (
        pytest.approx(0.752698)
    )
    by_morphology = signature["outside_paired_margin_by_morphology"]
    assert by_morphology["shell"] == {
        "active_images": 32,
        "flux": 0,
        "mask_iou": 26,
        "support_recall": 29,
    }
    assert by_morphology["curved_filament"] == {
        "active_images": 32,
        "flux": 0,
        "mask_iou": 0,
        "support_recall": 0,
    }
    assert by_morphology["mixed_compact_extended"] == {
        "active_images": 26,
        "flux": 25,
        "mask_iou": 20,
        "support_recall": 26,
    }


def test_review_separates_background_from_other_scientific_failures() -> None:
    """A background-only correction must not claim every floor failure."""
    findings = _review()["causal_findings"]

    assert (
        findings["adaptive_background_self_contamination"]["classification"]
        == "confirmed-primary-paired-regression-cause"
    )
    assert findings["support_loss"]["classification"] == (
        "confirmed-downstream-effect-not-independent-root-cause"
    )
    assert findings["integrated_flux_loss"]["classification"] == (
        "confirmed-direct-and-support-mediated-effect-with-independent-"
        "coarse-arm-gap"
    )
    assert findings["split_fraction"]["classification"] == (
        "independent-pre-existing-topology-gap"
    )
    assert findings["publication_specific_effect"]["classification"] == (
        "unresolved-observability-gap-not-demonstrated-primary-cause"
    )

    coarse = _review()["coarse_control_absolute_failures"]
    assert coarse["failing_geometry_count"] == 6
    assert coarse["implication"] == (
        "restoring coarse-only behaviour cannot pass the frozen lane"
    )
    assert coarse["active_split_transitions"] == {
        "coarse_false_adaptive_false": 57,
        "coarse_true_adaptive_false": 3,
        "coarse_true_adaptive_true": 30,
        "coarse_false_adaptive_true": 0,
    }


def test_recommended_correction_is_source_blind_and_bounded() -> None:
    """The proposal protects source support without using truth or tuning."""
    correction = _review()["recommended_correction"]

    assert correction["primary_scope"] == (
        "source-protected-adaptive-background-and-rms-estimation"
    )
    assert correction["source_protection"]["seed"] == (
        "coarse-normalized pixels above the existing 75-sigma adaptive "
        "candidate threshold"
    )
    assert correction["source_protection"]["support"] == (
        "the connected coarse-normalized island at the existing public "
        "island threshold containing each adaptive seed"
    )
    assert correction["fine_grid_policy"] == (
        "estimate only windows disjoint from protected support; mark "
        "intersecting windows unavailable and fill them only through the "
        "existing deterministic bounded interpolation fallback"
    )
    assert correction["new_numeric_science_thresholds"] is False
    assert correction["truth_or_reference_finder_inputs"] is False


def test_review_requires_attributable_fixture_gates_before_any_lane() -> None:
    """Distinct coarse and adaptive failures need distinct red fixtures."""
    review = _review()
    fixtures = set(review["test_first_matrix"])

    assert {
        "source-protected-background-shell",
        "source-protected-background-mixed-core-halo",
        "local-noise-patch-remains-adaptive",
        "below-trigger-bitwise-inert",
        "mixed-halo-measurement-aperture",
        "shell-and-filament-source-association",
        "pre-publication-versus-publication-support-attribution",
        "serial-existing-dask-tile-order-and-retry-invariance",
    } <= fixtures
    assert review["required_sequence"][-3:] == [
        "freeze-exact-non-executable-replacement-candidate-and-lane-identities",
        "obtain-separate-exact-approval-before-any-development-lane-execution",
        "open-held-out-qualification-only-after-the-replacement-lane-passes",
    ]


def test_review_writer_is_write_once(tmp_path: Path) -> None:
    """The root-cause record uses finite sorted JSON and never overwrites."""
    program = runpy.run_path(str(_PROGRAM))
    output = tmp_path / "review.json"
    review = _review()

    program["write_review"](output, review)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert output.read_text(encoding="utf-8").endswith("\n")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        program["write_review"](output, review)
