"""Contracts for the prospective Phase 5 source-association pre-review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "pre-review.json"
)


def _load() -> dict[str, Any]:
    """Load the non-executable scientific pre-review."""
    return json.loads(_REVIEW.read_text(encoding="utf-8"))


def test_source_association_review_is_non_executable() -> None:
    """A scientific design review grants no implementation or execution."""
    review = _load()

    assert review["schema_version"] == 1
    assert review["review_id"] == (
        "phase-5-public-finder-source-association-pre-review"
    )
    assert review["status"] == (
        "ready-for-named-source-association-implementation-review"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-pre-review-for-fixture-only-"
        "implementation"
    )


def test_source_association_review_binds_terminal_failure() -> None:
    """The proposal is inseparable from the exact failing replay evidence."""
    failure = _load()["terminal_failure"]

    assert failure["ledger"] == {
        "path": (
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-public-finder-correction.json"
        ),
        "sha256": (
            "1ac6deb24e4bfc1928318c95437d45acac6ac1f94621b53d45175e0f41bd9797"
        ),
    }
    assert failure["candidate"] == {
        "configuration_sha256": (
            "65c8876dcdb484bd5a82b3520e065ea6bf33cf24cfdd33b592c6c859231c62f0"
        ),
        "revision": "b1d59e5aaf778a5fed4ea662afeba2ee100424ff",
        "source_tree_sha256": (
            "2de6564e78f1a3664dd3fb18f696c747bfc3350fdd894164c4fafb07528d1ba9"
        ),
    }
    assert failure["compact"] == {
        "like_semantics_regression_count": 0,
        "status": "pass",
    }
    assert failure["continuum"] == {
        "failed_endpoint_count": 44,
        "like_semantics_regression_count": 37,
        "passed_endpoint_count": 89,
        "status": "fail",
        "underpowered_endpoint_count": 10,
    }
    assert failure["power_interpretation"] == (
        "underpowered-endpoints-cannot-compensate-for-absolute-failures-or-"
        "regressions"
    )


def test_source_association_review_preserves_three_semantic_layers() -> None:
    """Image-domain grouping cannot claim physical-object association."""
    semantics = _load()["catalogue_semantics"]

    assert semantics["detection_component"]["pixel_ownership"] == (
        "immutable-exact-seeded-owner-support"
    )
    assert semantics["catalogue_source"]["membership"] == (
        "one-or-more-detection-components-partitioned-exactly-once"
    )
    assert semantics["astrophysical_object"]["scope"] == (
        "out-of-scope-contextual-classification"
    )
    assert semantics["astrophysical_object"]["may_be_inferred"] is False
    assert semantics["binding_output"] == "catalogue-source-records"
    assert semantics["retained_diagnostic_output"] == (
        "detection-component-records"
    )


def test_source_association_review_freezes_conservative_graph_rule() -> None:
    """Grouping uses real signal continuity and cannot recreate dilation."""
    graph = _load()["prospective_design"]["association_graph"]

    assert graph["nodes"] == "canonical-detection-component-identities"
    assert graph["parent_support"] == (
        "eight-connected-direct-owner-plus-undilated-significant-b3-support"
    )
    assert graph["edge_requirements"] == [
        "same-undilated-parent-support",
        "valid-pixel-connecting-segment-never-below-existing-three-sigma-"
        "island-threshold",
        "centroid-separation-no-greater-than-half-the-sum-of-directional-"
        "component-fwhm",
        "both-component-shapes-available",
    ]
    assert graph["grouping"] == (
        "deterministic-complete-link-agglomeration-no-transitive-only-merge"
    )
    assert graph["forbidden_evidence"] == [
        "truth-identities",
        "reference-finder-products",
        "viewed-public-outcomes",
        "morphological-dilation",
        "distance-only-edges",
    ]
    assert graph["ambiguous_edge_policy"] == "leave-components-separate"


def test_source_association_review_preserves_measurements_and_ownership() -> (
    None
):
    """The proposal aggregates records without changing detection science."""
    design = _load()["prospective_design"]
    aggregation = design["source_record_aggregation"]

    assert design["component_ownership_invariant"] == "bitwise-identical"
    assert aggregation["integrated_flux"] == (
        "sum-existing-exclusive-component-integrated-flux"
    )
    assert aggregation["peak_flux"] == "maximum-component-peak-flux"
    assert aggregation["centroid"] == (
        "integrated-flux-weighted-local-tangent-plane-component-centroid"
    )
    assert aggregation["shape"] == (
        "moment-equivalent-shape-on-union-of-exact-component-owner-support"
    )
    assert aggregation["measurement_pixels_reassigned"] is False
    assert aggregation["photometric_calibration_changed"] is False


def test_source_association_review_requires_adversarial_fixture_matrix() -> (
    None
):
    """Both missed grouping and false grouping are first-class failures."""
    matrix = _load()["test_first_matrix"]

    assert {
        "single-compact-component",
        "split-broad-gaussian-with-continuous-b3-support",
        "two-compact-sources-with-low-saddle",
        "high-dynamic-range-neighbours",
        "three-component-transitive-bridge-chain",
        "disconnected-double-lobe-physical-object",
        "shell-and-filament-components",
        "masked-gap-and-invalid-pixel-barrier",
    } <= set(matrix["analytic"])
    assert {
        "component-label-permutation",
        "tile-shape-and-partition-origin",
        "worker-count-task-order-and-retry",
        "one-tile-versus-many-tile",
    } <= set(matrix["invariance"])
    assert matrix["forbidden_inputs"] == [
        "terminal-replay-products",
        "viewed-sdc1-products",
        "viewed-hydra-products",
        "pybdsf-or-aegean-catalogues",
    ]


def test_source_association_review_has_no_compensating_gate() -> None:
    """Every fixture, invariant, and cumulative endpoint remains binding."""
    gates = _load()["scientific_gates"]

    assert gates["fixture_rule"] == "every-case-must-pass-no-compensation"
    assert gates["component_partition"] == (
        "every-component-appears-in-exactly-one-source"
    )
    assert gates["flux_conservation"] == (
        "summed-source-flux-equals-summed-component-flux"
    )
    assert gates["false_association"] == "zero-on-analytic-negative-controls"
    assert gates["physical_association_claims"] == "zero"
    assert gates["cumulative_replay"] == (
        "separate-exact-approval-and-all-absolute-and-like-semantics-gates"
    )


def test_source_association_review_binds_clean_implementation_seams() -> None:
    """Later implementation must explicitly replace reviewed source bytes."""
    records = cast(list[dict[str, str]], _load()["implementation_seams"])

    assert {record["path"] for record in records} == {
        "src/hebog/algorithms/extended_measurement.py",
        "src/hebog/validation/post_campaign_science.py",
        "src/hebog/validation/products.py",
        "src/hebog/validation/public_finder_correction.py",
    }
    for record in records:
        assert file_sha256(_ROOT / record["path"]) == record["sha256"]


def test_source_association_review_requires_test_first_approval_boundary() -> (
    None
):
    """Approval may open fixtures only, never scientific execution."""
    review = _load()

    assert review["allowed_after_separate_approval"] == [
        "test-first-pure-source-association-records-and-graph",
        "fixture-only-component-and-source-catalogue-construction",
        "serial-and-existing-dask-invariance-validation",
        "non-executable-candidate-identity-freeze",
    ]
    assert review["required_sequence"][-2:] == [
        "freeze-exact-non-executable-candidate-and-cumulative-replay-"
        "identities",
        "obtain-separate-named-approval-before-one-complete-cumulative-replay",
    ]
