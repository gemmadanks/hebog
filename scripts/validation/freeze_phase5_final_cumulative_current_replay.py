#!/usr/bin/env python3
"""Freeze exact identities for the final cumulative current replay."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_PREFIX = "phase-5-final-cumulative-current-replay"
_PRE_REVIEW = Path(f"config/contracts/{_PREFIX}-pre-review.json")
_IMPLEMENTATION = Path(
    f"config/contracts/{_PREFIX}-implementation-decision.json"
)
_IDENTITY = Path(f"config/contracts/{_PREFIX}-identity-review.json")
_DECISION = Path(f"config/contracts/{_PREFIX}-execution-decision.json")
_PRE_REVIEW_SHA256 = (
    "57365335a4b7b119bb4dec8f0ea857481bf2d8d80f1162e60f555a258276b815"
)
_EXACT_AUTHORITY = (
    "I approve running the repaired development lane, the planned replay "
    "and final campaign required to verify and demonstrate scientific "
    "quality and pybdsf parity to close phase 5 as well as any bug fixes "
    "that are needed for this. Monitor long-running tasks hourly but prefer "
    "faster iterations where possible for catching and fixing bugs before "
    "starting longer replays and campaigns."
)


def _runner() -> Any:
    """Load the exact process-safe candidate runner."""
    return importlib.import_module(
        "scripts.validation.run_phase5_final_cumulative_current_replay"
    )


def _json_bytes(value: object) -> bytes:
    """Return one canonical checked-in JSON document."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _document_sha256(value: object) -> str:
    """Hash one canonical checked-in JSON document."""
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _bindings(root: Path, paths: dict[str, str]) -> dict[str, object]:
    """Bind every named repository file by exact bytes."""
    return {
        name: {"path": path, "sha256": file_sha256(root / path)}
        for name, path in sorted(paths.items())
    }


def build_implementation(root: Path) -> dict[str, object]:
    """Record the minimal current-only replay composition."""
    runner = _runner()
    return {
        "authorization": {
            "implementation_authorized": True,
            "candidate_execution_authorized": False,
            "evaluation_authorized": False,
            "pybdsf_execution_authorized": False,
            "release_authorized": False,
        },
        "candidate": {
            "configuration_sha256": runner._CANDIDATE_CONFIGURATION_SHA256,
            "revision": runner._CANDIDATE_REVISION,
            "source_tree_sha256": runner._CANDIDATE_SOURCE_TREE_SHA256,
        },
        "decision_id": f"{_PREFIX}-implementation-decision",
        "implemented_contracts": [
            (
                "current candidate only; retained incumbent and PyBDSF "
                "products are not executed"
            ),
            "complete task and reference no-write verification",
            "real spawned-process import seam before execution",
            "write-once scratch followed by complete product rehash",
            "one atomic product-set seal before scientific evaluation",
        ],
        "pre_review": {
            "path": str(_PRE_REVIEW),
            "sha256": _PRE_REVIEW_SHA256,
        },
        "program_bindings": _bindings(root, runner._PROGRAM_PATHS),
        "status": "implemented-and-preflightable-non-executable",
    }


def build_identity(
    root: Path, implementation: dict[str, object]
) -> dict[str, object]:
    """Freeze the exact non-executable candidate stage."""
    runner = _runner()
    expected = runner._expected_execution()
    return {
        "authorization": dict.fromkeys(runner._EXPECTED_AUTHORIZATION, False),
        "candidate": copy.deepcopy(implementation["candidate"]),
        "expected_execution": expected,
        "expected_execution_sha256": canonical_sha256(expected),
        "fixture_bindings": _bindings(root, runner._FIXTURE_PATHS),
        "identity_review_id": f"{_PREFIX}-identity-review",
        "implementation": {
            "path": str(_IMPLEMENTATION),
            "sha256": _document_sha256(implementation),
        },
        "pre_review": {
            "path": str(_PRE_REVIEW),
            "sha256": _PRE_REVIEW_SHA256,
        },
        "program_bindings": _bindings(root, runner._PROGRAM_PATHS),
        "required_next_decision": (
            "consume only the separately frozen one-use candidate replay "
            "decision"
        ),
        "status": "frozen-non-executable",
    }


def build_decision(
    identity: dict[str, object],
) -> dict[str, object]:
    """Bind the user's authority to one current-only cumulative run."""
    runner = _runner()
    return {
        "authorization": copy.deepcopy(runner._EXPECTED_AUTHORIZATION),
        "authorization_record": {
            "approved_on": "2026-09-05",
            "statement": _EXACT_AUTHORITY,
        },
        "candidate": copy.deepcopy(identity["candidate"]),
        "decision_id": f"{_PREFIX}-execution-decision",
        "expected_execution_sha256": identity["expected_execution_sha256"],
        "identity_review_sha256": _document_sha256(identity),
        "post_execution": (
            "freeze exact product-set identity before evaluation-only "
            "compilation"
        ),
        "status": "authorized-for-one-final-cumulative-current-replay",
    }


def _write_once(path: Path, value: object) -> None:
    """Create one canonical record without overwriting evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(_json_bytes(value))
    except FileExistsError as error:
        raise FileExistsError(f"refusing to overwrite {path}") from error


def freeze_records(arguments: argparse.Namespace) -> None:
    """Verify inputs and freeze implementation, identity, and authority."""
    root = arguments.repository_root.resolve()
    if file_sha256(root / _PRE_REVIEW) != _PRE_REVIEW_SHA256:
        raise ValueError("final cumulative pre-review changed")
    implementation = build_implementation(root)
    identity = build_identity(root, implementation)
    decision = build_decision(identity)
    for relative, value in (
        (_IMPLEMENTATION, implementation),
        (_IDENTITY, identity),
        (_DECISION, decision),
    ):
        _write_once(arguments.output_root / relative, value)


def _parse_args() -> argparse.Namespace:
    """Parse deterministic freezer paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Freeze the exact current-candidate replay identities."""
    freeze_records(_parse_args())


if __name__ == "__main__":
    main()
