"""Bounded executor orchestration for compact-island deblending."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Generic, Protocol, TypeVar, runtime_checkable

import numpy as np
import numpy.typing as npt

from hebog.algorithms.deblending import (
    CompactDeblendBatch,
    CompactDeblendResult,
    CompactDeblendSummary,
    CompactIslandPixels,
    DeblendedRegion,
    DeferredDeblendIsland,
    deblend_compact_island,
    extract_island_membership,
    plan_compact_deblend_batches,
)
from hebog.algorithms.detection import normalize_residual
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactDeblendConfig
from hebog.data_models.partitioning import ImageBounds
from hebog.executors.base import Executor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.stages.detection import DetectionStageResult

Record = TypeVar("Record")


class _WindowReadable(Protocol):
    """Read one bounded image window for an admitted island batch."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


@runtime_checkable
class _MultiWindowReadable(Protocol):
    """Read several bounded windows through one source operation."""

    def read_windows(
        self,
        bounds_collection: tuple[ImageBounds, ...],
    ) -> tuple[ImageWindow, ...]:
        """Read ordered globally bounded image windows."""
        ...


@dataclass(frozen=True, slots=True)
class CompactDeblendStageResult:
    """Compact summaries and explicit later-phase deferrals."""

    islands: tuple[CompactDeblendSummary, ...]
    deferred_islands: tuple[DeferredDeblendIsland, ...]
    planned_batch_count: int
    admitted_bounds_pixel_count: int


@dataclass(frozen=True, slots=True)
class WorkerLocalDeblendedIsland:
    """Exact bounded Phase 4 input that never crosses the executor boundary."""

    island: DetectedIsland
    regions: tuple[DeblendedRegion, ...]
    physical_residual: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    valid_pixels: npt.NDArray[np.bool_]
    region_labels: npt.NDArray[np.int32]

    def __post_init__(self) -> None:
        """Require aligned immutable arrays and exact region ownership."""
        self._validate_arrays()
        self._validate_scientific_pixels()
        self._validate_region_summaries()

    def _validate_arrays(self) -> None:
        """Require exact shapes, dtypes, and immutable worker ownership."""
        expected_shape = self.island.bounds.shape_yx
        arrays = (
            self.physical_residual,
            self.rms,
            self.valid_pixels,
            self.region_labels,
        )
        if any(array.shape != expected_shape for array in arrays):
            raise ValueError("worker-local region arrays must match bounds")
        if self.physical_residual.dtype != np.dtype(np.float64):
            raise TypeError("physical residual must be float64")
        if self.rms.dtype != np.dtype(np.float64):
            raise TypeError("worker-local RMS must be float64")
        if self.valid_pixels.dtype != np.dtype(np.bool_):
            raise TypeError("worker-local validity must be boolean")
        if self.region_labels.dtype != np.dtype(np.int32):
            raise TypeError("worker-local region labels must be int32")
        if any(array.flags.writeable for array in arrays):
            raise ValueError("worker-local region arrays must be read-only")

    def _validate_scientific_pixels(self) -> None:
        """Require every owned measurement pixel to be scientifically valid."""
        membership = self.region_labels > 0
        if np.any(membership & ~self.valid_pixels):
            raise ValueError("region membership contains an invalid pixel")
        if (
            not np.all(np.isfinite(self.physical_residual[membership]))
            or not np.all(np.isfinite(self.rms[membership]))
            or np.any(self.rms[membership] <= 0)
        ):
            raise ValueError(
                "region measurement planes are scientifically invalid"
            )

    def _validate_region_summaries(self) -> None:
        """Bind compact summaries to exact labels and their parent island."""
        expected_labels = {region.region_label for region in self.regions}
        observed_labels = set(np.unique(self.region_labels)) - {0}
        if observed_labels != expected_labels:
            raise ValueError("region summaries disagree with exact labels")
        if any(
            region.island_id != self.island.island_id
            or int(np.count_nonzero(self.region_labels == region.region_label))
            != region.pixel_count
            for region in self.regions
        ):
            raise ValueError(
                "region pixel counts or parent identities disagree"
            )

    @property
    def array_byte_count(self) -> int:
        """Return exact retained array bytes visible to the processor."""
        return sum(
            array.nbytes
            for array in (
                self.physical_residual,
                self.rms,
                self.valid_pixels,
                self.region_labels,
            )
        )


@dataclass(frozen=True, slots=True)
class WorkerLocalRegionBatch:
    """One coarse batch retaining exact labels only inside its worker task."""

    islands: tuple[WorkerLocalDeblendedIsland, ...]
    admitted_bounds_pixel_count: int

    def __post_init__(self) -> None:
        """Bind retained work to the planner's admitted bounds budget."""
        expected = sum(
            item.island.bounds.shape_yx[0] * item.island.bounds.shape_yx[1]
            for item in self.islands
        )
        if expected != self.admitted_bounds_pixel_count:
            raise ValueError(
                "worker-local batch disagrees with admitted bounds"
            )

    @property
    def array_byte_count(self) -> int:
        """Return exact retained array bytes passed to one processor call."""
        return sum(item.array_byte_count for item in self.islands)


@dataclass(frozen=True, slots=True)
class CompactRegionStageResult(Generic[Record]):
    """Compact processor records plus topology and bounded-work evidence."""

    records: tuple[Record, ...]
    islands: tuple[CompactDeblendSummary, ...]
    deferred_islands: tuple[DeferredDeblendIsland, ...]
    planned_batch_count: int
    admitted_bounds_pixel_count: int
    maximum_processor_array_bytes: int


@dataclass(frozen=True, slots=True)
class _ProcessedRegionBatch(Generic[Record]):
    """Scheduler-safe output from one worker-local region processor."""

    records: tuple[Record, ...]
    summaries: tuple[CompactDeblendSummary, ...]
    processor_array_bytes: int


@dataclass(frozen=True, slots=True)
class _BoundedIslandInputs:
    """Aligned source and product windows for one admitted island."""

    island: DetectedIsland
    window: ImageWindow
    background: npt.NDArray[np.generic]
    rms: npt.NDArray[np.generic]
    accepted_mask: npt.NDArray[np.generic]


def _read_window(
    source: _WindowReadable,
    bounds: ImageBounds,
) -> ImageWindow:
    """Read and validate one exact compact-island bounds region."""
    window = source.read_window(bounds)
    if window.bounds != bounds:
        raise ValueError("image source returned different island bounds")
    if (
        window.values.shape != bounds.shape_yx
        or window.valid_pixels.shape != bounds.shape_yx
    ):
        raise ValueError("image source returned a misaligned island window")
    return window


def _read_admitted_batch(
    batch: CompactDeblendBatch,
    *,
    source: _WindowReadable,
    sink: ZarrProductSink,
    config: CompactDeblendConfig,
) -> tuple[_BoundedIslandInputs, ...]:
    """Read only the five bounded inputs required by compact processing."""
    if batch.estimated_pixel_count > config.maximum_batch_pixels:
        raise ValueError("compact region batch exceeds its admitted limit")
    bounds_collection = tuple(island.bounds for island in batch.islands)
    if isinstance(source, _MultiWindowReadable):
        source_windows = source.read_windows(bounds_collection)
    else:
        source_windows = tuple(
            _read_window(source, bounds) for bounds in bounds_collection
        )
    backgrounds = sink.read_completed_windows(
        "background",
        bounds_collection,
    )
    rms_planes = sink.read_completed_windows("rms", bounds_collection)
    memberships = sink.read_completed_windows(
        "source-filtering-mask",
        bounds_collection,
    )
    inputs: list[_BoundedIslandInputs] = []
    for island, window, background, rms, accepted_mask in zip(
        batch.islands,
        source_windows,
        backgrounds,
        rms_planes,
        memberships,
        strict=True,
    ):
        bounds = island.bounds
        if window.bounds != bounds:
            raise ValueError("image source returned different island bounds")
        if (
            window.values.shape != bounds.shape_yx
            or window.valid_pixels.shape != bounds.shape_yx
        ):
            raise ValueError(
                "image source returned a misaligned island window"
            )
        inputs.append(
            _BoundedIslandInputs(
                island=island,
                window=window,
                background=np.asarray(background),
                rms=np.asarray(rms),
                accepted_mask=np.asarray(accepted_mask),
            )
        )
    return tuple(inputs)


def _deblend_inputs(
    inputs: _BoundedIslandInputs,
    config: CompactDeblendConfig,
) -> tuple[CompactDeblendResult, npt.NDArray[np.bool_]]:
    """Normalize and deblend one bounded input without retaining its SNR."""
    normalized, validity = normalize_residual(
        inputs.window.values,
        inputs.window.valid_pixels,
        np.asarray(inputs.background, dtype=np.float64),
        np.asarray(inputs.rms, dtype=np.float64),
    )
    exact_membership = extract_island_membership(
        inputs.island,
        inputs.accepted_mask,
    )
    if np.any(exact_membership & ~validity):
        raise ValueError("source-filtering mask contains an invalid pixel")
    return (
        deblend_compact_island(
            CompactIslandPixels(
                island=inputs.island,
                normalized_residual=normalized,
                island_membership=exact_membership,
            ),
            config,
        ),
        validity,
    )


def _prepare_worker_local_batch(
    batch: CompactDeblendBatch,
    *,
    source: _WindowReadable,
    sink: ZarrProductSink,
    config: CompactDeblendConfig,
) -> WorkerLocalRegionBatch:
    """Retain physical planes and exact labels for one processor call."""
    worker_islands: list[WorkerLocalDeblendedIsland] = []
    for inputs in _read_admitted_batch(
        batch,
        source=source,
        sink=sink,
        config=config,
    ):
        deblended, validity = _deblend_inputs(inputs, config)
        bounds = inputs.island.bounds
        physical_residual = np.full(bounds.shape_yx, np.nan, dtype=np.float64)
        np.subtract(
            np.asarray(inputs.window.values, dtype=np.float64),
            np.asarray(inputs.background, dtype=np.float64),
            out=physical_residual,
            where=validity,
        )
        rms_array = np.asarray(inputs.rms, dtype=np.float64)
        physical_residual.setflags(write=False)
        rms_array.setflags(write=False)
        worker_islands.append(
            WorkerLocalDeblendedIsland(
                island=inputs.island,
                regions=deblended.regions,
                physical_residual=physical_residual,
                rms=rms_array,
                valid_pixels=validity,
                region_labels=deblended.region_labels,
            )
        )
    return WorkerLocalRegionBatch(
        islands=tuple(worker_islands),
        admitted_bounds_pixel_count=batch.estimated_pixel_count,
    )


def _deblend_batch(
    batch: CompactDeblendBatch,
    *,
    source: _WindowReadable,
    sink: ZarrProductSink,
    config: CompactDeblendConfig,
) -> tuple[CompactDeblendSummary, ...]:
    """Return summaries while keeping exact label arrays inside the worker."""
    inputs = _read_admitted_batch(
        batch,
        source=source,
        sink=sink,
        config=config,
    )
    return tuple(
        _deblend_inputs(item, config)[0].compact_summary() for item in inputs
    )


def _process_region_batch(
    batch: CompactDeblendBatch,
    *,
    source: _WindowReadable,
    sink: ZarrProductSink,
    config: CompactDeblendConfig,
    processor: Callable[[WorkerLocalRegionBatch], tuple[Record, ...]],
) -> _ProcessedRegionBatch[Record]:
    """Run one processor before any exact pixel arrays leave its worker."""
    worker_batch = _prepare_worker_local_batch(
        batch,
        source=source,
        sink=sink,
        config=config,
    )
    records = processor(worker_batch)
    summaries = tuple(
        CompactDeblendSummary(
            island_id=item.island.island_id,
            status="deblended" if len(item.regions) > 1 else "single-region",
            regions=item.regions,
        )
        for item in worker_batch.islands
    )
    return _ProcessedRegionBatch(
        records=records,
        summaries=summaries,
        processor_array_bytes=worker_batch.array_byte_count,
    )


def run_compact_deblend_stage(
    source: _WindowReadable,
    detection: DetectionStageResult,
    config: CompactDeblendConfig,
    executor: Executor,
    sink: ZarrProductSink,
) -> CompactDeblendStageResult:
    """Deblend admitted islands from validated Zarr windows in batches."""
    generation = detection.generation
    if (
        generation.partition_manifest != sink.manifest
        or generation.generation_id != sink.generation_id
    ):
        raise ValueError(
            "deblend sink does not match the detection generation"
        )
    plan = plan_compact_deblend_batches(detection.islands, config)
    deblend = partial(
        _deblend_batch,
        source=source,
        sink=sink,
        config=config,
    )
    batch_results = executor.map_batches(deblend, plan.batches)
    summaries = tuple(
        summary for batch_result in batch_results for summary in batch_result
    )
    expected_ids = tuple(
        island.island_id for batch in plan.batches for island in batch.islands
    )
    if tuple(summary.island_id for summary in summaries) != expected_ids:
        raise ValueError(
            "deblend executor returned noncanonical island results"
        )
    return CompactDeblendStageResult(
        islands=summaries,
        deferred_islands=plan.deferred_islands,
        planned_batch_count=len(plan.batches),
        admitted_bounds_pixel_count=sum(
            batch.estimated_pixel_count for batch in plan.batches
        ),
    )


def run_compact_region_stage(  # noqa: PLR0913
    source: _WindowReadable,
    detection: DetectionStageResult,
    config: CompactDeblendConfig,
    *,
    processor: Callable[[WorkerLocalRegionBatch], tuple[Record, ...]],
    executor: Executor,
    sink: ZarrProductSink,
) -> CompactRegionStageResult[Record]:
    """Process exact deblended membership inside existing coarse tasks.

    The processor receives immutable bounded physical-residual, RMS, validity,
    and label arrays. It must reduce those arrays to compact typed records;
    only those records and deblending summaries cross the executor boundary.
    """
    generation = detection.generation
    if (
        generation.partition_manifest != sink.manifest
        or generation.generation_id != sink.generation_id
    ):
        raise ValueError("region sink does not match the detection generation")
    plan = plan_compact_deblend_batches(detection.islands, config)
    process = partial(
        _process_region_batch,
        source=source,
        sink=sink,
        config=config,
        processor=processor,
    )
    batch_results = executor.map_batches(process, plan.batches)
    summaries = tuple(
        summary
        for batch_result in batch_results
        for summary in batch_result.summaries
    )
    expected_ids = tuple(
        island.island_id for batch in plan.batches for island in batch.islands
    )
    if tuple(summary.island_id for summary in summaries) != expected_ids:
        raise ValueError(
            "region executor returned noncanonical island results"
        )
    return CompactRegionStageResult(
        records=tuple(
            record
            for batch_result in batch_results
            for record in batch_result.records
        ),
        islands=summaries,
        deferred_islands=plan.deferred_islands,
        planned_batch_count=len(plan.batches),
        admitted_bounds_pixel_count=sum(
            batch.estimated_pixel_count for batch in plan.batches
        ),
        maximum_processor_array_bytes=max(
            (
                batch_result.processor_array_bytes
                for batch_result in batch_results
            ),
            default=0,
        ),
    )
