#!/usr/bin/env python3
"""Freeze the Phase 5 version-8 public fast regression lane."""

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
    "validated-retry-identity-review.json"
)
_PREDECESSOR_IDENTITY_SHA256 = (
    "6289b9cecbd956e25e3054f2e52b9d7837f8bbf78e3050d09e93b737ec1915cc"
)
_PREDECESSOR_TERMINAL_SHA256 = (
    "0978d4a3653ce9bd4b1244ea1125142400607d04c330758ee3b4a495f4193eae"
)
_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-public-publication-owner-domain-"
    "identity-review.json"
)
_PUBLIC_IDENTITY_SHA256 = (
    "2920873aa430086d8b12a2092ac7f70bb59dc756c3a70b03db7e7f0708fb0611"
)
_RUNNER = Path(
    "scripts/validation/run_phase5_public_owner_domain_fast_lane.py"
)
_IMPLEMENTATION = Path(
    "config/contracts/phase-5-public-owner-domain-fast-lane-"
    "implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-public-owner-domain-fast-lane-"
    "identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-public-owner-domain-fast-lane-"
    "execution-decision.json"
)
_CANDIDATE_REVISION = "95cfc76ded56556dc3ad6894410962d34f0d5604"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
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


def _runner_records(
    root: Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, object]]:
    """Load exact bindings and execution shape from the lane runner."""
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


def _candidate() -> dict[str, str]:
    """Return the exact public candidate identity."""
    return {
        "configuration_sha256": (
            "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
        ),
        "entrypoint": "hebog.find_sources",
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
    }


def _verify_inputs(root: Path) -> None:
    """Require the successful predecessor and current public candidate."""
    if file_sha256(root / _PREDECESSOR_IDENTITY) != (
        _PREDECESSOR_IDENTITY_SHA256
    ):
        raise ValueError("public fast-lane predecessor identity changed")
    if file_sha256(root / _PUBLIC_IDENTITY) != _PUBLIC_IDENTITY_SHA256:
        raise ValueError("public fast-lane public identity changed")
    if source_tree_sha256(root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("public fast lane changed candidate science")


def build_implementation(root: Path) -> dict[str, object]:
    """Bind the exact current programs and fixture evidence."""
    programs, fixtures, _ = _runner_records(root)
    return {
        "candidate": _candidate(),
        "decision_id": (
            "phase-5-public-owner-domain-fast-lane-implementation-decision"
        ),
        "fixture_bindings": _bindings(root, fixtures),
        "implemented_contracts": [
            "reuse the passed seed-disjoint 144-case fast protocol",
            "bind the version-8 component and publication-owner corrections",
            "retain paired cell-median gates and non-binding tail diagnostics",
            "retain exact Serial and caller-owned-Dask invariance",
        ],
        "predecessor_fast_lane": {
            "identity": {
                "path": str(_PREDECESSOR_IDENTITY),
                "sha256": _PREDECESSOR_IDENTITY_SHA256,
            },
            "terminal_sha256": _PREDECESSOR_TERMINAL_SHA256,
            "status": "pass",
        },
        "program_bindings": _bindings(root, programs),
        "public_identity": {
            "path": str(_PUBLIC_IDENTITY),
            "sha256": _PUBLIC_IDENTITY_SHA256,
        },
        "schema_version": 1,
        "status": "implemented-and-preflight-validated-non-executable",
    }


def build_identity(
    root: Path,
    implementation: dict[str, object],
) -> dict[str, object]:
    """Freeze the exact current fast lane without execution authority."""
    predecessor = copy.deepcopy(_json_object(root / _PREDECESSOR_IDENTITY))
    programs, fixtures, expected_execution = _runner_records(root)
    predecessor.update(
        {
            "authorization": dict.fromkeys(
                cast(dict[str, object], predecessor["authorization"]), False
            ),
            "candidate": _candidate(),
            "execution_contract": {
                "atomic_output": expected_execution["output"],
                "attribution": "array-free-non-binding-per-input-record-v3",
                "candidate_executions": 144,
                "coarse_control_executions": 144,
                "existing_dask_executions": 12,
                "existing_dask_policy": (
                    "caller-owned scheduler address; runner creates no cluster"
                ),
                "output_policy": "one atomic write; never overwrite or rerun",
                "required_workers": 2,
                "scratch": expected_execution["scratch"],
                "total_finder_executions": 300,
            },
            "expected_execution": expected_execution,
            "expected_execution_sha256": canonical_sha256(expected_execution),
            "fixture_bindings": _bindings(root, fixtures),
            "identity_review_id": (
                "phase-5-public-owner-domain-fast-lane-identity-review"
            ),
            "implementation_decision": {
                "path": str(_IMPLEMENTATION),
                "sha256": _document_sha256(implementation),
            },
            "predecessor_fast_lane": {
                "identity": {
                    "path": str(_PREDECESSOR_IDENTITY),
                    "sha256": _PREDECESSOR_IDENTITY_SHA256,
                },
                "terminal_sha256": _PREDECESSOR_TERMINAL_SHA256,
                "status": "pass",
            },
            "program_bindings": _bindings(root, programs),
            "public_identity": {
                "path": str(_PUBLIC_IDENTITY),
                "sha256": _PUBLIC_IDENTITY_SHA256,
            },
            "required_next_decision": (
                "consume only the separately verified one-use version-8 "
                "fast-lane execution decision"
            ),
            "runtime": build_adaptive_runtime_identity(root),
            "status": "frozen-non-executable",
        }
    )
    return cast(dict[str, object], predecessor)


def build_execution_decision(
    root: Path,
    identity: dict[str, object],
) -> dict[str, object]:
    """Bind standing authority to exactly one version-8 fast lane."""
    runner = runpy.run_path(str(root / _RUNNER))
    expected = cast(dict[str, object], identity["expected_execution"])
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
        "candidate": _candidate(),
        "decision_id": (
            "phase-5-public-owner-domain-fast-lane-execution-decision"
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
        "expected_execution_sha256": canonical_sha256(expected),
        "identity_review": {
            "path": str(_IDENTITY),
            "sha256": identity_sha256,
        },
        "identity_review_sha256": identity_sha256,
        "output": expected["output"],
        "predecessor_fast_lane": identity["predecessor_fast_lane"],
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
    """Verify inputs and freeze all version-8 lane records."""
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
        raise FileExistsError("refusing to overwrite public fast-lane records")
    for destination, (_, document) in zip(
        destinations, documents, strict=True
    ):
        _write_once(destination, document)
    for path, document in documents:
        print(f"{path.name}_sha256={_document_sha256(document)}")


def main() -> None:
    """Parse roots and freeze the version-8 fast lane."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    freeze_records(parser.parse_args())


if __name__ == "__main__":
    main()
