"""Prospective Phase 5 parity and Hebog-retention contract.

The contract is intentionally independent of candidate results. It expands
the previously frozen compact and Continuum registries, binds one complete
closed Hebog incumbent, and fails closed when a binding comparison is missing
or inconclusive. Existing absolute science thresholds remain visible as
longer-term objectives while product-validity and provenance invariants remain
binding.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Self, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from hebog.validation.external_runners import canonical_sha256, file_sha256

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_COMMIT_PATTERN = r"^[0-9a-f]{40}$"
_REGISTRY_ID = "phase-5-prospective-science-endpoint-registry"
_CONTRACT_ID = "phase-5-prospective-science-decision-contract"
_COMPACT_ENDPOINT_COUNT = 225
_CONTINUUM_BINDING_ENDPOINT_COUNT = 143
_CONTINUUM_OBJECTIVE_ENDPOINT_COUNT = 15
_HISTORICAL_LEDGER_COUNT = 9
_ONE_SIDED_CONFIDENCE_LEVEL = 0.95
_BINDING_SAFETY_INVARIANTS = (
    "finite-measurements",
    "product-validity",
    "schema-and-provenance-integrity",
    "serial-and-existing-dask-determinism",
    "write-once-publication",
)
_ACTIVATION_REQUIREMENTS = (
    "human-scientific-approval-of-exact-contract-sha256",
    "prospective-evaluator-implementation-and-boundary-tests",
    "prospective-power-audit-for-every-binding-endpoint",
    "non-promotional-scientific-smoke-lane-pass",
    "exact-incumbent-runtime-and-paired-evidence-preflight",
)
_COMPARATORS = frozenset(
    {
        "aegean",
        "incumbent-hebog",
        "pinned-pybdsf-master",
        "released-pybdsf",
    }
)
_CONTINUUM_POLICY: dict[str, tuple[str, str, str, float | None]] = {
    "completeness": (
        "higher-is-better",
        "fraction",
        "injected-truth astronomical sources",
        0.02,
    ),
    "reliability": (
        "higher-is-better",
        "fraction",
        "accepted catalogue sources",
        0.02,
    ),
    "integrated-flux-median": (
        "lower-is-better",
        "fractional-error",
        "matched injected-truth astronomical sources",
        0.05,
    ),
    "integrated-flux-p95": (
        "lower-is-better",
        "fractional-error",
        "matched injected-truth astronomical sources",
        0.05,
    ),
    "absolute-mean-offset-x": (
        "lower-is-better",
        "restoring-beam-fwhm",
        "matched irregular-segment astronomical sources",
        0.05,
    ),
    "absolute-mean-offset-y": (
        "lower-is-better",
        "restoring-beam-fwhm",
        "matched irregular-segment astronomical sources",
        0.05,
    ),
    "position-median": (
        "lower-is-better",
        "restoring-beam-fwhm",
        "matched irregular-segment astronomical sources",
        None,
    ),
    "position-p95": (
        "lower-is-better",
        "restoring-beam-fwhm",
        "matched astronomical sources with comparable positions",
        0.05,
    ),
    "duplicate-fraction": (
        "lower-is-better",
        "fraction",
        "injected-truth astronomical sources",
        0.01,
    ),
    "mask-precision": (
        "higher-is-better",
        "fraction",
        "valid image pixels",
        0.05,
    ),
    "mask-recall": (
        "higher-is-better",
        "fraction",
        "valid image pixels",
        0.05,
    ),
    "mask-iou": (
        "higher-is-better",
        "fraction",
        "valid image pixels",
        0.05,
    ),
    "split-fraction": (
        "lower-is-better",
        "fraction",
        "injected-truth astronomical sources",
        0.02,
    ),
    "merge-fraction": (
        "lower-is-better",
        "fraction",
        "injected-truth astronomical sources",
        0.02,
    ),
}


class _FrozenModel(BaseModel):
    """Strict immutable base for prospective contract records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class FileBinding(_FrozenModel):
    """One exact path and byte digest."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        """Require a normalized repository-relative evidence path."""
        candidate = Path(self.path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("bound evidence path must be repository-relative")
        if candidate.as_posix() != self.path:
            raise ValueError("bound evidence path must be normalized")
        return self


class ProspectiveEndpoint(_FrozenModel):
    """One explicit governed endpoint and its applicable comparators."""

    endpoint_id: str = Field(min_length=1)
    lane: Literal["compact", "continuum"]
    metric_family: str = Field(min_length=1)
    stratum: str = Field(min_length=1)
    role: Literal["binding", "longer-term-objective"]
    desirable_direction: Literal["higher-is-better", "lower-is-better"]
    unit: str = Field(min_length=1)
    population: str = Field(min_length=1)
    statistic: str = Field(min_length=1)
    value_kind: str = Field(min_length=1)
    comparators: tuple[str, ...]
    practical_regression_margins: dict[str, float]
    cross_finder_applicability: str = Field(min_length=1)
    missing_output_outcome: str = Field(min_length=1)
    absolute_policy: Literal["report-not-compatibility-blocker"]

    @model_validator(mode="after")
    def validate_comparators(self) -> Self:
        """Keep each endpoint complete, ordered, and internally consistent."""
        if self.comparators != tuple(sorted(set(self.comparators))):
            raise ValueError("endpoint comparators must be sorted and unique")
        if not set(self.comparators).issubset(_COMPARATORS):
            raise ValueError("endpoint comparator is unsupported")
        if set(self.practical_regression_margins) != set(self.comparators):
            raise ValueError("endpoint margins and comparators differ")
        if any(
            value < 0.0 for value in self.practical_regression_margins.values()
        ):
            raise ValueError("endpoint margin must be non-negative")
        if (
            self.role == "binding"
            and "incumbent-hebog" not in self.comparators
        ):
            raise ValueError("binding endpoint lacks incumbent retention")
        if self.role == "longer-term-objective" and self.comparators:
            raise ValueError("objective endpoint cannot be co-primary")
        return self


class ProspectiveEndpointCounts(_FrozenModel):
    """Exact registry cardinalities frozen before candidate evidence."""

    total_endpoints: int
    compact_binding_endpoints: int
    continuum_binding_endpoints: int
    continuum_objective_endpoints: int
    pybdsf_endpoints_per_reference: int
    aegean_endpoints: int
    incumbent_retention_endpoints: int
    total_coprimary_comparisons: int


class ProspectiveEndpointRegistry(_FrozenModel):
    """Complete explicit prospective endpoint registry."""

    schema_version: Literal[1]
    registry_id: str
    status: str
    source_bindings: tuple[FileBinding, ...]
    counts: ProspectiveEndpointCounts
    endpoints: tuple[ProspectiveEndpoint, ...]

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        """Require every endpoint and comparator frozen by Section 3.1."""
        if (
            self.registry_id != _REGISTRY_ID
            or self.status != "frozen-before-candidate-results"
        ):
            raise ValueError("prospective endpoint registry identity differs")
        identifiers = tuple(item.endpoint_id for item in self.endpoints)
        if identifiers != tuple(sorted(set(identifiers))):
            raise ValueError(
                "prospective endpoint IDs must be sorted and unique"
            )
        compact = tuple(
            item for item in self.endpoints if item.lane == "compact"
        )
        continuum_binding = tuple(
            item
            for item in self.endpoints
            if item.lane == "continuum" and item.role == "binding"
        )
        continuum_objectives = tuple(
            item
            for item in self.endpoints
            if item.lane == "continuum"
            and item.role == "longer-term-objective"
        )
        calculated = ProspectiveEndpointCounts(
            total_endpoints=len(self.endpoints),
            compact_binding_endpoints=len(compact),
            continuum_binding_endpoints=len(continuum_binding),
            continuum_objective_endpoints=len(continuum_objectives),
            pybdsf_endpoints_per_reference=sum(
                "released-pybdsf" in item.comparators
                for item in self.endpoints
            ),
            aegean_endpoints=sum(
                "aegean" in item.comparators for item in self.endpoints
            ),
            incumbent_retention_endpoints=sum(
                "incumbent-hebog" in item.comparators
                for item in self.endpoints
            ),
            total_coprimary_comparisons=sum(
                len(item.comparators) for item in self.endpoints
            ),
        )
        expected = ProspectiveEndpointCounts(
            total_endpoints=(
                _COMPACT_ENDPOINT_COUNT
                + _CONTINUUM_BINDING_ENDPOINT_COUNT
                + _CONTINUUM_OBJECTIVE_ENDPOINT_COUNT
            ),
            compact_binding_endpoints=_COMPACT_ENDPOINT_COUNT,
            continuum_binding_endpoints=_CONTINUUM_BINDING_ENDPOINT_COUNT,
            continuum_objective_endpoints=_CONTINUUM_OBJECTIVE_ENDPOINT_COUNT,
            pybdsf_endpoints_per_reference=338,
            aegean_endpoints=143,
            incumbent_retention_endpoints=368,
            total_coprimary_comparisons=1187,
        )
        if self.counts != calculated or self.counts != expected:
            raise ValueError("prospective endpoint counts differ")
        master_count = sum(
            "pinned-pybdsf-master" in item.comparators
            for item in self.endpoints
        )
        if master_count != self.counts.pybdsf_endpoints_per_reference:
            raise ValueError("PyBDSF reference endpoint sets differ")
        if len({item.path for item in self.source_bindings}) != len(
            self.source_bindings
        ):
            raise ValueError("prospective registry source bindings differ")
        return self


class ProspectiveAuthorization(_FrozenModel):
    """Explicit non-executable authorization boundary."""

    execution_authorized: Literal[False]
    replay_identity_freeze_authorized: Literal[False]
    qualification_authorized: Literal[False]
    tuning_authorized: Literal[False]
    rescoring_authorized: Literal[False]
    cutover_authorized: Literal[False]
    release_authorized: Literal[False]


class ProspectiveIncumbent(_FrozenModel):
    """One whole closed Hebog candidate selected before replacement results."""

    candidate_revision: str = Field(pattern=_COMMIT_PATTERN)
    source_tree_sha256: str = Field(pattern=_SHA256_PATTERN)
    configuration_sha256: str = Field(pattern=_SHA256_PATTERN)
    ledger: FileBinding
    selection_rule: str
    realization_evidence: str
    selection_rationale: str


class ProspectiveDecisionRule(_FrozenModel):
    """Intersection-union rule for all co-primary comparisons."""

    combination_rule: Literal["intersection-union-every-coprimary-comparison"]
    one_sided_confidence_level: float
    confidence_limit_rule: Literal[
        "observed-paired-realization-upper-limit-at-or-below-frozen-margin"
    ]
    underpowered_outcome: Literal["parity-or-retention-not-demonstrated"]
    missing_candidate_outcome: Literal["binding-fail"]
    missing_comparator_outcome: Literal["underpowered-global-fail"]
    planning_variance_role: Literal[
        "design-and-assumption-audit-only-not-observed-data-gate"
    ]
    multiplicity: Literal[
        "none-required-for-intersection-union-noninferiority"
    ]
    superiority_policy: Literal[
        "descriptive-unless-prospective-multiplicity-procedure"
    ]

    @model_validator(mode="after")
    def validate_confidence_level(self) -> Self:
        """Require the frozen one-sided confidence level exactly."""
        if self.one_sided_confidence_level != _ONE_SIDED_CONFIDENCE_LEVEL:
            raise ValueError("prospective confidence level differs")
        return self


class ProspectiveAbsolutePolicy(_FrozenModel):
    """Separation of compatibility gates from improvement objectives."""

    numeric_science_targets: Literal["report-as-longer-term-objectives"]
    binding_safety_invariants: tuple[str, ...]

    @model_validator(mode="after")
    def validate_safety_invariants(self) -> Self:
        """Keep safety independent of the longer-term numeric targets."""
        if self.binding_safety_invariants != _BINDING_SAFETY_INVARIANTS:
            raise ValueError("prospective absolute policy differs")
        return self


class ProspectiveResampling(_FrozenModel):
    """Lane-specific realization-level resampling identities."""

    independent_unit: Literal["noise-seed-image"]
    method: Literal["paired-bca-bootstrap"]
    paired: Literal[True]
    compact_seed: Literal[20260807]
    continuum_seed: Literal[20260810]
    resamples: Literal[50000]


class ProspectiveScienceDecisionContract(_FrozenModel):
    """Complete non-executable prospective Phase 5 decision contract."""

    schema_version: Literal[1]
    contract_id: str
    status: str
    active: bool
    endpoint_registry: FileBinding
    endpoint_registry_canonical_sha256: str = Field(pattern=_SHA256_PATTERN)
    endpoint_counts: ProspectiveEndpointCounts
    incumbent: ProspectiveIncumbent
    decision: ProspectiveDecisionRule
    absolute_policy: ProspectiveAbsolutePolicy
    resampling: ProspectiveResampling
    historical_policy: str
    historical_ledgers: tuple[FileBinding, ...]
    committed_source_bindings: tuple[FileBinding, ...]
    activation_requirements: tuple[str, ...]
    authorization: ProspectiveAuthorization

    @model_validator(mode="after")
    def validate_identity_and_history(self) -> Self:
        """Require the non-executable whole-incumbent historical policy."""
        if (
            self.contract_id != _CONTRACT_ID
            or self.status != "frozen-for-human-scientific-review"
            or self.active
        ):
            raise ValueError("prospective science contract identity differs")
        if self.incumbent.selection_rule != (
            "one-whole-closed-candidate-no-endpoint-envelope"
        ):
            raise ValueError("retention requires one whole closed candidate")
        if self.incumbent.realization_evidence != (
            "exact-paired-reexecution-required-no-preserved-raw-incumbent-products"
        ):
            raise ValueError("incumbent realization evidence rule differs")
        if self.historical_policy != (
            "immutable-original-gates-no-retrospective-rescoring"
        ):
            raise ValueError("historical decision policy differs")
        if len(self.historical_ledgers) != _HISTORICAL_LEDGER_COUNT or len(
            {item.path for item in self.historical_ledgers}
        ) != len(self.historical_ledgers):
            raise ValueError("historical ledger bindings differ")
        if self.incumbent.ledger not in self.historical_ledgers:
            raise ValueError("incumbent ledger is not historically bound")
        return self

    @model_validator(mode="after")
    def validate_activation_and_sources(self) -> Self:
        """Require exact activation prerequisites and committed bindings."""
        if self.activation_requirements != _ACTIVATION_REQUIREMENTS:
            raise ValueError("prospective activation requirements differ")
        committed_paths = tuple(
            item.path for item in self.committed_source_bindings
        )
        if committed_paths != tuple(sorted(set(committed_paths))):
            raise ValueError("prospective committed sources differ")
        return self


def _load_json(path: Path, *, label: str) -> object:
    """Read one JSON document with a stable fail-closed error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} cannot be loaded") from error


def load_prospective_endpoint_registry(
    path: Path,
) -> ProspectiveEndpointRegistry:
    """Load and validate the frozen all-check endpoint registry."""
    try:
        return ProspectiveEndpointRegistry.model_validate(
            _load_json(path, label="prospective endpoint registry")
        )
    except ValidationError as error:
        raise ValueError(str(error)) from error


def load_prospective_science_contract(
    path: Path,
    *,
    endpoint_registry: ProspectiveEndpointRegistry,
) -> ProspectiveScienceDecisionContract:
    """Load the prospective decision contract against its exact registry."""
    try:
        contract = ProspectiveScienceDecisionContract.model_validate(
            _load_json(path, label="prospective science contract")
        )
    except ValidationError as error:
        raise ValueError(str(error)) from error
    registry_sha256 = canonical_sha256(
        endpoint_registry.model_dump(mode="json")
    )
    if (
        contract.endpoint_registry_canonical_sha256 != registry_sha256
        or contract.endpoint_counts != endpoint_registry.counts
    ):
        raise ValueError("prospective contract endpoint registry differs")
    return contract


def verify_prospective_contract_sources(
    contract: ProspectiveScienceDecisionContract,
    *,
    root: Path,
) -> None:
    """Verify every committed source bound by the contract."""
    bindings = (
        contract.endpoint_registry,
        *contract.committed_source_bindings,
    )
    if len({item.path for item in bindings}) != len(bindings):
        raise ValueError("prospective committed source paths must be unique")
    for binding in bindings:
        path = root / binding.path
        if not path.is_file() or file_sha256(path) != binding.sha256:
            raise ValueError(
                f"prospective committed source differs: {binding.path}"
            )


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    """Require one JSON object for deterministic registry construction."""
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, *, label: str) -> Sequence[object]:
    """Require one JSON array for deterministic registry construction."""
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return cast(Sequence[object], value)


def _number(value: object, *, label: str) -> float:
    """Require one finite JSON number used as a frozen margin."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    converted = float(value)
    if not 0.0 <= converted < float("inf"):
        raise ValueError(f"{label} must be finite and non-negative")
    return converted


def _compact_endpoints(
    metric_registry: Mapping[str, object],
    incumbent_ledger: Mapping[str, object],
) -> list[dict[str, object]]:
    """Expand all 225 compact endpoints without inspecting their outcomes."""
    metrics = {
        cast(str, row["metric_id"]): row
        for item in _sequence(
            metric_registry.get("metrics"), label="compact metrics"
        )
        for row in (_mapping(item, label="compact metric"),)
    }
    compact = _mapping(
        incumbent_ledger.get("prospective_compact"), label="incumbent compact"
    )
    decision = _mapping(
        compact.get("phase_four_pybdsf_decision"), label="compact decision"
    )
    rows = tuple(
        row
        for item in _sequence(
            decision.get("metric_decisions"), label="compact endpoints"
        )
        for row in (_mapping(item, label="compact endpoint"),)
        if row.get("reference_identifier") == "released-pybdsf"
    )
    aegean_rows = tuple(
        _mapping(item, label="Aegean endpoint")
        for item in _sequence(
            compact.get("aegean_binding_metric_decisions"),
            label="Aegean endpoints",
        )
    )
    aegean_keys = {
        (cast(str, row["metric_id"]), cast(str, row["stratum"]))
        for row in aegean_rows
    }
    endpoints: list[dict[str, object]] = []
    for row in rows:
        metric_id = cast(str, row["metric_id"])
        stratum = cast(str, row["stratum"])
        metric = metrics[metric_id]
        primary_margin = _number(
            metric["primary_practical_regression_margin"],
            label="primary compact margin",
        )
        secondary_margin = _number(
            metric["secondary_practical_regression_margin"],
            label="secondary compact margin",
        )
        comparators = {
            "incumbent-hebog": max(primary_margin, secondary_margin),
            "pinned-pybdsf-master": secondary_margin,
            "released-pybdsf": primary_margin,
        }
        if (metric_id, stratum) in aegean_keys:
            comparators["aegean"] = primary_margin
        endpoints.append(
            {
                "absolute_policy": "report-not-compatibility-blocker",
                "comparators": sorted(comparators),
                "cross_finder_applicability": "all-listed-comparators-binding",
                "desirable_direction": metric["desirable_direction"],
                "endpoint_id": f"compact--{metric_id}--{stratum}",
                "lane": "compact",
                "metric_family": metric_id,
                "missing_output_outcome": (
                    "candidate-fail-comparator-underpowered-global-fail"
                ),
                "population": metric["population"],
                "practical_regression_margins": dict(
                    sorted(comparators.items())
                ),
                "role": "binding",
                "statistic": metric["statistic"],
                "stratum": stratum,
                "unit": metric["unit"],
                "value_kind": "phase-4-realization-metric",
            }
        )
    if (
        len(endpoints) != _COMPACT_ENDPOINT_COUNT
        or len(aegean_keys) != _CONTINUUM_BINDING_ENDPOINT_COUNT
    ):
        raise ValueError("compact endpoint topology differs")
    return endpoints


def _continuum_endpoints(
    source_registry: Mapping[str, object],
) -> list[dict[str, object]]:
    """Expand all 143 binding and 15 objective Continuum endpoints."""
    endpoints: list[dict[str, object]] = []
    for item in _sequence(
        source_registry.get("continuum"), label="Continuum metrics"
    ):
        row = _mapping(item, label="Continuum metric")
        metric_id = cast(str, row["metric_family"])
        direction, unit, population, margin = _CONTINUUM_POLICY[metric_id]
        source_role = cast(str, row["role"])
        role = (
            "binding" if source_role == "binding" else "longer-term-objective"
        )
        cross_finder = row.get("paired") is not False and role == "binding"
        for stratum in _sequence(row.get("strata"), label="Continuum strata"):
            if not isinstance(stratum, str):
                raise ValueError("Continuum stratum must be a string")
            comparators: dict[str, float] = {}
            if role == "binding":
                if margin is None:
                    raise ValueError("binding Continuum margin is missing")
                comparators["incumbent-hebog"] = margin
                if cross_finder:
                    comparators["pinned-pybdsf-master"] = margin
                    comparators["released-pybdsf"] = margin
            endpoints.append(
                {
                    "absolute_policy": "report-not-compatibility-blocker",
                    "comparators": sorted(comparators),
                    "cross_finder_applicability": (
                        "all-listed-comparators-binding"
                        if cross_finder
                        else (
                            "not-applicable-irregular-segment-centroid-semantics"
                            if role == "binding"
                            else "not-applicable-report-only-objective"
                        )
                    ),
                    "desirable_direction": direction,
                    "endpoint_id": f"continuum--{metric_id}--{stratum}",
                    "lane": "continuum",
                    "metric_family": metric_id,
                    "missing_output_outcome": (
                        "candidate-fail-comparator-underpowered-global-fail"
                        if role == "binding"
                        else "report-indeterminate-no-promotion-effect"
                    ),
                    "population": population,
                    "practical_regression_margins": dict(
                        sorted(comparators.items())
                    ),
                    "role": role,
                    "statistic": row["statistic"],
                    "stratum": stratum,
                    "unit": unit,
                    "value_kind": row["value_kind"],
                }
            )
    return endpoints


def build_prospective_endpoint_registry(
    *,
    source_registry: Mapping[str, object],
    metric_registry: Mapping[str, object],
    incumbent_ledger: Mapping[str, object],
    source_bindings: Sequence[Mapping[str, str]],
) -> ProspectiveEndpointRegistry:
    """Build the all-check registry from pre-candidate sources."""
    endpoints = sorted(
        (
            *_compact_endpoints(metric_registry, incumbent_ledger),
            *_continuum_endpoints(source_registry),
        ),
        key=lambda item: cast(str, item["endpoint_id"]),
    )
    document: dict[str, Any] = {
        "schema_version": 1,
        "registry_id": _REGISTRY_ID,
        "status": "frozen-before-candidate-results",
        "source_bindings": list(source_bindings),
        "counts": {
            "total_endpoints": (
                _COMPACT_ENDPOINT_COUNT
                + _CONTINUUM_BINDING_ENDPOINT_COUNT
                + _CONTINUUM_OBJECTIVE_ENDPOINT_COUNT
            ),
            "compact_binding_endpoints": _COMPACT_ENDPOINT_COUNT,
            "continuum_binding_endpoints": _CONTINUUM_BINDING_ENDPOINT_COUNT,
            "continuum_objective_endpoints": (
                _CONTINUUM_OBJECTIVE_ENDPOINT_COUNT
            ),
            "pybdsf_endpoints_per_reference": 338,
            "aegean_endpoints": 143,
            "incumbent_retention_endpoints": 368,
            "total_coprimary_comparisons": 1187,
        },
        "endpoints": endpoints,
    }
    return ProspectiveEndpointRegistry.model_validate(document)
