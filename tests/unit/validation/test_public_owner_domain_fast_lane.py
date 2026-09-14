"""Contracts for the Phase 5 version-8 public fast regression lane."""

from __future__ import annotations

import importlib
import json
import os
import runpy
import subprocess
import sys
from argparse import Namespace
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, patch

from manifest_comparison import assert_regenerated_manifest_matches_snapshot

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
        "path": _PUBLIC_IDENTITY.relative_to(_ROOT).as_posix(),
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


def _runtime_fixture(root: Path, identity: dict[str, Any]) -> dict[str, Any]:
    """Check runtime files and explicitly simulate installed versions."""
    from hebog.validation.adaptive_background_lane import (  # noqa: PLC0415
        build_adaptive_runtime_identity,
    )

    actual = build_adaptive_runtime_identity(root)
    expected = cast(dict[str, Any], identity["runtime"])
    assert actual["source_files"] == expected["source_files"]
    return expected


def _historical_preflight_probe(
    root: Path,
    manifest_path: Path,
    identity_path: Path,
    scratch: Path,
    output: Path,
) -> dict[str, Any]:
    """Run in the isolated historical import process, never execute finders."""
    from hebog.validation.adaptive_background_lane import (  # noqa: PLC0415
        build_adaptive_replication_manifest,
    )
    from hebog.validation.datasets import DatasetManifest  # noqa: PLC0415

    identity = _object(identity_path)
    runtime = _runtime_fixture(root, identity)
    manifest = DatasetManifest.model_validate_json(manifest_path.read_bytes())
    assert_regenerated_manifest_matches_snapshot(
        build_adaptive_replication_manifest().model_dump(mode="json"),
        manifest.model_dump(mode="json"),
    )
    runner = importlib.import_module(
        "scripts.validation.run_phase5_public_owner_domain_fast_lane"
    )
    with runner._configured_base() as configured:
        context = configured["verify_no_write"].__globals__
        tasks_context = context["_parent_tasks"].__globals__
        # Prove the real guard still rejects each changed installed identity.
        for field in (
            "python_version",
            "python_implementation",
            "dependency_inventory_sha256",
        ):
            changed = deepcopy(runtime)
            changed["installed"][field] = "different"
            with patch.dict(
                context,
                {
                    "build_adaptive_runtime_identity": Mock(
                        return_value=changed
                    ),
                },
            ):
                try:
                    context["_verify_frozen_identity"](
                        root, manifest_path, identity
                    )
                except ValueError as error:
                    assert str(error) == "combined runtime changed"
                else:
                    raise AssertionError("runtime drift was accepted")
        # Raw file hashes remain exact. Only the already-compared in-memory
        # truth positions and installed runtime become test fixtures here.
        with (
            patch.dict(
                context,
                {
                    "build_adaptive_runtime_identity": Mock(
                        return_value=runtime
                    ),
                },
            ),
            patch.dict(
                tasks_context,
                {
                    "build_adaptive_replication_manifest": Mock(
                        return_value=manifest
                    ),
                },
            ),
        ):
            result = configured["verify_no_write"](
                repository_root=root,
                manifest_path=manifest_path,
                identity_path=identity_path,
                scratch=scratch,
                output=output,
                enforce_execution_paths=False,
                verify_process_pool=False,
            )
    return {**result, "historical_runtime_is_fixture": True}


def _historical_freezer_probe(
    root: Path,
    output: Path,
    identity_path: Path,
) -> None:
    """Reproduce frozen metadata, not a new identity for the CI runtime."""
    identity = _object(identity_path)
    runtime = _runtime_fixture(root, identity)
    program = runpy.run_path(str(root / _FREEZER.relative_to(_ROOT)))
    with patch.dict(
        program["build_identity"].__globals__,
        {
            "build_adaptive_runtime_identity": Mock(return_value=runtime),
        },
    ):
        program["freeze_records"](
            Namespace(
                repository_root=root,
                output_root=output,
            )
        )


def _run_historical_probe(
    root: Path,
    probe: Callable[..., object],
    *arguments: Path,
) -> subprocess.CompletedProcess[str]:
    """Expose child stderr and keep frozen imports out of current tests."""
    checked = subprocess.run(
        (
            sys.executable,
            "-c",
            "import json, runpy, sys; from pathlib import Path; "
            "sys.path.insert(0, str(Path(sys.argv[1]).parent)); "
            "program = runpy.run_path(sys.argv[1]); "
            "print(json.dumps(program[sys.argv[2]]("
            "Path.cwd(), *(Path(value) for value in sys.argv[3:]))))",
            str(Path(__file__).resolve()),
            probe.__name__,
            *(str(argument) for argument in arguments),
        ),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
    )
    assert checked.returncode == 0, checked.stderr
    return checked


def test_complete_no_write_preflight_uses_an_isolated_namespace(
    tmp_path: Path,
    frozen_campaign_root: Path,
) -> None:
    """Exercise 300 planned executions with explicit historical fixtures.

    This is portable no-write control flow, not runtime execution eligibility.
    The real runtime guard rejects drift independently in the child process.
    """
    scratch = tmp_path / "scratch"
    output = tmp_path / "decision.json"
    checked = _run_historical_probe(
        frozen_campaign_root,
        _historical_preflight_probe,
        frozen_campaign_root / _MANIFEST.relative_to(_ROOT),
        frozen_campaign_root / _IDENTITY.relative_to(_ROOT),
        scratch,
        output,
    )
    result = json.loads(checked.stdout)
    assert result["status"] == "pass"
    assert result["historical_runtime_is_fixture"] is True
    assert result["candidate_execution_count"] == 144
    assert result["coarse_control_execution_count"] == 144
    assert result["existing_dask_execution_count"] == 12
    assert result["candidate_execution_started"] is False
    assert not scratch.exists()
    assert not output.exists()


def test_freezer_reproduces_all_frozen_records(
    tmp_path: Path,
    frozen_campaign_root: Path,
) -> None:
    """Reproduce exact records using an explicit historical runtime fixture."""
    _run_historical_probe(
        frozen_campaign_root,
        _historical_freezer_probe,
        tmp_path,
        frozen_campaign_root / _IDENTITY.relative_to(_ROOT),
    )
    for path in (_IMPLEMENTATION, _IDENTITY, _DECISION):
        reproduced = tmp_path / path.relative_to(_ROOT)
        assert reproduced.read_bytes() == path.read_bytes()
