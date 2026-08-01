# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Aligned Zarr v3 storage for intermediate image planes."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import zarr
from zarr.codecs import BytesCodec, Crc32cCodec, ZstdCodec
from zarr.errors import ArrayNotFoundError, ChunkNotFoundError
from zarr.storage import LocalStore

from hebog.data_models.partitioning import PartitionManifest, TilePartition
from hebog.data_models.products import (
    ProductChunk,
    validate_product_name,
)

_IMAGE_DIMENSIONS = 2
_ZARR_FORMAT = 3
_GROUP_ATTRIBUTES: dict[str, Any] = {
    "hebog_storage_schema_version": 1,
    "zarr_format": _ZARR_FORMAT,
}
_ARRAY_ATTRIBUTES: dict[str, Any] = {
    "hebog_missing_chunk_policy": "error",
    "hebog_write_empty_chunks": True,
    "hebog_checksum_codec": "crc32c",
}


class ProductChunkError(ValueError):
    """A Zarr product chunk cannot be safely published or consumed."""


class ProductChunkConflictError(ProductChunkError):
    """A completed Zarr chunk contains different values for one tile."""


class InvalidProductChunkError(ProductChunkError):
    """A Zarr product chunk is missing, corrupt, or inconsistent."""


def _content_sha256(values: npt.NDArray[np.generic]) -> str:
    """Hash canonical C-order array bytes without including store encoding."""
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def _little_endian_dtype(dtype: npt.DTypeLike) -> np.dtype[Any]:
    """Return an explicit portable dtype and reject object arrays."""
    normalized = np.dtype(dtype)
    if normalized.hasobject:
        raise ValueError("Zarr product arrays cannot contain object values")
    return normalized.newbyteorder("<")


def _selection(tile: TilePartition) -> tuple[slice, slice]:
    """Return the global array selection owned by one tile."""
    bounds = tile.core_bounds
    return (
        slice(bounds.y_start, bounds.y_stop),
        slice(bounds.x_start, bounds.x_stop),
    )


class ZarrProductSink:
    """Write complete canonical tile cores into one local Zarr v3 group."""

    def __init__(self, root: Path, manifest: PartitionManifest) -> None:
        """Retain plain metadata without opening or creating a store."""
        if manifest.partition_origin_yx != (0, 0):
            raise ValueError(
                "Zarr chunk writes require a zero partition origin"
            )
        self._root = root.resolve()
        self._manifest = manifest

    @property
    def manifest(self) -> PartitionManifest:
        """Return the immutable partition geometry used by this sink."""
        return self._manifest

    def initialize_product(
        self,
        *,
        product_name: str,
        dtype: npt.DTypeLike,
    ) -> None:
        """Create or validate one product array before worker submission."""
        validate_product_name(product_name)
        normalized_dtype = _little_endian_dtype(dtype)
        group = zarr.open_group(
            store=LocalStore(self._root),
            mode="a",
            zarr_format=_ZARR_FORMAT,
        )
        expected_group_attributes = {
            **_GROUP_ATTRIBUTES,
            "image_shape_yx": list(self._manifest.image_shape_yx),
            "tile_core_shape_yx": list(self._manifest.tile_core_shape_yx),
            "partition_origin_yx": list(self._manifest.partition_origin_yx),
            "partition_schema_version": self._manifest.schema_version,
        }
        for name, expected in expected_group_attributes.items():
            existing = group.attrs.get(name)
            if existing is not None and existing != expected:
                raise InvalidProductChunkError(
                    f"Zarr group attribute {name!r} conflicts with manifest"
                )
            group.attrs[name] = expected

        if product_name in group:
            self._require_array_metadata(
                group[product_name],
                product_name=product_name,
                dtype=normalized_dtype,
            )
            return
        group.create_array(
            product_name,
            shape=self._manifest.image_shape_yx,
            chunks=self._manifest.tile_core_shape_yx,
            dtype=normalized_dtype,
            fill_value=0,
            filters=None,
            serializer=BytesCodec(endian="little"),
            compressors=(ZstdCodec(level=1), Crc32cCodec()),
            chunk_key_encoding={
                "name": "default",
                "configuration": {"separator": "/"},
            },
            attributes=cast(Any, dict(_ARRAY_ATTRIBUTES)),
            config={
                "read_missing_chunks": False,
                "write_empty_chunks": True,
            },
        )

    def _require_array_metadata(
        self,
        array: object,
        *,
        product_name: str,
        dtype: np.dtype[Any] | None = None,
    ) -> Any:
        """Validate the durable geometry and Hebog policy attributes."""
        zarr_array = cast(Any, array)
        if (
            zarr_array.metadata.zarr_format != _ZARR_FORMAT
            or tuple(zarr_array.shape) != self._manifest.image_shape_yx
            or tuple(zarr_array.chunks) != self._manifest.tile_core_shape_yx
            or (dtype is not None and zarr_array.dtype != dtype)
        ):
            raise InvalidProductChunkError(
                f"Zarr product {product_name!r} metadata conflicts with sink"
            )
        for name, expected in _ARRAY_ATTRIBUTES.items():
            if zarr_array.attrs.get(name) != expected:
                raise InvalidProductChunkError(
                    f"Zarr product {product_name!r} policy is invalid"
                )
        return zarr_array.with_config(
            {
                "read_missing_chunks": False,
                "write_empty_chunks": True,
            }
        )

    def _open_array(self, product_name: str) -> Any:
        """Open a pre-created product without racing metadata creation."""
        validate_product_name(product_name)
        try:
            array = zarr.open_array(
                store=LocalStore(self._root),
                path=product_name,
                mode="r+",
            )
        except (ArrayNotFoundError, FileNotFoundError) as error:
            raise InvalidProductChunkError(
                f"Zarr product {product_name!r} is not initialized"
            ) from error
        return self._require_array_metadata(
            array,
            product_name=product_name,
        )

    def _require_canonical_tile(self, tile: TilePartition) -> None:
        """Reject invented records and storage-chunk misalignment."""
        if self._canonical_tile(tile.tile_id) != tile:
            raise ValueError("tile must belong to the canonical manifest")

    def _canonical_tile(self, tile_id: str) -> TilePartition:
        """Resolve one zero-origin row-major tile in constant time."""
        try:
            _, tile_y_index_value, tile_x_index_value = tile_id.split("-")
            tile_y_index = int(tile_y_index_value)
            tile_x_index = int(tile_x_index_value)
            tiles_per_row = (
                self._manifest.image_shape_yx[1]
                + self._manifest.tile_core_shape_yx[1]
                - 1
            ) // self._manifest.tile_core_shape_yx[1]
            tile = self._manifest.tiles[
                tile_y_index * tiles_per_row + tile_x_index
            ]
        except (IndexError, ValueError) as error:
            raise InvalidProductChunkError(
                "Zarr product chunk is not in the canonical manifest"
            ) from error
        if tile.tile_id != tile_id:
            raise InvalidProductChunkError(
                "Zarr product chunk is not in the canonical manifest"
            )
        return tile

    def _record(
        self,
        *,
        product_name: str,
        tile: TilePartition,
        values: npt.NDArray[np.generic],
    ) -> ProductChunk:
        """Build the small logical identity returned to the scheduler."""
        return ProductChunk(
            product_name=product_name,
            tile_id=tile.tile_id,
            core_bounds=tile.core_bounds,
            dtype=values.dtype.str,
            shape_yx=tuple(values.shape),
            content_sha256=_content_sha256(values),
        )

    def write_chunk(
        self,
        *,
        product_name: str,
        tile: TilePartition,
        values: npt.NDArray[np.generic],
    ) -> ProductChunk:
        """Write one complete aligned chunk or accept an identical retry."""
        self._require_canonical_tile(tile)
        array = self._open_array(product_name)
        normalized = np.asarray(values)
        if (
            normalized.ndim != _IMAGE_DIMENSIONS
            or tuple(normalized.shape) != tile.core_bounds.shape_yx
        ):
            raise ValueError(
                "Zarr product values must match the tile core shape"
            )
        if normalized.dtype != array.dtype:
            raise ValueError(
                "Zarr product values must match the initialized dtype"
            )
        record = self._record(
            product_name=product_name,
            tile=tile,
            values=normalized,
        )
        try:
            self._read_values(array=array, tile=tile, record=record)
        except InvalidProductChunkError as error:
            if not isinstance(error.__cause__, ChunkNotFoundError):
                raise ProductChunkConflictError(
                    "published Zarr product chunk contains different values"
                ) from error
        else:
            return record

        array[_selection(tile)] = normalized
        self._read_values(array=array, tile=tile, record=record)
        return record

    def read_chunk(
        self,
        record: ProductChunk,
    ) -> npt.NDArray[np.generic]:
        """Validate one expected chunk and return an owned read-only array."""
        tile = self._canonical_tile(record.tile_id)
        if tile.core_bounds != record.core_bounds:
            raise InvalidProductChunkError(
                "Zarr product chunk is not in the canonical manifest"
            )
        array = self._open_array(record.product_name)
        return self._read_values(array=array, tile=tile, record=record)

    @staticmethod
    def _read_values(
        *,
        array: Any,
        tile: TilePartition,
        record: ProductChunk,
    ) -> npt.NDArray[np.generic]:
        """Validate one chunk selection from an already-open strict array."""
        try:
            values = np.array(
                array[_selection(tile)],
                copy=True,
            )
        except ChunkNotFoundError as error:
            raise InvalidProductChunkError(
                "Zarr product chunk is missing"
            ) from error
        except (OSError, ValueError) as error:
            raise InvalidProductChunkError(
                "Zarr product chunk is corrupt"
            ) from error
        if (
            values.ndim != _IMAGE_DIMENSIONS
            or tuple(values.shape) != record.shape_yx
            or values.dtype.str != record.dtype
        ):
            raise InvalidProductChunkError(
                "Zarr product chunk array metadata disagrees with its record"
            )
        if _content_sha256(values) != record.content_sha256:
            raise InvalidProductChunkError(
                "Zarr product chunk SHA-256 disagrees with its record"
            )
        values.setflags(write=False)
        return values
