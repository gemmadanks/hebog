"""Memory-bounded summaries for large Phase 4 qualification evidence.

The compact decision engine is checksum-bound by closed Phase 5 protocols, so
this adapter deliberately reuses its internal numerical functions without
changing that file. An exact-result regression test compares this path with
the original in-memory evaluator.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
)
from hebog.validation.contracts import (
    PairedNoninferiorityContract,
    PhaseFourScientificGates,
)
from hebog.validation.datasets import (
    DatasetRecord,
    DatasetRole,
    iter_dataset_recipes,
)
from hebog.validation.evidence import (
    CampaignImplementationEvidence,
    CampaignImplementationIdentity,
    CampaignRealizationDiagnostic,
    DatasetIdentity,
    EvidenceStatus,
    PhaseFourEndpointDecision,
    PhaseFourEnvelopeDecision,
    PhaseFourGateDecision,
    PhaseFourImplementationOutcome,
    PhaseFourQualificationDecision,
)
from hebog.validation.phase_four_analysis import (
    BINARY_ENDPOINT_IDS,
    endpoint_values,
)
from hebog.validation.phase_four_decision import (
    AnalysisInputs,
    _endpoint_map,  # pyright: ignore[reportPrivateUsage]
    _failure_reasons,  # pyright: ignore[reportPrivateUsage]
    _indeterminate_endpoints,  # pyright: ignore[reportPrivateUsage]
    _inputs,  # pyright: ignore[reportPrivateUsage]
    _regression_statistic,  # pyright: ignore[reportPrivateUsage]
    absolute_gate_decisions,
    paired_bca_upper_limits,
    stronger_hebog_envelope_decisions,
)

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_QUALIFICATION_IMPLEMENTATION_COUNT = 3


def implementation_analysis_inputs(
    realizations: Sequence[CampaignRealizationDiagnostic],
    dataset: DatasetRecord,
) -> AnalysisInputs:
    """Return bounded inputs through the frozen compact decision engine."""
    return _inputs(realizations, dataset)


def paired_endpoint_decisions_from_inputs(
    candidate_inputs: AnalysisInputs,
    reference_inputs: AnalysisInputs,
    *,
    realization_count: int,
    all_realizations_succeeded: bool,
    contract: PairedNoninferiorityContract,
) -> tuple[PhaseFourEndpointDecision, ...]:
    """Apply the frozen paired rule to bounded implementation summaries."""
    if realization_count < 1:
        return _indeterminate_endpoints(contract, "no paired realizations")
    if not all_realizations_succeeded:
        return _indeterminate_endpoints(
            contract,
            "candidate or primary reference realization failed",
        )
    endpoint_by_identifier = _endpoint_map(contract)
    try:
        statistic = _regression_statistic(
            candidate_inputs,
            reference_inputs,
            endpoint_by_identifier,
        )
        indices = np.arange(realization_count, dtype=np.int64)
        point_regressions, upper_limits = paired_bca_upper_limits(
            statistic,
            realization_count=realization_count,
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
    for index, endpoint in enumerate(endpoint_by_identifier.values()):
        identifier = endpoint.endpoint_id
        candidate_value = float(candidate_values[identifier][0])
        reference_value = float(reference_values[identifier][0])
        regression = float(point_regressions[index])
        upper = float(upper_limits[index])
        point_values = (candidate_value, reference_value, regression)
        if not all(np.isfinite(value) for value in (*point_values, upper)):
            point_estimate_is_finite = all(
                np.isfinite(value) for value in point_values
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


def qualification_failure_reasons(
    outcomes: Sequence[PhaseFourImplementationOutcome],
    endpoints: Sequence[PhaseFourEndpointDecision],
    gates: Sequence[PhaseFourGateDecision],
    envelopes: Sequence[PhaseFourEnvelopeDecision],
) -> tuple[str, ...]:
    """Return reasons through the frozen compact decision engine."""
    return _failure_reasons(outcomes, endpoints, gates, envelopes)


def file_sha256(path: Path) -> str:
    """Return the SHA-256 of one file without materializing it."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_evidence_file_sha256(path: Path) -> str:
    """Hash canonical evidence JSON without presentation whitespace.

    Evidence written by :func:`hebog.validation.evidence.write_evidence` has
    sorted keys and canonical JSON tokens. Removing whitespace outside string
    literals therefore yields the same payload hashed by ``canonical_sha256``
    without materializing the complete document.
    """
    digest = hashlib.sha256()
    in_string = False
    escaped = False
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            canonical_chunk = bytearray()
            for value in chunk:
                if in_string:
                    canonical_chunk.append(value)
                    if escaped:
                        escaped = False
                    elif value == ord("\\"):
                        escaped = True
                    elif value == ord('"'):
                        in_string = False
                elif value == ord('"'):
                    in_string = True
                    canonical_chunk.append(value)
                elif value not in b" \t\r\n":
                    canonical_chunk.append(value)
            digest.update(canonical_chunk)
    if in_string or escaped:
        raise ValueError("canonical evidence JSON ends inside a string")
    return digest.hexdigest()


class PhaseFourImplementationSummary(BaseModel):
    """Bounded numerical state retained after one implementation is loaded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    source_run_id: str
    source_shard_sha256: str = Field(pattern=_SHA256_PATTERN)
    captured_at: datetime
    status: EvidenceStatus
    dataset: DatasetIdentity
    configuration_sha256: str = Field(pattern=_SHA256_PATTERN)
    comparison_protocol_sha256: str = Field(pattern=_SHA256_PATTERN)
    scientific_gates_sha256: str = Field(pattern=_SHA256_PATTERN)
    implementation: CampaignImplementationIdentity
    seeds: tuple[int, ...]
    failed_seeds: tuple[int, ...] = ()
    counts: dict[str, tuple[tuple[float, float], ...]]
    blends: dict[str, tuple[tuple[float, ...], ...]]
    uncertainties: tuple[tuple[tuple[float, float, float, float], ...], ...]
    absolute_gates: tuple[PhaseFourGateDecision, ...] = ()

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        """Require complete, aligned implementation summaries."""
        if self.seeds != tuple(sorted(set(self.seeds))):
            raise ValueError("summary seeds must be unique and sorted")
        canonical_failures = tuple(sorted(set(self.failed_seeds)))
        failures_are_known = set(self.failed_seeds).issubset(self.seeds)
        if self.failed_seeds != canonical_failures or not failures_are_known:
            raise ValueError("summary failed seeds must be a subset of seeds")
        if frozenset(self.counts) != BINARY_ENDPOINT_IDS:
            raise ValueError("summary binary endpoint set is incomplete")
        if set(self.blends) != {"position", "total-flux"}:
            raise ValueError("summary blend endpoint set is incomplete")
        row_counts = {
            *(len(rows) for rows in self.counts.values()),
            *(len(rows) for rows in self.blends.values()),
            len(self.uncertainties),
        }
        if row_counts != {len(self.seeds)}:
            raise ValueError("summary arrays and seeds differ in length")
        if self.implementation.role == "reference" and self.absolute_gates:
            raise ValueError("reference summary cannot contain absolute gates")
        return self

    def analysis_inputs(self) -> AnalysisInputs:
        """Return NumPy views accepted by the paired decision evaluator."""
        return (
            {
                identifier: np.asarray(rows, dtype=np.float64)
                for identifier, rows in self.counts.items()
            },
            {
                identifier: np.asarray(rows, dtype=np.float64)
                for identifier, rows in self.blends.items()
            },
            np.asarray(self.uncertainties, dtype=np.float64),
        )


def _matrix(
    values: np.ndarray,
) -> tuple[tuple[float, ...], ...]:
    """Convert one bounded two-dimensional array to immutable JSON values."""
    return tuple(tuple(float(value) for value in row) for row in values)


def _cube(
    values: np.ndarray,
) -> tuple[tuple[tuple[float, ...], ...], ...]:
    """Convert one bounded three-dimensional array to immutable JSON values."""
    return tuple(_matrix(plane) for plane in values)


def summarize_phase_four_implementation(
    shard: CampaignImplementationEvidence,
    dataset: DatasetRecord,
    gates: PhaseFourScientificGates,
    *,
    source_shard_sha256: str,
) -> PhaseFourImplementationSummary:
    """Reduce one fully validated implementation shard to bounded state."""
    if shard.dataset != campaign_dataset_identity(dataset):
        raise ValueError("implementation shard and governed dataset differ")
    expected_seeds = tuple(
        recipe.seed for recipe in iter_dataset_recipes(dataset)
    )
    seeds = tuple(item.seed for item in shard.realizations)
    if seeds != expected_seeds:
        raise ValueError("implementation shard does not cover frozen seeds")
    counts, blends, uncertainties = implementation_analysis_inputs(
        shard.realizations,
        dataset,
    )
    candidate_gates = (
        absolute_gate_decisions(shard.realizations, dataset, gates)
        if shard.implementation.role == "candidate"
        else ()
    )
    return PhaseFourImplementationSummary(
        source_run_id=shard.run_id,
        source_shard_sha256=source_shard_sha256,
        captured_at=shard.captured_at,
        status=shard.status,
        dataset=shard.dataset,
        configuration_sha256=shard.configuration_sha256,
        comparison_protocol_sha256=shard.comparison_protocol_sha256,
        scientific_gates_sha256=canonical_sha256(
            gates.model_dump(mode="json")
        ),
        implementation=shard.implementation,
        seeds=seeds,
        failed_seeds=tuple(
            item.seed
            for item in shard.realizations
            if item.status == "failure"
        ),
        counts={
            identifier: _matrix(values)  # type: ignore[arg-type]
            for identifier, values in counts.items()
        },
        blends={
            identifier: _matrix(values)
            for identifier, values in blends.items()
        },
        uncertainties=_cube(uncertainties),  # type: ignore[arg-type]
        absolute_gates=candidate_gates,
    )


def write_implementation_summary(
    path: Path,
    summary: PhaseFourImplementationSummary,
) -> None:
    """Write one bounded summary atomically without overwriting it."""
    if path.exists():
        raise FileExistsError(f"refusing to overwrite summary: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(
            summary.model_dump(mode="json"),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_implementation_summary(path: Path) -> PhaseFourImplementationSummary:
    """Load and validate one bounded implementation summary."""
    return PhaseFourImplementationSummary.model_validate_json(
        path.read_text(encoding="utf-8")
    )


@dataclass(frozen=True)
class _EvaluationContext:
    """Frozen provenance expected by one bounded decision."""

    dataset: DatasetRecord
    protocol: PairedNoninferiorityContract
    gates: PhaseFourScientificGates
    scientific_contract_set_sha256: str
    implementation_identifiers: tuple[str, str, str]


def _validate_contracts(context: _EvaluationContext) -> tuple[str, str]:
    """Validate the reviewed dataset and return contract digests."""
    if context.dataset.role is not DatasetRole.QUALIFICATION:
        raise ValueError("one-look evaluator requires qualification data")
    if (
        len(iter_dataset_recipes(context.dataset))
        != context.protocol.realization_count
    ):
        raise ValueError(
            "frozen dataset and protocol realization counts differ"
        )
    if (
        context.protocol.status != "reviewed"
        or context.gates.status != "reviewed-provisional"
    ):
        raise ValueError("one-look evaluator requires reviewed contracts")
    return (
        canonical_sha256(context.protocol.model_dump(mode="json")),
        canonical_sha256(context.gates.model_dump(mode="json")),
    )


def _validate_summary(
    summary: PhaseFourImplementationSummary,
    candidate: PhaseFourImplementationSummary,
    context: _EvaluationContext,
    *,
    protocol_sha256: str,
    gates_sha256: str,
) -> None:
    """Validate one summary against its candidate and frozen contracts."""
    if summary.dataset != campaign_dataset_identity(context.dataset):
        raise ValueError("summary and governed dataset differ")
    if summary.configuration_sha256 != context.scientific_contract_set_sha256:
        raise ValueError("summary scientific contract set changed")
    if summary.comparison_protocol_sha256 != protocol_sha256:
        raise ValueError("summary paired protocol changed")
    if summary.scientific_gates_sha256 != gates_sha256:
        raise ValueError("summary scientific gates changed")
    if summary.seeds != candidate.seeds:
        raise ValueError("summary seed populations differ")


def _validated_summaries(
    summaries: Sequence[PhaseFourImplementationSummary],
    context: _EvaluationContext,
) -> tuple[
    PhaseFourImplementationSummary,
    PhaseFourImplementationSummary,
    PhaseFourImplementationSummary,
]:
    """Validate bounded summary provenance before evaluating science."""
    if len(summaries) != _QUALIFICATION_IMPLEMENTATION_COUNT:
        raise ValueError("bounded evaluation requires exactly three summaries")
    candidate, primary, secondary = summaries
    protocol_sha256, gates_sha256 = _validate_contracts(context)
    for summary in summaries:
        _validate_summary(
            summary,
            candidate,
            context,
            protocol_sha256=protocol_sha256,
            gates_sha256=gates_sha256,
        )
    if (
        tuple(summary.implementation.identifier for summary in summaries)
        != context.implementation_identifiers
    ):
        raise ValueError("bounded summaries have unexpected implementations")
    if (
        candidate.implementation.role != "candidate"
        or primary.implementation.role != "reference"
        or secondary.implementation.role != "reference"
    ):
        raise ValueError("bounded summary implementation roles differ")
    return candidate, primary, secondary


def evaluate_phase_four_qualification_summaries(  # noqa: PLR0913
    summaries: Sequence[PhaseFourImplementationSummary],
    dataset: DatasetRecord,
    protocol: PairedNoninferiorityContract,
    gates: PhaseFourScientificGates,
    *,
    scientific_contract_set_sha256: str,
    source_campaign_run_id: str,
    source_campaign_sha256: str,
    candidate_identifier: str = "hebog",
    primary_reference_identifier: str = "pybdsf-release",
    secondary_reference_identifier: str = "pybdsf-master",
    captured_at: datetime | None = None,
) -> PhaseFourQualificationDecision:
    """Produce the Phase 4 decision from sequential bounded summaries."""
    identifiers = (
        candidate_identifier,
        primary_reference_identifier,
        secondary_reference_identifier,
    )
    candidate, primary, secondary = _validated_summaries(
        summaries,
        _EvaluationContext(
            dataset=dataset,
            protocol=protocol,
            gates=gates,
            scientific_contract_set_sha256=scientific_contract_set_sha256,
            implementation_identifiers=identifiers,
        ),
    )
    outcomes = (
        PhaseFourImplementationOutcome(
            implementation_identifier=candidate_identifier,
            policy=protocol.reference_failures.candidate,
            failed_seeds=candidate.failed_seeds,
        ),
        PhaseFourImplementationOutcome(
            implementation_identifier=primary_reference_identifier,
            policy=protocol.reference_failures.primary,
            failed_seeds=primary.failed_seeds,
        ),
        PhaseFourImplementationOutcome(
            implementation_identifier=secondary_reference_identifier,
            policy=protocol.reference_failures.secondary,
            failed_seeds=secondary.failed_seeds,
        ),
    )
    endpoints = paired_endpoint_decisions_from_inputs(
        candidate.analysis_inputs(),
        primary.analysis_inputs(),
        realization_count=len(candidate.seeds),
        all_realizations_succeeded=not (
            candidate.failed_seeds or primary.failed_seeds
        ),
        contract=protocol,
    )
    secondary_endpoints = (
        paired_endpoint_decisions_from_inputs(
            candidate.analysis_inputs(),
            secondary.analysis_inputs(),
            realization_count=len(candidate.seeds),
            all_realizations_succeeded=True,
            contract=protocol,
        )
        if not candidate.failed_seeds and not secondary.failed_seeds
        else ()
    )
    absolute_gates = candidate.absolute_gates
    envelopes = stronger_hebog_envelope_decisions(absolute_gates)
    reasons = qualification_failure_reasons(
        outcomes,
        endpoints,
        absolute_gates,
        envelopes,
    )
    return PhaseFourQualificationDecision(
        schema_version=1,
        evidence_type="phase-4-qualification-decision",
        run_id=f"{source_campaign_run_id}-decision",
        captured_at=captured_at or datetime.now(timezone.utc),
        status=EvidenceStatus.EXPLORATORY,
        dataset=candidate.dataset,
        configuration_sha256=candidate.configuration_sha256,
        source_campaign_run_id=source_campaign_run_id,
        source_campaign_sha256=source_campaign_sha256,
        comparison_protocol_sha256=canonical_sha256(
            protocol.model_dump(mode="json")
        ),
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
