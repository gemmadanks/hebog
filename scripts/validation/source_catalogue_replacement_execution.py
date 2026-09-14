"""Current-only replay workers; preserved comparator records are read-only."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.validation import source_catalogue_input_evaluation as evaluator
from scripts.validation.source_catalogue_campaign_evidence import (
    load_image_records,
    retain_image_record,
)
from scripts.validation.source_catalogue_campaign_execution import (
    capture_current_task,
)
from scripts.validation.source_catalogue_replay_plan import binding

from hebog.validation.datasets import recipe_sha256
from hebog.validation.diagnostic_retention import _atomic_json


def capture_replacement(task: dict[str, Any]) -> dict[str, str]:
    """Capture only current Hebog and retain the full comparison manifest."""
    if set(task["captures"]) != expected_finders(task["lane"]) - {
        "current-hebog"
    }:
        raise ValueError("replacement retained capture census changed")
    directory = Path(task["output_directory"])
    directory.mkdir(parents=True, exist_ok=False)
    current = capture_current_task(
        {**task, "output_directory": str(directory / "current")}
    )
    captured = {
        **task,
        "evaluation_directory": str(directory / "evaluation"),
        "captures": {**task["captures"], "current-hebog": current},
    }
    _atomic_json(directory / "pair.json", captured)
    return binding(directory / "pair.json")


def evaluate_replacement(task: dict[str, Any]) -> dict[str, Any]:
    """Retain one new current record before late aggregate statistics."""
    output = Path(task["evaluation_directory"])
    output.mkdir(parents=True, exist_ok=False)
    records = evaluate_current_input(task, Path(task["root"]))
    if (
        len(records) != 1
        or records[0]["finder_id"] != "current-hebog"
        or records[0]["input_id"] != task["input_id"]
    ):
        raise ValueError("replacement current record census changed")
    record = records[0]
    _verify_record_capture(record, task)
    path = output / "current-hebog.json"
    digest = retain_image_record(path, record)
    completed = {
        "input_id": task["input_id"],
        "records": [{"path": str(path), "sha256": digest}],
    }
    _atomic_json(output / "complete.json", completed)
    return completed


def expected_finders(lane: str) -> set[str]:
    """Keep the complete comparator census even when only Hebog is scored."""
    finders = {
        "current-hebog",
        "incumbent-hebog",
        "released-pybdsf",
        "pinned-pybdsf-master",
    }
    if lane == "compact-blend":
        finders.add("aegean")
    elif lane != "continuum":
        raise ValueError("replacement evaluation lane is unsupported")
    return finders


def evaluate_current_input(
    task: dict[str, Any], root: Path
) -> tuple[dict[str, Any], ...]:
    """Evaluate only the new candidate using the existing scientific kernel."""
    if set(task["captures"]) != expected_finders(task["lane"]):
        raise ValueError("replacement finder census changed")
    context = evaluator.evaluation_context(root)
    recipe = context["recipes"][(task["dataset_identifier"], task["seed"])]
    if recipe_sha256(recipe) != task["recipe_sha256"]:
        raise ValueError("replacement recipe identity changed")
    selected = {
        **context,
        "recipe": recipe,
        "dataset": context["datasets"][task["dataset_identifier"]],
    }
    current = {
        **task,
        "captures": {"current-hebog": task["captures"]["current-hebog"]},
    }
    kernel = (
        evaluator._compact_records
        if task["lane"] == "compact-blend"
        else evaluator._continuum_records
    )
    return kernel(current, selected)


def combine_records(
    tasks: list[dict[str, Any]],
    completed: list[dict[str, Any]],
    retained: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Verify new and retained roles before the unchanged aggregate engine."""
    by_input = {task["input_id"]: task for task in tasks}
    new = {row["input_id"]: row for row in completed}
    expected = {
        (task["input_id"], finder)
        for task in tasks
        for finder in expected_finders(task["lane"]) - {"current-hebog"}
    }
    keys = [(row["input_id"], row["finder_id"]) for row in retained]
    if (
        len(by_input) != len(tasks)
        or len(new) != len(completed)
        or set(new) != set(by_input)
        or len(keys) != len(set(keys))
        or set(keys) != expected
    ):
        raise ValueError("replacement retained/new census changed")
    retained_by_input: dict[str, list[dict[str, str]]] = {}
    for row in sorted(
        retained, key=lambda row: (row["input_id"], row["finder_id"])
    ):
        entry = {"path": row["path"], "sha256": row["sha256"]}
        (record,) = load_image_records(
            [entry], [(row["input_id"], row["finder_id"])]
        )
        _verify_record_capture(record, by_input[row["input_id"]])
        retained_by_input.setdefault(row["input_id"], []).append(entry)
    combined: list[dict[str, Any]] = []
    for identifier, task in sorted(by_input.items()):
        if set(task["captures"]) != expected_finders(task["lane"]):
            raise ValueError("replacement capture census changed")
        entries = new[identifier]["records"]
        (record,) = load_image_records(
            entries, [(identifier, "current-hebog")]
        )
        _verify_record_capture(record, task)
        combined.append(
            {
                "input_id": identifier,
                "records": [*entries, *retained_by_input[identifier]],
            }
        )
    return combined


def _verify_record_capture(
    record: dict[str, Any], task: dict[str, Any]
) -> None:
    """Keep native measurements tied to the exact intended captured finder."""
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["lane"] != task["lane"]
        or record["capture"] != task["captures"][record["finder_id"]]
    ):
        raise ValueError("replacement record capture or schema changed")
