# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Analytic mechanism checks for terminal-cycle source-association corrections.

The frozen case manifest defines a small population of positive activations
and controls. Each case is evaluated through the production association
kernel; the lane passes only when every activation and control behaves as
declared. It is regression evidence, not promotion evidence.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from hebog.data_models.source_association import SourceAssociationResult

_MINIMUM_CASE_COUNT = 20
_MAXIMUM_CASE_COUNT = 40
_LANE_ID = "phase-5-terminal-cycle-mechanism-activation"
_REQUIRED_FAMILIES = frozenset(
    {
        "persistent-unseeded-geometry",
        "nonpersistent-unseeded-geometry",
        "terminal-bridge",
        "terminal-pair",
        "terminal-path",
        "disconnected-support",
        "ambiguous-child",
        "partial-group-conflict",
    }
)


@dataclass(frozen=True, slots=True)
class TerminalCycleCase:
    """One immutable analytic mechanism expectation."""

    case_id: str
    family: str
    variant: int
    expected_maximum_membership_size: int
    expected_terminal_parent_count: int
    expected_unseeded_accepted_count: int


@dataclass(frozen=True, slots=True)
class TerminalCycleCaseManifest:
    """The complete non-promotional analytic mechanism population."""

    lane_id: str
    cases: tuple[TerminalCycleCase, ...]


@dataclass(frozen=True, slots=True)
class TerminalCycleCaseObservation:
    """Array-free observation from one production association result."""

    case_id: str
    family: str
    maximum_membership_size: int
    pre_eligibility_candidate_count: int
    terminal_parent_count: int
    unseeded_candidate_count: int
    unseeded_persistent_accepted_count: int


def _integer(value: object, *, label: str, minimum: int = 0) -> int:
    """Require one exact bounded integer without accepting booleans."""
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def load_terminal_cycle_case_manifest(
    path: Path,
) -> TerminalCycleCaseManifest:
    """Load the frozen 20--40-case analytic activation population."""
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            "terminal-cycle case manifest cannot be loaded"
        ) from error
    if not isinstance(value, dict):
        raise ValueError("terminal-cycle case manifest must be an object")
    document = cast(dict[str, object], value)
    rows_value = document.get("cases")
    if (
        document.get("schema_version") != 1
        or document.get("evidence_role") != "analytic-non-promotional"
        or document.get("promotion_evidence") is not False
        or document.get("lane_id") != _LANE_ID
        or not isinstance(rows_value, list)
        or not (_MINIMUM_CASE_COUNT <= len(rows_value) <= _MAXIMUM_CASE_COUNT)
    ):
        raise ValueError("terminal-cycle case manifest policy changed")
    rows = cast(list[object], rows_value)
    cases: list[TerminalCycleCase] = []
    for row_value in rows:
        if not isinstance(row_value, dict):
            raise ValueError("terminal-cycle case must be an object")
        row = cast(dict[str, object], row_value)
        case_id = row.get("case_id")
        family = row.get("family")
        if not isinstance(case_id, str) or not isinstance(family, str):
            raise ValueError("terminal-cycle case identity is malformed")
        cases.append(
            TerminalCycleCase(
                case_id=case_id,
                family=family,
                variant=_integer(row.get("variant"), label="case variant"),
                expected_maximum_membership_size=_integer(
                    row.get("expected_maximum_membership_size"),
                    label="expected maximum membership size",
                    minimum=1,
                ),
                expected_terminal_parent_count=_integer(
                    row.get("expected_terminal_parent_count"),
                    label="expected terminal parent count",
                ),
                expected_unseeded_accepted_count=_integer(
                    row.get("expected_unseeded_accepted_count"),
                    label="expected unseeded accepted count",
                ),
            )
        )
    identifiers = tuple(case.case_id for case in cases)
    families = frozenset(case.family for case in cases)
    if identifiers != tuple(sorted(identifiers)) or len(
        set(identifiers)
    ) != len(identifiers):
        raise ValueError("terminal-cycle case IDs must be sorted and unique")
    if families != _REQUIRED_FAMILIES:
        raise ValueError("terminal-cycle case families changed")
    return TerminalCycleCaseManifest(
        lane_id=cast(str, document["lane_id"]),
        cases=tuple(cases),
    )


def observe_terminal_cycle_case(
    case: TerminalCycleCase,
    association: SourceAssociationResult,
) -> TerminalCycleCaseObservation:
    """Reduce one exact producer result to bounded mechanism evidence."""
    diagnostics = association.hierarchy_diagnostics
    if diagnostics is None:
        raise ValueError("terminal-cycle hierarchy diagnostics are required")
    return TerminalCycleCaseObservation(
        case_id=case.case_id,
        family=case.family,
        maximum_membership_size=max(
            (len(item.component_ids) for item in association.memberships),
            default=0,
        ),
        pre_eligibility_candidate_count=(
            diagnostics.terminal_cycle_pre_eligibility_candidate_count
        ),
        terminal_parent_count=diagnostics.terminal_cycle_parent_count,
        unseeded_candidate_count=(
            diagnostics.terminal_cycle_unseeded_candidate_count
        ),
        unseeded_persistent_accepted_count=(
            diagnostics.terminal_cycle_unseeded_persistent_accepted_count
        ),
    )


def evaluate_terminal_cycle_mechanism_lane(
    manifest: TerminalCycleCaseManifest,
    observations: Sequence[TerminalCycleCaseObservation],
) -> dict[str, object]:
    """Require activation, all controls, and exact case cardinality."""
    by_id = {item.case_id: item for item in observations}
    if len(by_id) != len(observations) or set(by_id) != {
        case.case_id for case in manifest.cases
    }:
        raise ValueError("terminal-cycle mechanism observations differ")
    positive_activation = 0
    pre_guard_rejections = 0
    for case in manifest.cases:
        observation = by_id[case.case_id]
        if observation.family != case.family:
            raise ValueError("terminal-cycle mechanism family differs")
        if (
            observation.maximum_membership_size
            != case.expected_maximum_membership_size
            or observation.terminal_parent_count
            != case.expected_terminal_parent_count
            or observation.unseeded_persistent_accepted_count
            != case.expected_unseeded_accepted_count
        ):
            raise ValueError(
                f"terminal-cycle mechanism expectation failed: {case.case_id}"
            )
        if case.family == "persistent-unseeded-geometry":
            if (
                observation.pre_eligibility_candidate_count < 1
                or observation.unseeded_candidate_count < 1
                or observation.unseeded_persistent_accepted_count < 1
            ):
                raise ValueError("terminal-cycle repair did not activate")
            positive_activation += (
                observation.unseeded_persistent_accepted_count
            )
            pre_guard_rejections += observation.unseeded_candidate_count
        elif observation.unseeded_persistent_accepted_count:
            raise ValueError("terminal-cycle negative control activated")
    if positive_activation < 1 or pre_guard_rejections < 1:
        raise ValueError("terminal-cycle activation census is empty")
    return {
        "schema_version": 1,
        "lane_id": manifest.lane_id,
        "case_count": len(manifest.cases),
        "family_count": len(_REQUIRED_FAMILIES),
        "positive_activation_count": positive_activation,
        "pre_guard_rejection_count": pre_guard_rejections,
        "all_controls_pass": True,
        "promotion_evidence": False,
    }
