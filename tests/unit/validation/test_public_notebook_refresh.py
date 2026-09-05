"""Tests for the diagnostic public-notebook refresh runner."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

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
) -> None:
    """A refresh must not reconstruct an obsolete candidate identity."""
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

    _REFRESH["run_refresh"](
        repository_root=_ROOT,
        input_campaign_path=input_campaign,
        reference_campaign_path=reference_campaign,
        history_root=tmp_path / "history",
        label="test",
        resume=False,
        preflight_only=True,
    )

    preflight = json.loads(capsys.readouterr().out)
    expected = _PUBLIC_RUNNER["public_hebog_configuration_sha256"]()
    assert preflight["configuration_sha256"] == expected
    assert preflight["configuration_sha256"] == (
        "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
    )
    assert not (tmp_path / "history").exists()
