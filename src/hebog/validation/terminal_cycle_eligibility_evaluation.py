# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Prospective validation for terminal-cycle eligibility evidence.

This overlay leaves the frozen terminal-feature persistence evaluator
byte-identical. It requires the bounded pre-eligibility and unseeded-cycle
census on every prospective Hebog association sidecar while delegating all
binding catalogue measurements to the closed evaluator chain.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from hebog.data_models.source_association import (
    SourceAssociationResult,
    SourceHierarchyDiagnostics,
)
from hebog.validation.parent_construction_association_evaluation import (
    AssociationPath,
)
from hebog.validation.terminal_feature_persistence_evaluation import (
    TerminalFeaturePersistenceContinuumImageCompiler,
)
from hebog.validation.terminal_feature_persistence_evaluation import (
    source_association_from_json as _base_source_association_from_json,
)

_RUN_ARGUMENT_POSITION = 2
_ELIGIBILITY_COUNT_FIELDS = (
    "terminal_cycle_pre_eligibility_candidate_count",
    "terminal_cycle_unseeded_candidate_count",
    "terminal_cycle_unseeded_persistent_accepted_count",
    "terminal_cycle_unseeded_persistence_rejected_count",
)


def _required_integer(row: Mapping[str, object], name: str) -> int:
    """Read one exact integer without accepting booleans."""
    value = row.get(name)
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def source_association_from_json(value: object) -> SourceAssociationResult:
    """Parse the frozen association shape plus the eligibility census."""
    association = _base_source_association_from_json(value)
    if association.hierarchy_diagnostics is None:
        return association
    document = cast(Mapping[str, object], value)
    row = cast(Mapping[str, object], document["hierarchy_diagnostics"])
    fields = {
        name: _required_integer(row, name)
        for name in _ELIGIBILITY_COUNT_FIELDS
    }
    return replace(
        association,
        hierarchy_diagnostics=replace(
            association.hierarchy_diagnostics,
            **fields,
        ),
    )


def load_source_association(path: Path) -> SourceAssociationResult:
    """Load one required prospective association sidecar."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            "terminal-cycle eligibility association cannot be loaded"
        ) from error
    return source_association_from_json(value)


def _required_diagnostics(
    association: SourceAssociationResult,
) -> SourceHierarchyDiagnostics:
    """Require the bounded hierarchy census on one candidate sidecar."""
    diagnostics = association.hierarchy_diagnostics
    if diagnostics is None:
        raise ValueError("terminal-cycle eligibility diagnostics are required")
    return diagnostics


def aggregate_terminal_cycle_eligibility(
    paths: Iterable[Path],
    *,
    expected_image_count: int,
) -> dict[str, int]:
    """Reduce exactly one bounded eligibility record per Continuum image."""
    if type(expected_image_count) is not int or expected_image_count < 1:
        raise ValueError("expected image count must be a positive integer")
    ordered = tuple(sorted(Path(path) for path in paths))
    if len(set(ordered)) != len(ordered):
        raise ValueError(
            "terminal-cycle eligibility sidecar paths must be unique"
        )
    if len(ordered) != expected_image_count:
        raise ValueError("terminal-cycle eligibility sidecar count differs")
    diagnostics = tuple(
        _required_diagnostics(load_source_association(path))
        for path in ordered
    )
    return {
        "image_count": len(diagnostics),
        "pre_eligibility_candidate_count": sum(
            item.terminal_cycle_pre_eligibility_candidate_count
            for item in diagnostics
        ),
        "schema_version": 1,
        "unseeded_candidate_count": sum(
            item.terminal_cycle_unseeded_candidate_count
            for item in diagnostics
        ),
        "unseeded_persistence_rejected_count": sum(
            item.terminal_cycle_unseeded_persistence_rejected_count
            for item in diagnostics
        ),
        "unseeded_persistent_accepted_count": sum(
            item.terminal_cycle_unseeded_persistent_accepted_count
            for item in diagnostics
        ),
    }


class TerminalCycleEligibilityContinuumImageCompiler(
    TerminalFeaturePersistenceContinuumImageCompiler
):
    """Require the eligibility census before closed science compilation."""

    def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Validate prospective Hebog evidence before closed evaluation."""
        run = (
            args[_RUN_ARGUMENT_POSITION]
            if len(args) > _RUN_ARGUMENT_POSITION
            else kwargs.get("run")
        )
        result = getattr(run, "result", None)
        if (
            getattr(result, "status", None) == "success"
            and getattr(result, "finder_id", None) == "hebog"
        ):
            _required_diagnostics(
                load_source_association(self._association_path(run))
            )
        return super().__call__(*args, **kwargs)


def install_terminal_cycle_eligibility_evaluation(
    terminal_globals: dict[str, Any],
    *,
    association_path: AssociationPath,
) -> None:
    """Layer eligibility validation over terminal persistence validation."""
    current = terminal_globals.get("_continuum_image_observations")
    if not isinstance(
        current,
        TerminalFeaturePersistenceContinuumImageCompiler,
    ) or not callable(association_path):
        raise ValueError("terminal-cycle eligibility evaluation seam changed")
    terminal_globals["_continuum_image_observations"] = (
        TerminalCycleEligibilityContinuumImageCompiler(
            terminal_globals,
            association_path=association_path,
        )
    )
