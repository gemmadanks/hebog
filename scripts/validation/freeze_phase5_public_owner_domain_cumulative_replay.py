#!/usr/bin/env python3
"""Freeze the version-8 public cumulative candidate-stage identities."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_PREFIX = "phase-5-public-owner-domain-cumulative-replay"
_IMPLEMENTATION = Path(
    f"config/contracts/{_PREFIX}-implementation-decision.json"
)
_IDENTITY = Path(f"config/contracts/{_PREFIX}-identity-review.json")
_DECISION = Path(f"config/contracts/{_PREFIX}-execution-decision.json")
_EXACT_AUTHORITY = (
    "I approve running the repaired development lane, the planned replay "
    "and final campaign required to verify and demonstrate scientific "
    "quality and pybdsf parity to close phase 5 as well as any bug fixes "
    "that are needed for this. Monitor long-running tasks hourly but prefer "
    "faster iterations where possible for catching and fixing bugs before "
    "starting longer replays and campaigns."
)


def _runner() -> Any:
    """Load the scoped version-8 cumulative runner."""
    return importlib.import_module(
        "scripts.validation.run_phase5_public_owner_domain_cumulative_replay"
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


def _configured_records() -> dict[str, Any]:
    """Snapshot all exact inherited and version-8 execution bindings."""
    runner = _runner()
    with runner._configured_runner() as configured:
        base = configured["base"]
        validated = configured["validated"]
        return {
            "authorization": copy.deepcopy(base._EXPECTED_AUTHORIZATION),
            "candidate": copy.deepcopy(runner._CANDIDATE),
            "expected_execution": copy.deepcopy(base._expected_execution()),
            "fixture_paths": copy.deepcopy(validated._FIXTURE_PATHS),
            "program_paths": copy.deepcopy(validated._PROGRAM_PATHS),
            "process_reviews": {
                "json_format_review": {
                    "path": str(validated._JSON_FORMAT_REVIEW),
                    "sha256": runner._JSON_FORMAT_REVIEW_SHA256,
                },
                "process_review": {
                    "path": str(validated._PROCESS_REVIEW),
                    "sha256": runner._PROCESS_REVIEW_SHA256,
                },
                "single_scan_review": {
                    "path": str(validated._SINGLE_SCAN_REVIEW),
                    "sha256": runner._SINGLE_SCAN_REVIEW_SHA256,
                },
                "type_clean_review": {
                    "path": str(validated._TYPE_CLEAN_REVIEW),
                    "sha256": runner._TYPE_CLEAN_REVIEW_SHA256,
                },
            },
            "retained_evidence": {
                "closed_baseline": {
                    "path": str(base._CLOSED_BASELINE),
                    "sha256": base._CLOSED_BASELINE_SHA256,
                },
                "incumbent_reconstruction": {
                    "path": str(base._INCUMBENT_RECONSTRUCTION),
                    "sha256": base._INCUMBENT_RECONSTRUCTION_SHA256,
                },
                "population": {
                    "path": str(base._POPULATION),
                    "sha256": base._POPULATION_SHA256,
                },
                "reference_reconstruction": {
                    "path": str(
                        base._REFERENCE_RECONSTRUCTION / "recovery.json"
                    ),
                    "sha256": base._REFERENCE_RECONSTRUCTION_SHA256,
                },
                "source_request": {
                    "path": str(base._SOURCE_REQUEST),
                    "sha256": base._SOURCE_REQUEST_SHA256,
                },
            },
        }


def _verify_inputs(root: Path, records: dict[str, Any]) -> None:
    """Require the passing fast lane and every retained evidence byte."""
    runner = _runner()
    if source_tree_sha256(root) != runner._CANDIDATE["source_tree_sha256"]:
        raise ValueError("public owner-domain cumulative source changed")
    with runner._configured_runner() as configured:
        configured["base"]._verify_static_evidence(root)
    for review in cast(
        dict[str, dict[str, str]], records["process_reviews"]
    ).values():
        if file_sha256(root / review["path"]) != review["sha256"]:
            raise ValueError("public owner-domain process review changed")


def build_implementation(
    root: Path, records: dict[str, Any]
) -> dict[str, object]:
    """Record the exact reusable single-scan composition."""
    runner = _runner()
    return {
        "authorization": {
            "candidate_execution_authorized": False,
            "implementation_authorized": True,
            "evaluation_authorized": False,
            "pybdsf_execution_authorized": False,
            "release_authorized": False,
        },
        "candidate": copy.deepcopy(records["candidate"]),
        "decision_id": f"{_PREFIX}-implementation-decision",
        "fast_terminal": {
            "path": str(runner._FAST_TERMINAL),
            "sha256": runner._FAST_TERMINAL_SHA256,
            "status": "pass",
        },
        "implemented_contracts": [
            "reuse the proven one-scan 2400-product candidate runner",
            "bind the exact version-8 public source identity",
            "reuse all 9600 retained PyBDSF reference runs without execution",
            "reuse the authentic incumbent and closed baseline identities",
            "verify every task and retained input before creating scratch",
            "rehash every product before one atomic write-once seal",
        ],
        "process_reviews": copy.deepcopy(records["process_reviews"]),
        "program_bindings": _bindings(root, records["program_paths"]),
        "retained_evidence": copy.deepcopy(records["retained_evidence"]),
        "schema_version": 1,
        "status": "implemented-and-preflightable-non-executable",
    }


def build_identity(
    root: Path,
    records: dict[str, Any],
    implementation: dict[str, object],
) -> dict[str, object]:
    """Freeze the exact non-executable version-8 candidate stage."""
    runner = _runner()
    expected = cast(dict[str, object], records["expected_execution"])
    reviews = cast(dict[str, object], records["process_reviews"])
    return {
        "authorization": dict.fromkeys(records["authorization"], False),
        "candidate": copy.deepcopy(records["candidate"]),
        "expected_execution": copy.deepcopy(expected),
        "expected_execution_sha256": canonical_sha256(expected),
        "fast_terminal": {
            "path": str(runner._FAST_TERMINAL),
            "sha256": runner._FAST_TERMINAL_SHA256,
            "status": "pass",
        },
        "fixture_bindings": _bindings(root, records["fixture_paths"]),
        "identity_review_id": f"{_PREFIX}-identity-review",
        "implementation": {
            "path": str(_IMPLEMENTATION),
            "sha256": _document_sha256(implementation),
        },
        **copy.deepcopy(reviews),
        "program_bindings": _bindings(root, records["program_paths"]),
        "required_next_decision": (
            "consume only the separately frozen one-use version-8 "
            "candidate-stage decision"
        ),
        "retained_evidence": copy.deepcopy(records["retained_evidence"]),
        "schema_version": 1,
        "status": "frozen-non-executable",
    }


def build_decision(
    records: dict[str, Any], identity: dict[str, object]
) -> dict[str, object]:
    """Bind standing replay authority to exactly one candidate stage."""
    reviews = cast(dict[str, dict[str, str]], records["process_reviews"])
    return {
        "authorization": copy.deepcopy(records["authorization"]),
        "authorization_record": {
            "approved_on": "2026-09-05",
            "statement": _EXACT_AUTHORITY,
        },
        "candidate": copy.deepcopy(records["candidate"]),
        "decision_id": f"{_PREFIX}-execution-decision",
        "expected_execution_sha256": identity["expected_execution_sha256"],
        "identity_review_sha256": _document_sha256(identity),
        "json_format_review_sha256": reviews["json_format_review"]["sha256"],
        "post_execution": (
            "freeze exact product-set identity before evaluation-only "
            "compilation"
        ),
        "process_review_sha256": reviews["process_review"]["sha256"],
        "schema_version": 1,
        "single_scan_review_sha256": reviews["single_scan_review"]["sha256"],
        "status": ("authorized-for-one-public-owner-domain-cumulative-replay"),
        "type_clean_review_sha256": reviews["type_clean_review"]["sha256"],
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
    records = _configured_records()
    _verify_inputs(root, records)
    implementation = build_implementation(root, records)
    identity = build_identity(root, records, implementation)
    decision = build_decision(records, identity)
    documents = (
        (_IMPLEMENTATION, implementation),
        (_IDENTITY, identity),
        (_DECISION, decision),
    )
    destinations = tuple(arguments.output_root / path for path, _ in documents)
    if any(path.exists() for path in destinations):
        raise FileExistsError("refusing to overwrite cumulative records")
    for destination, (_, document) in zip(
        destinations, documents, strict=True
    ):
        _write_once(destination, document)
    for path, document in documents:
        print(f"{path.name}_sha256={_document_sha256(document)}")


def _parse_args() -> argparse.Namespace:
    """Parse deterministic freezer paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Freeze the exact version-8 cumulative candidate identities."""
    freeze_records(_parse_args())


if __name__ == "__main__":
    main()
