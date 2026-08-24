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

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table

from hebog.adapters.rapthor_catalogue import (
    RAPTHOR_CATALOGUE_COLUMNS,
    read_rapthor_catalogue_fits,
    write_rapthor_catalogue_fits,
)
from hebog.algorithms.compact_preservation import (
    preserve_unassociated_compact_catalogue,
)
from hebog.data_models.catalogue_construction import CompletedCompactCatalogue
from hebog.data_models.catalogues import (
    FluxMeasurement,
    GaussianShape,
    Island,
    SkyPosition,
    SourceCandidate,
    SourceCatalogue,
    SpectralModel,
)
from hebog.data_models.multiscale import CrossScaleAssociation
from hebog.io.materialization import MaterializedProductConflictError

pytestmark = pytest.mark.integration


def _catalogue(*, empty: bool = False) -> SourceCatalogue:
    """Return a canonical compact catalogue with all adapter states."""
    if empty:
        return SourceCatalogue.create(
            catalogue_id="compact-empty",
            coordinate_frame="icrs",
            position_epoch="J2000",
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
        position_epoch="J2000",
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

    with pytest.raises(ValueError, match="J2000"):
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


def test_extended_only_evidence_preserves_exact_rapthor_catalogue_bytes(
    tmp_path: Path,
) -> None:
    """The no-op Phase 5 seam retains the Phase 4 compatibility product."""
    compact = CompletedCompactCatalogue(
        catalogue=_catalogue(),
        shard_count=2,
        reduction_depth=1,
        maximum_shard_record_count=1,
    )
    association = CrossScaleAssociation(
        association_id="scale-association-0001",
        scale_detection_ids=("scale-detection-0001",),
        compact_source_ids=(),
        selected_scale_detection_id="scale-detection-0001",
        contributing_scale_orders=(1, 2),
        relationship="extended-only",
    )
    before = write_rapthor_catalogue_fits(
        tmp_path / "compact-before.fits",
        compact.catalogue,
    )

    preserved = preserve_unassociated_compact_catalogue(
        compact,
        associations=(association,),
    )
    after = write_rapthor_catalogue_fits(
        tmp_path / "compact-after.fits",
        preserved.catalogue,
    )

    assert preserved is compact
    assert before.byte_count == after.byte_count
    assert before.content_sha256 == after.content_sha256
    assert (tmp_path / "compact-before.fits").read_bytes() == (
        tmp_path / "compact-after.fits"
    ).read_bytes()


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
