"""Tests for the diagnostic public-notebook refresh runner."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).parents[3]
_REFRESH = runpy.run_path(
    str(_ROOT / "scripts/benchmark/refresh_public_notebook_hebog.py")
)
_PUBLIC_RUNNER = runpy.run_path(
    str(_ROOT / "scripts/benchmark/run_phase5_public_finder_hebog.py")
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_preflight_rejects_an_unbound_public_runner(
    tmp_path: Path,
    capsys: Any,
) -> None:
    """A refresh cannot start while repaired science remains unbound."""
    input_campaign = tmp_path / "input.json"
    reference_campaign = tmp_path / "reference.json"
    _write_json(
        input_campaign,
        {
            "scientific_claims_authorized": False,
            "results": [{"case_id": "case", "status": "success"}],
        },
    )
    _write_json(
        reference_campaign,
        {
            "scientific_claims_authorized": False,
            "results": [
                {"case_id": "case", "status": "success"},
                {"case_id": "case", "status": "success"},
            ],
        },
    )

    with pytest.raises(ValueError, match="public-interface identity changed"):
        _REFRESH["run_refresh"](
            repository_root=_ROOT,
            input_campaign_path=input_campaign,
            reference_campaign_path=reference_campaign,
            history_root=tmp_path / "history",
            label="test",
            resume=False,
            preflight_only=True,
        )

    assert capsys.readouterr().out == ""
    assert not (tmp_path / "history").exists()
