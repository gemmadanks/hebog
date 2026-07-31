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


def _validate_rms_box(value: tuple[int, int], name: str) -> None:
    """Validate a positive RMS window width and step."""
    width, step = value
    if width <= 0 or step <= 0:
        raise ValueError(f"{name} width and step must be positive")
    if step > width:
        raise ValueError(f"{name} step cannot exceed its width")


@dataclass(frozen=True, slots=True)
class RapthorCompatibilityConfig:
    """Rapthor/LSMTool choices kept outside the scientific API.

    Rapthor supplies detection and island thresholds through its imaging
    strategy. The remaining values reproduce the currently traced LSMTool
    compatibility profile and are not universal Hebog defaults.
    """

    source_finder: SourceFinderConfig
    rms_box_pixels: tuple[int, int] = (150, 50)
    bright_source_rms_box_pixels: tuple[int, int] = (35, 7)
    adaptive_rms_threshold_sigma: float = 75.0
    estimate_background: bool = False
    use_spatial_rms: bool = True
    use_adaptive_rms: bool = True
    use_multiscale: bool = True
    multiscale_levels: int = 3
    filter_sky_model_by_mask: bool = True

    def __post_init__(self) -> None:
        """Validate compatibility values before workflow execution."""
        _validate_rms_box(self.rms_box_pixels, "rms_box_pixels")
        _validate_rms_box(
            self.bright_source_rms_box_pixels,
            "bright_source_rms_box_pixels",
        )
        if (
            not isfinite(self.adaptive_rms_threshold_sigma)
            or self.adaptive_rms_threshold_sigma <= 0
        ):
            raise ValueError(
                "adaptive_rms_threshold_sigma must be finite and positive"
            )
        if self.multiscale_levels < 1:
            raise ValueError("multiscale_levels must be positive")


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
