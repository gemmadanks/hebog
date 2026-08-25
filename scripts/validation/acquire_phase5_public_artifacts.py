#!/usr/bin/env python3
"""Acquire and hash the approved Phase 5 public evidence artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
_DECISION_PATH = (
    _ROOT
    / "config/contracts/phase-5-public-comparison-scientific-decision.json"
)
_DECISION_SHA256 = (
    "7bfd3866240d4300bf53758ef5b8cc1342620fa63447862feb2e112a109f2b45"
)
_PRE_REVIEW_SHA256 = (
    "ad412c20e312173861364ef053f08eb700615ad27e11cce26fe088d8e7b03425"
)
_EXPECTED_TOTAL_BYTES = 15_053_995_875
_EXPECTED_ARTIFACT_COUNT = 7
_FREE_HEADROOM_BYTES = 10 * 1024**3
_SEGMENTED_DOWNLOAD_THRESHOLD_BYTES = 1024**3
_SEGMENT_COUNT = 8


@dataclass(frozen=True, slots=True)
class AcquisitionRequest:
    """One exact approved public artifact request."""

    dataset_id: str
    identifier: str
    filename: str
    source_url: str
    expected_bytes: int


def load_acquisition_decision(
    repository_root: Path,
    decision_path: Path,
) -> tuple[dict[str, Any], tuple[AcquisitionRequest, ...]]:
    """Load the exact named acquisition decision and fixed requests."""
    if file_sha256(decision_path) != _DECISION_SHA256:
        raise ValueError("approved public scientific decision changed")
    decision = cast(
        dict[str, Any], json.loads(decision_path.read_text(encoding="utf-8"))
    )
    pre_review = repository_root / cast(
        str, decision.get("pre_review_contract_path")
    )
    requests = tuple(
        AcquisitionRequest(
            dataset_id=item["dataset_id"],
            identifier=item["identifier"],
            filename=item["filename"],
            source_url=item["source_url"],
            expected_bytes=item["expected_bytes"],
        )
        for item in cast(
            list[dict[str, Any]], decision.get("artifact_requests")
        )
    )
    if (
        decision.get("schema_version") != 1
        or decision.get("decision_id")
        != "phase-5-public-comparison-scientific-decision"
        or decision.get("status")
        != "scientifically-approved-for-acquisition-before-output"
        or decision.get("pre_review_contract_sha256") != _PRE_REVIEW_SHA256
        or file_sha256(pre_review) != _PRE_REVIEW_SHA256
        or decision.get("acquisition_authorized") is not True
        or decision.get("artifact_checksums_frozen") is not False
        or decision.get("cutout_selection_authorized") is not False
        or decision.get("execution_authorized") is not False
        or decision.get("qualification_opened") is not False
        or decision.get("scientific_products_opened") is not False
        or len(requests) != _EXPECTED_ARTIFACT_COUNT
        or sum(request.expected_bytes for request in requests)
        != _EXPECTED_TOTAL_BYTES
    ):
        raise ValueError("approved public acquisition decision is invalid")
    identities = tuple(
        (request.dataset_id, request.identifier) for request in requests
    )
    if tuple(sorted(set(identities))) != identities:
        raise ValueError(
            "public artifact requests must be canonical and unique"
        )
    for request in requests:
        if (
            request.expected_bytes <= 0
            or Path(request.filename).name != request.filename
            or not request.source_url.startswith("https://")
        ):
            raise ValueError("public artifact request is unsafe")
    return decision, requests


def inspect_acquired_artifacts(
    requests: tuple[AcquisitionRequest, ...],
    raw_directory: Path,
) -> list[dict[str, object]]:
    """Hash only complete, exact-size public artifacts."""
    records: list[dict[str, object]] = []
    for request in requests:
        path = raw_directory / request.filename
        if not path.is_file():
            raise FileNotFoundError(f"public artifact is absent: {path}")
        byte_size = path.stat().st_size
        if byte_size != request.expected_bytes:
            raise ValueError(
                f"public artifact byte size differs: {request.filename}"
            )
        records.append(
            {
                "dataset_id": request.dataset_id,
                "identifier": request.identifier,
                "filename": request.filename,
                "byte_size": byte_size,
                "sha256": file_sha256(path),
                "source_url": request.source_url,
            }
        )
    return records


def segment_bounds(
    byte_size: int,
    *,
    segment_count: int,
) -> tuple[tuple[int, int], ...]:
    """Partition a byte range into complete, disjoint inclusive segments."""
    if byte_size < 1 or segment_count < 1:
        raise ValueError("byte size and segment count must be positive")
    count = min(byte_size, segment_count)
    base, remainder = divmod(byte_size, count)
    start = 0
    bounds: list[tuple[int, int]] = []
    for index in range(count):
        length = base + (1 if index < remainder else 0)
        end = start + length - 1
        bounds.append((start, end))
        start = end + 1
    return tuple(bounds)


def _download_range(
    request: AcquisitionRequest,
    segment_path: Path,
    byte_bounds: tuple[int, int],
) -> None:
    """Download and verify one fixed inclusive byte range."""
    start, end = byte_bounds
    expected_bytes = end - start + 1
    if segment_path.exists() and segment_path.stat().st_size == expected_bytes:
        return
    subprocess.run(
        (
            "curl",
            "--fail",
            "--location",
            "--retry",
            "3",
            "--retry-all-errors",
            "--silent",
            "--show-error",
            "--range",
            f"{start}-{end}",
            "--max-filesize",
            str(expected_bytes),
            "--output",
            str(segment_path),
            request.source_url,
        ),
        check=True,
    )
    if segment_path.stat().st_size != expected_bytes:
        raise ValueError(
            f"public artifact range size differs: {request.filename}"
        )


def _download_segmented(
    request: AcquisitionRequest,
    raw_directory: Path,
) -> None:
    """Download a large range-capable artifact with bounded concurrency."""
    destination = raw_directory / request.filename
    bounds = segment_bounds(
        request.expected_bytes,
        segment_count=_SEGMENT_COUNT,
    )
    segment_paths = tuple(
        destination.with_name(f"{destination.name}.part.{index:02d}")
        for index in range(len(bounds))
    )
    with ThreadPoolExecutor(max_workers=len(bounds)) as executor:
        futures = tuple(
            executor.submit(_download_range, request, path, byte_bounds)
            for path, byte_bounds in zip(segment_paths, bounds, strict=True)
        )
        for future in futures:
            future.result()
    assembled = destination.with_name(destination.name + ".assembled")
    with assembled.open("wb") as output:
        for segment_path in segment_paths:
            with segment_path.open("rb") as segment:
                shutil.copyfileobj(segment, output, length=1024 * 1024)
    if assembled.stat().st_size != request.expected_bytes:
        raise ValueError(
            f"assembled public artifact byte size differs: {request.filename}"
        )
    assembled.replace(destination)
    for segment_path in segment_paths:
        segment_path.unlink()
    destination.with_name(destination.name + ".part").unlink(missing_ok=True)


def _download_artifact(
    request: AcquisitionRequest,
    raw_directory: Path,
) -> None:
    """Download one fixed URL resumably, then publish only its exact size."""
    destination = raw_directory / request.filename
    if destination.exists():
        if destination.stat().st_size != request.expected_bytes:
            raise ValueError(
                "existing public artifact byte size differs: "
                f"{request.filename}"
            )
        return
    if request.expected_bytes >= _SEGMENTED_DOWNLOAD_THRESHOLD_BYTES:
        _download_segmented(request, raw_directory)
        return
    partial = destination.with_name(destination.name + ".part")
    subprocess.run(
        (
            "curl",
            "--fail",
            "--location",
            "--retry",
            "3",
            "--retry-all-errors",
            "--continue-at",
            "-",
            "--output",
            str(partial),
            request.source_url,
        ),
        check=True,
    )
    if partial.stat().st_size != request.expected_bytes:
        raise ValueError(
            f"downloaded public artifact byte size differs: {request.filename}"
        )
    partial.replace(destination)


def _json_bytes(document: object) -> bytes:
    """Serialize one finite terminal record canonically."""
    return (
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def build_acquisition_record(
    *,
    repository_root: Path,
    decision_path: Path,
    raw_directory: Path,
) -> dict[str, object]:
    """Build the terminal checksum record without opening science."""
    _decision, requests = load_acquisition_decision(
        repository_root,
        decision_path,
    )
    records = inspect_acquired_artifacts(requests, raw_directory)
    return {
        "schema_version": 1,
        "acquisition_id": "phase-5-public-comparison-acquisition",
        "status": "complete-and-checksummed-before-science-inspection",
        "scientific_decision_path": decision_path.relative_to(
            repository_root
        ).as_posix(),
        "scientific_decision_sha256": _DECISION_SHA256,
        "artifact_count": len(records),
        "total_bytes": sum(cast(int, item["byte_size"]) for item in records),
        "artifacts": records,
        "schema_inspection_authorized": True,
        "cutout_selection_authorized": False,
        "finder_execution_authorized": False,
        "qualification_opened": False,
        "scientific_products_opened": False,
        "next_action": (
            "inspect-only-schema-units-and-archive-layout-then-freeze-exact-"
            "adapters-and-sdc1-selection-formulas-before-cutout-generation"
        ),
    }


def _parse_args() -> argparse.Namespace:
    """Parse fixed decision and ignored evidence locations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", type=Path, default=_DECISION_PATH)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=(
            _ROOT / "benchmark-results/phase-5/public-comparison-acquisition"
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Acquire all public artifacts and publish one checksum record."""
    arguments = _parse_args()
    raw_directory = arguments.output_directory / "raw"
    acquisition_path = arguments.output_directory / "acquisition.json"
    if acquisition_path.exists():
        raise FileExistsError(
            f"refusing to replace public acquisition: {acquisition_path}"
        )
    _decision, requests = load_acquisition_decision(_ROOT, arguments.decision)
    raw_directory.mkdir(parents=True, exist_ok=True)
    missing_bytes = sum(
        request.expected_bytes
        for request in requests
        if not (raw_directory / request.filename).exists()
    )
    segmented_working_bytes = max(
        (
            request.expected_bytes
            for request in requests
            if request.expected_bytes >= _SEGMENTED_DOWNLOAD_THRESHOLD_BYTES
            and not (raw_directory / request.filename).exists()
        ),
        default=0,
    )
    if shutil.disk_usage(raw_directory).free < (
        missing_bytes + segmented_working_bytes + _FREE_HEADROOM_BYTES
    ):
        raise OSError(
            "insufficient disk space for public artifact acquisition"
        )
    for request in sorted(requests, key=lambda item: item.expected_bytes):
        _download_artifact(request, raw_directory)
    record = build_acquisition_record(
        repository_root=_ROOT,
        decision_path=arguments.decision,
        raw_directory=raw_directory,
    )
    arguments.output_directory.mkdir(parents=True, exist_ok=True)
    with acquisition_path.open("xb") as output:
        output.write(_json_bytes(record))


if __name__ == "__main__":
    main()
