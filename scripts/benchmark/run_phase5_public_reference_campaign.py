#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
"""Build an isolated qualitative reference comparison for public data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from hebog.validation.contracts import PhaseFiveExternalComparisonProtocol

FinderId = Literal["released-pybdsf", "aegean"]

_ROOT = Path(__file__).parents[2]
_BASE_CAMPAIGN = Path("benchmark-results/phase-5/public-finder-comparison")
_OUTPUT = Path("benchmark-results/phase-5/public-reference-comparison")
_PROTOCOL = Path(
    "config/contracts/phase-5-external-post-failure-comparison.json"
)
_RUNNER = Path("scripts/benchmark/run_phase5_public_reference_finder.py")


def _load_protocol(path: Path) -> PhaseFiveExternalComparisonProtocol:
    helpers = runpy.run_path(
        str(_ROOT / "scripts/validation/phase5_viewed_recovery_protocol.py")
    )
    return cast(
        PhaseFiveExternalComparisonProtocol,
        helpers["load_viewed_recovery_protocol"](path),
    )


_FINDERS: tuple[FinderId, ...] = ("released-pybdsf", "aegean")


def _parse_args() -> argparse.Namespace:
    """Parse the isolated derived-campaign invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--released-pybdsf-image", required=True)
    parser.add_argument("--aegean-image", required=True)
    parser.add_argument("--podman-executable", default="podman")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    """Return one file's SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    """Read one required JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, Any], value)


def _write_once(path: Path, document: dict[str, object]) -> None:
    """Write one canonical JSON document without replacement."""
    if path.exists():
        raise FileExistsError(f"refusing to replace campaign state: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _run(command: list[str]) -> None:
    """Run one checked reference command without capturing its progress."""
    subprocess.run(command, check=True)


def _inspect_image(
    image: str,
    *,
    podman_executable: str,
) -> dict[str, Any]:
    """Return one local image identity without pulling or changing it."""
    completed = subprocess.run(
        [podman_executable, "image", "inspect", image],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    values = json.loads(completed.stdout)
    if not isinstance(values, list) or len(values) != 1:
        raise ValueError("Podman image inspection did not return one image")
    inspected = values[0]
    if not isinstance(inspected, dict):
        raise ValueError("Podman image inspection did not return an object")
    return cast(dict[str, Any], inspected)


def _active_reference_staging(
    output: Path,
    staging: Path,
) -> tuple[Path, ...]:
    """Return other reference staging roots that may own the Podman VM."""
    return tuple(
        path
        for path in output.parent.glob(".*reference*.staging")
        if path.resolve() != staging.resolve()
    )


def _input_path(
    repository_root: Path,
    base: Path,
    record: dict[str, Any],
) -> Path:
    """Resolve one sealed public input without permitting path escape."""
    relative = Path(str(record["input_path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("public input path is not repository-safe")
    location = record.get("input_location")
    root = repository_root if location == "repository" else base
    path = (root / relative).resolve()
    if not path.is_relative_to(repository_root) or not path.is_file():
        raise FileNotFoundError(f"public input is unavailable: {path}")
    if _sha256(path) != record.get("input_sha256"):
        raise ValueError(f"public input checksum changed: {path}")
    return path


def _validate_preflight(  # noqa: PLR0913
    *,
    repository_root: Path,
    output: Path,
    staging: Path,
    images: dict[FinderId, str],
    podman_executable: str,
    resume: bool,
) -> tuple[dict[FinderId, dict[str, str]], dict[str, Any]]:
    """Validate isolation, sealed inputs, and exact reference images."""
    expected_output = (repository_root / _OUTPUT).resolve()
    if output.resolve() != expected_output:
        raise ValueError(f"derived output must be {expected_output}")
    if output.exists():
        raise FileExistsError(f"derived campaign already exists: {output}")
    active = _active_reference_staging(output, staging)
    if active:
        names = ", ".join(str(path) for path in active)
        raise RuntimeError(
            "another reference campaign may be running; refusing to share "
            f"its Podman resources: {names}"
        )
    if staging.exists() and not resume:
        raise FileExistsError(f"derived staging already exists: {staging}")
    base = repository_root / _BASE_CAMPAIGN
    campaign = _read_json(base / "campaign.json")
    if campaign.get("status") != "terminal-raw-results-sealed":
        raise ValueError("base public campaign is not sealed")
    protocol = _load_protocol(repository_root / _PROTOCOL)
    identities: dict[FinderId, dict[str, str]] = {}
    for finder_id in _FINDERS:
        inspected = _inspect_image(
            images[finder_id],
            podman_executable=podman_executable,
        )
        reference = next(
            item for item in protocol.references if item.finder_id == finder_id
        )
        digest = str(inspected.get("Digest", ""))
        if digest != reference.container_image_digest:
            raise ValueError(f"{finder_id} local image digest changed")
        identities[finder_id] = {
            "image": images[finder_id],
            "image_id": str(inspected.get("Id", "")),
            "digest": digest,
        }
    return identities, campaign


def _container_command(  # noqa: PLR0913
    *,
    repository_root: Path,
    staging: Path,
    image: str,
    image_digest: str,
    finder_id: FinderId,
    case_id: str,
    input_path: Path,
    core: object,
    output_directory: Path,
    podman_executable: str,
) -> list[str]:
    """Build one networkless, read-only-repository reference invocation."""
    command = [
        podman_executable,
        "run",
        "--rm",
        "--network=none",
        "--volume",
        f"{repository_root}:/repository:ro",
        "--volume",
        f"{staging}:/comparison:rw",
        "--shm-size",
        "1g",
        "--workdir",
        "/repository",
        "--entrypoint",
        "python3",
        "--env",
        "PYTHONPATH=/repository/src",
        image,
        f"/repository/{_RUNNER}",
        "--protocol",
        f"/repository/{_PROTOCOL}",
        "--input",
        f"/repository/{input_path.relative_to(repository_root)}",
        "--output",
        f"/comparison/{output_directory.relative_to(staging)}",
        "--case-id",
        case_id,
        "--finder-id",
        finder_id,
        "--container-image-digest",
        image_digest,
        "--ncores",
        "4",
    ]
    if isinstance(core, list):
        command.extend(("--core", ",".join(str(value) for value in core)))
    return command


def _append_progress(path: Path, message: str) -> None:
    """Append and durably flush one operational progress line."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def run_public_reference_campaign(  # noqa: PLR0913
    *,
    repository_root: Path,
    output: Path,
    images: dict[FinderId, str],
    podman_executable: str,
    resume: bool,
    preflight_only: bool,
) -> None:
    """Run ten public cases serially and seal only the derived result root."""
    base = repository_root / _BASE_CAMPAIGN
    base_sha256 = _sha256(base / "campaign.json")
    staging = output.parent / (f".{output.name}.{base_sha256[:12]}.staging")
    identities, base_campaign = _validate_preflight(
        repository_root=repository_root,
        output=output,
        staging=staging,
        images=images,
        podman_executable=podman_executable,
        resume=resume,
    )
    if preflight_only:
        return
    staging.mkdir(parents=True, exist_ok=resume)
    request: dict[str, object] = {
        "schema_version": 1,
        "request_id": "phase-5-public-reference-visual-comparison",
        "status": "derived-qualitative-comparison",
        "base_campaign_repository_path": str(_BASE_CAMPAIGN / "campaign.json"),
        "base_campaign_sha256": base_sha256,
        "protocol_repository_path": str(_PROTOCOL),
        "protocol_sha256": _sha256(repository_root / _PROTOCOL),
        "containers": identities,
        "finders": list(_FINDERS),
        "modes": ["operational"],
        "scientific_claims_authorized": False,
    }
    request_path = staging / "request.json"
    if request_path.exists():
        if _read_json(request_path) != request:
            raise ValueError("derived campaign resume request changed")
    else:
        _write_once(request_path, request)
    progress_path = staging / "progress.log"
    terminal_results: list[dict[str, object]] = []
    for base_item in base_campaign["results"]:
        case_id = str(base_item["case_id"])
        input_json = base / "inputs" / case_id / "input.json"
        input_record = _read_json(input_json)
        input_path = _input_path(repository_root, base, input_record)
        for finder_id in _FINDERS:
            result_directory = (
                staging / "results" / case_id / finder_id / "operational"
            )
            result_path = result_directory / "result.json"
            if result_path.exists():
                result = _read_json(result_path)
                if result.get("status") != "success":
                    raise ValueError("resume found a failed reference result")
            else:
                _run(
                    _container_command(
                        repository_root=repository_root,
                        staging=staging,
                        image=images[finder_id],
                        image_digest=identities[finder_id]["digest"],
                        finder_id=finder_id,
                        case_id=case_id,
                        input_path=input_path,
                        core=input_record.get("local_core_yx_half_open"),
                        output_directory=result_directory,
                        podman_executable=podman_executable,
                    )
                )
                result = _read_json(result_path)
                _append_progress(
                    progress_path,
                    f"completed {case_id} {finder_id} operational",
                )
            terminal_results.append(
                {
                    "case_id": case_id,
                    "finder_id": finder_id,
                    "mode": "operational",
                    "result_path": str(result_path.relative_to(staging)),
                    "result_sha256": _sha256(result_path),
                    "status": result["status"],
                }
            )
    terminal: dict[str, object] = {
        "schema_version": 1,
        "campaign_id": "phase-5-public-reference-comparison",
        "status": "terminal-derived-results-sealed",
        "base_campaign_repository_path": str(_BASE_CAMPAIGN / "campaign.json"),
        "base_campaign_sha256": base_sha256,
        "request_sha256": _sha256(request_path),
        "case_count": len(base_campaign["results"]),
        "run_count": len(terminal_results),
        "successful_run_count": sum(
            item["status"] == "success" for item in terminal_results
        ),
        "results": terminal_results,
        "completed_at": datetime.now(UTC).isoformat(),
        "scientific_claims_authorized": False,
    }
    _write_once(staging / "campaign.json", terminal)
    if output.exists():
        raise FileExistsError(f"derived output appeared during run: {output}")
    staging.rename(output)


def main() -> None:
    """Preflight or execute the isolated public reference campaign."""
    arguments = _parse_args()
    repository_root = cast(Path, arguments.repository_root).resolve()
    images: dict[FinderId, str] = {
        "released-pybdsf": arguments.released_pybdsf_image,
        "aegean": arguments.aegean_image,
    }
    run_public_reference_campaign(
        repository_root=repository_root,
        output=cast(Path, arguments.output).resolve(),
        images=images,
        podman_executable=arguments.podman_executable,
        resume=arguments.resume,
        preflight_only=arguments.preflight_only,
    )


if __name__ == "__main__":
    main()
