"""File-oriented records safe to pass through Dask and Rapthor."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _empty_metadata() -> dict[str, Any]:
    """Create an explicitly typed empty metadata mapping."""
    return {}


@dataclass(frozen=True, slots=True)
class SourceFinderRequest:
    """Inputs for one independent source-finding analysis."""

    image_path: Path
    output_directory: Path
    run_id: str


@dataclass(frozen=True, slots=True)
class SourceFinderResult:
    """Materialised outputs and lightweight execution metadata."""

    catalogue_path: Path
    rms_path: Path
    mask_path: Path
    source_count: int
    wall_seconds: float
    metadata: dict[str, Any] = field(default_factory=_empty_metadata)
