#!/usr/bin/env python3
"""Freeze the non-executable process-only repair lane identity."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import runpy
from pathlib import Path
from typing import Any, cast

from hebog.validation.adaptive_background_lane import (
    build_adaptive_runtime_identity,
)
from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)

_PREDECESSOR_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "identity-review.json"
)
_PREDECESSOR_IDENTITY_SHA256 = (
    "4c611f1b61113584512f45650ef41e468237c59413b7464a7070cd7bce0e4944"
)
_FAILED_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "execution-decision.json"
)
_FAILED_EXECUTION_DECISION_SHA256 = (
    "c169bb85ba39d8fa0092e4315738514e0e47d05920b39dde49f8c857006f412d"
)
_PROCESS_REPAIR_REVIEW = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "process-repair-pre-review.json"
)
_PROCESS_REPAIR_REVIEW_SHA256 = (
    "c35c6eecb32141e88d1cec8fa501bfeddc5b7d2b8a680b99188957e454e886a4"
)
_RUNNER = Path(
    "scripts/validation/run_phase5_source_owned_measurement_topology.py"
)
_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "process-repair-identity-review.json"
)
_FAILED_SCRATCH = Path(
    "/private/tmp/hebog-phase5-source-owned-measurement-topology-c28343f"
)
_FAILED_NAMESPACE_SHA256 = (
    "08acc8726c191bc8ddb7deae139735282d6146c524625680a1fdbf7f3c739f0d"
)
_EMPTY_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "8235e9bcca0e184d1a1597a3dce1f91e9389795370b61f68734b3ee5002b220f"
)


def _json_object(path: Path) -> dict[str, Any]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"required identity must be a JSON object: {path}")
    return cast(dict[str, Any], value)


def _json_bytes(value: object) -> bytes:
    """Return one canonical checked-in JSON document."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _document_sha256(value: object) -> str:
    """Hash one canonical checked-in JSON document."""
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _verify_inputs(root: Path) -> None:
    """Verify the immutable predecessor, failed decision, and repair review."""
    expected = (
        (_PREDECESSOR_IDENTITY, _PREDECESSOR_IDENTITY_SHA256),
        (_FAILED_EXECUTION_DECISION, _FAILED_EXECUTION_DECISION_SHA256),
        (_PROCESS_REPAIR_REVIEW, _PROCESS_REPAIR_REVIEW_SHA256),
    )
    for path, sha256 in expected:
        if file_sha256(root / path) != sha256:
            raise ValueError(f"process-repair input changed: {path}")
    if source_tree_sha256(root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("process repair changed the scientific source tree")


def _verify_preserved_failure() -> None:
    """Require the exact zero-product failed namespace to remain preserved."""
    files = tuple(
        path for path in sorted(_FAILED_SCRATCH.rglob("*")) if path.is_file()
    )
    if files != (_FAILED_SCRATCH / "progress.log",):
        raise ValueError("failed process namespace file set changed")
    progress = files[0]
    record = (
        {
            "path": "progress.log",
            "sha256": file_sha256(progress),
            "size_bytes": progress.stat().st_size,
        },
    )
    if (
        record[0]["sha256"] != _EMPTY_SHA256
        or record[0]["size_bytes"] != 0
        or canonical_sha256(record) != _FAILED_NAMESPACE_SHA256
    ):
        raise ValueError("failed process namespace identity changed")


def build_identity(root: Path) -> dict[str, object]:
    """Build the process-repaired successor without granting execution."""
    _verify_inputs(root)
    runner = runpy.run_path(str(root / _RUNNER))
    identity = copy.deepcopy(_json_object(root / _PREDECESSOR_IDENTITY))
    program_paths = cast(dict[str, str], runner["_PROGRAM_BINDING_PATHS"])
    fixture_paths = cast(dict[str, str], runner["_FIXTURE_BINDING_PATHS"])
    expected_execution = cast(
        dict[str, object],
        runner["_expected_execution"](),
    )
    identity.update(
        {
            "authorization": dict.fromkeys(
                cast(dict[str, object], identity["authorization"]),
                False,
            ),
            "expected_execution": expected_execution,
            "expected_execution_sha256": canonical_sha256(expected_execution),
            "fixture_bindings": {
                name: {
                    "path": path,
                    "sha256": file_sha256(root / path),
                }
                for name, path in sorted(fixture_paths.items())
            },
            "identity_review_id": (
                "phase-5-source-owned-measurement-topology-"
                "process-repair-identity-review"
            ),
            "predecessor_identity": {
                "path": str(_PREDECESSOR_IDENTITY),
                "sha256": _PREDECESSOR_IDENTITY_SHA256,
            },
            "process_repair": {
                "failed_execution": {
                    "candidate_execution_count": 0,
                    "coarse_control_execution_count": 0,
                    "decision": {
                        "path": str(_FAILED_EXECUTION_DECISION),
                        "sha256": _FAILED_EXECUTION_DECISION_SHA256,
                    },
                    "execution_commit": (
                        "fd04cefece32b885d2a155743d29c3cf642d965c"
                    ),
                    "namespace_file_set_sha256": (_FAILED_NAMESPACE_SHA256),
                    "output_published": False,
                    "progress_record_count": 0,
                    "scratch": str(_FAILED_SCRATCH),
                },
                "repair_contract": (
                    "submit only built-in JSON-compatible task mappings and "
                    "reconstruct validated records inside each process worker"
                ),
                "review": {
                    "path": str(_PROCESS_REPAIR_REVIEW),
                    "sha256": _PROCESS_REPAIR_REVIEW_SHA256,
                },
            },
            "program_bindings": {
                name: {
                    "path": path,
                    "sha256": file_sha256(root / path),
                }
                for name, path in sorted(program_paths.items())
            },
            "required_next_decision": (
                "obtain a new exact one-use approval bound to this repaired "
                "identity and expected execution before retrying the lane"
            ),
            "runtime": build_adaptive_runtime_identity(root),
            "status": "frozen-non-executable",
        }
    )
    execution_contract = cast(
        dict[str, object], identity["execution_contract"]
    )
    execution_contract["scratch"] = expected_execution["scratch"]
    return cast(dict[str, object], identity)


def freeze_identity(arguments: argparse.Namespace) -> None:
    """Verify the failure and write one non-executable successor once."""
    root = arguments.repository_root.resolve()
    output_root = arguments.output_root.resolve()
    destination = output_root / _IDENTITY
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite process-repair identity: {destination}"
        )
    _verify_preserved_failure()
    identity = build_identity(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(_json_bytes(identity))
    print(f"{_IDENTITY.name}_sha256={_document_sha256(identity)}")


def main() -> None:
    """Parse explicit roots and freeze the repaired identity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    freeze_identity(parser.parse_args())


if __name__ == "__main__":
    main()
