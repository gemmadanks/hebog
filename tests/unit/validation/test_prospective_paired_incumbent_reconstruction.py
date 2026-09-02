"""Prospective paired incumbent provenance-reconstruction tests."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_PROGRAM = (
    _ROOT / "scripts/validation/"
    "reconstruct_phase5_prospective_paired_incumbent.py"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-incumbent-provenance-repair-pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-incumbent-provenance-repair-"
    "implementation-decision.json"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-incumbent-reconstruction-identity-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-incumbent-reconstruction-execution-"
    "decision.json"
)


def _program() -> dict[str, Any]:
    """Load the reconstruction program without executing its CLI."""
    return runpy.run_path(str(_PROGRAM))


def _association() -> dict[str, object]:
    """Return a minimal source-association document."""
    return {
        "schema_version": 1,
        "components": [
            {
                "component_id": "component-a",
                "label_value": 3,
            },
            {
                "component_id": "component-b",
                "label_value": 7,
            },
        ],
        "memberships": [
            {
                "source_id": "source-a",
                "component_ids": ["component-a"],
            },
            {
                "source_id": "source-b",
                "component_ids": ["component-b"],
            },
        ],
    }


def test_pre_review_records_the_failed_product_boundary() -> None:
    """The repair refuses to reinterpret the mixed-lineage product set."""
    review = json.loads(_PRE_REVIEW.read_text(encoding="utf-8"))

    assert review["status"] == (
        "reviewed-before-incumbent-producer-provenance-repair"
    )
    assert review["failed_execution"] == {
        "atomic_output_published": False,
        "current_product_count": 2400,
        "current_product_set_sha256": (
            "6bcb2959c56173d1a930eb14b3a794727649defc1b52dc1d9d70cd041d401014"
        ),
        "error": (
            "ValueError: associated source supports must be present and "
            "disjoint"
        ),
        "failed_incumbent_product_count": 2400,
        "failed_incumbent_product_set_sha256": (
            "b373cafe20285326b7a2f51b990670981edaf8dc06db16e11e8989ae86680528"
        ),
        "failed_stage": "paired-incumbent-continuum-compilation",
        "original_execution_commit": (
            "9fa879f924b34e9ba7150494700dde00f664a7a7"
        ),
    }
    assert review["authorization"]["incumbent_reconstruction_authorized"]
    assert review["authorization"]["evaluation_only_completion_authorized"]
    assert (
        review["authorization"]["current_candidate_execution_authorized"]
        is False
    )


def test_module_origin_requires_the_exact_historical_source_tree(
    tmp_path: Path,
) -> None:
    """A checked revision cannot be paired with imports from another tree."""
    require = _program()["_require_module_origin"]
    root = tmp_path / "candidate"
    expected = root / "src/hebog/validation/public_finder_correction.py"
    expected.parent.mkdir(parents=True)
    expected.touch()

    require(root, expected)
    with pytest.raises(ValueError, match="module origin"):
        require(root, tmp_path / "current/public_finder_correction.py")


def test_historical_support_partition_accepts_exact_disjoint_membership() -> (
    None
):
    """Every catalogue source partitions the one historical label plane."""
    verify = _program()["_verify_support_partition"]
    labels = np.array([[0, 3], [7, 7]], dtype=np.int32)

    verify(_association(), ("source-a", "source-b"), labels)


@pytest.mark.parametrize(
    ("labels", "catalogue", "message"),
    [
        (np.array([[0, 3], [0, 0]]), ("source-a", "source-b"), "partition"),
        (np.array([[0, 3], [7, 7]]), ("source-a",), "catalogue"),
        (np.array([[0, -1], [7, 7]]), ("source-a", "source-b"), "label"),
    ],
)
def test_historical_support_partition_rejects_incomplete_or_invalid_products(
    labels: np.ndarray, catalogue: tuple[str, ...], message: str
) -> None:
    """The repair cannot invent absent supports or ignore catalogue rows."""
    verify = _program()["_verify_support_partition"]

    with pytest.raises(ValueError, match=message):
        verify(_association(), catalogue, labels)


def test_reconstruction_program_binds_approved_review() -> None:
    """The executable program embeds the review and historical identities."""
    program = _program()

    assert program["_PRE_REVIEW_SHA256"] == file_sha256(_PRE_REVIEW)
    assert program["_INCUMBENT_REVISION"] == (
        "85d580713664b962ae256a98b065849cf8eb9283"
    )
    assert program["_INCUMBENT_SOURCE_TREE_SHA256"] == (
        "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
    )
    assert program["_INCUMBENT_CONFIGURATION_SHA256"] == (
        "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
    )


def test_implementation_decision_binds_provenance_only_repair() -> None:
    """The authorized repair is provenance-only and checksum complete."""
    decision = json.loads(_IMPLEMENTATION_DECISION.read_text(encoding="utf-8"))

    assert decision["pre_review"]["sha256"] == file_sha256(_PRE_REVIEW)
    program = decision["implementation"]
    assert (
        file_sha256(_ROOT / program["reconstruction_program_path"])
        == program["reconstruction_program_sha256"]
    )
    assert decision["authorization"]["incumbent_reconstruction_authorized"]
    assert decision["authorization"]["scientific_change_authorized"] is False
    assert (
        decision["repair_boundary"]["paired_decision_policy_changed"] is False
    )


def test_reconstruction_identity_review_binds_the_verified_invocation() -> (
    None
):
    """The no-write record binds every executable reconstruction identity."""
    review = json.loads(_IDENTITY_REVIEW.read_text(encoding="utf-8"))
    program = _program()
    arguments = argparse.Namespace(
        closed_baseline=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
        historical_root=Path(
            "/private/tmp/hebog-phase5-terminal-parent-replay-c1614c2"
        ),
        output=Path(
            "benchmark-results/phase-5/"
            "prospective-paired-incumbent-reconstruction.json"
        ),
        population=Path(
            "config/contracts/phase-5-prospective-paired-population.json"
        ),
        reference_reconstruction=Path(
            "benchmark-results/phase-5/"
            "viewed-reference-reconstruction-public-finder-correction"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-prospective-paired-"
            "incumbent-authentic-85d5807"
        ),
        source_request=Path(
            "benchmark-results/phase-5/external-post-failure-comparison/"
            "campaign-request.json"
        ),
        workers=2,
    )

    assert review["status"] == (
        "ready-for-authorized-provenance-only-reconstruction"
    )
    assert not any(review["authorization"].values())
    assert review["expected_execution_sha256"] == program["canonical_sha256"](
        program["_expected_execution_fields"](arguments)
    )
    assert review["implementation"]["program_sha256"] == file_sha256(_PROGRAM)
    assert review["implementation"]["decision_sha256"] == file_sha256(
        _IMPLEMENTATION_DECISION
    )


def test_reconstruction_execution_decision_consumes_only_repair_scope() -> (
    None
):
    """The one-use decision permits reconstruction and evaluation only."""
    decision = json.loads(_EXECUTION_DECISION.read_text(encoding="utf-8"))
    review = json.loads(_IDENTITY_REVIEW.read_text(encoding="utf-8"))

    assert decision["identity_review"]["sha256"] == file_sha256(
        _IDENTITY_REVIEW
    )
    assert (
        decision["expected_execution_sha256"]
        == review["expected_execution_sha256"]
    )
    assert decision["incumbent_reconstruction_authorized"] is True
    assert decision["evaluation_authorized"] is True
    assert not any(decision["prohibited_authorizations"].values())
