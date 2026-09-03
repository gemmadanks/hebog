#!/usr/bin/env python3
"""Use explicit association provenance in paired tail diagnostics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from hebog.validation.parent_construction_association_evaluation import (
    continuum_catalogue_objects_from_association,
    load_source_association,
)

TailCompiler = Callable[..., dict[str, object]]


def truth_linked_tail_record(
    *,
    parent_tail: TailCompiler,
    compiler_globals: Mapping[str, Any],
    **arguments: Any,
) -> dict[str, object]:
    """Delegate the repaired tail with a sidecar-aware candidate boundary."""
    catalogue_and_labels = compiler_globals.get("_catalogue_and_labels")
    fallback_candidates = compiler_globals.get("_candidate_objects")
    artifact_path = compiler_globals.get("_artifact_path")
    if not all(
        callable(item)
        for item in (catalogue_and_labels, fallback_candidates, artifact_path)
    ):
        raise ValueError("paired source-union tail compiler seam changed")
    active_run: Any | None = None

    def contextual_catalogue_and_labels(run: Any) -> Any:
        nonlocal active_run
        if active_run is not None:
            raise ValueError("paired source-union tail run context overlapped")
        active_run = run
        return cast(Callable[[Any], Any], catalogue_and_labels)(run)

    def provenance_candidates(
        catalogue: Any,
        label_plane: Any,
        *,
        finder_id: str,
        header: Any,
    ) -> tuple[Any, ...]:
        nonlocal active_run
        run = active_run
        active_run = None
        if run is None or getattr(run.result, "finder_id", None) != finder_id:
            raise ValueError("paired source-union tail run context changed")
        if finder_id != "hebog":
            return cast(Callable[..., tuple[Any, ...]], fallback_candidates)(
                catalogue,
                label_plane,
                finder_id=finder_id,
                header=header,
            )
        sidecar = cast(Callable[[Any, str], Any], artifact_path)(
            run, "source-association-json"
        )
        return cast(
            tuple[Any, ...],
            continuum_catalogue_objects_from_association(
                catalogue,
                label_plane,
                load_source_association(sidecar),
                finder_id=finder_id,
                header=header,
            ),
        )

    repaired = {
        **dict(compiler_globals),
        "_candidate_objects": provenance_candidates,
        "_catalogue_and_labels": contextual_catalogue_and_labels,
    }
    result = parent_tail(compiler_globals=repaired, **arguments)
    if active_run is not None:
        raise ValueError(
            "paired source-union tail run context was not consumed"
        )
    return result
