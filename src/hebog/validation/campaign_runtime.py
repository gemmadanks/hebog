"""Shared provenance and failure helpers for isolated campaign runners."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

from hebog.validation.comparison import CatalogueOutlierThresholds
from hebog.validation.contracts import (
    load_phase_four_scientific_gates,
)


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


def phase_four_outlier_thresholds(path: Path) -> CatalogueOutlierThresholds:
    """Load the unchanged community-science catastrophic thresholds."""
    outlier = load_phase_four_scientific_gates(path).catastrophic_outlier
    return CatalogueOutlierThresholds(
        position_beams=outlier.position_beams,
        peak_flux_fractional_difference=(
            outlier.peak_flux_fractional_difference
        ),
        integrated_flux_fractional_difference=(
            outlier.integrated_flux_fractional_difference
        ),
        fitted_axis_fractional_difference=(
            outlier.fitted_axis_fractional_difference
        ),
        deconvolved_axis_fractional_difference=(
            outlier.deconvolved_axis_fractional_difference
        ),
    )
