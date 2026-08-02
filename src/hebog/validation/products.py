# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Immutable PyBDSF reference-product manifests and typed readers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Self, TypeAlias, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.comparison import CatalogueEllipse, CatalogueSource
from hebog.validation.evidence import DatasetIdentity, SoftwareIdentity

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_REFERENCE_COUNT = 2
_PLANE_DIMENSIONS = 2

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

    def ellipse(row: np.void, prefix: str) -> CatalogueEllipse:
        return CatalogueEllipse(
            major_fwhm_degrees=float(row[f"{prefix}Maj"]),
            minor_fwhm_degrees=float(row[f"{prefix}Min"]),
            position_angle_degrees=float(row[f"{prefix}PA"]),
            major_fwhm_error_degrees=float(row[f"E_{prefix}Maj"]),
            minor_fwhm_error_degrees=float(row[f"E_{prefix}Min"]),
            position_angle_error_degrees=float(row[f"E_{prefix}PA"]),
        )

    return tuple(
        CatalogueSource(
            identifier=str(row["Source_id"]),
            right_ascension_degrees=float(row["RA"]),
            declination_degrees=float(row["DEC"]),
            peak_flux_jy_per_beam=float(row["Peak_flux"]),
            integrated_flux_jy=float(row["Total_flux"]),
            right_ascension_error_degrees=float(row["E_RA"]),
            declination_error_degrees=float(row["E_DEC"]),
            peak_flux_error_jy_per_beam=float(row["E_Peak_flux"]),
            integrated_flux_error_jy=float(row["E_Total_flux"]),
            fitted_shape=ellipse(row, ""),
            deconvolved_shape=(
                ellipse(row, "DC_") if float(row["DC_Maj"]) > 0 else None
            ),
            deconvolution_status=(
                "resolved" if float(row["DC_Maj"]) > 0 else "unresolved"
            ),
            island_identifier=str(row["Isl_id"]),
            component_count=1,
            quality_flags=(
                () if float(row["DC_Maj"]) > 0 else ("unresolved",)
            ),
        )
        for row in table
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
