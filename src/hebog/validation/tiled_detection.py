# pyright: reportMissingTypeStubs=false
"""Run the public tiled passes over in-memory science planes.

Tests and notebooks that hold analytic planes rather than a FITS file still
have to give the composition a published detection generation, because no
image-sized array reaches a stage through the executor. This module publishes
those planes and drives the same pass the public path runs, so a caller never
reimplements the detection science it is checking.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.algorithms.component_measurement import (
    ComponentMeasurements,
    reconcile_component_measurements,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.multiscale_association import ScaleDetections
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.source_association import (
    HierarchyOverlaps,
    associate_from_hierarchy_overlaps,
    constrain_source_memberships,
)
from hebog.config import SourceFinderConfig
from hebog.data_models.measurement_diagnostics import (
    SourcePositionDiagnostics,
)
from hebog.data_models.partitioning import ImageBounds
from hebog.data_models.products import ProductChunk
from hebog.data_models.source_association import (
    DetectionComponentRecord,
    SourceAssociationResult,
)
from hebog.executors import Executor, SerialExecutor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.public_api import (
    ADMITTED_TILE_CORE_PIXELS,
    detect_multiscale_products,
    publish_component_fits,
    publish_component_topology,
    publish_detection_islands,
    publish_hierarchy_overlaps,
    publish_segment_rows,
    publish_source_planes,
    publish_support_labels,
    reduce_support_topology,
)
from hebog.science.continuum import retained_scale_detections
from hebog.science.models import (
    CatalogueIsland,
    CatalogueSource,
    TiledComponentTopology,
    TiledMultiscaleDetection,
)
from hebog.science.profile import ContinuumScienceProfile

_BACKGROUND_TILE_SHAPE_YX = (128, 128)


def _selection(bounds: ImageBounds) -> tuple[slice, slice]:
    """Return global array slices for one half-open bound."""
    return (
        slice(bounds.y_start, bounds.y_stop),
        slice(bounds.x_start, bounds.x_stop),
    )


class ArrayImageSource:
    """Serializable bounded image source backed by one in-memory plane."""

    def __init__(
        self,
        values: npt.NDArray[np.float64],
        valid_pixels: npt.NDArray[np.bool_],
    ) -> None:
        """Retain the complete plane and its validity for window reads."""
        self._values = values
        self._valid_pixels = valid_pixels

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return one owned aligned window of the retained plane."""
        selection = _selection(bounds)
        return ImageWindow(
            bounds=bounds,
            values=np.array(self._values[selection], copy=True),
            valid_pixels=np.array(self._valid_pixels[selection], copy=True),
        )


def publish_background_rms(
    work_directory: Path,
    background_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
    *,
    generation_id: str,
) -> ZarrProductSink:
    """Publish the background/RMS generation the detection stage publishes."""
    manifest = plan_image_partitions(
        image_shape_yx=background_jy_per_beam.shape,
        tile_core_shape_yx=_BACKGROUND_TILE_SHAPE_YX,
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "background.zarr",
        manifest,
        generation_id=generation_id,
    )
    planes: tuple[tuple[str, npt.NDArray[Any], np.dtype[Any]], ...] = (
        ("background", background_jy_per_beam, np.dtype("<f8")),
        ("rms", rms_jy_per_beam, np.dtype("<f8")),
    )
    for product_name, _, dtype in planes:
        sink.initialize_product(product_name=product_name, dtype=dtype)
    chunks: list[ProductChunk] = []
    for tile in manifest.tiles:
        selection = _selection(tile.core_bounds)
        for product_name, values, dtype in planes:
            chunks.append(
                sink.write_chunk(
                    product_name=product_name,
                    tile=tile,
                    values=np.asarray(values[selection], dtype=dtype),
                )
            )
    sink.publish_generation(
        product_names=tuple(name for name, _, _ in planes),
        chunks=chunks,
    )
    return sink


@dataclass(frozen=True, slots=True)
class PublishedContinuumInputs:
    """Every record the continuum composition reads, and the stores behind it.

    The composition holds no plane from these passes, so a caller comparing
    published pixels — a partition-invariance test, or a notebook drawing a
    mask — reads them from the generation that wrote them. The sinks below are
    those generations, in pass order.
    """

    image_source: ArrayImageSource
    background_rms: ZarrProductSink
    accepted_island_count: int
    detection_source: ZarrProductSink
    support_source: ZarrProductSink
    labels_source: ZarrProductSink
    component_source: ZarrProductSink
    fit_source: ZarrProductSink
    hierarchy_source: ZarrProductSink
    source_label_source: ZarrProductSink
    source_support_source: ZarrProductSink
    multiscale: TiledMultiscaleDetection
    topology: TiledComponentTopology
    measurements: ComponentMeasurements
    association: SourceAssociationResult
    hierarchy: SourceAssociationResult
    component_rows: tuple[CatalogueSource, ...]
    source_rows: tuple[CatalogueSource, ...]
    source_positions: Mapping[int, SourcePositionDiagnostics]
    component_local_rms: Mapping[int, float]
    source_local_rms: Mapping[int, float]
    islands: tuple[CatalogueIsland, ...]
    island_ids_by_owner: Mapping[int, tuple[str, ...]]


def _source_association(
    records: tuple[DetectionComponentRecord, ...],
    scale_detections: Sequence[ScaleDetections],
    overlaps: HierarchyOverlaps,
    groups: tuple[frozenset[int], ...],
) -> tuple[SourceAssociationResult, SourceAssociationResult]:
    """Decide source membership, or nothing when no owner remains.

    The terminal composition publishes nothing for an image whose admitted
    islands are all rejected, and the hierarchy has no direct component to
    describe, so the decision is skipped rather than fabricated.
    """
    if not records:
        empty = SourceAssociationResult(
            components=(),
            edges=(),
            memberships=(),
            ambiguous_component_ids=(),
        )
        return empty, empty
    hierarchy = associate_from_hierarchy_overlaps(
        records, tuple(scale_detections), overlaps
    )
    return hierarchy, constrain_source_memberships(hierarchy, groups)


def publish_continuum_inputs(  # noqa: PLR0913
    image_jy_per_beam: npt.NDArray[np.float64],
    valid_pixels: npt.NDArray[np.bool_],
    background_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
    *,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
    work_directory: Path,
    header: fits.Header,
    executor: Executor | None = None,
    generation_id: str = "published-continuum-inputs",
    config: SourceFinderConfig,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
    support_tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> PublishedContinuumInputs:
    """Publish and read every pass the composition consumes."""
    work_directory.mkdir(parents=True, exist_ok=True)
    image_source = ArrayImageSource(image_jy_per_beam, valid_pixels)
    background_rms_source = publish_background_rms(
        work_directory,
        background_jy_per_beam,
        rms_jy_per_beam,
        generation_id=generation_id,
    )
    resolved_executor = SerialExecutor() if executor is None else executor
    detection_source, multiscale = detect_multiscale_products(
        image_source,
        background_rms_source,
        resolved_executor,
        work_directory,
        image_shape_yx=image_jy_per_beam.shape,
        beam=beam,
        review=review,
        generation_id=generation_id,
        tile_core_pixels=tile_core_pixels,
    )
    support_source = reduce_support_topology(
        detection_source,
        resolved_executor,
        work_directory,
        image_shape_yx=image_jy_per_beam.shape,
        scale_orders=tuple(
            range(1, len(multiscale.scale_islands_by_order) + 1)
        ),
        generation_id=generation_id,
        tile_core_pixels=support_tile_core_pixels,
    )
    accepted_island_count, labels_source = publish_support_labels(
        detection_source,
        support_source,
        resolved_executor,
        work_directory,
        image_shape_yx=image_jy_per_beam.shape,
        beam=beam,
        detection_islands=multiscale.detection_islands,
        config=config,
        review=review,
        generation_id=generation_id,
        tile_core_pixels=support_tile_core_pixels,
    )
    component_source, topology = publish_component_topology(
        labels_source,
        detection_source,
        resolved_executor,
        work_directory,
        image_shape_yx=image_jy_per_beam.shape,
        config=config,
        generation_id=generation_id,
        tile_core_pixels=support_tile_core_pixels,
    )
    scale_detections = retained_scale_detections(multiscale)
    component_fits, fit_source = publish_component_fits(
        image_source,
        background_rms_source,
        detection_source,
        component_source,
        resolved_executor,
        work_directory,
        image_shape_yx=image_jy_per_beam.shape,
        beam=beam,
        header=header,
        config=config,
        review=review,
        component_count=topology.component_count,
        generation_id=generation_id,
        tile_core_pixels=support_tile_core_pixels,
    )
    records = component_fits.component_records
    overlaps, hierarchy_source = publish_hierarchy_overlaps(
        detection_source,
        component_source,
        resolved_executor,
        work_directory,
        image_shape_yx=image_jy_per_beam.shape,
        records=records,
        scale_detections=scale_detections,
        generation_id=generation_id,
        tile_core_pixels=support_tile_core_pixels,
    )
    measurements = reconcile_component_measurements(
        parents=component_fits.parents,
        features=component_fits.features,
    )
    hierarchy, association = _source_association(
        records,
        scale_detections,
        overlaps,
        (*measurements.compact_groups, *measurements.extended_groups),
    )
    source_label_source, source_support_source = publish_source_planes(
        component_source,
        detection_source,
        hierarchy_source,
        fit_source,
        resolved_executor,
        work_directory,
        image_shape_yx=image_jy_per_beam.shape,
        association=association,
        generation_id=generation_id,
        tile_core_pixels=support_tile_core_pixels,
    )
    islands, island_ids_by_owner = publish_detection_islands(
        image_source,
        background_rms_source,
        labels_source,
        component_source,
        resolved_executor,
        image_shape_yx=image_jy_per_beam.shape,
        beam=beam,
        tile_core_pixels=support_tile_core_pixels,
    )
    component_rows, component_local_rms, _ = publish_segment_rows(
        image_source,
        background_rms_source,
        detection_source,
        component_source,
        component_source,
        resolved_executor,
        work_directory,
        image_shape_yx=image_jy_per_beam.shape,
        beam=beam,
        header=header,
        label_product_name="component-measurement-labels",
        centroid_product_name="component-measurement-labels",
        aperture_tie_policy="nearest-support",
        with_position_diagnostics=False,
        generation_id=generation_id,
        sink_name="component-rows",
        tile_core_pixels=support_tile_core_pixels,
    )
    source_rows, source_local_rms, source_positions = publish_segment_rows(
        image_source,
        background_rms_source,
        detection_source,
        source_support_source,
        source_label_source,
        resolved_executor,
        work_directory,
        image_shape_yx=image_jy_per_beam.shape,
        beam=beam,
        header=header,
        label_product_name="source-measurement-labels",
        centroid_product_name="source-labels",
        aperture_tie_policy="canonical-source",
        with_position_diagnostics=True,
        generation_id=generation_id,
        sink_name="source-rows",
        tile_core_pixels=support_tile_core_pixels,
    )
    return PublishedContinuumInputs(
        image_source=image_source,
        background_rms=background_rms_source,
        accepted_island_count=accepted_island_count,
        detection_source=detection_source,
        support_source=support_source,
        labels_source=labels_source,
        component_source=component_source,
        fit_source=fit_source,
        hierarchy_source=hierarchy_source,
        source_label_source=source_label_source,
        source_support_source=source_support_source,
        component_rows=component_rows,
        source_rows=source_rows,
        source_positions=source_positions,
        component_local_rms=component_local_rms,
        source_local_rms=source_local_rms,
        islands=islands,
        island_ids_by_owner=island_ids_by_owner,
        measurements=measurements,
        association=association,
        hierarchy=hierarchy,
        multiscale=multiscale,
        topology=topology,
    )
