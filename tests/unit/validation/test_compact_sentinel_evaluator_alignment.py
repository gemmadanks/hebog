"""Fixture contracts for like-semantics compact sentinel evaluation."""

from __future__ import annotations

import json
import runpy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from hebog.validation.external_runners import canonical_sha256
from hebog.validation.external_successor_compiler import ContinuumTruthObject

_ROOT = Path(__file__).parents[3]
_EVALUATOR = (
    _ROOT
    / "scripts/validation/evaluate_phase5_compact_held_out_sentinel_aligned.py"
)
_ALIGNMENT = _ROOT / "scripts/validation/compact_sentinel_alignment.py"
_PROGRAM = runpy.run_path(str(_ALIGNMENT))
AlignedComponent = _PROGRAM["AlignedComponent"]
AlignedSource = _PROGRAM["AlignedSource"]
AlignedSummaryInput = _PROGRAM["AlignedSummaryInput"]
compile_aligned_summary = _PROGRAM["compile_aligned_summary"]
group_components_by_source = _PROGRAM["group_components_by_source"]
validate_aligned_summary = _PROGRAM["validate_aligned_summary"]


def _truth(
    *, centre_xy: tuple[float, float] = (2.0, 0.0), flux: float = 3.0
) -> tuple[ContinuumTruthObject, ...]:
    return (
        ContinuumTruthObject(
            identifier="truth-source",
            support_label=1,
            centre_xy=centre_xy,
            integrated_flux_jy=flux,
            catalogue_role="astronomical-source",
            strata=("morphology-extended",),
        ),
    )


def _components() -> tuple[Any, ...]:
    return (
        AlignedComponent("component-a", "source-a", 7, (1.0, 0.0), 1.0),
        AlignedComponent("component-b", "source-a", 9, (3.0, 0.0), 2.0),
    )


def _source() -> tuple[Any, ...]:
    return (
        AlignedSource(
            "source-a",
            ("component-a", "component-b"),
            (7, 9),
            (2.0, 0.0),
            3.0,
        ),
    )


def _input(
    *,
    components: tuple[Any, ...] | None = None,
    sources: tuple[Any, ...] | None = None,
    native_owner_labels: np.ndarray | None = None,
    native_topology_domain: str = "component-owner",
    adaptive_background_trigger: str = "below",
) -> Any:
    labels = (
        np.asarray(((7, 7, 0, 9, 9),), dtype=np.int32)
        if native_owner_labels is None
        else native_owner_labels
    )
    return AlignedSummaryInput(
        input_id="fixture-seed-1",
        finder_id="current-hebog",
        truth=_truth(),
        truth_label_plane=np.asarray(((1, 1, 0, 1, 1),), dtype=np.int32),
        sources=_source() if sources is None else sources,
        components=_components() if components is None else components,
        native_owner_label_plane=labels,
        source_union_label_plane=np.asarray(labels > 0, dtype=np.int32),
        native_topology_domain=native_topology_domain,
        published_support_mask=labels > 0,
        beam_fwhm_pixels=2.0,
        adaptive_background_trigger=adaptive_background_trigger,
    )


def test_multiple_components_form_one_binding_source() -> None:
    """Native component multiplicity is not a source-level split."""
    result = compile_aligned_summary(_input())

    assert result["counts"] == {
        "component_count": 2,
        "source_count": 1,
        "source_union_count": 1,
    }
    assert result["metrics"]["split-fraction"] == 0.0
    assert result["component_diagnostic"]["metrics"]["split-fraction"] == 1.0
    assert result["component_diagnostic"]["binding"] is False


def test_pybdsf_multiple_gaussians_are_grouped_by_native_source() -> None:
    """A PyBDSF source is counted once even when it has two Gaussians."""
    components = (
        AlignedComponent(
            "gaussian-1", "island-2-source-4", 3, (0.0, 0.0), 1.0
        ),
        AlignedComponent(
            "gaussian-2", "island-2-source-4", 3, (2.0, 0.0), 3.0
        ),
    )

    sources = group_components_by_source(components)

    assert sources == (
        AlignedSource(
            "island-2-source-4",
            ("gaussian-1", "gaussian-2"),
            (3,),
            (1.5, 0.0),
            4.0,
        ),
    )


def test_one_pybdsf_island_gets_multiple_source_union_owners() -> None:
    """One island is partitioned by native source identity before topology."""
    truth = (
        ContinuumTruthObject(
            "truth-left", 1, (0.5, 0.0), 2.0, "astronomical-source", ()
        ),
        ContinuumTruthObject(
            "truth-right", 2, (10.5, 0.0), 2.0, "astronomical-source", ()
        ),
    )
    components = (
        AlignedComponent("gaussian-left", "source-left", 4, (0.5, 0.0), 2.0),
        AlignedComponent(
            "gaussian-right", "source-right", 4, (10.5, 0.0), 2.0
        ),
    )
    labels = np.full((1, 12), 4, dtype=np.int32)
    truth_labels = np.zeros((1, 12), dtype=np.int32)
    truth_labels[0, :2] = 1
    truth_labels[0, -2:] = 2
    result = compile_aligned_summary(
        replace(
            _input(),
            finder_id="released-pybdsf",
            truth=truth,
            truth_label_plane=truth_labels,
            components=components,
            sources=group_components_by_source(components),
            native_owner_label_plane=labels,
            source_union_label_plane=np.asarray(
                ((1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2),),
                dtype=np.int32,
            ),
            native_topology_domain="island-owner",
            published_support_mask=labels > 0,
            beam_fwhm_pixels=1.0,
        )
    )

    assert result["counts"]["source_union_count"] == 2
    assert result["metrics"]["completeness"] == 1.0
    assert result["metrics"]["split-fraction"] == 0.0
    assert result["metrics"]["merge-fraction"] == 0.0


def test_hebog_multi_component_membership_forms_exact_source_union() -> None:
    """Disjoint Hebog component owners become one source-union owner."""
    result = compile_aligned_summary(_input())

    assert result["source_records"][0]["native_support_labels"] == [7, 9]
    assert result["source_records"][0]["member_component_ids"] == [
        "component-a",
        "component-b",
    ]
    assert result["semantics"]["binding_topology_domain"] == "source-union"


def test_three_peak_connected_compact_source_remains_one_source() -> None:
    """Three Gaussian peaks in one island do not create three sources."""
    components = tuple(
        AlignedComponent(f"g-{index}", "source-a", 4, (float(index), 0.0), 1.0)
        for index in range(3)
    )
    sources = group_components_by_source(components)
    labels = np.full((1, 5), 4, dtype=np.int32)
    result = compile_aligned_summary(
        replace(
            _input(),
            truth=_truth(centre_xy=(1.0, 0.0)),
            truth_label_plane=np.ones((1, 5), dtype=np.int32),
            components=components,
            sources=sources,
            native_owner_label_plane=labels,
            source_union_label_plane=np.ones(labels.shape, dtype=np.int32),
            native_topology_domain="island-owner",
            published_support_mask=labels > 0,
        )
    )

    assert result["counts"]["source_count"] == 1
    assert result["counts"]["component_count"] == 3
    assert result["metrics"]["split-fraction"] == 0.0
    assert result["component_diagnostic"]["metrics"] is None


def test_binding_flux_sums_each_component_once() -> None:
    """Individual component flux is summed once per source."""
    source = group_components_by_source(_components())[0]
    result = compile_aligned_summary(_input(sources=(source,)))

    assert source.integrated_flux_jy == 3.0
    assert [
        item["integrated_flux_jy"] for item in result["component_records"]
    ] == [1.0, 2.0]
    assert result["metrics"]["integrated-flux-median"] == [0.0]


def test_binding_position_uses_source_centroid_not_component_centroid() -> (
    None
):
    """Component locations remain diagnostic while the source centre binds."""
    source = AlignedSource(
        "source-a",
        ("component-a", "component-b"),
        (7, 9),
        (2.0, 0.0),
        3.0,
    )
    result = compile_aligned_summary(_input(sources=(source,)))

    assert result["metrics"]["position-median"] == [0.0]
    assert [item["centre_xy"] for item in result["component_records"]] == [
        [1.0, 0.0],
        [3.0, 0.0],
    ]


def test_source_reliability_ignores_legitimate_component_multiplicity() -> (
    None
):
    """Two legitimate components cannot become two false source rows."""
    result = compile_aligned_summary(_input())

    assert result["metrics"]["reliability"] == 1.0
    assert result["component_diagnostic"]["metrics"]["reliability"] == 0.5


def test_validator_rejects_unlike_binding_topology_domain() -> None:
    """An island-owner summary cannot masquerade as source-union evidence."""
    result = compile_aligned_summary(_input())
    result["semantics"]["binding_topology_domain"] = "island-owner"

    with pytest.raises(ValueError, match="binding topology domain"):
        validate_aligned_summary(result)


def test_binary_mask_metrics_are_invariant_to_positive_relabeling() -> None:
    """Direct support overlap depends on positivity, not owner values."""
    first = compile_aligned_summary(_input())
    relabelled_components = tuple(
        replace(item, native_support_label=item.native_support_label * 10)
        for item in _components()
    )
    relabelled_sources = tuple(
        replace(item, native_support_labels=(70, 90)) for item in _source()
    )
    second = compile_aligned_summary(
        _input(
            components=relabelled_components,
            sources=relabelled_sources,
            native_owner_labels=np.asarray(((70, 70, 0, 90, 90),)),
        )
    )

    for metric in ("mask-precision", "mask-recall", "mask-iou"):
        assert second["metrics"][metric] == first["metrics"][metric]


def test_single_component_flux_and_position_residuals_are_preserved() -> None:
    """Alignment cannot erase a genuine single-source measurement error."""
    component = AlignedComponent("component-a", "source-a", 7, (2.5, 0.0), 2.4)
    source = AlignedSource("source-a", ("component-a",), (7,), (2.5, 0.0), 2.4)
    labels = np.asarray(((7, 7, 7),), dtype=np.int32)
    result = compile_aligned_summary(
        replace(
            _input(),
            truth=_truth(centre_xy=(1.5, 0.0), flux=3.0),
            truth_label_plane=np.ones((1, 3), dtype=np.int32),
            components=(component,),
            sources=(source,),
            native_owner_label_plane=labels,
            source_union_label_plane=np.ones(labels.shape, dtype=np.int32),
            published_support_mask=labels > 0,
        )
    )

    assert result["metrics"]["integrated-flux-median"] == pytest.approx([0.2])
    assert result["metrics"]["position-median"] == [0.5]


def test_below_trigger_control_does_not_change_evaluator_semantics() -> None:
    """Adaptive-trigger strata are metadata, not an evaluator branch."""
    below = compile_aligned_summary(
        _input(adaptive_background_trigger="below")
    )
    above = compile_aligned_summary(
        _input(adaptive_background_trigger="above")
    )

    assert below["metrics"] == above["metrics"]
    assert below["adaptive_background_trigger"] == "below"
    assert above["adaptive_background_trigger"] == "above"


def test_summary_is_array_free_explicit_and_hash_bound() -> None:
    """Retained records carry both semantic levels without image arrays."""
    result = compile_aligned_summary(_input())
    payload = json.dumps(result, allow_nan=False, sort_keys=True)

    assert "array(" not in payload
    assert result["semantics"] == {
        "binary_support_domain": "positive-support",
        "binding_catalogue_level": "source",
        "binding_topology_domain": "source-union",
        "component_catalogue_level": "component",
        "component_diagnostic_binding": False,
        "component_topology_domain": "component-owner",
    }
    assert result["source_records"][0]["source_union_pixel_count"] == 4
    assert (
        len(result["source_records"][0]["source_union_membership_sha256"])
        == 64
    )
    assert result["record_sha256"] == canonical_sha256(
        {key: value for key, value in result.items() if key != "record_sha256"}
    )


@pytest.mark.parametrize(
    ("record_group", "field", "value", "message"),
    [
        (
            "component_records",
            "source_identifier",
            "missing-source",
            "retained source memberships",
        ),
        (
            "source_records",
            "source_union_label",
            0,
            "retained source-union ownership",
        ),
        (
            "source_records",
            "source_union_pixel_count",
            0,
            "retained source-union ownership",
        ),
        (
            "source_records",
            "source_union_membership_sha256",
            "not-a-sha256",
            "retained source-union ownership",
        ),
        (
            "source_records",
            "integrated_flux_jy",
            -1.0,
            "retained source observables",
        ),
        (
            "component_records",
            "centre_xy",
            ["not-a-coordinate", 0.0],
            "retained component observables",
        ),
    ],
)
def test_validator_rejects_rehashed_inconsistent_retained_ownership(
    record_group: str, field: str, value: object, message: str
) -> None:
    """The outer digest cannot make malformed retained ownership valid."""
    result: dict[str, Any] = compile_aligned_summary(_input())
    records = result[record_group]
    assert isinstance(records, list)
    assert isinstance(records[0], dict)
    record = cast(dict[str, Any], records[0])
    record[field] = value
    result["record_sha256"] = canonical_sha256(
        {key: value for key, value in result.items() if key != "record_sha256"}
    )

    with pytest.raises(ValueError, match=message):
        validate_aligned_summary(result)


def test_validator_rejects_rehashed_wrong_schema_version() -> None:
    """A semantic record cannot masquerade as the aligned schema."""
    result: dict[str, Any] = compile_aligned_summary(_input())
    result["schema_version"] = 1
    result["record_sha256"] = canonical_sha256(
        {key: value for key, value in result.items() if key != "record_sha256"}
    )

    with pytest.raises(ValueError, match="aligned summary schema"):
        validate_aligned_summary(result)


def test_valid_empty_finder_result_remains_scientific_evidence() -> None:
    """A source-free result compiles without inventing owners or rows."""
    labels = np.zeros((1, 5), dtype=np.int32)
    result = compile_aligned_summary(
        replace(
            _input(),
            sources=(),
            components=(),
            native_owner_label_plane=labels,
            source_union_label_plane=labels,
            published_support_mask=labels > 0,
        )
    )

    assert result["counts"] == {
        "component_count": 0,
        "source_count": 0,
        "source_union_count": 0,
    }
    assert result["metrics"]["completeness"] == 0.0
    assert result["metrics"]["reliability"] == 0.0


@pytest.mark.parametrize(
    ("changed", "message"),
    [
        (
            {"sources": ()},
            "source memberships must partition components",
        ),
        (
            {"native_owner_label_plane": np.asarray(((7, 7, 0, 11, 11),))},
            "native support labels",
        ),
        (
            {
                "published_support_mask": np.asarray(
                    ((True, True, False, False, False),)
                )
            },
            "published support",
        ),
    ],
)
def test_alignment_fails_closed_on_inconsistent_ownership(
    changed: dict[str, object], message: str
) -> None:
    """Malformed source, component, and mask ownership cannot be scored."""
    with pytest.raises(ValueError, match=message):
        compile_aligned_summary(replace(_input(), **changed))


def _paired_summaries() -> list[dict[str, object]]:
    """Return four paired like-semantics fixture realizations."""
    return [
        compile_aligned_summary(
            replace(
                _input(),
                finder_id=finder_id,
                input_id=f"fixture-seed-{seed}",
                seed=seed,
            )
        )
        for seed in range(4)
        for finder_id in ("current-hebog", "released-pybdsf")
    ]


def test_aligned_evaluator_applies_frozen_gates_to_source_metrics() -> None:
    """The prospective wrapper changes semantics but not decision margins."""
    evaluate = runpy.run_path(str(_EVALUATOR))["evaluate_summaries"]

    decision = evaluate(
        _paired_summaries(),
        expected_cell_ids=("fixture-cell",),
        realizations_per_cell=4,
        dask_comparisons=tuple({"equal": True} for _index in range(12)),
    )

    assert decision["status"] == "pass"
    assert decision["pooling_used"] is False


def test_aligned_evaluator_rejects_legacy_or_tampered_summary() -> None:
    """A legacy component/island record cannot enter the new decision lane."""
    evaluate = runpy.run_path(str(_EVALUATOR))["evaluate_summaries"]
    summaries = _paired_summaries()
    semantics = summaries[0]["semantics"]
    assert isinstance(semantics, dict)
    semantics["binding_catalogue_level"] = "component"

    with pytest.raises(ValueError, match="source/component semantics"):
        evaluate(
            summaries,
            expected_cell_ids=("fixture-cell",),
            realizations_per_cell=4,
            dask_comparisons=tuple({"equal": True} for _index in range(12)),
        )
