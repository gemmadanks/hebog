# pyright: reportMissingTypeStubs=false
"""Independent scientific comparison reports for governed validation.

Catalogue matching uses canonical degrees and janskys. It maximizes the number
of valid matches, then total matched integrated flux, then angular proximity.
Array reports never broadcast inputs and state how many pixels were excluded.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any, Literal, Protocol, Self, cast

import numpy as np
import numpy.typing as npt
from scipy.optimize import (
    linear_sum_assignment as _lsa,  # pyright: ignore[reportUnknownVariableType]
)

_MINIMUM_DECLINATION_DEGREES = -90.0
_MAXIMUM_DECLINATION_DEGREES = 90.0
_FULL_CIRCLE_DEGREES = 360.0
_IMAGE_DIMENSIONS = 2
_HALF_CIRCLE_DEGREES = 180.0
_UncertaintyMetric = Literal[
    "right-ascension",
    "declination",
    "peak-flux",
    "integrated-flux",
    "fitted-major-axis",
    "fitted-minor-axis",
    "fitted-position-angle",
    "deconvolved-major-axis",
    "deconvolved-minor-axis",
    "deconvolved-position-angle",
]


class _LinearSumAssignment(Protocol):
    """Typed boundary around SciPy's untyped assignment function."""

    def __call__(
        self,
        cost_matrix: npt.NDArray[np.float64],
        *,
        maximize: bool,
    ) -> tuple[npt.NDArray[np.intp], npt.NDArray[np.intp]]: ...


_linear_sum_assignment = cast(_LinearSumAssignment, _lsa)


def _conversion_scale(
    unit: str,
    scales: dict[str, float],
    *,
    field_name: str,
) -> float:
    """Resolve one explicitly supported unit with a clear runtime error."""
    try:
        return scales[unit]
    except KeyError:
        supported = ", ".join(scales)
        raise ValueError(
            f"unsupported {field_name} {unit!r}; expected {supported}"
        ) from None


def _require_optional_positive(
    values: Sequence[float | None],
    *,
    field_name: str,
) -> None:
    """Require every available uncertainty to be finite and positive."""
    if any(
        value is not None and (not np.isfinite(value) or value <= 0)
        for value in values
    ):
        raise ValueError(f"{field_name} must be finite and positive")


@dataclass(frozen=True, slots=True)
class CatalogueEllipse:
    """One canonical comparison ellipse and optional one-sigma errors."""

    major_fwhm_degrees: float
    minor_fwhm_degrees: float
    position_angle_degrees: float
    major_fwhm_error_degrees: float | None = None
    minor_fwhm_error_degrees: float | None = None
    position_angle_error_degrees: float | None = None

    def __post_init__(self) -> None:
        """Require a positive ordered ellipse modulo 180 degrees."""
        if (
            not np.isfinite(self.major_fwhm_degrees)
            or not np.isfinite(self.minor_fwhm_degrees)
            or self.major_fwhm_degrees <= 0
            or self.minor_fwhm_degrees <= 0
        ):
            raise ValueError(
                "catalogue ellipse axes must be finite and positive"
            )
        if self.minor_fwhm_degrees > self.major_fwhm_degrees:
            raise ValueError("catalogue ellipse axes must be ordered")
        if not np.isfinite(self.position_angle_degrees):
            raise ValueError("catalogue position angle must be finite")
        object.__setattr__(
            self,
            "position_angle_degrees",
            self.position_angle_degrees % _HALF_CIRCLE_DEGREES,
        )
        _require_optional_positive(
            (
                self.major_fwhm_error_degrees,
                self.minor_fwhm_error_degrees,
                self.position_angle_error_degrees,
            ),
            field_name="catalogue ellipse errors",
        )


@dataclass(frozen=True, slots=True)
class CatalogueOutlierThresholds:
    """Caller-frozen thresholds defining catastrophic matched-row errors."""

    position_beams: float
    peak_flux_fractional_difference: float
    integrated_flux_fractional_difference: float
    fitted_axis_fractional_difference: float
    deconvolved_axis_fractional_difference: float

    def __post_init__(self) -> None:
        """Require finite positive thresholds without hidden defaults."""
        if any(
            not np.isfinite(value) or value <= 0
            for value in (
                self.position_beams,
                self.peak_flux_fractional_difference,
                self.integrated_flux_fractional_difference,
                self.fitted_axis_fractional_difference,
                self.deconvolved_axis_fractional_difference,
            )
        ):
            raise ValueError("catalogue outlier thresholds must be positive")


@dataclass(frozen=True, slots=True)
class CatalogueSource:
    """One source in the comparison oracle's canonical units."""

    identifier: str
    right_ascension_degrees: float
    declination_degrees: float
    peak_flux_jy_per_beam: float
    integrated_flux_jy: float
    right_ascension_error_degrees: float | None = None
    declination_error_degrees: float | None = None
    peak_flux_error_jy_per_beam: float | None = None
    integrated_flux_error_jy: float | None = None
    fitted_shape: CatalogueEllipse | None = None
    deconvolved_shape: CatalogueEllipse | None = None
    deconvolution_status: Literal["resolved", "unresolved", "unavailable"] = (
        "unavailable"
    )
    island_identifier: str | None = None
    component_count: int | None = None
    quality_flags: tuple[str, ...] = ()

    def _validate_optional_metadata(self) -> None:
        """Validate optional errors, associations, and quality flags."""
        _require_optional_positive(
            (
                self.right_ascension_error_degrees,
                self.declination_error_degrees,
                self.peak_flux_error_jy_per_beam,
                self.integrated_flux_error_jy,
            ),
            field_name="source errors",
        )
        if self.island_identifier is not None and not self.island_identifier:
            raise ValueError("island identifier must not be empty")
        if self.component_count is not None and self.component_count <= 0:
            raise ValueError("component count must be positive")
        if self.quality_flags != tuple(sorted(set(self.quality_flags))) or any(
            not flag for flag in self.quality_flags
        ):
            raise ValueError("quality flags must be non-empty and canonical")

    def _validate_deconvolution(self) -> None:
        """Keep resolved, unresolved, and unavailable states unambiguous."""
        if self.deconvolution_status == "resolved":
            if self.deconvolved_shape is None:
                raise ValueError("resolved deconvolution requires a shape")
        elif self.deconvolved_shape is not None:
            raise ValueError("only resolved deconvolution may contain a shape")
        if (
            self.deconvolution_status == "unresolved"
            and "unresolved" not in self.quality_flags
        ):
            raise ValueError(
                "unresolved deconvolution requires its quality flag"
            )

    def __post_init__(self) -> None:
        """Validate identity, coordinates, and positive finite fluxes."""
        if not self.identifier:
            raise ValueError("source identifier must not be empty")
        numeric_values = (
            self.right_ascension_degrees,
            self.declination_degrees,
            self.peak_flux_jy_per_beam,
            self.integrated_flux_jy,
        )
        if not all(np.isfinite(value) for value in numeric_values):
            raise ValueError("source coordinates and fluxes must be finite")
        if not (
            _MINIMUM_DECLINATION_DEGREES
            <= self.declination_degrees
            <= _MAXIMUM_DECLINATION_DEGREES
        ):
            raise ValueError("declination must be within [-90, 90] degrees")
        if self.peak_flux_jy_per_beam <= 0 or self.integrated_flux_jy <= 0:
            raise ValueError("source fluxes must be positive")
        self._validate_optional_metadata()
        self._validate_deconvolution()
        normalized_right_ascension = (
            self.right_ascension_degrees % _FULL_CIRCLE_DEGREES
        )
        object.__setattr__(
            self,
            "right_ascension_degrees",
            normalized_right_ascension,
        )

    @classmethod
    def from_units(  # noqa: PLR0913
        cls,
        *,
        identifier: str,
        right_ascension: float,
        declination: float,
        angle_unit: Literal["deg", "arcsec"],
        peak_flux_density: float,
        peak_flux_unit: Literal["Jy/beam", "mJy/beam"],
        integrated_flux_density: float,
        integrated_flux_unit: Literal["Jy", "mJy"],
    ) -> Self:
        """Convert supported angular and flux units into canonical units."""
        angle_scale = _conversion_scale(
            angle_unit,
            {"deg": 1.0, "arcsec": 1.0 / 3600.0},
            field_name="angle_unit",
        )
        peak_flux_scale = _conversion_scale(
            peak_flux_unit,
            {"Jy/beam": 1.0, "mJy/beam": 0.001},
            field_name="peak_flux_unit",
        )
        integrated_flux_scale = _conversion_scale(
            integrated_flux_unit,
            {"Jy": 1.0, "mJy": 0.001},
            field_name="integrated_flux_unit",
        )
        return cls(
            identifier=identifier,
            right_ascension_degrees=right_ascension * angle_scale,
            declination_degrees=declination * angle_scale,
            peak_flux_jy_per_beam=peak_flux_density * peak_flux_scale,
            integrated_flux_jy=(
                integrated_flux_density * integrated_flux_scale
            ),
        )


@dataclass(frozen=True, slots=True)
class CatalogueMatch:
    """One assigned reference/candidate source pair."""

    reference_identifier: str
    candidate_identifier: str
    separation_beam_fwhm: float
    peak_flux_fractional_difference: float
    integrated_flux_fractional_difference: float
    fitted_major_axis_fractional_difference: float | None
    fitted_minor_axis_fractional_difference: float | None
    fitted_position_angle_difference_degrees: float | None
    deconvolved_major_axis_fractional_difference: float | None
    deconvolved_minor_axis_fractional_difference: float | None
    deconvolved_position_angle_difference_degrees: float | None
    unresolved_classification_agrees: bool | None
    component_count_agrees: bool | None
    quality_flag_jaccard: float
    quality_flags_agree: bool


@dataclass(frozen=True, slots=True)
class UncertaintyCalibrationReport:
    """Bias, dispersion, and one-sigma coverage for one reported error."""

    metric: _UncertaintyMetric
    sample_count: int
    within_one_sigma_count: int
    coverage_fraction: float
    mean_normalized_residual: float
    sample_standard_deviation: float | None


@dataclass(frozen=True, slots=True)
class AssociationComparisonReport:
    """Pairwise parent-association confusion counts and rates."""

    matched_source_count: int
    compared_pair_count: int
    true_positive_pair_count: int
    false_positive_pair_count: int
    false_negative_pair_count: int
    disagreement_pair_count: int
    agreement_fraction: float | None
    precision: float
    recall: float
    intersection_over_union: float


@dataclass(frozen=True, slots=True)
class CatalogueComparisonReport:
    """Assignment, completeness, reliability, position, and flux metrics."""

    reference_count: int
    candidate_count: int
    matches: tuple[CatalogueMatch, ...]
    unmatched_reference_identifiers: tuple[str, ...]
    unmatched_candidate_identifiers: tuple[str, ...]
    completeness: float
    reliability: float
    median_separation_beam_fwhm: float | None
    percentile_95_separation_beam_fwhm: float | None
    median_absolute_peak_flux_fractional_difference: float | None
    percentile_95_absolute_peak_flux_fractional_difference: float | None
    median_absolute_integrated_flux_fractional_difference: float | None
    percentile_95_absolute_integrated_flux_fractional_difference: float | None
    median_absolute_fitted_axis_fractional_difference: float | None
    percentile_95_absolute_fitted_axis_fractional_difference: float | None
    median_absolute_deconvolved_axis_fractional_difference: float | None
    percentile_95_absolute_deconvolved_axis_fractional_difference: float | None
    median_absolute_fitted_position_angle_difference_degrees: float | None
    percentile_95_absolute_fitted_position_angle_difference_degrees: (
        float | None
    )
    median_absolute_deconvolved_position_angle_difference_degrees: float | None
    percentile_95_absolute_deconvolved_position_angle_difference_degrees: (
        float | None
    )
    unresolved_classification_count: int
    unresolved_classification_accuracy: float | None
    association: AssociationComparisonReport
    component_count_comparison_count: int
    component_count_agreement_fraction: float | None
    quality_flag_exact_agreement_fraction: float | None
    median_quality_flag_jaccard: float | None
    uncertainty_calibration: tuple[UncertaintyCalibrationReport, ...]
    catastrophic_outlier_thresholds: CatalogueOutlierThresholds | None
    catastrophic_outlier_reference_identifiers: tuple[str, ...]
    catastrophic_outlier_fraction: float | None


@dataclass(frozen=True, slots=True)
class MaskComparisonReport:
    """Pixel confusion matrix and derived mask agreement metrics."""

    compared_pixel_count: int
    excluded_pixel_count: int
    true_positive_count: int
    true_negative_count: int
    false_positive_count: int
    false_negative_count: int
    agreement_fraction: float
    precision: float
    recall: float
    intersection_over_union: float


@dataclass(frozen=True, slots=True)
class IslandLabelMatch:
    """One overlap-based assignment between two labelled regions."""

    reference_label: int
    candidate_label: int
    intersection_pixel_count: int
    union_pixel_count: int
    intersection_over_union: float


@dataclass(frozen=True, slots=True)
class IslandComparisonReport:
    """Object matches, splits, merges, and overlap for labelled masks."""

    compared_pixel_count: int
    excluded_pixel_count: int
    reference_count: int
    candidate_count: int
    matches: tuple[IslandLabelMatch, ...]
    unmatched_reference_labels: tuple[int, ...]
    unmatched_candidate_labels: tuple[int, ...]
    split_reference_labels: tuple[int, ...]
    merged_candidate_labels: tuple[int, ...]
    completeness: float
    reliability: float
    median_matched_intersection_over_union: float | None
    minimum_matched_intersection_over_union: float | None


@dataclass(frozen=True, slots=True)
class BinomialConfidenceInterval:
    """Two-sided Wilson score interval for one observed success rate."""

    confidence_level: float
    lower: float
    upper: float


@dataclass(frozen=True, slots=True)
class IslandPopulationReport:
    """Aggregate object non-inferiority metrics across a dataset matrix."""

    case_count: int
    reference_count: int
    candidate_count: int
    matched_count: int
    completeness: float
    reliability: float
    completeness_confidence_interval: BinomialConfidenceInterval | None
    reliability_confidence_interval: BinomialConfidenceInterval | None
    split_count: int
    merge_count: int
    median_matched_intersection_over_union: float | None
    minimum_matched_intersection_over_union: float | None


@dataclass(frozen=True, slots=True)
class RmsComparisonReport:
    """Absolute and relative RMS-map differences in canonical units."""

    compared_pixel_count: int
    relative_pixel_count: int
    excluded_pixel_count: int
    zero_reference_pixel_count: int
    median_absolute_difference_jy_per_beam: float | None
    percentile_95_absolute_difference_jy_per_beam: float | None
    median_absolute_fractional_difference: float | None
    percentile_95_absolute_fractional_difference: float | None


def _angular_separations_degrees(
    reference: Sequence[CatalogueSource],
    candidate: Sequence[CatalogueSource],
) -> npt.NDArray[np.float64]:
    """Return robust pairwise great-circle separations in degrees."""
    reference_ra = np.deg2rad(
        np.asarray(
            [source.right_ascension_degrees for source in reference],
            dtype=np.float64,
        )
    )[:, np.newaxis]
    candidate_ra = np.deg2rad(
        np.asarray(
            [source.right_ascension_degrees for source in candidate],
            dtype=np.float64,
        )
    )[np.newaxis, :]
    reference_dec = np.deg2rad(
        np.asarray(
            [source.declination_degrees for source in reference],
            dtype=np.float64,
        )
    )[:, np.newaxis]
    candidate_dec = np.deg2rad(
        np.asarray(
            [source.declination_degrees for source in candidate],
            dtype=np.float64,
        )
    )[np.newaxis, :]

    right_ascension_delta = candidate_ra - reference_ra
    haversine = np.square(np.sin((candidate_dec - reference_dec) / 2.0))
    haversine += (
        np.cos(reference_dec)
        * np.cos(candidate_dec)
        * np.square(np.sin(right_ascension_delta / 2.0))
    )
    angular_distance = 2.0 * np.arcsin(np.sqrt(np.clip(haversine, 0.0, 1.0)))
    return np.asarray(np.rad2deg(angular_distance), dtype=np.float64)


def _validate_catalogue_identifiers(
    sources: Sequence[CatalogueSource],
    *,
    catalogue_name: str,
) -> None:
    """Require stable unique row identity within one catalogue."""
    identifiers = [source.identifier for source in sources]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{catalogue_name} identifiers must be unique")


def _match_indices(
    reference: Sequence[CatalogueSource],
    candidate: Sequence[CatalogueSource],
    *,
    beam_fwhm_degrees: float,
    maximum_separation_beams: float,
) -> tuple[tuple[int, int, float], ...]:
    """Assign valid pairs using the documented lexicographic objectives."""
    if len(reference) == 0 or len(candidate) == 0:
        return ()
    separations_beams = (
        _angular_separations_degrees(reference, candidate) / beam_fwhm_degrees
    )
    valid_pairs = separations_beams <= maximum_separation_beams
    reference_flux = np.asarray(
        [source.integrated_flux_jy for source in reference],
        dtype=np.float64,
    )[:, np.newaxis]
    candidate_flux = np.asarray(
        [source.integrated_flux_jy for source in candidate],
        dtype=np.float64,
    )[np.newaxis, :]
    matched_flux = np.minimum(reference_flux, candidate_flux)

    total_flux_bound = float(reference_flux.sum() + candidate_flux.sum())
    match_count_bonus = total_flux_bound + 1.0
    proximity_scale = match_count_bonus * np.finfo(np.float64).eps * 16.0
    normalized_separation = separations_beams / maximum_separation_beams
    scores = match_count_bonus + matched_flux
    scores -= proximity_scale * normalized_separation
    invalid_score = -match_count_bonus * (
        min(len(reference), len(candidate)) + 1
    )
    scores = np.where(valid_pairs, scores, invalid_score)

    reference_indices, candidate_indices = _linear_sum_assignment(
        scores,
        maximize=True,
    )
    return tuple(
        (
            int(reference_index),
            int(candidate_index),
            float(separations_beams[reference_index, candidate_index]),
        )
        for reference_index, candidate_index in zip(
            reference_indices,
            candidate_indices,
            strict=True,
        )
        if valid_pairs[reference_index, candidate_index]
    )


def _median(values: Sequence[float]) -> float | None:
    """Return a scalar median or an explicit empty result."""
    if not values:
        return None
    return float(np.median(np.asarray(values, dtype=np.float64)))


def _percentile_95(values: Sequence[float]) -> float | None:
    """Return a scalar linear 95th percentile or an explicit empty result."""
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=np.float64), 95.0))


def _maximum_absolute_available(
    values: Sequence[float | None],
) -> float | None:
    """Return the largest available absolute value for one matched source."""
    available = [abs(value) for value in values if value is not None]
    return max(available) if available else None


def _signed_periodic_difference(
    candidate: float,
    reference: float,
    *,
    period: float,
) -> float:
    """Return the shortest signed candidate-minus-reference difference."""
    return (candidate - reference + period / 2.0) % period - period / 2.0


def _shape_differences(
    reference: CatalogueEllipse | None,
    candidate: CatalogueEllipse | None,
) -> tuple[float | None, float | None, float | None]:
    """Return signed axis fractions and half-circle orientation difference."""
    if reference is None or candidate is None:
        return None, None, None
    return (
        (candidate.major_fwhm_degrees - reference.major_fwhm_degrees)
        / reference.major_fwhm_degrees,
        (candidate.minor_fwhm_degrees - reference.minor_fwhm_degrees)
        / reference.minor_fwhm_degrees,
        _signed_periodic_difference(
            candidate.position_angle_degrees,
            reference.position_angle_degrees,
            period=_HALF_CIRCLE_DEGREES,
        ),
    )


def _deconvolution_classification_agrees(
    reference: CatalogueSource,
    candidate: CatalogueSource,
) -> bool | None:
    """Compare resolved/unresolved states while excluding unavailable rows."""
    comparable = {"resolved", "unresolved"}
    if (
        reference.deconvolution_status not in comparable
        or candidate.deconvolution_status not in comparable
    ):
        return None
    return reference.deconvolution_status == candidate.deconvolution_status


def _quality_flag_jaccard(
    reference: CatalogueSource,
    candidate: CatalogueSource,
) -> float:
    """Compare canonical quality-flag sets with explicit empty agreement."""
    reference_flags = set(reference.quality_flags)
    candidate_flags = set(candidate.quality_flags)
    union = reference_flags | candidate_flags
    if not union:
        return 1.0
    return len(reference_flags & candidate_flags) / len(union)


def _normalized_uncertainty_samples(
    reference: CatalogueSource,
    candidate: CatalogueSource,
) -> tuple[tuple[str, float], ...]:
    """Normalize candidate-minus-reference residuals by candidate errors."""
    samples: list[tuple[str, float]] = []

    def add(metric: str, difference: float, uncertainty: float | None) -> None:
        if uncertainty is not None:
            samples.append((metric, difference / uncertainty))

    add(
        "right-ascension",
        _signed_periodic_difference(
            candidate.right_ascension_degrees,
            reference.right_ascension_degrees,
            period=_FULL_CIRCLE_DEGREES,
        ),
        candidate.right_ascension_error_degrees,
    )
    add(
        "declination",
        candidate.declination_degrees - reference.declination_degrees,
        candidate.declination_error_degrees,
    )
    add(
        "peak-flux",
        candidate.peak_flux_jy_per_beam - reference.peak_flux_jy_per_beam,
        candidate.peak_flux_error_jy_per_beam,
    )
    add(
        "integrated-flux",
        candidate.integrated_flux_jy - reference.integrated_flux_jy,
        candidate.integrated_flux_error_jy,
    )
    _add_shape_uncertainty_samples(
        samples,
        prefix="fitted",
        reference=reference.fitted_shape,
        candidate=candidate.fitted_shape,
    )
    _add_shape_uncertainty_samples(
        samples,
        prefix="deconvolved",
        reference=reference.deconvolved_shape,
        candidate=candidate.deconvolved_shape,
    )
    return tuple(samples)


def _add_shape_uncertainty_samples(
    samples: list[tuple[str, float]],
    *,
    prefix: Literal["fitted", "deconvolved"],
    reference: CatalogueEllipse | None,
    candidate: CatalogueEllipse | None,
) -> None:
    """Append normalized ellipse residuals when both shapes are available."""
    if reference is None or candidate is None:
        return
    entries = (
        (
            f"{prefix}-major-axis",
            candidate.major_fwhm_degrees - reference.major_fwhm_degrees,
            candidate.major_fwhm_error_degrees,
        ),
        (
            f"{prefix}-minor-axis",
            candidate.minor_fwhm_degrees - reference.minor_fwhm_degrees,
            candidate.minor_fwhm_error_degrees,
        ),
        (
            f"{prefix}-position-angle",
            _signed_periodic_difference(
                candidate.position_angle_degrees,
                reference.position_angle_degrees,
                period=_HALF_CIRCLE_DEGREES,
            ),
            candidate.position_angle_error_degrees,
        ),
    )
    samples.extend(
        (metric, difference / uncertainty)
        for metric, difference, uncertainty in entries
        if uncertainty is not None
    )


def _uncertainty_calibration_reports(
    samples: dict[str, list[float]],
) -> tuple[UncertaintyCalibrationReport, ...]:
    """Aggregate normalized residuals without inventing empty metrics."""
    reports: list[UncertaintyCalibrationReport] = []
    for metric, metric_samples in samples.items():
        values = np.asarray(metric_samples, dtype=np.float64)
        within_one_sigma = int(np.count_nonzero(np.abs(values) <= 1.0))
        reports.append(
            UncertaintyCalibrationReport(
                metric=cast(_UncertaintyMetric, metric),
                sample_count=len(metric_samples),
                within_one_sigma_count=within_one_sigma,
                coverage_fraction=within_one_sigma / len(metric_samples),
                mean_normalized_residual=float(np.mean(values)),
                sample_standard_deviation=(
                    float(np.std(values, ddof=1))
                    if len(metric_samples) > 1
                    else None
                ),
            )
        )
    return tuple(reports)


def _association_report(
    reference: Sequence[CatalogueSource],
    candidate: Sequence[CatalogueSource],
    assignments: tuple[tuple[int, int, float], ...],
) -> AssociationComparisonReport:
    """Compare same-island relationships from linear-size count summaries."""
    associations = [
        (
            reference[reference_index].island_identifier,
            candidate[candidate_index].island_identifier,
        )
        for reference_index, candidate_index, _ in assignments
        if reference[reference_index].island_identifier is not None
        and candidate[candidate_index].island_identifier is not None
    ]
    compared = len(associations) * (len(associations) - 1) // 2
    reference_counts = Counter(item[0] for item in associations)
    candidate_counts = Counter(item[1] for item in associations)
    joint_counts = Counter(associations)

    def pair_count(counts: Sequence[int]) -> int:
        return sum(count * (count - 1) // 2 for count in counts)

    same_reference = pair_count(tuple(reference_counts.values()))
    same_candidate = pair_count(tuple(candidate_counts.values()))
    same_both = pair_count(tuple(joint_counts.values()))
    false_negative = same_reference - same_both
    false_positive = same_candidate - same_both
    disagreements = false_negative + false_positive
    agreement = (compared - disagreements) / compared if compared else None
    precision_denominator = same_both + false_positive
    recall_denominator = same_both + false_negative
    union = same_both + false_positive + false_negative
    return AssociationComparisonReport(
        matched_source_count=len(associations),
        compared_pair_count=compared,
        true_positive_pair_count=same_both,
        false_positive_pair_count=false_positive,
        false_negative_pair_count=false_negative,
        disagreement_pair_count=disagreements,
        agreement_fraction=agreement,
        precision=(
            same_both / precision_denominator if precision_denominator else 1.0
        ),
        recall=same_both / recall_denominator if recall_denominator else 1.0,
        intersection_over_union=same_both / union if union else 1.0,
    )


def _is_catastrophic_outlier(
    match: CatalogueMatch,
    thresholds: CatalogueOutlierThresholds,
) -> bool:
    """Apply one explicit matched-row catastrophic-outlier definition."""
    fitted_axes = (
        match.fitted_major_axis_fractional_difference,
        match.fitted_minor_axis_fractional_difference,
    )
    deconvolved_axes = (
        match.deconvolved_major_axis_fractional_difference,
        match.deconvolved_minor_axis_fractional_difference,
    )
    return (
        match.separation_beam_fwhm > thresholds.position_beams
        or abs(match.peak_flux_fractional_difference)
        > thresholds.peak_flux_fractional_difference
        or abs(match.integrated_flux_fractional_difference)
        > thresholds.integrated_flux_fractional_difference
        or any(
            value is not None
            and abs(value) > thresholds.fitted_axis_fractional_difference
            for value in fitted_axes
        )
        or any(
            value is not None
            and abs(value) > thresholds.deconvolved_axis_fractional_difference
            for value in deconvolved_axes
        )
    )


def compare_catalogues(
    reference: Sequence[CatalogueSource],
    candidate: Sequence[CatalogueSource],
    *,
    beam_fwhm_degrees: float,
    maximum_separation_beams: float,
    outlier_thresholds: CatalogueOutlierThresholds | None = None,
) -> CatalogueComparisonReport:
    """Match two catalogues and calculate scientific comparison metrics."""
    if not np.isfinite(beam_fwhm_degrees) or beam_fwhm_degrees <= 0:
        raise ValueError("beam_fwhm_degrees must be positive and finite")
    if (
        not np.isfinite(maximum_separation_beams)
        or maximum_separation_beams <= 0
    ):
        raise ValueError(
            "maximum_separation_beams must be positive and finite"
        )
    _validate_catalogue_identifiers(reference, catalogue_name="reference")
    _validate_catalogue_identifiers(candidate, catalogue_name="candidate")

    assignments = _match_indices(
        reference,
        candidate,
        beam_fwhm_degrees=beam_fwhm_degrees,
        maximum_separation_beams=maximum_separation_beams,
    )
    matches: list[CatalogueMatch] = []
    uncertainty_samples: dict[str, list[float]] = {}
    matched_reference_indices: set[int] = set()
    matched_candidate_indices: set[int] = set()
    for reference_index, candidate_index, separation_beams in assignments:
        reference_source = reference[reference_index]
        candidate_source = candidate[candidate_index]
        matched_reference_indices.add(reference_index)
        matched_candidate_indices.add(candidate_index)
        fitted_shape_differences = _shape_differences(
            reference_source.fitted_shape,
            candidate_source.fitted_shape,
        )
        deconvolved_shape_differences = _shape_differences(
            reference_source.deconvolved_shape,
            candidate_source.deconvolved_shape,
        )
        for metric, sample in _normalized_uncertainty_samples(
            reference_source,
            candidate_source,
        ):
            uncertainty_samples.setdefault(metric, []).append(sample)
        matches.append(
            CatalogueMatch(
                reference_identifier=reference_source.identifier,
                candidate_identifier=candidate_source.identifier,
                separation_beam_fwhm=separation_beams,
                peak_flux_fractional_difference=(
                    candidate_source.peak_flux_jy_per_beam
                    - reference_source.peak_flux_jy_per_beam
                )
                / reference_source.peak_flux_jy_per_beam,
                integrated_flux_fractional_difference=(
                    candidate_source.integrated_flux_jy
                    - reference_source.integrated_flux_jy
                )
                / reference_source.integrated_flux_jy,
                fitted_major_axis_fractional_difference=(
                    fitted_shape_differences[0]
                ),
                fitted_minor_axis_fractional_difference=(
                    fitted_shape_differences[1]
                ),
                fitted_position_angle_difference_degrees=(
                    fitted_shape_differences[2]
                ),
                deconvolved_major_axis_fractional_difference=(
                    deconvolved_shape_differences[0]
                ),
                deconvolved_minor_axis_fractional_difference=(
                    deconvolved_shape_differences[1]
                ),
                deconvolved_position_angle_difference_degrees=(
                    deconvolved_shape_differences[2]
                ),
                unresolved_classification_agrees=(
                    _deconvolution_classification_agrees(
                        reference_source,
                        candidate_source,
                    )
                ),
                component_count_agrees=(
                    None
                    if reference_source.component_count is None
                    or candidate_source.component_count is None
                    else reference_source.component_count
                    == candidate_source.component_count
                ),
                quality_flag_jaccard=_quality_flag_jaccard(
                    reference_source,
                    candidate_source,
                ),
                quality_flags_agree=(
                    reference_source.quality_flags
                    == candidate_source.quality_flags
                ),
            )
        )

    separations = [match.separation_beam_fwhm for match in matches]
    peak_flux_differences = [
        abs(match.peak_flux_fractional_difference) for match in matches
    ]
    integrated_flux_differences = [
        abs(match.integrated_flux_fractional_difference) for match in matches
    ]
    fitted_axis_differences = [
        value
        for match in matches
        if (
            value := _maximum_absolute_available(
                (
                    match.fitted_major_axis_fractional_difference,
                    match.fitted_minor_axis_fractional_difference,
                )
            )
        )
        is not None
    ]
    deconvolved_axis_differences = [
        value
        for match in matches
        if (
            value := _maximum_absolute_available(
                (
                    match.deconvolved_major_axis_fractional_difference,
                    match.deconvolved_minor_axis_fractional_difference,
                )
            )
        )
        is not None
    ]
    fitted_position_angle_differences = [
        abs(match.fitted_position_angle_difference_degrees)
        for match in matches
        if match.fitted_position_angle_difference_degrees is not None
    ]
    deconvolved_position_angle_differences = [
        abs(match.deconvolved_position_angle_difference_degrees)
        for match in matches
        if match.deconvolved_position_angle_difference_degrees is not None
    ]
    unresolved_classifications = [
        match.unresolved_classification_agrees
        for match in matches
        if match.unresolved_classification_agrees is not None
    ]
    component_comparisons = [
        match.component_count_agrees
        for match in matches
        if match.component_count_agrees is not None
    ]
    association_report = _association_report(reference, candidate, assignments)
    catastrophic_outliers = (
        tuple(
            match.reference_identifier
            for match in matches
            if _is_catastrophic_outlier(match, outlier_thresholds)
        )
        if outlier_thresholds is not None
        else ()
    )
    match_count = len(matches)
    reference_count = len(reference)
    candidate_count = len(candidate)
    return CatalogueComparisonReport(
        reference_count=reference_count,
        candidate_count=candidate_count,
        matches=tuple(matches),
        unmatched_reference_identifiers=tuple(
            source.identifier
            for index, source in enumerate(reference)
            if index not in matched_reference_indices
        ),
        unmatched_candidate_identifiers=tuple(
            source.identifier
            for index, source in enumerate(candidate)
            if index not in matched_candidate_indices
        ),
        completeness=(
            match_count / reference_count if reference_count else 1.0
        ),
        reliability=(
            match_count / candidate_count if candidate_count else 1.0
        ),
        median_separation_beam_fwhm=_median(separations),
        percentile_95_separation_beam_fwhm=_percentile_95(separations),
        median_absolute_peak_flux_fractional_difference=_median(
            peak_flux_differences
        ),
        percentile_95_absolute_peak_flux_fractional_difference=(
            _percentile_95(peak_flux_differences)
        ),
        median_absolute_integrated_flux_fractional_difference=_median(
            integrated_flux_differences
        ),
        percentile_95_absolute_integrated_flux_fractional_difference=(
            _percentile_95(integrated_flux_differences)
        ),
        median_absolute_fitted_axis_fractional_difference=_median(
            fitted_axis_differences
        ),
        percentile_95_absolute_fitted_axis_fractional_difference=(
            _percentile_95(fitted_axis_differences)
        ),
        median_absolute_deconvolved_axis_fractional_difference=_median(
            deconvolved_axis_differences
        ),
        percentile_95_absolute_deconvolved_axis_fractional_difference=(
            _percentile_95(deconvolved_axis_differences)
        ),
        median_absolute_fitted_position_angle_difference_degrees=_median(
            fitted_position_angle_differences
        ),
        percentile_95_absolute_fitted_position_angle_difference_degrees=(
            _percentile_95(fitted_position_angle_differences)
        ),
        median_absolute_deconvolved_position_angle_difference_degrees=(
            _median(deconvolved_position_angle_differences)
        ),
        percentile_95_absolute_deconvolved_position_angle_difference_degrees=(
            _percentile_95(deconvolved_position_angle_differences)
        ),
        unresolved_classification_count=len(unresolved_classifications),
        unresolved_classification_accuracy=(
            sum(unresolved_classifications) / len(unresolved_classifications)
            if unresolved_classifications
            else None
        ),
        association=association_report,
        component_count_comparison_count=len(component_comparisons),
        component_count_agreement_fraction=(
            sum(component_comparisons) / len(component_comparisons)
            if component_comparisons
            else None
        ),
        quality_flag_exact_agreement_fraction=(
            sum(match.quality_flags_agree for match in matches) / match_count
            if match_count
            else None
        ),
        median_quality_flag_jaccard=_median(
            [match.quality_flag_jaccard for match in matches]
        ),
        uncertainty_calibration=_uncertainty_calibration_reports(
            uncertainty_samples
        ),
        catastrophic_outlier_thresholds=outlier_thresholds,
        catastrophic_outlier_reference_identifiers=catastrophic_outliers,
        catastrophic_outlier_fraction=(
            len(catastrophic_outliers) / match_count
            if outlier_thresholds is not None and match_count
            else None
        ),
    )


def _as_same_shape_arrays(
    reference: npt.ArrayLike,
    candidate: npt.ArrayLike,
) -> tuple[npt.NDArray[np.generic], npt.NDArray[np.generic]]:
    """Materialize two arrays while forbidding implicit broadcasting."""
    reference_array = np.asarray(reference)
    candidate_array = np.asarray(candidate)
    if reference_array.shape != candidate_array.shape:
        raise ValueError("reference and candidate arrays must have same shape")
    return reference_array, candidate_array


def _valid_region(
    shape: tuple[int, ...],
    valid_mask: npt.ArrayLike | None,
) -> npt.NDArray[np.bool_]:
    """Validate or construct the caller-selected comparison region."""
    if valid_mask is None:
        return np.ones(shape, dtype=np.bool_)
    valid_array = np.asarray(valid_mask)
    if valid_array.shape != shape:
        raise ValueError("valid_mask must have the same shape as the products")
    if not np.issubdtype(valid_array.dtype, np.bool_):
        raise TypeError("valid_mask must be a boolean array")
    return np.asarray(valid_array, dtype=np.bool_)


def _safe_classification_fraction(
    numerator: int,
    denominator: int,
    *,
    empty_value: float,
) -> float:
    """Calculate a fraction with documented empty-class semantics."""
    return numerator / denominator if denominator else empty_value


def compare_masks(
    reference: npt.ArrayLike,
    candidate: npt.ArrayLike,
    *,
    valid_mask: npt.ArrayLike | None = None,
) -> MaskComparisonReport:
    """Compare two boolean masks over an optional valid pixel region."""
    reference_array, candidate_array = _as_same_shape_arrays(
        reference,
        candidate,
    )
    if not np.issubdtype(reference_array.dtype, np.bool_) or not np.issubdtype(
        candidate_array.dtype,
        np.bool_,
    ):
        raise TypeError("mask products must be boolean arrays")
    valid = _valid_region(reference_array.shape, valid_mask)
    reference_mask = np.asarray(reference_array, dtype=np.bool_)
    candidate_mask = np.asarray(candidate_array, dtype=np.bool_)

    true_positive = int(
        np.count_nonzero(valid & reference_mask & candidate_mask)
    )
    true_negative = int(
        np.count_nonzero(valid & ~reference_mask & ~candidate_mask)
    )
    false_positive = int(
        np.count_nonzero(valid & ~reference_mask & candidate_mask)
    )
    false_negative = int(
        np.count_nonzero(valid & reference_mask & ~candidate_mask)
    )
    compared = int(np.count_nonzero(valid))
    reference_positive = true_positive + false_negative
    candidate_positive = true_positive + false_positive
    return MaskComparisonReport(
        compared_pixel_count=compared,
        excluded_pixel_count=reference_mask.size - compared,
        true_positive_count=true_positive,
        true_negative_count=true_negative,
        false_positive_count=false_positive,
        false_negative_count=false_negative,
        agreement_fraction=_safe_classification_fraction(
            true_positive + true_negative,
            compared,
            empty_value=1.0,
        ),
        precision=_safe_classification_fraction(
            true_positive,
            candidate_positive,
            empty_value=1.0 if reference_positive == 0 else 0.0,
        ),
        recall=_safe_classification_fraction(
            true_positive,
            reference_positive,
            empty_value=1.0,
        ),
        intersection_over_union=_safe_classification_fraction(
            true_positive,
            true_positive + false_positive + false_negative,
            empty_value=1.0,
        ),
    )


def _as_island_labels(
    values: npt.NDArray[np.generic],
) -> npt.NDArray[np.integer[Any]]:
    """Require one two-dimensional non-negative integer label plane."""
    if values.ndim != _IMAGE_DIMENSIONS or np.issubdtype(
        values.dtype,
        np.bool_,
    ):
        raise TypeError("island labels must be two-dimensional integers")
    if not np.issubdtype(values.dtype, np.integer):
        raise TypeError("island labels must be two-dimensional integers")
    labels = cast(npt.NDArray[np.integer[Any]], values)
    if np.any(labels < 0):
        raise ValueError("island labels must be non-negative")
    return labels


def _positive_label_counts(
    labels: npt.NDArray[np.integer[Any]],
    valid: npt.NDArray[np.bool_],
) -> dict[int, int]:
    """Count each positive object label inside the selected valid region."""
    selected = labels[valid & (labels > 0)]
    unique, counts = np.unique(selected, return_counts=True)
    return {
        int(label): int(count)
        for label, count in zip(unique, counts, strict=True)
    }


def _label_intersections(
    reference: npt.NDArray[np.integer[Any]],
    candidate: npt.NDArray[np.integer[Any]],
    valid: npt.NDArray[np.bool_],
) -> dict[tuple[int, int], int]:
    """Count only positive reference/candidate overlap pairs."""
    selected = valid & (reference > 0) & (candidate > 0)
    if not np.any(selected):
        return {}
    pairs = np.column_stack((reference[selected], candidate[selected]))
    unique_pairs, counts = np.unique(pairs, axis=0, return_counts=True)
    return {
        (int(pair[0]), int(pair[1])): int(count)
        for pair, count in zip(unique_pairs, counts, strict=True)
    }


def _overlap_components(
    intersections: dict[tuple[int, int], int],
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    """Partition the sparse overlap graph into independent assignments."""
    reference_edges: dict[int, set[int]] = {}
    candidate_edges: dict[int, set[int]] = {}
    for reference_label, candidate_label in intersections:
        reference_edges.setdefault(reference_label, set()).add(candidate_label)
        candidate_edges.setdefault(candidate_label, set()).add(reference_label)

    components: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    remaining = set(reference_edges)
    while remaining:
        pending_reference = [min(remaining)]
        component_reference: set[int] = set()
        component_candidate: set[int] = set()
        while pending_reference:
            reference_label = pending_reference.pop()
            if reference_label in component_reference:
                continue
            component_reference.add(reference_label)
            remaining.discard(reference_label)
            for candidate_label in reference_edges[reference_label]:
                if candidate_label in component_candidate:
                    continue
                component_candidate.add(candidate_label)
                pending_reference.extend(candidate_edges[candidate_label])
        components.append(
            (
                tuple(sorted(component_reference)),
                tuple(sorted(component_candidate)),
            )
        )
    return tuple(components)


def _match_label_overlaps(
    intersections: dict[tuple[int, int], int],
    *,
    compared_pixel_count: int,
) -> tuple[tuple[int, int, int], ...]:
    """Maximize overlapping matches, then their total intersection."""
    matches: list[tuple[int, int, int]] = []
    cardinality_weight = compared_pixel_count + 1
    for reference_labels, candidate_labels in _overlap_components(
        intersections
    ):
        scores = np.zeros(
            (len(reference_labels), len(candidate_labels)),
            dtype=np.int64,
        )
        for reference_index, reference_label in enumerate(reference_labels):
            for candidate_index, candidate_label in enumerate(
                candidate_labels
            ):
                intersection = intersections.get(
                    (reference_label, candidate_label),
                    0,
                )
                if intersection:
                    scores[reference_index, candidate_index] = (
                        cardinality_weight + intersection
                    )
        reference_indices, candidate_indices = _linear_sum_assignment(
            np.asarray(scores, dtype=np.float64),
            maximize=True,
        )
        for reference_index, candidate_index in zip(
            reference_indices,
            candidate_indices,
            strict=True,
        ):
            intersection = intersections.get(
                (
                    reference_labels[int(reference_index)],
                    candidate_labels[int(candidate_index)],
                ),
                0,
            )
            if intersection:
                matches.append(
                    (
                        reference_labels[int(reference_index)],
                        candidate_labels[int(candidate_index)],
                        intersection,
                    )
                )
    return tuple(sorted(matches))


def compare_island_labels(
    reference: npt.ArrayLike,
    candidate: npt.ArrayLike,
    *,
    valid_mask: npt.ArrayLike | None = None,
) -> IslandComparisonReport:
    """Compare non-negative integer island labels by pixel overlap."""
    reference_array, candidate_array = _as_same_shape_arrays(
        reference,
        candidate,
    )
    reference_labels = _as_island_labels(reference_array)
    candidate_labels = _as_island_labels(candidate_array)
    valid = _valid_region(reference_array.shape, valid_mask)
    compared_pixel_count = int(np.count_nonzero(valid))
    reference_counts = _positive_label_counts(reference_labels, valid)
    candidate_counts = _positive_label_counts(candidate_labels, valid)
    intersections = _label_intersections(
        reference_labels,
        candidate_labels,
        valid,
    )
    assigned = _match_label_overlaps(
        intersections,
        compared_pixel_count=compared_pixel_count,
    )
    matches = tuple(
        IslandLabelMatch(
            reference_label=reference_label,
            candidate_label=candidate_label,
            intersection_pixel_count=intersection,
            union_pixel_count=(
                reference_counts[reference_label]
                + candidate_counts[candidate_label]
                - intersection
            ),
            intersection_over_union=(
                intersection
                / (
                    reference_counts[reference_label]
                    + candidate_counts[candidate_label]
                    - intersection
                )
            ),
        )
        for reference_label, candidate_label, intersection in assigned
    )
    matched_reference = {match.reference_label for match in matches}
    matched_candidate = {match.candidate_label for match in matches}
    reference_degrees: dict[int, int] = {}
    candidate_degrees: dict[int, int] = {}
    for reference_label, candidate_label in intersections:
        reference_degrees[reference_label] = (
            reference_degrees.get(reference_label, 0) + 1
        )
        candidate_degrees[candidate_label] = (
            candidate_degrees.get(candidate_label, 0) + 1
        )
    overlap_values = np.asarray(
        [match.intersection_over_union for match in matches],
        dtype=np.float64,
    )
    return IslandComparisonReport(
        compared_pixel_count=compared_pixel_count,
        excluded_pixel_count=reference_labels.size - compared_pixel_count,
        reference_count=len(reference_counts),
        candidate_count=len(candidate_counts),
        matches=matches,
        unmatched_reference_labels=tuple(
            sorted(set(reference_counts) - matched_reference)
        ),
        unmatched_candidate_labels=tuple(
            sorted(set(candidate_counts) - matched_candidate)
        ),
        split_reference_labels=tuple(
            sorted(
                label
                for label, degree in reference_degrees.items()
                if degree > 1
            )
        ),
        merged_candidate_labels=tuple(
            sorted(
                label
                for label, degree in candidate_degrees.items()
                if degree > 1
            )
        ),
        completeness=_safe_classification_fraction(
            len(matches),
            len(reference_counts),
            empty_value=1.0,
        ),
        reliability=_safe_classification_fraction(
            len(matches),
            len(candidate_counts),
            empty_value=1.0 if not reference_counts else 0.0,
        ),
        median_matched_intersection_over_union=_array_median(overlap_values),
        minimum_matched_intersection_over_union=(
            float(np.min(overlap_values)) if overlap_values.size else None
        ),
    )


def wilson_score_interval(
    successes: int,
    total: int,
    *,
    confidence_level: float = 0.95,
) -> BinomialConfidenceInterval | None:
    """Return a Wilson interval, or ``None`` for an empty population."""
    if (
        isinstance(successes, bool)
        or isinstance(total, bool)
        or successes < 0
        or total < 0
        or successes > total
    ):
        raise ValueError(
            "binomial counts must satisfy 0 <= successes <= total"
        )
    if not np.isfinite(confidence_level) or not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be finite and in (0, 1)")
    if total == 0:
        return None
    probability = successes / total
    z_score = NormalDist().inv_cdf(0.5 + confidence_level / 2.0)
    z_squared = z_score * z_score
    denominator = 1.0 + z_squared / total
    centre = probability + z_squared / (2.0 * total)
    radius = z_score * np.sqrt(
        probability * (1.0 - probability) / total
        + z_squared / (4.0 * total * total)
    )
    return BinomialConfidenceInterval(
        confidence_level=confidence_level,
        lower=float(max(0.0, (centre - radius) / denominator)),
        upper=float(min(1.0, (centre + radius) / denominator)),
    )


def aggregate_island_comparisons(
    reports: Sequence[IslandComparisonReport],
    *,
    confidence_level: float = 0.95,
) -> IslandPopulationReport:
    """Aggregate a generated or governed island-comparison matrix."""
    reference_count = sum(report.reference_count for report in reports)
    candidate_count = sum(report.candidate_count for report in reports)
    matched_count = sum(len(report.matches) for report in reports)
    overlaps = np.asarray(
        [
            match.intersection_over_union
            for report in reports
            for match in report.matches
        ],
        dtype=np.float64,
    )
    return IslandPopulationReport(
        case_count=len(reports),
        reference_count=reference_count,
        candidate_count=candidate_count,
        matched_count=matched_count,
        completeness=_safe_classification_fraction(
            matched_count,
            reference_count,
            empty_value=1.0,
        ),
        reliability=_safe_classification_fraction(
            matched_count,
            candidate_count,
            empty_value=1.0 if not reference_count else 0.0,
        ),
        completeness_confidence_interval=wilson_score_interval(
            matched_count,
            reference_count,
            confidence_level=confidence_level,
        ),
        reliability_confidence_interval=wilson_score_interval(
            matched_count,
            candidate_count,
            confidence_level=confidence_level,
        ),
        split_count=sum(
            len(report.split_reference_labels) for report in reports
        ),
        merge_count=sum(
            len(report.merged_candidate_labels) for report in reports
        ),
        median_matched_intersection_over_union=_array_median(overlaps),
        minimum_matched_intersection_over_union=(
            float(np.min(overlaps)) if overlaps.size else None
        ),
    )


def _array_median(values: npt.NDArray[np.float64]) -> float | None:
    """Return an array median with an explicit empty result."""
    if values.size == 0:
        return None
    return float(np.median(values))


def _array_percentile_95(
    values: npt.NDArray[np.float64],
) -> float | None:
    """Return an array 95th percentile with an explicit empty result."""
    if values.size == 0:
        return None
    return float(np.percentile(values, 95.0))


def compare_rms_maps(
    reference_rms_jy_per_beam: npt.ArrayLike,
    candidate_rms_jy_per_beam: npt.ArrayLike,
    *,
    valid_mask: npt.ArrayLike | None = None,
) -> RmsComparisonReport:
    """Compare non-negative RMS maps over finite, optionally masked pixels."""
    reference_input, candidate_input = _as_same_shape_arrays(
        reference_rms_jy_per_beam,
        candidate_rms_jy_per_beam,
    )
    reference = np.asarray(reference_input, dtype=np.float64)
    candidate = np.asarray(candidate_input, dtype=np.float64)
    selected = _valid_region(reference.shape, valid_mask)
    if np.any(selected & np.isfinite(reference) & (reference < 0)) or np.any(
        selected & np.isfinite(candidate) & (candidate < 0)
    ):
        raise ValueError("finite RMS values must be non-negative")

    comparable = selected & np.isfinite(reference) & np.isfinite(candidate)
    absolute_differences = np.asarray(
        np.abs(candidate[comparable] - reference[comparable]),
        dtype=np.float64,
    )
    positive_reference = comparable & (reference > 0)
    relative_differences = np.asarray(
        np.abs(
            (candidate[positive_reference] - reference[positive_reference])
            / reference[positive_reference]
        ),
        dtype=np.float64,
    )
    compared_count = int(np.count_nonzero(comparable))
    relative_count = int(np.count_nonzero(positive_reference))
    zero_reference_count = int(np.count_nonzero(comparable & (reference == 0)))
    return RmsComparisonReport(
        compared_pixel_count=compared_count,
        relative_pixel_count=relative_count,
        excluded_pixel_count=reference.size - compared_count,
        zero_reference_pixel_count=zero_reference_count,
        median_absolute_difference_jy_per_beam=_array_median(
            absolute_differences
        ),
        percentile_95_absolute_difference_jy_per_beam=(
            _array_percentile_95(absolute_differences)
        ),
        median_absolute_fractional_difference=_array_median(
            relative_differences
        ),
        percentile_95_absolute_fractional_difference=(
            _array_percentile_95(relative_differences)
        ),
    )
