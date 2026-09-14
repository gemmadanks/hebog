"""Bounded Phase 5 multiscale execution and atomic product publication."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from numbers import Integral
from typing import Protocol

import numpy as np
import numpy.typing as npt

from hebog.algorithms.detection import DetectionThresholdMasks
from hebog.algorithms.labelling import (
    LocalIslandTile,
    LocalIslandTileSummary,
    label_detection_tile,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    minimum_residual_island_pixels,
    prepare_scale_filter_inputs,
)
from hebog.algorithms.phase_five_execution import (
    PhaseFiveDetectionTileEvidence,
    PhaseFiveFilterTileResult,
    derive_phase_five_detection_tile_evidence,
    evaluate_phase_five_filter_tile,
    scale_filter_halo_pixels,
)
from hebog.algorithms.reconciliation import (
    DetectedIsland,
    TileLabelMapping,
    apply_tile_label_mapping,
    reconcile_candidate_tiles,
)
from hebog.config import ResidualMultiscaleDetectionConfig
from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import ProductChunk
from hebog.executors.base import Executor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink

_SCALE_ORDERS = (1, 2, 3)
_PHASE_FIVE_MULTISCALE_PRODUCT_NAMES = tuple(
    sorted(
        (
            "combined-snr",
            "position-signal",
            "reconstructed-signal",
            "reconstruction-mask",
            "retained-mask",
            *(f"scale-{order}-significant" for order in _SCALE_ORDERS),
        )
    )
)


class _WindowReadable(Protocol):
    """Read bounded global image windows without scheduler state."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


class _CompletedProductSource(Protocol):
    """Read checksum-validated windows from one published generation."""

    @property
    def manifest(self) -> PartitionManifest:
        """Return the source generation's canonical partition."""
        ...

    def read_generation(self) -> ProductGenerationManifest:
        """Validate and return the published completion record."""
        ...

    def read_completed_window(
        self,
        product_name: str,
        bounds: ImageBounds,
    ) -> npt.NDArray[np.generic]:
        """Read one validated bounded product window."""
        ...

    def access_session(self) -> AbstractContextManager[None]:
        """Reuse immutable metadata within one bounded coarse task."""
        ...


@dataclass(frozen=True, slots=True)
class PhaseFiveMultiscaleStageConfig:
    """Reviewed residual science and coarse executor-batch limit."""

    beam: BeamShapePixels
    detection: ResidualMultiscaleDetectionConfig
    maximum_tiles_per_batch: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before stage products are initialized."""
        if (
            isinstance(self.maximum_tiles_per_batch, bool)
            or not isinstance(self.maximum_tiles_per_batch, Integral)
            or self.maximum_tiles_per_batch < 1
        ):
            raise ValueError(
                "maximum_tiles_per_batch must be a positive integer"
            )


@dataclass(frozen=True, slots=True)
class PhaseFiveMultiscaleStageResult:
    """Published products, stable topology, and scalar execution evidence."""

    generation: ProductGenerationManifest
    detection_islands: tuple[DetectedIsland, ...]
    reconstruction_islands: tuple[DetectedIsland, ...]
    scale_islands_by_order: tuple[tuple[DetectedIsland, ...], ...]
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    maximum_batch_partition_count: int
    maximum_read_pixel_count: int
    maximum_workspace_bytes: int
    maximum_retained_array_bytes: int
    maximum_worker_bytes: int
    topology_summary_count: int
    scale_summary_count: int
    boundary_summary_array_bytes: int
    maximum_task_summary_array_bytes: int
    published_product_shard_count: int
    maximum_task_product_shard_count: int
    reconciliation_round_count: int


@dataclass(frozen=True, slots=True)
class _PartitionBatch:
    """One bounded coarse executor task containing canonical tiles."""

    partitions: tuple[TilePartition, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.partitions:
            raise ValueError("Phase 5 partition batch must not be empty")


@dataclass(frozen=True, slots=True)
class _TopologyBatchResult:
    """Array-free first-pass topology from one executor task."""

    reconstruction_summaries: tuple[LocalIslandTileSummary, ...]
    detection_summaries: tuple[LocalIslandTileSummary, ...]
    maximum_read_pixel_count: int
    maximum_workspace_bytes: int
    maximum_retained_array_bytes: int
    maximum_worker_bytes: int
    summary_array_bytes: int


@dataclass(frozen=True, slots=True)
class _PublicationTileRequest:
    """One second-pass tile and its accepted global label mappings."""

    partition: TilePartition
    reconstruction_mapping: TileLabelMapping
    detection_mapping: TileLabelMapping


@dataclass(frozen=True, slots=True)
class _PublicationBatch:
    """One bounded second-pass executor task."""

    requests: tuple[_PublicationTileRequest, ...]

    def __post_init__(self) -> None:
        """Forbid empty publication work records."""
        if not self.requests:
            raise ValueError("Phase 5 publication batch must not be empty")


@dataclass(frozen=True, slots=True)
class _PublicationBatchResult:
    """Persisted product identities and compact per-scale topology."""

    product_chunks: tuple[ProductChunk, ...]
    scale_summaries_by_order: tuple[tuple[LocalIslandTileSummary, ...], ...]
    maximum_read_pixel_count: int
    maximum_workspace_bytes: int
    maximum_retained_array_bytes: int
    maximum_worker_bytes: int
    summary_array_bytes: int


def phase_five_multiscale_product_names() -> tuple[str, ...]:
    """Return the canonical accepted multiscale product set."""
    return _PHASE_FIVE_MULTISCALE_PRODUCT_NAMES


def _require_image_window(
    window: ImageWindow,
    partition: TilePartition,
) -> ImageWindow:
    """Validate one exact halo window before filter preparation."""
    bounds = partition.read_bounds
    if window.bounds != bounds:
        raise ValueError("image source returned different filter-read bounds")
    if (
        window.values.shape != bounds.shape_yx
        or window.valid_pixels.shape != bounds.shape_yx
    ):
        raise ValueError("image source returned a misaligned filter window")
    return window


def _read_image_window(
    source: _WindowReadable,
    partition: TilePartition,
) -> ImageWindow:
    """Read and validate one exact halo window."""
    return _require_image_window(
        source.read_window(partition.read_bounds),
        partition,
    )


def _read_image_batch(
    source: _WindowReadable,
    partitions: tuple[TilePartition, ...],
) -> tuple[ImageWindow, ...]:
    """Use one optional bounded batch read or the scalar source contract."""
    read_windows = getattr(source, "read_windows", None)
    if read_windows is None:
        return tuple(_read_image_window(source, item) for item in partitions)
    windows = tuple(
        read_windows(tuple(item.read_bounds for item in partitions))
    )
    if len(windows) != len(partitions):
        raise ValueError("image source returned a different window count")
    return tuple(
        _require_image_window(window, partition)
        for window, partition in zip(windows, partitions, strict=True)
    )


def _image_batch_bytes(windows: tuple[ImageWindow, ...]) -> int:
    """Return exact arrays retained by one bounded source batch."""
    return sum(
        window.values.nbytes + window.valid_pixels.nbytes for window in windows
    )


def _evaluate_tile(  # noqa: PLR0913
    partition: TilePartition,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    detection: ResidualMultiscaleDetectionConfig,
    image_window: ImageWindow | None = None,
) -> tuple[PhaseFiveFilterTileResult, PhaseFiveDetectionTileEvidence]:
    """Recompute one bounded filter read without persistent response banks."""
    window = (
        _read_image_window(source, partition)
        if image_window is None
        else _require_image_window(image_window, partition)
    )
    background = background_rms_source.read_completed_window(
        "background",
        partition.read_bounds,
    )
    rms = background_rms_source.read_completed_window(
        "rms",
        partition.read_bounds,
    )
    prepared = prepare_scale_filter_inputs(
        window.values,
        window.valid_pixels,
        background,
        rms,
    )
    del window, background, rms
    result = evaluate_phase_five_filter_tile(
        prepared,
        partition=partition,
        image_shape_yx=image_shape_yx,
        beam=beam,
        minimum_support_fraction=detection.minimum_scale_support_fraction,
    )
    return result, derive_phase_five_detection_tile_evidence(
        result,
        detection,
    )


def _label_topology(
    evidence: PhaseFiveDetectionTileEvidence,
    *,
    image_shape_yx: tuple[int, int],
) -> tuple[LocalIslandTile, LocalIslandTile]:
    """Label point-local reconstruction and original-residual membership."""
    reconstruction = label_detection_tile(
        DetectionThresholdMasks(
            normalized_residual=evidence.atrous_maximum_snr,
            island_membership=evidence.reconstruction_membership,
            detection_seeds=evidence.reconstruction_seeds,
            valid_pixel_count=int(
                np.count_nonzero(evidence.reconstruction_membership)
            ),
        ),
        evidence.partition,
        image_shape_yx=image_shape_yx,
    )
    detection = label_detection_tile(
        DetectionThresholdMasks(
            normalized_residual=evidence.direct_snr,
            island_membership=evidence.detection_membership,
            detection_seeds=evidence.detection_seeds,
            valid_pixel_count=int(
                np.count_nonzero(evidence.detection_membership)
            ),
        ),
        evidence.partition,
        image_shape_yx=image_shape_yx,
    )
    return reconstruction, detection


def _workspace_bytes(result: PhaseFiveFilterTileResult) -> int:
    """Return the larger reviewed filter workspace for one tile read."""
    return max(
        result.matched_filter.maximum_workspace_bytes,
        result.atrous_result.maximum_workspace_bytes,
    )


def _summary_array_bytes(summary: LocalIslandTileSummary) -> int:
    """Return exact boundary-label payload retained by one summary."""
    labels = summary.boundary_labels
    return sum(
        array.nbytes
        for array in (labels.top, labels.bottom, labels.left, labels.right)
    )


def _tile_array_bytes(tile: LocalIslandTile) -> int:
    """Return exact label and boundary payload retained by one local tile."""
    return tile.labels.nbytes + _summary_array_bytes(tile.compact_summary())


def _product_array_bytes(
    products: tuple[tuple[str, npt.NDArray[np.generic]], ...],
) -> int:
    """Return unique ndarray payload retained by one publication record."""
    arrays = {id(values): values for _, values in products}
    return sum(values.nbytes for values in arrays.values())


def _scan_topology_batch(  # noqa: PLR0913
    batch: _PartitionBatch,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    detection: ResidualMultiscaleDetectionConfig,
) -> _TopologyBatchResult:
    """Evaluate one topology batch with task-local Zarr metadata reuse."""
    with background_rms_source.access_session():
        return _scan_topology_batch_in_session(
            batch,
            source=source,
            background_rms_source=background_rms_source,
            image_shape_yx=image_shape_yx,
            beam=beam,
            detection=detection,
        )


def _scan_topology_batch_in_session(  # noqa: PLR0913
    batch: _PartitionBatch,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    detection: ResidualMultiscaleDetectionConfig,
) -> _TopologyBatchResult:
    """Return compact side/corner topology without persisting responses."""
    reconstruction_summaries: list[LocalIslandTileSummary] = []
    detection_summaries: list[LocalIslandTileSummary] = []
    maximum_read_pixels = 0
    maximum_workspace_bytes = 0
    maximum_retained_array_bytes = 0
    maximum_worker_bytes = 0
    summary_array_bytes = 0
    image_windows = _read_image_batch(source, batch.partitions)
    image_batch_bytes = _image_batch_bytes(image_windows)
    for partition, image_window in zip(
        batch.partitions,
        image_windows,
        strict=True,
    ):
        result, evidence = _evaluate_tile(
            partition,
            source=source,
            background_rms_source=background_rms_source,
            image_shape_yx=image_shape_yx,
            beam=beam,
            detection=detection,
            image_window=image_window,
        )
        reconstruction, direct_detection = _label_topology(
            evidence,
            image_shape_yx=image_shape_yx,
        )
        retained_array_bytes = (
            image_batch_bytes
            + summary_array_bytes
            + result.retained_array_bytes
            + evidence.retained_array_bytes
            + _tile_array_bytes(reconstruction)
            + _tile_array_bytes(direct_detection)
        )
        maximum_retained_array_bytes = max(
            maximum_retained_array_bytes,
            retained_array_bytes,
        )
        maximum_worker_bytes = max(
            maximum_worker_bytes,
            image_batch_bytes
            + summary_array_bytes
            + result.maximum_filter_evaluation_bytes,
            retained_array_bytes,
        )
        reconstruction_summaries.append(reconstruction.compact_summary())
        detection_summaries.append(direct_detection.compact_summary())
        summary_array_bytes += _summary_array_bytes(
            reconstruction_summaries[-1]
        ) + _summary_array_bytes(detection_summaries[-1])
        maximum_read_pixels = max(
            maximum_read_pixels,
            result.read_pixel_count,
        )
        maximum_workspace_bytes = max(
            maximum_workspace_bytes,
            _workspace_bytes(result),
        )
    return _TopologyBatchResult(
        reconstruction_summaries=tuple(reconstruction_summaries),
        detection_summaries=tuple(detection_summaries),
        maximum_read_pixel_count=maximum_read_pixels,
        maximum_workspace_bytes=maximum_workspace_bytes,
        maximum_retained_array_bytes=maximum_retained_array_bytes,
        maximum_worker_bytes=maximum_worker_bytes,
        summary_array_bytes=summary_array_bytes,
    )


def _retain_mapping_labels(
    mapping: TileLabelMapping,
    accepted_global_labels: frozenset[int],
) -> TileLabelMapping:
    """Map scientifically rejected candidate components to background."""
    return TileLabelMapping(
        tile_id=mapping.tile_id,
        local_labels=mapping.local_labels,
        global_labels=tuple(
            global_label if global_label in accepted_global_labels else 0
            for global_label in mapping.global_labels
        ),
    )


def _publication_products(
    result: PhaseFiveFilterTileResult,
    evidence: PhaseFiveDetectionTileEvidence,
    *,
    reconstruction_mask: npt.NDArray[np.bool_],
    retained_mask: npt.NDArray[np.bool_],
) -> tuple[
    tuple[tuple[str, npt.NDArray[np.generic]], ...],
    tuple[npt.NDArray[np.bool_], ...],
]:
    """Derive accepted core products after global topology reconciliation."""
    scale_masks = tuple(
        np.asarray(mask & reconstruction_mask, dtype=np.bool_)
        for mask in evidence.significant_scale_masks
    )
    reconstructed = np.zeros(retained_mask.shape, dtype=np.float64)
    for response, mask in zip(
        result.atrous_result.responses,
        scale_masks,
        strict=True,
    ):
        np.add(
            reconstructed,
            response.response_jy_per_beam,
            out=reconstructed,
            where=mask,
        )
    combined_snr = np.maximum(
        evidence.matched_maximum_snr,
        evidence.direct_snr,
    )
    np.maximum(
        combined_snr,
        evidence.atrous_maximum_snr,
        out=combined_snr,
        where=reconstruction_mask,
    )
    combined_snr[~result.prepared_inputs.scientifically_valid] = -np.inf
    position_signal = np.asarray(
        result.prepared_inputs.residual_jy_per_beam + reconstructed,
        dtype=np.float64,
    )
    products: tuple[tuple[str, npt.NDArray[np.generic]], ...] = (
        ("combined-snr", combined_snr),
        ("position-signal", position_signal),
        ("reconstructed-signal", reconstructed),
        ("reconstruction-mask", reconstruction_mask),
        ("retained-mask", retained_mask),
        *(
            (f"scale-{order}-significant", mask)
            for order, mask in zip(_SCALE_ORDERS, scale_masks, strict=True)
        ),
    )
    return products, scale_masks


def _publish_batch(  # noqa: PLR0913
    batch: _PublicationBatch,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    sink: ZarrProductSink,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    detection: ResidualMultiscaleDetectionConfig,
) -> _PublicationBatchResult:
    """Publish one batch with bounded source and sink metadata reuse."""
    with background_rms_source.access_session(), sink.access_session():
        return _publish_batch_in_session(
            batch,
            source=source,
            background_rms_source=background_rms_source,
            sink=sink,
            image_shape_yx=image_shape_yx,
            beam=beam,
            detection=detection,
        )


def _publish_batch_in_session(  # noqa: PLR0913
    batch: _PublicationBatch,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    sink: ZarrProductSink,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    detection: ResidualMultiscaleDetectionConfig,
) -> _PublicationBatchResult:
    """Recompute, map global labels, and persist only accepted products."""
    chunks: list[ProductChunk] = []
    scale_summaries: list[list[LocalIslandTileSummary]] = [[], [], []]
    maximum_read_pixels = 0
    maximum_workspace_bytes = 0
    maximum_retained_array_bytes = 0
    maximum_worker_bytes = 0
    summary_array_bytes = 0
    partitions = tuple(request.partition for request in batch.requests)
    image_windows = _read_image_batch(source, partitions)
    image_batch_bytes = _image_batch_bytes(image_windows)
    for request, image_window in zip(
        batch.requests,
        image_windows,
        strict=True,
    ):
        result, evidence = _evaluate_tile(
            request.partition,
            source=source,
            background_rms_source=background_rms_source,
            image_shape_yx=image_shape_yx,
            beam=beam,
            detection=detection,
            image_window=image_window,
        )
        reconstruction, direct_detection = _label_topology(
            evidence,
            image_shape_yx=image_shape_yx,
        )
        labelled_retained_bytes = (
            image_batch_bytes
            + summary_array_bytes
            + result.retained_array_bytes
            + evidence.retained_array_bytes
            + _tile_array_bytes(reconstruction)
            + _tile_array_bytes(direct_detection)
        )
        maximum_retained_array_bytes = max(
            maximum_retained_array_bytes,
            labelled_retained_bytes,
        )
        reconstruction_mask = np.asarray(
            apply_tile_label_mapping(
                reconstruction,
                request.reconstruction_mapping,
            )
            > 0,
            dtype=np.bool_,
        )
        retained_mask = np.asarray(
            apply_tile_label_mapping(
                direct_detection,
                request.detection_mapping,
            )
            > 0,
            dtype=np.bool_,
        )
        del reconstruction, direct_detection
        products, scale_masks = _publication_products(
            result,
            evidence,
            reconstruction_mask=reconstruction_mask,
            retained_mask=retained_mask,
        )
        product_retained_bytes = (
            image_batch_bytes
            + summary_array_bytes
            + result.retained_array_bytes
            + evidence.retained_array_bytes
            + _product_array_bytes(products)
        )
        maximum_retained_array_bytes = max(
            maximum_retained_array_bytes,
            product_retained_bytes,
        )
        maximum_worker_bytes = max(
            maximum_worker_bytes,
            image_batch_bytes
            + summary_array_bytes
            + result.maximum_filter_evaluation_bytes,
            labelled_retained_bytes,
            product_retained_bytes,
        )
        chunks.extend(
            sink.write_chunk(
                product_name=product_name,
                tile=request.partition,
                values=np.asarray(values),
            )
            for product_name, values in products
        )
        for index, (scale_snr, scale_mask) in enumerate(
            zip(evidence.atrous_scale_snrs, scale_masks, strict=True)
        ):
            scale_tile = label_detection_tile(
                DetectionThresholdMasks(
                    normalized_residual=scale_snr,
                    island_membership=scale_mask,
                    detection_seeds=scale_mask,
                    valid_pixel_count=int(np.count_nonzero(scale_mask)),
                ),
                request.partition,
                image_shape_yx=image_shape_yx,
            )
            scale_retained_bytes = product_retained_bytes + _tile_array_bytes(
                scale_tile
            )
            maximum_retained_array_bytes = max(
                maximum_retained_array_bytes,
                scale_retained_bytes,
            )
            maximum_worker_bytes = max(
                maximum_worker_bytes,
                scale_retained_bytes,
            )
            scale_summaries[index].append(scale_tile.compact_summary())
            added_summary_bytes = _summary_array_bytes(
                scale_summaries[index][-1]
            )
            summary_array_bytes += added_summary_bytes
            product_retained_bytes += added_summary_bytes
        maximum_read_pixels = max(
            maximum_read_pixels,
            result.read_pixel_count,
        )
        maximum_workspace_bytes = max(
            maximum_workspace_bytes,
            _workspace_bytes(result),
        )
    return _PublicationBatchResult(
        product_chunks=tuple(chunks),
        scale_summaries_by_order=tuple(
            tuple(summaries) for summaries in scale_summaries
        ),
        maximum_read_pixel_count=maximum_read_pixels,
        maximum_workspace_bytes=maximum_workspace_bytes,
        maximum_retained_array_bytes=maximum_retained_array_bytes,
        maximum_worker_bytes=maximum_worker_bytes,
        summary_array_bytes=summary_array_bytes,
    )


def _partition_batches(
    manifest: PartitionManifest,
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_PartitionBatch, ...]:
    """Group canonical tiles without changing scientific ownership."""
    return tuple(
        _PartitionBatch(
            partitions=manifest.tiles[start : start + maximum_tiles_per_batch]
        )
        for start in range(0, len(manifest.tiles), maximum_tiles_per_batch)
    )


def _publication_batches(
    requests: tuple[_PublicationTileRequest, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_PublicationBatch, ...]:
    """Group mapped publication requests under the same bounded limit."""
    return tuple(
        _PublicationBatch(
            requests=requests[start : start + maximum_tiles_per_batch]
        )
        for start in range(0, len(requests), maximum_tiles_per_batch)
    )


def _validate_stage_inputs(
    background_rms_source: _CompletedProductSource,
    manifest: PartitionManifest,
    config: PhaseFiveMultiscaleStageConfig,
    sink: ZarrProductSink,
) -> None:
    """Fail before output initialization when identities cannot compose."""
    if sink.manifest != manifest:
        raise ValueError("Phase 5 multiscale sink must use the stage manifest")
    required_halo = scale_filter_halo_pixels(config.beam)
    if manifest.halo_yx != (required_halo, required_halo):
        raise ValueError(
            "Phase 5 manifest must provide the exact widest filter halo"
        )
    if (
        background_rms_source.manifest.image_shape_yx
        != manifest.image_shape_yx
    ):
        raise ValueError(
            "background/RMS generation must match the filter image shape"
        )
    generation = background_rms_source.read_generation()
    if not {"background", "rms"}.issubset(generation.product_names):
        raise ValueError(
            "background/RMS generation must publish background and rms"
        )


def run_phase_five_multiscale_stage(  # noqa: PLR0913
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: PhaseFiveMultiscaleStageConfig,
    executor: Executor,
    sink: ZarrProductSink,
) -> PhaseFiveMultiscaleStageResult:
    """Reconcile bounded multiscale topology and publish accepted products.

    The first pass returns only compact side/corner summaries. After global
    reconciliation, workers recompute the same bounded filters, apply stable
    label mappings, and write accepted core products. This deliberate second
    read avoids an image-sized persisted filter-response bank. No scientific
    array is returned through the executor.
    """
    _validate_stage_inputs(
        background_rms_source,
        manifest,
        config,
        sink,
    )
    partition_batches = _partition_batches(
        manifest,
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    scan = partial(
        _scan_topology_batch,
        source=source,
        background_rms_source=background_rms_source,
        image_shape_yx=manifest.image_shape_yx,
        beam=config.beam,
        detection=config.detection,
    )
    topology_results = tuple(executor.map_batches(scan, partition_batches))
    if not topology_results:
        raise ValueError("executor returned no Phase 5 topology results")
    reconstruction = reconcile_candidate_tiles(
        manifest,
        tuple(
            summary
            for result in topology_results
            for summary in result.reconstruction_summaries
        ),
    )
    detection_candidates = reconcile_candidate_tiles(
        manifest,
        tuple(
            summary
            for result in topology_results
            for summary in result.detection_summaries
        ),
    )
    minimum_pixels = minimum_residual_island_pixels(
        config.beam,
        config.detection,
    )
    detection_islands = tuple(
        island
        for island in detection_candidates.islands
        if island.pixel_count >= minimum_pixels
        or island.peak_signal_to_noise
        >= config.detection.detection_threshold_sigma
    )
    accepted_detection_labels = frozenset(
        island.global_label for island in detection_islands
    )
    publication_requests = tuple(
        _PublicationTileRequest(
            partition=partition,
            reconstruction_mapping=reconstruction.mapping_for_tile(
                partition.tile_id
            ),
            detection_mapping=_retain_mapping_labels(
                detection_candidates.mapping_for_tile(partition.tile_id),
                accepted_detection_labels,
            ),
        )
        for partition in manifest.tiles
    )
    for product_name in _PHASE_FIVE_MULTISCALE_PRODUCT_NAMES:
        dtype = (
            np.dtype(np.bool_)
            if product_name.endswith("mask")
            or product_name.endswith("significant")
            else np.dtype("<f8")
        )
        sink.initialize_product(product_name=product_name, dtype=dtype)
    publication_batches = _publication_batches(
        publication_requests,
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    publish = partial(
        _publish_batch,
        source=source,
        background_rms_source=background_rms_source,
        sink=sink,
        image_shape_yx=manifest.image_shape_yx,
        beam=config.beam,
        detection=config.detection,
    )
    publication_results = tuple(
        executor.map_batches(publish, publication_batches)
    )
    if not publication_results:
        raise ValueError("executor returned no Phase 5 publication results")
    generation = sink.publish_generation(
        product_names=_PHASE_FIVE_MULTISCALE_PRODUCT_NAMES,
        chunks=(
            chunk
            for result in publication_results
            for chunk in result.product_chunks
        ),
    )
    scale_islands = tuple(
        reconcile_candidate_tiles(
            manifest,
            tuple(
                summary
                for result in publication_results
                for summary in result.scale_summaries_by_order[scale_index]
            ),
        ).islands
        for scale_index in range(len(_SCALE_ORDERS))
    )
    all_results = (*topology_results, *publication_results)
    batch_counts = (len(partition_batches), len(publication_batches))
    return PhaseFiveMultiscaleStageResult(
        generation=generation,
        detection_islands=detection_islands,
        reconstruction_islands=reconstruction.islands,
        scale_islands_by_order=scale_islands,
        partition_count=len(manifest.tiles),
        executor_task_count=sum(batch_counts),
        maximum_graph_width=max(batch_counts),
        maximum_batch_partition_count=max(
            len(batch.partitions) for batch in partition_batches
        ),
        maximum_read_pixel_count=max(
            result.maximum_read_pixel_count for result in all_results
        ),
        maximum_workspace_bytes=max(
            result.maximum_workspace_bytes for result in all_results
        ),
        maximum_retained_array_bytes=max(
            result.maximum_retained_array_bytes for result in all_results
        ),
        maximum_worker_bytes=max(
            result.maximum_worker_bytes for result in all_results
        ),
        topology_summary_count=2 * len(manifest.tiles),
        scale_summary_count=len(_SCALE_ORDERS) * len(manifest.tiles),
        boundary_summary_array_bytes=sum(
            result.summary_array_bytes for result in all_results
        ),
        maximum_task_summary_array_bytes=max(
            result.summary_array_bytes for result in all_results
        ),
        published_product_shard_count=len(generation.chunks),
        maximum_task_product_shard_count=max(
            len(result.product_chunks) for result in publication_results
        ),
        reconciliation_round_count=max(
            reconstruction.reduction_round_count,
            detection_candidates.reduction_round_count,
        ),
    )
