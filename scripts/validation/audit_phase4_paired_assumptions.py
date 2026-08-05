"""Audit Phase 4 paired-design assumptions on governed regression evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import numpy as np

from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
    dataset_by_identifier,
)
from hebog.validation.contracts import load_paired_noninferiority_contract
from hebog.validation.evidence import (
    CampaignRealizationDiagnostic,
    ScientificCampaignEvidence,
    load_evidence,
)
from hebog.validation.noninferiority import (
    audit_planning_standard_deviation,
)
from hebog.validation.phase_four_analysis import (
    PAIRED_ENDPOINT_IDS,
    FloatArray,
    blend_arrays,
    count_arrays,
    endpoint_values,
    positive_regressions,
    uncertainty_arrays,
)

_MINIMUM_RESAMPLES = 2


def _parse_args() -> argparse.Namespace:
    """Parse immutable evidence, governed truth, and protocol paths."""
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
        raise ValueError("selected reference does not have the reference role")
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
            json.dumps(payload, allow_nan=False, indent=2, sort_keys=True)
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
        count_arrays(candidate, dataset),
        blend_arrays(candidate, dataset),
        uncertainty_arrays(candidate, dataset),
    )
    reference_inputs = (
        count_arrays(reference, dataset),
        blend_arrays(reference, dataset),
        uncertainty_arrays(reference, dataset),
    )
    endpoint_by_id = {
        item.endpoint_id: item
        for item in (
            *contract.binary_endpoints,
            *contract.continuous_endpoints,
        )
    }
    if set(endpoint_by_id) != PAIRED_ENDPOINT_IDS:
        raise ValueError(
            "paired protocol endpoint set is unsupported or incomplete"
        )

    full_indices = np.arange(realization_count, dtype=np.int64)[None, :]
    candidate_values = endpoint_values(*candidate_inputs, full_indices)
    reference_values = endpoint_values(*reference_inputs, full_indices)
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
        candidate_batch = endpoint_values(*candidate_inputs, indices)
        reference_batch = endpoint_values(*reference_inputs, indices)
        for endpoint_id, endpoint in endpoint_by_id.items():
            regressions[endpoint_id].append(
                positive_regressions(
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
