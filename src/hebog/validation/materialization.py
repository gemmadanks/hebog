# pyright: reportMissingTypeStubs=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Materialize governed synthetic datasets as radio-image FITS files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal, Self, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.data_models.images import CelestialWcs, ImageMetadata, RestoringBeam
from hebog.validation.contracts import (
    load_phase_five_external_comparison_protocol,
)
from hebog.validation.datasets import (
    DatasetRecord,
    SyntheticRecipe,
    generate_synthetic_image,
    iter_dataset_recipes,
    load_dataset_manifest,
    recipe_sha256,
)

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_EXTERNAL_ARTIFACT_NAMES = {
    "image": "image.fits",
    "mean": "mean.fits",
    "rms": "rms.fits",
}
_IMAGE_DIMENSIONS = 2


class _ExternalInputModel(BaseModel):
    """Strict immutable base for one shared external-comparison input."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ExternalInputArtifact(_ExternalInputModel):
    """One relative FITS artifact consumed identically by every finder."""

    role: Literal["image", "mean", "rms"]
    relative_path: str = Field(min_length=1)
    byte_count: int = Field(gt=0)
    sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        """Keep artifact names exact and inside the realization directory."""
        path = PurePosixPath(self.relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("external input artifact path must stay relative")
        if self.relative_path != _EXTERNAL_ARTIFACT_NAMES[self.role]:
            raise ValueError(
                "external input artifact name does not match role"
            )
        return self


class ExternalInputBundle(_ExternalInputModel):
    """Byte identities for one common image/background/RMS realization."""

    schema_version: Literal[1]
    protocol_sha256: str = Field(pattern=_SHA256_PATTERN)
    manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    dataset_identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    seed: int = Field(ge=0)
    recipe_sha256: str = Field(pattern=_SHA256_PATTERN)
    dtype: Literal["float64"]
    shape_yx: tuple[int, int]
    artifacts: tuple[
        ExternalInputArtifact,
        ExternalInputArtifact,
        ExternalInputArtifact,
    ]

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        """Require canonical roles and a positive two-dimensional shape."""
        if tuple(item.role for item in self.artifacts) != (
            "image",
            "mean",
            "rms",
        ):
            raise ValueError("external input artifacts must be canonical")
        if len(self.shape_yx) != _IMAGE_DIMENSIONS or any(
            size <= 0 for size in self.shape_yx
        ):
            raise ValueError("external input shape must be positive")
        return self

    def canonical_json_bytes(self) -> bytes:
        """Serialize one path-independent realization identity."""
        document = json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        return f"{document}\n".encode()


def _celestial_linear_transform(
    dataset: DatasetRecord,
) -> np.ndarray[tuple[int, int], np.dtype[np.float64]]:
    """Map pixel offsets to the synthetic celestial intermediate plane."""
    scale_x, scale_y = dataset.wcs.pixel_scale_degrees_xy
    rotation_radians = np.deg2rad(
        dataset.wcs.rotation_degrees_counterclockwise
    )
    cosine = float(np.cos(rotation_radians))
    sine = float(np.sin(rotation_radians))
    return np.asarray(
        [
            [scale_x * cosine, -scale_y * sine],
            [scale_x * sine, scale_y * cosine],
        ],
        dtype=np.float64,
    )


def _beam_header_values(dataset: DatasetRecord) -> tuple[float, float, float]:
    """Transform generator-v2 pixel-plane beam truth to celestial values."""
    scale_x, scale_y = dataset.wcs.pixel_scale_degrees_xy
    if dataset.recipe.generator_version == 1:
        return (
            dataset.beam.major_fwhm_pixels * abs(scale_x),
            dataset.beam.minor_fwhm_pixels * abs(scale_y),
            dataset.beam.position_angle_degrees,
        )

    beam_angle = np.deg2rad(dataset.beam.position_angle_degrees)
    beam_rotation = np.asarray(
        [
            [np.cos(beam_angle), -np.sin(beam_angle)],
            [np.sin(beam_angle), np.cos(beam_angle)],
        ],
        dtype=np.float64,
    )
    pixel_covariance = (
        beam_rotation
        @ np.diag(
            np.square(
                [
                    dataset.beam.major_fwhm_pixels,
                    dataset.beam.minor_fwhm_pixels,
                ]
            )
        )
        @ beam_rotation.T
    )
    linear_transform = _celestial_linear_transform(dataset)
    sky_covariance = linear_transform @ pixel_covariance @ linear_transform.T
    eigenvalues, eigenvectors = np.linalg.eigh(sky_covariance)
    major_index = int(np.argmax(eigenvalues))
    minor_index = 1 - major_index
    major_vector = eigenvectors[:, major_index]
    position_angle = (
        np.rad2deg(np.arctan2(major_vector[0], major_vector[1])) % 180.0
    )
    return (
        float(np.sqrt(eigenvalues[major_index])),
        float(np.sqrt(eigenvalues[minor_index])),
        float(position_angle),
    )


def _dataset_by_id(manifest_path: Path, dataset_id: str) -> DatasetRecord:
    """Resolve one unique checked-in dataset record."""
    manifest = load_dataset_manifest(manifest_path)
    matches = tuple(
        dataset
        for dataset in manifest.datasets
        if dataset.identifier == dataset_id
    )
    if len(matches) != 1:
        raise ValueError(
            f"expected one dataset named {dataset_id!r}, found {len(matches)}"
        )
    return matches[0]


def synthetic_fits_header(dataset: DatasetRecord) -> fits.Header:
    """Translate canonical manifest metadata to a four-axis FITS header."""
    header = fits.Header()
    reference_x, reference_y = dataset.wcs.reference_pixel_xy
    sky_ra, sky_dec = dataset.wcs.reference_sky_degrees
    scale_x, scale_y = dataset.wcs.pixel_scale_degrees_xy
    header["BUNIT"] = "Jy/beam"
    header["RADESYS"] = "ICRS"
    header["EQUINOX"] = 2000.0
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CTYPE3"] = "FREQ"
    header["CTYPE4"] = "STOKES"
    header["CRPIX1"] = reference_x + 1.0
    header["CRPIX2"] = reference_y + 1.0
    header["CRPIX3"] = 1.0
    header["CRPIX4"] = 1.0
    header["CRVAL1"] = sky_ra
    header["CRVAL2"] = sky_dec
    header["CRVAL3"] = 150_000_000.0
    header["CRVAL4"] = 1.0
    header["CDELT1"] = scale_x
    header["CDELT2"] = scale_y
    header["CDELT3"] = 1_000_000.0
    header["CDELT4"] = 1.0
    rotation_radians = np.deg2rad(
        dataset.wcs.rotation_degrees_counterclockwise
    )
    if rotation_radians != 0.0:
        cosine = float(np.cos(rotation_radians))
        sine = float(np.sin(rotation_radians))
        header["PC1_1"] = cosine
        header["PC1_2"] = -scale_y * sine / scale_x
        header["PC2_1"] = scale_x * sine / scale_y
        header["PC2_2"] = cosine
    beam_major, beam_minor, beam_position_angle = _beam_header_values(dataset)
    header["BMAJ"] = beam_major
    header["BMIN"] = beam_minor
    header["BPA"] = beam_position_angle
    header["RESTFRQ"] = 150_000_000.0
    header["HEBOGDS"] = dataset.identifier
    header["HEBOGRCP"] = dataset.recipe_sha256
    return header


def synthetic_image_metadata(dataset: DatasetRecord) -> ImageMetadata:
    """Return production metadata for one governed synthetic image."""
    header = synthetic_fits_header(dataset)
    header_text = header.tostring(
        sep="\n",
        endcard=False,
        padding=False,
    )
    if not isinstance(header_text, str):
        raise TypeError("FITS header serialization did not return text")
    return ImageMetadata(
        shape_yx=dataset.recipe.shape_yx,
        unit="Jy/beam",
        beam=RestoringBeam(
            major_fwhm_degrees=cast(float, header["BMAJ"]),
            minor_fwhm_degrees=cast(float, header["BMIN"]),
            position_angle_degrees=cast(float, header["BPA"]),
        ),
        celestial_wcs=CelestialWcs(
            fits_header=header_text,
            coordinate_frame="icrs",
        ),
        reference_frequency_hz=cast(float, header["RESTFRQ"]),
    )


def materialize_dataset(
    manifest_path: Path,
    dataset_id: str,
    output_path: Path,
    *,
    overwrite: bool = False,
) -> str:
    """Write one bounded deterministic recipe and return its file SHA-256."""
    dataset = _dataset_by_id(manifest_path, dataset_id)
    image = generate_synthetic_image(dataset.recipe)
    data = np.asarray(image[np.newaxis, np.newaxis, :, :], dtype=np.float32)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(data=data, header=synthetic_fits_header(dataset))
    hdu.add_checksum(when="hebog deterministic dataset recipe")
    hdu.writeto(
        output_path,
        overwrite=overwrite,
    )
    return hashlib.sha256(output_path.read_bytes()).hexdigest()


def _file_sha256(path: Path) -> str:
    """Hash one artifact without retaining another complete copy in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _external_dataset(
    protocol_path: Path,
    manifest_path: Path,
    dataset_identifier: str,
) -> DatasetRecord:
    """Resolve a dataset only through a manifest bound by the protocol."""
    protocol = load_phase_five_external_comparison_protocol(protocol_path)
    repository_root = protocol_path.resolve().parents[2]
    manifest = manifest_path.resolve()
    governed = tuple(
        population
        for population in protocol.populations
        if (repository_root / population.manifest).resolve() == manifest
    )
    if len(governed) != 1:
        raise ValueError("manifest is not bound by the external protocol")
    if _file_sha256(manifest_path) != governed[0].manifest_sha256:
        raise ValueError("external input manifest checksum changed")
    return _dataset_by_id(manifest_path, dataset_identifier)


def _external_recipe(dataset: DatasetRecord, seed: int) -> SyntheticRecipe:
    """Resolve one declared noise realization without inventing a seed."""
    matches = tuple(
        recipe
        for recipe in iter_dataset_recipes(dataset)
        if recipe.seed == seed
    )
    if len(matches) != 1:
        raise ValueError(
            f"seed {seed} is not declared for dataset {dataset.identifier!r}"
        )
    return matches[0]


def _external_mean_rms(
    dataset: DatasetRecord,
    valid_pixels: npt.NDArray[np.bool_],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Return the exact analytic generator mean and local RMS planes."""
    recipe = dataset.recipe
    height, width = recipe.shape_yx
    gradient_x, gradient_y = recipe.noise_rms_fractional_gradient_xy
    x_normalized = (
        np.arange(width, dtype=np.float64) / max(width - 1, 1) - 0.5
    )[np.newaxis, :]
    y_normalized = (
        np.arange(height, dtype=np.float64) / max(height - 1, 1) - 0.5
    )[:, np.newaxis]
    rms = recipe.noise_rms * (
        1.0 + gradient_x * x_normalized + gradient_y * y_normalized
    )
    mean = np.full(recipe.shape_yx, recipe.background, dtype=np.float64)
    return (
        np.where(valid_pixels, mean, np.nan),
        np.where(valid_pixels, rms, np.nan),
    )


def _write_external_fits(
    path: Path,
    plane: npt.NDArray[np.float64],
    header: fits.Header,
    *,
    plane_type: Literal["Intensity", "Background", "RMS"],
) -> None:
    """Write one deterministic four-axis float64 comparison plane."""
    plane_header = header.copy()
    plane_header["BTYPE"] = plane_type
    hdu = fits.PrimaryHDU(
        data=np.asarray(plane[np.newaxis, np.newaxis, :, :], dtype=np.float64),
        header=plane_header,
    )
    hdu.add_checksum(when="hebog phase-5 external input")
    hdu.writeto(path)


def _artifact(
    directory: Path,
    role: Literal["image", "mean", "rms"],
) -> ExternalInputArtifact:
    """Capture one complete input artifact identity."""
    relative_path = _EXTERNAL_ARTIFACT_NAMES[role]
    path = directory / relative_path
    return ExternalInputArtifact(
        role=role,
        relative_path=relative_path,
        byte_count=path.stat().st_size,
        sha256=_file_sha256(path),
    )


def materialize_external_realization(
    protocol_path: Path,
    manifest_path: Path,
    dataset_identifier: str,
    seed: int,
    output_directory: Path,
) -> Path:
    """Atomically materialize one byte-identical three-plane finder input."""
    if output_directory.exists():
        raise FileExistsError(
            f"refusing to overwrite external input: {output_directory}"
        )
    dataset = _external_dataset(
        protocol_path,
        manifest_path,
        dataset_identifier,
    )
    recipe = _external_recipe(dataset, seed)
    image = generate_synthetic_image(recipe)
    valid_pixels = np.asarray(np.isfinite(image), dtype=np.bool_)
    mean, rms = _external_mean_rms(dataset, valid_pixels)
    header = synthetic_fits_header(dataset)
    header["HEBOGBAS"] = dataset.recipe_sha256
    header["HEBOGRCP"] = recipe_sha256(recipe)
    header["HEBOGSED"] = seed
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{output_directory.name}-",
        dir=output_directory.parent,
    ) as temporary_name:
        temporary = Path(temporary_name)
        _write_external_fits(
            temporary / "image.fits",
            image,
            header,
            plane_type="Intensity",
        )
        _write_external_fits(
            temporary / "mean.fits",
            mean,
            header,
            plane_type="Background",
        )
        _write_external_fits(
            temporary / "rms.fits",
            rms,
            header,
            plane_type="RMS",
        )
        bundle = ExternalInputBundle(
            schema_version=1,
            protocol_sha256=_file_sha256(protocol_path),
            manifest_sha256=_file_sha256(manifest_path),
            dataset_identifier=dataset.identifier,
            seed=seed,
            recipe_sha256=recipe_sha256(recipe),
            dtype="float64",
            shape_yx=recipe.shape_yx,
            artifacts=(
                _artifact(temporary, "image"),
                _artifact(temporary, "mean"),
                _artifact(temporary, "rms"),
            ),
        )
        (temporary / "input.json").write_bytes(bundle.canonical_json_bytes())
        temporary.replace(output_directory)
    return output_directory / "input.json"


def _verify_external_artifact(
    bundle_path: Path,
    bundle: ExternalInputBundle,
    artifact: ExternalInputArtifact,
) -> None:
    """Verify one artifact's bytes, FITS checksum, shape, and provenance."""
    artifact_path = bundle_path.parent / artifact.relative_path
    if artifact_path.stat().st_size != artifact.byte_count:
        raise ValueError(
            f"external input artifact byte count changed: {artifact_path}"
        )
    if _file_sha256(artifact_path) != artifact.sha256:
        raise ValueError(
            f"external input artifact SHA-256 changed: {artifact_path}"
        )
    with fits.open(artifact_path, checksum=True) as hdus:
        primary_hdu = cast(fits.PrimaryHDU, hdus[0])
        if (
            primary_hdu.verify_checksum() != 1
            or primary_hdu.verify_datasum() != 1
        ):
            raise ValueError(
                f"external input FITS checksum changed: {artifact_path}"
            )
        plane = primary_hdu.data
        if plane is None or plane.shape != (1, 1, *bundle.shape_yx):
            raise ValueError(
                f"external input FITS shape changed: {artifact_path}"
            )
        if plane.dtype != np.dtype(">f8"):
            raise ValueError(
                f"external input FITS dtype changed: {artifact_path}"
            )
        if primary_hdu.header["HEBOGSED"] != bundle.seed:
            raise ValueError(
                f"external input FITS seed changed: {artifact_path}"
            )
        if primary_hdu.header["HEBOGRCP"] != bundle.recipe_sha256:
            raise ValueError(
                f"external input FITS recipe changed: {artifact_path}"
            )


def load_external_input_bundle(
    path: Path,
    *,
    verify_artifacts: bool = False,
) -> ExternalInputBundle:
    """Load one canonical shared-input record and optionally verify FITS."""
    payload = path.read_bytes()
    bundle = ExternalInputBundle.model_validate_json(payload)
    if payload != bundle.canonical_json_bytes():
        raise ValueError("external input bundle JSON must be canonical")
    if not verify_artifacts:
        return bundle
    for artifact in bundle.artifacts:
        _verify_external_artifact(path, bundle, artifact)
    return bundle
