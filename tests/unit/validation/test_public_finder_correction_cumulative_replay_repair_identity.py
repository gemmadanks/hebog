"""Contracts for the replacement correction replay identity freeze."""

from __future__ import annotations

import json
import runpy
import subprocess
from argparse import Namespace
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "repair-review.json"
)
_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_public_finder_correction_cumulative_regressions.py"
)


def _load() -> dict[str, Any]:
    """Load the non-executable replacement review."""
    return json.loads(_REVIEW.read_text(encoding="utf-8"))


def _arguments() -> Namespace:
    """Return the exact prospective two-worker invocation."""
    return Namespace(
        campaign=None,
        reference_reconstruction=(
            _ROOT / "benchmark-results/phase-5/viewed-reference-reconstruction"
        ),
        output=(
            _ROOT / "benchmark-results/phase-5/"
            "cumulative-regression-ledger-public-finder-correction.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-correction-b1d59e5"
        ),
        workers=2,
        closed_component_baseline_ledger=(
            _ROOT / "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
    )


def test_replacement_review_is_exact_and_non_executable() -> None:
    """The identity freeze grants no replay or later lifecycle action."""
    review = _load()

    assert review["status"] == (
        "ready-for-named-public-finder-correction-cumulative-replay-approval"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "separate-named-approval-bound-to-this-review-for-one-complete-"
        "cumulative-replay-only"
    )
    assert review["rejected_composition"]["transferable_to_repair"] is False
    assert (
        review["population"]["viewed_public_products_opened_during_freeze"]
        is False
    )


def test_replacement_review_binds_live_programs_and_evidence() -> None:
    """Every delegated program and closed identity is checksum-bound."""
    review = _load()
    records = [
        review["candidate"]["correction_contract"],
        review["closed_boundary"]["baseline"],
        review["dependency_runtime"]["uv_lock"],
        review["implementation"]["decision"],
        review["implementation"]["pre_review"],
        review["implementation"]["wrapper"],
        review["implementation"]["wrapper_tests"],
        review["population"]["original_request"],
        *review["programs_and_contracts"].values(),
        review["rejected_composition"]["decision"],
        review["rejected_composition"]["identity_review"],
    ]
    for value in records:
        record = cast(dict[str, str], value)
        assert file_sha256(_ROOT / record["path"]) == record["sha256"]
    recovery = review["population"]["reference_reconstruction"]
    assert (
        file_sha256(_ROOT / recovery["path"] / "recovery.json")
        == (recovery["recovery_sha256"])
    )
    implementation = review["implementation"]
    tree = subprocess.check_output(
        ("git", "rev-parse", f"{implementation['commit']}^{{tree}}"),
        cwd=_ROOT,
        text=True,
    ).strip()
    assert tree == implementation["tree"]


def test_replacement_review_matches_wrapper_execution_fields() -> None:
    """The future decision fields equal the wrapper's exact expectations."""
    review = _load()
    wrapper = runpy.run_path(str(_WRAPPER))
    expected = wrapper["_expected_execution_fields"](_arguments())

    assert expected == {
        "base_review_sha256": (
            review["programs_and_contracts"]["base_review"]["sha256"]
        ),
        "candidate_configuration_sha256": review["candidate"][
            "configuration_sha256"
        ],
        "candidate_revision": review["candidate"]["commit"],
        "candidate_source_tree_sha256": review["candidate"][
            "source_tree_sha256"
        ],
        "closed_baseline_path": str(
            _ROOT / review["closed_boundary"]["baseline"]["path"]
        ),
        "closed_baseline_sha256": review["closed_boundary"]["baseline"][
            "sha256"
        ],
        "compatibility_container_digest": review["dependency_runtime"][
            "compatibility_container"
        ]["digest"],
        "compatibility_dependency_inventory_sha256": review[
            "dependency_runtime"
        ]["compatibility_container"]["dependency_inventory_sha256"],
        "compiler_sha256": review["programs_and_contracts"]["compiler"][
            "sha256"
        ],
        "correction_contract_sha256": review["candidate"][
            "correction_contract"
        ]["sha256"],
        "dependency_lock_sha256": review["dependency_runtime"]["uv_lock"][
            "sha256"
        ],
        "endpoint_registry_sha256": review["programs_and_contracts"][
            "endpoint_registry"
        ]["sha256"],
        "evaluation_contract_sha256": review["programs_and_contracts"][
            "evaluation_contract"
        ]["sha256"],
        "evaluator_sha256": review["programs_and_contracts"]["evaluator"][
            "sha256"
        ],
        "historical_replay_sha256": review["programs_and_contracts"][
            "frozen_historical_replay"
        ]["sha256"],
        "implementation_decision_sha256": review["implementation"]["decision"][
            "sha256"
        ],
        "output_path": str(
            _ROOT / review["prospective_execution"]["output"]["path"]
        ),
        "reference_reconstruction_path": str(
            _ROOT / review["population"]["reference_reconstruction"]["path"]
        ),
        "reference_reconstruction_sha256": review["population"][
            "reference_reconstruction"
        ]["recovery_sha256"],
        "reference_verifier_sha256": review["programs_and_contracts"][
            "reference_verifier"
        ]["sha256"],
        "scratch_path": review["prospective_execution"]["scratch"]["path"],
        "viewed_request_sha256": review["population"]["original_request"][
            "sha256"
        ],
        "workers": review["prospective_execution"]["workers"],
        "wrapper_sha256": review["implementation"]["wrapper"]["sha256"],
    }


def test_replacement_write_once_and_public_outputs_are_absent() -> None:
    """Freezing identities creates no replay or corrected viewed products."""
    review = _load()
    execution = review["prospective_execution"]

    assert not (_ROOT / execution["execution_decision"]["path"]).exists()
    assert not (_ROOT / execution["output"]["path"]).exists()
    assert not Path(execution["scratch"]["path"]).exists()
    for name in (
        "public-finder-correction-analysis.json",
        "public-finder-correction-comparison",
        "public-finder-correction-decision.json",
    ):
        assert not (_ROOT / "benchmark-results/phase-5" / name).exists()
