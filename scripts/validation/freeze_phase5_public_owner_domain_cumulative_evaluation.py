#!/usr/bin/env python3
"""Freeze the version-8 cumulative evaluation identity and authority."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[2]
_PREFIX = "phase-5-public-owner-domain-cumulative-evaluation"
_IMPLEMENTATION = Path(
    f"config/contracts/{_PREFIX}-implementation-decision.json"
)
_IDENTITY = Path(f"config/contracts/{_PREFIX}-identity-review.json")
_DECISION = Path(f"config/contracts/{_PREFIX}-execution-decision.json")
_PRE_REVIEW = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-pre-review.json"
)
_PRE_REVIEW_SHA256 = (
    "57365335a4b7b119bb4dec8f0ea857481bf2d8d80f1162e60f555a258276b815"
)
_REPLAY_IDENTITY = Path(
    "config/contracts/"
    "phase-5-public-owner-domain-cumulative-replay-identity-review.json"
)
_REPLAY_IDENTITY_SHA256 = (
    "0a464a387d5e742d213eb9045743e1356f5c9510b2409cdd10e6c0efc24534a0"
)
_REPLAY_DECISION = Path(
    "config/contracts/"
    "phase-5-public-owner-domain-cumulative-replay-execution-decision.json"
)
_REPLAY_DECISION_SHA256 = (
    "5662241eab2112f230009743145c2b8c6bfc5136852814d73baed5b00d26de1f"
)
_PROGRAM_PATHS = {
    "base_completion": (
        "scripts/validation/complete_phase5_final_cumulative_evaluation.py"
    ),
    "base_evaluator": (
        "scripts/validation/evaluate_phase5_final_cumulative_current.py"
    ),
    "completion": (
        "scripts/validation/"
        "complete_phase5_public_owner_domain_cumulative_evaluation.py"
    ),
    "evaluator": (
        "scripts/validation/evaluate_phase5_public_owner_domain_cumulative.py"
    ),
    "freezer": (
        "scripts/validation/"
        "freeze_phase5_public_owner_domain_cumulative_evaluation.py"
    ),
}
_FIXTURE_PATHS = {
    "base_final_evaluation": (
        "tests/unit/validation/test_final_cumulative_evaluation.py"
    ),
    "paired_evaluator": (
        "tests/unit/validation/test_prospective_paired_cumulative_replay.py"
    ),
    "public_owner_domain_evaluation": (
        "tests/unit/validation/"
        "test_public_owner_domain_cumulative_evaluation.py"
    ),
    "topology_tail": (
        "tests/unit/validation/"
        "test_prospective_paired_tail_diagnostic_repair.py"
    ),
}
_STANDING_AUTHORITY = (
    "I approve running the repaired development lane, the planned replay "
    "and final campaign required to verify and demonstrate scientific "
    "quality and pybdsf parity to close phase 5 as well as any bug fixes "
    "that are needed for this. Monitor long-running tasks hourly but prefer "
    "faster iterations where possible for catching and fixing bugs before "
    "starting longer replays and campaigns."
)


def _completion(root: Path) -> dict[str, Any]:
    """Load the exact scoped completion program."""
    return runpy.run_path(str(root / _PROGRAM_PATHS["completion"]))


def _bindings(root: Path, paths: dict[str, str]) -> dict[str, object]:
    """Hash every named repository file by exact bytes."""
    return {
        name: {"path": path, "sha256": file_sha256(root / path)}
        for name, path in sorted(paths.items())
    }


def _smoke_summary(
    completion: dict[str, Any], record: dict[str, object]
) -> dict[str, object]:
    """Retain the compact bounded terminal-path proof."""
    return cast(dict[str, object], completion["bounded_smoke_summary"](record))


def build_records(root: Path) -> tuple[dict[str, object], ...]:
    """Build the implementation, identity, and separated authority."""
    required = (
        (_PRE_REVIEW, _PRE_REVIEW_SHA256),
        (_REPLAY_IDENTITY, _REPLAY_IDENTITY_SHA256),
        (_REPLAY_DECISION, _REPLAY_DECISION_SHA256),
    )
    if any(file_sha256(root / path) != sha256 for path, sha256 in required):
        raise ValueError("public owner-domain evaluation provenance changed")
    completion = _completion(root)
    verified = completion["expected_verified_products"]()
    smoke = completion["expected_bounded_smoke"]()
    programs = _bindings(root, _PROGRAM_PATHS)
    fixtures = _bindings(root, _FIXTURE_PATHS)
    candidate = {
        "configuration_sha256": completion["_CURRENT_CONFIGURATION_SHA256"],
        "product_seal_sha256": completion["_CURRENT_PRODUCT_SEAL_SHA256"],
        "product_set_sha256": completion["_CURRENT_PRODUCT_SET_SHA256"],
        "revision": completion["_CURRENT_REVISION"],
        "source_tree_sha256": completion["_CURRENT_SOURCE_TREE_SHA256"],
    }
    implementation: dict[str, object] = {
        "implementation_id": f"{_PREFIX}-implementation-decision",
        "status": "implemented-and-bounded-smoke-passed-non-executable",
        "candidate": candidate,
        "incumbent": {
            "configuration_sha256": completion[
                "_INCUMBENT_CONFIGURATION_SHA256"
            ],
            "product_set_sha256": completion[
                "_INCUMBENT_EVALUATOR_PRODUCT_SET_SHA256"
            ],
            "revision": completion["_INCUMBENT_REVISION"],
            "source_tree_sha256": completion["_INCUMBENT_SOURCE_TREE_SHA256"],
        },
        "bounded_terminal_smoke": _smoke_summary(completion, smoke),
        "program_bindings": programs,
        "fixture_bindings": fixtures,
        "pre_review": {
            "path": str(_PRE_REVIEW),
            "sha256": _PRE_REVIEW_SHA256,
        },
        "replay": {
            "execution_decision": {
                "path": str(_REPLAY_DECISION),
                "sha256": _REPLAY_DECISION_SHA256,
            },
            "identity_review": {
                "path": str(_REPLAY_IDENTITY),
                "sha256": _REPLAY_IDENTITY_SHA256,
            },
        },
        "science_policy": {
            "absolute_objectives": "reported-non-binding",
            "aegean_parity_required": True,
            "binding_safety_required": True,
            "dual_pybdsf_parity_required": True,
            "incumbent_retention_required": True,
            "like_semantics_regression_allowed": False,
            "post_result_tuning_or_rescoring_allowed": False,
        },
        "execution_scope": {
            "candidate_executions": 0,
            "incumbent_executions": 0,
            "pybdsf_executions": 0,
            "retained_reference_runs": 9600,
            "write_once_output": str(completion["_OUTPUT"]),
        },
    }
    expected = completion["_expected_execution"](verified, smoke)
    identity: dict[str, object] = {
        "identity_review_id": f"{_PREFIX}-identity-review",
        "status": "frozen-non-executable",
        "authorization": dict.fromkeys(completion["_AUTHORIZATION"], False),
        "implementation": {
            "path": str(_IMPLEMENTATION),
            "sha256": canonical_sha256(implementation),
        },
        "program_bindings": programs,
        "fixture_bindings": fixtures,
        "verified_products": verified,
        "bounded_terminal_smoke": _smoke_summary(completion, smoke),
        "expected_execution": expected,
        "expected_execution_sha256": canonical_sha256(expected),
    }
    decision: dict[str, object] = {
        "decision_id": f"{_PREFIX}-execution-decision",
        "status": "authorized-for-one-final-cumulative-evaluation",
        "authorization": dict(completion["_AUTHORIZATION"]),
        "authority_source": {
            "standing_user_authority": _STANDING_AUTHORITY,
            "user_instruction": (
                "2026-09-05 continue with the next task after the successful "
                "public owner-domain cumulative product seal"
            ),
        },
        "identity_review": {
            "path": str(_IDENTITY),
            "sha256": canonical_sha256(identity),
        },
        "identity_review_sha256": canonical_sha256(identity),
        "expected_execution_sha256": canonical_sha256(expected),
        "result_policy": {
            "scientific_failure_is_terminal": True,
            "threshold_or_margin_change_after_results": False,
            "write_once": True,
        },
    }
    return implementation, identity, decision


def _write(path: Path, record: dict[str, object]) -> None:
    """Write one canonical JSON record without overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, allow_nan=False, indent=2, sort_keys=True)
        stream.write("\n")


def freeze_records(arguments: argparse.Namespace) -> None:
    """Freeze all three records into one fresh output root."""
    root = arguments.repository_root.resolve()
    output_root = arguments.output_root.resolve()
    implementation, identity, decision = build_records(root)
    for relative, record in (
        (_IMPLEMENTATION, implementation),
        (_IDENTITY, identity),
        (_DECISION, decision),
    ):
        target = output_root / relative
        if target.exists():
            raise FileExistsError(f"refusing to overwrite {target}")
        _write(target, record)


def _parse_args() -> argparse.Namespace:
    """Parse source and output repository roots."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument("--output-root", type=Path, default=_ROOT)
    return parser.parse_args()


if __name__ == "__main__":
    freeze_records(_parse_args())
