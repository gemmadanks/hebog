"""Prospective contracts for the source-owned footprint-guard lane."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from astropy.wcs import WCS

from hebog.validation import adaptive_background_lane
from hebog.validation.adaptive_background_lane import source_signal_and_truth
from hebog.validation.materialization import synthetic_fits_header

_ROOT = Path(__file__).parents[3]
_RUNNER = (
    _ROOT
    / "scripts/validation/run_phase5_source_owned_measurement_topology.py"
)
_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_source_owned_measurement_topology_footprint_guard.py"
)
_SUCCESSOR_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_source_owned_measurement_topology_source_support_"
    "linkage.py"
)
_PROCESS_REPAIR_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_source_owned_source_support_linkage_process_repair.py"
)
_ROOT_CAUSE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-source-owned-footprint-guard-lane-root-cause-review.json"
)
_PROCESS_REPAIR_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-source-owned-source-support-linkage-process-repair-"
    "pre-review.json"
)


def _source(
    *,
    identifier: str,
    pixel_yx: tuple[float, float],
    flux_jy: float,
    dataset: Any,
) -> SimpleNamespace:
    """Return one minimal source row at an exact synthetic pixel position."""
    celestial = WCS(synthetic_fits_header(dataset), relax=True).celestial
    world = celestial.all_pix2world([[pixel_yx[1], pixel_yx[0]]], 0)[0]
    return SimpleNamespace(
        source_id=identifier,
        position=SimpleNamespace(
            right_ascension_degrees=float(world[0]),
            declination_degrees=float(world[1]),
        ),
        association_aperture_integrated_flux_jy=flux_jy,
        flux=SimpleNamespace(integrated_flux_jy=flux_jy),
    )


def _science_inputs() -> tuple[Any, Any, np.ndarray, np.ndarray]:
    """Return one exact lane task and its analytic truth products."""
    runner = runpy.run_path(str(_RUNNER))
    task = runner["_parent_tasks"](
        runner["DatasetManifest"].model_validate_json(
            (
                _ROOT / "config/contracts/"
                "phase-5-adaptive-background-development-manifest.json"
            ).read_bytes()
        )
    )[0]
    _, truth, true_rms = source_signal_and_truth(task.recipe)
    return runner, task, truth, true_rms


def test_science_summary_excludes_remote_rows_from_truth_flux_and_split(
    monkeypatch: Any,
) -> None:
    """False detections remain visible without becoming source fragments."""
    runner, task, truth, true_rms = _science_inputs()
    true_flux = runner["_parent_true_integrated_flux_jy"](task.dataset)
    truth_y, truth_x = np.nonzero(truth)
    linked_position = (float(np.mean(truth_y)), float(np.mean(truth_x)))
    remote_position = (8.0, 8.0)
    labels = np.zeros(truth.shape, dtype=np.int32)
    labels[truth] = 1
    labels[8, 8] = 2
    monkeypatch.setitem(
        runner["_science_summary"].__globals__,
        "_active_science_captures",
        [
            {
                "catalogue_linkage_inputs": (
                    labels,
                    {1: "source-linked", 2: "source-remote"},
                )
            }
        ],
    )
    catalogue = SimpleNamespace(
        sources=(
            _source(
                identifier="source-linked",
                pixel_yx=linked_position,
                flux_jy=true_flux,
                dataset=task.dataset,
            ),
            _source(
                identifier="source-remote",
                pixel_yx=remote_position,
                flux_jy=true_flux / 10.0,
                dataset=task.dataset,
            ),
        )
    )

    summary = runner["_science_summary"](
        dataset=task.dataset,
        recipe=task.recipe,
        catalogue=catalogue,
        mask=truth,
        background=np.full(truth.shape, task.recipe.background),
        rms=true_rms,
    )

    assert summary.completeness == 1.0
    assert summary.integrated_flux_absolute_fractional_error == pytest.approx(
        0.0
    )
    assert summary.split is False
    assert summary.source_count == 2
    assert runner["_latest_linkage"] == {
        "catalogue_source_count": 2,
        "truth_linked_source_count": 1,
        "unmatched_source_count": 1,
        "truth_linked_integrated_flux_jy": pytest.approx(true_flux),
        "unmatched_integrated_flux_jy": pytest.approx(true_flux / 10.0),
    }


def test_science_summary_detects_two_truth_linked_fragments(
    monkeypatch: Any,
) -> None:
    """Two rows at the analytic source remain a binding split outcome."""
    runner, task, truth, true_rms = _science_inputs()
    true_flux = runner["_parent_true_integrated_flux_jy"](task.dataset)
    truth_y, truth_x = np.nonzero(truth)
    centre = (float(np.mean(truth_y)), float(np.mean(truth_x)))
    truth_pixels = np.argwhere(truth)
    labels = np.zeros(truth.shape, dtype=np.int32)
    labels[tuple(truth_pixels[0])] = 1
    labels[tuple(truth_pixels[-1])] = 2
    monkeypatch.setitem(
        runner["_science_summary"].__globals__,
        "_active_science_captures",
        [
            {
                "catalogue_linkage_inputs": (
                    labels,
                    {1: "source-a", 2: "source-b"},
                )
            }
        ],
    )
    catalogue = SimpleNamespace(
        sources=(
            _source(
                identifier="source-a",
                pixel_yx=centre,
                flux_jy=true_flux / 2.0,
                dataset=task.dataset,
            ),
            _source(
                identifier="source-b",
                pixel_yx=(centre[0] + 1.0, centre[1] + 1.0),
                flux_jy=true_flux / 2.0,
                dataset=task.dataset,
            ),
        )
    )

    summary = runner["_science_summary"](
        dataset=task.dataset,
        recipe=task.recipe,
        catalogue=catalogue,
        mask=truth,
        background=np.full(truth.shape, task.recipe.background),
        rms=true_rms,
    )

    assert summary.split is True
    assert runner["_latest_linkage"]["truth_linked_source_count"] == 2


def test_science_summary_uses_owned_support_not_expanded_truth_box(
    monkeypatch: Any,
) -> None:
    """A nearby row with no truth-overlapping pixels remains unmatched."""
    runner, task, truth, true_rms = _science_inputs()
    globals_ = runner["_science_summary"].__globals__
    true_flux = runner["_parent_true_integrated_flux_jy"](task.dataset)
    truth_pixels = np.argwhere(truth)
    linked_yx = (
        float(truth_pixels[0, 0]),
        float(truth_pixels[0, 1]),
    )
    minimum_yx = truth_pixels.min(axis=0)
    maximum_yx = truth_pixels.max(axis=0)
    inside_box = np.zeros(truth.shape, dtype=np.bool_)
    inside_box[
        minimum_yx[0] : maximum_yx[0] + 1,
        minimum_yx[1] : maximum_yx[1] + 1,
    ] = True
    unlinked_pixel = np.argwhere(inside_box & ~truth)[0]
    unlinked_yx = (float(unlinked_pixel[0]), float(unlinked_pixel[1]))
    labels = np.zeros(truth.shape, dtype=np.int32)
    labels[tuple(truth_pixels[0])] = 1
    labels[tuple(unlinked_pixel)] = 2
    monkeypatch.setitem(
        globals_,
        "_active_science_captures",
        [
            {
                "catalogue_linkage_inputs": (
                    labels,
                    {1: "source-linked", 2: "source-nearby"},
                )
            }
        ],
    )
    catalogue = SimpleNamespace(
        sources=(
            _source(
                identifier="source-linked",
                pixel_yx=linked_yx,
                flux_jy=true_flux,
                dataset=task.dataset,
            ),
            _source(
                identifier="source-nearby",
                pixel_yx=unlinked_yx,
                flux_jy=true_flux / 10.0,
                dataset=task.dataset,
            ),
        )
    )

    summary = runner["_science_summary"](
        dataset=task.dataset,
        recipe=task.recipe,
        catalogue=catalogue,
        mask=truth,
        background=np.full(truth.shape, task.recipe.background),
        rms=true_rms,
    )

    assert summary.split is False
    assert runner["_latest_linkage"]["truth_linked_source_count"] == 1
    assert runner["_latest_linkage"]["unmatched_source_count"] == 1


def test_support_topology_rejects_subthreshold_rows_inside_truth_box() -> None:
    """A nearby noise island is unmatched when its own support misses truth."""
    truth = np.zeros((7, 7), dtype=np.bool_)
    truth[2:5, 2:5] = True
    source_labels = np.zeros((7, 7), dtype=np.int32)
    source_labels[3, 3] = 1
    source_labels[1, 3] = 2

    topology = adaptive_background_lane.truth_linked_source_support_topology(
        ("source-a", "source-b"),
        source_labels,
        {1: "source-a", 2: "source-b"},
        truth,
    )

    assert topology.truth_linked_source_indices == (0,)
    assert topology.unmatched_source_indices == (1,)
    assert topology.truth_linked_split is False


def test_support_topology_detects_distinct_rows_overlapping_one_truth() -> (
    None
):
    """Two source-owned supports intersecting one truth remain a split."""
    truth = np.zeros((7, 7), dtype=np.bool_)
    truth[2:5, 2:5] = True
    source_labels = np.zeros((7, 7), dtype=np.int32)
    source_labels[2, 2] = 1
    source_labels[4, 4] = 2

    topology = adaptive_background_lane.truth_linked_source_support_topology(
        ("source-a", "source-b"),
        source_labels,
        {1: "source-a", 2: "source-b"},
        truth,
    )

    assert topology.truth_linked_source_indices == (0, 1)
    assert topology.unmatched_source_indices == ()
    assert topology.truth_linked_split is True


@pytest.mark.parametrize(
    ("source_identifiers", "source_labels", "mapping", "truth", "message"),
    (
        (
            ("source-a",),
            np.zeros((2, 2), dtype=np.int32),
            {},
            np.zeros((2, 2), dtype=np.bool_),
            "truth support must not be empty",
        ),
        (
            ("source-a",),
            np.ones((2, 2), dtype=np.int32),
            {1: "source-a"},
            np.ones((2, 2), dtype=np.int32),
            "two-dimensional boolean plane",
        ),
        (
            ("source-a",),
            np.ones((3, 2), dtype=np.int32),
            {1: "source-a"},
            np.ones((2, 2), dtype=np.bool_),
            "aligned non-negative integer plane",
        ),
        (
            ("source-a",),
            np.full((2, 2), -1, dtype=np.int32),
            {1: "source-a"},
            np.ones((2, 2), dtype=np.bool_),
            "aligned non-negative integer plane",
        ),
        (
            ("source-a", "source-a"),
            np.ones((2, 2), dtype=np.int32),
            {1: "source-a"},
            np.ones((2, 2), dtype=np.bool_),
            "source identifiers must be unique",
        ),
        (
            ("source-a",),
            np.ones((2, 2), dtype=np.int32),
            {2: "source-a"},
            np.ones((2, 2), dtype=np.bool_),
            "source label identity mapping is inconsistent",
        ),
    ),
)
def test_support_topology_fails_closed_on_inconsistent_inputs(
    source_identifiers: tuple[str, ...],
    source_labels: np.ndarray,
    mapping: dict[int, str],
    truth: np.ndarray,
    message: str,
) -> None:
    """Malformed linkage evidence cannot silently change split semantics."""
    with pytest.raises(ValueError, match=message):
        adaptive_background_lane.truth_linked_source_support_topology(
            source_identifiers,
            source_labels,
            mapping,
            truth,
        )


def test_root_cause_review_accounts_for_the_only_failed_geometry() -> None:
    """The successor is justified by exact owned-support evidence."""
    review = json.loads(_ROOT_CAUSE_REVIEW.read_text(encoding="utf-8"))

    assert review["binding_context"]["terminal_decision"] == {
        "executor_invariance_passed": True,
        "failed_geometry_count": 1,
        "file_sha256": (
            "8add4b13568258219b3b52b5ae017a106d22143314995a547e6b8cd059a6b2ea"
        ),
        "geometry_count": 12,
        "input_count": 144,
        "path": (
            "benchmark-results/phase-5/"
            "source-owned-measurement-topology-footprint-guard-"
            "development-decision.json"
        ),
        "status": "fail",
        "trigger_seam_passed": True,
    }
    finding = review["causal_finding"]
    assert finding["owned_support_forensics"] == {
        "candidate_source_component_labels": [4, 72, 77, 86, 96],
        "source_component_truth_overlap_pixels": {
            "4": 0,
            "72": 440,
            "77": 0,
            "86": 0,
            "96": 0,
        },
        "truth_overlapping_candidate_source_count": 1,
        "zero_overlap_candidate_source_count": 4,
    }
    assert finding["classification"].endswith("not-source-finding-regression")
    assert review["recommended_repair"]["scope"] == (
        "validation-evaluator-only"
    )
    assert not any(review["authorization"].values())


def test_process_repair_review_accounts_for_public_schema_failure() -> None:
    """The retry is bound to the exact post-candidate process defect."""
    review = json.loads(_PROCESS_REPAIR_REVIEW.read_text(encoding="utf-8"))

    assert review["status"] == (
        "root-cause-complete-ready-for-process-only-repair"
    )
    assert review["failed_execution"] == {
        "candidate_bundle_count": 144,
        "candidate_execution_count": 144,
        "coarse_control_execution_count": 0,
        "execution_commit": "218a7f9ae8843511a07e4110af529d79ae21053f",
        "execution_decision_sha256": (
            "17a6c01c2d370055639e73f9cda6d91c4261747e36823f7db527cd4e7aacd716"
        ),
        "identity_review_sha256": (
            "cf59dd822a57820ca61161b1946ac2241d36a6b2a9fa0bc00b74dd87bb65f984"
        ),
        "namespace_file_count": 721,
        "namespace_file_set_sha256": (
            "cfea0bfcce25d80c48e248357cb215b78eb33b795d21af51b6821677e8b7ab8d"
        ),
        "namespace_size_bytes": 498192816,
        "output_published": False,
        "progress_record_count": 0,
        "scratch": (
            "/private/tmp/hebog-phase5-source-owned-measurement-topology-"
            "source-support-linkage-2e25cdf"
        ),
    }
    assert review["finding"]["classification"] == (
        "post-candidate-validation-schema-defect"
    )
    assert review["recommended_repair"]["candidate_identity_unchanged"]
    assert not any(review["authorization"].values())


def test_attribution_retains_candidate_and_control_linkage_scalars(
    monkeypatch: Any,
) -> None:
    """Unmatched reliability evidence survives without catalogue arrays."""
    runner = runpy.run_path(str(_RUNNER))
    globals_ = runner["_attribution_record"].__globals__
    truth = np.ones((2, 2), dtype=np.bool_)
    globals_["_captured_candidate"].update(
        {
            "detection": SimpleNamespace(
                background_rms_grids=SimpleNamespace(
                    adaptive_protected_pixel_count=4,
                    adaptive_protected_window_count=1,
                )
            ),
            "detection_support": truth,
            "measurement_support": truth,
            "publication_support": truth,
            "source_stage": {},
            "catalogue_linkage": {
                "catalogue_source_count": 2,
                "truth_linked_source_count": 1,
                "unmatched_source_count": 1,
                "truth_linked_integrated_flux_jy": 2.0,
                "unmatched_integrated_flux_jy": 0.2,
            },
        }
    )
    globals_["_captured_coarse"].update(
        {
            "detection_support": truth,
            "catalogue_linkage": {
                "catalogue_source_count": 1,
                "truth_linked_source_count": 1,
                "unmatched_source_count": 0,
                "truth_linked_integrated_flux_jy": 2.0,
                "unmatched_integrated_flux_jy": 0.0,
            },
        }
    )

    def empty_record() -> dict[str, int]:
        return {}

    def no_attribution(*_args: object) -> SimpleNamespace:
        return SimpleNamespace(to_record=empty_record)

    monkeypatch.setitem(
        globals_,
        "attribute_truth_support",
        no_attribution,
    )

    record = runner["_attribution_record"](truth)

    assert record["candidate_unmatched_source_count"] == 1
    assert record["candidate_unmatched_integrated_flux_jy"] == 0.2
    assert record["coarse_unmatched_source_count"] == 0
    assert all(not isinstance(value, np.ndarray) for value in record.values())


def test_successor_runner_uses_the_prospective_risk_evaluator() -> None:
    """Aspirational floors cannot block a comparator-safe development lane."""
    runner = runpy.run_path(str(_RUNNER))

    assert runner["_lane_evaluate"].__name__ == (
        "evaluate_phase_five_adaptive_risk"
    )


def test_freezer_builds_coherent_separate_identity_and_authority() -> None:
    """The scientific identity stays non-executable despite user authority."""
    freezer = runpy.run_path(str(_FREEZER))
    programs, fixtures, expected = freezer["_runner_records"](_ROOT)
    public = freezer["build_public_identity"](_ROOT)
    implementation = freezer["build_implementation"](
        _ROOT, public, programs, fixtures
    )
    identity = freezer["build_identity"](
        _ROOT, public, implementation, expected
    )
    decision = freezer["build_execution_decision"](_ROOT, identity, expected)

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert (
        identity["expected_execution_sha256"]
        == decision["expected_execution_sha256"]
    )
    assert decision["identity_review_sha256"] == freezer["_document_sha256"](
        identity
    )
    assert (
        decision["authorization"]
        == runpy.run_path(str(_RUNNER))["_EXPECTED_EXECUTION_AUTHORIZATION"]
    )


def test_historical_freezer_rejects_changed_scientific_source_tree(
    tmp_path: Path,
) -> None:
    """The consumed footprint lane cannot be rebound after this repair."""
    freezer = runpy.run_path(str(_FREEZER))
    arguments = argparse.Namespace(
        repository_root=_ROOT,
        output_root=tmp_path,
    )

    with pytest.raises(
        ValueError,
        match="footprint-guard scientific source tree changed",
    ):
        freezer["freeze_records"](arguments)
    assert not tuple(tmp_path.rglob("*.json"))


def test_successor_freezer_separates_identity_from_one_use_authority() -> None:
    """The repaired evaluator remains non-executable without its decision."""
    freezer = runpy.run_path(str(_SUCCESSOR_FREEZER))
    programs, fixtures, expected = freezer["_runner_records"](_ROOT)
    public = freezer["build_public_identity"](_ROOT)
    implementation = freezer["build_implementation"](
        _ROOT, public, programs, fixtures
    )
    identity = freezer["build_identity"](
        _ROOT, public, implementation, expected
    )
    decision = freezer["build_execution_decision"](_ROOT, identity, expected)

    assert public["source_support_linkage_repair"] == {
        "linkage": "exact-source-owned-support-intersects-analytic-truth",
        "root_cause_review": {
            "path": str(freezer["_ROOT_REVIEW"]),
            "sha256": freezer["_ROOT_REVIEW_SHA256"],
        },
        "source_finding_science_changed": False,
        "unmatched_reliability_retained": True,
    }
    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["predecessor_identity"]["sha256"] == (
        "d74d0fba79c689f6d3b1e857fd900c14d8c4138a22cbf31fe9ac29e9594486b8"
    )
    assert decision["identity_review_sha256"] == freezer["_document_sha256"](
        identity
    )
    assert set(decision["authorization"].values()) == {False, True}
    assert decision["output"] == expected["output"]


def test_process_repair_freezer_preserves_science_and_authority() -> None:
    """The retry changes only wrapper identity and scratch provenance."""
    freezer = runpy.run_path(str(_PROCESS_REPAIR_FREEZER))
    identity = freezer["build_identity"](_ROOT)
    decision = freezer["build_execution_decision"](_ROOT, identity)

    assert identity["candidate"] == {
        "configuration_sha256": (
            "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
        ),
        "entrypoint": "hebog.find_sources",
        "revision": "2e25cdf8bb0fbd739bba330ff20d9f798f95bf44",
        "source_tree_sha256": (
            "3da083b0a720fe0104fa51e135f224a2456b49bd49d85cd6a449fccb93805e8a"
        ),
    }
    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["expected_execution"]["scratch"].endswith(
        "source-support-linkage-process-repair-2e25cdf"
    )
    assert decision["status"] == "authorized-for-one-development-lane"
    assert set(decision["authorization"].values()) == {False, True}
    assert decision["identity_review_sha256"] == freezer["_document_sha256"](
        identity
    )
    assert (
        decision["expected_execution_sha256"]
        == identity["expected_execution_sha256"]
    )


def test_successor_freezer_writes_complete_set_once(tmp_path: Path) -> None:
    """A collision blocks the fresh four-record set before any rewrite."""
    freezer = runpy.run_path(str(_SUCCESSOR_FREEZER))
    arguments = argparse.Namespace(
        repository_root=_ROOT,
        output_root=tmp_path,
    )

    freezer["freeze_records"](arguments)
    relative_paths = (
        freezer["_PUBLIC_IDENTITY"],
        freezer["_IMPLEMENTATION"],
        freezer["_IDENTITY"],
        freezer["_EXECUTION_DECISION"],
    )
    before = {path: (tmp_path / path).read_bytes() for path in relative_paths}

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_records"](arguments)

    assert before == {
        path: (tmp_path / path).read_bytes() for path in relative_paths
    }
    assert all(
        isinstance(json.loads(payload), dict) for payload in before.values()
    )
