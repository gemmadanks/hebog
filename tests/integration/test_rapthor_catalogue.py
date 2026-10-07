# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Rapthor source-catalogue FITS compatibility contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.adapters.rapthor_catalogue import (
    RAPTHOR_CATALOGUE_COLUMNS,
    read_rapthor_catalogue_fits,
    write_rapthor_catalogue_fits,
)
from hebog.data_models.catalogues import (
    POSITION_EPOCH,
    FluxMeasurement,
    GaussianShape,
    Island,
    SkyPosition,
    SourceCandidate,
    SourceCatalogue,
    SpectralModel,
)
from hebog.executors import SerialExecutor
from hebog.io import read_catalogue_fits_product
from hebog.io.materialization import MaterializedProductConflictError

pytestmark = pytest.mark.integration


def _catalogue(*, empty: bool = False) -> SourceCatalogue:
    """Return a canonical compact catalogue with all adapter states."""
    if empty:
        return SourceCatalogue.create(
            catalogue_id="compact-empty",
            coordinate_frame="icrs",
            position_epoch=POSITION_EPOCH,
            reference_frequency_hz=150_000_000.0,
            islands=(),
            sources=(),
            gaussian_components=(),
        )
    islands = (
        Island(
            island_id="island-00001",
            pixel_count=20,
            integrated_flux_jy=0.012,
            integrated_flux_error_jy=None,
            local_rms_jy_per_beam=0.001,
            mean_brightness_jy_per_beam=0.003,
        ),
        Island(
            island_id="island-00002",
            pixel_count=12,
            integrated_flux_jy=0.007,
            integrated_flux_error_jy=None,
            local_rms_jy_per_beam=0.0012,
            mean_brightness_jy_per_beam=0.002,
        ),
    )
    spectrum = SpectralModel(
        kind="reference-frequency-only",
        reference_frequency_hz=150_000_000.0,
        coefficients=(),
    )
    fitted = GaussianShape(
        major_fwhm_degrees=0.004,
        minor_fwhm_degrees=0.003,
        position_angle_degrees=30.0,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )
    resolved = GaussianShape(
        major_fwhm_degrees=0.002,
        minor_fwhm_degrees=0.001,
        position_angle_degrees=25.0,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )
    first = SourceCandidate(
        source_id="source-island-00001-region-00001",
        island_id="island-00001",
        position=SkyPosition(
            right_ascension_degrees=180.1,
            declination_degrees=-30.1,
            right_ascension_error_degrees=1e-5,
            declination_error_degrees=2e-5,
        ),
        flux=FluxMeasurement(
            peak_flux_jy_per_beam=0.01,
            peak_flux_error_jy_per_beam=0.001,
            integrated_flux_jy=0.011,
            integrated_flux_error_jy=0.0015,
            local_rms_jy_per_beam=0.001,
        ),
        spectral_model=spectrum,
        fitted_shape=fitted,
        deconvolved_shape=resolved,
        quality_flags=("resolved", "shape-uncertainty-unavailable"),
    )
    second = SourceCandidate(
        source_id="source-island-00002-region-00001",
        island_id="island-00002",
        position=SkyPosition(
            right_ascension_degrees=180.2,
            declination_degrees=-30.2,
            right_ascension_error_degrees=None,
            declination_error_degrees=None,
        ),
        flux=FluxMeasurement(
            peak_flux_jy_per_beam=0.006,
            peak_flux_error_jy_per_beam=None,
            integrated_flux_jy=0.0065,
            integrated_flux_error_jy=None,
            local_rms_jy_per_beam=0.0012,
        ),
        spectral_model=spectrum,
        fitted_shape=fitted,
        deconvolved_shape=None,
        quality_flags=(
            "position-flux-uncertainty-unavailable",
            "shape-uncertainty-unavailable",
            "unresolved",
        ),
    )
    return SourceCatalogue.create(
        catalogue_id="compact-reference",
        coordinate_frame="icrs",
        position_epoch=POSITION_EPOCH,
        reference_frequency_hz=150_000_000.0,
        islands=islands,
        sources=(second, first),
        gaussian_components=(),
    )


def test_rapthor_view_has_only_frozen_consumed_columns_and_units(
    tmp_path: Path,
) -> None:
    """The adapter exposes the real eight-column Rapthor consumer surface."""
    path = tmp_path / "source_catalog.fits"

    write_rapthor_catalogue_fits(path, _catalogue())
    table = Table.read(path, format="fits", hdu=1)

    assert tuple(table.colnames) == RAPTHOR_CATALOGUE_COLUMNS
    assert len(table) == 2
    assert table["Source_id"].dtype.kind == "i"
    assert table["Source_id"].dtype.itemsize == 4
    for name in RAPTHOR_CATALOGUE_COLUMNS[1:]:
        assert table[name].dtype.kind == "f"
        assert table[name].dtype.itemsize == 8
    assert table["RA"].unit.to_string() == "deg"
    assert table["DEC"].unit.to_string() == "deg"
    assert table["Isl_Total_flux"].unit.to_string() == "Jy"
    assert table["Total_flux"].unit.to_string() == "Jy"
    assert table["DC_Maj"].unit.to_string() == "deg"
    assert table["E_RA"].unit.to_string() == "deg"
    assert table["E_DEC"].unit.to_string() == "deg"


def test_rapthor_mapping_uses_canonical_numbering_and_adapter_sentinels(
    tmp_path: Path,
) -> None:
    """Internal null shapes remain distinct from compatibility zero."""
    path = tmp_path / "source_catalog.fits"

    write_rapthor_catalogue_fits(path, _catalogue())
    table = read_rapthor_catalogue_fits(path)

    np.testing.assert_array_equal(table["Source_id"], [0, 1])
    np.testing.assert_allclose(table["RA"], [180.1, 180.2])
    np.testing.assert_allclose(table["DEC"], [-30.1, -30.2])
    np.testing.assert_allclose(table["Isl_Total_flux"], [0.012, 0.007])
    np.testing.assert_allclose(table["Total_flux"], [0.011, 0.0065])
    np.testing.assert_allclose(table["DC_Maj"], [0.002, 0.0])
    assert table["E_RA"][0] == pytest.approx(1e-5)
    assert table["E_DEC"][0] == pytest.approx(2e-5)
    assert np.ma.is_masked(table["E_RA"][1])
    assert np.ma.is_masked(table["E_DEC"][1])
    raw = fits.getdata(path, 1)
    assert raw is not None
    assert np.isnan(raw["E_RA"][1])
    assert np.isnan(raw["E_DEC"][1])


def test_rapthor_mapping_preserves_identifiable_major_only_axis(
    tmp_path: Path,
) -> None:
    """Rapthor receives DC_Maj without requiring an invented minor axis."""
    original = _catalogue()
    source = original.sources[0]
    payload = source.model_dump(mode="python")
    payload.update(
        {
            "deconvolved_shape": None,
            "deconvolved_major_fwhm_degrees": 0.0017,
            "quality_flags": ("major-axis-only",),
        }
    )
    major_only = SourceCandidate.model_validate(payload)
    catalogue = SourceCatalogue.create(
        catalogue_id=original.catalogue_id,
        coordinate_frame=original.coordinate_frame,
        position_epoch=original.position_epoch,
        reference_frequency_hz=original.reference_frequency_hz,
        islands=original.islands,
        sources=(major_only,),
        gaussian_components=(),
    )

    path = tmp_path / "major-only.fits"
    write_rapthor_catalogue_fits(path, catalogue)
    table = read_rapthor_catalogue_fits(path)

    assert table["DC_Maj"][0] == pytest.approx(0.0017)


def test_empty_rapthor_view_retains_exact_schema(tmp_path: Path) -> None:
    """Zero detections need no dummy scientific source row."""
    path = tmp_path / "empty.fits"

    write_rapthor_catalogue_fits(path, _catalogue(empty=True))
    table = read_rapthor_catalogue_fits(path)

    assert len(table) == 0
    assert tuple(table.colnames) == RAPTHOR_CATALOGUE_COLUMNS
    assert table["Source_id"].dtype.itemsize == 4


def test_writer_rejects_non_j2000_catalogue(tmp_path: Path) -> None:
    """The minimal Rapthor view cannot hide an unsupported position epoch."""
    catalogue = _catalogue().model_copy(update={"position_epoch": "B1950"})

    with pytest.raises(ValueError, match=POSITION_EPOCH):
        write_rapthor_catalogue_fits(tmp_path / "b1950.fits", catalogue)


def test_rapthor_view_is_restart_deterministic_and_conflict_safe(
    tmp_path: Path,
) -> None:
    """A retry reuses equal bytes and rejects a different destination."""
    path = tmp_path / "source_catalog.fits"
    first = write_rapthor_catalogue_fits(path, _catalogue())
    original = path.read_bytes()

    second = write_rapthor_catalogue_fits(path, _catalogue())

    assert second == first
    assert path.read_bytes() == original
    changed = _catalogue().model_copy(update={"catalogue_id": "changed"})
    with pytest.raises(MaterializedProductConflictError, match="different"):
        write_rapthor_catalogue_fits(path, changed)


def test_reader_rejects_noncanonical_schema(tmp_path: Path) -> None:
    """Missing or reordered columns cannot reach Rapthor diagnostics."""
    path = tmp_path / "invalid.fits"
    columns = [fits.Column(name="RA", format="D", array=[180.0])]
    fits.HDUList(
        [fits.PrimaryHDU(), fits.BinTableHDU.from_columns(columns)]
    ).writeto(path)

    with pytest.raises(ValueError, match="schema"):
        read_rapthor_catalogue_fits(path)


@pytest.mark.parametrize(
    ("header_key", "value", "message"),
    [
        ("TUNIT2", "rad", "units"),
        ("TFORM1", "K", "dtypes"),
    ],
)
def test_reader_rejects_wrong_units_or_dtypes(
    tmp_path: Path,
    header_key: str,
    value: str,
    message: str,
) -> None:
    """Column meaning and physical representation are both frozen."""
    path = tmp_path / "invalid-column.fits"
    write_rapthor_catalogue_fits(path, _catalogue())
    with fits.open(path, mode="update", memmap=False) as hdus:
        hdus[1].header[header_key] = value
        hdus.flush(output_verify="silentfix")

    with pytest.raises(ValueError, match=message):
        read_rapthor_catalogue_fits(path)


def test_reader_translates_unreadable_fits_to_boundary_error(
    tmp_path: Path,
) -> None:
    """Corrupt bytes cannot leak an Astropy exception across the adapter."""
    path = tmp_path / "corrupt.fits"
    path.write_bytes(b"not a fits file")

    with pytest.raises(ValueError, match="cannot read"):
        read_rapthor_catalogue_fits(path)


# Rapthor keeps a source for its checks when its deconvolved major axis is
# under 10 arcsec and both position errors are under 2 arcsec
# (`docs/reference/rapthor-source-finding-contract.md`).
_RAPTHOR_MAXIMUM_DECONVOLVED_MAJOR_DEGREES = 10.0 / 3600.0
_RAPTHOR_MAXIMUM_POSITION_ERROR_DEGREES = 2.0 / 3600.0


def _rapthor_kept(path: Path) -> np.ndarray:
    """Apply Rapthor's cuts to the raw columns, where NaN fails each one."""
    table = fits.getdata(path, 1)
    assert table is not None
    return (
        (
            np.asarray(table["DC_Maj"])
            < _RAPTHOR_MAXIMUM_DECONVOLVED_MAJOR_DEGREES
        )
        & (np.asarray(table["E_RA"]) < _RAPTHOR_MAXIMUM_POSITION_ERROR_DEGREES)
        & (
            np.asarray(table["E_DEC"])
            < _RAPTHOR_MAXIMUM_POSITION_ERROR_DEGREES
        )
    )


def _write_finder_input(path: Path, *, with_sources: bool) -> None:
    """Write unit white noise, with four isolated unresolved sources or none.

    The 4-arcsec beam spans 4 pixels, and the sources sit at signal-to-noise
    ratios of 20 to 100, so each is one Gaussian well inside Rapthor's cuts.
    """
    shape_yx = (96, 128)
    y_pixels, x_pixels = np.mgrid[: shape_yx[0], : shape_yx[1]]
    values = np.random.default_rng(57).normal(0.0, 1.0, shape_yx)
    if with_sources:
        sigma_pixels = 4.0 / np.sqrt(8.0 * np.log(2.0))
        for amplitude, (x_centre, y_centre) in zip(
            (20.0, 40.0, 60.0, 100.0),
            ((30.3, 30.6), (95.2, 28.1), (33.7, 70.4), (90.5, 66.8)),
            strict=True,
        ):
            values += amplitude * np.exp(
                -0.5
                * ((x_pixels - x_centre) ** 2 + (y_pixels - y_centre) ** 2)
                / sigma_pixels**2
            )
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = shape_yx[1] / 2 + 1
    header["CRPIX2"] = shape_yx[0] / 2 + 1
    header["CRVAL1"] = 180.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["CUNIT1"] = header["CUNIT2"] = "deg"
    header["RESTFRQ"] = 150_000_000.0
    fits.PrimaryHDU(data=values, header=header).writeto(path)


@pytest.mark.parametrize("profile", ("continuum", "compact"))
@pytest.mark.parametrize("with_sources", (True, False))
def test_find_sources_catalogue_passes_through_the_view_and_the_cuts(
    tmp_path: Path,
    profile: Literal["continuum", "compact"],
    *,
    with_sources: bool,
) -> None:
    """Given a catalogue ``find_sources`` published, empty or not,
    when the view is written and read back,
    then every row carries the published position, fluxes and errors, and
    Rapthor keeps every isolated unresolved source.

    A ``continuum`` source of one Gaussian publishes that Gaussian's errors
    and deconvolved size, so its row passes the cuts as a ``compact`` row
    does (task 57).
    """
    image = tmp_path / "image.fits"
    _write_finder_input(image, with_sources=with_sources)
    result = hebog.find_sources(
        SourceFinderRequest(image, tmp_path / "products", f"view-{profile}"),
        SourceFinderConfig(5.0, 3.0, 7, profile=profile),
        SerialExecutor(),
    )
    catalogue = read_catalogue_fits_product(result.catalogue)
    view = tmp_path / "source_catalog.fits"

    write_rapthor_catalogue_fits(view, catalogue)
    table = read_rapthor_catalogue_fits(view)

    expected_count = 4 if with_sources else 0
    assert result.source_count == len(table) == expected_count
    assert tuple(table.colnames) == RAPTHOR_CATALOGUE_COLUMNS
    np.testing.assert_array_equal(table["Source_id"], np.arange(len(table)))
    islands = {island.island_id: island for island in catalogue.islands}
    raw = fits.getdata(view, 1)
    assert raw is not None
    for column, published in (
        (
            "RA",
            [
                row.position.right_ascension_degrees
                for row in catalogue.sources
            ],
        ),
        (
            "DEC",
            [row.position.declination_degrees for row in catalogue.sources],
        ),
        (
            "Isl_Total_flux",
            [
                islands[row.island_id].integrated_flux_jy
                for row in catalogue.sources
            ],
        ),
        (
            "Total_flux",
            [row.flux.integrated_flux_jy for row in catalogue.sources],
        ),
        (
            "E_RA",
            [
                row.position.right_ascension_error_degrees
                for row in catalogue.sources
            ],
        ),
        (
            "E_DEC",
            [
                row.position.declination_error_degrees
                for row in catalogue.sources
            ],
        ),
    ):
        np.testing.assert_array_equal(
            raw[column],
            np.asarray(
                [np.nan if value is None else value for value in published],
                dtype=np.float64,
            ),
            err_msg=column,
        )
    assert np.count_nonzero(_rapthor_kept(view)) == expected_count
