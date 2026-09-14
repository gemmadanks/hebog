"""Regression tests for a valid empty PyBDSF sentinel result."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table

_ROOT = Path(__file__).parents[3]
_CHILD = (
    _ROOT / "scripts/benchmark/"
    "run_phase5_compact_held_out_pybdsf_empty_repair.py"
)
_RUNNER = (
    _ROOT / "scripts/benchmark/"
    "run_phase5_compact_held_out_sentinel_pybdsf_empty_repair.py"
)
_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_compact_sentinel_pybdsf_empty_repair.py"
)


def test_child_accepts_pybdsf_zero_row_schema(tmp_path: Path) -> None:
    """PyBDSF's no-island zero-column table is a valid empty catalogue."""
    program: dict[str, Any] = runpy.run_path(str(_CHILD))
    path = tmp_path / "empty.fits"
    fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU()]).writeto(path)

    assert program["_load_zero_row_safe"](path) == ()


def test_child_rejects_nonempty_malformed_catalogue(tmp_path: Path) -> None:
    """Only a genuinely zero-row table may omit the Gaussian schema."""
    program: dict[str, Any] = runpy.run_path(str(_CHILD))
    path = tmp_path / "malformed.fits"
    Table(rows=((1,),), names=("unexpected",)).write(path)

    with pytest.raises(ValueError, match="misses columns"):
        program["_load_zero_row_safe"](path)


def test_empty_catalogue_requires_zero_native_labels() -> None:
    """A zero-row catalogue may not hide a positive PyBDSF island."""
    program: dict[str, Any] = runpy.run_path(str(_CHILD))

    with pytest.raises(ValueError, match="positive native labels"):
        program["_validate_empty_support"](
            (), np.asarray([[0, 1]], dtype=np.int32)
        )


def test_runner_selects_only_repaired_child(tmp_path: Path) -> None:
    """The host wrapper must invoke the bounded empty-result child."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))

    command = program["_pybdsf_command_empty_safe"](
        repository_root=_ROOT,
        case_root=tmp_path,
        execution_decision=(
            _ROOT / "config/contracts/"
            "phase-5-compact-held-out-sentinel-zero-count-repair-"
            "execution-decision.json"
        ),
        identity_review=(
            _ROOT / "config/contracts/"
            "phase-5-compact-held-out-sentinel-zero-count-repair-review.json"
        ),
        podman_executable="podman",
    )

    assert (
        "/repository/scripts/benchmark/"
        "run_phase5_compact_held_out_pybdsf_empty_repair.py"
    ) in command
    assert (
        "/repository/scripts/benchmark/run_phase5_compact_held_out_pybdsf.py"
    ) not in command


def test_host_compiles_only_zero_count_with_zero_labels(
    tmp_path: Path,
) -> None:
    """The host must independently enforce the empty child contract."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))

    assert (
        program["_load_pybdsf_catalogue_empty_safe"](
            tmp_path,
            0,
            np.zeros((2, 3), dtype=np.int32),
        )
        == ()
    )
    with pytest.raises(ValueError, match="positive native labels"):
        program["_load_pybdsf_catalogue_empty_safe"](
            tmp_path,
            0,
            np.asarray([[0, 1]], dtype=np.int32),
        )


def test_runner_temporarily_replaces_all_execution_seams() -> None:
    """Pairs and Dask checks must share the complete repaired adapter."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))
    parent = program["_parent"]
    original_hebog = parent._run_hebog
    original_pybdsf = parent._run_pybdsf
    original_pair = parent._pair_worker

    with program["_configured_parent"]():
        assert parent._run_hebog is program["_zero"]._run_hebog_zero_count_safe
        assert parent._run_pybdsf is program["_run_pybdsf_empty_safe"]
        assert parent._pair_worker is program["_pair_worker_pybdsf_empty_safe"]

    assert parent._run_hebog is original_hebog
    assert parent._run_pybdsf is original_pybdsf
    assert parent._pair_worker is original_pair


@pytest.mark.integration
@pytest.mark.requires_data
def test_runner_binds_all_preserved_failures() -> None:
    """The replacement retry cannot detach from the failed attempts."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))

    program["_require_failed_lineage"]()


@pytest.mark.integration
@pytest.mark.requires_data
def test_pybdsf_empty_identity_preserves_science_and_population() -> None:
    """Only comparator empty-result interpretation and paths may change."""
    freezer: dict[str, Any] = runpy.run_path(str(_FREEZER))
    implementation, identity = freezer["build_records"](_ROOT)

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["candidate"]["source_tree_sha256"] == (
        "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
    )
    assert identity["execution_contract"]["total_finder_executions"] == 348
    assert identity["population"]["image_count"] == 168
    assert identity["expected_execution"]["output"].endswith(
        "compact-held-out-sentinel-pybdsf-empty-repair.json"
    )
    assert implementation["repair"] == {
        "child_and_host_empty_checks": True,
        "positive_native_labels_fail_closed": True,
        "pybdsf_configuration_unchanged": True,
        "schema_free_catalogue_only_when_zero_rows": True,
        "stable_hebog_repairs_preserved": True,
    }


def test_pybdsf_empty_freezer_refuses_existing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replacement identity cannot overwrite an existing record."""
    freezer: dict[str, Any] = runpy.run_path(str(_FREEZER))

    def build_fixture_records(_root: Path) -> tuple[dict[str, str], ...]:
        return ({"fixture": "implementation"}, {"fixture": "identity"})

    monkeypatch.setitem(
        freezer["freeze_records"].__globals__,
        "build_records",
        build_fixture_records,
    )
    identity = tmp_path / freezer["_IDENTITY"]
    identity.parent.mkdir(parents=True)
    identity.write_text("existing\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_records"](
            argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)
        )

    assert identity.read_text(encoding="utf-8") == "existing\n"
    assert not (tmp_path / freezer["_IMPLEMENTATION"]).exists()


def test_pybdsf_empty_review_records_exact_user_authority() -> None:
    """Comparator repair authority must not broaden into science changes."""
    review = json.loads(
        (
            _ROOT / "config/contracts/"
            "phase-5-compact-held-out-sentinel-pybdsf-empty-repair-"
            "pre-review.json"
        ).read_text(encoding="utf-8")
    )

    assert review["authorization"]["evaluator_repair_authorized"] is True
    assert review["authorization"]["all_retries_authorized"] is True
    assert (
        review["authorization"]["pybdsf_configuration_change_authorized"]
        is False
    )
    assert review["scientific_invariants"]["image_count"] == 168
