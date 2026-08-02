"""Scheduler-facing compact moment measurement stage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from hebog.algorithms.measurement import measure_compact_moments
from hebog.config import CompactDeblendConfig, CompactMomentConfig
from hebog.data_models.measurement import (
    CompactMeasurementGeometry,
    CompactMomentMeasurement,
)
from hebog.data_models.partitioning import ImageBounds
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
    """Read one bounded image window for compact measurement."""

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
