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


def _source(
    *,
    pixel_yx: tuple[float, float],
    flux_jy: float,
    dataset: Any,
) -> SimpleNamespace:
    """Return one minimal source row at an exact synthetic pixel position."""
    celestial = WCS(synthetic_fits_header(dataset), relax=True).celestial
    world = celestial.all_pix2world([[pixel_yx[1], pixel_yx[0]]], 0)[0]
    return SimpleNamespace(
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


def test_science_summary_excludes_remote_rows_from_truth_flux_and_split() -> (
    None
):
    """False detections remain visible without becoming source fragments."""
    runner, task, truth, true_rms = _science_inputs()
    true_flux = runner["_parent_true_integrated_flux_jy"](task.dataset)
    truth_y, truth_x = np.nonzero(truth)
    linked_position = (float(np.mean(truth_y)), float(np.mean(truth_x)))
    remote_position = (8.0, 8.0)
    catalogue = SimpleNamespace(
        sources=(
            _source(
                pixel_yx=linked_position,
                flux_jy=true_flux,
                dataset=task.dataset,
            ),
            _source(
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


def test_science_summary_detects_two_truth_linked_fragments() -> None:
    """Two rows at the analytic source remain a binding split outcome."""
    runner, task, truth, true_rms = _science_inputs()
    true_flux = runner["_parent_true_integrated_flux_jy"](task.dataset)
    truth_y, truth_x = np.nonzero(truth)
    centre = (float(np.mean(truth_y)), float(np.mean(truth_x)))
    catalogue = SimpleNamespace(
        sources=(
            _source(
                pixel_yx=centre,
                flux_jy=true_flux / 2.0,
                dataset=task.dataset,
            ),
            _source(
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


def test_freezer_writes_complete_set_once(tmp_path: Path) -> None:
    """A collision blocks the whole four-record set before any rewrite."""
    freezer = runpy.run_path(str(_FREEZER))
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
