"""Prospective population and decision logic for adaptive-background risk."""

from __future__ import annotations

from functools import lru_cache
from math import cos, pi, sin, sqrt

import numpy as np
import numpy.typing as npt

from hebog.validation.adaptive_background_development import (
    AdaptiveDevelopmentCell,
    build_adaptive_development_matrix,
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
    SyntheticNoiseCorrelation,
    SyntheticRecipe,
    SyntheticSource,
    WcsMetadata,
    generate_synthetic_window,
    recipe_sha256,
)

_FWHM_PER_SIGMA = 2.0 * sqrt(2.0 * np.log(2.0))
_IMAGE_SHAPE_YX = (512, 512)
_NOMINAL_RMS = 0.0002
_TRUTH_THRESHOLD_SIGMA = 3.0


def _beam(cell: AdaptiveDevelopmentCell) -> BeamMetadata:
    """Return the exact observing beam named by one approved cell."""
    values = {
        "beam-a": (5.4, 3.6, 31.0),
        "beam-b": (6.3, 4.0, 68.0),
    }
    major, minor, angle = values[cell.beam_id]
    return BeamMetadata(
        major_fwhm_pixels=major,
        minor_fwhm_pixels=minor,
        position_angle_degrees=angle,
    )


def _placement(cell: AdaptiveDevelopmentCell) -> tuple[float, float]:
    """Return the exact approved global source centre."""
    return (
        (181.0, 173.0) if cell.placement_id == "interior" else (256.0, 256.0)
    )


def _source(
    position_xy: tuple[float, float],
    peak: float,
    major_fwhm: float,
    minor_fwhm: float,
    angle: float,
) -> SyntheticSource:
    """Build one Gaussian from explicit FWHM geometry."""
    x, y = position_xy
    major = max(major_fwhm, minor_fwhm)
    minor = min(major_fwhm, minor_fwhm)
    return SyntheticSource(
        x_pixel=x,
        y_pixel=y,
        peak_flux_jy_per_beam=peak,
        major_sigma_pixels=major / _FWHM_PER_SIGMA,
        minor_sigma_pixels=minor / _FWHM_PER_SIGMA,
        rotation_degrees_counterclockwise_from_x=angle % 180.0,
    )


def _shell_sources(
    cell: AdaptiveDevelopmentCell,
    beam: BeamMetadata,
) -> tuple[SyntheticSource, ...]:
    """Construct eight contiguous beam-convolved knots on one ring."""
    center_x, center_y = _placement(cell)
    radius = 0.5 * cell.extent_major_beams * beam.major_fwhm_pixels
    tangent_fwhm = max(
        beam.major_fwhm_pixels,
        1.15 * 2.0 * pi * radius / 8.0,
    )
    return tuple(
        _source(
            (
                center_x + radius * cos(angle),
                center_y + radius * sin(angle),
            ),
            1.0,
            tangent_fwhm,
            beam.minor_fwhm_pixels,
            np.rad2deg(angle) + 90.0,
        )
        for angle in np.linspace(0.0, 2.0 * pi, 8, endpoint=False)
    )


def _filament_sources(
    cell: AdaptiveDevelopmentCell,
    beam: BeamMetadata,
) -> tuple[SyntheticSource, ...]:
    """Construct seven overlapping knots on a centred 120-degree arc."""
    center_x, center_y = _placement(cell)
    radius_beams = min(
        cell.extent_major_beams / (2.0 * sin(pi / 3.0)),
        1.25 / (2.0 * sin(pi / 18.0)),
    )
    radius = radius_beams * beam.major_fwhm_pixels
    angles = np.linspace(-pi / 3.0, pi / 3.0, 7)
    raw_offsets = tuple(
        (radius * cos(angle), radius * sin(angle)) for angle in angles
    )
    mean_x = float(np.mean([offset[0] for offset in raw_offsets]))
    mean_y = float(np.mean([offset[1] for offset in raw_offsets]))
    intrinsic_segment = cell.extent_major_beams * beam.major_fwhm_pixels / 7.0
    tangent_fwhm = sqrt(beam.major_fwhm_pixels**2 + intrinsic_segment**2)
    return tuple(
        _source(
            (
                center_x + x_offset - mean_x,
                center_y + y_offset - mean_y,
            ),
            1.0,
            tangent_fwhm,
            beam.minor_fwhm_pixels,
            np.rad2deg(angle) + 90.0,
        )
        for angle, (x_offset, y_offset) in zip(
            angles,
            raw_offsets,
            strict=True,
        )
    )


def _mixed_sources(
    cell: AdaptiveDevelopmentCell,
    beam: BeamMetadata,
) -> tuple[SyntheticSource, ...]:
    """Construct a restoring-beam core and 75%-flux elliptical halo."""
    center_x, center_y = _placement(cell)
    halo_major = cell.extent_major_beams * beam.major_fwhm_pixels
    halo_minor = max(2.0 * beam.minor_fwhm_pixels, halo_major / 2.0)
    core_area = beam.major_fwhm_pixels * beam.minor_fwhm_pixels
    halo_area = halo_major * halo_minor
    halo_peak = 3.0 * core_area / halo_area
    return (
        _source(
            (center_x, center_y),
            1.0,
            beam.major_fwhm_pixels,
            beam.minor_fwhm_pixels,
            beam.position_angle_degrees,
        ),
        _source(
            (center_x, center_y),
            halo_peak,
            halo_major,
            halo_minor,
            beam.position_angle_degrees,
        ),
    )


def _signal_from_sources(
    sources: tuple[SyntheticSource, ...],
) -> npt.NDArray[np.float64]:
    """Evaluate only the deterministic analytic source contribution."""
    recipe = SyntheticRecipe(
        generator="hebog.synthetic.gaussian-noise",
        generator_version=3,
        seed=0,
        shape_yx=_IMAGE_SHAPE_YX,
        background=0.0,
        noise_rms=0.0,
        sources=sources,
        noise_correlation=SyntheticNoiseCorrelation(
            major_fwhm_pixels=5.4,
            minor_fwhm_pixels=3.6,
            position_angle_degrees=31.0,
        ),
    )
    return generate_synthetic_window(
        recipe,
        y_start=0,
        y_stop=_IMAGE_SHAPE_YX[0],
        x_start=0,
        x_stop=_IMAGE_SHAPE_YX[1],
    )


@lru_cache(maxsize=12)
def _unit_template(
    cell: AdaptiveDevelopmentCell,
) -> tuple[SyntheticSource, ...]:
    """Return one geometry's uncalibrated component template."""
    beam = _beam(cell)
    if cell.morphology == "shell":
        return _shell_sources(cell, beam)
    if cell.morphology == "curved-filament":
        return _filament_sources(cell, beam)
    return _mixed_sources(cell, beam)


def _calibrated_sources(
    cell: AdaptiveDevelopmentCell,
) -> tuple[SyntheticSource, ...]:
    """Scale one noiseless composite to its predeclared nominal peak."""
    sources = _unit_template(cell)
    maximum = float(np.max(_signal_from_sources(sources)))
    scale = cell.target_nominal_peak_sigma * _NOMINAL_RMS / maximum
    return tuple(
        source.model_copy(
            update={
                "peak_flux_jy_per_beam": source.peak_flux_jy_per_beam * scale
            }
        )
        for source in sources
    )


def _domain_id(value: str) -> str:
    """Translate the descriptive cell identity into a domain identifier."""
    return value.replace("_", "-").replace("--", "-")


def _reference_quantities(
    sources: tuple[SyntheticSource, ...],
) -> tuple[tuple[float, float], float]:
    """Return flux-weighted pixel position and integrated pixel brightness."""
    brightness = np.asarray(
        [
            source.peak_flux_jy_per_beam
            * 2.0
            * pi
            * source.major_sigma_pixels
            * source.minor_sigma_pixels
            for source in sources
        ],
        dtype=np.float64,
    )
    total = float(np.sum(brightness))
    position = (
        float(
            np.dot(brightness, [source.x_pixel for source in sources]) / total
        ),
        float(
            np.dot(brightness, [source.y_pixel for source in sources]) / total
        ),
    )
    return position, total


def _dataset(
    cell: AdaptiveDevelopmentCell,
    *,
    provenance_review: str = "6287ad3e",
) -> DatasetRecord:
    """Build one four-realization dataset from an approved matrix cell."""
    beam = _beam(cell)
    sources = _calibrated_sources(cell)
    position, integrated = _reference_quantities(sources)
    gradient = (0.0, 0.0) if cell.noise_gradient_id == "flat" else (0.4, -0.2)
    recipe = SyntheticRecipe(
        generator="hebog.synthetic.gaussian-noise",
        generator_version=3,
        seed=cell.noise_seeds[0],
        shape_yx=_IMAGE_SHAPE_YX,
        background=0.0,
        noise_rms=_NOMINAL_RMS,
        sources=sources,
        noise_rms_fractional_gradient_xy=gradient,
        noise_correlation=SyntheticNoiseCorrelation(
            major_fwhm_pixels=beam.major_fwhm_pixels,
            minor_fwhm_pixels=beam.minor_fwhm_pixels,
            position_angle_degrees=beam.position_angle_degrees,
        ),
    )
    identifier = f"adaptive-{_domain_id(cell.cell_id)}"
    truth_id = f"truth-{identifier}"
    source_indices = tuple(range(len(sources)))
    at_corner = cell.placement_id == "tile-corner"
    return DatasetRecord(
        identifier=identifier,
        role=DatasetRole.DEVELOPMENT,
        purpose=(
            "Prospective truth-linked adaptive-background trigger and "
            f"self-absorption test for {cell.cell_id}."
        ),
        provenance=(
            "Deterministic analytic Gaussian composite pre-registered by "
            "Phase 5 adaptive-background development review "
            f"{provenance_review}."
        ),
        redistribution=RedistributionStatus.GENERATED_LOCALLY,
        beam=beam,
        wcs=WcsMetadata(
            reference_pixel_xy=(256.0, 256.0),
            reference_sky_degrees=(180.0, -30.0),
            pixel_scale_degrees_xy=(-0.0004, 0.0004),
            rotation_degrees_counterclockwise=23.0,
        ),
        expected_statistics=ExpectedImageStatistics(
            background_jy_per_beam=0.0,
            noise_rms_jy_per_beam=_NOMINAL_RMS,
            finite_fraction=1.0,
        ),
        recipe=recipe,
        recipe_sha256=recipe_sha256(recipe),
        noise_realization_seeds=cell.noise_seeds[1:],
        validation_strata=(
            SourceValidationStratum(
                identifier="adaptive-truth-components",
                source_indices=source_indices,
            ),
        ),
        association_truth_groups=(
            AssociationTruthGroup(
                identifier=truth_id,
                source_indices=source_indices,
                resolution_class="unresolved-blend",
                reference_position_xy=position,
                reference_integrated_brightness_jy_pixels_per_beam=integrated,
            ),
        ),
        association_group_strata=(
            AssociationGroupValidationStratum(
                identifier="adaptive-truth-group",
                group_identifiers=(truth_id,),
            ),
        ),
        multiscale_truth_groups=(
            MultiscaleTruthGroup(
                identifier=truth_id,
                source_indices=source_indices,
                morphology=cell.morphology,
                catalogue_role="astronomical-source",
                reference_position_xy=position,
                reference_integrated_brightness_jy_pixels_per_beam=integrated,
                major_extent_beams=cell.extent_major_beams,
                minor_extent_beams=max(1.0, cell.extent_major_beams / 2.0),
                governed_scale_orders=(1, 2, 3),
                crosses_tile_boundary=at_corner,
                crosses_tile_corner=at_corner,
                compact_deblend_disposition="deferred-extended",
                touches_image_edge=False,
            ),
        ),
        multiscale_group_strata=(
            MultiscaleGroupValidationStratum(
                identifier="adaptive-truth-group",
                group_identifiers=(truth_id,),
            ),
        ),
    )


def build_adaptive_development_manifest() -> DatasetManifest:
    """Return the exact approved 36-cell, 144-image development manifest."""
    return DatasetManifest(
        schema_version=3,
        manifest_id="phase-5-adaptive-background-development",
        datasets=tuple(
            _dataset(cell) for cell in build_adaptive_development_matrix()
        ),
    )


def _true_rms(recipe: SyntheticRecipe) -> npt.NDArray[np.float64]:
    """Return the exact analytic local RMS used by generator version three."""
    height, width = recipe.shape_yx
    gradient_x, gradient_y = recipe.noise_rms_fractional_gradient_xy
    x = (np.arange(width, dtype=np.float64) / max(width - 1, 1) - 0.5)[
        np.newaxis, :
    ]
    y = (np.arange(height, dtype=np.float64) / max(height - 1, 1) - 0.5)[
        :, np.newaxis
    ]
    return np.asarray(
        recipe.noise_rms * (1.0 + gradient_x * x + gradient_y * y),
        dtype=np.float64,
    )


def source_signal_and_truth(
    recipe: SyntheticRecipe,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.float64],
]:
    """Return analytic signal, three-sigma truth support, and true RMS."""
    signal = _signal_from_sources(recipe.sources)
    true_rms = _true_rms(recipe)
    truth = np.asarray(signal >= _TRUTH_THRESHOLD_SIGMA * true_rms)
    signal.setflags(write=False)
    truth.setflags(write=False)
    true_rms.setflags(write=False)
    return signal, truth, true_rms
