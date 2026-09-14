#!/usr/bin/env python3
"""Build the prospective compact Phase 5 held-out sentinel population.

This module only constructs and validates metadata.  It never generates a
science image, opens finder output, or authorizes execution.
"""

from __future__ import annotations

import json
from math import log, pi, sqrt
from pathlib import Path
from typing import NamedTuple

from hebog.validation.adaptive_background_lane import (
    build_adaptive_development_manifest,
)
from hebog.validation.datasets import (
    AssociationGroupValidationStratum,
    AssociationTruthGroup,
    BeamMetadata,
    DatasetManifest,
    DatasetRecord,
    DatasetRole,
    ExpectedImageStatistics,
    MultiscaleGroupValidationStratum,
    MultiscaleTruthGroup,
    RedistributionStatus,
    SourceValidationStratum,
    SyntheticInvalidRectangle,
    SyntheticNoiseCorrelation,
    SyntheticRecipe,
    SyntheticSource,
    WcsMetadata,
    iter_dataset_recipes,
    recipe_sha256,
)
from hebog.validation.external_runners import canonical_sha256, file_sha256

_FIRST_SEED = 2026970001
_LAST_SEED = 2026970168
_REALIZATIONS_PER_CELL = 4
_EXTENDED_CELL_COUNT = 36
_COMPACT_CELL_COUNT = 6
_NOMINAL_RMS = 0.0002
_BEAM = BeamMetadata(
    major_fwhm_pixels=5.4,
    minor_fwhm_pixels=3.6,
    position_angle_degrees=31.0,
)
_WCS = WcsMetadata(
    reference_pixel_xy=(256.0, 256.0),
    reference_sky_degrees=(180.0, -30.0),
    pixel_scale_degrees_xy=(-0.0004, 0.0004),
    rotation_degrees_counterclockwise=23.0,
)
_FWHM_PER_SIGMA = 2.0 * sqrt(2.0 * log(2.0))
_EXPECTED_HISTORICAL_AUDIT = {
    "historical_manifest_count": 46,
    "historical_registry_canonical_sha256": (
        "47aca0c78cd75b2e336148baa89a2354a72900c19ea84b3145788c1de519c160"
    ),
    "historical_seed_count": 20917,
}


class CompactCell(NamedTuple):
    """One prospectively declared compact failure-mode guard."""

    identifier: str
    shape_yx: tuple[int, int]
    sources: tuple[SyntheticSource, ...]
    noise_gradient_xy: tuple[float, float] = (0.0, 0.0)
    invalid_rectangles: tuple[SyntheticInvalidRectangle, ...] = ()
    crosses_tile_corner: bool = False
    touches_image_edge: bool = False


def _source(  # noqa: PLR0913
    x_pixel: float,
    y_pixel: float,
    peak_sigma: float,
    *,
    major_scale: float = 1.0,
    minor_scale: float = 1.0,
    angle_degrees: float = 31.0,
) -> SyntheticSource:
    """Return one beam-aligned analytic compact component."""
    return SyntheticSource(
        x_pixel=x_pixel,
        y_pixel=y_pixel,
        peak_flux_jy_per_beam=peak_sigma * _NOMINAL_RMS,
        major_sigma_pixels=(
            major_scale * _BEAM.major_fwhm_pixels / _FWHM_PER_SIGMA
        ),
        minor_sigma_pixels=(
            minor_scale * _BEAM.minor_fwhm_pixels / _FWHM_PER_SIGMA
        ),
        rotation_degrees_counterclockwise_from_x=angle_degrees,
    )


def compact_cells() -> tuple[CompactCell, ...]:
    """Return six small guards for known public-facade failure modes."""
    return (
        CompactCell(
            "compact-isolated-near-threshold-interior",
            (512, 512),
            (_source(173.0, 181.0, 6.0),),
        ),
        CompactCell(
            "compact-isolated-bright-image-edge",
            (512, 512),
            (_source(2.5, 257.0, 30.0, angle_degrees=74.0),),
            touches_image_edge=True,
        ),
        CompactCell(
            "compact-unequal-two-peak-connected",
            (512, 512),
            (
                _source(249.0, 191.0, 25.0),
                _source(257.0, 191.0, 12.0),
            ),
        ),
        CompactCell(
            "compact-three-peak-connected-tile-corner",
            (512, 512),
            (
                _source(248.0, 248.0, 25.0),
                _source(256.0, 253.0, 18.0),
                _source(264.0, 258.0, 14.0),
            ),
            crosses_tile_corner=True,
        ),
        CompactCell(
            "compact-non-square-varying-noise",
            (384, 512),
            (
                _source(181.0, 173.0, 18.0),
                _source(337.0, 281.0, 11.0, angle_degrees=103.0),
            ),
            noise_gradient_xy=(0.5, -0.3),
        ),
        CompactCell(
            "compact-invalid-pixel-boundary",
            (512, 512),
            (_source(255.0, 256.0, 22.0),),
            invalid_rectangles=(
                SyntheticInvalidRectangle(
                    y_start=248,
                    y_stop=265,
                    x_start=260,
                    x_stop=273,
                ),
            ),
        ),
    )


def _integrated_brightness(source: SyntheticSource) -> float:
    """Return the analytic Gaussian integral in Jy pixels per beam."""
    return float(
        2.0
        * pi
        * source.peak_flux_jy_per_beam
        * source.major_sigma_pixels
        * source.minor_sigma_pixels
    )


def _compact_dataset(
    cell: CompactCell,
    seeds: tuple[int, int, int, int],
) -> DatasetRecord:
    """Build one four-realization qualification record without pixels."""
    recipe = SyntheticRecipe(
        generator="hebog.synthetic.gaussian-noise",
        generator_version=3,
        seed=seeds[0],
        shape_yx=cell.shape_yx,
        background=-0.00005,
        noise_rms=_NOMINAL_RMS,
        sources=cell.sources,
        noise_rms_fractional_gradient_xy=cell.noise_gradient_xy,
        invalid_rectangles=cell.invalid_rectangles,
        noise_correlation=SyntheticNoiseCorrelation(
            major_fwhm_pixels=_BEAM.major_fwhm_pixels,
            minor_fwhm_pixels=_BEAM.minor_fwhm_pixels,
            position_angle_degrees=_BEAM.position_angle_degrees,
        ),
    )
    source_indices = tuple(range(len(cell.sources)))
    group_identifiers = tuple(
        f"{cell.identifier}-truth-{index}"
        for index in range(1, len(cell.sources) + 1)
    )
    invalid_pixels = sum(
        (rectangle.y_stop - rectangle.y_start)
        * (rectangle.x_stop - rectangle.x_start)
        for rectangle in cell.invalid_rectangles
    )
    height, width = cell.shape_yx
    return DatasetRecord(
        identifier=f"phase5-sentinel-compact-guard-{cell.identifier}",
        role=DatasetRole.QUALIFICATION,
        purpose=f"Fresh compact held-out guard for {cell.identifier}.",
        provenance=(
            "Prospectively declared analytic Gaussian-noise-v3 geometry; "
            "no pixels or finder results were generated before execution."
        ),
        redistribution=RedistributionStatus.GENERATED_LOCALLY,
        beam=_BEAM,
        wcs=_WCS,
        expected_statistics=ExpectedImageStatistics(
            background_jy_per_beam=recipe.background,
            noise_rms_jy_per_beam=recipe.noise_rms,
            finite_fraction=1.0 - invalid_pixels / (height * width),
        ),
        recipe=recipe,
        recipe_sha256=recipe_sha256(recipe),
        noise_realization_seeds=seeds[1:],
        validation_strata=(
            SourceValidationStratum(
                identifier="compact-guard-components",
                source_indices=source_indices,
            ),
        ),
        association_truth_groups=tuple(
            AssociationTruthGroup(
                identifier=identifier,
                source_indices=(index,),
                resolution_class="individually-resolvable",
                reference_position_xy=(source.x_pixel, source.y_pixel),
                reference_integrated_brightness_jy_pixels_per_beam=(
                    _integrated_brightness(source)
                ),
            )
            for index, (identifier, source) in enumerate(
                zip(group_identifiers, cell.sources, strict=True)
            )
        ),
        association_group_strata=(
            AssociationGroupValidationStratum(
                identifier="compact-guard-groups",
                group_identifiers=group_identifiers,
            ),
        ),
        multiscale_truth_groups=tuple(
            MultiscaleTruthGroup(
                identifier=identifier,
                source_indices=(index,),
                morphology="mixed-compact-extended",
                catalogue_role="astronomical-source",
                reference_position_xy=(source.x_pixel, source.y_pixel),
                reference_integrated_brightness_jy_pixels_per_beam=(
                    _integrated_brightness(source)
                ),
                major_extent_beams=(
                    source.major_sigma_pixels
                    * _FWHM_PER_SIGMA
                    / _BEAM.major_fwhm_pixels
                ),
                minor_extent_beams=(
                    source.minor_sigma_pixels
                    * _FWHM_PER_SIGMA
                    / _BEAM.minor_fwhm_pixels
                ),
                governed_scale_orders=(1,),
                crosses_tile_boundary=cell.crosses_tile_corner,
                crosses_tile_corner=cell.crosses_tile_corner,
                touches_image_edge=cell.touches_image_edge,
            )
            for index, (identifier, source) in enumerate(
                zip(group_identifiers, cell.sources, strict=True)
            )
        ),
        multiscale_group_strata=(
            MultiscaleGroupValidationStratum(
                identifier="compact-guard-groups",
                group_identifiers=group_identifiers,
            ),
        ),
    )


def _extended_datasets(
    seeds: tuple[int, ...],
) -> tuple[DatasetRecord, ...]:
    """Clone all reviewed adaptive cells with only new identities and seeds."""
    manifest = build_adaptive_development_manifest()
    if len(manifest.datasets) != _EXTENDED_CELL_COUNT:
        raise ValueError("adaptive-background cell population changed")
    output: list[DatasetRecord] = []
    for index, dataset in enumerate(manifest.datasets):
        start = index * _REALIZATIONS_PER_CELL
        cell_seeds = seeds[start : start + _REALIZATIONS_PER_CELL]
        recipe = dataset.recipe.model_copy(update={"seed": cell_seeds[0]})
        output.append(
            dataset.model_copy(
                update={
                    "identifier": (
                        "phase5-sentinel-extended-"
                        + dataset.identifier.removeprefix("adaptive-")
                    ),
                    "role": DatasetRole.QUALIFICATION,
                    "purpose": (
                        "Fresh held-out analogue of reviewed adaptive cell "
                        f"{dataset.identifier}."
                    ),
                    "provenance": (
                        "Seed-disjoint qualification clone of the reviewed "
                        "adaptive-background geometry; no pixels or results "
                        "were generated before execution."
                    ),
                    "recipe": recipe,
                    "recipe_sha256": recipe_sha256(recipe),
                    "noise_realization_seeds": cell_seeds[1:],
                }
            )
        )
    return tuple(output)


def build_manifest() -> DatasetManifest:
    """Return the exact 42-cell, 168-image prospective sentinel manifest."""
    seeds = tuple(range(_FIRST_SEED, _LAST_SEED + 1))
    extended_count = _EXTENDED_CELL_COUNT * _REALIZATIONS_PER_CELL
    extended = _extended_datasets(seeds[:extended_count])
    compact = tuple(
        _compact_dataset(
            cell,
            (
                seeds[extended_count + index * _REALIZATIONS_PER_CELL],
                seeds[extended_count + index * _REALIZATIONS_PER_CELL + 1],
                seeds[extended_count + index * _REALIZATIONS_PER_CELL + 2],
                seeds[extended_count + index * _REALIZATIONS_PER_CELL + 3],
            ),
        )
        for index, cell in enumerate(compact_cells())
    )
    if len(compact) != _COMPACT_CELL_COUNT:
        raise ValueError("compact guard population changed")
    return DatasetManifest(
        schema_version=3,
        manifest_id="phase-5-compact-held-out-sentinel",
        datasets=(*extended, *compact),
    )


def _manifest_seeds(manifest: DatasetManifest) -> set[int]:
    """Return all declared independent realization seeds."""
    return {
        recipe.seed
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }


def audit_manifest(
    repository_root: Path,
    manifest: DatasetManifest,
) -> dict[str, object]:
    """Prove the prospective seeds are unique and historically disjoint."""
    records: list[dict[str, object]] = []
    historical: set[int] = set()
    for path in sorted((repository_root / "config/datasets").glob("*.json")):
        if path.name == "phase-5-compact-held-out-sentinel.json":
            continue
        prior = DatasetManifest.model_validate_json(path.read_bytes())
        prior_seeds = _manifest_seeds(prior)
        if historical.intersection(prior_seeds):
            raise ValueError("checked-in historical dataset seeds overlap")
        historical.update(prior_seeds)
        records.append(
            {
                "path": path.relative_to(repository_root).as_posix(),
                "seed_count": len(prior_seeds),
                "sha256": file_sha256(path),
            }
        )
    prospective = _manifest_seeds(manifest)
    observed_historical = {
        "historical_manifest_count": len(records),
        "historical_registry_canonical_sha256": canonical_sha256(records),
        "historical_seed_count": len(historical),
    }
    if observed_historical != _EXPECTED_HISTORICAL_AUDIT:
        raise ValueError("historical seed registry changed after pre-review")
    if (
        len(prospective) != _LAST_SEED - _FIRST_SEED + 1
        or prospective != set(range(_FIRST_SEED, _LAST_SEED + 1))
        or not historical.isdisjoint(prospective)
    ):
        raise ValueError("prospective sentinel seeds are not fresh and exact")
    return {
        **observed_historical,
        "prospective_seed_count": len(prospective),
        "seed_disjoint": True,
    }


def cell_id(dataset: DatasetRecord) -> str:
    """Return the stable cell identity encoded by one manifest record."""
    for prefix in (
        "phase5-sentinel-extended-",
        "phase5-sentinel-compact-guard-",
    ):
        if dataset.identifier.startswith(prefix):
            return dataset.identifier.removeprefix(prefix)
    raise ValueError("sentinel dataset identifier is malformed")


def expected_input_ids(manifest: DatasetManifest) -> tuple[str, ...]:
    """Return all input identities in deterministic manifest order."""
    return tuple(
        f"{dataset.identifier}-seed-{recipe.seed}"
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    )


def manifest_json_bytes(manifest: DatasetManifest) -> bytes:
    """Serialize one exact finite manifest with canonical presentation."""
    return (
        json.dumps(
            manifest.model_dump(mode="json"),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


if __name__ == "__main__":
    root = Path(__file__).parents[2]
    population = build_manifest()
    print(json.dumps(audit_manifest(root, population), sort_keys=True))
