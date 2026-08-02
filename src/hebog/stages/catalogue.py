"""Scheduler-facing compact catalogue-shard construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from hebog.algorithms.catalogue import build_compact_catalogue_shard
from hebog.config import (
    CompactCatalogueConfig,
    CompactDeblendConfig,
    CompactGaussianFitConfig,
    CompactMomentConfig,
)
from hebog.data_models.catalogue_construction import CompactCatalogueShard
from hebog.data_models.images import ImageMetadata
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
from hebog.stages.fitting import CompactGaussianFitProcessor


class _WindowReadable(Protocol):
    """Read one bounded image window for compact catalogue construction."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


@dataclass(frozen=True, slots=True)
class CompactCatalogueProcessor:
    """Fit, transform, and associate one existing coarse worker batch."""

    metadata: ImageMetadata
    fit_processor: CompactGaussianFitProcessor
    catalogue_config: CompactCatalogueConfig

    def __call__(
        self,
        batch: WorkerLocalRegionBatch,
    ) -> tuple[CompactCatalogueShard, ...]:
        """Return exactly one bounded shard for the coarse input batch."""
        fits = self.fit_processor(batch)
        return (
            build_compact_catalogue_shard(
                fits,
                self.metadata,
                deconvolution_relative_tolerance=(
                    self.catalogue_config.deconvolution_relative_tolerance
                ),
            ),
        )


def run_compact_catalogue_stage(  # noqa: PLR0913
    source: _WindowReadable,
    detection: DetectionStageResult,
    *,
    deblend_config: CompactDeblendConfig,
    moment_config: CompactMomentConfig,
    fit_config: CompactGaussianFitConfig,
    catalogue_config: CompactCatalogueConfig,
    geometry: CompactMeasurementGeometry,
    metadata: ImageMetadata,
    executor: Executor,
    sink: ZarrProductSink,
) -> CompactRegionStageResult[CompactCatalogueShard]:
    """Construct one compact catalogue shard per existing coarse task."""
    return run_compact_region_stage(
        source,
        detection,
        deblend_config,
        processor=CompactCatalogueProcessor(
            metadata=metadata,
            fit_processor=CompactGaussianFitProcessor(
                geometry=geometry,
                moment_config=moment_config,
                fit_config=fit_config,
            ),
            catalogue_config=catalogue_config,
        ),
        executor=executor,
        sink=sink,
    )
