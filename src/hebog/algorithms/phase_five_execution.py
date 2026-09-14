"""Reviewed stage-halo derivation for bounded Phase 5 execution."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import ceil
from numbers import Integral
from typing import Literal, TypeVar

import numpy as np
import numpy.typing as npt

from hebog.algorithms.extended_measurement import (
    extended_measurement_halo_pixels,
    segment_refinement_halo_pixels,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    PreparedScaleInputs,
    ResidualAtrousResult,
    ScaleFilterBankResult,
    ScaleFilterResponse,
    build_residual_atrous_plan,
    build_scale_filter_bank,
    calibrated_scale_snrs,
    evaluate_residual_atrous,
    evaluate_scale_filter_bank,
    residual_atrous_scale_halos_pixels,
    scale_smoothing_halo_pixels,
)
from hebog.algorithms.multiscale_association import (
    compact_context_halo_pixels,
)
from hebog.config import (
    ExtendedEmissionMeasurementConfig,
    ResidualMultiscaleDetectionConfig,
)
from hebog.data_models.partitioning import PartitionManifest, TilePartition

PhaseFiveStageName = Literal[
    "matched-filter-seed",
    "residual-b3-atrous",
    "segment-labelling",
    "segment-association",
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
    "three-beam-residual-reconstruction-association-dilation",
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
_FROZEN_SEGMENT_ASSOCIATION_BEAMS = 3.0
_IMAGE_DIMENSIONS = 2
_ArrayScalar = TypeVar("_ArrayScalar", bound=np.generic)


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


@dataclass(frozen=True, slots=True)
class PhaseFiveFilterTileResult:
    """Core-only Phase 5 filter evidence from one bounded halo read.

    Workspace evidence describes the complete read evaluation. Every array in
    the returned scientific records is an owned immutable core copy, so no
    result retains an image-sized or halo-sized input buffer.
    """

    partition: TilePartition
    prepared_inputs: PreparedScaleInputs
    matched_filter: ScaleFilterBankResult
    atrous_result: ResidualAtrousResult
    read_pixel_count: int
    maximum_filter_evaluation_bytes: int

    @property
    def retained_array_bytes(self) -> int:
        """Return exact owned ndarray payload retained by this core result."""
        return (
            _prepared_array_bytes(self.prepared_inputs)
            + _scale_response_array_bytes(self.matched_filter.responses)
            + _residual_atrous_array_bytes(self.atrous_result)
        )


@dataclass(frozen=True, slots=True)
class PhaseFiveDetectionTileEvidence:
    """Core-local fields that precede global topology reconciliation."""

    partition: TilePartition
    direct_snr: npt.NDArray[np.float64]
    matched_maximum_snr: npt.NDArray[np.float64]
    atrous_maximum_snr: npt.NDArray[np.float64]
    atrous_scale_snrs: tuple[npt.NDArray[np.float64], ...]
    significant_scale_masks: tuple[npt.NDArray[np.bool_], ...]
    reconstruction_membership: npt.NDArray[np.bool_]
    reconstruction_seeds: npt.NDArray[np.bool_]
    detection_membership: npt.NDArray[np.bool_]
    detection_seeds: npt.NDArray[np.bool_]

    @property
    def retained_array_bytes(self) -> int:
        """Return exact owned ndarray payload retained for local topology."""
        return sum(
            array.nbytes
            for array in (
                self.direct_snr,
                self.matched_maximum_snr,
                self.atrous_maximum_snr,
                *self.atrous_scale_snrs,
                *self.significant_scale_masks,
                self.reconstruction_membership,
                self.reconstruction_seeds,
                self.detection_membership,
                self.detection_seeds,
            )
        )


def _prepared_array_bytes(prepared: PreparedScaleInputs) -> int:
    """Return exact retained payload for one prepared image record."""
    return sum(
        array.nbytes
        for array in (
            prepared.residual_jy_per_beam,
            prepared.rms_jy_per_beam,
            prepared.scientifically_valid,
        )
    )


def _scale_response_array_bytes(
    responses: tuple[ScaleFilterResponse, ...],
) -> int:
    """Return exact retained payload for aligned scale responses."""
    return sum(
        array.nbytes
        for response in responses
        for array in (
            response.response_jy_per_beam,
            response.effective_rms_jy_per_beam,
            response.valid_support_fraction,
            response.scientifically_valid,
        )
    )


def _residual_atrous_array_bytes(result: ResidualAtrousResult) -> int:
    """Return exact retained payload for one residual B3 result."""
    return _scale_response_array_bytes(result.responses) + sum(
        array.nbytes
        for array in (
            result.reconstructed_signal_jy_per_beam,
            result.coarse_smoothing_jy_per_beam,
            result.scientifically_valid,
        )
    )


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


def _scale_filter_halos_pixels(
    beam: BeamShapePixels,
) -> tuple[int, ...]:
    """Return the frozen matched-filter radii without allocating kernels."""
    return tuple(
        scale_smoothing_halo_pixels(
            beam,
            width_beams=width_beams,
            truncation_sigma=_FROZEN_FILTER_TRUNCATION_SIGMA,
        )
        for _, width_beams in _FROZEN_SCALES
    )


def scale_filter_halo_pixels(beam: BeamShapePixels) -> int:
    """Return the widest frozen Phase 5 filter halo without allocation."""
    return max(
        *_scale_filter_halos_pixels(beam),
        *residual_atrous_scale_halos_pixels(),
    )


def segment_association_halo_pixels(beam: BeamShapePixels) -> int:
    """Return the frozen residual/reconstruction grouping radius."""
    return ceil(_FROZEN_SEGMENT_ASSOCIATION_BEAMS * beam.major_fwhm_pixels)


def _validate_filter_read(
    partition: TilePartition,
    *,
    image_shape_yx: tuple[int, int],
    required_halo_pixels: int,
    read_shape_yx: tuple[int, int],
) -> None:
    """Require the exact clipped halo before allocating filter workspaces."""
    partition.read_bounds.require_inside(image_shape_yx)
    partition.core_bounds.require_inside(image_shape_yx)
    if partition.read_bounds.shape_yx != read_shape_yx:
        raise ValueError(
            "filter input arrays must match the partition read bounds"
        )
    expected_read = partition.core_bounds.expanded(
        required_halo_pixels,
        image_shape_yx,
    )
    if partition.read_bounds != expected_read:
        raise ValueError(
            "partition read bounds must provide the exact clipped Phase 5 "
            "filter halo"
        )


def _core_copy(
    values: npt.NDArray[_ArrayScalar],
    partition: TilePartition,
) -> npt.NDArray[_ArrayScalar]:
    """Copy one core so its record cannot retain the halo read allocation."""
    core = np.array(values[partition.core_slices_yx], copy=True)
    core.setflags(write=False)
    return core


def _core_response(
    response: ScaleFilterResponse,
    partition: TilePartition,
) -> ScaleFilterResponse:
    """Return one core-only immutable scale response."""
    return ScaleFilterResponse(
        scale_order=response.scale_order,
        nominal_scale_beam_fwhm=response.nominal_scale_beam_fwhm,
        response_jy_per_beam=_core_copy(
            response.response_jy_per_beam,
            partition,
        ),
        effective_rms_jy_per_beam=_core_copy(
            response.effective_rms_jy_per_beam,
            partition,
        ),
        valid_support_fraction=_core_copy(
            response.valid_support_fraction,
            partition,
        ),
        scientifically_valid=_core_copy(
            response.scientifically_valid,
            partition,
        ),
    )


def _immutable_array(
    values: npt.NDArray[_ArrayScalar],
) -> npt.NDArray[_ArrayScalar]:
    """Freeze one already-owned local scientific field without another copy."""
    values.setflags(write=False)
    return values


def derive_phase_five_detection_tile_evidence(
    result: PhaseFiveFilterTileResult,
    config: ResidualMultiscaleDetectionConfig,
) -> PhaseFiveDetectionTileEvidence:
    """Derive local masks and seeds before bounded global reconciliation.

    No connected component is accepted here because support may cross any
    number of tile boundaries. Adjacent-scale membership and seed values are
    point-local; the stage reconciles their compact side/corner summaries.
    """
    prepared = result.prepared_inputs
    shape = prepared.residual_jy_per_beam.shape
    minimum_support = config.minimum_scale_support_fraction
    matched_scale_snrs = calibrated_scale_snrs(
        result.matched_filter.responses,
        minimum_support_fraction=minimum_support,
    )
    atrous_scale_snrs = calibrated_scale_snrs(
        result.atrous_result.responses,
        minimum_support_fraction=minimum_support,
    )
    matched_maximum = np.maximum.reduce(matched_scale_snrs)
    atrous_maximum = np.maximum.reduce(atrous_scale_snrs)
    direct_snr = np.full(shape, -np.inf, dtype=np.float64)
    np.divide(
        prepared.residual_jy_per_beam,
        prepared.rms_jy_per_beam,
        out=direct_snr,
        where=prepared.scientifically_valid,
    )
    significant = tuple(
        np.asarray(
            scale_snr >= config.island_threshold_sigma,
            dtype=np.bool_,
        )
        for scale_snr in atrous_scale_snrs
    )
    reconstruction_membership = np.logical_or.reduce(
        tuple(
            current & following for current, following in pairwise(significant)
        )
    )
    reconstruction_seeds = reconstruction_membership & (
        atrous_maximum >= config.detection_threshold_sigma
    )
    detection_membership = prepared.scientifically_valid & (
        direct_snr >= config.island_threshold_sigma
    )
    combined_seed_snr = np.maximum(matched_maximum, direct_snr)
    np.maximum(
        combined_seed_snr,
        atrous_maximum,
        out=combined_seed_snr,
        where=reconstruction_membership,
    )
    detection_seeds = detection_membership & (
        combined_seed_snr >= config.detection_threshold_sigma
    )
    return PhaseFiveDetectionTileEvidence(
        partition=result.partition,
        direct_snr=_immutable_array(direct_snr),
        matched_maximum_snr=_immutable_array(matched_maximum),
        atrous_maximum_snr=_immutable_array(atrous_maximum),
        atrous_scale_snrs=atrous_scale_snrs,
        significant_scale_masks=tuple(
            _immutable_array(mask) for mask in significant
        ),
        reconstruction_membership=_immutable_array(reconstruction_membership),
        reconstruction_seeds=_immutable_array(reconstruction_seeds),
        detection_membership=_immutable_array(detection_membership),
        detection_seeds=_immutable_array(detection_seeds),
    )


def evaluate_phase_five_filter_tile(
    prepared_read: PreparedScaleInputs,
    *,
    partition: TilePartition,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    minimum_support_fraction: float,
) -> PhaseFiveFilterTileResult:
    """Evaluate the promoted filters on one read and return its owned core.

    This is the bounded local-neighbourhood seam for Phase 5. Connected
    support is deliberately not labelled here: callers reconcile core labels
    through the existing bounded edge and corner summaries.
    """
    read_shape_yx = prepared_read.residual_jy_per_beam.shape
    if not (
        prepared_read.rms_jy_per_beam.shape == read_shape_yx
        and prepared_read.scientifically_valid.shape == read_shape_yx
    ):
        raise ValueError(
            "prepared filter-read arrays must have the same shape"
        )
    required_halo = scale_filter_halo_pixels(beam)
    _validate_filter_read(
        partition,
        image_shape_yx=image_shape_yx,
        required_halo_pixels=required_halo,
        read_shape_yx=read_shape_yx,
    )
    prepared_core = PreparedScaleInputs(
        residual_jy_per_beam=_core_copy(
            prepared_read.residual_jy_per_beam,
            partition,
        ),
        rms_jy_per_beam=_core_copy(
            prepared_read.rms_jy_per_beam,
            partition,
        ),
        scientifically_valid=_core_copy(
            prepared_read.scientifically_valid,
            partition,
        ),
    )
    prepared_read_bytes = _prepared_array_bytes(prepared_read)
    prepared_core_bytes = _prepared_array_bytes(prepared_core)
    matched_read = evaluate_scale_filter_bank(
        prepared_read,
        build_scale_filter_bank(
            beam,
            family="beam-aware-matched-filter",
            scales=_FROZEN_SCALES,
            truncation_sigma=_FROZEN_FILTER_TRUNCATION_SIGMA,
            noise_correlation=beam,
        ),
        minimum_support_fraction=minimum_support_fraction,
    )
    maximum_filter_evaluation_bytes = (
        prepared_read_bytes
        + prepared_core_bytes
        + matched_read.maximum_workspace_bytes
    )
    matched_core = ScaleFilterBankResult(
        family=matched_read.family,
        responses=tuple(
            _core_response(response, partition)
            for response in matched_read.responses
        ),
        convolution_count=matched_read.convolution_count,
        temporary_plane_count=matched_read.temporary_plane_count,
        maximum_workspace_bytes=matched_read.maximum_workspace_bytes,
    )
    maximum_filter_evaluation_bytes = max(
        maximum_filter_evaluation_bytes,
        prepared_read_bytes
        + prepared_core_bytes
        + _scale_response_array_bytes(matched_read.responses)
        + _scale_response_array_bytes(matched_core.responses),
    )
    del matched_read
    atrous_read = evaluate_residual_atrous(
        prepared_read,
        build_residual_atrous_plan(beam, noise_correlation=beam),
        minimum_support_fraction=minimum_support_fraction,
    )
    matched_core_bytes = _scale_response_array_bytes(matched_core.responses)
    maximum_filter_evaluation_bytes = max(
        maximum_filter_evaluation_bytes,
        prepared_read_bytes
        + prepared_core_bytes
        + matched_core_bytes
        + atrous_read.maximum_workspace_bytes,
    )
    del prepared_read
    atrous_core = ResidualAtrousResult(
        family="residual-b3-atrous",
        responses=tuple(
            _core_response(response, partition)
            for response in atrous_read.responses
        ),
        reconstructed_signal_jy_per_beam=_core_copy(
            atrous_read.reconstructed_signal_jy_per_beam,
            partition,
        ),
        coarse_smoothing_jy_per_beam=_core_copy(
            atrous_read.coarse_smoothing_jy_per_beam,
            partition,
        ),
        scientifically_valid=_core_copy(
            atrous_read.scientifically_valid,
            partition,
        ),
        convolution_count=atrous_read.convolution_count,
        temporary_plane_count=atrous_read.temporary_plane_count,
        maximum_workspace_bytes=atrous_read.maximum_workspace_bytes,
    )
    maximum_filter_evaluation_bytes = max(
        maximum_filter_evaluation_bytes,
        prepared_core_bytes
        + matched_core_bytes
        + _residual_atrous_array_bytes(atrous_read)
        + _residual_atrous_array_bytes(atrous_core),
    )
    return PhaseFiveFilterTileResult(
        partition=partition,
        prepared_inputs=prepared_core,
        matched_filter=matched_core,
        atrous_result=atrous_core,
        read_pixel_count=partition.read_bounds.shape_yx[0]
        * partition.read_bounds.shape_yx[1],
        maximum_filter_evaluation_bytes=maximum_filter_evaluation_bytes,
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
    matched_halos = _scale_filter_halos_pixels(beam)
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
            "segment-association",
            segment_association_halo_pixels(beam),
            maximum_task_pixels,
            "three-beam-residual-reconstruction-association-dilation",
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
