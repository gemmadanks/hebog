"""Tests for shared isolated-campaign runtime helpers."""

from __future__ import annotations

import hashlib

from hebog.validation.campaign_runtime import (
    canonical_sha256,
    dependency_inventory_sha256,
)


def test_canonical_hash_ignores_json_presentation() -> None:
    """Shared shard identity depends on values rather than whitespace."""
    value = {"b": [2, 3], "a": 1}
    canonical = b'{"a":1,"b":[2,3]}'

    assert canonical_sha256(value) == hashlib.sha256(canonical).hexdigest()


def test_dependency_inventory_hash_is_available() -> None:
    """Shared runtime provenance hashes the installed distributions."""
    assert len(dependency_inventory_sha256()) == 64
