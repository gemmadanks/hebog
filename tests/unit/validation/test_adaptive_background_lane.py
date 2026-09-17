"""Scientific contracts for the adaptive-background development lane."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from hebog.validation.adaptive_background_development import (
    build_adaptive_development_matrix,
)
from hebog.validation.adaptive_background_lane import (
    build_adaptive_development_manifest,
    source_signal_and_truth,
)
from hebog.validation.datasets import iter_dataset_recipes


def test_manifest_exactly_expands_the_approved_population() -> None:
    """Every approved cell becomes four deterministic development images."""
    manifest = build_adaptive_development_manifest()
    matrix = build_adaptive_development_matrix()

    assert manifest.schema_version == 3
    assert manifest.manifest_id == "phase-5-adaptive-background-development"
    assert len(manifest.datasets) == 36
    assert (
        sum(
            len(iter_dataset_recipes(dataset)) for dataset in manifest.datasets
        )
        == 144
    )
    for cell, dataset in zip(matrix, manifest.datasets, strict=True):
        assert dataset.role.value == "development"
        assert (
            tuple(recipe.seed for recipe in iter_dataset_recipes(dataset))
            == cell.noise_seeds
        )
        assert dataset.recipe.shape_yx == (512, 512)
        assert len(dataset.multiscale_truth_groups) == 1
        assert dataset.multiscale_truth_groups[0].morphology == cell.morphology


def test_noiseless_templates_hit_each_nominal_trigger_target() -> None:
    """Calibration occurs before noise and is exact for every cell."""
    manifest = build_adaptive_development_manifest()
    matrix = build_adaptive_development_matrix()

    for cell, dataset in zip(matrix, manifest.datasets, strict=True):
        signal, truth, true_rms = source_signal_and_truth(dataset.recipe)
        assert float(
            np.max(signal)
        ) / dataset.recipe.noise_rms == pytest.approx(
            cell.target_nominal_peak_sigma, rel=2e-12
        )
        assert truth.dtype == np.bool_
        assert np.any(truth)
        assert np.all(true_rms > 0)
        if cell.placement_id == "tile-corner":
            y_pixels, x_pixels = np.nonzero(truth)
            assert min(y_pixels) < 256 <= max(y_pixels)
            assert min(x_pixels) < 256 <= max(x_pixels)


def test_mixed_template_places_three_quarters_of_truth_flux_in_halo() -> None:
    """The mixed source has one bright core without losing extended truth."""
    manifest = build_adaptive_development_manifest()
    matrix = build_adaptive_development_matrix()

    for cell, dataset in zip(matrix, manifest.datasets, strict=True):
        if cell.morphology != "mixed-compact-extended":
            continue
        core, halo = dataset.recipe.sources
        core_flux = (
            core.peak_flux_jy_per_beam
            * core.major_sigma_pixels
            * (core.minor_sigma_pixels)
        )
        halo_flux = (
            halo.peak_flux_jy_per_beam
            * halo.major_sigma_pixels
            * (halo.minor_sigma_pixels)
        )
        assert halo_flux / (core_flux + halo_flux) == pytest.approx(0.75)


def test_shell_template_ring_diameter_matches_declared_extent() -> None:
    """Shell knot centres must span the reviewed major extent exactly."""
    manifest = build_adaptive_development_manifest()
    matrix = build_adaptive_development_matrix()

    for cell, dataset in zip(matrix, manifest.datasets, strict=True):
        if cell.morphology != "shell":
            continue
        x_positions = tuple(
            source.x_pixel for source in dataset.recipe.sources
        )
        diameter_beams = (
            max(x_positions) - min(x_positions)
        ) / dataset.beam.major_fwhm_pixels
        assert diameter_beams == pytest.approx(cell.extent_major_beams)


def test_curved_filament_knots_obey_reviewed_spacing() -> None:
    """All seven curved-filament knots stay within the 1.25-beam bound."""
    manifest = build_adaptive_development_manifest()
    matrix = build_adaptive_development_matrix()

    for cell, dataset in zip(matrix, manifest.datasets, strict=True):
        if cell.morphology != "curved-filament":
            continue
        sources = dataset.recipe.sources
        assert len(sources) == 7
        assert len({source.peak_flux_jy_per_beam for source in sources}) == 1
        spacings = tuple(
            np.hypot(
                right.x_pixel - left.x_pixel,
                right.y_pixel - left.y_pixel,
            )
            / dataset.beam.major_fwhm_pixels
            for left, right in pairwise(sources)
        )
        assert max(spacings) <= 1.25 + 1e-12
