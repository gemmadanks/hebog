"""Behavioral contracts for the source-owned measurement/topology runner."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import json
import pickle
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from astropy.io import fits
from manifest_comparison import assert_regenerated_manifest_matches_snapshot

from hebog import public_science
from hebog.validation.adaptive_background_lane import (
    AdaptiveScienceSummary,
    build_adaptive_development_manifest,
)

_ROOT = Path(__file__).parents[3]
_RUNNER = (
    _ROOT
    / "scripts/validation/run_phase5_source_owned_measurement_topology.py"
)
_MANIFEST = (
    _ROOT
    / "config/contracts/phase-5-adaptive-background-development-manifest.json"
)


def test_source_stage_attribution_is_array_free_and_exact() -> None:
    """Measurement ownership and hierarchy state reduce to bounded scalars."""
    runner = runpy.run_path(str(_RUNNER))
    record = runner["_source_stage_attribution"](
        source_seed_labels=np.asarray([[1, 0, 0, 2]], dtype=np.int32),
        persistent_support=np.asarray([[True, True, True, True]]),
        source_owned_labels=np.asarray([[1, 1, 2, 2]], dtype=np.int32),
        source_measurement_labels=np.asarray([[1, 1, 2, 2]], dtype=np.int32),
        publication_support=np.asarray([[True, False, False, True]]),
        hierarchy_diagnostics=None,
    )

    assert record["source_owned_persistent_pixel_count"] == 4
    assert record["source_measurement_pixel_count"] == 4
    assert record["measurement_publication_overlap_count"] == 2
    assert all(not isinstance(value, np.ndarray) for value in record.values())


def test_capture_uses_expanded_source_measurement_support(
    monkeypatch: Any,
) -> None:
    """Truth attribution observes the actual source aperture, not its seed."""
    runner = runpy.run_path(str(_RUNNER))
    globals_ = runner["_captured_science"].__wrapped__.__globals__
    seeds = np.asarray([[1, 0, 2]], dtype=np.int32)
    persistent = np.asarray([[True, True, True]])
    owned = np.asarray([[1, 1, 2]], dtype=np.int32)
    expanded = np.asarray([[1, 1, 2]], dtype=np.int32)
    result = SimpleNamespace(
        association=SimpleNamespace(hierarchy_diagnostics=None)
    )

    def fake_catalogues(*_args: Any, **_kwargs: Any) -> Any:
        return result

    def fake_source_labels(*_args: Any) -> tuple[np.ndarray, dict[int, Any]]:
        return seeds, {}

    def fake_persistent(_planes: Any) -> np.ndarray:
        return persistent

    def fake_owned(*_args: Any) -> np.ndarray:
        return owned

    def fake_expanded(*_args: Any, **_kwargs: Any) -> np.ndarray:
        return expanded

    monkeypatch.setattr(
        public_science,
        "build_hebog_reconstructed_source_catalogues",
        fake_catalogues,
    )
    monkeypatch.setattr(
        globals_["validation_products"],
        "_source_label_plane",
        fake_source_labels,
    )
    monkeypatch.setitem(
        globals_,
        "persistent_adjacent_scale_support",
        fake_persistent,
    )
    monkeypatch.setitem(
        globals_,
        "assign_persistent_source_support",
        fake_owned,
    )
    monkeypatch.setitem(
        globals_,
        "expand_source_measurement_labels",
        fake_expanded,
    )

    with runner["_captured_science"]() as captured:
        public_science.build_hebog_reconstructed_source_catalogues(
            np.ones(seeds.shape),
            np.zeros(seeds.shape),
            np.ones(seeds.shape, dtype=np.bool_),
            seeds,
            seeds,
            persistent,
            (),
            fits.Header(),
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=2.0,
            measurement_aperture_radius_beams=1.5,
        )

    assert np.array_equal(captured["measurement_support"], expanded > 0)


def test_serial_wrapper_writes_only_array_free_attribution(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Transient stage arrays become one bounded per-input sidecar."""
    runner = runpy.run_path(str(_RUNNER))
    globals_ = runner["_run_serial_task"].__globals__
    truth = np.ones((2, 3), dtype=np.bool_)
    task = SimpleNamespace(input_id="fixture-input", recipe=object())
    source_stage = {
        "source_measurement_pixel_count": 6,
        "hierarchy_catalogue_source_count": 1,
    }

    def parent(_task: object, scratch: Path) -> dict[str, object]:
        (scratch / "fixture-input").mkdir()
        globals_["_captured_candidate"].update(
            {
                "detection": SimpleNamespace(
                    background_rms_grids=SimpleNamespace(
                        adaptive_protected_pixel_count=6,
                        adaptive_protected_window_count=1,
                    )
                ),
                "detection_support": truth,
                "measurement_support": truth,
                "publication_support": truth,
                "source_stage": source_stage,
                "catalogue_linkage": {
                    "catalogue_source_count": 1,
                    "truth_linked_source_count": 1,
                    "unmatched_source_count": 0,
                    "truth_linked_integrated_flux_jy": 1.0,
                    "unmatched_integrated_flux_jy": 0.0,
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
                    "truth_linked_integrated_flux_jy": 1.0,
                    "unmatched_integrated_flux_jy": 0.0,
                },
            }
        )
        return {"input_id": "fixture-input"}

    def synthetic_truth(_recipe: object) -> tuple[None, np.ndarray, None]:
        return None, truth, None

    monkeypatch.setitem(globals_, "_parent_run_serial_task", parent)
    monkeypatch.setitem(globals_, "source_signal_and_truth", synthetic_truth)

    result = runner["_run_serial_task"](task, tmp_path)
    sidecar = json.loads(
        (tmp_path / "fixture-input/attribution.json").read_text()
    )

    assert result["attribution"] == sidecar
    assert sidecar["schema_version"] == 3
    assert sidecar["source_measurement_pixel_count"] == 6
    assert sidecar["protected_pixel_count"] == 6
    assert all(not isinstance(value, np.ndarray) for value in sidecar.values())


def test_process_pool_payload_is_pickle_safe_and_exact() -> None:
    """Parent run-path task classes never cross the process boundary."""
    runner = runpy.run_path(str(_RUNNER))
    manifest = build_adaptive_development_manifest()
    assert_regenerated_manifest_matches_snapshot(
        manifest.model_dump(mode="json"), json.loads(_MANIFEST.read_bytes())
    )
    task = runner["_parent_tasks"](manifest)[0]

    payload = runner["_serial_task_payload"](task)
    restored = pickle.loads(pickle.dumps(payload))
    rebuilt = runner["_task_from_payload"](restored)

    assert rebuilt.input_id == task.input_id
    assert rebuilt.cell == task.cell
    assert rebuilt.dataset == task.dataset
    assert rebuilt.recipe == task.recipe
    assert (
        runner["_verify_process_payload"](payload, spawn_process=False)
        == "pickle-pass"
    )
    assert "<run_path>" not in repr(restored)


def test_process_pool_payload_fails_closed_when_malformed() -> None:
    """A malformed process payload is rejected before science execution."""
    runner = runpy.run_path(str(_RUNNER))

    with pytest.raises(ValueError, match="payload is malformed"):
        runner["_task_from_payload"]({"input_id": "fixture-input"})
    with pytest.raises(ValueError, match="cell is malformed"):
        runner["_task_from_payload"](
            {
                "cell": "not-a-cell",
                "dataset": {},
                "input_id": "fixture-input",
                "recipe": {},
            }
        )


def test_source_attribution_rejects_created_source_identity() -> None:
    """The ownership boundary fails closed when expansion creates a source."""
    runner = runpy.run_path(str(_RUNNER))

    with pytest.raises(ValueError, match="created a source identity"):
        runner["_source_stage_attribution"](
            source_seed_labels=np.asarray([[1, 0]], dtype=np.int32),
            persistent_support=np.asarray([[True, True]]),
            source_owned_labels=np.asarray([[1, 2]], dtype=np.int32),
            source_measurement_labels=np.asarray([[1, 2]], dtype=np.int32),
            publication_support=np.asarray([[True, True]]),
            hierarchy_diagnostics=None,
        )


def test_attribution_aggregate_is_bounded_and_fail_closed() -> None:
    """The terminal diagnostic requires one scalar schema per input."""
    runner = runpy.run_path(str(_RUNNER))
    records = tuple(
        {
            "schema_version": 3,
            "input_id": f"input-{index:03d}",
            "source_measurement_pixel_count": 10,
            "hierarchy_catalogue_source_count": 1,
        }
        for index in range(144)
    )

    summary = runner["_attribution_summary"](records)

    assert summary["record_count"] == 144
    assert summary["totals"] == {
        "hierarchy_catalogue_source_count": 144,
        "source_measurement_pixel_count": 1440,
    }
    with pytest.raises(ValueError, match="duplicated"):
        runner["_attribution_summary"]((records[0],) * 144)
    malformed: list[dict[str, object]] = [dict(record) for record in records]
    malformed[-1] = {**malformed[-1], "image": np.ones((1, 1))}
    with pytest.raises(ValueError, match="schema changed"):
        runner["_attribution_summary"](tuple(malformed))


def test_executor_digest_includes_source_stage_diagnostics() -> None:
    """Dask equality cannot hide a measurement or topology difference."""
    runner = runpy.run_path(str(_RUNNER))
    summary = AdaptiveScienceSummary(
        product_valid=True,
        completeness=1.0,
        integrated_flux_absolute_fractional_error=0.1,
        mask_iou=0.8,
        split=False,
        support_recall=0.9,
        background_error_median_rms=0.1,
        background_error_p95_rms=0.2,
        rms_error_median_fraction=0.1,
        rms_error_p95_fraction=0.2,
        source_count=1,
    )
    base = runner["_science_sha256"](
        summary,
        ((1.0, 2.0),),
        False,
        {"protected_pixel_count": 1, "protected_window_count": 1},
        {"source_measurement_pixel_count": 10},
    )
    changed = runner["_science_sha256"](
        summary,
        ((1.0, 2.0),),
        False,
        {"protected_pixel_count": 1, "protected_window_count": 1},
        {"source_measurement_pixel_count": 11},
    )

    assert changed != base


def test_source_fields_retain_persistent_support_count() -> None:
    """Executor equality includes the full measurement-support boundary."""
    runner = runpy.run_path(str(_RUNNER))

    assert runner["_source_fields"](
        {
            "input_id": "fixture-input",
            "persistent_support_pixel_count": 17,
            "source_measurement_pixel_count": 19,
        }
    ) == {
        "persistent_support_pixel_count": 17,
        "source_measurement_pixel_count": 19,
    }
