#!/usr/bin/env python3
"""Freeze the non-executable analysis-config repair lane identity."""

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
    "process-repair-identity-review.json"
)
_PREDECESSOR_IDENTITY_SHA256 = (
    "40a9f99f817fbc39ef38ddc9f3bfc6c748040957c7ccf3b1d783ada6ab2691d2"
)
_FAILED_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "process-repair-execution-decision.json"
)
_FAILED_EXECUTION_DECISION_SHA256 = (
    "8678b5399a138a321f42223b384ca994a7716bb6996861b542f4abebde1286d2"
)
_REPAIR_REVIEW = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "analysis-config-repair-pre-review.json"
)
_REPAIR_REVIEW_SHA256 = (
    "ff687012274695b4e410b643c2e012306c116e438e83186ba824f920c2914a02"
)
_RUNNER = Path(
    "scripts/validation/run_phase5_source_owned_measurement_topology.py"
)
_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "analysis-config-repair-identity-review.json"
)
_FAILED_SCRATCH = Path(
    "/private/tmp/hebog-phase5-source-owned-measurement-topology-"
    "process-repair-c28343f"
)
_FAILED_NAMESPACE_SHA256 = (
    "f008f8fe5850c52d4353b463ae928dbd951aa61dcbbf6f5cd7f6ef90ce8abd0c"
)
_FAILED_NAMESPACE_FILE_COUNT = 721
_FAILED_NAMESPACE_SIZE_BYTES = 498_192_816
_FAILED_CANDIDATE_BUNDLE_COUNT = 144
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
    """Verify the predecessor, consumed decision, review, and candidate."""
    expected = (
        (_PREDECESSOR_IDENTITY, _PREDECESSOR_IDENTITY_SHA256),
        (_FAILED_EXECUTION_DECISION, _FAILED_EXECUTION_DECISION_SHA256),
        (_REPAIR_REVIEW, _REPAIR_REVIEW_SHA256),
    )
    for path, sha256 in expected:
        if file_sha256(root / path) != sha256:
            raise ValueError(f"analysis-config repair input changed: {path}")
    if source_tree_sha256(root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError(
            "analysis-config repair changed the scientific source tree"
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
    if (
        len(files) != _FAILED_NAMESPACE_FILE_COUNT
        or sum(record["size_bytes"] for record in records)
        != _FAILED_NAMESPACE_SIZE_BYTES
        or canonical_sha256(records) != _FAILED_NAMESPACE_SHA256
        or len(tuple(_FAILED_SCRATCH.glob("*/candidate-products")))
        != _FAILED_CANDIDATE_BUNDLE_COUNT
        or tuple(_FAILED_SCRATCH.glob("*/coarse-work"))
        or tuple(_FAILED_SCRATCH.glob("*/observation.json"))
        or tuple(_FAILED_SCRATCH.glob("*/attribution.json"))
        or (_FAILED_SCRATCH / "progress.log").stat().st_size != 0
    ):
        raise ValueError("failed analysis-config namespace identity changed")


def build_identity(root: Path) -> dict[str, object]:
    """Build the config-repaired successor without granting execution."""
    _verify_inputs(root)
    _verify_preserved_failure()
    runner = runpy.run_path(str(root / _RUNNER))
    identity = copy.deepcopy(_json_object(root / _PREDECESSOR_IDENTITY))
    program_paths = cast(dict[str, str], runner["_PROGRAM_BINDING_PATHS"])
    fixture_paths = cast(dict[str, str], runner["_FIXTURE_BINDING_PATHS"])
    expected_execution = cast(
        dict[str, object], runner["_expected_execution"]()
    )
    identity.update(
        {
            "analysis_config_repair": {
                "failed_execution": {
                    "candidate_bundle_count": 144,
                    "candidate_execution_count": 144,
                    "coarse_control_execution_count": 0,
                    "decision": {
                        "path": str(_FAILED_EXECUTION_DECISION),
                        "sha256": _FAILED_EXECUTION_DECISION_SHA256,
                    },
                    "execution_commit": (
                        "8b29370c4ed0133557a84483b7c61ac91ff62152"
                    ),
                    "namespace_file_count": _FAILED_NAMESPACE_FILE_COUNT,
                    "namespace_file_set_sha256": _FAILED_NAMESPACE_SHA256,
                    "namespace_size_bytes": _FAILED_NAMESPACE_SIZE_BYTES,
                    "output_published": False,
                    "progress_record_count": 0,
                    "scratch": str(_FAILED_SCRATCH),
                },
                "repair_contract": (
                    "supply the exact frozen public configuration only when "
                    "adapting the predecessor coarse-control analysis call"
                ),
                "review": {
                    "path": str(_REPAIR_REVIEW),
                    "sha256": _REPAIR_REVIEW_SHA256,
                },
            },
            "authorization": dict.fromkeys(
                cast(dict[str, object], identity["authorization"]), False
            ),
            "expected_execution": expected_execution,
            "expected_execution_sha256": canonical_sha256(expected_execution),
            "fixture_bindings": {
                name: {"path": path, "sha256": file_sha256(root / path)}
                for name, path in sorted(fixture_paths.items())
            },
            "identity_review_id": (
                "phase-5-source-owned-measurement-topology-"
                "analysis-config-repair-identity-review"
            ),
            "predecessor_identity": {
                "path": str(_PREDECESSOR_IDENTITY),
                "sha256": _PREDECESSOR_IDENTITY_SHA256,
            },
            "program_bindings": {
                name: {"path": path, "sha256": file_sha256(root / path)}
                for name, path in sorted(program_paths.items())
            },
            "required_next_decision": (
                "record the user's standing repaired-lane authority in a new "
                "exact one-use decision before retrying"
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
    destination = arguments.output_root.resolve() / _IDENTITY
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite config-repair identity: {destination}"
        )
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
