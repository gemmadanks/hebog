# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Prospective validation for terminal-feature persistence evidence.

This overlay leaves the frozen parent-construction evaluator byte-identical.
It requires the new array-free rejection census on every prospective Hebog
association sidecar and reduces only those bounded counts for the terminal
cumulative ledger. Binding catalogue measurements remain delegated to the
closed sidecar-aware evaluator.
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
    ParentConstructionContinuumImageCompiler,
)
from hebog.validation.parent_construction_association_evaluation import (
    source_association_from_json as _base_source_association_from_json,
)

_RUN_ARGUMENT_POSITION = 2
_PROSPECTIVE_DIAGNOSTIC_COUNT_FIELDS = (
    "connected_support_candidate_count",
    "rejected_connected_support_ambiguity_count",
    "terminal_cycle_candidate_count",
    "terminal_cycle_parent_count",
    "rejected_terminal_cycle_count",
    "terminal_persistence_exact_feature_count",
    "terminal_persistence_displaced_candidate_count",
    "terminal_persistence_displaced_accepted_count",
    "terminal_persistence_missing_child_count",
    "terminal_persistence_ambiguous_child_count",
    "terminal_persistence_conflict_count",
)


def _required_integer(row: Mapping[str, object], name: str) -> int:
    """Read one exact integer without accepting booleans."""
    value = row.get(name)
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def source_association_from_json(value: object) -> SourceAssociationResult:
    """Parse the frozen association shape plus the new required census."""
    association = _base_source_association_from_json(value)
    if association.hierarchy_diagnostics is None:
        return association
    document = cast(Mapping[str, object], value)
    row = cast(Mapping[str, object], document["hierarchy_diagnostics"])
    fields = {
        name: _required_integer(row, name)
        for name in _PROSPECTIVE_DIAGNOSTIC_COUNT_FIELDS
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
            "terminal persistence association cannot be loaded"
        ) from error
    return source_association_from_json(value)


def _required_diagnostics(
    association: SourceAssociationResult,
) -> SourceHierarchyDiagnostics:
    """Require the bounded hierarchy census on one candidate sidecar."""
    diagnostics = association.hierarchy_diagnostics
    if diagnostics is None:
        raise ValueError("terminal persistence diagnostics are required")
    return diagnostics


def aggregate_terminal_feature_persistence(
    paths: Iterable[Path],
    *,
    expected_image_count: int,
) -> dict[str, int]:
    """Reduce exactly one bounded diagnostic record per Continuum image."""
    if type(expected_image_count) is not int or expected_image_count < 1:
        raise ValueError("expected image count must be a positive integer")
    ordered = tuple(sorted(Path(path) for path in paths))
    if len(set(ordered)) != len(ordered):
        raise ValueError("terminal persistence sidecar paths must be unique")
    if len(ordered) != expected_image_count:
        raise ValueError("terminal persistence sidecar count differs")
    diagnostics = tuple(
        _required_diagnostics(load_source_association(path))
        for path in ordered
    )
    return {
        "ambiguous_child_count": sum(
            item.terminal_persistence_ambiguous_child_count
            for item in diagnostics
        ),
        "displaced_accepted_count": sum(
            item.terminal_persistence_displaced_accepted_count
            for item in diagnostics
        ),
        "displaced_candidate_count": sum(
            item.terminal_persistence_displaced_candidate_count
            for item in diagnostics
        ),
        "exact_feature_count": sum(
            item.terminal_persistence_exact_feature_count
            for item in diagnostics
        ),
        "image_count": len(diagnostics),
        "missing_child_count": sum(
            item.terminal_persistence_missing_child_count
            for item in diagnostics
        ),
        "rejected_terminal_cycle_count": sum(
            item.rejected_terminal_cycle_count for item in diagnostics
        ),
        "schema_version": 1,
        "terminal_cycle_candidate_count": sum(
            item.terminal_cycle_candidate_count for item in diagnostics
        ),
        "terminal_cycle_parent_count": sum(
            item.terminal_cycle_parent_count for item in diagnostics
        ),
        "whole_group_conflict_count": sum(
            item.terminal_persistence_conflict_count for item in diagnostics
        ),
    }


class TerminalFeaturePersistenceContinuumImageCompiler(
    ParentConstructionContinuumImageCompiler
):
    """Require the new census before delegating binding measurements."""

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


def install_terminal_feature_persistence_evaluation(
    terminal_globals: dict[str, Any],
    *,
    association_path: AssociationPath,
) -> None:
    """Layer census validation over the exact closed science compiler."""
    current = terminal_globals.get("_continuum_image_observations")
    if not isinstance(current, ParentConstructionContinuumImageCompiler) or (
        not callable(association_path)
    ):
        raise ValueError("terminal persistence evaluation seam changed")
    terminal_globals["_continuum_image_observations"] = (
        TerminalFeaturePersistenceContinuumImageCompiler(
            terminal_globals,
            association_path=association_path,
        )
    )
