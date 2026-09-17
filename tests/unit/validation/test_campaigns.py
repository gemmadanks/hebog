# pyright: reportPrivateUsage=false
"""Tests for reproducible Phase 4 paired-campaign assembly."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from hebog.data_models import ImageBounds
from hebog.validation import hebog_campaign
from hebog.validation.campaigns import (
    _association_truth_source,
    _source_strata,
    diagnose_phase_four_realization,
    phase_four_truth_source,
)
from hebog.validation.comparison import (
    CatalogueOutlierThresholds,
    CatalogueSource,
)
from hebog.validation.datasets import (
    iter_dataset_recipes,
    load_dataset_manifest,
)

_ROOT = Path(__file__).parents[3]


def test_realization_diagnostics_retain_unmatched_association_group() -> None:
    """Group gates remain paired even when one unresolved blend is missed."""
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4-regression.json"
    ).datasets[1]
    recipe = iter_dataset_recipes(dataset)[0]
    candidates = tuple(
        phase_four_truth_source(
            recipe.sources[group.source_indices[0]],
            dataset,
            identifier=f"candidate-{group.identifier}",
        )
        for group in dataset.association_truth_groups
        if group.resolution_class == "individually-resolvable"
    )

    result = diagnose_phase_four_realization(
        dataset,
        recipe,
        candidates,
        implementation_identifier="hebog",
        outlier_thresholds=CatalogueOutlierThresholds(
            position_beams=0.5,
            peak_flux_fractional_difference=0.5,
            integrated_flux_fractional_difference=0.5,
            fitted_axis_fractional_difference=0.5,
            deconvolved_axis_fractional_difference=1.0,
        ),
        position_angle_minimum_axis_ratio=1.1,
    )

    assert result.status == "success"
    assert result.candidate_count == len(candidates)
    assert any(
        pair.decision == "unmatched-truth-group"
        and pair.resolution_class == "unresolved-blend"
        for pair in result.association_pairs
    )
    assert len(result.source_pairs) == len(candidates)


def test_association_uses_fitted_total_before_canonicalization() -> None:
    """Group flux uses fit evidence; individual rows keep peak-as-total."""
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4-regression.json"
    ).datasets[1]
    recipe = iter_dataset_recipes(dataset)[0]
    candidates: list[CatalogueSource] = []
    for group in dataset.association_truth_groups:
        truth = _association_truth_source(group, recipe, dataset)
        candidates.append(
            replace(
                truth,
                identifier=f"candidate-{group.identifier}",
                integrated_flux_jy=0.5 * truth.integrated_flux_jy,
                association_integrated_flux_jy=truth.integrated_flux_jy,
            )
        )

    result = diagnose_phase_four_realization(
        dataset,
        recipe,
        candidates,
        implementation_identifier="hebog",
        outlier_thresholds=CatalogueOutlierThresholds(
            position_beams=0.5,
            peak_flux_fractional_difference=0.5,
            integrated_flux_fractional_difference=0.5,
            fitted_axis_fractional_difference=0.5,
            deconvolved_axis_fractional_difference=1.0,
        ),
        position_angle_minimum_axis_ratio=1.1,
    )

    blend = next(
        item
        for item in result.association_pairs
        if item.resolution_class == "unresolved-blend"
    )
    assert blend.integrated_flux_fractional_difference == 0.0


def test_gaussian_component_view_retains_fitted_total_flux() -> None:
    """Like-product comparison does not apply Rapthor source semantics."""
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4-regression.json"
    ).datasets[1]
    recipe = iter_dataset_recipes(dataset)[0]
    group = next(
        item
        for item in dataset.association_truth_groups
        if item.resolution_class == "individually-resolvable"
    )
    truth = _association_truth_source(group, recipe, dataset)
    candidate = replace(
        truth,
        identifier="candidate-component",
        deconvolution_status="unresolved",
        deconvolved_shape=None,
        deconvolved_major_fwhm_degrees=None,
        quality_flags=("unresolved",),
        peak_flux_jy_per_beam=0.5 * truth.integrated_flux_jy,
    )

    source_view = diagnose_phase_four_realization(
        dataset,
        recipe,
        (candidate,),
        implementation_identifier="hebog",
        outlier_thresholds=CatalogueOutlierThresholds(
            position_beams=0.5,
            peak_flux_fractional_difference=1.0,
            integrated_flux_fractional_difference=1.0,
            fitted_axis_fractional_difference=1.0,
            deconvolved_axis_fractional_difference=1.0,
        ),
        position_angle_minimum_axis_ratio=1.1,
    )
    component_view = diagnose_phase_four_realization(
        dataset,
        recipe,
        (candidate,),
        implementation_identifier="hebog",
        outlier_thresholds=CatalogueOutlierThresholds(
            position_beams=0.5,
            peak_flux_fractional_difference=1.0,
            integrated_flux_fractional_difference=1.0,
            fitted_axis_fractional_difference=1.0,
            deconvolved_axis_fractional_difference=1.0,
        ),
        position_angle_minimum_axis_ratio=1.1,
        catalogue_semantics="fitted-gaussian-component",
    )

    source_pair = next(
        item for item in source_view.source_pairs if item.decision == "matched"
    )
    component_pair = next(
        item
        for item in component_view.source_pairs
        if item.decision == "matched"
    )
    assert source_pair.integrated_flux_fractional_difference == pytest.approx(
        -0.5
    )
    assert component_pair.integrated_flux_fractional_difference == 0.0


def test_source_diagnostics_do_not_union_conflicting_shape_strata() -> None:
    """One source receives only its governed extension classification."""
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4r-qualification-replacement.json"
    ).datasets[0]
    group = next(
        item
        for item in dataset.association_truth_groups
        if item.source_indices == (5,)
    )

    strata = _source_strata(dataset, group)

    assert "shape-marginal-resolved" in strata
    assert "shape-clear-resolved" not in strata


def test_declared_point_truth_survives_projection_roundoff() -> None:
    """The analytic point stratum remains unresolved across a wide WCS."""
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4s-qualification.json"
    ).datasets[0]
    recipe = iter_dataset_recipes(dataset)[0]
    point_indices = next(
        stratum.source_indices
        for stratum in dataset.classification_strata
        if stratum.identifier == "shape-unresolved"
    )
    point_groups = tuple(
        group
        for group in dataset.association_truth_groups
        if group.source_indices[0] in point_indices
    )

    truth = tuple(
        _association_truth_source(group, recipe, dataset)
        for group in point_groups
    )

    assert {source.deconvolution_status for source in truth} == {"unresolved"}
    assert all(
        source.integrated_flux_jy == source.peak_flux_jy_per_beam
        for source in truth
    )


def test_external_array_source_returns_owned_bounded_windows() -> None:
    """The common FITS plane enters the compact branch without aliasing."""
    image = np.arange(20, dtype=np.float64).reshape(4, 5)
    image[2, 3] = np.nan
    source = hebog_campaign._ArrayImageSource(image)
    bounds = ImageBounds(y_start=1, y_stop=4, x_start=2, x_stop=5)

    first = source.read_window(bounds)
    first.values[0, 0] = -1.0
    second = source.read_windows((bounds,))[0]

    assert second.values[0, 0] == image[1, 2]
    assert not second.valid_pixels[1, 1]
