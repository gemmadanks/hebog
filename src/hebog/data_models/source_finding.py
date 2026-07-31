"""Pipeline-neutral file records safe to pass through an executor."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class SourceFinderRequest:
    """Inputs for one independent source-finding analysis."""

    image_path: Path
    output_directory: Path
    run_id: str
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None:
        """Reject unsupported schema versions and empty run identifiers."""
        if self.schema_version != 1:
            raise ValueError(
                "unsupported source-finder request schema version"
            )
        if not self.run_id:
            raise ValueError("run_id must not be empty")


@dataclass(frozen=True, slots=True)
class SourceFinderResult:
    """Materialised products from one scientific image analysis."""

    catalogue_path: Path
    rms_path: Path
    mask_path: Path
    diagnostics_path: Path
    source_count: int
    wall_seconds: float
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None:
        """Validate the version and scalar result metadata."""
        if self.schema_version != 1:
            raise ValueError("unsupported source-finder result schema version")
        if self.source_count < 0:
            raise ValueError("source_count cannot be negative")
        if not isfinite(self.wall_seconds) or self.wall_seconds < 0:
            raise ValueError("wall_seconds must be finite and non-negative")
