"""Versioned completion records for intermediate product generations.

A store publishes one generation as a record per row of tiles and, last, a
small index naming each row record's SHA-256. A task reading a window parses
the index and the rows its window meets, so its cost follows the image's
side rather than its area.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from hebog.data_models.partitioning import PartitionManifest, TilePartition
from hebog.data_models.products import ProductChunk, validate_product_name

_SHA256 = re.compile(r"[0-9a-f]{64}")


class _CanonicalRecord(BaseModel):
    """Immutable record with one deterministic JSON encoding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_json_bytes(self) -> bytes:
        """Return deterministic UTF-8 JSON with one final newline."""
        document = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return f"{document}\n".encode()

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> Self:
        """Validate one canonical serialized record."""
        record = cls.model_validate_json(payload)
        if record.canonical_json_bytes() != payload:
            raise ValueError(f"{cls.__name__} JSON must be canonical")
        return record


def _validate_product_names(product_names: tuple[str, ...]) -> None:
    """Require at least one path-safe product, unique and sorted."""
    if not product_names:
        raise ValueError("generation must contain at least one product")
    for product_name in product_names:
        validate_product_name(product_name)
    if product_names != tuple(sorted(set(product_names))):
        raise ValueError(
            "generation product names must be unique and canonical"
        )


class ProductGenerationRow(_CanonicalRecord):
    """Chunk records of one row of tiles in a published generation.

    Chunks are ordered by product, then by tile column, so the record of
    product ``p`` and column ``x`` is ``chunks[p * tiles_per_row + x]``.
    """

    generation_id: str
    tile_y_index: int
    product_names: tuple[str, ...]
    chunks: tuple[ProductChunk, ...]
    schema_version: Literal[2] = 2

    @property
    def tiles_per_row(self) -> int:
        """Return the number of tile columns the row records."""
        return len(self.chunks) // len(self.product_names)

    @model_validator(mode="after")
    def _validate_row(self) -> Self:
        """Require every product of each column of this row once, in order."""
        _validate_product_names(self.product_names)
        tiles_per_row = self.tiles_per_row
        if tiles_per_row == 0 or len(self.chunks) % len(self.product_names):
            raise ValueError("generation row must record whole tile columns")
        expected = tuple(
            (product_name, f"tile-{self.tile_y_index:05d}-{x_index:05d}")
            for product_name in self.product_names
            for x_index in range(tiles_per_row)
        )
        actual = tuple(
            (chunk.product_name, chunk.tile_id) for chunk in self.chunks
        )
        if actual != expected:
            raise ValueError(
                "generation row chunks must be its tiles in canonical order"
            )
        if any(
            chunk.generation_id != self.generation_id for chunk in self.chunks
        ):
            raise ValueError("generation row contains a mixed generation ID")
        return self


class ProductGenerationIndex(_CanonicalRecord):
    """Completion marker naming one generation's row records.

    The partition is stored as the geometry its canonical tiles are planned
    from, and ``row_sha256[y]`` is the SHA-256 of row ``y``'s canonical JSON,
    so a reader verifies each row record it reads against the marker.
    """

    generation_id: str
    image_shape_yx: tuple[int, int]
    tile_core_shape_yx: tuple[int, int]
    halo_yx: tuple[int, int]
    partition_origin_yx: tuple[int, int]
    product_names: tuple[str, ...]
    row_sha256: tuple[str, ...]
    schema_version: Literal[2] = 2

    @model_validator(mode="after")
    def _validate_index(self) -> Self:
        """Reject an empty identity, products or malformed row digests."""
        if not self.generation_id:
            raise ValueError("generation ID must not be empty")
        _validate_product_names(self.product_names)
        if not self.row_sha256 or any(
            _SHA256.fullmatch(digest) is None for digest in self.row_sha256
        ):
            raise ValueError(
                "generation row SHA-256 values must be lowercase hex"
            )
        return self

    def describes(self, manifest: PartitionManifest) -> bool:
        """Return whether the index was published on ``manifest``."""
        return (
            self.image_shape_yx == manifest.image_shape_yx
            and self.tile_core_shape_yx == manifest.tile_core_shape_yx
            and self.halo_yx == manifest.halo_yx
            and self.partition_origin_yx == manifest.partition_origin_yx
            and len(self.row_sha256) == manifest.tiles[-1].tile_y_index + 1
        )


class ProductGenerationManifest(_CanonicalRecord):
    """Exact chunk set that makes one intermediate generation consumable."""

    generation_id: str
    partition_manifest: PartitionManifest
    product_names: tuple[str, ...]
    chunks: tuple[ProductChunk, ...]
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def _validate_generation(self) -> Self:
        """Reject incomplete, ambiguous, or non-canonical generations."""
        self._validate_identity_and_products()
        tiles_by_id = {
            tile.tile_id: tile for tile in self.partition_manifest.tiles
        }
        self._validate_chunk_records(tiles_by_id)
        self._validate_exact_chunk_set()
        return self

    def _validate_identity_and_products(self) -> None:
        """Validate the generation key and canonical product set."""
        if not self.generation_id:
            raise ValueError("generation ID must not be empty")
        _validate_product_names(self.product_names)

    def _validate_chunk_records(
        self,
        tiles_by_id: dict[str, TilePartition],
    ) -> None:
        """Validate chunk identity, ownership, and product dtype."""
        seen: dict[tuple[str, str], ProductChunk] = {}
        dtypes: dict[str, str] = {}
        for chunk in self.chunks:
            if chunk.generation_id != self.generation_id:
                raise ValueError("generation contains a mixed generation ID")
            key = (chunk.product_name, chunk.tile_id)
            previous = seen.get(key)
            if previous is not None:
                qualifier = "duplicate" if previous == chunk else "conflicting"
                raise ValueError(
                    f"generation contains {qualifier} chunk records"
                )
            seen[key] = chunk
            if chunk.product_name not in self.product_names:
                raise ValueError("generation contains an unexpected product")
            tile = tiles_by_id.get(chunk.tile_id)
            if tile is None:
                raise ValueError("generation contains an unexpected tile")
            if chunk.core_bounds != tile.core_bounds:
                raise ValueError(
                    "generation chunk core bounds disagree with ownership"
                )
            existing_dtype = dtypes.setdefault(
                chunk.product_name,
                chunk.dtype,
            )
            if existing_dtype != chunk.dtype:
                raise ValueError(
                    "generation product chunks must use one dtype"
                )

    def _validate_exact_chunk_set(self) -> None:
        """Require every product-owner pair once in canonical order."""
        expected = tuple(
            (product_name, tile.tile_id)
            for product_name in self.product_names
            for tile in self.partition_manifest.tiles
        )
        actual = tuple(
            (chunk.product_name, chunk.tile_id) for chunk in self.chunks
        )
        missing = set(expected).difference(actual)
        if missing:
            raise ValueError("generation is missing expected chunk records")
        if actual != expected:
            raise ValueError("generation chunks must use canonical order")

    @classmethod
    def create(
        cls,
        *,
        generation_id: str,
        partition_manifest: PartitionManifest,
        product_names: Iterable[str],
        chunks: Iterable[ProductChunk],
    ) -> Self:
        """Canonicalize caller results before validating exact completion."""
        return cls(
            generation_id=generation_id,
            partition_manifest=partition_manifest,
            product_names=tuple(sorted(product_names)),
            chunks=tuple(
                sorted(
                    chunks,
                    key=lambda chunk: (
                        chunk.product_name,
                        chunk.tile_id,
                    ),
                )
            ),
        )

    def rows(self) -> tuple[ProductGenerationRow, ...]:
        """Split the chunk records into one record per row of tiles."""
        tiles = self.partition_manifest.tiles
        tiles_per_row = tiles[-1].tile_x_index + 1
        product_count = len(self.product_names)
        return tuple(
            ProductGenerationRow(
                generation_id=self.generation_id,
                tile_y_index=y_index,
                product_names=self.product_names,
                chunks=tuple(
                    self.chunks[
                        product_index * len(tiles)
                        + y_index * tiles_per_row
                        + x
                    ]
                    for product_index in range(product_count)
                    for x in range(tiles_per_row)
                ),
            )
            for y_index in range(tiles[-1].tile_y_index + 1)
        )

    def index(self, row_sha256: Iterable[str]) -> ProductGenerationIndex:
        """Return the completion marker for row records of these digests."""
        manifest = self.partition_manifest
        return ProductGenerationIndex(
            generation_id=self.generation_id,
            image_shape_yx=manifest.image_shape_yx,
            tile_core_shape_yx=manifest.tile_core_shape_yx,
            halo_yx=manifest.halo_yx,
            partition_origin_yx=manifest.partition_origin_yx,
            product_names=self.product_names,
            row_sha256=tuple(row_sha256),
        )
