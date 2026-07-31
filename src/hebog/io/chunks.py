"""Atomic filesystem-backed publication of retryable product chunks."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import cast

import numpy as np
import numpy.typing as npt

from hebog.data_models.partitioning import TilePartition
from hebog.data_models.products import ProductChunk

_IMAGE_DIMENSIONS = 2


class ProductChunkError(ValueError):
    """A product chunk cannot be safely published or consumed."""


class ProductChunkConflictError(ProductChunkError):
    """A published chunk has a different identity for the same output key."""


class InvalidProductChunkError(ProductChunkError):
    """A published chunk no longer matches its immutable record."""


def _file_sha256(path: Path) -> str:
    """Hash a bounded file without retaining its complete contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_values(
    tile: TilePartition,
    values: npt.NDArray[np.generic],
) -> npt.NDArray[np.generic]:
    """Require one non-object two-dimensional array matching the owned core."""
    array = np.asarray(values)
    if (
        array.ndim != _IMAGE_DIMENSIONS
        or array.shape != tile.core_bounds.shape_yx
    ):
        raise ValueError("product chunk values must match the tile core shape")
    if array.dtype.hasobject:
        raise ValueError("product chunks cannot contain object arrays")
    return array


class FilesystemProductSink:
    """Publish immutable NumPy chunks beneath one caller-owned directory."""

    def __init__(self, root: Path) -> None:
        """Resolve the output root without creating files at construction."""
        self._root = root.resolve()

    def _product_directory(self, product_name: str, tile_id: str) -> Path:
        """Validate one identity before creating its contained directory."""
        ProductChunk.relative_path_for(product_name, tile_id)
        product_directory = self._root / product_name
        product_directory.mkdir(parents=True, exist_ok=True)
        if not product_directory.resolve().is_relative_to(self._root):
            raise ProductChunkError(
                "product directory must remain inside the sink root"
            )
        return product_directory

    def write_chunk(
        self,
        *,
        product_name: str,
        tile: TilePartition,
        values: npt.NDArray[np.generic],
    ) -> ProductChunk:
        """Atomically publish one core or reuse an identical existing chunk."""
        relative_path = ProductChunk.relative_path_for(
            product_name,
            tile.tile_id,
        )
        array = _validate_values(tile, values)
        product_directory = self._product_directory(
            product_name,
            tile.tile_id,
        )
        descriptor, candidate_name = tempfile.mkstemp(
            prefix=f".{tile.tile_id}.",
            suffix=".partial",
            dir=product_directory,
        )
        candidate = Path(candidate_name)
        final_path = self._root / relative_path
        try:
            with os.fdopen(descriptor, "wb") as handle:
                np.save(handle, array, allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
            chunk = ProductChunk(
                product_name=product_name,
                tile_id=tile.tile_id,
                core_bounds=tile.core_bounds,
                relative_path=relative_path,
                dtype=array.dtype.str,
                shape_yx=tuple(array.shape),
                size_bytes=candidate.stat().st_size,
                sha256=_file_sha256(candidate),
            )
            try:
                os.link(candidate, final_path)
            except FileExistsError:
                self._require_identical_existing(final_path, chunk)
            return chunk
        finally:
            candidate.unlink(missing_ok=True)

    def _require_identical_existing(
        self,
        path: Path,
        expected: ProductChunk,
    ) -> None:
        """Accept an idempotent retry and reject a conflicting publication."""
        if (
            path.is_symlink()
            or path.stat().st_size != expected.size_bytes
            or _file_sha256(path) != expected.sha256
        ):
            raise ProductChunkConflictError(
                "published product chunk contains different bytes"
            )

    def read_chunk(
        self,
        chunk: ProductChunk,
    ) -> npt.NDArray[np.generic]:
        """Validate and return one owned read-only published array."""
        path = self._root / chunk.relative_path
        if not path.parent.resolve().is_relative_to(self._root):
            raise InvalidProductChunkError(
                "product chunk path escapes the sink root"
            )
        if not path.is_file() or path.is_symlink():
            raise InvalidProductChunkError("product chunk file is missing")
        if path.stat().st_size != chunk.size_bytes:
            raise InvalidProductChunkError(
                "product chunk byte size no longer matches its record"
            )
        if _file_sha256(path) != chunk.sha256:
            raise InvalidProductChunkError(
                "product chunk SHA-256 no longer matches its record"
            )
        try:
            with path.open("rb") as handle:
                loaded: object = np.load(handle, allow_pickle=False)
        except (OSError, ValueError) as error:
            raise InvalidProductChunkError(
                "product chunk is not a readable NumPy array"
            ) from error
        if not isinstance(loaded, np.ndarray):
            raise InvalidProductChunkError(
                "product chunk must contain one NumPy array"
            )
        values = cast(npt.NDArray[np.generic], loaded)
        if (
            values.ndim != _IMAGE_DIMENSIONS
            or tuple(values.shape) != chunk.shape_yx
            or values.dtype.str != chunk.dtype
        ):
            raise InvalidProductChunkError(
                "product chunk array metadata no longer matches its record"
            )
        values.setflags(write=False)
        return values
