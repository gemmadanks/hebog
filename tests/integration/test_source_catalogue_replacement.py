"""Synthetic public capture, current-only truth evaluation and Dask smoke."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportPrivateUsage=false

from __future__ import annotations

import importlib
import io
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits

from hebog.config import SourceFinderConfig
from hebog.validation.adaptive_background_lane import (
    build_adaptive_development_manifest,
    source_signal_and_truth,
)
from hebog.validation.datasets import (
    generate_synthetic_image,
    iter_dataset_recipes,
    recipe_sha256,
)
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.materialization import synthetic_fits_header

_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_ROOT))
execution: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replacement_execution"
)
runner: Any = importlib.import_module(
    "scripts.validation.run_source_catalogue_cumulative_replay"
)
evaluator: Any = importlib.import_module(
    "scripts.validation.source_catalogue_input_evaluation"
)
evidence: Any = importlib.import_module(
    "scripts.validation.source_catalogue_campaign_evidence"
)
binding = importlib.import_module(
    "scripts.validation.source_catalogue_replay_plan"
).binding


@pytest.mark.integration
@pytest.mark.parametrize("lane", ("compact-blend", "continuum"))
def test_spawned_public_capture_current_only_evaluation_and_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lane: str
) -> None:
    dataset = build_adaptive_development_manifest().datasets[0]
    recipe = iter_dataset_recipes(dataset)[0]
    signal, _support, rms = source_signal_and_truth(recipe)
    image_paths: dict[str, Path] = {}
    for role, values in (
        ("image", generate_synthetic_image(recipe)),
        ("mean", np.full_like(signal, recipe.background)),
        ("rms", rms),
    ):
        path = tmp_path / f"{role}.fits"
        fits.PrimaryHDU(values, synthetic_fits_header(dataset)).writeto(path)
        image_paths[role] = path
    manifest = tmp_path / "input.json"
    manifest.write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "role": role,
                        "relative_path": path.name,
                        "sha256": file_sha256(path),
                        "byte_count": path.stat().st_size,
                    }
                    for role, path in image_paths.items()
                ]
            }
        )
    )
    tasks = [
        {
            "input_id": f"development-{index}",
            "lane": lane,
            "dataset_identifier": dataset.identifier,
            "seed": recipe.seed,
            "recipe_sha256": recipe_sha256(recipe),
            "root": str(_ROOT),
            "input_manifest": binding(manifest),
            "configuration": asdict(SourceFinderConfig(5.0, 3.0, 7)),
            "output_directory": str(tmp_path / f"capture-{index}"),
            "captures": {
                finder: {
                    "path": "unopened-fixture-reference",
                    "sha256": "a" * 64,
                }
                for finder in execution.expected_finders(lane)
                - {"current-hebog"}
            },
        }
        for index in range(2)
    ]
    progress = io.StringIO()
    outputs = runner._run_stage(
        "fixture-capture", tasks, execution.capture_replacement, progress
    )
    pairs = [json.loads(Path(row["path"]).read_bytes()) for row in outputs]
    assert len(pairs) == 2
    context = evaluator.evaluation_context(_ROOT)
    selected = {
        **context,
        "datasets": {dataset.identifier: dataset},
        "recipes": {(dataset.identifier, recipe.seed): recipe},
        # This one development geometry does not contain the full campaign
        # stratum vocabulary. Exercise every applicable overall family here;
        # the frozen campaign keeps its full 158-specification census.
        "specifications": tuple(
            spec
            for spec in context["specifications"]
            if spec.stratum == "overall"
        ),
    }

    def fixture_context(_root: Path) -> dict[str, Any]:
        return selected

    monkeypatch.setattr(evaluator, "evaluation_context", fixture_context)
    completed = [execution.evaluate_replacement(task) for task in pairs]
    retained = []
    for task, row in zip(pairs, completed, strict=True):
        current = json.loads(Path(row["records"][0]["path"]).read_bytes())
        assert current["finder_id"] == "current-hebog"
        assert current["lane"] == lane
        for finder in execution.expected_finders(lane) - {"current-hebog"}:
            # Synthetic comparator observations, never executed native tools.
            record = {
                **current,
                "finder_id": finder,
                "capture": task["captures"][finder],
            }
            record.pop("record_sha256")
            record["record_sha256"] = canonical_sha256(record)
            path = tmp_path / f"{task['input_id']}-{finder}.json"
            evidence.retain_image_record(path, record)
            retained.append(
                {
                    "input_id": task["input_id"],
                    "finder_id": finder,
                    **binding(path),
                }
            )
    combined = execution.combine_records(pairs, completed, retained)
    assert sum(len(row["records"]) for row in combined) == 2 * len(
        execution.expected_finders(lane)
    )
    plan = {
        "scratch": str(tmp_path),
        "configuration": tasks[0]["configuration"],
        "dask_input_ids": [row["input_id"] for row in tasks],
    }
    results = runner.compare_existing_dask(plan, pairs, progress)
    assert len(results) == 2 and all(row["pass"] for row in results)
    assert "completed=2/2" in progress.getvalue()


@pytest.mark.integration
def test_noiseless_public_capture_has_finite_scale_response(
    tmp_path: Path,
) -> None:
    """A noiseless source must not turn FFT roundoff into scale detections."""
    dataset = build_adaptive_development_manifest().datasets[0]
    recipe = iter_dataset_recipes(dataset)[0]
    signal, _, _ = source_signal_and_truth(recipe)
    path = tmp_path / "noiseless.fits"
    fits.PrimaryHDU(signal, synthetic_fits_header(dataset)).writeto(path)
    manifest = tmp_path / "input.json"
    manifest.write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "role": "image",
                        "relative_path": path.name,
                        "sha256": file_sha256(path),
                        "byte_count": path.stat().st_size,
                    }
                ]
            }
        )
    )
    task: dict[str, Any] = {
        "input_id": "noiseless-development",
        "lane": "continuum",
        "root": str(_ROOT),
        "input_manifest": binding(manifest),
        "configuration": asdict(SourceFinderConfig(5.0, 3.0, 7)),
        "output_directory": str(tmp_path / "capture"),
        "captures": {
            finder: {}
            for finder in execution.expected_finders("continuum")
            - {"current-hebog"}
        },
    }
    result = execution.capture_replacement(task)
    assert Path(result["path"]).is_file()
