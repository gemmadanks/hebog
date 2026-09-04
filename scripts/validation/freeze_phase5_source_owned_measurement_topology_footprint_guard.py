#!/usr/bin/env python3
"""Freeze and authorize the one-use source-owned footprint-guard lane."""

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
import runpy
from pathlib import Path
from typing import Any, cast

from hebog import public_api
from hebog.validation.adaptive_background_lane import (
    build_adaptive_runtime_identity,
)
from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)

_ROOT_REVIEW = Path(
    "config/contracts/phase-5-source-owned-lane-terminal-root-cause-review.json"
)
_ROOT_REVIEW_SHA256 = (
    "2c9495f310b3ab21cb5a49adb2fa2a04e93e71e09046bfc2362ca73dd35a33fa"
)
_PREDECESSOR_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "analysis-config-repair-identity-review.json"
)
_PREDECESSOR_IDENTITY_SHA256 = (
    "3e0730df83b1973af9455bb3be97f3194a76b2cfad9dcdf75e44eb4c4fd60570"
)
_PREDECESSOR_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "public-interface-identity-review.json"
)
_PREDECESSOR_PUBLIC_IDENTITY_SHA256 = (
    "ca1abba66a6368fe37fb8e43b93b81999ced462f3e01d16be9011cc629913490"
)
_MANIFEST = Path(
    "config/contracts/phase-5-adaptive-background-development-manifest.json"
)
_MANIFEST_SHA256 = (
    "77203f85930a99ffbb5490f93db7073cab434b42c8350d6da864625efd09946b"
)
_RUNNER = Path(
    "scripts/validation/run_phase5_source_owned_measurement_topology.py"
)
_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "footprint-guard-public-interface-identity-review.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "footprint-guard-implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "footprint-guard-identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "footprint-guard-execution-decision.json"
)
_CANDIDATE_REVISION = "4fb2f483bc54292e869ef744d4a473434c18f4ac"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "1275580e38aa320b65a4f71cfee2ebb07d231fccb8633565d39f0713d0e791b6"
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
_INTERFACE_FILES = (
    "src/hebog/__init__.py",
    "src/hebog/config.py",
    "src/hebog/data_models/source_finding.py",
    "src/hebog/io/materialization.py",
    "src/hebog/pipeline.py",
    "src/hebog/public_api.py",
    "src/hebog/public_science.py",
    "src/hebog/resources/phase_5_continuum_review.json",
)


def _json_object(path: Path) -> dict[str, Any]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"required identity must be a JSON object: {path}")
    return cast(dict[str, Any], value)


def _json_bytes(value: object) -> bytes:
    """Return the canonical checked-in JSON representation."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _document_sha256(value: object) -> str:
    """Hash one canonical checked-in JSON document."""
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _require_inputs(root: Path) -> None:
    """Verify the exact terminal predecessor and reviewed correction."""
    expected = (
        (_ROOT_REVIEW, _ROOT_REVIEW_SHA256),
        (_PREDECESSOR_IDENTITY, _PREDECESSOR_IDENTITY_SHA256),
        (
            _PREDECESSOR_PUBLIC_IDENTITY,
            _PREDECESSOR_PUBLIC_IDENTITY_SHA256,
        ),
        (_MANIFEST, _MANIFEST_SHA256),
    )
    for path, sha256 in expected:
        if file_sha256(root / path) != sha256:
            raise ValueError(f"footprint-guard input changed: {path}")
    if source_tree_sha256(root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("footprint-guard scientific source tree changed")


def _module_path(root: Path, module_name: str) -> Path:
    """Resolve one installed scientific module into this checkout."""
    module = importlib.import_module(module_name)
    path = Path(module.__file__ or "").resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "scientific module is not loaded from this checkout: "
            f"{module_name}"
        ) from error
    return path


def build_public_identity(root: Path) -> dict[str, object]:
    """Bind the corrected source tree and current public composition."""
    predecessor = _json_object(root / _PREDECESSOR_PUBLIC_IDENTITY)
    identity = copy.deepcopy(predecessor)
    identity.update(
        {
            "algorithm_candidate": {
                "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
                "revision": _CANDIDATE_REVISION,
                "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
            },
            "footprint_guard_correction": {
                "association_radius_beams": 1.5,
                "estimator_guard": "maximum-estimator-half-window",
                "root_cause_review": {
                    "path": str(_ROOT_REVIEW),
                    "sha256": _ROOT_REVIEW_SHA256,
                },
                "truth_linked_split_semantics": True,
                "unmatched_reliability_retained": True,
            },
            "interface_file_sha256": {
                path: file_sha256(root / path) for path in _INTERFACE_FILES
            },
            "predecessor_identity": {
                "path": str(_PREDECESSOR_PUBLIC_IDENTITY),
                "sha256": _PREDECESSOR_PUBLIC_IDENTITY_SHA256,
            },
            "review_id": (
                "phase-5-source-owned-measurement-topology-footprint-guard-"
                "public-interface-identity-review"
            ),
            "scientific_composition": public_api._COMPOSITION_NAME,
            "scientific_composition_sha256": (
                public_api._scientific_composition_sha256()
            ),
            "scientific_module_sha256": {
                name: file_sha256(_module_path(root, name))
                for name in public_api._SCIENTIFIC_MODULES
            },
            "status": "frozen-non-executable",
        }
    )
    identity["authorizations"] = dict.fromkeys(
        cast(dict[str, object], identity["authorizations"]), False
    )
    return cast(dict[str, object], identity)


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


def build_implementation(
    root: Path,
    public_identity: dict[str, object],
    programs: dict[str, str],
    fixtures: dict[str, str],
) -> dict[str, object]:
    """Record the tested prospective correction without execution authority."""
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
            "threshold_or_margin_tuning_authorized": False,
            "viewed_data_execution_authorized": False,
        },
        "decision_id": (
            "phase-5-source-owned-measurement-topology-footprint-guard-"
            "implementation-decision"
        ),
        "exact_user_authority": _EXACT_AUTHORITY,
        "fixture_bindings": {
            name: {"path": path, "sha256": file_sha256(root / path)}
            for name, path in sorted(fixtures.items())
        },
        "fixture_evidence": {
            "combined_successor_tests_passed": 21,
            "process_errors": 0,
            "test_first_regression_confirmed": True,
        },
        "implemented_contracts": [
            (
                "adaptive background and RMS source protection expands by "
                "the maximum estimator half-window"
            ),
            (
                "analytic recovery and split diagnostics use only catalogue "
                "rows associated with the injected truth footprint"
            ),
            (
                "remote catalogue rows remain explicit array-free reliability "
                "evidence and are not hidden by source association"
            ),
            (
                "the fast lane binds product validity, trigger activation, "
                "paired practical margins, and Serial/existing-Dask identity"
            ),
            (
                "dual-PyBDSF parity and incumbent retention remain mandatory "
                "in cumulative replay and held-out qualification"
            ),
        ],
        "program_bindings": {
            name: {"path": path, "sha256": file_sha256(root / path)}
            for name, path in sorted(programs.items())
        },
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
    public_identity: dict[str, object],
    implementation: dict[str, object],
    expected_execution: dict[str, object],
) -> dict[str, object]:
    """Freeze the one-use fast lane independently from its authorization."""
    return {
        "authorization": {
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
        "fixture_bindings": implementation["fixture_bindings"],
        "footprint_guard_correction": {
            "root_cause_review": {
                "path": str(_ROOT_REVIEW),
                "sha256": _ROOT_REVIEW_SHA256,
            }
        },
        "identity_review_id": (
            "phase-5-source-owned-measurement-topology-footprint-guard-"
            "identity-review"
        ),
        "implementation_decision": {
            "path": str(_IMPLEMENTATION),
            "sha256": _document_sha256(implementation),
        },
        "population": {
            "geometry_count": 12,
            "input_count": 144,
            "manifest_path": str(_MANIFEST),
            "manifest_sha256": _MANIFEST_SHA256,
            "matrix_cell_count": 36,
            "total_finder_executions": 300,
        },
        "predecessor_identity": {
            "path": str(_PREDECESSOR_IDENTITY),
            "sha256": _PREDECESSOR_IDENTITY_SHA256,
        },
        "program_bindings": implementation["program_bindings"],
        "public_identity": {
            "path": str(_PUBLIC_IDENTITY),
            "sha256": _document_sha256(public_identity),
        },
        "required_next_decision": (
            "consume only the separately verified one-use execution decision"
        ),
        "root_cause_review": {
            "path": str(_ROOT_REVIEW),
            "sha256": _ROOT_REVIEW_SHA256,
        },
        "runtime": build_adaptive_runtime_identity(root),
        "schema_version": 1,
        "status": "frozen-non-executable",
    }


def build_execution_decision(
    root: Path,
    identity: dict[str, object],
    expected_execution: dict[str, object],
) -> dict[str, object]:
    """Bind the user's authority to exactly one corrected fast lane."""
    runner = runpy.run_path(str(root / _RUNNER))
    return {
        "authorization": cast(
            dict[str, bool], runner["_EXPECTED_EXECUTION_AUTHORIZATION"]
        ),
        "authorization_record": {
            "approved_on": "2026-09-05",
            "statement": _EXACT_AUTHORITY,
        },
        "candidate": {
            "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
            "revision": _CANDIDATE_REVISION,
            "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        },
        "decision_id": (
            "phase-5-source-owned-measurement-topology-footprint-guard-"
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
            "sha256": _document_sha256(identity),
        },
        "identity_review_sha256": _document_sha256(identity),
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


def freeze_records(arguments: argparse.Namespace) -> None:
    """Build and write the four exact records without overwriting any."""
    root = arguments.repository_root.resolve()
    output_root = arguments.output_root.resolve()
    _require_inputs(root)
    programs, fixtures, expected_execution = _runner_records(root)
    public_identity = build_public_identity(root)
    implementation = build_implementation(
        root, public_identity, programs, fixtures
    )
    identity = build_identity(
        root, public_identity, implementation, expected_execution
    )
    decision = build_execution_decision(root, identity, expected_execution)
    documents = (
        (_PUBLIC_IDENTITY, public_identity),
        (_IMPLEMENTATION, implementation),
        (_IDENTITY, identity),
        (_EXECUTION_DECISION, decision),
    )
    destinations = tuple(output_root / path for path, _ in documents)
    if any(path.exists() for path in destinations):
        raise FileExistsError("refusing to overwrite footprint-guard records")
    for destination, (_, document) in zip(
        destinations, documents, strict=True
    ):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(_json_bytes(document))
    for path, document in documents:
        print(f"{path.name}_sha256={_document_sha256(document)}")


def main() -> None:
    """Parse explicit roots and freeze the authorized successor lane."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    freeze_records(parser.parse_args())


if __name__ == "__main__":
    main()
