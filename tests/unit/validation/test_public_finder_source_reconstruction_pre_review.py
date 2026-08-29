"""Contracts for the terminal Phase 5 source-reconstruction pre-review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "pre-review.json"
)


def _load() -> dict[str, Any]:
    """Load the non-executable source-reconstruction pre-review."""
    return json.loads(_REVIEW.read_text(encoding="utf-8"))


def test_source_reconstruction_review_is_non_executable() -> None:
    """A failure diagnosis cannot grant implementation or execution."""
    review = _load()

    assert review["schema_version"] == 1
    assert review["review_id"] == (
        "phase-5-public-finder-source-reconstruction-pre-review"
    )
    assert review["status"] == (
        "ready-for-named-source-reconstruction-implementation-review"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-pre-review-for-fixture-only-"
        "implementation"
    )


def test_source_reconstruction_review_binds_terminal_evidence() -> None:
    """The prospective repair is inseparable from the exact failed ledger."""
    evidence = _load()["terminal_evidence"]

    assert evidence["ledger"] == {
        "path": (
            "benchmark-results/phase-5/cumulative-regression-ledger-public-"
            "finder-source-association-measurement-repair.json"
        ),
        "sha256": (
            "6b2aa4deb306e0d7ba8285aae1e18bfb4f4e838b57aecd0497bec990e8a8c842"
        ),
    }
    assert evidence["candidate_revision"] == (
        "6184a32648eee637f0aca03ab2ec0249bd0510f0"
    )
    assert evidence["candidate_product_set_sha256"] == (
        "dbc317fa98638d96ebecac26d98014a953defc96ed48a741f42f48954daa48ab"
    )
    assert evidence["compact"] == {
        "like_semantics_regression_count": 0,
        "status": "pass",
    }
    assert evidence["continuum"]["status_counts"] == {
        "fail": 44,
        "indeterminate": 0,
        "pass": 89,
        "underpowered": 10,
    }
    assert evidence["continuum"]["like_semantics_regression_count"] == 37


def test_source_reconstruction_review_accounts_for_every_failure() -> None:
    """Every failed endpoint belongs to one explicit causal workstream."""
    census = _load()["failure_census"]
    groups = census["groups"]

    assert census["failed_endpoint_count"] == 44
    assert {name: group["count"] for name, group in groups.items()} == {
        "astrometry": 13,
        "flux": 11,
        "mask": 1,
        "reliability": 1,
        "topology": 18,
    }
    endpoints = [
        endpoint
        for group in groups.values()
        for endpoint in group["endpoints"]
    ]
    assert len(endpoints) == len(set(endpoints)) == 44
    assert all(endpoint.startswith("continuum--") for endpoint in endpoints)
    assert census["unaccounted_failed_endpoints"] == []


def test_source_reconstruction_review_distinguishes_causal_confidence() -> (
    None
):
    """Direct code facts and hypotheses must not be presented as equivalent."""
    causes = _load()["root_cause_model"]

    assert causes["under_association"]["confidence"] == "high"
    assert causes["topology_semantics_mismatch"]["confidence"] == "certain"
    assert causes["component_level_measurement_composition"]["confidence"] == (
        "high"
    )
    assert causes["disconnected_support_admission"]["confidence"] == (
        "moderate"
    )
    assert causes["excluded_primary_causes"] == [
        "gross-detection-sensitivity-loss",
        "candidate-overmerge",
        "global-astrometric-bias",
        "insufficient-statistical-power-as-an-explanation-for-absolute-failures",
    ]


def test_source_reconstruction_review_replaces_pairwise_grouping() -> None:
    """A source hierarchy must represent curved and multiply peaked support."""
    hierarchy = _load()["prospective_design"]["source_hierarchy"]

    assert hierarchy["component_ownership"] == "bitwise-unchanged"
    assert hierarchy["parent_evidence"] == (
        "undilated-connected-multiscale-reconstruction-features"
    )
    assert hierarchy["grouping"] == (
        "deterministic-common-parent-membership-not-pairwise-complete-link"
    )
    assert hierarchy["path_geometry"] == (
        "geodesic-within-significant-support-not-straight-centroid-segment"
    )
    assert hierarchy["new_numeric_thresholds"] == "none"
    assert hierarchy["reuse_boundary"] == (
        "adapt the already tested bounded cross-scale association records and "
        "overlap reduction; do not add a second graph framework or reuse its "
        "half-beam compact-context dilation"
    )
    assert hierarchy["proposed_mechanism"][0] == (
        "reuse ScaleDetectionPlane and associate_adjacent_scale_detections "
        "from the existing multiscale association seam"
    )
    assert {
        "truth-identities",
        "reference-finder-products",
        "terminal-candidate-products",
        "morphological-dilation",
    } <= set(hierarchy["forbidden_evidence"])


def test_source_reconstruction_review_reuses_existing_multiscale_seam() -> (
    None
):
    """The proposal cannot add a competing association framework."""
    seams = {item["path"]: item for item in _load()["implementation_seams"]}

    association = seams["src/hebog/algorithms/multiscale_association.py"]
    assert association["sha256"] == (
        "84a66a9ce6500a44c37c241e25606720755c8501e29dfb9249c52325775daad9"
    )
    assert association["role"] == (
        "reuse the existing bounded adjacent-scale exact-overlap association "
        "kernel rather than create a parallel hierarchy implementation"
    )


def test_source_reconstruction_review_measures_each_source_once() -> None:
    """Source measurements cannot sum overlapping component views."""
    measurement = _load()["prospective_design"]["source_measurement"]

    assert measurement["support"] == (
        "exact-union-of-member-owner-support-plus-one-uniquely-owned-source-"
        "aperture"
    )
    assert measurement["integrated_flux"] == (
        "sum-background-subtracted-residual-once-per-source-owned-pixel"
    )
    assert measurement["centroid"] == (
        "single-source-level-positive-denoised-first-moment"
    )
    assert measurement["component_aperture_sums_are_binding"] is False
    assert measurement["component_centroid_averages_are_binding"] is False
    assert measurement["thresholds_changed"] is False


def test_source_reconstruction_review_separates_binding_source_topology() -> (
    None
):
    """Catalogue-source and native-component topology remain explicit."""
    topology = _load()["prospective_design"]["evaluation_semantics"]

    assert topology["binding_split_and_merge"] == (
        "catalogue-source-union-topology"
    )
    assert topology["diagnostic_split_and_merge"] == (
        "native-detection-component-topology"
    )
    assert topology["duplicate_fraction"] == "catalogue-source-topology"
    assert topology["retrospective_rescore_authorized"] is False


def test_source_reconstruction_review_requires_adversarial_fixture_gates() -> (
    None
):
    """The proposal must prove recovery and false-association safety."""
    matrix = _load()["test_first_matrix"]

    assert {
        "multi-peak-shell-at-centre-boundary-and-corner",
        "three-lobe-artifact-group",
        "curved-and-straight-filaments",
        "scale-one-and-scale-four-emission",
        "varying-noise-source",
        "two-nearby-independent-sources-with-faint-bridge",
        "deep-crowded-many-seed-field",
        "invalid-pixel-and-masked-gap",
    } <= set(matrix["association"])
    assert {
        "source-flux-counts-each-owned-pixel-once",
        "source-centroid-recovers-analytic-symmetry-centre",
        "source-apertures-are-disjoint",
    } <= set(matrix["measurement"])
    assert {
        "disconnected-significant-support-is-not-admitted",
        "connected-extended-wings-remain-admitted",
    } <= set(matrix["mask"])
    assert matrix["forbidden_inputs"] == [
        "terminal-ledger-products-or-per-realization-products",
        "viewed-sdc1-products",
        "viewed-hydra-products",
        "pybdsf-or-aegean-catalogues",
    ]


def test_source_reconstruction_review_requires_separate_replay_approval() -> (
    None
):
    """Named pre-review approval may open implementation, never execution."""
    review = _load()

    assert review["allowed_after_separate_approval"] == [
        "test-first-source-hierarchy-and-association-implementation",
        "test-first-source-level-measurement-implementation",
        "test-first-connected-support-admission-implementation",
        "prospective-source-topology-evaluator-implementation",
        "fixture-serial-and-existing-dask-validation",
        "non-executable-candidate-and-replay-identity-freeze",
    ]
    assert review["required_sequence"][-2:] == [
        "freeze-exact-non-executable-candidate-and-replay-identities",
        "obtain-separate-named-approval-before-one-complete-cumulative-replay",
    ]
