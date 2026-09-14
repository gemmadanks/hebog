#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Run one authorized write-once Phase 5 public-finder campaign."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import numpy as np
from astropy.io import fits

_ROOT = Path(__file__).parents[2]
_PROTOCOL_PATH = "config/contracts/phase-5-public-finder-protocol.json"
_DECISION_PATH = (
    "config/contracts/phase-5-public-finder-execution-decision.json"
)
_ACQUISITION_PATH = (
    "benchmark-results/phase-5/public-comparison-acquisition/acquisition.json"
)
_SELECTION_PATH = (
    "benchmark-results/phase-5/public-comparison-selection/population.json"
)
_OUTPUT_PATH = "benchmark-results/phase-5/public-finder-comparison"
_RUNNER_PATH = "scripts/benchmark/run_phase5_public_finder_hebog.py"
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_public_finder_protocol.py")
)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one checked external command with captured diagnostic output."""
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _inspect_hebog_image(
    image: str,
    *,
    podman_executable: str,
) -> dict[str, Any]:
    """Resolve one local container without pulling or mutating it."""
    completed = _run(
        [
            podman_executable,
            "image",
            "inspect",
            image,
        ]
    )
    value = cast(object, json.loads(completed.stdout))
    if not isinstance(value, list) or len(value) != 1:
        raise ValueError("Podman image inspection did not return one image")
    inspected = value[0]
    if not isinstance(inspected, dict):
        raise ValueError("Podman image inspection did not return an object")
    return cast(dict[str, Any], inspected)


def _validate_runtime_image(
    protocol: dict[str, Any],
    inspection: dict[str, Any],
) -> None:
    """Require the exact qualified local Hebog image identity."""
    runtime = cast(dict[str, Any], protocol["runtime"])
    observed_id = str(inspection.get("Id", "")).removeprefix("sha256:")
    observed_digest = str(inspection.get("Digest", ""))
    if observed_id != runtime["image_id"]:
        raise ValueError("qualified Hebog image ID changed")
    if observed_digest != runtime["digest"]:
        raise ValueError("qualified Hebog image digest changed")


def preflight_public_finder(
    *,
    repository_root: Path,
    output: Path,
    hebog_image: str,
    podman_executable: str = "podman",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Perform the complete no-write check after exact named approval."""
    decision = _HELPERS["load_public_finder_execution_decision"](
        repository_root / _DECISION_PATH
    )
    if not decision["execution_authorized"]:
        raise ValueError("public finder execution is not authorized")
    protocol = _HELPERS["load_public_finder_protocol"](
        repository_root / _PROTOCOL_PATH
    )
    expected_output = (repository_root / _OUTPUT_PATH).resolve()
    if output.resolve() != expected_output:
        raise ValueError("public finder output path changed")
    if output.exists():
        raise FileExistsError(
            f"public finder campaign already exists: {output}"
        )
    for path in (
        repository_root / _ACQUISITION_PATH,
        repository_root / _SELECTION_PATH,
    ):
        if not path.is_file():
            raise FileNotFoundError(
                f"required public evidence is absent: {path}"
            )
    inspection = _inspect_hebog_image(
        hebog_image,
        podman_executable=podman_executable,
    )
    _validate_runtime_image(protocol, inspection)
    _validate_input_evidence(repository_root, protocol)
    return protocol, decision


def _acquisition_paths(repository_root: Path) -> dict[str, Path]:
    """Resolve the seven checksum-bound public source artifacts."""
    acquisition_path = repository_root / _ACQUISITION_PATH
    acquisition = _HELPERS["json_object"](acquisition_path)
    raw = acquisition_path.parent / "raw"
    paths = {
        item["identifier"]: raw / item["filename"]
        for item in acquisition["artifacts"]
    }
    for item in acquisition["artifacts"]:
        path = paths[item["identifier"]]
        if _HELPERS["file_sha256"](path) != item["sha256"]:
            raise ValueError("public acquisition artifact checksum changed")
    return paths


def _shifted_header(
    header: fits.Header,
    *,
    x_start: int,
    y_start: int,
) -> fits.Header:
    """Translate a full-image WCS to one bounded halo materialization."""
    shifted = header.copy()
    shifted["CRPIX1"] = float(cast(Any, shifted["CRPIX1"])) - x_start
    shifted["CRPIX2"] = float(cast(Any, shifted["CRPIX2"])) - y_start
    if shifted.get("BPA") is None:
        shifted["BPA"] = 0.0
    if shifted.get("RESTFRQ", shifted.get("RESTFREQ")) is None:
        shifted["RESTFRQ"] = 1.4e9
    return shifted


def _materialize_sdc1_input(
    *,
    source: Path,
    destination: Path,
    bounds_xy: list[int],
    halo_pixels: int,
) -> list[int]:
    """Write one haloed SDC1 input and return its local output core."""
    x_start, x_stop, y_start, y_stop = bounds_xy
    with fits.open(source, mode="readonly", memmap=True) as hdus:
        primary = cast(Any, hdus[0])
        height, width = primary.shape[-2:]
        read_x_start = max(0, x_start - halo_pixels)
        read_x_stop = min(width, x_stop + halo_pixels)
        read_y_start = max(0, y_start - halo_pixels)
        read_y_stop = min(height, y_stop + halo_pixels)
        values = np.asarray(
            primary.section[
                0,
                0,
                read_y_start:read_y_stop,
                read_x_start:read_x_stop,
            ],
            dtype=np.float64,
        )
        header = _shifted_header(
            primary.header,
            x_start=read_x_start,
            y_start=read_y_start,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(
        data=values[np.newaxis, np.newaxis, :, :],
        header=header,
    ).writeto(destination)
    return [
        y_start - read_y_start,
        y_stop - read_y_start,
        x_start - read_x_start,
        x_stop - read_x_start,
    ]


def _selected_tiles(repository_root: Path) -> dict[str, dict[str, Any]]:
    """Return selected metadata without reading any selected pixels."""
    population = _HELPERS["json_object"](repository_root / _SELECTION_PATH)
    return {
        item["stratum"]: item
        for item in cast(
            list[dict[str, Any]], population["sdc1"]["selected_tiles"]
        )
    }


def _validate_input_evidence(
    repository_root: Path,
    protocol: dict[str, Any],
) -> None:
    """Hash every frozen public input without creating campaign state."""
    acquisition_paths = _acquisition_paths(repository_root)
    selection_directory = (
        repository_root
        / "benchmark-results/phase-5/public-comparison-selection"
    )
    selected_tiles = _selected_tiles(repository_root)
    for stratum in protocol["sdc1"]["strata"]:
        selected = selected_tiles[stratum["stratum"]]
        if selected["tile"]["tile_id"] != stratum["tile_id"]:
            raise ValueError("selected SDC1 tile identity changed")
        for role in ("image", "truth"):
            identity = selected[role]
            path = selection_directory / identity["path"]
            if (
                identity["sha256"] != stratum[f"{role}_sha256"]
                or _HELPERS["file_sha256"](path) != identity["sha256"]
            ):
                raise ValueError(f"selected SDC1 {role} checksum changed")
    for case in protocol["hydra"]["cases"]:
        path = acquisition_paths[case["source_identifier"]]
        if _HELPERS["file_sha256"](path) != case["source_sha256"]:
            raise ValueError("selected Hydra source checksum changed")


def _input_record(  # noqa: PLR0913
    *,
    repository_root: Path,
    staging: Path,
    case: dict[str, Any],
    protocol: dict[str, Any],
    acquisition_paths: dict[str, Path],
    selected_tiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Materialize or bind one complete campaign input."""
    case_id = cast(str, case["case_id"])
    directory = staging / "inputs" / case_id
    if directory.exists():
        raise FileExistsError(f"incomplete public input exists: {directory}")
    directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{case_id}.",
        dir=directory.parent,
    ) as temporary_directory:
        unpublished = Path(temporary_directory) / "record"
        unpublished.mkdir()
        if case_id.startswith("sdc1-"):
            selected = selected_tiles[cast(str, case["stratum"])]
            core_path = (
                repository_root
                / "benchmark-results/phase-5/public-comparison-selection"
                / selected["image"]["path"]
            )
            if _HELPERS["file_sha256"](core_path) != case["image_sha256"]:
                raise ValueError("selected SDC1 core checksum changed")
            unpublished_input = unpublished / "input.fits"
            local_core = _materialize_sdc1_input(
                source=acquisition_paths["image"],
                destination=unpublished_input,
                bounds_xy=case["bounds_xy_half_open"],
                halo_pixels=protocol["sdc1"]["halo_pixels_yx"][0],
            )
            input_path = directory / "input.fits"
            input_sha256 = _HELPERS["file_sha256"](unpublished_input)
            input_location = "staging"
        else:
            input_path = acquisition_paths[case["source_identifier"]]
            local_core = None
            input_sha256 = _HELPERS["file_sha256"](input_path)
            input_location = "repository"
        record = {
            "schema_version": 1,
            "case_id": case_id,
            "input_path": str(input_path.relative_to(repository_root))
            if input_location == "repository"
            else str(input_path.relative_to(staging)),
            "input_location": input_location,
            "input_sha256": input_sha256,
            "local_core_yx_half_open": local_core,
        }
        _HELPERS["write_once_json"](unpublished / "input.json", record)
        unpublished.rename(directory)
    return record


def _validated_existing_input_record(
    *,
    repository_root: Path,
    staging: Path,
    case_id: str,
    input_json: Path,
) -> dict[str, Any]:
    """Revalidate one restartable input record before finder execution."""
    record = _HELPERS["json_object"](input_json)
    location = record.get("input_location")
    if record.get("case_id") != case_id or location not in {
        "repository",
        "staging",
    }:
        raise ValueError("public finder resume input record changed")
    relative = Path(cast(str, record.get("input_path")))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("public finder resume input path changed")
    root = repository_root if location == "repository" else staging
    input_path = root / relative
    if not input_path.is_file() or _HELPERS["file_sha256"](
        input_path
    ) != record.get("input_sha256"):
        raise ValueError("public finder resume input checksum changed")
    return record


def _cases(protocol: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return the canonical eight SDC1 then two Hydra cases."""
    sdc1 = tuple(
        {
            **item,
            "case_id": f"sdc1-{item['stratum']}-{item['tile_id']}",
        }
        for item in protocol["sdc1"]["strata"]
    )
    return sdc1 + tuple(protocol["hydra"]["cases"])


def _container_path(record: dict[str, Any]) -> str:
    """Translate one bound host input path into the container mount."""
    root = (
        "/repository"
        if record["input_location"] == "repository"
        else "/campaign"
    )
    return f"{root}/{record['input_path']}"


def _runner_command(  # noqa: PLR0913
    *,
    repository_root: Path,
    staging: Path,
    image: str,
    case_id: str,
    record: dict[str, Any],
    podman_executable: str,
) -> list[str]:
    """Build one isolated exact-runtime Hebog invocation."""
    command = [
        podman_executable,
        "run",
        "--rm",
        "--volume",
        f"{repository_root}:/repository:ro",
        "--volume",
        f"{staging}:/campaign:rw",
        "--workdir",
        "/repository",
        image,
        "python",
        f"/repository/{_RUNNER_PATH}",
        "--authorization",
        f"/repository/{_DECISION_PATH}",
        "--input",
        _container_path(record),
        "--output",
        f"/campaign/results/{case_id}",
        "--case-id",
        case_id,
    ]
    core = record["local_core_yx_half_open"]
    if core is not None:
        command.extend(("--core", ",".join(str(value) for value in core)))
    return command


def _append_progress(path: Path, message: str) -> None:
    """Append one operational line and flush it durably."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def run_public_finder_campaign(
    *,
    repository_root: Path,
    output: Path,
    hebog_image: str,
    podman_executable: str = "podman",
    resume: bool = False,
) -> None:
    """Execute and atomically seal the single approved public campaign."""
    protocol, decision = preflight_public_finder(
        repository_root=repository_root,
        output=output,
        hebog_image=hebog_image,
        podman_executable=podman_executable,
    )
    decision_sha256 = _HELPERS["file_sha256"](repository_root / _DECISION_PATH)
    staging = output.parent / f".{output.name}.{decision_sha256[:12]}.staging"
    if staging.exists() and not resume:
        raise FileExistsError(
            f"public finder staging already exists: {staging}"
        )
    staging.mkdir(parents=True, exist_ok=resume)
    request = {
        "schema_version": 1,
        "request_id": "phase-5-public-finder-one-look",
        "status": "authorized-private-staging",
        "protocol_sha256": _HELPERS["file_sha256"](
            repository_root / _PROTOCOL_PATH
        ),
        "execution_decision_sha256": decision_sha256,
        "identity_review_sha256": decision["identity_review"]["sha256"],
        "case_count": protocol["case_count"],
        "hebog_image_id": protocol["runtime"]["image_id"],
        "hebog_image_digest": protocol["runtime"]["digest"],
    }
    request_path = staging / "request.json"
    if request_path.exists():
        if _HELPERS["json_object"](request_path) != request:
            raise ValueError("public finder resume request changed")
    else:
        _HELPERS["write_once_json"](request_path, request)
    opened_path = staging / "open-state.json"
    if not opened_path.exists():
        _HELPERS["write_once_json"](
            opened_path,
            {
                "schema_version": 1,
                "status": "private-staging-open",
                "request_sha256": _HELPERS["file_sha256"](request_path),
                "opened_at": datetime.now(UTC).isoformat(),
            },
        )
    progress_path = staging / "progress.log"
    acquisition_paths = _acquisition_paths(repository_root)
    selected_tiles = _selected_tiles(repository_root)
    results: list[dict[str, object]] = []
    for case in _cases(protocol):
        case_id = cast(str, case["case_id"])
        result_path = staging / "results" / case_id / "result.json"
        if result_path.exists():
            result = _HELPERS["json_object"](result_path)
            if result.get("status") != "success":
                raise ValueError("public finder resume found a failed result")
        else:
            input_json = staging / "inputs" / case_id / "input.json"
            record = (
                _validated_existing_input_record(
                    repository_root=repository_root,
                    staging=staging,
                    case_id=case_id,
                    input_json=input_json,
                )
                if input_json.exists()
                else _input_record(
                    repository_root=repository_root,
                    staging=staging,
                    case=case,
                    protocol=protocol,
                    acquisition_paths=acquisition_paths,
                    selected_tiles=selected_tiles,
                )
            )
            _run(
                _runner_command(
                    repository_root=repository_root,
                    staging=staging,
                    image=hebog_image,
                    case_id=case_id,
                    record=record,
                    podman_executable=podman_executable,
                )
            )
            result = _HELPERS["json_object"](result_path)
            _append_progress(progress_path, f"completed {case_id}")
        results.append(
            {
                "case_id": case_id,
                "result_path": str(result_path.relative_to(staging)),
                "result_sha256": _HELPERS["file_sha256"](result_path),
                "status": result["status"],
            }
        )
    terminal: dict[str, object] = {
        "schema_version": 1,
        "campaign_id": "phase-5-public-finder-comparison",
        "status": "terminal-raw-results-sealed",
        "request_sha256": _HELPERS["file_sha256"](request_path),
        "protocol_sha256": request["protocol_sha256"],
        "execution_decision_sha256": decision_sha256,
        "case_count": len(results),
        "successful_case_count": sum(
            item["status"] == "success" for item in results
        ),
        "results": results,
        "completed_at": datetime.now(UTC).isoformat(),
        "scientific_review_opened": False,
        "cutover_authorized": False,
    }
    _HELPERS["write_once_json"](staging / "campaign.json", terminal)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(
            "public finder terminal output appeared during execution: "
            f"{output}"
        )
    staging.rename(output)


def _parse_args() -> argparse.Namespace:
    """Parse the single public campaign invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hebog-image", required=True)
    parser.add_argument("--podman-executable", default="podman")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Preflight or execute only the exactly authorized public campaign."""
    arguments = _parse_args()
    repository_root = cast(Path, arguments.repository_root).resolve()
    output = cast(Path, arguments.output).resolve()
    if arguments.preflight_only:
        preflight_public_finder(
            repository_root=repository_root,
            output=output,
            hebog_image=arguments.hebog_image,
            podman_executable=arguments.podman_executable,
        )
        return
    run_public_finder_campaign(
        repository_root=repository_root,
        output=output,
        hebog_image=arguments.hebog_image,
        podman_executable=arguments.podman_executable,
        resume=arguments.resume,
    )


if __name__ == "__main__":
    main()
