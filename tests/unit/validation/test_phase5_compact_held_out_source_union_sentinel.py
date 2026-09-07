# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Contracts for the fresh aligned compact Phase 5 sentinel."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from hebog.validation.datasets import DatasetRole, iter_dataset_recipes
from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_POPULATION = _ROOT / (
    "scripts/validation/phase5_compact_held_out_source_union_sentinel.py"
)
_CHILD = _ROOT / (
    "scripts/benchmark/run_phase5_compact_held_out_source_union_pybdsf.py"
)
_RUNNER = _ROOT / (
    "scripts/benchmark/run_phase5_compact_held_out_source_union_sentinel.py"
)
_FREEZER = _ROOT / (
    "scripts/validation/freeze_phase5_compact_held_out_source_union_sentinel.py"
)
_MANIFEST = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-sentinel-manifest.json"
)
_IMPLEMENTATION = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-sentinel-implementation-decision.json"
)
_IDENTITY = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-sentinel-identity-review.json"
)


def _program(path: Path) -> dict[str, Any]:
    """Load one non-executable script without invoking its CLI."""
    return runpy.run_path(str(path))


def test_population_is_fresh_seed_disjoint_and_exact() -> None:
    """The successor is the same bounded design with 168 unseen seeds."""
    population = _program(_POPULATION)
    manifest = population["build_manifest"]()
    audit = population["audit_manifest"](_ROOT, manifest)
    seeds = tuple(
        recipe.seed
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    )

    assert manifest.manifest_id == (
        "phase-5-compact-held-out-source-union-sentinel"
    )
    assert len(manifest.datasets) == 42
    assert seeds == tuple(range(2026971001, 2026971169))
    assert {dataset.role for dataset in manifest.datasets} == {
        DatasetRole.QUALIFICATION
    }
    assert audit == {
        "historical_manifest_count": 47,
        "historical_registry_canonical_sha256": (
            "39644fb6ee13279623c2aea52ba8ee818886203c84cf904fe47e9725668f00ff"
        ),
        "historical_seed_count": 21085,
        "prospective_seed_count": 168,
        "seed_disjoint": True,
    }


def _header() -> fits.Header:
    """Return the sentinel's deterministic celestial frame."""
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [1.0, 1.0]
    wcs.wcs.cdelt = np.asarray([-0.01, 0.01])
    wcs.wcs.crval = [10.0, -30.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return wcs.to_header()


def _world(
    header: fits.Header, centre_xy: tuple[float, float]
) -> tuple[float, float]:
    world = WCS(header, relax=True).celestial.all_pix2world([centre_xy], 0)[0]
    return float(world[0]), float(world[1])


def test_pybdsf_child_projects_source_rows_and_fitless_support() -> None:
    """The child derives source unions before publishing its bundle."""
    child = _program(_CHILD)
    header = _header()
    left = _world(header, (0.0, 0.0))
    right = _world(header, (4.0, 0.0))
    source_table = np.asarray(
        [
            (0, 0, 1, left[0], left[1], 2.0),
            (0, 1, 1, right[0], right[1], 2.0),
        ],
        dtype=[
            ("Isl_id", "<i4"),
            ("Source_id", "<i4"),
            ("N_Gaus", "<i4"),
            ("RA", "<f8"),
            ("DEC", "<f8"),
            ("Total_flux", "<f8"),
        ],
    )
    gaussian_table = np.asarray(
        [
            (0, 0, 0, left[0], left[1], 2.0, 1.0, 0.02, 0.02, 0.0),
            (1, 0, 1, right[0], right[1], 2.0, 1.0, 0.02, 0.02, 0.0),
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
        native_island_labels=np.asarray(((1, 1, 1, 1, 1, 0, 2),)),
        header=header,
    )

    assert len(projection.sources) == 2
    assert len(projection.components) == 2
    assert projection.unowned_native_support_labels == (2,)
    np.testing.assert_array_equal(
        projection.source_union_label_plane,
        np.asarray(((1, 1, 2, 2, 2, 0, 0),), dtype=np.int32),
    )


def test_pybdsf_child_accepts_schema_free_empty_catalogues() -> None:
    """Zero-row native tables preserve fitless island support as unowned."""
    child = _program(_CHILD)
    projection = child["projection_from_catalogue_tables"](
        source_table=np.empty(0, dtype=[]),
        gaussian_table=np.empty(0, dtype=[]),
        native_island_labels=np.asarray(((1, 1, 0),), dtype=np.int32),
        header=_header(),
    )

    assert projection.sources == ()
    assert projection.components == ()
    assert projection.unowned_native_support_labels == (1,)
    np.testing.assert_array_equal(
        projection.source_union_label_plane,
        np.zeros((1, 3), dtype=np.int32),
    )


def test_runner_preflight_is_no_write_and_needs_new_authority(
    tmp_path: Path,
) -> None:
    """A frozen identity cannot execute either finder by itself."""
    runner = _program(_RUNNER)
    scratch = tmp_path / "scratch"
    output = tmp_path / "terminal.json"

    verified = runner["verify_no_write"](
        repository_root=_ROOT,
        manifest_path=_MANIFEST,
        identity_path=_IDENTITY,
        scratch=scratch,
        output=output,
        minimum_free_disk_gib=0,
    )
    assert verified["status"] == "pass"
    assert verified["finder_execution_started"] is False
    assert not scratch.exists()
    assert not output.exists()

    with pytest.raises(PermissionError, match="exact execution decision"):
        runner["verify_execution_authority"](
            SimpleNamespace(
                execution_decision=None,
                identity_review=_IDENTITY,
                manifest=_MANIFEST,
                output=output,
                repository_root=_ROOT,
                scratch=scratch,
                workers=2,
            )
        )


def test_identity_binds_aligned_program_and_remains_non_executable() -> None:
    """Every alignment and adapter seam is immutable before approval."""
    identity = json.loads(_IDENTITY.read_text(encoding="utf-8"))
    implementation = json.loads(_IMPLEMENTATION.read_text(encoding="utf-8"))

    assert identity["status"] == "frozen-non-executable"
    assert implementation["status"] == (
        "implemented-and-validated-non-executable"
    )
    assert set(identity["authorization"].values()) == {False}
    assert identity["population"]["image_count"] == 168
    assert identity["execution_contract"]["total_finder_executions"] == 348
    assert identity["evidence_schema_version"] == 3
    assert {
        "aligned_evaluator",
        "alignment",
        "source_union_adapters",
        "source_union_pybdsf_child",
        "source_union_runner",
    }.issubset(identity["program_bindings"])
    for binding in identity["program_bindings"].values():
        assert file_sha256(_ROOT / binding["path"]) == binding["sha256"]


def test_freezer_collision_writes_nothing_else(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The successor identity set refuses every overwrite."""
    freezer = _program(_FREEZER)
    existing = tmp_path / _IDENTITY.relative_to(_ROOT)
    existing.parent.mkdir(parents=True)
    existing.write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(_FREEZER),
            "--repository-root",
            str(_ROOT),
            "--output-root",
            str(tmp_path),
        ],
    )

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["main"]()

    assert existing.read_text(encoding="utf-8") == "existing\n"
    assert not (tmp_path / _MANIFEST.relative_to(_ROOT)).exists()
    assert not (tmp_path / _IMPLEMENTATION.relative_to(_ROOT)).exists()
