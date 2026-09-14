"""Write-once, checksum-verified retention of bounded campaign diagnostics."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, cast

from hebog.validation.external_runners import canonical_sha256, file_sha256

DiagnosticKey = tuple[str, str]


def _record_key(record: dict[str, Any]) -> DiagnosticKey:
    """Require an explicit input/finder pair, independent of a filename."""
    key = record.get("input_id"), record.get("finder_id")
    if not all(isinstance(value, str) and value for value in key):
        raise ValueError("retained diagnostic record identity is absent")
    return str(key[0]), str(key[1])


def _verify_record_digest(record: dict[str, Any]) -> None:
    """Validate the record before any persistent namespace is created."""
    payload = {
        key: value for key, value in record.items() if key != "record_sha256"
    }
    if record.get("record_sha256") != canonical_sha256(payload):
        raise ValueError("retained diagnostic record digest changed")


def _verify_dask_comparison(record: dict[str, Any]) -> str:
    """Bind a completed equivalence claim to both scientific payload hashes."""
    identifier = record.get("input_id")
    digests = record.get("serial_sha256"), record.get("dask_sha256")
    if (
        not isinstance(identifier, str)
        or not identifier
        or not all(
            isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
            for value in digests
        )
        or record.get("status")
        != ("pass" if digests[0] == digests[1] else "fail")
        or (
            "equal" in record
            and record["equal"] is not (digests[0] == digests[1])
        )
    ):
        raise ValueError("retained Dask comparison is absent or inconsistent")
    return identifier


def _atomic_json(path: Path, record: dict[str, Any]) -> None:
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


def _require_census(
    observed: tuple[Any, ...], expected: tuple[Any, ...]
) -> None:
    if len(set(expected)) != len(expected) or sorted(observed) != sorted(
        expected
    ):
        raise ValueError(
            "retained diagnostic census is incomplete or duplicated"
        )


def publish_diagnostic_packet(  # noqa: PLR0913
    directory: Path,
    records: tuple[dict[str, Any], ...],
    dask_comparisons: tuple[dict[str, Any], ...],
    *,
    expected_keys: tuple[DiagnosticKey, ...],
    expected_dask_ids: tuple[str, ...],
    provenance: dict[str, str],
) -> Path:
    """Publish every record and comparison before the atomic manifest."""
    _require_census(tuple(_record_key(row) for row in records), expected_keys)
    _require_census(
        tuple(_verify_dask_comparison(row) for row in dask_comparisons),
        expected_dask_ids,
    )
    for row in records:
        _verify_record_digest(row)
    # Reject arrays, non-finite observations and malformed payloads pre-write.
    json.dumps((records, dask_comparisons, provenance), allow_nan=False)
    directory.mkdir(parents=True, exist_ok=False)
    retained: list[dict[str, Any]] = []
    for row in sorted(records, key=_record_key):
        path = (
            directory
            / "records"
            / f"{canonical_sha256(_record_key(row))}.json"
        )
        _atomic_json(path, row)
        retained.append(
            {
                "input_id": row["input_id"],
                "finder_id": row["finder_id"],
                "path": path.relative_to(directory).as_posix(),
                "sha256": file_sha256(path),
            }
        )
    comparisons: list[dict[str, Any]] = []
    for row in sorted(dask_comparisons, key=lambda row: row["input_id"]):
        path = directory / "dask" / f"{canonical_sha256(row['input_id'])}.json"
        _atomic_json(path, row)
        comparisons.append(
            {
                "input_id": row["input_id"],
                "path": path.relative_to(directory).as_posix(),
                "sha256": file_sha256(path),
            }
        )
    manifest = directory / "manifest.json"
    _atomic_json(
        manifest,
        {
            "schema_version": 1,
            "status": "complete",
            "provenance": provenance,
            "record_count": len(records),
            "dask_comparison_count": len(comparisons),
            "expected_keys": sorted(expected_keys),
            "expected_dask_ids": sorted(expected_dask_ids),
            "records": retained,
            "dask_comparisons": comparisons,
        },
    )
    verify_diagnostic_packet(manifest, expected_sha256=file_sha256(manifest))
    return manifest


def _checked_json(path: Path, digest: str) -> dict[str, Any]:
    """Fail on absent, substituted or non-object evidence."""
    if path.is_symlink() or not path.is_file() or file_sha256(path) != digest:
        raise ValueError("retained diagnostic bytes are absent or changed")
    document: object = json.loads(path.read_bytes())
    if not isinstance(document, dict):
        raise ValueError("retained diagnostic must be a JSON object")
    return cast(dict[str, Any], document)


def _relative_path(root: Path, relative: str) -> Path:
    """Do not follow evidence pointers outside their durable packet."""
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("retained diagnostic path escapes its packet")
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("retained diagnostic path must not traverse symlinks")
    return path


def verify_diagnostic_packet(
    manifest_path: Path,
    *,
    expected_sha256: str,
) -> dict[str, Any]:
    """Verify the complete retained census and bytes, not only a digest."""
    manifest = _checked_json(manifest_path, expected_sha256)
    if (
        manifest.get("schema_version") != 1
        or manifest.get("status") != "complete"
    ):
        raise ValueError("retained diagnostic manifest is incomplete")
    keys: list[DiagnosticKey] = []
    for entry in manifest["records"]:
        path = _relative_path(manifest_path.parent, entry["path"])
        record = _checked_json(path, entry["sha256"])
        _verify_record_digest(record)
        key = _record_key(record)
        if key != _record_key(entry):
            raise ValueError("retained diagnostic record identity changed")
        keys.append(key)
    dask_ids: list[str] = []
    for entry in manifest["dask_comparisons"]:
        path = _relative_path(manifest_path.parent, entry["path"])
        record = _checked_json(path, entry["sha256"])
        _verify_dask_comparison(record)
        if record.get("input_id") != entry["input_id"]:
            raise ValueError("retained diagnostic Dask identity changed")
        dask_ids.append(entry["input_id"])
    _require_census(
        tuple(keys), tuple(tuple(key) for key in manifest["expected_keys"])
    )
    _require_census(tuple(dask_ids), tuple(manifest["expected_dask_ids"]))
    if manifest["record_count"] != len(keys) or manifest[
        "dask_comparison_count"
    ] != len(dask_ids):
        raise ValueError("retained diagnostic census count changed")
    return manifest


def require_retained_diagnostics(
    terminal_path: Path,
    *,
    terminal_sha256: str,
) -> None:
    """Refuse scratch cleanup unless the exact terminal's records survive."""
    terminal = _checked_json(terminal_path, terminal_sha256)
    pointer = terminal.get("diagnostic_packet")
    if not isinstance(pointer, dict):
        raise ValueError("retained diagnostic packet is absent from terminal")
    pointer = cast(dict[str, Any], pointer)
    verify_diagnostic_packet(
        _relative_path(terminal_path.parent, pointer["path"]),
        expected_sha256=pointer["sha256"],
    )


def publish_retained_terminal(  # noqa: PLR0913
    terminal_path: Path,
    decision: dict[str, Any],
    *,
    records: tuple[dict[str, Any], ...],
    dask_comparisons: tuple[dict[str, Any], ...],
    expected_keys: tuple[DiagnosticKey, ...],
    expected_dask_ids: tuple[str, ...],
    provenance: dict[str, str],
) -> None:
    """Retain the exact evidence before publishing one final decision."""
    if terminal_path.exists() or terminal_path.is_symlink():
        raise FileExistsError(
            f"terminal output already exists: {terminal_path}"
        )
    if "diagnostic_packet" in decision or "provenance" in decision:
        raise ValueError(
            "terminal evidence fields must be assigned at publication"
        )
    json.dumps(decision, allow_nan=False)
    manifest = publish_diagnostic_packet(
        terminal_path.with_suffix(".diagnostics"),
        records,
        dask_comparisons,
        expected_keys=expected_keys,
        expected_dask_ids=expected_dask_ids,
        provenance=provenance,
    )
    _atomic_json(
        terminal_path,
        {
            **decision,
            "provenance": provenance,
            "diagnostic_packet": {
                "path": manifest.relative_to(terminal_path.parent).as_posix(),
                "sha256": file_sha256(manifest),
            },
        },
    )
    require_retained_diagnostics(
        terminal_path, terminal_sha256=file_sha256(terminal_path)
    )
