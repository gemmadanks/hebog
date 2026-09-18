# pyright: reportMissingTypeStubs=false
"""Shared integration helpers for substituting published stage inputs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.data_models.products import ProductChunk
from hebog.io.zarr import ZarrProductSink

_BACKGROUND_TILE_SHAPE_YX = (128, 128)

PublishBackgroundRms = Callable[
    [Path, npt.NDArray[np.float64], npt.NDArray[np.float64], str],
    ZarrProductSink,
]


def _publish_background_rms(
    work_directory: Path,
    background_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
    generation_id: str,
) -> ZarrProductSink:
    """Publish analytic background and RMS planes as one generation.

    A test that substitutes the background stage still has to give the
    detection pass a published generation to read, because no image-sized
    plane reaches a stage through the executor.
    """
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
    for product_name in ("background", "rms"):
        sink.initialize_product(
            product_name=product_name,
            dtype=np.dtype("<f8"),
        )
    chunks: list[ProductChunk] = []
    for tile in manifest.tiles:
        bounds = tile.core_bounds
        selection = (
            slice(bounds.y_start, bounds.y_stop),
            slice(bounds.x_start, bounds.x_stop),
        )
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
    sink.publish_generation(
        product_names=("background", "rms"),
        chunks=chunks,
    )
    return sink


@pytest.fixture
def published_background_rms() -> PublishBackgroundRms:
    """Return a helper publishing analytic background and RMS planes."""
    return _publish_background_rms
