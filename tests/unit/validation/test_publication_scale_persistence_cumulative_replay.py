# pyright: reportMissingTypeStubs=false
"""Fail-closed contracts for the publication-scale-persistence replay."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from typing import Any

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[3]
_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_publication_scale_persistence_cumulative_regressions.py"
)
_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-publication-scale-persistence-cumulative-replay-review.json"
)
_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-publication-scale-persistence-cumulative-replay-execution-"
    "decision.json"
)
_SMOKE = (
    _ROOT / "benchmark-results/phase-5/"
    "prospective-science-smoke-publication-scale-persistence.json"
)


def _arguments() -> argparse.Namespace:
    """Return the exact reviewed replay invocation."""
    return argparse.Namespace(
        campaign=None,
        reference_reconstruction=Path(
            "benchmark-results/phase-5/"
            "viewed-reference-reconstruction-public-finder-correction"
        ),
        output=Path(
            "benchmark-results/phase-5/cumulative-regression-ledger-"
            "public-finder-publication-scale-persistence.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-publication-scale-"
            "persistence-937737d"
        ),
        workers=2,
        closed_component_baseline_ledger=Path(
            "benchmark-results/phase-5/cumulative-regression-ledger-"
            "recovery.json"
        ),
    )


def _load() -> dict[str, Any]:
    """Load one isolated wrapper composition."""
    return runpy.run_path(str(_WRAPPER))


def test_review_and_decision_bind_exact_execution() -> None:
    """User authority cannot drift to another candidate or namespace."""
    wrapper = _load()
    review = json.loads(_REVIEW.read_text(encoding="utf-8"))
    decision = json.loads(_DECISION.read_text(encoding="utf-8"))
    expected = wrapper["_expected_execution_fields"](_arguments())
    expected_sha256 = canonical_sha256(expected)

    assert review["expected_execution"] == expected
    assert review["expected_execution_sha256"] == expected_sha256
    assert decision["expected_execution_sha256"] == expected_sha256
    assert decision["identity_review"] == {
        "path": str(_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_REVIEW),
    }
    assert decision["execution_authorized"] is True
    assert not any(decision["prohibited_authorizations"].values())


def test_sealed_smoke_opens_only_the_larger_replay() -> None:
    """Zero confirmed failures, not post-result tuning, opens replay."""
    wrapper = _load()
    smoke = json.loads(_SMOKE.read_text(encoding="utf-8"))

    wrapper["_validate_smoke"]()

    assert smoke["terminal_failure_count"] == 0
    assert smoke["compact_product_identity_equal"] is True
    assert not [
        decision
        for decision in smoke["decisions"]
        if decision["status"] == "fail"
    ]
    precision = [
        decision
        for decision in smoke["decisions"]
        if decision["comparator_id"] == "pinned-pybdsf-master"
        and decision["endpoint_id"] == "continuum--mask-precision--overall"
    ]
    assert len(precision) == 1
    assert precision[0]["status"] == "underpowered"
    assert precision[0]["positive_regression"] < 0.05


def test_composition_replaces_stale_serializer_and_keeps_science_seams() -> (
    None
):
    """The replay cannot read the predecessor candidate's sidecar scratch."""
    frozen = _load()["_current_composition"]()

    assert frozen["_write_continuum_products"].__name__ == (
        "write_mask_separated"
    )
    assert frozen["_install_prospective_compiler"].__name__ == (
        "install_terminal_cycle"
    )
    assert frozen["_canonical_json_bytes"].__name__ == "_serialize_ledger"
    assert frozen["_git_revision"].__name__ == "_git_revision"


def test_authorized_replay_replaces_strict_historical_git_check(
    tmp_path: Path,
) -> None:
    """Ignored retained evidence must not fail after the no-write preflight."""
    wrapper = _load()
    output = tmp_path / "ledger.json"
    arguments = argparse.Namespace(output=output)
    frozen: dict[str, Any] = {
        "_generate_candidate_product": object(),
        "_git_revision": object(),
        "_parse_args": None,
    }

    def main() -> None:
        assert frozen["_git_revision"] is wrapper["_git_revision"]
        execution = frozen["_parse_args"]()
        execution.output.write_text('{"status":"pass"}\n', encoding="utf-8")

    def authorize(_arguments: argparse.Namespace) -> dict[str, object]:
        return {}

    frozen["main"] = main
    wrapper["run_authorized_replay"].__globals__.update(
        {
            "_authorize_replay": authorize,
            "_current_composition": lambda: frozen,
            "_generate_candidate_product": object(),
        }
    )

    wrapper["run_authorized_replay"](arguments)

    assert output.is_file()


def test_serializer_records_exact_provenance_and_current_diagnostics() -> None:
    """Terminal evidence names this replay and only its sidecar census."""
    wrapper = _load()
    serializer = wrapper["_serialize_ledger"]

    def aggregate(scratch: Path) -> dict[str, int]:
        return {
            "image_count": 1600,
            "scratch_is_current": int(
                scratch == wrapper["_PROSPECTIVE_SCRATCH_PATH"]
            ),
        }

    serializer.__globals__["_aggregate_completed_sidecars"] = aggregate

    document = json.loads(
        serializer(
            {
                "ledger_id": "phase-5-cumulative-regression-ledger",
                "status": "pass",
            }
        )
    )

    assert document["terminal_feature_persistence_diagnostics"] == {
        "image_count": 1600,
        "scratch_is_current": 1,
    }
    provenance = document["publication_scale_persistence_provenance"]
    assert provenance["candidate_smoke_sha256"] == file_sha256(_SMOKE)
    assert provenance["identity_review_sha256"] == file_sha256(_REVIEW)
    assert provenance["execution_decision_sha256"] == file_sha256(_DECISION)


def test_authorization_rejects_invocation_drift() -> None:
    """A changed output path cannot consume the one-replay authority."""
    wrapper = _load()
    arguments = _arguments()
    arguments.output = Path("benchmark-results/phase-5/different.json")

    try:
        wrapper["_require_exact_invocation"](arguments)
    except ValueError as error:
        assert "output changed" in str(error)
    else:
        raise AssertionError("drifted replay invocation was accepted")


def test_authorized_replay_publishes_ledger_atomically(tmp_path: Path) -> None:
    """The compiler writes privately before the final hard-link publish."""
    wrapper = _load()
    output = tmp_path / "ledger.json"
    arguments = argparse.Namespace(output=output)
    frozen: dict[str, Any] = {
        "_generate_candidate_product": object(),
        "_parse_args": None,
    }

    def main() -> None:
        execution = frozen["_parse_args"]()
        execution.output.write_text('{"status":"pass"}\n', encoding="utf-8")

    def authorize(_arguments: argparse.Namespace) -> dict[str, object]:
        return {}

    def current() -> dict[str, Any]:
        return frozen

    frozen["main"] = main
    wrapper["run_authorized_replay"].__globals__.update(
        {
            "_authorize_replay": authorize,
            "_current_composition": current,
            "_generate_candidate_product": object(),
        }
    )

    wrapper["run_authorized_replay"](arguments)

    assert output.read_text(encoding="utf-8") == '{"status":"pass"}\n'
    assert not tuple(tmp_path.glob(".*.tmp"))
