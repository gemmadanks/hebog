"""Governance for the rejected correction replay composition."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any, cast

from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.external_runners import file_sha256
from hebog.validation.public_finder_correction import (
    public_finder_correction_candidate_configuration,
)

_ROOT = Path(__file__).parents[3]
_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-public-finder-correction-cumulative-replay-decision.json"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-public-finder-correction-cumulative-replay-repair-pre-review.json"
)
_FROZEN_REPLAY = (
    _ROOT / "scripts/validation/review_phase5_cumulative_regressions.py"
)


def _load(path: Path) -> dict[str, Any]:
    """Load one governed JSON record."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_approved_replay_failed_closed_before_execution() -> None:
    """The exact approval cannot transfer to a changed composition."""
    decision = _load(_DECISION)

    assert decision["status"] == (
        "approved-but-preflight-rejected-before-execution"
    )
    assert decision["authorization"]["cumulative_replay_authorized"] is True
    for key, value in decision["authorization"].items():
        if key != "cumulative_replay_authorized":
            assert value is False
    assert decision["preflight"]["execution_process_started"] is False
    assert decision["preflight"]["scientific_products_opened"] is False
    assert decision["preflight"]["write_once_output_created"] is False
    assert decision["preflight"]["output_state"] == "absent"
    assert decision["preflight"]["failure_stage"] == (
        "no-write-candidate-composition-validation"
    )
    assert decision["transfer_policy"] == {
        "authorization_consumed_by_execution": False,
        "authorization_transferable_to_changed_program": False,
        "execution_eligible": False,
        "replacement_identity_review_required": True,
    }


def test_repair_pre_review_is_exact_and_non_executable() -> None:
    """The repair boundary freezes evidence but grants no implementation."""
    review = _load(_PRE_REVIEW)

    assert review["status"] == (
        "ready-for-named-replay-repair-implementation-review"
    )
    assert set(review["authorization_boundary"].values()) == {False}
    assert set(review["scientific_scope"].values()) == {False}
    identities = (
        review["approved_but_rejected_execution"]["decision"],
        review["approved_but_rejected_execution"]["identity_review"],
        review["approved_but_rejected_execution"]["program"],
    )
    for identity in cast(tuple[dict[str, str], ...], identities):
        assert file_sha256(_ROOT / identity["path"]) == identity["sha256"]


def test_pre_review_binds_actual_correction_configuration() -> None:
    """The prospective identity includes the correction, not only its base."""
    review = _load(_PRE_REVIEW)
    configuration = public_finder_correction_candidate_configuration(
        _ROOT / "config/contracts/phase-5-corrective-a-review.json",
        _ROOT / "config/contracts/phase-5-public-finder-correction.json",
    )

    assert (
        canonical_sha256(configuration)
        == (review["candidate"]["correction_configuration_sha256"])
    )
    assert (
        review["candidate"]["correction_configuration_sha256"]
        != (review["candidate"]["base_configuration_sha256"])
    )


def test_frozen_replay_really_selects_pre_correction_candidate() -> None:
    """The no-write finding exercises the actual frozen module seams."""
    frozen = runpy.run_path(str(_FROZEN_REPLAY))

    assert frozen["_CANDIDATE_REVISION"] == (
        "c184acf7f55f936442285835b4601a6ac193fe2a"
    )
    assert frozen["_candidate_configuration_sha256"]() == (
        "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
    )
    writer_globals = frozen["_write_continuum_products"].__globals__
    assert (
        writer_globals["build_post_correction_continuum_products"].__name__
        == "build_post_correction_continuum_products"
    )
    assert "build_public_finder_correction_continuum_products" not in (
        writer_globals
    )
