"""Tests for serializable retryable product-chunk records."""

from __future__ import annotations

import pickle
from dataclasses import replace

import pytest

from hebog.data_models import ImageBounds, ProductChunk


def _product_chunk() -> ProductChunk:
    """Return one valid logical Zarr chunk record for mutation tests."""
    return ProductChunk(
        generation_id="run-001",
        product_name="rms",
        tile_id="tile-00000-00001",
        core_bounds=ImageBounds(2, 4, 3, 6),
        dtype="<f8",
        shape_yx=(2, 3),
        content_sha256="a" * 64,
    )


def test_product_chunk_is_pickle_serializable() -> None:
    """Dask can move chunk identities without moving their pixel arrays."""
    chunk = _product_chunk()

    assert pickle.loads(pickle.dumps(chunk)) == chunk


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 3}, "schema version"),
        ({"generation_id": ""}, "generation ID"),
        ({"product_name": "../rms"}, "product name"),
        ({"tile_id": "../tile"}, "tile ID"),
        ({"dtype": ""}, "dtype"),
        ({"shape_yx": (3, 2)}, "shape"),
        ({"content_sha256": "not-a-digest"}, "SHA-256"),
    ],
)
def test_product_chunk_rejects_invalid_identity(
    changes: dict[str, object],
    message: str,
) -> None:
    """Malformed records fail before workers open a Zarr store."""
    with pytest.raises(ValueError, match=message):
        replace(_product_chunk(), **changes)
