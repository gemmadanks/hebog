# pyright: reportMissingTypeStubs=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Versioned, restartable FITS and JSON product materialisation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from pydantic import ValidationError

from hebog.data_models.catalogues import (
    FluxMeasurement,
    GaussianComponent,
    GaussianShape,
    Island,
    SkyPosition,
    SourceCandidate,
    SourceCatalogue,
    SpectralModel,
)
from hebog.data_models.images import ImageMetadata
from hebog.data_models.source_finding import (
    MaterializedProduct,
    ProductRole,
    SourceFindingDiagnostics,
)
from hebog.io.base import ImageBounds, ImageWindow
from hebog.io.fits import FitsImageSource, InvalidFitsImageError

_CONTENT_SCHEMA_VERSION = 1
_IMAGE_DIMENSIONS = 2
_IMAGE_ROLES = {"rms": "RMS", "source-filtering-mask": "MASK"}
_IMAGE_MEDIA_TYPE = "image/fits"
_CATALOGUE_MEDIA_TYPE = "application/fits"
_DIAGNOSTICS_MEDIA_TYPE = "application/json"

_ISLAND_COLUMNS = (
    "ISLAND_ID",
    "PIXEL_COUNT",
    "INTEGRATED_FLUX",
    "INTEGRATED_FLUX_ERROR",
    "LOCAL_RMS",
    "MEAN_BRIGHTNESS",
)
_MEASURED_COLUMNS = (
    "ISLAND_ID",
    "RIGHT_ASCENSION",
    "RIGHT_ASCENSION_ERROR",
    "DECLINATION",
    "DECLINATION_ERROR",
    "PEAK_FLUX",
    "PEAK_FLUX_ERROR",
    "INTEGRATED_FLUX",
    "INTEGRATED_FLUX_ERROR",
    "LOCAL_RMS",
    "SPECTRAL_KIND",
    "REFERENCE_FREQUENCY",
    "SPECTRAL_COEFFICIENTS",
    "FITTED_MAJOR",
    "FITTED_MINOR",
    "FITTED_POSITION_ANGLE",
    "FITTED_MAJOR_ERROR",
    "FITTED_MINOR_ERROR",
    "FITTED_POSITION_ANGLE_ERROR",
    "DECONVOLVED_MAJOR",
    "DECONVOLVED_MINOR",
    "DECONVOLVED_POSITION_ANGLE",
    "DECONVOLVED_MAJOR_ERROR",
    "DECONVOLVED_MINOR_ERROR",
    "DECONVOLVED_POSITION_ANGLE_ERROR",
    "QUALITY_FLAGS",
)
_SOURCE_COLUMNS = ("SOURCE_ID", *_MEASURED_COLUMNS)
_COMPONENT_COLUMNS = (
    "GAUSSIAN_COMPONENT_ID",
    "SOURCE_ID",
    *_MEASURED_COLUMNS,
)
_CATALOGUE_COLUMN_UNITS: dict[str, str | None] = {
    "ISLAND_ID": None,
    "SOURCE_ID": None,
    "GAUSSIAN_COMPONENT_ID": None,
    "PIXEL_COUNT": None,
    "INTEGRATED_FLUX": "Jy",
    "INTEGRATED_FLUX_ERROR": "Jy",
    "LOCAL_RMS": "Jy/beam",
    "MEAN_BRIGHTNESS": "Jy/beam",
    "RIGHT_ASCENSION": "deg",
    "RIGHT_ASCENSION_ERROR": "deg",
    "DECLINATION": "deg",
    "DECLINATION_ERROR": "deg",
    "PEAK_FLUX": "Jy/beam",
    "PEAK_FLUX_ERROR": "Jy/beam",
    "SPECTRAL_KIND": None,
    "REFERENCE_FREQUENCY": "Hz",
    "SPECTRAL_COEFFICIENTS": None,
    "QUALITY_FLAGS": None,
    **{
        f"{prefix}_{suffix}": "deg"
        for prefix in ("FITTED", "DECONVOLVED")
        for suffix in (
            "MAJOR",
            "MINOR",
            "POSITION_ANGLE",
            "MAJOR_ERROR",
            "MINOR_ERROR",
            "POSITION_ANGLE_ERROR",
        )
    },
}


class ProductMaterializationError(ValueError):
    """A restartable product could not be written or validated."""


class InvalidMaterializedProductError(ProductMaterializationError):
    """A product is corrupt, incomplete, or scientifically invalid."""


class UnsupportedMaterializedProductError(InvalidMaterializedProductError):
    """A valid product uses an unsupported role or schema version."""


class MaterializedProductConflictError(ProductMaterializationError):
    """A destination already contains different product bytes."""


def _content_identity(path: Path) -> tuple[int, str]:
    """Return byte count and streaming SHA-256 for one closed file."""
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            byte_count += len(block)
            digest.update(block)
    return byte_count, digest.hexdigest()


def _product_record(
    path: Path,
    *,
    role: ProductRole,
    media_type: Literal["application/fits", "image/fits", "application/json"],
    scientific_status: Literal["valid", "unavailable"],
) -> MaterializedProduct:
    """Describe one validated, closed product file."""
    byte_count, content_sha256 = _content_identity(path)
    return MaterializedProduct(
        product_role=role,
        path=path,
        media_type=media_type,
        byte_count=byte_count,
        content_sha256=content_sha256,
        scientific_status=scientific_status,
        content_schema_version=_CONTENT_SCHEMA_VERSION,
    )


def _resolve_product_path(
    product_or_path: MaterializedProduct | Path,
    *,
    expected_role: ProductRole,
) -> Path:
    """Resolve a path and verify restart identity when a record is supplied."""
    if not isinstance(product_or_path, MaterializedProduct):
        return Path(product_or_path)
    product = product_or_path
    if product.product_role != expected_role:
        raise UnsupportedMaterializedProductError(
            f"expected {expected_role} product role, got "
            f"{product.product_role}"
        )
    if product.content_schema_version != _CONTENT_SCHEMA_VERSION:
        raise UnsupportedMaterializedProductError(
            f"unsupported materialized product schema: "
            f"{product.content_schema_version}"
        )
    if expected_role != "rms" and product.scientific_status != "valid":
        raise InvalidMaterializedProductError(
            f"{expected_role} product must be scientifically valid"
        )
    try:
        byte_count, content_sha256 = _content_identity(product.path)
    except OSError as error:
        raise InvalidMaterializedProductError(
            f"cannot verify {expected_role} product identity: {error}"
        ) from error
    if (
        byte_count != product.byte_count
        or content_sha256 != product.content_sha256
    ):
        raise InvalidMaterializedProductError(
            f"{expected_role} product identity does not match its record"
        )
    return product.path


def _materialize(  # noqa: PLR0913
    path: Path,
    *,
    write_temporary: Callable[[Path], None],
    validate_temporary: Callable[[Path], object],
    role: ProductRole,
    media_type: Literal["application/fits", "image/fits", "application/json"],
    scientific_status: Literal["valid", "unavailable"],
) -> MaterializedProduct:
    """Validate a same-directory temporary file before publishing it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        write_temporary(temporary)
        validate_temporary(temporary)
        candidate = _product_record(
            temporary,
            role=role,
            media_type=media_type,
            scientific_status=scientific_status,
        )
        if path.exists():
            current = _product_record(
                path,
                role=role,
                media_type=media_type,
                scientific_status=scientific_status,
            )
            if (
                current.byte_count == candidate.byte_count
                and current.content_sha256 == candidate.content_sha256
            ):
                return current
            raise MaterializedProductConflictError(
                f"destination contains different product bytes: {path}"
            )
        temporary.replace(path)
        return _product_record(
            path,
            role=role,
            media_type=media_type,
            scientific_status=scientific_status,
        )
    finally:
        temporary.unlink(missing_ok=True)


def _string_width(values: Sequence[str]) -> int:
    """Return a non-zero ASCII field width."""
    return max(
        1,
        max((len(value.encode("ascii")) for value in values), default=0),
    )


def _string_column(name: str, values: Sequence[str]) -> fits.Column:
    """Build one fixed-width ASCII FITS column."""
    width = _string_width(values)
    return fits.Column(name=name, format=f"{width}A", array=list(values))


def _float_column(
    name: str,
    values: Sequence[float | None],
    *,
    unit: str | None = None,
) -> fits.Column:
    """Build one float64 column using NaN for unavailable values."""
    array = np.asarray(
        [np.nan if value is None else value for value in values],
        dtype=np.float64,
    )
    return fits.Column(name=name, format="D", unit=unit, array=array)


def _shape_values(
    values: Sequence[GaussianShape | None],
    attribute: str,
) -> list[float | None]:
    """Extract one optional shape field for a table column."""
    return [
        None
        if shape is None
        else cast(float | None, getattr(shape, attribute))
        for shape in values
    ]


def _shape_columns(
    prefix: str,
    values: Sequence[GaussianShape | None],
) -> list[fits.Column]:
    """Build the six canonical columns for optional Gaussian ellipses."""
    fields = (
        ("MAJOR", "major_fwhm_degrees", "deg"),
        ("MINOR", "minor_fwhm_degrees", "deg"),
        ("POSITION_ANGLE", "position_angle_degrees", "deg"),
        ("MAJOR_ERROR", "major_fwhm_error_degrees", "deg"),
        ("MINOR_ERROR", "minor_fwhm_error_degrees", "deg"),
        ("POSITION_ANGLE_ERROR", "position_angle_error_degrees", "deg"),
    )
    return [
        _float_column(
            f"{prefix}_{suffix}",
            _shape_values(values, attribute),
            unit=unit,
        )
        for suffix, attribute, unit in fields
    ]


def _spectral_coefficient_column(
    spectra: Sequence[SpectralModel],
) -> fits.Column:
    """Build one deterministic fixed-width vector with trailing NaN padding."""
    width = max(
        1,
        max((len(spectrum.coefficients) for spectrum in spectra), default=0),
    )
    coefficients = np.full(
        (len(spectra), width),
        np.nan,
        dtype=np.float64,
    )
    for row_index, spectrum in enumerate(spectra):
        value_count = len(spectrum.coefficients)
        coefficients[row_index, :value_count] = spectrum.coefficients
    return fits.Column(
        name="SPECTRAL_COEFFICIENTS",
        format=f"{width}D",
        array=coefficients,
    )


def _measured_columns(
    values: Sequence[SourceCandidate | GaussianComponent],
) -> list[fits.Column]:
    """Build shared source and Gaussian-component columns."""
    positions = [value.position for value in values]
    fluxes = [value.flux for value in values]
    spectra = [value.spectral_model for value in values]
    fitted = [value.fitted_shape for value in values]
    deconvolved = [value.deconvolved_shape for value in values]
    columns = [
        _string_column("ISLAND_ID", [value.island_id for value in values]),
        _float_column(
            "RIGHT_ASCENSION",
            [value.right_ascension_degrees for value in positions],
            unit="deg",
        ),
        _float_column(
            "RIGHT_ASCENSION_ERROR",
            [value.right_ascension_error_degrees for value in positions],
            unit="deg",
        ),
        _float_column(
            "DECLINATION",
            [value.declination_degrees for value in positions],
            unit="deg",
        ),
        _float_column(
            "DECLINATION_ERROR",
            [value.declination_error_degrees for value in positions],
            unit="deg",
        ),
        _float_column(
            "PEAK_FLUX",
            [value.peak_flux_jy_per_beam for value in fluxes],
            unit="Jy/beam",
        ),
        _float_column(
            "PEAK_FLUX_ERROR",
            [value.peak_flux_error_jy_per_beam for value in fluxes],
            unit="Jy/beam",
        ),
        _float_column(
            "INTEGRATED_FLUX",
            [value.integrated_flux_jy for value in fluxes],
            unit="Jy",
        ),
        _float_column(
            "INTEGRATED_FLUX_ERROR",
            [value.integrated_flux_error_jy for value in fluxes],
            unit="Jy",
        ),
        _float_column(
            "LOCAL_RMS",
            [value.local_rms_jy_per_beam for value in fluxes],
            unit="Jy/beam",
        ),
        _string_column("SPECTRAL_KIND", [value.kind for value in spectra]),
        _float_column(
            "REFERENCE_FREQUENCY",
            [value.reference_frequency_hz for value in spectra],
            unit="Hz",
        ),
        _spectral_coefficient_column(spectra),
        *_shape_columns("FITTED", fitted),
        *_shape_columns("DECONVOLVED", deconvolved),
        _string_column(
            "QUALITY_FLAGS",
            [",".join(value.quality_flags) for value in values],
        ),
    ]
    return columns


def _catalogue_hdus(catalogue: SourceCatalogue) -> fits.HDUList:
    """Serialize one internal catalogue into exact version-one FITS HDUs."""
    primary = fits.PrimaryHDU()
    primary.header["HBGROLE"] = "CATALOGUE"
    primary.header["HBGSCHE"] = _CONTENT_SCHEMA_VERSION
    primary.header["CATID"] = catalogue.catalogue_id
    primary.header["HBGFRAME"] = catalogue.coordinate_frame
    primary.header["HBGEPCH"] = catalogue.position_epoch
    primary.header["RESTFRQ"] = catalogue.reference_frequency_hz

    islands = catalogue.islands
    island_columns = [
        _string_column("ISLAND_ID", [value.island_id for value in islands]),
        fits.Column(
            name="PIXEL_COUNT",
            format="K",
            array=np.asarray(
                [value.pixel_count for value in islands],
                dtype=np.int64,
            ),
        ),
        _float_column(
            "INTEGRATED_FLUX",
            [value.integrated_flux_jy for value in islands],
            unit="Jy",
        ),
        _float_column(
            "INTEGRATED_FLUX_ERROR",
            [value.integrated_flux_error_jy for value in islands],
            unit="Jy",
        ),
        _float_column(
            "LOCAL_RMS",
            [value.local_rms_jy_per_beam for value in islands],
            unit="Jy/beam",
        ),
        _float_column(
            "MEAN_BRIGHTNESS",
            [value.mean_brightness_jy_per_beam for value in islands],
            unit="Jy/beam",
        ),
    ]
    source_columns = [
        _string_column(
            "SOURCE_ID",
            [value.source_id for value in catalogue.sources],
        ),
        *_measured_columns(catalogue.sources),
    ]
    component_columns = [
        _string_column(
            "GAUSSIAN_COMPONENT_ID",
            [
                value.gaussian_component_id
                for value in catalogue.gaussian_components
            ],
        ),
        _string_column(
            "SOURCE_ID",
            [value.source_id for value in catalogue.gaussian_components],
        ),
        *_measured_columns(catalogue.gaussian_components),
    ]
    return fits.HDUList(
        [
            primary,
            fits.BinTableHDU.from_columns(island_columns, name="ISLANDS"),
            fits.BinTableHDU.from_columns(source_columns, name="SOURCES"),
            fits.BinTableHDU.from_columns(
                component_columns,
                name="GAUSSIAN_COMPONENTS",
            ),
        ]
    )


def _text(value: Any) -> str:
    """Normalize one FITS text cell."""
    if isinstance(value, bytes):
        return value.decode("ascii").rstrip()
    return str(value).rstrip()


def _optional_float(value: Any) -> float | None:
    """Map the internal FITS NaN null convention back to ``None``."""
    converted = float(value)
    return None if np.isnan(converted) else converted


def _shape_from_row(
    row: Any,
    prefix: str,
) -> GaussianShape | None:
    """Reconstruct one optional Gaussian ellipse from a FITS row."""
    major = _optional_float(row[f"{prefix}_MAJOR"])
    minor = _optional_float(row[f"{prefix}_MINOR"])
    position_angle = _optional_float(row[f"{prefix}_POSITION_ANGLE"])
    if major is None and minor is None and position_angle is None:
        errors = (
            _optional_float(row[f"{prefix}_MAJOR_ERROR"]),
            _optional_float(row[f"{prefix}_MINOR_ERROR"]),
            _optional_float(row[f"{prefix}_POSITION_ANGLE_ERROR"]),
        )
        if any(value is not None for value in errors):
            raise ValueError("shape errors require a measured shape")
        return None
    if major is None or minor is None or position_angle is None:
        raise ValueError("partial Gaussian shape")
    return GaussianShape(
        major_fwhm_degrees=major,
        minor_fwhm_degrees=minor,
        position_angle_degrees=position_angle,
        major_fwhm_error_degrees=_optional_float(row[f"{prefix}_MAJOR_ERROR"]),
        minor_fwhm_error_degrees=_optional_float(row[f"{prefix}_MINOR_ERROR"]),
        position_angle_error_degrees=_optional_float(
            row[f"{prefix}_POSITION_ANGLE_ERROR"]
        ),
    )


def _spectral_coefficients_from_row(row: Any) -> tuple[float, ...]:
    """Decode a fixed vector and require canonical trailing NaN padding."""
    values = np.atleast_1d(
        np.asarray(row["SPECTRAL_COEFFICIENTS"], dtype=np.float64)
    )
    if np.isinf(values).any():
        raise ValueError("spectral coefficients cannot contain infinity")
    padding = np.isnan(values)
    if not padding.any():
        return tuple(float(value) for value in values)
    first_padding = int(np.flatnonzero(padding)[0])
    if not padding[first_padding:].all():
        raise ValueError("spectral coefficient padding must be trailing")
    return tuple(float(value) for value in values[:first_padding])


def _measured_fields(row: Any) -> dict[str, Any]:
    """Reconstruct shared measured-object fields from one table row."""
    coefficients = _spectral_coefficients_from_row(row)
    quality_flags_text = _text(row["QUALITY_FLAGS"])
    return {
        "island_id": _text(row["ISLAND_ID"]),
        "position": SkyPosition(
            right_ascension_degrees=float(row["RIGHT_ASCENSION"]),
            right_ascension_error_degrees=_optional_float(
                row["RIGHT_ASCENSION_ERROR"]
            ),
            declination_degrees=float(row["DECLINATION"]),
            declination_error_degrees=_optional_float(
                row["DECLINATION_ERROR"]
            ),
        ),
        "flux": FluxMeasurement(
            peak_flux_jy_per_beam=float(row["PEAK_FLUX"]),
            peak_flux_error_jy_per_beam=_optional_float(
                row["PEAK_FLUX_ERROR"]
            ),
            integrated_flux_jy=float(row["INTEGRATED_FLUX"]),
            integrated_flux_error_jy=_optional_float(
                row["INTEGRATED_FLUX_ERROR"]
            ),
            local_rms_jy_per_beam=float(row["LOCAL_RMS"]),
        ),
        "spectral_model": SpectralModel(
            kind=cast(
                Literal["reference-frequency-only", "log-polynomial"],
                _text(row["SPECTRAL_KIND"]),
            ),
            reference_frequency_hz=float(row["REFERENCE_FREQUENCY"]),
            coefficients=coefficients,
        ),
        "deconvolved_shape": _shape_from_row(row, "DECONVOLVED"),
        "quality_flags": (
            tuple(quality_flags_text.split(",")) if quality_flags_text else ()
        ),
    }


def _require_catalogue_structure(hdus: fits.HDUList) -> None:
    """Require exact version-one HDUs and column names."""
    expected_hdus = ("PRIMARY", "ISLANDS", "SOURCES", "GAUSSIAN_COMPONENTS")
    if tuple(hdu.name for hdu in hdus) != expected_hdus:
        raise InvalidMaterializedProductError(
            "catalogue FITS structure does not match schema version 1"
        )
    expected_columns = (
        _ISLAND_COLUMNS,
        _SOURCE_COLUMNS,
        _COMPONENT_COLUMNS,
    )
    for hdu, columns in zip(hdus[1:], expected_columns, strict=True):
        if tuple(hdu.columns.names) != columns:
            raise InvalidMaterializedProductError(
                "catalogue FITS structure has unexpected columns"
            )
        for column in hdu.columns:
            expected_unit = _CATALOGUE_COLUMN_UNITS[column.name]
            actual_unit = None if column.unit is None else str(column.unit)
            if actual_unit != expected_unit:
                raise InvalidMaterializedProductError(
                    "catalogue FITS structure has unexpected column units"
                )
    for hdu in hdus[2:]:
        coefficient_format = str(hdu.columns["SPECTRAL_COEFFICIENTS"].format)
        repeat = coefficient_format[:-1]
        if (
            not coefficient_format.endswith("D")
            or not repeat.isdecimal()
            or int(repeat) < 1
        ):
            raise InvalidMaterializedProductError(
                "catalogue spectral coefficients must use a fixed-width "
                "float64 column"
            )


def read_catalogue_fits_product(
    product_or_path: MaterializedProduct | Path,
) -> SourceCatalogue:
    """Read and strictly validate an internal catalogue FITS product."""
    path = _resolve_product_path(
        product_or_path,
        expected_role="source-catalogue",
    )
    try:
        with fits.open(path, mode="readonly", memmap=False) as hdus:
            header = hdus[0].header
            schema_version = header.get("HBGSCHE")
            if schema_version != _CONTENT_SCHEMA_VERSION:
                raise UnsupportedMaterializedProductError(
                    f"unsupported catalogue content schema: {schema_version}"
                )
            if header.get("HBGROLE") != "CATALOGUE":
                raise InvalidMaterializedProductError(
                    "catalogue FITS has an invalid product role"
                )
            _require_catalogue_structure(hdus)
            islands = tuple(
                Island(
                    island_id=_text(row["ISLAND_ID"]),
                    pixel_count=int(row["PIXEL_COUNT"]),
                    integrated_flux_jy=float(row["INTEGRATED_FLUX"]),
                    integrated_flux_error_jy=_optional_float(
                        row["INTEGRATED_FLUX_ERROR"]
                    ),
                    local_rms_jy_per_beam=float(row["LOCAL_RMS"]),
                    mean_brightness_jy_per_beam=float(row["MEAN_BRIGHTNESS"]),
                )
                for row in hdus[1].data
            )
            sources = tuple(
                SourceCandidate(
                    source_id=_text(row["SOURCE_ID"]),
                    fitted_shape=_shape_from_row(row, "FITTED"),
                    **_measured_fields(row),
                )
                for row in hdus[2].data
            )
            components: list[GaussianComponent] = []
            for row in hdus[3].data:
                fitted_shape = _shape_from_row(row, "FITTED")
                if fitted_shape is None:
                    raise ValueError(
                        "Gaussian component requires fitted shape"
                    )
                components.append(
                    GaussianComponent(
                        gaussian_component_id=_text(
                            row["GAUSSIAN_COMPONENT_ID"]
                        ),
                        source_id=_text(row["SOURCE_ID"]),
                        fitted_shape=fitted_shape,
                        **_measured_fields(row),
                    )
                )
            return SourceCatalogue(
                catalogue_id=str(header["CATID"]),
                coordinate_frame=cast(
                    Literal["icrs"],
                    str(header["HBGFRAME"]),
                ),
                position_epoch=str(header["HBGEPCH"]),
                reference_frequency_hz=float(header["RESTFRQ"]),
                islands=islands,
                sources=sources,
                gaussian_components=tuple(components),
            )
    except UnsupportedMaterializedProductError:
        raise
    except InvalidMaterializedProductError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        raise InvalidMaterializedProductError(
            f"cannot read catalogue FITS product {path}: {error}"
        ) from error


def write_catalogue_fits_product(
    path: Path,
    catalogue: SourceCatalogue,
) -> MaterializedProduct:
    """Write one validated, idempotent internal catalogue FITS product."""

    def write(temporary: Path) -> None:
        with _catalogue_hdus(catalogue) as hdus:
            hdus.writeto(temporary, checksum=True)

    return _materialize(
        path,
        write_temporary=write,
        validate_temporary=read_catalogue_fits_product,
        role="source-catalogue",
        media_type=_CATALOGUE_MEDIA_TYPE,
        scientific_status="valid",
    )


def _image_header(
    metadata: ImageMetadata,
    *,
    dtype: np.dtype[Any],
    role: Literal["rms", "source-filtering-mask"],
    scientific_status: Literal["valid", "unavailable"],
) -> fits.Header:
    """Build a two-dimensional primary header for incremental writing."""
    header = fits.Header()
    header["SIMPLE"] = True
    if dtype == np.dtype("float32"):
        bitpix = -32
    elif dtype == np.dtype("float64"):
        bitpix = -64
    elif dtype == np.dtype("uint8"):
        bitpix = 8
    else:  # pragma: no cover - guarded by the public writers
        raise ValueError(f"unsupported FITS product dtype: {dtype}")
    header["BITPIX"] = bitpix
    header["NAXIS"] = 2
    header["NAXIS1"] = metadata.shape_yx[1]
    header["NAXIS2"] = metadata.shape_yx[0]
    celestial = fits.Header.fromstring(
        metadata.celestial_wcs.fits_header,
        sep="\n",
    )
    for card in celestial.cards:
        if card.keyword not in {"", "COMMENT", "HISTORY", "END"}:
            header[card.keyword] = (card.value, card.comment)
    header["BUNIT"] = metadata.unit if role == "rms" else "1"
    header["BMAJ"] = metadata.beam.major_fwhm_degrees
    header["BMIN"] = metadata.beam.minor_fwhm_degrees
    header["BPA"] = metadata.beam.position_angle_degrees
    header["RESTFRQ"] = metadata.reference_frequency_hz
    header["HBGROLE"] = _IMAGE_ROLES[role]
    header["HBGSCHE"] = _CONTENT_SCHEMA_VERSION
    header["HBGSTAT"] = scientific_status.upper()
    return header


def _require_row_block(
    block: npt.NDArray[Any],
    *,
    width: int,
    row_count: int,
    height: int,
) -> None:
    """Require one full-width, non-empty, in-range sequential row block."""
    if block.ndim != _IMAGE_DIMENSIONS:
        raise InvalidMaterializedProductError(
            "product row blocks must be two-dimensional"
        )
    if block.shape[1] != width:
        raise InvalidMaterializedProductError(
            f"product row block width must be {width}"
        )
    if block.shape[0] < 1:
        raise InvalidMaterializedProductError(
            "product row blocks must contain rows"
        )
    if row_count + block.shape[0] > height:
        raise InvalidMaterializedProductError(
            "product row blocks contain too many rows"
        )


def _write_rms_temporary(
    path: Path,
    metadata: ImageMetadata,
    row_blocks: Iterable[npt.NDArray[Any]],
    *,
    dtype: np.dtype[Any],
    scientific_status: Literal["valid", "unavailable"],
) -> None:
    """Incrementally write and scientifically validate RMS row blocks."""
    height, width = metadata.shape_yx
    row_count = 0
    finite_count = 0
    header = _image_header(
        metadata,
        dtype=dtype,
        role="rms",
        scientific_status=scientific_status,
    )
    with fits.StreamingHDU(str(path), header) as stream:
        for raw_block in row_blocks:
            block = np.asarray(raw_block)
            _require_row_block(
                block,
                width=width,
                row_count=row_count,
                height=height,
            )
            if block.dtype != dtype:
                raise InvalidMaterializedProductError(
                    f"RMS block dtype must be exactly {dtype.name}"
                )
            if np.isinf(block).any():
                raise InvalidMaterializedProductError(
                    "RMS blocks cannot contain infinite values"
                )
            finite = np.isfinite(block)
            if np.any(block[finite] < 0):
                raise InvalidMaterializedProductError(
                    "RMS blocks cannot contain negative values"
                )
            finite_count += int(np.count_nonzero(finite))
            row_count += block.shape[0]
            stream.write(np.ascontiguousarray(block))
    if row_count != height:
        raise InvalidMaterializedProductError(
            f"RMS product rows must total {height}; received {row_count}"
        )
    if scientific_status == "valid" and finite_count == 0:
        raise InvalidMaterializedProductError(
            "valid RMS product contains no finite estimates"
        )
    if scientific_status == "unavailable" and finite_count:
        raise InvalidMaterializedProductError(
            "unavailable RMS product must contain all NaN pixels"
        )


def _write_mask_temporary(
    path: Path,
    metadata: ImageMetadata,
    row_blocks: Iterable[npt.NDArray[Any]],
) -> None:
    """Incrementally write exact boolean mask row blocks as FITS uint8."""
    height, width = metadata.shape_yx
    row_count = 0
    header = _image_header(
        metadata,
        dtype=np.dtype("uint8"),
        role="source-filtering-mask",
        scientific_status="valid",
    )
    with fits.StreamingHDU(str(path), header) as stream:
        for raw_block in row_blocks:
            block = np.asarray(raw_block)
            _require_row_block(
                block,
                width=width,
                row_count=row_count,
                height=height,
            )
            if block.dtype != np.dtype(np.bool_):
                raise InvalidMaterializedProductError(
                    "mask row blocks must have boolean dtype"
                )
            row_count += block.shape[0]
            stream.write(np.ascontiguousarray(block, dtype=np.uint8))
    if row_count != height:
        raise InvalidMaterializedProductError(
            f"mask product rows must total {height}; received {row_count}"
        )


def _image_header_status(
    path: Path,
    role: Literal["rms", "source-filtering-mask"],
) -> Literal["valid", "unavailable"]:
    """Validate the product header and return its scientific status."""
    try:
        with fits.open(path, mode="readonly", memmap=True) as hdus:
            if len(hdus) != 1:
                raise InvalidMaterializedProductError(
                    "image product must contain one primary HDU"
                )
            header = hdus[0].header
            schema_version = header.get("HBGSCHE")
            if schema_version != _CONTENT_SCHEMA_VERSION:
                raise UnsupportedMaterializedProductError(
                    f"unsupported image product schema: {schema_version}"
                )
            if header.get("HBGROLE") != _IMAGE_ROLES[role]:
                raise InvalidMaterializedProductError(
                    "image product role does not match its materialized record"
                )
            raw_status = str(header.get("HBGSTAT", "")).lower()
            if raw_status not in {"valid", "unavailable"}:
                raise InvalidMaterializedProductError(
                    "image product has an invalid scientific status"
                )
            if role == "source-filtering-mask" and raw_status != "valid":
                raise InvalidMaterializedProductError(
                    "source-filtering mask must be scientifically valid"
                )
            return cast(Literal["valid", "unavailable"], raw_status)
    except (OSError, ValueError) as error:
        if isinstance(error, InvalidMaterializedProductError):
            raise
        raise InvalidMaterializedProductError(
            f"cannot read image product {path}: {error}"
        ) from error


def _validate_image_path(
    path: Path,
    *,
    role: Literal["rms", "source-filtering-mask"],
    scientific_status: Literal["valid", "unavailable"],
) -> None:
    """Validate a completed image header without loading its pixel plane."""
    status = _image_header_status(path, role)
    if status != scientific_status:
        raise InvalidMaterializedProductError(
            "image product scientific status does not match its record"
        )
    try:
        FitsImageSource(path).metadata()
    except InvalidFitsImageError as error:
        raise InvalidMaterializedProductError(
            f"cannot read image product {path}: {error}"
        ) from error


def write_rms_fits_product(
    path: Path,
    metadata: ImageMetadata,
    row_blocks: Iterable[npt.NDArray[Any]],
    *,
    dtype: np.dtype[Any],
    scientific_status: str,
) -> MaterializedProduct:
    """Write one row-block-bounded RMS FITS product without implicit casts."""
    dtype = np.dtype(dtype)
    if dtype not in {np.dtype("float32"), np.dtype("float64")}:
        raise InvalidMaterializedProductError(
            "RMS product dtype must be float32 or float64"
        )
    if scientific_status not in {"valid", "unavailable"}:
        raise InvalidMaterializedProductError(
            "RMS scientific status must be valid or unavailable"
        )
    status = cast(Literal["valid", "unavailable"], scientific_status)
    return _materialize(
        path,
        write_temporary=lambda temporary: _write_rms_temporary(
            temporary,
            metadata,
            row_blocks,
            dtype=dtype,
            scientific_status=status,
        ),
        validate_temporary=lambda temporary: _validate_image_path(
            temporary,
            role="rms",
            scientific_status=status,
        ),
        role="rms",
        media_type=_IMAGE_MEDIA_TYPE,
        scientific_status=status,
    )


def write_mask_fits_product(
    path: Path,
    metadata: ImageMetadata,
    row_blocks: Iterable[npt.NDArray[Any]],
) -> MaterializedProduct:
    """Write one row-block-bounded binary source-filtering mask."""
    return _materialize(
        path,
        write_temporary=lambda temporary: _write_mask_temporary(
            temporary,
            metadata,
            row_blocks,
        ),
        validate_temporary=lambda temporary: _validate_image_path(
            temporary,
            role="source-filtering-mask",
            scientific_status="valid",
        ),
        role="source-filtering-mask",
        media_type=_IMAGE_MEDIA_TYPE,
        scientific_status="valid",
    )


class FitsProductImageSource:
    """Read a checksum-verified RMS or mask product through bounded windows."""

    def __init__(self, product: MaterializedProduct) -> None:
        """Require a supported image-product role without opening its file."""
        if product.product_role not in _IMAGE_ROLES:
            raise UnsupportedMaterializedProductError(
                f"materialized role is not a supported image product: "
                f"{product.product_role}"
            )
        self._product = product
        self._role: Literal["rms", "source-filtering-mask"] = cast(
            Literal["rms", "source-filtering-mask"],
            product.product_role,
        )
        self._identity_validated = False

    def _validate(self) -> None:
        """Verify byte identity and product-level header fields."""
        if self._identity_validated:
            return
        _resolve_product_path(self._product, expected_role=self._role)
        status = _image_header_status(self._product.path, self._role)
        if status != self._product.scientific_status:
            raise InvalidMaterializedProductError(
                "image scientific status does not match its "
                "materialized record"
            )
        self._identity_validated = True

    def scientific_status(self) -> Literal["valid", "unavailable"]:
        """Return the verified scientific availability of this product."""
        self._validate()
        return self._product.scientific_status

    def metadata(self) -> ImageMetadata:
        """Return verified image metadata without materialising the plane."""
        self._validate()
        try:
            return FitsImageSource(self._product.path).metadata()
        except InvalidFitsImageError as error:
            raise InvalidMaterializedProductError(
                f"cannot read image product metadata: {error}"
            ) from error

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read and validate one bounded product window."""
        self._validate()
        try:
            window = FitsImageSource(self._product.path).read_window(bounds)
        except InvalidFitsImageError as error:
            raise InvalidMaterializedProductError(
                f"cannot read image product window: {error}"
            ) from error
        if self._role == "rms":
            finite = np.isfinite(window.values)
            if np.isinf(window.values).any():
                raise InvalidMaterializedProductError(
                    "RMS image contains infinite values"
                )
            if np.any(window.values[finite] < 0):
                raise InvalidMaterializedProductError(
                    "RMS image contains negative values"
                )
            if (
                self._product.scientific_status == "unavailable"
                and finite.any()
            ):
                raise InvalidMaterializedProductError(
                    "unavailable RMS image must contain all NaN pixels"
                )
        elif not np.all(np.isin(window.values, (0, 1))):
            raise InvalidMaterializedProductError(
                "source-filtering mask image must be binary"
            )
        return window


def read_diagnostics_product(
    product_or_path: MaterializedProduct | Path,
) -> SourceFindingDiagnostics:
    """Read and strictly validate canonical diagnostics JSON."""
    path = _resolve_product_path(
        product_or_path,
        expected_role="diagnostics",
    )
    try:
        payload = path.read_bytes()
        raw_document = json.loads(payload)
        if not isinstance(raw_document, dict):
            raise ValueError("diagnostics root must be an object")
        schema_version = raw_document.get("schema_version")
        if schema_version != _CONTENT_SCHEMA_VERSION:
            raise UnsupportedMaterializedProductError(
                f"unsupported diagnostics content schema: {schema_version}"
            )
        return SourceFindingDiagnostics.from_json_bytes(payload)
    except UnsupportedMaterializedProductError:
        raise
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as error:
        raise InvalidMaterializedProductError(
            f"cannot read diagnostics product {path}: {error}"
        ) from error


def write_diagnostics_product(
    path: Path,
    diagnostics: SourceFindingDiagnostics,
) -> MaterializedProduct:
    """Write one canonical, idempotent diagnostics JSON product."""

    def write(temporary: Path) -> None:
        temporary.write_bytes(diagnostics.canonical_json_bytes())

    return _materialize(
        path,
        write_temporary=write,
        validate_temporary=read_diagnostics_product,
        role="diagnostics",
        media_type=_DIAGNOSTICS_MEDIA_TYPE,
        scientific_status="valid",
    )
