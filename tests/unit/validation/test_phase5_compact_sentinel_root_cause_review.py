"""Contracts for the compact held-out sentinel root-cause review."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any, cast

import pytest

_ROOT = Path(__file__).parents[3]
_PROGRAM = (
    _ROOT / "scripts/validation/review_phase5_compact_sentinel_root_cause.py"
)
_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-compact-held-out-sentinel-root-cause-pre-review.json"
)


def _review() -> dict[str, Any]:
    """Load the checked-in non-executable root-cause review."""
    value: object = json.loads(_REVIEW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_review_is_non_executable_and_requires_named_approval() -> None:
    """Diagnosis alone cannot authorize a new evaluator or execution."""
    review = _review()

    assert review["schema_version"] == 1
    assert review["review_id"] == (
        "phase-5-compact-held-out-sentinel-root-cause-pre-review"
    )
    assert review["status"] == (
        "ready-for-named-sentinel-evaluator-alignment-review"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-review-for-test-first-fixture-only-"
        "sentinel-evaluator-alignment"
    )


def test_review_binds_the_exact_failed_terminal_and_array_free_summaries() -> (
    None
):
    """Causal claims cannot drift away from the viewed failed evidence."""
    context = _review()["binding_context"]
    terminal = context["terminal_decision"]

    assert terminal["path"] == (
        "benchmark-results/phase-5/"
        "compact-held-out-sentinel-pybdsf-empty-repair.json"
    )
    assert terminal["file_sha256"] == (
        "f542c7dbdc98bb3023efda4604d453b654c6da7bf61e5892fe528c5e601820aa"
    )
    assert terminal["canonical_sha256"] == (
        "00e292ef79504d54e63c464e9a7591902e113aad4aeb102c19fba3b374726602"
    )
    summaries = context["array_free_pair_summaries"]
    assert summaries["input_count"] == 168
    assert summaries["file_count"] == 168
    assert summaries["file_set_canonical_sha256"] == (
        "4965e408701b15badf3025614b8f071f124947ff5146533e201b63834ae1db1f"
    )


def test_review_accounts_for_interpretability_without_rescoring() -> None:
    """Unlike semantics and valid mask evidence remain visibly separate."""
    accounting = _review()["failure_accounting"]

    assert accounting["failed_cell_count"] == 35
    assert accounting["failed_endpoint_count"] == 186
    assert (
        accounting["source_representation_sensitive_endpoint_failures"] == 180
    )
    assert accounting["label_invariant_mask_endpoint_failures"] == 6
    assert accounting["terminal_result_remains_fail"] is True
    assert accounting["retrospective_rescore_permitted"] is False


def test_review_confirms_the_catalogue_topology_domain_mismatch() -> None:
    """Gaussian/component rows were not compared on like support domains."""
    evidence = _review()["paired_evidence"]["representation_counts"]

    assert evidence["current_hebog"] == {
        "catalogue_equals_native_support_images": 168,
        "catalogue_exceeds_native_support_images": 0,
        "maximum_catalogue_rows_per_native_support_excess": 0,
    }
    assert evidence["released_pybdsf"] == {
        "catalogue_equals_native_support_images": 18,
        "catalogue_exceeds_native_support_images": 150,
        "maximum_catalogue_rows_per_native_support_excess": 9,
    }
    split = _review()["paired_evidence"]["image_level_adverse_movements"][
        "split-fraction"
    ]
    assert split == {
        "adverse_images": 110,
        "current_hebog_has_more_native_supports": 109,
        "pybdsf_gaussian_rows_share_native_support": 110,
    }


def test_review_classifies_evaluator_defects_and_residual_science_risks() -> (
    None
):
    """The review fixes invalid comparisons without dismissing real gaps."""
    findings = _review()["causal_findings"]

    assert findings["catalogue_and_topology_level"]["classification"] == (
        "confirmed-like-semantics-evaluator-defect"
    )
    assert findings["integrated_flux"]["classification"] == (
        "confirmed-source-versus-component-flux-aggregation-defect-with-"
        "residual-science-risk"
    )
    assert findings["position_and_reliability"]["classification"] == (
        "confirmed-source-versus-component-observable-defect-with-residual-"
        "science-risk"
    )
    assert findings["adaptive_background_trigger"]["classification"] == (
        "excluded-as-primary-cause"
    )
    assert findings["binary_support"]["classification"] == (
        "independent-like-semantics-candidate-risk"
    )
    assert (
        findings["integrated_flux"]["evidence"][
            "adverse_images_without_hebog_component_excess"
        ]
        == 14
    )
    assert (
        findings["position_and_reliability"]["evidence"][
            "position_adverse_images_without_hebog_component_excess"
        ]
        == 10
    )


def test_review_requires_separate_source_and_component_evidence() -> None:
    """Successor metrics must bind each observable to one semantic level."""
    correction = _review()["recommended_correction"]

    assert correction["binding_source_lane"]["hebog_catalogue"] == (
        "terminal associated-source catalogue"
    )
    assert correction["binding_source_lane"]["pybdsf_catalogue"] == (
        "rows grouped by native PyBDSF source identity"
    )
    assert correction["binding_source_lane"]["topology"] == (
        "source-union ownership for both finders"
    )
    assert correction["component_diagnostic_lane"]["binding"] is False
    assert correction["binary_support_lane"] == (
        "retain direct truth-versus-positive-support mask metrics as binding"
    )


def test_review_requires_edge_fixtures_before_any_new_run() -> None:
    """The exact failure modes receive red fixtures before a successor lane."""
    review = _review()
    fixtures = set(review["test_first_matrix"])

    assert {
        "one-extended-truth-multiple-components",
        "pybdsf-multiple-gaussians-one-source",
        "hebog-multi-component-source-union",
        "three-peak-connected-compact-source",
        "grouped-source-versus-individual-component-flux",
        "source-centroid-versus-component-centroid",
        "source-reliability-with-legitimate-component-multiplicity",
        "like-domain-topology-labels",
        "mask-metrics-invariant-to-positive-relabeling",
        "single-component-flux-and-position-residual",
        "below-trigger-extended-control",
        "serial-existing-dask-invariance",
    } <= fixtures
    assert review["required_sequence"][-3:] == [
        "freeze-new-seed-disjoint-sentinel-identities-only-after-all-fixtures-pass",
        "obtain-separate-exact-approval-before-any-new-execution",
        "keep-phase-5-open-until-a-new-like-semantics-sentinel-passes",
    ]


def test_review_writer_is_write_once(tmp_path: Path) -> None:
    """The review is finite, sorted, reproducible, and never overwritten."""
    program = runpy.run_path(str(_PROGRAM))
    output = tmp_path / "review.json"
    review = _review()

    program["write_review"](output, review)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert output.read_text(encoding="utf-8").endswith("\n")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        program["write_review"](output, review)
