"""Prospective source-level topology contracts for future evidence."""

from __future__ import annotations

import inspect

import numpy as np

from hebog.validation.external_successor_compiler import ContinuumTruthObject
from hebog.validation.source_association_evaluation_repair import (
    AssociatedContinuumCatalogueObject,
    measure_prospective_source_topology,
)


def _truth() -> tuple[ContinuumTruthObject, ...]:
    return (
        ContinuumTruthObject(
            identifier="truth-one",
            support_label=1,
            centre_xy=(2.5, 0.0),
            integrated_flux_jy=2.0,
            catalogue_role="astronomical-source",
            strata=("morphology-shell",),
        ),
    )


def test_source_union_topology_is_binding_and_components_are_diagnostic() -> (
    None
):
    """Two native fragments in one source are not a binding split."""
    labels = np.asarray(((7, 7, 0, 9, 9, 9),), dtype=np.int32)
    source = AssociatedContinuumCatalogueObject(
        identifier="source-one",
        support_labels=(7, 9),
        centre_xy=(2.5, 0.0),
        integrated_flux_jy=2.0,
    )

    result = measure_prospective_source_topology(
        _truth(),
        (source,),
        truth_label_plane=np.asarray(((1, 1, 0, 1, 1, 1),)),
        candidate_label_plane=labels,
        beam_fwhm_pixels=2.0,
    )

    assert result.binding_metrics["split-fraction"] == {
        "morphology-shell": 0.0,
        "overall": 0.0,
    }
    assert result.binding_metrics["merge-fraction"] == {
        "morphology-shell": 0.0,
        "overall": 0.0,
    }
    assert result.binding_metrics["duplicate-fraction"] == {
        "morphology-shell": 0.0,
        "overall": 0.0,
    }
    assert result.binding_metrics["reliability"]["overall"] == 1.0
    assert result.native_component_split_fraction == {
        "morphology-shell": 1.0,
        "overall": 1.0,
    }
    assert result.native_component_merge_fraction == {
        "morphology-shell": 0.0,
        "overall": 0.0,
    }


def test_source_union_merge_is_binding_not_hidden_by_components() -> None:
    """One catalogue source spanning two truths is a binding source merge."""
    truth = (
        _truth()[0],
        ContinuumTruthObject(
            identifier="truth-two",
            support_label=2,
            centre_xy=(8.5, 0.0),
            integrated_flux_jy=2.0,
            catalogue_role="astronomical-source",
            strata=("morphology-shell",),
        ),
    )
    truth_labels = np.asarray(((1, 1, 0, 2, 2, 2),), dtype=np.int32)
    candidate_labels = np.asarray(((7, 7, 0, 9, 9, 9),), dtype=np.int32)
    merged = AssociatedContinuumCatalogueObject(
        identifier="source-merged",
        support_labels=(7, 9),
        centre_xy=(5.5, 0.0),
        integrated_flux_jy=4.0,
    )

    result = measure_prospective_source_topology(
        truth,
        (merged,),
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=2.0,
    )

    assert result.binding_metrics["merge-fraction"]["overall"] == 1.0


def test_prospective_topology_has_no_closed_evidence_input() -> None:
    """The future evaluator cannot accept a ledger or campaign path."""
    parameter_names = set(
        inspect.signature(measure_prospective_source_topology).parameters
    )

    assert parameter_names == {
        "truth",
        "catalogue",
        "truth_label_plane",
        "candidate_label_plane",
        "beam_fwhm_pixels",
    }
