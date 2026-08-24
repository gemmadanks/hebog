# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Aligned Zarr v3 storage for intermediate image planes."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Generator, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import zarr
from zarr.codecs import BytesCodec, Crc32cCodec, ZstdCodec
from zarr.core.buffer import default_buffer_prototype
from zarr.core.sync import sync
from zarr.errors import ArrayNotFoundError, ChunkNotFoundError
from zarr.storage import LocalStore

from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import (
    ProductChunk,
    validate_product_name,
)

_IMAGE_DIMENSIONS = 2
_GENERATION_VALIDATION_TILE_ROWS = 4
_WINDOW_CHUNK_CACHE_SIZE = 4
_ZARR_FORMAT = 3
_COMPLETION_KEY = ".hebog/completed-generation-v1.json"
_GROUP_ATTRIBUTES: dict[str, Any] = {
    "hebog_storage_schema_version": 3,
    "zarr_format": _ZARR_FORMAT,
}


def _compressors(dtype: np.dtype[Any]) -> tuple[Any, ...]:
    """Compress boolean masks but avoid wasting CPU on numeric planes."""
    if dtype == np.dtype(np.bool_):
        return (ZstdCodec(level=1), Crc32cCodec())
    return (Crc32cCodec(),)


def _compression_policy(dtype: np.dtype[Any]) -> str:
    """Return the durable product-role codec policy name."""
    return "zstd-1" if dtype == np.dtype(np.bool_) else "none"


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


class ProductGenerationError(ProductChunkError):
    """A Zarr generation cannot be safely published or consumed."""


class InvalidProductGenerationError(ProductGenerationError):
    """A completion manifest or one of its chunks is invalid."""


class ProductGenerationConflictError(ProductGenerationError):
    """A different completion manifest already publishes this generation."""


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

    def __init__(
        self,
        root: Path,
        manifest: PartitionManifest,
        *,
        generation_id: str,
    ) -> None:
        """Retain plain metadata without opening or creating a store."""
        if manifest.partition_origin_yx != (0, 0):
            raise ValueError(
                "Zarr chunk writes require a zero partition origin"
            )
        if not generation_id:
            raise ValueError("Zarr generation ID must not be empty")
        self._root = root.resolve()
        self._manifest = manifest
        self._generation_id = generation_id
        self._access_depth = 0
        self._array_cache: dict[str, Any] = {}
        self._published_generation_cache: ProductGenerationManifest | None = (
            None
        )

    @property
    def manifest(self) -> PartitionManifest:
        """Return the immutable partition geometry used by this sink."""
        return self._manifest

    @property
    def generation_id(self) -> str:
        """Return the immutable run identity stored with every chunk."""
        return self._generation_id

    @contextmanager
    def access_session(self) -> Generator[None]:
        """Amortise immutable metadata opens within one bounded coarse task.

        Array handles and the parsed completion record remain local to this
        sink instance and are discarded at the outermost session boundary.
        Chunk bytes are still read and checksum-validated on every access.
        """
        if self._access_depth == 0:
            self._array_cache.clear()
            self._published_generation_cache = None
        self._access_depth += 1
        try:
            yield
        finally:
            self._access_depth -= 1
            if self._access_depth == 0:
                self._array_cache.clear()
                self._published_generation_cache = None

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
            "generation_id": self._generation_id,
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
            compressors=_compressors(normalized_dtype),
            chunk_key_encoding={
                "name": "default",
                "configuration": {"separator": "/"},
            },
            attributes=cast(
                Any,
                {
                    **_ARRAY_ATTRIBUTES,
                    "hebog_generation_id": self._generation_id,
                    "hebog_compression_policy": _compression_policy(
                        normalized_dtype
                    ),
                },
            ),
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
        expected_attributes = {
            **_ARRAY_ATTRIBUTES,
            "hebog_generation_id": self._generation_id,
            "hebog_compression_policy": _compression_policy(
                np.dtype(zarr_array.dtype)
            ),
        }
        for name, expected in expected_attributes.items():
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
        cached = self._array_cache.get(product_name)
        if cached is not None:
            return cached
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
        validated = self._require_array_metadata(
            array,
            product_name=product_name,
        )
        if self._access_depth:
            self._array_cache[product_name] = validated
        return validated

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
            generation_id=self._generation_id,
            product_name=product_name,
            tile_id=tile.tile_id,
            core_bounds=tile.core_bounds,
            dtype=values.dtype.str,
            shape_yx=tuple(values.shape),
            content_sha256=_content_sha256(values),
        )

    @staticmethod
    def _chunk_exists(array: Any, tile: TilePartition) -> bool:
        """Return whether one canonical encoded chunk key already exists."""
        chunk_key = array.metadata.encode_chunk_key(
            (tile.tile_y_index, tile.tile_x_index)
        )
        return bool(sync((array.store_path / chunk_key).exists()))

    def write_chunk(
        self,
        *,
        product_name: str,
        tile: TilePartition,
        values: npt.NDArray[np.generic],
    ) -> ProductChunk:
        """Write one aligned chunk or content-validate an existing retry.

        Fresh LocalStore writes are atomic and use the required CRC32C codec.
        Their content SHA-256 is validated in the mandatory full-generation
        check before a completion marker can be published.
        """
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
        if self._chunk_exists(array, tile):
            try:
                self._read_values(array=array, tile=tile, record=record)
            except InvalidProductChunkError as error:
                if not isinstance(error.__cause__, ChunkNotFoundError):
                    raise ProductChunkConflictError(
                        "published Zarr product chunk contains different "
                        "values"
                    ) from error
            else:
                return record

        array[_selection(tile)] = normalized
        return record

    def read_chunk(
        self,
        record: ProductChunk,
    ) -> npt.NDArray[np.generic]:
        """Validate one expected chunk and return an owned read-only array."""
        if record.generation_id != self._generation_id:
            raise InvalidProductChunkError(
                "Zarr product chunk has a different generation ID"
            )
        tile = self._canonical_tile(record.tile_id)
        if tile.core_bounds != record.core_bounds:
            raise InvalidProductChunkError(
                "Zarr product chunk is not in the canonical manifest"
            )
        array = self._open_array(record.product_name)
        return self._read_values(array=array, tile=tile, record=record)

    @staticmethod
    def _require_values_match_record(
        values: npt.NDArray[np.generic],
        record: ProductChunk,
    ) -> npt.NDArray[np.generic]:
        """Validate one owned array against its immutable chunk record."""
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

    @classmethod
    def _read_values(
        cls,
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
        return cls._require_values_match_record(values, record)

    @classmethod
    def _read_product_block(
        cls,
        *,
        array: Any,
        tiles: tuple[TilePartition, ...],
        records: tuple[ProductChunk, ...],
    ) -> tuple[npt.NDArray[np.generic], ...]:
        """Read and validate one contiguous bounded canonical tile block."""
        first_bounds = tiles[0].core_bounds
        last_bounds = tiles[-1].core_bounds
        selection = (
            slice(first_bounds.y_start, last_bounds.y_stop),
            slice(first_bounds.x_start, last_bounds.x_stop),
        )
        try:
            row = np.array(array[selection], copy=True)
        except ChunkNotFoundError as error:
            raise InvalidProductChunkError(
                "Zarr product chunk is missing"
            ) from error
        except (OSError, ValueError) as error:
            raise InvalidProductChunkError(
                "Zarr product chunk is corrupt"
            ) from error
        values_by_tile: list[npt.NDArray[np.generic]] = []
        for tile, record in zip(tiles, records, strict=True):
            bounds = tile.core_bounds
            values = np.ascontiguousarray(
                row[
                    bounds.y_start - first_bounds.y_start : bounds.y_stop
                    - first_bounds.y_start,
                    bounds.x_start - first_bounds.x_start : bounds.x_stop
                    - first_bounds.x_start,
                ]
            )
            values_by_tile.append(
                cls._require_values_match_record(values, record)
            )
        return tuple(values_by_tile)

    def _require_generation_chunks(
        self,
        generation: ProductGenerationManifest,
    ) -> None:
        """Validate identity, geometry, and every referenced store chunk."""
        self._require_generation_identity(generation)
        tile_count = len(self._manifest.tiles)
        tiles_per_row = (
            self._manifest.image_shape_yx[1]
            + self._manifest.tile_core_shape_yx[1]
            - 1
        ) // self._manifest.tile_core_shape_yx[1]
        tiles_per_validation_block = (
            tiles_per_row * _GENERATION_VALIDATION_TILE_ROWS
        )
        try:
            for product_index, product_name in enumerate(
                generation.product_names
            ):
                array = self._open_array(product_name)
                product_start = product_index * tile_count
                for row_start in range(
                    0,
                    tile_count,
                    tiles_per_validation_block,
                ):
                    row_stop = min(
                        row_start + tiles_per_validation_block,
                        tile_count,
                    )
                    self._read_product_block(
                        array=array,
                        tiles=self._manifest.tiles[row_start:row_stop],
                        records=generation.chunks[
                            product_start + row_start : product_start
                            + row_stop
                        ],
                    )
        except ProductChunkError as error:
            raise InvalidProductGenerationError(
                "completion manifest references an invalid product chunk"
            ) from error

    def _require_generation_identity(
        self,
        generation: ProductGenerationManifest,
    ) -> None:
        """Require a published record for this exact run and partition."""
        if generation.generation_id != self._generation_id:
            raise InvalidProductGenerationError(
                "completion manifest has a different generation ID"
            )
        if generation.partition_manifest != self._manifest:
            raise InvalidProductGenerationError(
                "completion manifest has a different partition manifest"
            )

    def publish_generation(
        self,
        *,
        product_names: Iterable[str],
        chunks: Iterable[ProductChunk],
    ) -> ProductGenerationManifest:
        """Conditionally publish one exact, fully validated generation."""
        try:
            generation = ProductGenerationManifest.create(
                generation_id=self._generation_id,
                partition_manifest=self._manifest,
                product_names=product_names,
                chunks=chunks,
            )
        except ValueError as error:
            raise InvalidProductGenerationError(
                "product chunks do not form a complete generation"
            ) from error
        with self.access_session():
            self._require_generation_chunks(generation)
        payload = generation.canonical_json_bytes()
        buffer = default_buffer_prototype().buffer.from_bytes(payload)
        with LocalStore(self._root) as store:
            sync(store.set_if_not_exists(_COMPLETION_KEY, buffer))
            published = store.get_sync(_COMPLETION_KEY)
        if published is None or published.to_bytes() != payload:
            raise ProductGenerationConflictError(
                "a different completion manifest is already published"
            )
        return generation

    def _read_published_generation(self) -> ProductGenerationManifest:
        """Read and validate the immutable record without rereading chunks."""
        if self._published_generation_cache is not None:
            return self._published_generation_cache
        with LocalStore(self._root, read_only=True) as store:
            stored = store.get_sync(_COMPLETION_KEY)
        if stored is None:
            raise InvalidProductGenerationError(
                "product generation is not published"
            )
        payload = stored.to_bytes()
        try:
            generation = ProductGenerationManifest.from_json_bytes(payload)
        except ValueError as error:
            raise InvalidProductGenerationError(
                f"published completion manifest is invalid: {error}"
            ) from error
        if generation.canonical_json_bytes() != payload:
            raise InvalidProductGenerationError(
                "published completion manifest is not canonical"
            )
        self._require_generation_identity(generation)
        if self._access_depth:
            self._published_generation_cache = generation
        return generation

    def read_generation(self) -> ProductGenerationManifest:
        """Read and fully validate the published completion manifest."""
        with self.access_session():
            generation = self._read_published_generation()
            self._require_generation_chunks(generation)
        return generation

    def read_completed_window(
        self,
        product_name: str,
        bounds: ImageBounds,
    ) -> npt.NDArray[np.generic]:
        """Read one checksum-validated bounded window from owned chunks."""
        return self.read_completed_windows(product_name, (bounds,))[0]

    def read_completed_windows(
        self,
        product_name: str,
        bounds_collection: Iterable[ImageBounds],
    ) -> tuple[npt.NDArray[np.generic], ...]:
        """Read windows through a bounded cache of validated owned chunks."""
        requested_bounds = tuple(bounds_collection)
        if not requested_bounds:
            return ()
        for bounds in requested_bounds:
            bounds.require_inside(self._manifest.image_shape_yx)
        validate_product_name(product_name)
        generation = self._read_published_generation()
        if product_name not in generation.product_names:
            raise InvalidProductGenerationError(
                "published generation does not contain product "
                f"{product_name!r}"
            )
        product_index = generation.product_names.index(product_name)
        tile_count = len(self._manifest.tiles)
        core_y, core_x = self._manifest.tile_core_shape_yx
        tiles_per_row = (
            self._manifest.image_shape_yx[1] + core_x - 1
        ) // core_x
        array = self._open_array(product_name)
        cache: OrderedDict[int, npt.NDArray[np.generic]] = OrderedDict()
        windows: list[npt.NDArray[np.generic]] = []
        for bounds in requested_bounds:
            tile_y_start = bounds.y_start // core_y
            tile_y_stop = (bounds.y_stop - 1) // core_y
            tile_x_start = bounds.x_start // core_x
            tile_x_stop = (bounds.x_stop - 1) // core_x
            first_tile_index = tile_y_start * tiles_per_row + tile_x_start
            first_record = generation.chunks[
                product_index * tile_count + first_tile_index
            ]
            window = np.empty(
                bounds.shape_yx,
                dtype=np.dtype(first_record.dtype),
            )
            for tile_y_index in range(tile_y_start, tile_y_stop + 1):
                tile_indices = tuple(
                    tile_y_index * tiles_per_row + tile_x_index
                    for tile_x_index in range(tile_x_start, tile_x_stop + 1)
                )
                row_values = {
                    tile_index: cache[tile_index]
                    for tile_index in tile_indices
                    if tile_index in cache
                }
                missing_indices = tuple(
                    tile_index
                    for tile_index in tile_indices
                    if tile_index not in row_values
                )
                if len(missing_indices) > 1 and not row_values:
                    missing_tiles = tuple(
                        self._manifest.tiles[tile_index]
                        for tile_index in missing_indices
                    )
                    missing_records = tuple(
                        generation.chunks[
                            product_index * tile_count + tile_index
                        ]
                        for tile_index in missing_indices
                    )
                    row_values.update(
                        zip(
                            missing_indices,
                            self._read_product_block(
                                array=array,
                                tiles=missing_tiles,
                                records=missing_records,
                            ),
                            strict=True,
                        )
                    )
                else:
                    for tile_index in missing_indices:
                        row_values[tile_index] = self._read_values(
                            array=array,
                            tile=self._manifest.tiles[tile_index],
                            record=generation.chunks[
                                product_index * tile_count + tile_index
                            ],
                        )
                for tile_index in tile_indices:
                    values = row_values[tile_index]
                    cache.pop(tile_index, None)
                    if len(cache) >= _WINDOW_CHUNK_CACHE_SIZE:
                        cache.popitem(last=False)
                    cache[tile_index] = values
                    tile = self._manifest.tiles[tile_index]
                    overlap_y_start = max(
                        bounds.y_start,
                        tile.core_bounds.y_start,
                    )
                    overlap_y_stop = min(
                        bounds.y_stop,
                        tile.core_bounds.y_stop,
                    )
                    overlap_x_start = max(
                        bounds.x_start,
                        tile.core_bounds.x_start,
                    )
                    overlap_x_stop = min(
                        bounds.x_stop,
                        tile.core_bounds.x_stop,
                    )
                    window[
                        overlap_y_start - bounds.y_start : overlap_y_stop
                        - bounds.y_start,
                        overlap_x_start - bounds.x_start : overlap_x_stop
                        - bounds.x_start,
                    ] = values[
                        overlap_y_start
                        - tile.core_bounds.y_start : overlap_y_stop
                        - tile.core_bounds.y_start,
                        overlap_x_start
                        - tile.core_bounds.x_start : overlap_x_stop
                        - tile.core_bounds.x_start,
                    ]
            window.setflags(write=False)
            windows.append(window)
        return tuple(windows)

    def iter_completed_row_blocks(
        self,
        product_name: str,
        *,
        max_block_bytes: int,
    ) -> Iterator[npt.NDArray[np.generic]]:
        """Yield validated full-width tile rows for final materialisation.

        Every storage chunk is read and checksum-validated exactly once. A
        multi-tile row is assembled into one owned C-contiguous block. The
        caller must admit enough memory for one full tile row; this is bounded
        by image width times tile-core height rather than full image height.
        A one-tile image returns its already-owned chunk without an assembly
        copy.
        """
        if max_block_bytes < 1:
            raise ValueError("row-block memory budget must be positive")
        validate_product_name(product_name)
        generation = self._read_published_generation()
        if product_name not in generation.product_names:
            raise InvalidProductGenerationError(
                "published generation does not contain product "
                f"{product_name!r}"
            )
        records_by_tile = {
            chunk.tile_id: chunk
            for chunk in generation.chunks
            if chunk.product_name == product_name
        }
        tile_rows: dict[int, list[TilePartition]] = {}
        for tile in self._manifest.tiles:
            tile_rows.setdefault(tile.tile_y_index, []).append(tile)
        for row_tiles in tile_rows.values():
            first_record = records_by_tile[row_tiles[0].tile_id]
            dtype = np.dtype(first_record.dtype)
            row_height = row_tiles[0].core_bounds.shape_yx[0]
            required_bytes = (
                row_height * self._manifest.image_shape_yx[1] * dtype.itemsize
            )
            if required_bytes > max_block_bytes:
                raise ValueError(
                    "row-block memory budget is below one canonical tile row: "
                    f"requires {required_bytes} bytes"
                )
            if len(row_tiles) == 1:
                yield self.read_chunk(first_record)
                continue
            block = np.empty(
                (row_height, self._manifest.image_shape_yx[1]),
                dtype=dtype,
            )
            for tile in row_tiles:
                values = self.read_chunk(records_by_tile[tile.tile_id])
                bounds = tile.core_bounds
                block[:, bounds.x_start : bounds.x_stop] = values
            block.setflags(write=False)
            yield block
