# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportAttributeAccessIssue=false
"""Tests for validation product readers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table
from pytest_mock import MockerFixture

from hebog.validation.products import (
    aegean_support_label_plane,
    build_hebog_segment_catalogue,
    build_hebog_segment_moment_catalogue,
    load_aegean_catalogue,
    load_comparison_catalogue,
    load_pybdsf_catalogue,
    load_pybdsf_gaussian_catalogue,
    write_comparison_catalogue,
)

_ROOT = Path(__file__).parents[3]
_CATALOGUE = (
    _ROOT / "tests/data/pybdsf/pybdsf-compact-reference-256/release/"
    "source_catalog.fits"
)


def test_pybdsf_reader_treats_nonpositive_errors_as_unavailable(
    tmp_path: Path,
) -> None:
    """PyBDSF zero and NaN sentinels do not become invalid uncertainties."""
    output = tmp_path / "catalogue.fits"
    with fits.open(_CATALOGUE) as source:
        source[1].data["E_RA"][0] = np.nan
        source[1].data["E_Maj"][0] = 0.0
        source.writeto(output)

    row = load_pybdsf_catalogue(output)[0]
    table = cast(Any, fits.getdata(output, ext=1))

    assert row.right_ascension_error_degrees is None
    assert row.fitted_shape is not None
    assert row.fitted_shape.major_fwhm_error_degrees is None
    assert row.association_integrated_flux_jy == float(table["Total_flux"][0])


def test_pybdsf_gaussian_reader_preserves_component_and_source_identity(
    tmp_path: Path,
) -> None:
    """Gaussian centres retain their PyBDSF source grouping."""
    names = (
        "Gaus_id",
        "Isl_id",
        "Source_id",
        "Wave_id",
        "RA",
        "E_RA",
        "DEC",
        "E_DEC",
        "Total_flux",
        "E_Total_flux",
        "Peak_flux",
        "E_Peak_flux",
        "Maj",
        "E_Maj",
        "Min",
        "E_Min",
        "PA",
        "E_PA",
        "DC_Maj",
        "E_DC_Maj",
        "DC_Min",
        "E_DC_Min",
        "DC_PA",
        "E_DC_PA",
    )
    rows = (
        (
            2,
            0,
            4,
            1,
            10.0,
            0.001,
            -30.0,
            0.001,
            0.7,
            0.1,
            0.6,
            0.1,
            0.002,
            0.0001,
            0.001,
            0.0001,
            20.0,
            2.0,
            0.001,
            0.0001,
            0.0005,
            0.0001,
            20.0,
            2.0,
        ),
        (
            1,
            0,
            4,
            0,
            10.001,
            0.001,
            -30.0,
            0.001,
            0.3,
            0.1,
            0.25,
            0.1,
            0.002,
            0.0001,
            0.001,
            0.0001,
            25.0,
            2.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        ),
    )
    path = tmp_path / "gaussian_catalog.fits"
    Table(rows=rows, names=names).write(path)

    sources = load_pybdsf_gaussian_catalogue(path)

    assert tuple(source.identifier for source in sources) == (
        "pybdsf-island-0-source-4-wave-0-gaussian-1",
        "pybdsf-island-0-source-4-wave-1-gaussian-2",
    )
    assert all(source.component_count == 2 for source in sources)
    assert all(
        source.association_integrated_flux_jy == 1.0 for source in sources
    )
    assert sources[0].deconvolution_status == "unresolved"
    assert sources[1].deconvolution_status == "resolved"


def _write_aegean_catalogues(
    component_path: Path,
    island_path: Path,
) -> None:
    """Write the exact maintained Aegean column boundary used by the reader."""
    components = Table(
        rows=(
            (
                0,
                0,
                10.0,
                -30.0,
                1.0,
                0.1,
                1.2,
                0.2,
                6.0,
                0.5,
                3.0,
                0.4,
                20.0,
                2.0,
                0,
            ),
            (
                0,
                1,
                10.001,
                -30.0,
                0.5,
                np.nan,
                0.6,
                0.0,
                5.0,
                0.4,
                2.5,
                0.3,
                30.0,
                0.0,
                4,
            ),
        ),
        names=(
            "island",
            "source",
            "ra",
            "dec",
            "peak_flux",
            "err_peak_flux",
            "int_flux",
            "err_int_flux",
            "a",
            "err_a",
            "b",
            "err_b",
            "pa",
            "err_pa",
            "flags",
        ),
    )
    islands = Table(
        rows=((0, 2, 10.0005, -30.0, 1.0, 1.9, 0.3),),
        names=(
            "island",
            "components",
            "ra",
            "dec",
            "peak_flux",
            "int_flux",
            "err_int_flux",
        ),
    )
    components.write(component_path)
    islands.write(island_path)


def test_aegean_reader_uses_stable_ids_and_island_flux(tmp_path: Path) -> None:
    """Random Aegean UUIDs never enter matching or association identity."""
    component_path = tmp_path / "catalog_comp.fits"
    island_path = tmp_path / "catalog_isle.fits"
    _write_aegean_catalogues(component_path, island_path)

    sources = load_aegean_catalogue(component_path, island_path)

    assert tuple(item.identifier for item in sources) == (
        "aegean-island-0-component-0",
        "aegean-island-0-component-1",
    )
    assert all(item.island_identifier == "aegean-island-0" for item in sources)
    assert all(item.component_count == 2 for item in sources)
    assert all(item.association_integrated_flux_jy == 1.9 for item in sources)
    assert sources[0].fitted_shape is not None
    assert sources[0].fitted_shape.major_fwhm_degrees == 6.0 / 3600.0
    assert sources[1].peak_flux_error_jy_per_beam is None
    assert sources[1].integrated_flux_error_jy is None
    assert sources[1].quality_flags == ("aegean-flags-4",)


def test_aegean_support_proxy_is_island_grouped_and_deterministic(
    tmp_path: Path,
) -> None:
    """Three-sigma fitted ellipses are an association proxy, not a mask."""
    component_path = tmp_path / "catalog_comp.fits"
    island_path = tmp_path / "catalog_isle.fits"
    _write_aegean_catalogues(component_path, island_path)
    sources = load_aegean_catalogue(component_path, island_path)
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = 21
    header["NAXIS2"] = 21
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 11.0
    header["CRPIX2"] = 11.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0

    first, first_labels = aegean_support_label_plane(
        sources,
        header,
        shape_yx=(21, 21),
    )
    second, second_labels = aegean_support_label_plane(
        tuple(reversed(sources)),
        header,
        shape_yx=(21, 21),
    )

    np.testing.assert_array_equal(first, second)
    assert first_labels == second_labels == {"aegean-island-0": 1}
    assert first[10, 10] == 1
    assert first[0, 0] == 0


def test_hebog_segment_catalogue_measures_original_aperture_and_round_trips(
    tmp_path: Path,
) -> None:
    """Extended flux recovers wings while position retains exact identity."""
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = 21
    header["NAXIS2"] = 21
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 11.0
    header["CRPIX2"] = 11.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    yy, xx = np.indices((21, 21), dtype=np.float64)
    image = np.exp(-0.5 * ((xx - 10.0) ** 2 + (yy - 10.0) ** 2) / 2.0)
    labels = np.zeros((21, 21), dtype=np.int32)
    labels[9:12, 9:12] = 4

    sources = build_hebog_segment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        labels,
        header,
        beam_major_fwhm_pixels=3.0,
        beam_minor_fwhm_pixels=2.0,
    )
    path = tmp_path / "segments.json"
    write_comparison_catalogue(path, sources)

    assert load_comparison_catalogue(path) == sources
    assert sources[0].identifier == "hebog-segment-4"
    assert sources[0].right_ascension_degrees == pytest.approx(10.0)
    assert sources[0].declination_degrees == pytest.approx(-30.0)
    observable_flux = float(np.sum(image, dtype=np.float64))
    beam_area_pixels = 2.0 * np.pi / (8.0 * np.log(2.0)) * 3.0 * 2.0
    assert sources[0].integrated_flux_jy == pytest.approx(
        observable_flux / beam_area_pixels
    )


def test_hebog_segment_moment_catalogue_publishes_sky_shape_and_round_trips(
    tmp_path: Path,
) -> None:
    """Exact owner moments become an honest WCS-aware public ellipse."""
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = 41
    header["NAXIS2"] = 41
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["RADESYS"] = "ICRS"
    header["CRPIX1"] = 21.0
    header["CRPIX2"] = 21.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 2.0 / 3600.0
    header["BMAJ"] = 2.0 / 3600.0
    header["BMIN"] = 1.0 / 3600.0
    header["BPA"] = 0.0
    yy, xx = np.indices((41, 41), dtype=np.float64)
    image = np.exp(
        -0.5 * (((xx - 20.0) / 3.0) ** 2 + ((yy - 20.0) / 2.0) ** 2)
    )
    labels = np.ones(image.shape, dtype=np.int32)

    sources = build_hebog_segment_moment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        labels,
        header,
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=0.5,
        measurement_aperture_radius_beams=1.5,
    )
    path = tmp_path / "moment-shapes.json"
    write_comparison_catalogue(path, sources)

    source = sources[0]
    assert source.fitted_shape is not None
    assert source.fitted_shape.major_fwhm_degrees * 3600.0 == pytest.approx(
        2.0 * np.sqrt(2.0 * np.log(2.0)) * 4.0,
        rel=2e-6,
    )
    assert source.fitted_shape.minor_fwhm_degrees * 3600.0 == pytest.approx(
        2.0 * np.sqrt(2.0 * np.log(2.0)) * 3.0,
        rel=2e-6,
    )
    assert source.fitted_shape.position_angle_degrees == pytest.approx(0.0)
    assert source.deconvolution_status == "resolved"
    assert source.deconvolved_shape is not None
    assert "segment-moment-equivalent-shape" in source.quality_flags
    assert source.fitted_shape.major_fwhm_error_degrees is None
    assert load_comparison_catalogue(path) == sources


def test_hebog_moment_catalogue_reports_singular_shape_unavailable() -> None:
    """A line-like segment does not acquire a fabricated circular ellipse."""
    image = np.zeros((7, 7), dtype=np.float64)
    labels = np.zeros(image.shape, dtype=np.int32)
    labels[3, 2:5] = 4
    image[labels == 4] = 1.0
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["RADESYS"] = "ICRS"
    header["CRPIX1"] = 4.0
    header["CRPIX2"] = 4.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["BMAJ"] = 2.0 / 3600.0
    header["BMIN"] = 1.0 / 3600.0
    header["BPA"] = 0.0

    source = build_hebog_segment_moment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        labels,
        header,
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=1.0,
    )[0]

    assert source.fitted_shape is None
    assert source.deconvolution_status == "unavailable"
    assert source.deconvolved_shape is None
    assert source.quality_flags == (
        "segment-moment-equivalent-shape",
        "shape-unavailable",
    )


@pytest.mark.parametrize(
    ("beam_major_arcseconds", "beam_minor_arcseconds", "beam_pa", "status"),
    (
        (
            2.0 * np.sqrt(2.0 * np.log(2.0)) * 3.1,
            2.0 * np.sqrt(2.0 * np.log(2.0)) * 2.1,
            90.0,
            "unresolved",
        ),
        (
            2.0 * np.sqrt(2.0 * np.log(2.0)) * 2.0,
            2.0 * np.sqrt(2.0 * np.log(2.0)) * 2.0,
            0.0,
            "major-axis-only",
        ),
    ),
)
def test_hebog_moment_catalogue_preserves_partial_deconvolution_states(
    beam_major_arcseconds: float,
    beam_minor_arcseconds: float,
    beam_pa: float,
    status: str,
) -> None:
    """Beam subtraction distinguishes unresolved and one-axis shapes."""
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["RADESYS"] = "ICRS"
    header["CRPIX1"] = 21.0
    header["CRPIX2"] = 21.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["BMAJ"] = beam_major_arcseconds / 3600.0
    header["BMIN"] = beam_minor_arcseconds / 3600.0
    header["BPA"] = beam_pa
    yy, xx = np.indices((41, 41), dtype=np.float64)
    image = np.exp(
        -0.5 * (((xx - 20.0) / 3.0) ** 2 + ((yy - 20.0) / 2.0) ** 2)
    )

    source = build_hebog_segment_moment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        np.ones(image.shape, dtype=np.int32),
        header,
        beam_major_fwhm_pixels=3.0,
        beam_minor_fwhm_pixels=2.0,
    )[0]

    assert source.deconvolution_status == status
    assert status in source.quality_flags


def test_hebog_moment_catalogue_marks_missing_beam_shape_unavailable() -> None:
    """Missing beam metadata cannot fabricate deconvolution evidence."""
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["RADESYS"] = "ICRS"
    header["CRPIX1"] = 3.0
    header["CRPIX2"] = 3.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    image = np.ones((5, 5), dtype=np.float64)

    source = build_hebog_segment_moment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        np.ones(image.shape, dtype=np.int32),
        header,
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=1.0,
    )[0]

    assert source.fitted_shape is None
    assert source.deconvolution_status == "unavailable"
    assert "shape-unavailable" in source.quality_flags


def test_hebog_moment_catalogue_marks_transform_failure_unavailable(
    mocker: MockerFixture,
) -> None:
    """A failed local sky transform cannot fabricate a pixel-space shape."""
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["RADESYS"] = "ICRS"
    header["CRPIX1"] = 3.0
    header["CRPIX2"] = 3.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["BMAJ"] = 2.0 / 3600.0
    header["BMIN"] = 1.0 / 3600.0
    header["BPA"] = 0.0
    mocker.patch(
        "hebog.validation.products.local_tangent_plane_transform_from_wcs",
        side_effect=ValueError("singular transform"),
    )
    image = np.ones((5, 5), dtype=np.float64)

    source = build_hebog_segment_moment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        np.ones(image.shape, dtype=np.int32),
        header,
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=1.0,
    )[0]

    assert source.fitted_shape is None
    assert source.deconvolution_status == "unavailable"
    assert "shape-unavailable" in source.quality_flags


def test_aegean_products_reject_schema_and_association_drift(
    tmp_path: Path,
) -> None:
    """Maintained Aegean schema or island-count changes fail explicitly."""
    component_path = tmp_path / "catalog_comp.fits"
    island_path = tmp_path / "catalog_isle.fits"
    _write_aegean_catalogues(component_path, island_path)
    islands = cast(Table, Table.read(island_path))
    islands["components"][0] = 3
    changed_islands = tmp_path / "changed_isle.fits"
    islands.write(changed_islands)

    with pytest.raises(ValueError, match="component count differs"):
        load_aegean_catalogue(component_path, changed_islands)

    components = cast(Table, Table.read(component_path))
    components.remove_column("flags")
    changed_components = tmp_path / "changed_comp.fits"
    components.write(changed_components)
    with pytest.raises(ValueError, match="misses columns: flags"):
        load_aegean_catalogue(changed_components, island_path)


def test_support_and_catalogue_boundaries_reject_ambiguous_products(
    tmp_path: Path,
) -> None:
    """Proxy and JSON products never infer missing identity or shape."""
    component_path = tmp_path / "catalog_comp.fits"
    island_path = tmp_path / "catalog_isle.fits"
    _write_aegean_catalogues(component_path, island_path)
    sources = load_aegean_catalogue(component_path, island_path)
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 2.0
    header["CRPIX2"] = 2.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0

    with pytest.raises(ValueError, match="positive axes"):
        aegean_support_label_plane(sources, header, shape_yx=(0, 3))
    with pytest.raises(ValueError, match="island identifiers"):
        aegean_support_label_plane(
            (replace(sources[0], island_identifier=None),),
            header,
            shape_yx=(3, 3),
        )
    with pytest.raises(ValueError, match="identifiers must be unique"):
        write_comparison_catalogue(
            tmp_path / "duplicate.json",
            (sources[0], sources[0]),
        )
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON array"):
        load_comparison_catalogue(malformed)


def test_hebog_segment_catalogue_rejects_invalid_planes_and_beam() -> None:
    """Extended measurement cannot coerce fractional labels or a zero beam."""
    image = np.ones((3, 3), dtype=np.float64)
    valid = np.ones((3, 3), dtype=np.bool_)
    header = fits.Header()

    with pytest.raises(ValueError, match="integer array"):
        build_hebog_segment_catalogue(
            image,
            np.zeros_like(image),
            valid,
            np.ones((3, 3), dtype=np.float64),
            header,
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=1.0,
        )
    with pytest.raises(ValueError, match="beam axes"):
        build_hebog_segment_catalogue(
            image,
            np.zeros_like(image),
            valid,
            np.ones((3, 3), dtype=np.int32),
            header,
            beam_major_fwhm_pixels=0.0,
            beam_minor_fwhm_pixels=1.0,
        )
    negative = np.ones((3, 3), dtype=np.int32)
    negative[0, 0] = -1
    with pytest.raises(ValueError, match="non-negative"):
        build_hebog_segment_catalogue(
            image,
            np.zeros_like(image),
            valid,
            negative,
            header,
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=1.0,
        )
    with pytest.raises(ValueError, match="match the image"):
        build_hebog_segment_catalogue(
            image,
            np.zeros_like(image),
            valid,
            np.ones((2, 3), dtype=np.int32),
            header,
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=1.0,
        )


def test_hebog_segment_catalogue_uses_signed_original_aperture_pixels() -> (
    None
):
    """Flux includes observable wings without moving the exact centroid."""
    image = np.zeros((21, 21), dtype=np.float64)
    labels = np.zeros((21, 21), dtype=np.int32)
    labels[9:12, 9:12] = 4
    image[labels == 4] = 1.0
    image[8:13, 8:13] += 0.25
    image[10, 13:16] = 0.5
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 11.0
    header["CRPIX2"] = 11.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0

    sources = build_hebog_segment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        labels,
        header,
        beam_major_fwhm_pixels=3.0,
        beam_minor_fwhm_pixels=2.0,
    )

    beam_area_pixels = 2.0 * np.pi / (8.0 * np.log(2.0)) * 3.0 * 2.0
    assert sources[0].integrated_flux_jy == pytest.approx(
        float(np.sum(image, dtype=np.float64)) / beam_area_pixels
    )
    assert sources[0].right_ascension_degrees == pytest.approx(10.0)
    assert sources[0].declination_degrees == pytest.approx(-30.0)


def test_hebog_segment_catalogue_accepts_reviewed_measurement_aperture() -> (
    None
):
    """A prospective aperture excludes noise-dominated distant pixels."""
    image = np.zeros((25, 25), dtype=np.float64)
    labels = np.zeros((25, 25), dtype=np.int32)
    labels[11:14, 11:14] = 1
    image[labels == 1] = 1.0
    image[12, 19] = 4.0
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 13.0
    header["CRPIX2"] = 13.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0

    reviewed = build_hebog_segment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        labels,
        header,
        beam_major_fwhm_pixels=3.0,
        beam_minor_fwhm_pixels=2.0,
        measurement_aperture_radius_beams=1.5,
    )
    historical = build_hebog_segment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        labels,
        header,
        beam_major_fwhm_pixels=3.0,
        beam_minor_fwhm_pixels=2.0,
    )

    assert reviewed[0].integrated_flux_jy < (historical[0].integrated_flux_jy)

    with pytest.raises(ValueError, match="aperture radius"):
        build_hebog_segment_catalogue(
            image,
            np.zeros_like(image),
            np.ones_like(image, dtype=np.bool_),
            labels,
            header,
            beam_major_fwhm_pixels=3.0,
            beam_minor_fwhm_pixels=2.0,
            measurement_aperture_radius_beams=0.0,
        )


def test_hebog_segment_catalogue_accepts_denoised_position_signal() -> None:
    """Multiscale position weights do not alter original-pixel photometry."""
    image = np.zeros((9, 9), dtype=np.float64)
    labels = np.zeros((9, 9), dtype=np.int32)
    labels[3:6, 3:6] = 1
    image[labels == 1] = 1.0
    image[4, 5] = 3.0
    position_signal = np.zeros_like(image)
    position_signal[4, 4] = 3.0
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 5.0
    header["CRPIX2"] = 5.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0

    source = build_hebog_segment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        labels,
        header,
        beam_major_fwhm_pixels=3.0,
        beam_minor_fwhm_pixels=2.0,
        position_signal_jy_per_beam=position_signal,
    )[0]

    assert source.right_ascension_degrees == pytest.approx(10.0)
    assert source.declination_degrees == pytest.approx(-30.0)
    beam_area_pixels = 2.0 * np.pi / (8.0 * np.log(2.0)) * 3.0 * 2.0
    assert source.integrated_flux_jy == pytest.approx(
        float(np.sum(image)) / beam_area_pixels
    )

    with pytest.raises(ValueError, match="position signal"):
        build_hebog_segment_catalogue(
            image,
            np.zeros_like(image),
            np.ones_like(image, dtype=np.bool_),
            labels,
            header,
            beam_major_fwhm_pixels=3.0,
            beam_minor_fwhm_pixels=2.0,
            position_signal_jy_per_beam=position_signal[:-1],
        )


def test_compact_dominated_segment_keeps_original_position_weights() -> None:
    """A high peak-to-mean ratio bypasses the diffuse denoised estimator."""
    image = np.zeros((9, 9), dtype=np.float64)
    labels = np.zeros((9, 9), dtype=np.int32)
    labels[3:6, 3:6] = 1
    image[labels == 1] = 1.0
    image[4, 5] = 10.0
    position_signal = np.zeros_like(image)
    position_signal[4, 3] = 5.0
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 5.0
    header["CRPIX2"] = 5.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    arguments = (
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        labels,
        header,
    )
    keywords = {
        "beam_major_fwhm_pixels": 3.0,
        "beam_minor_fwhm_pixels": 2.0,
    }

    original = build_hebog_segment_catalogue(*arguments, **keywords)[0]
    hybrid = build_hebog_segment_catalogue(
        *arguments,
        **keywords,
        position_signal_jy_per_beam=position_signal,
    )[0]

    assert hybrid.right_ascension_degrees == (original.right_ascension_degrees)
    assert hybrid.declination_degrees == original.declination_degrees

    with pytest.raises(ValueError, match="peak-to-mean"):
        build_hebog_segment_catalogue(
            *arguments,
            **keywords,
            position_signal_jy_per_beam=position_signal,
            denoised_position_maximum_peak_to_mean_ratio=1.0,
        )


def test_unavailable_denoised_position_falls_back_to_original() -> None:
    """A non-positive reconstruction cannot remove a measurable segment."""
    image = np.ones((7, 7), dtype=np.float64)
    labels = np.zeros((7, 7), dtype=np.int32)
    labels[2:5, 2:5] = 1
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 4.0
    header["CRPIX2"] = 4.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    arguments = (
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        labels,
        header,
    )
    keywords = {
        "beam_major_fwhm_pixels": 3.0,
        "beam_minor_fwhm_pixels": 2.0,
    }

    original = build_hebog_segment_catalogue(*arguments, **keywords)
    fallback = build_hebog_segment_catalogue(
        *arguments,
        **keywords,
        position_signal_jy_per_beam=np.zeros_like(image),
    )

    assert fallback == original


def test_denoised_position_allows_an_invalid_only_segment() -> None:
    """Invalid native support remains mask-only without a reduction error."""
    labels = np.ones((3, 3), dtype=np.int32)

    sources = build_hebog_segment_catalogue(
        np.full(labels.shape, np.nan),
        np.full(labels.shape, np.nan),
        np.zeros(labels.shape, dtype=np.bool_),
        labels,
        fits.Header(),
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=1.0,
        position_signal_jy_per_beam=np.zeros(labels.shape),
    )

    assert sources == ()


def test_hebog_segment_apertures_do_not_double_count_close_sources() -> None:
    """Nearest-support ownership partitions overlapping flux apertures."""
    image = np.ones((13, 13), dtype=np.float64)
    labels = np.zeros((13, 13), dtype=np.int32)
    labels[6, 4] = 1
    labels[6, 8] = 2
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 7.0
    header["CRPIX2"] = 7.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0

    sources = build_hebog_segment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        labels,
        header,
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=1.0,
    )

    beam_area_pixels = 2.0 * np.pi / (8.0 * np.log(2.0)) * 2.0
    assert sum(source.integrated_flux_jy for source in sources) == (
        pytest.approx(image.size / beam_area_pixels)
    )


def test_hebog_unmeasurable_segment_remains_mask_only() -> None:
    """A non-physical segment cannot turn the finder run into an error."""
    image = np.ones((5, 5), dtype=np.float64)
    labels = np.zeros((5, 5), dtype=np.int32)
    labels[1:3, 1:3] = 1
    labels[3:5, 3:5] = 2
    image[labels == 2] = -1.0
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 3.0
    header["CRPIX2"] = 3.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0

    sources = build_hebog_segment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=np.bool_),
        labels,
        header,
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=1.0,
    )

    assert tuple(source.island_identifier for source in sources) == (
        "hebog-segment-1",
    )
