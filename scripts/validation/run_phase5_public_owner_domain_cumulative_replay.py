#!/usr/bin/env python3
"""Verify or run the version-8 public cumulative candidate stage."""

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

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_base_module = importlib.import_module(
    "scripts.validation.run_phase5_final_cumulative_current_replay"
)
_validated_module = importlib.import_module(
    "scripts.validation."
    "run_phase5_final_cumulative_current_replay_validated_retry"
)

_EXECUTION_ROOT = Path(
    "/private/tmp/hebog-phase5-public-owner-domain-cumulative-replay"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-public-owner-domain-cumulative-95cfc76"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/public-owner-domain-cumulative-product-set.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/phase-5-public-owner-domain-cumulative-replay-"
    "implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-public-owner-domain-cumulative-replay-"
    "identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-public-owner-domain-cumulative-replay-"
    "execution-decision.json"
)
_FAST_TERMINAL = Path(
    "benchmark-results/phase-5/public-owner-domain-fast-lane-decision.json"
)
_FAST_TERMINAL_SHA256 = (
    "a274888dab12bd5a1623310b35ba3f9a90ff14f9fd5249d118cd2a1c8b778348"
)
_PROCESS_REVIEW_SHA256 = (
    "f67d74c05af40ff509562583bc7dca51fbb2d7dbc29bff581a03f20f4cf2ab39"
)
_TYPE_CLEAN_REVIEW_SHA256 = (
    "853fe3982fc6e098ab2a3b1e986a9853b0ebac57cbcee6a7f174033d119c62b1"
)
_SINGLE_SCAN_REVIEW_SHA256 = (
    "8d4848d265aaf07bb858856d05c984dc8a33b128b0f6d3e67d73f9b322c5dffa"
)
_JSON_FORMAT_REVIEW_SHA256 = (
    "ab96bacf3625aa5942a51080affeb7ea3d31687aaaff5a4dbcf74e2fe20decc6"
)
_CANDIDATE = {
    "configuration_sha256": (
        "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
    ),
    "revision": "95cfc76ded56556dc3ad6894410962d34f0d5604",
    "source_tree_sha256": (
        "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
    ),
}
_PROGRAM_PATHS = {
    "base_runner": (
        "scripts/validation/run_phase5_final_cumulative_current_replay.py"
    ),
    "freezer": (
        "scripts/validation/"
        "freeze_phase5_public_owner_domain_cumulative_replay.py"
    ),
    "materializer": (
        "scripts/validation/materialize_phase5_prospective_paired_products.py"
    ),
    "predecessor_runner": (
        "scripts/validation/"
        "run_phase5_final_cumulative_current_replay_validated_retry.py"
    ),
    "runner": (
        "scripts/validation/"
        "run_phase5_public_owner_domain_cumulative_replay.py"
    ),
    "smoke_evaluator": (
        "scripts/validation/evaluate_phase5_prospective_science_smoke.py"
    ),
    "topology_evaluator": (
        "scripts/validation/"
        "evaluate_phase5_prospective_paired_cumulative_topology_repair.py"
    ),
}
_FIXTURE_PATHS = {
    "current_replay": (
        "tests/unit/validation/"
        "test_final_cumulative_current_replay_validated_retry.py"
    ),
    "paired_materializer": (
        "tests/unit/validation/test_prospective_paired_cumulative_replay.py"
    ),
    "public_fast_lane": (
        "tests/unit/validation/test_public_owner_domain_fast_lane.py"
    ),
    "public_owner_domain_replay": (
        "tests/unit/validation/test_public_owner_domain_cumulative_replay.py"
    ),
    "topology_completion": (
        "tests/unit/validation/"
        "test_prospective_paired_topology_repair_completion.py"
    ),
}

_BASE_GLOBALS = vars(_base_module)
_VALIDATED_GLOBALS = vars(_validated_module)
_EXPECTED_AUTHORIZATION = cast(
    dict[str, bool], _BASE_GLOBALS["_EXPECTED_AUTHORIZATION"]
)


def _require_authority(root: Path) -> None:
    """Require the exact one-use version-8 cumulative decision."""
    decision = _validated_module._load_json(
        root / _EXECUTION_DECISION,
        label="public owner-domain cumulative execution decision",
    )
    identity = _validated_module._load_json(
        root / _IDENTITY,
        label="public owner-domain cumulative identity review",
    )
    expected_sha256 = canonical_sha256(_base_module._expected_execution())
    if (
        decision.get("status")
        != "authorized-for-one-public-owner-domain-cumulative-replay"
        or decision.get("authorization") != _EXPECTED_AUTHORIZATION
        or decision.get("identity_review_sha256")
        != file_sha256(root / _IDENTITY)
        or decision.get("expected_execution_sha256") != expected_sha256
        or identity.get("expected_execution_sha256") != expected_sha256
        or decision.get("process_review_sha256") != _PROCESS_REVIEW_SHA256
        or decision.get("type_clean_review_sha256")
        != _TYPE_CLEAN_REVIEW_SHA256
        or decision.get("single_scan_review_sha256")
        != _SINGLE_SCAN_REVIEW_SHA256
        or decision.get("json_format_review_sha256")
        != _JSON_FORMAT_REVIEW_SHA256
    ):
        raise PermissionError(
            "public owner-domain cumulative replay authority changed"
        )


@contextmanager
def _configured_runner() -> Generator[dict[str, Any]]:
    """Apply version-8 bindings for one call and restore module state."""
    previous_base = dict(_BASE_GLOBALS)
    previous_validated = dict(_VALIDATED_GLOBALS)
    try:
        importlib.reload(_base_module)
        importlib.reload(_validated_module)
        base_globals = vars(_base_module)
        validated_globals = vars(_validated_module)
        base_globals.update(
            {
                "_CANDIDATE_CONFIGURATION_SHA256": (
                    _CANDIDATE["configuration_sha256"]
                ),
                "_CANDIDATE_REVISION": _CANDIDATE["revision"],
                "_CANDIDATE_SOURCE_TREE_SHA256": (
                    _CANDIDATE["source_tree_sha256"]
                ),
                "_EXECUTION_ROOT": _EXECUTION_ROOT,
                "_FAST_TERMINAL": _FAST_TERMINAL,
                "_FAST_TERMINAL_SHA256": _FAST_TERMINAL_SHA256,
                "_OUTPUT": _OUTPUT,
                "_SCRATCH": _SCRATCH,
            }
        )
        validated_globals.update(
            {
                "_EXECUTION_DECISION": _EXECUTION_DECISION,
                "_FIXTURE_PATHS": _FIXTURE_PATHS,
                "_IDENTITY": _IDENTITY,
                "_IMPLEMENTATION": _IMPLEMENTATION,
                "_PROGRAM_PATHS": _PROGRAM_PATHS,
                "_require_authority": _require_authority,
            }
        )
        yield {"base": _base_module, "validated": _validated_module}
    finally:
        _VALIDATED_GLOBALS.clear()
        _VALIDATED_GLOBALS.update(previous_validated)
        _BASE_GLOBALS.clear()
        _BASE_GLOBALS.update(previous_base)


def _expected_execution() -> dict[str, object]:
    """Return the exact fresh cumulative execution shape."""
    with _configured_runner() as configured:
        base = configured["base"]
        return cast(dict[str, object], base._expected_execution())


def verify_no_write(*args: Any, **kwargs: Any) -> dict[str, object]:
    """Verify all inputs and process seams without persistent mutation."""
    with _configured_runner() as configured:
        validated = configured["validated"]
        return cast(
            dict[str, object], validated.verify_no_write(*args, **kwargs)
        )


def main() -> None:
    """Use the proven single-scan CLI with version-8 bindings."""
    with _configured_runner() as configured:
        configured["validated"].main()


if __name__ == "__main__":
    main()
