# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
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
from scipy.ndimage import correlate

GENERATOR_NAME = "hebog.synthetic.gaussian-noise"
GENERATOR_VERSION = 3

_CORRELATED_NOISE_GENERATOR_VERSION = 3

_UINT64_LIMIT = 2**64 - 1
_FIRST_RANDOM_STREAM = np.uint64(0xD1B54A32D192ED03)
_SECOND_RANDOM_STREAM = np.uint64(0x94D049BB133111EB)
_Y_COORDINATE_STREAM = np.uint64(0x8CB92BA72F3D8DD7)
_X_COORDINATE_STREAM = np.uint64(0xDB4F0B9175AE2165)
_MANTISSA_SCALE = 1.0 / 2**53
_MINIMUM_DECLINATION_DEGREES = -90.0
_MAXIMUM_DECLINATION_DEGREES = 90.0
_DEFAULT_MAXIMUM_IN_MEMORY_PIXELS = 4096 * 4096
_MINIMUM_UNRESOLVED_GROUP_SOURCES = 2


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
    rotation_degrees_counterclockwise: float = Field(
        default=0.0,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def validate_wcs(self) -> Self:
        """Reject non-finite or degenerate WCS metadata."""
        values = (
            *self.reference_pixel_xy,
            *self.reference_sky_degrees,
            *self.pixel_scale_degrees_xy,
            self.rotation_degrees_counterclockwise,
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


class SyntheticInvalidRectangle(_ManifestModel):
    """One half-open rectangular region materialised as invalid pixels."""

    y_start: int = Field(ge=0)
    y_stop: int = Field(ge=1)
    x_start: int = Field(ge=0)
    x_stop: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Require a non-empty half-open rectangle."""
        if self.y_start >= self.y_stop or self.x_start >= self.x_stop:
            raise ValueError("invalid rectangle bounds must be increasing")
        return self


class SyntheticNoiseCorrelation(_ManifestModel):
    """Gaussian noise-correlation function in image-pixel coordinates."""

    major_fwhm_pixels: float = Field(gt=0, allow_inf_nan=False)
    minor_fwhm_pixels: float = Field(gt=0, allow_inf_nan=False)
    position_angle_degrees: float = Field(allow_inf_nan=False)
    truncation_sigma: float = Field(default=4.0, ge=3.0, le=8.0)

    @model_validator(mode="after")
    def validate_axis_order(self) -> Self:
        """Require the correlation major width to contain the minor width."""
        if self.minor_fwhm_pixels > self.major_fwhm_pixels:
            raise ValueError(
                "noise-correlation minor axis cannot exceed major axis"
            )
        return self


class SyntheticRecipe(_ManifestModel):
    """Complete inputs to one version of the synthetic image generator."""

    generator: Literal["hebog.synthetic.gaussian-noise"]
    generator_version: Literal[1, 2, 3]
    seed: int = Field(ge=0, le=_UINT64_LIMIT)
    shape_yx: tuple[int, int]
    background: float = Field(allow_inf_nan=False)
    noise_rms: float = Field(ge=0, allow_inf_nan=False)
    sources: tuple[SyntheticSource, ...] = ()
    noise_rms_fractional_gradient_xy: tuple[float, float] = (0.0, 0.0)
    invalid_rectangles: tuple[SyntheticInvalidRectangle, ...] = ()
    noise_correlation: SyntheticNoiseCorrelation | None = None

    def _validate_sources(self, *, height: int, width: int) -> None:
        """Require every analytic source centre to be inside the plane."""
        for source in self.sources:
            if source.x_pixel >= width or source.y_pixel >= height:
                raise ValueError("source centre must be inside shape_yx")

    def _validate_noise_policy(self) -> None:
        """Require finite, positive, version-compatible RMS variation."""
        if not all(
            np.isfinite(value)
            for value in self.noise_rms_fractional_gradient_xy
        ):
            raise ValueError("noise RMS gradient must be finite")
        if self.generator_version == 1 and (
            self.noise_rms_fractional_gradient_xy != (0.0, 0.0)
            or self.invalid_rectangles
        ):
            raise ValueError("generator version 1 cannot use version 2 fields")
        if (
            self.generator_version < _CORRELATED_NOISE_GENERATOR_VERSION
            and self.noise_correlation is not None
        ):
            raise ValueError(
                "noise correlation is available only in generator version 3"
            )
        if (
            self.generator_version == _CORRELATED_NOISE_GENERATOR_VERSION
            and self.noise_correlation is None
        ):
            raise ValueError("generator version 3 requires noise correlation")
        gradient_x, gradient_y = self.noise_rms_fractional_gradient_xy
        if 1.0 - 0.5 * (abs(gradient_x) + abs(gradient_y)) <= 0:
            raise ValueError("noise RMS gradient must remain positive")

    def _validate_invalid_rectangles(
        self,
        *,
        height: int,
        width: int,
    ) -> None:
        """Require non-overlapping invalid regions inside the plane."""
        for rectangle in self.invalid_rectangles:
            if rectangle.y_stop > height or rectangle.x_stop > width:
                raise ValueError("invalid rectangle must be inside shape_yx")
        for index, left in enumerate(self.invalid_rectangles):
            for right in self.invalid_rectangles[index + 1 :]:
                overlaps = (
                    left.y_start < right.y_stop
                    and right.y_start < left.y_stop
                    and left.x_start < right.x_stop
                    and right.x_start < left.x_stop
                )
                if overlaps:
                    raise ValueError("invalid rectangles must not overlap")

    @model_validator(mode="after")
    def validate_geometry(self) -> Self:
        """Keep dimensions positive and every source centre in the plane."""
        height, width = self.shape_yx
        if height <= 0 or width <= 0:
            raise ValueError("shape_yx dimensions must be positive")
        self._validate_sources(height=height, width=width)
        self._validate_noise_policy()
        self._validate_invalid_rectangles(height=height, width=width)
        return self


def recipe_sha256(recipe: SyntheticRecipe) -> str:
    """Return the canonical SHA-256 provenance digest for a recipe."""
    document = recipe.model_dump(mode="json")
    if recipe.generator_version == 1:
        document.pop("noise_rms_fractional_gradient_xy")
        document.pop("invalid_rectangles")
    if recipe.generator_version < _CORRELATED_NOISE_GENERATOR_VERSION:
        document.pop("noise_correlation")
    canonical_json = json.dumps(
        document,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_json).hexdigest()


class SourceValidationStratum(_ManifestModel):
    """One named, possibly overlapping subset of analytic source truth."""

    identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    source_indices: tuple[int, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_indices(self) -> Self:
        """Require canonical non-negative indices without double counting."""
        if any(index < 0 for index in self.source_indices):
            raise ValueError(
                "validation stratum source indices must be non-negative"
            )
        if tuple(sorted(set(self.source_indices))) != self.source_indices:
            raise ValueError(
                "validation stratum source indices must be unique and sorted"
            )
        return self


class AssociationTruthGroup(_ManifestModel):
    """One explicitly identified observable association in injected truth."""

    identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    source_indices: tuple[int, ...] = Field(min_length=1)
    resolution_class: Literal["individually-resolvable", "unresolved-blend"]
    reference_position_xy: tuple[float, float]
    reference_integrated_brightness_jy_pixels_per_beam: float = Field(
        gt=0,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def validate_group(self) -> Self:
        """Require canonical membership and resolution cardinality."""
        if tuple(sorted(set(self.source_indices))) != self.source_indices:
            raise ValueError(
                "truth-group source indices must be unique and sorted"
            )
        if any(index < 0 for index in self.source_indices):
            raise ValueError("truth-group source indices must be non-negative")
        if not all(np.isfinite(value) for value in self.reference_position_xy):
            raise ValueError("truth-group reference position must be finite")
        if (
            self.resolution_class == "individually-resolvable"
            and len(self.source_indices) != 1
        ):
            raise ValueError(
                "individually resolvable truth group must contain one source"
            )
        if (
            self.resolution_class == "unresolved-blend"
            and len(self.source_indices) < _MINIMUM_UNRESOLVED_GROUP_SOURCES
        ):
            raise ValueError(
                "unresolved blend must contain at least two sources"
            )
        return self


class AssociationGroupValidationStratum(_ManifestModel):
    """One named subset of explicit truth associations."""

    identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    group_identifiers: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_group_identifiers(self) -> Self:
        """Require canonical unique group identities."""
        if (
            tuple(sorted(set(self.group_identifiers)))
            != self.group_identifiers
        ):
            raise ValueError(
                "validation stratum group identifiers must be unique and "
                "sorted"
            )
        return self


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
    noise_realization_seeds: tuple[int, ...] = ()
    validation_strata: tuple[SourceValidationStratum, ...] = ()
    classification_strata: tuple[SourceValidationStratum, ...] = ()
    association_truth_groups: tuple[AssociationTruthGroup, ...] = ()
    association_group_strata: tuple[
        AssociationGroupValidationStratum, ...
    ] = ()

    @model_validator(mode="after")
    def validate_recipe_checksum(self) -> Self:
        """Detect stale provenance whenever generation inputs change."""
        expected = recipe_sha256(self.recipe)
        if self.recipe_sha256 != expected:
            raise ValueError(
                "recipe_sha256 does not match the canonical recipe"
            )
        if (
            self.recipe.generator_version == 1
            and self.wcs.rotation_degrees_counterclockwise != 0.0
        ):
            raise ValueError("generator version 1 cannot use rotated WCS")
        if len(set(self.noise_realization_seeds)) != len(
            self.noise_realization_seeds
        ):
            raise ValueError("noise realization seeds must be unique")
        if self.recipe.seed in self.noise_realization_seeds:
            raise ValueError(
                "noise realization seeds must not repeat the base seed"
            )
        if any(
            seed < 0 or seed > _UINT64_LIMIT
            for seed in self.noise_realization_seeds
        ):
            raise ValueError("noise realization seeds must fit uint64")
        self._validate_source_strata()
        self._validate_association_truth()
        if (
            self.expected_statistics.background_jy_per_beam
            != self.recipe.background
            or self.expected_statistics.noise_rms_jy_per_beam
            != self.recipe.noise_rms
        ):
            raise ValueError(
                "expected statistics must match the synthetic recipe"
            )
        invalid_pixels = sum(
            (rectangle.y_stop - rectangle.y_start)
            * (rectangle.x_stop - rectangle.x_start)
            for rectangle in self.recipe.invalid_rectangles
        )
        height, width = self.recipe.shape_yx
        expected_finite_fraction = 1.0 - invalid_pixels / (height * width)
        if not np.isclose(
            self.expected_statistics.finite_fraction,
            expected_finite_fraction,
            rtol=0.0,
            atol=np.finfo(np.float64).eps,
        ):
            raise ValueError(
                "expected finite fraction must match invalid rectangles"
            )
        return self

    def _validate_source_strata(self) -> None:
        """Require unique strata that refer only to declared source truth."""
        all_strata: tuple[SourceValidationStratum, ...] = ()
        for strata, label in (
            (self.validation_strata, "validation"),
            (self.classification_strata, "classification"),
        ):
            identifiers = tuple(stratum.identifier for stratum in strata)
            if len(set(identifiers)) != len(identifiers):
                raise ValueError(f"{label} stratum identifiers must be unique")
            all_strata += strata
        classification_indices = tuple(
            source_index
            for stratum in self.classification_strata
            for source_index in stratum.source_indices
        )
        if len(set(classification_indices)) != len(classification_indices):
            raise ValueError("classification strata must not overlap")
        if any(
            source_index >= len(self.recipe.sources)
            for stratum in all_strata
            for source_index in stratum.source_indices
        ):
            raise ValueError("source stratum index must identify recipe truth")

    def _validate_association_truth(self) -> None:
        """Bind explicit observable groups and strata to analytic sources."""
        if not self.association_truth_groups:
            if self.association_group_strata:
                raise ValueError(
                    "association group strata require association truth groups"
                )
            return
        identifiers = tuple(
            group.identifier for group in self.association_truth_groups
        )
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(
                "association truth-group identifiers must be unique"
            )
        memberships = tuple(
            index
            for group in self.association_truth_groups
            for index in group.source_indices
        )
        if sorted(memberships) != list(range(len(self.recipe.sources))):
            raise ValueError(
                "association truth groups must partition recipe sources"
            )
        for group in self.association_truth_groups:
            self._validate_association_group_quantities(group)
        stratum_identifiers = tuple(
            stratum.identifier for stratum in self.association_group_strata
        )
        if len(set(stratum_identifiers)) != len(stratum_identifiers):
            raise ValueError(
                "association group stratum identifiers must be unique"
            )
        known_identifiers = set(identifiers)
        if any(
            identifier not in known_identifiers
            for stratum in self.association_group_strata
            for identifier in stratum.group_identifiers
        ):
            raise ValueError(
                "association group stratum must identify governed truth"
            )

    def _validate_association_group_quantities(
        self,
        group: AssociationTruthGroup,
    ) -> None:
        """Require stored group position and brightness to match emitters."""
        sources = tuple(
            self.recipe.sources[index] for index in group.source_indices
        )
        brightnesses = np.asarray(
            [
                source.peak_flux_jy_per_beam
                * 2.0
                * np.pi
                * source.major_sigma_pixels
                * source.minor_sigma_pixels
                for source in sources
            ],
            dtype=np.float64,
        )
        total = float(np.sum(brightnesses))
        reference_position = (
            float(
                np.dot(
                    brightnesses,
                    [source.x_pixel for source in sources],
                )
                / total
            ),
            float(
                np.dot(
                    brightnesses,
                    [source.y_pixel for source in sources],
                )
                / total
            ),
        )
        if not np.allclose(
            group.reference_position_xy,
            reference_position,
            rtol=1e-12,
            atol=1e-12,
        ):
            raise ValueError(
                "truth-group reference position does not match source truth"
            )
        if not np.isclose(
            group.reference_integrated_brightness_jy_pixels_per_beam,
            total,
            rtol=1e-12,
            atol=0.0,
        ):
            raise ValueError(
                "truth-group reference integrated brightness does not match "
                "source truth"
            )


class DatasetManifest(_ManifestModel):
    """Versioned collection of uniquely identified validation datasets."""

    schema_version: Literal[1, 2]
    manifest_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    datasets: tuple[DatasetRecord, ...]

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> Self:
        """Prevent ambiguous test-data lookup."""
        identifiers = [dataset.identifier for dataset in self.datasets]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("dataset identifiers must be unique")
        if self.schema_version == 1 and any(
            dataset.association_truth_groups for dataset in self.datasets
        ):
            raise ValueError(
                "association truth groups require manifest schema 2"
            )
        return self


def load_dataset_manifest(path: Path) -> DatasetManifest:
    """Load and validate a dataset manifest without resolving its data."""
    document = path.read_text(encoding="utf-8")
    return DatasetManifest.model_validate_json(document)


def iter_dataset_recipes(
    dataset: DatasetRecord,
) -> tuple[SyntheticRecipe, ...]:
    """Expand one governed truth recipe across recorded noise realizations."""
    return (
        dataset.recipe,
        *(
            dataset.recipe.model_copy(update={"seed": seed})
            for seed in dataset.noise_realization_seeds
        ),
    )


def _splitmix64(values: npt.NDArray[np.uint64]) -> npt.NDArray[np.uint64]:
    """Mix integer pixel addresses into deterministic pseudo-random bits."""
    mixed = values + np.uint64(0x9E3779B97F4A7C15)
    mixed = (mixed ^ (mixed >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    mixed = (mixed ^ (mixed >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return mixed ^ (mixed >> np.uint64(31))


def _standard_normal_from_addresses(
    addresses: npt.NDArray[np.uint64],
    *,
    seed: int,
) -> npt.NDArray[np.float64]:
    """Map deterministic integer addresses to one standard-normal stream."""
    seed_bits = np.uint64(seed)
    first_bits = _splitmix64(addresses ^ seed_bits ^ _FIRST_RANDOM_STREAM)
    second_bits = _splitmix64(addresses ^ seed_bits ^ _SECOND_RANDOM_STREAM)
    first_uniform = (first_bits >> np.uint64(11)).astype(np.float64) + 0.5
    first_uniform *= _MANTISSA_SCALE
    second_uniform = (second_bits >> np.uint64(11)).astype(np.float64) + 0.5
    second_uniform *= _MANTISSA_SCALE
    return np.sqrt(-2.0 * np.log(first_uniform)) * np.cos(
        2.0 * np.pi * second_uniform
    )


def _coordinate_normal_noise(
    recipe: SyntheticRecipe,
    *,
    y_start: int,
    y_stop: int,
    x_start: int,
    x_stop: int,
) -> npt.NDArray[np.float64]:
    """Generate deterministic noise on the unbounded integer pixel lattice."""
    y_coordinates = np.arange(y_start, y_stop, dtype=np.int64).view(np.uint64)
    x_coordinates = np.arange(x_start, x_stop, dtype=np.int64).view(np.uint64)
    y_addresses = _splitmix64(
        y_coordinates[:, np.newaxis] ^ _Y_COORDINATE_STREAM
    )
    x_addresses = _splitmix64(
        x_coordinates[np.newaxis, :] ^ _X_COORDINATE_STREAM
    )
    return _standard_normal_from_addresses(
        y_addresses ^ x_addresses,
        seed=recipe.seed,
    )


def _noise_correlation_kernel(
    correlation: SyntheticNoiseCorrelation,
) -> tuple[npt.NDArray[np.float64], int]:
    """Return an L2-normalized filter whose autocorrelation is requested."""
    fwhm_to_sigma = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    filter_major_sigma = (
        correlation.major_fwhm_pixels * fwhm_to_sigma / np.sqrt(2.0)
    )
    filter_minor_sigma = (
        correlation.minor_fwhm_pixels * fwhm_to_sigma / np.sqrt(2.0)
    )
    halo = int(np.ceil(correlation.truncation_sigma * filter_major_sigma))
    offsets = np.arange(-halo, halo + 1, dtype=np.float64)
    y_grid, x_grid = np.meshgrid(offsets, offsets, indexing="ij")
    angle = np.deg2rad(correlation.position_angle_degrees)
    cosine = np.cos(angle)
    sine = np.sin(angle)
    major_offset = cosine * x_grid + sine * y_grid
    minor_offset = -sine * x_grid + cosine * y_grid
    kernel = np.exp(
        -0.5
        * (
            np.square(major_offset / filter_major_sigma)
            + np.square(minor_offset / filter_minor_sigma)
        )
    )
    kernel /= np.sqrt(np.sum(np.square(kernel), dtype=np.float64))
    return np.asarray(kernel, dtype=np.float64), halo


def _correlated_normal_noise(
    recipe: SyntheticRecipe,
    *,
    y_start: int,
    y_stop: int,
    x_start: int,
    x_stop: int,
) -> npt.NDArray[np.float64]:
    """Generate normalized Gaussian-correlated noise for one exact window."""
    correlation = recipe.noise_correlation
    if correlation is None:
        raise ValueError("correlated noise recipe lacks correlation metadata")
    kernel, halo = _noise_correlation_kernel(correlation)
    expanded = _coordinate_normal_noise(
        recipe,
        y_start=y_start - halo,
        y_stop=y_stop + halo,
        x_start=x_start - halo,
        x_stop=x_stop + halo,
    )
    filtered = correlate(expanded, kernel, mode="constant", cval=0.0)
    return np.asarray(filtered[halo:-halo, halo:-halo], dtype=np.float64)


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
    if recipe.generator_version == _CORRELATED_NOISE_GENERATOR_VERSION:
        return _correlated_normal_noise(
            recipe,
            y_start=y_start,
            y_stop=y_stop,
            x_start=x_start,
            x_stop=x_stop,
        )

    full_width = np.uint64(recipe.shape_yx[1])
    y_indices = np.arange(y_start, y_stop, dtype=np.uint64)[:, np.newaxis]
    x_indices = np.arange(x_start, x_stop, dtype=np.uint64)[np.newaxis, :]
    addresses = y_indices * full_width + x_indices
    return _standard_normal_from_addresses(
        addresses,
        seed=recipe.seed,
    )


def _noise_rms_scale(
    recipe: SyntheticRecipe,
    *,
    y_start: int,
    y_stop: int,
    x_start: int,
    x_stop: int,
) -> npt.NDArray[np.float64]:
    """Return the partition-invariant affine RMS multiplier for a window."""
    gradient_x, gradient_y = recipe.noise_rms_fractional_gradient_xy
    if gradient_x == 0 and gradient_y == 0:
        return np.ones((y_stop - y_start, x_stop - x_start), dtype=np.float64)
    height, width = recipe.shape_yx
    x_denominator = max(width - 1, 1)
    y_denominator = max(height - 1, 1)
    x_normalized = (
        np.arange(x_start, x_stop, dtype=np.float64) / x_denominator - 0.5
    )[np.newaxis, :]
    y_normalized = (
        np.arange(y_start, y_stop, dtype=np.float64) / y_denominator - 0.5
    )[:, np.newaxis]
    return np.asarray(
        1.0 + gradient_x * x_normalized + gradient_y * y_normalized,
        dtype=np.float64,
    )


def _apply_invalid_rectangles(
    image: npt.NDArray[np.float64],
    recipe: SyntheticRecipe,
    window_bounds: tuple[int, int, int, int],
) -> None:
    """Set intersections with governed invalid rectangles to NaN in place."""
    y_start, y_stop, x_start, x_stop = window_bounds
    for rectangle in recipe.invalid_rectangles:
        intersection_y_start = max(y_start, rectangle.y_start)
        intersection_y_stop = min(y_stop, rectangle.y_stop)
        intersection_x_start = max(x_start, rectangle.x_start)
        intersection_x_stop = min(x_stop, rectangle.x_stop)
        if (
            intersection_y_start >= intersection_y_stop
            or intersection_x_start >= intersection_x_stop
        ):
            continue
        image[
            intersection_y_start - y_start : intersection_y_stop - y_start,
            intersection_x_start - x_start : intersection_x_stop - x_start,
        ] = np.nan


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
    rms_scale = _noise_rms_scale(
        recipe,
        y_start=y_start,
        y_stop=y_stop,
        x_start=x_start,
        x_stop=x_stop,
    )
    image = recipe.background + recipe.noise_rms * rms_scale * standard_noise
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

    _apply_invalid_rectangles(
        image,
        recipe,
        (y_start, y_stop, x_start, x_stop),
    )

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
