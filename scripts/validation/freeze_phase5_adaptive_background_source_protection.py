#!/usr/bin/env python3
"""Freeze the non-executable source-protected adaptive lane identities."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any, cast

from hebog import public_api
from hebog.validation.adaptive_background_lane import (
    build_adaptive_runtime_identity,
)
from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
)

_ROOT_REVIEW = Path(
    "config/contracts/phase-5-adaptive-background-root-cause-pre-review.json"
)
_ROOT_REVIEW_SHA256 = (
    "8e00269924b50c1b52188beefcb177e50d9035e25a69755d5d2d31ddead3d902"
)
_PREDECESSOR_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-configurable-public-interface-identity-review.json"
)
_PREDECESSOR_PUBLIC_IDENTITY_SHA256 = (
    "6ad0866f5ffcb4077139fb51afe3bbb9c5bc0d3d26d5782212aa7b541542f77f"
)
_MANIFEST = Path(
    "config/contracts/phase-5-adaptive-background-development-manifest.json"
)
_MANIFEST_SHA256 = (
    "77203f85930a99ffbb5490f93db7073cab434b42c8350d6da864625efd09946b"
)
_PUBLIC_IDENTITY = Path(
    "config/contracts/"
    "phase-5-adaptive-background-source-protection-public-interface-identity-review.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/"
    "phase-5-adaptive-background-source-protection-implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/"
    "phase-5-adaptive-background-source-protection-identity-review.json"
)
_RUNNER = Path(
    "scripts/validation/run_phase5_adaptive_background_source_protection.py"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-adaptive-background-source-protection-7ebde58"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/"
    "adaptive-background-source-protection-development-decision.json"
)
_CANDIDATE_REVISION = "7ebde589c82e153e0f7d475a8469c120138be4da"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "c83ee5a90c33f9c915b69402710835a5a094d08df83e003f8e2fd0799f23ae2d"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_PROGRAMS = {
    "attribution": Path(
        "src/hebog/validation/adaptive_background_diagnostics.py"
    ),
    "background_algorithm": Path("src/hebog/algorithms/background.py"),
    "background_stage": Path("src/hebog/stages/background.py"),
    "detection_stage": Path("src/hebog/stages/detection.py"),
    "freezer": Path(
        "scripts/validation/"
        "freeze_phase5_adaptive_background_source_protection.py"
    ),
    "lane_evaluator": Path("src/hebog/validation/adaptive_background_lane.py"),
    "parent_runner": Path(
        "scripts/validation/run_phase5_adaptive_background_development.py"
    ),
    "runner": _RUNNER,
}
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
_EXACT_AUTHORITY = (
    "I approve the Phase 5 adaptive-background root-cause pre-review SHA-256 "
    "8e00269924b50c1b52188beefcb177e50d9035e25a69755d5d2d31ddead3d902 "
    "and its recommendations. This authorizes test-first implementation and "
    "fixture-only validation of bounded source-protected adaptive "
    "background/RMS estimation, diagnostic-only reproduction of the "
    "independent coarse-control gaps, bounded pre-publication attribution "
    "telemetry, Serial/existing-Dask invariance validation, and freezing "
    "non-executable replacement identities after all fixture gates pass. It "
    "does not authorize development-lane execution, cumulative replay, "
    "held-out qualification, PyBDSF or viewed-data execution, tuning, "
    "rescoring, optimization, cutover, or release."
)


def _json_object(path: Path) -> dict[str, Any]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"required identity must be a JSON object: {path}")
    return cast(dict[str, Any], value)


def _json_bytes(value: object) -> bytes:
    """Return the canonical checked-in document representation."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _document_sha256(value: object) -> str:
    """Hash one exact formatted JSON document."""
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _require_inputs(root: Path) -> None:
    """Verify every approved predecessor before deriving a successor."""
    expected = (
        (_ROOT_REVIEW, _ROOT_REVIEW_SHA256),
        (
            _PREDECESSOR_PUBLIC_IDENTITY,
            _PREDECESSOR_PUBLIC_IDENTITY_SHA256,
        ),
        (_MANIFEST, _MANIFEST_SHA256),
    )
    for relative_path, sha256 in expected:
        if file_sha256(root / relative_path) != sha256:
            raise ValueError(f"approved input changed: {relative_path}")


def _module_path(root: Path, module_name: str) -> Path:
    """Resolve one installed scientific module back into this checkout."""
    module = importlib.import_module(module_name)
    module_path = Path(module.__file__ or "").resolve()
    try:
        module_path.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "scientific module is not loaded from this checkout: "
            f"{module_name}"
        ) from error
    return module_path


def build_public_identity(root: Path) -> dict[str, object]:
    """Build the successor public composition without rewriting history."""
    _require_inputs(root)
    predecessor = _json_object(root / _PREDECESSOR_PUBLIC_IDENTITY)
    identity = copy.deepcopy(predecessor)
    identity.update(
        {
            "adaptive_background_policy": {
                "compact_profile": "qualified-unprotected-compatibility-path",
                "continuum_profile": (
                    "candidate-connected-public-island-windows-unavailable-"
                    "with-deterministic-fallback"
                ),
                "new_numeric_thresholds": False,
            },
            "algorithm_candidate": {
                "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
                "revision": _CANDIDATE_REVISION,
                "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
            },
            "interface_file_sha256": {
                path: file_sha256(root / path) for path in _INTERFACE_FILES
            },
            "predecessor_identity": {
                "path": str(_PREDECESSOR_PUBLIC_IDENTITY),
                "sha256": _PREDECESSOR_PUBLIC_IDENTITY_SHA256,
            },
            "review_id": (
                "phase-5-adaptive-background-source-protection-"
                "public-interface-identity-review"
            ),
            "schema_version": 3,
            "scientific_composition": public_api._COMPOSITION_NAME,
            "scientific_composition_sha256": (
                public_api._scientific_composition_sha256()
            ),
            "scientific_module_sha256": {
                module_name: file_sha256(_module_path(root, module_name))
                for module_name in public_api._SCIENTIFIC_MODULES
            },
            "status": "frozen-non-executable",
        }
    )
    identity["authorizations"] = dict.fromkeys(
        cast(dict[str, object], identity["authorizations"]),
        False,
    )
    return cast(dict[str, object], identity)


def _expected_execution() -> dict[str, object]:
    """Return the only shape a later separately approved lane may use."""
    return {
        "candidate_executions": 144,
        "coarse_control_executions": 144,
        "existing_dask_executions": 12,
        "existing_dask_scheduler": "caller-owned-runtime-address",
        "identity_review": str(_IDENTITY),
        "manifest": str(_MANIFEST),
        "output": str(_OUTPUT),
        "scratch": str(_SCRATCH),
        "workers": 2,
    }


def build_implementation_decision(
    root: Path,
    public_identity: dict[str, object],
) -> dict[str, object]:
    """Record the consumed implementation authority and fixture evidence."""
    _require_inputs(root)
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
            "phase-5-adaptive-background-source-protection-"
            "implementation-decision"
        ),
        "exact_user_authority": _EXACT_AUTHORITY,
        "fixture_evidence": {
            "affected_and_regression_tests_passed": 73,
            "compact_dual_pybdsf_equivalence_tests_passed": 27,
            "project_branch_coverage_percent": 94.80,
            "project_coverage_tests_passed": 2649,
            "project_coverage_xfailed": 2,
        },
        "implemented_contracts": [
            (
                "continuum fine windows intersecting protected support are "
                "unavailable"
            ),
            (
                "protection is the connected coarse-normalized public-"
                "threshold island containing each existing 75-sigma seed"
            ),
            "protected cells use only existing deterministic fallback",
            "source-free high-noise fine cells remain adaptive",
            "compact profile retains its qualified fine-grid path",
            "protected pixel and window counters are bounded scalar telemetry",
            (
                "array-free truth attribution separates adaptive, "
                "measurement, and publication losses"
            ),
            (
                "mixed-halo and shell gaps are reproduced diagnostically, "
                "not changed"
            ),
            "Serial, existing-Dask, tile, order, and retry invariance pass",
            "the replacement lane remains non-executable",
        ],
        "program_bindings": {
            name: {"path": str(path), "sha256": file_sha256(root / path)}
            for name, path in sorted(_PROGRAMS.items())
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


def build_identity_review(
    root: Path,
    public_identity: dict[str, object],
    implementation: dict[str, object],
) -> dict[str, object]:
    """Freeze the exact candidate and lane without granting execution."""
    _require_inputs(root)
    expected_execution = _expected_execution()
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
            "attribution": "array-free-non-binding-per-input-record-v1",
            "atomic_output": str(_OUTPUT),
            "candidate_executions": 144,
            "coarse_control_executions": 144,
            "existing_dask_executions": 12,
            "existing_dask_policy": (
                "caller-owned scheduler address; runner creates no cluster"
            ),
            "output_policy": "one atomic write; never overwrite or rerun",
            "required_workers": 2,
            "scratch": str(_SCRATCH),
            "total_finder_executions": 300,
        },
        "expected_execution": expected_execution,
        "expected_execution_sha256": canonical_sha256(expected_execution),
        "identity_review_id": (
            "phase-5-adaptive-background-source-protection-identity-review"
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
        "program_bindings": cast(
            dict[str, object], implementation["program_bindings"]
        ),
        "public_identity": {
            "path": str(_PUBLIC_IDENTITY),
            "sha256": _document_sha256(public_identity),
        },
        "required_next_decision": (
            "obtain separate exact one-use approval bound to this identity "
            "review and expected execution before running the lane"
        ),
        "root_cause_review": {
            "path": str(_ROOT_REVIEW),
            "sha256": _ROOT_REVIEW_SHA256,
        },
        "runtime": build_adaptive_runtime_identity(root),
        "schema_version": 1,
        "status": "frozen-non-executable",
    }


def _write_once(path: Path, value: object) -> None:
    """Write one exact JSON identity without overwriting evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(_json_bytes(value))


def _parse_arguments() -> argparse.Namespace:
    """Parse the explicit repository and destination roots."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    return parser.parse_args()


def freeze_identities(arguments: argparse.Namespace) -> None:
    """Build and atomically preflight the complete three-record freeze."""
    root = arguments.repository_root.resolve()
    output = arguments.output_root.resolve()
    public_identity = build_public_identity(root)
    implementation = build_implementation_decision(root, public_identity)
    identity = build_identity_review(root, public_identity, implementation)
    documents = (
        (_PUBLIC_IDENTITY, public_identity),
        (_IMPLEMENTATION, implementation),
        (_IDENTITY, identity),
    )
    destinations = tuple(output / path for path, _ in documents)
    existing = tuple(path for path in destinations if path.exists())
    if existing:
        raise FileExistsError(
            "refusing to overwrite adaptive source-protection identities: "
            + ", ".join(str(path) for path in existing)
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
    """Freeze all non-executable successor records."""
    freeze_identities(_parse_arguments())


if __name__ == "__main__":
    main()
