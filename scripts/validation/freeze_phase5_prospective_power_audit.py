#!/usr/bin/env python3
"""Freeze the endpoint-complete Phase 5 prospective power audit."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import cast
from uuid import uuid4

from hebog.validation.external_runners import file_sha256
from hebog.validation.prospective_science_contract import (
    load_prospective_endpoint_registry,
)
from hebog.validation.prospective_science_power import (
    build_prospective_power_audit,
)

_REGISTRY = (
    "config/contracts/phase-5-prospective-science-endpoint-registry.json"
)
_PROTOCOL = "config/contracts/phase-5-external-comparison.json"


def _object(path: Path, *, label: str) -> dict[str, object]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is malformed")
    return cast(dict[str, object], value)


def _publish(path: Path, record: dict[str, object]) -> None:
    """Atomically publish one finite write-once record."""
    payload = (
        json.dumps(record, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        descriptor = os.open(
            temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    """Verify the smoke result and freeze the exact full-replay design."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--smoke", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    root = arguments.repository_root.resolve()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite power audit: {arguments.output}"
        )
    registry_path = root / _REGISTRY
    protocol_path = root / _PROTOCOL
    smoke = _object(arguments.smoke, label="prospective smoke record")
    record = build_prospective_power_audit(
        registry=load_prospective_endpoint_registry(registry_path),
        external_protocol=_object(
            protocol_path, label="external comparison protocol"
        ),
        smoke_record=smoke,
    )
    record.update(
        {
            "endpoint_registry_sha256": file_sha256(registry_path),
            "external_protocol_sha256": file_sha256(protocol_path),
            "smoke_record_sha256": file_sha256(arguments.smoke),
        }
    )
    if record["status"] != "pass":
        raise ValueError("prospective full replay is not adequately powered")
    _publish(arguments.output, record)
    print(arguments.output)
    print(f"status={record['status']}")


if __name__ == "__main__":
    main()
