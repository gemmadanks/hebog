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
from hebog.validation.hebog_campaign import process_hebog_image

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


def test_external_compact_configuration_uses_selected_model_position() -> None:
    """Like-product compact results use their fitted Gaussian directly."""
    fit = hebog_campaign.phase_five_corrected_candidate_configs()[3]

    assert fit.position_estimator == "selected-model"
    assert fit.model_selection == "free-only"
    assert hebog_campaign.phase_four_candidate_configs()[
        3
    ].position_estimator == ("bounded-context-free")
    assert hebog_campaign.phase_four_candidate_configs()[
        3
    ].model_selection == ("beam-or-free")


def test_external_compact_entry_validates_shape_before_processing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The compact branch uses the shared plane only at its frozen shape."""
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-5-external-compact-blend.json"
    ).datasets[0]
    with pytest.raises(ValueError, match="shape differs"):
        process_hebog_image(
            np.zeros((2, 2), dtype=np.float64),
            dataset,
            tmp_path,
            generation_id="bad-shape",
        )

    observed: dict[str, object] = {}

    def fake_process(  # noqa: PLR0913
        source: object,
        selected_dataset: object,
        directory: Path,
        *,
        shape_yx: tuple[int, int],
        generation_id: str,
        configs: object,
    ) -> tuple[CatalogueSource, ...]:
        observed.update(
            source=source,
            dataset=selected_dataset,
            directory=directory,
            shape_yx=shape_yx,
            generation_id=generation_id,
            configs=configs,
        )
        return ()

    monkeypatch.setattr(hebog_campaign, "_process_hebog_source", fake_process)
    image = np.zeros(dataset.recipe.shape_yx, dtype=np.float64)

    assert (
        process_hebog_image(
            image,
            dataset,
            tmp_path,
            generation_id="external-unit-test",
        )
        == ()
    )
    assert observed["shape_yx"] == dataset.recipe.shape_yx
    assert observed["generation_id"] == "external-unit-test"
    assert observed["configs"] == (
        hebog_campaign.phase_five_corrected_candidate_configs()
    )
