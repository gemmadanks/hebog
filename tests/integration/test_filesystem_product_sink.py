"""Contract tests for atomic filesystem-backed product chunks."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO

import numpy as np
import numpy.typing as npt
import pytest

import hebog.io.chunks as chunk_io
from hebog.data_models import PartitionManifest, ProductChunk, TilePartition
from hebog.io import (
    FilesystemProductSink,
    InvalidProductChunkError,
    ProductChunkConflictError,
    ProductChunkError,
    ProductSink,
)

pytestmark = pytest.mark.integration


def _tile() -> TilePartition:
    """Return a complete non-square core for small filesystem tests."""
    return PartitionManifest.create(
        image_shape_yx=(2, 3),
        tile_core_shape_yx=(4, 4),
        halo_yx=(0, 0),
    ).tiles[0]


def _values() -> npt.NDArray[np.float64]:
    """Return deterministic values including an invalid scientific pixel."""
    return np.array([[1.0, np.nan, 3.0], [4.0, 5.0, 6.0]])


def _accepts_product_sink(
    sink: ProductSink[ProductChunk],
) -> ProductSink[ProductChunk]:
    """Exercise structural conformance without a concrete dependency."""
    return sink


def _identity_for_bytes(
    chunk: ProductChunk,
    path: Path,
) -> ProductChunk:
    """Bind an existing test record to deliberately substituted bytes."""
    return replace(
        chunk,
        size_bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_writes_and_reads_one_checksummed_chunk(tmp_path: Path) -> None:
    """A published chunk preserves dtype, shape, bounds, and invalid pixels."""
    root = tmp_path / "products"
    sink = FilesystemProductSink(root)

    chunk = _accepts_product_sink(sink).write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )

    path = root / chunk.relative_path
    assert chunk.product_name == "rms"
    assert chunk.tile_id == "tile-00000-00000"
    assert chunk.core_bounds == _tile().core_bounds
    assert chunk.shape_yx == (2, 3)
    assert chunk.dtype == "<f8"
    assert chunk.size_bytes == path.stat().st_size
    assert chunk.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert not tuple(root.rglob("*.partial"))

    restored = sink.read_chunk(chunk)

    np.testing.assert_array_equal(restored, _values())
    assert restored.dtype == np.dtype("<f8")
    assert not restored.flags.writeable


def test_identical_retry_reuses_the_published_chunk(tmp_path: Path) -> None:
    """A completed task can be retried without replacing its durable output."""
    root = tmp_path / "products"
    sink = FilesystemProductSink(root)
    first = sink.write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )
    path = root / first.relative_path
    modified_at = path.stat().st_mtime_ns

    second = sink.write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )

    assert second == first
    assert path.stat().st_mtime_ns == modified_at
    assert not tuple(root.rglob("*.partial"))


def test_conflicting_retry_preserves_the_first_chunk(tmp_path: Path) -> None:
    """The same product and tile cannot silently acquire different results."""
    root = tmp_path / "products"
    sink = FilesystemProductSink(root)
    first = sink.write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )
    original = (root / first.relative_path).read_bytes()

    with pytest.raises(ProductChunkConflictError, match="different bytes"):
        sink.write_chunk(
            product_name="rms",
            tile=_tile(),
            values=np.zeros((2, 3), dtype=np.float64),
        )

    assert (root / first.relative_path).read_bytes() == original


def test_interrupted_serialization_leaves_no_visible_chunk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed writer removes its private partial file before publication."""
    root = tmp_path / "products"
    sink = FilesystemProductSink(root)

    def fail_after_partial_write(
        handle: BinaryIO,
        values: object,
        *,
        allow_pickle: bool,
    ) -> None:
        del values, allow_pickle
        handle.write(b"partial")
        raise OSError("injected serialization failure")

    monkeypatch.setattr(chunk_io.np, "save", fail_after_partial_write)

    with pytest.raises(OSError, match="injected"):
        sink.write_chunk(
            product_name="rms",
            tile=_tile(),
            values=_values(),
        )

    assert not (root / "rms" / "tile-00000-00000.npy").exists()
    assert not tuple(root.rglob("*.partial"))


def test_retry_recovers_after_publication_response_is_lost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry recognizes output published before a worker failure."""
    root = tmp_path / "products"
    sink = FilesystemProductSink(root)
    original_link = os.link

    def publish_then_fail(source: Path, destination: Path) -> None:
        original_link(source, destination)
        raise OSError("injected lost task response")

    monkeypatch.setattr(chunk_io.os, "link", publish_then_fail)
    with pytest.raises(OSError, match="lost task response"):
        sink.write_chunk(
            product_name="rms",
            tile=_tile(),
            values=_values(),
        )
    monkeypatch.setattr(chunk_io.os, "link", original_link)

    recovered = sink.write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )

    np.testing.assert_array_equal(sink.read_chunk(recovered), _values())
    assert not tuple(root.rglob("*.partial"))


def test_read_rejects_a_corrupt_published_chunk(tmp_path: Path) -> None:
    """Checksums fail closed when durable product bytes change."""
    root = tmp_path / "products"
    sink = FilesystemProductSink(root)
    chunk = sink.write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )
    (root / chunk.relative_path).write_bytes(b"corrupt")

    with pytest.raises(InvalidProductChunkError, match="byte size"):
        sink.read_chunk(chunk)


def test_read_rejects_same_size_checksum_corruption(tmp_path: Path) -> None:
    """Byte changes cannot evade validation by preserving file length."""
    root = tmp_path / "products"
    sink = FilesystemProductSink(root)
    chunk = sink.write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )
    path = root / chunk.relative_path
    payload = bytearray(path.read_bytes())
    payload[-1] ^= 1
    path.write_bytes(payload)

    with pytest.raises(InvalidProductChunkError, match="SHA-256"):
        sink.read_chunk(chunk)


def test_read_rejects_a_missing_published_chunk(tmp_path: Path) -> None:
    """A manifest record is not evidence that its durable bytes still exist."""
    root = tmp_path / "products"
    sink = FilesystemProductSink(root)
    chunk = sink.write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )
    (root / chunk.relative_path).unlink()

    with pytest.raises(InvalidProductChunkError, match="missing"):
        sink.read_chunk(chunk)


def test_read_rejects_non_array_bytes_with_a_matching_identity(
    tmp_path: Path,
) -> None:
    """A checksum alone cannot turn arbitrary bytes into an array product."""
    root = tmp_path / "products"
    sink = FilesystemProductSink(root)
    chunk = sink.write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )
    path = root / chunk.relative_path
    path.write_bytes(b"not a NumPy array")
    substituted = _identity_for_bytes(chunk, path)

    with pytest.raises(InvalidProductChunkError, match="readable NumPy"):
        sink.read_chunk(substituted)


def test_read_rejects_a_multi_array_archive(tmp_path: Path) -> None:
    """A chunk contains exactly one array rather than an NPZ collection."""
    root = tmp_path / "products"
    sink = FilesystemProductSink(root)
    chunk = sink.write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )
    path = root / chunk.relative_path
    with path.open("wb") as handle:
        np.savez(handle, values=_values())
    substituted = _identity_for_bytes(chunk, path)

    with pytest.raises(InvalidProductChunkError, match="one NumPy array"):
        sink.read_chunk(substituted)


def test_read_rejects_array_metadata_disagreement(tmp_path: Path) -> None:
    """The durable dtype must agree with the small manifest record."""
    sink = FilesystemProductSink(tmp_path / "products")
    chunk = sink.write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )

    with pytest.raises(InvalidProductChunkError, match="metadata"):
        sink.read_chunk(replace(chunk, dtype="<f4"))


@pytest.mark.skipif(os.name == "nt", reason="symlink setup needs privileges")
def test_write_rejects_a_product_directory_outside_the_root(
    tmp_path: Path,
) -> None:
    """A caller-created product symlink cannot redirect worker writes."""
    root = tmp_path / "products"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "rms").symlink_to(outside, target_is_directory=True)
    sink = FilesystemProductSink(root)

    with pytest.raises(ProductChunkError, match="inside the sink root"):
        sink.write_chunk(
            product_name="rms",
            tile=_tile(),
            values=_values(),
        )


@pytest.mark.skipif(os.name == "nt", reason="symlink setup needs privileges")
def test_read_rejects_a_product_directory_outside_the_root(
    tmp_path: Path,
) -> None:
    """A product symlink cannot redirect validated reads outside the root."""
    outside_root = tmp_path / "outside"
    outside_sink = FilesystemProductSink(outside_root)
    chunk = outside_sink.write_chunk(
        product_name="rms",
        tile=_tile(),
        values=_values(),
    )
    root = tmp_path / "products"
    root.mkdir()
    (root / "rms").symlink_to(
        outside_root / "rms",
        target_is_directory=True,
    )

    with pytest.raises(InvalidProductChunkError, match="escapes"):
        FilesystemProductSink(root).read_chunk(chunk)


@pytest.mark.parametrize(
    ("product_name", "values", "message"),
    [
        ("../rms", np.zeros((2, 3)), "product name"),
        ("rms", np.zeros(6), "core shape"),
        ("rms", np.zeros((3, 2)), "core shape"),
        ("rms", np.array([[object(), object(), object()]] * 2), "object"),
    ],
)
def test_write_rejects_unsafe_or_incompatible_chunks(
    tmp_path: Path,
    product_name: str,
    values: npt.NDArray[np.generic],
    message: str,
) -> None:
    """Invalid work fails before a product directory or file is created."""
    sink = FilesystemProductSink(tmp_path / "products")

    with pytest.raises(ValueError, match=message):
        sink.write_chunk(
            product_name=product_name,
            tile=_tile(),
            values=values,
        )
