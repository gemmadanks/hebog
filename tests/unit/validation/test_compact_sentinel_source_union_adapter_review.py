"""Contracts for the prospective finder source-union adapter review."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

_ROOT = Path(__file__).parents[3]
_PROGRAM = _ROOT / (
    "scripts/validation/"
    "review_phase5_compact_sentinel_source_union_adapters.py"
)
_REVIEW = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-sentinel-source-union-adapter-pre-review.json"
)


def _review() -> dict[str, Any]:
    """Load the checked-in non-executable prospective review."""
    value: object = json.loads(_REVIEW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _reviewed_sha256(relative_path: str) -> str:
    """Hash one dependency at the exact commit inspected by the review."""
    revision = cast(str, _review()["binding_context"]["repository_commit"])
    contents = subprocess.run(
        ("git", "show", f"{revision}:{relative_path}"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(contents).hexdigest()


def test_review_is_non_executable_and_requires_exact_approval() -> None:
    """A design review cannot authorize implementation or execution."""
    review = _review()

    assert review["schema_version"] == 1
    assert review["review_id"] == (
        "phase-5-compact-held-out-sentinel-source-union-adapter-pre-review"
    )
    assert review["status"] == (
        "ready-for-named-fixture-only-source-union-adapter-implementation-"
        "review"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-review-for-test-first-fixture-only-"
        "finder-source-union-adapters"
    )


def test_review_binds_approved_alignment_and_current_product_schemas() -> None:
    """Recommendations bind exact historical product contracts."""
    bindings = _review()["binding_context"]["repository_files"]

    for binding in bindings.values():
        assert _reviewed_sha256(binding["path"]) == binding["sha256"]
    assert bindings["approved_root_cause_review"]["sha256"] == (
        "f94d0455be9bbb4472b7ee6e6b0cd24fbf4ecc8be1d3e8a293d4467dbc02cad3"
    )
    assert _review()["binding_context"]["released_pybdsf"] == {
        "container_digest": (
            "sha256:5310afe78c8fc09ed99ddee1c6978e5e32181b69f1d22432a02ef6e3a6761198"
        ),
        "dependency_inventory_sha256": (
            "8211043e9fca55d706d1e890e2bf0b630e228a854db0949258c498506975669f"
        ),
        "release_commit": "1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc",
        "version": "1.14.1",
    }


def test_hebog_adapter_uses_exact_association_membership() -> None:
    """Hebog source unions are a lossless projection, not an inference."""
    design = _review()["adapter_designs"]["current_hebog"]

    assert design["classification"] == "direct-lossless-projection"
    assert design["source_measurements"] == "terminal.catalogue"
    assert design["component_measurements"] == "terminal.component_catalogue"
    assert design["membership"] == (
        "terminal.source_association.memberships joined through "
        "terminal.source_association.components.label_value"
    )
    assert design["owner_plane"] == "terminal.measurement_component_labels"
    assert design["coverage"] == "every positive owner pixel exactly once"


def test_pybdsf_adapter_uses_source_rows_and_named_model_partition() -> None:
    """PyBDSF source semantics cannot be approximated by Gaussian rows."""
    design = _review()["adapter_designs"]["released_pybdsf"]

    assert design["classification"] == (
        "prospective-explicit-source-model-dominance-partition"
    )
    assert design["source_measurements"] == (
        "native srl catalogue Total_flux and RA/DEC, one row per "
        "canonical (Isl_id, Source_id)"
    )
    assert design["component_measurements"] == (
        "native gaul catalogue rows retained diagnostic-only"
    )
    assert design["multi_source_island_partition"] == (
        "within the native island, assign each pixel to the canonical "
        "source whose summed accepted-Gaussian model is largest"
    )
    assert design["tie_break"] == (
        "lexicographically first canonical (Isl_id, Source_id)"
    )
    assert design["scientific_label"] == (
        "pybdsf-source-model-dominance-v1-derived-topology"
    )
    assert design["native_export_available"] is False


def test_review_preserves_fitless_support_without_inventing_sources() -> None:
    """Mask-only PyBDSF islands remain visible outside source topology."""
    fitless = _review()["fitless_native_support"]

    assert fitless["binary_mask_binding"] == "all positive native support"
    assert fitless["source_union_binding"] == (
        "only support owned by a real source row"
    )
    assert fitless["unowned_support"] == (
        "whole native islands with no accepted source row, retained with "
        "count, pixel count, and membership digest"
    )
    assert fitless["forbidden"] == [
        "drop fitless pixels from binary-mask metrics",
        "fabricate a catalogue source for a fitless island",
        "partially leave a modelled island unowned",
    ]
    assert _review()["alignment_contract_amendment"]["required"] is True


def test_review_rejects_unreviewed_shortcuts() -> None:
    """Common shortcuts would reintroduce unlike topology semantics."""
    rejected = set(_review()["rejected_alternatives"])

    assert {
        "treat-one-pybdsf-island-as-one-source",
        "duplicate-a-whole-island-for-every-pybdsf-source",
        "nearest-gaussian-or-source-centroid-partition",
        "aggregate-gaussian-centres-instead-of-using-srl-source-centres",
        "drop-fitless-native-islands",
        "fabricate-dummy-sources-for-fitless-native-islands",
        "treat-pybdsf-as-ground-truth",
    } <= rejected


def test_review_requires_edge_fixtures_before_identity_freeze() -> None:
    """All ambiguous ownership and empty-support cases are fixture-gated."""
    review = _review()
    fixtures = set(review["test_first_matrix"])

    assert {
        "hebog-one-source-multiple-component-owners",
        "hebog-two-sources-and-complete-component-partition",
        "hebog-source-catalogue-membership-mismatch-fails-closed",
        "pybdsf-one-island-one-source-owns-whole-island",
        "pybdsf-one-island-multiple-sources-model-dominance-partition",
        "pybdsf-multiple-gaussians-one-source-uses-srl-observables",
        "pybdsf-model-dominance-exact-tie-is-canonical",
        "pybdsf-fitless-island-remains-mask-only",
        "pybdsf-modelled-plus-fitless-islands-retain-both-domains",
        "pybdsf-source-with-zero-owned-pixels-fails-closed",
        "pybdsf-missing-or-duplicate-srl-gaul-membership-fails-closed",
        "source-union-relabel-order-and-worker-invariance",
        "binary-mask-invariance-to-source-union-partition",
        "array-free-owned-and-unowned-membership-digests",
    } <= fixtures
    assert review["required_sequence"][-3:] == [
        "freeze-new-seed-disjoint-sentinel-identities-only-after-all-fixtures-pass",
        "obtain-separate-exact-one-use-approval-before-executing-either-finder",
        "keep-phase-5-open-until-the-new-like-semantics-sentinel-passes",
    ]


def test_review_writer_is_write_once(tmp_path: Path) -> None:
    """The prospective review is canonical, reproducible, and immutable."""
    program = runpy.run_path(str(_PROGRAM))
    output = tmp_path / "review.json"
    review = _review()

    program["write_review"](output, review)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert output.read_text(encoding="utf-8").endswith("\n")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        program["write_review"](output, review)
