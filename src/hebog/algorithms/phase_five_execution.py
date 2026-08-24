"""Reviewed stage-halo derivation for bounded Phase 5 execution."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
from typing import Literal

from hebog.algorithms.extended_measurement import (
    extended_measurement_halo_pixels,
    segment_refinement_halo_pixels,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    residual_atrous_scale_halos_pixels,
    scale_smoothing_halo_pixels,
)
from hebog.algorithms.multiscale_association import (
    compact_context_halo_pixels,
)
from hebog.config import ExtendedEmissionMeasurementConfig
from hebog.data_models.partitioning import PartitionManifest

PhaseFiveStageName = Literal[
    "matched-filter-seed",
    "residual-b3-atrous",
    "segment-labelling",
    "segment-refinement",
    "cross-scale-association",
    "compact-context",
    "extended-measurement",
    "combined-reconciliation",
    "product-materialization",
]
PhaseFiveHaloBasis = Literal[
    "four-sigma-gaussian-kernel-radius",
    "cumulative-b3-spline-support",
    "boundary-summary-reconciliation",
    "three-pixel-opening-and-half-beam-recovery",
    "reconciled-exact-support-records",
    "half-beam-context-dilation",
    "one-point-five-beam-nearest-owned-aperture",
    "array-free-canonical-record-reduction",
    "bounded-row-block-materialization",
]

_FROZEN_SCALES: tuple[tuple[int, float], ...] = (
    (1, 1.0),
    (2, 2.0),
    (3, 4.0),
)
_FROZEN_FILTER_TRUNCATION_SIGMA = 4.0
_FROZEN_MEASUREMENT_APERTURE_BEAMS = 1.5
_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class PhaseFiveStageHalo:
    """One stage's worst-case interior read and admission evidence."""

    stage_name: PhaseFiveStageName
    halo_yx: tuple[int, int]
    read_shape_yx: tuple[int, int]
    read_pixel_count: int
    admission_limit_pixels: int
    basis: PhaseFiveHaloBasis
    scale_halos_pixels: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class PhaseFiveHaloPlan:
    """Complete pre-allocation halo plan for the frozen Rapthor profile."""

    tile_core_shape_yx: tuple[int, int]
    maximum_task_pixels: int
    stages: tuple[PhaseFiveStageHalo, ...]
    maximum_halo_yx: tuple[int, int]
    maximum_read_shape_yx: tuple[int, int]
    maximum_read_pixel_count: int


def _validate_task_limit(maximum_task_pixels: int) -> None:
    """Require one explicit positive global task-pixel limit."""
    if (
        isinstance(maximum_task_pixels, bool)
        or not isinstance(maximum_task_pixels, Integral)
        or maximum_task_pixels < 1
    ):
        raise ValueError("maximum_task_pixels must be a positive integer")


def _validate_core_shape(tile_core_shape_yx: tuple[int, int]) -> None:
    """Reject non-integral or empty tile cores before arithmetic."""
    if len(tile_core_shape_yx) != _IMAGE_DIMENSIONS or any(
        isinstance(value, bool) or not isinstance(value, Integral) or value < 1
        for value in tile_core_shape_yx
    ):
        raise ValueError(
            "tile_core_shape_yx must contain two positive integers"
        )


def _stage_halo(  # noqa: PLR0913
    stage_name: PhaseFiveStageName,
    *,
    halo_pixels: int,
    tile_core_shape_yx: tuple[int, int],
    admission_limit_pixels: int,
    basis: PhaseFiveHaloBasis,
    scale_halos_pixels: tuple[int, ...] = (),
) -> PhaseFiveStageHalo:
    """Validate and record one stage's worst-case interior read."""
    halo_yx = (halo_pixels, halo_pixels)
    # Reuse the canonical geometry validator rather than allowing the Phase 5
    # planner to drift from the partition-manifest guardrail.
    PartitionManifest.create(
        image_shape_yx=tile_core_shape_yx,
        tile_core_shape_yx=tile_core_shape_yx,
        halo_yx=halo_yx,
    )
    read_shape_yx = (
        tile_core_shape_yx[0] + 2 * halo_yx[0],
        tile_core_shape_yx[1] + 2 * halo_yx[1],
    )
    read_pixel_count = read_shape_yx[0] * read_shape_yx[1]
    if read_pixel_count > admission_limit_pixels:
        raise ValueError(
            f"{stage_name} requires {read_pixel_count} pixels but its "
            f"admission limit is {admission_limit_pixels}"
        )
    return PhaseFiveStageHalo(
        stage_name=stage_name,
        halo_yx=halo_yx,
        read_shape_yx=read_shape_yx,
        read_pixel_count=read_pixel_count,
        admission_limit_pixels=admission_limit_pixels,
        basis=basis,
        scale_halos_pixels=scale_halos_pixels,
    )


def derive_phase_five_halo_plan(
    beam: BeamShapePixels,
    *,
    tile_core_shape_yx: tuple[int, int],
    maximum_task_pixels: int,
    measurement_config: ExtendedEmissionMeasurementConfig,
) -> PhaseFiveHaloPlan:
    """Derive and admit every frozen Phase 5 stage before execution.

    The returned sizes describe worst-case interior tiles. Image-edge reads
    may be smaller because manifests clip halos to the logical image. Pixel
    admission is the first bounded-memory guard; measured byte and workspace
    evidence is recorded by the later Step 5 execution audit.
    """
    _validate_core_shape(tile_core_shape_yx)
    _validate_task_limit(maximum_task_pixels)
    if (
        measurement_config.aperture_radius_beams
        != _FROZEN_MEASUREMENT_APERTURE_BEAMS
    ):
        raise ValueError("Phase 5 requires the reviewed 1.5-beam aperture")
    matched_halos = tuple(
        scale_smoothing_halo_pixels(
            beam,
            width_beams=width_beams,
            truncation_sigma=_FROZEN_FILTER_TRUNCATION_SIGMA,
        )
        for _, width_beams in _FROZEN_SCALES
    )
    atrous_halos = residual_atrous_scale_halos_pixels()
    measurement_limit = min(
        maximum_task_pixels,
        measurement_config.maximum_task_pixels,
    )
    definitions: tuple[
        tuple[
            PhaseFiveStageName,
            int,
            int,
            PhaseFiveHaloBasis,
            tuple[int, ...],
        ],
        ...,
    ] = (
        (
            "matched-filter-seed",
            matched_halos[-1],
            maximum_task_pixels,
            "four-sigma-gaussian-kernel-radius",
            matched_halos,
        ),
        (
            "residual-b3-atrous",
            atrous_halos[-1],
            maximum_task_pixels,
            "cumulative-b3-spline-support",
            atrous_halos,
        ),
        (
            "segment-labelling",
            0,
            maximum_task_pixels,
            "boundary-summary-reconciliation",
            (),
        ),
        (
            "segment-refinement",
            segment_refinement_halo_pixels(beam.major_fwhm_pixels),
            maximum_task_pixels,
            "three-pixel-opening-and-half-beam-recovery",
            (),
        ),
        (
            "cross-scale-association",
            0,
            maximum_task_pixels,
            "reconciled-exact-support-records",
            (),
        ),
        (
            "compact-context",
            compact_context_halo_pixels(beam.major_fwhm_pixels),
            maximum_task_pixels,
            "half-beam-context-dilation",
            (),
        ),
        (
            "extended-measurement",
            extended_measurement_halo_pixels(
                measurement_config,
                beam_major_fwhm_pixels=beam.major_fwhm_pixels,
            ),
            measurement_limit,
            "one-point-five-beam-nearest-owned-aperture",
            (),
        ),
        (
            "combined-reconciliation",
            0,
            maximum_task_pixels,
            "array-free-canonical-record-reduction",
            (),
        ),
        (
            "product-materialization",
            0,
            maximum_task_pixels,
            "bounded-row-block-materialization",
            (),
        ),
    )
    stages = tuple(
        _stage_halo(
            stage_name,
            halo_pixels=halo_pixels,
            tile_core_shape_yx=tile_core_shape_yx,
            admission_limit_pixels=admission_limit_pixels,
            basis=basis,
            scale_halos_pixels=scale_halos_pixels,
        )
        for (
            stage_name,
            halo_pixels,
            admission_limit_pixels,
            basis,
            scale_halos_pixels,
        ) in definitions
    )
    maximum_halo = max(stage.halo_yx[0] for stage in stages)
    maximum_stage = max(stages, key=lambda stage: stage.read_pixel_count)
    return PhaseFiveHaloPlan(
        tile_core_shape_yx=tile_core_shape_yx,
        maximum_task_pixels=maximum_task_pixels,
        stages=stages,
        maximum_halo_yx=(maximum_halo, maximum_halo),
        maximum_read_shape_yx=maximum_stage.read_shape_yx,
        maximum_read_pixel_count=maximum_stage.read_pixel_count,
    )
