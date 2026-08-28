#!/usr/bin/env python3
"""Refresh public Hebog products from the current source tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from hebog.data_models import ImageBounds
from hebog.validation.external_runners import source_tree_sha256
from hebog.validation.post_correction_recovery import (
    post_correction_candidate_configuration_sha256,
)

_REFERENCE_CAMPAIGN = Path(
    "benchmark-results/phase-5/public-reference-comparison"
)
_INPUT_CAMPAIGN = Path("benchmark-results/phase-5/public-finder-comparison")
_OUTPUT = Path("benchmark-results/phase-5/current-public-hebog-comparison")
_BASE_REVIEW = Path("config/contracts/phase-5-corrective-a-review.json")
_HEBOG_RUNNER = Path("scripts/benchmark/run_phase5_public_finder_hebog.py")
_RUNNER_REPOSITORY_PATH = Path(
    "scripts/benchmark/run_phase5_current_public_hebog_campaign.py"
)
_CORE_BOUNDS_LENGTH = 4
_PUBLIC_CASE_COUNT = 10
_REFERENCE_RESULT_COUNT = 20


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, Any], value)


def _write_once(path: Path, value: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite campaign state: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _append_progress(path: Path, message: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _resolve_input(
    repository_root: Path,
    input_campaign: Path,
    case_id: str,
) -> tuple[Path, ImageBounds | None, dict[str, Any]]:
    record_path = input_campaign / "inputs" / case_id / "input.json"
    record = _read_json(record_path)
    if record.get("case_id") != case_id:
        raise ValueError(f"input case identity changed: {case_id}")
    relative = Path(str(record.get("input_path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe input path for {case_id}")
    location = record.get("input_location")
    if location == "repository":
        input_path = repository_root / relative
    elif location == "staging":
        input_path = input_campaign / relative
    else:
        raise ValueError(f"unsupported input location for {case_id}")
    if not input_path.is_file():
        raise FileNotFoundError(f"missing input for {case_id}: {input_path}")
    if _file_sha256(input_path) != record.get("input_sha256"):
        raise ValueError(f"input checksum changed for {case_id}")
    raw_core = record.get("local_core_yx_half_open")
    if raw_core is None:
        core = None
    elif isinstance(raw_core, list) and len(raw_core) == _CORE_BOUNDS_LENGTH:
        core = ImageBounds(
            y_start=int(raw_core[0]),
            y_stop=int(raw_core[1]),
            x_start=int(raw_core[2]),
            x_stop=int(raw_core[3]),
        )
    else:
        raise ValueError(f"invalid core bounds for {case_id}")
    return input_path, core, record


def _preflight(
    *,
    repository_root: Path,
    output: Path,
    resume: bool,
) -> tuple[
    Path,
    dict[str, Any],
    str,
    str,
    tuple[dict[str, Any], ...],
]:
    expected_output = (repository_root / _OUTPUT).resolve()
    if output.resolve() != expected_output:
        raise ValueError(f"derived output must be {expected_output}")
    if output.exists():
        raise FileExistsError(f"derived campaign already exists: {output}")
    reference_root = repository_root / _REFERENCE_CAMPAIGN
    input_root = repository_root / _INPUT_CAMPAIGN
    reference = _read_json(reference_root / "campaign.json")
    if (
        reference.get("status") != "terminal-derived-results-sealed"
        or reference.get("case_count") != _PUBLIC_CASE_COUNT
        or len(cast(list[object], reference.get("results", [])))
        != _REFERENCE_RESULT_COUNT
        or reference.get("scientific_claims_authorized") is not False
        or reference.get("base_campaign_repository_path")
        != str(_INPUT_CAMPAIGN / "campaign.json")
    ):
        raise ValueError("reference campaign is not the sealed 20-result base")
    historical = _read_json(input_root / "campaign.json")
    raw_results = historical.get("results")
    if (
        historical.get("status") != "terminal-raw-results-sealed"
        or historical.get("case_count") != _PUBLIC_CASE_COUNT
        or historical.get("successful_case_count") != _PUBLIC_CASE_COUNT
        or not isinstance(raw_results, list)
        or len(raw_results) != _PUBLIC_CASE_COUNT
    ):
        raise ValueError("historical Hebog input campaign is not sealed")
    source_sha256 = source_tree_sha256(repository_root)
    configuration_sha256 = post_correction_candidate_configuration_sha256(
        repository_root / _BASE_REVIEW
    )
    staging = output.parent / (f".{output.name}.{source_sha256[:12]}.staging")
    active = sorted(
        path for path in output.parent.glob(".*.staging") if path != staging
    )
    if active:
        raise RuntimeError(
            "another campaign staging directory exists: "
            + ", ".join(str(path) for path in active)
        )
    if staging.exists() and not resume:
        raise FileExistsError(f"derived staging already exists: {staging}")
    results = tuple(cast(dict[str, Any], item) for item in raw_results)
    for item in results:
        case_id = str(item.get("case_id", ""))
        if item.get("status") != "success" or not case_id:
            raise ValueError("historical campaign result index changed")
        input_path, _, _ = _resolve_input(
            repository_root,
            input_root,
            case_id,
        )
        historical_result = _read_json(
            input_root / str(item.get("result_path", ""))
        )
        if (
            historical_result.get("status") != "success"
            or historical_result.get("configuration_sha256")
            != configuration_sha256
            or historical_result.get("input_sha256")
            != _file_sha256(input_path)
        ):
            raise ValueError(f"historical result binding changed: {case_id}")
    return (
        staging,
        reference,
        source_sha256,
        configuration_sha256,
        results,
    )


def run_campaign(
    *,
    repository_root: Path,
    output: Path,
    resume: bool,
    preflight_only: bool,
) -> None:
    (
        staging,
        _reference,
        source_sha256,
        configuration_sha256,
        cases,
    ) = _preflight(
        repository_root=repository_root,
        output=output,
        resume=resume,
    )
    if preflight_only:
        print(
            json.dumps(
                {
                    "case_count": len(cases),
                    "configuration_sha256": configuration_sha256,
                    "source_tree_sha256": source_sha256,
                    "status": "preflight-passed",
                },
                sort_keys=True,
            )
        )
        return
    staging.mkdir(parents=True, exist_ok=resume)
    runner_sha256 = _file_sha256(Path(__file__))
    request: dict[str, object] = {
        "schema_version": 1,
        "request_id": "phase-5-current-public-hebog-refresh",
        "status": "derived-current-worktree-staging",
        "base_campaign_repository_path": str(
            _REFERENCE_CAMPAIGN / "campaign.json"
        ),
        "base_campaign_sha256": _file_sha256(
            repository_root / _REFERENCE_CAMPAIGN / "campaign.json"
        ),
        "input_campaign_repository_path": str(
            _INPUT_CAMPAIGN / "campaign.json"
        ),
        "input_campaign_sha256": _file_sha256(
            repository_root / _INPUT_CAMPAIGN / "campaign.json"
        ),
        "source_tree_sha256": source_sha256,
        "configuration_sha256": configuration_sha256,
        "runner_repository_path": str(_RUNNER_REPOSITORY_PATH),
        "runner_sha256": runner_sha256,
        "case_count": len(cases),
        "scientific_claims_authorized": False,
    }
    request_path = staging / "request.json"
    if request_path.exists():
        if _read_json(request_path) != request:
            raise ValueError("derived campaign resume request changed")
    else:
        _write_once(request_path, request)
    runner = runpy.run_path(str(repository_root / _HEBOG_RUNNER))
    run_public_hebog = cast(
        Callable[..., dict[str, object]],
        runner["run_public_hebog"],
    )
    input_root = repository_root / _INPUT_CAMPAIGN
    progress_path = staging / "progress.log"
    terminal_results: list[dict[str, object]] = []
    for item in cases:
        case_id = str(item["case_id"])
        result_directory = (
            staging / "results" / case_id / "hebog" / "operational"
        )
        result_path = result_directory / "result.json"
        if result_path.exists():
            result = _read_json(result_path)
            if result.get("status") != "success":
                raise ValueError("resume found a failed current Hebog result")
        else:
            input_path, core, _ = _resolve_input(
                repository_root,
                input_root,
                case_id,
            )
            result = run_public_hebog(
                input_path=input_path,
                output=result_directory,
                case_id=case_id,
                core=core,
                configuration_sha256=configuration_sha256,
            )
            _append_progress(progress_path, f"completed {case_id}")
        terminal_results.append(
            {
                "case_id": case_id,
                "finder_id": "hebog",
                "mode": "operational",
                "result_path": str(result_path.relative_to(staging)),
                "result_sha256": _file_sha256(result_path),
                "status": result["status"],
            }
        )
    if source_tree_sha256(repository_root) != source_sha256:
        raise RuntimeError("Hebog source tree changed during refresh")
    terminal: dict[str, object] = {
        "schema_version": 1,
        "campaign_id": "phase-5-current-public-hebog-comparison",
        "status": "terminal-derived-results-sealed",
        "base_campaign_repository_path": request[
            "base_campaign_repository_path"
        ],
        "base_campaign_sha256": request["base_campaign_sha256"],
        "input_campaign_repository_path": request[
            "input_campaign_repository_path"
        ],
        "input_campaign_sha256": request["input_campaign_sha256"],
        "source_tree_sha256": source_sha256,
        "configuration_sha256": configuration_sha256,
        "runner_repository_path": request["runner_repository_path"],
        "runner_sha256": runner_sha256,
        "case_count": len(terminal_results),
        "successful_case_count": sum(
            item["status"] == "success" for item in terminal_results
        ),
        "results": terminal_results,
        "completed_at": datetime.now(UTC).isoformat(),
        "scientific_claims_authorized": False,
    }
    _write_once(staging / "campaign.json", terminal)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"derived output appeared during run: {output}")
    staging.rename(output)
    print(
        json.dumps(
            {
                "case_count": len(terminal_results),
                "output": str(output),
                "source_tree_sha256": source_sha256,
                "status": terminal["status"],
                "successful_case_count": terminal["successful_case_count"],
            },
            sort_keys=True,
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    arguments = _parse_args()
    repository_root = cast(Path, arguments.repository_root).resolve()
    output = cast(Path, arguments.output).resolve()
    run_campaign(
        repository_root=repository_root,
        output=output,
        resume=bool(arguments.resume),
        preflight_only=bool(arguments.preflight_only),
    )


if __name__ == "__main__":
    main()
