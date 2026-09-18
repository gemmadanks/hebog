# pyright: reportMissingTypeStubs=false
"""Run the public tiled detection pass over in-memory science planes.

Tests and notebooks that hold analytic planes rather than a FITS file still
have to give the composition a published detection generation, because no
image-sized array reaches a stage through the executor. This module publishes
those planes and drives the same pass the public path runs, so a caller never
reimplements the detection science it is checking.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.data_models.partitioning import ImageBounds
from hebog.data_models.products import ProductChunk
from hebog.executors import Executor, SerialExecutor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.public_api import (
    DETECTION_TILE_CORE_PIXELS,
    detect_multiscale_products,
)
from hebog.science.models import TiledMultiscaleDetection
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
        work_directory / "detection.zarr",
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


def detect_multiscale_planes(  # noqa: PLR0913
    image_jy_per_beam: npt.NDArray[np.float64],
    valid_pixels: npt.NDArray[np.bool_],
    background_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
    *,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
    work_directory: Path,
    executor: Executor | None = None,
    generation_id: str = "tiled-detection",
    tile_core_pixels: int = DETECTION_TILE_CORE_PIXELS,
) -> TiledMultiscaleDetection:
    """Publish and read the detection pass the composition consumes."""
    work_directory.mkdir(parents=True, exist_ok=True)
    return detect_multiscale_products(
        ArrayImageSource(image_jy_per_beam, valid_pixels),
        publish_background_rms(
            work_directory,
            background_jy_per_beam,
            rms_jy_per_beam,
            generation_id=generation_id,
        ),
        SerialExecutor() if executor is None else executor,
        work_directory,
        image_shape_yx=image_jy_per_beam.shape,
        beam=beam,
        review=review,
        generation_id=generation_id,
        tile_core_pixels=tile_core_pixels,
    )
