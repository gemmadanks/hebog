# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Contract tests for aligned Zarr v3 intermediate product chunks."""

from __future__ import annotations

import hashlib
import pickle
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest
import zarr

from hebog.data_models import PartitionManifest, ProductChunk
from hebog.io import (
    InvalidProductChunkError,
    ProductChunkConflictError,
    ZarrProductSink,
)

pytestmark = pytest.mark.integration


def _manifest(
    *,
    partition_origin_yx: tuple[int, int] = (0, 0),
) -> PartitionManifest:
    """Return four regular cores with clipped image-edge chunks."""
    return PartitionManifest.create(
        image_shape_yx=(5, 7),
        tile_core_shape_yx=(3, 4),
        halo_yx=(0, 0),
        partition_origin_yx=partition_origin_yx,
    )


def _values_for(tile_index: int) -> npt.NDArray[np.float64]:
    """Return deterministic values with one invalid scientific pixel."""
    tile = _manifest().tiles[tile_index]
    values = np.full(tile.core_bounds.shape_yx, tile_index + 1.0)
    if tile_index == 0:
        values[0, 0] = np.nan
    return values


def test_initializes_one_strict_zarr_v3_array_per_product(
    tmp_path: Path,
) -> None:
    """Array geometry and missing/empty policy are explicit and durable."""
    root = tmp_path / "run.zarr"
    sink = ZarrProductSink(root, _manifest())

    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))

    group = zarr.open_group(store=root, mode="r")
    array = group["rms"]
    assert array.metadata.zarr_format == 3
    assert array.shape == (5, 7)
    assert array.chunks == (3, 4)
    assert array.dtype == np.dtype("<f8")
    assert array.attrs["hebog_missing_chunk_policy"] == "error"
    assert array.attrs["hebog_write_empty_chunks"] is True
    assert group.attrs["partition_schema_version"] == 1
    assert group.attrs["partition_origin_yx"] == [0, 0]
    assert pickle.loads(pickle.dumps(sink)).manifest == sink.manifest

    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))


def test_initialization_rejects_conflicting_group_or_array_metadata(
    tmp_path: Path,
) -> None:
    """A reused run store cannot silently acquire different geometry."""
    root = tmp_path / "run.zarr"
    sink = ZarrProductSink(root, _manifest())
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))

    with pytest.raises(InvalidProductChunkError, match="metadata"):
        sink.initialize_product(product_name="rms", dtype=np.dtype("<f4"))

    group = zarr.open_group(store=root, mode="r+")
    group.attrs["image_shape_yx"] = [99, 99]
    with pytest.raises(InvalidProductChunkError, match="attribute"):
        ZarrProductSink(root, _manifest()).initialize_product(
            product_name="mask",
            dtype=np.dtype("u1"),
        )


def test_initialization_rejects_object_arrays(tmp_path: Path) -> None:
    """Intermediate image products never enable object deserialization."""
    sink = ZarrProductSink(tmp_path / "run.zarr", _manifest())

    with pytest.raises(ValueError, match="object"):
        sink.initialize_product(product_name="rms", dtype=np.dtype("O"))


def test_writes_and_reads_independent_complete_chunks(tmp_path: Path) -> None:
    """Tile owners preserve global placement, dtype, NaNs, and edge shapes."""
    root = tmp_path / "run.zarr"
    manifest = _manifest()
    sink = ZarrProductSink(root, manifest)
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))
    records = tuple(
        sink.write_chunk(
            product_name="rms",
            tile=tile,
            values=_values_for(index),
        )
        for index, tile in enumerate(manifest.tiles)
    )

    assert all(isinstance(record, ProductChunk) for record in records)
    for index, record in enumerate(records):
        restored = sink.read_chunk(record)
        np.testing.assert_array_equal(restored, _values_for(index))
        assert not restored.flags.writeable

    array = cast(Any, zarr.open_array(store=root, path="rms", mode="r"))
    plane = np.asarray(array[:])
    assert plane.shape == manifest.image_shape_yx
    assert np.isnan(plane[0, 0])
    np.testing.assert_array_equal(plane[3:, 4:], 4.0)


def test_writes_an_all_fill_value_chunk_for_strict_reads(
    tmp_path: Path,
) -> None:
    """A valid zero chunk remains distinguishable from a missing chunk."""
    manifest = _manifest()
    sink = ZarrProductSink(tmp_path / "run.zarr", manifest)
    sink.initialize_product(product_name="mask", dtype=np.dtype("u1"))
    tile = manifest.tiles[0]

    record = sink.write_chunk(
        product_name="mask",
        tile=tile,
        values=np.zeros(tile.core_bounds.shape_yx, dtype=np.uint8),
    )

    np.testing.assert_array_equal(sink.read_chunk(record), 0)


def test_read_rejects_a_missing_chunk_instead_of_returning_fill(
    tmp_path: Path,
) -> None:
    """A hierarchy with metadata but no tile bytes fails closed."""
    manifest = _manifest()
    sink = ZarrProductSink(tmp_path / "run.zarr", manifest)
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))
    missing_tile = manifest.tiles[1]
    missing_values = _values_for(1)
    missing = ProductChunk(
        product_name="rms",
        tile_id=missing_tile.tile_id,
        core_bounds=missing_tile.core_bounds,
        dtype=missing_values.dtype.str,
        shape_yx=tuple(missing_values.shape),
        content_sha256=hashlib.sha256(
            np.ascontiguousarray(missing_values).tobytes()
        ).hexdigest(),
    )

    with pytest.raises(InvalidProductChunkError, match="missing"):
        sink.read_chunk(missing)


def test_identical_retry_is_idempotent_and_conflict_fails_closed(
    tmp_path: Path,
) -> None:
    """Sequential retries cannot silently replace completed science bytes."""
    manifest = _manifest()
    sink = ZarrProductSink(tmp_path / "run.zarr", manifest)
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))
    tile = manifest.tiles[0]

    first = sink.write_chunk(
        product_name="rms",
        tile=tile,
        values=_values_for(0),
    )
    second = sink.write_chunk(
        product_name="rms",
        tile=tile,
        values=_values_for(0),
    )

    assert second == first
    with pytest.raises(ProductChunkConflictError, match="different values"):
        sink.write_chunk(
            product_name="rms",
            tile=tile,
            values=np.zeros(tile.core_bounds.shape_yx, dtype=np.float64),
        )
    np.testing.assert_array_equal(sink.read_chunk(first), _values_for(0))


def test_crc32c_rejects_corrupt_stored_bytes(tmp_path: Path) -> None:
    """The configured codec detects mutations to encoded chunk bytes."""
    root = tmp_path / "run.zarr"
    manifest = _manifest()
    sink = ZarrProductSink(root, manifest)
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))
    record = sink.write_chunk(
        product_name="rms",
        tile=manifest.tiles[0],
        values=_values_for(0),
    )
    stored_chunks = tuple(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name != "zarr.json"
    )
    assert len(stored_chunks) == 1
    chunk_path = stored_chunks[0]
    payload = bytearray(chunk_path.read_bytes())
    payload[-1] ^= 1
    chunk_path.write_bytes(payload)

    with pytest.raises(InvalidProductChunkError, match="corrupt"):
        sink.read_chunk(record)


def test_read_rejects_record_content_disagreement(tmp_path: Path) -> None:
    """A valid Zarr chunk must still match its Hebog content identity."""
    manifest = _manifest()
    sink = ZarrProductSink(tmp_path / "run.zarr", manifest)
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))
    record = sink.write_chunk(
        product_name="rms",
        tile=manifest.tiles[0],
        values=_values_for(0),
    )

    with pytest.raises(InvalidProductChunkError, match="SHA-256"):
        sink.read_chunk(replace(record, content_sha256="0" * 64))

    with pytest.raises(InvalidProductChunkError, match="metadata"):
        sink.read_chunk(replace(record, dtype="<f4"))


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (np.zeros((2, 2), dtype=np.float64), "shape"),
        (np.zeros((3, 4), dtype=np.float32), "dtype"),
    ],
)
def test_write_rejects_values_outside_the_initialized_contract(
    tmp_path: Path,
    values: npt.NDArray[np.generic],
    message: str,
) -> None:
    """Zarr cannot silently reshape or cast a worker result."""
    manifest = _manifest()
    sink = ZarrProductSink(tmp_path / "run.zarr", manifest)
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))

    with pytest.raises(ValueError, match=message):
        sink.write_chunk(
            product_name="rms",
            tile=manifest.tiles[0],
            values=values,
        )


def test_read_rejects_noncanonical_records_and_changed_policy(
    tmp_path: Path,
) -> None:
    """Both Hebog ownership and durable array policy are validated."""
    root = tmp_path / "run.zarr"
    manifest = _manifest()
    sink = ZarrProductSink(root, manifest)
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))
    record = sink.write_chunk(
        product_name="rms",
        tile=manifest.tiles[0],
        values=_values_for(0),
    )
    invalid_records = (
        replace(record, tile_id="tile-99999-99999"),
        replace(record, tile_id="tile-00000-00002"),
        replace(
            record,
            core_bounds=replace(record.core_bounds, y_stop=2),
            shape_yx=(2, 4),
        ),
    )

    for invalid_record in invalid_records:
        with pytest.raises(InvalidProductChunkError, match="manifest"):
            sink.read_chunk(invalid_record)

    group = zarr.open_group(store=root, mode="r+")
    group["rms"].attrs["hebog_missing_chunk_policy"] = "fill"
    with pytest.raises(InvalidProductChunkError, match="policy"):
        sink.read_chunk(record)


def test_requires_preinitialized_products_and_canonical_tiles(
    tmp_path: Path,
) -> None:
    """Workers cannot race metadata creation or invent storage selections."""
    manifest = _manifest()
    sink = ZarrProductSink(tmp_path / "run.zarr", manifest)

    with pytest.raises(InvalidProductChunkError, match="initialized"):
        sink.write_chunk(
            product_name="rms",
            tile=manifest.tiles[0],
            values=_values_for(0),
        )

    invented_tile = replace(
        manifest.tiles[0],
        read_bounds=replace(manifest.tiles[0].read_bounds, y_stop=4),
    )
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))
    with pytest.raises(ValueError, match="canonical manifest"):
        sink.write_chunk(
            product_name="rms",
            tile=invented_tile,
            values=_values_for(0),
        )


def test_rejects_shifted_partitions_that_do_not_align_with_zarr_chunks(
    tmp_path: Path,
) -> None:
    """Direct tile writes require exactly one owner for each storage chunk."""
    with pytest.raises(ValueError, match="origin"):
        ZarrProductSink(
            tmp_path / "run.zarr",
            _manifest(partition_origin_yx=(1, 1)),
        )
