"""Analytic tests for the independent scientific comparison oracle."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal, cast

import numpy as np
import pytest

from hebog.validation.comparison import (
    CatalogueEllipse,
    CatalogueOutlierThresholds,
    CatalogueSource,
    aggregate_island_comparisons,
    compare_catalogues,
    compare_island_labels,
    compare_masks,
    compare_rms_maps,
    evaluate_uncertainty_calibration,
    uncertainty_calibration_report,
    wilson_score_interval,
)


def _source(
    identifier: str,
    *,
    right_ascension_degrees: float,
    declination_degrees: float = 0.0,
    integrated_flux_jy: float = 1.0,
    peak_flux_jy_per_beam: float | None = None,
) -> CatalogueSource:
    """Construct a source with concise defaults for matching tests."""
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=right_ascension_degrees,
        declination_degrees=declination_degrees,
        peak_flux_jy_per_beam=(
            integrated_flux_jy
            if peak_flux_jy_per_beam is None
            else peak_flux_jy_per_beam
        ),
        integrated_flux_jy=integrated_flux_jy,
    )


def _ellipse(
    major: float,
    minor: float,
    position_angle: float,
    *,
    error: float | None = None,
) -> CatalogueEllipse:
    """Construct one comparison ellipse with concise error defaults."""
    return CatalogueEllipse(
        major_fwhm_degrees=major,
        minor_fwhm_degrees=minor,
        position_angle_degrees=position_angle,
        major_fwhm_error_degrees=error,
        minor_fwhm_error_degrees=error,
        position_angle_error_degrees=error,
    )


def test_catalogue_source_converts_values_to_canonical_units() -> None:
    """The ingestion helper accepts compatible angular and flux units."""
    source = CatalogueSource.from_units(
        identifier="converted",
        right_ascension=1_296_000,
        declination=-108_000,
        angle_unit="arcsec",
        peak_flux_density=2_000,
        peak_flux_unit="mJy/beam",
        integrated_flux_density=3_000,
        integrated_flux_unit="mJy",
    )

    assert source.right_ascension_degrees == pytest.approx(0.0)
    assert source.declination_degrees == pytest.approx(-30.0)
    assert source.peak_flux_jy_per_beam == pytest.approx(2.0)
    assert source.integrated_flux_jy == pytest.approx(3.0)


def test_catalogue_source_rejects_an_unsupported_runtime_unit() -> None:
    """Untyped adapters cannot silently trigger an implicit conversion."""
    unsupported = cast(Literal["deg", "arcsec"], "rad")

    with pytest.raises(ValueError, match="angle_unit"):
        CatalogueSource.from_units(
            identifier="invalid-unit",
            right_ascension=0.0,
            declination=0.0,
            angle_unit=unsupported,
            peak_flux_density=1.0,
            peak_flux_unit="Jy/beam",
            integrated_flux_density=1.0,
            integrated_flux_unit="Jy",
        )


def test_catalogue_matching_wraps_right_ascension() -> None:
    """Sources on opposite sides of zero right ascension can match."""
    reference = (_source("reference", right_ascension_degrees=359.99),)
    candidate = (_source("candidate", right_ascension_degrees=0.01),)

    report = compare_catalogues(
        reference,
        candidate,
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
    )

    assert len(report.matches) == 1
    assert report.matches[0].separation_beam_fwhm == pytest.approx(0.2)
    assert report.unmatched_reference_identifiers == ()
    assert report.unmatched_candidate_identifiers == ()


def test_catalogue_matching_uses_great_circle_declination() -> None:
    """Beam-normalized distance is spherical rather than a flat-sky delta."""
    reference = (
        _source(
            "reference",
            right_ascension_degrees=10.0,
            declination_degrees=-10.0,
        ),
    )
    candidate = (
        _source(
            "candidate",
            right_ascension_degrees=10.0,
            declination_degrees=10.0,
        ),
    )

    report = compare_catalogues(
        reference,
        candidate,
        beam_fwhm_degrees=100.0,
        maximum_separation_beams=0.5,
    )

    assert report.matches[0].separation_beam_fwhm == pytest.approx(0.2)


def test_ambiguous_matching_maximizes_total_matched_flux() -> None:
    """Flux resolves a blend ambiguity before angular distance does."""
    reference = (
        _source(
            "reference-bright",
            right_ascension_degrees=0.0,
            integrated_flux_jy=10.0,
        ),
        _source(
            "reference-faint",
            right_ascension_degrees=0.1,
            integrated_flux_jy=1.0,
        ),
    )
    candidate = (
        _source(
            "candidate-bright",
            right_ascension_degrees=0.1,
            integrated_flux_jy=10.0,
        ),
        _source(
            "candidate-faint",
            right_ascension_degrees=0.0,
            integrated_flux_jy=1.0,
        ),
    )

    report = compare_catalogues(
        reference,
        candidate,
        beam_fwhm_degrees=1.0,
        maximum_separation_beams=0.5,
    )

    assert {
        (match.reference_identifier, match.candidate_identifier)
        for match in report.matches
    } == {
        ("reference-bright", "candidate-bright"),
        ("reference-faint", "candidate-faint"),
    }


def test_catalogue_report_records_unmatched_rows_and_flux_metrics() -> None:
    """Report fractions and flux errors use observable matched rows."""
    reference = (
        _source(
            "matched-reference",
            right_ascension_degrees=10.0,
            integrated_flux_jy=2.0,
            peak_flux_jy_per_beam=1.0,
        ),
        _source("missed-reference", right_ascension_degrees=20.0),
    )
    candidate = (
        _source(
            "matched-candidate",
            right_ascension_degrees=10.01,
            integrated_flux_jy=2.2,
            peak_flux_jy_per_beam=0.9,
        ),
        _source("extra-candidate", right_ascension_degrees=30.0),
    )

    report = compare_catalogues(
        reference,
        candidate,
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
    )

    assert report.reference_count == 2
    assert report.candidate_count == 2
    assert report.completeness == pytest.approx(0.5)
    assert report.reliability == pytest.approx(0.5)
    assert report.unmatched_reference_identifiers == ("missed-reference",)
    assert report.unmatched_candidate_identifiers == ("extra-candidate",)
    assert report.median_absolute_peak_flux_fractional_difference == (
        pytest.approx(0.1)
    )
    assert (
        report.percentile_95_absolute_integrated_flux_fractional_difference
        == (pytest.approx(0.1))
    )


def test_catalogue_report_compares_shapes_modulo_half_a_circle() -> None:
    """Fitted/deconvolved axes and orientation retain physical semantics."""
    reference = CatalogueSource(
        identifier="reference",
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=1.5,
        fitted_shape=_ellipse(0.01, 0.005, 179.0),
        deconvolved_shape=_ellipse(0.008, 0.004, 179.0),
        deconvolution_status="resolved",
    )
    candidate = CatalogueSource(
        identifier="candidate",
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=1.5,
        fitted_shape=_ellipse(0.011, 0.0045, 1.0),
        deconvolved_shape=_ellipse(0.0088, 0.0036, 1.0, error=1.0),
        deconvolution_status="resolved",
    )

    report = compare_catalogues(
        (reference,),
        (candidate,),
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
        position_angle_minimum_axis_ratio=1.1,
    )

    match = report.matches[0]
    assert match.fitted_major_axis_fractional_difference == pytest.approx(0.1)
    assert match.fitted_minor_axis_fractional_difference == pytest.approx(-0.1)
    assert match.fitted_position_angle_difference_degrees == pytest.approx(2.0)
    assert match.deconvolved_major_axis_fractional_difference == pytest.approx(
        0.1
    )
    assert report.median_absolute_fitted_axis_fractional_difference == (
        pytest.approx(0.1)
    )
    assert report.median_absolute_fitted_position_angle_difference_degrees == (
        pytest.approx(2.0)
    )
    assert (
        report.median_absolute_deconvolved_position_angle_difference_degrees
        == pytest.approx(2.0)
    )
    assert report.unresolved_classification_accuracy == 1.0


def test_catalogue_report_distinguishes_unresolved_from_unavailable() -> None:
    """Only explicit resolved/unresolved states enter classification gates."""
    reference = replace(
        _source("reference", right_ascension_degrees=10.0),
        deconvolution_status="unresolved",
        quality_flags=("unresolved",),
    )
    candidate = replace(
        _source("candidate", right_ascension_degrees=10.0),
        deconvolved_shape=_ellipse(0.01, 0.005, 20.0),
        deconvolution_status="resolved",
    )

    report = compare_catalogues(
        (reference,),
        (candidate,),
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
        position_angle_minimum_axis_ratio=1.1,
    )

    assert report.unresolved_classification_count == 1
    assert report.unresolved_classification_accuracy == 0.0

    unavailable = compare_catalogues(
        (_source("r", right_ascension_degrees=10.0),),
        (_source("c", right_ascension_degrees=10.0),),
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
    )
    assert unavailable.unresolved_classification_count == 0
    assert unavailable.unresolved_classification_accuracy is None


def test_catalogue_report_calibrates_candidate_reported_uncertainties() -> (
    None
):
    """Normalized residuals expose bias, dispersion, and one-sigma coverage."""
    reference = CatalogueSource(
        identifier="truth",
        right_ascension_degrees=359.99,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=2.0,
        fitted_shape=_ellipse(0.01, 0.005, 179.0),
    )
    candidate = CatalogueSource(
        identifier="measured",
        right_ascension_degrees=0.0,
        declination_degrees=-29.99,
        peak_flux_jy_per_beam=1.1,
        integrated_flux_jy=1.8,
        right_ascension_error_degrees=0.01,
        declination_error_degrees=0.02,
        peak_flux_error_jy_per_beam=0.2,
        integrated_flux_error_jy=0.1,
        fitted_shape=_ellipse(0.011, 0.0045, 1.0, error=1.0),
    )

    report = compare_catalogues(
        (reference,),
        (candidate,),
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
        position_angle_minimum_axis_ratio=1.1,
    )
    calibration = {
        item.metric: item for item in report.uncertainty_calibration
    }

    assert calibration["right-ascension"].mean_normalized_residual == (
        pytest.approx(1.0)
    )
    assert calibration["declination"].coverage_fraction == 1.0
    assert calibration["peak-flux"].mean_normalized_residual == pytest.approx(
        0.5
    )
    assert calibration["integrated-flux"].coverage_fraction == 0.0
    assert calibration["fitted-position-angle"].mean_normalized_residual == (
        pytest.approx(2.0)
    )


def test_uncertainty_report_calculates_sample_dispersion() -> None:
    """More than one normalized residual reports sample standard deviation."""
    references = (
        _source("r1", right_ascension_degrees=10.0),
        _source("r2", right_ascension_degrees=20.0),
    )
    candidates = (
        replace(
            _source("c1", right_ascension_degrees=10.01),
            right_ascension_error_degrees=0.01,
        ),
        replace(
            _source("c2", right_ascension_degrees=19.99),
            right_ascension_error_degrees=0.01,
        ),
    )

    report = compare_catalogues(
        references,
        candidates,
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
    )
    calibration = report.uncertainty_calibration[0]

    assert calibration.metric == "right-ascension"
    assert calibration.mean_normalized_residual == pytest.approx(0.0)
    assert calibration.sample_standard_deviation == pytest.approx(np.sqrt(2))


def test_uncertainty_calibration_uses_predeclared_confidence_methods() -> None:
    """Calibration records deterministic intervals for all three metrics."""
    samples = np.random.default_rng(7).normal(size=240)

    report = uncertainty_calibration_report(
        "peak-flux",
        samples,
        eligible_count=240,
        confidence_level=0.95,
        bootstrap_resamples=10_000,
        bootstrap_seed=20260802,
    )
    repeated = uncertainty_calibration_report(
        "peak-flux",
        samples,
        eligible_count=240,
        confidence_level=0.95,
        bootstrap_resamples=10_000,
        bootstrap_seed=20260802,
    )

    assert report == repeated
    assert report.coverage_confidence_interval is not None
    assert report.mean_confidence_interval is not None
    assert report.dispersion_confidence_interval is not None
    assert report.mean_normalized_residual is not None
    assert report.sample_standard_deviation is not None
    assert (
        report.mean_confidence_interval.lower < report.mean_normalized_residual
    )
    assert (
        report.mean_confidence_interval.upper > report.mean_normalized_residual
    )
    assert (
        report.dispersion_confidence_interval.lower
        < report.sample_standard_deviation
    )
    assert (
        report.dispersion_confidence_interval.upper
        > report.sample_standard_deviation
    )


def test_uncertainty_calibration_gates_entire_intervals() -> None:
    """A point estimate inside a margin cannot hide an uncertain interval."""
    samples = np.tile(np.asarray([-1.0, 1.0]), 100)
    report = uncertainty_calibration_report(
        "declination",
        samples,
        eligible_count=200,
        confidence_level=0.95,
        bootstrap_resamples=10_000,
        bootstrap_seed=20260802,
    )

    decision = evaluate_uncertainty_calibration(
        report,
        minimum_samples=200,
        nominal_coverage=0.6826894921370859,
        maximum_absolute_coverage_difference=0.1,
        maximum_absolute_mean=0.15,
        minimum_standard_deviation=0.8,
        maximum_standard_deviation=1.2,
    )

    assert decision.status == "fail"
    assert decision.failed_metrics == ("coverage",)


def test_uncertainty_calibration_is_report_only_below_sample_floor() -> None:
    """Small strata remain visible without being mislabelled as passing."""
    report = uncertainty_calibration_report(
        "integrated-flux",
        np.asarray([-0.5, 0.5]),
        eligible_count=3,
        confidence_level=0.95,
        bootstrap_resamples=10_000,
        bootstrap_seed=20260802,
    )

    decision = evaluate_uncertainty_calibration(
        report,
        minimum_samples=200,
        nominal_coverage=0.6826894921370859,
        maximum_absolute_coverage_difference=0.1,
        maximum_absolute_mean=0.15,
        minimum_standard_deviation=0.8,
        maximum_standard_deviation=1.2,
    )

    assert report.availability_fraction == pytest.approx(2 / 3)
    assert decision.status == "report-only"
    assert decision.failed_metrics == ("insufficient-samples",)


def test_catalogue_report_compares_association_components_and_flags() -> None:
    """Matched flux cannot conceal a split parent or metadata divergence."""
    reference = (
        replace(
            _source("r1", right_ascension_degrees=1.0),
            island_identifier="island-a",
            component_count=1,
            quality_flags=("unresolved",),
        ),
        replace(
            _source("r2", right_ascension_degrees=2.0),
            island_identifier="island-a",
            component_count=2,
            quality_flags=("edge", "unresolved"),
        ),
        replace(
            _source("r3", right_ascension_degrees=3.0),
            island_identifier="island-b",
            component_count=1,
        ),
    )
    candidate = (
        replace(
            _source("c1", right_ascension_degrees=1.0),
            island_identifier="candidate-a",
            component_count=1,
            quality_flags=("unresolved",),
        ),
        replace(
            _source("c2", right_ascension_degrees=2.0),
            island_identifier="candidate-b",
            component_count=1,
            quality_flags=("edge",),
        ),
        replace(
            _source("c3", right_ascension_degrees=3.0),
            island_identifier="candidate-b",
            component_count=1,
        ),
    )

    report = compare_catalogues(
        reference,
        candidate,
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
    )

    assert report.association.compared_pair_count == 3
    assert report.association.true_positive_pair_count == 0
    assert report.association.false_positive_pair_count == 1
    assert report.association.false_negative_pair_count == 1
    assert report.association.disagreement_pair_count == 2
    assert report.association.agreement_fraction == pytest.approx(1 / 3)
    assert report.association.precision == 0.0
    assert report.association.recall == 0.0
    assert report.association.intersection_over_union == 0.0
    assert report.component_count_agreement_fraction == pytest.approx(2 / 3)
    assert report.quality_flag_exact_agreement_fraction == pytest.approx(2 / 3)
    assert report.median_quality_flag_jaccard == pytest.approx(1.0)


def test_catalogue_report_recognizes_matching_parent_associations() -> None:
    """A shared parent pair in both catalogues is a true positive."""
    reference = tuple(
        replace(
            _source(f"r{index}", right_ascension_degrees=float(index)),
            island_identifier="reference-parent",
        )
        for index in (1, 2)
    )
    candidate = tuple(
        replace(
            _source(f"c{index}", right_ascension_degrees=float(index)),
            island_identifier="candidate-parent",
        )
        for index in (1, 2)
    )

    report = compare_catalogues(
        reference,
        candidate,
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
    )

    assert report.association.true_positive_pair_count == 1
    assert report.association.precision == 1.0
    assert report.association.recall == 1.0
    assert report.association.intersection_over_union == 1.0


def test_catalogue_report_identifies_explicit_catastrophic_outliers() -> None:
    """Outliers use caller-frozen thresholds rather than hidden constants."""
    reference = (
        replace(
            _source(
                "reference",
                right_ascension_degrees=0.0,
                integrated_flux_jy=1.0,
            ),
            fitted_shape=_ellipse(0.01, 0.005, 0.0),
        ),
    )
    candidate = (
        replace(
            _source(
                "candidate",
                right_ascension_degrees=0.01,
                integrated_flux_jy=2.0,
            ),
            fitted_shape=_ellipse(0.02, 0.005, 0.0),
        ),
    )

    thresholds = CatalogueOutlierThresholds(
        position_beams=0.5,
        peak_flux_fractional_difference=0.5,
        integrated_flux_fractional_difference=0.5,
        fitted_axis_fractional_difference=0.5,
        deconvolved_axis_fractional_difference=1.0,
    )
    report = compare_catalogues(
        reference,
        candidate,
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
        outlier_thresholds=thresholds,
        position_angle_minimum_axis_ratio=1.1,
    )

    assert report.catastrophic_outlier_thresholds == thresholds
    assert report.catastrophic_outlier_reference_identifiers == ("reference",)
    assert report.catastrophic_outlier_fraction == 1.0


def test_catalogue_report_uses_reference_selected_shape_eligibility() -> None:
    """Near-circular truth keeps axis evidence but excludes meaningless PA."""
    reference = replace(
        _source("reference", right_ascension_degrees=10.0),
        fitted_shape=_ellipse(0.01, 0.0095, 0.0),
    )
    candidate = replace(
        _source("candidate", right_ascension_degrees=10.0),
        fitted_shape=_ellipse(0.01, 0.0095, 90.0),
    )

    report = compare_catalogues(
        (reference,),
        (candidate,),
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
        position_angle_minimum_axis_ratio=1.1,
    )

    assert report.median_absolute_fitted_axis_fractional_difference == 0.0
    assert (
        report.median_absolute_fitted_position_angle_difference_degrees is None
    )


def test_catalogue_report_counts_missing_candidate_fields_as_unavailable() -> (
    None
):
    """A candidate cannot pass a gate by omitting difficult measurements."""
    reference = replace(
        _source("reference", right_ascension_degrees=10.0),
        fitted_shape=_ellipse(0.01, 0.005, 20.0),
        deconvolved_shape=_ellipse(0.008, 0.004, 20.0),
        deconvolution_status="resolved",
        island_identifier="parent",
    )
    candidate = _source("candidate", right_ascension_degrees=10.0)

    report = compare_catalogues(
        (reference,),
        (candidate,),
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
        position_angle_minimum_axis_ratio=1.1,
    )
    availability = {item.metric: item for item in report.field_availability}
    uncertainty = {
        item.metric: item for item in report.uncertainty_calibration
    }

    assert availability["fitted-shape"].eligible_count == 1
    assert availability["fitted-shape"].availability_fraction == 0.0
    assert (
        availability["deconvolution-classification"].availability_fraction
        == 0.0
    )
    assert (
        availability["resolved-deconvolved-shape"].availability_fraction == 0.0
    )
    assert availability["parent-island-identity"].availability_fraction == 0.0
    assert report.unresolved_classification_count == 1
    assert report.unresolved_classification_accuracy == 0.0
    assert report.association.identity_eligible_count == 1
    assert report.association.identity_available_count == 0
    assert uncertainty["right-ascension"].eligible_count == 1
    assert uncertainty["right-ascension"].sample_count == 0
    assert uncertainty["right-ascension"].availability_fraction == 0.0
    assert uncertainty["right-ascension"].coverage_fraction is None
    assert uncertainty["right-ascension"].mean_normalized_residual is None


def test_missing_parent_identity_counts_as_false_negative() -> None:
    """Missing candidate identities do not disappear from association gates."""
    reference = tuple(
        replace(
            _source(f"r{index}", right_ascension_degrees=float(index)),
            island_identifier="reference-parent",
        )
        for index in (1, 2)
    )
    candidate = tuple(
        _source(f"c{index}", right_ascension_degrees=float(index))
        for index in (1, 2)
    )

    report = compare_catalogues(
        reference,
        candidate,
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
    )

    assert report.association.identity_availability_fraction == 0.0
    assert report.association.false_negative_pair_count == 1
    assert report.association.recall == 0.0


def test_rich_catalogue_source_rejects_ambiguous_absence_or_flags() -> None:
    """Unavailable and unresolved shapes are explicit and flags canonical."""
    with pytest.raises(ValueError, match="resolved deconvolution"):
        replace(
            _source("source", right_ascension_degrees=1.0),
            deconvolution_status="resolved",
        )

    with pytest.raises(ValueError, match="quality flags"):
        replace(
            _source("source", right_ascension_degrees=1.0),
            quality_flags=("unresolved", "edge"),
        )

    with pytest.raises(ValueError, match="source errors"):
        replace(
            _source("source", right_ascension_degrees=1.0),
            right_ascension_error_degrees=0.0,
        )

    with pytest.raises(ValueError, match="island identifier"):
        replace(
            _source("source", right_ascension_degrees=1.0),
            island_identifier="",
        )

    with pytest.raises(ValueError, match="component count"):
        replace(
            _source("source", right_ascension_degrees=1.0),
            component_count=0,
        )

    with pytest.raises(ValueError, match="only identifiable"):
        replace(
            _source("source", right_ascension_degrees=1.0),
            deconvolved_shape=_ellipse(0.01, 0.005, 0.0),
        )

    with pytest.raises(ValueError, match="requires its quality flag"):
        replace(
            _source("source", right_ascension_degrees=1.0),
            deconvolution_status="unresolved",
        )


def test_major_only_deconvolution_compares_only_identifiable_axis() -> None:
    """A censored minor axis cannot create a catastrophic minor residual."""
    reference = replace(
        _source("reference", right_ascension_degrees=10.0),
        deconvolved_shape=_ellipse(0.008, 0.002, 20.0),
        deconvolution_status="resolved",
    )
    candidate = replace(
        _source("candidate", right_ascension_degrees=10.0),
        deconvolved_major_fwhm_degrees=0.0088,
        deconvolution_status="major-axis-only",
        quality_flags=("major-axis-only",),
    )

    report = compare_catalogues(
        (reference,),
        (candidate,),
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
        position_angle_minimum_axis_ratio=1.1,
    )

    match = report.matches[0]
    assert match.deconvolved_major_axis_fractional_difference == (
        pytest.approx(0.1)
    )
    assert match.deconvolved_minor_axis_fractional_difference is None
    assert match.deconvolved_position_angle_difference_degrees is None
    assert match.unresolved_classification_agrees is True


@pytest.mark.parametrize(
    "ellipse",
    [
        (0.0, 0.0, 0.0),
        (0.01, 0.02, 0.0),
        (0.01, 0.005, np.inf),
    ],
)
def test_catalogue_ellipse_rejects_invalid_geometry(
    ellipse: tuple[float, float, float],
) -> None:
    """Shape reports cannot normalize physically invalid ellipses."""
    with pytest.raises(ValueError, match="catalogue"):
        _ellipse(*ellipse)


def test_catalogue_outlier_thresholds_must_be_explicitly_positive() -> None:
    """A disabled or nonsensical outlier definition fails at construction."""
    with pytest.raises(ValueError, match="outlier thresholds"):
        CatalogueOutlierThresholds(
            position_beams=0.0,
            peak_flux_fractional_difference=0.5,
            integrated_flux_fractional_difference=0.5,
            fitted_axis_fractional_difference=0.5,
            deconvolved_axis_fractional_difference=1.0,
        )


@pytest.mark.parametrize(
    "field", ["beam_fwhm_degrees", "maximum_separation_beams"]
)
def test_catalogue_comparison_rejects_nonpositive_match_geometry(
    field: str,
) -> None:
    """Matching never accepts a zero beam or search radius."""
    beam_fwhm_degrees = 0.0 if field == "beam_fwhm_degrees" else 0.1
    maximum_separation_beams = (
        0.0 if field == "maximum_separation_beams" else 0.5
    )

    with pytest.raises(ValueError, match="positive and finite"):
        compare_catalogues(
            (),
            (),
            beam_fwhm_degrees=beam_fwhm_degrees,
            maximum_separation_beams=maximum_separation_beams,
        )


def test_shape_comparison_requires_an_explicit_position_angle_population() -> (
    None
):
    """Shape evidence cannot inherit a hidden circularity threshold."""
    shaped = replace(
        _source("source", right_ascension_degrees=1.0),
        fitted_shape=_ellipse(0.01, 0.005, 0.0),
    )

    with pytest.raises(ValueError, match="required when comparing shapes"):
        compare_catalogues(
            (shaped,),
            (),
            beam_fwhm_degrees=1.0,
            maximum_separation_beams=0.5,
        )


@pytest.mark.parametrize("minimum_axis_ratio", [1.0, np.inf])
def test_position_angle_axis_ratio_must_define_ellipticity(
    minimum_axis_ratio: float,
) -> None:
    """The position-angle population needs a finite ratio above unity."""
    with pytest.raises(ValueError, match="finite and greater than one"):
        compare_catalogues(
            (),
            (),
            beam_fwhm_degrees=1.0,
            maximum_separation_beams=0.5,
            position_angle_minimum_axis_ratio=minimum_axis_ratio,
        )


def test_empty_catalogues_have_explicit_success_semantics() -> None:
    """Two empty catalogues agree without inventing numerical match metrics."""
    report = compare_catalogues(
        (),
        (),
        beam_fwhm_degrees=1.0,
        maximum_separation_beams=0.5,
    )

    assert report.matches == ()
    assert report.completeness == 1.0
    assert report.reliability == 1.0
    assert report.median_separation_beam_fwhm is None
    assert report.median_absolute_peak_flux_fractional_difference is None
    assert report.association.precision == 1.0
    assert report.association.recall == 1.0
    assert report.association.intersection_over_union == 1.0

    candidate_only = compare_catalogues(
        (),
        (_source("candidate", right_ascension_degrees=0.0),),
        beam_fwhm_degrees=1.0,
        maximum_separation_beams=0.5,
    )
    assert candidate_only.completeness == 1.0
    assert candidate_only.reliability == 0.0


def test_catalogue_comparison_rejects_duplicate_identifiers() -> None:
    """Ambiguous row identities cannot enter a scientific report."""
    duplicate = _source("duplicate", right_ascension_degrees=1.0)

    with pytest.raises(ValueError, match="reference identifiers"):
        compare_catalogues(
            (duplicate, duplicate),
            (),
            beam_fwhm_degrees=1.0,
            maximum_separation_beams=0.5,
        )


def test_mask_report_has_confusion_counts_and_valid_region() -> None:
    """Mask agreement distinguishes false inclusions from exclusions."""
    reference = np.array([[True, True, False], [False, True, False]])
    candidate = np.array([[True, False, True], [False, True, True]])
    valid = np.array([[True, True, True], [True, True, False]])

    report = compare_masks(reference, candidate, valid_mask=valid)

    assert report.compared_pixel_count == 5
    assert report.excluded_pixel_count == 1
    assert report.true_positive_count == 2
    assert report.true_negative_count == 1
    assert report.false_positive_count == 1
    assert report.false_negative_count == 1
    assert report.agreement_fraction == pytest.approx(0.6)
    assert report.precision == pytest.approx(2 / 3)
    assert report.recall == pytest.approx(2 / 3)
    assert report.intersection_over_union == pytest.approx(0.5)


def test_empty_masks_agree_without_division_by_zero() -> None:
    """All-false masks have perfect agreement, precision, and recall."""
    empty = np.zeros((2, 3), dtype=np.bool_)

    report = compare_masks(empty, empty)

    assert report.agreement_fraction == 1.0
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.intersection_over_union == 1.0


def test_island_matching_uses_overlap_not_numeric_label_identity() -> None:
    """Canonical regions match even when local label numbers differ."""
    reference = np.array(
        [
            [1, 1, 0, 2],
            [1, 1, 0, 2],
        ],
        dtype=np.int32,
    )
    candidate = np.array(
        [
            [20, 20, 0, 10],
            [20, 20, 0, 10],
        ],
        dtype=np.int64,
    )

    report = compare_island_labels(reference, candidate)

    assert report.reference_count == 2
    assert report.candidate_count == 2
    assert report.completeness == 1.0
    assert report.reliability == 1.0
    assert report.unmatched_reference_labels == ()
    assert report.unmatched_candidate_labels == ()
    assert report.split_reference_labels == ()
    assert report.merged_candidate_labels == ()
    assert {
        (
            match.reference_label,
            match.candidate_label,
            match.intersection_pixel_count,
            match.intersection_over_union,
        )
        for match in report.matches
    } == {(1, 20, 4, 1.0), (2, 10, 2, 1.0)}
    assert report.median_matched_intersection_over_union == 1.0
    assert report.minimum_matched_intersection_over_union == 1.0


def test_island_matching_reports_splits_and_unmatched_fragments() -> None:
    """One reference region split into two candidates stays observable."""
    reference = np.array([[1, 1, 1, 1]], dtype=np.int16)
    candidate = np.array([[10, 10, 11, 11]], dtype=np.int16)

    report = compare_island_labels(reference, candidate)

    assert report.split_reference_labels == (1,)
    assert report.merged_candidate_labels == ()
    assert len(report.matches) == 1
    assert report.matches[0].intersection_over_union == pytest.approx(0.5)
    assert report.unmatched_reference_labels == ()
    assert len(report.unmatched_candidate_labels) == 1
    assert report.completeness == 1.0
    assert report.reliability == pytest.approx(0.5)


def test_island_matching_reports_merges_and_valid_region() -> None:
    """A candidate joining reference regions reports a merge after masking."""
    reference = np.array([[1, 1, 0, 2, 2, 3]], dtype=np.int16)
    candidate = np.array([[8, 8, 0, 8, 8, 9]], dtype=np.int16)
    valid = np.array([[True, True, True, True, True, False]])

    report = compare_island_labels(reference, candidate, valid_mask=valid)

    assert report.compared_pixel_count == 5
    assert report.excluded_pixel_count == 1
    assert report.reference_count == 2
    assert report.candidate_count == 1
    assert report.split_reference_labels == ()
    assert report.merged_candidate_labels == (8,)
    assert len(report.matches) == 1
    assert len(report.unmatched_reference_labels) == 1
    assert report.unmatched_candidate_labels == ()


def test_empty_island_labels_have_explicit_success_semantics() -> None:
    """Two empty segmentations agree without invented overlap metrics."""
    empty = np.zeros((2, 3), dtype=np.int32)

    report = compare_island_labels(empty, empty)

    assert report.matches == ()
    assert report.completeness == 1.0
    assert report.reliability == 1.0
    assert report.median_matched_intersection_over_union is None
    assert report.minimum_matched_intersection_over_union is None


@pytest.mark.parametrize(
    "labels",
    [
        np.ones((2, 2), dtype=np.float64),
        np.ones((2, 2), dtype=np.bool_),
        np.array([[0, -1]], dtype=np.int64),
    ],
)
def test_island_matching_rejects_invalid_labels(labels: np.ndarray) -> None:
    """Island labels must be non-negative integer identifiers."""
    with pytest.raises((TypeError, ValueError), match="island labels"):
        compare_island_labels(labels, np.zeros(labels.shape, dtype=np.int64))


def test_rms_report_has_explicit_exclusions() -> None:
    """RMS metrics state which pixels support each kind of error."""
    reference = np.array([[1.0, 2.0, 0.0], [4.0, np.nan, 8.0]])
    candidate = np.array([[1.1, 1.8, 0.5], [4.0, 6.0, np.inf]])
    valid = np.array([[True, True, True], [False, True, True]])

    report = compare_rms_maps(reference, candidate, valid_mask=valid)

    assert report.compared_pixel_count == 3
    assert report.relative_pixel_count == 2
    assert report.excluded_pixel_count == 3
    assert report.zero_reference_pixel_count == 1
    assert report.median_absolute_difference_jy_per_beam == pytest.approx(0.2)
    assert report.percentile_95_absolute_difference_jy_per_beam == (
        pytest.approx(0.47)
    )
    assert report.median_absolute_fractional_difference == pytest.approx(0.1)
    assert report.percentile_95_absolute_fractional_difference == (
        pytest.approx(0.1)
    )


def test_rms_report_handles_an_empty_valid_region() -> None:
    """An empty comparison reports counts and no invented numerical values."""
    rms = np.ones((2, 2), dtype=np.float64)
    valid = np.zeros((2, 2), dtype=np.bool_)

    report = compare_rms_maps(rms, rms, valid_mask=valid)

    assert report.compared_pixel_count == 0
    assert report.relative_pixel_count == 0
    assert report.excluded_pixel_count == 4
    assert report.median_absolute_difference_jy_per_beam is None
    assert report.median_absolute_fractional_difference is None


@pytest.mark.parametrize("comparison", [compare_masks, compare_rms_maps])
def test_array_comparison_rejects_shape_mismatches(
    comparison: object,
) -> None:
    """Pixel reports never broadcast scientifically unrelated planes."""
    assert callable(comparison)
    with pytest.raises(ValueError, match="same shape"):
        comparison(np.ones((2, 2)), np.ones((2, 3)))


def test_mask_comparison_requires_boolean_arrays() -> None:
    """Numeric masks are not silently coerced to truth values."""
    with pytest.raises(TypeError, match="boolean"):
        compare_masks(np.ones((2, 2)), np.ones((2, 2)))


def test_rms_comparison_rejects_negative_finite_values() -> None:
    """A negative RMS is invalid scientific input rather than a difference."""
    with pytest.raises(ValueError, match="non-negative"):
        compare_rms_maps(
            np.array([[1.0, -1.0]]),
            np.array([[1.0, 1.0]]),
        )


def test_rms_comparison_ignores_invalid_values_outside_valid_region() -> None:
    """Masked pixels never contribute to validation or report metrics."""
    report = compare_rms_maps(
        np.array([[1.0, -1.0]]),
        np.array([[1.0, -2.0]]),
        valid_mask=np.array([[True, False]]),
    )

    assert report.compared_pixel_count == 1
    assert report.excluded_pixel_count == 1


def test_wilson_interval_reports_finite_population_uncertainty() -> None:
    """Perfect recovery retains a nontrivial finite-sample lower bound."""
    interval = wilson_score_interval(20, 20)

    assert interval is not None
    assert interval.confidence_level == 0.95
    assert interval.lower == pytest.approx(0.8388748, rel=1e-6)
    assert interval.upper == 1.0
    assert wilson_score_interval(0, 0) is None


@pytest.mark.parametrize(
    ("successes", "total"),
    [(-1, 2), (3, 2), (True, 2)],
)
def test_wilson_interval_rejects_invalid_counts(
    successes: int,
    total: int,
) -> None:
    """Confidence evidence cannot contain impossible binomial counts."""
    with pytest.raises(ValueError, match="binomial counts"):
        wilson_score_interval(successes, total)


def test_island_population_report_aggregates_cases_and_intervals() -> None:
    """Matrix evidence preserves counts, topology failures, and uncertainty."""
    exact = compare_island_labels(
        np.array([[1, 1, 0], [0, 0, 2]]),
        np.array([[8, 8, 0], [0, 0, 9]]),
    )
    missed = compare_island_labels(
        np.array([[1, 0, 2]]),
        np.array([[4, 0, 0]]),
    )

    report = aggregate_island_comparisons((exact, missed))

    assert report.case_count == 2
    assert report.reference_count == 4
    assert report.candidate_count == 3
    assert report.matched_count == 3
    assert report.completeness == 0.75
    assert report.reliability == 1.0
    assert report.completeness_confidence_interval is not None
    assert report.reliability_confidence_interval is not None
    assert report.minimum_matched_intersection_over_union == 1.0
    assert report.split_count == report.merge_count == 0


def test_empty_island_population_has_explicit_success_without_interval() -> (
    None
):
    """An empty matrix does not fabricate a confidence interval."""
    report = aggregate_island_comparisons(())

    assert report.case_count == 0
    assert report.completeness == report.reliability == 1.0
    assert report.completeness_confidence_interval is None
    assert report.reliability_confidence_interval is None
    assert report.median_matched_intersection_over_union is None
