# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Component fits: every fit parent measured in its own context window.

The measuring round also describes the direct components each parent owns,
and the cores then write each measured parent's persistent support.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import partial
from numbers import Integral

import numpy as np
import numpy.typing as npt

from hebog.algorithms.astrometry import (
    celestial_wcs_from_header_text,
    compact_geometries_from_wcs,
)
from hebog.algorithms.component_measurement import (
    FitParentMeasurement,
    compact_window_is_admitted,
    fit_parent_margin_pixels,
    fit_parent_measurement_support,
    measure_fit_parent_components,
)
from hebog.algorithms.component_records import (
    build_detection_component_record,
    build_detection_component_records,
)
from hebog.algorithms.multiscale import ResidualAtrousPlan
from hebog.config import (
    CompactGaussianFitConfig,
    CompactMomentConfig,
)
from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.images import RestoringBeam
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import ProductChunk
from hebog.data_models.source_association import DetectionComponentRecord
from hebog.executors.base import Executor
from hebog.io.base import CompletedProductSource, WindowReadable
from hebog.io.zarr import ZarrProductSink
from hebog.stages.batching import (
    batch_object_windows,
    map_round,
    read_pixels,
)
from hebog.stages.object_extents import (
    EXTENT_SCAN_BYTES_PER_READ_PIXEL,
    CoreExtent,
    ExtentBatchResult,
    bounds_intersect,
    core_label_extents,
    crop_slices,
    parent_holders,
    reduce_extents,
)
from hebog.stages.task_memory import read_requirement

# Each round's cost per pixel of its largest read, which a task declares
# (``hebog.stages.task_memory``): the largest traced task peak over that read
# on the 3,000-, 10,000- and 15,402-pixel LoTSS-DR3 anchors and the dense
# ELAIS-N1 central 5,000 pixels, rounded up to eight bytes (plan task 17).
_FIT_BYTES_PER_READ_PIXEL = 128
# No anchor held a deferred fit parent, so this round takes the cost of the
# component fits it stands in for.
_DEFERRED_BYTES_PER_READ_PIXEL = 128
_SUPPORT_PUBLICATION_BYTES_PER_READ_PIXEL = 80


_MEASUREMENT_PRODUCT_NAMES = ("measurement-support",)


def component_fit_product_names() -> tuple[str, ...]:
    """Return the canonical published component-fit product set."""
    return _MEASUREMENT_PRODUCT_NAMES


@dataclass(frozen=True, slots=True)
class ComponentFitStageConfig:
    """Reviewed measurement policy and the bounded task limits."""

    moment: CompactMomentConfig
    fit: CompactGaussianFitConfig
    atrous_plan: ResidualAtrousPlan
    detection_sigma: float
    island_sigma: float
    minimum_pixels: int
    maximum_bounds_pixels: int
    minimum_support_fraction: float
    maximum_tiles_per_batch: int
    maximum_batch_read_pixels: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before stage products are initialized."""
        for name, value in (
            ("maximum_tiles_per_batch", self.maximum_tiles_per_batch),
            ("maximum_batch_read_pixels", self.maximum_batch_read_pixels),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")

    @property
    def margin_pixels(self) -> int:
        """Return the context a fit parent reads beyond its own support."""
        return fit_parent_margin_pixels(self.fit, self.atrous_plan)


@dataclass(frozen=True, slots=True)
class ComponentFitStageResult:
    """Published measurement support and every fit parent's records.

    ``component_records`` describes every direct component the association
    decision reads, in canonical first-pixel order. The parent that reads a
    component's pixels builds it: the residual, the validity and both
    component planes are already on that task, so nothing after the fits
    reads a component's window again.
    """

    generation: ProductGenerationManifest
    parents: tuple[FitParentMeasurement, ...]
    component_records: tuple[DetectionComponentRecord, ...]
    fit_parent_count: int
    deferred_parent_count: int
    wide_parent_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    maximum_parent_read_pixels: int
    parent_batch_count: int


@dataclass(frozen=True, slots=True)
class _FitParentExtent:
    """One fit parent's support bounds and the window that measures it."""

    parent_index: int
    read_bounds: ImageBounds


@dataclass(frozen=True, slots=True)
class _FitBatch:
    """One bounded coarse executor task over several fit parents."""

    parents: tuple[_FitParentExtent, ...]
    read_bounds: ImageBounds

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.parents:
            raise ValueError("fit batch must not be empty")


@dataclass(frozen=True, slots=True)
class _FitBatchResult:
    """Bounded measurement records one batch of fit parents produced."""

    parents: tuple[tuple[int, FitParentMeasurement], ...]
    component_records: tuple[DetectionComponentRecord, ...]
    maximum_parent_read_pixels: int


@dataclass(frozen=True, slots=True)
class _SupportRequest:
    """One core and the measured fit parents whose windows reach it."""

    partition: TilePartition
    parents: tuple[_FitParentExtent, ...]


@dataclass(frozen=True, slots=True)
class _SupportBatch:
    """One bounded coarse executor task over several cores."""

    requests: tuple[_SupportRequest, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.requests:
            raise ValueError("support batch must not be empty")


@dataclass(frozen=True, slots=True)
class _DeferredCore:
    """One core and the deferred fit parents whose components it holds."""

    partition: TilePartition
    parent_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _DeferredBatch:
    """One bounded coarse executor task over the cores of deferred parents."""

    cores: tuple[_DeferredCore, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.cores:
            raise ValueError("deferred component batch must not be empty")


@dataclass(frozen=True, slots=True)
class _ComponentPiece:
    """One component's direct pixels in one core, in raster order.

    ``raster_indices`` are global ``y * width + x`` positions, so pieces
    from several cores sort back into the order one window presents them in.
    """

    label_value: int
    raster_indices: npt.NDArray[np.int64]
    residual: npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class _DeferredBatchResult:
    """The deferred parents' component pixels one batch of cores held."""

    pieces: tuple[_ComponentPiece, ...]
    tile_ids: tuple[str, ...]
    maximum_core_read_pixels: int


def _scan_fit_parent_extents(
    batch: _SupportBatch,
    *,
    fit_parent_source: CompletedProductSource,
) -> ExtentBatchResult:
    """Observe every fit parent's extent inside the cores of one batch."""
    extents: list[CoreExtent] = []
    for request in batch.requests:
        bounds = request.partition.core_bounds
        for parent_index, (
            parent_bounds,
            first,
            pixel_count,
        ) in core_label_extents(
            np.asarray(
                fit_parent_source.read_completed_window(
                    "fit-parent-labels",
                    bounds,
                ),
                dtype=np.int32,
            ),
            bounds,
        ).items():
            extents.append(
                CoreExtent(
                    parent_label=parent_index,
                    direct_bounds=parent_bounds,
                    measurement_bounds=parent_bounds,
                    first_pixel_yx=first,
                    tile_id=request.partition.tile_id,
                    direct_pixel_count=pixel_count,
                )
            )
    return ExtentBatchResult(extents=tuple(extents))


def _fit_batches(
    parents: tuple[_FitParentExtent, ...],
    *,
    maximum_batch_read_pixels: int,
    maximum_bounds_pixels: int,
) -> tuple[_FitBatch, ...]:
    """Group fit parents so one read serves several, within the budget.

    A joint fit needs a parent's whole window at once, and no core can stand
    in for it. The reviewed compact bound limits that window: a parent beyond
    it is deferred and never reaches a batch. So a parent wider than the
    read budget is read alone, and its read is bounded by that admission,
    not by the image.

    Raises:
        ValueError: If a parent beyond the reviewed bound reaches a batch,
            which would leave its read bounded by nothing.
    """
    return tuple(
        _FitBatch(parents=batch.objects, read_bounds=batch.read_bounds)
        for batch in batch_object_windows(
            parents,
            window=lambda parent: parent.read_bounds,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
            bounded_by_admission=lambda parent: compact_window_is_admitted(
                parent.read_bounds,
                maximum_bounds_pixels=maximum_bounds_pixels,
            ),
        )
    )


def _fit_batch(  # noqa: PLR0913
    batch: _FitBatch,
    *,
    source: WindowReadable,
    background_rms_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    component_source: CompletedProductSource,
    fit_parent_source: CompletedProductSource,
    config: ComponentFitStageConfig,
    wcs_header_text: str,
    beam: RestoringBeam,
    image_shape_yx: tuple[int, int],
) -> _FitBatchResult:
    """Fit every parent of one batch inside its own context window."""
    wcs = celestial_wcs_from_header_text(wcs_header_text)
    bounds = batch.read_bounds
    window = source.read_window(bounds)
    if window.bounds != bounds:
        raise ValueError("image source returned different fit-read bounds")
    background = np.asarray(
        background_rms_source.read_completed_window("background", bounds),
        dtype=np.float64,
    )
    residual = np.asarray(window.values, dtype=np.float64) - background
    rms = np.asarray(
        background_rms_source.read_completed_window("rms", bounds),
        dtype=np.float64,
    )
    valid = np.asarray(
        detection_source.read_completed_window("valid-pixels", bounds),
        dtype=np.bool_,
    )
    fit_parents = np.asarray(
        fit_parent_source.read_completed_window(
            "fit-parent-labels",
            bounds,
        ),
        dtype=np.int32,
    )
    direct = np.asarray(
        component_source.read_completed_window(
            "component-direct-labels",
            bounds,
        ),
        dtype=np.int32,
    )
    measurement = np.asarray(
        component_source.read_completed_window(
            "component-measurement-labels",
            bounds,
        ),
        dtype=np.int32,
    )
    # One conversion for the batch. Astropy pays its frame machinery per
    # call, not per position, so deriving each parent's geometry inside
    # the fit costs more than the fit does.
    geometries = compact_geometries_from_wcs(
        beam,
        wcs,
        tuple(parent.read_bounds.center_xy for parent in batch.parents),
    )
    measured: list[tuple[int, FitParentMeasurement]] = []
    records: list[DetectionComponentRecord] = []
    for parent, geometry in zip(batch.parents, geometries, strict=True):
        crop = crop_slices(bounds, parent.read_bounds)
        records.extend(
            _parent_component_records(
                residual[crop],
                valid[crop],
                fit_parents[crop],
                direct[crop],
                parent,
            )
        )
        measured.append(
            (
                parent.parent_index,
                measure_fit_parent_components(
                    residual[crop],
                    rms[crop],
                    valid[crop],
                    fit_parents[crop],
                    direct[crop],
                    measurement[crop],
                    geometry,
                    config.moment,
                    config.fit,
                    parent_index=parent.parent_index,
                    bounds=parent.read_bounds,
                    image_shape_yx=image_shape_yx,
                    detection_sigma=config.detection_sigma,
                    island_sigma=config.island_sigma,
                    minimum_pixels=config.minimum_pixels,
                    maximum_bounds_pixels=config.maximum_bounds_pixels,
                    atrous_plan=config.atrous_plan,
                    minimum_support_fraction=(config.minimum_support_fraction),
                ),
            )
        )
    return _FitBatchResult(
        parents=tuple(measured),
        component_records=tuple(records),
        maximum_parent_read_pixels=int(np.prod(bounds.shape_yx)),
    )


def _parent_component_records(
    residual_window: npt.NDArray[np.float64],
    valid_window: npt.NDArray[np.bool_],
    fit_parent_window: npt.NDArray[np.int32],
    direct_window: npt.NDArray[np.int32],
    parent: _FitParentExtent,
) -> tuple[DetectionComponentRecord, ...]:
    """Describe the direct components one fit parent owns, from its own read.

    Every array covers that parent's support and the reviewed context margin
    around it. A component's direct support lies inside the measurement
    support this parent was dilated from, so the window holds each owned
    component entirely and the record costs the component's own pixels. The
    margin can expose a neighbour's pixels, so only the components standing
    on this parent's support are described.
    """
    return build_detection_component_records(
        np.where(
            fit_parent_window == parent.parent_index,
            direct_window,
            0,
        ).astype(np.int32, copy=False),
        residual_window,
        valid_window,
        origin_yx=(parent.read_bounds.y_start, parent.read_bounds.x_start),
    )


def _deferred_batches(
    deferred: tuple[_FitParentExtent, ...],
    holders: dict[int, frozenset[str]],
    manifest: PartitionManifest,
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_DeferredBatch, ...]:
    """Name each core holding a deferred parent, and which parents it holds."""
    parents_by_tile: dict[str, list[int]] = {}
    for parent in deferred:
        for tile_id in holders[parent.parent_index]:
            parents_by_tile.setdefault(tile_id, []).append(parent.parent_index)
    cores = tuple(
        _DeferredCore(
            partition=partition,
            parent_indexes=tuple(sorted(parents_by_tile[partition.tile_id])),
        )
        for partition in manifest.tiles
        if partition.tile_id in parents_by_tile
    )
    return tuple(
        _DeferredBatch(cores=cores[start : start + maximum_tiles_per_batch])
        for start in range(0, len(cores), maximum_tiles_per_batch)
    )


def _gather_deferred_components(  # noqa: PLR0913
    batch: _DeferredBatch,
    *,
    source: WindowReadable,
    background_rms_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    component_source: CompletedProductSource,
    fit_parent_source: CompletedProductSource,
    image_width: int,
) -> _DeferredBatchResult:
    """Return the direct pixels of deferred parents' components, per core.

    A deferred parent is not fitted, so nothing needs its window: the record
    of each component it owns reads only that component's own pixels, which
    every core holding them returns with global raster indices.

    Raises:
        ValueError: If the image source answers with other bounds, or a
            component owns a pixel that is not scientifically valid.
    """
    pieces: list[_ComponentPiece] = []
    maximum_read_pixels = 0
    for core in batch.cores:
        bounds = core.partition.core_bounds
        window = source.read_window(bounds)
        if window.bounds != bounds:
            raise ValueError("image source returned different fit-read bounds")
        residual = np.asarray(window.values, dtype=np.float64) - np.asarray(
            background_rms_source.read_completed_window("background", bounds),
            dtype=np.float64,
        )
        valid = np.asarray(
            detection_source.read_completed_window("valid-pixels", bounds),
            dtype=np.bool_,
        )
        direct = np.asarray(
            component_source.read_completed_window(
                "component-direct-labels", bounds
            ),
            dtype=np.int32,
        )
        owned = (direct > 0) & np.isin(
            np.asarray(
                fit_parent_source.read_completed_window(
                    "fit-parent-labels", bounds
                ),
                dtype=np.int32,
            ),
            core.parent_indexes,
        )
        if bool(np.any(owned & ~valid)):
            raise ValueError(
                "component owner pixels must be scientifically valid"
            )
        rows, columns = np.nonzero(owned)
        labels = direct[rows, columns]
        raster_indices = (
            (rows.astype(np.int64) + bounds.y_start) * image_width
            + columns
            + bounds.x_start
        )
        values = residual[rows, columns]
        # Boolean selection keeps each component's pixels in the raster
        # order this core holds them in.
        for label_value in np.unique(labels):
            selected = labels == label_value
            pieces.append(
                _ComponentPiece(
                    label_value=int(label_value),
                    raster_indices=raster_indices[selected],
                    residual=values[selected],
                )
            )
        maximum_read_pixels = max(maximum_read_pixels, read_pixels(bounds))
    return _DeferredBatchResult(
        pieces=tuple(pieces),
        tile_ids=tuple(core.partition.tile_id for core in batch.cores),
        maximum_core_read_pixels=maximum_read_pixels,
    )


def _deferred_component_records(
    batches: tuple[_DeferredBatch, ...],
    results: tuple[_DeferredBatchResult, ...],
    *,
    image_width: int,
) -> tuple[DetectionComponentRecord, ...]:
    """Describe every component of a deferred parent from its cores' pieces.

    The pieces are put back in raster order, which is the order a window
    over the component presents its pixels, so each record is the one that
    window would build, bit for bit.

    Raises:
        ValueError: If a core that holds a deferred parent did not answer,
            which would describe its components from part of their pixels.
    """
    requested = {
        core.partition.tile_id for batch in batches for core in batch.cores
    }
    answered = {tile_id for result in results for tile_id in result.tile_ids}
    if answered != requested:
        raise ValueError(
            "every core holding a deferred fit parent must answer"
        )
    pieces: dict[int, list[_ComponentPiece]] = {}
    for result in results:
        for piece in result.pieces:
            pieces.setdefault(piece.label_value, []).append(piece)
    records: list[DetectionComponentRecord] = []
    for label_value, parts in sorted(pieces.items()):
        raster_indices = np.concatenate(
            [part.raster_indices for part in parts]
        )
        order = np.argsort(raster_indices, kind="stable")
        records.append(
            build_detection_component_record(
                label_value,
                raster_indices[order],
                np.concatenate([part.residual for part in parts])[order],
                image_width=image_width,
            )
        )
    return tuple(records)


@dataclass(frozen=True, slots=True)
class _SupportPublishResult:
    """Persisted support chunks and the widest window one core read."""

    product_chunks: tuple[ProductChunk, ...]
    maximum_parent_read_pixels: int


def _publish_support(  # noqa: PLR0913
    batch: _SupportBatch,
    *,
    source: WindowReadable,
    background_rms_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    fit_parent_source: CompletedProductSource,
    config: ComponentFitStageConfig,
    sink: ZarrProductSink,
) -> _SupportPublishResult:
    """Derive each measured parent's support again and write the core's share.

    The persistent measurement support a fit parent contributes is a
    function of the residual, the RMS, the validity and the fit-parent
    labels inside its own window, not of its fit, so every core the window
    reaches derives it from the published planes and keeps its own pixels.
    That costs the matched-filter bank once more for each further core a
    window crosses, and returns nothing that grows with a parent's area.

    Raises:
        ValueError: If the image source answers with other bounds.
    """
    chunks: list[ProductChunk] = []
    maximum_read_pixels = 0
    for request in batch.requests:
        core = request.partition.core_bounds
        values = np.zeros(core.shape_yx, dtype=np.bool_)
        for read in _fit_batches(
            request.parents,
            maximum_batch_read_pixels=config.maximum_batch_read_pixels,
            maximum_bounds_pixels=config.maximum_bounds_pixels,
        ):
            bounds = read.read_bounds
            window = source.read_window(bounds)
            if window.bounds != bounds:
                raise ValueError(
                    "image source returned different fit-read bounds"
                )
            residual = np.asarray(
                window.values, dtype=np.float64
            ) - np.asarray(
                background_rms_source.read_completed_window(
                    "background", bounds
                ),
                dtype=np.float64,
            )
            rms = np.asarray(
                background_rms_source.read_completed_window("rms", bounds),
                dtype=np.float64,
            )
            valid = np.asarray(
                detection_source.read_completed_window("valid-pixels", bounds),
                dtype=np.bool_,
            )
            fit_parents = np.asarray(
                fit_parent_source.read_completed_window(
                    "fit-parent-labels", bounds
                ),
                dtype=np.int32,
            )
            maximum_read_pixels = max(maximum_read_pixels, read_pixels(bounds))
            for parent in read.parents:
                crop = crop_slices(bounds, parent.read_bounds)
                support = fit_parent_measurement_support(
                    residual[crop],
                    rms[crop],
                    valid[crop],
                    fit_parents[crop],
                    parent_index=parent.parent_index,
                    atrous_plan=config.atrous_plan,
                    minimum_support_fraction=config.minimum_support_fraction,
                    detection_sigma=config.detection_sigma,
                    island_sigma=config.island_sigma,
                    minimum_pixels=config.minimum_pixels,
                )
                overlap = ImageBounds(
                    max(core.y_start, parent.read_bounds.y_start),
                    min(core.y_stop, parent.read_bounds.y_stop),
                    max(core.x_start, parent.read_bounds.x_start),
                    min(core.x_stop, parent.read_bounds.x_stop),
                )
                values[crop_slices(core, overlap)] |= support[
                    crop_slices(parent.read_bounds, overlap)
                ]
        chunks.append(
            sink.write_chunk(
                product_name="measurement-support",
                tile=request.partition,
                values=values,
            )
        )
    return _SupportPublishResult(
        product_chunks=tuple(chunks),
        maximum_parent_read_pixels=maximum_read_pixels,
    )


def _support_batches(
    requests: tuple[_SupportRequest, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_SupportBatch, ...]:
    """Group canonical cores without changing scientific ownership."""
    return tuple(
        _SupportBatch(
            requests=requests[start : start + maximum_tiles_per_batch]
        )
        for start in range(0, len(requests), maximum_tiles_per_batch)
    )


def _reduce_component_records(
    component_records: Iterable[DetectionComponentRecord],
    *,
    component_count: int,
) -> tuple[DetectionComponentRecord, ...]:
    """Order every parent's component records canonically, once.

    Completion order decides nothing: the records are sorted by canonical
    first pixel, which is how a whole-plane pass over the direct labels would
    present them. The topology stage numbered the direct components
    ``1..component_count`` and required both of its planes to name exactly
    those, so the records must describe each of them once.

    Raises:
        ValueError: If two fit parents described the same component, which
            would mean a component's support reached beyond the parent whose
            measurement support it belongs to, or if the records do not
            describe exactly the published components, which would mean a
            fit parent's read missed a component that the association would
            otherwise silently lose.
    """
    records = tuple(
        sorted(
            component_records,
            key=lambda record: record.canonical_pixel_yx,
        )
    )
    described = {record.label_value for record in records}
    if len(described) != len(records):
        raise ValueError("every component must belong to one fit parent")
    if described != set(range(1, component_count + 1)):
        raise ValueError("fit parents must describe every published component")
    return records


def run_component_fit_stage(  # noqa: PLR0913, PLR0917
    source: WindowReadable,
    background_rms_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    component_source: CompletedProductSource,
    fit_parent_source: CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: ComponentFitStageConfig,
    component_count: int,
    wcs_header_text: str,
    beam: RestoringBeam,
    executor: Executor,
    sink: ZarrProductSink,
) -> ComponentFitStageResult:
    """Fit every parent in its own context window and publish its support.

    Three rounds: the cores observe each fit parent's extent, one task per
    batch of parents measures them inside that extent plus the reviewed
    context margin, and the cores derive each measured parent's persistent
    support again inside that window and write their own pixels of it. Only
    the last round writes, and no round returns an array.

    The measuring round also describes the direct components each parent
    owns, because the residual and the validity those records need are
    already on the task that fits them.

    A parent whose window the reviewed compact bound refuses is deferred, as
    the whole-plane pass defers it, so its window is never read. Its
    components are described instead from the pixels each core holding them
    returns, restored to raster order, which gives the records a window would
    give, bit for bit. No read is then wider than the budget, one core, or
    one window that bound admits, whichever is largest.

    ``component_count`` is the count the topology stage that published
    ``component_source`` returned. The records must describe exactly those
    components, so a fit-parent read that misses one stops the stage rather
    than publishing fewer components.

    ``wcs_header_text`` is the caller's own header as
    :meth:`astropy.io.fits.Header.tostring` writes it, not a ``WCS``; see
    :func:`~hebog.algorithms.astrometry.celestial_wcs_from_header_text`.
    """
    if sink.manifest != manifest:
        raise ValueError("component fit sink must use the stage manifest")
    if manifest.halo_yx != (0, 0):
        raise ValueError("measurement support writes cores without a halo")
    for product_source, names in (
        (background_rms_source, ("background", "rms")),
        (detection_source, ("valid-pixels",)),
        (
            component_source,
            ("component-direct-labels", "component-measurement-labels"),
        ),
        (fit_parent_source, ("fit-parent-labels",)),
    ):
        if product_source.manifest.image_shape_yx != manifest.image_shape_yx:
            raise ValueError(
                "published generations must match the fit image shape"
            )
        if not set(names).issubset(
            product_source.read_generation().product_names
        ):
            raise ValueError(
                "published generations must carry every fit plane read"
            )
    image_shape_yx = manifest.image_shape_yx
    margin = config.margin_pixels
    scan_batches = _support_batches(
        tuple(
            _SupportRequest(partition=partition, parents=())
            for partition in manifest.tiles
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    scan_results = tuple(
        executor.map_batches(
            partial(
                _scan_fit_parent_extents,
                fit_parent_source=fit_parent_source,
            ),
            scan_batches,
            requirement=read_requirement(
                EXTENT_SCAN_BYTES_PER_READ_PIXEL,
                (partition.read_bounds for partition in manifest.tiles),
                chunk_shape_yx=manifest.tile_core_shape_yx,
            ),
        )
    )
    if not scan_results:
        raise ValueError("executor returned no fit-parent extent results")
    extents = tuple(
        _FitParentExtent(
            parent_index=parent.parent_label,
            read_bounds=parent.direct_bounds.expanded(margin, image_shape_yx),
        )
        for parent in sorted(
            reduce_extents(scan_results),
            key=lambda item: item.parent_label,
        )
    )
    fitted = tuple(
        extent
        for extent in extents
        if compact_window_is_admitted(
            extent.read_bounds,
            maximum_bounds_pixels=config.maximum_bounds_pixels,
        )
    )
    deferred = tuple(
        extent
        for extent in extents
        if not compact_window_is_admitted(
            extent.read_bounds,
            maximum_bounds_pixels=config.maximum_bounds_pixels,
        )
    )
    fit_batches = _fit_batches(
        fitted,
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
        maximum_bounds_pixels=config.maximum_bounds_pixels,
    )
    fit_results = map_round(
        executor,
        partial(
            _fit_batch,
            source=source,
            background_rms_source=background_rms_source,
            detection_source=detection_source,
            component_source=component_source,
            fit_parent_source=fit_parent_source,
            config=config,
            wcs_header_text=wcs_header_text,
            beam=beam,
            image_shape_yx=image_shape_yx,
        ),
        fit_batches,
        round_name="component fit",
        requirement=read_requirement(
            _FIT_BYTES_PER_READ_PIXEL,
            (batch.read_bounds for batch in fit_batches),
            chunk_shape_yx=manifest.tile_core_shape_yx,
        ),
    )
    deferred_batches = _deferred_batches(
        deferred,
        parent_holders(scan_results),
        manifest,
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    deferred_results = map_round(
        executor,
        partial(
            _gather_deferred_components,
            source=source,
            background_rms_source=background_rms_source,
            detection_source=detection_source,
            component_source=component_source,
            fit_parent_source=fit_parent_source,
            image_width=image_shape_yx[1],
        ),
        deferred_batches,
        round_name="deferred component",
        requirement=read_requirement(
            _DEFERRED_BYTES_PER_READ_PIXEL,
            (
                core.partition.read_bounds
                for batch in deferred_batches
                for core in batch.cores
            ),
            chunk_shape_yx=manifest.tile_core_shape_yx,
        ),
    )
    measured = tuple(
        sorted(
            (
                *(item for result in fit_results for item in result.parents),
                *(
                    (parent.parent_index, FitParentMeasurement(deferred=True))
                    for parent in deferred
                ),
            ),
            key=lambda item: item[0],
        )
    )
    component_records = _reduce_component_records(
        (
            *(
                record
                for result in fit_results
                for record in result.component_records
            ),
            *_deferred_component_records(
                deferred_batches,
                deferred_results,
                image_width=image_shape_yx[1],
            ),
        ),
        component_count=component_count,
    )
    # A parent the measurement deferred, by its bound or for want of a
    # seed, contributes no support, exactly as the whole-plane pass.
    contributing = {
        parent_index
        for parent_index, parent in measured
        if not parent.deferred
    }
    supported = tuple(
        extent for extent in fitted if extent.parent_index in contributing
    )
    sink.initialize_product(
        product_name="measurement-support",
        dtype=np.dtype(np.bool_),
    )
    publish_batches = _support_batches(
        tuple(
            _SupportRequest(
                partition=partition,
                parents=tuple(
                    extent
                    for extent in supported
                    if bounds_intersect(
                        extent.read_bounds, partition.core_bounds
                    )
                ),
            )
            for partition in manifest.tiles
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    publish_results = tuple(
        executor.map_batches(
            partial(
                _publish_support,
                source=source,
                background_rms_source=background_rms_source,
                detection_source=detection_source,
                fit_parent_source=fit_parent_source,
                config=config,
                sink=sink,
            ),
            publish_batches,
            requirement=read_requirement(
                _SUPPORT_PUBLICATION_BYTES_PER_READ_PIXEL,
                (
                    *(partition.read_bounds for partition in manifest.tiles),
                    *(extent.read_bounds for extent in supported),
                ),
                chunk_shape_yx=manifest.tile_core_shape_yx,
            ),
        )
    )
    if not publish_results:
        raise ValueError("executor returned no support publication results")
    return ComponentFitStageResult(
        generation=sink.publish_generation(
            product_names=_MEASUREMENT_PRODUCT_NAMES,
            chunks=(
                chunk
                for result in publish_results
                for chunk in result.product_chunks
            ),
        ),
        parents=tuple(parent for _, parent in measured),
        component_records=component_records,
        fit_parent_count=len(extents),
        deferred_parent_count=sum(
            int(parent.deferred) for _, parent in measured
        ),
        wide_parent_count=len(deferred),
        partition_count=len(manifest.tiles),
        executor_task_count=(
            len(scan_batches)
            + len(fit_batches)
            + len(deferred_batches)
            + len(publish_batches)
        ),
        maximum_graph_width=max(
            len(scan_batches),
            len(fit_batches),
            len(deferred_batches),
            len(publish_batches),
        ),
        maximum_parent_read_pixels=max(
            (
                *(result.maximum_parent_read_pixels for result in fit_results),
                *(
                    result.maximum_core_read_pixels
                    for result in deferred_results
                ),
                *(
                    result.maximum_parent_read_pixels
                    for result in publish_results
                ),
            ),
            default=0,
        ),
        parent_batch_count=len(fit_batches),
    )
