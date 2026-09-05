#!/usr/bin/env python3
"""Freeze the source-support-linkage process-only retry identity."""

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
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-identity-review.json"
)
_PREDECESSOR_IDENTITY_SHA256 = (
    "cf59dd822a57820ca61161b1946ac2241d36a6b2a9fa0bc00b74dd87bb65f984"
)
_FAILED_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-execution-decision.json"
)
_FAILED_EXECUTION_DECISION_SHA256 = (
    "17a6c01c2d370055639e73f9cda6d91c4261747e36823f7db527cd4e7aacd716"
)
_REPAIR_REVIEW = Path(
    "config/contracts/phase-5-source-owned-source-support-linkage-"
    "process-repair-pre-review.json"
)
_REPAIR_REVIEW_SHA256 = (
    "b829a4b58c6edc86560b3e0d242869f12b5a66de1298713a705ef827e2be4fa5"
)
_RUNNER = Path(
    "scripts/validation/run_phase5_source_owned_measurement_topology.py"
)
_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-process-repair-identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-process-repair-execution-decision.json"
)
_FAILED_SCRATCH = Path(
    "/private/tmp/hebog-phase5-source-owned-measurement-topology-"
    "source-support-linkage-2e25cdf"
)
_FAILED_NAMESPACE_FILE_COUNT = 721
_FAILED_NAMESPACE_SIZE_BYTES = 498_192_816
_FAILED_CANDIDATE_BUNDLE_COUNT = 144
_FAILED_NAMESPACE_SHA256 = (
    "cfea0bfcce25d80c48e248357cb215b78eb33b795d21af51b6821677e8b7ab8d"
)
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "3da083b0a720fe0104fa51e135f224a2456b49bd49d85cd6a449fccb93805e8a"
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
    """Verify predecessor, consumed decision, review, and candidate science."""
    for path, expected_sha256 in (
        (_PREDECESSOR_IDENTITY, _PREDECESSOR_IDENTITY_SHA256),
        (_FAILED_EXECUTION_DECISION, _FAILED_EXECUTION_DECISION_SHA256),
        (_REPAIR_REVIEW, _REPAIR_REVIEW_SHA256),
    ):
        if file_sha256(root / path) != expected_sha256:
            raise ValueError(f"source-linkage process input changed: {path}")
    if source_tree_sha256(root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError(
            "source-linkage process repair changed candidate science"
        )


def _verify_preserved_failure() -> None:
    """Require the exact post-candidate failed namespace to remain sealed."""
    files = tuple(
        path for path in sorted(_FAILED_SCRATCH.rglob("*")) if path.is_file()
    )
    records = tuple(
        {
            "path": str(path.relative_to(_FAILED_SCRATCH)),
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in files
    )
    namespace_size_bytes = sum(path.stat().st_size for path in files)
    if (
        len(files) != _FAILED_NAMESPACE_FILE_COUNT
        or namespace_size_bytes != _FAILED_NAMESPACE_SIZE_BYTES
        or canonical_sha256(records) != _FAILED_NAMESPACE_SHA256
        or len(tuple(_FAILED_SCRATCH.glob("*/candidate-products")))
        != _FAILED_CANDIDATE_BUNDLE_COUNT
        or tuple(_FAILED_SCRATCH.glob("*/coarse-products"))
        or tuple(_FAILED_SCRATCH.glob("*/attribution.json"))
        or (_FAILED_SCRATCH / "progress.log").stat().st_size != 0
    ):
        raise ValueError("failed source-linkage namespace identity changed")


def _runner_records(
    root: Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, object]]:
    """Load exact binding paths and execution shape from the runner."""
    runner = runpy.run_path(str(root / _RUNNER))
    return (
        cast(dict[str, str], runner["_PROGRAM_BINDING_PATHS"]),
        cast(dict[str, str], runner["_FIXTURE_BINDING_PATHS"]),
        cast(dict[str, object], runner["_expected_execution"]()),
    )


def build_identity(root: Path) -> dict[str, object]:
    """Build the process-only successor without granting execution."""
    _verify_inputs(root)
    predecessor = copy.deepcopy(_json_object(root / _PREDECESSOR_IDENTITY))
    programs, fixtures, expected_execution = _runner_records(root)
    predecessor.update(
        {
            "authorization": dict.fromkeys(
                cast(dict[str, object], predecessor["authorization"]), False
            ),
            "expected_execution": expected_execution,
            "expected_execution_sha256": canonical_sha256(expected_execution),
            "fixture_bindings": {
                name: {"path": path, "sha256": file_sha256(root / path)}
                for name, path in sorted(fixtures.items())
            },
            "identity_review_id": (
                "phase-5-source-owned-measurement-topology-source-support-"
                "linkage-process-repair-identity-review"
            ),
            "predecessor_identity": {
                "path": str(_PREDECESSOR_IDENTITY),
                "sha256": _PREDECESSOR_IDENTITY_SHA256,
            },
            "process_repair": {
                "failed_execution": {
                    "candidate_bundle_count": _FAILED_CANDIDATE_BUNDLE_COUNT,
                    "candidate_execution_count": (
                        _FAILED_CANDIDATE_BUNDLE_COUNT
                    ),
                    "coarse_control_execution_count": 0,
                    "decision": {
                        "path": str(_FAILED_EXECUTION_DECISION),
                        "sha256": _FAILED_EXECUTION_DECISION_SHA256,
                    },
                    "execution_commit": (
                        "218a7f9ae8843511a07e4110af529d79ae21053f"
                    ),
                    "namespace_file_count": _FAILED_NAMESPACE_FILE_COUNT,
                    "namespace_file_set_sha256": _FAILED_NAMESPACE_SHA256,
                    "namespace_size_bytes": _FAILED_NAMESPACE_SIZE_BYTES,
                    "output_published": False,
                    "progress_record_count": 0,
                    "scratch": str(_FAILED_SCRATCH),
                },
                "repair_contract": (
                    "read canonical SourceCandidate.source_id at the exact "
                    "post-candidate truth-linkage boundary"
                ),
                "review": {
                    "path": str(_REPAIR_REVIEW),
                    "sha256": _REPAIR_REVIEW_SHA256,
                },
            },
            "program_bindings": {
                name: {"path": path, "sha256": file_sha256(root / path)}
                for name, path in sorted(programs.items())
            },
            "required_next_decision": (
                "consume only the separately verified one-use process-repair "
                "execution decision"
            ),
            "runtime": build_adaptive_runtime_identity(root),
            "status": "frozen-non-executable",
        }
    )
    execution_contract = cast(
        dict[str, object], predecessor["execution_contract"]
    )
    execution_contract["scratch"] = expected_execution["scratch"]
    return cast(dict[str, object], predecessor)


def build_execution_decision(
    root: Path,
    identity: dict[str, object],
) -> dict[str, object]:
    """Bind standing bug-fix authority to exactly one repaired lane."""
    runner = runpy.run_path(str(root / _RUNNER))
    expected_execution = cast(
        dict[str, object], identity["expected_execution"]
    )
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
            "phase-5-source-owned-measurement-topology-source-support-"
            "linkage-process-repair-execution-decision"
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
            "sha256": _document_sha256(identity),
        },
        "identity_review_sha256": _document_sha256(identity),
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


def freeze_records(arguments: argparse.Namespace) -> None:
    """Verify the failure and create the exact identity and decision once."""
    root = arguments.repository_root.resolve()
    output_root = arguments.output_root.resolve()
    destinations = (output_root / _IDENTITY, output_root / _EXECUTION_DECISION)
    if any(path.exists() for path in destinations):
        raise FileExistsError(
            "refusing to overwrite source-linkage process-repair records"
        )
    _verify_preserved_failure()
    identity = build_identity(root)
    decision = build_execution_decision(root, identity)
    for destination, document in zip(
        destinations, (identity, decision), strict=True
    ):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(_json_bytes(document))
    print(f"{_IDENTITY.name}_sha256={_document_sha256(identity)}")
    print(f"{_EXECUTION_DECISION.name}_sha256={_document_sha256(decision)}")


def main() -> None:
    """Parse exact roots and freeze the repaired retry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    freeze_records(parser.parse_args())


if __name__ == "__main__":
    main()
