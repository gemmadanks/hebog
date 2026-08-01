"""Versioned completion records for intermediate product generations."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from hebog.data_models.partitioning import PartitionManifest, TilePartition
from hebog.data_models.products import ProductChunk, validate_product_name


class ProductGenerationManifest(BaseModel):
    """Exact chunk set that makes one intermediate generation consumable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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
        if not self.product_names:
            raise ValueError("generation must contain at least one product")
        for product_name in self.product_names:
            validate_product_name(product_name)
        if self.product_names != tuple(sorted(set(self.product_names))):
            raise ValueError(
                "generation product names must be unique and canonical"
            )

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
        """Validate one serialized completion record."""
        return cls.model_validate_json(payload)
