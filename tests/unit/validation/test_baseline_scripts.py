"""Tests for the isolated PyBDSF baseline entry points."""

from __future__ import annotations

import hashlib
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


def _script(name: str) -> dict[str, Any]:
    """Load one script without invoking its command-line entry point."""
    root = Path(__file__).parents[3]
    return runpy.run_path(str(root / "scripts" / "benchmark" / name))


def test_reference_configuration_requires_explicit_ordered_thresholds() -> (
    None
):
    """A campaign cannot silently inherit the Rapthor helper defaults."""
    namespace = _script("pybdsf_reference_run.py")
    configuration: Callable[[float, float], dict[str, object]] = namespace[
        "_configuration"
    ]

    assert configuration(5.0, 3.0)["threshold_pixel_sigma"] == 5.0
    assert configuration(5.0, 3.0)["threshold_island_sigma"] == 3.0
    with pytest.raises(ValueError, match="0 < island <= detection"):
        configuration(3.0, 5.0)


def test_directory_identity_excludes_mutable_casa_lock_files(
    tmp_path: Path,
) -> None:
    """Opening a Measurement Set must not change its scientific identity."""
    namespace = _script("run_phase0_pybdsf_baseline.py")
    path_sha256: Callable[[Path], str] = namespace["_path_sha256"]
    (tmp_path / "table.dat").write_bytes(b"science")
    (tmp_path / "table.lock").write_bytes(b"first lock state")

    first = path_sha256(tmp_path)
    (tmp_path / "table.lock").write_bytes(b"second lock state")

    assert path_sha256(tmp_path) == first
    assert first != hashlib.sha256(b"science").hexdigest()
