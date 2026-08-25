# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
"""Approved SDC1 and Hydra public-comparison semantics."""

from __future__ import annotations

import json
import math
import runpy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from astropy.wcs import WCS

from hebog.validation.public_comparison import (
    HydraDepth,
    HydraFinder,
    PublicTileAttributes,
    PublicTileTruth,
    adapt_hydra_columns,
    apparent_peak_snr,
    build_public_tile_attributes,
    gaussian_fwhm_arcsec,
    select_public_tiles,
)

_ROOT = Path(__file__).parents[3]
_SELECTOR = _ROOT / "scripts/validation/select_phase5_public_population.py"
_VERIFIER = _ROOT / "scripts/validation/verify_phase5_public_population.py"
_REGISTRY = (
    _ROOT
    / "config/contracts/phase-5-public-comparison-selected-population.json"
)


def _selector() -> dict[str, Any]:
    """Load the selection command without creating public products."""
    return runpy.run_path(str(_SELECTOR))


def _verifier() -> dict[str, Any]:
    """Load the terminal verifier without opening public products."""
    return runpy.run_path(str(_VERIFIER))


def test_sdc1_size_codes_and_apparent_peak_snr_are_exact() -> None:
    """SDC1 morphology conversion precedes beam-convolved peak SNR."""
    major, minor = gaussian_fwhm_arcsec(
        np.array([1, 2, 3]),
        np.array([10.0, 10.0, 10.0]),
        np.array([4.0, 4.0, 4.0]),
    )

    np.testing.assert_allclose(
        major,
        np.array([10.0 * 2.355 / 5.0, 10.0, 10.0 * math.sqrt(2.0)]),
    )
    np.testing.assert_allclose(
        minor,
        np.array([4.0 * 2.355 / 5.0, 4.0, 4.0 * math.sqrt(2.0)]),
    )
    snr = apparent_peak_snr(
        integrated_flux_jy=np.array([1.0]),
        primary_beam_response=np.array([0.5]),
        major_fwhm_arcsec=np.array([0.6]),
        minor_fwhm_arcsec=np.array([0.6]),
    )
    expected = 0.5 * 0.6 * 0.6 / (math.sqrt(0.72) ** 2) / 73e-9
    np.testing.assert_allclose(snr, np.array([expected]))

    with pytest.raises(ValueError, match="size code"):
        gaussian_fwhm_arcsec(
            np.array([4]),
            np.array([1.0]),
            np.array([1.0]),
        )


def _tile(  # noqa: PLR0913
    tile_id: str,
    index: int,
    *,
    count: int,
    resolved: float,
    pair: float,
    dynamic: float,
    low_snr: float,
    primary_beam: float,
) -> PublicTileAttributes:
    return PublicTileAttributes(
        tile_id=tile_id,
        x_start=index * 2048,
        y_start=0,
        source_count=count,
        resolved_fraction=resolved,
        closest_pair_beams=pair,
        dynamic_range=dynamic,
        low_snr_fraction=low_snr,
        mean_primary_beam=primary_beam,
        truth_ids=(index,),
    )


def test_public_tile_selection_is_unique_and_deterministic() -> None:
    """The eight approved strata select unique tiles in fixed order."""
    tiles = tuple(
        _tile(
            f"tile-{index}",
            index,
            count=(1, 10, 20, 30, 40, 50, 60, 70, 80)[index],
            resolved=index / 8,
            pair=9 - index,
            dynamic=float(index + 1),
            low_snr=index / 9,
            primary_beam=0.5 + index / 100,
        )
        for index in range(9)
    )

    selected = select_public_tiles(tiles)

    assert [item.stratum for item in selected] == [
        "sparse",
        "ordinary",
        "crowded",
        "resolved",
        "close-pair",
        "high-dynamic-range",
        "low-apparent-SNR",
        "primary-beam-boundary",
    ]
    assert len({item.tile.tile_id for item in selected}) == 8
    assert selected[0].tile.tile_id == "tile-0"
    assert selected[1].tile.tile_id == "tile-4"

    with pytest.raises(ValueError, match="eight admitted"):
        select_public_tiles(tiles[:7])


def test_public_tile_attributes_apply_reviewed_empty_and_pair_rules() -> None:
    """Tile metrics use exact inclusive SNR and spherical-pair semantics."""
    populated = build_public_tile_attributes(
        tile_id="populated",
        x_start=0,
        y_start=0,
        truth=PublicTileTruth(
            identifiers=np.array([1, 2, 3]),
            ra_deg=np.array([0.0, 1.0 / 3600.0, 1.0]),
            dec_deg=np.array([-30.0, -30.0, -30.0]),
            major_fwhm_arcsec=np.array([0.6, 0.7, 1.0]),
            apparent_flux_jy=np.array([1.0, 2.0, -1.0]),
            peak_snr=np.array([5.0, 8.0, 9.0]),
        ),
        mean_primary_beam=0.75,
    )
    assert populated.resolved_fraction == pytest.approx(2.0 / 3.0)
    assert populated.low_snr_fraction == pytest.approx(2.0 / 3.0)
    assert populated.dynamic_range == pytest.approx(4.0 / 3.0)
    assert populated.closest_pair_beams == pytest.approx(
        math.cos(math.radians(30.0)) / 0.6,
        rel=1e-6,
    )

    empty = build_public_tile_attributes(
        tile_id="empty",
        x_start=2048,
        y_start=0,
        truth=PublicTileTruth(
            identifiers=np.array([], dtype=np.int64),
            ra_deg=np.array([]),
            dec_deg=np.array([]),
            major_fwhm_arcsec=np.array([]),
            apparent_flux_jy=np.array([]),
            peak_snr=np.array([]),
        ),
        mean_primary_beam=0.5,
    )
    assert empty.resolved_fraction == 0.0
    assert empty.low_snr_fraction == 0.0
    assert empty.dynamic_range == 0.0
    assert math.isinf(empty.closest_pair_beams)


def test_hydra_adapter_preserves_identity_and_normalizes_units() -> None:
    """Finder-specific identities survive unit-safe neutral adaptation."""
    selavy = adapt_hydra_columns(
        finder_id="selavy",
        depth="deep",
        columns={
            "id": np.array([7]),
            "island_id": np.array([3]),
            "component_id": np.array([2]),
            "ra": np.array([12.0]),
            "dec": np.array([-30.0]),
            "flux_peak": np.array([5.0]),
            "flux_total": np.array([8.0]),
            "major": np.array([10.0]),
            "minor": np.array([4.0]),
            "pa": np.array([20.0]),
        },
    )
    assert selavy[0].finder_id == "selavy"
    assert selavy[0].native_id == "7"
    assert selavy[0].native_island_id == "3"
    assert selavy[0].native_component_id == "2"
    assert selavy[0].peak_flux_jy_per_beam == pytest.approx(0.005)
    assert selavy[0].integrated_flux_jy == pytest.approx(0.008)
    assert selavy[0].major_axis_arcsec == pytest.approx(10.0)

    profound = adapt_hydra_columns(
        finder_id="profound",
        depth="shallow",
        columns={
            "id": np.array([11]),
            "component_id": np.array([4]),
            "unique_id": np.array(["native-4"]),
            "ra_centre": np.array([12.0]),
            "dec_centre": np.array([-30.0]),
            "flux_total": np.array([0.2]),
            "semimajor": np.array([0.01]),
            "semiminor": np.array([0.005]),
            "pa": np.array([30.0]),
        },
    )
    assert profound[0].peak_flux_jy_per_beam is None
    assert profound[0].native_island_id == "11"
    assert profound[0].native_component_id == "4"
    assert profound[0].major_axis_arcsec == pytest.approx(36.0)
    assert profound[0].minor_axis_arcsec == pytest.approx(18.0)


@pytest.mark.parametrize(
    ("finder_id", "columns", "identity", "axes"),
    [
        (
            "aegean",
            {
                "id": np.array([1]),
                "island_id": np.array([2]),
                "source_id": np.array([3]),
                "ra": np.array([12.0]),
                "dec": np.array([-30.0]),
                "flux_peak": np.array([0.1]),
                "flux_total": np.array([0.2]),
                "semimajor": np.array([4.0]),
                "semiminor": np.array([2.0]),
                "pa": np.array([20.0]),
            },
            ("1", "2", "3"),
            (4.0, 2.0),
        ),
        (
            "caesar",
            {
                "id": np.array([4]),
                "component_id": np.array([5]),
                "ra": np.array([12.0]),
                "dec": np.array([-30.0]),
                "flux_peak": np.array([0.1]),
                "flux_total": np.array([0.2]),
                "bmaj_wcs": np.array([6.0]),
                "bmin_wcs": np.array([3.0]),
                "pa_wcs": np.array([21.0]),
            },
            ("4", "4", "5"),
            (6.0, 3.0),
        ),
        (
            "pybdsf",
            {
                "id": np.array([6]),
                "island_id": np.array([8]),
                "source_id": np.array([7]),
                "ra": np.array([12.0]),
                "dec": np.array([-30.0]),
                "flux_peak": np.array([0.1]),
                "flux_total": np.array([0.2]),
                "major": np.array([0.01]),
                "minor": np.array([0.005]),
                "pa": np.array([22.0]),
            },
            ("6", "8", "7"),
            (36.0, 18.0),
        ),
    ],
)
def test_hydra_adapter_covers_each_published_schema(
    finder_id: HydraFinder,
    columns: dict[str, Any],
    identity: tuple[str, str, str],
    axes: tuple[float, float],
) -> None:
    """Every approved Hydra finder mapping preserves IDs and native axes."""
    component = adapt_hydra_columns(
        finder_id=finder_id,
        depth="deep",
        columns=columns,
    )[0]

    assert (
        component.native_id,
        component.native_island_id,
        component.native_component_id,
    ) == identity
    assert component.major_axis_arcsec == pytest.approx(axes[0])
    assert component.minor_axis_arcsec == pytest.approx(axes[1])


def test_public_adapters_reject_malformed_scientific_arrays() -> None:
    """Shape, code, finite-value, and catalogue-schema drift fail closed."""
    with pytest.raises(ValueError, match="equal shapes"):
        gaussian_fwhm_arcsec([1], [1.0, 2.0], [1.0])
    with pytest.raises(ValueError, match="non-negative"):
        gaussian_fwhm_arcsec([2], [-1.0], [1.0])
    with pytest.raises(ValueError, match="axes must be finite"):
        gaussian_fwhm_arcsec([2], [float("nan")], [1.0])
    with pytest.raises(ValueError, match="equal shapes"):
        apparent_peak_snr(
            integrated_flux_jy=[1.0],
            primary_beam_response=[0.5, 0.6],
            major_fwhm_arcsec=[0.6],
            minor_fwhm_arcsec=[0.6],
        )
    with pytest.raises(ValueError, match="inputs must be finite"):
        apparent_peak_snr(
            integrated_flux_jy=[float("nan")],
            primary_beam_response=[0.5],
            major_fwhm_arcsec=[0.6],
            minor_fwhm_arcsec=[0.6],
        )
    with pytest.raises(ValueError, match="must be non-negative"):
        apparent_peak_snr(
            integrated_flux_jy=[1.0],
            primary_beam_response=[-0.5],
            major_fwhm_arcsec=[0.6],
            minor_fwhm_arcsec=[0.6],
        )
    with pytest.raises(ValueError, match="missing Hydra columns"):
        adapt_hydra_columns(
            finder_id="aegean",
            depth="deep",
            columns={"id": np.array([1])},
        )

    candidates = tuple(
        _tile(
            f"tile-{index}",
            index,
            count=index,
            resolved=0.0,
            pair=float("inf"),
            dynamic=0.0,
            low_snr=0.0,
            primary_beam=0.5,
        )
        for index in range(8)
    )
    duplicate = (*candidates[:-1], replace(candidates[-1], tile_id="tile-0"))
    with pytest.raises(ValueError, match="identifiers must be unique"):
        select_public_tiles(duplicate)


def test_public_tile_and_hydra_failure_boundaries_are_explicit() -> None:
    """Malformed membership and native catalogue records fail closed."""
    valid_truth = PublicTileTruth(
        identifiers=np.array([1]),
        ra_deg=np.array([0.0]),
        dec_deg=np.array([-30.0]),
        major_fwhm_arcsec=np.array([0.6]),
        apparent_flux_jy=np.array([1.0]),
        peak_snr=np.array([6.0]),
    )
    two_dimensional_truth = PublicTileTruth(
        identifiers=np.array([[1]]),
        ra_deg=np.array([[0.0]]),
        dec_deg=np.array([[-30.0]]),
        major_fwhm_arcsec=np.array([[0.6]]),
        apparent_flux_jy=np.array([[1.0]]),
        peak_snr=np.array([[6.0]]),
    )
    malformed_truth = [
        replace(valid_truth, ra_deg=np.array([0.0, 1.0])),
        two_dimensional_truth,
        replace(valid_truth, peak_snr=np.array([float("nan")])),
    ]
    messages = ("equal shapes", "one-dimensional", "must be finite")
    for truth, message in zip(malformed_truth, messages, strict=True):
        with pytest.raises(ValueError, match=message):
            build_public_tile_attributes(
                tile_id="invalid",
                x_start=0,
                y_start=0,
                truth=truth,
                mean_primary_beam=0.5,
            )
    with pytest.raises(ValueError, match="mean primary-beam"):
        build_public_tile_attributes(
            tile_id="invalid",
            x_start=0,
            y_start=0,
            truth=valid_truth,
            mean_primary_beam=float("nan"),
        )

    columns = {
        "id": np.array([1]),
        "island_id": np.array([b"island"]),
        "source_id": np.array([2]),
        "ra": np.array([12.0]),
        "dec": np.array([-30.0]),
        "flux_peak": np.array([0.1]),
        "flux_total": np.array([0.2]),
        "semimajor": np.array([4.0]),
        "semiminor": np.array([2.0]),
        "pa": np.array([20.0]),
    }
    assert (
        adapt_hydra_columns(
            finder_id="aegean",
            depth="deep",
            columns=columns,
        )[0].native_island_id
        == "island"
    )
    unequal = {**columns, "id": np.array([1, 2])}
    with pytest.raises(ValueError, match="equal lengths"):
        adapt_hydra_columns(
            finder_id="aegean",
            depth="deep",
            columns=unequal,
        )
    nonfinite = {**columns, "ra": np.array([float("nan")])}
    with pytest.raises(ValueError, match="non-finite"):
        adapt_hydra_columns(
            finder_id="aegean",
            depth="deep",
            columns=nonfinite,
        )
    with pytest.raises(ValueError, match="unsupported Hydra finder"):
        adapt_hydra_columns(
            finder_id=cast(HydraFinder, "unknown"),
            depth="deep",
            columns=columns,
        )
    with pytest.raises(ValueError, match="unsupported Hydra depth"):
        adapt_hydra_columns(
            finder_id="aegean",
            depth=cast(HydraDepth, "medium"),
            columns=columns,
        )


def test_public_selector_binds_approval_and_keeps_finders_closed() -> None:
    """The named selection approval cannot be broadened to finder execution."""
    decision = _selector()["load_selection_authorization"](_ROOT)

    assert decision["schema_review_sha256"].startswith("409318f5")
    assert decision["adapter_implementation_authorized"] is True
    assert decision["cutout_selection_authorized"] is True
    assert decision["finder_execution_authorized"] is False
    assert decision["qualification_opened"] is False


def test_public_selector_resamples_pixels_and_serializes_infinity() -> None:
    """Beam admission uses bilinear pixel values and strict JSON semantics."""
    namespace = _selector()
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [1.0, 1.0]
    wcs.wcs.cdelt = np.array([-0.01, 0.01])
    wcs.wcs.crval = [0.0, -30.0]
    wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]
    beam = np.arange(16, dtype=np.float64).reshape(4, 4)

    mean, valid = namespace["_resample_primary_beam"](
        x_start=1,
        y_start=1,
        side=2,
        context=namespace["_BeamContext"](
            image_wcs=wcs,
            primary_beam=beam,
            primary_beam_wcs=wcs,
        ),
    )

    assert valid is True
    assert mean == pytest.approx(7.5)
    empty = _tile(
        "empty",
        0,
        count=0,
        resolved=0.0,
        pair=float("inf"),
        dynamic=0.0,
        low_snr=0.0,
        primary_beam=0.5,
    )
    assert (
        namespace["_tile_attribute_record"](empty)["closest_pair_beams"]
        == "infinity"
    )


def test_public_selector_handles_only_the_known_unplaceable_truth_row(
    tmp_path: Path,
) -> None:
    """The one official NaN centroid is excluded by half-open membership."""
    namespace = _selector()
    truth_path = tmp_path / "truth.txt"
    truth = np.ones((2, 12), dtype=np.float64)
    truth[:, 0] = [1, 32_397_377]
    truth[:, 10] = 2
    truth[1, 3:5] = np.nan
    np.savetxt(truth_path, truth)

    loaded = namespace["_load_truth"](truth_path)

    assert loaded.shape == (2, 12)
    truth[1, 0] = 99
    np.savetxt(truth_path, truth)
    with pytest.raises(ValueError, match="centroid population changed"):
        namespace["_load_truth"](truth_path)


def test_public_population_semantics_remain_closed_after_selection() -> None:
    """A selected population cannot silently authorize finder or release."""
    strata = [
        "sparse",
        "ordinary",
        "crowded",
        "resolved",
        "close-pair",
        "high-dynamic-range",
        "low-apparent-SNR",
        "primary-beam-boundary",
    ]
    document = {
        "schema_version": 1,
        "population_id": "phase-5-public-comparison-selected-population",
        "status": "sealed-before-finder-execution",
        "selection_authorization": {
            "sha256": (
                "d60fb6454ffc93c240d06e2e40888e1a4d378bc242057276f63a6d82238f565b"
            )
        },
        "schema_review": {
            "sha256": (
                "409318f58cafe259b4347953051ef8dddcf2308f041e8145e4199f7ad281eed8"
            )
        },
        "acquisition": {
            "sha256": (
                "a74e60de95debcc53bdf43d4f6046a6f74befe8a85e849a5b0105f2ecb0bd0ce"
            )
        },
        "implementation": {
            "selector_sha256": (
                "0ddbc6566bb9b61dcf135857311068f8d5162eb6d04ff1d8481588c1cd980233"
            ),
            "adapter_sha256": (
                "3a3aa7c3118ebb7189e9bbc0363ee3eb04b4baf5f3c0fc08b95fc63a9369beac"
            ),
        },
        "sdc1": {
            "candidate_tile_count": 256,
            "admitted_tile_count": 32,
            "excluded_nonfinite_centroid_truth_ids": [32_397_377],
            "candidate_output_used": False,
            "selected_tiles": [
                {"stratum": stratum, "tile": {"tile_id": f"tile-{index}"}}
                for index, stratum in enumerate(strata)
            ],
        },
        "hydra": {
            "complete_images_no_crop": True,
            "published_catalogue_products_opened": False,
        },
        "finder_execution_authorized": False,
        "finder_outputs_created": False,
        "qualification_opened": False,
        "cutover_authorized": False,
        "release_authorized": False,
    }
    validate = _verifier()["validate_population_document"]

    validate(document)
    document["finder_execution_authorized"] = True
    with pytest.raises(ValueError, match="semantics are invalid"):
        validate(document)


def test_checked_public_population_registry_binds_terminal_evidence() -> None:
    """The durable registry retains exact selected identities and closures."""
    registry = json.loads(_REGISTRY.read_text(encoding="utf-8"))

    assert registry["population"] == {
        "admitted_tile_count": 32,
        "candidate_tile_count": 256,
        "excluded_nonfinite_centroid_truth_ids": [32_397_377],
        "path": (
            "benchmark-results/phase-5/public-comparison-selection/"
            "population.json"
        ),
        "selected_tile_count": 8,
        "sha256": (
            "0a7c2b18d96ee47277072528949c5a64239f0c3053d5e7b33c03b36c194b7824"
        ),
    }
    assert [item["stratum"] for item in registry["selected_tiles"]] == [
        "sparse",
        "ordinary",
        "crowded",
        "resolved",
        "close-pair",
        "high-dynamic-range",
        "low-apparent-SNR",
        "primary-beam-boundary",
    ]
    assert len({item["tile_id"] for item in registry["selected_tiles"]}) == 8
    assert registry["finder_execution_authorized"] is False
    assert registry["finder_outputs_created"] is False
    assert registry["qualification_opened"] is False
    assert registry["cutover_authorized"] is False
    assert registry["release_authorized"] is False
