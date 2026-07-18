"""Immutable scientific and execution configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceFinderConfig:
    """Configuration shared by serial and distributed executions.

    The initial defaults mirror the common PyBDSF threshold relationship.
    Exact Rapthor defaults will be frozen during the baseline phase in the
    implementation plan.
    """

    detection_sigma: float = 5.0
    island_sigma: float = 3.0
    adaptive_rms: bool = True
    multiscale: bool = True
    max_wavelet_scale: int = 3
    batch_target_seconds: float = 0.5

    def __post_init__(self) -> None:
        """Validate threshold and batching invariants."""
        if self.detection_sigma <= 0:
            raise ValueError("detection_sigma must be positive")
        if self.island_sigma <= 0:
            raise ValueError("island_sigma must be positive")
        if self.island_sigma >= self.detection_sigma:
            raise ValueError("island_sigma must be lower than detection_sigma")
        if self.max_wavelet_scale < 0:
            raise ValueError("max_wavelet_scale cannot be negative")
        if self.batch_target_seconds <= 0:
            raise ValueError("batch_target_seconds must be positive")
