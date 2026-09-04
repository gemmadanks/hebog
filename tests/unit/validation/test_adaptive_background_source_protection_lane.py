"""Contracts for the source-protected adaptive-background lane."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

_ROOT = Path(__file__).parents[3]
_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_adaptive_background_source_protection.py"
)
_RUNNER = (
    _ROOT / "scripts/validation/"
    "run_phase5_adaptive_background_source_protection.py"
)
_IMPLEMENTATION = (
    _ROOT / "config/contracts/"
    "phase-5-adaptive-background-source-protection-implementation-decision.json"
)
_PUBLIC_IDENTITY = (
    _ROOT / "config/contracts/"
    "phase-5-adaptive-background-source-protection-public-interface-identity-review.json"
)
_IDENTITY = (
    _ROOT / "config/contracts/"
    "phase-5-adaptive-background-source-protection-identity-review.json"
)
_MANIFEST = (
    _ROOT
    / "config/contracts/phase-5-adaptive-background-development-manifest.json"
)
_FREEZE_REVISION = "d860050e174ee6633260630f804dd7063517606b"


def _historical_bytes(revision: str, relative_path: str) -> bytes:
    """Read one immutable file from the revision that froze its evidence."""
    return subprocess.run(
        ("git", "show", f"{revision}:{relative_path}"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout


def _terminal_products(
    *,
    detection_support: np.ndarray,
    measurement_support: np.ndarray | None = None,
    publication_support: np.ndarray | None = None,
) -> SimpleNamespace:
    """Return minimal terminal products for attribution boundary tests."""
    terminal: dict[str, object] = {
        "direct_component_labels": detection_support.astype(np.int32),
        "significant_multiscale_support": np.zeros_like(
            detection_support,
            dtype=np.bool_,
        ),
    }
    if measurement_support is not None:
        terminal["measurement_component_labels"] = measurement_support.astype(
            np.int32
        )
    if publication_support is not None:
        terminal["detection"] = SimpleNamespace(
            retained_mask=publication_support
        )
    return SimpleNamespace(terminal=SimpleNamespace(**terminal))


def test_frozen_successor_identities_are_reproducible_and_non_executable() -> (
    None
):
    """The superseded lane remains bound to its exact frozen snapshot."""
    identity = json.loads(_IDENTITY.read_text())
    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["candidate"] == {
        "configuration_sha256": (
            "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
        ),
        "entrypoint": "hebog.find_sources",
        "revision": "7ebde589c82e153e0f7d475a8469c120138be4da",
        "source_tree_sha256": (
            "c83ee5a90c33f9c915b69402710835a5a094d08df83e003f8e2fd0799f23ae2d"
        ),
    }
    for binding in identity["program_bindings"].values():
        assert (
            hashlib.sha256(
                _historical_bytes(_FREEZE_REVISION, binding["path"])
            ).hexdigest()
            == binding["sha256"]
        )
    assert (
        _historical_bytes(
            _FREEZE_REVISION,
            str(_IDENTITY.relative_to(_ROOT)),
        )
        == _IDENTITY.read_bytes()
    )


def test_complete_no_write_verification_creates_no_namespace(
    tmp_path: Path,
) -> None:
    """A superseded lane fails closed without starting science."""
    runner = runpy.run_path(str(_RUNNER))
    scratch = tmp_path / "scratch"
    output = tmp_path / "decision.json"
    with pytest.raises(
        ValueError,
        match="adaptive source-protection public candidate changed",
    ):
        runner["verify_no_write"](
            repository_root=_ROOT,
            manifest_path=_MANIFEST,
            identity_path=_IDENTITY,
            scratch=scratch,
            output=output,
            enforce_execution_paths=False,
        )

    assert not scratch.exists()
    assert not output.exists()


def test_attribution_record_separates_stage_losses() -> None:
    """One bounded record locates losses without retaining image arrays."""
    runner = runpy.run_path(str(_RUNNER))
    truth = np.ones((5, 5), dtype=np.bool_)
    coarse_support = truth.copy()
    adaptive_support = truth.copy()
    adaptive_support[0, 0] = False
    measurement = adaptive_support.copy()
    measurement[0, 1] = False
    publication = measurement.copy()
    publication[0, 2] = False
    coarse = _terminal_products(
        detection_support=coarse_support,
    )
    candidate = _terminal_products(
        detection_support=adaptive_support,
        measurement_support=measurement,
        publication_support=publication,
    )
    detection = SimpleNamespace(
        background_rms_grids=SimpleNamespace(
            adaptive_protected_pixel_count=9,
            adaptive_protected_window_count=4,
        )
    )

    record = runner["_attribution_record"](
        truth=truth,
        coarse_products=coarse,
        candidate_products=candidate,
        candidate_detection=detection,
    )

    assert record["adaptive_background_rejected_count"] == 1
    assert record["measurement_rejected_count"] == 1
    assert record["publication_rejected_count"] == 1
    assert record["protected_pixel_count"] == 9
    assert record["protected_window_count"] == 4
    assert all(not isinstance(value, np.ndarray) for value in record.values())


def test_serial_wrapper_writes_only_array_free_attribution(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Transient captured planes become one bounded per-input sidecar."""
    runner = runpy.run_path(str(_RUNNER))
    globals_ = runner["_run_serial_task"].__globals__
    truth = np.ones((4, 4), dtype=np.bool_)
    products = _terminal_products(
        detection_support=truth,
        measurement_support=truth,
        publication_support=truth,
    )
    detection = SimpleNamespace(
        background_rms_grids=SimpleNamespace(
            adaptive_protected_pixel_count=16,
            adaptive_protected_window_count=2,
        )
    )
    task = SimpleNamespace(input_id="fixture-input", recipe=object())

    def parent(_task: object, scratch: Path) -> dict[str, object]:
        (scratch / "fixture-input").mkdir()
        globals_["_captured_candidate"].update(
            {"detection": detection, "products": products}
        )
        globals_["_captured_coarse"].update({"products": products})
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
    assert result["observation"] == {"input_id": "fixture-input"}
    assert sidecar["protected_pixel_count"] == 16
    assert sidecar["protected_window_count"] == 2
    assert all(not isinstance(value, np.ndarray) for value in sidecar.values())


def test_attribution_aggregate_is_bounded_and_fail_closed() -> None:
    """The terminal diagnostic accepts one canonical record per input."""
    runner = runpy.run_path(str(_RUNNER))
    records = tuple(
        {
            "schema_version": 1,
            "input_id": f"input-{index:03d}",
            "truth_pixel_count": 10,
            "protected_pixel_count": index,
        }
        for index in range(144)
    )

    summary = runner["_attribution_summary"](records)

    assert summary["status"] == "non-binding-diagnostic"
    assert summary["record_count"] == 144
    assert summary["totals"] == {
        "protected_pixel_count": sum(range(144)),
        "truth_pixel_count": 1440,
    }
    with pytest.raises(ValueError, match="duplicated"):
        runner["_attribution_summary"]((records[0],) * 144)


def test_execution_requires_a_separate_exact_decision() -> None:
    """The successor identity alone cannot start the development lane."""
    runner = runpy.run_path(str(_RUNNER))
    arguments = argparse.Namespace(
        execution_decision=None,
        identity_review=_IDENTITY,
        manifest=_MANIFEST,
        output=(
            _ROOT / "benchmark-results/phase-5/"
            "adaptive-background-source-protection-development-decision.json"
        ),
        repository_root=_ROOT,
        scratch=Path(
            "/private/tmp/"
            "hebog-phase5-adaptive-background-source-protection-7ebde58"
        ),
        workers=2,
    )

    with pytest.raises(PermissionError, match="exact execution decision"):
        runner["_verify_execution_authority"](arguments)


def test_identity_collision_is_atomic(
    tmp_path: Path,
) -> None:
    """One stale destination prevents every successor identity write."""
    freezer = runpy.run_path(str(_FREEZER))
    existing = tmp_path / _IDENTITY.relative_to(_ROOT)
    existing.parent.mkdir(parents=True)
    existing.write_text("existing\n", encoding="utf-8")
    arguments = argparse.Namespace(
        output_root=tmp_path,
        repository_root=_ROOT,
    )
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_identities"](arguments)

    assert existing.read_text() == "existing\n"
    assert not (tmp_path / _PUBLIC_IDENTITY.relative_to(_ROOT)).exists()
    assert not (tmp_path / _IMPLEMENTATION.relative_to(_ROOT)).exists()
