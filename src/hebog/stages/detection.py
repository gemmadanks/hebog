"""Bounded compact-detection execution and Zarr product publication."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Protocol

import numpy as np

from hebog.algorithms.detection import (
    detect_high_significance_candidates,
    detect_threshold_masks,
)
from hebog.algorithms.labelling import (
    LocalIslandTileSummary,
    label_detection_tile,
)
from hebog.algorithms.reconciliation import (
    DetectedIsland,
    TileLabelMapping,
    apply_tile_label_mapping,
    reconcile_candidate_tiles,
    reconcile_island_tiles,
)
from hebog.config import BackgroundRmsConfig, SourceFinderConfig
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
from hebog.stages.background import (
    BackgroundRmsGrids,
    BackgroundRmsTileRequest,
    estimate_background_rms_grids,
    interpolate_background_rms_tile,
    prepare_background_rms_tile_request,
    refine_background_rms_grids,
)


class _WindowReadable(Protocol):
    """Read bounded global image windows without opening scheduler state."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


@dataclass(frozen=True, slots=True)
class _DetectionTileProducts:
    """Compact scheduler result from one first-pass detection tile."""

    summary: LocalIslandTileSummary
    product_chunks: tuple[ProductChunk, ProductChunk]


@dataclass(frozen=True, slots=True)
class _MaskTileRequest:
    """One final tile request carrying only its local label mapping."""

    background_rms: BackgroundRmsTileRequest
    label_mapping: TileLabelMapping


@dataclass(frozen=True, slots=True)
class DetectionStageResult:
    """Published compact topology and bounded execution evidence."""

    generation: ProductGenerationManifest
    islands: tuple[DetectedIsland, ...]
    adaptive_candidate_positions_yx: tuple[tuple[float, float], ...]
    background_rms_grids: BackgroundRmsGrids
    boundary_label_count: int
    reconciliation_round_count: int
    separate_candidate_scan: bool


@dataclass(frozen=True, slots=True)
class DetectionStageConfig:
    """Scientific policies required by the compact-detection stage."""

    background_rms: BackgroundRmsConfig
    source_finder: SourceFinderConfig


def _read_tile_window(
    source: _WindowReadable,
    partition: TilePartition,
) -> ImageWindow:
    """Read and validate one owned core before scientific processing."""
    bounds = partition.core_bounds
    window = source.read_window(bounds)
    if window.bounds != bounds:
        raise ValueError("image source returned different tile bounds")
    if (
        window.values.shape != bounds.shape_yx
        or window.valid_pixels.shape != bounds.shape_yx
    ):
        raise ValueError("image source returned a misaligned window")
    return window


def _scan_candidate_tile(
    request: BackgroundRmsTileRequest,
    *,
    source: _WindowReadable,
    threshold_sigma: float,
    image_shape_yx: tuple[int, int],
) -> LocalIslandTileSummary:
    """Return only bounded topology from one high-significance scan."""
    window = _read_tile_window(source, request.partition)
    background_rms = interpolate_background_rms_tile(window, request)
    masks = detect_high_significance_candidates(
        window.values,
        window.valid_pixels,
        background_rms.background,
        background_rms.rms,
        threshold_sigma=threshold_sigma,
    )
    return label_detection_tile(
        masks,
        request.partition,
        image_shape_yx=image_shape_yx,
    ).compact_summary()


def discover_adaptive_candidates(
    source: _WindowReadable,
    manifest: PartitionManifest,
    coarse_grids: BackgroundRmsGrids,
    config: BackgroundRmsConfig,
    executor: Executor,
) -> tuple[tuple[float, float], ...]:
    """Find deterministic global peaks for strict adaptive-RMS candidates."""
    adaptive = config.adaptive
    if adaptive is None:
        return ()
    if coarse_grids.adaptive_regions:
        raise ValueError("candidate discovery requires a coarse-only cache")
    requests = tuple(
        prepare_background_rms_tile_request(tile, coarse_grids, config)
        for tile in manifest.tiles
    )
    scan = partial(
        _scan_candidate_tile,
        source=source,
        threshold_sigma=adaptive.candidate_threshold_sigma,
        image_shape_yx=manifest.image_shape_yx,
    )
    summaries = tuple(executor.map_batches(scan, requests))
    candidates = reconcile_candidate_tiles(manifest, summaries)
    return tuple(
        (float(island.peak_position_yx[0]), float(island.peak_position_yx[1]))
        for island in candidates.islands
    )


def _detect_and_write_background_rms(
    request: BackgroundRmsTileRequest,
    *,
    source: _WindowReadable,
    sink: ZarrProductSink,
    config: SourceFinderConfig,
    image_shape_yx: tuple[int, int],
) -> _DetectionTileProducts:
    """Persist output fields and return no image-sized scheduler payload."""
    window = _read_tile_window(source, request.partition)
    background_rms = interpolate_background_rms_tile(window, request)
    masks = detect_threshold_masks(
        window.values,
        window.valid_pixels,
        background_rms.background,
        background_rms.rms,
        config,
    )
    tile = label_detection_tile(
        masks,
        request.partition,
        image_shape_yx=image_shape_yx,
    )
    chunks = (
        sink.write_chunk(
            product_name="background",
            tile=request.partition,
            values=np.asarray(background_rms.background),
        ),
        sink.write_chunk(
            product_name="rms",
            tile=request.partition,
            values=np.asarray(background_rms.rms),
        ),
    )
    return _DetectionTileProducts(
        summary=tile.compact_summary(),
        product_chunks=chunks,
    )


def _write_source_filtering_mask(
    request: _MaskTileRequest,
    *,
    source: _WindowReadable,
    sink: ZarrProductSink,
    config: SourceFinderConfig,
    image_shape_yx: tuple[int, int],
) -> ProductChunk:
    """Recompute one bounded label core and publish accepted membership."""
    background_request = request.background_rms
    window = _read_tile_window(source, background_request.partition)
    background_rms = interpolate_background_rms_tile(
        window,
        background_request,
    )
    masks = detect_threshold_masks(
        window.values,
        window.valid_pixels,
        background_rms.background,
        background_rms.rms,
        config,
    )
    local_tile = label_detection_tile(
        masks,
        background_request.partition,
        image_shape_yx=image_shape_yx,
    )
    accepted = np.asarray(
        apply_tile_label_mapping(local_tile, request.label_mapping) > 0,
        dtype=np.bool_,
    )
    return sink.write_chunk(
        product_name="source-filtering-mask",
        tile=background_request.partition,
        values=accepted,
    )


def run_detection_stage(
    source: _WindowReadable,
    manifest: PartitionManifest,
    config: DetectionStageConfig,
    executor: Executor,
    sink: ZarrProductSink,
) -> DetectionStageResult:
    """Run bounded compact detection and publish one complete generation.

    The separate high-significance scan and final mask pass deliberately trade
    one extra bounded image read each for simple retry semantics and compact
    scheduler results. No normalized, label, background, RMS, or mask plane is
    gathered by the executor.
    """
    if sink.manifest != manifest:
        raise ValueError(
            "detection sink must use the stage partition manifest"
        )
    coarse_grids = estimate_background_rms_grids(
        source,
        manifest.image_shape_yx,
        config.background_rms,
        executor,
        bright_candidate_positions_yx=(),
    )
    return run_detection_from_coarse_grids(
        source,
        manifest,
        coarse_grids,
        config=config,
        executor=executor,
        sink=sink,
    )


def run_detection_from_coarse_grids(  # noqa: PLR0913
    source: _WindowReadable,
    manifest: PartitionManifest,
    coarse_grids: BackgroundRmsGrids,
    *,
    config: DetectionStageConfig,
    executor: Executor,
    sink: ZarrProductSink,
) -> DetectionStageResult:
    """Run Phase 3 from one immutable Phase 2 coarse-grid result.

    This boundary lets component benchmarks and future pipeline execution
    reuse an already-computed coarse background/RMS grid without changing the
    automatic adaptive-candidate or final product semantics.
    """
    if sink.manifest != manifest:
        raise ValueError(
            "detection sink must use the stage partition manifest"
        )
    if coarse_grids.adaptive_regions:
        raise ValueError("detection requires a coarse-only background cache")
    if coarse_grids.coarse.geometry.image_shape_yx != manifest.image_shape_yx:
        raise ValueError(
            "coarse background cache must match the detection image shape"
        )
    candidate_positions = discover_adaptive_candidates(
        source,
        manifest,
        coarse_grids,
        config.background_rms,
        executor,
    )
    grids = refine_background_rms_grids(
        source,
        coarse_grids,
        config.background_rms,
        executor,
        bright_candidate_positions_yx=candidate_positions,
    )
    for product_name, dtype in (
        ("background", np.dtype("<f8")),
        ("rms", np.dtype("<f8")),
        ("source-filtering-mask", np.dtype(np.bool_)),
    ):
        sink.initialize_product(product_name=product_name, dtype=dtype)

    requests = tuple(
        prepare_background_rms_tile_request(
            partition,
            grids,
            config.background_rms,
        )
        for partition in manifest.tiles
    )
    detect = partial(
        _detect_and_write_background_rms,
        source=source,
        sink=sink,
        config=config.source_finder,
        image_shape_yx=manifest.image_shape_yx,
    )
    tile_products = tuple(executor.map_batches(detect, requests))
    summaries = tuple(result.summary for result in tile_products)
    reconciliation = reconcile_island_tiles(
        manifest,
        summaries,
        config.source_finder,
    )
    mask_requests = tuple(
        _MaskTileRequest(background_rms=request, label_mapping=mapping)
        for request, mapping in zip(
            requests,
            reconciliation.tile_mappings,
            strict=True,
        )
    )
    write_mask = partial(
        _write_source_filtering_mask,
        source=source,
        sink=sink,
        config=config.source_finder,
        image_shape_yx=manifest.image_shape_yx,
    )
    mask_chunks = tuple(executor.map_batches(write_mask, mask_requests))
    product_chunks = (
        tuple(
            chunk
            for result in tile_products
            for chunk in result.product_chunks
        )
        + mask_chunks
    )
    generation = sink.publish_generation(
        product_names=("background", "rms", "source-filtering-mask"),
        chunks=product_chunks,
    )
    boundary_label_count = sum(
        summary.boundary_labels.top.size
        + summary.boundary_labels.bottom.size
        + summary.boundary_labels.left.size
        + summary.boundary_labels.right.size
        for summary in summaries
    )
    return DetectionStageResult(
        generation=generation,
        islands=reconciliation.islands,
        adaptive_candidate_positions_yx=candidate_positions,
        background_rms_grids=grids,
        boundary_label_count=boundary_label_count,
        reconciliation_round_count=reconciliation.reduction_round_count,
        separate_candidate_scan=config.background_rms.adaptive is not None,
    )
