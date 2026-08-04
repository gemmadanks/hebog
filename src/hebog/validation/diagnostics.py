"""Explainable per-source diagnostics for paired scientific campaigns."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Literal, TypeAlias

from hebog.validation.comparison import (
    CatalogueComparisonReport,
    CatalogueMatch,
    CatalogueOutlierThresholds,
    CatalogueSource,
    normalized_uncertainty_samples,
)
from hebog.validation.evidence import (
    CatastrophicMetricDiagnostic,
    NormalizedResidualDiagnostic,
    SourcePairDiagnostic,
)

CatastrophicMetricName: TypeAlias = Literal[
    "position",
    "peak-flux",
    "integrated-flux",
    "fitted-axis",
    "deconvolved-axis",
]

_CATASTROPHIC_METRICS: frozenset[str] = frozenset(
    {
        "position",
        "peak-flux",
        "integrated-flux",
        "fitted-axis",
        "deconvolved-axis",
    }
)


def _maximum_absolute_available(
    values: tuple[float | None, float | None],
) -> float | None:
    """Return the largest absolute available axis difference."""
    available = tuple(abs(value) for value in values if value is not None)
    return max(available) if available else None


def _catastrophic_diagnostic(
    match: CatalogueMatch,
    thresholds: CatalogueOutlierThresholds,
) -> CatastrophicMetricDiagnostic:
    """Evaluate every governed catastrophic metric independently."""
    fitted_axis = _maximum_absolute_available(
        (
            match.fitted_major_axis_fractional_difference,
            match.fitted_minor_axis_fractional_difference,
        )
    )
    deconvolved_axis = _maximum_absolute_available(
        (
            match.deconvolved_major_axis_fractional_difference,
            match.deconvolved_minor_axis_fractional_difference,
        )
    )
    return CatastrophicMetricDiagnostic(
        position=match.separation_beam_fwhm > thresholds.position_beams,
        peak_flux=(
            abs(match.peak_flux_fractional_difference)
            > thresholds.peak_flux_fractional_difference
        ),
        integrated_flux=(
            abs(match.integrated_flux_fractional_difference)
            > thresholds.integrated_flux_fractional_difference
        ),
        fitted_axis=(
            fitted_axis is not None
            and fitted_axis > thresholds.fitted_axis_fractional_difference
        ),
        deconvolved_axis=(
            deconvolved_axis is not None
            and deconvolved_axis
            > thresholds.deconvolved_axis_fractional_difference
        ),
    )


def _gated_catastrophic(
    diagnostic: CatastrophicMetricDiagnostic,
    ungated_metrics: frozenset[CatastrophicMetricName],
) -> bool:
    """Apply an explicit population-specific exclusion set to raw flags."""
    flags = {
        "position": diagnostic.position,
        "peak-flux": diagnostic.peak_flux,
        "integrated-flux": diagnostic.integrated_flux,
        "fitted-axis": diagnostic.fitted_axis,
        "deconvolved-axis": diagnostic.deconvolved_axis,
    }
    return any(
        failed
        for metric, failed in flags.items()
        if metric not in ungated_metrics
    )


def _validate_report_context(
    report: CatalogueComparisonReport,
    *,
    truth_count: int,
    candidate_count: int,
    position_angle_minimum_axis_ratio: float,
) -> None:
    """Keep diagnostics bound to the aggregate comparison context."""
    if report.catastrophic_outlier_thresholds is None:
        raise ValueError("source diagnostics require catastrophic thresholds")
    if (
        not isfinite(position_angle_minimum_axis_ratio)
        or position_angle_minimum_axis_ratio <= 1.0
    ):
        raise ValueError(
            "position_angle_minimum_axis_ratio must be finite and greater "
            "than one"
        )
    if report.reference_count != truth_count:
        raise ValueError("comparison report reference count changed")
    if report.candidate_count != candidate_count:
        raise ValueError("comparison report candidate count changed")


def _validate_truth_metadata(
    truth: Sequence[CatalogueSource],
    truth_strata_by_identifier: Mapping[str, tuple[str, ...]],
    ungated_catastrophic_metrics_by_truth_identifier: Mapping[
        str,
        frozenset[CatastrophicMetricName],
    ],
) -> None:
    """Require complete strata and scoped catastrophic exclusions."""
    truth_identifiers = {source.identifier for source in truth}
    if set(truth_strata_by_identifier) != truth_identifiers or any(
        not strata for strata in truth_strata_by_identifier.values()
    ):
        raise ValueError(
            "truth strata must cover every truth identifier exactly once"
        )
    if not set(ungated_catastrophic_metrics_by_truth_identifier).issubset(
        truth_identifiers
    ):
        raise ValueError("ungated metrics contain an unknown truth identifier")
    unknown_ungated = {
        metric
        for metrics in (
            ungated_catastrophic_metrics_by_truth_identifier.values()
        )
        for metric in metrics
        if metric not in _CATASTROPHIC_METRICS
    }
    if unknown_ungated:
        raise ValueError("unsupported ungated catastrophic metric")


def source_pair_diagnostics(  # noqa: PLR0913
    truth: Sequence[CatalogueSource],
    candidate: Sequence[CatalogueSource],
    report: CatalogueComparisonReport,
    *,
    truth_strata_by_identifier: Mapping[str, tuple[str, ...]],
    ungated_catastrophic_metrics_by_truth_identifier: Mapping[
        str,
        frozenset[CatastrophicMetricName],
    ],
    position_angle_minimum_axis_ratio: float,
) -> tuple[SourcePairDiagnostic, ...]:
    """Expand one aggregate catalogue report into deterministic source rows."""
    _validate_report_context(
        report,
        truth_count=len(truth),
        candidate_count=len(candidate),
        position_angle_minimum_axis_ratio=position_angle_minimum_axis_ratio,
    )
    _validate_truth_metadata(
        truth,
        truth_strata_by_identifier,
        ungated_catastrophic_metrics_by_truth_identifier,
    )
    thresholds = report.catastrophic_outlier_thresholds
    assert thresholds is not None  # Narrowed by _validate_report_context.

    candidate_by_identifier = {
        source.identifier: source for source in candidate
    }
    matches_by_truth = {
        match.reference_identifier: match for match in report.matches
    }
    diagnostics: list[SourcePairDiagnostic] = []

    for truth_source in truth:
        match = matches_by_truth.get(truth_source.identifier)
        truth_strata = tuple(
            sorted(truth_strata_by_identifier[truth_source.identifier])
        )
        if match is None:
            diagnostics.append(
                SourcePairDiagnostic(
                    decision="unmatched-truth",
                    truth_identifier=truth_source.identifier,
                    truth_strata=truth_strata,
                )
            )
            continue
        candidate_source = candidate_by_identifier[match.candidate_identifier]
        catastrophic = _catastrophic_diagnostic(match, thresholds)
        ungated_metrics = ungated_catastrophic_metrics_by_truth_identifier.get(
            truth_source.identifier,
            frozenset(),
        )
        residuals = tuple(
            sorted(
                (
                    NormalizedResidualDiagnostic(metric=metric, value=value)
                    for metric, value in normalized_uncertainty_samples(
                        truth_source,
                        candidate_source,
                        position_angle_minimum_axis_ratio=(
                            position_angle_minimum_axis_ratio
                        ),
                    )
                ),
                key=lambda residual: residual.metric,
            )
        )
        diagnostics.append(
            SourcePairDiagnostic(
                decision="matched",
                truth_identifier=truth_source.identifier,
                candidate_identifier=candidate_source.identifier,
                truth_strata=truth_strata,
                candidate_deconvolution_status=(
                    candidate_source.deconvolution_status
                ),
                candidate_quality_flags=candidate_source.quality_flags,
                classification_agrees=(match.unresolved_classification_agrees),
                separation_beam_fwhm=match.separation_beam_fwhm,
                peak_flux_fractional_difference=(
                    match.peak_flux_fractional_difference
                ),
                integrated_flux_fractional_difference=(
                    match.integrated_flux_fractional_difference
                ),
                maximum_absolute_fitted_axis_fractional_difference=(
                    _maximum_absolute_available(
                        (
                            match.fitted_major_axis_fractional_difference,
                            match.fitted_minor_axis_fractional_difference,
                        )
                    )
                ),
                maximum_absolute_deconvolved_axis_fractional_difference=(
                    _maximum_absolute_available(
                        (
                            match.deconvolved_major_axis_fractional_difference,
                            match.deconvolved_minor_axis_fractional_difference,
                        )
                    )
                ),
                fitted_position_angle_difference_degrees=(
                    match.fitted_position_angle_difference_degrees
                ),
                deconvolved_position_angle_difference_degrees=(
                    match.deconvolved_position_angle_difference_degrees
                ),
                catastrophic=catastrophic,
                gated_catastrophic=_gated_catastrophic(
                    catastrophic,
                    ungated_metrics,
                ),
                normalized_residuals=residuals,
            )
        )

    for candidate_source in candidate:
        if candidate_source.identifier not in (
            report.unmatched_candidate_identifiers
        ):
            continue
        diagnostics.append(
            SourcePairDiagnostic(
                decision="unmatched-candidate",
                candidate_identifier=candidate_source.identifier,
                candidate_deconvolution_status=(
                    candidate_source.deconvolution_status
                ),
                candidate_quality_flags=candidate_source.quality_flags,
            )
        )
    return tuple(diagnostics)
