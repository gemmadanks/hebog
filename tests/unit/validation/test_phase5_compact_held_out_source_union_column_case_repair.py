"""Regression contracts for the PyBDSF ``N_gaus`` sentinel repair."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import runpy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_CHILD = _ROOT / (
    "scripts/benchmark/"
    "run_phase5_compact_held_out_source_union_pybdsf_column_case_repair.py"
)
_RUNNER = _ROOT / (
    "scripts/benchmark/"
    "run_phase5_compact_held_out_source_union_sentinel_column_case_repair.py"
)
_FREEZER = _ROOT / (
    "scripts/validation/"
    "freeze_phase5_compact_held_out_source_union_column_case_repair.py"
)
_FAILED_OUTPUT = _ROOT / (
    "benchmark-results/phase-5/compact-held-out-source-union-sentinel.json"
)


def _header() -> fits.Header:
    """Return one deterministic celestial frame."""
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [1.0, 1.0]
    wcs.wcs.cdelt = np.asarray([-0.01, 0.01])
    wcs.wcs.crval = [10.0, -30.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return wcs.to_header()


def test_child_accepts_pybdsf_native_n_gaus_column() -> None:
    """The released ``srl`` spelling is ``N_gaus``, not ``N_Gaus``."""
    child: dict[str, Any] = runpy.run_path(str(_CHILD))
    header = _header()
    world = WCS(header, relax=True).celestial.all_pix2world([[0.0, 0.0]], 0)[0]
    source_table = np.asarray(
        [(0, 0, 1, world[0], world[1], 2.0)],
        dtype=[
            ("Isl_id", "<i4"),
            ("Source_id", "<i4"),
            ("N_gaus", "<i4"),
            ("RA", "<f8"),
            ("DEC", "<f8"),
            ("Total_flux", "<f8"),
        ],
    )
    gaussian_table = np.asarray(
        [(0, 0, 0, world[0], world[1], 2.0, 1.0, 0.02, 0.02, 0.0)],
        dtype=[
            ("Gaus_id", "<i4"),
            ("Isl_id", "<i4"),
            ("Source_id", "<i4"),
            ("RA", "<f8"),
            ("DEC", "<f8"),
            ("Total_flux", "<f8"),
            ("Peak_flux", "<f8"),
            ("Maj", "<f8"),
            ("Min", "<f8"),
            ("PA", "<f8"),
        ],
    )

    projection = child["projection_from_catalogue_tables"](
        source_table=source_table,
        gaussian_table=gaussian_table,
        native_island_labels=np.ones((1, 2), dtype=np.int32),
        header=header,
    )

    assert len(projection.sources) == 1
    assert len(projection.components) == 1
    np.testing.assert_array_equal(
        projection.source_union_label_plane,
        np.ones((1, 2), dtype=np.int32),
    )


def test_runner_selects_only_the_column_case_child(tmp_path: Path) -> None:
    """The repair changes only the isolated PyBDSF child program."""
    runner: dict[str, Any] = runpy.run_path(str(_RUNNER))
    command = runner["_pybdsf_command_column_case_safe"](
        repository_root=_ROOT,
        case_root=tmp_path,
        execution_decision=_ROOT
        / "config/contracts/phase-5-compact-held-out-source-union-"
        "sentinel-execution-decision.json",
        identity_review=_ROOT
        / "config/contracts/phase-5-compact-held-out-source-union-"
        "sentinel-identity-review.json",
        podman_executable="podman",
    )

    repaired = (
        "/repository/scripts/benchmark/"
        "run_phase5_compact_held_out_source_union_pybdsf_column_case_repair.py"
    )
    parent = (
        "/repository/scripts/benchmark/"
        "run_phase5_compact_held_out_source_union_pybdsf.py"
    )
    assert repaired in command
    assert parent not in command


@pytest.mark.integration
@pytest.mark.requires_data
def test_repair_freeze_binds_failure_without_authorizing_execution() -> None:
    """The replacement identity preserves the terminal and frozen science."""
    freezer: dict[str, Any] = runpy.run_path(str(_FREEZER))
    implementation, identity = freezer["build_records"](_ROOT)

    assert file_sha256(_FAILED_OUTPUT) == (
        "331e36a5afee90e799a281186000ae1c760f46388fd2662514eba379503a4b9f"
    )
    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["candidate"]["source_tree_sha256"] == (
        "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
    )
    assert identity["execution_contract"]["total_finder_executions"] == 348
    assert identity["population"]["image_count"] == 168
    assert implementation["repair"] == {
        "accepted_source_count_column": "N_gaus",
        "candidate_science_changed": False,
        "comparator_configuration_changed": False,
        "evaluator_or_gate_changed": False,
    }


def test_repair_freezer_refuses_any_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The replacement records are write-once as a set."""
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
