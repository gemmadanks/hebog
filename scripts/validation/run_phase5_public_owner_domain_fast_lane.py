#!/usr/bin/env python3
"""Run the Phase 5 version-8 public fast regression lane."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnusedFunction=false

from __future__ import annotations

import importlib
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from hebog import public_api
from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))
_base_module = importlib.import_module(
    "scripts.validation.run_phase5_source_owned_measurement_topology"
)
_base_runner = importlib.import_module(
    "scripts.validation.run_phase5_source_support_linkage_replication"
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
_MANIFEST = Path(
    "config/contracts/phase-5-source-support-linkage-replication-manifest.json"
)
_MANIFEST_SHA256 = (
    "8d5394770e592ad925201bdead76bd6821986d19473935bcf54c61466e1a7cb9"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-public-owner-domain-fast-lane-95cfc76"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/public-owner-domain-fast-lane-decision.json"
)
_CANDIDATE_REVISION = "95cfc76ded56556dc3ad6894410962d34f0d5604"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_PROGRAM_BINDING_PATHS = {
    "attribution": "src/hebog/validation/adaptive_background_diagnostics.py",
    "background_algorithm": "src/hebog/algorithms/background.py",
    "background_stage": "src/hebog/stages/background.py",
    "base_runner": (
        "scripts/validation/run_phase5_source_owned_measurement_topology.py"
    ),
    "component_topology": "src/hebog/algorithms/component_topology.py",
    "deblending": "src/hebog/algorithms/deblending.py",
    "detection_stage": "src/hebog/stages/detection.py",
    "freezer": (
        "scripts/validation/freeze_phase5_public_owner_domain_fast_lane.py"
    ),
    "lane_design": "src/hebog/validation/adaptive_background_development.py",
    "lane_evaluator": "src/hebog/validation/adaptive_background_lane.py",
    "mask_origin_sibling_pair": (
        "src/hebog/validation/mask_origin_sibling_pair.py"
    ),
    "measurement_algorithm": "src/hebog/algorithms/extended_measurement.py",
    "measurement_composition": "src/hebog/validation/products.py",
    "parent_runner": (
        "scripts/validation/run_phase5_adaptive_background_development.py"
    ),
    "public_api": "src/hebog/public_api.py",
    "public_science": "src/hebog/public_science.py",
    "replication_runner": (
        "scripts/validation/run_phase5_source_support_linkage_replication.py"
    ),
    "runner": "scripts/validation/run_phase5_public_owner_domain_fast_lane.py",
    "source_association": "src/hebog/algorithms/source_association.py",
    "source_association_model": "src/hebog/data_models/source_association.py",
}
_FIXTURE_BINDING_PATHS = {
    "component_topology": "tests/unit/test_component_topology.py",
    "deblending": "tests/unit/test_deblending.py",
    "executor_invariance": (
        "tests/integration/test_public_finder_correction_execution.py"
    ),
    "exact_notebook_runner": (
        "tests/integration/test_public_notebook_runner.py"
    ),
    "fast_lane": (
        "tests/unit/validation/test_public_owner_domain_fast_lane.py"
    ),
    "publication_owner_domain": (
        "tests/unit/validation/test_mask_origin_sibling_pair.py"
    ),
    "public_science": "tests/unit/test_public_science.py",
    "public_science_profile": "tests/unit/test_public_science_profile.py",
    "replication_lane": (
        "tests/unit/validation/test_source_support_linkage_replication_lane.py"
    ),
}

_BASE = vars(_base_runner)
_BASE_GLOBALS = cast(dict[str, Any], _BASE["verify_no_write"].__globals__)
_FIXTURE_CONTEXT = {"base": _BASE_GLOBALS["_verify_fixture_seams"]}


def _object_field(
    value: dict[str, Any], field: str, *, label: str
) -> dict[str, Any]:
    """Return one required nested JSON object."""
    nested: object = value.get(field)
    if not isinstance(nested, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], nested)


def _verify_public_owner_domain_identity(
    repository_root: Path,
    identity: dict[str, Any],
) -> None:
    """Verify the exact version-8 public composition and source files."""
    binding = _object_field(
        identity,
        "public_identity",
        label="public owner-domain identity binding",
    )
    if binding != {
        "path": str(_PUBLIC_IDENTITY),
        "sha256": _PUBLIC_IDENTITY_SHA256,
    } or file_sha256(repository_root / _PUBLIC_IDENTITY) != (
        _PUBLIC_IDENTITY_SHA256
    ):
        raise ValueError("public owner-domain identity changed")
    review = _BASE_GLOBALS["_json_object"](
        repository_root / _PUBLIC_IDENTITY,
        label="public owner-domain identity",
    )
    expected_candidate = {
        "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
    }
    if (
        review.get("status") != "frozen-non-executable"
        or review.get("algorithm_candidate") != expected_candidate
        or review.get("scientific_composition") != public_api._COMPOSITION_NAME
        or review.get("scientific_composition_sha256")
        != public_api._scientific_composition_sha256()
    ):
        raise ValueError("public owner-domain candidate changed")
    interface_files = _object_field(
        review,
        "interface_file_sha256",
        label="public owner-domain source bindings",
    )
    for relative_path, expected_sha256 in interface_files.items():
        if file_sha256(repository_root / relative_path) != expected_sha256:
            raise ValueError("public owner-domain source changed")


def _verify_fast_lane_identity(
    repository_root: Path,
    identity: dict[str, Any],
) -> None:
    """Verify the new candidate and the successful predecessor lane."""
    authorization = _object_field(
        identity,
        "authorization",
        label="public fast-lane authorization",
    )
    expected_candidate = {
        "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "entrypoint": "hebog.find_sources",
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
    }
    if (
        identity.get("status") != "frozen-non-executable"
        or set(authorization.values()) != {False}
        or identity.get("candidate") != expected_candidate
    ):
        raise ValueError("public fast-lane candidate changed")
    predecessor = _object_field(
        identity,
        "predecessor_fast_lane",
        label="public fast-lane predecessor",
    )
    if predecessor != {
        "identity": {
            "path": str(_PREDECESSOR_IDENTITY),
            "sha256": _PREDECESSOR_IDENTITY_SHA256,
        },
        "terminal_sha256": _PREDECESSOR_TERMINAL_SHA256,
        "status": "pass",
    } or file_sha256(repository_root / _PREDECESSOR_IDENTITY) != (
        _PREDECESSOR_IDENTITY_SHA256
    ):
        raise ValueError("public fast-lane predecessor changed")


def _fixture_seams() -> str:
    """Extend the passing replication seam with version-8 provenance."""
    predecessor_sha256 = cast(str, _FIXTURE_CONTEXT["base"]())
    return canonical_sha256(
        {
            "predecessor_fixture_seam_sha256": predecessor_sha256,
            "public_identity_sha256": _PUBLIC_IDENTITY_SHA256,
            "scientific_composition": public_api._COMPOSITION_NAME,
            "scientific_composition_sha256": (
                public_api._scientific_composition_sha256()
            ),
        }
    )


_OVERLAY_GLOBALS = {
    "_CANDIDATE_CONFIGURATION_SHA256": _CANDIDATE_CONFIGURATION_SHA256,
    "_CANDIDATE_REVISION": _CANDIDATE_REVISION,
    "_CANDIDATE_SOURCE_TREE_SHA256": _CANDIDATE_SOURCE_TREE_SHA256,
    "_EXECUTION_DECISION": _EXECUTION_DECISION,
    "_FIXTURE_BINDING_PATHS": _FIXTURE_BINDING_PATHS,
    "_IDENTITY": _IDENTITY,
    "_IMPLEMENTATION": _IMPLEMENTATION,
    "_MANIFEST": _MANIFEST,
    "_MANIFEST_SHA256": _MANIFEST_SHA256,
    "_OUTPUT": _OUTPUT,
    "_PREDECESSOR_IDENTITY": _PREDECESSOR_IDENTITY,
    "_PREDECESSOR_IDENTITY_SHA256": _PREDECESSOR_IDENTITY_SHA256,
    "_PROGRAM_BINDING_PATHS": _PROGRAM_BINDING_PATHS,
    "_PUBLIC_IDENTITY": _PUBLIC_IDENTITY,
    "_SCRATCH": _SCRATCH,
    "_verify_fixture_seams": _fixture_seams,
    "_verify_public_identity": _verify_public_owner_domain_identity,
    "_verify_source_support_linkage_identity": _verify_fast_lane_identity,
}


@contextmanager
def _configured_base() -> Generator[dict[str, Any]]:
    """Rebuild, configure, and later restore the proven base runner."""
    previous_base = dict(_BASE_GLOBALS)
    previous_runner = dict(_BASE)
    previous_fixture_seams = _FIXTURE_CONTEXT["base"]
    try:
        importlib.reload(_base_module)
        importlib.reload(_base_runner)
        configured_runner = vars(_base_runner)
        configured_globals = cast(
            dict[str, Any],
            configured_runner["verify_no_write"].__globals__,
        )
        _FIXTURE_CONTEXT["base"] = configured_globals["_verify_fixture_seams"]
        configured_globals.update(_OVERLAY_GLOBALS)
        yield configured_runner
    finally:
        _BASE.clear()
        _BASE.update(previous_runner)
        _BASE_GLOBALS.clear()
        _BASE_GLOBALS.update(previous_base)
        _FIXTURE_CONTEXT["base"] = previous_fixture_seams


_EXPECTED_EXECUTION_AUTHORIZATION = _BASE_GLOBALS[
    "_EXPECTED_EXECUTION_AUTHORIZATION"
]


def verify_no_write(*args: Any, **kwargs: Any) -> dict[str, object]:
    """Verify the lane without leaking overlay state to other runners."""
    with _configured_base() as configured:
        return cast(
            dict[str, object],
            configured["verify_no_write"](*args, **kwargs),
        )


def _expected_execution() -> dict[str, object]:
    """Return this lane's execution shape without persistent mutation."""
    with _configured_base() as configured:
        return cast(dict[str, object], configured["_expected_execution"]())


def main() -> None:
    """Use the proven CLI after retargeting every version-8 binding."""
    with _configured_base() as configured:
        configured["main"]()


if __name__ == "__main__":
    main()
