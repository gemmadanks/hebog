"""Scheduler-facing compact and extended measurement stages."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from math import ceil
from typing import Protocol

import numpy as np

from hebog.algorithms.deblending import (
    DeferredIslandShard,
    PartitionedDeferredIsland,
    extract_deferred_island_shard_membership,
)
from hebog.algorithms.extended_measurement import (
    ExtendedEmissionTilePartial,
    ExtendedEmissionTilePlanes,
    ExtendedEmissionTileTarget,
    combine_extended_emission_partials,
    expand_detected_segment_labels,
    measure_extended_emission_tile,
)
from hebog.algorithms.measurement import measure_compact_moments
from hebog.config import (
    CompactDeblendConfig,
    CompactMomentConfig,
    ExtendedEmissionMeasurementConfig,
)
from hebog.data_models.measurement import (
    CompactMeasurementGeometry,
    CompactMomentMeasurement,
    ExtendedEmissionMeasurementResult,
    ExtendedEmissionTarget,
    ExtendedMeasurementGeometry,
    MeasuredExtendedEmission,
)
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.executors.base import Executor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.stages.deblending import (
    CompactRegionStageResult,
    WorkerLocalRegionBatch,
    run_compact_region_stage,
)
from hebog.stages.detection import DetectionStageResult


class _WindowReadable(Protocol):
    """Read one bounded image window for scientific measurement."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


@dataclass(frozen=True, slots=True)
class CompactMomentProcessor:
    """Pickleable processor reducing exact labels to compact records."""

    geometry: CompactMeasurementGeometry
    config: CompactMomentConfig

    def __call__(
        self,
        batch: WorkerLocalRegionBatch,
    ) -> tuple[CompactMomentMeasurement, ...]:
        """Measure every admitted island and region in canonical order."""
        return tuple(
            result
            for compact_island in batch.islands
            for result in measure_compact_moments(
                compact_island,
                self.geometry,
                self.config,
            )
        )


@dataclass(frozen=True, slots=True)
class _ExtendedTargetShards:
    """One global target and only the exact shards needed by a task."""

    target: ExtendedEmissionTarget
    shards: tuple[DeferredIslandShard, ...]


@dataclass(frozen=True, slots=True)
class _ExtendedMeasurementTileRequest:
    """Array-free request for one non-overlapping measurement core."""

    partition: TilePartition
    read_bounds: ImageBounds
    targets: tuple[_ExtendedTargetShards, ...]


@dataclass(frozen=True, slots=True)
class ExtendedEmissionMeasurementStageResult:
    """Canonical measurements plus bounded execution evidence."""

    measurements: tuple[ExtendedEmissionMeasurementResult, ...]
    planned_tile_count: int
    maximum_task_pixels: int
    maximum_request_shards: int
    flux_uncertainty_available_count: int
    truncated_measurement_count: int


def run_compact_moment_stage(  # noqa: PLR0913
    source: _WindowReadable,
    detection: DetectionStageResult,
    deblend_config: CompactDeblendConfig,
    moment_config: CompactMomentConfig,
    geometry: CompactMeasurementGeometry,
    *,
    executor: Executor,
    sink: ZarrProductSink,
) -> CompactRegionStageResult[CompactMomentMeasurement]:
    """Measure exact compact labels within existing coarse executor tasks."""
    return run_compact_region_stage(
        source,
        detection,
        deblend_config,
        processor=CompactMomentProcessor(
            geometry=geometry,
            config=moment_config,
        ),
        executor=executor,
        sink=sink,
    )


def _bounds_intersect(first: ImageBounds, second: ImageBounds) -> bool:
    """Return whether two half-open image regions overlap."""
    return (
        first.y_start < second.y_stop
        and second.y_start < first.y_stop
        and first.x_start < second.x_stop
        and second.x_start < first.x_stop
    )


def _copy_shard_into_read_labels(
    labels: np.ndarray,
    *,
    read_bounds: ImageBounds,
    shard: DeferredIslandShard,
    membership: np.ndarray,
    local_label: int,
) -> None:
    """Copy one exact shard intersection into a bounded task label plane."""
    shard_bounds = shard.partition.core_bounds
    y_start = max(read_bounds.y_start, shard_bounds.y_start)
    y_stop = min(read_bounds.y_stop, shard_bounds.y_stop)
    x_start = max(read_bounds.x_start, shard_bounds.x_start)
    x_stop = min(read_bounds.x_stop, shard_bounds.x_stop)
    if y_start >= y_stop or x_start >= x_stop:
        raise ValueError("extended request contains a non-intersecting shard")
    shard_selection = (
        slice(y_start - shard_bounds.y_start, y_stop - shard_bounds.y_start),
        slice(x_start - shard_bounds.x_start, x_stop - shard_bounds.x_start),
    )
    read_selection = (
        slice(y_start - read_bounds.y_start, y_stop - read_bounds.y_start),
        slice(x_start - read_bounds.x_start, x_stop - read_bounds.x_start),
    )
    selected = membership[shard_selection]
    destination = labels[read_selection]
    if np.any(selected & (destination > 0)):
        raise ValueError("extended measurement supports overlap")
    destination[selected] = local_label


def _measure_extended_request(
    request: _ExtendedMeasurementTileRequest,
    *,
    source: _WindowReadable,
    sink: ZarrProductSink,
    config: ExtendedEmissionMeasurementConfig,
    geometry: ExtendedMeasurementGeometry,
) -> tuple[ExtendedEmissionTilePartial, ...]:
    """Read and reduce one bounded original-pixel measurement task."""
    read_pixels = (
        request.read_bounds.shape_yx[0] * request.read_bounds.shape_yx[1]
    )
    if read_pixels > config.maximum_task_pixels:
        raise ValueError("extended measurement task exceeds its hard bound")
    labels = np.zeros(request.read_bounds.shape_yx, dtype=np.int32)
    accepted_by_tile: dict[str, np.ndarray] = {}
    tile_targets: list[ExtendedEmissionTileTarget] = []
    for local_label, item in enumerate(request.targets, start=1):
        tile_targets.append(
            ExtendedEmissionTileTarget(local_label, item.target)
        )
        for shard in item.shards:
            tile_id = shard.partition.tile_id
            accepted = accepted_by_tile.get(tile_id)
            if accepted is None:
                accepted = np.asarray(
                    sink.read_completed_window(
                        "source-filtering-mask",
                        shard.partition.core_bounds,
                    )
                )
                accepted_by_tile[tile_id] = accepted
            membership = extract_deferred_island_shard_membership(
                shard,
                accepted,
            )
            _copy_shard_into_read_labels(
                labels,
                read_bounds=request.read_bounds,
                shard=shard,
                membership=membership,
                local_label=local_label,
            )
    accepted_values = np.asarray(
        sink.read_completed_window(
            "source-filtering-mask",
            request.read_bounds,
        )
    )
    if (
        accepted_values.shape != request.read_bounds.shape_yx
        or accepted_values.dtype != np.dtype(np.bool_)
    ):
        raise ValueError(
            "extended accepted mask must be a bounded boolean plane"
        )
    accepted_window = np.asarray(accepted_values, dtype=np.bool_)
    if np.any((labels > 0) & ~accepted_window):
        raise ValueError("extended shard support disagrees with accepted mask")
    barrier_label = len(request.targets) + 1
    labels[accepted_window & (labels == 0)] = barrier_label
    aperture_radius_pixels = ceil(
        config.aperture_radius_beams
        * geometry.restoring_beam_major_fwhm_pixels
    )
    aperture_labels = expand_detected_segment_labels(
        labels,
        np.ones(labels.shape, dtype=np.bool_),
        radius_pixels=aperture_radius_pixels,
    )
    aperture_labels[aperture_labels == barrier_label] = 0
    labels[labels == barrier_label] = 0
    core_selection = (
        slice(
            request.partition.core_bounds.y_start
            - request.read_bounds.y_start,
            request.partition.core_bounds.y_stop - request.read_bounds.y_start,
        ),
        slice(
            request.partition.core_bounds.x_start
            - request.read_bounds.x_start,
            request.partition.core_bounds.x_stop - request.read_bounds.x_start,
        ),
    )
    window = source.read_window(request.partition.core_bounds)
    if window.bounds != request.partition.core_bounds or any(
        array.shape != request.partition.core_bounds.shape_yx
        for array in (window.values, window.valid_pixels)
    ):
        raise ValueError("extended image source returned a misaligned core")
    background = np.asarray(
        sink.read_completed_window(
            "background", request.partition.core_bounds
        ),
        dtype=np.float64,
    )
    rms = np.asarray(
        sink.read_completed_window("rms", request.partition.core_bounds),
        dtype=np.float64,
    )
    if any(
        array.shape != request.partition.core_bounds.shape_yx
        for array in (background, rms)
    ):
        raise ValueError("extended prepared fields must match the task core")
    residual = np.asarray(window.values - background, dtype=np.float64)
    return measure_extended_emission_tile(
        ExtendedEmissionTilePlanes(
            residual_jy_per_beam=residual,
            background_jy_per_beam=background,
            rms_jy_per_beam=rms,
            valid_pixels=np.asarray(window.valid_pixels, dtype=np.bool_),
            support_labels=np.asarray(labels[core_selection], dtype=np.int32),
            aperture_labels=np.asarray(
                aperture_labels[core_selection],
                dtype=np.int32,
            ),
        ),
        request.partition,
        tuple(tile_targets),
    )


def _measurement_targets(
    islands: tuple[PartitionedDeferredIsland, ...],
) -> tuple[ExtendedEmissionTarget, ...]:
    """Translate canonical compact deferrals to generic support targets."""
    return tuple(
        ExtendedEmissionTarget(
            object_kind="deferred-island",
            object_id=item.island.island_id,
            parent_island_id=item.island.island_id,
            support_pixel_count=item.island.pixel_count,
            bounds=item.island.bounds,
        )
        for item in islands
    )


def _plan_extended_requests(
    islands: tuple[PartitionedDeferredIsland, ...],
    manifest: PartitionManifest,
    *,
    config: ExtendedEmissionMeasurementConfig,
    geometry: ExtendedMeasurementGeometry,
) -> tuple[_ExtendedMeasurementTileRequest, ...]:
    """Plan bounded cores with only nearby array-free membership shards."""
    targets = _measurement_targets(islands)
    target_items = tuple(zip(targets, islands, strict=True))
    radius_pixels = ceil(
        config.aperture_radius_beams
        * geometry.restoring_beam_major_fwhm_pixels
    )
    requests: list[_ExtendedMeasurementTileRequest] = []
    for partition in manifest.tiles:
        read_bounds = partition.core_bounds.expanded(
            radius_pixels,
            manifest.image_shape_yx,
        )
        if (
            read_bounds.shape_yx[0] * read_bounds.shape_yx[1]
            > config.maximum_task_pixels
        ):
            raise ValueError(
                "extended measurement task exceeds its hard bound"
            )
        request_targets: list[_ExtendedTargetShards] = []
        for target, island in target_items:
            if not _bounds_intersect(read_bounds, target.bounds):
                continue
            shards = tuple(
                shard
                for shard in island.shards
                if _bounds_intersect(read_bounds, shard.partition.core_bounds)
            )
            if not shards:
                # Irregular support need not occupy every core intersecting
                # its rectangular global bounds.
                continue
            request_targets.append(_ExtendedTargetShards(target, shards))
        if request_targets:
            requests.append(
                _ExtendedMeasurementTileRequest(
                    partition=partition,
                    read_bounds=read_bounds,
                    targets=tuple(request_targets),
                )
            )
    return tuple(requests)


def _validate_extended_stage_inputs(
    detection: DetectionStageResult,
    islands: tuple[PartitionedDeferredIsland, ...],
    manifest: PartitionManifest,
    sink: ZarrProductSink,
) -> None:
    """Bind exact shard identity to the published detection generation."""
    generation = detection.generation
    if (
        generation.partition_manifest != sink.manifest
        or generation.generation_id != sink.generation_id
    ):
        raise ValueError(
            "extended measurement sink does not match detection generation"
        )
    if manifest.image_shape_yx != sink.manifest.image_shape_yx:
        raise ValueError(
            "extended measurement manifest must match the detection image"
        )
    if manifest.halo_yx != (0, 0):
        raise ValueError("extended measurement manifest must use zero halo")
    if islands != tuple(
        sorted(islands, key=lambda item: item.island.island_id)
    ) or len({item.island.island_id for item in islands}) != len(islands):
        raise ValueError("extended measurement islands must be canonical")
    partitions = {tile.tile_id: tile for tile in manifest.tiles}
    for island in islands:
        for shard in island.shards:
            if partitions.get(shard.partition.tile_id) != shard.partition:
                raise ValueError(
                    "extended measurement shard is outside its manifest"
                )


def run_extended_emission_measurement_stage(  # noqa: PLR0913
    source: _WindowReadable,
    detection: DetectionStageResult,
    islands: tuple[PartitionedDeferredIsland, ...],
    manifest: PartitionManifest,
    *,
    config: ExtendedEmissionMeasurementConfig,
    geometry: ExtendedMeasurementGeometry,
    executor: Executor,
    sink: ZarrProductSink,
) -> ExtendedEmissionMeasurementStageResult:
    """Measure deferred emission through bounded nearest-owned core tasks."""
    _validate_extended_stage_inputs(detection, islands, manifest, sink)
    if not islands:
        return ExtendedEmissionMeasurementStageResult(
            measurements=(),
            planned_tile_count=0,
            maximum_task_pixels=0,
            maximum_request_shards=0,
            flux_uncertainty_available_count=0,
            truncated_measurement_count=0,
        )
    requests = _plan_extended_requests(
        islands,
        manifest,
        config=config,
        geometry=geometry,
    )
    measure = partial(
        _measure_extended_request,
        source=source,
        sink=sink,
        config=config,
        geometry=geometry,
    )
    partials = tuple(
        partial
        for batch in executor.map_batches(measure, requests)
        for partial in batch
    )
    measurements = combine_extended_emission_partials(
        _measurement_targets(islands),
        partials,
        geometry,
        config,
        image_shape_yx=manifest.image_shape_yx,
    )
    return ExtendedEmissionMeasurementStageResult(
        measurements=measurements,
        planned_tile_count=len(requests),
        maximum_task_pixels=max(
            request.read_bounds.shape_yx[0] * request.read_bounds.shape_yx[1]
            for request in requests
        ),
        maximum_request_shards=max(
            sum(len(item.shards) for item in request.targets)
            for request in requests
        ),
        flux_uncertainty_available_count=sum(
            isinstance(item, MeasuredExtendedEmission) for item in measurements
        ),
        truncated_measurement_count=sum(
            item.truncation.status != "none" for item in measurements
        ),
    )
