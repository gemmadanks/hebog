#!/usr/bin/env python3
"""Freeze the source-support-linkage repair replication identities."""

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
    build_adaptive_replication_manifest,
    build_adaptive_runtime_identity,
)
from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)

_ROOT_REVIEW = Path(
    "config/contracts/phase-5-source-owned-source-support-linkage-"
    "terminal-root-cause-review.json"
)
_ROOT_REVIEW_SHA256 = (
    "25f6bf0f0f1a41964ba59e7030579d13487c633cbd09ba5948dad3b6e5915462"
)
_PREDECESSOR_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-process-repair-identity-review.json"
)
_PREDECESSOR_IDENTITY_SHA256 = (
    "b4d7636484218377dd4125ba0079970d08fa2602f2caa3b8dd4a9f7c31c82d55"
)
_PREDECESSOR_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-public-interface-identity-review.json"
)
_PREDECESSOR_PUBLIC_IDENTITY_SHA256 = (
    "48a57449ebd80abaeec1af5db4ba8ac07d73be60262fa53f56053b4f7ca806ea"
)
_PROCESS_REPAIR_REVIEW = Path(
    "config/contracts/phase-5-source-owned-source-support-linkage-"
    "process-repair-pre-review.json"
)
_PROCESS_REPAIR_REVIEW_SHA256 = (
    "b829a4b58c6edc86560b3e0d242869f12b5a66de1298713a705ef827e2be4fa5"
)
_RUNNER = Path(
    "scripts/validation/run_phase5_source_support_linkage_replication.py"
)
_MANIFEST = Path(
    "config/contracts/phase-5-source-support-linkage-replication-manifest.json"
)
_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "public-interface-identity-review.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "execution-decision.json"
)
_CANDIDATE_REVISION = "0b9e13299f3fbbd42af0dea4f70155a802a8441d"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "11307db0059739d473288dd2ed647970cce43b69e874632e1d1f14ee0ed032df"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
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
    """Return canonical checked-in JSON bytes."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _document_sha256(value: object) -> str:
    """Hash one canonical checked-in document."""
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _verify_inputs(root: Path) -> None:
    """Verify the terminal review, predecessor, and unchanged science."""
    for path, expected in (
        (_ROOT_REVIEW, _ROOT_REVIEW_SHA256),
        (_PREDECESSOR_IDENTITY, _PREDECESSOR_IDENTITY_SHA256),
        (
            _PREDECESSOR_PUBLIC_IDENTITY,
            _PREDECESSOR_PUBLIC_IDENTITY_SHA256,
        ),
        (_PROCESS_REPAIR_REVIEW, _PROCESS_REPAIR_REVIEW_SHA256),
    ):
        if file_sha256(root / path) != expected:
            raise ValueError(f"replication predecessor changed: {path}")
    if source_tree_sha256(root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("replication candidate source tree changed")


def _runner_records(
    root: Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, object]]:
    """Load exact binding sets and execution shape from the runner."""
    runner = runpy.run_path(str(root / _RUNNER))
    return (
        cast(dict[str, str], runner["_PROGRAM_BINDING_PATHS"]),
        cast(dict[str, str], runner["_FIXTURE_BINDING_PATHS"]),
        cast(dict[str, object], runner["_expected_execution"]()),
    )


def build_public_identity(root: Path) -> dict[str, object]:
    """Rebind the unchanged public candidate to the reviewed replication."""
    public = copy.deepcopy(_json_object(root / _PREDECESSOR_PUBLIC_IDENTITY))
    public.update(
        {
            "algorithm_candidate": {
                "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
                "revision": _CANDIDATE_REVISION,
                "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
            },
            "predecessor_identity": {
                "path": str(_PREDECESSOR_PUBLIC_IDENTITY),
                "sha256": _PREDECESSOR_PUBLIC_IDENTITY_SHA256,
            },
            "review_id": (
                "phase-5-source-support-linkage-replication-public-"
                "interface-identity-review"
            ),
            "source_support_linkage_repair": {
                "binding_statistic": (
                    "paired-median-within-each-four-seed-trigger-cell"
                ),
                "linkage": (
                    "source-owned-truth-overlap-at-existing-seven-pixel-"
                    "minimum-island-support"
                ),
                "root_cause_review": {
                    "path": str(_ROOT_REVIEW),
                    "sha256": _ROOT_REVIEW_SHA256,
                },
                "source_finding_science_changed": False,
                "tail_policy": (
                    "maximum-per-image-movements-visible-non-binding"
                ),
                "unmatched_reliability_retained": True,
            },
            "status": "frozen-non-executable",
        }
    )
    return cast(dict[str, object], public)


def _bindings(root: Path, paths: dict[str, str]) -> dict[str, object]:
    """Bind each declared repository file by exact digest."""
    return {
        name: {"path": path, "sha256": file_sha256(root / path)}
        for name, path in sorted(paths.items())
    }


def build_implementation(
    root: Path,
    public_identity: dict[str, object],
) -> dict[str, object]:
    """Describe the fixture-validated prospective replication only."""
    programs, fixtures, _ = _runner_records(root)
    return {
        "current_authorization": {
            "candidate_execution_authorized": False,
            "coarse_control_execution_authorized": False,
            "cutover_authorized": False,
            "development_lane_execution_authorized": False,
            "fresh_qualification_authorized": False,
            "optimization_authorized": False,
            "pybdsf_execution_authorized": False,
            "release_authorized": False,
            "replay_authorized": False,
            "rescoring_authorized": False,
            "source_finding_change_authorized": False,
            "threshold_or_margin_tuning_authorized": False,
            "viewed_data_execution_authorized": False,
        },
        "decision_id": (
            "phase-5-source-support-linkage-replication-implementation-"
            "decision"
        ),
        "exact_user_authority": _EXACT_AUTHORITY,
        "fixture_bindings": _bindings(root, fixtures),
        "fixture_evidence": {
            "complete_non_slow_tests_passed": 2750,
            "focused_tests_passed": 69,
            "project_branch_coverage_percent": 94.80,
            "test_first_regression_confirmed": True,
        },
        "implemented_contracts": [
            (
                "fresh replication uses 144 seeds disjoint from viewed "
                "development and frozen qualification populations"
            ),
            (
                "truth linkage requires the existing seven-pixel public "
                "minimum-island support inside analytic truth"
            ),
            (
                "paired retention binds to each four-seed trigger-cell "
                "median without pooling geometries or cohorts"
            ),
            (
                "maximum single-image movements remain visible non-binding "
                "tail sentinels"
            ),
            (
                "all final per-geometry released-PyBDSF, pinned-master-"
                "PyBDSF, and incumbent gates remain unchanged"
            ),
        ],
        "program_bindings": _bindings(root, programs),
        "public_identity": {
            "path": str(_PUBLIC_IDENTITY),
            "sha256": _document_sha256(public_identity),
        },
        "root_cause_review": {
            "path": str(_ROOT_REVIEW),
            "sha256": _ROOT_REVIEW_SHA256,
        },
        "schema_version": 1,
        "status": "implemented-and-fixture-validated-non-executable",
    }


def build_identity(
    root: Path,
    manifest: dict[str, object],
    public_identity: dict[str, object],
    implementation: dict[str, object],
) -> dict[str, object]:
    """Freeze the exact replication population without granting execution."""
    predecessor = copy.deepcopy(_json_object(root / _PREDECESSOR_IDENTITY))
    programs, fixtures, expected_execution = _runner_records(root)
    manifest_sha256 = _document_sha256(manifest)
    predecessor.update(
        {
            "authorization": dict.fromkeys(
                cast(dict[str, object], predecessor["authorization"]), False
            ),
            "candidate": {
                "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
                "entrypoint": "hebog.find_sources",
                "revision": _CANDIDATE_REVISION,
                "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
            },
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
                "phase-5-source-support-linkage-replication-identity-review"
            ),
            "implementation_decision": {
                "path": str(_IMPLEMENTATION),
                "sha256": _document_sha256(implementation),
            },
            "population": {
                "geometry_count": 12,
                "input_count": 144,
                "manifest_path": str(_MANIFEST),
                "manifest_sha256": manifest_sha256,
                "matrix_cell_count": 36,
                "total_finder_executions": 300,
            },
            "predecessor_identity": {
                "path": str(_PREDECESSOR_IDENTITY),
                "sha256": _PREDECESSOR_IDENTITY_SHA256,
            },
            "program_bindings": _bindings(root, programs),
            "prospective_replication": {
                "binding_statistic": (
                    "paired-median-within-each-four-seed-trigger-cell"
                ),
                "first_seed": 2026952001,
                "last_seed": 2026952144,
                "minimum_truth_overlap_pixels": 7,
                "tail_policy": (
                    "maximum-per-image-movements-remain-visible-and-non-binding"
                ),
            },
            "public_identity": {
                "path": str(_PUBLIC_IDENTITY),
                "sha256": _document_sha256(public_identity),
            },
            "required_next_decision": (
                "consume only the separately verified one-use replication "
                "execution decision"
            ),
            "root_cause_review": {
                "path": str(_ROOT_REVIEW),
                "sha256": _ROOT_REVIEW_SHA256,
            },
            "runtime": build_adaptive_runtime_identity(root),
            "source_support_linkage_repair": {
                "root_cause_review": {
                    "path": str(_ROOT_REVIEW),
                    "sha256": _ROOT_REVIEW_SHA256,
                }
            },
            "status": "frozen-non-executable",
        }
    )
    return cast(dict[str, object], predecessor)


def build_execution_decision(
    root: Path,
    identity: dict[str, object],
) -> dict[str, object]:
    """Bind the user's authority to one exact short replication lane."""
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
            "phase-5-source-support-linkage-replication-execution-decision"
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
        "root_cause_review": {
            "path": str(_ROOT_REVIEW),
            "sha256": _ROOT_REVIEW_SHA256,
        },
        "schema_version": 1,
        "status": "authorized-for-one-development-lane",
        "workers": 2,
        "wrapper_sha256": file_sha256(root / _RUNNER),
    }


def _write_once(path: Path, value: object) -> None:
    """Write one canonical JSON document without overwriting evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(_json_bytes(value))


def freeze_records(arguments: argparse.Namespace) -> None:
    """Build and publish the exact five-record replication freeze."""
    root = arguments.repository_root.resolve()
    output_root = arguments.output_root.resolve()
    _verify_inputs(root)
    manifest = cast(
        dict[str, object],
        build_adaptive_replication_manifest().model_dump(mode="json"),
    )
    public = build_public_identity(root)
    implementation = build_implementation(root, public)
    identity = build_identity(
        root,
        manifest,
        public,
        implementation,
    )
    decision = build_execution_decision(root, identity)
    documents = (
        (_MANIFEST, manifest),
        (_PUBLIC_IDENTITY, public),
        (_IMPLEMENTATION, implementation),
        (_IDENTITY, identity),
        (_EXECUTION_DECISION, decision),
    )
    destinations = tuple(output_root / path for path, _ in documents)
    if any(path.exists() for path in destinations):
        raise FileExistsError(
            "refusing to overwrite source-linkage replication records"
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
    """Parse explicit roots and freeze the approved replication."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    freeze_records(parser.parse_args())


if __name__ == "__main__":
    main()
