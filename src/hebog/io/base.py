"""Scheduler-independent contracts for bounded image input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt

from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.images import ImageMetadata
from hebog.data_models.partitioning import ImageBounds, PartitionManifest


@dataclass(frozen=True, slots=True)
class ImageWindow:
    """One owned, read-only bounded pixel window and its validity mask.

    ``valid_pixels`` says which pixels the finder measures. A pixel's
    validity belongs to the pixel, not to the window that holds it: the same
    pixel must be valid in every window that contains it, however the image
    is tiled.
    """

    bounds: ImageBounds
    values: npt.NDArray[np.float64]
    valid_pixels: npt.NDArray[np.bool_]


class ImageSource(Protocol):
    """Narrow input seam implemented by window-readable image stores."""

    def metadata(self) -> ImageMetadata:
        """Return logical image metadata without materialising the plane."""
        ...

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window into worker-owned memory.

        The window's ``valid_pixels`` must not depend on ``bounds``: a source
        whose rule looks at a pixel's neighbours, as the FITS source's block
        rule (:mod:`hebog.io.pixel_validity`) does, reads a margin around the
        window and keeps only the window, so any tiling decides the same
        pixels.
        """
        ...


class WindowReadable(Protocol):
    """Read bounded global image windows without scheduler state.

    The read-only part of :class:`ImageSource` that a stage task needs; a
    task never needs the image metadata.
    """

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


class CompletedProductSource(Protocol):
    """Read checksum-validated windows from one published generation."""

    @property
    def manifest(self) -> PartitionManifest:
        """Return the canonical partition the generation was written on."""
        ...

    def read_generation(self) -> ProductGenerationManifest:
        """Validate and return the published completion record."""
        ...

    def read_completed_window(
        self,
        product_name: str,
        bounds: ImageBounds,
    ) -> npt.NDArray[np.generic]:
        """Read one validated bounded product window."""
        ...
