"""Candidate-neutral tests for the frozen Phase 5 Step 2B review."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from hebog.algorithms.multiscale import (
    BeamShapePixels,
    ScaleFilterBankResult,
    ScaleFilterResponse,
)
from hebog.validation.contracts import load_phase_five_filter_review
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
    evaluate_generated_image,
    select_filter_family,
    threshold_filter_responses,
)

_ROOT = Path(__file__).parents[3]
_CONTRACT = _ROOT / "config/contracts/phase-5-filter-paired-review.json"
_DEVELOPMENT = _ROOT / "config/datasets/phase-5-development.json"


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
