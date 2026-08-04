# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Immutable one-look decision logic for the final Phase 4 campaign."""

from __future__ import annotations

import warnings
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt
from scipy.stats import DegenerateDataWarning, bootstrap

from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
)
from hebog.validation.comparison import uncertainty_calibration_report
from hebog.validation.contracts import (
    PairedNoninferiorityContract,
    PairedResamplingProtocol,
    PhaseFourCatalogueGate,
    PhaseFourScientificGates,
)
from hebog.validation.datasets import DatasetRecord, DatasetRole
from hebog.validation.evidence import (
    CampaignRealizationDiagnostic,
    EvidenceStatus,
    PhaseFourEndpointDecision,
    PhaseFourEnvelopeDecision,
    PhaseFourGateDecision,
    PhaseFourImplementationOutcome,
    PhaseFourQualificationDecision,
    ScientificCampaignEvidence,
)
from hebog.validation.phase_four_analysis import (
    PAIRED_ENDPOINT_IDS,
    POSITION_FLUX_METRICS,
    FloatArray,
    PairedEndpoint,
    blend_arrays,
    count_arrays,
    endpoint_values,
    group_values,
    positive_regressions,
    ratio_values,
    truth_sets,
    uncertainty_arrays,
)

AnalysisInputs = tuple[
    dict[str, FloatArray],
    dict[str, FloatArray],
    FloatArray,
]
EndpointStatistic = Callable[..., npt.NDArray[np.float64]]
_MINIMUM_BOOTSTRAP_REALIZATIONS = 2


class _ConfidenceInterval(Protocol):
    """Common bounds exposed by numeric and binomial intervals."""

    @property
    def lower(self) -> float:
        """Return the lower interval bound."""
        ...

    @property
    def upper(self) -> float:
        """Return the upper interval bound."""
        ...


_SCIENTIFIC_ENVELOPES: dict[str, tuple[str, ...]] = {
    "complete-group-recovery": (
        "compact-completeness",
        "unresolved-group-completeness",
    ),
    "uncertainty-availability-and-calibration": (
        "position-flux-uncertainty-availability",
    ),
    "unresolved-group-errors": (
        "unresolved-group-median-position",
        "unresolved-group-median-total-flux",
        "unresolved-group-position-tail",
        "unresolved-group-total-flux-tail",
    ),
    "clear-resolved-recall": ("clear-resolved-classification-recall",),
    "catastrophic-tail": ("catastrophic-outlier-fraction",),
}


def _implementation_realizations(
    campaign: ScientificCampaignEvidence,
    identifier: str,
    *,
    role: Literal["candidate", "reference"],
) -> tuple[CampaignRealizationDiagnostic, ...]:
    """Return one implementation's ordered realization records."""
    identities = {item.identifier: item for item in campaign.implementations}
    identity = identities.get(identifier)
    if identity is None:
        raise ValueError(f"campaign implementation is absent: {identifier}")
    if identity.role != role:
        raise ValueError(
            f"campaign implementation has the wrong role: {identifier}"
        )
    return tuple(
        realization
        for realization in campaign.realizations
        if realization.implementation_identifier == identifier
    )


def _inputs(
    realizations: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
) -> AnalysisInputs:
    """Materialize the bounded summaries used by every paired endpoint."""
    return (
        count_arrays(realizations, dataset),
        blend_arrays(realizations, dataset),
        uncertainty_arrays(realizations, dataset),
    )


def _endpoint_map(
    contract: PairedNoninferiorityContract,
) -> dict[str, PairedEndpoint]:
    """Return the complete reviewed endpoint map in contract order."""
    endpoints = (
        *contract.binary_endpoints,
        *contract.continuous_endpoints,
    )
    by_identifier = {item.endpoint_id: item for item in endpoints}
    if frozenset(by_identifier) != PAIRED_ENDPOINT_IDS:
        raise ValueError(
            "paired protocol endpoint set is unsupported or incomplete"
        )
    return by_identifier


def _regression_statistic(
    candidate_inputs: AnalysisInputs,
    reference_inputs: AnalysisInputs,
    endpoint_by_identifier: dict[str, PairedEndpoint],
) -> EndpointStatistic:
    """Build one vectorized statistic sharing every whole-image resample."""
    endpoint_items = tuple(endpoint_by_identifier.items())

    def statistic(
        sampled_indices: npt.ArrayLike,
        axis: int = -1,
    ) -> npt.NDArray[np.float64]:
        selected = np.moveaxis(
            np.asarray(sampled_indices, dtype=np.int64),
            axis,
            -1,
        )
        leading_shape = selected.shape[:-1]
        index_rows = selected.reshape(-1, selected.shape[-1])
        candidate = endpoint_values(*candidate_inputs, index_rows)
        reference = endpoint_values(*reference_inputs, index_rows)
        regressions = np.stack(
            [
                positive_regressions(
                    endpoint,
                    candidate[identifier],
                    reference[identifier],
                )
                for identifier, endpoint in endpoint_items
            ],
            axis=0,
        )
        if not leading_shape:
            return regressions[:, 0]
        return regressions.reshape((len(endpoint_items), *leading_shape))

    return statistic


def _indeterminate_endpoints(
    contract: PairedNoninferiorityContract,
    reason: str,
) -> tuple[PhaseFourEndpointDecision, ...]:
    """Return a complete failed-closed endpoint set."""
    return tuple(
        PhaseFourEndpointDecision(
            endpoint_id=endpoint.endpoint_id,
            practical_regression_margin=endpoint.practical_regression_margin,
            confidence_level=contract.resampling.confidence_level,
            resamples=contract.resampling.resamples,
            status="indeterminate",
            reason=reason,
        )
        for endpoint in (
            *contract.binary_endpoints,
            *contract.continuous_endpoints,
        )
    )


def paired_bca_upper_limits(
    statistic: EndpointStatistic,
    *,
    realization_count: int,
    resampling: PairedResamplingProtocol,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Return point estimates and one-sided SciPy BCa upper limits."""
    if realization_count < _MINIMUM_BOOTSTRAP_REALIZATIONS:
        raise ValueError("paired BCa intervals require at least two images")
    indices = np.arange(realization_count, dtype=np.int64)
    point_estimates = np.asarray(statistic(indices), dtype=np.float64)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DegenerateDataWarning)
        warnings.simplefilter("ignore", RuntimeWarning)
        result = bootstrap(
            (indices,),
            statistic,
            vectorized=True,
            paired=True,
            confidence_level=resampling.confidence_level,
            n_resamples=resampling.resamples,
            batch=500,
            method="BCa",
            alternative=resampling.alternative,
            rng=np.random.default_rng(resampling.seed),
        )
    upper_limits = np.asarray(
        result.confidence_interval.high,
        dtype=np.float64,
    )
    return point_estimates, upper_limits


def paired_endpoint_decisions(
    candidate: Sequence[CampaignRealizationDiagnostic],
    reference: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
    contract: PairedNoninferiorityContract,
) -> tuple[PhaseFourEndpointDecision, ...]:
    """Apply the reviewed one-sided paired BCa rule to every endpoint."""
    if len(candidate) != len(reference):
        raise ValueError("paired endpoint realizations differ in count")
    if tuple(item.seed for item in candidate) != tuple(
        item.seed for item in reference
    ):
        raise ValueError("paired endpoint realization seeds differ")
    if not candidate:
        return _indeterminate_endpoints(contract, "no paired realizations")
    if any(item.status != "success" for item in (*candidate, *reference)):
        return _indeterminate_endpoints(
            contract,
            "candidate or primary reference realization failed",
        )

    endpoint_by_identifier = _endpoint_map(contract)
    try:
        candidate_inputs = _inputs(candidate, dataset)
        reference_inputs = _inputs(reference, dataset)
        statistic = _regression_statistic(
            candidate_inputs,
            reference_inputs,
            endpoint_by_identifier,
        )
        indices = np.arange(len(candidate), dtype=np.int64)
        point_regressions, upper_limits = paired_bca_upper_limits(
            statistic,
            realization_count=len(candidate),
            resampling=contract.resampling,
        )
        full_indices = indices[None, :]
        candidate_values = endpoint_values(*candidate_inputs, full_indices)
        reference_values = endpoint_values(*reference_inputs, full_indices)
    except (ValueError, FloatingPointError) as error:
        return _indeterminate_endpoints(
            contract,
            f"paired interval is undefined: {error}",
        )

    decisions: list[PhaseFourEndpointDecision] = []
    endpoints = tuple(endpoint_by_identifier.values())
    for index, endpoint in enumerate(endpoints):
        identifier = endpoint.endpoint_id
        candidate_value = float(candidate_values[identifier][0])
        reference_value = float(reference_values[identifier][0])
        regression = float(point_regressions[index])
        upper = float(upper_limits[index])
        if not all(
            np.isfinite(value)
            for value in (
                candidate_value,
                reference_value,
                regression,
                upper,
            )
        ):
            point_estimate_is_finite = all(
                np.isfinite(value)
                for value in (
                    candidate_value,
                    reference_value,
                    regression,
                )
            )
            decisions.append(
                PhaseFourEndpointDecision(
                    endpoint_id=identifier,
                    candidate_value=(
                        candidate_value if point_estimate_is_finite else None
                    ),
                    reference_value=(
                        reference_value if point_estimate_is_finite else None
                    ),
                    positive_regression=(
                        regression if point_estimate_is_finite else None
                    ),
                    practical_regression_margin=(
                        endpoint.practical_regression_margin
                    ),
                    confidence_level=contract.resampling.confidence_level,
                    resamples=contract.resampling.resamples,
                    status="indeterminate",
                    reason="SciPy BCa interval is degenerate or non-finite",
                )
            )
            continue
        margin = endpoint.practical_regression_margin
        decisions.append(
            PhaseFourEndpointDecision(
                endpoint_id=identifier,
                candidate_value=candidate_value,
                reference_value=reference_value,
                positive_regression=regression,
                practical_regression_margin=margin,
                upper_confidence_limit=upper,
                confidence_level=contract.resampling.confidence_level,
                resamples=contract.resampling.resamples,
                status="pass" if upper <= margin else "fail",
            )
        )
    return tuple(decisions)


def _scalar_gate(  # noqa: PLR0913
    gate_id: str,
    value: float | None,
    *,
    comparator: Literal["minimum", "maximum"],
    threshold: float,
    eligible_count: int,
    role: Literal["gate", "report-only"] = "gate",
    missing_reason: str = "required population has no finite measurement",
) -> PhaseFourGateDecision:
    """Build one fail-closed scalar absolute gate."""
    if value is None or not np.isfinite(value):
        return PhaseFourGateDecision(
            gate_id=gate_id,
            comparator=comparator,
            minimum=threshold if comparator == "minimum" else None,
            maximum=threshold if comparator == "maximum" else None,
            eligible_count=eligible_count,
            role=role,
            status="indeterminate",
            reason=missing_reason,
        )
    passed = (
        value >= threshold if comparator == "minimum" else value <= threshold
    )
    return PhaseFourGateDecision(
        gate_id=gate_id,
        value=value,
        comparator=comparator,
        minimum=threshold if comparator == "minimum" else None,
        maximum=threshold if comparator == "maximum" else None,
        eligible_count=eligible_count,
        role=role,
        status="pass" if passed else "fail",
    )


def _interval_gate(  # noqa: PLR0913
    gate_id: str,
    value: float | None,
    interval: _ConfidenceInterval | None,
    *,
    minimum: float,
    maximum: float,
    eligible_count: int,
    role: Literal["gate", "report-only"] = "gate",
) -> PhaseFourGateDecision:
    """Build one entire-confidence-interval absolute gate."""
    if value is None or interval is None:
        return PhaseFourGateDecision(
            gate_id=gate_id,
            value=(
                float(value)
                if value is not None and np.isfinite(value)
                else None
            ),
            comparator="interval",
            minimum=minimum,
            maximum=maximum,
            eligible_count=eligible_count,
            role=role,
            status="indeterminate",
            reason="required uncertainty interval is unavailable",
        )
    passed = interval.lower >= minimum and interval.upper <= maximum
    return PhaseFourGateDecision(
        gate_id=gate_id,
        value=value,
        comparator="interval",
        minimum=minimum,
        maximum=maximum,
        interval_lower=interval.lower,
        interval_upper=interval.upper,
        eligible_count=eligible_count,
        role=role,
        status="pass" if passed else "fail",
    )


def _rate_gates(
    values: dict[str, FloatArray],
    counts: dict[str, FloatArray],
    gate: PhaseFourCatalogueGate,
) -> list[PhaseFourGateDecision]:
    """Evaluate every absolute binary catalogue gate."""
    thresholds: dict[str, tuple[Literal["minimum", "maximum"], float]] = {
        "compact-completeness": ("minimum", gate.minimum_completeness),
        "catalogue-reliability": ("minimum", gate.minimum_reliability),
        "association-pair-precision": (
            "minimum",
            gate.minimum_association_pair_precision,
        ),
        "association-pair-recall": (
            "minimum",
            gate.minimum_association_pair_recall,
        ),
        "fitted-shape-availability": (
            "minimum",
            gate.minimum_fitted_shape_availability,
        ),
        "deconvolution-classification-availability": (
            "minimum",
            gate.minimum_deconvolution_classification_availability,
        ),
        "resolved-deconvolved-shape-availability": (
            "minimum",
            gate.minimum_resolved_deconvolved_shape_availability,
        ),
        "association-identity-availability": (
            "minimum",
            gate.minimum_association_identity_availability,
        ),
        "position-flux-uncertainty-availability": (
            "minimum",
            gate.minimum_position_flux_uncertainty_availability,
        ),
        "point-source-specificity": (
            "minimum",
            gate.minimum_point_source_specificity,
        ),
        "clear-resolved-classification-recall": (
            "minimum",
            gate.minimum_clear_resolved_classification_recall,
        ),
        "catastrophic-outlier-fraction": (
            "maximum",
            gate.maximum_catastrophic_outlier_fraction,
        ),
    }
    decisions: list[PhaseFourGateDecision] = []
    for identifier, (comparator, threshold) in thresholds.items():
        total_eligible = int(np.sum(counts[identifier][:, 1]))
        decisions.append(
            _scalar_gate(
                identifier,
                float(values[identifier][0]),
                comparator=comparator,
                threshold=threshold,
                eligible_count=total_eligible,
            )
        )
    return decisions


def _required_float(value: float | None, metric: str) -> float:
    """Return a core matched-source metric or reject corrupt evidence."""
    if value is None:
        raise ValueError(f"matched source lacks required {metric} metric")
    return float(value)


def distribution_gate_decisions(
    realizations: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
    gate: PhaseFourCatalogueGate,
) -> list[PhaseFourGateDecision]:
    """Evaluate absolute matched-source position, flux, and shape gates."""
    _, individual, _, clear, _ = truth_sets(dataset)
    matched = tuple(
        pair
        for realization in realizations
        for pair in realization.source_pairs
        if pair.decision == "matched" and pair.truth_identifier in individual
    )
    clear_matched = tuple(
        pair for pair in matched if pair.truth_identifier in clear
    )
    fitted_position_angles = [
        abs(float(pair.fitted_position_angle_difference_degrees))
        for pair in matched
        if pair.fitted_position_angle_difference_degrees is not None
    ]
    deconvolved_position_angles = [
        abs(float(pair.deconvolved_position_angle_difference_degrees))
        for pair in clear_matched
        if pair.deconvolved_position_angle_difference_degrees is not None
    ]
    populations: dict[str, tuple[list[float], int, float, float]] = {
        "position": (
            [
                _required_float(pair.separation_beam_fwhm, "position")
                for pair in matched
            ],
            len(individual) * len(realizations),
            gate.maximum_median_position_beams,
            gate.maximum_percentile_95_position_beams,
        ),
        "peak-flux": (
            [
                abs(
                    _required_float(
                        pair.peak_flux_fractional_difference,
                        "peak flux",
                    )
                )
                for pair in matched
            ],
            len(individual) * len(realizations),
            gate.maximum_median_peak_flux_fractional_difference,
            gate.maximum_percentile_95_peak_flux_fractional_difference,
        ),
        "integrated-flux": (
            [
                abs(
                    _required_float(
                        pair.integrated_flux_fractional_difference,
                        "integrated flux",
                    )
                )
                for pair in matched
            ],
            len(individual) * len(realizations),
            gate.maximum_median_integrated_flux_fractional_difference,
            gate.maximum_percentile_95_integrated_flux_fractional_difference,
        ),
        "fitted-axis": (
            [
                float(pair.maximum_absolute_fitted_axis_fractional_difference)
                for pair in matched
                if pair.maximum_absolute_fitted_axis_fractional_difference
                is not None
            ],
            len(individual) * len(realizations),
            gate.maximum_median_fitted_axis_fractional_difference,
            gate.maximum_percentile_95_fitted_axis_fractional_difference,
        ),
        "deconvolved-axis": (
            [
                float(
                    pair.maximum_absolute_deconvolved_axis_fractional_difference
                )
                for pair in clear_matched
                if pair.maximum_absolute_deconvolved_axis_fractional_difference
                is not None
            ],
            len(clear) * len(realizations),
            gate.maximum_median_deconvolved_axis_fractional_difference,
            gate.maximum_percentile_95_deconvolved_axis_fractional_difference,
        ),
        "fitted-position-angle": (
            fitted_position_angles,
            len(fitted_position_angles),
            gate.maximum_median_position_angle_difference_degrees,
            gate.maximum_percentile_95_position_angle_difference_degrees,
        ),
        "deconvolved-position-angle": (
            deconvolved_position_angles,
            len(deconvolved_position_angles),
            gate.maximum_median_position_angle_difference_degrees,
            gate.maximum_percentile_95_position_angle_difference_degrees,
        ),
    }
    decisions: list[PhaseFourGateDecision] = []
    for identifier, (
        values,
        eligible_count,
        median_limit,
        tail_limit,
    ) in populations.items():
        observed = np.asarray(values, dtype=np.float64)
        median = float(np.median(observed)) if observed.size else None
        tail = float(np.quantile(observed, 0.95)) if observed.size else None
        decisions.extend(
            (
                _scalar_gate(
                    f"median-{identifier}",
                    median,
                    comparator="maximum",
                    threshold=median_limit,
                    eligible_count=eligible_count,
                ),
                _scalar_gate(
                    f"percentile-95-{identifier}",
                    tail,
                    comparator="maximum",
                    threshold=tail_limit,
                    eligible_count=eligible_count,
                    role=gate.absolute_tail_policy,
                ),
            )
        )
    return decisions


def _unresolved_group_gates(
    values: dict[str, FloatArray],
    counts: dict[str, FloatArray],
    gates: PhaseFourScientificGates,
) -> list[PhaseFourGateDecision]:
    """Evaluate the frozen unresolved-association-group gates."""
    group = gates.unresolved_group
    completeness_count = int(
        np.sum(counts["unresolved-group-completeness"][:, 1])
    )
    definitions = (
        (
            "unresolved-group-completeness",
            float(values["unresolved-group-completeness"][0]),
            "minimum",
            group.minimum_completeness,
        ),
        (
            "unresolved-group-median-position",
            float(values["unresolved-group-median-position"][0]),
            "maximum",
            group.maximum_median_position_beams,
        ),
        (
            "unresolved-group-position-tail",
            float(values["unresolved-group-position-tail"][0]),
            "maximum",
            group.maximum_percentile_95_position_beams,
        ),
        (
            "unresolved-group-median-total-flux",
            float(values["unresolved-group-median-total-flux"][0]),
            "maximum",
            group.maximum_median_integrated_flux_fractional_difference,
        ),
        (
            "unresolved-group-total-flux-tail",
            float(values["unresolved-group-total-flux-tail"][0]),
            "maximum",
            group.maximum_percentile_95_integrated_flux_fractional_difference,
        ),
    )
    return [
        _scalar_gate(
            identifier,
            value,
            comparator=comparator,  # type: ignore[arg-type]
            threshold=threshold,
            eligible_count=completeness_count,
        )
        for identifier, value, comparator, threshold in definitions
    ]


def _uncertainty_gate_decisions(
    realizations: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
    gates: PhaseFourScientificGates,
) -> list[PhaseFourGateDecision]:
    """Evaluate every reviewed uncertainty interval by truth stratum."""
    individual_by_source_index = {
        item.source_indices[0]: item.identifier
        for item in dataset.association_truth_groups
        if item.resolution_class == "individually-resolvable"
    }
    _, _, point, _, _ = truth_sets(dataset)
    decisions: list[PhaseFourGateDecision] = []
    uncertainty = gates.uncertainty
    for stratum in dataset.validation_strata:
        identifiers = tuple(
            individual_by_source_index[index]
            for index in stratum.source_indices
            if index in individual_by_source_index
        )
        for metric in sorted(POSITION_FLUX_METRICS):
            eligible_identifiers = tuple(
                identifier
                for identifier in identifiers
                if metric != "integrated-flux" or identifier in point
            )
            if not eligible_identifiers:
                continue
            samples: list[float] = []
            for realization in realizations:
                by_truth = {
                    item.truth_identifier: item
                    for item in realization.source_pairs
                    if item.truth_identifier is not None
                }
                for identifier in eligible_identifiers:
                    item = by_truth.get(identifier)
                    if item is None or item.decision != "matched":
                        continue
                    residuals = {
                        residual.metric: residual.value
                        for residual in item.normalized_residuals
                    }
                    if metric in residuals:
                        samples.append(residuals[metric])
            eligible_count = len(eligible_identifiers) * len(realizations)
            report = uncertainty_calibration_report(
                metric,  # type: ignore[arg-type]
                samples,
                eligible_count=eligible_count,
                confidence_level=uncertainty.confidence_interval_level,
                bootstrap_resamples=uncertainty.bootstrap_resamples,
                bootstrap_seed=uncertainty.bootstrap_seed,
            )
            prefix = f"{stratum.identifier}-{metric}-uncertainty"
            role: Literal["gate", "report-only"] = (
                "gate"
                if report.sample_count
                >= uncertainty.minimum_samples_per_stratum
                else "report-only"
            )
            decisions.extend(
                (
                    _interval_gate(
                        f"{prefix}-coverage",
                        report.coverage_fraction,
                        report.coverage_confidence_interval,
                        minimum=(
                            uncertainty.nominal_coverage
                            - uncertainty.maximum_absolute_coverage_difference
                        ),
                        maximum=(
                            uncertainty.nominal_coverage
                            + uncertainty.maximum_absolute_coverage_difference
                        ),
                        eligible_count=eligible_count,
                        role=role,
                    ),
                    _interval_gate(
                        f"{prefix}-bias",
                        report.mean_normalized_residual,
                        report.mean_confidence_interval,
                        minimum=(
                            -uncertainty.maximum_absolute_mean_normalized_residual
                        ),
                        maximum=(
                            uncertainty.maximum_absolute_mean_normalized_residual
                        ),
                        eligible_count=eligible_count,
                        role=role,
                    ),
                    _interval_gate(
                        f"{prefix}-dispersion",
                        report.sample_standard_deviation,
                        report.dispersion_confidence_interval,
                        minimum=(
                            uncertainty.minimum_normalized_residual_standard_deviation
                        ),
                        maximum=(
                            uncertainty.maximum_normalized_residual_standard_deviation
                        ),
                        eligible_count=eligible_count,
                        role=role,
                    ),
                )
            )
    return decisions


def absolute_gate_decisions(
    realizations: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
    gates: PhaseFourScientificGates,
) -> tuple[PhaseFourGateDecision, ...]:
    """Apply all existing absolute held-out science gates to Hebog."""
    if any(item.status != "success" for item in realizations):
        return ()
    counts = count_arrays(realizations, dataset)
    indices = np.arange(len(realizations), dtype=np.int64)[None, :]
    values = {
        **ratio_values(counts, indices),
        **group_values(blend_arrays(realizations, dataset), indices),
    }
    decisions = _rate_gates(values, counts, gates.heldout_qualification)
    decisions.extend(
        distribution_gate_decisions(
            realizations,
            dataset,
            gates.heldout_qualification,
        )
    )
    decisions.extend(_unresolved_group_gates(values, counts, gates))
    decisions.extend(_uncertainty_gate_decisions(realizations, dataset, gates))
    return tuple(decisions)


def stronger_hebog_envelope_decisions(
    absolute_gates: Sequence[PhaseFourGateDecision],
) -> tuple[PhaseFourEnvelopeDecision, ...]:
    """Protect every campaign-measurable stronger Hebog result by name."""
    by_identifier = {item.gate_id: item for item in absolute_gates}
    uncertainty_ids = tuple(
        sorted(
            identifier
            for identifier in by_identifier
            if identifier.endswith(
                (
                    "-uncertainty-coverage",
                    "-uncertainty-bias",
                    "-uncertainty-dispersion",
                )
            )
        )
    )
    definitions = dict(_SCIENTIFIC_ENVELOPES)
    definitions["uncertainty-availability-and-calibration"] = tuple(
        sorted(
            (
                "position-flux-uncertainty-availability",
                *uncertainty_ids,
            )
        )
    )
    decisions: list[PhaseFourEnvelopeDecision] = []
    for identifier, gate_ids in definitions.items():
        statuses = tuple(
            (
                by_identifier[gate_id].status
                if by_identifier[gate_id].role == "gate"
                else "indeterminate"
            )
            if gate_id in by_identifier
            else "indeterminate"
            for gate_id in gate_ids
        )
        status: Literal["pass", "fail", "indeterminate"]
        if "fail" in statuses:
            status = "fail"
        elif "indeterminate" in statuses:
            status = "indeterminate"
        else:
            status = "pass"
        decisions.append(
            PhaseFourEnvelopeDecision(
                envelope_id=identifier,
                absolute_gate_ids=tuple(sorted(gate_ids)),
                status=status,
            )
        )
    return tuple(decisions)


def _failure_reasons(
    outcomes: Sequence[PhaseFourImplementationOutcome],
    endpoints: Sequence[PhaseFourEndpointDecision],
    gates: Sequence[PhaseFourGateDecision],
    envelopes: Sequence[PhaseFourEnvelopeDecision],
) -> tuple[str, ...]:
    """Return stable aggregate failure reasons without hiding detail."""
    reasons = {
        f"required-implementation-failed:{item.implementation_identifier}"
        for item in outcomes
        if item.failed_seeds and item.policy == "qualification-fails"
    }
    reasons.update(
        f"paired-endpoint-{item.status}:{item.endpoint_id}"
        for item in endpoints
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
    if not endpoints:
        reasons.add("paired-endpoints-unavailable")
    if not gates:
        reasons.add("absolute-gates-unavailable")
    if not envelopes:
        reasons.add("stronger-envelopes-unavailable")
    return tuple(sorted(reasons))


def _validate_qualification_provenance(  # noqa: PLR0913
    campaign: ScientificCampaignEvidence,
    dataset: DatasetRecord,
    protocol: PairedNoninferiorityContract,
    gates: PhaseFourScientificGates,
    *,
    scientific_contract_set_sha256: str,
    implementation_identifiers: tuple[str, str, str],
) -> str:
    """Validate all frozen identities before evaluating any result."""
    if dataset.role is not DatasetRole.QUALIFICATION:
        raise ValueError("one-look evaluator requires qualification data")
    if campaign.dataset != campaign_dataset_identity(dataset):
        raise ValueError("campaign evidence and governed dataset differ")
    if len(dataset.noise_realization_seeds) != protocol.realization_count:
        raise ValueError(
            "frozen dataset and protocol realization counts differ"
        )
    if campaign.configuration_sha256 != scientific_contract_set_sha256:
        raise ValueError("campaign scientific contract set changed")
    protocol_sha256 = canonical_sha256(protocol.model_dump(mode="json"))
    if campaign.comparison_protocol_sha256 != protocol_sha256:
        raise ValueError("campaign paired protocol changed")
    if protocol.status != "reviewed" or gates.status != "reviewed-provisional":
        raise ValueError("one-look evaluator requires reviewed contracts")
    actual_implementations = {
        item.identifier for item in campaign.implementations
    }
    if actual_implementations != set(implementation_identifiers):
        raise ValueError(
            "one-look campaign must contain exactly the candidate and two "
            "reviewed references"
        )
    return protocol_sha256


def evaluate_phase_four_qualification(  # noqa: PLR0913
    campaign: ScientificCampaignEvidence,
    dataset: DatasetRecord,
    protocol: PairedNoninferiorityContract,
    gates: PhaseFourScientificGates,
    *,
    scientific_contract_set_sha256: str,
    candidate_identifier: str = "hebog",
    primary_reference_identifier: str = "pybdsf-release",
    secondary_reference_identifier: str = "pybdsf-master",
    captured_at: datetime | None = None,
) -> PhaseFourQualificationDecision:
    """Produce the single immutable final Phase 4 decision document."""
    implementation_identifiers = (
        candidate_identifier,
        primary_reference_identifier,
        secondary_reference_identifier,
    )
    protocol_sha256 = _validate_qualification_provenance(
        campaign,
        dataset,
        protocol,
        gates,
        scientific_contract_set_sha256=scientific_contract_set_sha256,
        implementation_identifiers=implementation_identifiers,
    )

    candidate = _implementation_realizations(
        campaign,
        candidate_identifier,
        role="candidate",
    )
    primary = _implementation_realizations(
        campaign,
        primary_reference_identifier,
        role="reference",
    )
    secondary = _implementation_realizations(
        campaign,
        secondary_reference_identifier,
        role="reference",
    )
    expected_seeds = dataset.noise_realization_seeds
    for identifier, realizations in (
        (candidate_identifier, candidate),
        (primary_reference_identifier, primary),
        (secondary_reference_identifier, secondary),
    ):
        if tuple(item.seed for item in realizations) != expected_seeds:
            raise ValueError(
                "implementation does not cover every frozen seed: "
                f"{identifier}"
            )

    outcomes = (
        PhaseFourImplementationOutcome(
            implementation_identifier=candidate_identifier,
            policy=protocol.reference_failures.candidate,
            failed_seeds=tuple(
                item.seed for item in candidate if item.status == "failure"
            ),
        ),
        PhaseFourImplementationOutcome(
            implementation_identifier=primary_reference_identifier,
            policy=protocol.reference_failures.primary,
            failed_seeds=tuple(
                item.seed for item in primary if item.status == "failure"
            ),
        ),
        PhaseFourImplementationOutcome(
            implementation_identifier=secondary_reference_identifier,
            policy=protocol.reference_failures.secondary,
            failed_seeds=tuple(
                item.seed for item in secondary if item.status == "failure"
            ),
        ),
    )
    endpoints = paired_endpoint_decisions(
        candidate,
        primary,
        dataset,
        protocol,
    )
    secondary_endpoints = (
        paired_endpoint_decisions(candidate, secondary, dataset, protocol)
        if all(item.status == "success" for item in secondary)
        and all(item.status == "success" for item in candidate)
        else ()
    )
    try:
        absolute_gates = absolute_gate_decisions(candidate, dataset, gates)
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
    envelopes = stronger_hebog_envelope_decisions(absolute_gates)
    reasons = _failure_reasons(outcomes, endpoints, absolute_gates, envelopes)
    return PhaseFourQualificationDecision(
        schema_version=1,
        evidence_type="phase-4-qualification-decision",
        run_id=f"{campaign.run_id}-decision",
        captured_at=captured_at or datetime.now(timezone.utc),
        status=EvidenceStatus.EXPLORATORY,
        dataset=campaign.dataset,
        configuration_sha256=campaign.configuration_sha256,
        source_campaign_run_id=campaign.run_id,
        source_campaign_sha256=canonical_sha256(
            campaign.model_dump(mode="json")
        ),
        comparison_protocol_sha256=protocol_sha256,
        scientific_gates_sha256=canonical_sha256(
            gates.model_dump(mode="json")
        ),
        candidate_identifier=candidate_identifier,
        primary_reference_identifier=primary_reference_identifier,
        secondary_reference_identifier=secondary_reference_identifier,
        implementation_outcomes=outcomes,
        paired_endpoints=endpoints,
        secondary_paired_endpoints=secondary_endpoints,
        absolute_gates=absolute_gates,
        stronger_hebog_envelopes=envelopes,
        passed=not reasons,
        failure_reasons=reasons,
    )
