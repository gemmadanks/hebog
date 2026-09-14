#!/usr/bin/env python3
"""Freeze non-executable identities for the adaptive-background lane."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from hebog.validation.adaptive_background_lane import (
    build_adaptive_development_manifest,
    build_adaptive_runtime_identity,
)
from hebog.validation.external_runners import canonical_sha256, file_sha256

_PRE_REVIEW = Path(
    "config/contracts/phase-5-adaptive-background-development-pre-review.json"
)
_PRE_REVIEW_SHA256 = (
    "6287ad3ef734c91142637142f04abebfb7226253e9e49060af686fe07292eed4"
)
_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-public-interface-identity-review.json"
)
_PUBLIC_IDENTITY_SHA256 = (
    "a521c656683cdae8b8d2250a3d29dee716c4ff774a25e23556301b21e5d898f8"
)
_CANDIDATE_REVISION = "937737d811dd229d71dbcfdbda6cb5829de6faca"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_MANIFEST = Path(
    "config/contracts/phase-5-adaptive-background-development-manifest.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/"
    "phase-5-adaptive-background-development-implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-adaptive-background-development-identity-review.json"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-adaptive-background-development-937737d"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/adaptive-background-development-decision.json"
)
_PROGRAMS = {
    "approved_design": Path(
        "src/hebog/validation/adaptive_background_development.py"
    ),
    "evaluator_and_population": Path(
        "src/hebog/validation/adaptive_background_lane.py"
    ),
    "freezer": Path(
        "scripts/validation/freeze_phase5_adaptive_background_development.py"
    ),
    "runner": Path(
        "scripts/validation/run_phase5_adaptive_background_development.py"
    ),
}
_EXACT_AUTHORITY = (
    "I approve the Phase 5 adaptive-background development pre-review SHA-256 "
    "6287ad3ef734c91142637142f04abebfb7226253e9e49060af686fe07292eed4 "
    "and its recommendations. This authorizes test-first implementation, "
    "fixture and complete no-write validation, and freezing non-executable "
    "development-lane identities. It does not authorize executing the lane, "
    "changing source-finding science, PyBDSF or viewed-data execution, "
    "qualification, tuning, rescoring, cutover, or release."
)


def _json_bytes(value: object) -> bytes:
    """Return the exact checked-in JSON representation."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _document_sha256(value: object) -> str:
    """Hash one exact formatted JSON document before publication."""
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _require_approved_inputs(root: Path) -> None:
    """Fail closed if either approved upstream identity changes."""
    for path, expected, label in (
        (_PRE_REVIEW, _PRE_REVIEW_SHA256, "adaptive pre-review"),
        (_PUBLIC_IDENTITY, _PUBLIC_IDENTITY_SHA256, "public identity"),
    ):
        if file_sha256(root / path) != expected:
            raise ValueError(f"{label} changed")


def _expected_execution() -> dict[str, object]:
    """Return the exact path-independent shape of a future lane run."""
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


def build_implementation_decision(root: Path) -> dict[str, object]:
    """Build the exact record of the approved implementation scope."""
    _require_approved_inputs(root)
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
        "decision_id": (
            "phase-5-adaptive-background-development-implementation-decision"
        ),
        "exact_user_authority": _EXACT_AUTHORITY,
        "implementation": {
            name: {
                "path": str(path),
                "sha256": file_sha256(root / path),
            }
            for name, path in sorted(_PROGRAMS.items())
        },
        "implemented_contracts": [
            (
                "36 exact matrix cells expand to 144 seed-disjoint "
                "512-pixel inputs"
            ),
            (
                "noiseless composite templates are calibrated before "
                "adding noise"
            ),
            "candidate execution enters through hebog.find_sources",
            (
                "coarse control disables only adaptive background/RMS "
                "refinement"
            ),
            (
                "array-free truth, trigger, background, RMS, mask, flux, "
                "and topology summaries are retained"
            ),
            (
                "12 above-trigger inputs compare Serial with caller-owned "
                "existing-Dask execution"
            ),
            (
                "hard truth floors and per-image paired practical margins "
                "fail closed"
            ),
            (
                "verify-only validates all 300 planned executions without "
                "creating scratch or output"
            ),
            "the terminal decision is atomic and write-once",
        ],
        "pre_review": {
            "path": str(_PRE_REVIEW),
            "sha256": _PRE_REVIEW_SHA256,
        },
        "runtime": build_adaptive_runtime_identity(root),
        "schema_version": 1,
        "status": "implemented-and-validated-non-executable",
    }


def build_identity_review(
    root: Path,
    implementation: dict[str, object],
) -> dict[str, object]:
    """Build exact non-executable identities for a future one-use decision."""
    _require_approved_inputs(root)
    manifest = build_adaptive_development_manifest()
    manifest_document = manifest.model_dump(mode="json")
    manifest_sha256 = _document_sha256(manifest_document)
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
            "atomic_output": (
                "benchmark-results/phase-5/"
                "adaptive-background-development-decision.json"
            ),
            "candidate_executions": 144,
            "coarse_control_executions": 144,
            "existing_dask_executions": 12,
            "existing_dask_policy": (
                "caller-owned scheduler address; runner creates no cluster"
            ),
            "output_policy": (
                "one atomic write; never overwrite or adaptive-rerun"
            ),
            "required_workers": 2,
            "scratch": str(_SCRATCH),
            "total_finder_executions": 300,
        },
        "expected_execution": _expected_execution(),
        "expected_execution_sha256": canonical_sha256(_expected_execution()),
        "implementation_decision": {
            "path": str(_IMPLEMENTATION),
            "sha256": _document_sha256(implementation),
        },
        "identity_review_id": (
            "phase-5-adaptive-background-development-identity-review"
        ),
        "population": {
            "geometry_count": 12,
            "input_count": 144,
            "manifest_path": str(_MANIFEST),
            "manifest_sha256": manifest_sha256,
            "matrix_cell_count": 36,
            "total_finder_executions": 300,
        },
        "program_bindings": {
            name: {
                "path": str(path),
                "sha256": file_sha256(root / path),
            }
            for name, path in sorted(_PROGRAMS.items())
        },
        "review_binding": {
            "path": str(_PRE_REVIEW),
            "sha256": _PRE_REVIEW_SHA256,
        },
        "required_next_decision": (
            "obtain separate exact one-use approval bound to this identity "
            "review and expected execution"
        ),
        "runtime": build_adaptive_runtime_identity(root),
        "schema_version": 1,
        "status": "frozen-non-executable",
    }


def _write_once(path: Path, value: object) -> None:
    """Write one exact JSON identity without overwriting another review."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(_json_bytes(value))


def main() -> None:
    """Freeze the manifest, implementation decision, and identity review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    arguments = parser.parse_args()
    root = arguments.repository_root.resolve()
    output = arguments.output_root.resolve()
    implementation = build_implementation_decision(root)
    identity = build_identity_review(root, implementation)
    manifest = build_adaptive_development_manifest().model_dump(mode="json")
    destinations = (
        output / _MANIFEST,
        output / _IMPLEMENTATION,
        output / _IDENTITY,
    )
    existing = tuple(path for path in destinations if path.exists())
    if existing:
        raise FileExistsError(
            "refusing to overwrite adaptive development identity set: "
            + ", ".join(str(path) for path in existing)
        )
    for path, value in zip(
        destinations,
        (manifest, implementation, identity),
        strict=True,
    ):
        _write_once(path, value)
    print(f"manifest_sha256={_document_sha256(manifest)}")
    print(f"implementation_sha256={_document_sha256(implementation)}")
    print(f"identity_review_sha256={_document_sha256(identity)}")


if __name__ == "__main__":
    main()
