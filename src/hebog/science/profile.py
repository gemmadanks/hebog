"""Minimal installed profile for the reviewed continuum science."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from math import isfinite
from typing import Any, cast

from hebog.config import SourceFinderConfig


@dataclass(frozen=True, slots=True)
class ContinuumDetectionProfile:
    """Threshold, scale, and valid-support settings used at runtime."""

    scale_orders: tuple[int, ...]
    support_fraction_bounds: tuple[float, float]
    detection_sigma: float
    island_sigma: float


@dataclass(frozen=True, slots=True)
class ContinuumCorrectionProfile:
    """Reviewed continuum correction settings used at runtime."""

    minimum_island_area_beams: float


@dataclass(frozen=True, slots=True)
class ContinuumScienceProfile:
    """Small phase-neutral projection of the historical review record."""

    matrix: ContinuumDetectionProfile
    corrections: ContinuumCorrectionProfile


def _object(value: object, *, name: str) -> dict[str, Any]:
    """Return one JSON object or reject a malformed installed profile."""
    if not isinstance(value, dict):
        raise ValueError(f"continuum science profile {name} must be an object")
    return cast(dict[str, Any], value)


def load_continuum_science_profile(payload: bytes) -> ContinuumScienceProfile:
    """Project the reviewed JSON record onto fields used by source finding."""
    document = _object(json.loads(payload), name="document")
    matrix = _object(document.get("matrix"), name="matrix")
    corrections = _object(document.get("corrections"), name="corrections")
    scale_orders = tuple(int(value) for value in matrix["scale_orders"])
    support_bounds = tuple(
        float(value) for value in matrix["support_fraction_bounds"]
    )
    if scale_orders != (1, 2, 3):
        raise ValueError(
            "continuum science profile scales must be 1, 2, and 3"
        )
    if support_bounds != (0.5, 1.0):
        raise ValueError(
            "continuum science profile support fraction must span 0.5--1"
        )
    detection_sigma = float(matrix["detection_sigma"])
    island_sigma = float(matrix["island_sigma"])
    minimum_area = float(corrections["minimum_island_area_beams"])
    if (
        not isfinite(detection_sigma)
        or not isfinite(island_sigma)
        or detection_sigma <= island_sigma
        or island_sigma <= 0.0
    ):
        raise ValueError(
            "continuum science thresholds must be positive and ordered"
        )
    if not isfinite(minimum_area) or minimum_area <= 0.0:
        raise ValueError("continuum minimum island area must be positive")
    return ContinuumScienceProfile(
        matrix=ContinuumDetectionProfile(
            scale_orders=scale_orders,
            support_fraction_bounds=(support_bounds[0], support_bounds[1]),
            detection_sigma=detection_sigma,
            island_sigma=island_sigma,
        ),
        corrections=ContinuumCorrectionProfile(
            minimum_island_area_beams=minimum_area
        ),
    )


def configured_science_profile(
    profile: ContinuumScienceProfile,
    config: SourceFinderConfig,
) -> ContinuumScienceProfile:
    """Apply caller thresholds without mutating the installed profile."""
    return replace(
        profile,
        matrix=replace(
            profile.matrix,
            detection_sigma=config.detection_threshold_sigma,
            island_sigma=config.island_threshold_sigma,
        ),
    )
