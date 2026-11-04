# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""One-tile/many-tile equality for the promoted multiscale science path."""

from __future__ import annotations

import gc
import weakref
from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import pairwise

import numpy as np
import numpy.typing as npt
import pytest
from scipy.ndimage import binary_dilation

from hebog.algorithms import multiscale_tiles
from hebog.algorithms.detection import DetectionThresholdMasks
from hebog.algorithms.extended_measurement import (
    refine_multiscale_segment_labels,
    segment_refinement_halo_pixels,
)
from hebog.algorithms.labelling import label_detection_tile
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    PreparedScaleInputs,
    ResidualAtrousResult,
    ScaleFilterBank,
    ScaleFilterBankResult,
    ScaleFilterResponse,
    detect_residual_multiscale_islands,
    prepare_scale_filter_inputs,
    reconstruct_significant_atrous,
)
from hebog.algorithms.multiscale_tiles import (
    MultiscaleFilterTileResult,
    derive_multiscale_detection_tile_evidence,
    evaluate_multiscale_filter_tile,
    filter_block_pixels,
    multiscale_filter_read_bounds,
    scale_filter_halo_pixels,
    segment_association_halo_pixels,
)
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.reconciliation import (
    DetectedIsland,
    apply_reconciled_labels,
    reconcile_candidate_tiles,
)
from hebog.config import ResidualMultiscaleDetectionConfig
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)

_DETECTION_SIGMA = 5.0
_ISLAND_SIGMA = 3.0
_SUPPORT_FRACTION = 0.5


@dataclass(frozen=True, slots=True)
class _AssembledFilterEvidence:
    """Complete small-image serial oracle assembled from bounded cores."""

    prepared: PreparedScaleInputs
    matched: ScaleFilterBankResult
    atrous: ResidualAtrousResult
    position_signal_jy_per_beam: npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class _PartitionedScienceResult:
    """Comparable scientific outputs after bounded topology reconciliation."""

    evidence: _AssembledFilterEvidence
    reconstruction_islands: tuple[DetectedIsland, ...]
    detection_islands: tuple[DetectedIsland, ...]
    association_islands: tuple[DetectedIsland, ...]
    retained_mask: npt.NDArray[np.bool_]
    component_labels: npt.NDArray[np.int64]
    refined_labels: npt.NDArray[np.int32]
    combined_snr: npt.NDArray[np.float64]


def _beam() -> BeamShapePixels:
    """Return a beam whose four-beam filter needs a 21-pixel halo."""
    return BeamShapePixels(3.0, 2.5, 27.0)


def _config() -> ResidualMultiscaleDetectionConfig:
    """Return the promoted residual-B3 detection policy."""
    return ResidualMultiscaleDetectionConfig(
        detection_threshold_sigma=_DETECTION_SIGMA,
        island_threshold_sigma=_ISLAND_SIGMA,
        minimum_scale_support_fraction=_SUPPORT_FRACTION,
        minimum_island_area_beams=1.0,
    )


def _analytic_planes() -> tuple[
    np.ndarray, np.ndarray, np.ndarray, np.ndarray
]:
    """Build edge, corner, shifted-corner, invalid, and four-beam evidence."""
    shape = (193, 211)
    y_grid, x_grid = np.indices(shape, dtype=np.float64)
    image = np.zeros(shape, dtype=np.float64)
    four_beam_sigma = 4.0 * _beam().major_fwhm_pixels / 2.354820045
    for centre_yx, amplitude in (
        ((88.0, 96.0), 24.0),
        ((43.0, 47.0), 20.0),
        ((2.0, 170.0), 22.0),
        ((190.0, 208.0), 26.0),
        ((140.0, 70.0), 18.0),
    ):
        image += amplitude * np.exp(
            -0.5
            * (
                np.square((y_grid - centre_yx[0]) / four_beam_sigma)
                + np.square((x_grid - centre_yx[1]) / four_beam_sigma)
            )
        )
    background = np.zeros(shape, dtype=np.float64)
    rms = np.ones(shape, dtype=np.float64)
    valid = np.ones(shape, dtype=np.bool_)
    valid[136:146, 74:78] = False
    valid[86:91, 101:104] = False
    return image, valid, background, rms


def _global_selection(bounds: ImageBounds) -> tuple[slice, slice]:
    """Return global NumPy slices for one half-open bound."""
    return (
        slice(bounds.y_start, bounds.y_stop),
        slice(bounds.x_start, bounds.x_stop),
    )


def _read_plane(values: np.ndarray, bounds: ImageBounds) -> np.ndarray:
    """Read one bounded in-memory window without copying its source plane."""
    return np.asarray(values[_global_selection(bounds)])


def _freeze(values: np.ndarray) -> np.ndarray:
    """Return one immutable assembled plane."""
    values.setflags(write=False)
    return values


def _assemble_response(
    results: tuple[MultiscaleFilterTileResult, ...],
    manifest: PartitionManifest,
    *,
    response_index: int,
    family: str,
) -> ScaleFilterResponse:
    """Assemble one response from non-overlapping core-only records."""
    first_result = (
        results[0].matched_filter
        if family == "matched"
        else results[0].atrous_result
    )
    template = first_result.responses[response_index]
    shape = manifest.image_shape_yx
    response = np.empty(shape, dtype=np.float64)
    rms = np.empty(shape, dtype=np.float64)
    support = np.empty(shape, dtype=np.float64)
    valid = np.empty(shape, dtype=np.bool_)
    for result in results:
        source = (
            result.matched_filter
            if family == "matched"
            else result.atrous_result
        ).responses[response_index]
        selection = _global_selection(result.partition.core_bounds)
        response[selection] = source.response_jy_per_beam
        rms[selection] = source.effective_rms_jy_per_beam
        support[selection] = source.valid_support_fraction
        valid[selection] = source.scientifically_valid
    return ScaleFilterResponse(
        scale_order=template.scale_order,
        nominal_scale_beam_fwhm=template.nominal_scale_beam_fwhm,
        response_jy_per_beam=_freeze(response),
        effective_rms_jy_per_beam=_freeze(rms),
        valid_support_fraction=_freeze(support),
        scientifically_valid=_freeze(valid),
    )


def _assemble_filter_evidence(
    results: tuple[MultiscaleFilterTileResult, ...],
    manifest: PartitionManifest,
) -> _AssembledFilterEvidence:
    """Assemble bounded cores only for this small deterministic test oracle."""
    shape = manifest.image_shape_yx
    residual = np.empty(shape, dtype=np.float64)
    rms = np.empty(shape, dtype=np.float64)
    scientifically_valid = np.empty(shape, dtype=np.bool_)
    reconstructed = np.empty(shape, dtype=np.float64)
    coarse = np.empty(shape, dtype=np.float64)
    atrous_valid = np.empty(shape, dtype=np.bool_)
    for result in results:
        selection = _global_selection(result.partition.core_bounds)
        residual[selection] = result.prepared_inputs.residual_jy_per_beam
        rms[selection] = result.prepared_inputs.rms_jy_per_beam
        scientifically_valid[selection] = (
            result.prepared_inputs.scientifically_valid
        )
        reconstructed[selection] = (
            result.atrous_result.reconstructed_signal_jy_per_beam
        )
        coarse[selection] = result.atrous_result.coarse_smoothing_jy_per_beam
        atrous_valid[selection] = result.atrous_result.scientifically_valid
    prepared = PreparedScaleInputs(
        residual_jy_per_beam=_freeze(residual),
        rms_jy_per_beam=_freeze(rms),
        scientifically_valid=_freeze(scientifically_valid),
    )
    matched_responses = tuple(
        _assemble_response(
            results,
            manifest,
            response_index=index,
            family="matched",
        )
        for index in range(len(results[0].matched_filter.responses))
    )
    atrous_responses = tuple(
        _assemble_response(
            results,
            manifest,
            response_index=index,
            family="atrous",
        )
        for index in range(len(results[0].atrous_result.responses))
    )
    matched = ScaleFilterBankResult(
        family="beam-aware-matched-filter",
        responses=matched_responses,
        convolution_count=results[0].matched_filter.convolution_count,
        temporary_plane_count=results[0].matched_filter.temporary_plane_count,
        maximum_workspace_bytes=max(
            result.matched_filter.maximum_workspace_bytes for result in results
        ),
    )
    atrous = ResidualAtrousResult(
        family="residual-b3-atrous",
        responses=atrous_responses,
        reconstructed_signal_jy_per_beam=_freeze(reconstructed),
        coarse_smoothing_jy_per_beam=_freeze(coarse),
        scientifically_valid=_freeze(atrous_valid),
        convolution_count=results[0].atrous_result.convolution_count,
        temporary_plane_count=results[0].atrous_result.temporary_plane_count,
        maximum_workspace_bytes=max(
            result.atrous_result.maximum_workspace_bytes for result in results
        ),
    )
    position_signal = np.asarray(
        prepared.residual_jy_per_beam
        + atrous.reconstructed_signal_jy_per_beam,
        dtype=np.float64,
    )
    return _AssembledFilterEvidence(
        prepared=prepared,
        matched=matched,
        atrous=atrous,
        position_signal_jy_per_beam=_freeze(position_signal),
    )


def _filter_evidence(manifest: PartitionManifest) -> _AssembledFilterEvidence:
    """Evaluate every canonical read halo and retain only its owned core."""
    results = tuple(
        _evaluate_filter_tile(tile, manifest) for tile in manifest.tiles
    )
    return _assemble_filter_evidence(results, manifest)


def _prepared_filter_read(  # noqa: PLR0913, PLR0917
    image: np.ndarray,
    valid: np.ndarray,
    background: np.ndarray,
    rms: np.ndarray,
    tile: TilePartition,
    beam: BeamShapePixels,
) -> PreparedScaleInputs:
    """Prepare the window one tile's filters read from whole planes."""
    bounds = multiscale_filter_read_bounds(tile.core_bounds, image.shape, beam)
    return prepare_scale_filter_inputs(
        _read_plane(image, bounds),
        _read_plane(valid, bounds),
        _read_plane(background, bounds),
        _read_plane(rms, bounds),
    )


def _evaluate_filter_tile(
    tile: TilePartition,
    manifest: PartitionManifest,
) -> MultiscaleFilterTileResult:
    """Prepare and evaluate one bounded analytic read."""
    image, valid, background, rms = _analytic_planes()
    return evaluate_multiscale_filter_tile(
        _prepared_filter_read(image, valid, background, rms, tile, _beam()),
        partition=tile,
        image_shape_yx=manifest.image_shape_yx,
        beam=_beam(),
        minimum_support_fraction=_SUPPORT_FRACTION,
    )


def _maximum_scale_snr(atrous: ResidualAtrousResult) -> np.ndarray:
    """Return the exact maximum calibrated scale-SNR plane."""
    maximum = np.full(
        atrous.responses[0].response_jy_per_beam.shape,
        -np.inf,
        dtype=np.float64,
    )
    for response in atrous.responses:
        scale_snr = np.full(maximum.shape, -np.inf, dtype=np.float64)
        validity = (
            response.scientifically_valid
            & (response.valid_support_fraction >= _SUPPORT_FRACTION)
            & np.isfinite(response.response_jy_per_beam)
            & np.isfinite(response.effective_rms_jy_per_beam)
            & (response.effective_rms_jy_per_beam > 0)
        )
        np.divide(
            response.response_jy_per_beam,
            response.effective_rms_jy_per_beam,
            out=scale_snr,
            where=validity,
        )
        np.maximum(maximum, scale_snr, out=maximum)
    return maximum


def _reconcile_labels(
    manifest: PartitionManifest,
    membership: np.ndarray,
    seeds: np.ndarray,
    normalized: np.ndarray,
) -> tuple[tuple[DetectedIsland, ...], np.ndarray]:
    """Label cores and reconcile eight-connected sides and corners."""
    tiles = tuple(
        label_detection_tile(
            DetectionThresholdMasks(
                normalized_residual=_read_plane(
                    normalized,
                    partition.core_bounds,
                ),
                island_membership=_read_plane(
                    membership,
                    partition.core_bounds,
                ),
                detection_seeds=_read_plane(
                    seeds & membership,
                    partition.core_bounds,
                ),
                valid_pixel_count=int(
                    np.count_nonzero(
                        _read_plane(membership, partition.core_bounds)
                    )
                ),
            ),
            partition,
            image_shape_yx=manifest.image_shape_yx,
        )
        for partition in manifest.tiles
    )
    reconciliation = reconcile_candidate_tiles(
        manifest,
        tuple(tile.compact_summary() for tile in tiles),
    )
    labels = np.zeros(manifest.image_shape_yx, dtype=np.int64)
    for tile in tiles:
        labels[_global_selection(tile.partition.core_bounds)] = (
            apply_reconciled_labels(tile, reconciliation)
        )
    return reconciliation.islands, labels


def _tile_dilation(
    values: np.ndarray,
    manifest: PartitionManifest,
    *,
    radius_pixels: int,
) -> np.ndarray:
    """Apply a finite dilation on clipped reads and retain owned cores."""
    result = np.zeros(values.shape, dtype=np.bool_)
    for partition in manifest.tiles:
        read_bounds = partition.core_bounds.expanded(
            radius_pixels,
            manifest.image_shape_yx,
        )
        dilated = binary_dilation(
            _read_plane(values, read_bounds),
            iterations=radius_pixels,
        )
        core_selection = (
            slice(
                partition.core_bounds.y_start - read_bounds.y_start,
                partition.core_bounds.y_stop - read_bounds.y_start,
            ),
            slice(
                partition.core_bounds.x_start - read_bounds.x_start,
                partition.core_bounds.x_stop - read_bounds.x_start,
            ),
        )
        result[_global_selection(partition.core_bounds)] = dilated[
            core_selection
        ]
    return result


def _tile_refinement(
    labels: np.ndarray,
    combined_snr: np.ndarray,
    multiscale_support: np.ndarray,
    manifest: PartitionManifest,
) -> np.ndarray:
    """Refine bounded halo reads and retain only deterministic cores."""
    result = np.zeros(labels.shape, dtype=np.int32)
    radius = segment_refinement_halo_pixels(_beam().major_fwhm_pixels)
    for partition in manifest.tiles:
        read_bounds = partition.core_bounds.expanded(
            radius,
            manifest.image_shape_yx,
        )
        refined = refine_multiscale_segment_labels(
            _read_plane(labels, read_bounds),
            _read_plane(combined_snr, read_bounds),
            _read_plane(multiscale_support, read_bounds),
            beam_major_fwhm_pixels=_beam().major_fwhm_pixels,
        )
        core_selection = (
            slice(
                partition.core_bounds.y_start - read_bounds.y_start,
                partition.core_bounds.y_stop - read_bounds.y_start,
            ),
            slice(
                partition.core_bounds.x_start - read_bounds.x_start,
                partition.core_bounds.x_stop - read_bounds.x_start,
            ),
        )
        result[_global_selection(partition.core_bounds)] = refined[
            core_selection
        ]
    return result


def _evaluate_partitioned(
    manifest: PartitionManifest,
) -> _PartitionedScienceResult:
    """Evaluate local-neighbourhood work and reconcile global topology."""
    evidence = _filter_evidence(manifest)
    reconstruction = reconstruct_significant_atrous(
        evidence.atrous,
        detection_sigma=_DETECTION_SIGMA,
        island_sigma=_ISLAND_SIGMA,
        minimum_support_fraction=_SUPPORT_FRACTION,
    )
    adjacent_support = np.logical_or.reduce(
        tuple(
            current & following
            for current, following in pairwise(
                reconstruction.significant_scale_masks
            )
        )
    )
    scale_snr = _maximum_scale_snr(evidence.atrous)
    reconstruction_islands, reconstruction_labels = _reconcile_labels(
        manifest,
        adjacent_support,
        scale_snr >= _DETECTION_SIGMA,
        scale_snr,
    )
    np.testing.assert_array_equal(
        reconstruction_labels > 0,
        reconstruction.support_mask,
    )
    detection = detect_residual_multiscale_islands(
        evidence.prepared,
        evidence.matched,
        evidence.atrous,
        _beam(),
        _config(),
    )
    direct_snr = np.full(manifest.image_shape_yx, -np.inf, dtype=np.float64)
    np.divide(
        evidence.prepared.residual_jy_per_beam,
        evidence.prepared.rms_jy_per_beam,
        out=direct_snr,
        where=evidence.prepared.scientifically_valid,
    )
    detection_islands, raw_labels = _reconcile_labels(
        manifest,
        evidence.prepared.scientifically_valid & (direct_snr >= _ISLAND_SIGMA),
        detection.combined_snr >= _DETECTION_SIGMA,
        direct_snr,
    )
    accepted_labels = tuple(
        island.global_label
        for island in detection_islands
        if island.pixel_count >= detection.minimum_island_pixels
        or island.peak_signal_to_noise >= _DETECTION_SIGMA
    )
    retained_mask = np.isin(raw_labels, accepted_labels)
    np.testing.assert_array_equal(retained_mask, detection.retained_mask)
    association_radius = segment_association_halo_pixels(_beam())
    association_support = _tile_dilation(
        retained_mask | reconstruction.support_mask,
        manifest,
        radius_pixels=association_radius,
    )
    association_islands, association_labels = _reconcile_labels(
        manifest,
        association_support,
        association_support,
        detection.combined_snr,
    )
    component_labels = np.where(
        retained_mask,
        association_labels,
        0,
    ).astype(np.int64, copy=False)
    refined = _tile_refinement(
        component_labels,
        detection.combined_snr,
        reconstruction.support_mask,
        manifest,
    )
    return _PartitionedScienceResult(
        evidence=evidence,
        reconstruction_islands=reconstruction_islands,
        detection_islands=detection_islands,
        association_islands=association_islands,
        retained_mask=np.asarray(refined > 0, dtype=np.bool_),
        component_labels=component_labels,
        refined_labels=refined,
        combined_snr=detection.combined_snr,
    )


def _manifest(
    *,
    core_yx: tuple[int, int],
    origin_yx: tuple[int, int] = (0, 0),
) -> PartitionManifest:
    """Return one filter-stage manifest with the exact widest halo."""
    halo = scale_filter_halo_pixels(_beam())
    return plan_image_partitions(
        image_shape_yx=_analytic_planes()[0].shape,
        tile_core_shape_yx=core_yx,
        halo_yx=(halo, halo),
        partition_origin_yx=origin_yx,
    )


def _assert_islands_equal(
    candidate: tuple[DetectedIsland, ...],
    reference: tuple[DetectedIsland, ...],
) -> None:
    """Compare exact topology and peak values."""
    assert len(candidate) == len(reference)
    for candidate_island, reference_island in zip(
        candidate,
        reference,
        strict=True,
    ):
        assert candidate_island.island_id == reference_island.island_id
        assert candidate_island.global_label == reference_island.global_label
        assert candidate_island.pixel_count == reference_island.pixel_count
        assert candidate_island.bounds == reference_island.bounds
        assert (
            candidate_island.peak_position_yx
            == reference_island.peak_position_yx
        )
        assert (
            candidate_island.first_pixel_yx == reference_island.first_pixel_yx
        )
        assert (
            candidate_island.touches_image_edge
            == reference_island.touches_image_edge
        )
        np.testing.assert_array_equal(
            candidate_island.peak_signal_to_noise,
            reference_island.peak_signal_to_noise,
        )


def _assert_responses_equal(
    candidate: tuple[ScaleFilterResponse, ...],
    reference: tuple[ScaleFilterResponse, ...],
) -> None:
    """Compare complete calibrated response records across tilings."""
    for candidate_response, reference_response in zip(
        candidate,
        reference,
        strict=True,
    ):
        assert candidate_response.scale_order == reference_response.scale_order
        assert (
            candidate_response.nominal_scale_beam_fwhm
            == reference_response.nominal_scale_beam_fwhm
        )
        for candidate_values, reference_values in (
            (
                candidate_response.response_jy_per_beam,
                reference_response.response_jy_per_beam,
            ),
            (
                candidate_response.effective_rms_jy_per_beam,
                reference_response.effective_rms_jy_per_beam,
            ),
            (
                candidate_response.valid_support_fraction,
                reference_response.valid_support_fraction,
            ),
        ):
            np.testing.assert_array_equal(
                candidate_values,
                reference_values,
            )
        np.testing.assert_array_equal(
            candidate_response.scientifically_valid,
            reference_response.scientifically_valid,
        )


def test_filter_tile_returns_owned_immutable_core_evidence() -> None:
    """No returned scientific plane retains one halo-read allocation."""
    manifest = _manifest(core_yx=(88, 96))
    tile = manifest.tiles[0]

    result = _evaluate_filter_tile(tile, manifest)

    assert result.read_pixel_count == np.prod(
        multiscale_filter_read_bounds(
            tile.core_bounds, manifest.image_shape_yx, _beam()
        ).shape_yx
    )
    arrays = (
        result.prepared_inputs.residual_jy_per_beam,
        result.prepared_inputs.rms_jy_per_beam,
        result.prepared_inputs.scientifically_valid,
        result.atrous_result.reconstructed_signal_jy_per_beam,
        result.atrous_result.coarse_smoothing_jy_per_beam,
        result.atrous_result.scientifically_valid,
        *(
            response.response_jy_per_beam
            for response in result.matched_filter.responses
        ),
        *(
            response.response_jy_per_beam
            for response in result.atrous_result.responses
        ),
    )
    assert all(array.shape == tile.core_bounds.shape_yx for array in arrays)
    assert all(not array.flags.writeable for array in arrays)
    assert all(array.base is None for array in arrays)
    assert result.retained_array_bytes == 184 * np.prod(
        tile.core_bounds.shape_yx
    )
    assert result.maximum_filter_evaluation_bytes >= (
        result.retained_array_bytes
    )

    evidence = derive_multiscale_detection_tile_evidence(result, _config())
    evidence_arrays = (
        evidence.direct_snr,
        evidence.matched_maximum_snr,
        evidence.atrous_maximum_snr,
        *evidence.atrous_scale_snrs,
        *evidence.significant_scale_masks,
        evidence.reconstruction_membership,
        evidence.reconstruction_seeds,
        evidence.detection_membership,
        evidence.detection_seeds,
    )
    assert all(not array.flags.writeable for array in evidence_arrays)
    assert evidence.retained_array_bytes == 55 * np.prod(
        tile.core_bounds.shape_yx
    )


def test_reviewed_1024_core_records_exact_filter_memory_evidence() -> None:
    """The five-pixel beam profile stays below one bounded worker budget."""
    beam = BeamShapePixels(5.0, 4.0, 13.0)
    manifest = plan_image_partitions(
        image_shape_yx=(3072, 3072),
        tile_core_shape_yx=(1024, 1024),
        halo_yx=(34, 34),
    )
    tile = manifest.tiles[4]
    shape = tile.read_bounds.shape_yx
    zeros = np.zeros(shape, dtype=np.float64)
    prepared = prepare_scale_filter_inputs(
        zeros,
        np.ones(shape, dtype=np.bool_),
        zeros,
        np.ones(shape, dtype=np.float64),
    )

    result = evaluate_multiscale_filter_tile(
        prepared,
        partition=tile,
        image_shape_yx=manifest.image_shape_yx,
        beam=beam,
        minimum_support_fraction=_SUPPORT_FRACTION,
    )
    evidence = derive_multiscale_detection_tile_evidence(result, _config())

    assert tile.read_bounds.shape_yx == (1092, 1092)
    assert result.read_pixel_count == 1_192_464
    assert result.retained_array_bytes == 192_937_984
    assert evidence.retained_array_bytes == 57_671_680
    assert result.matched_filter.maximum_workspace_bytes == 181_356_080
    assert result.atrous_result.maximum_workspace_bytes == 209_881_984
    assert result.maximum_filter_evaluation_bytes == 326_622_864


def test_filter_tile_rejects_incomplete_interior_halo() -> None:
    """A caller cannot evaluate science from an undersized halo read."""
    manifest = _manifest(core_yx=(88, 96))
    tile = manifest.tiles[0]
    shortened = TilePartition(
        tile_y_index=tile.tile_y_index,
        tile_x_index=tile.tile_x_index,
        core_bounds=tile.core_bounds,
        read_bounds=ImageBounds(
            tile.read_bounds.y_start,
            tile.read_bounds.y_stop - 1,
            tile.read_bounds.x_start,
            tile.read_bounds.x_stop,
        ),
    )

    with pytest.raises(
        ValueError, match="exact clipped multiscale filter halo"
    ):
        _evaluate_filter_tile(shortened, manifest)


def test_filter_tile_rejects_inconsistent_prepared_shapes() -> None:
    """Malformed prepared records fail before any filter allocation."""
    manifest = _manifest(core_yx=(88, 96))
    tile = manifest.tiles[0]
    image, valid, background, rms = _analytic_planes()
    prepared = prepare_scale_filter_inputs(
        _read_plane(image, tile.read_bounds),
        _read_plane(valid, tile.read_bounds),
        _read_plane(background, tile.read_bounds),
        _read_plane(rms, tile.read_bounds),
    )

    with pytest.raises(ValueError, match="prepared filter-read arrays"):
        evaluate_multiscale_filter_tile(
            replace(
                prepared,
                rms_jy_per_beam=prepared.rms_jy_per_beam[:-1],
            ),
            partition=tile,
            image_shape_yx=manifest.image_shape_yx,
            beam=_beam(),
            minimum_support_fraction=_SUPPORT_FRACTION,
        )


def test_filter_tile_rejects_read_shape_outside_the_filter_read() -> None:
    """A self-consistent input still has to cover the declared filter read."""
    manifest = _manifest(core_yx=(88, 96))
    tile = manifest.tiles[0]
    image, valid, background, rms = _analytic_planes()
    prepared = prepare_scale_filter_inputs(
        image[:-1],
        valid[:-1],
        background[:-1],
        rms[:-1],
    )

    with pytest.raises(ValueError, match="match the filter read"):
        evaluate_multiscale_filter_tile(
            prepared,
            partition=tile,
            image_shape_yx=manifest.image_shape_yx,
            beam=_beam(),
            minimum_support_fraction=_SUPPORT_FRACTION,
        )


def _quiet_patch_planes() -> tuple[
    np.ndarray, np.ndarray, np.ndarray, np.ndarray
]:
    """Add noise, and a quiet patch that turns one read's filter spatial.

    The bank chooses spatial convolution from the smallest and largest values
    in its read, so a tile holding this patch must not change its arithmetic
    for any block but the patch's own.
    """
    image, valid, background, rms = _analytic_planes()
    image = image + np.random.default_rng(193).normal(0.0, 1.0, image.shape)
    rms = rms.copy()
    rms[60:66, 150:156] = 1e-12
    image[~valid] = np.nan
    return image, valid, background, rms


def _noisy_planes() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Add noise to the analytic planes, so no response is trivially zero."""
    image, valid, background, rms = _analytic_planes()
    image = image + np.random.default_rng(211).normal(0.0, 1.0, image.shape)
    image[~valid] = np.nan
    return image, valid, background, rms


def _use_filter_blocks_of(
    pixels: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Give the kernel another block size, to cross blocks on a small image."""

    def block_pixels(_: BeamShapePixels) -> int:
        return pixels

    monkeypatch.setattr(multiscale_tiles, "filter_block_pixels", block_pixels)


def _core_filter_responses(
    planes: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    manifest: PartitionManifest,
) -> tuple[ScaleFilterResponse, ...]:
    """Return each scale's whole image responses, assembled from every core."""
    results = tuple(
        evaluate_multiscale_filter_tile(
            _prepared_filter_read(*planes, tile, _beam()),
            partition=tile,
            image_shape_yx=manifest.image_shape_yx,
            beam=_beam(),
            minimum_support_fraction=_SUPPORT_FRACTION,
        )
        for tile in manifest.tiles
    )
    return _assemble_filter_evidence(results, manifest).matched.responses


@pytest.mark.parametrize(
    "planes",
    [_noisy_planes, _quiet_patch_planes],
    ids=["noisy", "quiet-patch"],
)
@pytest.mark.parametrize(
    ("core_yx", "origin_yx"),
    [
        pytest.param((128, 128), (0, 0), id="whole-blocks"),
        pytest.param((88, 96), (0, 0), id="off-the-block-grid"),
        pytest.param((88, 96), (43, 47), id="shifted-origin"),
        pytest.param((86, 130), (63, 1), id="seams-beside-block-edges"),
        pytest.param((90, 87), (65, 64), id="seams-beyond-block-edges"),
    ],
)
def test_filter_responses_are_bitwise_equal_across_tile_grids(
    monkeypatch: pytest.MonkeyPatch,
    planes: Callable[
        [], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
    ],
    core_yx: tuple[int, int],
    origin_yx: tuple[int, int],
) -> None:
    """No tile grid changes a bit of any response, at any edge or corner.

    Small blocks make a small image cross many of them: blocks here cross
    tile edges and corners, invalid pixels and the image's edges. The stage
    test holds the real block size.
    """
    _use_filter_blocks_of(64, monkeypatch)
    reference = _core_filter_responses(planes(), _manifest(core_yx=(193, 211)))

    responses = _core_filter_responses(
        planes(), _manifest(core_yx=core_yx, origin_yx=origin_yx)
    )

    for response, expected in zip(responses, reference, strict=True):
        np.testing.assert_array_equal(
            response.response_jy_per_beam, expected.response_jy_per_beam
        )
        np.testing.assert_array_equal(
            response.effective_rms_jy_per_beam,
            expected.effective_rms_jy_per_beam,
        )
        np.testing.assert_array_equal(
            response.valid_support_fraction, expected.valid_support_fraction
        )
        np.testing.assert_array_equal(
            response.scientifically_valid, expected.scientifically_valid
        )


def test_a_core_across_blocks_holds_one_block_at_a_time_and_counts_them_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each block's planes go before the next, and its cost is reported."""
    _use_filter_blocks_of(64, monkeypatch)
    evaluate = multiscale_tiles.evaluate_scale_filter_bank
    previous: list[weakref.ref[np.ndarray]] = []
    held_across_blocks: list[bool] = []

    def evaluate_recording_release(
        prepared: PreparedScaleInputs,
        bank: ScaleFilterBank,
        *,
        minimum_support_fraction: float,
    ) -> ScaleFilterBankResult:
        gc.collect()
        held_across_blocks.extend(plane() is not None for plane in previous)
        previous.clear()
        result = evaluate(
            prepared,
            bank,
            minimum_support_fraction=minimum_support_fraction,
        )
        previous.append(weakref.ref(result.responses[0].response_jy_per_beam))
        return result

    monkeypatch.setattr(
        multiscale_tiles,
        "evaluate_scale_filter_bank",
        evaluate_recording_release,
    )
    manifest = _manifest(core_yx=(88, 96), origin_yx=(43, 47))
    tile = next(
        item
        for item in manifest.tiles
        if item.core_bounds == ImageBounds(43, 131, 47, 143)
    )

    result = _evaluate_filter_tile(tile, manifest)

    # The core reaches rows 43 to 130 and columns 47 to 142: three blocks by
    # three, nine evaluations of the bank's nine convolutions.
    assert held_across_blocks == [False] * 8
    assert result.matched_filter.convolution_count == 81


def test_a_quiet_patch_changes_the_arithmetic_of_its_own_block_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A block's arithmetic comes from its own window, not the tile's read.

    One block over the whole image takes the patch's spatial arithmetic
    everywhere, so far from the patch its bits differ from those of a small
    block that holds no quiet pixel. This also proves the patch has an effect.
    """
    planes = _quiet_patch_planes()
    _use_filter_blocks_of(64, monkeypatch)
    blocks = _core_filter_responses(planes, _manifest(core_yx=(193, 211)))
    _use_filter_blocks_of(1024, monkeypatch)
    whole = _core_filter_responses(planes, _manifest(core_yx=(193, 211)))

    far_from_the_patch = (slice(128, 193), slice(0, 64))
    assert not np.array_equal(
        blocks[0].response_jy_per_beam[far_from_the_patch],
        whole[0].response_jy_per_beam[far_from_the_patch],
        equal_nan=True,
    )


@pytest.mark.parametrize(
    ("fwhm_pixels", "halo", "block"),
    [
        (4.0, 28, 1024),
        (15.0, 102, 1024),
        (15.1, 103, 2048),
        (30.0, 204, 2048),
        (100.0, 680, 2721),
    ],
)
def test_filter_blocks_hold_ten_halos_or_the_smallest_core_of_the_beam(
    fwhm_pixels: float, halo: int, block: int
) -> None:
    """Block size follows the beam alone, and tiles can be made of blocks."""
    beam = BeamShapePixels(fwhm_pixels, fwhm_pixels, 0.0)

    assert scale_filter_halo_pixels(beam) == halo
    assert filter_block_pixels(beam) == block


@pytest.mark.parametrize(
    ("fwhm_pixels", "core"),
    [(4.0, 2048), (4.0, 1024), (30.0, 2048), (100.0, 2721)],
)
def test_a_core_of_whole_blocks_reads_only_its_tile_and_halo(
    fwhm_pixels: float, core: int
) -> None:
    """The cores production runs on read no more than a tile's halo read."""
    beam = BeamShapePixels(fwhm_pixels, fwhm_pixels, 0.0)
    halo = scale_filter_halo_pixels(beam)
    manifest = plan_image_partitions(
        image_shape_yx=(5000, 6000),
        tile_core_shape_yx=(core, core),
        halo_yx=(halo, halo),
    )

    for tile in manifest.tiles:
        assert (
            multiscale_filter_read_bounds(
                tile.core_bounds, manifest.image_shape_yx, beam
            )
            == tile.read_bounds
        )


def test_a_core_off_the_block_grid_reads_every_block_it_touches() -> None:
    """It holds whole blocks and their halo, and stops at the image."""
    beam = BeamShapePixels(4.0, 4.0, 0.0)

    read = multiscale_filter_read_bounds(
        ImageBounds(1000, 1030, 2100, 2200), (1100, 5000), beam
    )

    assert read == ImageBounds(0, 1100, 2048 - 28, 3072 + 28)


def test_detection_tile_evidence_rejects_misaligned_scale_response() -> None:
    """Local detection fields require every calibrated core to align."""
    manifest = _manifest(core_yx=(88, 96))
    result = _evaluate_filter_tile(manifest.tiles[0], manifest)
    first = result.matched_filter.responses[0]
    malformed = replace(
        result,
        matched_filter=replace(
            result.matched_filter,
            responses=(
                replace(
                    first,
                    effective_rms_jy_per_beam=(
                        first.effective_rms_jy_per_beam[:-1]
                    ),
                ),
                *result.matched_filter.responses[1:],
            ),
        ),
    )

    with pytest.raises(ValueError, match="same shape"):
        derive_multiscale_detection_tile_evidence(malformed, _config())


def test_multiscale_science_is_one_tile_many_tile_equal() -> None:
    """All reviewed boundary and scale cases agree across partitions."""
    one = _evaluate_partitioned(_manifest(core_yx=(193, 211)))
    many = tuple(
        _evaluate_partitioned(_manifest(core_yx=(88, 96), origin_yx=origin))
        for origin in ((0, 0), (43, 47))
    )

    for candidate in many:
        _assert_islands_equal(
            candidate.reconstruction_islands,
            one.reconstruction_islands,
        )
        _assert_islands_equal(
            candidate.detection_islands,
            one.detection_islands,
        )
        _assert_islands_equal(
            candidate.association_islands,
            one.association_islands,
        )
        np.testing.assert_array_equal(
            candidate.retained_mask,
            one.retained_mask,
        )
        np.testing.assert_array_equal(
            candidate.component_labels,
            one.component_labels,
        )
        np.testing.assert_array_equal(
            candidate.refined_labels,
            one.refined_labels,
        )
        np.testing.assert_array_equal(
            candidate.combined_snr,
            one.combined_snr,
        )
        np.testing.assert_array_equal(
            candidate.evidence.position_signal_jy_per_beam,
            one.evidence.position_signal_jy_per_beam,
        )
        _assert_responses_equal(
            candidate.evidence.matched.responses,
            one.evidence.matched.responses,
        )
        _assert_responses_equal(
            candidate.evidence.atrous.responses,
            one.evidence.atrous.responses,
        )
        for candidate_values, one_values in (
            (
                candidate.evidence.atrous.reconstructed_signal_jy_per_beam,
                one.evidence.atrous.reconstructed_signal_jy_per_beam,
            ),
            (
                candidate.evidence.atrous.coarse_smoothing_jy_per_beam,
                one.evidence.atrous.coarse_smoothing_jy_per_beam,
            ),
        ):
            np.testing.assert_array_equal(
                candidate_values,
                one_values,
            )
        np.testing.assert_array_equal(
            candidate.evidence.atrous.scientifically_valid,
            one.evidence.atrous.scientifically_valid,
        )

    assert one.refined_labels[88, 96] > 0
    assert one.refined_labels[88, 96] == one.refined_labels[87, 95]
    assert one.refined_labels[43, 47] > 0
    assert one.refined_labels[43, 47] == one.refined_labels[42, 46]
    assert np.any(one.retained_mask[0, :])
    assert np.any(one.retained_mask[-1, :])
    assert not np.any(one.retained_mask[136:146, 74:78])
