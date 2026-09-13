"""Portable publication and CLI contracts for historical record freezers."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[3]
_PROGRAMS = (
    "freeze_phase5_final_cumulative_evaluation.py",
    "freeze_phase5_public_owner_domain_cumulative_evaluation.py",
)


@pytest.mark.parametrize("program_name", _PROGRAMS)
def test_freezer_publishes_once_without_campaign_inputs(
    program_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real file publication is independent of historical record building."""
    program = runpy.run_path(str(_ROOT / "scripts/validation" / program_name))
    records = tuple(
        {"fixture": name}
        for name in ("implementation", "identity", "decision")
    )
    freeze = program["freeze_records"]

    def build_fixture_records(_root: Path) -> tuple[dict[str, str], ...]:
        return records

    monkeypatch.setitem(
        freeze.__globals__, "build_records", build_fixture_records
    )
    arguments = argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)

    freeze(arguments)

    paths = tuple(
        tmp_path / program[key]
        for key in ("_IMPLEMENTATION", "_IDENTITY", "_DECISION")
    )
    assert tuple(json.loads(path.read_text("utf-8")) for path in paths) == (
        records
    )
    original = tuple(path.read_bytes() for path in paths)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freeze(arguments)
    assert tuple(path.read_bytes() for path in paths) == original


@pytest.mark.parametrize("program_name", _PROGRAMS)
def test_freezer_cli_help_needs_no_evidence_or_import_path(
    program_name: str, tmp_path: Path
) -> None:
    """The direct CLI loads from a foreign cwd without campaign data."""
    result = subprocess.run(
        (
            sys.executable,
            str(_ROOT / "scripts/validation" / program_name),
            "--help",
        ),
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": ""},
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--output-root" in result.stdout
    assert list(tmp_path.iterdir()) == []
