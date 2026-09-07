"""Regression contracts for the source-union spawn-process repair."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import importlib
import multiprocessing
import runpy
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_HELPER_MODULE = (
    "scripts.benchmark.phase5_compact_held_out_source_union_spawn_repair"
)
_RUNNER = _ROOT / (
    "scripts/benchmark/"
    "run_phase5_compact_held_out_source_union_sentinel_spawn_repair.py"
)
_FREEZER = _ROOT / (
    "scripts/validation/"
    "freeze_phase5_compact_held_out_source_union_spawn_repair.py"
)
_FAILED_OUTPUT = _ROOT / (
    "benchmark-results/phase-5/"
    "compact-held-out-source-union-sentinel-gaussian-count-repair.json"
)


def test_spawned_worker_imports_the_gaussian_count_child() -> None:
    """A fresh spawn must not fall back to an ambient parent monkeypatch."""
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    helper: Any = importlib.import_module(_HELPER_MODULE)

    with ProcessPoolExecutor(
        max_workers=1,
        mp_context=multiprocessing.get_context("spawn"),
    ) as pool:
        selected = pool.submit(helper.selected_pybdsf_child).result(timeout=30)

    assert selected.endswith(
        "run_phase5_compact_held_out_source_union_"
        "pybdsf_gaussian_count_repair.py"
    )
    assert "column_case_repair.py" not in selected


def test_runner_installs_an_importable_pair_worker() -> None:
    """The submitted callable must belong to the stable helper module."""
    runner: dict[str, Any] = runpy.run_path(str(_RUNNER))
    parent = runner["_parent"]
    original = parent._pair_worker

    with runner["_configured_parent"]():
        assert parent._pair_worker.__module__ == _HELPER_MODULE

    assert parent._pair_worker is original


def test_spawn_repair_freeze_binds_failure_and_preserves_science() -> None:
    """The replacement changes process dispatch, not science or gates."""
    freezer: dict[str, Any] = runpy.run_path(str(_FREEZER))
    implementation, identity = freezer["build_records"](_ROOT)

    assert file_sha256(_FAILED_OUTPUT) == (
        "a6a119feba1047cf197286c51daaf731b4b88520f58402cb383c9b8a5ad8c0ea"
    )
    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["execution_contract"]["total_finder_executions"] == 348
    assert identity["population"]["image_count"] == 168
    assert implementation["repair"] == {
        "candidate_science_changed": False,
        "comparator_configuration_changed": False,
        "evaluator_or_gate_changed": False,
        "process_dispatch": "explicit-importable-pair-worker",
        "source_count_provenance": "derived-from-exact-gaul-membership",
    }


def test_spawn_repair_freezer_refuses_any_collision(tmp_path: Path) -> None:
    """The replacement record set remains write-once."""
    freezer: dict[str, Any] = runpy.run_path(str(_FREEZER))
    identity = tmp_path / freezer["_IDENTITY"]
    identity.parent.mkdir(parents=True)
    identity.write_text("existing\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_records"](
            argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)
        )

    assert identity.read_text(encoding="utf-8") == "existing\n"
    assert not (tmp_path / freezer["_IMPLEMENTATION"]).exists()
