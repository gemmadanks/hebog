"""Write-once R6 orchestration checks without campaign directories."""

# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_ROOT))


def test_pair_failure_preserves_current_capture_without_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution: Any = importlib.import_module(
        "scripts.validation.source_catalogue_campaign_execution"
    )
    image = tmp_path / "image.fits"
    image.write_bytes(b"fixture")
    task = {
        "input_id": "fixture",
        "output_directory": str(tmp_path / "pair"),
        "input_manifest": {"path": str(image), "sha256": file_sha256(image)},
        "configuration": {
            "detection_threshold_sigma": 5.0,
            "island_threshold_sigma": 3.0,
            "minimum_island_pixels": 7,
        },
        "historical_task": {},
        "root": str(_ROOT),
        "captures": {},
    }
    monkeypatch.setattr(
        execution, "native_artifacts", lambda *_args: {"image": image}
    )

    def capture(_input: Path, output: Path, **_kwargs: Any) -> None:
        output.mkdir(parents=True)
        (output / "capture.json").write_text('{"preserved": true}\n')

    def fail(*_args: Any) -> None:
        raise RuntimeError("injected incumbent process failure")

    monkeypatch.setattr(execution, "capture_current_image", capture)
    monkeypatch.setattr(execution, "execute_incumbent", fail)
    with pytest.raises(RuntimeError, match="injected incumbent"):
        execution.capture_pair(task)
    assert (
        tmp_path / "pair/current/capture.json"
    ).read_text() == '{"preserved": true}\n'
    assert not (tmp_path / "pair/pair.json").exists()
    with pytest.raises(FileExistsError):
        execution.capture_pair(task)


def test_evaluation_retains_each_complete_image_before_aggregation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution: Any = importlib.import_module(
        "scripts.validation.source_catalogue_campaign_execution"
    )
    evidence: Any = importlib.import_module(
        "scripts.validation.source_catalogue_campaign_evidence"
    )
    fixture = {
        "input_id": "fixture",
        "finder_id": "current-hebog",
        "lane": "continuum",
    }
    fixture["record_sha256"] = evidence.canonical_sha256(fixture)
    monkeypatch.setattr(
        execution, "evaluate_captured_input", lambda *_args: (fixture,)
    )
    task = {
        "input_id": "fixture",
        "root": str(_ROOT),
        "evaluation_directory": str(tmp_path / "records"),
    }
    result = execution.evaluate_pair(task)
    assert len(result["records"]) == 1
    path = Path(result["records"][0]["path"])
    assert json.loads(path.read_bytes()) == fixture
    assert result["records"][0]["sha256"] == file_sha256(path)
    with pytest.raises(FileExistsError):
        execution.evaluate_pair(task)


@pytest.mark.parametrize("failure", (None, "process", "identity"))
def test_historical_process_uses_exact_isolated_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None,
) -> None:
    execution: Any = importlib.import_module(
        "scripts.validation.source_catalogue_campaign_execution"
    )
    historical = tmp_path / "historical"
    historical.mkdir()
    task = {
        "historical_root": str(historical),
        "input_id": "fixture",
        "dataset_identifier": "fixture-dataset",
        "configuration_sha256": "a" * 64,
        "source_tree_sha256": "b" * 64,
    }
    monkeypatch.setattr(
        execution,
        "evaluation_context",
        lambda _root: {
            "datasets": {
                "fixture-dataset": SimpleNamespace(
                    model_dump=lambda **_kw: {"fixture": True}
                )
            },
        },
    )

    def run(command: tuple[str, ...], **kwargs: Any) -> None:
        assert kwargs["cwd"] == str(historical)
        assert kwargs["env"]["PYTHONPATH"] == str(historical / "src")
        assert kwargs["env"]["NUMBA_NUM_THREADS"] == "1"
        assert kwargs["check"] is True
        payload = json.loads(Path(command[-1]).read_bytes())
        assert payload["dataset"] == {"fixture": True}
        assert "dataset_identifier" not in payload
        if failure == "process":
            raise subprocess.CalledProcessError(1, command)
        output = Path(payload["output_directory"])
        output.mkdir()
        marker = {
            key: payload[key]
            for key in (
                "input_id",
                "configuration_sha256",
                "source_tree_sha256",
            )
        }
        marker["artifacts"] = []
        if failure == "identity":
            marker["source_tree_sha256"] = "c" * 64
        (output / "complete.json").write_text(json.dumps(marker))

    monkeypatch.setattr(execution.subprocess, "run", run)
    if failure is not None:
        with pytest.raises((subprocess.CalledProcessError, ValueError)):
            execution.execute_incumbent(task, _ROOT, tmp_path)
    else:
        assert (
            execution.execute_incumbent(task, _ROOT, tmp_path)
            == tmp_path / "incumbent/complete.json"
        )
    assert (tmp_path / "incumbent-task.json").is_file()
    assert (tmp_path / "incumbent-process.log").is_file()


def test_complete_pair_seals_both_native_captures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution: Any = importlib.import_module(
        "scripts.validation.source_catalogue_campaign_execution"
    )
    input_path = tmp_path / "input.json"
    input_path.write_text("{}\n")
    monkeypatch.setattr(
        execution, "native_artifacts", lambda *_args: {"image": input_path}
    )

    def capture(_input: Path, output: Path, **_kw: Any) -> None:
        output.mkdir()
        (output / "capture.json").write_text("{}\n")

    def incumbent(_task: Any, _root: Path, directory: Path) -> Path:
        path = directory / "incumbent.json"
        path.write_text("{}\n")
        return path

    monkeypatch.setattr(execution, "capture_current_image", capture)
    monkeypatch.setattr(execution, "execute_incumbent", incumbent)
    result = execution.capture_pair(
        {
            "root": str(_ROOT),
            "input_id": "fixture",
            "output_directory": str(tmp_path / "pair"),
            "input_manifest": {
                "path": str(input_path),
                "sha256": file_sha256(input_path),
            },
            "configuration": {
                "detection_threshold_sigma": 5.0,
                "island_threshold_sigma": 3.0,
                "minimum_island_pixels": 7,
            },
            "historical_task": {},
            "captures": {"released-pybdsf": {"preserved": True}},
        }
    )
    pair = json.loads(Path(result["path"]).read_bytes())
    assert pair["captures"]["released-pybdsf"] == {"preserved": True}
    assert set(pair["captures"]) == {
        "released-pybdsf",
        "current-hebog",
        "incumbent-hebog",
    }
    assert file_sha256(Path(result["path"])) == result["sha256"]
