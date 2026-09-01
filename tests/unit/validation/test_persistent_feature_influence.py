# pyright: reportMissingTypeStubs=false
"""Governance contracts for prospective persistent-feature influence."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.mask_origin_sibling_pair import (
    build_mask_origin_sibling_pair_continuum_products,
)

_ROOT = Path(__file__).parents[3]
_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-persistent-feature-influence-pre-review.json"
)
_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-persistent-feature-influence-implementation-"
    "decision.json"
)
_ACTIVATION_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-mask-origin-sibling-pair-activation-repair-"
    "pre-review.json"
)
_ACTIVATION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-mask-origin-sibling-pair-activation-repair-"
    "implementation-decision.json"
)
_MATERIALIZER = (
    _ROOT / "scripts/validation/"
    "materialize_phase5_prospective_persistent_feature_influence_products.py"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_persistent_feature_influence_smoke.py"
)


def test_pre_review_binds_terminal_failure_and_all_observed_topologies() -> (
    None
):
    """The prospective policy answers the exact closed smoke evidence."""
    review = json.loads(_PRE_REVIEW.read_text(encoding="utf-8"))

    assert review["binding_evidence"]["terminal_smoke_sha256"] == (
        "778e43a96f0fad15c7ae28a562bcd18ca4b6e000df672221657e0803148addfc"
    )
    observed = review["causal_review"]["observed_topology"]
    assert len(observed) == 4
    assert {
        (item["dataset_identifier"], item["seed"], item["truth_group"])
        for item in observed
    } == {
        (
            "phase5-external-post-failure-continuum-1-1024",
            2026860341,
            "extended-edge-0001",
        ),
        (
            "phase5-external-post-failure-continuum-3-1024",
            2026862118,
            "extended-diffuse-0001",
        ),
        (
            "phase5-external-post-failure-continuum-3-1024",
            2026862301,
            "artifact-bright-sidelobes-0001",
        ),
        (
            "phase5-external-post-failure-continuum-3-1024",
            2026862301,
            "extended-diffuse-0001",
        ),
    }
    assert review["candidate_rule"]["policy_id"] == (
        "mutually-unique-persistent-feature-symmetric-b3-influence-pair-v1"
    )
    assert (
        review["authorization"]["threshold_or_margin_tuning_authorized"]
        is False
    )
    assert review["authorization"]["rescoring_closed_evidence_authorized"] is (
        False
    )


def test_implementation_decision_binds_exact_reviewed_programs() -> None:
    """No governed source or producer byte can drift before execution."""
    decision = json.loads(_DECISION.read_text(encoding="utf-8"))

    assert decision["pre_review"] == {
        "path": str(_PRE_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_PRE_REVIEW),
    }
    assert decision["fixed_predecessor_identity"] == {
        "activation_repair_implementation_decision_sha256": file_sha256(
            _ACTIVATION_DECISION
        ),
        "activation_repair_pre_review_sha256": file_sha256(
            _ACTIVATION_PRE_REVIEW
        ),
        "failed_candidate_product_set_canonical_sha256": (
            "021d24ee6a75af6e96f703c4425d54ffc9268902e5ee20301eac75fa6c82ebff"
        ),
        "failed_candidate_revision": (
            "52d4fed7e13aa4a79379c99155ce5f35bb60521c"
        ),
        "terminal_smoke_sha256": (
            "778e43a96f0fad15c7ae28a562bcd18ca4b6e000df672221657e0803148addfc"
        ),
    }
    for identity in decision["implementation"]:
        assert file_sha256(_ROOT / identity["path"]) == identity["sha256"]


def test_configuration_composes_exact_activation_and_topology_reviews() -> (
    None
):
    """The smoke configuration binds both process and science layers."""
    wrapper = runpy.run_path(str(_MATERIALIZER))
    base_configuration = wrapper["_base"](_ROOT)["_current_configuration"](
        _ROOT
    )

    assert wrapper["_current_configuration"](_ROOT) == canonical_sha256(
        {
            "base_configuration_sha256": base_configuration,
            "persistent_feature_influence_pre_review_sha256": file_sha256(
                _PRE_REVIEW
            ),
            "persistent_feature_influence_implementation_decision_sha256": (
                file_sha256(_DECISION)
            ),
        }
    )


def test_composition_keeps_the_activated_final_publication_writer() -> None:
    """The topology layer cannot accidentally bypass the mask repair."""
    wrapper = runpy.run_path(str(_MATERIALIZER))

    frozen = wrapper["_current_composition"](
        _ROOT,
        revision="candidate-revision",
        configuration="candidate-configuration",
    )

    writer = frozen["_write_continuum_products"]
    separated_writer = writer.__globals__[  # pyright: ignore[reportFunctionMemberAccess]
        "_write_mask_separated_continuum_products"
    ]
    assert (
        separated_writer.__globals__[  # pyright: ignore[reportFunctionMemberAccess]
            "build_public_finder_source_reconstruction_continuum_products"
        ]
        is build_mask_origin_sibling_pair_continuum_products
    )


def test_materializer_fails_closed_on_unknown_candidate_mode() -> None:
    """Only the exact current and immutable incumbent producers may run."""
    wrapper = runpy.run_path(str(_MATERIALIZER))

    with pytest.raises(ValueError, match="mode is unsupported"):
        wrapper["_composition"](
            {"candidate_mode": "unknown", "tooling_root": str(_ROOT)}
        )


def test_cli_installs_every_replacement_override() -> None:
    """Spawned workers resolve only this layer's importable functions."""
    wrapper = runpy.run_path(str(_MATERIALIZER))
    entrypoint = wrapper["_install_materializer_overrides"](
        wrapper["_base"](_ROOT)
    )

    for name in (
        "_current_configuration",
        "_current_composition",
        "_verified_reference",
        "_composition",
        "_generate_product",
    ):
        assert entrypoint.__globals__[name] is wrapper[name]


def test_evaluator_dispatches_only_the_replacement_materializer() -> None:
    """The write-once evaluator cannot select a predecessor producer."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    base = evaluator["_base"](_ROOT)
    expected = (
        "scripts/validation/"
        "materialize_phase5_prospective_persistent_feature_influence_"
        "products.py"
    )

    assert base["_MATERIALIZER"] == expected
    assert base["main"].__globals__["_MATERIALIZER"] == expected
