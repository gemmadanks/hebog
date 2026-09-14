# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Contracts for the fresh aligned compact Phase 5 sentinel."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from hebog.validation.datasets import DatasetRole, iter_dataset_recipes

_ROOT = Path(__file__).parents[3]
_POPULATION = _ROOT / (
    "scripts/validation/phase5_compact_held_out_source_union_sentinel.py"
)
_CHILD = _ROOT / (
    "scripts/benchmark/run_phase5_compact_held_out_source_union_pybdsf.py"
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
