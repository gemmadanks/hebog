#!/usr/bin/env python3
"""Freeze the source-owned support-linkage development-lane repair."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import copy
import runpy
from pathlib import Path
from typing import cast

from hebog.validation.external_runners import file_sha256, source_tree_sha256

_ROOT_REVIEW = Path(
    "config/contracts/phase-5-source-owned-footprint-guard-lane-"
    "root-cause-review.json"
)
_ROOT_REVIEW_SHA256 = (
    "07a73bfd07f483624ec017b739ec6d0222a57a18a9f4b729640e626da0c648bf"
)
_PREDECESSOR_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "footprint-guard-identity-review.json"
)
_PREDECESSOR_IDENTITY_SHA256 = (
    "d74d0fba79c689f6d3b1e857fd900c14d8c4138a22cbf31fe9ac29e9594486b8"
)
_PREDECESSOR_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "footprint-guard-public-interface-identity-review.json"
)
_PREDECESSOR_PUBLIC_IDENTITY_SHA256 = (
    "73157afa614b99fb6507f80df3ebc146f5585542160fcbc300910550464b659e"
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
_PARENT_FREEZER = Path(
    "scripts/validation/"
    "freeze_phase5_source_owned_measurement_topology_footprint_guard.py"
)
_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-public-interface-identity-review.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-execution-decision.json"
)
_CANDIDATE_REVISION = "2e25cdf8bb0fbd739bba330ff20d9f798f95bf44"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "3da083b0a720fe0104fa51e135f224a2456b49bd49d85cd6a449fccb93805e8a"
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

_PARENT = runpy.run_path(str(Path(__file__).parents[2] / _PARENT_FREEZER))
_PARENT_GLOBALS = _PARENT["build_identity"].__globals__
_json_bytes = _PARENT["_json_bytes"]
_document_sha256 = _PARENT["_document_sha256"]
_json_object = _PARENT["_json_object"]


def _configure_parent() -> None:
    """Retarget the established freezer mechanics to this fresh successor."""
    _PARENT_GLOBALS.update(
        {
            "_ROOT_REVIEW": _ROOT_REVIEW,
            "_ROOT_REVIEW_SHA256": _ROOT_REVIEW_SHA256,
            "_PREDECESSOR_IDENTITY": _PREDECESSOR_IDENTITY,
            "_PREDECESSOR_IDENTITY_SHA256": _PREDECESSOR_IDENTITY_SHA256,
            "_PREDECESSOR_PUBLIC_IDENTITY": _PREDECESSOR_PUBLIC_IDENTITY,
            "_PREDECESSOR_PUBLIC_IDENTITY_SHA256": (
                _PREDECESSOR_PUBLIC_IDENTITY_SHA256
            ),
            "_MANIFEST": _MANIFEST,
            "_MANIFEST_SHA256": _MANIFEST_SHA256,
            "_RUNNER": _RUNNER,
            "_PUBLIC_IDENTITY": _PUBLIC_IDENTITY,
            "_IMPLEMENTATION": _IMPLEMENTATION,
            "_IDENTITY": _IDENTITY,
            "_EXECUTION_DECISION": _EXECUTION_DECISION,
            "_CANDIDATE_REVISION": _CANDIDATE_REVISION,
            "_CANDIDATE_SOURCE_TREE_SHA256": (_CANDIDATE_SOURCE_TREE_SHA256),
            "_CANDIDATE_CONFIGURATION_SHA256": (
                _CANDIDATE_CONFIGURATION_SHA256
            ),
            "_EXACT_AUTHORITY": _EXACT_AUTHORITY,
        }
    )


def _require_inputs(root: Path) -> None:
    """Require the exact failed predecessor and prospective repair review."""
    for path, expected_sha256 in (
        (_ROOT_REVIEW, _ROOT_REVIEW_SHA256),
        (_PREDECESSOR_IDENTITY, _PREDECESSOR_IDENTITY_SHA256),
        (
            _PREDECESSOR_PUBLIC_IDENTITY,
            _PREDECESSOR_PUBLIC_IDENTITY_SHA256,
        ),
        (_MANIFEST, _MANIFEST_SHA256),
    ):
        if file_sha256(root / path) != expected_sha256:
            raise ValueError(f"source-support-linkage input changed: {path}")
    if source_tree_sha256(root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError(
            "source-support-linkage scientific source tree changed"
        )


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


def build_public_identity(root: Path) -> dict[str, object]:
    """Bind unchanged finder science and corrected evaluator linkage."""
    _configure_parent()
    identity = cast(dict[str, object], _PARENT["build_public_identity"](root))
    predecessor = _json_object(root / _PREDECESSOR_PUBLIC_IDENTITY)
    identity["footprint_guard_correction"] = copy.deepcopy(
        predecessor["footprint_guard_correction"]
    )
    identity["source_support_linkage_repair"] = {
        "linkage": "exact-source-owned-support-intersects-analytic-truth",
        "root_cause_review": {
            "path": str(_ROOT_REVIEW),
            "sha256": _ROOT_REVIEW_SHA256,
        },
        "source_finding_science_changed": False,
        "unmatched_reliability_retained": True,
    }
    identity["review_id"] = (
        "phase-5-source-owned-measurement-topology-source-support-linkage-"
        "public-interface-identity-review"
    )
    return identity


def build_implementation(
    root: Path,
    public_identity: dict[str, object],
    programs: dict[str, str],
    fixtures: dict[str, str],
) -> dict[str, object]:
    """Record the validation-only repair without execution authority."""
    _configure_parent()
    implementation = cast(
        dict[str, object],
        _PARENT["build_implementation"](
            root,
            public_identity,
            programs,
            fixtures,
        ),
    )
    implementation["decision_id"] = (
        "phase-5-source-owned-measurement-topology-source-support-linkage-"
        "implementation-decision"
    )
    implementation["fixture_evidence"] = {
        "affected_tests_passed": 33,
        "process_errors": 0,
        "test_first_regression_confirmed": True,
    }
    implementation["implemented_contracts"] = [
        (
            "analytic truth linkage requires exact intersection with the "
            "source-owned component-label support"
        ),
        (
            "nearby and remote zero-overlap catalogue rows remain explicit "
            "array-free unmatched-source reliability evidence"
        ),
        (
            "truth, source labels, and label-to-public-source mappings fail "
            "closed when malformed, negative, duplicate, or incomplete"
        ),
        (
            "source-finding science, population, thresholds, paired margins, "
            "and Serial/existing-Dask identity requirements are unchanged"
        ),
        (
            "dual-PyBDSF parity and incumbent retention remain mandatory in "
            "cumulative replay and seed-disjoint held-out qualification"
        ),
    ]
    return implementation


def build_identity(
    root: Path,
    public_identity: dict[str, object],
    implementation: dict[str, object],
    expected_execution: dict[str, object],
) -> dict[str, object]:
    """Freeze the corrected lane separately from one-use authorization."""
    _configure_parent()
    identity = cast(
        dict[str, object],
        _PARENT["build_identity"](
            root,
            public_identity,
            implementation,
            expected_execution,
        ),
    )
    identity.pop("footprint_guard_correction", None)
    identity["source_support_linkage_repair"] = {
        "root_cause_review": {
            "path": str(_ROOT_REVIEW),
            "sha256": _ROOT_REVIEW_SHA256,
        }
    }
    identity["identity_review_id"] = (
        "phase-5-source-owned-measurement-topology-source-support-linkage-"
        "identity-review"
    )
    return identity


def build_execution_decision(
    root: Path,
    identity: dict[str, object],
    expected_execution: dict[str, object],
) -> dict[str, object]:
    """Bind standing user authority to one exact corrected fast lane."""
    _configure_parent()
    decision = cast(
        dict[str, object],
        _PARENT["build_execution_decision"](
            root,
            identity,
            expected_execution,
        ),
    )
    decision["decision_id"] = (
        "phase-5-source-owned-measurement-topology-source-support-linkage-"
        "execution-decision"
    )
    return decision


def freeze_records(arguments: argparse.Namespace) -> None:
    """Build and atomically create all four successor records."""
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
        raise FileExistsError(
            "refusing to overwrite source-support-linkage records"
        )
    for destination, (_, document) in zip(
        destinations, documents, strict=True
    ):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(_json_bytes(document))
    for path, document in documents:
        print(f"{path.name}_sha256={_document_sha256(document)}")


def main() -> None:
    """Parse roots and freeze the authorized source-linkage successor."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    freeze_records(parser.parse_args())


if __name__ == "__main__":
    main()
