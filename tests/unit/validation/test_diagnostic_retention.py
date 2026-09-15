"""Checksum verification and write-once JSON for retained records."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hebog.validation.diagnostic_retention import (
    verify_record_digest,
    write_json_once,
)
from hebog.validation.external_runners import canonical_sha256


def _record() -> dict[str, object]:
    payload: dict[str, object] = {"input_id": "case", "values": [1.0, 2.0]}
    return {**payload, "record_sha256": canonical_sha256(payload)}


def test_record_digest_accepts_unchanged_and_rejects_changed_payload() -> None:
    """A retained record cannot be edited without changing its digest."""
    record = _record()
    verify_record_digest(record)

    with pytest.raises(ValueError, match="digest changed"):
        verify_record_digest({**record, "values": [1.0, 3.0]})
    with pytest.raises(ValueError, match="digest changed"):
        verify_record_digest({key: record[key] for key in ("input_id",)})


def test_json_is_published_once_without_leaving_temporary_files(
    tmp_path: Path,
) -> None:
    """Publication is complete, canonical and never replaces a record."""
    path = tmp_path / "nested" / "capture.json"
    record = _record()

    write_json_once(path, record)

    assert json.loads(path.read_text(encoding="utf-8")) == record
    assert path.read_text(encoding="utf-8").endswith("\n")
    with pytest.raises(FileExistsError):
        write_json_once(path, {"replacement": True})
    assert json.loads(path.read_text(encoding="utf-8")) == record
    assert sorted(item.name for item in path.parent.iterdir()) == [
        "capture.json"
    ]
