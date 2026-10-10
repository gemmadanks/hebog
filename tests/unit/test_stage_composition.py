"""Unit tests for the stage sequence's own decisions."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest

from hebog.data_models.images import ImageMetadata
from hebog.data_models.partitioning import ImageBounds
from hebog.io.base import ImageWindow
from hebog.stages.composition import estimate_has_usable_noise


@dataclass(frozen=True, slots=True)
class _Manifest:
    """The one partition field the usable-noise reduction reads."""

    tile_core_shape_yx: tuple[int, int]


class _PublishedRms:
    """A published RMS plane served in fixed row blocks."""

    def __init__(self, rms: npt.NDArray[np.float64], block_rows: int) -> None:
        """Hold the plane and the rows each block carries."""
        self._rms = rms
        self.manifest = _Manifest((block_rows, rms.shape[1]))

    def iter_completed_row_blocks(
        self, product_name: str, *, max_block_bytes: int
    ) -> Iterator[npt.NDArray[np.float64]]:
        """Yield the RMS plane one block of rows at a time."""
        assert product_name == "rms"
        assert max_block_bytes > 0
        rows = self.manifest.tile_core_shape_yx[0]
        for start in range(0, self._rms.shape[0], rows):
            yield self._rms[start : start + rows]


class _Image:
    """An image whose every pixel is valid."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return a zero window that is valid throughout."""
        shape = (
            bounds.y_stop - bounds.y_start,
            bounds.x_stop - bounds.x_start,
        )
        return ImageWindow(
            bounds=bounds,
            values=np.zeros(shape),
            valid_pixels=np.ones(shape, dtype=np.bool_),
        )


def _metadata(shape_yx: tuple[int, int]) -> ImageMetadata:
    """Return metadata of the given shape; the reduction reads nothing else."""
    return cast(ImageMetadata, SimpleNamespace(shape_yx=shape_yx))


@pytest.mark.parametrize(
    ("rms", "usable"),
    [
        (np.zeros((4, 3)), False),
        (np.where(np.arange(12).reshape(4, 3) == 10, 1.0, 0.0), True),
    ],
)
def test_noise_is_usable_where_a_valid_pixel_has_positive_rms(
    rms: npt.NDArray[np.float64], usable: bool
) -> None:
    """One valid pixel with a positive RMS, in any row block, is enough."""
    published = _PublishedRms(rms, block_rows=2)

    assert (
        estimate_has_usable_noise(
            _Image(), cast(Any, published), _metadata(rms.shape)
        )
        is usable
    )


def test_rms_rows_that_do_not_cover_the_image_are_refused() -> None:
    """A published estimate shorter than the image is an invariant breach."""
    published = _PublishedRms(np.ones((2, 3)), block_rows=2)

    with pytest.raises(ValueError, match="rows must total 4; received 2"):
        estimate_has_usable_noise(
            _Image(), cast(Any, published), _metadata((4, 3))
        )
