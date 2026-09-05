"""Contracts for the source-support-linkage repair replication lane."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from typing import Any, cast

import pytest

from hebog.validation.adaptive_background_lane import (
    build_adaptive_replication_manifest,
)
from hebog.validation.datasets import iter_dataset_recipes
from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_RUNNER = (
    _ROOT
    / "scripts/validation/run_phase5_source_support_linkage_replication.py"
)
_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_source_support_linkage_replication_validated_retry.py"
)
_PREFIX = "phase-5-source-support-linkage-replication"
_MANIFEST = _ROOT / f"config/contracts/{_PREFIX}-manifest.json"
_PUBLIC_IDENTITY = (
    _ROOT / f"config/contracts/{_PREFIX}-public-interface-identity-review.json"
)
_IMPLEMENTATION = _ROOT / (
    f"config/contracts/{_PREFIX}-validated-retry-implementation-decision.json"
)
_IDENTITY = (
    _ROOT / f"config/contracts/{_PREFIX}-validated-retry-identity-review.json"
)
_DECISION = (
    _ROOT
    / f"config/contracts/{_PREFIX}-validated-retry-execution-decision.json"
)
_FAILED_IDENTITY = (
    _ROOT / f"config/contracts/{_PREFIX}-binding-repair-identity-review.json"
)
_FAILED_DECISION = (
    _ROOT
    / f"config/contracts/{_PREFIX}-binding-repair-execution-decision.json"
)


def _object(path: Path) -> dict[str, Any]:
    """Load one checked-in JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_manifest_is_the_exact_seed_disjoint_replication() -> None:
    """Checked-in inputs match the pure fresh-population builder."""
    actual = _object(_MANIFEST)
    expected = build_adaptive_replication_manifest().model_dump(mode="json")
    seeds = tuple(
        recipe.seed
        for dataset in build_adaptive_replication_manifest().datasets
        for recipe in iter_dataset_recipes(dataset)
    )

    assert actual == expected
    assert len(seeds) == 144
    assert seeds == tuple(range(2026952001, 2026952145))
    assert file_sha256(_MANIFEST) == (
        "8d5394770e592ad925201bdead76bd6821986d19473935bcf54c61466e1a7cb9"
    )


def test_identity_is_non_executable_and_preserves_candidate_science() -> None:
    """The fresh lane changes evidence, not Hebog's scientific candidate."""
    identity = _object(_IDENTITY)

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["candidate"] == {
        "configuration_sha256": (
            "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
        ),
        "entrypoint": "hebog.find_sources",
        "revision": "0b9e13299f3fbbd42af0dea4f70155a802a8441d",
        "source_tree_sha256": (
            "11307db0059739d473288dd2ed647970cce43b69e874632e1d1f14ee0ed032df"
        ),
    }
    assert identity["population"]["manifest_sha256"] == file_sha256(_MANIFEST)
    assert identity["prospective_replication"]["binding_statistic"] == (
        "paired-median-within-each-four-seed-trigger-cell"
    )
    assert identity["prospective_replication"]["tail_policy"] == (
        "maximum-per-image-movements-remain-visible-and-non-binding"
    )
    assert identity["predecessor_identity"] == {
        "path": (
            f"config/contracts/{_PREFIX}-binding-repair-identity-review.json"
        ),
        "sha256": file_sha256(_FAILED_IDENTITY),
    }
    assert identity["process_repair"]["superseded_identity"] == {
        "decision": {
            "path": (
                f"config/contracts/{_PREFIX}-binding-repair-"
                "execution-decision.json"
            ),
            "sha256": file_sha256(_FAILED_DECISION),
        },
        "execution_started": False,
        "reason": "bound freezer required lint-only formatting",
    }


def test_one_use_decision_binds_only_the_fast_replication() -> None:
    """Broader replay authority stays prospective until this lane passes."""
    runner = runpy.run_path(str(_RUNNER))
    identity = _object(_IDENTITY)
    decision = _object(_DECISION)

    assert decision["status"] == "authorized-for-one-development-lane"
    assert (
        decision["authorization"]
        == runner["_EXPECTED_EXECUTION_AUTHORIZATION"]
    )
    assert decision["identity_review_sha256"] == file_sha256(_IDENTITY)
    assert (
        decision["expected_execution_sha256"]
        == identity["expected_execution_sha256"]
    )
    assert decision["downstream_authority"]["status"] == (
        "approved-in-principle-pending-passing-fast-lane-and-frozen-exact-"
        "identities"
    )


def test_complete_no_write_preflight_covers_real_process_payload() -> None:
    """All 300 slots and an actual process seam pass before execution."""
    runner = runpy.run_path(str(_RUNNER))
    expected = _object(_IDENTITY)["expected_execution"]
    verification = runner["verify_no_write"](
        repository_root=_ROOT,
        manifest_path=_MANIFEST,
        identity_path=_IDENTITY,
        scratch=Path(expected["scratch"]),
        output=_ROOT / expected["output"],
        verify_process_pool=True,
    )

    assert verification == {
        **verification,
        "status": "pass",
        "candidate_execution_count": 144,
        "coarse_control_execution_count": 144,
        "existing_dask_execution_count": 12,
        "candidate_execution_started": False,
        "process_payload_status": "spawn-pass",
    }


def test_freezer_rebuilds_exact_records_and_refuses_collision(
    tmp_path: Path,
) -> None:
    """The deterministic freezer emits the complete set exactly once."""
    freezer = runpy.run_path(str(_FREEZER))
    arguments = argparse.Namespace(
        repository_root=_ROOT,
        output_root=tmp_path,
    )

    freezer["freeze_records"](arguments)
    paths = tuple(
        Path("config/contracts") / name
        for name in (
            f"{_PREFIX}-validated-retry-implementation-decision.json",
            f"{_PREFIX}-validated-retry-identity-review.json",
            f"{_PREFIX}-validated-retry-execution-decision.json",
        )
    )
    assert tuple(_object(tmp_path / path) for path in paths) == tuple(
        _object(_ROOT / path) for path in paths
    )

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_records"](arguments)
