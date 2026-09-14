#!/usr/bin/env python3
"""Adapt paired truth-linked summaries to associated-source unions."""

from __future__ import annotations

import runpy
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256
from hebog.validation.source_association_evaluation_repair import (
    AssociatedContinuumCatalogueObject,
    _associated_context,
)

_ROOT = Path(__file__).parents[2]
_PARENT_PREPARER = (
    _ROOT / "scripts/validation/prepare_phase5_prospective_paired_evidence.py"
)
_PARENT_PREPARER_SHA256 = (
    "54f1416d544c7cc4dd84591dcf22e2ced21c24722286cea55e6b1e1d3c72ba77"
)


class _SourceUnionSuccessor:
    """Forward legacy helpers while dispatching associated-source context."""

    def __init__(self, successor: Any) -> None:
        self._successor = successor

    def __getattr__(self, name: str) -> Any:
        return getattr(self._successor, name)

    def _topology_support_objects(
        self, native_supports: tuple[Any, ...], catalogue: tuple[Any, ...]
    ) -> tuple[Any, ...]:
        associated = tuple(
            item
            for item in catalogue
            if isinstance(item, AssociatedContinuumCatalogueObject)
        )
        if not associated:
            return cast(
                tuple[Any, ...],
                self._successor._topology_support_objects(
                    native_supports, catalogue
                ),
            )
        if len(associated) != len(catalogue):
            raise ValueError(
                "continuum catalogue cannot mix support semantics"
            )
        return native_supports

    def _association_context(
        self,
        truth: tuple[Any, ...],
        catalogue: tuple[Any, ...],
        native_supports: tuple[Any, ...],
        *,
        label_planes: tuple[Any, Any],
        beam_fwhm_pixels: float,
    ) -> Any:
        associated = tuple(
            item
            for item in catalogue
            if isinstance(item, AssociatedContinuumCatalogueObject)
        )
        if not associated:
            return self._successor._association_context(
                truth,
                catalogue,
                native_supports,
                label_planes=label_planes,
                beam_fwhm_pixels=beam_fwhm_pixels,
            )
        if len(associated) != len(catalogue):
            raise ValueError(
                "continuum catalogue cannot mix support semantics"
            )
        truth_labels, association_labels = label_planes
        return _associated_context(
            truth,
            associated,
            truth_labels=truth_labels,
            candidate_labels=association_labels,
            beam_fwhm_pixels=beam_fwhm_pixels,
        )


@lru_cache(maxsize=1)
def _parent_preparer() -> dict[str, Any]:
    """Load the exact historical preparer into an isolated globals mapping."""
    if file_sha256(_PARENT_PREPARER) != _PARENT_PREPARER_SHA256:
        raise ValueError("prospective paired parent preparer changed")
    parent = runpy.run_path(str(_PARENT_PREPARER))
    build = parent.get("build_truth_linked_continuum_summary")
    if not callable(build):
        raise ValueError("prospective paired parent preparer seam changed")
    successor = build.__globals__.get("successor")
    if successor is None:
        raise ValueError("prospective paired successor seam changed")
    build.__globals__["successor"] = _SourceUnionSuccessor(successor)
    return cast(dict[str, Any], parent)


def build_truth_linked_continuum_summary(
    **arguments: Any,
) -> dict[str, object]:
    """Build one summary with exact source-union membership semantics."""
    catalogue = tuple(arguments.get("catalogue", ()))
    associated = tuple(
        item
        for item in catalogue
        if isinstance(item, AssociatedContinuumCatalogueObject)
    )
    if associated and len(associated) != len(catalogue):
        raise ValueError("continuum catalogue cannot mix support semantics")
    if associated:
        counts = arguments.get("source_member_counts")
        if not isinstance(counts, Mapping) or any(
            counts.get(source.identifier) != len(source.support_labels)
            for source in associated
        ):
            raise ValueError(
                "source membership counts do not match associated "
                "support unions"
            )
    parent = _parent_preparer()
    return cast(
        dict[str, object],
        parent["build_truth_linked_continuum_summary"](**arguments),
    )


_PARENT_EXPORTS = _parent_preparer()
build_aligned_prospective_power_audit = _PARENT_EXPORTS[
    "build_aligned_prospective_power_audit"
]
build_array_free_endpoint_summary = _PARENT_EXPORTS[
    "build_array_free_endpoint_summary"
]
evaluate_prospective_cumulative_evidence = _PARENT_EXPORTS[
    "evaluate_prospective_cumulative_evidence"
]
select_result_neutral_tail_sentinels = _PARENT_EXPORTS[
    "select_result_neutral_tail_sentinels"
]
