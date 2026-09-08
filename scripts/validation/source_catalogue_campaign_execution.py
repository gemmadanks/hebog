"""Importable, bounded R6 workers with durable capture/evaluation boundaries.

The command-line owner supplies the process and scheduler budget. Importing
this module neither inspects a campaign nor creates workers.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.validation.source_catalogue_campaign_evidence import (
    retain_image_record,
)
from scripts.validation.source_catalogue_campaign_worker import (
    capture_current_image,
)
from scripts.validation.source_catalogue_input_evaluation import (
    evaluate_captured_input,
    evaluation_context,
    native_artifacts,
)

from hebog.config import SourceFinderConfig
from hebog.executors import SerialExecutor
from hebog.validation.diagnostic_retention import _atomic_json
from hebog.validation.external_runners import file_sha256


def execute_incumbent(
    task: dict[str, Any],
    root: Path,
    directory: Path,
) -> Path:
    """Run the exact historical producer with isolated historical imports."""
    payload = {
        **{
            key: value
            for key, value in task.items()
            if key != "dataset_identifier"
        },
        "dataset": evaluation_context(root)["datasets"][
            task["dataset_identifier"]
        ].model_dump(mode="json"),
        "output_directory": str(directory / "incumbent"),
    }
    task_path = directory / "incumbent-task.json"
    _atomic_json(task_path, payload)
    script = (
        root
        / "scripts/validation"
        / "reconstruct_phase5_prospective_paired_incumbent.py"
    )
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(task["historical_root"]) / "src"),
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMBA_NUM_THREADS": "1",
    }
    command = (
        sys.executable,
        "-c",
        "import json,runpy,sys; "
        "worker=runpy.run_path(sys.argv[1]); "
        "worker['_generate_product'](json.load(open(sys.argv[2])))",
        str(script),
        str(task_path),
    )
    with (directory / "incumbent-process.log").open("xb") as stream:
        subprocess.run(
            command,
            cwd=task["historical_root"],
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=True,
        )
    marker = directory / "incumbent/complete.json"
    record = json.loads(marker.read_bytes())
    if any(
        record[key] != payload[key]
        for key in (
            "input_id",
            "configuration_sha256",
            "source_tree_sha256",
        )
    ):
        raise ValueError("incumbent product identity changed")
    native_artifacts(marker, file_sha256(marker))
    return marker


def capture_current_task(task: dict[str, Any]) -> dict[str, str]:
    """Expose the actual public capture through an importable process seam."""
    directory = Path(task["output_directory"])
    binding = task["input_manifest"]
    inputs = native_artifacts(Path(binding["path"]), binding["sha256"])
    capture_current_image(
        inputs["image"],
        directory,
        input_id=task["input_id"],
        config=SourceFinderConfig(**task["configuration"]),
        executor=SerialExecutor(),
    )
    current = directory / "capture.json"
    return {"path": str(current), "sha256": file_sha256(current)}


def capture_pair(task: dict[str, Any]) -> dict[str, Any]:
    """Capture current science first; preserve it if the incumbent fails."""
    directory = Path(task["output_directory"])
    directory.mkdir(parents=True, exist_ok=False)
    current = capture_current_task(
        {**task, "output_directory": str(directory / "current")}
    )
    incumbent = execute_incumbent(
        task["historical_task"], Path(task["root"]), directory
    )
    captured = {
        **task,
        "evaluation_directory": str(directory / "evaluation"),
        "captures": {
            **task["captures"],
            "current-hebog": current,
            "incumbent-hebog": {
                "path": str(incumbent),
                "sha256": file_sha256(incumbent),
            },
        },
    }
    _atomic_json(directory / "pair.json", captured)
    return {
        "path": str(directory / "pair.json"),
        "sha256": file_sha256(directory / "pair.json"),
    }


def evaluate_pair(task: dict[str, Any]) -> dict[str, Any]:
    """Persist complete array-free observations before late statistics."""
    output = Path(task["evaluation_directory"])
    output.mkdir(parents=True, exist_ok=False)
    records = evaluate_captured_input(task, Path(task["root"]))
    entries: list[dict[str, str]] = []
    for record in records:
        path = output / f"{record['finder_id']}.json"
        digest = retain_image_record(path, record)
        entries.append({"path": str(path), "sha256": digest})
    completed = {"input_id": task["input_id"], "records": entries}
    _atomic_json(output / "complete.json", completed)
    return completed
