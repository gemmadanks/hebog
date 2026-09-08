"""Real spawned-process smoke for the evaluation-only continuation boundary."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportPrivateUsage=false

from __future__ import annotations

import importlib
import json
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_ROOT))
_FIXTURE_PATH = (
    _ROOT
    / "tests/unit/validation/test_source_catalogue_evaluation_continuation.py"
)


def _publish_fixture_evaluation(task: dict[str, Any]) -> dict[str, Any]:
    """Publish synthetic records through the actual spawned-worker seam."""
    helpers = runpy.run_path(str(_FIXTURE_PATH))
    return helpers["_complete"](task, schema=2)


@pytest.mark.integration
def test_two_spawned_evaluations_combine_with_unchanged_retained_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helpers = runpy.run_path(str(_FIXTURE_PATH))
    plan, inventory = helpers["_fixture"](tmp_path)
    runner: Any = importlib.import_module(
        "scripts.validation.continue_source_catalogue_evaluation"
    )

    def fixture_code_identity(_plan: Any) -> None:
        """Synthetic fixture admission substitutes no scientific code."""

    monkeypatch.setattr(runner, "verify_execution_code", fixture_code_identity)
    monkeypatch.setattr(
        runner, "evaluate_missing_pair", _publish_fixture_evaluation
    )

    def aggregate(_plan: Any, _pairs: Any, evaluated: Any, _dask: Any) -> Any:
        assert len(evaluated) == 3
        assert evaluated[0] == inventory["completed_evaluations"][0]
        return {"status": "fixture-only"}

    monkeypatch.setattr(runner, "aggregate_records", aggregate)
    terminal = runner.run_continuation(plan, {"fixture": True})
    assert terminal["new_input_evaluations"] == 2
    assert terminal["reused_input_evaluations"] == 1
    seal = json.loads(
        (Path(plan["scratch"]) / "evaluation-seal.json").read_bytes()
    )
    assert len(seal["complete_markers"]) == 3
    assert (
        "completed=2/2" in (Path(plan["scratch"]) / "progress.log").read_text()
    )
