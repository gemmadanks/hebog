"""Prospective paired cumulative-evidence preparation tests."""

from __future__ import annotations

import json
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
    ContinuumTruthObject,
)
from hebog.validation.prospective_science_contract import (
    ProspectiveEndpoint,
    ProspectiveEndpointCounts,
    ProspectiveEndpointRegistry,
    load_prospective_endpoint_registry,
)
from hebog.validation.source_association_evaluation_repair import (
    AssociatedContinuumCatalogueObject,
)

_ROOT = Path(__file__).parents[3]
_PROGRAM = (
    _ROOT / "scripts/validation/prepare_phase5_prospective_paired_evidence.py"
)
_SOURCE_UNION_PROGRAM = (
    _ROOT / "scripts/validation/"
    "prepare_phase5_prospective_paired_source_union_evidence.py"
)
_REQUEST = (
    _ROOT / "benchmark-results/phase-5/external-post-failure-comparison/"
    "campaign-request.json"
)
_MANIFEST = (
    _ROOT / "config/datasets/phase-5-external-post-failure-continuum.json"
)
_SMOKE = (
    _ROOT / "benchmark-results/phase-5/"
    "prospective-science-smoke-publication-scale-persistence.json"
)


def _program() -> dict[str, Any]:
    """Load the evaluation-only program without executing its CLI."""
    return runpy.run_path(str(_PROGRAM))


def _source_union_program() -> dict[str, Any]:
    """Load the prospective adapter over the immutable parent preparer."""
    return runpy.run_path(str(_SOURCE_UNION_PROGRAM))


def test_source_union_preparer_preserves_parent_program_and_entry_points() -> (
    None
):
    """The overlay composes every evaluator entry point without mutation."""
    program = _source_union_program()

    assert (
        file_sha256(program["_PARENT_PREPARER"])
        == program["_PARENT_PREPARER_SHA256"]
    )
    for name in (
        "build_aligned_prospective_power_audit",
        "build_array_free_endpoint_summary",
        "build_truth_linked_continuum_summary",
        "evaluate_prospective_cumulative_evidence",
        "select_result_neutral_tail_sentinels",
    ):
        assert callable(program[name])


def _endpoint(
    endpoint_id: str,
    *,
    lane: str,
    role: str = "binding",
    comparators: tuple[str, ...] = (),
    margin: float = 0.05,
) -> ProspectiveEndpoint:
    """Build one focused registry endpoint."""
    return ProspectiveEndpoint(
        endpoint_id=endpoint_id,
        lane=cast(Any, lane),
        metric_family=endpoint_id.split("--")[1],
        stratum="overall",
        role=cast(Any, role),
        desirable_direction="higher-is-better",
        unit="fraction",
        population="fixture population",
        statistic="rate",
        value_kind="scalar",
        comparators=comparators,
        practical_regression_margins=dict.fromkeys(comparators, margin),
        cross_finder_applicability="fixture",
        missing_output_outcome=(
            "candidate-fail-comparator-underpowered-global-fail"
            if role == "binding"
            else "report-indeterminate-no-promotion-effect"
        ),
        absolute_policy="report-not-compatibility-blocker",
    )


def _registry() -> ProspectiveEndpointRegistry:
    """Return a cardinality-relaxed registry for focused decisions."""
    endpoints = (
        _endpoint(
            "compact--completeness--overall",
            lane="compact",
            comparators=(
                "aegean",
                "incumbent-hebog",
                "pinned-pybdsf-master",
                "released-pybdsf",
            ),
        ),
        _endpoint(
            "continuum--reliability--overall",
            lane="continuum",
            comparators=(
                "incumbent-hebog",
                "pinned-pybdsf-master",
                "released-pybdsf",
            ),
        ),
        _endpoint(
            "continuum--position-median--overall",
            lane="continuum",
            role="longer-term-objective",
        ),
    )
    return ProspectiveEndpointRegistry.model_construct(
        schema_version=1,
        registry_id="phase-5-prospective-science-endpoint-registry",
        status="frozen-before-candidate-results",
        source_bindings=(),
        counts=ProspectiveEndpointCounts(
            total_endpoints=3,
            compact_binding_endpoints=1,
            continuum_binding_endpoints=1,
            continuum_objective_endpoints=1,
            pybdsf_endpoints_per_reference=2,
            aegean_endpoints=1,
            incumbent_retention_endpoints=2,
            total_coprimary_comparisons=7,
        ),
        endpoints=endpoints,
    )


def _comparisons() -> list[dict[str, object]]:
    """Return all seven passing fixture comparisons."""
    return [
        {
            "candidate_available": True,
            "comparator_available": True,
            "comparator_id": comparator,
            "endpoint_id": endpoint.endpoint_id,
            "observed_paired_standard_deviation": (
                0.08 if comparator != "aegean" else None
            ),
            "planning_paired_standard_deviation": 0.06,
            "positive_regression": 0.01,
            "upper_confidence_limit": 0.04,
        }
        for endpoint in _registry().endpoints
        for comparator in endpoint.comparators
    ]


def _safety(**changes: bool) -> dict[str, bool]:
    values = {
        "finite-measurements": True,
        "product-validity": True,
        "schema-and-provenance-integrity": True,
        "serial-and-existing-dask-determinism": True,
        "write-once-publication": True,
    }
    values.update(changes)
    return values


def test_cumulative_adapter_separates_every_decision_section() -> None:
    """Objectives and planning audits cannot hide comparator evidence."""
    evaluate = _program()["evaluate_prospective_cumulative_evidence"]
    record = evaluate(
        registry=_registry(),
        comparisons=_comparisons(),
        safety_results=_safety(),
        absolute_objectives=(
            {
                "candidate_status": "success",
                "candidate_value": 0.7,
                "endpoint_id": "continuum--position-median--overall",
                "objective_passed": False,
                "objective_value": 0.5,
            },
        ),
    )

    assert record["status"] == "pass"
    assert record["cumulative_science_regression_ready"] is True
    assert record["all_required_endpoints_pass"] is True
    assert record["section_counts"] == {
        "aegean_parity": 1,
        "binding_safety": 5,
        "incumbent_retention": 2,
        "longer_term_absolute_objectives": 1,
        "pybdsf_parity": 4,
    }
    assert record["planning_assumption_audit"]["deviation_count"] == 6
    assert (
        record["longer_term_absolute_objectives"][0]["objective_passed"]
        is False
    )


@pytest.mark.parametrize(
    ("mutation", "expected_status"),
    [
        ("missing", "incomplete"),
        ("underpowered", "incomplete"),
        ("material-regression", "fail"),
        ("candidate-missing", "fail"),
    ],
)
def test_cumulative_adapter_fails_closed(
    mutation: str, expected_status: str
) -> None:
    """Missing, inconclusive, and materially bad evidence cannot pass."""
    evaluate = _program()["evaluate_prospective_cumulative_evidence"]
    rows = _comparisons()
    if mutation == "missing":
        rows.pop()
    elif mutation == "underpowered":
        rows[0]["upper_confidence_limit"] = 0.06
    elif mutation == "material-regression":
        rows[0]["positive_regression"] = 0.051
        rows[0]["upper_confidence_limit"] = 0.07
    else:
        rows[0]["candidate_available"] = False

    record = evaluate(
        registry=_registry(),
        comparisons=rows,
        safety_results=_safety(),
        absolute_objectives=(
            {
                "candidate_status": "success",
                "candidate_value": 0.4,
                "endpoint_id": "continuum--position-median--overall",
                "objective_passed": True,
                "objective_value": 0.5,
            },
        ),
    )

    assert record["status"] == expected_status
    assert record["cumulative_science_regression_ready"] is False


def test_binding_safety_is_independent_and_fail_closed() -> None:
    """Green science comparisons cannot compensate for invalid products."""
    evaluate = _program()["evaluate_prospective_cumulative_evidence"]
    record = evaluate(
        registry=_registry(),
        comparisons=_comparisons(),
        safety_results=_safety(**{"product-validity": False}),
        absolute_objectives=(
            {
                "candidate_status": "success",
                "candidate_value": 0.4,
                "endpoint_id": "continuum--position-median--overall",
                "objective_passed": True,
                "objective_value": 0.5,
            },
        ),
    )

    assert record["status"] == "fail"
    assert all(item["status"] == "pass" for item in record["pybdsf_parity"])
    assert record["binding_safety"]["product-validity"] is False


def test_truth_linked_summary_is_array_free_and_reconstructable() -> None:
    """Transient planes reduce to bounded truth-linked scientific rows."""
    build = _source_union_program()["build_truth_linked_continuum_summary"]
    truth = (
        ContinuumTruthObject(
            identifier="shell",
            support_label=1,
            centre_xy=(1.0, 1.0),
            integrated_flux_jy=2.0,
            catalogue_role="astronomical-source",
            strata=("morphology-shell", "scale-4-beam", "tile-corner"),
        ),
        ContinuumTruthObject(
            identifier="artifact",
            support_label=2,
            centre_xy=(3.0, 3.0),
            integrated_flux_jy=1.0,
            catalogue_role="artifact",
            strata=("morphology-artifact", "varying-noise"),
        ),
    )
    catalogue = (
        ContinuumCatalogueObject("source-a", 7, (1.0, 1.0), 2.2),
        ContinuumCatalogueObject("source-b", 8, (1.3, 1.1), 0.4),
    )
    truth_labels = np.array(
        [[0, 0, 0, 0], [0, 1, 1, 0], [0, 1, 1, 0], [0, 0, 0, 2]],
        dtype=np.int64,
    )
    candidate_labels = np.array(
        [[0, 0, 0, 0], [0, 7, 7, 0], [0, 7, 8, 0], [0, 0, 0, 0]],
        dtype=np.int64,
    )
    record = build(
        input_id="continuum-seed-1",
        dataset_identifier="continuum-1",
        seed=1,
        finder_id="hebog",
        truth=truth,
        catalogue=catalogue,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=4.0,
        source_member_counts={"source-a": 2, "source-b": 1},
        hierarchy_diagnostics={"unique_convergence_count": 2},
    )

    payload = json.dumps(record, allow_nan=False, sort_keys=True)
    assert "array(" not in payload
    assert record["image_counts"] == {
        "candidate_association_mask_pixels": 4,
        "candidate_catalogue_sources": 2,
        "candidate_mask_pixels": 4,
        "intersection_mask_pixels": 4,
        "truth_mask_pixels": 5,
        "union_mask_pixels": 5,
    }
    shell = record["truth_groups"][1]
    assert shell["truth_group_id"] == "shell"
    assert shell["catalogue_candidate_count"] == 2
    assert shell["native_support_count"] == 2
    assert shell["association_mechanisms"] == [
        "catalogue-duplicate",
        "native-support-split",
        "native-support-merge",
    ]
    assert shell["integrated_flux_fractional_error"] == pytest.approx(0.1)
    assert record["record_sha256"] == canonical_sha256(
        {key: value for key, value in record.items() if key != "record_sha256"}
    )


def test_truth_linked_summary_accepts_exact_multi_support_sources() -> None:
    """Associated sources use source unions and retain native topology."""
    build = _source_union_program()["build_truth_linked_continuum_summary"]
    truth = (
        ContinuumTruthObject(
            identifier="shell",
            support_label=1,
            centre_xy=(2.5, 0.0),
            integrated_flux_jy=2.0,
            catalogue_role="astronomical-source",
            strata=("morphology-shell",),
        ),
    )
    catalogue = (
        AssociatedContinuumCatalogueObject(
            identifier="source-a",
            support_labels=(7, 9),
            centre_xy=(2.5, 0.0),
            integrated_flux_jy=2.0,
        ),
    )

    record = build(
        input_id="continuum-seed-1",
        dataset_identifier="continuum-1",
        seed=1,
        finder_id="hebog",
        truth=truth,
        catalogue=catalogue,
        truth_label_plane=np.asarray(((1, 1, 0, 1, 1, 1),)),
        candidate_label_plane=np.asarray(((0, 0, 0, 9, 9, 9),)),
        association_label_plane=np.asarray(((7, 7, 0, 9, 9, 9),)),
        beam_fwhm_pixels=2.0,
        source_member_counts={"source-a": 2},
        hierarchy_diagnostics={},
    )

    group = record["truth_groups"][0]
    assert group["primary_candidate_id"] == "source-a"
    assert group["primary_source_member_count"] == 2
    assert group["catalogue_candidate_count"] == 1
    assert group["native_support_count"] == 2
    assert group["association_mechanisms"] == ["native-support-split"]
    assert record["image_counts"] == {
        "candidate_association_mask_pixels": 5,
        "candidate_catalogue_sources": 1,
        "candidate_mask_pixels": 3,
        "intersection_mask_pixels": 3,
        "truth_mask_pixels": 5,
        "union_mask_pixels": 5,
    }


@pytest.mark.parametrize(
    ("catalogue", "counts", "message"),
    [
        (
            (
                AssociatedContinuumCatalogueObject(
                    "source-a", (7, 11), (1.0, 0.0), 1.0
                ),
            ),
            {"source-a": 2},
            "partition native supports",
        ),
        (
            (
                AssociatedContinuumCatalogueObject(
                    "source-a", (7,), (0.0, 0.0), 1.0
                ),
                AssociatedContinuumCatalogueObject(
                    "source-b", (7,), (1.0, 0.0), 1.0
                ),
            ),
            {"source-a": 1, "source-b": 1},
            "present and disjoint",
        ),
        (
            (
                AssociatedContinuumCatalogueObject(
                    "source-a", (7,), (0.0, 0.0), 1.0
                ),
                ContinuumCatalogueObject("source-b", 9, (1.0, 0.0), 1.0),
            ),
            {"source-a": 1, "source-b": 1},
            "mix support semantics",
        ),
        (
            (
                AssociatedContinuumCatalogueObject(
                    "source-a", (7, 9), (0.5, 0.0), 1.0
                ),
            ),
            {"source-a": 1},
            "counts do not match associated support unions",
        ),
    ],
)
def test_truth_linked_summary_rejects_invalid_source_support_partitions(
    catalogue: tuple[
        ContinuumCatalogueObject | AssociatedContinuumCatalogueObject, ...
    ],
    counts: dict[str, int],
    message: str,
) -> None:
    """Tail diagnostics fail closed on invalid source-support evidence."""
    build = _source_union_program()["build_truth_linked_continuum_summary"]

    with pytest.raises(ValueError, match=message):
        build(
            input_id="continuum-seed-1",
            dataset_identifier="continuum-1",
            seed=1,
            finder_id="hebog",
            truth=(
                ContinuumTruthObject(
                    "truth",
                    1,
                    (0.5, 0.0),
                    1.0,
                    "astronomical-source",
                    ("overall",),
                ),
            ),
            catalogue=catalogue,
            truth_label_plane=np.asarray(((1, 1),)),
            candidate_label_plane=np.asarray(((7, 9),)),
            association_label_plane=np.asarray(((7, 9),)),
            beam_fwhm_pixels=2.0,
            source_member_counts=counts,
            hierarchy_diagnostics={},
        )


def test_truth_linked_multi_support_summary_is_catalogue_order_invariant() -> (
    None
):
    """Associated-source diagnostics are deterministic across row order."""
    build = _source_union_program()["build_truth_linked_continuum_summary"]
    truth = (
        ContinuumTruthObject(
            "truth-a", 1, (0.5, 0.0), 1.0, "astronomical-source", ("overall",)
        ),
        ContinuumTruthObject(
            "truth-b", 2, (4.5, 0.0), 1.0, "astronomical-source", ("overall",)
        ),
    )
    sources = (
        AssociatedContinuumCatalogueObject(
            "source-a", (7, 8), (0.5, 0.0), 1.0
        ),
        AssociatedContinuumCatalogueObject(
            "source-b", (9, 10), (4.5, 0.0), 1.0
        ),
    )
    arguments = {
        "input_id": "continuum-seed-1",
        "dataset_identifier": "continuum-1",
        "seed": 1,
        "finder_id": "hebog",
        "truth": truth,
        "truth_label_plane": np.asarray(((1, 1, 0, 2, 2, 2),)),
        "candidate_label_plane": np.asarray(((7, 8, 0, 9, 10, 10),)),
        "association_label_plane": np.asarray(((7, 8, 0, 9, 10, 10),)),
        "beam_fwhm_pixels": 2.0,
        "source_member_counts": {"source-a": 2, "source-b": 2},
        "hierarchy_diagnostics": {},
    }

    forward = build(catalogue=sources, **arguments)
    reversed_rows = build(catalogue=tuple(reversed(sources)), **arguments)

    assert reversed_rows == forward


@dataclass(frozen=True)
class _Observation:
    image_key: str
    values: tuple[float, ...] = ()
    status: str = "success"
    reason: str | None = None


def test_endpoint_summary_retains_sufficient_statistics_without_arrays() -> (
    None
):
    """Every realization keeps hash-bound endpoint values and failures."""
    build = _program()["build_array_free_endpoint_summary"]

    record = build(
        input_id="continuum-seed-1",
        finder_id="current-hebog",
        observations={
            "continuum--completeness--overall": _Observation(
                "continuum-seed-1", (1.0, 0.0)
            ),
            "continuum--reliability--overall": _Observation(
                "continuum-seed-1",
                status="failed",
                reason="finder failed",
            ),
        },
    )

    assert record["array_planes_retained"] is False
    assert len(record["record_sha256"]) == 64
    assert record["endpoints"]["continuum--completeness--overall"] == {
        "status": "success",
        "reason": None,
        "values": [1.0, 0.0],
    }
    assert "array(" not in json.dumps(record, allow_nan=False)


def test_endpoint_summary_rejects_cross_realization_observation() -> None:
    """A summary cannot silently mix statistics from another image."""
    build = _program()["build_array_free_endpoint_summary"]

    with pytest.raises(ValueError, match="identity is malformed"):
        build(
            input_id="continuum-seed-1",
            finder_id="current-hebog",
            observations={
                "continuum--completeness--overall": _Observation(
                    "continuum-seed-2", (1.0,)
                )
            },
        )


def test_summary_separates_measurement_and_publication_masks() -> None:
    """Association topology and publication-mask metrics cannot alias."""
    build = _program()["build_truth_linked_continuum_summary"]
    truth = (
        ContinuumTruthObject(
            identifier="source",
            support_label=1,
            centre_xy=(0.5, 0.0),
            integrated_flux_jy=1.0,
            catalogue_role="astronomical-source",
            strata=("overall",),
        ),
    )
    catalogue = (ContinuumCatalogueObject("candidate", 7, (0.5, 0.0), 1.0),)

    record = build(
        input_id="continuum-seed-1",
        dataset_identifier="continuum-1",
        seed=1,
        finder_id="hebog",
        truth=truth,
        catalogue=catalogue,
        truth_label_plane=np.array([[1, 1], [0, 0]]),
        candidate_label_plane=np.array([[0, 7], [0, 0]]),
        association_label_plane=np.array([[7, 7], [0, 0]]),
        beam_fwhm_pixels=4.0,
        source_member_counts={"candidate": 1},
        hierarchy_diagnostics={},
    )

    assert record["image_counts"] == {
        "candidate_association_mask_pixels": 2,
        "candidate_catalogue_sources": 1,
        "candidate_mask_pixels": 1,
        "intersection_mask_pixels": 1,
        "truth_mask_pixels": 2,
        "union_mask_pixels": 2,
    }
    assert record["truth_groups"][0]["native_support_count"] == 1


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"source_member_counts": {"missing": 1}}, "source membership"),
        ({"hierarchy_diagnostics": {"bad": -1}}, "hierarchy diagnostic"),
        ({"beam_fwhm_pixels": float("nan")}, "beam FWHM"),
    ],
)
def test_truth_linked_summary_rejects_unverifiable_inputs(
    change: dict[str, object], message: str
) -> None:
    """Diagnostic retention must never guess malformed provenance."""
    build = _program()["build_truth_linked_continuum_summary"]
    arguments: dict[str, object] = {
        "input_id": "continuum-seed-1",
        "dataset_identifier": "continuum-1",
        "seed": 1,
        "finder_id": "hebog",
        "truth": (
            ContinuumTruthObject(
                identifier="source",
                support_label=1,
                centre_xy=(1.0, 1.0),
                integrated_flux_jy=2.0,
                catalogue_role="astronomical-source",
                strata=("overall",),
            ),
        ),
        "catalogue": (
            ContinuumCatalogueObject("candidate", 7, (1.0, 1.0), 2.0),
        ),
        "truth_label_plane": np.array([[1, 1], [0, 0]]),
        "candidate_label_plane": np.array([[7, 7], [0, 0]]),
        "beam_fwhm_pixels": 4.0,
        "source_member_counts": {"candidate": 1},
        "hierarchy_diagnostics": {"unique_convergence_count": 1},
    }
    arguments.update(change)

    with pytest.raises(ValueError, match=message):
        build(**arguments)


def test_tail_sentinels_are_result_neutral_and_reproducible() -> None:
    """Sentinel membership depends only on frozen input and truth identity."""
    select = _program()["select_result_neutral_tail_sentinels"]
    request = json.loads(_REQUEST.read_text(encoding="utf-8"))
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))

    sentinels = select(
        request=request,
        continuum_manifest=manifest,
        count_per_dataset_and_sentinel=8,
    )

    assert sentinels["selection_method"] == (
        "sha256-sentinel-id-colon-input-id-then-input-id"
    )
    assert sentinels["candidate_results_inspected"] is False
    assert sentinels["membership_count"] == 160
    assert sentinels["sentinel_ids"] == [
        "morphology-artifact",
        "morphology-shell",
        "scale-4-beam",
        "tile-corner",
        "varying-noise",
    ]
    assert sentinels["membership_sha256"] == canonical_sha256(
        sentinels["memberships"]
    )
    assert (
        select(
            request=request,
            continuum_manifest=manifest,
            count_per_dataset_and_sentinel=8,
        )
        == sentinels
    )


def test_frozen_tail_sentinels_reproduce_without_results() -> None:
    """The compact freeze binds the complete deterministic membership."""
    select = _program()["select_result_neutral_tail_sentinels"]
    frozen_path = (
        _ROOT / "config/contracts/phase-5-prospective-paired-tail-"
        "sentinels.json"
    )
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    reproduced = select(
        request=json.loads(_REQUEST.read_text(encoding="utf-8")),
        continuum_manifest=json.loads(_MANIFEST.read_text(encoding="utf-8")),
        count_per_dataset_and_sentinel=frozen[
            "count_per_dataset_and_sentinel"
        ],
    )

    for key in (
        "candidate_results_inspected",
        "count_per_dataset_and_sentinel",
        "evidence_role",
        "membership_count",
        "membership_sha256",
        "record_id",
        "schema_version",
        "selection_method",
        "sentinel_ids",
        "unique_input_count",
    ):
        assert frozen[key] == reproduced[key]


def test_aligned_power_audit_covers_every_frozen_comparison() -> None:
    """Legacy smoke status cannot replace its zero-failure prerequisites."""
    build = _program()["build_aligned_prospective_power_audit"]
    registry_path = (
        _ROOT / "config/contracts/phase-5-prospective-science-endpoint-"
        "registry.json"
    )
    protocol_path = _ROOT / "config/contracts/phase-5-external-comparison.json"
    smoke = json.loads(_SMOKE.read_text(encoding="utf-8"))

    audit = build(
        registry=load_prospective_endpoint_registry(registry_path),
        external_protocol=json.loads(
            protocol_path.read_text(encoding="utf-8")
        ),
        smoke_record=smoke,
    )

    assert smoke["status"] == audit["immutable_smoke_status"] == "fail"
    assert audit["status"] == "pass"
    assert audit["comparison_count"] == 1187
    assert audit["adequately_powered_comparison_count"] == 1187
    assert audit["combined_familywise_power_lower_bound"] >= 0.9
    assert audit["comparison_design_sha256"] == (
        "1110b922bdedfb9fa9f05664590f15e3ed484fa22a3416e31d07c56636e6b4f8"
    )
    frozen = json.loads(
        (
            _ROOT / "config/contracts/phase-5-prospective-paired-power-"
            "audit.json"
        ).read_text(encoding="utf-8")
    )
    for key, value in audit.items():
        assert frozen[key] == value


def test_aligned_power_audit_rejects_confirmed_smoke_failure() -> None:
    """The adapter cannot bypass a genuine failed prerequisite."""
    build = _program()["build_aligned_prospective_power_audit"]
    smoke = json.loads(_SMOKE.read_text(encoding="utf-8"))
    smoke["terminal_failure_count"] = 1

    with pytest.raises(ValueError, match="prerequisites"):
        build(
            registry=load_prospective_endpoint_registry(
                _ROOT / "config/contracts/phase-5-prospective-science-"
                "endpoint-registry.json"
            ),
            external_protocol=json.loads(
                (
                    _ROOT / "config/contracts/phase-5-external-comparison.json"
                ).read_text(encoding="utf-8")
            ),
            smoke_record=smoke,
        )


def test_implementation_decision_binds_exact_approved_review() -> None:
    """The approved task remains evaluation-only and non-executable."""
    decision_path = (
        _ROOT / "config/contracts/phase-5-prospective-paired-evidence-"
        "implementation-decision.json"
    )
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    review = (
        _ROOT / "config/contracts/phase-5-publication-scale-persistence-"
        "root-cause-pre-review.json"
    )

    assert decision["approved_review_sha256"] == file_sha256(review)
    assert decision["approved_review_sha256"] == (
        "77bd4b82cc7526b5e6f1b276ea16c887428c92f1c18126071405de69a07dce82"
    )
    assert decision["authorization"]["implementation_authorized"] is True
    assert {
        value
        for key, value in decision["authorization"].items()
        if key != "implementation_authorized"
    } == {False}
