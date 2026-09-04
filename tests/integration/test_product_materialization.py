# pyright: reportMissingTypeStubs=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Contracts for restartable FITS and JSON compatibility products."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from hebog.adapters.rapthor_catalogue import write_rapthor_catalogue_fits
from hebog.data_models import (
    CelestialWcs,
    ContinuumSourceFindingDiagnostics,
    FluxMeasurement,
    GaussianComponent,
    GaussianShape,
    ImageBounds,
    ImageMetadata,
    Island,
    MaterializedProduct,
    RestoringBeam,
    SkyPosition,
    SourceCandidate,
    SourceCatalogue,
    SourceFindingDiagnostics,
    SourceScaleProvenance,
    SpectralModel,
)
from hebog.data_models.catalogue_construction import CompletedCombinedCatalogue
from hebog.data_models.multiscale import (
    CombinedCatalogueState,
    CombinedIslandDisposition,
    CompletedCombinedCatalogueState,
)
from hebog.io import (
    CombinedProductPaths,
    FitsProductImageSource,
    InvalidMaterializedProductError,
    MaterializedProductConflictError,
    ProductMaterializationError,
    UnsupportedMaterializedProductError,
    materialize_combined_products,
    read_catalogue_fits_product,
    read_diagnostics_product,
    write_catalogue_fits_product,
    write_diagnostics_product,
    write_mask_fits_product,
    write_rms_fits_product,
)

pytestmark = pytest.mark.integration


def _metadata() -> ImageMetadata:
    """Return a small non-square celestial plane contract."""
    return ImageMetadata(
        shape_yx=(3, 4),
        unit="Jy/beam",
        beam=RestoringBeam(
            major_fwhm_degrees=0.01,
            minor_fwhm_degrees=0.008,
            position_angle_degrees=20.0,
        ),
        celestial_wcs=CelestialWcs(
            fits_header=(
                "WCSAXES =                    2\n"
                "CRPIX1  =                  1.0\n"
                "CRPIX2  =                  1.0\n"
                "CDELT1  =               -0.001\n"
                "CDELT2  =                0.001\n"
                "CUNIT1  = 'deg     '\n"
                "CUNIT2  = 'deg     '\n"
                "CTYPE1  = 'RA---SIN'\n"
                "CTYPE2  = 'DEC--SIN'\n"
                "CRVAL1  =                180.0\n"
                "CRVAL2  =                -30.0\n"
                "LONPOLE =                180.0\n"
                "LATPOLE =                -30.0\n"
                "MJDREF  =                  0.0\n"
                "RADESYS = 'ICRS    '"
            ),
            coordinate_frame="icrs",
        ),
        reference_frequency_hz=150_000_000.0,
    )


def _position() -> SkyPosition:
    """Return one source position with an explicit unavailable error."""
    return SkyPosition(
        right_ascension_degrees=180.25,
        declination_degrees=-30.5,
        right_ascension_error_degrees=0.0001,
        declination_error_degrees=None,
    )


def _flux() -> FluxMeasurement:
    """Return one source flux measurement."""
    return FluxMeasurement(
        peak_flux_jy_per_beam=0.01,
        peak_flux_error_jy_per_beam=0.001,
        integrated_flux_jy=0.012,
        integrated_flux_error_jy=None,
        local_rms_jy_per_beam=0.0002,
    )


def _shape() -> GaussianShape:
    """Return one fitted source shape."""
    return GaussianShape(
        major_fwhm_degrees=0.002,
        minor_fwhm_degrees=0.001,
        position_angle_degrees=45.0,
        major_fwhm_error_degrees=0.0001,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=2.0,
    )


def _spectrum() -> SpectralModel:
    """Return one explicit log-polynomial spectrum."""
    return SpectralModel(
        kind="log-polynomial",
        reference_frequency_hz=150_000_000.0,
        coefficients=(-0.7, 0.02),
    )


def _catalogue(
    *,
    catalogue_id: str = "catalogue-run-001",
    position_epoch: str = "J2000.0",
) -> SourceCatalogue:
    """Return a complete internal catalogue with nullable fields."""
    island = Island(
        island_id="island-00001",
        pixel_count=24,
        integrated_flux_jy=0.013,
        integrated_flux_error_jy=None,
        local_rms_jy_per_beam=0.0002,
        mean_brightness_jy_per_beam=-0.00001,
    )
    source = SourceCandidate(
        source_id="source-00001",
        island_id=island.island_id,
        position=_position(),
        flux=_flux(),
        spectral_model=_spectrum(),
        fitted_shape=None,
        deconvolved_shape=None,
        quality_flags=("deblended", "edge-truncated"),
        association_aperture_integrated_flux_jy=0.011,
    )
    component = GaussianComponent(
        gaussian_component_id="gaussian-component-00001",
        source_id=source.source_id,
        island_id=island.island_id,
        position=_position(),
        flux=_flux(),
        spectral_model=_spectrum(),
        fitted_shape=_shape(),
        deconvolved_shape=None,
        quality_flags=(),
    )
    return SourceCatalogue.create(
        catalogue_id=catalogue_id,
        coordinate_frame="icrs",
        position_epoch=position_epoch,
        reference_frequency_hz=150_000_000.0,
        islands=(island,),
        sources=(source,),
        gaussian_components=(component,),
    )


def _diagnostics(*, source_count: int = 1) -> SourceFindingDiagnostics:
    """Return versioned scientific summary metadata."""
    return SourceFindingDiagnostics(
        run_id="run-001",
        source_count=source_count,
        gaussian_component_count=1 if source_count else 0,
        island_count=1 if source_count else 0,
        rms_scientific_status="valid",
    )


def _continuum_diagnostics() -> ContinuumSourceFindingDiagnostics:
    """Return one provenance-rich combined continuum summary."""
    return ContinuumSourceFindingDiagnostics(
        run_id="run-001",
        source_count=2,
        gaussian_component_count=1,
        island_count=1,
        extended_source_count=1,
        terminal_disposition_count=1,
        rms_scientific_status="valid",
        source_provenance=(
            SourceScaleProvenance(
                source_id="source-extended",
                island_id="island-combined",
                association_id="scale-association-extended",
                scale_detection_ids=("scale-detection-extended",),
                selected_scale_detection_id="scale-detection-extended",
                contributing_scale_orders=(2,),
                relationship="contains-compact-support",
                support_pixel_count=20,
                visible_model_fraction=0.95,
            ),
        ),
    )


def _completed_combined(
    catalogue: SourceCatalogue,
    *,
    provenance: tuple[SourceScaleProvenance, ...] = (),
) -> CompletedCombinedCatalogue:
    """Return compact-only or accepted-continuum completion evidence."""
    island = catalogue.islands[0]
    compact_only = not provenance
    association_ids = () if compact_only else (provenance[0].association_id,)
    state = CompletedCombinedCatalogueState(
        state=CombinedCatalogueState(
            catalogue_id=catalogue.catalogue_id,
            accepted_island_ids=(island.island_id,),
            deferred_island_ids=(),
            dispositions=(
                CombinedIslandDisposition(
                    island_id=island.island_id,
                    status=(
                        "retained-compact"
                        if compact_only
                        else "accepted-multiscale"
                    ),
                    source_ids=(catalogue.sources[0].source_id,),
                    association_ids=association_ids,
                    reason=None,
                ),
            ),
            omissions=(),
        ),
        shard_count=1,
        reduction_depth=0,
        maximum_shard_record_count=1,
    )
    return CompletedCombinedCatalogue(
        catalogue=catalogue,
        terminal_state=state,
        source_provenance=provenance,
        compact_only_preserved=compact_only,
    )


def _current_identity(
    product: MaterializedProduct,
    path: Path,
) -> MaterializedProduct:
    """Update one immutable product record after deliberate corruption."""
    return product.model_copy(
        update={
            "content_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "byte_count": path.stat().st_size,
        }
    )


def test_catalogue_fits_round_trip_preserves_internal_schema(
    tmp_path: Path,
) -> None:
    """FITS tables preserve identities, units, nulls, and spectral arrays."""
    path = tmp_path / "catalogue.fits"
    catalogue = _catalogue()

    product = write_catalogue_fits_product(path, catalogue)

    assert product.product_role == "source-catalogue"
    assert product.media_type == "application/fits"
    assert product.content_schema_version == 3
    assert product.scientific_status == "valid"
    assert product.byte_count == path.stat().st_size
    assert (
        product.content_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    )
    assert read_catalogue_fits_product(path) == catalogue
    assert read_catalogue_fits_product(product) == catalogue
    with fits.open(path) as hdus:
        assert tuple(hdu.name for hdu in hdus) == (
            "PRIMARY",
            "ISLANDS",
            "SOURCES",
            "GAUSSIAN_COMPONENTS",
        )
        assert hdus[2].columns["RIGHT_ASCENSION"].unit == "deg"
        assert hdus[2].columns["PEAK_FLUX"].unit == "Jy/beam"
        assert hdus[2].columns["ASSOCIATION_APERTURE_FLUX"].unit == "Jy"
        assert "Source_id" not in hdus[2].columns.names

    assert write_catalogue_fits_product(path, catalogue) == product
    with pytest.raises(MaterializedProductConflictError, match="different"):
        write_catalogue_fits_product(
            path,
            _catalogue(catalogue_id="catalogue-run-002"),
        )


def test_catalogue_fits_round_trip_preserves_major_only_deconvolution(
    tmp_path: Path,
) -> None:
    """The internal product stores major while censoring minor and PA."""
    original = _catalogue()
    source_payload = original.sources[0].model_dump(mode="python")
    source_payload.update(
        {
            "deconvolved_shape": None,
            "deconvolved_major_fwhm_degrees": 0.0017,
            "quality_flags": ("major-axis-only",),
        }
    )
    source = SourceCandidate.model_validate(source_payload)
    catalogue = SourceCatalogue.create(
        catalogue_id=original.catalogue_id,
        coordinate_frame=original.coordinate_frame,
        position_epoch=original.position_epoch,
        reference_frequency_hz=original.reference_frequency_hz,
        islands=original.islands,
        sources=(source,),
        gaussian_components=(),
    )
    path = tmp_path / "major-only-catalogue.fits"

    write_catalogue_fits_product(path, catalogue)

    assert read_catalogue_fits_product(path) == catalogue
    with fits.open(path) as hdus:
        row = hdus[2].data[0]
        assert row["DECONVOLVED_MAJOR"] == pytest.approx(0.0017)
        assert np.isnan(row["DECONVOLVED_MINOR"])
        assert np.isnan(row["DECONVOLVED_POSITION_ANGLE"])


def test_empty_catalogue_is_a_structurally_complete_fits_product(
    tmp_path: Path,
) -> None:
    """Zero detections produce typed zero-row tables without a dummy row."""
    path = tmp_path / "empty-catalogue.fits"
    empty = SourceCatalogue.create(
        catalogue_id="catalogue-empty",
        coordinate_frame="icrs",
        position_epoch="J2000.0",
        reference_frequency_hz=150_000_000.0,
        islands=(),
        sources=(),
        gaussian_components=(),
    )

    write_catalogue_fits_product(path, empty)

    assert read_catalogue_fits_product(path) == empty
    with fits.open(path) as hdus:
        assert tuple(len(hdu.data) for hdu in hdus[1:]) == (0, 0, 0)
        assert "SOURCE_ID" in hdus[2].columns.names


def test_spectral_coefficients_use_deterministic_fixed_width_columns(
    tmp_path: Path,
) -> None:
    """Catalogue retries avoid platform-dependent FITS heap serialization."""
    original = _catalogue()
    reference_only = SpectralModel(
        kind="reference-frequency-only",
        reference_frequency_hz=original.reference_frequency_hz,
        coefficients=(),
    )
    source = original.sources[0].model_copy(
        update={"spectral_model": reference_only}
    )
    catalogue = SourceCatalogue.create(
        catalogue_id=original.catalogue_id,
        coordinate_frame=original.coordinate_frame,
        position_epoch=original.position_epoch,
        reference_frequency_hz=original.reference_frequency_hz,
        islands=original.islands,
        sources=(source,),
        gaussian_components=original.gaussian_components,
    )
    path = tmp_path / "fixed-spectra.fits"

    first = write_catalogue_fits_product(path, catalogue)

    assert read_catalogue_fits_product(path) == catalogue
    with fits.open(path) as hdus:
        source_format = str(hdus[2].columns["SPECTRAL_COEFFICIENTS"].format)
        component_format = str(hdus[3].columns["SPECTRAL_COEFFICIENTS"].format)
        assert source_format == "1D"
        assert component_format == "2D"
        assert not source_format.startswith(("P", "Q"))
        assert not component_format.startswith(("P", "Q"))
        for hdu in hdus:
            assert hdu.header.comments["CHECKSUM"] == (
                "hebog deterministic catalogue"
            )
            assert hdu.header.comments["DATASUM"] == (
                "hebog deterministic catalogue"
            )
            assert hdu.verify_checksum() == 1
            assert hdu.verify_datasum() == 1
    assert write_catalogue_fits_product(path, catalogue) == first


@pytest.mark.parametrize("payload", [b"not-fits", b""])
def test_catalogue_reader_rejects_corrupt_files(
    tmp_path: Path,
    payload: bytes,
) -> None:
    """Malformed files never become empty or successful catalogues."""
    path = tmp_path / "corrupt.fits"
    path.write_bytes(payload)

    with pytest.raises(InvalidMaterializedProductError, match="catalogue"):
        read_catalogue_fits_product(path)


def test_catalogue_reader_rejects_unknown_schema_and_structure(
    tmp_path: Path,
) -> None:
    """Unknown versions and missing required tables fail explicitly."""
    path = tmp_path / "catalogue.fits"
    write_catalogue_fits_product(path, _catalogue())
    with fits.open(path, mode="update", checksum=False) as hdus:
        hdus[0].header["HBGSCHE"] = 4

    with pytest.raises(UnsupportedMaterializedProductError, match="schema"):
        read_catalogue_fits_product(path)

    missing = tmp_path / "missing-table.fits"
    write_catalogue_fits_product(missing, _catalogue())
    with fits.open(missing) as hdus:
        fits.HDUList(hdus[:-1]).writeto(
            tmp_path / "rewritten.fits",
            overwrite=True,
        )
    (tmp_path / "rewritten.fits").replace(missing)
    with pytest.raises(InvalidMaterializedProductError, match="structure"):
        read_catalogue_fits_product(missing)


def test_catalogue_reader_rejects_wrong_role_or_columns(
    tmp_path: Path,
) -> None:
    """Catalogue headers and column names are closed schema fields."""
    wrong_role = tmp_path / "wrong-role.fits"
    write_catalogue_fits_product(wrong_role, _catalogue())
    with fits.open(wrong_role, mode="update", checksum=False) as hdus:
        hdus[0].header["HBGROLE"] = "RMS"
    with pytest.raises(InvalidMaterializedProductError, match="role"):
        read_catalogue_fits_product(wrong_role)

    wrong_column = tmp_path / "wrong-column.fits"
    write_catalogue_fits_product(wrong_column, _catalogue())
    with fits.open(wrong_column, mode="update", checksum=False) as hdus:
        hdus[1].header["TTYPE1"] = "BROKEN_ID"
    with pytest.raises(InvalidMaterializedProductError, match="columns"):
        read_catalogue_fits_product(wrong_column)

    wrong_unit = tmp_path / "wrong-unit.fits"
    write_catalogue_fits_product(wrong_unit, _catalogue())
    with fits.open(wrong_unit, mode="update", checksum=False) as hdus:
        source_columns = hdus[2].columns.names
        column_number = source_columns.index("RIGHT_ASCENSION") + 1
        hdus[2].header[f"TUNIT{column_number}"] = "arcsec"
    with pytest.raises(InvalidMaterializedProductError, match="units"):
        read_catalogue_fits_product(wrong_unit)

    heap_backed = tmp_path / "heap-backed-spectra.fits"
    write_catalogue_fits_product(heap_backed, _catalogue())
    with fits.open(heap_backed, mode="update", checksum=False) as hdus:
        coefficient_index = (
            hdus[2].columns.names.index("SPECTRAL_COEFFICIENTS") + 1
        )
        hdus[2].header[f"TFORM{coefficient_index}"] = "PD()"
    with pytest.raises(InvalidMaterializedProductError, match="fixed-width"):
        read_catalogue_fits_product(heap_backed)


@pytest.mark.parametrize(
    ("coefficients", "message"),
    [
        ((np.nan, 0.02), "padding"),
        ((np.inf, 0.02), "infinity"),
    ],
)
def test_catalogue_reader_rejects_invalid_spectral_padding(
    tmp_path: Path,
    coefficients: tuple[float, float],
    message: str,
) -> None:
    """Only a trailing NaN suffix may appear outside finite coefficients."""
    path = tmp_path / "invalid-spectral-padding.fits"
    write_catalogue_fits_product(path, _catalogue())
    with fits.open(path, mode="update", checksum=False) as hdus:
        hdus[2].data["SPECTRAL_COEFFICIENTS"][0] = coefficients

    with pytest.raises(InvalidMaterializedProductError, match=message):
        read_catalogue_fits_product(path)


def test_catalogue_reader_verifies_materialized_identity(
    tmp_path: Path,
) -> None:
    """Restart reads use the catalogue product's stored content identity."""
    path = tmp_path / "catalogue.fits"
    product = write_catalogue_fits_product(path, _catalogue())
    with path.open("ab") as handle:
        handle.write(b"changed")

    with pytest.raises(InvalidMaterializedProductError, match="identity"):
        read_catalogue_fits_product(product)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"FITTED_MAJOR": 0.001}, "partial Gaussian shape"),
        ({"FITTED_MAJOR_ERROR": 0.001}, "errors require"),
    ],
)
def test_catalogue_reader_rejects_partial_source_shapes(
    tmp_path: Path,
    updates: dict[str, float],
    message: str,
) -> None:
    """Unavailable FITS shapes cannot contain partial measurements."""
    path = tmp_path / "partial-shape.fits"
    write_catalogue_fits_product(path, _catalogue())
    with fits.open(path, mode="update", checksum=False) as hdus:
        for column, value in updates.items():
            hdus[2].data[column][0] = value

    with pytest.raises(InvalidMaterializedProductError, match=message):
        read_catalogue_fits_product(path)


def test_catalogue_reader_requires_a_component_fitted_shape(
    tmp_path: Path,
) -> None:
    """A Gaussian component cannot lose its fitted ellipse on disk."""
    path = tmp_path / "component-without-shape.fits"
    write_catalogue_fits_product(path, _catalogue())
    with fits.open(path, mode="update", checksum=False) as hdus:
        for column in (
            "FITTED_MAJOR",
            "FITTED_MINOR",
            "FITTED_POSITION_ANGLE",
            "FITTED_MAJOR_ERROR",
            "FITTED_MINOR_ERROR",
            "FITTED_POSITION_ANGLE_ERROR",
        ):
            hdus[3].data[column][0] = np.nan

    with pytest.raises(InvalidMaterializedProductError, match="requires"):
        read_catalogue_fits_product(path)


def test_rms_product_streams_row_blocks_and_preserves_invalid_pixels(
    tmp_path: Path,
) -> None:
    """RMS materialisation is row-block bounded and round-trips NaN masks."""
    path = tmp_path / "rms.fits"
    plane = np.array(
        [
            [0.1, 0.2, np.nan, 0.3],
            [0.4, 0.5, 0.6, 0.7],
            [0.8, 0.9, 1.0, 1.1],
        ],
        dtype=np.float32,
    )

    product = write_rms_fits_product(
        path,
        _metadata(),
        (plane[:1], plane[1:]),
        dtype=np.dtype("float32"),
        scientific_status="valid",
    )
    source = FitsProductImageSource(product)

    assert source.scientific_status() == "valid"
    assert source.metadata().shape_yx == (3, 4)
    assert source.metadata().unit == "Jy/beam"
    window = source.read_window(ImageBounds(0, 3, 0, 4))
    np.testing.assert_array_equal(window.values, plane)
    np.testing.assert_array_equal(window.valid_pixels, np.isfinite(plane))
    with fits.open(path) as hdus:
        assert hdus[0].header["BITPIX"] == -32
        assert hdus[0].header["HBGROLE"] == "RMS"


def test_unavailable_rms_is_explicitly_all_nan(tmp_path: Path) -> None:
    """Unavailable RMS pixels cannot be mistaken for input or estimates."""
    path = tmp_path / "unavailable-rms.fits"
    plane = np.full((3, 4), np.nan, dtype=np.float64)

    product = write_rms_fits_product(
        path,
        _metadata(),
        (plane,),
        dtype=np.dtype("float64"),
        scientific_status="unavailable",
    )
    source = FitsProductImageSource(product)

    assert source.scientific_status() == "unavailable"
    assert not source.read_window(ImageBounds(0, 3, 0, 4)).valid_pixels.any()


@pytest.mark.parametrize(
    ("blocks", "dtype", "status", "message"),
    [
        ((np.ones(4, dtype=np.float32),), "float32", "valid", "two"),
        ((np.ones((0, 4), dtype=np.float32),), "float32", "valid", "rows"),
        ((np.ones((4, 4), dtype=np.float32),), "float32", "valid", "many"),
        ((np.ones((2, 4), dtype=np.float32),), "float32", "valid", "rows"),
        ((np.ones((3, 3), dtype=np.float32),), "float32", "valid", "width"),
        ((np.ones((3, 4), dtype=np.float64),), "float32", "valid", "dtype"),
        (
            (-np.ones((3, 4), dtype=np.float32),),
            "float32",
            "valid",
            "negative",
        ),
        (
            (np.full((3, 4), np.inf, dtype=np.float32),),
            "float32",
            "valid",
            "infinite",
        ),
        (
            (np.full((3, 4), np.nan, dtype=np.float32),),
            "float32",
            "valid",
            "no finite",
        ),
        (
            (np.ones((3, 4), dtype=np.float32),),
            "float32",
            "unavailable",
            "all NaN",
        ),
    ],
)
def test_rms_writer_rejects_incomplete_or_unscientific_blocks(
    tmp_path: Path,
    blocks: tuple[np.ndarray, ...],
    dtype: str,
    status: str,
    message: str,
) -> None:
    """Incomplete, cast, negative, infinite, or fake RMS fails closed."""
    with pytest.raises(InvalidMaterializedProductError, match=message):
        write_rms_fits_product(
            tmp_path / "invalid-rms.fits",
            _metadata(),
            blocks,
            dtype=np.dtype(dtype),
            scientific_status=status,
        )
    assert not (tmp_path / "invalid-rms.fits").exists()


@pytest.mark.parametrize(
    ("dtype", "status", "message"),
    [
        ("int16", "valid", "float32 or float64"),
        ("float32", "provisional", "status"),
    ],
)
def test_rms_writer_rejects_unsupported_dtype_or_status(
    tmp_path: Path,
    dtype: str,
    status: str,
    message: str,
) -> None:
    """The RMS encoding and availability vocabulary are closed."""
    block = np.ones((3, 4), dtype=np.float32)
    with pytest.raises(InvalidMaterializedProductError, match=message):
        write_rms_fits_product(
            tmp_path / "unsupported-rms.fits",
            _metadata(),
            (block,),
            dtype=np.dtype(dtype),
            scientific_status=status,
        )


def test_mask_product_round_trip_is_binary_and_bounded(tmp_path: Path) -> None:
    """Boolean row blocks become a dimensionless binary FITS image."""
    path = tmp_path / "mask.fits"
    mask = np.array(
        [
            [True, False, True, False],
            [False, True, False, True],
            [True, True, False, False],
        ],
        dtype=np.bool_,
    )

    product = write_mask_fits_product(path, _metadata(), (mask[:2], mask[2:]))
    source = FitsProductImageSource(product)
    window = source.read_window(ImageBounds(0, 3, 0, 4))

    assert product.product_role == "source-filtering-mask"
    assert source.metadata().unit == "1"
    np.testing.assert_array_equal(window.values.astype(np.bool_), mask)
    np.testing.assert_array_equal(window.valid_pixels, True)
    with fits.open(path) as hdus:
        assert hdus[0].header["BITPIX"] == 8
        assert set(np.unique(hdus[0].data)) <= {0, 1}


def test_mask_writer_and_reader_reject_non_binary_values(
    tmp_path: Path,
) -> None:
    """Masks cannot silently cast arbitrary numeric arrays to truth values."""
    with pytest.raises(InvalidMaterializedProductError, match="boolean"):
        write_mask_fits_product(
            tmp_path / "invalid-mask.fits",
            _metadata(),
            (np.ones((3, 4), dtype=np.uint8),),
        )

    path = tmp_path / "corrupt-mask.fits"
    product = write_mask_fits_product(
        path,
        _metadata(),
        (np.zeros((3, 4), dtype=np.bool_),),
    )
    with fits.open(path, mode="update", checksum=False) as hdus:
        hdus[0].data[0, 0] = 2
    changed = _current_identity(product, path)
    with pytest.raises(InvalidMaterializedProductError, match="binary"):
        FitsProductImageSource(changed).read_window(ImageBounds(0, 3, 0, 4))


@pytest.mark.parametrize(
    "block",
    [
        np.zeros((2, 4), dtype=np.bool_),
        np.zeros((4, 4), dtype=np.bool_),
        np.zeros((0, 4), dtype=np.bool_),
        np.zeros(4, dtype=np.bool_),
    ],
)
def test_mask_writer_rejects_incomplete_or_invalid_row_blocks(
    tmp_path: Path,
    block: np.ndarray,
) -> None:
    """Mask output requires one complete sequence of full-width rows."""
    with pytest.raises(InvalidMaterializedProductError):
        write_mask_fits_product(
            tmp_path / "incomplete-mask.fits",
            _metadata(),
            (block,),
        )


def test_image_source_rejects_changed_bytes_and_unsupported_roles(
    tmp_path: Path,
) -> None:
    """Restart reads verify content identity and one image product role."""
    path = tmp_path / "rms.fits"
    plane = np.ones((3, 4), dtype=np.float32)
    product = write_rms_fits_product(
        path,
        _metadata(),
        (plane,),
        dtype=np.dtype("float32"),
        scientific_status="valid",
    )
    with path.open("ab") as handle:
        handle.write(b"changed")

    with pytest.raises(InvalidMaterializedProductError, match="identity"):
        FitsProductImageSource(product).metadata()

    catalogue = write_catalogue_fits_product(
        tmp_path / "catalogue.fits",
        _catalogue(),
    )
    with pytest.raises(UnsupportedMaterializedProductError, match="image"):
        FitsProductImageSource(catalogue)


def test_image_source_rejects_missing_or_inconsistent_product_metadata(
    tmp_path: Path,
) -> None:
    """Restart reads fail closed on absent files and status mismatches."""
    path = tmp_path / "rms.fits"
    product = write_rms_fits_product(
        path,
        _metadata(),
        (np.ones((3, 4), dtype=np.float32),),
        dtype=np.dtype("float32"),
        scientific_status="valid",
    )
    missing = product.model_copy(update={"path": tmp_path / "missing.fits"})
    with pytest.raises(InvalidMaterializedProductError, match="identity"):
        FitsProductImageSource(missing).metadata()

    inconsistent = product.model_copy(
        update={"scientific_status": "unavailable"}
    )
    with pytest.raises(InvalidMaterializedProductError, match="status"):
        FitsProductImageSource(inconsistent).scientific_status()

    unsupported = product.model_copy(update={"content_schema_version": 2})
    with pytest.raises(UnsupportedMaterializedProductError, match="schema"):
        FitsProductImageSource(unsupported).metadata()


@pytest.mark.parametrize(
    ("keyword", "value", "error_type", "message"),
    [
        ("HBGSCHE", 2, UnsupportedMaterializedProductError, "schema"),
        ("HBGROLE", "MASK", InvalidMaterializedProductError, "role"),
        ("HBGSTAT", "UNKNOWN", InvalidMaterializedProductError, "status"),
        ("BUNIT", "", InvalidMaterializedProductError, "metadata"),
    ],
)
def test_image_source_rejects_unsupported_or_corrupt_headers(
    tmp_path: Path,
    keyword: str,
    value: object,
    error_type: type[Exception],
    message: str,
) -> None:
    """Validate version, role, status, and physical metadata on restart."""
    path = tmp_path / f"corrupt-{keyword}.fits"
    product = write_rms_fits_product(
        path,
        _metadata(),
        (np.ones((3, 4), dtype=np.float32),),
        dtype=np.dtype("float32"),
        scientific_status="valid",
    )
    with fits.open(path, mode="update", checksum=False) as hdus:
        hdus[0].header[keyword] = value
    changed = _current_identity(product, path)

    with pytest.raises(error_type, match=message):
        FitsProductImageSource(changed).metadata()


@pytest.mark.parametrize(
    ("value", "message"),
    [(-1.0, "negative"), (np.inf, "infinite")],
)
def test_rms_reader_rejects_unscientific_pixels(
    tmp_path: Path,
    value: float,
    message: str,
) -> None:
    """Checksummed files still undergo bounded scientific validation."""
    path = tmp_path / "corrupt-rms.fits"
    product = write_rms_fits_product(
        path,
        _metadata(),
        (np.ones((3, 4), dtype=np.float32),),
        dtype=np.dtype("float32"),
        scientific_status="valid",
    )
    with fits.open(path, mode="update", checksum=False) as hdus:
        hdus[0].data[0, 0] = value
    changed = _current_identity(product, path)

    with pytest.raises(InvalidMaterializedProductError, match=message):
        FitsProductImageSource(changed).read_window(ImageBounds(0, 1, 0, 1))


def test_unavailable_rms_reader_rejects_finite_pixels(tmp_path: Path) -> None:
    """An unavailable status cannot relabel finite pixels after restart."""
    path = tmp_path / "unavailable-rms.fits"
    product = write_rms_fits_product(
        path,
        _metadata(),
        (np.full((3, 4), np.nan, dtype=np.float32),),
        dtype=np.dtype("float32"),
        scientific_status="unavailable",
    )
    with fits.open(path, mode="update", checksum=False) as hdus:
        hdus[0].data[0, 0] = 1.0
    changed = _current_identity(product, path)

    with pytest.raises(InvalidMaterializedProductError, match="all NaN"):
        FitsProductImageSource(changed).read_window(ImageBounds(0, 1, 0, 1))


def test_diagnostics_round_trip_is_canonical_versioned_json(
    tmp_path: Path,
) -> None:
    """Diagnostics use typed canonical JSON and restartable identity."""
    path = tmp_path / "diagnostics.json"
    diagnostics = _diagnostics()

    product = write_diagnostics_product(path, diagnostics)

    assert product.product_role == "diagnostics"
    assert product.media_type == "application/json"
    assert path.read_bytes() == diagnostics.canonical_json_bytes()
    assert read_diagnostics_product(path) == diagnostics
    assert read_diagnostics_product(product) == diagnostics
    assert write_diagnostics_product(path, diagnostics) == product


def test_continuum_diagnostics_round_trip_preserves_scale_provenance(
    tmp_path: Path,
) -> None:
    """Version two records retain auditable scale/support provenance."""
    path = tmp_path / "continuum-diagnostics.json"
    diagnostics = _continuum_diagnostics()

    product = write_diagnostics_product(path, diagnostics)

    assert product.content_schema_version == 2
    assert path.read_bytes() == diagnostics.canonical_json_bytes()
    assert read_diagnostics_product(path) == diagnostics
    assert read_diagnostics_product(product) == diagnostics


def test_diagnostics_record_schema_must_match_payload(tmp_path: Path) -> None:
    """Restart records cannot misdescribe otherwise valid diagnostic bytes."""
    product = write_diagnostics_product(
        tmp_path / "diagnostics.json",
        _diagnostics(),
    )
    mislabeled = product.model_copy(update={"content_schema_version": 2})

    with pytest.raises(
        InvalidMaterializedProductError, match="product record"
    ):
        read_diagnostics_product(mislabeled)


def test_compact_combined_materialization_preserves_existing_products(
    tmp_path: Path,
) -> None:
    """A compact-only finalization reproduces all Phase 4 product bytes."""
    catalogue = _catalogue(position_epoch="J2000")
    combined = _completed_combined(catalogue)
    metadata = _metadata()
    mask = np.asarray(
        [
            [False, True, False, False],
            [False, True, True, False],
            [False, False, False, False],
        ],
        dtype=np.bool_,
    )
    rms = write_rms_fits_product(
        tmp_path / "rms.fits",
        metadata,
        (np.full(metadata.shape_yx, 0.001, dtype=np.float32),),
        dtype=np.dtype("float32"),
        scientific_status="valid",
    )
    expected_catalogue = write_catalogue_fits_product(
        tmp_path / "expected-catalogue.fits",
        catalogue,
    )
    expected_mask = write_mask_fits_product(
        tmp_path / "expected-mask.fits",
        metadata,
        (mask,),
    )
    expected_diagnostics = write_diagnostics_product(
        tmp_path / "expected-diagnostics.json",
        _diagnostics(),
    )
    expected_rapthor = write_rapthor_catalogue_fits(
        tmp_path / "expected-rapthor.fits",
        catalogue,
    )

    materialized = materialize_combined_products(
        combined,
        metadata=metadata,
        rms_product=rms,
        compact_mask_row_blocks=(mask,),
        extended_mask_row_blocks=None,
        paths=CombinedProductPaths(
            catalogue=tmp_path / "combined-catalogue.fits",
            mask=tmp_path / "combined-mask.fits",
            diagnostics=tmp_path / "combined-diagnostics.json",
            rapthor_catalogue=tmp_path / "combined-rapthor.fits",
        ),
        run_id="run-001",
        wall_seconds=1.25,
    )

    assert materialized.result.rms is rms
    assert (
        materialized.result.catalogue.path.read_bytes()
        == expected_catalogue.path.read_bytes()
    )
    assert (
        materialized.result.mask.path.read_bytes()
        == expected_mask.path.read_bytes()
    )
    assert (
        materialized.result.diagnostics.path.read_bytes()
        == expected_diagnostics.path.read_bytes()
    )
    assert (
        materialized.rapthor_catalogue.path.read_bytes()
        == expected_rapthor.path.read_bytes()
    )


def test_continuum_materialization_unions_masks_and_reuses_rms(
    tmp_path: Path,
) -> None:
    """Accepted extended support augments products without rewriting RMS."""
    catalogue = _catalogue(position_epoch="J2000")
    provenance = (
        _continuum_diagnostics()
        .source_provenance[0]
        .model_copy(
            update={
                "source_id": catalogue.sources[0].source_id,
                "island_id": catalogue.islands[0].island_id,
            }
        ),
    )
    combined = _completed_combined(catalogue, provenance=provenance)
    metadata = _metadata()
    rms = write_rms_fits_product(
        tmp_path / "rms.fits",
        metadata,
        (np.full(metadata.shape_yx, 0.001, dtype=np.float32),),
        dtype=np.dtype("float32"),
        scientific_status="valid",
    )
    compact_mask = np.zeros(metadata.shape_yx, dtype=np.bool_)
    compact_mask[0, 0] = True
    extended_mask = np.zeros(metadata.shape_yx, dtype=np.bool_)
    extended_mask[2, 3] = True

    materialized = materialize_combined_products(
        combined,
        metadata=metadata,
        rms_product=rms,
        compact_mask_row_blocks=(compact_mask,),
        extended_mask_row_blocks=(extended_mask,),
        paths=CombinedProductPaths(
            catalogue=tmp_path / "catalogue.fits",
            mask=tmp_path / "mask.fits",
            diagnostics=tmp_path / "diagnostics.json",
            rapthor_catalogue=tmp_path / "rapthor.fits",
        ),
        run_id="run-001",
        wall_seconds=1.25,
    )

    assert materialized.result.rms is rms
    assert materialized.result.diagnostics.content_schema_version == 2
    np.testing.assert_array_equal(
        FitsProductImageSource(materialized.result.mask)
        .read_window(ImageBounds(0, 3, 0, 4))
        .values,
        np.logical_or(compact_mask, extended_mask),
    )


def test_combined_materialization_rejects_inconsistent_product_evidence(
    tmp_path: Path,
) -> None:
    """Metadata, paths, provenance, and mask roles fail before publication."""
    catalogue = _catalogue(position_epoch="J2000")
    compact = _completed_combined(catalogue)
    metadata = _metadata()
    rms = write_rms_fits_product(
        tmp_path / "rms.fits",
        metadata,
        (np.full(metadata.shape_yx, 0.001, dtype=np.float32),),
        dtype=np.dtype("float32"),
        scientific_status="valid",
    )
    paths = CombinedProductPaths(
        catalogue=tmp_path / "catalogue.fits",
        mask=tmp_path / "mask.fits",
        diagnostics=tmp_path / "diagnostics.json",
        rapthor_catalogue=tmp_path / "rapthor.fits",
    )
    compact_mask = (np.zeros(metadata.shape_yx, dtype=np.bool_),)

    with pytest.raises(ValueError, match="distinct"):
        CombinedProductPaths(
            catalogue=paths.catalogue,
            mask=paths.catalogue,
            diagnostics=paths.diagnostics,
            rapthor_catalogue=paths.rapthor_catalogue,
        )
    with pytest.raises(ProductMaterializationError, match="metadata"):
        materialize_combined_products(
            compact,
            metadata=replace(metadata, unit="Jy/pixel"),
            rms_product=rms,
            compact_mask_row_blocks=compact_mask,
            extended_mask_row_blocks=None,
            paths=paths,
            run_id="run-001",
            wall_seconds=0.0,
        )
    with pytest.raises(ProductMaterializationError, match="RMS plane"):
        materialize_combined_products(
            compact,
            metadata=metadata,
            rms_product=rms,
            compact_mask_row_blocks=compact_mask,
            extended_mask_row_blocks=None,
            paths=replace(paths, catalogue=rms.path),
            run_id="run-001",
            wall_seconds=0.0,
        )
    with pytest.raises(ProductMaterializationError, match="extended mask"):
        materialize_combined_products(
            compact,
            metadata=metadata,
            rms_product=rms,
            compact_mask_row_blocks=compact_mask,
            extended_mask_row_blocks=(
                np.zeros(metadata.shape_yx, dtype=np.bool_),
            ),
            paths=paths,
            run_id="run-001",
            wall_seconds=0.0,
        )
    provenance = (
        _continuum_diagnostics()
        .source_provenance[0]
        .model_copy(
            update={
                "source_id": catalogue.sources[0].source_id,
                "island_id": catalogue.islands[0].island_id,
            }
        ),
    )
    with pytest.raises(ProductMaterializationError, match="provenance"):
        materialize_combined_products(
            replace(compact, source_provenance=provenance),
            metadata=metadata,
            rms_product=rms,
            compact_mask_row_blocks=compact_mask,
            extended_mask_row_blocks=None,
            paths=paths,
            run_id="run-001",
            wall_seconds=0.0,
        )
    valid_continuum = _completed_combined(catalogue, provenance=provenance)
    continuum = replace(valid_continuum, source_provenance=())
    with pytest.raises(ProductMaterializationError, match="provenance"):
        materialize_combined_products(
            continuum,
            metadata=metadata,
            rms_product=rms,
            compact_mask_row_blocks=compact_mask,
            extended_mask_row_blocks=None,
            paths=paths,
            run_id="run-001",
            wall_seconds=0.0,
        )
    with pytest.raises(ProductMaterializationError, match="support masks"):
        materialize_combined_products(
            valid_continuum,
            metadata=metadata,
            rms_product=rms,
            compact_mask_row_blocks=compact_mask,
            extended_mask_row_blocks=None,
            paths=paths,
            run_id="run-001",
            wall_seconds=0.0,
        )


def test_diagnostics_reader_rejects_corrupt_or_unsupported_json(
    tmp_path: Path,
) -> None:
    """Malformed, noncanonical, unknown, and extra fields fail closed."""
    path = tmp_path / "diagnostics.json"
    path.write_bytes(b"not-json\n")
    with pytest.raises(InvalidMaterializedProductError, match="diagnostics"):
        read_diagnostics_product(path)

    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(InvalidMaterializedProductError, match="diagnostics"):
        read_diagnostics_product(path)

    path.write_text(
        json.dumps(_diagnostics().model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    with pytest.raises(InvalidMaterializedProductError, match="canonical"):
        read_diagnostics_product(path)

    path.write_text(
        json.dumps(_continuum_diagnostics().model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    with pytest.raises(InvalidMaterializedProductError, match="canonical"):
        read_diagnostics_product(path)

    with pytest.raises(InvalidMaterializedProductError, match="diagnostics"):
        read_diagnostics_product(tmp_path / "missing.json")

    document = _diagnostics().model_dump(mode="json")
    document["schema_version"] = 4
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(UnsupportedMaterializedProductError, match="schema"):
        read_diagnostics_product(path)

    document = _diagnostics().model_dump(mode="json")
    document["unexpected"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(InvalidMaterializedProductError, match="diagnostics"):
        read_diagnostics_product(path)
