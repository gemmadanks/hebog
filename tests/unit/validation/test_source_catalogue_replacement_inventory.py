"""Preparation retains exact closed records, not old candidate measurements."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.external_runners import canonical_sha256

_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_ROOT))
inventory: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replacement_inventory"
)
evidence: Any = importlib.import_module(
    "scripts.validation.source_catalogue_campaign_evidence"
)
plan: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replay_plan"
)


def _fixture(
    tmp_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pairs: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    for lane in ("continuum", "compact-blend"):
        captures: dict[str, dict[str, str]] = {}
        entries: list[dict[str, str]] = []
        for finder in sorted(inventory.expected_finders(lane)):
            path = tmp_path / f"{lane}-{finder}.json"
            capture = {
                "path": str(path.with_suffix(".capture")),
                "sha256": "c" * 64,
            }
            captures[finder] = capture
            record = {
                "schema_version": 1,
                "input_id": lane,
                "lane": lane,
                "finder_id": finder,
                "capture": capture,
            }
            record["record_sha256"] = canonical_sha256(record)
            evidence.retain_image_record(path, record)
            entries.append(plan.binding(path))
        pairs.append(
            {
                "input_id": lane,
                "lane": lane,
                "dataset_identifier": "fixture",
                "seed": 1,
                "recipe_sha256": "a" * 64,
                "input_manifest": {},
                "captures": captures,
                "historical_task": {"never-execute": True},
                "evaluation_directory": "old",
            }
        )
        images.append({"input_id": lane, "records": entries})
    return pairs, images


@pytest.mark.parametrize(
    "defect",
    (None, "image", "pair", "capture", "record", "schema", "lane", "finders"),
)
def test_inventory_rejects_any_closed_census_or_capture_drift(
    tmp_path: Path, defect: str | None
) -> None:
    pairs, images = _fixture(tmp_path)
    if defect == "image":
        images.append(images[0])
    elif defect == "pair":
        pairs.append(pairs[0])
    elif defect == "capture":
        pairs[0]["captures"]["released-pybdsf"] = {}
    elif defect == "record":
        images[0]["records"].pop()
    elif defect == "finders":
        pairs[0]["captures"].pop("current-hebog")
    elif defect in ("schema", "lane"):
        entry = images[0]["records"][0]
        path = Path(entry["path"])
        record = json.loads(path.read_bytes())
        record["schema_version" if defect == "schema" else "lane"] = (
            True if defect == "schema" else "compact-blend"
        )
        record.pop("record_sha256")
        record["record_sha256"] = canonical_sha256(record)
        path.write_text(json.dumps(record))
        images[0]["records"][0] = plan.binding(path)
    if defect:
        with pytest.raises(ValueError):
            inventory.retained_inventory(pairs, images)
    else:
        retained = inventory.retained_inventory(pairs, images)
        assert len(retained) == 7
        assert all(row["finder_id"] != "current-hebog" for row in retained)
        assert retained == sorted(
            retained, key=lambda row: (row["input_id"], row["finder_id"])
        )
        assert all(
            plan.binding(Path(row["path"]))["sha256"] == row["sha256"]
            for row in retained
        )


def test_new_tasks_drop_old_current_and_incumbent_execution(
    tmp_path: Path,
) -> None:
    pairs, _ = _fixture(tmp_path)
    tasks = inventory.replacement_tasks(
        pairs,
        root=_ROOT,
        scratch=tmp_path / "new",
        configuration={"profile": "continuum"},
    )
    assert len(tasks) == 2
    assert not (tmp_path / "new").exists()
    for old, new in zip(
        sorted(pairs, key=lambda row: row["input_id"]), tasks, strict=True
    ):
        assert "historical_task" not in new
        assert "evaluation_directory" not in new
        assert "current-hebog" not in new["captures"]
        assert (
            new["captures"]["incumbent-hebog"]
            == old["captures"]["incumbent-hebog"]
        )
        assert new["recipe_sha256"] == old["recipe_sha256"]
        assert new["configuration"] == {"profile": "continuum"}
        assert (
            Path(new["output_directory"])
            == tmp_path / "new/pairs" / old["input_id"]
        )
    assert all("current-hebog" in row["captures"] for row in pairs)
