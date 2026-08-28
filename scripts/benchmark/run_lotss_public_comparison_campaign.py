#!/usr/bin/env python3
"""Build an isolated LoTSS DR2 comparison and aggregate notebook campaign.

The script never writes to the sealed SDC1/Hydra campaigns. It downloads
three checksum-bound LoTSS DR2 cutouts into a new staging tree, runs current
Hebog on the host, runs released PyBDSF and Aegean in the already reviewed
networkless containers, and finally creates a symlink-based aggregate view for
the campaign comparison notebook.

The LoTSS products are observational diagnostics, not ground truth. The
published LoTSS catalogue is PyBDSF-derived and is deliberately not promoted
to an independent oracle by this campaign.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import subprocess
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from hebog.validation.external_runners import source_tree_sha256
from hebog.validation.post_correction_recovery import (
    post_correction_candidate_configuration_sha256,
)

_ROOT = Path(__file__).parents[2]
_OUTPUT = Path("benchmark-results/phase-5/lotss-public-comparison")
_AGGREGATE_OUTPUT = Path(
    "benchmark-results/phase-5/current-public-plus-lotss-comparison"
)
_EXISTING_CURRENT = Path(
    "benchmark-results/phase-5/current-public-hebog-comparison/campaign.json"
)
_REFERENCE_IDENTITY = Path(
    "benchmark-results/phase-5/public-reference-comparison/request.json"
)
_BASE_REVIEW = Path("config/contracts/phase-5-corrective-a-review.json")
_REFERENCE_PROTOCOL = Path(
    "config/contracts/phase-5-external-post-failure-comparison.json"
)
_HEBOG_RUNNER = Path("scripts/benchmark/run_phase5_public_finder_hebog.py")
_REFERENCE_RUNNER = Path(
    "scripts/benchmark/run_phase5_public_reference_finder.py"
)
_RUNNER_PATH = Path(
    "scripts/benchmark/run_lotss_public_comparison_campaign.py"
)
_CUTOUT_ENDPOINT = "https://lofar-surveys.org/dr2-cutout.fits"


@dataclass(frozen=True, slots=True)
class LoTSSCase:
    """One prospectively declared LoTSS DR2 observational diagnostic."""

    case_id: str
    label: str
    position: str
    size_arcminutes: int
    role: str


_CASES = (
    LoTSSCase(
        case_id="lotss-dr2-wide-ra13-90arcmin",
        label="LoTSS DR2 wide RA-13 survey field (90 arcmin)",
        position="13:00:00 +47:00:00",
        size_arcminutes=90,
        role="wide representative low-frequency survey diagnostic",
    ),
    LoTSSCase(
        case_id="lotss-dr2-3c295-12arcmin",
        label="LoTSS DR2 3C 295 bright-source field (12 arcmin)",
        position="3C 295",
        size_arcminutes=12,
        role="bright-source dynamic-range and nearby-completeness stress",
    ),
    LoTSSCase(
        case_id="lotss-dr2-m51-20arcmin",
        label="LoTSS DR2 M51 complex-emission field (20 arcmin)",
        position="M51",
        size_arcminutes=20,
        role="extended-emission and association stress",
    ),
)
_FINDERS = ("released-pybdsf", "aegean")
_PRESERVED_HEADER_KEYS = (
    "BUNIT",
    "BMAJ",
    "BMIN",
    "BPA",
    "RESTFRQ",
    "RESTFREQ",
    "TELESCOP",
    "INSTRUME",
    "ORIGIN",
    "OBJECT",
    "DATE-OBS",
)


def _parse_args() -> argparse.Namespace:
    """Parse the isolated campaign invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument(
        "--aggregate-output",
        type=Path,
        default=_AGGREGATE_OUTPUT,
    )
    parser.add_argument(
        "--existing-current-campaign",
        type=Path,
        default=_EXISTING_CURRENT,
    )
    parser.add_argument(
        "--reference-identity",
        type=Path,
        default=_REFERENCE_IDENTITY,
    )
    parser.add_argument("--podman-executable", default="podman")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    """Read one required JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, Any], value)


def _write_json(path: Path, value: object) -> None:
    """Write one canonical JSON document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{json.dumps(value, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _write_once(path: Path, value: object) -> None:
    """Write a request once or require an identical resume request."""
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != value:
            raise ValueError(f"resume request changed: {path}")
        return
    _write_json(path, value)


def _sha256(path: Path) -> str:
    """Return one file's SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repository_path(repository_root: Path, path: Path) -> Path:
    """Resolve a path and require it to remain under the repository."""
    resolved = path if path.is_absolute() else repository_root / path
    resolved = resolved.resolve()
    if not resolved.is_relative_to(repository_root):
        raise ValueError(f"path escapes repository: {resolved}")
    return resolved


def _repository_relative(repository_root: Path, path: Path) -> str:
    """Return one resolved repository-relative path."""
    return str(path.resolve().relative_to(repository_root))


def _download_url(case: LoTSSCase) -> str:
    """Return the official DR2 cutout URL for one frozen request."""
    query = urllib.parse.urlencode(
        {"pos": case.position, "size": str(case.size_arcminutes)}
    )
    return f"{_CUTOUT_ENDPOINT}?{query}"


def _download(url: str, destination: Path) -> None:
    """Stream one remote product into campaign-owned staging storage."""
    partial = destination.with_suffix(".download")
    if partial.exists():
        partial.unlink()
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Hebog-LoTSS-validation/1"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"LoTSS cutout returned HTTP {response.status}")
        with partial.open("wb") as handle:
            while block := response.read(1024 * 1024):
                handle.write(block)
    partial.rename(destination)


def _normalise_fits(download: Path, destination: Path) -> dict[str, object]:
    """Write a canonical two-dimensional science plane with celestial WCS."""
    with fits.open(download, memmap=False) as hdul:
        source_header = hdul[0].header.copy()
        plane = np.squeeze(np.asarray(hdul[0].data))
    if plane.ndim != 2 or not np.issubdtype(plane.dtype, np.number):
        raise ValueError(f"LoTSS cutout is not one numeric image plane: {plane.shape}")
    if not np.any(np.isfinite(plane)):
        raise ValueError("LoTSS cutout contains no finite pixels")
    header = WCS(source_header, relax=True).celestial.to_header(relax=True)
    for key in _PRESERVED_HEADER_KEYS:
        if key in source_header:
            header[key] = source_header[key]
    if "RESTFRQ" not in header and "RESTFREQ" not in header:
        spectral_wcs = WCS(source_header, relax=True).spectral
        frequency_hz = (
            float(spectral_wcs.wcs.crval[0])
            if spectral_wcs.pixel_n_dim == 1
            else 144_000_000.0
        )
        if not np.isfinite(frequency_hz) or frequency_hz <= 0.0:
            frequency_hz = 144_000_000.0
        header["RESTFRQ"] = (frequency_hz, "Reference frequency [Hz]")
        header["RESTFREQ"] = (
            frequency_hz,
            "Reference frequency [Hz]; released PyBDSF spelling",
        )
    header["HISTORY"] = "Canonical 2D plane frozen by Hebog LoTSS campaign"
    fits.PrimaryHDU(data=plane, header=header).writeto(
        destination,
        checksum=True,
        output_verify="fix",
    )
    return {
        "shape_yx": [int(plane.shape[0]), int(plane.shape[1])],
        "dtype": str(plane.dtype),
        "finite_pixel_count": int(np.count_nonzero(np.isfinite(plane))),
        "bunit": str(header.get("BUNIT", "unavailable")),
        "reference_frequency_hz": float(
            header.get("RESTFREQ", header.get("RESTFRQ"))
        ),
        "beam_degrees": {
            "major": header.get("BMAJ"),
            "minor": header.get("BMIN"),
            "position_angle": header.get("BPA"),
        },
    }


def _acquire_case(input_root: Path, case: LoTSSCase) -> dict[str, object]:
    """Acquire and freeze one LoTSS case, resuming completed inputs."""
    directory = input_root / "inputs" / case.case_id
    image_path = directory / "input.fits"
    input_record_path = directory / "input.json"
    provenance_path = directory / "provenance.json"
    if image_path.is_file() and input_record_path.is_file():
        record = _read_json(input_record_path)
        if record.get("input_sha256") != _sha256(image_path):
            raise ValueError(f"resumed LoTSS input checksum changed: {case.case_id}")
        return record

    directory.mkdir(parents=True, exist_ok=True)
    raw_path = directory / "downloaded.fits"
    url = _download_url(case)
    _download(url, raw_path)
    raw_sha256 = _sha256(raw_path)
    metadata = _normalise_fits(raw_path, image_path)
    raw_path.unlink()
    record: dict[str, object] = {
        "schema_version": 1,
        "case_id": case.case_id,
        "input_location": "staging",
        "input_path": f"inputs/{case.case_id}/input.fits",
        "input_sha256": _sha256(image_path),
        "local_core_yx_half_open": None,
    }
    provenance = {
        "schema_version": 1,
        "case": asdict(case),
        "survey": "LoTSS",
        "data_release": "DR2",
        "product": "6-arcsec restored Stokes I mosaic cutout",
        "download_url": url,
        "downloaded_sha256": raw_sha256,
        "canonical_input_sha256": record["input_sha256"],
        "canonicalisation": "squeeze singleton axes and retain celestial WCS",
        "metadata": metadata,
        "scientific_role": "observational diagnostic; no ground-truth claim",
    }
    _write_json(provenance_path, provenance)
    _write_json(input_record_path, record)
    return record


def _run_command(command: list[str]) -> None:
    """Run one isolated reference process and surface bounded diagnostics."""
    completed = subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        diagnostic = "\n".join(
            [completed.stdout[-4000:], completed.stderr[-4000:]]
        ).strip()
        raise RuntimeError(
            f"reference finder exited {completed.returncode}:\n{diagnostic}"
        )


def _reference_command(
    *,
    repository_root: Path,
    staging: Path,
    input_path: Path,
    output: Path,
    case_id: str,
    finder_id: str,
    image: str,
    digest: str,
    podman_executable: str,
) -> list[str]:
    """Build one networkless reference-finder invocation."""
    return [
        podman_executable,
        "run",
        "--rm",
        "--network=none",
        "--volume",
        f"{repository_root}:/repository:ro",
        "--volume",
        f"{staging}:/comparison:rw",
        "--shm-size",
        "2g",
        "--workdir",
        "/repository",
        "--entrypoint",
        "python3",
        "--env",
        "PYTHONPATH=/repository/src",
        image,
        f"/repository/{_REFERENCE_RUNNER}",
        "--protocol",
        f"/repository/{_REFERENCE_PROTOCOL}",
        "--input",
        f"/comparison/{input_path.relative_to(staging)}",
        "--output",
        f"/comparison/{output.relative_to(staging)}",
        "--case-id",
        case_id,
        "--finder-id",
        finder_id,
        "--container-image-digest",
        digest,
        "--ncores",
        "4",
    ]


def _link_directory(source: Path, destination: Path) -> None:
    """Mirror one directory with non-overwriting in-root hard links."""
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"aggregate destination already exists: {destination}")
    destination.mkdir(parents=True)
    for source_path in sorted(source.rglob("*")):
        relative = source_path.relative_to(source)
        destination_path = destination / relative
        if source_path.is_dir():
            destination_path.mkdir()
        elif source_path.is_file():
            os.link(source_path, destination_path)
        else:
            raise ValueError(f"unsupported aggregate source: {source_path}")


def _input_manifest(root: Path, cases: list[str]) -> dict[str, object]:
    """Describe input records exposed by one aggregate input campaign."""
    results = []
    for case_id in cases:
        record_path = root / "inputs" / case_id / "input.json"
        results.append(
            {
                "case_id": case_id,
                "result_path": f"inputs/{case_id}/input.json",
                "result_sha256": _sha256(record_path),
                "status": "success",
            }
        )
    return {
        "schema_version": 1,
        "campaign_id": "phase-5-public-plus-lotss-inputs",
        "status": "terminal-inputs-assembled",
        "case_count": len(cases),
        "successful_case_count": len(cases),
        "scientific_claims_authorized": False,
        "results": results,
    }


def _build_aggregate(
    *,
    repository_root: Path,
    lotss_root: Path,
    existing_current_path: Path,
    aggregate: Path,
) -> None:
    """Assemble an additive SDC1/Hydra/LoTSS notebook campaign."""
    if aggregate.exists():
        raise FileExistsError(f"aggregate campaign already exists: {aggregate}")
    staging = aggregate.parent / f".{aggregate.name}.staging"
    if staging.exists():
        raise FileExistsError(f"aggregate staging already exists: {staging}")
    existing_current = _read_json(existing_current_path)
    existing_input_path = _repository_path(
        repository_root,
        Path(str(existing_current["input_campaign_repository_path"])),
    )
    existing_reference_path = _repository_path(
        repository_root,
        Path(str(existing_current["base_campaign_repository_path"])),
    )
    existing_input_root = existing_input_path.parent
    existing_reference_root = existing_reference_path.parent
    lotss_current = _read_json(lotss_root / "campaign.json")
    lotss_reference_root = lotss_root / "reference-campaign"
    lotss_input_root = lotss_root / "input-campaign"

    existing_cases = [
        str(item["case_id"]) for item in existing_current["results"]
    ]
    lotss_cases = [str(item["case_id"]) for item in lotss_current["results"]]
    all_cases = [*existing_cases, *lotss_cases]
    if len(set(all_cases)) != len(all_cases):
        raise ValueError("aggregate campaign case identifiers overlap")

    for case_id in existing_cases:
        _link_directory(
            existing_input_root / "inputs" / case_id,
            staging / "input-campaign" / "inputs" / case_id,
        )
        _link_directory(
            existing_input_root / "inputs" / case_id,
            staging / "reference-campaign" / "inputs" / case_id,
        )
        _link_directory(
            existing_current_path.parent / "results" / case_id,
            staging / "results" / case_id,
        )
        _link_directory(
            existing_reference_root / "results" / case_id,
            staging / "reference-campaign" / "results" / case_id,
        )
    for case_id in lotss_cases:
        _link_directory(
            lotss_input_root / "inputs" / case_id,
            staging / "input-campaign" / "inputs" / case_id,
        )
        _link_directory(
            lotss_input_root / "inputs" / case_id,
            staging / "reference-campaign" / "inputs" / case_id,
        )
        _link_directory(
            lotss_root / "results" / case_id,
            staging / "results" / case_id,
        )
        _link_directory(
            lotss_reference_root / "results" / case_id,
            staging / "reference-campaign" / "results" / case_id,
        )

    input_campaign = _input_manifest(staging / "input-campaign", all_cases)
    input_manifest_path = staging / "input-campaign" / "campaign.json"
    _write_json(input_manifest_path, input_campaign)

    existing_reference = _read_json(existing_reference_path)
    lotss_reference = _read_json(lotss_reference_root / "campaign.json")
    reference_results = [
        *existing_reference["results"],
        *lotss_reference["results"],
    ]
    reference_campaign = {
        "schema_version": 1,
        "campaign_id": "phase-5-public-plus-lotss-reference-comparison",
        "status": "terminal-derived-results-assembled",
        "case_count": len(all_cases),
        "run_count": len(reference_results),
        "successful_run_count": sum(
            item["status"] == "success" for item in reference_results
        ),
        "scientific_claims_authorized": False,
        "results": reference_results,
    }
    reference_manifest_path = staging / "reference-campaign" / "campaign.json"
    _write_json(reference_manifest_path, reference_campaign)

    current_results = [*existing_current["results"], *lotss_current["results"]]
    request = {
        "schema_version": 1,
        "request_id": "phase-5-current-public-plus-lotss-notebook-view",
        "status": "derived-current-worktree-aggregate",
        "base_campaign_repository_path": _repository_relative(
            repository_root,
            aggregate / "reference-campaign" / "campaign.json",
        ),
        "input_campaign_repository_path": _repository_relative(
            repository_root,
            aggregate / "input-campaign" / "campaign.json",
        ),
        "case_count": len(all_cases),
        "scientific_claims_authorized": False,
    }
    _write_json(staging / "request.json", request)
    campaign = {
        **request,
        "campaign_id": "phase-5-current-public-plus-lotss-comparison",
        "status": "terminal-derived-results-assembled",
        "base_campaign_sha256": _sha256(reference_manifest_path),
        "input_campaign_sha256": _sha256(input_manifest_path),
        "source_tree_sha256": lotss_current["source_tree_sha256"],
        "configuration_sha256": lotss_current["configuration_sha256"],
        "completed_at": datetime.now(UTC).isoformat(),
        "successful_case_count": sum(
            item["status"] == "success" for item in current_results
        ),
        "results": current_results,
    }
    _write_json(staging / "campaign.json", campaign)
    staging.rename(aggregate)


def run_campaign(  # noqa: C901, PLR0915
    *,
    repository_root: Path,
    output: Path,
    aggregate_output: Path,
    existing_current_path: Path,
    reference_identity_path: Path,
    podman_executable: str,
    resume: bool,
) -> None:
    """Acquire, execute, seal, and aggregate the LoTSS comparison."""
    if output.exists():
        if aggregate_output.exists():
            raise FileExistsError(
                f"LoTSS and aggregate campaigns already exist: {output}"
            )
        _build_aggregate(
            repository_root=repository_root,
            lotss_root=output,
            existing_current_path=existing_current_path,
            aggregate=aggregate_output,
        )
        return
    staging = output.parent / f".{output.name}.staging"
    if staging.exists() and not resume:
        raise FileExistsError(
            f"campaign staging exists; pass --resume to continue: {staging}"
        )
    staging.mkdir(parents=True, exist_ok=True)

    source_sha256 = source_tree_sha256(repository_root)
    configuration_sha256 = post_correction_candidate_configuration_sha256(
        repository_root / _BASE_REVIEW
    )
    reference_identity = _read_json(reference_identity_path)
    containers = cast(dict[str, dict[str, str]], reference_identity["containers"])
    request = {
        "schema_version": 1,
        "request_id": "phase-5-lotss-dr2-observational-comparison",
        "status": "isolated-observational-staging",
        "cases": [asdict(case) for case in _CASES],
        "cutout_endpoint": _CUTOUT_ENDPOINT,
        "data_release": "LoTSS DR2",
        "source_tree_sha256": source_sha256,
        "configuration_sha256": configuration_sha256,
        "reference_identity_repository_path": _repository_relative(
            repository_root, reference_identity_path
        ),
        "reference_identity_sha256": _sha256(reference_identity_path),
        "runner_repository_path": str(_RUNNER_PATH),
        "runner_sha256": _sha256(repository_root / _RUNNER_PATH),
        "scientific_claims_authorized": False,
    }
    _write_once(staging / "request.json", request)

    input_root = staging / "input-campaign"
    input_records: dict[str, dict[str, object]] = {}
    for case in _CASES:
        print(f"acquiring {case.case_id}", flush=True)
        input_records[case.case_id] = _acquire_case(input_root, case)
    input_campaign = _input_manifest(
        input_root,
        [case.case_id for case in _CASES],
    )
    _write_json(input_root / "campaign.json", input_campaign)

    runner = runpy.run_path(str(repository_root / _HEBOG_RUNNER))
    run_public_hebog = cast(
        Callable[..., dict[str, object]], runner["run_public_hebog"]
    )
    current_results: list[dict[str, object]] = []
    reference_results: list[dict[str, object]] = []
    for case in _CASES:
        input_path = input_root / str(input_records[case.case_id]["input_path"])
        hebog_output = (
            staging / "results" / case.case_id / "hebog" / "operational"
        )
        hebog_result_path = hebog_output / "result.json"
        if not hebog_result_path.exists():
            print(f"running current Hebog: {case.case_id}", flush=True)
            run_public_hebog(
                input_path=input_path,
                output=hebog_output,
                case_id=case.case_id,
                core=None,
                configuration_sha256=configuration_sha256,
            )
        hebog_result = _read_json(hebog_result_path)
        current_results.append(
            {
                "case_id": case.case_id,
                "finder_id": "hebog",
                "mode": "operational",
                "result_path": str(hebog_result_path.relative_to(staging)),
                "result_sha256": _sha256(hebog_result_path),
                "status": hebog_result["status"],
            }
        )
        for finder_id in _FINDERS:
            reference_output = (
                staging
                / "reference-campaign"
                / "results"
                / case.case_id
                / finder_id
                / "operational"
            )
            reference_result_path = reference_output / "result.json"
            if not reference_result_path.exists():
                identity = containers[finder_id]
                print(f"running {finder_id}: {case.case_id}", flush=True)
                _run_command(
                    _reference_command(
                        repository_root=repository_root,
                        staging=staging,
                        input_path=input_path,
                        output=reference_output,
                        case_id=case.case_id,
                        finder_id=finder_id,
                        image=identity["image"],
                        digest=identity["digest"],
                        podman_executable=podman_executable,
                    )
                )
            reference_result = _read_json(reference_result_path)
            reference_results.append(
                {
                    "case_id": case.case_id,
                    "finder_id": finder_id,
                    "mode": "operational",
                    "result_path": str(
                        reference_result_path.relative_to(
                            staging / "reference-campaign"
                        )
                    ),
                    "result_sha256": _sha256(reference_result_path),
                    "status": reference_result["status"],
                }
            )

    completed_at = datetime.now(UTC).isoformat()
    reference_campaign = {
        "schema_version": 1,
        "campaign_id": "phase-5-lotss-dr2-reference-comparison",
        "status": "terminal-derived-results-sealed",
        "base_campaign_repository_path": _repository_relative(
            repository_root, output / "input-campaign" / "campaign.json"
        ),
        "case_count": len(_CASES),
        "run_count": len(reference_results),
        "successful_run_count": sum(
            item["status"] == "success" for item in reference_results
        ),
        "completed_at": completed_at,
        "scientific_claims_authorized": False,
        "results": reference_results,
    }
    reference_campaign_path = staging / "reference-campaign" / "campaign.json"
    _write_json(reference_campaign_path, reference_campaign)
    campaign = {
        "schema_version": 1,
        "campaign_id": "phase-5-current-lotss-dr2-comparison",
        "status": "terminal-derived-results-sealed",
        "base_campaign_repository_path": _repository_relative(
            repository_root, output / "reference-campaign" / "campaign.json"
        ),
        "base_campaign_sha256": _sha256(reference_campaign_path),
        "input_campaign_repository_path": _repository_relative(
            repository_root, output / "input-campaign" / "campaign.json"
        ),
        "input_campaign_sha256": _sha256(input_root / "campaign.json"),
        "case_count": len(_CASES),
        "successful_case_count": sum(
            item["status"] == "success" for item in current_results
        ),
        "completed_at": completed_at,
        "source_tree_sha256": source_sha256,
        "configuration_sha256": configuration_sha256,
        "scientific_claims_authorized": False,
        "results": current_results,
    }
    _write_json(staging / "campaign.json", campaign)
    if source_tree_sha256(repository_root) != source_sha256:
        raise RuntimeError("Hebog source tree changed during LoTSS execution")
    staging.rename(output)
    _build_aggregate(
        repository_root=repository_root,
        lotss_root=output,
        existing_current_path=existing_current_path,
        aggregate=aggregate_output,
    )
    print(
        json.dumps(
            {
                "aggregate_case_count": len(_CASES)
                + len(_read_json(existing_current_path)["results"]),
                "aggregate_output": str(aggregate_output),
                "lotss_case_count": len(_CASES),
                "lotss_output": str(output),
                "status": campaign["status"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


def main() -> None:
    """Run the isolated LoTSS campaign from command-line arguments."""
    arguments = _parse_args()
    repository_root = cast(Path, arguments.repository_root).resolve()
    run_campaign(
        repository_root=repository_root,
        output=_repository_path(repository_root, cast(Path, arguments.output)),
        aggregate_output=_repository_path(
            repository_root, cast(Path, arguments.aggregate_output)
        ),
        existing_current_path=_repository_path(
            repository_root, cast(Path, arguments.existing_current_campaign)
        ),
        reference_identity_path=_repository_path(
            repository_root, cast(Path, arguments.reference_identity)
        ),
        podman_executable=str(arguments.podman_executable),
        resume=bool(arguments.resume),
    )


if __name__ == "__main__":
    main()
