"""Analytic tests for the independent scientific comparison oracle."""

from __future__ import annotations

from typing import Literal, cast

import numpy as np
import pytest

from hebog.validation.comparison import (
    CatalogueSource,
    compare_catalogues,
    compare_masks,
    compare_rms_maps,
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


def test_empty_masks_agree_without_division_by_zero() -> None:
    """All-false masks have perfect agreement, precision, and recall."""
    empty = np.zeros((2, 3), dtype=np.bool_)

    report = compare_masks(empty, empty)

    assert report.agreement_fraction == 1.0
    assert report.precision == 1.0
    assert report.recall == 1.0


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
