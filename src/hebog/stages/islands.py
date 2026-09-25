# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Scheduler-facing rounds that measure one catalogue row per island.

ADR-008's island round is the one object round whose objects are mask
connectivity rather than owner support: an island is a connected region of the
published retained mask, so it spans tiles exactly as a label plane does and is
reconciled the same way. Its labels are never published, because only these
rounds read them, and an island's own bounds hold it entirely, so the round
that measures it recovers it by labelling its own window.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from numbers import Integral
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import label as connected_component_labels

from hebog.algorithms.detection import DetectionThresholdMasks
from hebog.algorithms.labelling import (
    LocalIslandTile,
    LocalIslandTileSummary,
    label_detection_tile,
)
from hebog.algorithms.reconciliation import (
    DetectedIsland,
    TileLabelMapping,
    reconcile_candidate_tiles,
)
from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.executors.base import Executor
from hebog.io.base import ImageWindow
from hebog.science.catalogues import (
    detection_island_identifier,
    island_ids_by_owner,
    measure_detection_island,
)
from hebog.science.models import CatalogueIsland


class _WindowReadable(Protocol):
    """Read bounded global image windows without scheduler state."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


class _CompletedProductSource(Protocol):
    """Read checksum-validated windows from one published generation."""

    @property
    def manifest(self) -> PartitionManifest:
        """Return the canonical partition the generation was written on."""
        ...

    def access_session(self) -> AbstractContextManager[None]:
        """Hold one bounded read session open for a batch of windows."""
        ...

    def read_generation(self) -> ProductGenerationManifest:
        """Return the published generation this source reads."""
        ...

    def read_completed_window(
        self,
        product_name: str,
        bounds: ImageBounds,
    ) -> npt.NDArray[np.generic]:
        """Read one checksum-validated bounded window."""
        ...


@dataclass(frozen=True, slots=True)
class DetectionIslandStageConfig:
    """The reviewed beam area and the bounded task limits."""

    beam_area_pixels: float
    maximum_tiles_per_batch: int
    maximum_objects_per_batch: int
    maximum_batch_read_pixels: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before any round is submitted."""
        for name, value in (
            ("maximum_tiles_per_batch", self.maximum_tiles_per_batch),
            ("maximum_objects_per_batch", self.maximum_objects_per_batch),
            ("maximum_batch_read_pixels", self.maximum_batch_read_pixels),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")
        if (
            not np.isfinite(self.beam_area_pixels)
            or self.beam_area_pixels <= 0.0
        ):
            raise ValueError("beam_area_pixels must be finite and positive")


@dataclass(frozen=True, slots=True)
class DetectionIslandStageResult:
    """Every measured island, its owners, and scalar evidence."""

    islands: tuple[CatalogueIsland, ...]
    island_ids_by_owner: Mapping[int, tuple[str, ...]]
    island_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    maximum_island_read_pixels: int
    boundary_summary_array_bytes: int
    reconciliation_round_count: int


@dataclass(frozen=True, slots=True)
class _CoreBatch:
    """One bounded coarse executor task over several cores."""

    partitions: tuple[TilePartition, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.partitions:
            raise ValueError("island core batch must not be empty")


@dataclass(frozen=True, slots=True)
class _TileIslands:
    """One core's island topology and the owners its islands hold."""

    summary: LocalIslandTileSummary
    owner_pairs: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class _ScanBatchResult:
    """The topology one bounded batch of cores observed."""

    tiles: tuple[_TileIslands, ...]
    maximum_core_read_pixels: int
    summary_array_bytes: int


@dataclass(frozen=True, slots=True)
class _Island:
    """One reconciled island and the window that measures it."""

    global_label: int
    first_pixel_yx: tuple[int, int]
    pixel_count: int
    bounds: ImageBounds


@dataclass(frozen=True, slots=True)
class _IslandBatch:
    """One bounded coarse executor task over several islands."""

    islands: tuple[_Island, ...]
    read_bounds: ImageBounds

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.islands:
            raise ValueError("island row batch must not be empty")


@dataclass(frozen=True, slots=True)
class _RowBatchResult:
    """The rows one bounded batch of islands measured."""

    rows: tuple[tuple[int, CatalogueIsland], ...]
    maximum_island_read_pixels: int


def _core_batches(
    partitions: tuple[TilePartition, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_CoreBatch, ...]:
    """Group cores into bounded coarse tasks."""
    return tuple(
        _CoreBatch(
            partitions=tuple(
                partitions[start : start + maximum_tiles_per_batch]
            )
        )
        for start in range(0, len(partitions), maximum_tiles_per_batch)
    )


def _label_core(
    mask: npt.NDArray[np.bool_],
    partition: TilePartition,
    *,
    image_shape_yx: tuple[int, int],
) -> LocalIslandTile:
    """Label one owned core of a mask whose members are all islands."""
    return label_detection_tile(
        DetectionThresholdMasks(
            normalized_residual=np.zeros(mask.shape, dtype=np.float64),
            island_membership=mask,
            detection_seeds=mask,
            valid_pixel_count=int(np.count_nonzero(mask)),
        ),
        partition,
        image_shape_yx=image_shape_yx,
    )


def _core_owner_pairs(
    island_labels: npt.NDArray[np.int32],
    owner_labels: npt.NDArray[np.int32],
) -> tuple[tuple[int, int], ...]:
    """Observe which local islands each owner's support reaches in one core.

    The pairs stay local: the reconciliation that names the islands has not
    run yet, so the driver maps them once every core has been observed.
    """
    selected = (island_labels > 0) & (owner_labels > 0)
    if not bool(np.any(selected)):
        return ()
    pairs = np.unique(
        np.column_stack((owner_labels[selected], island_labels[selected])),
        axis=0,
    )
    return tuple((int(owner), int(island)) for owner, island in pairs)


def _summary_array_bytes(summary: LocalIslandTileSummary) -> int:
    """Return the boundary-array bytes one compact summary carries."""
    boundaries = summary.boundary_labels
    return sum(
        array.nbytes
        for array in (
            boundaries.top,
            boundaries.bottom,
            boundaries.left,
            boundaries.right,
        )
    )


def _scan_islands(
    batch: _CoreBatch,
    *,
    publication_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    image_shape_yx: tuple[int, int],
) -> _ScanBatchResult:
    """Label each core's islands and observe the owners they hold."""
    with (
        publication_source.access_session(),
        component_source.access_session(),
    ):
        tiles: list[_TileIslands] = []
        maximum_read_pixels = 0
        summary_bytes = 0
        for partition in batch.partitions:
            bounds = partition.core_bounds
            retained = np.asarray(
                publication_source.read_completed_window(
                    "retained-mask",
                    bounds,
                ),
                dtype=np.bool_,
            )
            owners = np.asarray(
                component_source.read_completed_window(
                    "component-measurement-labels",
                    bounds,
                ),
                dtype=np.int32,
            )
            tile = _label_core(
                retained,
                partition,
                image_shape_yx=image_shape_yx,
            )
            tiles.append(
                _TileIslands(
                    summary=tile.compact_summary(),
                    owner_pairs=_core_owner_pairs(tile.labels, owners),
                )
            )
            maximum_read_pixels = max(
                maximum_read_pixels,
                int(np.prod(bounds.shape_yx)),
            )
            summary_bytes += _summary_array_bytes(tiles[-1].summary)
        return _ScanBatchResult(
            tiles=tuple(tiles),
            maximum_core_read_pixels=maximum_read_pixels,
            summary_array_bytes=summary_bytes,
        )


def _global_owner_pairs(
    tiles: tuple[_TileIslands, ...],
    mappings: tuple[TileLabelMapping, ...],
) -> tuple[tuple[int, int], ...]:
    """Name every core's owner-to-island observation globally, once.

    Raises:
        ValueError: If a core observed an island the reconciliation did not
            accept. Every retained pixel is an island member and an island
            owns at least one pixel, so this round admits no way to produce
            one.
    """
    global_labels = {
        (mapping.tile_id, local_label): global_label
        for mapping in mappings
        for local_label, global_label in zip(
            mapping.local_labels,
            mapping.global_labels,
            strict=True,
        )
    }
    pairs: set[tuple[int, int]] = set()
    for tile in tiles:
        tile_id = tile.summary.partition.tile_id
        for owner, local_label in tile.owner_pairs:
            global_label = global_labels[tile_id, local_label]
            if global_label == 0:
                raise ValueError(
                    "every island a core observed must be reconciled"
                )
            pairs.add((owner, global_label))
    return tuple(sorted(pairs))


def _islands(reconciled: tuple[DetectedIsland, ...]) -> tuple[_Island, ...]:
    """Bound every reconciled island in the window that measures it."""
    return tuple(
        _Island(
            global_label=island.global_label,
            first_pixel_yx=island.first_pixel_yx,
            pixel_count=island.pixel_count,
            bounds=island.bounds,
        )
        for island in reconciled
    )


def _union(first: ImageBounds, second: ImageBounds) -> ImageBounds:
    """Return the smallest bound holding both observations."""
    return ImageBounds(
        min(first.y_start, second.y_start),
        max(first.y_stop, second.y_stop),
        min(first.x_start, second.x_start),
        max(first.x_stop, second.x_stop),
    )


def _batch_bounds(islands: list[_Island]) -> ImageBounds:
    """Return the one read that serves every island in a batch."""
    bounds = islands[0].bounds
    for island in islands[1:]:
        bounds = _union(bounds, island.bounds)
    return bounds


def _island_batches(
    islands: tuple[_Island, ...],
    *,
    maximum_objects_per_batch: int,
    maximum_batch_read_pixels: int,
) -> tuple[_IslandBatch, ...]:
    """Group islands so one read serves several, within both budgets.

    Islands are visited in raster order of their windows, so a batch covers a
    compact region: the residual is assembled from storage chunks far larger
    than one island, and one read per island would decode the chunks its
    neighbours share again for each of them.
    """
    ordered = sorted(
        islands, key=lambda item: (item.bounds.y_start, item.bounds.x_start)
    )
    batches: list[_IslandBatch] = []
    grouped: list[_Island] = []
    for island in ordered:
        candidate = [*grouped, island]
        if grouped and (
            len(candidate) > maximum_objects_per_batch
            or int(np.prod(_batch_bounds(candidate).shape_yx))
            > maximum_batch_read_pixels
        ):
            batches.append(
                _IslandBatch(
                    islands=tuple(grouped),
                    read_bounds=_batch_bounds(grouped),
                )
            )
            grouped = [island]
            continue
        grouped = candidate
    if grouped:
        batches.append(
            _IslandBatch(
                islands=tuple(grouped), read_bounds=_batch_bounds(grouped)
            )
        )
    return tuple(batches)


def _crop(read: ImageBounds, window: ImageBounds) -> tuple[slice, slice]:
    """Return the slices selecting one window inside a wider read."""
    return (
        slice(window.y_start - read.y_start, window.y_stop - read.y_start),
        slice(window.x_start - read.x_start, window.x_stop - read.x_start),
    )


def _connected_components(
    mask: npt.NDArray[np.bool_],
) -> npt.NDArray[np.int32]:
    """Label one window's eight-connected components."""
    labels, _ = cast(
        "tuple[npt.NDArray[np.int32], int]",
        connected_component_labels(mask, np.ones((3, 3), dtype=np.int8)),
    )
    return labels


def _island_mask(
    retained: npt.NDArray[np.bool_],
    island: _Island,
) -> npt.NDArray[np.bool_]:
    """Recover one reconciled island inside the window that contains it.

    The window is the island's own global bounds, so every pixel it owns lies
    inside it and no other island can be connected to it there. The canonical
    first pixel names which local component it is.

    Raises:
        ValueError: If the window does not reproduce the reconciled island.
    """
    local = _connected_components(retained)
    identity = int(
        local[
            island.first_pixel_yx[0] - island.bounds.y_start,
            island.first_pixel_yx[1] - island.bounds.x_start,
        ]
    )
    if identity == 0:
        raise ValueError("detection island must own its canonical first pixel")
    mask = np.asarray(local == identity, dtype=np.bool_)
    if int(mask.sum()) != island.pixel_count:
        raise ValueError("detection island must match its reconciled extent")
    return mask


def _measure_islands(
    batch: _IslandBatch,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    publication_source: _CompletedProductSource,
    config: DetectionIslandStageConfig,
) -> _RowBatchResult:
    """Measure every island of one batch inside its own window."""
    with (
        background_rms_source.access_session(),
        publication_source.access_session(),
    ):
        bounds = batch.read_bounds
        window = source.read_window(bounds)
        if window.bounds != bounds:
            raise ValueError("image source returned different island bounds")
        background = np.asarray(
            background_rms_source.read_completed_window("background", bounds),
            dtype=np.float64,
        )
        residual = np.asarray(window.values, dtype=np.float64) - background
        rms = np.asarray(
            background_rms_source.read_completed_window("rms", bounds),
            dtype=np.float64,
        )
        retained = np.asarray(
            publication_source.read_completed_window("retained-mask", bounds),
            dtype=np.bool_,
        )
        rows = tuple(
            (
                island.global_label,
                measure_detection_island(
                    residual[_crop(bounds, island.bounds)],
                    rms[_crop(bounds, island.bounds)],
                    _island_mask(
                        retained[_crop(bounds, island.bounds)],
                        island,
                    ),
                    first_pixel_yx=island.first_pixel_yx,
                    beam_area_pixels=config.beam_area_pixels,
                ),
            )
            for island in batch.islands
        )
        return _RowBatchResult(
            rows=rows,
            maximum_island_read_pixels=int(np.prod(bounds.shape_yx)),
        )


def _require_island_inputs(
    background_rms_source: _CompletedProductSource,
    publication_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    manifest: PartitionManifest,
) -> None:
    """Check every identity before any round is submitted."""
    if manifest.halo_yx != (0, 0):
        raise ValueError("island cores are labelled without a halo")
    for product_source, names in (
        (background_rms_source, ("background", "rms")),
        (publication_source, ("retained-mask",)),
        (component_source, ("component-measurement-labels",)),
    ):
        if product_source.manifest.image_shape_yx != manifest.image_shape_yx:
            raise ValueError(
                "published generations must match the island image shape"
            )
        if not set(names).issubset(
            product_source.read_generation().product_names
        ):
            raise ValueError(
                "published generations must carry every island plane read"
            )


def run_detection_island_stage(  # noqa: PLR0913
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    publication_source: _CompletedProductSource,
    component_source: _CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: DetectionIslandStageConfig,
    executor: Executor,
) -> DetectionIslandStageResult:
    """Measure every island of the retained mask, each in its own window.

    Two rounds and one reconciliation: the cores label their own retained
    mask and observe which owners its islands hold, the fragments reconcile
    into islands numbered by canonical first pixel, and one task per batch of
    islands measures their rows. The round publishes no plane, because only
    these rounds read the island labels.
    """
    _require_island_inputs(
        background_rms_source,
        publication_source,
        component_source,
        manifest,
    )
    core_batches = _core_batches(
        manifest.tiles,
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    scan_results = tuple(
        executor.map_batches(
            partial(
                _scan_islands,
                publication_source=publication_source,
                component_source=component_source,
                image_shape_yx=manifest.image_shape_yx,
            ),
            core_batches,
        )
    )
    if not scan_results:
        raise ValueError("executor returned no island topology results")
    tiles = tuple(tile for result in scan_results for tile in result.tiles)
    reconciled = reconcile_candidate_tiles(
        manifest,
        tuple(tile.summary for tile in tiles),
    )
    islands = _islands(reconciled.islands)
    identifier_by_island_label = {
        island.global_label: detection_island_identifier(island.first_pixel_yx)
        for island in islands
    }
    row_batches = _island_batches(
        islands,
        maximum_objects_per_batch=config.maximum_objects_per_batch,
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
    )
    row_results: tuple[_RowBatchResult, ...] = ()
    if row_batches:
        row_results = tuple(
            executor.map_batches(
                partial(
                    _measure_islands,
                    source=source,
                    background_rms_source=background_rms_source,
                    publication_source=publication_source,
                    config=config,
                ),
                row_batches,
            )
        )
        if not row_results:
            raise ValueError("executor returned no island row results")
    return DetectionIslandStageResult(
        islands=tuple(
            row
            for _, row in sorted(
                (item for result in row_results for item in result.rows),
                key=lambda item: item[0],
            )
        ),
        island_ids_by_owner=island_ids_by_owner(
            _global_owner_pairs(tiles, reconciled.tile_mappings),
            identifier_by_island_label=identifier_by_island_label,
        ),
        island_count=len(islands),
        partition_count=len(manifest.tiles),
        executor_task_count=len(core_batches) + len(row_batches),
        maximum_graph_width=max(len(core_batches), len(row_batches)),
        maximum_island_read_pixels=max(
            (result.maximum_island_read_pixels for result in row_results),
            default=0,
        ),
        boundary_summary_array_bytes=sum(
            result.summary_array_bytes for result in scan_results
        ),
        reconciliation_round_count=reconciled.reduction_round_count,
    )
