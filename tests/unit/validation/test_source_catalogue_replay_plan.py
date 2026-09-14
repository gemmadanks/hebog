"""Portable identity and no-write contracts for source-catalogue replay."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hebog.validation.external_runners import canonical_sha256

_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_ROOT))
planning: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replay_plan"
)


def _census() -> dict[str, Any]:
    tasks = [
        {
            "input_id": f"fixture-{index}",
            "lane": "compact-blend" if index < 800 else "continuum",
            "dataset_identifier": f"group-{index // 400}",
        }
        for index in range(2400)
    ]
    return {
        "tasks": tasks,
        "workers": 2,
        "candidate_serial_executions": 2400,
        "incumbent_executions": 2400,
        "pybdsf_executions": 0,
        "existing_dask_comparisons": 12,
        "reference_run_count": 9600,
        "bootstrap_resamples": 50000,
        "bootstrap_seed": 20260810,
        "retained_references": {
            f"reference-{index}": {} for index in range(9600)
        },
        "dask_input_ids": planning.select_dask_inputs(tasks),
    }


@pytest.mark.parametrize(
    "defect",
    (
        None,
        "status",
        "started",
        "root",
        "revision",
        "origin",
        "source",
        "configuration",
        "runtime",
        "python",
    ),
)
def test_live_code_and_runtime_must_match_the_plan_identity(  # noqa: C901
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str | None,
) -> None:
    """Replay rejects every mismatch without reading historical Git objects."""
    plan: dict[str, Any] = {
        "status": "frozen-non-executable",
        "finder_execution_started": False,
        "execution_root": str(tmp_path),
        "execution_revision": "a" * 40,
        "candidate": {
            "source_tree_sha256": "b" * 64,
            "configuration_sha256": canonical_sha256({}),
        },
        "configuration": {},
        "runtime": {
            "dependency_inventory_sha256": "c" * 64,
            "python": "3.14.2",
        },
    }
    monkeypatch.setattr(
        planning, "repository_revision", lambda _root: "a" * 40
    )
    monkeypatch.setattr(planning, "source_tree_sha256", lambda _root: "b" * 64)
    monkeypatch.setattr(
        planning, "dependency_inventory_sha256", lambda: "c" * 64
    )
    monkeypatch.setattr(planning.platform, "python_version", lambda: "3.14.2")
    monkeypatch.setattr(
        planning,
        "hebog",
        SimpleNamespace(__file__=str(tmp_path / "src/hebog/__init__.py")),
    )
    if defect == "status":
        plan["status"] = "consumed"
    elif defect == "started":
        plan["finder_execution_started"] = True
    elif defect == "root":
        plan["execution_root"] = str(tmp_path / "other")
    elif defect == "revision":
        plan["execution_revision"] = "d" * 40
    elif defect == "origin":
        monkeypatch.setattr(
            planning,
            "hebog",
            SimpleNamespace(__file__=str(tmp_path / "other/hebog.py")),
        )
    elif defect == "source":
        plan["candidate"]["source_tree_sha256"] = "d" * 64
    elif defect == "configuration":
        plan["configuration"] = {"changed": True}
    elif defect == "runtime":
        plan["runtime"]["dependency_inventory_sha256"] = "d" * 64
    elif defect == "python":
        plan["runtime"]["python"] = "3.12.0"
    if defect is None:
        planning.verify_code_identity(plan, tmp_path)
    else:
        with pytest.raises(ValueError, match="R6"):
            planning.verify_code_identity(plan, tmp_path)


@pytest.mark.parametrize("defect", (None, "metadata", "scratch", "disk"))
def test_preflight_reads_all_native_files_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str | None,
) -> None:
    """Preflight checks every bound artifact and leaves outputs untouched."""
    path = tmp_path / "metadata.json"
    path.write_text("{}\n")
    plan = _census()
    plan.update(
        {
            "scratch": str(tmp_path / "scratch"),
            "output": str(tmp_path / "terminal.json"),
            "metadata": {"fixture": planning.binding(path)},
            "admission": {"required_free_bytes": 100},
        }
    )
    for task in plan["tasks"]:
        task["input_manifest"] = planning.binding(path)
    for key in plan["retained_references"]:
        plan["retained_references"][key] = planning.binding(path)
    monkeypatch.setattr(planning, "verify_code_identity", lambda *_args: None)
    monkeypatch.setattr(planning, "verify_task_metadata", lambda *_args: None)
    monkeypatch.setattr(
        planning, "verify_historical_producer", lambda *_args: None
    )
    calls: list[Path] = []
    monkeypatch.setattr(
        planning, "native_artifacts", lambda path, _sha: calls.append(path)
    )
    monkeypatch.setattr(
        planning.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=99 if defect == "disk" else 1000),
    )
    if defect == "metadata":
        path.write_text('{"changed": true}\n')
    if defect == "scratch":
        Path(plan["scratch"]).mkdir()
    if defect is not None:
        with pytest.raises((ValueError, FileExistsError)):
            planning.verify_replay_plan(plan, tmp_path)
    else:
        planning.verify_replay_plan(plan, tmp_path)
        assert len(calls) == 12000
    assert not Path(plan["output"]).exists()
    assert Path(plan["scratch"]).exists() is (defect == "scratch")
