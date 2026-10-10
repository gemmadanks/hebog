"""Serializable records for Rapthor's source-finding compatibility boundary.

This module deliberately imports no Rapthor, Prefect, LSMTool, or scheduler
objects. It names the workflow-specific inputs, products, and scientific
profile that a later adapter will translate to Hebog analyses.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal

from hebog.config import SourceFinderConfig


@dataclass(frozen=True, slots=True)
class RapthorCompatibilityConfig:
    """Rapthor/LSMTool choices kept outside the scientific API.

    Rapthor supplies the detection and island thresholds through its imaging
    strategy, and LSMTool's ``filter_by_mask`` decides whether sky-model
    components outside the island mask are removed. The other options
    LSMTool passes to PyBDSF (the RMS boxes, the bright-source threshold,
    the wavelet scales and the zero mean map) are fixed by Hebog's reviewed
    science, so the profile does not offer them; the Rapthor
    source-finding contract maps each to the behaviour that replaces it.
    """

    source_finder: SourceFinderConfig
    filter_sky_model_by_mask: bool = True


@dataclass(frozen=True, slots=True)
class RapthorSourceFindingRequest:
    """Inputs for one Rapthor sector's two-branch compatibility operation."""

    flat_noise_image_path: Path
    primary_beam_corrected_image_path: Path
    sector_vertices_path: Path
    output_directory: Path
    run_id: str
    intrinsic_sky_model_path: Path | None = None
    apparent_sky_model_path: Path | None = None
    bright_intrinsic_sky_model_path: Path | None = None
    beam_measurement_set_paths: tuple[Path, ...] = ()
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None:
        """Reject unsupported versions and empty run identifiers."""
        if self.schema_version != 1:
            raise ValueError("unsupported Rapthor request schema version")
        if not self.run_id:
            raise ValueError("run_id must not be empty")


@dataclass(frozen=True, slots=True)
class RapthorSourceFindingResult:
    """Materialised products consumed by Rapthor after both branches join."""

    catalogue_path: Path
    primary_beam_corrected_rms_path: Path
    flat_noise_rms_path: Path
    source_filtering_mask_path: Path | None
    filtered_intrinsic_sky_model_path: Path
    filtered_apparent_sky_model_path: Path
    diagnostics_path: Path
    source_count: int
    wall_seconds: float
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None:
        """Validate the version and scalar result metadata."""
        if self.schema_version != 1:
            raise ValueError("unsupported Rapthor result schema version")
        if self.source_count < 0:
            raise ValueError("source_count cannot be negative")
        if not isfinite(self.wall_seconds) or self.wall_seconds < 0:
            raise ValueError("wall_seconds must be finite and non-negative")
