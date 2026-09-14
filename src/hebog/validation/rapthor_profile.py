"""Fail-closed retained/rejected component profile comparison.

This module compares decisions produced by the exact external LSMTool
filtering boundary. It deliberately does not reproduce LSMTool mask lookup,
sector clipping, patch grouping, or apparent-sky name transfer.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

ProfileLaneIdentifier = Literal[
    "compact",
    "continuum",
    "released-pybdsf-used-by-rapthor",
    "pinned-pybdsf-master",
]

_LANE_IDENTIFIERS: tuple[ProfileLaneIdentifier, ...] = (
    "compact",
    "continuum",
    "released-pybdsf-used-by-rapthor",
    "pinned-pybdsf-master",
)


@dataclass(frozen=True, slots=True)
class ComponentDecision:
    """One stable input component and its post-filter membership."""

    identifier: str
    retained: bool
    strata: frozenset[str]

    def __post_init__(self) -> None:
        """Reject identities or strata that cannot be audited."""
        if not self.identifier:
            raise ValueError("component identifier must not be empty")
        if not self.strata or any(not item for item in self.strata):
            raise ValueError("component strata must be non-empty strings")


@dataclass(frozen=True, slots=True)
class Agreement:
    """Exact binary membership agreement for one population."""

    component_count: int
    matching_count: int
    agreement: float


@dataclass(frozen=True, slots=True)
class StratumAgreement:
    """One named safety-lane agreement result."""

    stratum: str
    observation: Agreement
    passed: bool


@dataclass(frozen=True, slots=True)
class RapthorProfileDecision:
    """Conjunctive compact-versus-continuum workflow decision."""

    selected_profile: Literal["compact", "continuum"]
    complete: bool
    overall: Agreement
    strata: tuple[StratumAgreement, ...]
    missing_strata: tuple[str, ...]
    failed_strata: tuple[str, ...]
    disagreement_identifiers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComponentDecisionLane:
    """One complete post-LSMTool profile or reference population."""

    identifier: ProfileLaneIdentifier
    components: tuple[ComponentDecision, ...]


@dataclass(frozen=True, slots=True)
class ReferenceAgreement:
    """Pairwise workflow membership agreement with one reference."""

    profile_identifier: Literal["compact", "continuum"]
    reference_identifier: Literal[
        "released-pybdsf-used-by-rapthor",
        "pinned-pybdsf-master",
    ]
    complete: bool
    overall: Agreement
    strata: tuple[StratumAgreement, ...]
    missing_strata: tuple[str, ...]
    failed_strata: tuple[str, ...]
    disagreement_identifiers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RapthorProfileEvidenceDecision:
    """Terminal selection plus non-compensating reference comparisons."""

    selection: RapthorProfileDecision
    reference_comparisons: tuple[ReferenceAgreement, ...]


def _index_decisions(
    decisions: Iterable[ComponentDecision],
    *,
    label: str,
) -> dict[str, ComponentDecision]:
    indexed: dict[str, ComponentDecision] = {}
    for decision in decisions:
        if decision.identifier in indexed:
            raise ValueError(
                f"{label} repeats component identifier {decision.identifier!r}"
            )
        indexed[decision.identifier] = decision
    return indexed


def _agreement(
    identifiers: Iterable[str],
    continuum: dict[str, ComponentDecision],
    compact: dict[str, ComponentDecision],
) -> Agreement:
    population = tuple(identifiers)
    matching = sum(
        continuum[identifier].retained == compact[identifier].retained
        for identifier in population
    )
    return Agreement(
        component_count=len(population),
        matching_count=matching,
        agreement=(matching / len(population) if population else 0.0),
    )


def decide_rapthor_profile(
    continuum_decisions: Iterable[ComponentDecision],
    compact_decisions: Iterable[ComponentDecision],
    *,
    required_strata: Iterable[str],
    minimum_agreement: float,
) -> RapthorProfileDecision:
    """Select compact only after complete conjunctive membership agreement.

    Component identities and strata describe the common pre-filter population
    and therefore must match exactly between profiles. Missing safety evidence
    is incomplete and safely retains the continuum profile.
    """
    if not 0.0 <= minimum_agreement <= 1.0:
        raise ValueError("minimum agreement must be between zero and one")
    supplied_strata = tuple(required_strata)
    canonical_strata = tuple(sorted(supplied_strata))
    if not canonical_strata or any(not item for item in canonical_strata):
        raise ValueError("required strata must be non-empty strings")
    if len(set(canonical_strata)) != len(canonical_strata):
        raise ValueError("required strata must not contain duplicates")

    continuum = _index_decisions(continuum_decisions, label="continuum")
    compact = _index_decisions(compact_decisions, label="compact")
    if set(continuum) != set(compact):
        raise ValueError("compact and continuum component identities differ")
    for identifier in continuum:
        if continuum[identifier].strata != compact[identifier].strata:
            raise ValueError(
                "compact and continuum component strata differ for "
                f"{identifier!r}"
            )

    identifiers = tuple(sorted(continuum))
    overall = _agreement(identifiers, continuum, compact)
    rows: list[StratumAgreement] = []
    missing: list[str] = []
    failed: list[str] = []
    for stratum in canonical_strata:
        members = tuple(
            identifier
            for identifier in identifiers
            if stratum in continuum[identifier].strata
        )
        observation = _agreement(members, continuum, compact)
        if not members:
            missing.append(stratum)
        elif observation.agreement < minimum_agreement:
            failed.append(stratum)
        rows.append(
            StratumAgreement(
                stratum=stratum,
                observation=observation,
                passed=bool(members)
                and observation.agreement >= minimum_agreement,
            )
        )

    complete = bool(identifiers) and not missing
    compact_passed = (
        complete and overall.agreement >= minimum_agreement and not failed
    )
    disagreements = tuple(
        identifier
        for identifier in identifiers
        if continuum[identifier].retained != compact[identifier].retained
    )
    return RapthorProfileDecision(
        selected_profile="compact" if compact_passed else "continuum",
        complete=complete,
        overall=overall,
        strata=tuple(rows),
        missing_strata=tuple(missing),
        failed_strata=tuple(failed),
        disagreement_identifiers=disagreements,
    )


def decide_rapthor_profile_evidence(
    lanes: Iterable[ComponentDecisionLane],
    *,
    required_strata: Iterable[str],
    minimum_agreement: float,
) -> RapthorProfileEvidenceDecision:
    """Evaluate the exact four controlled-runner membership lanes.

    The compact selection is based only on its agreement with the qualified
    continuum profile. Released and pinned-master PyBDSF comparisons are
    always reported independently and cannot compensate for that decision.
    """
    supplied = tuple(lanes)
    if tuple(item.identifier for item in supplied) != _LANE_IDENTIFIERS:
        raise ValueError("profile evidence requires four canonical lanes")
    indexed = {item.identifier: item.components for item in supplied}
    canonical_strata = tuple(required_strata)
    selection = decide_rapthor_profile(
        indexed["continuum"],
        indexed["compact"],
        required_strata=canonical_strata,
        minimum_agreement=minimum_agreement,
    )
    comparisons: list[ReferenceAgreement] = []
    for profile_identifier in ("compact", "continuum"):
        for reference_identifier in (
            "released-pybdsf-used-by-rapthor",
            "pinned-pybdsf-master",
        ):
            comparison = decide_rapthor_profile(
                indexed[profile_identifier],
                indexed[reference_identifier],
                required_strata=canonical_strata,
                minimum_agreement=minimum_agreement,
            )
            comparisons.append(
                ReferenceAgreement(
                    profile_identifier=profile_identifier,
                    reference_identifier=reference_identifier,
                    complete=comparison.complete,
                    overall=comparison.overall,
                    strata=comparison.strata,
                    missing_strata=comparison.missing_strata,
                    failed_strata=comparison.failed_strata,
                    disagreement_identifiers=(
                        comparison.disagreement_identifiers
                    ),
                )
            )
    return RapthorProfileEvidenceDecision(
        selection=selection,
        reference_comparisons=tuple(comparisons),
    )
