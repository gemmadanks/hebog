"""Shared provenance and failure helpers for isolated campaign runners."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json


def canonical_sha256(value: object) -> str:
    """Hash one JSON-compatible value without presentation whitespace."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def dependency_inventory_sha256() -> str:
    """Hash the complete installed distribution inventory."""
    inventory = sorted(
        (
            {
                "name": distribution.metadata["Name"]
                .lower()
                .replace("_", "-"),
                "version": distribution.version,
            }
            for distribution in importlib.metadata.distributions()
        ),
        key=lambda item: item["name"],
    )
    return canonical_sha256(inventory)
