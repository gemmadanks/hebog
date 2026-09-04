"""Scientific contracts for the adaptive-background development lane."""

from __future__ import annotations

from itertools import pairwise
from typing import cast

import numpy as np
import pytest
from pydantic import ValidationError

from hebog.validation.adaptive_background_development import (
    build_adaptive_development_matrix,
)
from hebog.validation.adaptive_background_lane import (
    AdaptiveDevelopmentObservation,
    AdaptiveExecutorComparison,
    AdaptiveScienceSummary,
    build_adaptive_development_manifest,
    evaluate_adaptive_development,
    evaluate_phase_five_adaptive_risk,
    input_identifier,
    source_signal_and_truth,
    truth_linked_source_topology,
)
from hebog.validation.datasets import iter_dataset_recipes


def _summary(**changes: object) -> AdaptiveScienceSummary:
    values: dict[str, object] = {
        "product_valid": True,
        "completeness": 1.0,
        "integrated_flux_absolute_fractional_error": 0.04,
        "mask_iou": 0.82,
        "split": False,
        "support_recall": 0.94,
        "background_error_median_rms": 0.02,
        "background_error_p95_rms": 0.08,
        "rms_error_median_fraction": 0.01,
        "rms_error_p95_fraction": 0.04,
        "source_count": 1,
    }
    values.update(changes)
    return AdaptiveScienceSummary.model_validate(values)


def _geometry_failures(decision: dict[str, object]) -> list[str]:
    """Return the first geometry's typed failure list."""
    geometries = cast(
        tuple[dict[str, object], ...], decision["geometry_decisions"]
    )
    return cast(list[str], geometries[0]["failures"])


def _passing_evidence() -> tuple[
    tuple[AdaptiveDevelopmentObservation, ...],
    tuple[AdaptiveExecutorComparison, ...],
]:
    observations: list[AdaptiveDevelopmentObservation] = []
    invariance: list[AdaptiveExecutorComparison] = []
    for cell in build_adaptive_development_matrix():
        for seed in cell.noise_seeds:
            identifier = input_identifier(cell, seed)
            observations.append(
                AdaptiveDevelopmentObservation(
                    input_id=identifier,
                    cell_id=cell.cell_id,
                    seed=seed,
                    trigger_cohort=cell.trigger_cohort,
                    pre_adaptive_maximum_sigma=(
                        60.0
                        if cell.trigger_cohort == "below"
                        else 75.0
                        if cell.trigger_cohort == "boundary"
                        else 90.0
                    ),
                    adaptive_candidate_positions_yx=(
                        ((256.0, 256.0),)
                        if cell.trigger_cohort == "above"
                        else ()
                    ),
                    adaptive_activation_intersects_truth=(
                        cell.trigger_cohort == "above"
                    ),
                    adaptive=_summary(),
                    coarse=_summary(),
                )
            )
        if cell.trigger_cohort == "above":
            identifier = input_identifier(cell, cell.noise_seeds[0])
            invariance.append(
                AdaptiveExecutorComparison(
                    input_id=identifier,
                    serial_science_sha256="a" * 64,
                    existing_dask_science_sha256="a" * 64,
                )
            )
    return tuple(observations), tuple(invariance)


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


def test_truth_linked_topology_separates_remote_false_detections() -> None:
    """Remote catalogue rows are reliability errors, not fragmentation."""
    truth = np.zeros((40, 50), dtype=np.bool_)
    truth[18:23, 23:28] = True

    topology = truth_linked_source_topology(
        ((20.0, 25.0), (22.0, 30.0), (3.0, 45.0)),
        truth,
        association_radius_pixels=3.0,
    )

    assert topology.truth_linked_source_indices == (0, 1)
    assert topology.unmatched_source_indices == (2,)
    assert topology.truth_linked_split is True


def test_truth_linked_topology_rejects_invalid_geometry() -> None:
    """The development evaluator fails closed on malformed linkage input."""
    truth = np.zeros((4, 4), dtype=np.bool_)
    truth[2, 2] = True

    with pytest.raises(ValueError, match="two-dimensional boolean"):
        truth_linked_source_topology(
            ((2.0, 2.0),),
            np.ones((4, 4)),
            association_radius_pixels=1.0,
        )
    with pytest.raises(ValueError, match="finite and non-negative"):
        truth_linked_source_topology(
            ((2.0, 2.0),),
            truth,
            association_radius_pixels=float("nan"),
        )
    with pytest.raises(ValueError, match="must not be empty"):
        truth_linked_source_topology(
            (),
            np.zeros((4, 4), dtype=np.bool_),
            association_radius_pixels=1.0,
        )
    with pytest.raises(ValueError, match="source positions must be finite"):
        truth_linked_source_topology(
            ((float("nan"), 2.0),),
            truth,
            association_radius_pixels=1.0,
        )

    out_of_bounds = truth_linked_source_topology(
        ((-1.0, 2.0),),
        truth,
        association_radius_pixels=1.0,
    )
    assert out_of_bounds.truth_linked_source_indices == ()
    assert out_of_bounds.unmatched_source_indices == (0,)


def test_truth_linked_topology_links_a_hollow_shell_centroid() -> None:
    """A real shell source is linked even when its centroid is in the hole."""
    truth = np.zeros((31, 31), dtype=np.bool_)
    truth[5, 5:26] = True
    truth[25, 5:26] = True
    truth[5:26, 5] = True
    truth[5:26, 25] = True

    topology = truth_linked_source_topology(
        ((15.0, 15.0), (29.0, 29.0)),
        truth,
        association_radius_pixels=1.0,
    )

    assert topology.truth_linked_source_indices == (0,)
    assert topology.unmatched_source_indices == (1,)


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


def test_passing_evidence_closes_only_the_development_risk() -> None:
    """A fully passing lane cannot claim qualification or release readiness."""
    observations, invariance = _passing_evidence()

    decision = evaluate_adaptive_development(observations, invariance)

    assert decision["status"] == "pass"
    assert decision["claim"] == (
        "development-risk-closed-not-qualification-or-release-readiness"
    )
    assert decision["input_count"] == 144
    assert decision["geometry_count"] == 12
    assert decision["failed_geometry_count"] == 0
    assert decision["executor_invariance_passed"] is True


def test_risk_gate_reports_absolute_objectives_without_binding() -> None:
    """Fast development gates regression before fresh comparator parity."""
    observations, invariance = _passing_evidence()
    objective_only = tuple(
        item.model_copy(
            update={
                "adaptive": item.adaptive.model_copy(
                    update={
                        "integrated_flux_absolute_fractional_error": 0.40,
                    }
                ),
                "coarse": item.coarse.model_copy(
                    update={
                        "integrated_flux_absolute_fractional_error": 0.40,
                    }
                ),
            }
        )
        for item in observations
    )

    decision = evaluate_phase_five_adaptive_risk(objective_only, invariance)

    assert decision["status"] == "pass"
    assert decision["failed_geometry_count"] == 0
    assert decision["improvement_objective_geometry_count"] == 12
    geometries = cast(
        tuple[dict[str, object], ...], decision["geometry_decisions"]
    )
    assert all(
        geometry["binding_failures"] == []
        and geometry["improvement_objective_failures"]
        == [
            "integrated-flux-median-floor",
            "integrated-flux-p95-floor",
        ]
        for geometry in geometries
    )


def test_phase_five_risk_gate_keeps_paired_regression_binding() -> None:
    """A missed absolute target cannot excuse a new Hebog regression."""
    observations, invariance = _passing_evidence()
    regressed = tuple(
        item.model_copy(
            update={
                "adaptive": item.adaptive.model_copy(
                    update={
                        "integrated_flux_absolute_fractional_error": 0.20,
                    }
                ),
                "coarse": item.coarse.model_copy(
                    update={
                        "integrated_flux_absolute_fractional_error": 0.04,
                    }
                ),
            }
        )
        for item in observations
    )

    decision = evaluate_phase_five_adaptive_risk(regressed, invariance)

    assert decision["status"] == "fail"
    assert decision["failed_geometry_count"] == 12
    geometries = cast(
        tuple[dict[str, object], ...], decision["geometry_decisions"]
    )
    assert all(
        "integrated-flux-paired-margin"
        in cast(list[str], geometry["binding_failures"])
        for geometry in geometries
    )


@pytest.mark.parametrize(
    ("summary_change", "expected_failure"),
    [
        ({"support_recall": 0.70}, "support-recall-image-floor"),
        ({"mask_iou": 0.55}, "mask-iou-image-floor"),
        (
            {"integrated_flux_absolute_fractional_error": 0.60},
            "integrated-flux-p95-floor",
        ),
        ({"completeness": 0.0}, "completeness-floor"),
    ],
)
def test_hard_truth_failures_cannot_be_averaged_away(
    summary_change: dict[str, object], expected_failure: str
) -> None:
    """One unsafe image fails its complete trigger-independent geometry."""
    observations, invariance = _passing_evidence()
    changed = observations[0].model_copy(
        update={"adaptive": _summary(**summary_change)},
    )

    decision = evaluate_adaptive_development(
        (changed, *observations[1:]), invariance
    )

    assert decision["status"] == "fail"
    assert expected_failure in _geometry_failures(decision)


@pytest.mark.parametrize(
    ("summary_change", "expected_failure"),
    [
        ({"product_valid": False}, "product-validity"),
        (
            {"integrated_flux_absolute_fractional_error": 0.11},
            "integrated-flux-median-floor",
        ),
        ({"mask_iou": 0.70}, "mask-iou-cell-median-floor"),
        ({"split": True}, "split-fraction-floor"),
        ({"support_recall": 0.85}, "support-recall-cell-median-floor"),
    ],
)
def test_geometry_level_truth_floors_are_binding(
    summary_change: dict[str, object], expected_failure: str
) -> None:
    """A failing geometry cannot be hidden by the other eleven geometries."""
    observations, invariance = _passing_evidence()
    changed = tuple(
        observation.model_copy(update={"adaptive": _summary(**summary_change)})
        if index < 12
        else observation
        for index, observation in enumerate(observations)
    )

    decision = evaluate_adaptive_development(changed, invariance)

    assert decision["status"] == "fail"
    assert expected_failure in _geometry_failures(decision)


def test_paired_regression_outside_margin_fails_even_with_another_gain() -> (
    None
):
    """A large support loss cannot be traded for better flux recovery."""
    observations, invariance = _passing_evidence()
    changed = observations[0].model_copy(
        update={
            "adaptive": _summary(
                support_recall=0.80,
                integrated_flux_absolute_fractional_error=0.0,
            ),
            "coarse": _summary(support_recall=0.94),
        },
    )

    decision = evaluate_adaptive_development(
        (changed, *observations[1:]), invariance
    )

    assert decision["status"] == "fail"
    assert "support-recall-paired-margin" in _geometry_failures(decision)


def test_trigger_seams_and_dask_invariance_are_binding() -> None:
    """Activation drift or executor drift fails before scientific promotion."""
    observations, invariance = _passing_evidence()
    above = next(
        index
        for index, observation in enumerate(observations)
        if observation.trigger_cohort == "above"
    )
    broken_observations = list(observations)
    broken_observations[above] = broken_observations[above].model_copy(
        update={"adaptive_activation_intersects_truth": False},
    )
    broken_invariance = (
        invariance[0].model_copy(
            update={"existing_dask_science_sha256": "b" * 64},
        ),
        *invariance[1:],
    )

    decision = evaluate_adaptive_development(
        tuple(broken_observations), broken_invariance
    )

    assert decision["status"] == "fail"
    assert decision["executor_invariance_passed"] is False
    assert decision["trigger_seam_passed"] is False


def test_evaluator_rejects_incomplete_or_duplicated_population() -> None:
    """The terminal decision requires exactly the frozen independent units."""
    observations, invariance = _passing_evidence()

    with pytest.raises(ValueError, match="exactly 144"):
        evaluate_adaptive_development(observations[:-1], invariance)
    with pytest.raises(ValueError, match="duplicated"):
        evaluate_adaptive_development(
            (*observations[:-1], observations[0]), invariance
        )


def test_evaluator_rejects_changed_input_metadata_and_dask_population() -> (
    None
):
    """No observation or executor comparison may change identity in flight."""
    observations, invariance = _passing_evidence()
    changed_id = observations[0].model_copy(update={"input_id": "changed"})
    changed_metadata = observations[0].model_copy(update={"seed": 0})

    with pytest.raises(ValueError, match="input identity changed"):
        evaluate_adaptive_development(
            (changed_id, *observations[1:]), invariance
        )
    with pytest.raises(ValueError, match="metadata changed"):
        evaluate_adaptive_development(
            (changed_metadata, *observations[1:]), invariance
        )
    with pytest.raises(ValueError, match="comparison is duplicated"):
        evaluate_adaptive_development(
            observations, (*invariance[:-1], invariance[0])
        )
    with pytest.raises(ValueError, match="requires 12 Dask comparisons"):
        evaluate_adaptive_development(observations, invariance[:-1])


def test_observation_positions_and_input_seeds_are_strict() -> None:
    """Trigger diagnostics must be finite, canonical, and population-bound."""
    observations, _ = _passing_evidence()
    payload = observations[0].model_dump(mode="python")

    with pytest.raises(ValidationError, match="must be finite"):
        AdaptiveDevelopmentObservation.model_validate(
            {
                **payload,
                "adaptive_candidate_positions_yx": ((float("nan"), 1.0),),
            }
        )
    with pytest.raises(ValidationError, match="must be canonical"):
        AdaptiveDevelopmentObservation.model_validate(
            {
                **payload,
                "adaptive_candidate_positions_yx": ((2.0, 2.0), (1.0, 1.0)),
            }
        )
    cell = build_adaptive_development_matrix()[0]
    with pytest.raises(ValueError, match="does not belong"):
        input_identifier(cell, 0)
