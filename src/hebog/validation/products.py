# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Immutable PyBDSF reference-product manifests and typed readers."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from math import ceil
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Self, TypeAlias, cast

import numpy as np
import numpy.typing as npt
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.algorithms.astrometry import (
    deconvolve_gaussian_shapes,
    local_tangent_plane_transform_from_wcs,
    moment_equivalent_gaussian_shape,
)
from hebog.algorithms.extended_measurement import (
    DetectedSegmentPosition,
    expand_detected_segment_labels,
    measure_detected_segment_position,
)
from hebog.algorithms.multiscale_association import ScaleDetectionPlane
from hebog.algorithms.source_association import (
    associate_components_by_multiscale_hierarchy,
    associate_detection_components,
    build_detection_component_records,
)
from hebog.data_models.catalogues import GaussianShape
from hebog.data_models.images import RestoringBeam
from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    SourceAssociationResult,
)
from hebog.validation.comparison import CatalogueEllipse, CatalogueSource
from hebog.validation.evidence import DatasetIdentity, SoftwareIdentity

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_REFERENCE_COUNT = 2
_PLANE_DIMENSIONS = 2
_ARCSECONDS_PER_DEGREE = 3600.0
_FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
_AEGEAN_SUPPORT_SIGMAS = 3.0
_MINIMUM_MOMENT_PIXELS = 3
_AEGEAN_COMPONENT_COLUMNS = {
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
}
_AEGEAN_ISLAND_COLUMNS = {
    "island",
    "components",
    "int_flux",
}

ProductName: TypeAlias = Literal[
    "apparent_sky.txt",
    "diagnostics.json",
    "flat_noise_rms.fits",
    "source_catalog.fits",
    "source_filter_mask.fits",
    "true_sky.txt",
    "true_sky_rms.fits",
]
_PRODUCT_NAMES: set[str] = {
    "apparent_sky.txt",
    "diagnostics.json",
    "flat_noise_rms.fits",
    "source_catalog.fits",
    "source_filter_mask.fits",
    "true_sky.txt",
    "true_sky_rms.fits",
}


class _ProductModel(BaseModel):
    """Strict immutable base for governed reference products."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProductArtifact(_ProductModel):
    """Repository-relative identity of one immutable reference artifact."""

    relative_path: str = Field(min_length=1)
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_relative_path(self) -> Self:
        """Keep product paths bounded by the repository root."""
        path = PurePosixPath(self.relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("product artifact path must stay relative")
        return self


class ReferenceProductSet(_ProductModel):
    """Products and provenance frozen from one measured reference run."""

    reference: Literal["release", "master"]
    captured_at: datetime
    source_run_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    source_repetition_index: int = Field(ge=1)
    subject: SoftwareIdentity
    related_software: tuple[SoftwareIdentity, ...]
    configuration_sha256: str = Field(pattern=_SHA256_PATTERN)
    environment_sha256: str = Field(pattern=_SHA256_PATTERN)
    artifacts: dict[ProductName, ProductArtifact]

    @model_validator(mode="after")
    def validate_products(self) -> Self:
        """Require every standardized Rapthor-facing product exactly once."""
        if (
            self.captured_at.tzinfo is None
            or self.captured_at.utcoffset() is None
        ):
            raise ValueError("reference capture time must include a timezone")
        if set(self.artifacts) != _PRODUCT_NAMES:
            raise ValueError(
                "reference set does not contain standard products"
            )
        return self


class ReferenceProductManifest(_ProductModel):
    """Released and master reference products for one governed dataset."""

    schema_version: Literal[1]
    dataset: DatasetIdentity
    product_sets: tuple[ReferenceProductSet, ReferenceProductSet]

    @model_validator(mode="after")
    def validate_reference_pair(self) -> Self:
        """Require one release and one master set with distinct identities."""
        references = {
            product_set.reference for product_set in self.product_sets
        }
        if references != {"release", "master"}:
            raise ValueError("manifest requires release and master products")
        run_ids = {
            product_set.source_run_id for product_set in self.product_sets
        }
        if len(run_ids) != _REFERENCE_COUNT:
            raise ValueError("reference product source run IDs must be unique")
        return self


def canonical_product_set_sha256(product_set: ReferenceProductSet) -> str:
    """Return the canonical digest of one product set and its provenance."""
    payload = json.dumps(
        product_set.model_dump(mode="json"),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_product_manifest_json(
    manifest: ReferenceProductManifest,
) -> str:
    """Serialize a product manifest deterministically with a final newline."""
    return (
        json.dumps(
            manifest.model_dump(mode="json"),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def write_reference_product_manifest(
    path: Path, manifest: ReferenceProductManifest
) -> None:
    """Atomically write one validated reference-product manifest."""
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        canonical_product_manifest_json(manifest),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def load_reference_product_manifest(path: Path) -> ReferenceProductManifest:
    """Load and validate one reference-product manifest."""
    return ReferenceProductManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _file_sha256(path: Path) -> str:
    """Hash a file without retaining it in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_reference_product_files(
    repository_root: Path,
    manifest: ReferenceProductManifest,
) -> None:
    """Fail closed if any checked-in reference product has changed."""
    root = repository_root.resolve()
    for product_set in manifest.product_sets:
        for artifact in product_set.artifacts.values():
            path = root / artifact.relative_path
            if not path.is_relative_to(root):
                raise ValueError("product artifact escapes repository root")
            if path.stat().st_size != artifact.bytes:
                raise ValueError(
                    f"reference product byte size changed: {path}"
                )
            if _file_sha256(path) != artifact.sha256:
                raise ValueError(f"reference product SHA-256 changed: {path}")


def product_set_by_reference(
    manifest: ReferenceProductManifest,
    reference: Literal["release", "master"],
) -> ReferenceProductSet:
    """Resolve one unique reference product set."""
    return next(
        item for item in manifest.product_sets if item.reference == reference
    )


def load_pybdsf_catalogue(path: Path) -> tuple[CatalogueSource, ...]:
    """Read governed PyBDSF source, shape, association, and error fields."""
    table = cast(npt.NDArray[np.void], fits.getdata(path, ext=1))

    def optional_positive(row: np.void, name: str) -> float | None:
        """Translate PyBDSF zero and NaN error sentinels to unavailable."""
        value = float(row[name])
        return value if np.isfinite(value) and value > 0.0 else None

    def ellipse(row: np.void, prefix: str) -> CatalogueEllipse:
        return CatalogueEllipse(
            major_fwhm_degrees=float(row[f"{prefix}Maj"]),
            minor_fwhm_degrees=float(row[f"{prefix}Min"]),
            position_angle_degrees=float(row[f"{prefix}PA"]),
            major_fwhm_error_degrees=optional_positive(
                row,
                f"E_{prefix}Maj",
            ),
            minor_fwhm_error_degrees=optional_positive(
                row,
                f"E_{prefix}Min",
            ),
            position_angle_error_degrees=optional_positive(
                row,
                f"E_{prefix}PA",
            ),
        )

    return tuple(
        CatalogueSource(
            identifier=str(row["Source_id"]),
            right_ascension_degrees=float(row["RA"]),
            declination_degrees=float(row["DEC"]),
            peak_flux_jy_per_beam=float(row["Peak_flux"]),
            integrated_flux_jy=float(row["Total_flux"]),
            association_integrated_flux_jy=float(row["Total_flux"]),
            right_ascension_error_degrees=optional_positive(row, "E_RA"),
            declination_error_degrees=optional_positive(row, "E_DEC"),
            peak_flux_error_jy_per_beam=optional_positive(
                row,
                "E_Peak_flux",
            ),
            integrated_flux_error_jy=optional_positive(row, "E_Total_flux"),
            fitted_shape=ellipse(row, ""),
            deconvolved_shape=(
                ellipse(row, "DC_")
                if float(row["DC_Maj"]) > 0 and float(row["DC_Min"]) > 0
                else None
            ),
            deconvolved_major_fwhm_degrees=(
                float(row["DC_Maj"])
                if float(row["DC_Maj"]) > 0 and not float(row["DC_Min"]) > 0
                else None
            ),
            deconvolution_status=(
                "resolved"
                if float(row["DC_Maj"]) > 0 and float(row["DC_Min"]) > 0
                else "major-axis-only"
                if float(row["DC_Maj"]) > 0
                else "unresolved"
            ),
            island_identifier=str(row["Isl_id"]),
            component_count=1,
            quality_flags=(
                ()
                if float(row["DC_Maj"]) > 0 and float(row["DC_Min"]) > 0
                else ("major-axis-only",)
                if float(row["DC_Maj"]) > 0
                else ("unresolved",)
            ),
        )
        for row in table
    )


def load_pybdsf_gaussian_catalogue(
    path: Path,
) -> tuple[CatalogueSource, ...]:
    """Read PyBDSF Gaussian components for compact-source comparisons."""
    table = cast(npt.NDArray[np.void], fits.getdata(path, ext=1))
    required = {
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
    }
    missing = required.difference(table.dtype.names or ())
    if missing:
        raise ValueError(
            "PyBDSF Gaussian catalogue misses columns: "
            + ", ".join(sorted(missing))
        )

    def optional_positive(row: np.void, name: str) -> float | None:
        value = float(row[name])
        return value if np.isfinite(value) and value > 0.0 else None

    def ellipse(row: np.void, prefix: str) -> CatalogueEllipse:
        return CatalogueEllipse(
            major_fwhm_degrees=float(row[f"{prefix}Maj"]),
            minor_fwhm_degrees=float(row[f"{prefix}Min"]),
            position_angle_degrees=float(row[f"{prefix}PA"]),
            major_fwhm_error_degrees=optional_positive(row, f"E_{prefix}Maj"),
            minor_fwhm_error_degrees=optional_positive(row, f"E_{prefix}Min"),
            position_angle_error_degrees=optional_positive(
                row, f"E_{prefix}PA"
            ),
        )

    group_fluxes: dict[tuple[int, int], float] = {}
    component_counts = Counter(
        (int(row["Isl_id"]), int(row["Source_id"])) for row in table
    )
    for row in table:
        key = (int(row["Isl_id"]), int(row["Source_id"]))
        group_fluxes[key] = group_fluxes.get(key, 0.0) + float(
            row["Total_flux"]
        )
    output: list[CatalogueSource] = []
    for row in sorted(
        table,
        key=lambda item: (
            int(item["Isl_id"]),
            int(item["Source_id"]),
            int(item["Wave_id"]),
            int(item["Gaus_id"]),
        ),
    ):
        island_id = int(row["Isl_id"])
        source_id = int(row["Source_id"])
        gaussian_id = int(row["Gaus_id"])
        wave_id = int(row["Wave_id"])
        deconvolved_major = float(row["DC_Maj"])
        deconvolved_minor = float(row["DC_Min"])
        resolved = deconvolved_major > 0.0 and deconvolved_minor > 0.0
        major_only = deconvolved_major > 0.0 and not resolved
        output.append(
            CatalogueSource(
                identifier=(
                    f"pybdsf-island-{island_id}-source-{source_id}-"
                    f"wave-{wave_id}-gaussian-{gaussian_id}"
                ),
                right_ascension_degrees=float(row["RA"]),
                declination_degrees=float(row["DEC"]),
                peak_flux_jy_per_beam=float(row["Peak_flux"]),
                integrated_flux_jy=float(row["Total_flux"]),
                association_integrated_flux_jy=group_fluxes[
                    (island_id, source_id)
                ],
                right_ascension_error_degrees=optional_positive(row, "E_RA"),
                declination_error_degrees=optional_positive(row, "E_DEC"),
                peak_flux_error_jy_per_beam=optional_positive(
                    row, "E_Peak_flux"
                ),
                integrated_flux_error_jy=optional_positive(
                    row, "E_Total_flux"
                ),
                fitted_shape=ellipse(row, ""),
                deconvolved_shape=ellipse(row, "DC_") if resolved else None,
                deconvolved_major_fwhm_degrees=(
                    deconvolved_major if major_only else None
                ),
                deconvolution_status=(
                    "resolved"
                    if resolved
                    else "major-axis-only"
                    if major_only
                    else "unresolved"
                ),
                island_identifier=str(island_id),
                component_count=component_counts[(island_id, source_id)],
                quality_flags=(
                    ()
                    if resolved
                    else ("major-axis-only",)
                    if major_only
                    else ("unresolved",)
                ),
            )
        )
    return tuple(output)


def _require_table_columns(
    table: npt.NDArray[np.void],
    required: set[str],
    *,
    product: str,
) -> None:
    """Fail clearly when a maintained external schema changes."""
    missing = required.difference(table.dtype.names or ())
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"Aegean {product} catalogue misses columns: {names}")


def _optional_positive_value(value: object) -> float | None:
    """Translate Aegean zero and NaN error sentinels to unavailable."""
    if np.ma.is_masked(value):
        return None
    numeric = float(value)  # type: ignore[arg-type]
    return numeric if np.isfinite(numeric) and numeric > 0.0 else None


def _load_aegean_islands(
    islands: npt.NDArray[np.void],
) -> dict[int, tuple[int, float]]:
    """Return validated component count and flux for every Aegean island."""
    island_rows: dict[int, tuple[int, float]] = {}
    for row in islands:
        island_number = int(row["island"])
        if island_number in island_rows:
            raise ValueError(f"duplicate Aegean island: {island_number}")
        component_count = int(row["components"])
        association_flux = float(row["int_flux"])
        if component_count <= 0:
            raise ValueError("Aegean island component count must be positive")
        if not np.isfinite(association_flux) or association_flux <= 0.0:
            raise ValueError("Aegean island flux must be finite and positive")
        island_rows[island_number] = (component_count, association_flux)
    return island_rows


def _validate_aegean_component_counts(
    components: npt.NDArray[np.void],
    island_rows: dict[int, tuple[int, float]],
) -> None:
    """Cross-check component identity and island membership."""
    component_keys = [
        (int(row["island"]), int(row["source"])) for row in components
    ]
    if len(component_keys) != len(set(component_keys)):
        raise ValueError("duplicate Aegean component identity")
    observed_counts = Counter(island for island, _ in component_keys)
    for island_number, observed in observed_counts.items():
        if island_number not in island_rows:
            raise ValueError(
                f"Aegean component references missing island: {island_number}"
            )
        declared = island_rows[island_number][0]
        if observed != declared:
            raise ValueError(
                "Aegean island component count differs from component "
                f"catalogue: island {island_number}"
            )
    if set(island_rows) != set(observed_counts):
        raise ValueError("Aegean island catalogue contains an empty island")


def _aegean_ellipse(row: np.void) -> CatalogueEllipse:
    """Convert one Aegean FWHM ellipse from arcseconds to degrees."""
    major_arcseconds = float(row["a"])
    minor_arcseconds = float(row["b"])
    major_error = _optional_positive_value(row["err_a"])
    minor_error = _optional_positive_value(row["err_b"])
    if minor_arcseconds > major_arcseconds:
        major_arcseconds, minor_arcseconds = (
            minor_arcseconds,
            major_arcseconds,
        )
        major_error, minor_error = minor_error, major_error
    return CatalogueEllipse(
        major_fwhm_degrees=major_arcseconds / _ARCSECONDS_PER_DEGREE,
        minor_fwhm_degrees=minor_arcseconds / _ARCSECONDS_PER_DEGREE,
        position_angle_degrees=float(row["pa"]),
        major_fwhm_error_degrees=(
            major_error / _ARCSECONDS_PER_DEGREE
            if major_error is not None
            else None
        ),
        minor_fwhm_error_degrees=(
            minor_error / _ARCSECONDS_PER_DEGREE
            if minor_error is not None
            else None
        ),
        position_angle_error_degrees=_optional_positive_value(row["err_pa"]),
    )


def _aegean_source(
    row: np.void,
    island_rows: dict[int, tuple[int, float]],
) -> CatalogueSource:
    """Convert one validated Aegean component to comparison units."""
    island_number = int(row["island"])
    source_number = int(row["source"])
    component_count, association_flux = island_rows[island_number]
    flags = int(row["flags"])
    return CatalogueSource(
        identifier=f"aegean-island-{island_number}-component-{source_number}",
        right_ascension_degrees=float(row["ra"]),
        declination_degrees=float(row["dec"]),
        peak_flux_jy_per_beam=float(row["peak_flux"]),
        integrated_flux_jy=float(row["int_flux"]),
        peak_flux_error_jy_per_beam=_optional_positive_value(
            row["err_peak_flux"]
        ),
        integrated_flux_error_jy=_optional_positive_value(row["err_int_flux"]),
        fitted_shape=_aegean_ellipse(row),
        deconvolution_status="unavailable",
        island_identifier=f"aegean-island-{island_number}",
        component_count=component_count,
        quality_flags=(() if flags == 0 else (f"aegean-flags-{flags}",)),
        association_integrated_flux_jy=association_flux,
    )


def load_aegean_catalogue(
    component_path: Path,
    island_path: Path,
    *,
    exclude_invalid_islands: bool = False,
) -> tuple[CatalogueSource, ...]:
    """Read maintained Aegean component and island FITS catalogues.

    Aegean component UUIDs are deliberately ignored. Stable comparison IDs
    come from the integer island and source columns, while association fluxes
    come from the companion island catalogue. Callers importing diagnostic
    observational catalogues may explicitly exclude islands whose integrated
    flux is non-finite or non-positive; strict validation remains the default.
    """
    components = cast(
        npt.NDArray[np.void], fits.getdata(component_path, ext=1)
    )
    islands = cast(npt.NDArray[np.void], fits.getdata(island_path, ext=1))
    _require_table_columns(
        components,
        _AEGEAN_COMPONENT_COLUMNS,
        product="component",
    )
    _require_table_columns(
        islands,
        _AEGEAN_ISLAND_COLUMNS,
        product="island",
    )

    island_identifiers = [int(row["island"]) for row in islands]
    if len(island_identifiers) != len(set(island_identifiers)):
        raise ValueError("duplicate Aegean island")
    if exclude_invalid_islands:
        invalid_islands = {
            int(row["island"])
            for row in islands
            if not np.isfinite(float(row["int_flux"]))
            or float(row["int_flux"]) <= 0.0
        }
        if invalid_islands:
            islands = islands[
                np.asarray(
                    [
                        int(row["island"]) not in invalid_islands
                        for row in islands
                    ],
                    dtype=np.bool_,
                )
            ]
            components = components[
                np.asarray(
                    [
                        int(row["island"]) not in invalid_islands
                        for row in components
                    ],
                    dtype=np.bool_,
                )
            ]

    island_rows = _load_aegean_islands(islands)
    _validate_aegean_component_counts(components, island_rows)
    ordered_rows = sorted(
        components,
        key=lambda item: (int(item["island"]), int(item["source"])),
    )
    return tuple(_aegean_source(row, island_rows) for row in ordered_rows)


def _pixel_covariance(
    source: CatalogueSource,
    pixel_to_tangent_degrees: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Transform one Aegean sky ellipse into local pixel covariance."""
    shape = source.fitted_shape
    if shape is None:
        raise ValueError("Aegean support proxy requires fitted ellipses")
    angle = np.deg2rad(shape.position_angle_degrees)
    rotation = np.asarray(
        (
            (np.sin(angle), np.cos(angle)),
            (np.cos(angle), -np.sin(angle)),
        ),
        dtype=np.float64,
    )
    sigma = np.asarray(
        (
            shape.major_fwhm_degrees * _FWHM_TO_SIGMA,
            shape.minor_fwhm_degrees * _FWHM_TO_SIGMA,
        ),
        dtype=np.float64,
    )
    sky_covariance = rotation @ np.diag(sigma**2) @ rotation.T
    tangent_to_pixel = np.linalg.inv(pixel_to_tangent_degrees)
    return tangent_to_pixel @ sky_covariance @ tangent_to_pixel.T


def aegean_support_label_plane(
    sources: tuple[CatalogueSource, ...],
    header: fits.Header,
    *,
    shape_yx: tuple[int, int],
) -> tuple[npt.NDArray[np.int32], dict[str, int]]:
    """Rasterize deterministic island-grouped three-sigma fit proxies.

    This plane supports truth association only. It is not an Aegean
    segmentation product and must not be reported as one.
    """
    if len(shape_yx) != _PLANE_DIMENSIONS or any(
        size <= 0 for size in shape_yx
    ):
        raise ValueError("Aegean support shape must contain two positive axes")
    if any(source.island_identifier is None for source in sources):
        raise ValueError("Aegean support proxy requires island identifiers")
    island_identifiers = sorted(
        {cast(str, source.island_identifier) for source in sources}
    )
    labels_by_island = {
        identifier: index + 1
        for index, identifier in enumerate(island_identifiers)
    }
    labels = np.zeros(shape_yx, dtype=np.int32)
    best_distance = np.full(shape_yx, np.inf, dtype=np.float64)
    celestial_wcs = WCS(header, relax=True).celestial
    pixel_matrix = np.asarray(
        celestial_wcs.pixel_scale_matrix,
        dtype=np.float64,
    )
    if pixel_matrix.shape != (_PLANE_DIMENSIONS, _PLANE_DIMENSIONS):
        raise ValueError("Aegean support WCS must have two celestial axes")

    ordered_sources = sorted(
        sources,
        key=lambda source: (
            cast(str, source.island_identifier),
            source.identifier,
        ),
    )
    for source in ordered_sources:
        island_identifier = cast(str, source.island_identifier)
        centre = np.asarray(
            celestial_wcs.all_world2pix(
                [
                    [
                        source.right_ascension_degrees,
                        source.declination_degrees,
                    ]
                ],
                0,
            )[0],
            dtype=np.float64,
        )
        if not np.all(np.isfinite(centre)):
            raise ValueError("Aegean source does not map to a finite pixel")
        pixel_to_tangent = pixel_matrix.copy()
        pixel_to_tangent[0] *= np.cos(np.deg2rad(source.declination_degrees))
        covariance = _pixel_covariance(source, pixel_to_tangent)
        eigenvalues = np.linalg.eigvalsh(covariance)
        if not np.all(np.isfinite(eigenvalues)) or np.any(eigenvalues <= 0.0):
            raise ValueError("Aegean ellipse has invalid pixel covariance")
        radius = _AEGEAN_SUPPORT_SIGMAS * np.sqrt(float(eigenvalues[-1]))
        x_min = max(0, int(np.floor(centre[0] - radius)))
        x_max = min(shape_yx[1], int(np.ceil(centre[0] + radius)) + 1)
        y_min = max(0, int(np.floor(centre[1] - radius)))
        y_max = min(shape_yx[0], int(np.ceil(centre[1] + radius)) + 1)
        if x_min >= x_max or y_min >= y_max:
            continue
        yy, xx = np.mgrid[y_min:y_max, x_min:x_max]
        offsets = np.stack((xx - centre[0], yy - centre[1]), axis=-1)
        inverse_covariance = np.linalg.inv(covariance)
        squared_distance = np.einsum(
            "...i,ij,...j->...",
            offsets,
            inverse_covariance,
            offsets,
        )
        within = squared_distance <= _AEGEAN_SUPPORT_SIGMAS**2
        current = best_distance[y_min:y_max, x_min:x_max]
        update = within & (squared_distance < current)
        current[update] = squared_distance[update]
        labels[y_min:y_max, x_min:x_max][update] = labels_by_island[
            island_identifier
        ]
    return labels, labels_by_island


def write_comparison_catalogue(
    path: Path,
    sources: tuple[CatalogueSource, ...],
) -> None:
    """Write validation catalogue records as canonical JSON."""
    if len({source.identifier for source in sources}) != len(sources):
        raise ValueError("comparison catalogue identifiers must be unique")
    document = json.dumps(
        [
            asdict(source)
            for source in sorted(sources, key=lambda item: item.identifier)
        ],
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    path.write_text(f"{document}\n", encoding="utf-8")


def load_comparison_catalogue(path: Path) -> tuple[CatalogueSource, ...]:
    """Load a canonical validation catalogue and verify its encoding."""
    payload = path.read_text(encoding="utf-8")
    rows = json.loads(payload)
    if not isinstance(rows, list):
        raise ValueError("comparison catalogue must contain a JSON array")
    sources: list[CatalogueSource] = []
    for value in rows:
        if not isinstance(value, dict):
            raise ValueError("comparison catalogue rows must be objects")
        row = dict(value)
        for name in ("fitted_shape", "deconvolved_shape"):
            shape = row.get(name)
            if shape is not None:
                if not isinstance(shape, dict):
                    raise ValueError(
                        "comparison catalogue shape must be an object"
                    )
                row[name] = CatalogueEllipse(**shape)
        flags = row.get("quality_flags")
        if isinstance(flags, list):
            row["quality_flags"] = tuple(flags)
        sources.append(CatalogueSource(**row))  # type: ignore[arg-type]
    result = tuple(sorted(sources, key=lambda item: item.identifier))
    expected = json.dumps(
        [asdict(source) for source in result],
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    if payload != f"{expected}\n":
        raise ValueError("comparison catalogue is not canonical JSON")
    return result


def _validated_hebog_segment_planes(
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    component_labels: npt.ArrayLike,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.int64],
]:
    """Return aligned residual, validity, and exact segment labels."""
    image = np.asarray(image_jy_per_beam, dtype=np.float64)
    background = np.asarray(background_jy_per_beam, dtype=np.float64)
    valid = np.asarray(valid_pixels, dtype=np.bool_)
    label_values = np.asarray(component_labels)
    if label_values.ndim != _PLANE_DIMENSIONS or not np.issubdtype(
        label_values.dtype,
        np.integer,
    ):
        raise ValueError(
            "component labels must be a two-dimensional integer array"
        )
    if np.any(label_values < 0):
        raise ValueError("component labels must be non-negative")
    if image.shape != background.shape or image.shape != valid.shape:
        raise ValueError("Hebog segment planes must share one shape")
    if label_values.shape != image.shape:
        raise ValueError("Hebog segment labels must match the image")
    return (
        np.where(valid, image - background, np.nan),
        valid,
        np.asarray(label_values, dtype=np.int64),
    )


def _validated_position_signal(
    position_signal_jy_per_beam: npt.ArrayLike | None,
    *,
    shape: tuple[int, ...],
    valid_pixels: npt.NDArray[np.bool_],
) -> npt.NDArray[np.float64] | None:
    """Return one optional aligned real denoised measurement plane."""
    if position_signal_jy_per_beam is None:
        return None
    position_values = np.asarray(position_signal_jy_per_beam)
    if (
        position_values.ndim != _PLANE_DIMENSIONS
        or position_values.shape != shape
        or not np.issubdtype(position_values.dtype, np.number)
        or np.issubdtype(position_values.dtype, np.complexfloating)
    ):
        raise ValueError(
            "Hebog segment position signal must be an aligned real "
            "two-dimensional plane"
        )
    return np.where(
        valid_pixels,
        np.asarray(position_values, dtype=np.float64),
        np.nan,
    )


def _segment_position(
    residual: npt.NDArray[np.float64],
    denoised_position_signal: npt.NDArray[np.float64] | None,
    support: npt.NDArray[np.bool_],
    *,
    maximum_peak_to_mean_ratio: float,
) -> DetectedSegmentPosition:
    """Select original or denoised weights from measured concentration."""
    selected = residual
    if denoised_position_signal is not None:
        direct_weights = residual[support]
        if direct_weights.size:
            direct_mean = float(np.mean(direct_weights, dtype=np.float64))
            peak_to_mean = (
                float(np.max(direct_weights)) / direct_mean
                if np.isfinite(direct_mean) and direct_mean > 0.0
                else np.inf
            )
            if peak_to_mean <= maximum_peak_to_mean_ratio:
                selected = denoised_position_signal
    estimate = measure_detected_segment_position(selected, support)
    if not estimate.available and denoised_position_signal is not None:
        return measure_detected_segment_position(residual, support)
    return estimate


def build_hebog_segment_catalogue(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    component_labels: npt.ArrayLike,
    header: fits.Header,
    *,
    beam_major_fwhm_pixels: float,
    beam_minor_fwhm_pixels: float,
    measurement_aperture_radius_beams: float = 4.0,
    position_signal_jy_per_beam: npt.ArrayLike | None = None,
    denoised_position_maximum_peak_to_mean_ratio: float = 3.0,
) -> tuple[CatalogueSource, ...]:
    """Measure catalogue rows for physically measurable blind segments.

    Labels remain the authoritative record of every accepted detection.
    Expanded-aperture photometry is preferred. When surrounding negative
    residuals make that aperture non-positive, the accepted owner's positive
    exact support provides an explicitly flagged conservative fallback.
    """
    residual, valid, labels = _validated_hebog_segment_planes(
        image_jy_per_beam,
        background_jy_per_beam,
        valid_pixels,
        component_labels,
    )
    if (
        not np.isfinite(beam_major_fwhm_pixels)
        or not np.isfinite(beam_minor_fwhm_pixels)
        or beam_major_fwhm_pixels <= 0.0
        or beam_minor_fwhm_pixels <= 0.0
    ):
        raise ValueError("Hebog segment beam axes must be positive")
    if (
        not np.isfinite(measurement_aperture_radius_beams)
        or measurement_aperture_radius_beams <= 0.0
    ):
        raise ValueError(
            "Hebog segment measurement aperture radius must be positive"
        )
    if (
        not np.isfinite(denoised_position_maximum_peak_to_mean_ratio)
        or denoised_position_maximum_peak_to_mean_ratio <= 1.0
    ):
        raise ValueError(
            "Hebog segment denoised-position peak-to-mean ratio must exceed 1"
        )
    position_signal = _validated_position_signal(
        position_signal_jy_per_beam,
        shape=residual.shape,
        valid_pixels=valid,
    )
    measurement_labels = expand_detected_segment_labels(
        labels,
        valid & np.isfinite(residual),
        radius_pixels=ceil(
            measurement_aperture_radius_beams * beam_major_fwhm_pixels
        ),
    )
    beam_area_pixels = (
        2.0
        * np.pi
        / (8.0 * np.log(2.0))
        * beam_major_fwhm_pixels
        * beam_minor_fwhm_pixels
    )
    celestial_wcs = WCS(header, relax=True).celestial
    output: list[CatalogueSource] = []
    for label_value in sorted(
        int(item) for item in np.unique(labels) if item > 0
    ):
        support = (labels == label_value) & valid & np.isfinite(residual)
        estimate = _segment_position(
            residual,
            position_signal,
            support,
            maximum_peak_to_mean_ratio=(
                denoised_position_maximum_peak_to_mean_ratio
            ),
        )
        if not estimate.available or estimate.centroid_xy is None:
            continue
        measurement_support = measurement_labels == label_value
        integrated_weight = float(
            np.sum(residual[measurement_support], dtype=np.float64)
        )
        quality_flags: tuple[str, ...] = ()
        if not np.isfinite(integrated_weight) or integrated_weight <= 0.0:
            exact_positive_support = support & (residual > 0.0)
            integrated_weight = float(
                np.sum(
                    residual[exact_positive_support],
                    dtype=np.float64,
                )
            )
            quality_flags = (
                "association-aperture-nonpositive",
                "exact-owner-positive-residual-flux",
            )
        if not np.isfinite(integrated_weight) or integrated_weight <= 0.0:
            continue
        integrated_flux = integrated_weight / beam_area_pixels
        peak_flux = float(np.max(residual[support]))
        right_ascension, declination = celestial_wcs.all_pix2world(
            [estimate.centroid_xy],
            0,
        )[0]
        identifier = f"hebog-segment-{label_value}"
        output.append(
            CatalogueSource(
                identifier=identifier,
                right_ascension_degrees=float(right_ascension),
                declination_degrees=float(declination),
                peak_flux_jy_per_beam=peak_flux,
                integrated_flux_jy=integrated_flux,
                association_integrated_flux_jy=integrated_flux,
                deconvolution_status="unavailable",
                island_identifier=identifier,
                component_count=1,
                quality_flags=quality_flags,
            )
        )
    return tuple(output)


def _catalogue_ellipse(shape: GaussianShape) -> CatalogueEllipse:
    """Translate one validated Gaussian-like shape into comparison units."""
    return CatalogueEllipse(
        major_fwhm_degrees=shape.major_fwhm_degrees,
        minor_fwhm_degrees=shape.minor_fwhm_degrees,
        position_angle_degrees=shape.position_angle_degrees,
    )


def _segment_pixel_moment_covariance(
    residual_jy_per_beam: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
) -> tuple[tuple[float, float], npt.NDArray[np.float64]] | None:
    """Return a positive centroid and exact-support covariance."""
    positive = (
        support
        & np.isfinite(residual_jy_per_beam)
        & (residual_jy_per_beam > 0.0)
    )
    if int(np.count_nonzero(positive)) < _MINIMUM_MOMENT_PIXELS:
        return None
    weights = residual_jy_per_beam[positive]
    weight = float(np.sum(weights, dtype=np.float64))
    if not np.isfinite(weight) or weight <= 0.0:
        return None
    y_pixels, x_pixels = np.nonzero(positive)
    centroid_x = float(np.sum(x_pixels * weights, dtype=np.float64) / weight)
    centroid_y = float(np.sum(y_pixels * weights, dtype=np.float64) / weight)
    delta_x = x_pixels - centroid_x
    delta_y = y_pixels - centroid_y
    covariance = np.asarray(
        (
            (
                np.sum(weights * delta_x * delta_x, dtype=np.float64) / weight,
                np.sum(weights * delta_x * delta_y, dtype=np.float64) / weight,
            ),
            (
                np.sum(weights * delta_x * delta_y, dtype=np.float64) / weight,
                np.sum(weights * delta_y * delta_y, dtype=np.float64) / weight,
            ),
        ),
        dtype=np.float64,
    )
    if (
        not np.all(np.isfinite(covariance))
        or float(np.linalg.det(covariance)) <= 0.0
    ):
        return None
    return (centroid_x, centroid_y), covariance


def _moment_shape_fields(
    residual_jy_per_beam: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
    celestial_wcs: WCS,
    beam: RestoringBeam,
) -> dict[str, object]:
    """Return comparison fields for one moment-equivalent owner shape."""
    moment = _segment_pixel_moment_covariance(
        residual_jy_per_beam,
        support,
    )
    provenance = "segment-moment-equivalent-shape"
    if moment is None:
        return {
            "fitted_shape": None,
            "deconvolved_shape": None,
            "deconvolved_major_fwhm_degrees": None,
            "deconvolution_status": "unavailable",
            "quality_flags": (provenance, "shape-unavailable"),
        }
    centroid_xy, covariance = moment
    try:
        transform = local_tangent_plane_transform_from_wcs(
            celestial_wcs,
            centroid_xy,
        )
        fitted = moment_equivalent_gaussian_shape(covariance, transform)
        deconvolution = deconvolve_gaussian_shapes(
            fitted,
            beam,
            relative_tolerance=1e-10,
        )
    except (TypeError, ValueError, np.linalg.LinAlgError):
        return {
            "fitted_shape": None,
            "deconvolved_shape": None,
            "deconvolved_major_fwhm_degrees": None,
            "deconvolution_status": "unavailable",
            "quality_flags": (provenance, "shape-unavailable"),
        }
    flags = {provenance}
    if deconvolution.status in {"major-axis-only", "unresolved"}:
        flags.update(deconvolution.quality_flags)
    return {
        "fitted_shape": _catalogue_ellipse(fitted),
        "deconvolved_shape": (
            _catalogue_ellipse(deconvolution.shape)
            if deconvolution.shape is not None
            else None
        ),
        "deconvolved_major_fwhm_degrees": (
            deconvolution.major_axis_fwhm_degrees
        ),
        "deconvolution_status": deconvolution.status,
        "quality_flags": tuple(sorted(flags)),
    }


def build_hebog_segment_moment_catalogue(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    component_labels: npt.ArrayLike,
    header: fits.Header,
    *,
    beam_major_fwhm_pixels: float,
    beam_minor_fwhm_pixels: float,
    measurement_aperture_radius_beams: float = 4.0,
    position_signal_jy_per_beam: npt.ArrayLike | None = None,
    denoised_position_maximum_peak_to_mean_ratio: float = 3.0,
) -> tuple[CatalogueSource, ...]:
    """Publish exact-support moment shapes without changing photometry."""
    sources = build_hebog_segment_catalogue(
        image_jy_per_beam,
        background_jy_per_beam,
        valid_pixels,
        component_labels,
        header,
        beam_major_fwhm_pixels=beam_major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam_minor_fwhm_pixels,
        measurement_aperture_radius_beams=measurement_aperture_radius_beams,
        position_signal_jy_per_beam=position_signal_jy_per_beam,
        denoised_position_maximum_peak_to_mean_ratio=(
            denoised_position_maximum_peak_to_mean_ratio
        ),
    )
    residual, valid, labels = _validated_hebog_segment_planes(
        image_jy_per_beam,
        background_jy_per_beam,
        valid_pixels,
        component_labels,
    )
    celestial_wcs = WCS(header, relax=True).celestial
    try:
        beam = RestoringBeam(
            major_fwhm_degrees=cast(float, header["BMAJ"]),
            minor_fwhm_degrees=cast(float, header["BMIN"]),
            position_angle_degrees=cast(float, header["BPA"]),
        )
    except (KeyError, TypeError, ValueError):
        return tuple(
            replace(
                source,
                quality_flags=(
                    "segment-moment-equivalent-shape",
                    "shape-unavailable",
                ),
            )
            for source in sources
        )
    by_identifier = {source.identifier: source for source in sources}
    output: list[CatalogueSource] = []
    for label_value in sorted(
        int(item) for item in np.unique(labels) if item > 0
    ):
        identifier = f"hebog-segment-{label_value}"
        source = by_identifier.get(identifier)
        if source is None:
            continue
        support = (labels == label_value) & valid
        shape_fields = _moment_shape_fields(
            residual,
            support,
            celestial_wcs,
            beam,
        )
        shape_fields["quality_flags"] = tuple(
            sorted(
                {
                    *source.quality_flags,
                    *cast(tuple[str, ...], shape_fields["quality_flags"]),
                }
            )
        )
        output.append(
            replace(
                source,
                **shape_fields,  # type: ignore[arg-type]
            )
        )
    return tuple(output)


@dataclass(frozen=True, slots=True)
class AssociatedMomentCatalogues:
    """Binding source rows plus retained immutable component diagnostics."""

    component_catalogue: tuple[CatalogueSource, ...]
    source_catalogue: tuple[CatalogueSource, ...]
    association: SourceAssociationResult


def _source_label_plane(
    labels: npt.NDArray[np.int64],
    association: SourceAssociationResult,
) -> tuple[
    npt.NDArray[np.int32],
    dict[int, CatalogueSourceMembership],
]:
    """Map immutable component owners to canonical source-local labels."""
    records_by_id = {
        item.component_id: item for item in association.components
    }
    output = np.zeros(labels.shape, dtype=np.int32)
    memberships_by_label: dict[int, CatalogueSourceMembership] = {}
    for source_label, membership in enumerate(
        association.memberships,
        start=1,
    ):
        component_labels = tuple(
            records_by_id[component_id].label_value
            for component_id in membership.component_ids
        )
        output[np.isin(labels, component_labels)] = source_label
        memberships_by_label[source_label] = membership
    if np.any((labels > 0) & (output == 0)):
        raise ValueError("source memberships must own every component pixel")
    return output, memberships_by_label


def build_hebog_reconstructed_source_catalogues(  # noqa: PLR0913, PLR0917
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    component_labels: npt.ArrayLike,
    scale_detection_planes: tuple[ScaleDetectionPlane, ...],
    header: fits.Header,
    *,
    beam_major_fwhm_pixels: float,
    beam_minor_fwhm_pixels: float,
    measurement_aperture_radius_beams: float = 4.0,
    position_signal_jy_per_beam: npt.ArrayLike | None = None,
    denoised_position_maximum_peak_to_mean_ratio: float = 3.0,
) -> AssociatedMomentCatalogues:
    """Measure each common-parent catalogue source exactly once.

    Immutable component measurements remain diagnostic. Binding source rows
    are measured from a source-label plane before aperture expansion, so every
    observable pixel belongs to at most one source aperture.
    """
    residual, valid, labels = _validated_hebog_segment_planes(
        image_jy_per_beam,
        background_jy_per_beam,
        valid_pixels,
        component_labels,
    )
    component_sources = build_hebog_segment_moment_catalogue(
        image_jy_per_beam,
        background_jy_per_beam,
        valid,
        labels,
        header,
        beam_major_fwhm_pixels=beam_major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam_minor_fwhm_pixels,
        measurement_aperture_radius_beams=measurement_aperture_radius_beams,
        position_signal_jy_per_beam=position_signal_jy_per_beam,
        denoised_position_maximum_peak_to_mean_ratio=(
            denoised_position_maximum_peak_to_mean_ratio
        ),
    )
    records = build_detection_component_records(labels, residual, valid)
    association = associate_components_by_multiscale_hierarchy(
        records,
        labels,
        scale_detection_planes,
        valid,
    )
    stable_components = _stable_component_catalogue(
        component_sources,
        association,
    )
    source_labels, membership_by_label = _source_label_plane(
        labels,
        association,
    )
    measured_sources = build_hebog_segment_moment_catalogue(
        image_jy_per_beam,
        background_jy_per_beam,
        valid,
        source_labels,
        header,
        beam_major_fwhm_pixels=beam_major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam_minor_fwhm_pixels,
        measurement_aperture_radius_beams=measurement_aperture_radius_beams,
        position_signal_jy_per_beam=position_signal_jy_per_beam,
        denoised_position_maximum_peak_to_mean_ratio=(
            denoised_position_maximum_peak_to_mean_ratio
        ),
    )
    components_by_id = {item.identifier: item for item in stable_components}
    output: list[CatalogueSource] = []
    for source in measured_sources:
        prefix = "hebog-segment-"
        if not source.identifier.startswith(prefix):
            raise ValueError("measured source identity is malformed")
        source_label = int(source.identifier[len(prefix) :])
        membership = membership_by_label[source_label]
        member_flags = {
            flag
            for component_id in membership.component_ids
            for component in (components_by_id.get(component_id),)
            if component is not None
            for flag in component.quality_flags
        }
        flags = {
            *source.quality_flags,
            *member_flags,
            "reconstructed-catalogue-source",
        }
        if any(
            component_id in association.ambiguous_component_ids
            for component_id in membership.component_ids
        ):
            flags.add("ambiguous-multiscale-parent")
        output.append(
            replace(
                source,
                identifier=membership.source_id,
                island_identifier=membership.source_id,
                component_count=len(membership.component_ids),
                quality_flags=tuple(sorted(flags)),
            )
        )
    if len(output) != len(association.memberships):
        raise ValueError(
            "reconstructed source has no measurable catalogue row"
        )
    return AssociatedMomentCatalogues(
        component_catalogue=stable_components,
        source_catalogue=tuple(
            sorted(output, key=lambda item: item.identifier)
        ),
        association=association,
    )


def _stable_component_catalogue(
    sources: tuple[CatalogueSource, ...],
    association: SourceAssociationResult,
) -> tuple[CatalogueSource, ...]:
    """Replace task-local label identities with stable component identities."""
    by_label_identifier = {
        f"hebog-segment-{record.label_value}": record.component_id
        for record in association.components
    }
    output = tuple(
        replace(
            source,
            identifier=by_label_identifier[source.identifier],
            island_identifier=by_label_identifier[source.identifier],
            quality_flags=tuple(
                sorted({*source.quality_flags, "detection-component"})
            ),
        )
        for source in sources
    )
    return tuple(sorted(output, key=lambda item: item.identifier))


def _flux_weighted_tangent_position(
    components: tuple[CatalogueSource, ...],
) -> tuple[float, float]:
    """Combine component centroids in one local tangent plane."""
    origin_source = components[0]
    origin = SkyCoord(
        ra=origin_source.right_ascension_degrees * u.deg,
        dec=origin_source.declination_degrees * u.deg,
        frame="icrs",
    )
    coordinates = SkyCoord(
        ra=[item.right_ascension_degrees for item in components] * u.deg,
        dec=[item.declination_degrees for item in components] * u.deg,
        frame="icrs",
    )
    east, north = origin.spherical_offsets_to(coordinates)
    weights = np.asarray(
        [item.integrated_flux_jy for item in components],
        dtype=np.float64,
    )
    combined = origin.spherical_offsets_by(
        float(np.average(east.to_value(u.deg), weights=weights)) * u.deg,
        float(np.average(north.to_value(u.deg), weights=weights)) * u.deg,
    )
    combined_coordinates = cast(Any, combined)
    right_ascension = float(combined_coordinates.ra.deg)
    declination = float(combined_coordinates.dec.deg)
    return right_ascension, declination


def _associated_source_catalogue(  # noqa: PLR0913
    components: tuple[CatalogueSource, ...],
    association: SourceAssociationResult,
    *,
    residual: npt.NDArray[np.float64],
    valid: npt.NDArray[np.bool_],
    labels: npt.NDArray[np.int64],
    celestial_wcs: WCS,
    beam: RestoringBeam | None,
) -> tuple[CatalogueSource, ...]:
    """Aggregate existing component measurements without remeasurement."""
    components_by_id = {item.identifier: item for item in components}
    records_by_id = {
        item.component_id: item for item in association.components
    }
    output: list[CatalogueSource] = []
    for membership in association.memberships:
        members = tuple(
            components_by_id[component_id]
            for component_id in membership.component_ids
            if component_id in components_by_id
        )
        if not members:
            raise ValueError(
                "associated source has no measurable detection component"
            )
        if len(members) != len(membership.component_ids):
            raise ValueError(
                "associated source cannot mix measurable and unavailable "
                "components"
            )
        member_labels = tuple(
            records_by_id[item.identifier].label_value for item in members
        )
        support = np.isin(labels, member_labels) & valid
        if beam is None:
            shape_fields: dict[str, object] = {
                "fitted_shape": None,
                "deconvolved_shape": None,
                "deconvolved_major_fwhm_degrees": None,
                "deconvolution_status": "unavailable",
                "quality_flags": (
                    "segment-moment-equivalent-shape",
                    "shape-unavailable",
                ),
            }
        else:
            shape_fields = _moment_shape_fields(
                residual,
                support,
                celestial_wcs,
                beam,
            )
        right_ascension, declination = _flux_weighted_tangent_position(members)
        association_fluxes = tuple(
            item.association_integrated_flux_jy
            if item.association_integrated_flux_jy is not None
            else item.integrated_flux_jy
            for item in members
        )
        flags = cast(tuple[str, ...], shape_fields["quality_flags"])
        member_flags = {
            flag for item in members for flag in item.quality_flags
        }
        shape_fields["quality_flags"] = tuple(
            sorted(
                {
                    *flags,
                    *member_flags,
                    "associated-component-source",
                }
            )
        )
        output.append(
            CatalogueSource(
                identifier=membership.source_id,
                right_ascension_degrees=right_ascension,
                declination_degrees=declination,
                peak_flux_jy_per_beam=max(
                    item.peak_flux_jy_per_beam for item in members
                ),
                integrated_flux_jy=sum(
                    item.integrated_flux_jy for item in members
                ),
                association_integrated_flux_jy=sum(association_fluxes),
                island_identifier=membership.source_id,
                component_count=len(members),
                **shape_fields,  # type: ignore[arg-type]
            )
        )
    return tuple(sorted(output, key=lambda item: item.identifier))


def build_hebog_associated_moment_catalogues(  # noqa: PLR0913, PLR0917
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    component_labels: npt.ArrayLike,
    significant_multiscale_support: npt.ArrayLike,
    combined_snr: npt.ArrayLike,
    header: fits.Header,
    *,
    beam_major_fwhm_pixels: float,
    beam_minor_fwhm_pixels: float,
    island_threshold_sigma: float,
    measurement_aperture_radius_beams: float = 4.0,
    position_signal_jy_per_beam: npt.ArrayLike | None = None,
    denoised_position_maximum_peak_to_mean_ratio: float = 3.0,
) -> AssociatedMomentCatalogues:
    """Build component diagnostics and binding associated source rows."""
    components = build_hebog_segment_moment_catalogue(
        image_jy_per_beam,
        background_jy_per_beam,
        valid_pixels,
        component_labels,
        header,
        beam_major_fwhm_pixels=beam_major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam_minor_fwhm_pixels,
        measurement_aperture_radius_beams=measurement_aperture_radius_beams,
        position_signal_jy_per_beam=position_signal_jy_per_beam,
        denoised_position_maximum_peak_to_mean_ratio=(
            denoised_position_maximum_peak_to_mean_ratio
        ),
    )
    residual, valid, labels = _validated_hebog_segment_planes(
        image_jy_per_beam,
        background_jy_per_beam,
        valid_pixels,
        component_labels,
    )
    records = build_detection_component_records(
        labels,
        residual,
        valid,
    )
    association = associate_detection_components(
        records,
        labels,
        significant_multiscale_support,
        combined_snr,
        valid,
        island_threshold_sigma=island_threshold_sigma,
    )
    stable_components = _stable_component_catalogue(components, association)
    celestial_wcs = WCS(header, relax=True).celestial
    try:
        beam: RestoringBeam | None = RestoringBeam(
            major_fwhm_degrees=cast(float, header["BMAJ"]),
            minor_fwhm_degrees=cast(float, header["BMIN"]),
            position_angle_degrees=cast(float, header["BPA"]),
        )
    except (KeyError, TypeError, ValueError):
        beam = None
    sources = _associated_source_catalogue(
        stable_components,
        association,
        residual=residual,
        valid=valid,
        labels=labels,
        celestial_wcs=celestial_wcs,
        beam=beam,
    )
    return AssociatedMomentCatalogues(
        component_catalogue=stable_components,
        source_catalogue=sources,
        association=association,
    )


def load_fits_plane(path: Path) -> npt.NDArray[np.float64]:
    """Read one logical FITS image plane as a two-dimensional float array."""
    plane = np.asarray(fits.getdata(path), dtype=np.float64).squeeze()
    if plane.ndim != _PLANE_DIMENSIONS:
        raise ValueError(f"expected one two-dimensional FITS plane: {path}")
    return plane


def load_mask_plane(path: Path) -> npt.NDArray[np.bool_]:
    """Read a binary PyBDSF island-mask plane."""
    plane = load_fits_plane(path)
    if not np.all(np.isin(plane, (0.0, 1.0))):
        raise ValueError(
            f"mask contains values other than zero and one: {path}"
        )
    return np.asarray(plane, dtype=np.bool_)
