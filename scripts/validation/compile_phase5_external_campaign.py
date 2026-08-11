#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
"""Compile sealed Phase 5 finder products into frozen scientific evidence.

The compiler is the only boundary permitted to interpret the terminal raw
campaign.  It verifies the sealed request, input bundles, result manifests,
and every artifact before deriving truth populations.  It then performs
truth-first continuum association and delegates compact catalogue decisions
to the reviewed Phase 4R engine.  It never changes a finder product and never
opens an endpoint that is absent from the checksum-bound registry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import hypot
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS

from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
    contract_set_sha256,
    phase_four_outlier_thresholds,
)
from hebog.validation.campaigns import diagnose_phase_four_realization
from hebog.validation.contracts import (
    load_paired_noninferiority_contract,
    load_phase_five_corrective_a_review,
    load_phase_four_metric_registry,
    load_phase_four_scientific_gates,
)
from hebog.validation.datasets import (
    DatasetRecord,
    SyntheticRecipe,
    iter_dataset_recipes,
    load_dataset_manifest,
)
from hebog.validation.evidence import (
    CampaignFailure,
    CampaignImplementationIdentity,
    CampaignRealizationDiagnostic,
    EvidenceStatus,
    ScientificCampaignEvidence,
    SoftwareIdentity,
)
from hebog.validation.external_comparison import (
    AssociationObject,
    match_truth_to_finder,
)
from hebog.validation.external_runners import (
    ExternalRunResult,
    file_sha256,
    load_external_run_result,
)
from hebog.validation.materialization import (
    ExternalInputBundle,
    load_external_input_bundle,
)
from hebog.validation.phase_five_astrometry_follow_up import (
    cluster_bootstrap_absolute_mean,
)
from hebog.validation.phase_five_astrometry_review import (
    BootstrapDesign,
    _reference_position,
    cluster_bootstrap_statistic,
)
from hebog.validation.phase_five_filter_review import _build_generated_truth
from hebog.validation.phase_four_decision import paired_bca_upper_limits
from hebog.validation.phase_four_recovery import (
    _metric_keys,
    _truth_index,
    evaluate_phase_four_recovery,
)
from hebog.validation.products import (
    load_aegean_catalogue,
    load_comparison_catalogue,
    load_fits_plane,
    load_pybdsf_catalogue,
    load_pybdsf_gaussian_catalogue,
)

_LAUNCHER = runpy.run_path(
    str(
        Path(__file__).parents[1] / "benchmark/run_phase5_external_campaign.py"
    )
)
CampaignRequest = _LAUNCHER["CampaignRequest"]
CampaignRunRequest = _LAUNCHER["CampaignRunRequest"]
TerminalCampaignResult = _LAUNCHER["TerminalCampaignResult"]

FinderStatus = Literal["success", "failed", "unavailable"]
Direction = Literal["higher-is-better", "lower-is-better"]
PositionPopulation = Literal[
    "not-applicable",
    "compact-component",
    "irregular-segment",
]
ValueKind = Literal[
    "image-scalar",
    "group-values",
    "signed-group-values",
]
Statistic = Literal["mean", "median", "percentile-95", "absolute-mean"]
AbsoluteDecisionStatistic = Literal[
    "point-estimate",
    "one-sided-95-percent-upper-confidence-limit",
]
_MINIMUM_PAIRED_IMAGES = 2


@dataclass(frozen=True, slots=True)
class ContinuumEndpointSpec:
    """One prospectively expanded continuum endpoint identity."""

    endpoint_id: str
    metric_family: str
    stratum: str
    value_kind: ValueKind
    statistic: Statistic
    position_population: PositionPopulation
    binding: bool
    paired: bool = True


@dataclass(frozen=True, slots=True)
class EndpointObservation:
    """One image cluster's values or retained unavailable state."""

    image_key: str
    values: tuple[float, ...] = ()
    status: FinderStatus = "success"
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ContinuumTruthObject:
    """One prospectively declared injected continuum truth group."""

    identifier: str
    support_label: int
    centre_xy: tuple[float, float]
    integrated_flux_jy: float
    catalogue_role: Literal["astronomical-source", "artifact"]
    strata: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContinuumCandidateObject:
    """One finder catalogue row linked to its native support label."""

    identifier: str
    support_label: int
    centre_xy: tuple[float, float]
    integrated_flux_jy: float


@dataclass(frozen=True, slots=True)
class CompiledReferenceComparison:
    """Paired whole-image evidence for one frozen reference."""

    reference_id: str
    status: FinderStatus
    reference_value: float | None
    positive_regression: float | None
    upper_confidence_limit: float | None
    observed_paired_standard_deviation: float | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CompiledContinuumEndpoint:
    """Candidate absolute evidence and all binding paired comparisons."""

    endpoint_id: str
    lane: Literal["continuum"]
    metric_family: str
    stratum: str
    position_population: PositionPopulation
    image_count: int
    candidate_status: FinderStatus
    candidate_value: float | None
    absolute_decision_value: float | None
    comparisons: tuple[CompiledReferenceComparison, ...]
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class VerifiedRun:
    """One checksum-verified terminal finder result and request."""

    request: CampaignRunRequest
    result: ExternalRunResult
    directory: Path


@dataclass(frozen=True, slots=True)
class VerifiedTerminalCampaign:
    """Complete sealed campaign inputs made available to science code."""

    root: Path
    request: CampaignRequest
    terminal: TerminalCampaignResult
    campaign_sha256: str
    inputs: dict[str, tuple[ExternalInputBundle, Path]]
    runs: dict[tuple[str, str, str], VerifiedRun]


def _file_sha256(path: Path) -> str:
    """Hash one potentially large file without retaining it in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    """Return deterministic finite JSON with one final newline."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _json_object(path: Path) -> dict[str, Any]:
    """Load one strict JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, Any], value)


def _require_bound_file(
    root: Path,
    document: dict[str, Any],
    *,
    path_key: str,
    sha_key: str,
    description: str,
) -> None:
    """Verify one registry-bound repository input."""
    relative = document.get(path_key)
    expected = document.get(sha_key)
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise ValueError(f"{description} identity is incomplete")
    if _file_sha256(root / relative) != expected:
        raise ValueError(f"{description} checksum changed")


def load_endpoint_registry(
    registry_path: Path, compiler_path: Path
) -> dict[str, Any]:
    """Load the exact prospective registry and verify all identities."""
    registry = _json_object(registry_path)
    if (
        registry.get("schema_version") != 1
        or registry.get("registry_id") != "phase-5-external-endpoint-registry"
        or registry.get("status") != "frozen-before-campaign-output"
    ):
        raise ValueError("external endpoint registry identity is invalid")
    if registry.get("compiler_path") != (
        "scripts/validation/compile_phase5_external_campaign.py"
    ):
        raise ValueError("external endpoint compiler path changed")
    if registry.get("compiler_sha256") != _file_sha256(compiler_path):
        raise ValueError("external endpoint compiler checksum changed")
    root = compiler_path.parents[2]
    for path_key, sha_key, description in (
        ("protocol_path", "protocol_sha256", "external protocol"),
        (
            "continuum_manifest_path",
            "continuum_manifest_sha256",
            "continuum manifest",
        ),
        (
            "compact_manifest_path",
            "compact_manifest_sha256",
            "compact manifest",
        ),
        (
            "phase_four_registry_path",
            "phase_four_registry_sha256",
            "Phase 4R metric registry",
        ),
        (
            "phase_four_gates_path",
            "phase_four_gates_sha256",
            "Phase 4 scientific gates",
        ),
        (
            "phase_four_protocol_path",
            "phase_four_protocol_sha256",
            "Phase 4 paired protocol",
        ),
        (
            "phase_four_measurement_path",
            "phase_four_measurement_sha256",
            "Phase 4 measurement contract",
        ),
        (
            "phase_five_review_path",
            "phase_five_review_sha256",
            "Phase 5 candidate review",
        ),
        (
            "execution_decision_path",
            "execution_decision_sha256",
            "external execution decision",
        ),
        (
            "launcher_path",
            "launcher_sha256",
            "complete-population launcher",
        ),
    ):
        _require_bound_file(
            root,
            registry,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    specifications = expand_continuum_endpoint_specs(registry)
    declared = registry.get("expanded_continuum_counts")
    observed = {
        "binding": sum(item.binding for item in specifications),
        "report_only": sum(not item.binding for item in specifications),
        "total": len(specifications),
    }
    if declared != observed:
        raise ValueError("expanded continuum endpoint counts changed")
    _validate_compact_endpoint_derivation(registry, root)
    return registry


def _endpoint_id(metric_family: str, stratum: str) -> str:
    """Return one stable unambiguous continuum endpoint identity."""
    return f"continuum--{metric_family}--{stratum}"


def expand_continuum_endpoint_specs(
    registry: dict[str, Any],
) -> tuple[ContinuumEndpointSpec, ...]:
    """Expand the closed rule matrix into every exact endpoint identity."""
    rows = registry.get("continuum")
    if not isinstance(rows, list):
        raise ValueError("continuum endpoint rule matrix is absent")
    output: list[ContinuumEndpointSpec] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("continuum endpoint rule is malformed")
        strata = row.get("strata")
        if not isinstance(strata, list) or not strata:
            raise ValueError("continuum endpoint strata are absent")
        for stratum in strata:
            if not isinstance(stratum, str):
                raise ValueError("continuum endpoint stratum is malformed")
            output.append(
                ContinuumEndpointSpec(
                    endpoint_id=_endpoint_id(row["metric_family"], stratum),
                    metric_family=row["metric_family"],
                    stratum=stratum,
                    value_kind=row["value_kind"],
                    statistic=row["statistic"],
                    position_population=row["position_population"],
                    binding=row["role"] == "binding",
                    paired=row.get("paired", True),
                )
            )
    identifiers = [item.endpoint_id for item in output]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("continuum endpoint identities are not unique")
    return tuple(output)


def _derived_compact_endpoint_keys(
    registry: dict[str, Any], repository_root: Path
) -> tuple[tuple[str, str], ...]:
    """Derive exact Phase 4R metric/stratum keys from bound contracts."""
    manifest = load_dataset_manifest(
        repository_root / registry["compact_manifest_path"]
    )
    if len(manifest.datasets) != 1:
        raise ValueError("compact external manifest must contain one dataset")
    phase_four_registry = load_phase_four_metric_registry(
        repository_root / registry["phase_four_registry_path"]
    )
    truth = _truth_index(manifest.datasets[0])
    return tuple(
        (metric.metric_id, stratum)
        for metric, stratum, _ in _metric_keys(phase_four_registry, truth)
    )


def _validate_compact_endpoint_derivation(
    registry: dict[str, Any], repository_root: Path
) -> None:
    """Check declared compact counts against exact prospective expansion."""
    compact = registry.get("compact")
    if not isinstance(compact, dict):
        raise ValueError("compact endpoint policy is absent")
    endpoint_keys = _derived_compact_endpoint_keys(registry, repository_root)
    if len(endpoint_keys) != len(set(endpoint_keys)):
        raise ValueError("derived Phase 4R endpoint identities are duplicated")
    if len(endpoint_keys) != compact.get(
        "pybdsf_expected_endpoint_count_per_reference"
    ):
        raise ValueError("derived Phase 4R endpoint population changed")
    applicable = set(compact.get("aegean_applicable_metric_ids", ()))
    aegean_keys = tuple(key for key in endpoint_keys if key[0] in applicable)
    if len(aegean_keys) != compact.get("aegean_expected_endpoint_count"):
        raise ValueError("derived Aegean endpoint population changed")


def _validate_observations(
    observations: Sequence[EndpointObservation],
    *,
    expected_image_count: int | None = None,
    allow_empty_values: bool = False,
) -> str | None:
    """Return a fail-closed reason or validate one complete image vector."""
    if expected_image_count is not None and len(observations) != (
        expected_image_count
    ):
        return "endpoint image population is incomplete"
    keys = tuple(item.image_key for item in observations)
    if len(keys) != len(set(keys)):
        return "endpoint image identities are duplicated"
    for observation in observations:
        if observation.status != "success":
            return observation.reason or "finder endpoint unavailable"
        if not observation.values and not allow_empty_values:
            return "endpoint image contains no applicable values"
        if not np.all(np.isfinite(observation.values)):
            return "endpoint image contains non-finite values"
    return None


def _summary(values: npt.NDArray[np.float64], statistic: Statistic) -> float:
    """Apply one prospectively declared endpoint statistic."""
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("endpoint statistic requires finite values")
    if statistic == "mean":
        return float(np.mean(values))
    if statistic == "median":
        return float(np.median(values))
    if statistic == "percentile-95":
        return float(np.percentile(values, 95))
    return abs(float(np.mean(values)))


def _selected_values(
    observations: Sequence[EndpointObservation],
    indices: npt.NDArray[np.int64],
) -> npt.NDArray[np.float64]:
    """Flatten selected image clusters without changing within-image rows."""
    return np.asarray(
        [
            value
            for index in np.ravel(indices)
            for value in observations[int(index)].values
        ],
        dtype=np.float64,
    )


def _aggregate_observations(
    spec: ContinuumEndpointSpec,
    observations: Sequence[EndpointObservation],
    indices: npt.NDArray[np.int64] | None = None,
) -> float:
    """Aggregate complete observations at the declared scientific level."""
    selected = (
        np.arange(len(observations), dtype=np.int64)
        if indices is None
        else np.asarray(indices, dtype=np.int64)
    )
    values = _selected_values(observations, selected)
    return _summary(values, spec.statistic)


def _per_image_summaries(
    spec: ContinuumEndpointSpec,
    observations: Sequence[EndpointObservation],
) -> npt.NDArray[np.float64]:
    """Return one paired planning contribution for every complete image."""
    return np.asarray(
        [
            (
                _summary(
                    np.asarray(item.values, dtype=np.float64),
                    spec.statistic,
                )
                if item.values
                else np.nan
            )
            for item in observations
        ],
        dtype=np.float64,
    )


def _observation_matrix(
    observations: Sequence[EndpointObservation],
) -> npt.NDArray[np.float64]:
    """Pad bounded per-image rows once for vectorized cluster resampling."""
    width = max((len(item.values) for item in observations), default=0)
    matrix = np.full((len(observations), width), np.nan, dtype=np.float64)
    for index, observation in enumerate(observations):
        matrix[index, : len(observation.values)] = observation.values
    return matrix


def _resampled_statistic(
    values: npt.NDArray[np.float64],
    indices: npt.NDArray[np.int64],
    statistic: Statistic,
) -> npt.NDArray[np.float64]:
    """Aggregate padded cluster rows for every SciPy bootstrap sample."""
    selected = values[indices]
    flattened = selected.reshape((*indices.shape[:-1], -1))
    with np.errstate(invalid="ignore"):
        if statistic == "mean":
            return np.nanmean(flattened, axis=-1)
        if statistic == "median":
            return np.nanmedian(flattened, axis=-1)
        if statistic == "percentile-95":
            return np.nanpercentile(flattened, 95, axis=-1)
    return np.abs(np.nanmean(flattened, axis=-1))


def _regression(
    candidate: float, reference: float, direction: Direction
) -> float:
    """Orient every difference so a positive value is a regression."""
    return (
        reference - candidate
        if direction == "higher-is-better"
        else candidate - reference
    )


def _paired_statistic(
    spec: ContinuumEndpointSpec,
    candidate: Sequence[EndpointObservation],
    reference: Sequence[EndpointObservation],
    direction: Direction,
) -> Callable[[npt.NDArray[np.int64]], npt.NDArray[np.float64]]:
    """Build a vectorized whole-image regression statistic for SciPy BCa."""
    candidate_values = _observation_matrix(candidate)
    reference_values = _observation_matrix(reference)

    def statistic(
        indices: npt.NDArray[np.int64], axis: int = -1
    ) -> npt.NDArray[np.float64]:
        array = np.asarray(indices, dtype=np.int64)
        if axis != -1:
            array = np.moveaxis(array, axis, -1)
        candidate_statistics = _resampled_statistic(
            candidate_values,
            array,
            spec.statistic,
        )
        reference_statistics = _resampled_statistic(
            reference_values,
            array,
            spec.statistic,
        )
        return (
            reference_statistics - candidate_statistics
            if direction == "higher-is-better"
            else candidate_statistics - reference_statistics
        )

    return statistic


def compile_reference_comparison(  # noqa: PLR0913
    spec: ContinuumEndpointSpec,
    candidate: Sequence[EndpointObservation],
    reference: Sequence[EndpointObservation],
    *,
    reference_id: str,
    desirable_direction: Direction,
    resamples: int,
    seed: int,
) -> CompiledReferenceComparison:
    """Compile one paired BCa comparison without dropping failed images."""
    allow_empty = spec.value_kind != "image-scalar"
    candidate_reason = _validate_observations(
        candidate, allow_empty_values=allow_empty
    )
    reference_reason = _validate_observations(
        reference, allow_empty_values=allow_empty
    )
    if candidate_reason is not None or reference_reason is not None:
        return CompiledReferenceComparison(
            reference_id=reference_id,
            status="unavailable",
            reference_value=None,
            positive_regression=None,
            upper_confidence_limit=None,
            observed_paired_standard_deviation=None,
            reason=reference_reason or candidate_reason,
        )
    candidate_keys = tuple(item.image_key for item in candidate)
    if candidate_keys != tuple(item.image_key for item in reference):
        return CompiledReferenceComparison(
            reference_id=reference_id,
            status="unavailable",
            reference_value=None,
            positive_regression=None,
            upper_confidence_limit=None,
            observed_paired_standard_deviation=None,
            reason="paired endpoint image identities differ",
        )
    try:
        reference_value = _aggregate_observations(spec, reference)
    except ValueError:
        return CompiledReferenceComparison(
            reference_id=reference_id,
            status="unavailable",
            reference_value=None,
            positive_regression=None,
            upper_confidence_limit=None,
            observed_paired_standard_deviation=None,
            reason="paired endpoint has no measured reference values",
        )
    point, upper = paired_bca_upper_limits(
        _paired_statistic(
            spec,
            candidate,
            reference,
            desirable_direction,
        ),
        realization_count=len(candidate),
        resampling=cast(
            Any,
            type(
                "Resampling",
                (),
                {
                    "confidence_level": 0.95,
                    "resamples": resamples,
                    "alternative": "less",
                    "seed": seed,
                },
            )(),
        ),
    )
    candidate_images = _per_image_summaries(spec, candidate)
    reference_images = _per_image_summaries(spec, reference)
    image_regressions = (
        reference_images - candidate_images
        if desirable_direction == "higher-is-better"
        else candidate_images - reference_images
    )
    finite_image_regressions = image_regressions[
        np.isfinite(image_regressions)
    ]
    if finite_image_regressions.size < _MINIMUM_PAIRED_IMAGES:
        return CompiledReferenceComparison(
            reference_id=reference_id,
            status="unavailable",
            reference_value=None,
            positive_regression=None,
            upper_confidence_limit=None,
            observed_paired_standard_deviation=None,
            reason="paired endpoint has fewer than two measured images",
        )
    point_value = float(np.asarray(point))
    upper_value = float(np.asarray(upper))
    if not np.isfinite(point_value) or not np.isfinite(upper_value):
        return CompiledReferenceComparison(
            reference_id=reference_id,
            status="unavailable",
            reference_value=None,
            positive_regression=None,
            upper_confidence_limit=None,
            observed_paired_standard_deviation=None,
            reason="paired BCa interval is non-finite",
        )
    return CompiledReferenceComparison(
        reference_id=reference_id,
        status="success",
        reference_value=reference_value,
        positive_regression=point_value,
        upper_confidence_limit=upper_value,
        observed_paired_standard_deviation=float(
            np.std(finite_image_regressions, ddof=1)
        ),
    )


def _absolute_upper_bound(
    spec: ContinuumEndpointSpec,
    observations: Sequence[EndpointObservation],
    *,
    resamples: int,
    seed: int,
) -> float:
    """Compile the reviewed irregular-position absolute confidence bound."""
    values = np.asarray(
        [value for item in observations for value in item.values],
        dtype=np.float64,
    )
    image_keys = tuple(
        item.image_key for item in observations for _ in item.values
    )
    if spec.statistic == "absolute-mean":
        _, upper = cluster_bootstrap_absolute_mean(
            values=tuple(float(item) for item in values),
            image_keys=image_keys,
            resamples=resamples,
            seed=seed,
            confidence_level=0.95,
        )
        return upper
    _, upper = cluster_bootstrap_statistic(
        values,
        image_keys,
        BootstrapDesign(
            statistic=cast(Literal["median", "percentile-95"], spec.statistic),
            resamples=resamples,
            seed=seed,
            confidence_level=0.95,
        ),
    )
    return upper


def compile_continuum_endpoint(  # noqa: PLR0913
    spec: ContinuumEndpointSpec,
    candidate: Sequence[EndpointObservation],
    references: dict[str, Sequence[EndpointObservation]],
    *,
    expected_image_count: int,
    desirable_direction: Direction,
    absolute_decision_statistic: AbsoluteDecisionStatistic,
    resamples: int,
    seed: int,
) -> CompiledContinuumEndpoint:
    """Compile one exact endpoint, retaining every image in its denominator."""
    reason = _validate_observations(
        candidate,
        expected_image_count=expected_image_count,
        allow_empty_values=spec.value_kind != "image-scalar",
    )
    if reason is not None:
        return CompiledContinuumEndpoint(
            endpoint_id=spec.endpoint_id,
            lane="continuum",
            metric_family=spec.metric_family,
            stratum=spec.stratum,
            position_population=spec.position_population,
            image_count=expected_image_count,
            candidate_status="failed",
            candidate_value=None,
            absolute_decision_value=None,
            comparisons=(),
            reason=reason,
        )
    try:
        candidate_value = _aggregate_observations(spec, candidate)
        absolute_value = (
            candidate_value
            if absolute_decision_statistic == "point-estimate"
            else _absolute_upper_bound(
                spec,
                candidate,
                resamples=resamples,
                seed=seed,
            )
        )
    except ValueError as error:
        return CompiledContinuumEndpoint(
            endpoint_id=spec.endpoint_id,
            lane="continuum",
            metric_family=spec.metric_family,
            stratum=spec.stratum,
            position_population=spec.position_population,
            image_count=expected_image_count,
            candidate_status="unavailable",
            candidate_value=None,
            absolute_decision_value=None,
            comparisons=(),
            reason=str(error),
        )
    comparisons = (
        tuple(
            compile_reference_comparison(
                spec,
                candidate,
                reference,
                reference_id=reference_id,
                desirable_direction=desirable_direction,
                resamples=resamples,
                seed=seed,
            )
            for reference_id, reference in references.items()
        )
        if spec.paired
        else ()
    )
    return CompiledContinuumEndpoint(
        endpoint_id=spec.endpoint_id,
        lane="continuum",
        metric_family=spec.metric_family,
        stratum=spec.stratum,
        position_population=spec.position_population,
        image_count=expected_image_count,
        candidate_status="success",
        candidate_value=candidate_value,
        absolute_decision_value=absolute_value,
        comparisons=comparisons,
    )


def select_aegean_binding_decisions(
    decision: dict[str, Any], registry: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    """Select only prospectively applicable Aegean Phase 4R decisions."""
    compact = registry.get("compact")
    if not isinstance(compact, dict):
        raise ValueError("compact endpoint policy is absent")
    applicable = set(compact.get("aegean_applicable_metric_ids", ()))
    rows = decision.get("metric_decisions")
    if not isinstance(rows, list):
        raise ValueError("compact metric decisions are absent")
    selected = tuple(
        cast(dict[str, Any], item)
        for item in rows
        if isinstance(item, dict)
        and item.get("reference_identifier") == "aegean"
        and item.get("metric_id") in applicable
    )
    keys = tuple((item["metric_id"], item["stratum"]) for item in selected)
    if len(keys) != len(set(keys)):
        raise ValueError("Aegean binding metric keys are duplicated")
    return selected


def _association_object(
    item: ContinuumTruthObject | ContinuumCandidateObject,
) -> AssociationObject:
    """Convert one compiler record to the frozen matcher boundary."""
    return AssociationObject(
        identifier=item.identifier,
        object_class="extended",
        centre_x_pixel=item.centre_xy[0],
        centre_y_pixel=item.centre_xy[1],
        support_label=item.support_label,
    )


def _support_candidates(
    candidates: Sequence[ContinuumCandidateObject],
) -> tuple[ContinuumCandidateObject, ...]:
    """Collapse catalogue rows to distinct native supports for topology."""
    grouped: dict[int, list[ContinuumCandidateObject]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.support_label].append(candidate)
    return tuple(
        ContinuumCandidateObject(
            identifier=f"support-{label}",
            support_label=label,
            centre_xy=(
                float(np.mean([item.centre_xy[0] for item in rows])),
                float(np.mean([item.centre_xy[1] for item in rows])),
            ),
            integrated_flux_jy=float(
                np.sum([item.integrated_flux_jy for item in rows])
            ),
        )
        for label, rows in sorted(grouped.items())
    )


def _truth_strata(
    truth: Sequence[ContinuumTruthObject],
) -> tuple[str, ...]:
    """Return the exact present overall and declared group strata."""
    return (
        "overall",
        *sorted({stratum for item in truth for stratum in item.strata}),
    )


def _selected_truth(
    truth: Sequence[ContinuumTruthObject], stratum: str
) -> tuple[ContinuumTruthObject, ...]:
    """Select one truth-only scientific population."""
    return tuple(
        item
        for item in truth
        if stratum == "overall" or stratum in item.strata
    )


def _mask_metrics(
    truth_label_plane: npt.NDArray[np.int64],
    candidate_label_plane: npt.NDArray[np.int64],
) -> dict[str, float]:
    """Return finder-neutral whole-image support overlap fractions."""
    truth_mask = truth_label_plane > 0
    candidate_mask = candidate_label_plane > 0
    intersection = int(np.count_nonzero(truth_mask & candidate_mask))
    truth_count = int(np.count_nonzero(truth_mask))
    candidate_count = int(np.count_nonzero(candidate_mask))
    union = int(np.count_nonzero(truth_mask | candidate_mask))
    return {
        "mask-precision": (
            intersection / candidate_count if candidate_count else 0.0
        ),
        "mask-recall": intersection / truth_count if truth_count else 1.0,
        "mask-iou": intersection / union if union else 1.0,
    }


def measure_continuum_image(
    truth: Sequence[ContinuumTruthObject],
    candidates: Sequence[ContinuumCandidateObject],
    *,
    truth_label_plane: npt.ArrayLike,
    candidate_label_plane: npt.ArrayLike,
    beam_fwhm_pixels: float,
) -> dict[str, dict[str, float | tuple[float, ...]]]:
    """Derive all finder-neutral sufficient statistics for one image."""
    truth_rows = tuple(truth)
    candidate_rows = tuple(candidates)
    truth_labels = np.asarray(truth_label_plane, dtype=np.int64)
    candidate_labels = np.asarray(candidate_label_plane, dtype=np.int64)
    catalogue_report = match_truth_to_finder(
        tuple(_association_object(item) for item in truth_rows),
        tuple(_association_object(item) for item in candidate_rows),
        beam_fwhm_pixels=beam_fwhm_pixels,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
    )
    support_rows = _support_candidates(candidate_rows)
    support_report = match_truth_to_finder(
        tuple(_association_object(item) for item in truth_rows),
        tuple(_association_object(item) for item in support_rows),
        beam_fwhm_pixels=beam_fwhm_pixels,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
    )
    primary = {
        item.truth_identifier: item.candidate_identifier
        for item in catalogue_report.primary_associations
    }
    candidate_by_id = {item.identifier: item for item in candidate_rows}
    catalogue_degrees = Counter(
        item.truth_identifier
        for item in catalogue_report.eligible_associations
    )
    support_truth_degrees = Counter(
        item.truth_identifier for item in support_report.eligible_associations
    )
    support_candidate_degrees = Counter(
        item.candidate_identifier
        for item in support_report.eligible_associations
    )
    results: dict[str, dict[str, float | tuple[float, ...]]] = {
        metric: {}
        for metric in (
            "completeness",
            "reliability",
            "integrated-flux-median",
            "integrated-flux-p95",
            "absolute-mean-offset-x",
            "absolute-mean-offset-y",
            "position-median",
            "position-p95",
            "duplicate-fraction",
            "mask-precision",
            "mask-recall",
            "mask-iou",
            "split-fraction",
            "merge-fraction",
        )
    }
    matched_candidates = set(primary.values())
    results["reliability"]["overall"] = (
        len(matched_candidates) / len(candidate_rows)
        if candidate_rows
        else 0.0
    )
    for metric, value in _mask_metrics(truth_labels, candidate_labels).items():
        results[metric]["overall"] = value
    for stratum in _truth_strata(truth_rows):
        selected = _selected_truth(truth_rows, stratum)
        identifiers = {item.identifier for item in selected}
        results["completeness"][stratum] = sum(
            identifier in primary for identifier in identifiers
        ) / len(selected)
        results["duplicate-fraction"][stratum] = sum(
            catalogue_degrees[identifier] > 1 for identifier in identifiers
        ) / len(selected)
        results["split-fraction"][stratum] = sum(
            support_truth_degrees[identifier] > 1 for identifier in identifiers
        ) / len(selected)
        selected_supports = {
            item.candidate_identifier
            for item in support_report.eligible_associations
            if item.truth_identifier in identifiers
        }
        results["merge-fraction"][stratum] = (
            sum(
                support_candidate_degrees[identifier] > 1
                for identifier in selected_supports
            )
            / len(selected_supports)
            if selected_supports
            else 0.0
        )
        flux_errors: list[float] = []
        offsets_x: list[float] = []
        offsets_y: list[float] = []
        radial: list[float] = []
        for truth_item in selected:
            if truth_item.catalogue_role != "astronomical-source":
                continue
            candidate_id = primary.get(truth_item.identifier)
            if candidate_id is None:
                continue
            candidate = candidate_by_id[candidate_id]
            flux_errors.append(
                abs(
                    candidate.integrated_flux_jy
                    - truth_item.integrated_flux_jy
                )
                / truth_item.integrated_flux_jy
            )
            offset_x = (
                candidate.centre_xy[0] - truth_item.centre_xy[0]
            ) / beam_fwhm_pixels
            offset_y = (
                candidate.centre_xy[1] - truth_item.centre_xy[1]
            ) / beam_fwhm_pixels
            offsets_x.append(offset_x)
            offsets_y.append(offset_y)
            radial.append(hypot(offset_x, offset_y))
        values = tuple(flux_errors)
        positions = tuple(radial)
        results["integrated-flux-median"][stratum] = values
        results["integrated-flux-p95"][stratum] = values
        results["absolute-mean-offset-x"][stratum] = tuple(offsets_x)
        results["absolute-mean-offset-y"][stratum] = tuple(offsets_y)
        results["position-median"][stratum] = positions
        results["position-p95"][stratum] = positions
    return results


def _request_sha256(request: CampaignRequest) -> str:
    """Hash the exact unopened request embedded in a terminal campaign."""
    return hashlib.sha256(request.canonical_json_bytes()).hexdigest()


def _expected_artifact_roles(run: CampaignRunRequest) -> frozenset[str]:
    """Return the exact native product set for one successful finder leg."""
    if run.finder_id == "hebog":
        return frozenset(
            {
                "compact-catalogue-json",
                "segment-catalogue-json",
                "segment-labels-fits",
                "segment-mask-fits",
            }
        )
    if run.finder_id in {"released-pybdsf", "pinned-pybdsf-master"}:
        return frozenset(
            {
                "gaussian-catalogue-fits",
                "island-labels-fits",
                "island-mask-fits",
                "source-catalogue-fits",
            }
        )
    return frozenset(
        {
            "component-catalogue-fits",
            "island-catalogue-fits",
            "support-proxy-labels-fits",
        }
    )


def _approved_runtime_identities(
    registry: dict[str, Any], repository_root: Path
) -> dict[str, tuple[str, str, str]]:
    """Return approved source, container, and dependency identities."""
    decision = _json_object(
        repository_root / registry["execution_decision_path"]
    )
    protocol = _json_object(repository_root / registry["protocol_path"])
    identities = {
        "hebog": (
            decision["implementation_commit"],
            decision["hebog_container_image_digest"],
            decision["hebog_dependency_inventory_sha256"],
        )
    }
    for reference in protocol["references"]:
        identities[reference["finder_id"]] = (
            reference["source_revision"],
            reference["container_image_digest"],
            reference["dependency_inventory_sha256"],
        )
    return identities


def _validate_campaign_request_identity(
    request: CampaignRequest,
    registry: dict[str, Any],
    repository_root: Path,
) -> None:
    """Require the sealed request to be the exact approved campaign."""
    decision = _json_object(
        repository_root / registry["execution_decision_path"]
    )
    if (
        decision.get("decision_id") != "phase-5-external-execution-decision"
        or decision.get("decision")
        != "authorize-one-terminal-external-comparison"
        or decision.get("execution_authorized") is not True
        or decision.get("one_look_opened") is not False
    ):
        raise ValueError("external execution decision is not approved")
    request_fields = {
        "protocol_sha256": registry["protocol_sha256"],
        "execution_decision_sha256": registry["execution_decision_sha256"],
        "candidate_review_sha256": registry["phase_five_review_sha256"],
        "implementation_commit": decision["implementation_commit"],
        "source_tree_sha256": decision["source_tree_sha256"],
        "launcher_sha256": registry["launcher_sha256"],
    }
    if any(
        getattr(request, field) != expected
        for field, expected in request_fields.items()
    ):
        raise ValueError("terminal campaign request identity is not approved")
    approved_runtimes = _approved_runtime_identities(registry, repository_root)
    observed_digests = {
        container.finder_id: container.digest
        for container in request.containers
    }
    expected_digests = {
        finder: identity[1] for finder, identity in approved_runtimes.items()
    }
    if observed_digests != expected_digests:
        raise ValueError("terminal campaign container identities changed")
    lane_manifests = {
        "continuum": (
            registry["continuum_manifest_path"],
            registry["continuum_manifest_sha256"],
        ),
        "compact-blend": (
            registry["compact_manifest_path"],
            registry["compact_manifest_sha256"],
        ),
    }
    for campaign_input in request.inputs:
        expected_path, expected_sha256 = lane_manifests[campaign_input.lane]
        if (
            campaign_input.manifest_relative_path != expected_path
            or campaign_input.manifest_sha256 != expected_sha256
        ):
            raise ValueError("terminal campaign input manifest changed")


def verify_terminal_campaign(  # noqa: C901, PLR0912
    campaign_path: Path,
    registry: dict[str, Any],
    repository_root: Path,
) -> VerifiedTerminalCampaign:
    """Re-verify the complete raw campaign before reading science values."""
    root = campaign_path.resolve().parent
    terminal = TerminalCampaignResult.model_validate_json(
        campaign_path.read_text(encoding="utf-8")
    )
    request_path = root / "campaign-request.json"
    request = CampaignRequest.model_validate_json(
        request_path.read_text(encoding="utf-8")
    )
    _validate_campaign_request_identity(request, registry, repository_root)
    if terminal.request_sha256 != _request_sha256(request):
        raise ValueError("terminal campaign request checksum changed")
    if terminal.protocol_sha256 != registry["protocol_sha256"]:
        raise ValueError("terminal campaign protocol differs from registry")
    if terminal.execution_decision_sha256 != (
        request.execution_decision_sha256
    ):
        raise ValueError("terminal execution decision differs from request")
    summaries = {item.run_id: item for item in terminal.runs}
    if len(summaries) != len(terminal.runs):
        raise ValueError("terminal run summaries are duplicated")
    if set(summaries) != {item.run_id for item in request.runs}:
        raise ValueError("terminal run summary population is incomplete")

    inputs: dict[str, tuple[ExternalInputBundle, Path]] = {}
    for campaign_input in request.inputs:
        input_path = root / campaign_input.relative_directory / "input.json"
        bundle = load_external_input_bundle(input_path, verify_artifacts=True)
        if (
            bundle.protocol_sha256 != request.protocol_sha256
            or bundle.manifest_sha256 != campaign_input.manifest_sha256
            or bundle.dataset_identifier != campaign_input.dataset_identifier
            or bundle.seed != campaign_input.seed
            or bundle.recipe_sha256 != campaign_input.recipe_sha256
        ):
            raise ValueError(
                f"terminal input identity changed: {campaign_input.input_id}"
            )
        inputs[campaign_input.input_id] = (bundle, input_path)

    approved_runtimes = _approved_runtime_identities(registry, repository_root)
    verified_runs: dict[tuple[str, str, str], VerifiedRun] = {}
    for run in request.runs:
        summary = summaries[run.run_id]
        expected_relative = f"{run.relative_directory}/result.json"
        if (
            summary.result_relative_path != expected_relative
            or summary.input_id != run.input_id
            or summary.finder_id != run.finder_id
            or summary.mode != run.mode
        ):
            raise ValueError(f"terminal result path changed: {run.run_id}")
        result_path = root / expected_relative
        if file_sha256(result_path) != summary.result_sha256:
            raise ValueError(f"terminal result checksum changed: {run.run_id}")
        result = load_external_run_result(result_path, verify_artifacts=True)
        bundle, input_path = inputs[run.input_id]
        if (
            result.protocol_sha256 != request.protocol_sha256
            or result.execution_decision_sha256
            != request.execution_decision_sha256
            or result.input_bundle_sha256 != file_sha256(input_path)
            or result.dataset_identifier != bundle.dataset_identifier
            or result.seed != bundle.seed
            or result.finder_id != run.finder_id
            or result.mode != run.mode
            or result.status != summary.status
        ):
            raise ValueError(f"terminal run identity changed: {run.run_id}")
        approved_source, approved_container, approved_inventory = (
            approved_runtimes[run.finder_id]
        )
        if (
            result.runtime.source_revision != approved_source
            or result.runtime.container_image_digest != approved_container
            or result.runtime.dependency_inventory_sha256 != approved_inventory
        ):
            raise ValueError(f"terminal runtime changed: {run.run_id}")
        roles = frozenset(item.role for item in result.artifacts)
        expected_roles = (
            _expected_artifact_roles(run)
            if result.status == "success"
            else frozenset()
        )
        if roles != expected_roles:
            raise ValueError(f"terminal artifact roles changed: {run.run_id}")
        key = (run.input_id, run.finder_id, run.mode)
        if key in verified_runs:
            raise ValueError("terminal finder leg identity is duplicated")
        verified_runs[key] = VerifiedRun(
            request=run,
            result=result,
            directory=result_path.parent,
        )
    return VerifiedTerminalCampaign(
        root=root,
        request=request,
        terminal=terminal,
        campaign_sha256=file_sha256(campaign_path),
        inputs=inputs,
        runs=verified_runs,
    )


def _artifact_path(run: VerifiedRun, role: str) -> Path:
    """Resolve one already-verified result artifact by exact role."""
    artifact = next(
        (item for item in run.result.artifacts if item.role == role), None
    )
    if artifact is None:
        raise ValueError(
            f"run {run.request.run_id} lacks required artifact {role}"
        )
    return run.directory / artifact.relative_path


def _integer_label_plane(path: Path) -> npt.NDArray[np.int64]:
    """Load one non-negative two-dimensional native support plane."""
    raw = load_fits_plane(path)
    if np.any(raw < 0) or not np.all(raw == np.floor(raw)):
        raise ValueError(
            f"support label plane is not non-negative integer: {path}"
        )
    return np.asarray(raw, dtype=np.int64)


def _input_artifact_path(
    bundle: ExternalInputBundle, input_path: Path, role: str
) -> Path:
    """Resolve one checksum-verified common input artifact."""
    artifact = next(item for item in bundle.artifacts if item.role == role)
    return input_path.parent / artifact.relative_path


def _dataset_maps(
    manifest_path: Path,
) -> tuple[dict[str, DatasetRecord], dict[tuple[str, int], SyntheticRecipe]]:
    """Index exact manifest geometries and every prospective recipe."""
    manifest = load_dataset_manifest(manifest_path)
    datasets = {item.identifier: item for item in manifest.datasets}
    recipes = {
        (dataset.identifier, recipe.seed): recipe
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }
    return datasets, recipes


def _truth_objects(
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    valid_pixels: npt.NDArray[np.bool_],
    review: Any,
) -> tuple[tuple[ContinuumTruthObject, ...], npt.NDArray[np.int64]]:
    """Derive immutable truth supports and observable-domain centroids."""
    generated = _build_generated_truth(dataset, review)
    group_by_id = {
        item.identifier: item for item in dataset.multiscale_truth_groups
    }
    strata_by_group: dict[str, set[str]] = defaultdict(set)
    for stratum in dataset.multiscale_group_strata:
        for identifier in stratum.group_identifiers:
            strata_by_group[identifier].add(stratum.identifier)
    labels = np.zeros(recipe.shape_yx, dtype=np.int64)
    truth: list[ContinuumTruthObject] = []
    beam_area_pixels = (
        np.pi
        * dataset.beam.major_fwhm_pixels
        * dataset.beam.minor_fwhm_pixels
        / (4.0 * np.log(2.0))
    )
    for label, generated_truth in enumerate(generated, start=1):
        group = group_by_id[generated_truth.identifier]
        support = generated_truth.detection_mask & valid_pixels
        if np.any(labels[support] != 0):
            raise ValueError("continuum truth supports overlap")
        labels[support] = label
        centre = _reference_position(
            generated_truth.signal_jy_per_beam,
            support,
        )
        truth.append(
            ContinuumTruthObject(
                identifier=group.identifier,
                support_label=label,
                centre_xy=centre,
                integrated_flux_jy=(
                    group.reference_integrated_brightness_jy_pixels_per_beam
                    / beam_area_pixels
                ),
                catalogue_role=group.catalogue_role,
                strata=tuple(sorted(strata_by_group[group.identifier])),
            )
        )
    return tuple(truth), labels


def _catalogue_and_labels(
    run: VerifiedRun,
) -> tuple[tuple[Any, ...], npt.NDArray[np.int64]]:
    """Load one like-product continuum catalogue and native support plane."""
    if run.result.finder_id == "hebog":
        catalogue = load_comparison_catalogue(
            _artifact_path(run, "segment-catalogue-json")
        )
        labels = _integer_label_plane(
            _artifact_path(run, "segment-labels-fits")
        )
    else:
        catalogue = load_pybdsf_catalogue(
            _artifact_path(run, "source-catalogue-fits")
        )
        labels = _integer_label_plane(
            _artifact_path(run, "island-labels-fits")
        )
    return catalogue, labels


def _catalogue_support_label(source: Any, finder_id: str) -> int:
    """Map each normalized row to its exact native support label."""
    identifier = source.island_identifier
    if identifier is None:
        raise ValueError("continuum catalogue row lacks an island identity")
    if finder_id == "hebog":
        prefix = "hebog-segment-"
        if not str(identifier).startswith(prefix):
            raise ValueError("Hebog segment island identity is malformed")
        return int(str(identifier)[len(prefix) :])
    return int(identifier) + 1


def _candidate_objects(
    catalogue: Sequence[Any],
    labels: npt.NDArray[np.int64],
    *,
    finder_id: str,
    header: fits.Header,
) -> tuple[ContinuumCandidateObject, ...]:
    """Translate normalized catalogue rows to pixel-centred matcher objects."""
    celestial = WCS(header, relax=True).celestial
    candidates: list[ContinuumCandidateObject] = []
    for source in catalogue:
        label = _catalogue_support_label(source, finder_id)
        if not np.any(labels == label):
            raise ValueError("continuum catalogue support label is absent")
        centre = celestial.all_world2pix(
            [[source.right_ascension_degrees, source.declination_degrees]],
            0,
        )[0]
        integrated = (
            source.association_integrated_flux_jy
            if source.association_integrated_flux_jy is not None
            else source.integrated_flux_jy
        )
        candidates.append(
            ContinuumCandidateObject(
                identifier=source.identifier,
                support_label=label,
                centre_xy=(float(centre[0]), float(centre[1])),
                integrated_flux_jy=float(integrated),
            )
        )
    if {item.support_label for item in candidates} != {
        int(item) for item in np.unique(labels) if item > 0
    }:
        raise ValueError("continuum catalogue and support labels disagree")
    return tuple(candidates)


def _failed_endpoint_observations(
    specifications: Sequence[ContinuumEndpointSpec],
    *,
    image_key: str,
    reason: str,
) -> dict[str, EndpointObservation]:
    """Retain one finder failure in every exact endpoint denominator."""
    return {
        item.endpoint_id: EndpointObservation(
            image_key=image_key,
            status="failed",
            reason=reason,
        )
        for item in specifications
    }


def _continuum_image_observations(  # noqa: PLR0913
    verified: VerifiedTerminalCampaign,
    campaign_input: Any,
    run: VerifiedRun,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    review: Any,
    specifications: Sequence[ContinuumEndpointSpec],
) -> dict[str, EndpointObservation]:
    """Compile one finder/image product set after truth is fixed."""
    image_key = campaign_input.input_id
    if run.result.status != "success":
        failure = run.result.failure
        return _failed_endpoint_observations(
            specifications,
            image_key=image_key,
            reason=(
                failure.message if failure is not None else "finder failed"
            ),
        )
    bundle, input_path = verified.inputs[campaign_input.input_id]
    image_path = _input_artifact_path(bundle, input_path, "image")
    image = load_fits_plane(image_path)
    mean = load_fits_plane(_input_artifact_path(bundle, input_path, "mean"))
    rms = load_fits_plane(_input_artifact_path(bundle, input_path, "rms"))
    valid = np.isfinite(image) & np.isfinite(mean) & np.isfinite(rms)
    truth, truth_labels = _truth_objects(dataset, recipe, valid, review)
    catalogue, candidate_labels = _catalogue_and_labels(run)
    header = cast(fits.Header, fits.getheader(image_path))
    candidates = _candidate_objects(
        catalogue,
        candidate_labels,
        finder_id=run.result.finder_id,
        header=header,
    )
    values = measure_continuum_image(
        truth,
        candidates,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=dataset.beam.major_fwhm_pixels,
    )
    output: dict[str, EndpointObservation] = {}
    for specification in specifications:
        untyped = values[specification.metric_family][specification.stratum]
        row = untyped if isinstance(untyped, tuple) else (untyped,)
        output[specification.endpoint_id] = EndpointObservation(
            image_key=image_key,
            values=tuple(float(item) for item in row),
        )
    return output


def _continuum_policy(
    metric_family: str,
) -> tuple[Direction, AbsoluteDecisionStatistic]:
    """Return the frozen direction and absolute statistic for one family."""
    higher = {
        "completeness",
        "reliability",
        "mask-precision",
        "mask-recall",
        "mask-iou",
    }
    absolute_confidence = {
        "absolute-mean-offset-x",
        "absolute-mean-offset-y",
        "position-p95",
    }
    return (
        "higher-is-better" if metric_family in higher else "lower-is-better",
        (
            "one-sided-95-percent-upper-confidence-limit"
            if metric_family in absolute_confidence
            else "point-estimate"
        ),
    )


def compile_continuum_campaign(
    verified: VerifiedTerminalCampaign,
    registry: dict[str, Any],
    repository_root: Path,
) -> tuple[
    tuple[CompiledContinuumEndpoint, ...],
    tuple[CompiledContinuumEndpoint, ...],
]:
    """Compile every exact continuum endpoint and report-only diagnostic."""
    specifications = expand_continuum_endpoint_specs(registry)
    datasets, recipes = _dataset_maps(
        repository_root / registry["continuum_manifest_path"]
    )
    review = load_phase_five_corrective_a_review(
        repository_root / registry["phase_five_review_path"]
    )
    observations: dict[str, dict[str, list[EndpointObservation]]] = {
        finder: {item.endpoint_id: [] for item in specifications}
        for finder in (
            "hebog",
            "released-pybdsf",
            "pinned-pybdsf-master",
        )
    }
    continuum_inputs = tuple(
        item for item in verified.request.inputs if item.lane == "continuum"
    )
    for campaign_input in continuum_inputs:
        dataset = datasets[campaign_input.dataset_identifier]
        recipe = recipes[(dataset.identifier, campaign_input.seed)]
        for finder in observations:
            mode = "candidate" if finder == "hebog" else "operational"
            run = verified.runs[(campaign_input.input_id, finder, mode)]
            compiled = _continuum_image_observations(
                verified,
                campaign_input,
                run,
                dataset,
                recipe,
                review,
                specifications,
            )
            for endpoint_id, observation in compiled.items():
                observations[finder][endpoint_id].append(observation)
    protocol = _json_object(repository_root / registry["protocol_path"])
    resamples = int(protocol["bootstrap_resamples"])
    seed = int(protocol["bootstrap_seed"])
    binding: list[CompiledContinuumEndpoint] = []
    diagnostic: list[CompiledContinuumEndpoint] = []
    for specification in specifications:
        direction, absolute_statistic = _continuum_policy(
            specification.metric_family
        )
        candidate = tuple(observations["hebog"][specification.endpoint_id])
        references = {
            finder: tuple(observations[finder][specification.endpoint_id])
            for finder in (
                "released-pybdsf",
                "pinned-pybdsf-master",
            )
        }
        compiled = compile_continuum_endpoint(
            specification,
            candidate,
            references,
            expected_image_count=len(continuum_inputs),
            desirable_direction=direction,
            absolute_decision_statistic=absolute_statistic,
            resamples=resamples,
            seed=seed,
        )
        (binding if specification.binding else diagnostic).append(compiled)
    return tuple(binding), tuple(diagnostic)


def _external_failure_diagnostic(
    run: VerifiedRun,
    *,
    implementation_identifier: str,
) -> CampaignRealizationDiagnostic:
    """Translate one retained finder failure without dropping its seed."""
    failure = run.result.failure
    if failure is None:
        raise ValueError("failed external run lacks failure details")
    return CampaignRealizationDiagnostic(
        implementation_identifier=implementation_identifier,
        seed=run.result.seed,
        status="failure",
        failure=CampaignFailure(
            stage=failure.stage,
            exception_type=failure.exception_type,
            message=failure.message,
            traceback_sha256=hashlib.sha256(
                failure.traceback.encode()
            ).hexdigest(),
        ),
    )


def _compact_catalogue(run: VerifiedRun) -> tuple[Any, ...]:
    """Load the like-for-like normalized compact catalogue for one finder."""
    if run.result.finder_id == "hebog":
        return load_comparison_catalogue(
            _artifact_path(run, "compact-catalogue-json")
        )
    if run.result.finder_id in {
        "released-pybdsf",
        "pinned-pybdsf-master",
    }:
        return load_pybdsf_gaussian_catalogue(
            _artifact_path(run, "gaussian-catalogue-fits")
        )
    return load_aegean_catalogue(
        _artifact_path(run, "component-catalogue-fits"),
        _artifact_path(run, "island-catalogue-fits"),
    )


def _compact_realization(  # noqa: PLR0913
    run: VerifiedRun,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    *,
    implementation_identifier: str,
    outlier_thresholds: Any,
    position_angle_minimum_axis_ratio: float,
) -> CampaignRealizationDiagnostic:
    """Build one Phase 4 diagnostic from already verified native products."""
    if run.result.status != "success":
        return _external_failure_diagnostic(
            run,
            implementation_identifier=implementation_identifier,
        )
    try:
        return diagnose_phase_four_realization(
            dataset,
            recipe,
            _compact_catalogue(run),
            implementation_identifier=implementation_identifier,
            outlier_thresholds=outlier_thresholds,
            maximum_separation_beams=0.5,
            position_angle_minimum_axis_ratio=(
                position_angle_minimum_axis_ratio
            ),
        )
    except Exception as error:
        return CampaignRealizationDiagnostic(
            implementation_identifier=implementation_identifier,
            seed=recipe.seed,
            status="failure",
            failure=CampaignFailure(
                stage="campaign-comparison",
                exception_type=type(error).__name__,
                message=str(error) or repr(error),
                traceback_sha256=hashlib.sha256(
                    repr(error).encode()
                ).hexdigest(),
            ),
        )


def _implementation_identity(
    identifier: str,
    runs: Sequence[VerifiedRun],
    *,
    role: Literal["candidate", "reference"],
) -> CampaignImplementationIdentity:
    """Bind one compact evidence implementation to one exact runtime."""
    configurations = {item.result.configuration_sha256 for item in runs}
    runtimes = {item.result.runtime for item in runs}
    if len(configurations) != 1 or len(runtimes) != 1:
        raise ValueError(f"compact runtime identity varies: {identifier}")
    runtime = next(iter(runtimes))
    return CampaignImplementationIdentity(
        identifier=identifier,
        role=role,
        execution_configuration_sha256=next(iter(configurations)),
        software=SoftwareIdentity(
            name=runtime.name,
            version=runtime.version,
            commit_sha=runtime.source_revision,
            container_image_digest=runtime.container_image_digest,
            dependency_inventory_sha256=(runtime.dependency_inventory_sha256),
        ),
    )


def _compact_campaign(  # noqa: PLR0913
    verified: VerifiedTerminalCampaign,
    dataset: DatasetRecord,
    recipes: dict[tuple[str, int], SyntheticRecipe],
    *,
    identifiers: tuple[str, str, str],
    scientific_contract_set_sha256: str,
    comparison_protocol_sha256: str,
    outlier_thresholds: Any,
    position_angle_minimum_axis_ratio: float,
) -> ScientificCampaignEvidence:
    """Compile one candidate/two-reference view for the Phase 4R engine."""
    inputs = tuple(
        item
        for item in verified.request.inputs
        if item.lane == "compact-blend"
    )
    runs_by_implementation: dict[str, tuple[VerifiedRun, ...]] = {}
    for identifier in identifiers:
        mode = "candidate" if identifier == "hebog" else "operational"
        runs_by_implementation[identifier] = tuple(
            verified.runs[(item.input_id, identifier, mode)] for item in inputs
        )
    implementations = tuple(
        _implementation_identity(
            identifier,
            runs_by_implementation[identifier],
            role="candidate" if identifier == "hebog" else "reference",
        )
        for identifier in identifiers
    )
    realizations: list[CampaignRealizationDiagnostic] = []
    for campaign_input in inputs:
        recipe = recipes[(dataset.identifier, campaign_input.seed)]
        for identifier in identifiers:
            mode = "candidate" if identifier == "hebog" else "operational"
            realizations.append(
                _compact_realization(
                    verified.runs[(campaign_input.input_id, identifier, mode)],
                    dataset,
                    recipe,
                    implementation_identifier=identifier,
                    outlier_thresholds=outlier_thresholds,
                    position_angle_minimum_axis_ratio=(
                        position_angle_minimum_axis_ratio
                    ),
                )
            )
    return ScientificCampaignEvidence(
        schema_version=1,
        evidence_type="scientific-campaign",
        run_id=(
            "phase-5-external-compact-"
            + "-".join(
                identifier.replace("pinned-", "")
                for identifier in identifiers[1:]
            )
        ),
        captured_at=verified.terminal.completed_at,
        status=EvidenceStatus.EXPLORATORY,
        dataset=campaign_dataset_identity(dataset),
        configuration_sha256=scientific_contract_set_sha256,
        comparison_protocol_sha256=comparison_protocol_sha256,
        implementations=implementations,
        realizations=tuple(realizations),
    )


def _phase_four_interval_dataset(dataset: DatasetRecord) -> DatasetRecord:
    """Use the Phase 4 qualification interval mode on external confirmation.

    The external population remains a regression-role confirmation population
    in its immutable manifest.  Phase 4R exposes its reviewed BCa interval
    implementation only through the qualification decision stage, so this
    analysis-only view changes the role field and no truth, recipe, or stratum.
    """
    return dataset.model_copy(update={"role": "qualification"})


def _compact_status(
    pybdsf: dict[str, Any],
    aegean: dict[str, Any],
    aegean_binding: Sequence[dict[str, Any]],
) -> tuple[str, tuple[str, ...]]:
    """Apply compact absolute and exact-reference conjunction."""
    reasons: set[str] = set()
    if not pybdsf.get("passed"):
        reasons.add("phase-four-pybdsf-decision-failed")
    aegean_outcome = next(
        (
            item
            for item in aegean["implementation_outcomes"]
            if item["implementation_identifier"] == "aegean"
        ),
        None,
    )
    if aegean_outcome is None or aegean_outcome["failed_seeds"]:
        reasons.add("aegean-realization-failed")
    for item in aegean_binding:
        if item["status"] != "pass":
            reasons.add(
                "aegean-metric-"
                f"{item['status']}:{item['metric_id']}:{item['stratum']}"
            )
    return ("pass" if not reasons else "fail", tuple(sorted(reasons)))


def compile_compact_campaign(
    verified: VerifiedTerminalCampaign,
    registry: dict[str, Any],
    repository_root: Path,
) -> dict[str, Any]:
    """Reuse Phase 4R for PyBDSF and exact applicable Aegean endpoints."""
    datasets, recipes = _dataset_maps(
        repository_root / registry["compact_manifest_path"]
    )
    if len(datasets) != 1:
        raise ValueError("compact external manifest must contain one dataset")
    source_dataset = next(iter(datasets.values()))
    dataset = _phase_four_interval_dataset(source_dataset)
    qualified_recipes = {
        (dataset.identifier, seed): recipe.model_copy()
        for (_, seed), recipe in recipes.items()
    }
    phase_four_paths = tuple(
        repository_root / registry[key]
        for key in (
            "phase_four_measurement_path",
            "phase_four_gates_path",
            "phase_four_registry_path",
            "phase_four_protocol_path",
        )
    )
    scientific_hash = contract_set_sha256(phase_four_paths)
    phase_four_registry = load_phase_four_metric_registry(
        repository_root / registry["phase_four_registry_path"]
    )
    phase_four_protocol = load_paired_noninferiority_contract(
        repository_root / registry["phase_four_protocol_path"]
    )
    phase_four_gates = load_phase_four_scientific_gates(
        repository_root / registry["phase_four_gates_path"]
    )
    comparison_hash = canonical_sha256(
        phase_four_protocol.model_dump(mode="json")
    )
    outliers = phase_four_outlier_thresholds(
        repository_root / registry["phase_four_gates_path"]
    )
    measurement = _json_object(
        repository_root / registry["phase_four_measurement_path"]
    )
    minimum_axis_ratio = float(
        measurement["eligibility"]["position_angle_minimum_axis_ratio"]
    )

    pybdsf_campaign = _compact_campaign(
        verified,
        dataset,
        qualified_recipes,
        identifiers=(
            "hebog",
            "released-pybdsf",
            "pinned-pybdsf-master",
        ),
        scientific_contract_set_sha256=scientific_hash,
        comparison_protocol_sha256=comparison_hash,
        outlier_thresholds=outliers,
        position_angle_minimum_axis_ratio=minimum_axis_ratio,
    )
    pybdsf_decision = evaluate_phase_four_recovery(
        pybdsf_campaign,
        dataset,
        phase_four_registry,
        phase_four_protocol,
        phase_four_gates,
        stage="qualification",
        scientific_contract_set_sha256=scientific_hash,
        candidate_identifier="hebog",
        reference_identifiers=(
            "released-pybdsf",
            "pinned-pybdsf-master",
        ),
        captured_at=verified.terminal.completed_at,
    )
    aegean_campaign = _compact_campaign(
        verified,
        dataset,
        qualified_recipes,
        identifiers=("hebog", "aegean", "released-pybdsf"),
        scientific_contract_set_sha256=scientific_hash,
        comparison_protocol_sha256=comparison_hash,
        outlier_thresholds=outliers,
        position_angle_minimum_axis_ratio=minimum_axis_ratio,
    )
    aegean_decision = evaluate_phase_four_recovery(
        aegean_campaign,
        dataset,
        phase_four_registry,
        phase_four_protocol,
        phase_four_gates,
        stage="qualification",
        scientific_contract_set_sha256=scientific_hash,
        candidate_identifier="hebog",
        reference_identifiers=("aegean", "released-pybdsf"),
        captured_at=verified.terminal.completed_at,
    )
    pybdsf_document = pybdsf_decision.model_dump(mode="json")
    aegean_document = aegean_decision.model_dump(mode="json")
    compact_policy = registry["compact"]
    expected_pybdsf = int(
        compact_policy["pybdsf_expected_endpoint_count_per_reference"]
    )
    pybdsf_counts = Counter(
        item["reference_identifier"]
        for item in pybdsf_document["metric_decisions"]
    )
    if set(pybdsf_counts.values()) != {expected_pybdsf}:
        raise ValueError("Phase 4R PyBDSF endpoint population changed")
    expected_keys = set(
        _derived_compact_endpoint_keys(registry, repository_root)
    )
    for reference_identifier in (
        "released-pybdsf",
        "pinned-pybdsf-master",
    ):
        observed_keys = {
            (item["metric_id"], item["stratum"])
            for item in pybdsf_document["metric_decisions"]
            if item["reference_identifier"] == reference_identifier
        }
        if observed_keys != expected_keys:
            raise ValueError(
                f"{reference_identifier} Phase 4R endpoint identities changed"
            )
    aegean_binding = select_aegean_binding_decisions(aegean_document, registry)
    if len(aegean_binding) != compact_policy["aegean_expected_endpoint_count"]:
        raise ValueError("Aegean binding endpoint population changed")
    expected_aegean_keys = {
        key
        for key in expected_keys
        if key[0] in compact_policy["aegean_applicable_metric_ids"]
    }
    observed_aegean_keys = {
        (item["metric_id"], item["stratum"]) for item in aegean_binding
    }
    if observed_aegean_keys != expected_aegean_keys:
        raise ValueError("Aegean binding endpoint identities changed")
    status, reasons = _compact_status(
        pybdsf_document,
        aegean_document,
        aegean_binding,
    )
    return {
        "status": status,
        "failure_reasons": list(reasons),
        "source_manifest_role": source_dataset.role.value,
        "phase_four_interval_engine_mode": "qualification-bca",
        "phase_four_pybdsf_decision": pybdsf_document,
        "phase_four_aegean_decision": aegean_document,
        "aegean_binding_metric_decisions": list(aegean_binding),
    }


def _parse_args() -> argparse.Namespace:
    """Parse sealed campaign, registry, and write-once output paths."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument(
        "--registry",
        type=Path,
        default=(
            root / "config/contracts/phase-5-external-endpoint-registry.json"
        ),
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def compile_terminal_analysis(
    campaign_path: Path,
    registry_path: Path,
    compiler_path: Path,
) -> dict[str, Any]:
    """Compile one sealed campaign into the complete immutable analysis."""
    registry = load_endpoint_registry(registry_path, compiler_path)
    repository_root = compiler_path.parents[2]
    verified = verify_terminal_campaign(
        campaign_path,
        registry,
        repository_root,
    )
    continuum, diagnostics = compile_continuum_campaign(
        verified,
        registry,
        repository_root,
    )
    compact = compile_compact_campaign(
        verified,
        registry,
        repository_root,
    )
    binding_runs = tuple(
        run
        for run in verified.request.runs
        if run.mode in {"candidate", "operational"}
    )
    successful_binding = sum(
        verified.runs[(run.input_id, run.finder_id, run.mode)].result.status
        == "success"
        for run in binding_runs
    )
    expected_ids = tuple(
        item.endpoint_id
        for item in expand_continuum_endpoint_specs(registry)
        if item.binding
    )
    return {
        "schema_version": 1,
        "analysis_id": "phase-5-external-terminal-science",
        "status": "compiled-terminal-science",
        "compiled_at": datetime.now(UTC).isoformat(),
        "compiler_sha256": _file_sha256(compiler_path),
        "endpoint_registry_sha256": _file_sha256(registry_path),
        "campaign_sha256": verified.campaign_sha256,
        "request_sha256": verified.terminal.request_sha256,
        "protocol_sha256": verified.terminal.protocol_sha256,
        "execution_decision_sha256": (
            verified.terminal.execution_decision_sha256
        ),
        "population_audit": {
            "image_count": verified.terminal.image_count,
            "terminal_run_count": verified.terminal.run_count,
            "binding_run_count": len(binding_runs),
            "successful_binding_run_count": successful_binding,
            "failed_binding_run_count": (
                len(binding_runs) - successful_binding
            ),
            "unavailable_binding_run_count": 0,
            "unexpected_run_count": 0,
        },
        "expected_continuum_endpoint_ids": list(expected_ids),
        "continuum_endpoints": [asdict(item) for item in continuum],
        "continuum_diagnostics": [asdict(item) for item in diagnostics],
        "compact": compact,
        "scientific_outcomes_before_runtime": True,
        "step_three_authorized": False,
        "optimization_authorized": False,
        "qualification_opened": False,
    }


def main() -> None:
    """Compile one terminal campaign once after every preflight passes."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite external analysis: {arguments.output}"
        )
    analysis = compile_terminal_analysis(
        arguments.campaign,
        arguments.registry,
        Path(__file__),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as output:
        output.write(_canonical_json_bytes(analysis))


if __name__ == "__main__":
    main()
