"""Versioned validation-dataset manifests and synthetic image generation.

The generator is deliberately stateless at the pixel level. Generating any
window produces the same values as slicing a plane generated in one call, so
large validation images do not depend on a particular partition layout.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Literal, Self

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, model_validator

GENERATOR_NAME = "hebog.synthetic.gaussian-noise"
GENERATOR_VERSION = 1

_UINT64_LIMIT = 2**64 - 1
_FIRST_RANDOM_STREAM = np.uint64(0xD1B54A32D192ED03)
_SECOND_RANDOM_STREAM = np.uint64(0x94D049BB133111EB)
_MANTISSA_SCALE = 1.0 / 2**53
_MINIMUM_DECLINATION_DEGREES = -90.0
_MAXIMUM_DECLINATION_DEGREES = 90.0
_DEFAULT_MAXIMUM_IN_MEMORY_PIXELS = 4096 * 4096


class DatasetRole(str, Enum):
    """The one test lane allowed to consume a dataset."""

    DEVELOPMENT = "development"
    REGRESSION = "regression"
    QUALIFICATION = "qualification"


class RedistributionStatus(str, Enum):
    """How a validation dataset may be obtained and shared."""

    GENERATED_LOCALLY = "generated-locally"
    REDISTRIBUTABLE = "redistributable"
    RESTRICTED = "restricted"


class _ManifestModel(BaseModel):
    """Strict immutable base for versioned manifest records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class BeamMetadata(_ManifestModel):
    """Synthetic restoring-beam metadata in image-pixel units."""

    major_fwhm_pixels: float = Field(gt=0, allow_inf_nan=False)
    minor_fwhm_pixels: float = Field(gt=0, allow_inf_nan=False)
    position_angle_degrees: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_axis_order(self) -> Self:
        """Require the named major axis to be at least the minor axis."""
        if self.minor_fwhm_pixels > self.major_fwhm_pixels:
            raise ValueError("minor beam axis cannot exceed major beam axis")
        return self


class WcsMetadata(_ManifestModel):
    """Minimal celestial WCS provenance in canonical manifest units."""

    frame: Literal["icrs"] = "icrs"
    reference_pixel_xy: tuple[float, float]
    reference_sky_degrees: tuple[float, float]
    pixel_scale_degrees_xy: tuple[float, float]

    @model_validator(mode="after")
    def validate_wcs(self) -> Self:
        """Reject non-finite or degenerate WCS metadata."""
        values = (
            *self.reference_pixel_xy,
            *self.reference_sky_degrees,
            *self.pixel_scale_degrees_xy,
        )
        if not all(np.isfinite(value) for value in values):
            raise ValueError("WCS values must be finite")
        _, declination_degrees = self.reference_sky_degrees
        if not (
            _MINIMUM_DECLINATION_DEGREES
            <= declination_degrees
            <= _MAXIMUM_DECLINATION_DEGREES
        ):
            raise ValueError("reference declination must be within [-90, 90]")
        if any(scale == 0 for scale in self.pixel_scale_degrees_xy):
            raise ValueError("WCS pixel scales must be non-zero")
        return self


class ExpectedImageStatistics(_ManifestModel):
    """Generator parameters used as expected image statistics."""

    background_jy_per_beam: float = Field(allow_inf_nan=False)
    noise_rms_jy_per_beam: float = Field(ge=0, allow_inf_nan=False)
    finite_fraction: float = Field(ge=0, le=1, allow_inf_nan=False)


class SyntheticSource(_ManifestModel):
    """Analytic elliptical Gaussian source in global pixel coordinates."""

    x_pixel: float = Field(ge=0, allow_inf_nan=False)
    y_pixel: float = Field(ge=0, allow_inf_nan=False)
    peak_flux_jy_per_beam: float = Field(gt=0, allow_inf_nan=False)
    major_sigma_pixels: float = Field(gt=0, allow_inf_nan=False)
    minor_sigma_pixels: float = Field(gt=0, allow_inf_nan=False)
    rotation_degrees_counterclockwise_from_x: float = Field(
        default=0.0,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def validate_axis_order(self) -> Self:
        """Require the analytic major axis to be the larger axis."""
        if self.minor_sigma_pixels > self.major_sigma_pixels:
            raise ValueError(
                "minor source axis cannot exceed major source axis"
            )
        return self


class SyntheticRecipe(_ManifestModel):
    """Complete inputs to one version of the synthetic image generator."""

    generator: Literal["hebog.synthetic.gaussian-noise"]
    generator_version: Literal[1]
    seed: int = Field(ge=0, le=_UINT64_LIMIT)
    shape_yx: tuple[int, int]
    background: float = Field(allow_inf_nan=False)
    noise_rms: float = Field(ge=0, allow_inf_nan=False)
    sources: tuple[SyntheticSource, ...] = ()

    @model_validator(mode="after")
    def validate_geometry(self) -> Self:
        """Keep dimensions positive and every source centre in the plane."""
        height, width = self.shape_yx
        if height <= 0 or width <= 0:
            raise ValueError("shape_yx dimensions must be positive")
        for source in self.sources:
            if source.x_pixel >= width or source.y_pixel >= height:
                raise ValueError("source centre must be inside shape_yx")
        return self


def recipe_sha256(recipe: SyntheticRecipe) -> str:
    """Return the canonical SHA-256 provenance digest for a recipe."""
    canonical_json = json.dumps(
        recipe.model_dump(mode="json"),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_json).hexdigest()


class DatasetRecord(_ManifestModel):
    """One governed validation dataset and its generation provenance."""

    identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    role: DatasetRole
    purpose: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    redistribution: RedistributionStatus
    beam: BeamMetadata
    wcs: WcsMetadata
    expected_statistics: ExpectedImageStatistics
    recipe: SyntheticRecipe
    recipe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_recipe_checksum(self) -> Self:
        """Detect stale provenance whenever generation inputs change."""
        expected = recipe_sha256(self.recipe)
        if self.recipe_sha256 != expected:
            raise ValueError(
                "recipe_sha256 does not match the canonical recipe"
            )
        if (
            self.expected_statistics.background_jy_per_beam
            != self.recipe.background
            or self.expected_statistics.noise_rms_jy_per_beam
            != self.recipe.noise_rms
        ):
            raise ValueError(
                "expected statistics must match the synthetic recipe"
            )
        return self


class DatasetManifest(_ManifestModel):
    """Versioned collection of uniquely identified validation datasets."""

    schema_version: Literal[1]
    manifest_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    datasets: tuple[DatasetRecord, ...]

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> Self:
        """Prevent ambiguous test-data lookup."""
        identifiers = [dataset.identifier for dataset in self.datasets]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("dataset identifiers must be unique")
        return self


def load_dataset_manifest(path: Path) -> DatasetManifest:
    """Load and validate a dataset manifest without resolving its data."""
    document = path.read_text(encoding="utf-8")
    return DatasetManifest.model_validate_json(document)


def _splitmix64(values: npt.NDArray[np.uint64]) -> npt.NDArray[np.uint64]:
    """Mix integer pixel addresses into deterministic pseudo-random bits."""
    mixed = values + np.uint64(0x9E3779B97F4A7C15)
    mixed = (mixed ^ (mixed >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    mixed = (mixed ^ (mixed >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return mixed ^ (mixed >> np.uint64(31))


def _normal_noise(
    recipe: SyntheticRecipe,
    *,
    y_start: int,
    y_stop: int,
    x_start: int,
    x_stop: int,
) -> npt.NDArray[np.float64]:
    """Generate partition-invariant standard-normal noise for one window."""
    height = y_stop - y_start
    width = x_stop - x_start
    if recipe.noise_rms == 0:
        return np.zeros((height, width), dtype=np.float64)

    full_width = np.uint64(recipe.shape_yx[1])
    y_indices = np.arange(y_start, y_stop, dtype=np.uint64)[:, np.newaxis]
    x_indices = np.arange(x_start, x_stop, dtype=np.uint64)[np.newaxis, :]
    addresses = y_indices * full_width + x_indices
    seed = np.uint64(recipe.seed)
    first_bits = _splitmix64(addresses ^ seed ^ _FIRST_RANDOM_STREAM)
    second_bits = _splitmix64(addresses ^ seed ^ _SECOND_RANDOM_STREAM)
    first_uniform = (first_bits >> np.uint64(11)).astype(np.float64) + 0.5
    first_uniform *= _MANTISSA_SCALE
    second_uniform = (second_bits >> np.uint64(11)).astype(np.float64) + 0.5
    second_uniform *= _MANTISSA_SCALE
    return np.sqrt(-2.0 * np.log(first_uniform)) * np.cos(
        2.0 * np.pi * second_uniform
    )


def _validate_window(
    recipe: SyntheticRecipe,
    *,
    y_start: int,
    y_stop: int,
    x_start: int,
    x_stop: int,
) -> None:
    """Validate a half-open generation window against the global plane."""
    if y_start >= y_stop or x_start >= x_stop:
        raise ValueError("synthetic window must be non-empty")
    height, width = recipe.shape_yx
    if y_start < 0 or x_start < 0 or y_stop > height or x_stop > width:
        raise ValueError("synthetic window bounds must be inside shape_yx")


def generate_synthetic_window(
    recipe: SyntheticRecipe,
    *,
    y_start: int,
    y_stop: int,
    x_start: int,
    x_stop: int,
) -> npt.NDArray[np.float64]:
    """Generate one half-open window without materialising the full plane."""
    _validate_window(
        recipe,
        y_start=y_start,
        y_stop=y_stop,
        x_start=x_start,
        x_stop=x_stop,
    )
    standard_noise = _normal_noise(
        recipe,
        y_start=y_start,
        y_stop=y_stop,
        x_start=x_start,
        x_stop=x_stop,
    )
    image = recipe.background + recipe.noise_rms * standard_noise
    y_grid = np.arange(y_start, y_stop, dtype=np.float64)[:, np.newaxis]
    x_grid = np.arange(x_start, x_stop, dtype=np.float64)[np.newaxis, :]

    for source in recipe.sources:
        rotation_radians = np.deg2rad(
            source.rotation_degrees_counterclockwise_from_x
        )
        cosine = np.cos(rotation_radians)
        sine = np.sin(rotation_radians)
        x_offset = x_grid - source.x_pixel
        y_offset = y_grid - source.y_pixel
        major_offset = cosine * x_offset + sine * y_offset
        minor_offset = -sine * x_offset + cosine * y_offset
        exponent = -0.5 * (
            np.square(major_offset / source.major_sigma_pixels)
            + np.square(minor_offset / source.minor_sigma_pixels)
        )
        image += source.peak_flux_jy_per_beam * np.exp(exponent)

    return np.asarray(image, dtype=np.float64)


def generate_synthetic_image(
    recipe: SyntheticRecipe,
    *,
    maximum_pixels: int = _DEFAULT_MAXIMUM_IN_MEMORY_PIXELS,
) -> npt.NDArray[np.float64]:
    """Generate a complete in-memory image for a bounded recipe."""
    height, width = recipe.shape_yx
    if maximum_pixels <= 0:
        raise ValueError("maximum_pixels must be positive")
    if height * width > maximum_pixels:
        raise ValueError(
            "complete synthetic image exceeds maximum_pixels; use "
            "generate_synthetic_window for bounded generation"
        )
    return generate_synthetic_window(
        recipe,
        y_start=0,
        y_stop=height,
        x_start=0,
        x_stop=width,
    )
