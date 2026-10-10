# pyright: reportMissingTypeStubs=false
"""Run the public tiled passes over in-memory science planes.

Tests and notebooks that hold analytic planes rather than a FITS file still
have to give the composition a published detection generation, because no
image-sized array reaches a stage through the executor. This module publishes
those planes and drives the same pass the public path runs, so a caller never
reimplements the detection science it is checking.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.algorithms.component_measurement import (
    ComponentMeasurements,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import SourceFinderConfig
from hebog.data_models.measurement_diagnostics import (
    SourcePositionDiagnostics,
)
from hebog.data_models.partitioning import ImageBounds
from hebog.data_models.products import ProductChunk
from hebog.data_models.source_association import (
    SourceAssociationResult,
)
from hebog.executors import Executor, SerialExecutor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.science.catalogue_rows import CatalogueSource
from hebog.science.models import (
    CatalogueIsland,
    TiledComponentTopology,
    TiledMultiscaleDetection,
)
from hebog.science.profile import ContinuumScienceProfile
from hebog.stages.composition import (
    ADMITTED_TILE_CORE_PIXELS,
    restoring_beam_from_header,
    run_stages_from_background,
)

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
    """Publish and read every pass the composition consumes.

    The supplied background and RMS are published as the background stage
    would publish them, and every later stage then runs exactly as
    ``find_sources`` runs it.
    """
    work_directory.mkdir(parents=True, exist_ok=True)
    image_source = ArrayImageSource(image_jy_per_beam, valid_pixels)
    background_rms_source = publish_background_rms(
        work_directory,
        background_jy_per_beam,
        rms_jy_per_beam,
        generation_id=generation_id,
    )
    published = run_stages_from_background(
        image_source,
        background_rms_source,
        SerialExecutor() if executor is None else executor,
        work_directory,
        image_shape_yx=image_jy_per_beam.shape,
        config=config,
        wcs_header_text=header.tostring(),
        restoring_beam=restoring_beam_from_header(header),
        beam=beam,
        review=review,
        generation_id=generation_id,
        multiscale_tile_core_pixels=tile_core_pixels,
        support_tile_core_pixels=support_tile_core_pixels,
    )
    records = published.records
    return PublishedContinuumInputs(
        image_source=image_source,
        background_rms=background_rms_source,
        accepted_island_count=records.accepted_island_count,
        detection_source=published.detection_source,
        support_source=published.support_source,
        labels_source=published.publication_source,
        component_source=published.component_source,
        fit_source=published.fit_source,
        hierarchy_source=published.hierarchy_source,
        source_label_source=published.source_label_source,
        source_support_source=published.source_support_source,
        component_rows=records.component_rows,
        source_rows=records.source_rows,
        source_positions=records.source_positions,
        component_local_rms=records.component_local_rms,
        source_local_rms=records.source_local_rms,
        islands=records.islands,
        island_ids_by_owner=records.island_ids_by_owner,
        measurements=records.measurements,
        association=records.association,
        hierarchy=records.hierarchy,
        multiscale=published.multiscale,
        topology=records.topology,
    )
