# pyright: reportMissingTypeStubs=false
"""Independent scientific comparison reports for Phase 0 validation.

Catalogue matching uses canonical degrees and janskys. It maximizes the number
of valid matches, then total matched integrated flux, then angular proximity.
Array reports never broadcast inputs and state how many pixels were excluded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, Self, cast

import numpy as np
import numpy.typing as npt
from scipy.optimize import (
    linear_sum_assignment as _lsa,  # pyright: ignore[reportUnknownVariableType]
)

_MINIMUM_DECLINATION_DEGREES = -90.0
_MAXIMUM_DECLINATION_DEGREES = 90.0
_FULL_CIRCLE_DEGREES = 360.0


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


@dataclass(frozen=True, slots=True)
class CatalogueSource:
    """One source in the comparison oracle's canonical units."""

    identifier: str
    right_ascension_degrees: float
    declination_degrees: float
    peak_flux_jy_per_beam: float
    integrated_flux_jy: float

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


def compare_catalogues(
    reference: Sequence[CatalogueSource],
    candidate: Sequence[CatalogueSource],
    *,
    beam_fwhm_degrees: float,
    maximum_separation_beams: float,
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
    matched_reference_indices: set[int] = set()
    matched_candidate_indices: set[int] = set()
    for reference_index, candidate_index, separation_beams in assignments:
        reference_source = reference[reference_index]
        candidate_source = candidate[candidate_index]
        matched_reference_indices.add(reference_index)
        matched_candidate_indices.add(candidate_index)
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
            )
        )

    separations = [match.separation_beam_fwhm for match in matches]
    peak_flux_differences = [
        abs(match.peak_flux_fractional_difference) for match in matches
    ]
    integrated_flux_differences = [
        abs(match.integrated_flux_fractional_difference) for match in matches
    ]
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
