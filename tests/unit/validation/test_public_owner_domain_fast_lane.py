"""Contracts for the Phase 5 version-8 public fast regression lane."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
)

_ROOT = Path(__file__).parents[3]
_RUNNER = (
    _ROOT / "scripts/validation/run_phase5_public_owner_domain_fast_lane.py"
)
_FREEZER = (
    _ROOT / "scripts/validation/freeze_phase5_public_owner_domain_fast_lane.py"
)
_IDENTITY = (
    _ROOT / "config/contracts/phase-5-public-owner-domain-fast-lane-"
    "identity-review.json"
)
_IMPLEMENTATION = _ROOT / (
    "config/contracts/phase-5-public-owner-domain-fast-lane-"
    "implementation-decision.json"
)
_DECISION = _ROOT / (
    "config/contracts/phase-5-public-owner-domain-fast-lane-"
    "execution-decision.json"
)
_PUBLIC_IDENTITY = _ROOT / (
    "config/contracts/phase-5-public-publication-owner-domain-"
    "identity-review.json"
)
_MANIFEST = _ROOT / (
    "config/contracts/phase-5-source-support-linkage-replication-manifest.json"
)
_CANDIDATE = {
    "configuration_sha256": (
        "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
    ),
    "entrypoint": "hebog.find_sources",
    "revision": "95cfc76ded56556dc3ad6894410962d34f0d5604",
    "source_tree_sha256": (
        "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
    ),
}


def _object(path: Path) -> dict[str, Any]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_runner_targets_the_exact_version_eight_candidate() -> None:
    """The fast lane must exercise the candidate used by the notebook."""
    runner = runpy.run_path(str(_RUNNER))

    assert runner["_CANDIDATE_REVISION"] == _CANDIDATE["revision"]
    assert (
        runner["_CANDIDATE_SOURCE_TREE_SHA256"]
        == (_CANDIDATE["source_tree_sha256"])
    )
    assert runner["_PUBLIC_IDENTITY"] == _PUBLIC_IDENTITY.relative_to(_ROOT)
    expected = runner["_expected_execution"]()
    assert expected["candidate_executions"] == 144
    assert expected["coarse_control_executions"] == 144
    assert expected["existing_dask_executions"] == 12
    assert expected["workers"] == 2


def test_identity_is_non_executable_and_binds_current_repairs() -> None:
    """The frozen lane must bind all current source-changing corrections."""
    identity = _object(_IDENTITY)

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["candidate"] == _CANDIDATE
    assert identity["public_identity"] == {
        "path": str(_PUBLIC_IDENTITY.relative_to(_ROOT)),
        "sha256": file_sha256(_PUBLIC_IDENTITY),
    }
    assert identity["predecessor_fast_lane"]["terminal_sha256"] == (
        "0978d4a3653ce9bd4b1244ea1125142400607d04c330758ee3b4a495f4193eae"
    )
    required_programs = {
        "component_topology",
        "deblending",
        "mask_origin_sibling_pair",
        "public_science",
        "runner",
    }
    assert required_programs <= set(identity["program_bindings"])


def test_decision_authorizes_only_one_two_worker_fast_lane() -> None:
    """The separate decision must not authorize replay or qualification."""
    runner = runpy.run_path(str(_RUNNER))
    identity = _object(_IDENTITY)
    decision = _object(_DECISION)

    assert decision["status"] == "authorized-for-one-development-lane"
    assert decision["workers"] == 2
    assert (
        decision["authorization"]
        == (runner["_EXPECTED_EXECUTION_AUTHORIZATION"])
    )
    assert decision["identity_review_sha256"] == file_sha256(_IDENTITY)
    assert decision["expected_execution_sha256"] == canonical_sha256(
        identity["expected_execution"]
    )
    assert decision["authorization"]["replay_authorized"] is False
    assert decision["authorization"]["fresh_qualification_authorized"] is False


def test_complete_no_write_preflight_uses_an_isolated_namespace(
    tmp_path: Path,
) -> None:
    """All 300 executions must verify before any output is created."""
    runner = runpy.run_path(str(_RUNNER))
    scratch = tmp_path / "scratch"
    output = tmp_path / "decision.json"

    result = runner["verify_no_write"](
        repository_root=_ROOT,
        manifest_path=_MANIFEST,
        identity_path=_IDENTITY,
        scratch=scratch,
        output=output,
        enforce_execution_paths=False,
        verify_process_pool=False,
    )

    assert result["status"] == "pass"
    assert result["candidate_execution_count"] == 144
    assert result["coarse_control_execution_count"] == 144
    assert result["existing_dask_execution_count"] == 12
    assert result["candidate_execution_started"] is False
    assert not scratch.exists()
    assert not output.exists()


def test_freezer_reproduces_all_frozen_records(tmp_path: Path) -> None:
    """The freezer must deterministically reproduce every exact record."""
    freezer = runpy.run_path(str(_FREEZER))
    arguments = type(
        "Arguments",
        (),
        {"repository_root": _ROOT, "output_root": tmp_path},
    )()

    freezer["freeze_records"](arguments)

    for path in (_IMPLEMENTATION, _IDENTITY, _DECISION):
        reproduced = tmp_path / path.relative_to(_ROOT)
        assert reproduced.read_bytes() == path.read_bytes()
