# pyright: reportMissingTypeStubs=false
"""Run the public tiled passes over in-memory science planes.

Tests and notebooks that hold analytic planes rather than a FITS file still
have to give the composition a published detection generation, because no
image-sized array reaches a stage through the executor. This module publishes
those planes and drives the same pass the public path runs, so a caller never
reimplements the detection science it is checking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.source_association import HierarchyOverlaps
from hebog.config import SourceFinderConfig
from hebog.data_models.partitioning import ImageBounds
from hebog.data_models.products import ProductChunk
from hebog.executors import Executor, SerialExecutor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.public_api import (
    ADMITTED_TILE_CORE_PIXELS,
    detect_multiscale_products,
    publish_component_fits,
    publish_component_topology,
    publish_hierarchy_overlaps,
    publish_support_labels,
    reduce_support_topology,
)
from hebog.science.models import (
    TiledComponentFits,
    TiledComponentTopology,
    TiledMultiscaleDetection,
    TiledSupportLabels,
    TiledSupportTopology,
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
    """Publish background and RMS planes as one completed generation."""
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
    product_names = ("background", "rms")
    for product_name in product_names:
        sink.initialize_product(
            product_name=product_name,
            dtype=np.dtype("<f8"),
        )
    chunks: list[ProductChunk] = []
    for tile in manifest.tiles:
        selection = _selection(tile.core_bounds)
        for product_name, values in (
            ("background", background_jy_per_beam),
            ("rms", rms_jy_per_beam),
        ):
            chunks.append(
                sink.write_chunk(
                    product_name=product_name,
                    tile=tile,
                    values=np.asarray(values[selection], dtype=np.float64),
                )
            )
    sink.publish_generation(product_names=product_names, chunks=chunks)
    return sink


@dataclass(frozen=True, slots=True)
class PublishedContinuumInputs:
    """Every published plane the continuum composition reads."""

    multiscale: TiledMultiscaleDetection
    support: TiledSupportTopology
    labels: TiledSupportLabels
    topology: TiledComponentTopology
    component_fits: TiledComponentFits
    hierarchy_overlaps: HierarchyOverlaps


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
            range(1, len(multiscale.significant_scale_masks) + 1)
        ),
        generation_id=generation_id,
        tile_core_pixels=support_tile_core_pixels,
    )
    bounds = ImageBounds(
        0,
        image_jy_per_beam.shape[0],
        0,
        image_jy_per_beam.shape[1],
    )
    support_labels, labels_source = publish_support_labels(
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
    return PublishedContinuumInputs(
        hierarchy_overlaps=publish_hierarchy_overlaps(
            detection_source,
            component_source,
            resolved_executor,
            image_shape_yx=image_jy_per_beam.shape,
            direct_component_labels=topology.direct_component_labels,
            residual_jy_per_beam=(image_jy_per_beam - background_jy_per_beam),
            valid_pixels=valid_pixels,
            scale_islands_by_order=multiscale.scale_islands_by_order,
            tile_core_pixels=support_tile_core_pixels,
        ),
        multiscale=multiscale,
        support=TiledSupportTopology(
            support_component_labels=np.asarray(
                support_source.read_completed_window(
                    "support-components",
                    bounds,
                ),
                dtype=np.int32,
            ),
            persistent_scale_support=np.asarray(
                support_source.read_completed_window(
                    "persistent-support",
                    bounds,
                ),
                dtype=np.bool_,
            ),
        ),
        labels=support_labels,
        topology=topology,
        component_fits=publish_component_fits(
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
            generation_id=generation_id,
            tile_core_pixels=support_tile_core_pixels,
        ),
    )
