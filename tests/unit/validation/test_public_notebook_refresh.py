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


def test_preflight_uses_the_public_runners_exact_configuration(
    tmp_path: Path,
    capsys: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refresh must not reconstruct an obsolete candidate identity."""
    input_campaign = tmp_path / "input.json"
    reference_campaign = tmp_path / "reference.json"
    runner_path = (
        tmp_path / "scripts/benchmark/run_phase5_public_finder_hebog.py"
    )
    runner_path.parent.mkdir(parents=True)
    expected = "e" * 64
    runner_path.write_text(
        "def public_hebog_configuration_sha256():\n"
        f"    return {expected!r}\n"
        "def run_public_hebog(**kwargs):\n"
        "    raise AssertionError('preflight must not execute a finder')\n",
        encoding="utf-8",
    )

    def git_identity(_root: Path) -> tuple[str, bool]:
        return "a" * 40, False

    monkeypatch.setitem(
        _REFRESH["run_refresh"].__globals__, "_git_identity", git_identity
    )
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

    _REFRESH["run_refresh"](
        repository_root=tmp_path,
        input_campaign_path=input_campaign,
        reference_campaign_path=reference_campaign,
        history_root=tmp_path / "history",
        label="test",
        resume=False,
        preflight_only=True,
    )

    preflight = json.loads(capsys.readouterr().out)
    assert preflight["configuration_sha256"] == expected
    assert not (tmp_path / "history").exists()
