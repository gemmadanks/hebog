"""Serializable identities for independently retryable product chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from hebog.data_models.partitioning import ImageBounds

_PRODUCT_NAME = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*")
_TILE_ID = re.compile(r"tile-[0-9]{5}-[0-9]{5}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def validate_product_name(product_name: str) -> None:
    """Require one path-safe domain product name."""
    if _PRODUCT_NAME.fullmatch(product_name) is None:
        raise ValueError("product name must be a path-safe domain name")


def validate_tile_id(tile_id: str) -> None:
    """Require one canonical row-major tile identifier."""
    if _TILE_ID.fullmatch(tile_id) is None:
        raise ValueError("product chunk tile ID must be canonical")


def _relative_path_for(product_name: str, tile_id: str) -> str:
    """Validate path components and return their canonical chunk path."""
    validate_product_name(product_name)
    validate_tile_id(tile_id)
    return f"{product_name}/{tile_id}.npy"


@dataclass(frozen=True, slots=True)
class ProductChunk:
    """Immutable identity of one atomically published two-dimensional chunk."""

    product_name: str
    tile_id: str
    core_bounds: ImageBounds
    relative_path: str
    dtype: str
    shape_yx: tuple[int, int]
    size_bytes: int
    sha256: str
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None:
        """Reject unsupported, unsafe, or internally inconsistent records."""
        if self.schema_version != 1:
            raise ValueError("unsupported product chunk schema version")
        expected_path = self.relative_path_for(
            self.product_name,
            self.tile_id,
        )
        if self.relative_path != expected_path:
            raise ValueError(
                "product chunk relative path must match its identity"
            )
        if not self.dtype:
            raise ValueError("product chunk dtype must not be empty")
        if self.shape_yx != self.core_bounds.shape_yx:
            raise ValueError("product chunk shape must match its core bounds")
        if self.size_bytes < 1:
            raise ValueError("product chunk byte size must be positive")
        if _SHA256.fullmatch(self.sha256) is None:
            raise ValueError("product chunk SHA-256 must be lowercase hex")

    @staticmethod
    def relative_path_for(product_name: str, tile_id: str) -> str:
        """Return the canonical relative path for one chunk identity."""
        return _relative_path_for(product_name, tile_id)


@dataclass(frozen=True, slots=True)
class ZarrProductChunk:
    """Logical identity of one tile-owned chunk in a Zarr v3 array."""

    product_name: str
    tile_id: str
    core_bounds: ImageBounds
    array_name: str
    dtype: str
    shape_yx: tuple[int, int]
    content_sha256: str
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None:
        """Reject malformed storage-independent chunk identities."""
        if self.schema_version != 1:
            raise ValueError("unsupported Zarr product chunk schema version")
        validate_product_name(self.product_name)
        validate_tile_id(self.tile_id)
        if self.array_name != self.product_name:
            raise ValueError("Zarr array name must match its product name")
        if not self.dtype:
            raise ValueError("Zarr product chunk dtype must not be empty")
        if self.shape_yx != self.core_bounds.shape_yx:
            raise ValueError(
                "Zarr product chunk shape must match its core bounds"
            )
        if _SHA256.fullmatch(self.content_sha256) is None:
            raise ValueError(
                "Zarr product chunk SHA-256 must be lowercase hex"
            )


ProductChunkRecord = ProductChunk | ZarrProductChunk
