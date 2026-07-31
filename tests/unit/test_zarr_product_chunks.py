"""Tests for serializable Zarr product-chunk records."""

from __future__ import annotations

import pickle
from dataclasses import replace

import pytest

from hebog.data_models import ImageBounds, ZarrProductChunk


def _zarr_product_chunk() -> ZarrProductChunk:
    """Return one valid storage-neutral Zarr chunk record."""
    return ZarrProductChunk(
        product_name="rms",
        tile_id="tile-00000-00001",
        core_bounds=ImageBounds(2, 4, 3, 6),
        array_name="rms",
        dtype="<f8",
        shape_yx=(2, 3),
        content_sha256="a" * 64,
    )


def test_zarr_product_chunk_is_pickle_serializable() -> None:
    """Dask can move logical chunk identities without open store objects."""
    chunk = _zarr_product_chunk()

    assert pickle.loads(pickle.dumps(chunk)) == chunk


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 2}, "schema version"),
        ({"product_name": "../rms"}, "product name"),
        ({"tile_id": "../tile"}, "tile ID"),
        ({"array_name": "other"}, "array name"),
        ({"dtype": ""}, "dtype"),
        ({"shape_yx": (3, 2)}, "shape"),
        ({"content_sha256": "not-a-digest"}, "SHA-256"),
    ],
)
def test_zarr_product_chunk_rejects_invalid_identity(
    changes: dict[str, object],
    message: str,
) -> None:
    """Malformed records fail before workers open a Zarr store."""
    with pytest.raises(ValueError, match=message):
        replace(_zarr_product_chunk(), **changes)
