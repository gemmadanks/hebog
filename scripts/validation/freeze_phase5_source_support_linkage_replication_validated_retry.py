#!/usr/bin/env python3
"""Freeze the validation-clean source-linkage replication retry."""

# pyright: reportPrivateUsage=false
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
    "config/contracts/phase-5-source-support-linkage-replication-"
    "binding-repair-identity-review.json"
)
_PREDECESSOR_IDENTITY_SHA256 = (
    "25fbd5c333a93d58adfaf819c30d1f5bb1f9e43d4d33a9d83df4b4d923066449"
)
_PREDECESSOR_DECISION = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "binding-repair-execution-decision.json"
)
_PREDECESSOR_DECISION_SHA256 = (
    "44cdea3d828607db4231372dec4c98bf87eb82953db3fd73033a3624aa1acb73"
)
_PREDECESSOR_IMPLEMENTATION = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "binding-repair-implementation-decision.json"
)
_PREDECESSOR_IMPLEMENTATION_SHA256 = (
    "79154f76e23a1e4ef669a7c6806aa29a3ef81a5e603f0cda330f7fa9ccc2e50a"
)
_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "public-interface-identity-review.json"
)
_PUBLIC_IDENTITY_SHA256 = (
    "7b6fd62327ba72f66189020fbca6535ecb853c24006aae460b0e67137034d3cd"
)
_MANIFEST = Path(
    "config/contracts/phase-5-source-support-linkage-replication-manifest.json"
)
_MANIFEST_SHA256 = (
    "8d5394770e592ad925201bdead76bd6821986d19473935bcf54c61466e1a7cb9"
)
_REPAIR_REVIEW = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "binding-repair-pre-review.json"
)
_REPAIR_REVIEW_SHA256 = (
    "d8163967a876ccaed188d9bcfe2c536d2642e3cba99ff573e7d26197d7e8a974"
)
_RUNNER = Path(
    "scripts/validation/run_phase5_source_support_linkage_replication.py"
)
_IMPLEMENTATION = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "validated-retry-implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "validated-retry-identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "validated-retry-execution-decision.json"
)
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "11307db0059739d473288dd2ed647970cce43b69e874632e1d1f14ee0ed032df"
)
_EXACT_AUTHORITY = (
    "I approve running the repaired development lane, the planned replay "
    "and final campaign required to verify and demonstrate scientific "
    "quality and pybdsf parity to close phase 5 as well as any bug fixes "
    "that are needed for this. Monitor long-running tasks hourly but prefer "
    "faster iterations where possible for catching and fixing bugs before "
    "starting longer replays and campaigns."
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
    """Require the exact validated predecessor and unchanged science."""
    for path, expected in (
        (_PREDECESSOR_IDENTITY, _PREDECESSOR_IDENTITY_SHA256),
        (_PREDECESSOR_DECISION, _PREDECESSOR_DECISION_SHA256),
        (
            _PREDECESSOR_IMPLEMENTATION,
            _PREDECESSOR_IMPLEMENTATION_SHA256,
        ),
        (_PUBLIC_IDENTITY, _PUBLIC_IDENTITY_SHA256),
        (_MANIFEST, _MANIFEST_SHA256),
        (_REPAIR_REVIEW, _REPAIR_REVIEW_SHA256),
    ):
        if file_sha256(root / path) != expected:
            raise ValueError(f"validated-retry input changed: {path}")
    if source_tree_sha256(root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("validated retry changed candidate science")


def _runner_records(
    root: Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, object]]:
    """Load exact bindings and execution shape from the final runner."""
    runner = runpy.run_path(str(root / _RUNNER))
    return (
        cast(dict[str, str], runner["_PROGRAM_BINDING_PATHS"]),
        cast(dict[str, str], runner["_FIXTURE_BINDING_PATHS"]),
        cast(dict[str, object], runner["_expected_execution"]()),
    )


def _bindings(root: Path, paths: dict[str, str]) -> dict[str, object]:
    """Bind every declared repository file by digest."""
    return {
        name: {"path": path, "sha256": file_sha256(root / path)}
        for name, path in sorted(paths.items())
    }


def build_implementation(root: Path) -> dict[str, object]:
    """Bind the fully formatted, lint-clean retry programs."""
    implementation = copy.deepcopy(
        _json_object(root / _PREDECESSOR_IMPLEMENTATION)
    )
    programs, fixtures, _ = _runner_records(root)
    implementation.update(
        {
            "decision_id": (
                "phase-5-source-support-linkage-replication-validated-retry-"
                "implementation-decision"
            ),
            "fixture_bindings": _bindings(root, fixtures),
            "implemented_contracts": [
                "stable-module spawned-process composition is retained",
                "all overlay identity and process-review globals are bound",
                "all bound programs are Ruff-formatted and lint-clean",
                (
                    "candidate algorithms, configuration, population, "
                    "seeds, metrics, margins, and final comparator gates are "
                    "unchanged"
                ),
            ],
            "program_bindings": _bindings(root, programs),
            "public_identity": {
                "path": str(_PUBLIC_IDENTITY),
                "sha256": _PUBLIC_IDENTITY_SHA256,
            },
            "status": "implemented-and-preflight-validated-non-executable",
        }
    )
    return cast(dict[str, object], implementation)


def build_identity(
    root: Path,
    implementation: dict[str, object],
) -> dict[str, object]:
    """Freeze the exact validation-clean retry without execution authority."""
    identity = copy.deepcopy(_json_object(root / _PREDECESSOR_IDENTITY))
    programs, fixtures, expected_execution = _runner_records(root)
    identity.update(
        {
            "authorization": dict.fromkeys(
                cast(dict[str, object], identity["authorization"]), False
            ),
            "expected_execution": expected_execution,
            "expected_execution_sha256": canonical_sha256(expected_execution),
            "fixture_bindings": _bindings(root, fixtures),
            "identity_review_id": (
                "phase-5-source-support-linkage-replication-validated-retry-"
                "identity-review"
            ),
            "implementation_decision": {
                "path": str(_IMPLEMENTATION),
                "sha256": _document_sha256(implementation),
            },
            "predecessor_identity": {
                "path": str(_PREDECESSOR_IDENTITY),
                "sha256": _PREDECESSOR_IDENTITY_SHA256,
            },
            "process_repair": {
                "repair_contract": (
                    "retain import and complete-binding repairs in final "
                    "formatted programs"
                ),
                "review": {
                    "path": str(_REPAIR_REVIEW),
                    "sha256": _REPAIR_REVIEW_SHA256,
                },
                "superseded_identity": {
                    "decision": {
                        "path": str(_PREDECESSOR_DECISION),
                        "sha256": _PREDECESSOR_DECISION_SHA256,
                    },
                    "execution_started": False,
                    "reason": "bound freezer required lint-only formatting",
                },
            },
            "program_bindings": _bindings(root, programs),
            "required_next_decision": (
                "consume only the separately verified one-use validated-retry "
                "execution decision"
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


def build_execution_decision(
    root: Path,
    identity: dict[str, object],
) -> dict[str, object]:
    """Bind the user's authority to the validation-clean fast lane."""
    runner = runpy.run_path(str(root / _RUNNER))
    expected_execution = cast(
        dict[str, object], identity["expected_execution"]
    )
    identity_sha256 = _document_sha256(identity)
    return {
        "authorization": copy.deepcopy(
            cast(
                dict[str, object],
                runner["_EXPECTED_EXECUTION_AUTHORIZATION"],
            )
        ),
        "authorization_record": {
            "approved_on": "2026-09-05",
            "statement": _EXACT_AUTHORITY,
        },
        "candidate": copy.deepcopy(identity["candidate"]),
        "decision_id": (
            "phase-5-source-support-linkage-replication-validated-retry-"
            "execution-decision"
        ),
        "downstream_authority": {
            "sequence": [
                "cumulative dual-PyBDSF replay",
                "fresh held-out dual-PyBDSF qualification",
            ],
            "status": (
                "approved-in-principle-pending-passing-fast-lane-and-frozen-"
                "exact-identities"
            ),
        },
        "expected_execution_sha256": canonical_sha256(expected_execution),
        "identity_review": {
            "path": str(_IDENTITY),
            "sha256": identity_sha256,
        },
        "identity_review_sha256": identity_sha256,
        "output": expected_execution["output"],
        "process_repair_review": {
            "path": str(_REPAIR_REVIEW),
            "sha256": _REPAIR_REVIEW_SHA256,
        },
        "schema_version": 1,
        "status": "authorized-for-one-development-lane",
        "workers": 2,
        "wrapper_sha256": file_sha256(root / _RUNNER),
    }


def _write_once(path: Path, value: object) -> None:
    """Write one canonical JSON record without overwriting evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(_json_bytes(value))


def freeze_records(arguments: argparse.Namespace) -> None:
    """Verify the predecessor and freeze the validation-clean retry."""
    root = arguments.repository_root.resolve()
    output_root = arguments.output_root.resolve()
    _verify_inputs(root)
    implementation = build_implementation(root)
    identity = build_identity(root, implementation)
    decision = build_execution_decision(root, identity)
    documents = (
        (_IMPLEMENTATION, implementation),
        (_IDENTITY, identity),
        (_EXECUTION_DECISION, decision),
    )
    destinations = tuple(output_root / path for path, _ in documents)
    if any(path.exists() for path in destinations):
        raise FileExistsError(
            "refusing to overwrite validated replication retry records"
        )
    for destination, (_, document) in zip(
        destinations,
        documents,
        strict=True,
    ):
        _write_once(destination, document)
    for path, document in documents:
        print(f"{path.name}_sha256={_document_sha256(document)}")


def main() -> None:
    """Parse roots and freeze the validation-clean retry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    freeze_records(parser.parse_args())


if __name__ == "__main__":
    main()
