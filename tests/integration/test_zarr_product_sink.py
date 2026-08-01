# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Contract tests for aligned Zarr v3 intermediate product chunks."""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest
import zarr
from zarr.errors import ChunkNotFoundError

from hebog.data_models import (
    PartitionManifest,
    ProductChunk,
    ProductGenerationManifest,
)
from hebog.io import (
    InvalidProductChunkError,
    InvalidProductGenerationError,
    ProductChunkConflictError,
    ProductGenerationConflictError,
    ZarrProductSink,
)

pytestmark = pytest.mark.integration


def test_uses_zarr_3_2_for_native_strict_missing_chunk_reads() -> None:
    """The storage contract relies on the Zarr 3.2 strict-read API."""
    assert tuple(int(part) for part in zarr.__version__.split(".")[:2]) == (
        3,
        2,
    )


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


def _sink(
    root: Path,
    manifest: PartitionManifest | None = None,
    *,
    generation_id: str = "run-001",
) -> ZarrProductSink:
    """Return a sink with one explicit generation identity."""
    return ZarrProductSink(
        root,
        _manifest() if manifest is None else manifest,
        generation_id=generation_id,
    )


def _values_for(tile_index: int) -> npt.NDArray[np.float64]:
    """Return deterministic values with one invalid scientific pixel."""
    tile = _manifest().tiles[tile_index]
    values = np.full(tile.core_bounds.shape_yx, tile_index + 1.0)
    if tile_index == 0:
        values[0, 0] = np.nan
    return values


def _write_product(
    sink: ZarrProductSink,
    manifest: PartitionManifest,
    product_name: str,
) -> tuple[ProductChunk, ...]:
    """Initialize and write every canonical chunk for one product."""
    dtype = np.dtype("u1") if product_name == "mask" else np.dtype("<f8")
    sink.initialize_product(product_name=product_name, dtype=dtype)
    return tuple(
        sink.write_chunk(
            product_name=product_name,
            tile=tile,
            values=np.full(
                tile.core_bounds.shape_yx,
                index + 1,
                dtype=dtype,
            ),
        )
        for index, tile in enumerate(manifest.tiles)
    )


def test_initializes_one_strict_zarr_v3_array_per_product(
    tmp_path: Path,
) -> None:
    """Array geometry and missing/empty policy are explicit and durable."""
    root = tmp_path / "run.zarr"
    sink = _sink(root)

    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))

    group = zarr.open_group(store=root, mode="r")
    array = group["rms"]
    assert array.metadata.zarr_format == 3
    assert array.shape == (5, 7)
    assert array.chunks == (3, 4)
    assert array.dtype == np.dtype("<f8")
    assert array.attrs["hebog_missing_chunk_policy"] == "error"
    assert array.attrs["hebog_write_empty_chunks"] is True
    assert array.attrs["hebog_generation_id"] == "run-001"
    assert group.attrs["hebog_storage_schema_version"] == 2
    assert group.attrs["partition_schema_version"] == 1
    assert group.attrs["partition_origin_yx"] == [0, 0]
    assert group.attrs["generation_id"] == "run-001"
    assert pickle.loads(pickle.dumps(sink)).manifest == sink.manifest
    assert sink.generation_id == "run-001"

    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))


def test_initialization_rejects_conflicting_group_or_array_metadata(
    tmp_path: Path,
) -> None:
    """A reused run store cannot silently acquire different geometry."""
    root = tmp_path / "run.zarr"
    sink = _sink(root)
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))

    with pytest.raises(InvalidProductChunkError, match="metadata"):
        sink.initialize_product(product_name="rms", dtype=np.dtype("<f4"))

    group = zarr.open_group(store=root, mode="r+")
    group.attrs["image_shape_yx"] = [99, 99]
    with pytest.raises(InvalidProductChunkError, match="attribute"):
        _sink(root).initialize_product(
            product_name="mask",
            dtype=np.dtype("u1"),
        )


def test_initialization_rejects_object_arrays(tmp_path: Path) -> None:
    """Intermediate image products never enable object deserialization."""
    sink = _sink(tmp_path / "run.zarr")

    with pytest.raises(ValueError, match="object"):
        sink.initialize_product(product_name="rms", dtype=np.dtype("O"))


def test_writes_and_reads_independent_complete_chunks(tmp_path: Path) -> None:
    """Tile owners preserve global placement, dtype, NaNs, and edge shapes."""
    root = tmp_path / "run.zarr"
    manifest = _manifest()
    sink = _sink(root, manifest)
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


def test_streams_completed_product_as_bounded_canonical_tile_rows(
    tmp_path: Path,
) -> None:
    """Final materialisation reads every validated chunk once in row order."""
    manifest = _manifest()
    sink = _sink(tmp_path / "run.zarr", manifest)
    records = _write_product(sink, manifest, "rms")
    sink.publish_generation(product_names=("rms",), chunks=records)
    maximum_block_bytes = 3 * 7 * np.dtype("<f8").itemsize

    blocks = tuple(
        sink.iter_completed_row_blocks(
            "rms",
            max_block_bytes=maximum_block_bytes,
        )
    )

    assert tuple(block.shape for block in blocks) == ((3, 7), (2, 7))
    assert all(block.nbytes <= maximum_block_bytes for block in blocks)
    assert all(block.flags.c_contiguous for block in blocks)
    assert all(not block.flags.writeable for block in blocks)
    expected = np.block(
        [
            [np.full((3, 4), 1.0), np.full((3, 3), 2.0)],
            [np.full((2, 4), 3.0), np.full((2, 3), 4.0)],
        ]
    )
    np.testing.assert_array_equal(np.concatenate(blocks), expected)


def test_one_tile_completed_product_streams_as_one_existing_chunk(
    tmp_path: Path,
) -> None:
    """Small work avoids multi-tile assembly and produces one row block."""
    manifest = PartitionManifest.create(
        image_shape_yx=(2, 3),
        tile_core_shape_yx=(8, 8),
        halo_yx=(0, 0),
    )
    sink = _sink(tmp_path / "one-tile.zarr", manifest)
    records = _write_product(sink, manifest, "rms")
    sink.publish_generation(product_names=("rms",), chunks=records)

    blocks = tuple(
        sink.iter_completed_row_blocks(
            "rms",
            max_block_bytes=2 * 3 * np.dtype("<f8").itemsize,
        )
    )

    assert len(blocks) == 1
    np.testing.assert_array_equal(blocks[0], 1.0)


def test_completed_row_stream_rejects_unpublished_unknown_or_too_small(
    tmp_path: Path,
) -> None:
    """A row stream requires a published product and admitted row memory."""
    manifest = _manifest()
    sink = _sink(tmp_path / "run.zarr", manifest)
    records = _write_product(sink, manifest, "rms")

    with pytest.raises(InvalidProductGenerationError, match="published"):
        tuple(
            sink.iter_completed_row_blocks(
                "rms",
                max_block_bytes=1024,
            )
        )

    sink.publish_generation(product_names=("rms",), chunks=records)
    with pytest.raises(InvalidProductGenerationError, match="product"):
        tuple(
            sink.iter_completed_row_blocks(
                "mask",
                max_block_bytes=1024,
            )
        )
    with pytest.raises(ValueError, match="memory budget"):
        tuple(
            sink.iter_completed_row_blocks(
                "rms",
                max_block_bytes=3 * 7 * np.dtype("<f8").itemsize - 1,
            )
        )


def test_writes_an_all_fill_value_chunk_for_strict_reads(
    tmp_path: Path,
) -> None:
    """A valid zero chunk remains distinguishable from a missing chunk."""
    manifest = _manifest()
    sink = _sink(tmp_path / "run.zarr", manifest)
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
    sink = _sink(tmp_path / "run.zarr", manifest)
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))
    missing_tile = manifest.tiles[1]
    missing_values = _values_for(1)
    missing = ProductChunk(
        generation_id="run-001",
        product_name="rms",
        tile_id=missing_tile.tile_id,
        core_bounds=missing_tile.core_bounds,
        dtype=missing_values.dtype.str,
        shape_yx=tuple(missing_values.shape),
        content_sha256=hashlib.sha256(
            np.ascontiguousarray(missing_values).tobytes()
        ).hexdigest(),
    )

    with pytest.raises(
        InvalidProductChunkError,
        match="missing",
    ) as exc_info:
        sink.read_chunk(missing)
    assert isinstance(exc_info.value.__cause__, ChunkNotFoundError)


def test_identical_retry_is_idempotent_and_conflict_fails_closed(
    tmp_path: Path,
) -> None:
    """Sequential retries cannot silently replace completed science bytes."""
    manifest = _manifest()
    sink = _sink(tmp_path / "run.zarr", manifest)
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
    sink = _sink(root, manifest)
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
    sink = _sink(tmp_path / "run.zarr", manifest)
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
    sink = _sink(tmp_path / "run.zarr", manifest)
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
    sink = _sink(root, manifest)
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

    with pytest.raises(InvalidProductChunkError, match="generation ID"):
        sink.read_chunk(replace(record, generation_id="run-002"))

    group = zarr.open_group(store=root, mode="r+")
    group["rms"].attrs["hebog_missing_chunk_policy"] = "fill"
    with pytest.raises(InvalidProductChunkError, match="policy"):
        sink.read_chunk(record)


def test_requires_preinitialized_products_and_canonical_tiles(
    tmp_path: Path,
) -> None:
    """Workers cannot race metadata creation or invent storage selections."""
    manifest = _manifest()
    sink = _sink(tmp_path / "run.zarr", manifest)

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
        _sink(
            tmp_path / "run.zarr",
            _manifest(partition_origin_yx=(1, 1)),
        )

    with pytest.raises(ValueError, match="generation ID"):
        _sink(tmp_path / "empty-generation.zarr", generation_id="")


def test_publishes_and_reads_one_exact_generation_idempotently(
    tmp_path: Path,
) -> None:
    """Only a validated marker makes all expected chunks consumable."""
    manifest = _manifest()
    sink = _sink(tmp_path / "run.zarr", manifest)
    records = _write_product(sink, manifest, "rms")

    published = sink.publish_generation(
        product_names=("rms",),
        chunks=reversed(records),
    )

    assert published.generation_id == "run-001"
    assert sink.read_generation() == published
    assert (
        sink.publish_generation(product_names=("rms",), chunks=records)
        == published
    )


def test_interrupted_generation_is_not_published_and_can_resume(
    tmp_path: Path,
) -> None:
    """Missing work fails closed without preventing deterministic retries."""
    manifest = _manifest()
    sink = _sink(tmp_path / "run.zarr", manifest)
    sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))
    records = tuple(
        sink.write_chunk(
            product_name="rms",
            tile=tile,
            values=_values_for(index),
        )
        for index, tile in enumerate(manifest.tiles[:-1])
    )

    with pytest.raises(InvalidProductGenerationError, match="complete"):
        sink.publish_generation(product_names=("rms",), chunks=records)
    with pytest.raises(InvalidProductGenerationError, match="not published"):
        sink.read_generation()

    last_index = len(manifest.tiles) - 1
    resumed = sink.write_chunk(
        product_name="rms",
        tile=manifest.tiles[last_index],
        values=_values_for(last_index),
    )
    published = sink.publish_generation(
        product_names=("rms",),
        chunks=(*records, resumed),
    )
    assert sink.read_generation() == published


def test_generation_validation_rejects_store_corruption_before_publish(
    tmp_path: Path,
) -> None:
    """A complete record set cannot publish corrupt underlying bytes."""
    root = tmp_path / "run.zarr"
    manifest = _manifest()
    sink = _sink(root, manifest)
    records = _write_product(sink, manifest, "rms")
    chunk_path = next(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name != "zarr.json"
    )
    payload = bytearray(chunk_path.read_bytes())
    payload[-1] ^= 1
    chunk_path.write_bytes(payload)

    with pytest.raises(InvalidProductGenerationError, match="invalid"):
        sink.publish_generation(product_names=("rms",), chunks=records)
    with pytest.raises(InvalidProductGenerationError, match="not published"):
        sink.read_generation()


def test_completion_marker_is_immutable_and_run_scoped(tmp_path: Path) -> None:
    """A completed generation cannot be replaced or mixed with another run."""
    root = tmp_path / "run.zarr"
    manifest = _manifest()
    sink = _sink(root, manifest)
    rms_records = _write_product(sink, manifest, "rms")
    first = sink.publish_generation(
        product_names=("rms",),
        chunks=rms_records,
    )
    mask_records = _write_product(sink, manifest, "mask")

    with pytest.raises(ProductGenerationConflictError, match="different"):
        sink.publish_generation(
            product_names=("mask",),
            chunks=mask_records,
        )
    assert sink.read_generation() == first

    other_generation = _sink(root, manifest, generation_id="run-002")
    with pytest.raises(InvalidProductChunkError, match="policy"):
        other_generation.read_chunk(
            replace(rms_records[0], generation_id="run-002")
        )
    with pytest.raises(InvalidProductChunkError, match="attribute"):
        other_generation.initialize_product(
            product_name="diagnostics",
            dtype=np.dtype("<f8"),
        )


def test_read_rejects_a_corrupt_completion_marker(tmp_path: Path) -> None:
    """Completion metadata is validated before any generation is consumed."""
    root = tmp_path / "run.zarr"
    manifest = _manifest()
    sink = _sink(root, manifest)
    records = _write_product(sink, manifest, "rms")
    sink.publish_generation(product_names=("rms",), chunks=records)
    marker = next(root.rglob("completed-generation-v1.json"))
    marker.write_bytes(b"not-json\n")

    with pytest.raises(InvalidProductGenerationError, match="invalid"):
        sink.read_generation()


def test_read_rejects_noncanonical_or_wrong_generation_metadata(
    tmp_path: Path,
) -> None:
    """A marker must be canonical and bound to this sink's run and tiling."""
    root = tmp_path / "run.zarr"
    manifest = _manifest()
    sink = _sink(root, manifest)
    records = _write_product(sink, manifest, "rms")
    published = sink.publish_generation(
        product_names=("rms",),
        chunks=records,
    )
    marker = next(root.rglob("completed-generation-v1.json"))
    pretty = json.dumps(published.model_dump(mode="json"), indent=2)
    marker.write_text(f"{pretty}\n", encoding="utf-8")

    with pytest.raises(InvalidProductGenerationError, match="canonical"):
        sink.read_generation()

    other_records = tuple(
        replace(record, generation_id="run-002") for record in records
    )
    other_generation = ProductGenerationManifest.create(
        generation_id="run-002",
        partition_manifest=manifest,
        product_names=("rms",),
        chunks=other_records,
    )
    marker.write_bytes(other_generation.canonical_json_bytes())
    with pytest.raises(InvalidProductGenerationError, match="generation ID"):
        sink.read_generation()

    other_partition = PartitionManifest.create(
        image_shape_yx=manifest.image_shape_yx,
        tile_core_shape_yx=manifest.image_shape_yx,
        halo_yx=(0, 0),
    )
    other_tile = other_partition.tiles[0]
    other_partition_generation = ProductGenerationManifest.create(
        generation_id="run-001",
        partition_manifest=other_partition,
        product_names=("rms",),
        chunks=(
            ProductChunk(
                generation_id="run-001",
                product_name="rms",
                tile_id=other_tile.tile_id,
                core_bounds=other_tile.core_bounds,
                dtype="<f8",
                shape_yx=other_tile.core_bounds.shape_yx,
                content_sha256="a" * 64,
            ),
        ),
    )
    marker.write_bytes(other_partition_generation.canonical_json_bytes())
    with pytest.raises(InvalidProductGenerationError, match="partition"):
        sink.read_generation()
