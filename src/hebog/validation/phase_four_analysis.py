"""Shared aggregate statistics for Phase 4 paired campaigns.

The planning audit and final evaluator use these functions so the endpoint
population and sign conventions cannot drift between design and decision.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import TypeAlias

import numpy as np
import numpy.typing as npt

from hebog.validation.contracts import (
    PairedBinaryEndpoint,
    PairedContinuousEndpoint,
)
from hebog.validation.datasets import DatasetRecord
from hebog.validation.evidence import CampaignRealizationDiagnostic

POSITION_FLUX_METRICS = frozenset(
    {"right-ascension", "declination", "peak-flux", "integrated-flux"}
)
BINARY_ENDPOINT_IDS = frozenset(
    {
        "compact-completeness",
        "catalogue-reliability",
        "association-pair-precision",
        "association-pair-recall",
        "fitted-shape-availability",
        "deconvolution-classification-availability",
        "resolved-deconvolved-shape-availability",
        "association-identity-availability",
        "position-flux-uncertainty-availability",
        "point-source-specificity",
        "clear-resolved-classification-recall",
        "catastrophic-outlier-fraction",
        "unresolved-group-completeness",
    }
)
GROUP_ENDPOINT_IDS = frozenset(
    {
        "unresolved-group-median-position",
        "unresolved-group-position-tail",
        "unresolved-group-median-total-flux",
        "unresolved-group-total-flux-tail",
    }
)
UNCERTAINTY_ENDPOINT_IDS = frozenset(
    {
        "uncertainty-normalized-bias",
        "uncertainty-one-sigma-coverage",
        "uncertainty-normalized-dispersion",
    }
)
PAIRED_ENDPOINT_IDS = (
    BINARY_ENDPOINT_IDS | GROUP_ENDPOINT_IDS | UNCERTAINTY_ENDPOINT_IDS
)

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
CountArrays = dict[str, FloatArray]
UncertaintyArrays = FloatArray
PairedEndpoint: TypeAlias = PairedBinaryEndpoint | PairedContinuousEndpoint


def truth_sets(
    dataset: DatasetRecord,
) -> tuple[set[str], set[str], set[str], set[str], set[str]]:
    """Return group, individual, point, clear, and blend identifiers."""
    all_groups = {item.identifier for item in dataset.association_truth_groups}
    individual_by_source_index = {
        item.source_indices[0]: item.identifier
        for item in dataset.association_truth_groups
        if item.resolution_class == "individually-resolvable"
    }
    individual = set(individual_by_source_index.values())
    classifications = {
        item.identifier: {
            individual_by_source_index[index]
            for index in item.source_indices
            if index in individual_by_source_index
        }
        for item in dataset.classification_strata
    }
    try:
        point = classifications["shape-unresolved"]
        clear = classifications["shape-clear-resolved"]
    except KeyError as error:
        raise ValueError(
            "Phase 4 dataset lacks a governed classification stratum"
        ) from error
    blend = all_groups - individual
    return all_groups, individual, point, clear, blend


def count_row(
    realization: CampaignRealizationDiagnostic,
    dataset: DatasetRecord,
) -> dict[str, tuple[float, float]]:
    """Return binary numerators and denominators for one complete image."""
    all_groups, individual, point, clear, blend = truth_sets(dataset)
    association_matches = {
        item.truth_group_identifier
        for item in realization.association_pairs
        if item.decision == "matched"
    }
    source_by_truth = {
        item.truth_identifier: item
        for item in realization.source_pairs
        if item.truth_identifier is not None
    }
    matched_individual = tuple(
        item
        for identifier, item in source_by_truth.items()
        if identifier in individual and item.decision == "matched"
    )

    def classified_as(
        identifiers: set[str],
        expected_statuses: frozenset[str],
    ) -> int:
        return sum(
            source_by_truth.get(identifier) is not None
            and source_by_truth[identifier].decision == "matched"
            and source_by_truth[identifier].candidate_deconvolution_status
            in expected_statuses
            for identifier in identifiers
        )

    return {
        "compact-completeness": (
            float(len(association_matches & all_groups)),
            float(len(all_groups)),
        ),
        "catalogue-reliability": (
            float(len(association_matches)),
            float(realization.candidate_count or 0),
        ),
        "association-pair-precision": (
            float(len(association_matches)),
            float(realization.candidate_count or 0),
        ),
        "association-pair-recall": (
            float(len(association_matches & all_groups)),
            float(len(all_groups)),
        ),
        "fitted-shape-availability": (
            float(
                sum(
                    item.maximum_absolute_fitted_axis_fractional_difference
                    is not None
                    for item in matched_individual
                )
            ),
            float(len(individual)),
        ),
        "deconvolution-classification-availability": (
            float(
                sum(
                    item.candidate_deconvolution_status is not None
                    for item in matched_individual
                )
            ),
            float(len(individual)),
        ),
        "resolved-deconvolved-shape-availability": (
            float(
                sum(
                    source_by_truth.get(identifier) is not None
                    and source_by_truth[identifier].decision == "matched"
                    and source_by_truth[
                        identifier
                    ].maximum_absolute_deconvolved_axis_fractional_difference
                    is not None
                    for identifier in clear
                )
            ),
            float(len(clear)),
        ),
        "association-identity-availability": (
            float(len(matched_individual)),
            float(len(individual)),
        ),
        "position-flux-uncertainty-availability": (
            float(
                sum(
                    POSITION_FLUX_METRICS.issubset(
                        {
                            residual.metric
                            for residual in item.normalized_residuals
                        }
                    )
                    for item in matched_individual
                )
            ),
            float(len(individual)),
        ),
        "point-source-specificity": (
            float(classified_as(point, frozenset({"unresolved"}))),
            float(len(point)),
        ),
        "clear-resolved-classification-recall": (
            float(
                classified_as(
                    clear,
                    frozenset({"resolved", "major-axis-only"}),
                )
            ),
            float(len(clear)),
        ),
        "catastrophic-outlier-fraction": (
            float(
                sum(
                    item.gated_catastrophic is True
                    for item in matched_individual
                )
            ),
            float(len(matched_individual)),
        ),
        "unresolved-group-completeness": (
            float(len(association_matches & blend)),
            float(len(blend)),
        ),
    }


def count_arrays(
    realizations: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
) -> CountArrays:
    """Stack binary counts with numerator and denominator columns."""
    rows = [count_row(item, dataset) for item in realizations]
    return {
        endpoint_id: np.asarray(
            [row[endpoint_id] for row in rows], dtype=np.float64
        )
        for endpoint_id in BINARY_ENDPOINT_IDS
    }


def blend_arrays(
    realizations: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
) -> dict[str, FloatArray]:
    """Return conditional per-image unresolved-group error arrays.

    An unmatched group is represented by ``NaN`` here and by a failure in the
    separate unresolved-group completeness endpoint. Retained error metrics
    therefore remain calculable without hiding the missing group.
    """
    blend_ids = tuple(
        item.identifier
        for item in dataset.association_truth_groups
        if item.resolution_class == "unresolved-blend"
    )
    position: list[list[float]] = []
    flux: list[list[float]] = []
    for realization in realizations:
        by_truth = {
            item.truth_group_identifier: item
            for item in realization.association_pairs
            if item.truth_group_identifier is not None
        }
        position_row: list[float] = []
        flux_row: list[float] = []
        for identifier in blend_ids:
            item = by_truth.get(identifier)
            if (
                item is None
                or item.decision != "matched"
                or item.separation_beam_fwhm is None
                or item.integrated_flux_fractional_difference is None
            ):
                position_row.append(np.nan)
                flux_row.append(np.nan)
            else:
                position_row.append(abs(item.separation_beam_fwhm))
                flux_row.append(
                    abs(item.integrated_flux_fractional_difference)
                )
        position.append(position_row)
        flux.append(flux_row)
    return {
        "position": np.asarray(position, dtype=np.float64),
        "total-flux": np.asarray(flux, dtype=np.float64),
    }


def uncertainty_arrays(
    realizations: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
) -> UncertaintyArrays:
    """Return conditional per-image uncertainty sufficient statistics.

    Missing matches and unavailable residuals remain represented by the
    separate completeness and uncertainty-availability endpoints. They do not
    erase calibration evidence from the explicitly retained population.
    """
    individual_by_source_index = {
        item.source_indices[0]: item.identifier
        for item in dataset.association_truth_groups
        if item.resolution_class == "individually-resolvable"
    }
    strata = {
        item.identifier: tuple(
            individual_by_source_index[index]
            for index in item.source_indices
            if index in individual_by_source_index
        )
        for item in dataset.validation_strata
    }
    _, _, point, _, _ = truth_sets(dataset)
    identifiers_by_key = {
        (stratum, metric): tuple(
            identifier
            for identifier in identifiers
            if metric != "integrated-flux" or identifier in point
        )
        for stratum, identifiers in strata.items()
        for metric in sorted(POSITION_FLUX_METRICS)
    }
    keys = sorted(
        key for key, identifiers in identifiers_by_key.items() if identifiers
    )
    summaries = np.zeros(
        (len(realizations), len(keys), 4),
        dtype=np.float64,
    )
    for realization_index, realization in enumerate(realizations):
        by_truth = {
            item.truth_identifier: item
            for item in realization.source_pairs
            if item.truth_identifier is not None
        }
        for key_index, key in enumerate(keys):
            identifiers = identifiers_by_key[key]
            values: list[float] = []
            metric = key[1]
            for identifier in identifiers:
                item = by_truth.get(identifier)
                if item is None or item.decision != "matched":
                    continue
                residuals = {
                    residual.metric: residual.value
                    for residual in item.normalized_residuals
                }
                value = residuals.get(metric)
                if value is not None:
                    values.append(value)
            sample_array = np.asarray(values, dtype=np.float64)
            summaries[realization_index, key_index, 0] = np.sum(sample_array)
            summaries[realization_index, key_index, 1] = np.sum(
                sample_array**2
            )
            summaries[realization_index, key_index, 2] = sample_array.size
            summaries[realization_index, key_index, 3] = np.sum(
                np.abs(sample_array) <= 1.0
            )
    return summaries


def ratio_values(
    arrays: CountArrays,
    indices: IntArray,
) -> dict[str, FloatArray]:
    """Calculate aggregate binary rates for every selected image sample."""
    values: dict[str, FloatArray] = {}
    for endpoint_id, counts in arrays.items():
        denominator = np.sum(counts[indices, 1], axis=1)
        numerator = np.sum(counts[indices, 0], axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            rates = np.asarray(numerator / denominator, dtype=np.float64)
        rates[denominator == 0] = np.nan
        values[endpoint_id] = rates
    return values


def group_values(
    arrays: dict[str, FloatArray],
    indices: IntArray,
) -> dict[str, FloatArray]:
    """Calculate conditional aggregate blend errors over retained matches."""
    position = arrays["position"][indices].reshape(indices.shape[0], -1)
    flux = arrays["total-flux"][indices].reshape(indices.shape[0], -1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return {
            "unresolved-group-median-position": np.nanmedian(position, axis=1),
            "unresolved-group-position-tail": np.nanquantile(
                position, 0.95, axis=1
            ),
            "unresolved-group-median-total-flux": np.nanmedian(flux, axis=1),
            "unresolved-group-total-flux-tail": np.nanquantile(
                flux, 0.95, axis=1
            ),
        }


def uncertainty_values(
    arrays: UncertaintyArrays,
    indices: IntArray,
) -> dict[str, FloatArray]:
    """Calculate maximum predeclared normalized-residual departures."""
    totals = np.sum(arrays[indices], axis=1)
    sums = totals[:, :, 0]
    sum_squares = totals[:, :, 1]
    counts = totals[:, :, 2]
    covered = totals[:, :, 3]
    expected_coverage = 0.6826894921370859
    means = sums / counts
    coverage = covered / counts
    variances = np.maximum(
        (sum_squares - sums**2 / counts) / (counts - 1.0),
        0.0,
    )
    return {
        "uncertainty-normalized-bias": np.max(np.abs(means), axis=1),
        "uncertainty-one-sigma-coverage": np.max(
            np.abs(coverage - expected_coverage),
            axis=1,
        ),
        "uncertainty-normalized-dispersion": np.max(
            np.abs(np.sqrt(variances) - 1.0),
            axis=1,
        ),
    }


def endpoint_values(
    counts: CountArrays,
    blends: dict[str, FloatArray],
    uncertainties: UncertaintyArrays,
    indices: IntArray,
) -> dict[str, FloatArray]:
    """Calculate every paired endpoint for selected image clusters."""
    return {
        **ratio_values(counts, indices),
        **group_values(blends, indices),
        **uncertainty_values(uncertainties, indices),
    }


def positive_regressions(
    endpoint: PairedEndpoint,
    candidate: FloatArray,
    reference: FloatArray,
) -> FloatArray:
    """Normalize vector endpoints so positive means candidate regression."""
    if isinstance(endpoint, PairedBinaryEndpoint):
        if endpoint.desirable_direction == "higher-is-better":
            return reference - candidate
        return candidate - reference
    if endpoint.desirable_direction == "lower-is-better":
        return candidate - reference
    assert endpoint.ideal_value is not None
    return np.abs(candidate - endpoint.ideal_value) - np.abs(
        reference - endpoint.ideal_value
    )
