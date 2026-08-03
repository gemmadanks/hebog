"""Audit Phase 4 paired-design assumptions on governed regression evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import numpy as np
import numpy.typing as npt

from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
    dataset_by_identifier,
)
from hebog.validation.contracts import load_paired_noninferiority_contract
from hebog.validation.datasets import DatasetRecord
from hebog.validation.evidence import (
    CampaignRealizationDiagnostic,
    ScientificCampaignEvidence,
    load_evidence,
)
from hebog.validation.noninferiority import (
    PairedEndpoint,
    audit_planning_standard_deviation,
)

_POSITION_FLUX_METRICS = frozenset(
    {"right-ascension", "declination", "peak-flux", "integrated-flux"}
)
_BINARY_ENDPOINT_IDS = frozenset(
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
_GROUP_ENDPOINT_IDS = frozenset(
    {
        "unresolved-group-median-position",
        "unresolved-group-position-tail",
        "unresolved-group-median-total-flux",
        "unresolved-group-total-flux-tail",
    }
)
_UNCERTAINTY_ENDPOINT_IDS = frozenset(
    {
        "uncertainty-normalized-bias",
        "uncertainty-one-sigma-coverage",
        "uncertainty-normalized-dispersion",
    }
)
_MINIMUM_RESAMPLES = 2

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
CountArrays = dict[str, FloatArray]
UncertaintyArrays = FloatArray


def _parse_args() -> argparse.Namespace:
    """Parse immutable evidence, governed truth, and draft protocol paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--candidate-id", default="hebog")
    parser.add_argument("--reference-id", default="pybdsf-release")
    parser.add_argument("--resamples", type=int)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _campaign(path: Path) -> ScientificCampaignEvidence:
    """Load one compiled campaign and reject an implementation shard."""
    evidence = load_evidence(path)
    if not isinstance(evidence, ScientificCampaignEvidence):
        raise TypeError(f"not compiled scientific campaign evidence: {path}")
    return evidence


def _paired_realizations(
    campaign: ScientificCampaignEvidence,
    *,
    candidate_identifier: str,
    reference_identifier: str,
) -> tuple[
    tuple[CampaignRealizationDiagnostic, ...],
    tuple[CampaignRealizationDiagnostic, ...],
]:
    """Return ordered, complete candidate and reference realizations."""
    identities = {item.identifier: item for item in campaign.implementations}
    if candidate_identifier not in identities:
        raise ValueError(f"candidate is absent: {candidate_identifier}")
    if identities[candidate_identifier].role != "candidate":
        raise ValueError("selected candidate does not have the candidate role")
    if reference_identifier not in identities:
        raise ValueError(f"reference is absent: {reference_identifier}")
    if identities[reference_identifier].role != "reference":
        raise ValueError("selected reference does not have a reference role")
    by_identifier = {
        identifier: tuple(
            realization
            for realization in campaign.realizations
            if realization.implementation_identifier == identifier
        )
        for identifier in (candidate_identifier, reference_identifier)
    }
    candidate = by_identifier[candidate_identifier]
    reference = by_identifier[reference_identifier]
    if tuple(item.seed for item in candidate) != tuple(
        item.seed for item in reference
    ):
        raise ValueError("candidate and reference realization seeds differ")
    failures = [
        f"{item.implementation_identifier}:{item.seed}"
        for item in (*candidate, *reference)
        if item.status != "success"
    ]
    if failures:
        raise ValueError(
            "planning audit requires complete regression realizations: "
            + ", ".join(failures)
        )
    return candidate, reference


def _truth_sets(
    dataset: DatasetRecord,
) -> tuple[set[str], set[str], set[str], set[str], set[str]]:
    """Return group, individual, point, and clear truth identifiers."""
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
    point = classifications["shape-unresolved"]
    clear = classifications["shape-clear-resolved"]
    blend = all_groups - individual
    return all_groups, individual, point, clear, blend


def _count_row(
    realization: CampaignRealizationDiagnostic,
    dataset: DatasetRecord,
) -> dict[str, tuple[float, float]]:
    """Return aggregate binary numerators and denominators for one image."""
    all_groups, individual, point, clear, blend = _truth_sets(dataset)
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

    def agrees(identifiers: set[str]) -> int:
        return sum(
            source_by_truth.get(identifier) is not None
            and source_by_truth[identifier].decision == "matched"
            and source_by_truth[identifier].classification_agrees is True
            for identifier in identifiers
        )

    return {
        "compact-completeness": (
            float(len(association_matches & all_groups)),
            float(len(all_groups)),
        ),
        "catalogue-reliability": (
            float(len(association_matches)),
            float(realization.candidate_count),
        ),
        "association-pair-precision": (
            float(len(association_matches)),
            float(realization.candidate_count),
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
                    _POSITION_FLUX_METRICS.issubset(
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
            float(agrees(point)),
            float(len(point)),
        ),
        "clear-resolved-classification-recall": (
            float(agrees(clear)),
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


def _count_arrays(
    realizations: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
) -> CountArrays:
    """Stack binary counts with numerator and denominator columns."""
    rows = [_count_row(item, dataset) for item in realizations]
    return {
        endpoint_id: np.asarray(
            [row[endpoint_id] for row in rows], dtype=np.float64
        )
        for endpoint_id in _BINARY_ENDPOINT_IDS
    }


def _blend_arrays(
    realizations: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
) -> dict[str, FloatArray]:
    """Return complete per-image unresolved-group error arrays."""
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
                raise ValueError(
                    "unresolved-group endpoint requires every group match"
                )
            position_row.append(abs(item.separation_beam_fwhm))
            flux_row.append(abs(item.integrated_flux_fractional_difference))
        position.append(position_row)
        flux.append(flux_row)
    return {
        "position": np.asarray(position, dtype=np.float64),
        "total-flux": np.asarray(flux, dtype=np.float64),
    }


def _uncertainty_arrays(
    realizations: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
) -> UncertaintyArrays:
    """Return per-image sum, sum-square, count, and coverage summaries."""
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
    _, _, point, _, _ = _truth_sets(dataset)
    identifiers_by_key = {
        (stratum, metric): tuple(
            identifier
            for identifier in identifiers
            if metric != "integrated-flux" or identifier in point
        )
        for stratum, identifiers in strata.items()
        for metric in sorted(_POSITION_FLUX_METRICS)
    }
    collected: dict[tuple[str, str], list[list[float]]] = {
        (stratum, metric): []
        for (stratum, metric), identifiers in identifiers_by_key.items()
        if identifiers
    }
    for realization in realizations:
        by_truth = {
            item.truth_identifier: item
            for item in realization.source_pairs
            if item.truth_identifier is not None
        }
        for key, identifiers in identifiers_by_key.items():
            if key not in collected:
                continue
            values: list[float] = []
            metric = key[1]
            for identifier in identifiers:
                item = by_truth.get(identifier)
                if item is None or item.decision != "matched":
                    raise ValueError(
                        "uncertainty endpoint requires every source match"
                    )
                residuals = {
                    residual.metric: residual.value
                    for residual in item.normalized_residuals
                }
                if not _POSITION_FLUX_METRICS.issubset(residuals):
                    raise ValueError(
                        "uncertainty endpoint requires all position/flux "
                        "errors"
                    )
                values.append(residuals[metric])
            collected[key].append(values)
    keys = sorted(collected)
    summaries = np.empty(
        (len(realizations), len(keys), 4),
        dtype=np.float64,
    )
    for key_index, key in enumerate(keys):
        values = np.asarray(collected[key], dtype=np.float64)
        summaries[:, key_index, 0] = np.sum(values, axis=1)
        summaries[:, key_index, 1] = np.sum(values**2, axis=1)
        summaries[:, key_index, 2] = values.shape[1]
        summaries[:, key_index, 3] = np.sum(np.abs(values) <= 1.0, axis=1)
    return summaries


def _ratio_values(
    arrays: CountArrays,
    indices: IntArray,
) -> dict[str, FloatArray]:
    """Calculate aggregate binary rates for every bootstrap sample."""
    return {
        endpoint_id: np.sum(values[indices, 0], axis=1)
        / np.sum(values[indices, 1], axis=1)
        for endpoint_id, values in arrays.items()
    }


def _group_values(
    arrays: dict[str, FloatArray],
    indices: IntArray,
) -> dict[str, FloatArray]:
    """Calculate aggregate median and 95th-percentile blend errors."""
    position = arrays["position"][indices].reshape(indices.shape[0], -1)
    flux = arrays["total-flux"][indices].reshape(indices.shape[0], -1)
    return {
        "unresolved-group-median-position": np.median(position, axis=1),
        "unresolved-group-position-tail": np.quantile(position, 0.95, axis=1),
        "unresolved-group-median-total-flux": np.median(flux, axis=1),
        "unresolved-group-total-flux-tail": np.quantile(flux, 0.95, axis=1),
    }


def _uncertainty_values(
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


def _endpoint_values(
    counts: CountArrays,
    blends: dict[str, FloatArray],
    uncertainties: UncertaintyArrays,
    indices: IntArray,
) -> dict[str, FloatArray]:
    """Calculate all aggregate endpoint values for selected image clusters."""
    return {
        **_ratio_values(counts, indices),
        **_group_values(blends, indices),
        **_uncertainty_values(uncertainties, indices),
    }


def _positive_regressions(
    endpoint: PairedEndpoint,
    candidate: FloatArray,
    reference: FloatArray,
) -> FloatArray:
    """Normalize vector endpoints so positive means candidate regression."""
    if endpoint.desirable_direction == "higher-is-better":
        return reference - candidate
    if endpoint.desirable_direction == "lower-is-better":
        return candidate - reference
    assert endpoint.ideal_value is not None
    return np.abs(candidate - endpoint.ideal_value) - np.abs(
        reference - endpoint.ideal_value
    )


def _write_json(path: Path, payload: object) -> None:
    """Publish canonical JSON without exposing a partial audit."""
    if path.exists():
        raise FileExistsError(
            f"refusing to overwrite assumption audit: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(
                payload,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    """Run the deterministic whole-image planning-assumption audit."""
    arguments = _parse_args()
    campaign = _campaign(arguments.campaign)
    dataset = dataset_by_identifier(arguments.manifest, arguments.dataset_id)
    if campaign.dataset != campaign_dataset_identity(dataset):
        raise ValueError("campaign evidence and governed dataset differ")
    contract = load_paired_noninferiority_contract(arguments.protocol)
    candidate, reference = _paired_realizations(
        campaign,
        candidate_identifier=arguments.candidate_id,
        reference_identifier=arguments.reference_id,
    )
    realization_count = len(candidate)
    resample_count = arguments.resamples or contract.resampling.resamples
    if resample_count < _MINIMUM_RESAMPLES:
        raise ValueError("planning audit requires at least two resamples")

    candidate_inputs = (
        _count_arrays(candidate, dataset),
        _blend_arrays(candidate, dataset),
        _uncertainty_arrays(candidate, dataset),
    )
    reference_inputs = (
        _count_arrays(reference, dataset),
        _blend_arrays(reference, dataset),
        _uncertainty_arrays(reference, dataset),
    )
    endpoint_by_id = {
        item.endpoint_id: item
        for item in (
            *contract.binary_endpoints,
            *contract.continuous_endpoints,
        )
    }
    expected_ids = (
        _BINARY_ENDPOINT_IDS | _GROUP_ENDPOINT_IDS | _UNCERTAINTY_ENDPOINT_IDS
    )
    if set(endpoint_by_id) != expected_ids:
        raise ValueError(
            "paired protocol endpoint set is unsupported or incomplete"
        )

    full_indices = np.arange(realization_count, dtype=np.int64)[None, :]
    candidate_values = _endpoint_values(*candidate_inputs, full_indices)
    reference_values = _endpoint_values(*reference_inputs, full_indices)
    regressions: dict[str, list[FloatArray]] = {
        endpoint_id: [] for endpoint_id in endpoint_by_id
    }
    generator = np.random.default_rng(contract.resampling.seed)
    remaining = resample_count
    while remaining:
        batch_size = min(500, remaining)
        indices = generator.integers(
            0,
            realization_count,
            size=(batch_size, realization_count),
            dtype=np.int64,
        )
        candidate_batch = _endpoint_values(*candidate_inputs, indices)
        reference_batch = _endpoint_values(*reference_inputs, indices)
        for endpoint_id, endpoint in endpoint_by_id.items():
            regressions[endpoint_id].append(
                _positive_regressions(
                    endpoint,
                    candidate_batch[endpoint_id],
                    reference_batch[endpoint_id],
                )
            )
        remaining -= batch_size

    estimates = tuple(
        audit_planning_standard_deviation(
            endpoint,
            candidate_value=float(candidate_values[endpoint_id][0]),
            reference_value=float(reference_values[endpoint_id][0]),
            bootstrap_regressions=np.concatenate(regressions[endpoint_id]),
            realization_count=realization_count,
        )
        for endpoint_id, endpoint in endpoint_by_id.items()
    )
    evaluated_protocol_sha256 = canonical_sha256(
        contract.model_dump(mode="json")
    )
    payload = {
        "all_planning_bounds_verified": all(
            item.planning_bound_verified for item in estimates
        ),
        "candidate_identifier": arguments.candidate_id,
        "dataset_content_sha256": campaign.dataset.content_sha256,
        "dataset_identifier": campaign.dataset.identifier,
        "evaluated_protocol_sha256": evaluated_protocol_sha256,
        "evidence_type": "phase-4-paired-planning-assumption-audit",
        "estimates": [asdict(item) for item in estimates],
        "protocol_revised_since_evidence_capture": (
            campaign.comparison_protocol_sha256 != evaluated_protocol_sha256
        ),
        "realization_count": realization_count,
        "reference_identifier": arguments.reference_id,
        "resamples": resample_count,
        "run_id": f"{campaign.run_id}-planning-assumption-audit",
        "schema_version": 1,
        "source_campaign_run_id": campaign.run_id,
        "source_comparison_protocol_sha256": (
            campaign.comparison_protocol_sha256
        ),
        "status": "exploratory",
    }
    _write_json(arguments.output, payload)


if __name__ == "__main__":
    main()
