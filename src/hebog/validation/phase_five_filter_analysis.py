"""Frozen endpoint analysis for the Phase 5 Step 2B filter review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, cast

import numpy as np
import numpy.typing as npt

from hebog.algorithms.multiscale import FilterFamily
from hebog.validation.contracts import (
    PhaseFiveCorrectiveReview,
    PhaseFiveFilterReview,
)
from hebog.validation.datasets import DatasetRecord
from hebog.validation.evidence import (
    PhaseFiveFilterReviewCandidateConclusion,
    PhaseFiveFilterReviewEndpointEvidence,
    PhaseFiveFilterReviewPairedEndpointEvidence,
)
from hebog.validation.phase_five_filter_review import (
    AnalyticFilterObservation,
    GeneratedGroupObservation,
    GeneratedImageObservation,
)

_Statistic = Literal["fraction", "maximum", "mean", "median", "percentile-95"]
_Direction = Literal["maximum", "minimum"]
_ReviewContract = PhaseFiveFilterReview | PhaseFiveCorrectiveReview


@dataclass(frozen=True, slots=True)
class CompiledFilterReview:
    """All endpoint decisions and the resulting fail-closed candidates."""

    endpoints: tuple[PhaseFiveFilterReviewEndpointEvidence, ...]
    paired_endpoints: tuple[PhaseFiveFilterReviewPairedEndpointEvidence, ...]
    candidates: tuple[PhaseFiveFilterReviewCandidateConclusion, ...]


@dataclass(frozen=True, slots=True)
class FilterReviewObservations:
    """Paired analytic, development, and regression observations."""

    analytic: tuple[AnalyticFilterObservation, ...]
    development: tuple[GeneratedImageObservation, ...]
    regression: tuple[GeneratedImageObservation, ...]


@dataclass(frozen=True, slots=True)
class FilterReviewDatasets:
    """Distinct governed populations used by the paired review."""

    development: DatasetRecord
    regression: DatasetRecord


@dataclass(frozen=True, slots=True)
class _EndpointSpec:
    """Definition of one absolute or diagnostic endpoint."""

    metric: str
    statistic: _Statistic
    limit: float | None
    direction: _Direction | None


@dataclass(frozen=True, slots=True)
class _PairedSpec:
    """Definition of one candidate-to-candidate endpoint."""

    metric: str
    statistic: Literal["fraction", "mean", "median", "percentile-95"]
    margin: float
    higher_is_better: bool
    fractional: bool


@dataclass(frozen=True, slots=True)
class _PairedSeries:
    """One candidate and reference pair of aligned metric values."""

    family: FilterFamily
    reference_family: FilterFamily
    candidate: npt.NDArray[np.float64]
    reference: npt.NDArray[np.float64]


def _families(
    review: _ReviewContract,
) -> tuple[FilterFamily, FilterFamily]:
    """Return the contract-validated canonical candidate pair."""
    return cast(tuple[FilterFamily, FilterFamily], review.candidates)


def _statistic(values: npt.NDArray[np.float64], name: _Statistic) -> float:
    """Evaluate one frozen scalar summary over finite image-level values."""
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError("filter-review endpoint values must be finite")
    if name in {"fraction", "mean"}:
        return float(np.mean(values))
    if name == "maximum":
        return float(np.max(values))
    if name == "median":
        return float(np.median(values))
    return float(np.percentile(values, 95))


def _endpoint(
    *,
    population: Literal["analytic", "development", "regression"],
    stratum: str,
    family: FilterFamily,
    values: npt.NDArray[np.float64],
    spec: _EndpointSpec,
) -> PhaseFiveFilterReviewEndpointEvidence:
    """Build one derivable absolute or diagnostic endpoint."""
    estimate = _statistic(values, spec.statistic)
    passed = None
    if spec.limit is not None and spec.direction is not None:
        passed = (
            estimate <= spec.limit
            if spec.direction == "maximum"
            else estimate >= spec.limit
        )
    return PhaseFiveFilterReviewEndpointEvidence(
        metric=spec.metric,
        population=population,
        stratum=stratum,
        statistic=spec.statistic,
        family=family,
        sample_count=int(values.size),
        estimate=estimate,
        absolute_limit=spec.limit,
        absolute_direction=spec.direction,
        passed=passed,
    )


def _paired_regression(
    candidate: npt.NDArray[np.float64],
    reference: npt.NDArray[np.float64],
    *,
    spec: _PairedSpec,
    resamples: int,
    seed: int,
) -> tuple[float, float]:
    """Return a paired regression estimate and one-sided percentile limit."""
    if candidate.shape != reference.shape or candidate.ndim != 1:
        raise ValueError("paired filter-review arrays must be aligned vectors")
    if candidate.size == 0:
        raise ValueError("paired filter-review arrays must not be empty")

    def regression(
        candidate_values: npt.NDArray[np.float64],
        reference_values: npt.NDArray[np.float64],
    ) -> float:
        candidate_statistic = _statistic(candidate_values, spec.statistic)
        reference_statistic = _statistic(reference_values, spec.statistic)
        difference = (
            reference_statistic - candidate_statistic
            if spec.higher_is_better
            else candidate_statistic - reference_statistic
        )
        if not spec.fractional:
            return difference
        denominator = abs(reference_statistic)
        if denominator == 0:
            raise ValueError("fractional paired endpoint has zero reference")
        return difference / denominator

    estimate = regression(candidate, reference)
    random = np.random.default_rng(seed)
    bootstrap = np.empty(resamples, dtype=np.float64)
    chunk_size = 1_000
    for start in range(0, resamples, chunk_size):
        stop = min(start + chunk_size, resamples)
        indices = random.integers(
            0,
            candidate.size,
            size=(stop - start, candidate.size),
        )
        for offset, sampled_indices in enumerate(indices):
            bootstrap[start + offset] = regression(
                candidate[sampled_indices],
                reference[sampled_indices],
            )
    return estimate, float(np.percentile(bootstrap, 95))


def _paired_endpoint(
    *,
    population: Literal["analytic", "regression"],
    stratum: str,
    series: _PairedSeries,
    spec: _PairedSpec,
    review: _ReviewContract,
) -> PhaseFiveFilterReviewPairedEndpointEvidence:
    """Build one exact analytic or bootstrapped generated comparison."""
    if population == "analytic":
        candidate_statistic = _statistic(series.candidate, spec.statistic)
        reference_statistic = _statistic(series.reference, spec.statistic)
        estimate = (
            reference_statistic - candidate_statistic
            if spec.higher_is_better
            else candidate_statistic - reference_statistic
        )
        if spec.fractional:
            estimate /= abs(reference_statistic)
        upper = estimate
    else:
        estimate, upper = _paired_regression(
            series.candidate,
            series.reference,
            spec=spec,
            resamples=review.statistical_design.bootstrap_resamples,
            seed=review.statistical_design.bootstrap_seed,
        )
    return PhaseFiveFilterReviewPairedEndpointEvidence(
        metric=spec.metric,
        population=population,
        stratum=stratum,
        statistic=spec.statistic,
        family=series.family,
        reference_family=series.reference_family,
        sample_count=int(series.candidate.size),
        estimate_difference=estimate,
        upper_confidence_limit=upper,
        margin=spec.margin,
        passed=upper <= spec.margin,
    )


def _analytic_strata(
    observations: tuple[AnalyticFilterObservation, ...],
) -> tuple[tuple[str, Callable[[AnalyticFilterObservation], bool]], ...]:
    """Return overall and all governed exact analytic strata."""
    scales = sorted({item.scale_order for item in observations})
    geometries = sorted({item.geometry for item in observations})
    snrs = sorted({item.input_peak_snr for item in observations})
    strata: list[tuple[str, Callable[[AnalyticFilterObservation], bool]]] = [
        ("overall", lambda _item: True)
    ]
    strata.extend(
        (f"scale-{scale}", lambda item, scale=scale: item.scale_order == scale)
        for scale in scales
    )
    strata.extend(
        (
            f"geometry-{geometry}",
            lambda item, geometry=geometry: item.geometry == geometry,
        )
        for geometry in geometries
    )
    strata.extend(
        (
            f"snr-{snr:g}",
            lambda item, snr=snr: item.input_peak_snr == snr,
        )
        for snr in snrs
    )
    strata.extend(
        (
            f"scale-{scale}/geometry-{geometry}/snr-{snr:g}",
            lambda item, scale=scale, geometry=geometry, snr=snr: (
                item.scale_order == scale
                and item.geometry == geometry
                and item.input_peak_snr == snr
            ),
        )
        for scale in scales
        for geometry in geometries
        for snr in snrs
    )
    return tuple(strata)


def _analytic_values(
    rows: tuple[AnalyticFilterObservation, ...],
    attribute: str,
) -> npt.NDArray[np.float64]:
    """Extract a complete finite analytic endpoint vector."""
    values = [getattr(item, attribute) for item in rows]
    if any(value is None for value in values):
        raise ValueError(f"analytic endpoint {attribute} is unavailable")
    return np.asarray(values, dtype=np.float64)


def _compile_analytic(
    observations: tuple[AnalyticFilterObservation, ...],
    review: _ReviewContract,
) -> tuple[
    tuple[PhaseFiveFilterReviewEndpointEvidence, ...],
    tuple[PhaseFiveFilterReviewPairedEndpointEvidence, ...],
]:
    """Compile exact analytic absolute and paired decisions."""
    gates = review.absolute_gates
    margins = review.paired_margins
    endpoints: list[PhaseFiveFilterReviewEndpointEvidence] = []
    paired: list[PhaseFiveFilterReviewPairedEndpointEvidence] = []
    for stratum, predicate in _analytic_strata(observations):
        by_family: dict[
            FilterFamily, tuple[AnalyticFilterObservation, ...]
        ] = {
            family: tuple(
                item
                for item in observations
                if item.family == family and predicate(item)
            )
            for family in _families(review)
        }
        for family, rows in by_family.items():
            response = _analytic_values(rows, "response_fractional_error")
            flux = _analytic_values(rows, "integrated_flux_fractional_error")
            position = _analytic_values(rows, "position_error_beams")
            snr = _analytic_values(rows, "calibrated_response_snr")
            support = np.asarray(
                [float(item.available) for item in rows], dtype=np.float64
            )
            negative_lobe = _analytic_values(rows, "negative_lobe_fraction")
            endpoint_specs = (
                (
                    _EndpointSpec(
                        "response-fractional-error",
                        "median",
                        gates.maximum_median_response_fractional_error,
                        "maximum",
                    ),
                    response,
                ),
                (
                    _EndpointSpec(
                        "response-fractional-error",
                        "percentile-95",
                        gates.maximum_percentile_95_response_fractional_error,
                        "maximum",
                    ),
                    response,
                ),
                (
                    _EndpointSpec(
                        "integrated-flux-fractional-error",
                        "median",
                        gates.maximum_median_integrated_flux_fractional_error,
                        "maximum",
                    ),
                    flux,
                ),
                (
                    _EndpointSpec(
                        "integrated-flux-fractional-error",
                        "percentile-95",
                        gates.maximum_percentile_95_integrated_flux_fractional_error,
                        "maximum",
                    ),
                    flux,
                ),
                (
                    _EndpointSpec(
                        "position-error-beams",
                        "percentile-95",
                        gates.maximum_percentile_95_position_beams,
                        "maximum",
                    ),
                    position,
                ),
                (
                    _EndpointSpec(
                        "support-availability",
                        "fraction",
                        gates.minimum_support_availability,
                        "minimum",
                    ),
                    support,
                ),
                (
                    _EndpointSpec(
                        "calibrated-response-snr", "median", None, None
                    ),
                    snr,
                ),
                (
                    _EndpointSpec(
                        "negative-lobe-depth",
                        "percentile-95",
                        None,
                        None,
                    ),
                    negative_lobe,
                ),
            )
            endpoints.extend(
                _endpoint(
                    population="analytic",
                    stratum=stratum,
                    family=family,
                    values=values,
                    spec=spec,
                )
                for spec, values in endpoint_specs
            )
        for family in _families(review):
            reference_family = cast(
                FilterFamily,
                next(item for item in _families(review) if item != family),
            )
            candidate_rows = by_family[family]
            reference_rows = by_family[reference_family]
            paired_specs = (
                (
                    _PairedSpec(
                        "response-fractional-error",
                        "median",
                        margins.maximum_median_response_error_increase,
                        False,
                        False,
                    ),
                    "response_fractional_error",
                ),
                (
                    _PairedSpec(
                        "response-fractional-error",
                        "percentile-95",
                        margins.maximum_percentile_95_response_error_increase,
                        False,
                        False,
                    ),
                    "response_fractional_error",
                ),
                (
                    _PairedSpec(
                        "integrated-flux-fractional-error",
                        "median",
                        margins.maximum_median_integrated_flux_error_increase,
                        False,
                        False,
                    ),
                    "integrated_flux_fractional_error",
                ),
                (
                    _PairedSpec(
                        "calibrated-response-snr",
                        "median",
                        margins.maximum_calibrated_snr_fractional_loss,
                        True,
                        True,
                    ),
                    "calibrated_response_snr",
                ),
                (
                    _PairedSpec(
                        "position-error-beams",
                        "percentile-95",
                        margins.maximum_position_error_increase_beams,
                        False,
                        False,
                    ),
                    "position_error_beams",
                ),
            )
            paired.extend(
                _paired_endpoint(
                    population="analytic",
                    stratum=stratum,
                    series=_PairedSeries(
                        family,
                        reference_family,
                        _analytic_values(candidate_rows, attribute),
                        _analytic_values(reference_rows, attribute),
                    ),
                    spec=spec,
                    review=review,
                )
                for spec, attribute in paired_specs
            )
    return tuple(endpoints), tuple(paired)


def _group_strata(
    dataset: DatasetRecord,
) -> tuple[tuple[str, frozenset[str]], ...]:
    """Return the overall group population and declared manifest strata."""
    all_groups = frozenset(
        item.identifier for item in dataset.multiscale_truth_groups
    )
    return (
        ("overall", all_groups),
        *(
            (item.identifier, frozenset(item.group_identifiers))
            for item in dataset.multiscale_group_strata
        ),
    )


def _group_image_values(
    observations: tuple[GeneratedImageObservation, ...],
    group_identifiers: frozenset[str],
    function: Callable[[tuple[GeneratedGroupObservation, ...]], float],
) -> npt.NDArray[np.float64]:
    """Reduce governed groups to one aligned scalar per generated image."""
    values: list[float] = []
    for observation in sorted(observations, key=lambda item: item.seed):
        groups = tuple(
            item
            for item in observation.groups
            if item.group_identifier in group_identifiers
        )
        if not groups:
            raise ValueError("generated filter-review stratum is empty")
        values.append(function(groups))
    return np.asarray(values, dtype=np.float64)


def _available_group_values(
    groups: tuple[GeneratedGroupObservation, ...], attribute: str
) -> npt.NDArray[np.float64]:
    """Extract a complete group metric, failing closed on missing values."""
    values = [cast(float | None, getattr(item, attribute)) for item in groups]
    if any(value is None for value in values):
        raise ValueError(f"generated endpoint {attribute} is unavailable")
    return np.asarray(values, dtype=np.float64)


def _generated_group_series(
    observations: tuple[GeneratedImageObservation, ...],
    groups: frozenset[str],
) -> dict[str, npt.NDArray[np.float64]]:
    """Return every group-level endpoint as paired image summaries."""
    return {
        "completeness": _group_image_values(
            observations,
            groups,
            lambda rows: float(np.mean([item.detected for item in rows])),
        ),
        "integrated-flux-fractional-error": _group_image_values(
            observations,
            groups,
            lambda rows: float(
                np.median(
                    _available_group_values(
                        rows, "integrated_flux_fractional_error"
                    )
                )
            ),
        ),
        "calibrated-response-snr": _group_image_values(
            observations,
            groups,
            lambda rows: float(np.median([item.maximum_snr for item in rows])),
        ),
        "position-error-beams": _group_image_values(
            observations,
            groups,
            lambda rows: float(
                np.percentile(
                    _available_group_values(rows, "position_error_beams"), 95
                )
            ),
        ),
        "support-availability": _group_image_values(
            observations,
            groups,
            lambda rows: float(
                np.mean([item.support_available for item in rows])
            ),
        ),
        "fragmentation-fraction": _group_image_values(
            observations,
            groups,
            lambda rows: float(
                np.mean([item.fragment_count > 1 for item in rows])
            ),
        ),
    }


def _generated_image_series(
    observations: tuple[GeneratedImageObservation, ...],
) -> dict[str, npt.NDArray[np.float64]]:
    """Return aligned whole-image endpoint vectors."""
    ordered = sorted(observations, key=lambda item: item.seed)
    return {
        "reliability": np.asarray([item.reliability for item in ordered]),
        "mask-intersection-over-union": np.asarray(
            [item.mask_intersection_over_union for item in ordered]
        ),
        "noise-standard-deviation-error": np.asarray(
            [item.noise_std_fractional_error for item in ordered]
        ),
    }


def _compile_generated_population(
    observations: tuple[GeneratedImageObservation, ...],
    dataset: DatasetRecord,
    review: _ReviewContract,
    *,
    population: Literal["development", "regression"],
) -> tuple[
    tuple[PhaseFiveFilterReviewEndpointEvidence, ...],
    tuple[PhaseFiveFilterReviewPairedEndpointEvidence, ...],
]:
    """Compile candidate-neutral generated-image endpoint summaries."""
    gates = review.absolute_gates
    margins = review.paired_margins
    binding = population == "regression"
    by_family: dict[FilterFamily, tuple[GeneratedImageObservation, ...]] = {
        family: tuple(item for item in observations if item.family == family)
        for family in _families(review)
    }
    endpoints: list[PhaseFiveFilterReviewEndpointEvidence] = []
    paired: list[PhaseFiveFilterReviewPairedEndpointEvidence] = []
    for stratum, groups in _group_strata(dataset):
        series = {
            family: _generated_group_series(rows, groups)
            for family, rows in by_family.items()
        }
        specs = (
            _EndpointSpec(
                "completeness",
                "mean",
                gates.minimum_completeness,
                "minimum",
            ),
            _EndpointSpec(
                "integrated-flux-fractional-error",
                "median",
                gates.maximum_median_integrated_flux_fractional_error,
                "maximum",
            ),
            _EndpointSpec(
                "integrated-flux-fractional-error",
                "percentile-95",
                gates.maximum_percentile_95_integrated_flux_fractional_error,
                "maximum",
            ),
            _EndpointSpec("calibrated-response-snr", "median", None, None),
            _EndpointSpec(
                "position-error-beams",
                "percentile-95",
                gates.maximum_percentile_95_position_beams,
                "maximum",
            ),
            _EndpointSpec(
                "support-availability",
                "mean",
                gates.minimum_support_availability,
                "minimum",
            ),
            _EndpointSpec(
                "fragmentation-fraction",
                "mean",
                gates.maximum_fragmentation_fraction,
                "maximum",
            ),
        )
        for family in _families(review):
            endpoints.extend(
                _endpoint(
                    population=population,
                    stratum=stratum,
                    family=family,
                    values=series[family][spec.metric],
                    spec=spec
                    if binding
                    else _EndpointSpec(
                        spec.metric, spec.statistic, None, None
                    ),
                )
                for spec in specs
            )
        if binding:
            paired_specs = (
                _PairedSpec(
                    "completeness",
                    "mean",
                    margins.maximum_completeness_loss,
                    True,
                    False,
                ),
                _PairedSpec(
                    "integrated-flux-fractional-error",
                    "median",
                    margins.maximum_median_integrated_flux_error_increase,
                    False,
                    False,
                ),
                _PairedSpec(
                    "calibrated-response-snr",
                    "median",
                    margins.maximum_calibrated_snr_fractional_loss,
                    True,
                    True,
                ),
                _PairedSpec(
                    "position-error-beams",
                    "percentile-95",
                    margins.maximum_position_error_increase_beams,
                    False,
                    False,
                ),
                _PairedSpec(
                    "fragmentation-fraction",
                    "mean",
                    margins.maximum_fragmentation_fraction_increase,
                    False,
                    False,
                ),
            )
            for family in _families(review):
                reference_family = cast(
                    FilterFamily,
                    next(item for item in _families(review) if item != family),
                )
                paired.extend(
                    _paired_endpoint(
                        population="regression",
                        stratum=stratum,
                        series=_PairedSeries(
                            family,
                            reference_family,
                            series[family][spec.metric],
                            series[reference_family][spec.metric],
                        ),
                        spec=spec,
                        review=review,
                    )
                    for spec in paired_specs
                )

    image_series = {
        family: _generated_image_series(rows)
        for family, rows in by_family.items()
    }
    image_specs = (
        _EndpointSpec(
            "reliability", "mean", gates.minimum_reliability, "minimum"
        ),
        _EndpointSpec(
            "mask-intersection-over-union",
            "mean",
            gates.minimum_mask_intersection_over_union,
            "minimum",
        ),
        _EndpointSpec(
            "noise-standard-deviation-error",
            "maximum",
            gates.maximum_noise_std_fractional_error,
            "maximum",
        ),
    )
    for family in _families(review):
        endpoints.extend(
            _endpoint(
                population=population,
                stratum="overall",
                family=family,
                values=image_series[family][spec.metric],
                spec=spec
                if binding
                else _EndpointSpec(spec.metric, spec.statistic, None, None),
            )
            for spec in image_specs
        )
    if binding:
        image_paired_specs = (
            _PairedSpec(
                "reliability",
                "mean",
                margins.maximum_reliability_loss,
                True,
                False,
            ),
            _PairedSpec(
                "mask-intersection-over-union",
                "mean",
                margins.maximum_mask_intersection_over_union_loss,
                True,
                False,
            ),
            _PairedSpec(
                "noise-standard-deviation-error",
                "median",
                margins.maximum_noise_std_error_increase,
                False,
                False,
            ),
        )
        for family in _families(review):
            reference_family = cast(
                FilterFamily,
                next(item for item in _families(review) if item != family),
            )
            paired.extend(
                _paired_endpoint(
                    population="regression",
                    stratum="overall",
                    series=_PairedSeries(
                        family,
                        reference_family,
                        image_series[family][spec.metric],
                        image_series[reference_family][spec.metric],
                    ),
                    spec=spec,
                    review=review,
                )
                for spec in image_paired_specs
            )
    return tuple(endpoints), tuple(paired)


def compile_filter_review(
    observations: FilterReviewObservations,
    datasets: FilterReviewDatasets,
    review: _ReviewContract,
    *,
    bounded_costs: dict[FilterFamily, tuple[int, int, int]],
) -> CompiledFilterReview:
    """Apply every frozen absolute and paired rule without compensation."""
    analytic_endpoints, analytic_paired = _compile_analytic(
        observations.analytic, review
    )
    development_endpoints, _ = _compile_generated_population(
        observations.development,
        datasets.development,
        review,
        population="development",
    )
    regression_endpoints, regression_paired = _compile_generated_population(
        observations.regression,
        datasets.regression,
        review,
        population="regression",
    )
    endpoints = (
        *analytic_endpoints,
        *development_endpoints,
        *regression_endpoints,
    )
    paired = (*analytic_paired, *regression_paired)
    candidates = tuple(
        PhaseFiveFilterReviewCandidateConclusion(
            family=family,
            passes_absolute=not any(
                item.family == family and item.passed is False
                for item in endpoints
            ),
            noninferior_to_other=not any(
                item.family == family and not item.passed for item in paired
            ),
            bounded_cost=bounded_costs[family],
            failed_absolute_endpoint_count=sum(
                item.family == family and item.passed is False
                for item in endpoints
            ),
            failed_paired_endpoint_count=sum(
                item.family == family and not item.passed for item in paired
            ),
        )
        for family in _families(review)
    )
    return CompiledFilterReview(
        endpoints=tuple(endpoints),
        paired_endpoints=tuple(paired),
        candidates=candidates,
    )
