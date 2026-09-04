"""Contracts for the combined adaptive measurement/topology lane."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from astropy.io import fits

from hebog import public_science
from hebog.validation.adaptive_background_lane import AdaptiveScienceSummary
from hebog.validation.datasets import DatasetManifest

_ROOT = Path(__file__).parents[3]
_REPAIR_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_source_owned_measurement_topology_process_repair.py"
)
_RUNNER = (
    _ROOT / "scripts/validation/"
    "run_phase5_source_owned_measurement_topology.py"
)
_PREFIX = "phase-5-source-owned-measurement-topology"
_IMPLEMENTATION = (
    _ROOT / f"config/contracts/{_PREFIX}-implementation-decision.json"
)
_PUBLIC_IDENTITY = (
    _ROOT / f"config/contracts/{_PREFIX}-public-interface-identity-review.json"
)
_PREDECESSOR_IDENTITY = (
    _ROOT / f"config/contracts/{_PREFIX}-identity-review.json"
)
_IDENTITY = (
    _ROOT / f"config/contracts/{_PREFIX}-process-repair-identity-review.json"
)
_FAILED_DECISION = (
    _ROOT / f"config/contracts/{_PREFIX}-execution-decision.json"
)
_MANIFEST = (
    _ROOT
    / "config/contracts/phase-5-adaptive-background-development-manifest.json"
)


def _sha256(path: Path) -> str:
    """Hash one exact file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_repair_identity_is_reproducible_and_non_executable() -> None:
    """Historical identities stay exact and the repair grants no authority."""
    expected_historical_sha256 = {
        _PUBLIC_IDENTITY: (
            "ca1abba66a6368fe37fb8e43b93b81999ced462f3e01d16be9011cc629913490"
        ),
        _IMPLEMENTATION: (
            "fc4728c852da061920c9e8cb68facb18990256e18949fad4a1a0873b20b06731"
        ),
        _PREDECESSOR_IDENTITY: (
            "4c611f1b61113584512f45650ef41e468237c59413b7464a7070cd7bce0e4944"
        ),
        _FAILED_DECISION: (
            "c169bb85ba39d8fa0092e4315738514e0e47d05920b39dde49f8c857006f412d"
        ),
    }
    assert {
        path: _sha256(path) for path in expected_historical_sha256
    } == expected_historical_sha256

    freezer = runpy.run_path(str(_REPAIR_FREEZER))
    assert freezer["build_identity"](_ROOT) == json.loads(
        _IDENTITY.read_text()
    )
    identity = json.loads(_IDENTITY.read_text())
    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["candidate"]["revision"] == (
        "c28343fb85ae9bd0d1d927701564f93fbe51b659"
    )
    for binding in identity["program_bindings"].values():
        assert _sha256(_ROOT / binding["path"]) == binding["sha256"]


def test_complete_no_write_verification_creates_no_namespace(
    tmp_path: Path,
) -> None:
    """All future work is verified without executing or creating products."""
    runner = runpy.run_path(str(_RUNNER))
    scratch = tmp_path / "scratch"
    output = tmp_path / "decision.json"

    result = runner["verify_no_write"](
        repository_root=_ROOT,
        manifest_path=_MANIFEST,
        identity_path=_IDENTITY,
        scratch=scratch,
        output=output,
        enforce_execution_paths=False,
    )

    assert result["status"] == "pass"
    assert result["candidate_execution_count"] == 144
    assert result["coarse_control_execution_count"] == 144
    assert result["existing_dask_execution_count"] == 12
    assert result["candidate_execution_started"] is False
    assert result["fixture_seam_status"] == "pass"
    assert result["process_payload_status"] == "pickle-pass"
    assert not scratch.exists()
    assert not output.exists()


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
            }
        )
        globals_["_captured_coarse"].update({"detection_support": truth})
        return {"input_id": "fixture-input"}

    def synthetic_truth(_recipe: object) -> tuple[None, np.ndarray, None]:
        return None, truth, None

    monkeypatch.setitem(globals_, "_parent_run_serial_task", parent)
    monkeypatch.setitem(
        globals_,
        "source_signal_and_truth",
        synthetic_truth,
    )

    result = runner["_run_serial_task"](task, tmp_path)
    sidecar = json.loads(
        (tmp_path / "fixture-input/attribution.json").read_text()
    )

    assert result["attribution"] == sidecar
    assert sidecar["schema_version"] == 2
    assert sidecar["source_measurement_pixel_count"] == 6
    assert sidecar["protected_pixel_count"] == 6
    assert all(not isinstance(value, np.ndarray) for value in sidecar.values())


def test_process_pool_payload_is_pickle_safe_and_exact() -> None:
    """Parent run-path task classes never cross the process boundary."""
    runner = runpy.run_path(str(_RUNNER))
    manifest = DatasetManifest.model_validate_json(_MANIFEST.read_bytes())
    task = runner["_parent_tasks"](manifest)[0]

    payload = runner["_serial_task_payload"](task)
    restored = pickle.loads(pickle.dumps(payload))
    rebuilt = runner["_task_from_payload"](restored)

    assert rebuilt.input_id == task.input_id
    assert rebuilt.cell == task.cell
    assert rebuilt.dataset == task.dataset
    assert rebuilt.recipe == task.recipe
    assert (
        runner["_verify_process_payload"](
            payload,
            spawn_process=False,
        )
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


def test_no_write_fixture_seams_reject_created_source_identity() -> None:
    """The exact preflight exercises the fail-closed ownership boundary."""
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
            "schema_version": 2,
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


def test_no_write_rejects_source_tree_drift(monkeypatch: Any) -> None:
    """The frozen lane rejects any post-freeze production source change."""
    runner = runpy.run_path(str(_RUNNER))
    globals_ = runner["_verify_frozen_identity"].__globals__
    identity = json.loads(_IDENTITY.read_text())

    def drifted_source_tree(_root: Path) -> str:
        return "0" * 64

    monkeypatch.setitem(globals_, "source_tree_sha256", drifted_source_tree)

    with pytest.raises(ValueError, match="source tree changed"):
        runner["_verify_frozen_identity"](_ROOT, _MANIFEST, identity)


def test_execution_requires_a_separate_exact_decision() -> None:
    """The frozen combined identity cannot start the lane."""
    runner = runpy.run_path(str(_RUNNER))
    arguments = argparse.Namespace(
        execution_decision=None,
        identity_review=_IDENTITY,
        manifest=_MANIFEST,
        output=(
            _ROOT / "benchmark-results/phase-5/"
            "source-owned-measurement-topology-development-decision.json"
        ),
        repository_root=_ROOT,
        scratch=Path(
            "/private/tmp/"
            "hebog-phase5-source-owned-measurement-topology-"
            "process-repair-c28343f"
        ),
        workers=2,
    )

    with pytest.raises(PermissionError, match="exact execution decision"):
        runner["_verify_execution_authority"](arguments)


def test_identity_collision_is_atomic(tmp_path: Path) -> None:
    """A stale repair-identity destination remains untouched."""
    freezer = runpy.run_path(str(_REPAIR_FREEZER))
    existing = tmp_path / _IDENTITY.relative_to(_ROOT)
    existing.parent.mkdir(parents=True)
    existing.write_text("existing\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        freezer["freeze_identity"](
            argparse.Namespace(output_root=tmp_path, repository_root=_ROOT)
        )

    assert existing.read_text() == "existing\n"
