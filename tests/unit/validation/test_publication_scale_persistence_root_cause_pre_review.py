"""Contracts for the publication-persistence prospective root-cause review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-publication-scale-persistence-root-cause-"
    "pre-review.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    """Load one JSON object used by the reproducibility checks."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _sha256(path: Path) -> str:
    """Return one evidence file's SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _continuum_values(document: dict[str, Any]) -> dict[str, float]:
    """Index the terminal Continuum point estimates by endpoint."""
    return {
        endpoint["endpoint_id"]: endpoint["candidate_value"]
        for endpoint in document["prospective_continuum_analysis"]
    }


def test_review_is_non_executable() -> None:
    """A root-cause review cannot silently authorize repair or execution."""
    review = _load_json(_REVIEW)

    assert review["schema_version"] == 1
    assert review["review_id"] == (
        "phase-5-publication-scale-persistence-root-cause-pre-review"
    )
    assert review["status"] == (
        "ready-for-named-prospective-evaluation-alignment-review"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-review-for-evaluation-only-"
        "prospective-alignment-and-paired-evidence-preparation"
    )


def test_review_binds_every_governed_input_by_hash() -> None:
    """The diagnosis must remain inseparable from its exact evidence."""
    context = _load_json(_REVIEW)["binding_context"]
    bindings = (
        context["current_terminal_ledger"],
        context["closed_historical_baseline"],
        context["prospective_decision_contract"],
        context["prospective_endpoint_registry"],
        context["full_continuum_population"],
        context["prospective_smoke"],
    )
    for binding in bindings:
        assert _sha256(_ROOT / binding["path"]) == binding["sha256"]

    incumbent = context["selected_terminal_parent_incumbent"]
    assert (
        _sha256(_ROOT / incumbent["ledger_path"])
        == (incumbent["ledger_sha256"])
    )
    assert context["current_candidate"] == {
        "configuration_sha256": (
            "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
        ),
        "product_set_sha256": (
            "77a71b5fd537e30efd67a6a225c9d0b52d9bc9d56417437b10bd659539a013b1"
        ),
        "revision": "937737d811dd229d71dbcfdbda6cb5829de6faca",
        "source_tree_sha256": (
            "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
        ),
    }


def test_prospective_contract_reclassifies_numeric_targets_only() -> None:
    """Absolute objectives cannot replace parity, retention, or safety."""
    review = _load_json(_REVIEW)
    context = review["binding_context"]
    contract = _load_json(
        _ROOT / context["prospective_decision_contract"]["path"]
    )
    registry = _load_json(
        _ROOT / context["prospective_endpoint_registry"]["path"]
    )

    assert contract["absolute_policy"]["numeric_science_targets"] == (
        "report-as-longer-term-objectives"
    )
    assert all(
        endpoint["absolute_policy"] == "report-not-compatibility-blocker"
        for endpoint in registry["endpoints"]
    )
    assert review["change_control"]["historical_terminal_status_immutable"]
    assert review["prospective_contract_audit"][
        "historical_terminal_decision"
    ] == {
        "absolute_failure_count": 31,
        "historical_like_semantics_regression_count": 26,
        "status": "immutable-fail-under-original-wrapper-policy",
        "underpowered_count": 11,
    }


def test_all_stored_pybdsf_comparisons_fit_prospective_margins() -> None:
    """Reproduce the non-inferiority audit from stored analysis evidence."""
    review = _load_json(_REVIEW)
    context = review["binding_context"]
    terminal = _load_json(_ROOT / context["current_terminal_ledger"]["path"])
    registry = _load_json(
        _ROOT / context["prospective_endpoint_registry"]["path"]
    )
    endpoints = {
        value["endpoint_id"]: value for value in registry["endpoints"]
    }
    recorded = review["prospective_contract_audit"][
        "pybdsf_parity_from_stored_analysis"
    ]

    for reference_id, review_key in (
        ("released-pybdsf", "released_pybdsf"),
        ("pinned-pybdsf-master", "pinned_pybdsf_master"),
    ):
        comparisons = [
            (analysis["endpoint_id"], comparison)
            for analysis in terminal["prospective_continuum_analysis"]
            for comparison in analysis["comparisons"]
            if comparison["reference_id"] == reference_id
        ]
        within_margin = sum(
            comparison["upper_confidence_limit"]
            <= endpoints[endpoint_id]["practical_regression_margins"][
                reference_id
            ]
            for endpoint_id, comparison in comparisons
        )
        assert len(comparisons) == 113
        assert within_margin == 113
        assert recorded[review_key] == {
            "applicable_comparisons": 113,
            "observed_upper_limits_within_frozen_margin": 113,
        }


def test_legacy_absolute_failures_suppress_retained_comparisons() -> None:
    """The terminal schema exposes the exact evaluator dispatch defect."""
    review = _load_json(_REVIEW)
    context = review["binding_context"]
    terminal = _load_json(_ROOT / context["current_terminal_ledger"]["path"])
    analysis = {
        value["endpoint_id"]: value
        for value in terminal["prospective_continuum_analysis"]
    }
    suppressed = [
        value
        for value in terminal["prospective_continuum_endpoints"]
        if value["absolute_passed"] is False and not value["comparisons"]
    ]

    assert len(suppressed) == 31
    assert all(
        len(analysis[value["endpoint_id"]]["comparisons"]) == 2
        for value in suppressed
    )
    retained_underpowered = [
        comparison
        for value in terminal["prospective_continuum_endpoints"]
        for comparison in value["comparisons"]
        if comparison["status"] == "underpowered"
    ]
    assert len(retained_underpowered) == 22
    assert all(
        comparison["upper_confidence_limit"]
        <= comparison["practical_regression_margin"]
        for comparison in retained_underpowered
    )


def test_incumbent_point_audit_does_not_substitute_for_pairing() -> None:
    """Point estimates bound risk but cannot prove paired retention."""
    review = _load_json(_REVIEW)
    context = review["binding_context"]
    terminal = _load_json(_ROOT / context["current_terminal_ledger"]["path"])
    incumbent = _load_json(
        _ROOT / context["selected_terminal_parent_incumbent"]["ledger_path"]
    )
    registry = _load_json(
        _ROOT / context["prospective_endpoint_registry"]["path"]
    )
    endpoint_policy = {
        value["endpoint_id"]: value
        for value in registry["endpoints"]
        if value["lane"] == "continuum" and value["role"] == "binding"
    }
    current_values = _continuum_values(terminal)
    incumbent_values = _continuum_values(incumbent)
    worse: list[tuple[float, float]] = []
    for endpoint_id, current in current_values.items():
        prior = incumbent_values[endpoint_id]
        policy = endpoint_policy[endpoint_id]
        regression = (
            prior - current
            if policy["desirable_direction"] == "higher-is-better"
            else current - prior
        )
        if regression > 0:
            worse.append(
                (
                    regression,
                    policy["practical_regression_margins"]["incumbent-hebog"],
                )
            )

    audit = review["prospective_contract_audit"][
        "current_candidate_vs_selected_incumbent_point_estimates"
    ]
    assert len(current_values) == 143
    assert len(worse) == audit["nominally_worse"] == 32
    assert sum(regression > margin for regression, margin in worse) == 0
    assert audit["material_regressions_beyond_frozen_margin"] == 0
    assert audit["paired_confidence_status"] == (
        "unavailable-full-population-incumbent-products-not-retained"
    )


def test_failure_partition_reconciles_overlapping_truth_strata() -> None:
    """One shell cohort must not be counted as several causal cohorts."""
    review = _load_json(_REVIEW)
    context = review["binding_context"]
    terminal = _load_json(_ROOT / context["current_terminal_ledger"]["path"])
    incumbent = _load_json(
        _ROOT / context["selected_terminal_parent_incumbent"]["ledger_path"]
    )
    manifest = _load_json(_ROOT / context["full_continuum_population"]["path"])
    current = _continuum_values(terminal)
    prior = _continuum_values(incumbent)
    partition = review["failure_partition"]

    assert len(manifest["datasets"]) == 4
    for dataset in manifest["datasets"]:
        truth_groups = dataset["multiscale_truth_groups"]
        strata = {
            value["identifier"]: value["group_identifiers"]
            for value in dataset["multiscale_group_strata"]
        }
        assert len(truth_groups) == 7
        assert (
            strata["above-compact-deblend-limit"]
            == strata["morphology-shell"]
            == strata["tile-corner"]
            == ["extended-shell-0001"]
        )
        assert len(strata["tile-boundary"]) == 2
        assert len(strata["scale-1-beam"]) == 2
        assert len(strata["scale-4-beam"]) == 5
        assert len(strata["varying-noise"]) == 6

    denominators = partition["denominators"]
    assert (
        round(current["continuum--duplicate-fraction--overall"] * 11200) == 676
    )
    assert (
        round(
            current["continuum--duplicate-fraction--morphology-shell"] * 1600
        )
        == 553
    )
    assert (
        round(
            current["continuum--duplicate-fraction--morphology-artifact"]
            * 1600
        )
        == 118
    )
    assert (
        round(
            current["continuum--duplicate-fraction--morphology-diffuse"] * 3200
        )
        == 3
    )
    assert (
        round(
            current[
                "continuum--duplicate-fraction--morphology-mixed-compact-extended"
            ]
            * 1600
        )
        == 2
    )
    assert denominators["overall_truth_groups"] == 11200
    assert partition["current_duplicate_and_split_truth_groups"] == {
        "artifact": 118,
        "diffuse": 3,
        "mixed_compact_extended": 2,
        "shell": 553,
        "total": 676,
    }
    assert (
        round(prior["continuum--duplicate-fraction--overall"] * 11200) == 1437
    )
    assert partition["selected_incumbent_comparison"][
        "total_groups_improved"
    ] == (1437 - 676)


def test_review_records_material_gains_and_bounded_movements() -> None:
    """The review must not hide improvement behind the legacy fail label."""
    review = _load_json(_REVIEW)
    context = review["binding_context"]
    terminal = _load_json(_ROOT / context["current_terminal_ledger"]["path"])
    incumbent = _load_json(
        _ROOT / context["selected_terminal_parent_incumbent"]["ledger_path"]
    )
    current = _continuum_values(terminal)
    prior = _continuum_values(incumbent)
    expected = review["prospective_contract_audit"][
        "current_candidate_vs_selected_incumbent_point_estimates"
    ]

    for endpoint_id, name in (
        ("continuum--reliability--overall", "reliability"),
        ("continuum--mask-precision--overall", "mask_precision"),
        ("continuum--mask-iou--overall", "mask_iou"),
    ):
        assert current[endpoint_id] - prior[endpoint_id] == pytest.approx(
            expected["selected_material_improvements"][name]
        )
    assert current["continuum--mask-recall--overall"] - prior[
        "continuum--mask-recall--overall"
    ] == pytest.approx(
        expected["selected_nominal_worsenings_within_margin"]["mask_recall"]
    )


def test_terminal_diagnostics_exclude_late_persistence_as_dominant_cause() -> (
    None
):
    """Four late rejections cannot account for the 553 shell splits."""
    review = _load_json(_REVIEW)
    context = review["binding_context"]
    terminal = _load_json(_ROOT / context["current_terminal_ledger"]["path"])
    smoke = _load_json(_ROOT / context["prospective_smoke"]["path"])
    diagnostics = terminal["terminal_feature_persistence_diagnostics"]

    assert diagnostics["terminal_cycle_candidate_count"] == 1821
    assert diagnostics["terminal_cycle_parent_count"] == 1817
    assert diagnostics["rejected_terminal_cycle_count"] == 4
    assert diagnostics["displaced_candidate_count"] == 0
    assert diagnostics["displaced_accepted_count"] == 0
    assert smoke["continuum_status_counts"] == {
        "pass": 334,
        "underpowered": 35,
    }
    assert smoke["promotion_evidence"] is False


def test_next_step_repairs_evaluation_before_science() -> None:
    """Unresolved pairing must block both a pass and a science correction."""
    review = _load_json(_REVIEW)

    assert review["prospective_contract_audit"][
        "prospective_global_status"
    ] == ("incomplete-not-pass-and-not-demonstrated-scientific-fail")
    assert review["change_control"][
        "no_scientific_change_before_paired_attribution"
    ]
    assert review["recommended_next_correction"][
        "science_decision"
    ].startswith("Do not change source-finding science yet.")
    assert review["required_sequence"][-2:] == [
        "freeze-exact-non-executable-paired-replay-identities",
        "obtain-separate-exact-approval-before-any-execution",
    ]
