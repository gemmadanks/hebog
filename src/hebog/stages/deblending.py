"""Bounded executor orchestration for compact-island deblending."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Protocol, runtime_checkable

import numpy as np

from hebog.algorithms.deblending import (
    CompactDeblendBatch,
    CompactDeblendSummary,
    CompactIslandPixels,
    DeferredDeblendIsland,
    deblend_compact_batch,
    plan_compact_deblend_batches,
)
from hebog.algorithms.detection import normalize_residual
from hebog.config import CompactDeblendConfig
from hebog.data_models.partitioning import ImageBounds
from hebog.executors.base import Executor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.stages.detection import DetectionStageResult


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


def _deblend_batch(
    batch: CompactDeblendBatch,
    *,
    source: _WindowReadable,
    sink: ZarrProductSink,
    config: CompactDeblendConfig,
) -> tuple[CompactDeblendSummary, ...]:
    """Read admitted Zarr windows and return no pixel arrays to the caller."""
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
    compact_inputs: list[CompactIslandPixels] = []
    for island, window, background, rms, membership in zip(
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
        normalized, validity = normalize_residual(
            window.values,
            window.valid_pixels,
            np.asarray(background, dtype=np.float64),
            np.asarray(rms, dtype=np.float64),
        )
        normalized_membership = np.asarray(membership, dtype=np.bool_)
        if np.any(normalized_membership & ~validity):
            raise ValueError("source-filtering mask contains an invalid pixel")
        compact_inputs.append(
            CompactIslandPixels(
                island=island,
                normalized_residual=normalized,
                island_membership=normalized_membership,
            )
        )
    return tuple(
        result.compact_summary()
        for result in deblend_compact_batch(tuple(compact_inputs), config)
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
