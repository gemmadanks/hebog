"""Checksum verification and atomic write-once JSON for retained records."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from hebog.validation.external_runners import canonical_sha256


def verify_record_digest(record: dict[str, Any]) -> None:
    """Validate the record before any persistent namespace is created."""
    payload = {
        key: value for key, value in record.items() if key != "record_sha256"
    }
    if record.get("record_sha256") != canonical_sha256(payload):
        raise ValueError("retained diagnostic record digest changed")


def write_json_once(path: Path, record: dict[str, Any]) -> None:
    """Publish standard JSON with an atomic same-filesystem no-replace link."""
    payload = (
        json.dumps(
            record, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    # The context below is inside cleanup's try, so write failures also close.
    handle = NamedTemporaryFile(  # noqa: SIM115
        dir=path.parent, prefix=".diagnostic-", delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # Close before publication and unlink: Windows locks open files.
        os.link(temporary, path)
    finally:
        temporary.unlink()
