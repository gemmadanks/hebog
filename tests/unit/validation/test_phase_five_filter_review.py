"""Candidate-neutral tests for the frozen Phase 5 Step 2B review."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from hebog.algorithms.multiscale import (
    BeamShapePixels,
    ScaleFilterBankResult,
    ScaleFilterResponse,
)
from hebog.validation.contracts import (
    load_phase_five_corrective_r_review,
    load_phase_five_corrective_review,
    load_phase_five_filter_review,
)
from hebog.validation.datasets import load_dataset_manifest
from hebog.validation.phase_five_filter_analysis import (
    FilterReviewDatasets,
    FilterReviewObservations,
    compile_filter_review,
)
from hebog.validation.phase_five_filter_review import (
    CandidateScientificDecision,
    build_analytic_review_cases,
    evaluate_analytic_cases,
    evaluate_corrective_analytic_cases,
    evaluate_corrective_generated_image,
    evaluate_generated_image,
    select_filter_family,
    threshold_filter_responses,
)

_ROOT = Path(__file__).parents[3]
_CONTRACT = _ROOT / "config/contracts/phase-5-filter-paired-review.json"
_DEVELOPMENT = _ROOT / "config/datasets/phase-5-development.json"
_CORRECTIVE_CONTRACT = (
    _ROOT / "config/contracts/phase-5-corrective-review.json"
)
_CORRECTIVE_R_CONTRACT = (
    _ROOT / "config/contracts/phase-5-corrective-r-review.json"
)


def _response(values: np.ndarray) -> ScaleFilterResponse:
    """Return one governed scale response for threshold tests."""
    shape = values.shape
    return ScaleFilterResponse(
        scale_order=1,
        nominal_scale_beam_fwhm=1.0,
        response_jy_per_beam=values,
        effective_rms_jy_per_beam=np.ones(shape, dtype=np.float64),
        valid_support_fraction=np.ones(shape, dtype=np.float64),
        scientifically_valid=np.ones(shape, dtype=np.bool_),
    )


def test_analytic_matrix_covers_frozen_dimensions() -> None:
    """Cases cover every predeclared scale, geometry, and SNR level."""
    review = load_phase_five_filter_review(_CONTRACT)
    cases = build_analytic_review_cases(
        BeamShapePixels(5.0, 3.5, 20.0),
        review,
    )

    assert {case.scale_order for case in cases} == set(
        review.matrix.scale_orders
    )
    assert {case.geometry for case in cases} == set(
        review.matrix.mask_geometries
    )
    assert {case.input_peak_snr for case in cases} == set(
        review.matrix.snr_levels
    )
    assert len({case.identifier for case in cases}) == len(cases)
    assert all(not case.image_jy_per_beam.flags.writeable for case in cases)
    assert all(not case.valid_pixels.flags.writeable for case in cases)


def test_both_candidates_use_identical_analytic_cases() -> None:
    """Only the filter family varies within every paired observation."""
    review = load_phase_five_filter_review(_CONTRACT)
    beam = BeamShapePixels(5.0, 3.5, 20.0)
    cases = build_analytic_review_cases(beam, review)

    observations = evaluate_analytic_cases(cases, beam, review)
    by_family = {
        family: tuple(item for item in observations if item.family == family)
        for family in review.candidates
    }

    assert tuple(
        item.case_identifier for item in by_family[review.candidates[0]]
    ) == tuple(
        item.case_identifier for item in by_family[review.candidates[1]]
    )
    assert (
        min(item.support_fraction for item in observations if item.available)
        >= 0.5
    )
    assert max(item.support_fraction for item in observations) == 1.0
    assert (
        sum(item.available for item in observations) / len(observations)
        >= 0.95
    )


def test_threshold_filter_responses_requires_a_five_sigma_seed() -> None:
    """Three-sigma support is retained only around a five-sigma seed."""
    no_seed = np.zeros((7, 7), dtype=np.float64)
    no_seed[3, 2:5] = 3.5
    no_seed_result = ScaleFilterBankResult(
        family="beam-aware-matched-filter",
        responses=(_response(no_seed),),
        convolution_count=3,
        temporary_plane_count=7,
        maximum_workspace_bytes=1,
    )
    with_seed = no_seed.copy()
    with_seed[3, 3] = 5.1
    with_seed_result = ScaleFilterBankResult(
        family="beam-aware-matched-filter",
        responses=(_response(with_seed),),
        convolution_count=3,
        temporary_plane_count=7,
        maximum_workspace_bytes=1,
    )

    rejected = threshold_filter_responses(
        no_seed_result,
        detection_sigma=5.0,
        island_sigma=3.0,
    )
    accepted = threshold_filter_responses(
        with_seed_result,
        detection_sigma=5.0,
        island_sigma=3.0,
    )

    assert not rejected.retained_mask.any()
    assert accepted.retained_mask[3, 2:5].all()
    assert accepted.component_count == 1


def test_generated_image_evaluation_is_candidate_neutral() -> None:
    """Both candidates see the same generated truth, thresholds, and groups."""
    review = load_phase_five_filter_review(_CONTRACT)
    dataset = load_dataset_manifest(_DEVELOPMENT).datasets[0]

    matched = evaluate_generated_image(
        dataset,
        recipe_index=0,
        family="beam-aware-matched-filter",
        review=review,
    )
    wavelet = evaluate_generated_image(
        dataset,
        recipe_index=0,
        family="undecimated-wavelet",
        review=review,
    )

    expected_groups = tuple(
        group.identifier for group in dataset.multiscale_truth_groups
    )
    assert tuple(item.group_identifier for item in matched.groups) == (
        expected_groups
    )
    assert tuple(item.group_identifier for item in wavelet.groups) == (
        expected_groups
    )
    assert matched.seed == wavelet.seed == dataset.recipe.seed
    assert 0.0 <= matched.completeness <= 1.0
    assert 0.0 <= matched.reliability <= 1.0
    assert 0.0 <= matched.mask_intersection_over_union <= 1.0
    assert matched.noise_std_fractional_error >= 0.0
    assert all(item.maximum_snr >= 0.0 for item in matched.groups)
    assert any(
        matched_group.integrated_flux_fractional_error
        != wavelet_group.integrated_flux_fractional_error
        for matched_group, wavelet_group in zip(
            matched.groups, wavelet.groups, strict=True
        )
    )


def test_scientific_decision_precedes_bounded_cost() -> None:
    """Cost breaks a scientific tie but cannot rescue a failed candidate."""
    matched = CandidateScientificDecision(
        family="beam-aware-matched-filter",
        passes_absolute=True,
        noninferior_to_other=True,
        bounded_cost=(9, 7, 34),
    )
    wavelet = CandidateScientificDecision(
        family="undecimated-wavelet",
        passes_absolute=True,
        noninferior_to_other=False,
        bounded_cost=(11, 9, 49),
    )

    assert select_filter_family((matched, wavelet)) == (
        "beam-aware-matched-filter"
    )
    assert (
        select_filter_family(
            (
                matched,
                wavelet.__class__(
                    family=wavelet.family,
                    passes_absolute=True,
                    noninferior_to_other=True,
                    bounded_cost=wavelet.bounded_cost,
                ),
            )
        )
        == "beam-aware-matched-filter"
    )
    assert (
        select_filter_family(
            (
                matched.__class__(
                    family=matched.family,
                    passes_absolute=False,
                    noninferior_to_other=False,
                    bounded_cost=matched.bounded_cost,
                ),
                wavelet,
            )
        )
        is None
    )


def test_compiled_review_fails_closed_across_recorded_strata() -> None:
    """Absolute and paired summaries cannot compensate across strata."""
    review = load_phase_five_filter_review(_CONTRACT)
    dataset = load_dataset_manifest(_DEVELOPMENT).datasets[0]
    beam = BeamShapePixels(5.0, 3.5, 20.0)
    analytic = evaluate_analytic_cases(
        build_analytic_review_cases(beam, review), beam, review
    )
    generated = tuple(
        evaluate_generated_image(
            dataset,
            recipe_index=0,
            family=family,
            review=review,
        )
        for family in review.candidates
    )

    compiled = compile_filter_review(
        FilterReviewObservations(
            analytic=analytic,
            development=generated,
            regression=generated,
        ),
        FilterReviewDatasets(development=dataset, regression=dataset),
        review,
        bounded_costs={
            "beam-aware-matched-filter": (9, 7, 34),
            "undecimated-wavelet": (11, 9, 49),
        },
    )

    assert len(compiled.candidates) == 2
    assert all(not item.passes_absolute for item in compiled.candidates)
    assert any(
        item.population == "analytic"
        and item.stratum.startswith("scale-1/geometry-")
        for item in compiled.endpoints
    )
    assert any(
        item.population == "regression"
        and item.stratum == "morphology-diffuse"
        for item in compiled.paired_endpoints
    )


def test_corrective_analytic_measurement_uses_observable_original_pixels() -> (
    None
):
    """Masked final-output flux and position use observable original truth."""
    review = load_phase_five_corrective_review(_CORRECTIVE_CONTRACT)
    beam = BeamShapePixels(5.0, 3.5, 20.0)
    cases = build_analytic_review_cases(beam, review)

    observations = evaluate_corrective_analytic_cases(cases, beam, review)

    assert len(observations) == 2 * len(cases)
    assert all(item.available for item in observations)
    response_limit = (
        review.absolute_gates.maximum_percentile_95_response_fractional_error
    )
    assert (
        max(item.response_fractional_error or 0.0 for item in observations)
        <= response_limit
    )
    assert max(
        item.integrated_flux_fractional_error or 0.0 for item in observations
    ) <= (
        review.absolute_gates.maximum_percentile_95_integrated_flux_fractional_error
    )
    assert (
        max(item.position_error_beams or 0.0 for item in observations)
        <= review.absolute_gates.maximum_percentile_95_position_beams
    )


def test_corrective_generated_measurement_passes_development_smoke_case() -> (
    None
):
    """Final residual masks and measurements satisfy one untuned image."""
    review = load_phase_five_corrective_review(_CORRECTIVE_CONTRACT)
    dataset = load_dataset_manifest(_DEVELOPMENT).datasets[0]

    observation = evaluate_corrective_generated_image(
        dataset,
        recipe_index=0,
        family="residual-b3-atrous",
        review=review,
    )

    assert (
        observation.completeness >= review.absolute_gates.minimum_completeness
    )
    assert observation.reliability >= review.absolute_gates.minimum_reliability
    assert observation.mask_intersection_over_union >= (
        review.absolute_gates.minimum_mask_intersection_over_union
    )
    assert observation.fragmentation_fraction <= (
        review.absolute_gates.maximum_fragmentation_fraction
    )
    gates = review.absolute_gates
    flux_limit = gates.maximum_percentile_95_integrated_flux_fractional_error
    assert all(
        group.integrated_flux_fractional_error is not None
        and group.integrated_flux_fractional_error <= flux_limit
        for group in observation.groups
    )
    assert all(
        group.position_error_beams is not None
        and np.isfinite(group.position_error_beams)
        for group in observation.groups
    )


def test_corrective_r_applies_association_and_false_positive_controls() -> (
    None
):
    """The frozen area and linkage rules remove development false islands."""
    review = load_phase_five_corrective_r_review(_CORRECTIVE_R_CONTRACT)
    dataset = load_dataset_manifest(_DEVELOPMENT).datasets[0]

    observation = evaluate_corrective_generated_image(
        dataset,
        recipe_index=0,
        family="residual-b3-atrous",
        review=review,
    )

    assert observation.completeness == 1.0
    assert observation.reliability == 1.0
    assert observation.fragmentation_fraction == 0.0
    assert observation.mask_intersection_over_union >= (
        review.absolute_gates.minimum_mask_intersection_over_union
    )


def test_corrective_r_preserves_all_exact_analytic_endpoints() -> None:
    """The false-positive floor retains low-SNR and truncated exact truth."""
    review = load_phase_five_corrective_r_review(_CORRECTIVE_R_CONTRACT)
    beam = BeamShapePixels(5.0, 3.5, 20.0)
    cases = build_analytic_review_cases(beam, review)

    observations = evaluate_corrective_analytic_cases(cases, beam, review)

    assert len(observations) == 2 * 84
    assert all(item.available for item in observations)
    assert (
        max(item.position_error_beams or 0.0 for item in observations)
        <= review.absolute_gates.maximum_percentile_95_position_beams
    )


def test_corrective_r_types_artifact_and_truncated_measurements() -> None:
    """Non-photometric controls and truncated sources remain explicit."""
    review = load_phase_five_corrective_r_review(_CORRECTIVE_R_CONTRACT)
    dataset = load_dataset_manifest(_DEVELOPMENT).datasets[0]

    observation = evaluate_corrective_generated_image(
        dataset,
        recipe_index=0,
        family="residual-b3-atrous",
        review=review,
    )
    groups = {item.morphology: item for item in observation.groups}

    artifact = groups["artifact"]
    assert artifact.measurement_disposition == "known-artifact-control"
    assert artifact.integrated_flux_fractional_error is None
    assert artifact.position_error_beams is None
    edge = next(
        item
        for item in observation.groups
        if item.group_identifier == "extended-edge-0001"
    )
    assert edge.measurement_disposition == "truncated-observable-domain"
    assert edge.integrated_flux_fractional_error is not None
    assert edge.position_error_beams is not None


def test_corrective_r_astrometry_reports_bias_separately_from_scatter() -> (
    None
):
    """Development astrometry is observable, finite, and bias-auditable."""
    review = load_phase_five_corrective_r_review(_CORRECTIVE_R_CONTRACT)
    dataset = load_dataset_manifest(_DEVELOPMENT).datasets[0]
    offsets: dict[str, list[tuple[float, float]]] = {}

    for recipe_index in range(10):
        observation = evaluate_corrective_generated_image(
            dataset,
            recipe_index=recipe_index,
            family="residual-b3-atrous",
            review=review,
        )
        for group in observation.groups:
            if group.measurement_disposition == "known-artifact-control":
                continue
            assert group.position_offset_xy_beams is not None
            offsets.setdefault(group.morphology, []).append(
                group.position_offset_xy_beams
            )

    for morphology_offsets in offsets.values():
        values = np.asarray(morphology_offsets, dtype=np.float64)
        bias = np.linalg.norm(np.mean(values, axis=0))
        centred = values - np.mean(values, axis=0)
        scatter_95 = np.percentile(np.linalg.norm(centred, axis=1), 95)
        assert bias <= 0.15
        assert scatter_95 <= 0.3
