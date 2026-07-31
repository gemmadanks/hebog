"""Scheduler-independent contracts for bounded image input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt

from hebog.data_models.images import ImageMetadata
from hebog.data_models.partitioning import ImageBounds, TilePartition
from hebog.data_models.products import ProductChunk


@dataclass(frozen=True, slots=True)
class ImageWindow:
    """One owned, read-only bounded pixel window and its validity mask."""

    bounds: ImageBounds
    values: npt.NDArray[np.float64]
    valid_pixels: npt.NDArray[np.bool_]


class ImageSource(Protocol):
    """Narrow input seam implemented by window-readable image stores."""

    def metadata(self) -> ImageMetadata:
        """Return logical image metadata without materialising the plane."""
        ...

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window into worker-owned memory."""
        ...


class ProductSink(Protocol):
    """Narrow publication seam for independently retryable product chunks."""

    def write_chunk(
        self,
        *,
        product_name: str,
        tile: TilePartition,
        values: npt.NDArray[np.generic],
    ) -> ProductChunk:
        """Atomically publish or reuse one tile-owned output core."""
        ...
