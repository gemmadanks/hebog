"""Scheduler-independent contracts for bounded image input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class ImageBounds:
    """Half-open global pixel bounds in NumPy ``(y, x)`` axis order."""

    y_start: int
    y_stop: int
    x_start: int
    x_stop: int

    def __post_init__(self) -> None:
        """Require non-negative, non-empty half-open bounds."""
        if min(self.y_start, self.y_stop, self.x_start, self.x_stop) < 0:
            raise ValueError("image bounds must be non-negative")
        if self.y_stop <= self.y_start or self.x_stop <= self.x_start:
            raise ValueError("image bounds must be non-empty")

    @property
    def shape_yx(self) -> tuple[int, int]:
        """Return the bounded array shape in NumPy axis order."""
        return (
            self.y_stop - self.y_start,
            self.x_stop - self.x_start,
        )

    def require_inside(self, shape_yx: tuple[int, int]) -> None:
        """Reject bounds extending beyond one logical image plane."""
        if self.y_stop > shape_yx[0] or self.x_stop > shape_yx[1]:
            raise ValueError(
                f"image bounds must stay inside image shape {shape_yx}"
            )


@dataclass(frozen=True, slots=True)
class ImageMetadata:
    """Small serializable facts required before reading image pixels."""

    shape_yx: tuple[int, int]
    unit: str


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
