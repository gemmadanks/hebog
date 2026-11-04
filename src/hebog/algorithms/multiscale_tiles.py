"""Reviewed stage halos and bounded multiscale tile evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import ceil
from typing import TypeVar

import numpy as np
import numpy.typing as npt

from hebog.algorithms.multiscale import (
    BeamShapePixels,
    PreparedScaleInputs,
    ResidualAtrousResult,
    ScaleFilterBank,
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
from hebog.config import (
    ResidualMultiscaleDetectionConfig,
)
from hebog.data_models.partitioning import ImageBounds, TilePartition

_FROZEN_SCALES: tuple[tuple[int, float], ...] = (
    (1, 1.0),
    (2, 2.0),
    (3, 4.0),
)
_FROZEN_FILTER_TRUNCATION_SIGMA = 4.0
_FROZEN_SEGMENT_ASSOCIATION_BEAMS = 3.0
_FILTER_BLOCK_PIXELS = 1024
_FILTER_BLOCK_HALOS = 10
# A block holds at least this many halos, so padding stays a modest share of
# its transform. A wider beam's block is the smallest tile core it admits.
_WIDE_BEAM_FILTER_BLOCK_PIXELS = 2048
_HALOS_PER_TILE_CORE = 4
_IMAGE_DIMENSIONS = 2
_ArrayScalar = TypeVar("_ArrayScalar", bound=np.generic)


@dataclass(frozen=True, slots=True)
class MultiscaleFilterTileResult:
    """Core-only multiscale filter evidence from one bounded read.

    Workspace evidence describes the complete read evaluation. Every array in
    the returned scientific records is an owned immutable core plane, so no
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
class MultiscaleDetectionTileEvidence:
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


def _response_planes(
    response: ScaleFilterResponse,
) -> tuple[npt.NDArray[np.generic], ...]:
    """Return the planes one scale's response holds, in one order."""
    return (
        response.response_jy_per_beam,
        response.effective_rms_jy_per_beam,
        response.valid_support_fraction,
        response.scientifically_valid,
    )


def _scale_response_array_bytes(
    responses: tuple[ScaleFilterResponse, ...],
) -> int:
    """Return exact retained payload for aligned scale responses."""
    return sum(
        array.nbytes
        for response in responses
        for array in _response_planes(response)
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
    """Return the widest frozen multiscale filter halo without allocation."""
    return max(
        *_scale_filter_halos_pixels(beam),
        *residual_atrous_scale_halos_pixels(),
    )


def filter_block_pixels(beam: BeamShapePixels) -> int:
    """Return the side of the fixed blocks the matched filter runs on.

    An FFT's rounding depends on its shape, so the filter is evaluated on
    blocks placed from the image origin, never on a tile: a block's padded
    window, and so every bit of its responses, is the same whichever tile
    evaluates it. The size depends on the beam alone. Every tile core the
    composition chooses is a whole number of these blocks, so it evaluates no
    block twice.

    Examples:
        >>> filter_block_pixels(BeamShapePixels(4.0, 4.0, 0.0))
        1024
        >>> filter_block_pixels(BeamShapePixels(30.0, 30.0, 0.0))
        2048
        >>> filter_block_pixels(BeamShapePixels(100.0, 100.0, 0.0))
        2721
    """
    halo = scale_filter_halo_pixels(beam)
    if _FILTER_BLOCK_HALOS * halo <= _FILTER_BLOCK_PIXELS:
        return _FILTER_BLOCK_PIXELS
    return max(_WIDE_BEAM_FILTER_BLOCK_PIXELS, _HALOS_PER_TILE_CORE * halo + 1)


def _axis_block_span(start: int, stop: int, block: int) -> tuple[int, int]:
    """Return the block edges enclosing one half-open axis interval."""
    return start // block * block, -(-stop // block) * block


def _filter_blocks(
    core: ImageBounds,
    image_shape_yx: tuple[int, int],
    block: int,
) -> tuple[ImageBounds, ...]:
    """Return every image-anchored block a core touches, in row-major order."""
    y_start, y_stop = _axis_block_span(core.y_start, core.y_stop, block)
    x_start, x_stop = _axis_block_span(core.x_start, core.x_stop, block)
    return tuple(
        ImageBounds(
            y,
            min(y + block, image_shape_yx[0]),
            x,
            min(x + block, image_shape_yx[1]),
        )
        for y in range(y_start, y_stop, block)
        for x in range(x_start, x_stop, block)
    )


def multiscale_filter_read_bounds(
    core: ImageBounds,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
) -> ImageBounds:
    """Return the window a tile reads to fill one core with filter responses.

    It holds every block the core touches and the widest filter halo around
    them, clipped to the image. For a core made of whole blocks this is the
    core and its halo; any other core reads up to one block more on a side.

    Examples:
        >>> beam = BeamShapePixels(4.0, 4.0, 0.0)
        >>> multiscale_filter_read_bounds(
        ...     ImageBounds(2048, 4096, 0, 2048), (5000, 5000), beam
        ... )
        ImageBounds(y_start=2020, y_stop=4124, x_start=0, x_stop=2076)
        >>> multiscale_filter_read_bounds(
        ...     ImageBounds(1000, 1100, 0, 100), (1500, 5000), beam
        ... )
        ImageBounds(y_start=0, y_stop=1500, x_start=0, x_stop=1052)
    """
    block = filter_block_pixels(beam)
    y_start, y_stop = _axis_block_span(core.y_start, core.y_stop, block)
    x_start, x_stop = _axis_block_span(core.x_start, core.x_stop, block)
    return ImageBounds(
        y_start,
        min(y_stop, image_shape_yx[0]),
        x_start,
        min(x_stop, image_shape_yx[1]),
    ).expanded(scale_filter_halo_pixels(beam), image_shape_yx)


def segment_association_halo_pixels(beam: BeamShapePixels) -> int:
    """Return the frozen residual/reconstruction grouping radius."""
    return ceil(_FROZEN_SEGMENT_ASSOCIATION_BEAMS * beam.major_fwhm_pixels)


def _validate_filter_read(
    partition: TilePartition,
    *,
    image_shape_yx: tuple[int, int],
    required_halo_pixels: int,
    filter_read: ImageBounds,
    read_shape_yx: tuple[int, int],
) -> None:
    """Require the exact clipped halo before allocating filter workspaces."""
    partition.read_bounds.require_inside(image_shape_yx)
    partition.core_bounds.require_inside(image_shape_yx)
    if filter_read.shape_yx != read_shape_yx:
        raise ValueError("filter input arrays must match the filter read")
    expected_read = partition.core_bounds.expanded(
        required_halo_pixels,
        image_shape_yx,
    )
    if partition.read_bounds != expected_read:
        raise ValueError(
            "partition read bounds must provide the exact clipped multiscale "
            "filter halo"
        )


def _crop_slices(
    outer: ImageBounds, inner: ImageBounds
) -> tuple[slice, slice]:
    """Locate one region inside an array read over a region holding it."""
    return (
        slice(inner.y_start - outer.y_start, inner.y_stop - outer.y_start),
        slice(inner.x_start - outer.x_start, inner.x_stop - outer.x_start),
    )


def _cropped_inputs(
    prepared: PreparedScaleInputs,
    outer: ImageBounds,
    inner: ImageBounds,
) -> PreparedScaleInputs:
    """Return views of one region of a prepared read, without a copy."""
    crop = _crop_slices(outer, inner)
    return PreparedScaleInputs(
        residual_jy_per_beam=prepared.residual_jy_per_beam[crop],
        rms_jy_per_beam=prepared.rms_jy_per_beam[crop],
        scientifically_valid=prepared.scientifically_valid[crop],
    )


def _empty_core_responses(
    bank: ScaleFilterBank,
    core_shape_yx: tuple[int, int],
) -> tuple[ScaleFilterResponse, ...]:
    """Allocate one core's response planes for its blocks to fill."""
    return tuple(
        ScaleFilterResponse(
            scale_order=item.scale_order,
            nominal_scale_beam_fwhm=item.nominal_scale_beam_fwhm,
            response_jy_per_beam=np.empty(core_shape_yx, dtype=np.float64),
            effective_rms_jy_per_beam=np.empty(
                core_shape_yx, dtype=np.float64
            ),
            valid_support_fraction=np.empty(core_shape_yx, dtype=np.float64),
            scientifically_valid=np.empty(core_shape_yx, dtype=np.bool_),
        )
        for item in bank.filters
    )


def _fill_core_from_block(  # noqa: PLR0913
    core_responses: tuple[ScaleFilterResponse, ...],
    prepared_read: PreparedScaleInputs,
    *,
    filter_read: ImageBounds,
    core: ImageBounds,
    block: ImageBounds,
    window: ImageBounds,
    bank: ScaleFilterBank,
    minimum_support_fraction: float,
) -> int:
    """Copy what a core owns of one block's responses; return its workspace.

    The block's planes are released on return, before the next block needs its
    own workspace.
    """
    evaluated = evaluate_scale_filter_bank(
        _cropped_inputs(prepared_read, filter_read, window),
        bank,
        minimum_support_fraction=minimum_support_fraction,
    )
    owned = ImageBounds(
        max(block.y_start, core.y_start),
        min(block.y_stop, core.y_stop),
        max(block.x_start, core.x_start),
        min(block.x_stop, core.x_stop),
    )
    target = _crop_slices(core, owned)
    source = _crop_slices(window, owned)
    for core_response, response in zip(
        core_responses, evaluated.responses, strict=True
    ):
        for core_plane, plane in zip(
            _response_planes(core_response),
            _response_planes(response),
            strict=True,
        ):
            core_plane[target] = plane[source]
    return evaluated.maximum_workspace_bytes


def _matched_filter_on_blocks(  # noqa: PLR0913
    prepared_read: PreparedScaleInputs,
    *,
    filter_read: ImageBounds,
    core: ImageBounds,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    minimum_support_fraction: float,
) -> ScaleFilterBankResult:
    """Fill one core with the matched responses of the blocks it touches.

    Each block is evaluated on its own window, whatever the tile, and the core
    keeps the part it owns. Filter arithmetic, including the bank's choices
    from the values in its read, therefore never sees the tile.
    """
    bank = build_scale_filter_bank(
        beam,
        family="beam-aware-matched-filter",
        scales=_FROZEN_SCALES,
        truncation_sigma=_FROZEN_FILTER_TRUNCATION_SIGMA,
        noise_correlation=beam,
    )
    halo = scale_filter_halo_pixels(beam)
    blocks = _filter_blocks(core, image_shape_yx, filter_block_pixels(beam))
    core_responses = _empty_core_responses(bank, core.shape_yx)
    maximum_workspace_bytes = max(
        _fill_core_from_block(
            core_responses,
            prepared_read,
            filter_read=filter_read,
            core=core,
            block=block,
            window=block.expanded(halo, image_shape_yx),
            bank=bank,
            minimum_support_fraction=minimum_support_fraction,
        )
        for block in blocks
    )
    for core_response in core_responses:
        for core_plane in _response_planes(core_response):
            core_plane.setflags(write=False)
    return ScaleFilterBankResult(
        family=bank.family,
        responses=core_responses,
        convolution_count=bank.convolution_count_per_evaluation * len(blocks),
        temporary_plane_count=bank.temporary_plane_count,
        maximum_workspace_bytes=maximum_workspace_bytes,
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


def derive_multiscale_detection_tile_evidence(
    result: MultiscaleFilterTileResult,
    config: ResidualMultiscaleDetectionConfig,
) -> MultiscaleDetectionTileEvidence:
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
    return MultiscaleDetectionTileEvidence(
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


def evaluate_multiscale_filter_tile(
    prepared_read: PreparedScaleInputs,
    *,
    partition: TilePartition,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    minimum_support_fraction: float,
) -> MultiscaleFilterTileResult:
    """Evaluate the promoted filters on one read and return its owned core.

    ``prepared_read`` covers :func:`multiscale_filter_read_bounds` of the core.
    This is the bounded local-neighbourhood seam for multiscale detection.
    Connected support is deliberately not labelled here: callers reconcile core
    labels through the existing bounded edge and corner summaries.
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
    filter_read = multiscale_filter_read_bounds(
        partition.core_bounds, image_shape_yx, beam
    )
    _validate_filter_read(
        partition,
        image_shape_yx=image_shape_yx,
        required_halo_pixels=required_halo,
        filter_read=filter_read,
        read_shape_yx=read_shape_yx,
    )
    # The direct transforms need only the tile's own halo.
    tile_read = _cropped_inputs(
        prepared_read, filter_read, partition.read_bounds
    )
    prepared_core = PreparedScaleInputs(
        residual_jy_per_beam=_core_copy(
            tile_read.residual_jy_per_beam,
            partition,
        ),
        rms_jy_per_beam=_core_copy(
            tile_read.rms_jy_per_beam,
            partition,
        ),
        scientifically_valid=_core_copy(
            tile_read.scientifically_valid,
            partition,
        ),
    )
    prepared_read_bytes = _prepared_array_bytes(prepared_read)
    prepared_core_bytes = _prepared_array_bytes(prepared_core)
    matched_core = _matched_filter_on_blocks(
        prepared_read,
        filter_read=filter_read,
        core=partition.core_bounds,
        image_shape_yx=image_shape_yx,
        beam=beam,
        minimum_support_fraction=minimum_support_fraction,
    )
    matched_core_bytes = _scale_response_array_bytes(matched_core.responses)
    maximum_filter_evaluation_bytes = (
        prepared_read_bytes
        + prepared_core_bytes
        + matched_core_bytes
        + matched_core.maximum_workspace_bytes
    )
    atrous_read = evaluate_residual_atrous(
        tile_read,
        build_residual_atrous_plan(beam, noise_correlation=beam),
        minimum_support_fraction=minimum_support_fraction,
    )
    maximum_filter_evaluation_bytes = max(
        maximum_filter_evaluation_bytes,
        prepared_read_bytes
        + prepared_core_bytes
        + matched_core_bytes
        + atrous_read.maximum_workspace_bytes,
    )
    del prepared_read, tile_read
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
    return MultiscaleFilterTileResult(
        partition=partition,
        prepared_inputs=prepared_core,
        matched_filter=matched_core,
        atrous_result=atrous_core,
        read_pixel_count=read_shape_yx[0] * read_shape_yx[1],
        maximum_filter_evaluation_bytes=maximum_filter_evaluation_bytes,
    )
