"""Regression contracts for absent PyBDSF ``srl`` Gaussian counts."""

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
    "run_phase5_compact_held_out_source_union_pybdsf_"
    "gaussian_count_repair.py"
)
_RUNNER = _ROOT / (
    "scripts/benchmark/"
    "run_phase5_compact_held_out_source_union_sentinel_"
    "gaussian_count_repair.py"
)
_FREEZER = _ROOT / (
    "scripts/validation/"
    "freeze_phase5_compact_held_out_source_union_gaussian_count_repair.py"
)
_FAILED_OUTPUT = _ROOT / (
    "benchmark-results/phase-5/"
    "compact-held-out-source-union-sentinel-column-case-repair.json"
)


def _header() -> fits.Header:
    """Return one deterministic celestial frame."""
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [1.0, 1.0]
    wcs.wcs.cdelt = np.asarray([-0.01, 0.01])
    wcs.wcs.crval = [10.0, -30.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return wcs.to_header()


def test_child_derives_gaussian_count_from_native_gaul_membership() -> None:
    """Released ``srl`` omits the count; exact ``gaul`` rows supply it."""
    child: dict[str, Any] = runpy.run_path(str(_CHILD))
    header = _header()
    world = WCS(header, relax=True).celestial.all_pix2world([[0.0, 0.0]], 0)[0]
    source_table = np.asarray(
        [(0, 0, world[0], world[1], 3.0)],
        dtype=[
            ("Isl_id", "<i4"),
            ("Source_id", "<i4"),
            ("RA", "<f8"),
            ("DEC", "<f8"),
            ("Total_flux", "<f8"),
        ],
    )
    gaussian_table = np.asarray(
        [
            (0, 0, 0, world[0], world[1], 2.0, 1.0, 0.02, 0.02, 0.0),
            (1, 0, 0, world[0], world[1], 1.0, 0.5, 0.02, 0.02, 0.0),
        ],
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
    assert len(projection.components) == 2
    assert projection.sources[0].member_component_ids == (
        "pybdsf-island-0-source-0-gaussian-0",
        "pybdsf-island-0-source-0-gaussian-1",
    )


def test_runner_selects_only_the_gaussian_count_child(tmp_path: Path) -> None:
    """The second repair changes only the isolated PyBDSF child program."""
    runner: dict[str, Any] = runpy.run_path(str(_RUNNER))
    command = runner["_pybdsf_command_gaussian_count_safe"](
        repository_root=_ROOT,
        case_root=tmp_path,
        execution_decision=_ROOT
        / "config/contracts/phase-5-compact-held-out-source-union-"
        "column-case-repair-execution-decision.json",
        identity_review=_ROOT
        / "config/contracts/phase-5-compact-held-out-source-union-"
        "column-case-repair-identity-review.json",
        podman_executable="podman",
    )

    repaired = (
        "/repository/scripts/benchmark/"
        "run_phase5_compact_held_out_source_union_pybdsf_"
        "gaussian_count_repair.py"
    )
    assert repaired in command
    assert not any("column_case_repair.py" in item for item in command)


@pytest.mark.integration
@pytest.mark.requires_data
def test_repair_freeze_binds_second_failure_and_preserves_science() -> None:
    """The replacement identity changes schema provenance only."""
    freezer: dict[str, Any] = runpy.run_path(str(_FREEZER))
    implementation, identity = freezer["build_records"](_ROOT)

    assert file_sha256(_FAILED_OUTPUT) == (
        "9d96a9ed36f580fe307e9992ca6f093f5fc0fe88bfbdc4361cf282bbe23e3bb5"
    )
    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["execution_contract"]["total_finder_executions"] == 348
    assert identity["population"]["image_count"] == 168
    assert implementation["repair"] == {
        "candidate_science_changed": False,
        "comparator_configuration_changed": False,
        "evaluator_or_gate_changed": False,
        "source_count_provenance": "derived-from-exact-gaul-membership",
        "source_table_count_column": None,
    }


def test_repair_freezer_refuses_any_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second replacement records are write-once as a set."""
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
