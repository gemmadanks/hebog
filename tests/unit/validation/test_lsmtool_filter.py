# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Planning and judging a run of LSMTool's filter_sources on a mask."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from hebog.validation.lsmtool_filter import (
    FilterOutcome,
    FilterPlan,
    _declination_text,  # pyright: ignore[reportPrivateUsage]
    _right_ascension_text,  # pyright: ignore[reportPrivateUsage]
    filter_failures,
    plan_filter_inputs,
)

_SHAPE_YX = (100, 120)


def _header(*, mask: bool) -> fits.Header:
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 61.0
    header["CRPIX2"] = 51.0
    header["CRVAL1"] = 242.75
    header["CRVAL2"] = 54.95
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["CUNIT1"] = "deg"
    header["CUNIT2"] = "deg"
    header["CTYPE3"] = "STOKES" if mask else "FREQ"
    header["CRVAL3"] = 1.0 if mask else 144e6
    header["CDELT3"] = 1.0
    header["CRPIX3"] = 1.0
    header["CTYPE4"] = "FREQ" if mask else "STOKES"
    header["CRVAL4"] = 144e6 if mask else 1.0
    header["CDELT4"] = 3e8 if mask else 1.0
    header["CRPIX4"] = 1.0
    return header


def _write(path: Path, plane: np.ndarray, *, mask: bool) -> Path:
    data = np.asarray(plane, dtype=np.float32)[np.newaxis, np.newaxis]
    fits.PrimaryHDU(data, header=_header(mask=mask)).writeto(path)
    return path


_BLANKED_FROM_ROW = 90


def _plan(
    tmp_path: Path, *, decoy_count: int = 12, island_limit: int = 2_000
) -> FilterPlan:
    """Plan for islands A and B inside the polygon and C in its margin.

    A one-pixel line is too thin to hold a component, and the true-sky
    image is blank above row 90, where the attenuation is unknown.
    """
    y_pixels, x_pixels = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    mask = np.zeros(_SHAPE_YX)
    mask[30:45, 30:50] = 1.0
    mask[(x_pixels - 80) ** 2 + (y_pixels - 60) ** 2 <= 8**2] = 1.0
    mask[2:8, 2:8] = 1.0
    mask[60, 5:30] = 1.0
    true_sky = np.full(_SHAPE_YX, 2.0)
    flat_noise = true_sky / 2
    true_sky[_BLANKED_FROM_ROW:] = np.nan
    return plan_filter_inputs(
        _write(tmp_path / "sector.mask.fits", mask, mask=True),
        _write(tmp_path / "true-sky.fits", true_sky, mask=False),
        _write(tmp_path / "flat-noise.fits", flat_noise, mask=False),
        tmp_path / "inputs",
        margin_fraction=0.1,
        island_limit=island_limit,
        decoy_count=decoy_count,
    )


def _outcome(plan: FilterPlan) -> FilterOutcome:
    """Return the outcome ``filter_sources`` should produce for a plan."""
    patches = {
        component.name: f"mask_patch_{component.island}"
        for component in plan.components
        if component.island
    }
    return FilterOutcome(
        true_patches=patches,
        apparent_patches=dict(patches),
        apparent_fluxes_jy={
            component.name: component.apparent_flux_jy
            for component in plan.components
            if component.island
        },
    )


def test_the_plan_keeps_island_components_and_groups_them(
    tmp_path: Path,
) -> None:
    """Components on islands in the polygon stay, one patch an island."""
    plan = _plan(tmp_path)

    by_name = {component.name: component for component in plan.components}
    # Islands are numbered in raster order: C in the margin, then A and B.
    assert plan.kept() == {"island2a", "island2b", "island3a", "island3b"}
    assert len(plan.groups()) == 2
    assert all(len(group) == 2 for group in plan.groups())
    clipped = [component for component in plan.components if component.clipped]
    assert len(clipped) == 1
    assert clipped[0].island == 0
    decoys = [name for name in by_name if name.startswith("decoy")]
    assert decoys
    assert all(by_name[name].island == 0 for name in decoys)
    assert all(
        component.apparent_flux_jy
        == pytest.approx(
            component.true_flux_jy
            * (1.0 if component.y >= _BLANKED_FROM_ROW else 0.5)
        )
        for component in plan.components
    )
    assert any(
        component.y >= _BLANKED_FROM_ROW for component in plan.components
    )


def test_a_plan_without_decoys_holds_island_components_only(
    tmp_path: Path,
) -> None:
    """Decoys are optional; island components are always planned."""
    plan = _plan(tmp_path, decoy_count=0)

    assert all(
        component.name.startswith("island") for component in plan.components
    )
    assert len(plan.kept()) == 4


def test_the_plan_writes_rapthors_inputs(tmp_path: Path) -> None:
    """A closed polygon in degrees, and two makesourcedb models."""
    plan = _plan(tmp_path)

    vertices = np.load(plan.vertices_path)
    assert vertices.shape == (5, 2)
    assert vertices.dtype == np.float64
    np.testing.assert_array_equal(vertices[0], vertices[-1])
    for path in (plan.true_sky_model_path, plan.apparent_sky_model_path):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("FORMAT = Name, Type, Ra, Dec, I")
        assert len(lines) == 1 + len(plan.components)
        assert lines[1].split(",")[1] == "POINT"


def test_a_filter_run_that_follows_the_plan_has_no_failure(
    tmp_path: Path,
) -> None:
    """The outcome the mask decides, on every executor, passes."""
    plan = _plan(tmp_path)
    clipped_mask = tmp_path / "sector.mask.fits"
    with fits.open(clipped_mask, mode="update") as hdus:
        # The polygon spans x 11.9 to 107.1 and y 9.9 to 89.1.
        inside = np.zeros(_SHAPE_YX, dtype=bool)
        inside[10:90, 12:108] = True
        hdus[0].data[..., ~inside] = 0.0

    outcomes = {"serial": _outcome(plan), "dask": _outcome(plan)}

    assert (
        filter_failures(
            plan, outcomes, {"serial": clipped_mask, "dask": clipped_mask}
        )
        == []
    )


def test_each_departure_from_the_plan_is_named(tmp_path: Path) -> None:
    """A wrong survivor, patch, name, flux or mask pixel is reported."""
    plan = _plan(tmp_path)
    expected = _outcome(plan)
    kept = sorted(plan.kept())
    merged = dict.fromkeys(expected.true_patches, "mask_patch_1")
    outcomes = {
        "kept": replace(
            expected,
            true_patches={**expected.true_patches, "decoy0": "patch_1"},
        ),
        "grouped": replace(
            expected, true_patches=merged, apparent_patches=merged
        ),
        "renamed": replace(
            expected, apparent_patches={kept[0]: "mask_patch_1"}
        ),
        "flux": replace(
            expected,
            apparent_fluxes_jy={
                name: flux * 1.01
                for name, flux in expected.apparent_fluxes_jy.items()
            },
        ),
    }
    unclipped = tmp_path / "sector.mask.fits"

    failures = filter_failures(plan, outcomes, {"unclipped": unclipped})

    assert any(failure.startswith("kept: kept") for failure in failures)
    assert any("grouped: patches" in failure for failure in failures)
    assert any(
        "renamed: apparent-sky names" in failure for failure in failures
    )
    assert any("flux: apparent-sky fluxes" in failure for failure in failures)
    # Island C and six pixels of the line lie outside the polygon.
    assert any("unclipped: 42 mask pixels" in failure for failure in failures)
    assert "the executors' filtered sky models differ" in failures


def test_executors_whose_clipped_masks_differ_fail(tmp_path: Path) -> None:
    """Every executor's products must give LSMTool the same mask."""
    plan = _plan(tmp_path)
    first = tmp_path / "first.mask.fits"
    second = tmp_path / "second.mask.fits"
    for path, value in ((first, 0.0), (second, 0.0)):
        _write(path, np.full(_SHAPE_YX, value), mask=True)
    with fits.open(second, mode="update") as hdus:
        hdus[0].data[0, 0, 50, 60] = 1.0

    failures = filter_failures(
        plan,
        {"serial": _outcome(plan)},
        {"serial": first, "threads": second},
    )

    assert "the executors' clipped masks differ" in failures


def test_the_worker_summary_reads_as_an_outcome(tmp_path: Path) -> None:
    """The container worker writes each survivor's name, patch and flux."""
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "lsmtool": "1.9.1.dev15+g9bac2f7",
                "true_sky": [
                    ["a", "mask_patch_1", 1.0],
                    ["b", "mask_patch_1", 2.0],
                ],
                "apparent_sky": [["a", "mask_patch_1", 0.5]],
            }
        ),
        encoding="utf-8",
    )

    outcome = FilterOutcome.read(summary)

    assert outcome.true_patches == {"a": "mask_patch_1", "b": "mask_patch_1"}
    assert outcome.apparent_patches == {"a": "mask_patch_1"}
    assert outcome.apparent_fluxes_jy == {"a": 0.5}
    assert outcome.groups() == {frozenset({"a", "b"})}


def test_a_plan_samples_islands_evenly_up_to_its_limit(
    tmp_path: Path,
) -> None:
    """A sector-sized mask gives components to a bounded share of islands.

    Of the four islands, numbered C, A, B and the line in raster order, a
    limit of three takes the first, the middle and the last; the line is
    too thin, so only A's two components remain to be kept.
    """
    plan = _plan(tmp_path, island_limit=3, decoy_count=0)

    assert {component.name for component in plan.components} == {
        "island1a",
        "island2a",
        "island2b",
    }
    assert plan.kept() == {"island2a", "island2b"}


@pytest.mark.parametrize(
    ("ra_deg", "expected"),
    [
        (242.75, "16:11:00.000000"),
        (0.0, "00:00:00.000000"),
        (359.9999999999, "00:00:00.000000"),
        # 15 degrees less a part in 10^12 rounds up to the next hour.
        (15.0 - 1e-12, "01:00:00.000000"),
        (242.77695709037, "16:11:06.469702"),
    ],
)
def test_a_right_ascension_is_written_as_makesourcedb_reads_it(
    ra_deg: float, expected: str
) -> None:
    """Hours, minutes and seconds to the microsecond, carried exactly."""
    assert _right_ascension_text(ra_deg) == expected


@pytest.mark.parametrize(
    ("dec_deg", "expected"),
    [
        (54.95, "+54.57.00.000000"),
        (-30.5, "-30.30.00.000000"),
        (0.0, "+00.00.00.000000"),
        (-(1.0 - 1e-12), "-01.00.00.000000"),
        (-0.0000001, "-00.00.00.000360"),
    ],
)
def test_a_declination_is_written_as_makesourcedb_reads_it(
    dec_deg: float, expected: str
) -> None:
    """A sign, then degrees, arcminutes and arcseconds to the microsecond."""
    assert _declination_text(dec_deg) == expected
