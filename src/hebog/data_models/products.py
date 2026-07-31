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


@dataclass(frozen=True, slots=True)
class ProductChunk:
    """Logical identity of one tile-owned chunk in a product array."""

    product_name: str
    tile_id: str
    core_bounds: ImageBounds
    dtype: str
    shape_yx: tuple[int, int]
    content_sha256: str
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None:
        """Reject malformed chunk identities before storage access."""
        if self.schema_version != 1:
            raise ValueError("unsupported product chunk schema version")
        validate_product_name(self.product_name)
        validate_tile_id(self.tile_id)
        if not self.dtype:
            raise ValueError("product chunk dtype must not be empty")
        if self.shape_yx != self.core_bounds.shape_yx:
            raise ValueError("product chunk shape must match its core bounds")
        if _SHA256.fullmatch(self.content_sha256) is None:
            raise ValueError("product chunk SHA-256 must be lowercase hex")
