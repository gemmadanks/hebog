# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Direction-aware, no-compensation decisions for Phase 4R campaigns."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import numpy as np
import numpy.typing as npt

from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
)
from hebog.validation.contracts import (
    PairedNoninferiorityContract,
    PhaseFourMetricDefinition,
    PhaseFourMetricRegistry,
    PhaseFourScientificGates,
)
from hebog.validation.datasets import DatasetRecord, DatasetRole
from hebog.validation.evidence import (
    AssociationPairDiagnostic,
    CampaignRealizationDiagnostic,
    EvidenceStatus,
    PhaseFourEnvelopeDecision,
    PhaseFourGateDecision,
    PhaseFourImplementationOutcome,
    PhaseFourRecoveryDecision,
    PhaseFourRecoveryMetricDecision,
    ScientificCampaignEvidence,
    SourcePairDiagnostic,
)
from hebog.validation.phase_four_analysis import POSITION_FLUX_METRICS
from hebog.validation.phase_four_decision import (
    absolute_gate_decisions,
    paired_bca_upper_limits,
    stronger_hebog_envelope_decisions,
)

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
MetricKey = tuple[str, str]
DecisionStage = Literal["development", "regression", "qualification"]
_OVERALL = "overall"
_MINIMUM_DISPERSION_SAMPLES = 2
_SOURCE_RATE_METRICS = frozenset(
    {
        "fitted-shape-availability",
        "deconvolution-classification-availability",
        "resolved-deconvolved-shape-availability",
        "association-identity-availability",
        "position-flux-uncertainty-availability",
        "point-source-specificity",
        "clear-resolved-classification-recall",
        "catastrophic-outlier-fraction",
    }
)
_GROUP_RATE_METRICS = frozenset(
    {
        "compact-completeness",
        "association-pair-recall",
        "unresolved-group-completeness",
    }
)
_OVERALL_RATE_METRICS = frozenset(
    {"catalogue-reliability", "association-pair-precision"}
)
_GROUP_ERROR_METRICS = frozenset(
    {
        "unresolved-group-median-position",
        "unresolved-group-position-tail",
        "unresolved-group-median-total-flux",
        "unresolved-group-total-flux-tail",
    }
)
_UNCERTAINTY_METRICS = frozenset(
    {
        "uncertainty-normalized-bias",
        "uncertainty-one-sigma-coverage",
        "uncertainty-normalized-dispersion",
    }
)
_DECONVOLVED_METRICS = frozenset(
    {
        "median-deconvolved-axis",
        "percentile-95-deconvolved-axis",
        "median-deconvolved-position-angle",
        "percentile-95-deconvolved-position-angle",
    }
)
_UNCERTAINTY_GATE_SUFFIXES = {
    "-uncertainty-bias": "uncertainty-normalized-bias",
    "-uncertainty-coverage": "uncertainty-one-sigma-coverage",
    "-uncertainty-dispersion": "uncertainty-normalized-dispersion",
}


@dataclass(frozen=True, slots=True)
class _TruthIndex:
    """Static truth populations used by every implementation."""

    all_groups: tuple[str, ...]
    individual: tuple[str, ...]
    point: frozenset[str]
    clear: frozenset[str]
    blend: tuple[str, ...]
    sources_by_stratum: dict[str, frozenset[str]]
    groups_by_stratum: dict[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class _MetricPopulation:
    """One bounded per-image sufficient-statistic array."""

    kind: Literal["rate", "observations", "uncertainty"]
    values: FloatArray


@dataclass(frozen=True, slots=True)
class _DecisionContext:
    """Frozen contracts and data shared by one Phase 4R decision."""

    dataset: DatasetRecord
    registry: PhaseFourMetricRegistry
    protocol: PairedNoninferiorityContract
    gates: PhaseFourScientificGates
    stage: DecisionStage
    scientific_contract_set_sha256: str


def _truth_index(dataset: DatasetRecord) -> _TruthIndex:
    """Map manifest source indices to stable diagnostic identifiers."""
    groups = dataset.association_truth_groups
    individual_by_index = {
        group.source_indices[0]: group.identifier
        for group in groups
        if group.resolution_class == "individually-resolvable"
    }
    classifications = {
        stratum.identifier: frozenset(
            individual_by_index[index]
            for index in stratum.source_indices
            if index in individual_by_index
        )
        for stratum in dataset.classification_strata
    }
    try:
        point = classifications["shape-unresolved"]
        clear = classifications["shape-clear-resolved"]
    except KeyError as error:
        raise ValueError(
            "Phase 4R dataset lacks a governed classification stratum"
        ) from error
    source_strata: dict[str, set[str]] = {}
    group_strata: dict[str, set[str]] = {}
    for stratum in (
        *dataset.validation_strata,
        *dataset.classification_strata,
    ):
        source_strata.setdefault(stratum.identifier, set()).update(
            individual_by_index[index]
            for index in stratum.source_indices
            if index in individual_by_index
        )
        group_strata.setdefault(stratum.identifier, set()).update(
            group.identifier
            for group in groups
            if set(group.source_indices).intersection(stratum.source_indices)
        )
    return _TruthIndex(
        all_groups=tuple(group.identifier for group in groups),
        individual=tuple(
            group.identifier
            for group in groups
            if group.resolution_class == "individually-resolvable"
        ),
        point=point,
        clear=clear,
        blend=tuple(
            group.identifier
            for group in groups
            if group.resolution_class == "unresolved-blend"
        ),
        sources_by_stratum={
            key: frozenset(value) for key, value in source_strata.items()
        },
        groups_by_stratum={
            key: frozenset(value) for key, value in group_strata.items()
        },
    )


def _eligible_identifiers(
    metric_id: str,
    stratum: str,
    truth: _TruthIndex,
) -> tuple[str, ...]:
    """Return the fixed truth denominator for one metric population."""
    if metric_id in _GROUP_ERROR_METRICS or metric_id == (
        "unresolved-group-completeness"
    ):
        base = truth.blend
        stratum_ids = truth.groups_by_stratum.get(stratum, frozenset())
    elif metric_id in {"compact-completeness", "association-pair-recall"}:
        base = truth.all_groups
        stratum_ids = truth.groups_by_stratum.get(stratum, frozenset())
    elif metric_id in _DECONVOLVED_METRICS or metric_id in {
        "resolved-deconvolved-shape-availability",
        "clear-resolved-classification-recall",
    }:
        base = tuple(
            identifier
            for identifier in truth.individual
            if identifier in truth.clear
        )
        stratum_ids = truth.sources_by_stratum.get(stratum, frozenset())
    elif metric_id == "point-source-specificity":
        base = tuple(
            identifier
            for identifier in truth.individual
            if identifier in truth.point
        )
        stratum_ids = truth.sources_by_stratum.get(stratum, frozenset())
    else:
        base = truth.individual
        stratum_ids = truth.sources_by_stratum.get(stratum, frozenset())
    if stratum == _OVERALL:
        return tuple(base)
    return tuple(
        identifier for identifier in base if identifier in stratum_ids
    )


def _metric_keys(
    registry: PhaseFourMetricRegistry,
    truth: _TruthIndex,
) -> tuple[tuple[PhaseFourMetricDefinition, str, tuple[str, ...]], ...]:
    """Expand each metric into its eligible overall and governed strata."""
    expanded: list[tuple[PhaseFourMetricDefinition, str, tuple[str, ...]]] = []
    for metric in registry.metrics:
        overall = _eligible_identifiers(metric.metric_id, _OVERALL, truth)
        expanded.append((metric, _OVERALL, overall))
        if metric.stratification == "overall-only":
            continue
        for stratum in registry.governed_strata:
            eligible = _eligible_identifiers(metric.metric_id, stratum, truth)
            if eligible:
                expanded.append((metric, stratum, eligible))
    return tuple(expanded)


def _rate_counts(
    realization: CampaignRealizationDiagnostic,
    metric_id: str,
    eligible: tuple[str, ...],
) -> tuple[float, float]:
    """Return one image's numerator and denominator for a rate metric."""
    if metric_id == "implementation-completion":
        return float(realization.status == "success"), 1.0
    if realization.status != "success":
        return 0.0, 0.0
    if metric_id in _OVERALL_RATE_METRICS:
        matched = sum(
            item.decision == "matched"
            for item in realization.association_pairs
        )
        return float(matched), float(realization.candidate_count or 0)
    eligible_set = set(eligible)
    if metric_id in _GROUP_RATE_METRICS:
        return _group_rate_counts(realization, eligible_set)
    return _source_rate_counts(realization, metric_id, eligible_set)


def _group_rate_counts(
    realization: CampaignRealizationDiagnostic,
    eligible: set[str],
) -> tuple[float, float]:
    """Return association recovery counts over one fixed truth group set."""
    associations = {
        item.truth_group_identifier: item
        for item in realization.association_pairs
        if item.truth_group_identifier is not None
        and item.truth_group_identifier in eligible
    }
    matched_associations = sum(
        item.decision == "matched" for item in associations.values()
    )
    return float(matched_associations), float(len(eligible))


def _source_rate_counts(
    realization: CampaignRealizationDiagnostic,
    metric_id: str,
    eligible: set[str],
) -> tuple[float, float]:
    """Return source-level availability or classification counts."""
    sources = {
        item.truth_identifier: item
        for item in realization.source_pairs
        if item.truth_identifier is not None
        and item.truth_identifier in eligible
    }
    matched = tuple(
        item for item in sources.values() if item.decision == "matched"
    )
    if metric_id == "fitted-shape-availability":
        numerator = sum(
            item.maximum_absolute_fitted_axis_fractional_difference is not None
            for item in matched
        )
        denominator = len(eligible)
    elif metric_id == "deconvolution-classification-availability":
        numerator = sum(
            item.candidate_deconvolution_status is not None for item in matched
        )
        denominator = len(eligible)
    elif metric_id == "resolved-deconvolved-shape-availability":
        numerator = sum(
            item.maximum_absolute_deconvolved_axis_fractional_difference
            is not None
            for item in matched
        )
        denominator = len(eligible)
    elif metric_id == "association-identity-availability":
        numerator = len(matched)
        denominator = len(eligible)
    elif metric_id == "position-flux-uncertainty-availability":
        numerator = sum(
            POSITION_FLUX_METRICS.issubset(
                {residual.metric for residual in item.normalized_residuals}
            )
            for item in matched
        )
        denominator = len(eligible)
    elif metric_id in {
        "point-source-specificity",
        "clear-resolved-classification-recall",
    }:
        numerator = sum(item.classification_agrees is True for item in matched)
        denominator = len(eligible)
    elif metric_id == "catastrophic-outlier-fraction":
        numerator = sum(item.gated_catastrophic is True for item in matched)
        denominator = len(matched)
    else:
        raise ValueError(f"unsupported Phase 4R rate metric: {metric_id}")
    return float(numerator), float(denominator)


def _group_observation_value(
    item: AssociationPairDiagnostic,
    metric_id: str,
) -> float | None:
    """Extract one unresolved-group absolute error."""
    if metric_id in {
        "unresolved-group-median-position",
        "unresolved-group-position-tail",
    }:
        value = item.separation_beam_fwhm
    else:
        value = item.integrated_flux_fractional_difference
    return None if value is None else abs(float(value))


def _source_observation_value(
    item: SourcePairDiagnostic,
    metric_id: str,
) -> float | None:
    """Extract one source-level absolute error."""
    extractors = {
        "position": item.separation_beam_fwhm,
        "peak-flux": item.peak_flux_fractional_difference,
        "integrated-flux": item.integrated_flux_fractional_difference,
        "fitted-axis": (
            item.maximum_absolute_fitted_axis_fractional_difference
        ),
        "deconvolved-axis": (
            item.maximum_absolute_deconvolved_axis_fractional_difference
        ),
        "fitted-position-angle": (
            item.fitted_position_angle_difference_degrees
        ),
        "deconvolved-position-angle": (
            item.deconvolved_position_angle_difference_degrees
        ),
    }
    statistic_prefix = (
        "percentile-95-"
        if metric_id.startswith("percentile-95-")
        else "median-"
    )
    quantity = metric_id.removeprefix(statistic_prefix)
    try:
        value = extractors[quantity]
    except KeyError as error:
        raise ValueError(
            f"unsupported Phase 4R observation metric: {metric_id}"
        ) from error
    return None if value is None else abs(float(value))


def _observation_row(
    realization: CampaignRealizationDiagnostic,
    metric_id: str,
    eligible: tuple[str, ...],
) -> FloatArray:
    """Return a fixed-width conditional error row with explicit NaNs."""
    values = np.full(len(eligible), np.nan, dtype=np.float64)
    if realization.status != "success":
        return values
    if metric_id in _GROUP_ERROR_METRICS:
        groups = {
            item.truth_group_identifier: item
            for item in realization.association_pairs
            if item.truth_group_identifier is not None
        }
        for index, identifier in enumerate(eligible):
            item = groups.get(identifier)
            if item is not None and item.decision == "matched":
                value = _group_observation_value(item, metric_id)
                if value is not None:
                    values[index] = value
        return values
    sources = {
        item.truth_identifier: item
        for item in realization.source_pairs
        if item.truth_identifier is not None
    }
    for index, identifier in enumerate(eligible):
        item = sources.get(identifier)
        if item is None or item.decision != "matched":
            continue
        value = _source_observation_value(item, metric_id)
        if value is not None:
            values[index] = value
    return values


def _uncertainty_row(
    realization: CampaignRealizationDiagnostic,
    eligible: tuple[str, ...],
    truth: _TruthIndex,
) -> FloatArray:
    """Return per-source normalized residuals in a stable metric order."""
    metrics = tuple(sorted(POSITION_FLUX_METRICS))
    values = np.full((len(eligible), len(metrics)), np.nan, dtype=np.float64)
    if realization.status != "success":
        return values
    by_truth = {
        item.truth_identifier: item
        for item in realization.source_pairs
        if item.truth_identifier is not None
    }
    for source_index, identifier in enumerate(eligible):
        item = by_truth.get(identifier)
        if item is None or item.decision != "matched":
            continue
        residuals = {
            residual.metric: residual.value
            for residual in item.normalized_residuals
        }
        for metric_index, metric in enumerate(metrics):
            if metric == "integrated-flux" and identifier not in truth.point:
                continue
            if metric in residuals:
                values[source_index, metric_index] = residuals[metric]
    return values


def _populations(
    realizations: Sequence[CampaignRealizationDiagnostic],
    expanded: Sequence[tuple[PhaseFourMetricDefinition, str, tuple[str, ...]]],
    truth: _TruthIndex,
) -> dict[MetricKey, _MetricPopulation]:
    """Materialize bounded sufficient statistics for one implementation."""
    populations: dict[MetricKey, _MetricPopulation] = {}
    for metric, stratum, eligible in expanded:
        key = (metric.metric_id, stratum)
        if metric.statistic in {"completion-rate", "rate"}:
            rows = np.asarray(
                [
                    _rate_counts(realization, metric.metric_id, eligible)
                    for realization in realizations
                ],
                dtype=np.float64,
            )
            populations[key] = _MetricPopulation("rate", rows)
        elif metric.metric_id in _UNCERTAINTY_METRICS:
            rows = np.asarray(
                [
                    _uncertainty_row(realization, eligible, truth)
                    for realization in realizations
                ],
                dtype=np.float64,
            )
            populations[key] = _MetricPopulation("uncertainty", rows)
        else:
            rows = np.asarray(
                [
                    _observation_row(
                        realization,
                        metric.metric_id,
                        eligible,
                    )
                    for realization in realizations
                ],
                dtype=np.float64,
            )
            populations[key] = _MetricPopulation("observations", rows)
    return populations


def _uncertainty_value(metric_id: str, selected: FloatArray) -> FloatArray:
    """Aggregate normalized residuals over images and eligible sources."""
    leading = selected.shape[:-3]
    samples = selected.reshape((*leading, -1, selected.shape[-1]))
    finite = np.isfinite(samples)
    counts = np.sum(finite, axis=-2)
    sums = np.nansum(samples, axis=-2)
    sums_squared = np.nansum(samples**2, axis=-2)
    with np.errstate(divide="ignore", invalid="ignore"):
        means = sums / counts
        coverage = np.sum(np.abs(samples) <= 1.0, axis=-2) / counts
        variances = (sums_squared - sums**2 / counts) / (counts - 1.0)
    variances = np.maximum(variances, 0.0)
    means[counts == 0] = np.nan
    coverage[counts == 0] = np.nan
    variances[counts < _MINIMUM_DISPERSION_SAMPLES] = np.nan
    if metric_id == "uncertainty-normalized-bias":
        departures = np.abs(means)
    elif metric_id == "uncertainty-one-sigma-coverage":
        departures = np.abs(coverage - 0.6826894921370859)
    else:
        departures = np.abs(np.sqrt(variances) - 1.0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.asarray(np.nanmax(departures, axis=-1), dtype=np.float64)


def _aggregate(
    metric: PhaseFourMetricDefinition,
    population: _MetricPopulation,
    indices: IntArray,
) -> FloatArray:
    """Aggregate one metric over whole-image resampling indices."""
    selected = np.asarray(population.values[indices], dtype=np.float64)
    if population.kind == "rate":
        numerator = np.sum(selected[..., 0], axis=-1)
        denominator = np.sum(selected[..., 1], axis=-1)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.asarray(numerator / denominator, dtype=np.float64)
    if population.kind == "uncertainty":
        return _uncertainty_value(metric.metric_id, selected)
    leading = selected.shape[:-2]
    flattened = selected.reshape((*leading, -1))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        if metric.statistic == "median-absolute-error":
            value = np.nanmedian(flattened, axis=-1)
        else:
            value = np.nanquantile(flattened, 0.95, axis=-1)
    return np.asarray(value, dtype=np.float64)


def _positive_regression(
    metric: PhaseFourMetricDefinition,
    candidate: FloatArray,
    reference: FloatArray,
) -> FloatArray:
    """Normalize direction so positive always means Hebog is worse."""
    if metric.desirable_direction == "higher-is-better":
        return reference - candidate
    return candidate - reference


def _statistic(
    expanded: Sequence[tuple[PhaseFourMetricDefinition, str, tuple[str, ...]]],
    candidate: dict[MetricKey, _MetricPopulation],
    reference: dict[MetricKey, _MetricPopulation],
):
    """Build one vector statistic sharing each whole-image resample."""

    def statistic(
        sampled_indices: npt.ArrayLike,
        axis: int = -1,
    ) -> FloatArray:
        indices = np.moveaxis(
            np.asarray(sampled_indices, dtype=np.int64),
            axis,
            -1,
        )
        values = [
            _positive_regression(
                metric,
                _aggregate(
                    metric, candidate[(metric.metric_id, stratum)], indices
                ),
                _aggregate(
                    metric, reference[(metric.metric_id, stratum)], indices
                ),
            )
            for metric, stratum, _ in expanded
        ]
        return np.stack(values, axis=0)

    return statistic


def _implementation_realizations(
    campaign: ScientificCampaignEvidence,
    identifier: str,
) -> tuple[CampaignRealizationDiagnostic, ...]:
    """Return one implementation's ordered realization diagnostics."""
    return tuple(
        realization
        for realization in campaign.realizations
        if realization.implementation_identifier == identifier
    )


def _metric_decisions(
    candidate: Sequence[CampaignRealizationDiagnostic],
    reference: Sequence[CampaignRealizationDiagnostic],
    context: _DecisionContext,
    *,
    reference_identifier: str,
) -> tuple[PhaseFourRecoveryMetricDecision, ...]:
    """Evaluate every eligible metric independently against one reference."""
    truth = _truth_index(context.dataset)
    expanded = _metric_keys(context.registry, truth)
    candidate_populations = _populations(candidate, expanded, truth)
    reference_populations = _populations(reference, expanded, truth)
    indices = np.arange(len(candidate), dtype=np.int64)
    candidate_values = np.asarray(
        [
            _aggregate(
                metric,
                candidate_populations[(metric.metric_id, stratum)],
                indices,
            )
            for metric, stratum, _ in expanded
        ],
        dtype=np.float64,
    )
    reference_values = np.asarray(
        [
            _aggregate(
                metric,
                reference_populations[(metric.metric_id, stratum)],
                indices,
            )
            for metric, stratum, _ in expanded
        ],
        dtype=np.float64,
    )
    regressions = np.asarray(
        [
            _positive_regression(
                metric, candidate_values[index], reference_values[index]
            )
            for index, (metric, _, _) in enumerate(expanded)
        ],
        dtype=np.float64,
    )
    upper_limits: FloatArray | None = None
    if context.stage == "qualification":
        _, upper_limits = paired_bca_upper_limits(
            _statistic(
                expanded,
                candidate_populations,
                reference_populations,
            ),
            realization_count=len(candidate),
            resampling=context.protocol.resampling,
        )

    decisions: list[PhaseFourRecoveryMetricDecision] = []
    for index, (metric, stratum, _) in enumerate(expanded):
        candidate_value = float(candidate_values[index])
        reference_value = float(reference_values[index])
        regression = float(regressions[index])
        finite_point = all(
            np.isfinite(value)
            for value in (candidate_value, reference_value, regression)
        )
        margin = metric.primary_practical_regression_margin
        if not finite_point:
            decisions.append(
                PhaseFourRecoveryMetricDecision(
                    metric_id=metric.metric_id,
                    stratum=stratum,
                    reference_identifier=reference_identifier,
                    practical_regression_margin=margin,
                    point_status="indeterminate",
                    interval_status=(
                        "not-evaluated"
                        if context.stage != "qualification"
                        else "indeterminate"
                    ),
                    status="indeterminate",
                    reason="metric population is unavailable or non-finite",
                )
            )
            continue
        point_status: Literal["pass", "fail"] = (
            "pass" if regression <= margin else "fail"
        )
        if upper_limits is None:
            decisions.append(
                PhaseFourRecoveryMetricDecision(
                    metric_id=metric.metric_id,
                    stratum=stratum,
                    reference_identifier=reference_identifier,
                    candidate_value=candidate_value,
                    reference_value=reference_value,
                    positive_regression=regression,
                    practical_regression_margin=margin,
                    point_status=point_status,
                    interval_status="not-evaluated",
                    status=point_status,
                )
            )
            continue
        upper = float(upper_limits[index])
        if not np.isfinite(upper):
            decisions.append(
                PhaseFourRecoveryMetricDecision(
                    metric_id=metric.metric_id,
                    stratum=stratum,
                    reference_identifier=reference_identifier,
                    candidate_value=candidate_value,
                    reference_value=reference_value,
                    positive_regression=regression,
                    practical_regression_margin=margin,
                    point_status=point_status,
                    interval_status="indeterminate",
                    status=(
                        "fail" if point_status == "fail" else "indeterminate"
                    ),
                    reason="paired BCa interval is non-finite",
                )
            )
            continue
        interval_status: Literal["pass", "fail"] = (
            "pass" if upper <= margin else "fail"
        )
        decisions.append(
            PhaseFourRecoveryMetricDecision(
                metric_id=metric.metric_id,
                stratum=stratum,
                reference_identifier=reference_identifier,
                candidate_value=candidate_value,
                reference_value=reference_value,
                positive_regression=regression,
                practical_regression_margin=margin,
                point_status=point_status,
                upper_confidence_limit=upper,
                interval_status=interval_status,
                status=(
                    "pass"
                    if point_status == "pass" and interval_status == "pass"
                    else "fail"
                ),
            )
        )
    return tuple(decisions)


def _validate_inputs(
    campaign: ScientificCampaignEvidence,
    context: _DecisionContext,
) -> None:
    """Reject role, identity, or frozen-contract drift before evaluation."""
    expected_role = DatasetRole(context.stage)
    if context.dataset.role is not expected_role:
        raise ValueError("Phase 4R decision stage and dataset role differ")
    if campaign.dataset != campaign_dataset_identity(context.dataset):
        raise ValueError("campaign evidence and governed dataset differ")
    if campaign.configuration_sha256 != context.scientific_contract_set_sha256:
        raise ValueError("campaign scientific contract set changed")
    protocol_sha256 = canonical_sha256(
        context.protocol.model_dump(mode="json")
    )
    if campaign.comparison_protocol_sha256 != protocol_sha256:
        raise ValueError("campaign paired protocol changed")
    if context.registry.point_estimate_rule != (
        "within-practical-margin-on-frozen-development-regression"
    ):
        raise ValueError("Phase 4R point rule is unsupported")


def _absolute_metric_identifier(
    gate_id: str,
    metric_identifiers: frozenset[str],
) -> str:
    """Map one legacy absolute-gate name to its registry metric."""
    if gate_id in metric_identifiers:
        return gate_id
    for suffix, metric_id in _UNCERTAINTY_GATE_SUFFIXES.items():
        if gate_id.endswith(suffix):
            return metric_id
    raise ValueError(
        f"absolute gate is absent from the Phase 4R registry: {gate_id}"
    )


def _apply_absolute_roles(
    decisions: Sequence[PhaseFourGateDecision],
    registry: PhaseFourMetricRegistry,
) -> tuple[PhaseFourGateDecision, ...]:
    """Apply the registry's noisy-campaign gate/report distinction."""
    by_identifier = {item.metric_id: item for item in registry.metrics}
    metric_identifiers = frozenset(by_identifier)
    governed: list[PhaseFourGateDecision] = []
    for decision in decisions:
        metric_id = _absolute_metric_identifier(
            decision.gate_id,
            metric_identifiers,
        )
        registered_role = by_identifier[metric_id].absolute_role
        if registered_role == "none":
            raise ValueError(
                "absolute gate maps to a registry metric without an absolute "
                f"role: {decision.gate_id}"
            )
        role = (
            "report-only"
            if "report-only" in (decision.role, registered_role)
            else "gate"
        )
        governed.append(decision.model_copy(update={"role": role}))
    return tuple(governed)


def _failure_reasons(
    outcomes: Sequence[PhaseFourImplementationOutcome],
    metrics: Sequence[PhaseFourRecoveryMetricDecision],
    gates: Sequence[PhaseFourGateDecision],
    envelopes: Sequence[PhaseFourEnvelopeDecision],
) -> tuple[str, ...]:
    """Return canonical reasons without collapsing metric identities."""
    reasons = {
        f"required-implementation-failed:{item.implementation_identifier}"
        for item in outcomes
        if item.policy == "qualification-fails" and item.failed_seeds
    }
    reasons.update(
        f"metric-{item.status}:{item.reference_identifier}:"
        f"{item.metric_id}:{item.stratum}"
        for item in metrics
        if item.status != "pass"
    )
    reasons.update(
        f"absolute-gate-{item.status}:{item.gate_id}"
        for item in gates
        if item.role == "gate" and item.status != "pass"
    )
    reasons.update(
        f"stronger-envelope-{item.status}:{item.envelope_id}"
        for item in envelopes
        if item.status != "pass"
    )
    return tuple(sorted(reasons))


def evaluate_phase_four_recovery(  # noqa: PLR0913
    campaign: ScientificCampaignEvidence,
    dataset: DatasetRecord,
    registry: PhaseFourMetricRegistry,
    protocol: PairedNoninferiorityContract,
    gates: PhaseFourScientificGates,
    *,
    stage: DecisionStage,
    scientific_contract_set_sha256: str,
    candidate_identifier: str = "hebog",
    reference_identifiers: tuple[str, str] = (
        "pybdsf-master",
        "pybdsf-release",
    ),
    captured_at: datetime | None = None,
) -> PhaseFourRecoveryDecision:
    """Produce one immutable conjunctive Phase 4R campaign decision."""
    context = _DecisionContext(
        dataset=dataset,
        registry=registry,
        protocol=protocol,
        gates=gates,
        stage=stage,
        scientific_contract_set_sha256=scientific_contract_set_sha256,
    )
    _validate_inputs(campaign, context)
    implementations = {
        item.identifier: item for item in campaign.implementations
    }
    required = {candidate_identifier, *reference_identifiers}
    if set(implementations) != required:
        raise ValueError(
            "Phase 4R campaign must contain exactly Hebog and both references"
        )
    ordered_references = tuple(sorted(reference_identifiers))
    candidate = _implementation_realizations(campaign, candidate_identifier)
    expected_seeds = tuple(item.seed for item in candidate)
    if not candidate:
        raise ValueError("Phase 4R campaign has no candidate realizations")
    metrics: list[PhaseFourRecoveryMetricDecision] = []
    ordered_realizations: dict[
        str, tuple[CampaignRealizationDiagnostic, ...]
    ] = {candidate_identifier: candidate}
    for reference_identifier in ordered_references:
        reference = _implementation_realizations(
            campaign, reference_identifier
        )
        if tuple(item.seed for item in reference) != expected_seeds:
            raise ValueError("Phase 4R implementations cover different seeds")
        ordered_realizations[reference_identifier] = reference
        metrics.extend(
            _metric_decisions(
                candidate,
                reference,
                context,
                reference_identifier=reference_identifier,
            )
        )
    outcomes = tuple(
        PhaseFourImplementationOutcome(
            implementation_identifier=identifier,
            policy=(
                "qualification-fails"
                if identifier == candidate_identifier
                else "record-and-continue"
            ),
            failed_seeds=tuple(
                item.seed
                for item in ordered_realizations[identifier]
                if item.status == "failure"
            ),
        )
        for identifier in (candidate_identifier, *ordered_references)
    )
    try:
        absolute_gates = _apply_absolute_roles(
            absolute_gate_decisions(
                candidate,
                context.dataset,
                context.gates,
            ),
            context.registry,
        )
    except (ValueError, FloatingPointError) as error:
        absolute_gates = (
            PhaseFourGateDecision(
                gate_id="absolute-science-evaluation",
                comparator="maximum",
                maximum=0.0,
                eligible_count=0,
                status="indeterminate",
                reason=f"absolute gate input is invalid: {error}",
            ),
        )
    if not absolute_gates:
        absolute_gates = (
            PhaseFourGateDecision(
                gate_id="absolute-science-evaluation",
                comparator="maximum",
                maximum=0.0,
                eligible_count=0,
                status="indeterminate",
                reason="candidate did not complete every realization",
            ),
        )
    envelopes = stronger_hebog_envelope_decisions(absolute_gates)
    reasons = _failure_reasons(outcomes, metrics, absolute_gates, envelopes)
    return PhaseFourRecoveryDecision(
        schema_version=1,
        evidence_type="phase-4r-decision",
        run_id=f"{campaign.run_id}-{stage}-decision",
        captured_at=captured_at or datetime.now(timezone.utc),
        status=EvidenceStatus.EXPLORATORY,
        dataset=campaign.dataset,
        configuration_sha256=campaign.configuration_sha256,
        decision_stage=stage,
        source_campaign_run_id=campaign.run_id,
        source_campaign_sha256=canonical_sha256(
            campaign.model_dump(mode="json")
        ),
        comparison_protocol_sha256=canonical_sha256(
            protocol.model_dump(mode="json")
        ),
        scientific_gates_sha256=canonical_sha256(
            gates.model_dump(mode="json")
        ),
        metric_registry_sha256=canonical_sha256(
            registry.model_dump(mode="json")
        ),
        candidate_identifier=candidate_identifier,
        reference_identifiers=ordered_references,
        implementation_outcomes=outcomes,
        metric_decisions=tuple(metrics),
        absolute_gates=absolute_gates,
        stronger_hebog_envelopes=envelopes,
        passed=not reasons,
        failure_reasons=reasons,
    )
