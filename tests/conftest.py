"""Shared test fixtures for Hebog."""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip POSIX-bound sealed-record reconstruction on Windows only."""
    if os.name != "nt":
        return
    marker = pytest.mark.skip(
        reason=(
            "sealed historical record binds POSIX path spelling; "
            "the exact reconstruction remains covered by Linux CI"
        )
    )
    for item in items:
        if item.get_closest_marker("posix_frozen_record") is not None:
            item.add_marker(marker)
