"""Scheduler-facing fit-all compact Gaussian stage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from hebog.algorithms.fitting import fit_compact_gaussian
from hebog.algorithms.measurement import measure_compact_moments
from hebog.config import (
    CompactDeblendConfig,
    CompactGaussianFitConfig,
    CompactMomentConfig,
)
from hebog.data_models.fitting import CompactIslandFitResult
from hebog.data_models.measurement import CompactMeasurementGeometry
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
    """Read one bounded image window for compact fitting."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


@dataclass(frozen=True, slots=True)
class CompactGaussianFitProcessor:
    """Pickleable fit-all processor for one existing coarse region task."""

    geometry: CompactMeasurementGeometry
    moment_config: CompactMomentConfig
    fit_config: CompactGaussianFitConfig

    def __call__(
        self,
        batch: WorkerLocalRegionBatch,
    ) -> tuple[CompactIslandFitResult, ...]:
        """Measure and fit every eligible region in canonical order."""
        records: list[CompactIslandFitResult] = []
        for compact_island in batch.islands:
            moments = measure_compact_moments(
                compact_island,
                self.geometry,
                self.moment_config,
            )
            region_moments = {
                moment.target.object_id: moment for moment in moments[1:]
            }
            records.append(
                CompactIslandFitResult(
                    island_measurement=moments[0],
                    region_fits=tuple(
                        fit_compact_gaussian(
                            compact_island,
                            region,
                            region_moments[region.region_id],
                            self.geometry,
                            self.fit_config,
                        )
                        for region in compact_island.regions
                    ),
                )
            )
        return tuple(records)


def run_compact_gaussian_fit_stage(  # noqa: PLR0913
    source: _WindowReadable,
    detection: DetectionStageResult,
    *,
    deblend_config: CompactDeblendConfig,
    moment_config: CompactMomentConfig,
    fit_config: CompactGaussianFitConfig,
    geometry: CompactMeasurementGeometry,
    executor: Executor,
    sink: ZarrProductSink,
) -> CompactRegionStageResult[CompactIslandFitResult]:
    """Run fit-all compact measurement inside bounded coarse tasks."""
    return run_compact_region_stage(
        source,
        detection,
        deblend_config,
        processor=CompactGaussianFitProcessor(
            geometry=geometry,
            moment_config=moment_config,
            fit_config=fit_config,
        ),
        executor=executor,
        sink=sink,
        context_margin_pixels=fit_config.context_margin_pixels,
    )
