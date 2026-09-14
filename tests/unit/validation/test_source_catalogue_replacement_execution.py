"""Replacement replay roles are explicit and never rescore a comparator."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.adaptive_background_lane import (
    build_adaptive_development_manifest,
)
from hebog.validation.datasets import iter_dataset_recipes, recipe_sha256
from hebog.validation.external_runners import canonical_sha256

_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_ROOT))
evaluator: Any = importlib.import_module(
    "scripts.validation.source_catalogue_input_evaluation"
)
replacement: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replacement_execution"
)
retain_image_record = importlib.import_module(
    "scripts.validation.source_catalogue_campaign_evidence"
).retain_image_record
binding = importlib.import_module(
    "scripts.validation.source_catalogue_replay_plan"
).binding


@pytest.mark.parametrize("lane", ("compact-blend", "continuum"))
@pytest.mark.parametrize("bad_recipe", (False, True))
def test_current_only_selection_uses_unchanged_kernel(
    monkeypatch: pytest.MonkeyPatch, lane: str, bad_recipe: bool
) -> None:
    dataset = build_adaptive_development_manifest().datasets[0]
    recipe = iter_dataset_recipes(dataset)[0]
    context = {
        "datasets": {dataset.identifier: dataset},
        "recipes": {(dataset.identifier, recipe.seed): recipe},
    }

    def load_context(_root: Path) -> dict[str, Any]:
        return context

    calls: list[dict[str, Any]] = []

    def kernel(
        task: dict[str, Any], selected: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        assert set(task["captures"]) == {"current-hebog"}
        assert selected["recipe"] == recipe
        calls.append(task)
        return ({"input_id": "fixture", "finder_id": "current-hebog"},)

    monkeypatch.setattr(evaluator, "evaluation_context", load_context)
    monkeypatch.setattr(evaluator, "_compact_records", kernel)
    monkeypatch.setattr(evaluator, "_continuum_records", kernel)
    task: dict[str, Any] = {
        "input_id": "fixture",
        "lane": lane,
        "dataset_identifier": dataset.identifier,
        "seed": recipe.seed,
        "recipe_sha256": "0" * 64 if bad_recipe else recipe_sha256(recipe),
        "captures": {
            "current-hebog": {},
            "incumbent-hebog": {},
            "released-pybdsf": {},
            "pinned-pybdsf-master": {},
        },
    }
    if lane == "compact-blend":
        task["captures"]["aegean"] = {}
    if bad_recipe:
        with pytest.raises(ValueError, match="recipe"):
            replacement.evaluate_current_input(task, _ROOT)
        assert not calls
    else:
        assert (
            replacement.evaluate_current_input(task, _ROOT)[0]["finder_id"]
            == "current-hebog"
        )
        assert len(calls) == 1
        assert "incumbent-hebog" in task["captures"]


@pytest.mark.parametrize(
    "defect",
    (
        None,
        "missing",
        "duplicate",
        "old-current",
        "foreign",
        "capture",
        "bytes",
        "capture-census",
        "schema",
        "new-duplicate",
        "task-duplicate",
        "new-missing",
    ),
)
def test_combined_records_preserve_exact_bytes_and_census(  # noqa: C901, PLR0912
    tmp_path: Path, defect: str | None
) -> None:
    captures = {
        finder: {
            "path": str(tmp_path / (finder + "-capture")),
            "sha256": "a" * 64,
        }
        for finder in (
            "current-hebog",
            "incumbent-hebog",
            "released-pybdsf",
            "pinned-pybdsf-master",
        )
    }
    task: dict[str, Any] = {
        "input_id": "fixture",
        "lane": "continuum",
        "captures": captures,
    }
    retained: list[dict[str, str]] = []
    new: list[dict[str, str]] = []
    for finder, capture in captures.items():
        record = {
            "schema_version": 1,
            "input_id": "fixture",
            "lane": "continuum",
            "finder_id": finder,
            "capture": capture,
        }
        if defect == "capture" and finder == "released-pybdsf":
            record["capture"] = {}
        if defect == "schema" and finder == "released-pybdsf":
            record["schema_version"] = True
        if defect == "foreign" and finder == "released-pybdsf":
            record["input_id"] = "foreign"
        record["record_sha256"] = canonical_sha256(record)
        path = tmp_path / (finder + ".json")
        retain_image_record(path, record)
        entry = binding(path)
        if finder == "current-hebog":
            new.append(entry)
        else:
            retained.append(
                {"input_id": "fixture", "finder_id": finder, **entry}
            )
    if defect == "missing":
        retained.pop()
    elif defect == "duplicate":
        retained.append(retained[0])
    elif defect == "old-current":
        retained.append(
            {"input_id": "fixture", "finder_id": "current-hebog", **new[0]}
        )
    elif defect == "bytes":
        Path(retained[0]["path"]).write_text("{}\n")
    before = {row["path"]: Path(row["path"]).read_bytes() for row in retained}
    completed = [{"input_id": "fixture", "records": new}]
    tasks = [task]
    if defect == "capture-census":
        task["captures"].pop("current-hebog")
    elif defect == "new-duplicate":
        completed.append(completed[0])
    elif defect == "task-duplicate":
        tasks.append(task)
    elif defect == "new-missing":
        completed.clear()
    if defect:
        with pytest.raises(ValueError):
            replacement.combine_records(tasks, completed, retained)
    else:
        combined = replacement.combine_records([task], completed, retained)
        assert combined == [
            {
                "input_id": "fixture",
                "records": [
                    new[0],
                    *[
                        {"path": row["path"], "sha256": row["sha256"]}
                        for row in sorted(
                            retained, key=lambda row: row["finder_id"]
                        )
                    ],
                ],
            }
        ]
        assert len(combined[0]["records"]) == 4
        assert (
            json.loads(Path(new[0]["path"]).read_bytes())["finder_id"]
            == "current-hebog"
        )
    assert before == {path: Path(path).read_bytes() for path in before}


@pytest.mark.parametrize("fail", (False, True))
def test_current_workers_are_write_once_and_preserve_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    calls: list[dict[str, Any]] = []

    def capture(task: dict[str, Any]) -> dict[str, str]:
        calls.append(task)
        path = Path(task["output_directory"]) / "capture.json"
        path.parent.mkdir()
        path.write_text("{}\n")
        return binding(path)

    def evaluate(
        task: dict[str, Any], root: Path
    ) -> tuple[dict[str, Any], ...]:
        assert root == _ROOT
        if fail:
            raise RuntimeError("injected evaluation failure")
        record: dict[str, Any] = {
            "schema_version": 1,
            "input_id": task["input_id"],
            "finder_id": "current-hebog",
            "lane": "continuum",
            "capture": task["captures"]["current-hebog"],
        }
        record["record_sha256"] = canonical_sha256(record)
        return (record,)

    monkeypatch.setattr(replacement, "capture_current_task", capture)
    monkeypatch.setattr(replacement, "evaluate_current_input", evaluate)
    task: dict[str, Any] = {
        "input_id": "fixture",
        "lane": "continuum",
        "root": str(_ROOT),
        "output_directory": str(tmp_path / "new"),
        "captures": {
            finder: {}
            for finder in (
                "incumbent-hebog",
                "released-pybdsf",
                "pinned-pybdsf-master",
            )
        },
    }
    entry = replacement.capture_replacement(task)
    saved = json.loads(Path(entry["path"]).read_bytes())
    assert len(calls) == 1
    assert "historical_task" not in calls[0]
    assert set(saved["captures"]) == replacement.expected_finders("continuum")
    with pytest.raises(FileExistsError):
        replacement.capture_replacement(task)
    if fail:
        with pytest.raises(RuntimeError, match="injected"):
            replacement.evaluate_replacement(saved)
    else:
        completed = replacement.evaluate_replacement(saved)
        assert len(completed["records"]) == 1
        assert (
            json.loads(Path(completed["records"][0]["path"]).read_bytes())[
                "finder_id"
            ]
            == "current-hebog"
        )
        with pytest.raises(FileExistsError):
            replacement.evaluate_replacement(saved)
    assert Path(saved["captures"]["current-hebog"]["path"]).exists()


@pytest.mark.parametrize("lane", ("other", "continuum"))
def test_capture_rejects_wrong_roles_before_work(
    tmp_path: Path, lane: str
) -> None:
    with pytest.raises(ValueError, match=r"lane|census"):
        replacement.capture_replacement(
            {
                "lane": lane,
                "captures": {},
                "output_directory": str(tmp_path / "new"),
            }
        )
    assert not (tmp_path / "new").exists()


def test_evaluation_rejects_wrong_roles_before_loading_truth() -> None:
    with pytest.raises(ValueError, match="finder census"):
        replacement.evaluate_current_input(
            {"lane": "continuum", "captures": {}}, _ROOT
        )


@pytest.mark.parametrize("defect", ("empty", "finder", "input"))
def test_evaluation_rejects_wrong_new_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    def evaluate(*_args: Any) -> tuple[dict[str, Any], ...]:
        if defect == "empty":
            return ()
        return (
            {
                "finder_id": "released-pybdsf"
                if defect == "finder"
                else "current-hebog",
                "input_id": "wrong" if defect == "input" else "fixture",
            },
        )

    monkeypatch.setattr(replacement, "evaluate_current_input", evaluate)
    with pytest.raises(ValueError, match="current record census"):
        replacement.evaluate_replacement(
            {
                "evaluation_directory": str(tmp_path / "evaluation"),
                "root": str(_ROOT),
                "input_id": "fixture",
            }
        )
    assert not (tmp_path / "evaluation/complete.json").exists()
