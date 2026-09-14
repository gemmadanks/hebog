"""Contracts for the Phase 5 coarse-science gap review."""

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
    / "scripts/validation/review_phase5_coarse_measurement_and_topology.py"
)
_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-coarse-measurement-and-topology-pre-review.json"
)


def _review() -> dict[str, Any]:
    """Load the checked-in non-executable review."""
    value: object = json.loads(_REVIEW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_review_is_non_executable_and_requires_named_approval() -> None:
    """A diagnosis cannot itself authorize a science change or execution."""
    review = _review()

    assert review["schema_version"] == 1
    assert review["review_id"] == (
        "phase-5-coarse-measurement-and-topology-pre-review"
    )
    assert review["status"] == (
        "ready-for-named-measurement-and-topology-correction-review"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-review-for-test-first-fixture-only-"
        "measurement-and-topology-correction"
    )


def test_review_binds_terminal_evidence_and_source_protected_successor() -> (
    None
):
    """The prospective recommendation stays attached to exact evidence."""
    context = _review()["binding_context"]

    assert (
        file_sha256(_ROOT / context["root_cause_review"]["path"])
        == (context["root_cause_review"]["sha256"])
    )
    assert context["root_cause_review"]["sha256"] == (
        "8e00269924b50c1b52188beefcb177e50d9035e25a69755d5d2d31ddead3d902"
    )
    assert context["candidate"] == {
        "configuration_sha256": (
            "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
        ),
        "revision": "7ebde589c82e153e0f7d475a8469c120138be4da",
        "source_tree_sha256": (
            "c83ee5a90c33f9c915b69402710835a5a094d08df83e003f8e2fd0799f23ae2d"
        ),
    }
    successor = context["source_protected_successor"]
    assert successor["implementation_decision"]["sha256"] == (
        "0bf418efede130b49a50ea0fea7c216856d5a0c434b64932111a7c7682a36e8f"
    )
    assert successor["public_identity"]["sha256"] == (
        "4f8c110fb45ffa151d54bc9c9dfdad1385306101a1e8397718f82a0b43388b81"
    )
    assert successor["lane_identity"]["sha256"] == (
        "9f416775382a55dd600dbf6956b0ced069a6bd692bc7a0e36783702e34fe8eb3"
    )


def test_measurement_gap_is_localized_without_claiming_unobserved_pixels() -> (
    None
):
    """The review separates strong localization from missing attribution."""
    finding = _review()["causal_findings"]["source_photometry_support"]

    assert finding["classification"] == (
        "localized-source-photometry-composition-gap"
    )
    scale_twelve = finding["strongest_observed_contrast"]
    assert scale_twelve["integrated_flux_error_median"] == pytest.approx(
        0.529076
    )
    assert scale_twelve["truth_support_recall_median"] == pytest.approx(
        0.947679
    )
    assert scale_twelve["background_error_median_rms"] == pytest.approx(
        0.015469
    )
    assert finding["evidence_limit"] == (
        "retained scalar observations do not identify the exact missing "
        "aperture pixels or apportion the remaining loss between source-"
        "owned support and finite aperture growth"
    )


def test_split_gap_is_catalogue_association_not_publication_mask() -> None:
    """The binding split metric cannot be attributed to mask publication."""
    findings = _review()["causal_findings"]
    topology = findings["catalogue_source_topology"]

    assert topology["classification"] == (
        "confirmed-catalogue-association-over-splitting"
    )
    shell = topology["strongest_observed_contrast"]
    assert shell["split_fraction"] == pytest.approx(2 / 3)
    assert shell["integrated_flux_error_median"] == pytest.approx(0.003100)
    assert shell["mask_iou_median"] == pytest.approx(0.926517)
    assert findings["publication_mask"]["classification"] == (
        "excluded-as-the-cause-of-the-binding-split-metric"
    )
    assert topology["exact_rejection_branch"] == (
        "unresolved-until-production-equivalent-red-fixtures-retain-"
        "hierarchy-diagnostics"
    )


def test_recommendation_preserves_thresholds_and_uses_owned_evidence() -> None:
    """The proposal is bounded, source-blind, and not aperture tuning."""
    correction = _review()["recommended_correction"]
    measurement = correction["source_owned_measurement_support"]
    topology = correction["conservative_source_parent"]

    assert measurement["aperture_policy"] == (
        "retain the existing 1.5-beam outer guard; extend its seed from "
        "measurement labels to the exact source-owned multiscale support "
        "union"
    )
    assert measurement["ownership_conflicts"] == (
        "assign once by deterministic nearest immutable member support and "
        "canonical source identity for exact distance ties"
    )
    assert topology["positive_evidence"] == (
        "one exclusive connected adjacent-scale feature graph with every "
        "member anchored by immutable direct support and no competing parent "
        "assignment"
    )
    assert topology["resilience_rule"] == (
        "an unowned persistent terminal feature may corroborate topology but "
        "cannot add membership; one missing or displaced child cannot veto "
        "an otherwise exclusive persistent whole-source graph"
    )
    assert topology["negative_controls"] == [
        "close-unrelated-pair",
        "crossing-or-branched-features",
        "competing-source-parent",
        "single-scale-broad-bridge",
    ]
    assert correction["new_numeric_science_thresholds"] is False
    assert correction["truth_or_reference_finder_inputs"] is False
    assert correction["global_aperture_radius_change"] is False


def test_review_requires_production_equivalent_red_fixtures() -> None:
    """The next implementation must close both mechanisms before a lane."""
    review = _review()
    fixtures = set(review["test_first_matrix"])

    assert {
        "mixed-core-halo-source-owned-photometry-at-4-8-and-12-beam-extents",
        "eight-knot-shell-at-interior-edge-and-tile-corner",
        "seven-knot-curved-filament-negative-and-positive-controls",
        "missing-and-displaced-terminal-feature",
        "close-unrelated-blend-must-not-merge",
        "overlapping-source-support-is-owned-once",
        "measurement-versus-publication-attribution",
        "serial-existing-dask-tile-order-and-retry-invariance",
    } <= fixtures
    assert review["required_sequence"][-3:] == [
        "freeze-exact-non-executable-combined-candidate-and-lane-identities",
        "obtain-separate-exact-approval-before-running-the-combined-"
        "development-lane",
        "open-held-out-qualification-only-after-every-development-geometry-"
        "passes",
    ]


def test_review_writer_is_write_once(tmp_path: Path) -> None:
    """The review record is finite sorted JSON and is never overwritten."""
    program = runpy.run_path(str(_PROGRAM))
    output = tmp_path / "review.json"
    review = _review()

    program["write_review"](output, review)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert output.read_text(encoding="utf-8").endswith("\n")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        program["write_review"](output, review)
