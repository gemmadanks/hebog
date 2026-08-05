"""Independent generated development matrix for compact blend photometry."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from hebog.validation.campaign_runtime import phase_four_outlier_thresholds
from hebog.validation.campaigns import diagnose_phase_four_realization
from hebog.validation.datasets import (
    DatasetRecord,
    SyntheticRecipe,
    load_dataset_manifest,
    recipe_sha256,
)
from hebog.validation.hebog_campaign import process_hebog_recipe

pytestmark = pytest.mark.equivalence

_DEVELOPMENT_MANIFEST = Path("config/datasets/phase-4r-development-2.json")
_SCIENTIFIC_GATES = Path("config/contracts/phase-4-scientific-gates.json")
_DEVELOPMENT_SEEDS = tuple(range(2026501001, 2026501019))


def _blend_development_case(
    base: DatasetRecord,
    *,
    seed: int,
    pair_angle_offset_degrees: float,
    faint_to_bright_ratio: float,
) -> DatasetRecord:
    """Rotate one independent blend while preserving its total peak flux."""
    blend = next(
        group
        for group in base.association_truth_groups
        if group.resolution_class == "unresolved-blend"
    )
    first_index, second_index = blend.source_indices
    sources = list(base.recipe.sources)
    first = sources[first_index]
    second = sources[second_index]
    total_peak_flux = 0.006
    first_peak = total_peak_flux / (1.0 + faint_to_bright_ratio)
    second_peak = total_peak_flux - first_peak
    center_xy = (103.5, 211.0)
    separation_pixels = 3.8
    angle = np.deg2rad(
        base.beam.position_angle_degrees + pair_angle_offset_degrees
    )
    offset_xy = (
        0.5 * separation_pixels * np.cos(angle),
        0.5 * separation_pixels * np.sin(angle),
    )
    sources[first_index] = first.model_copy(
        update={
            "peak_flux_jy_per_beam": first_peak,
            "x_pixel": center_xy[0] - offset_xy[0],
            "y_pixel": center_xy[1] - offset_xy[1],
        }
    )
    sources[second_index] = second.model_copy(
        update={
            "peak_flux_jy_per_beam": second_peak,
            "x_pixel": center_xy[0] + offset_xy[0],
            "y_pixel": center_xy[1] + offset_xy[1],
        }
    )
    recipe_document = base.recipe.model_dump(mode="json")
    recipe_document.update(
        {
            "seed": seed,
            "sources": [source.model_dump(mode="json") for source in sources],
        }
    )
    recipe = SyntheticRecipe.model_validate(recipe_document)
    brightnesses = np.asarray(
        [
            source.peak_flux_jy_per_beam
            * 2.0
            * np.pi
            * source.major_sigma_pixels
            * source.minor_sigma_pixels
            for source in (sources[first_index], sources[second_index])
        ]
    )
    reference_position_xy = (
        float(
            np.dot(
                brightnesses,
                [sources[first_index].x_pixel, sources[second_index].x_pixel],
            )
            / np.sum(brightnesses)
        ),
        float(
            np.dot(
                brightnesses,
                [sources[first_index].y_pixel, sources[second_index].y_pixel],
            )
            / np.sum(brightnesses)
        ),
    )
    groups = [
        group.model_copy(
            update={
                "reference_position_xy": reference_position_xy,
                "reference_integrated_brightness_jy_pixels_per_beam": float(
                    np.sum(brightnesses)
                ),
            }
        )
        if group.identifier == blend.identifier
        else group
        for group in base.association_truth_groups
    ]
    document = base.model_dump(mode="json")
    document.update(
        {
            "identifier": "phase4u-development-blend-matrix-256",
            "purpose": (
                "Independent rotated and unequal compact blends for Phase 4U "
                "association-flux development"
            ),
            "recipe": recipe.model_dump(mode="json"),
            "recipe_sha256": recipe_sha256(recipe),
            "noise_realization_seeds": [],
            "association_truth_groups": [
                group.model_dump(mode="json") for group in groups
            ],
        }
    )
    return DatasetRecord.model_validate(document)


def test_noisy_rotated_blend_matrix_has_margin_inside_absolute_gate(
    tmp_path: Path,
) -> None:
    """Fresh development blends avoid systematic orientation-dependent loss."""
    base = load_dataset_manifest(_DEVELOPMENT_MANIFEST).datasets[0]
    configurations = tuple(
        (angle, ratio)
        for _ in range(3)
        for ratio in (1.0, 0.5)
        for angle in (0.0, 45.0, 90.0)
    )
    signed_errors: list[float] = []
    for seed, (angle, ratio) in zip(
        _DEVELOPMENT_SEEDS,
        configurations,
        strict=True,
    ):
        dataset = _blend_development_case(
            base,
            seed=seed,
            pair_angle_offset_degrees=angle,
            faint_to_bright_ratio=ratio,
        )
        recipe = dataset.recipe
        candidates = process_hebog_recipe(
            recipe,
            dataset,
            tmp_path / str(seed),
        )
        diagnostic = diagnose_phase_four_realization(
            dataset,
            recipe,
            candidates,
            implementation_identifier="hebog",
            outlier_thresholds=phase_four_outlier_thresholds(
                _SCIENTIFIC_GATES
            ),
            maximum_separation_beams=0.5,
            position_angle_minimum_axis_ratio=1.1,
        )
        result = next(
            item
            for item in diagnostic.association_pairs
            if item.truth_group_identifier == "blend-00001"
        )
        assert result.decision == "matched"
        assert result.integrated_flux_fractional_difference is not None
        signed_errors.append(result.integrated_flux_fractional_difference)

    absolute_errors = np.abs(signed_errors)
    assert float(np.quantile(absolute_errors, 0.95)) < 0.15
    assert abs(float(np.mean(signed_errors))) < 0.08
