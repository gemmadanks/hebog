# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Minimal deterministic PyBDSF-style catalogue view consumed by Rapthor."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import numpy as np
from astropy.io import fits
from astropy.table import Table

from hebog.data_models.catalogues import SourceCandidate, SourceCatalogue
from hebog.data_models.source_finding import MaterializedProduct
from hebog.io.materialization import MaterializedProductConflictError

RAPTHOR_CATALOGUE_COLUMNS = (
    "Source_id",
    "RA",
    "DEC",
    "Isl_Total_flux",
    "Total_flux",
    "DC_Maj",
    "E_RA",
    "E_DEC",
)
_COLUMN_UNITS = (
    None,
    "deg",
    "deg",
    "Jy",
    "Jy",
    "deg",
    "deg",
    "deg",
)
_CHECKSUM_COMMENT = "hebog deterministic Rapthor catalogue"


def _content_identity(path: Path) -> tuple[int, str]:
    """Return streaming byte count and SHA-256 for one closed file."""
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            byte_count += len(block)
            digest.update(block)
    return byte_count, digest.hexdigest()


def _product(path: Path) -> MaterializedProduct:
    """Describe one validated compatibility catalogue product."""
    byte_count, content_sha256 = _content_identity(path)
    return MaterializedProduct(
        product_role="source-catalogue",
        path=path,
        media_type="application/fits",
        byte_count=byte_count,
        content_sha256=content_sha256,
        scientific_status="valid",
        content_schema_version=1,
    )


def _optional(values: list[float | None]) -> np.ndarray:
    """Translate internal nulls to the FITS-view NaN convention."""
    return np.asarray(
        [np.nan if value is None else value for value in values],
        dtype=np.float64,
    )


def _deconvolved_major(source: SourceCandidate) -> float:
    """Translate reviewed full, one-axis, and unresolved states."""
    shape = source.deconvolved_shape
    if shape is not None:
        return float(shape.major_fwhm_degrees)
    if source.deconvolved_major_fwhm_degrees is not None:
        return float(source.deconvolved_major_fwhm_degrees)
    return 0.0 if "unresolved" in source.quality_flags else float("nan")


def _catalogue_hdus(catalogue: SourceCatalogue) -> fits.HDUList:
    """Build the exact eight-column Rapthor compatibility view."""
    if catalogue.position_epoch != "J2000":
        raise ValueError("Rapthor catalogue compatibility requires J2000")
    sources = catalogue.sources
    islands = {island.island_id: island for island in catalogue.islands}
    primary = fits.PrimaryHDU()
    primary.header["HBGROLE"] = "RAPTHOR"
    primary.header["HBGSCHE"] = 1
    primary.header["CATID"] = catalogue.catalogue_id
    primary.header["HBGFRAME"] = catalogue.coordinate_frame
    primary.header["HBGEPCH"] = catalogue.position_epoch
    primary.header["RESTFRQ"] = catalogue.reference_frequency_hz
    columns = [
        fits.Column(
            name="Source_id",
            format="J",
            array=np.arange(len(sources), dtype=np.int32),
        ),
        fits.Column(
            name="RA",
            format="D",
            unit="deg",
            array=np.asarray(
                [
                    source.position.right_ascension_degrees
                    for source in sources
                ],
                dtype=np.float64,
            ),
        ),
        fits.Column(
            name="DEC",
            format="D",
            unit="deg",
            array=np.asarray(
                [source.position.declination_degrees for source in sources],
                dtype=np.float64,
            ),
        ),
        fits.Column(
            name="Isl_Total_flux",
            format="D",
            unit="Jy",
            array=np.asarray(
                [
                    islands[source.island_id].integrated_flux_jy
                    for source in sources
                ],
                dtype=np.float64,
            ),
        ),
        fits.Column(
            name="Total_flux",
            format="D",
            unit="Jy",
            array=np.asarray(
                [source.flux.integrated_flux_jy for source in sources],
                dtype=np.float64,
            ),
        ),
        fits.Column(
            name="DC_Maj",
            format="D",
            unit="deg",
            array=np.asarray(
                [_deconvolved_major(source) for source in sources],
                dtype=np.float64,
            ),
        ),
        fits.Column(
            name="E_RA",
            format="D",
            unit="deg",
            array=_optional(
                [
                    source.position.right_ascension_error_degrees
                    for source in sources
                ]
            ),
        ),
        fits.Column(
            name="E_DEC",
            format="D",
            unit="deg",
            array=_optional(
                [
                    source.position.declination_error_degrees
                    for source in sources
                ]
            ),
        ),
    ]
    return fits.HDUList(
        [
            primary,
            fits.BinTableHDU.from_columns(columns, name="SOURCES"),
        ]
    )


def read_rapthor_catalogue_fits(path: Path) -> Table:
    """Read and strictly validate the frozen Rapthor catalogue view."""
    path = Path(path)
    try:
        with fits.open(path, mode="readonly", memmap=False) as hdus:
            if (
                tuple(hdu.name for hdu in hdus) != ("PRIMARY", "SOURCES")
                or hdus[0].header.get("HBGROLE") != "RAPTHOR"
                or hdus[0].header.get("HBGSCHE") != 1
                or hdus[0].header.get("HBGFRAME") != "icrs"
                or hdus[0].header.get("HBGEPCH") != "J2000"
                or tuple(hdus[1].columns.names) != RAPTHOR_CATALOGUE_COLUMNS
            ):
                raise ValueError("Rapthor catalogue FITS schema is invalid")
            units = tuple(
                None if column.unit is None else str(column.unit)
                for column in hdus[1].columns
            )
            if units != _COLUMN_UNITS:
                raise ValueError(
                    "Rapthor catalogue FITS schema has invalid units"
                )
            formats = tuple(str(column.format) for column in hdus[1].columns)
            if formats != ("J", "D", "D", "D", "D", "D", "D", "D"):
                raise ValueError(
                    "Rapthor catalogue FITS schema has invalid dtypes"
                )
    except OSError as error:
        raise ValueError(
            f"cannot read Rapthor catalogue FITS: {error}"
        ) from error
    return Table.read(path, format="fits", hdu=1)


def write_rapthor_catalogue_fits(
    path: Path,
    catalogue: SourceCatalogue,
) -> MaterializedProduct:
    """Atomically publish a deterministic validated Rapthor catalogue view."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with _catalogue_hdus(catalogue) as hdus:
            for hdu in hdus:
                hdu.add_checksum(when=_CHECKSUM_COMMENT)
            hdus.writeto(temporary, overwrite=False, checksum=False)
        read_rapthor_catalogue_fits(temporary)
        candidate = _product(temporary)
        if path.exists():
            current = _product(path)
            if (
                current.byte_count == candidate.byte_count
                and current.content_sha256 == candidate.content_sha256
            ):
                return current
            raise MaterializedProductConflictError(
                f"destination contains different product bytes: {path}"
            )
        temporary.replace(path)
        return _product(path)
    finally:
        temporary.unlink(missing_ok=True)
