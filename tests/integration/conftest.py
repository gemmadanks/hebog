# pyright: reportMissingTypeStubs=false
"""Shared integration helpers for substituting published stage inputs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.data_models.partitioning import ImageBounds
from hebog.data_models.products import ProductChunk
from hebog.io.zarr import ZarrProductSink

_BACKGROUND_TILE_SHAPE_YX = (128, 128)


def _publish_background_rms(
    work_directory: Path,
    image_jy_per_beam: npt.NDArray[np.float64],
    background_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
    generation_id: str,
) -> ZarrProductSink:
    """Publish an analytic background/RMS generation, masks included.

    A test that substitutes the background stage still has to give the later
    passes a published generation to read, because no image-sized plane
    reaches a stage through the executor. The stage publishes the two masks
    the composition asks of its estimate, so this double publishes them too.
    """
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
    valid = np.asarray(
        np.isfinite(image_jy_per_beam)
        & np.isfinite(background_jy_per_beam)
        & np.isfinite(rms_jy_per_beam),
        dtype=np.bool_,
    )
    planes: tuple[tuple[str, npt.NDArray[Any], np.dtype[Any]], ...] = (
        ("background", background_jy_per_beam, np.dtype("<f8")),
        ("rms", rms_jy_per_beam, np.dtype("<f8")),
        ("valid", valid, np.dtype(np.bool_)),
        (
            "positive-rms",
            np.asarray(valid & (rms_jy_per_beam > 0.0), dtype=np.bool_),
            np.dtype(np.bool_),
        ),
    )
    for product_name, _, dtype in planes:
        sink.initialize_product(product_name=product_name, dtype=dtype)
    chunks: list[ProductChunk] = []
    for tile in manifest.tiles:
        bounds = tile.core_bounds
        selection = (
            slice(bounds.y_start, bounds.y_stop),
            slice(bounds.x_start, bounds.x_stop),
        )
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


SubstituteBackgroundRms = Callable[
    [
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ],
    Callable[..., tuple[ZarrProductSink, Any, Any]],
]


def _substituted_background_rms(
    image_jy_per_beam: npt.NDArray[np.float64],
    background_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
) -> Callable[..., tuple[ZarrProductSink, Any, Any]]:
    """Return a stand-in for the background stage over analytic planes.

    The stage publishes its estimate and returns the two masks the
    composition asks of it, so the substitute has to do both. Keeping the
    work-directory argument's position here means one place knows it.
    """

    def estimate(
        *args: object,
        generation_id: str,
        **_kwargs: object,
    ) -> tuple[ZarrProductSink, Any, Any]:
        """Publish the analytic planes and describe their valid domain."""
        sink = _publish_background_rms(
            cast(Path, args[4]),
            image_jy_per_beam,
            background_jy_per_beam,
            rms_jy_per_beam,
            generation_id,
        )
        valid = np.asarray(
            np.isfinite(image_jy_per_beam)
            & np.isfinite(background_jy_per_beam)
            & np.isfinite(rms_jy_per_beam),
            dtype=np.bool_,
        )
        return sink, valid, valid & (rms_jy_per_beam > 0.0)

    return estimate


@pytest.fixture
def substituted_background_rms() -> SubstituteBackgroundRms:
    """Return a helper standing in for the whole background/RMS stage."""
    return _substituted_background_rms


def estimated_maps(
    sink: ZarrProductSink,
    shape_yx: tuple[int, int],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Read the background and RMS estimates one generation published.

    The stage returns the masks the composition asks of its estimate, so a
    test about the estimate itself reads it back from the store that holds
    it.
    """
    bounds = ImageBounds(0, shape_yx[0], 0, shape_yx[1])
    return (
        np.asarray(
            sink.read_completed_window("background", bounds),
            dtype=np.float64,
        ),
        np.asarray(
            sink.read_completed_window("rms", bounds),
            dtype=np.float64,
        ),
    )
