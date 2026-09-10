"""Replacement late failures never require re-running preserved finders."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_ROOT))
runner: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replacement_runner"
)
binding = importlib.import_module(
    "scripts.validation.source_catalogue_replay_plan"
).binding


@pytest.mark.parametrize(
    "failure",
    (None, "capture", "census", "dask", "evaluation", "reuse", "aggregation"),
)
def test_stages_preserve_candidate_and_original_comparators(  # noqa: C901
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    scratch = tmp_path / "new"
    retained = [{"path": "never-write-reference", "sha256": "a" * 64}]
    plan: dict[str, Any] = {
        "scratch": str(scratch),
        "output": str(tmp_path / "terminal.json"),
        "tasks": [{"input_id": "fixture"}],
        "candidate": {"revision": "new"},
        "incumbent": {"revision": "old"},
        "retained_records": retained,
    }
    calls: list[tuple[str, str]] = []

    def stage(
        name: str, _tasks: Any, worker: Any, _progress: Any
    ) -> list[dict[str, Any]]:
        calls.append((name, worker.__name__))
        if failure == name:
            raise RuntimeError("injected " + name)
        if name == "capture":
            path = scratch / "pair.json"
            path.write_text(
                json.dumps(
                    {"input_id": "wrong" if failure == "census" else "fixture"}
                )
            )
            return [binding(path)]
        return [{"input_id": "fixture", "records": []}]

    def dask(*_args: Any) -> list[Any]:
        if failure == "dask":
            raise RuntimeError("injected dask")
        (scratch / "dask-comparisons.json").write_text("{}")
        return []

    def combine(_pairs: Any, evaluated: Any, reused: Any) -> Any:
        assert reused == retained
        if failure == "reuse":
            raise ValueError("injected reuse")
        return evaluated

    def aggregate(*_args: Any) -> dict[str, Any]:
        if failure == "aggregation":
            raise RuntimeError("injected aggregation")
        return {"status": "fail", "all_required_endpoints_pass": False}

    monkeypatch.setattr(runner, "_run_stage", stage, raising=False)
    monkeypatch.setattr(runner, "compare_existing_dask", dask, raising=False)
    monkeypatch.setattr(runner, "combine_records", combine, raising=False)
    monkeypatch.setattr(runner, "aggregate_records", aggregate, raising=False)
    if failure:
        with pytest.raises((RuntimeError, ValueError)):
            runner.run_replacement(plan, {"fixture": True})
        assert not Path(plan["output"]).exists()
        assert (
            json.loads((scratch / "process-failure.json").read_bytes())[
                "candidate_products_preserved"
            ]
            is True
        )
        if failure in ("dask", "evaluation", "reuse", "aggregation"):
            assert (scratch / "capture-seal.json").exists()
        if failure in ("reuse", "aggregation"):
            assert (scratch / "current-evaluation-seal.json").exists()
        if failure == "aggregation":
            assert (scratch / "evaluation-seal.json").exists()
    else:
        terminal = runner.run_replacement(plan, {"fixture": True})
        assert (terminal["campaign"], terminal["candidate"]) == (
            "phase-5-public-catalogue-replacement-cumulative",
            plan["candidate"],
        )
        assert terminal["result"]["status"] == "fail"
        assert terminal["candidate_serial_executions"] == 1
        assert (
            terminal["incumbent_executions"]
            == terminal["pybdsf_executions"]
            == terminal["aegean_executions"]
            == 0
        )
        assert terminal["reused_comparator_records"] == 1
        assert terminal["fresh_qualification"] is False
        assert json.loads(Path(plan["output"]).read_bytes()) == terminal
    assert calls[0] == ("capture", "capture_replacement")
    assert all(
        worker in ("capture_replacement", "evaluate_replacement")
        for _, worker in calls
    )
    with pytest.raises(FileExistsError):
        runner.run_replacement(plan, {"fixture": True})
