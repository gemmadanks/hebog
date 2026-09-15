#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
"""Prepare Hydra, LoTSS and SDC1 notebook inputs and reference results.

Cases, downloads and reference-finder options come from
``config/comparisons/notebook-comparison.json``. Requires local Podman images.
--dry-run performs no downloads, container operations or writes. Run Hebog
separately with ``refresh_public_notebook_hebog.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import runpy
import shutil
import subprocess
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from hebog.validation.external_runners import source_tree_sha256

_ROOT = Path(__file__).resolve().parents[2]
_CONFIGURATION = "config/comparisons/notebook-comparison.json"
_FINDERS = ("released-pybdsf", "aegean")
_WORKER = "scripts/benchmark/run_notebook_reference.py"
_CONTAINER_RECIPES = "scripts/benchmark/containers/reference-finders"
_PROGRAMS = (
    "prepare_notebook_comparison.py",
    "run_notebook_reference.py",
    "download_notebook_data.py",
)
_IMAGE_DIMENSIONS = 2
_DEFAULT_REFERENCE_FREQUENCY_HZ = 144_000_000.0
_LOTSS_PRESERVED_HEADER_KEYS = (
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


def _comparison_cases() -> dict[str, dict[str, Any]]:
    """Return the configured cases in SDC1, then whole-image order."""
    configuration = json.loads((_ROOT / _CONFIGURATION).read_text())
    sdc1 = configuration["sdc1"]
    cases = {
        f"sdc1-{item['stratum']}-{item['tile_id']}": {
            "download": sdc1["download"],
            "bounds_xy": item["bounds_xy_half_open"],
            "halo_pixels": sdc1["halo_pixels"],
        }
        for item in sdc1["tiles"]
    }
    cases.update(
        {
            item["case_id"]: {
                "download": item["download"],
                "normalisation": item["normalisation"],
            }
            for item in configuration["whole_image_cases"]
        }
    )
    return cases


def _sdc1_cutout_header(
    header: fits.Header,
    *,
    x_start: int,
    y_start: int,
) -> fits.Header:
    """Translate a full-image WCS to one bounded halo cutout."""
    shifted = header.copy()
    shifted["CRPIX1"] = float(cast(Any, shifted["CRPIX1"])) - x_start
    shifted["CRPIX2"] = float(cast(Any, shifted["CRPIX2"])) - y_start
    if shifted.get("BPA") is None:
        shifted["BPA"] = 0.0
    if shifted.get("RESTFRQ", shifted.get("RESTFREQ")) is None:
        shifted["RESTFRQ"] = 1.4e9
    return shifted


def _write_sdc1_cutout(
    *,
    source: Path,
    destination: Path,
    bounds_xy: list[int],
    halo_pixels: int,
) -> list[int]:
    """Write one haloed SDC1 cutout and return its local output core.

    ``bounds_xy`` is ``[x_start, x_stop, y_start, y_stop]`` in full-image
    pixels; the returned core is ``[y_start, y_stop, x_start, x_stop]``
    within the written cutout. The halo is clipped at image edges.
    """
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
        header = _sdc1_cutout_header(
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


def _reference_frequency_hz(
    header: fits.Header, source_header: fits.Header
) -> float:
    """Return the first finite positive LoTSS reference frequency in Hz."""
    candidates: list[object] = [header.get("RESTFRQ"), header.get("RESTFREQ")]
    spectral_wcs = WCS(source_header, relax=True).spectral
    if spectral_wcs.pixel_n_dim == 1:
        candidates.append(spectral_wcs.wcs.crval[0])
    for candidate in candidates:
        try:
            frequency_hz = float(cast(Any, candidate))
        except (TypeError, ValueError):
            continue
        if np.isfinite(frequency_hz) and frequency_hz > 0.0:
            return frequency_hz
    return _DEFAULT_REFERENCE_FREQUENCY_HZ


def _normalise_lotss_image(download: Path, destination: Path) -> None:
    """Write a canonical two-dimensional LoTSS plane with celestial WCS.

    Released PyBDSF reads ``RESTFREQ`` while the cutout service may supply
    only the WCS ``RESTFRQ`` spelling, so both are written. A finite positive
    header frequency is kept; otherwise the spectral axis value is used when
    present, then the LoTSS 144 MHz centre frequency.
    """
    with fits.open(download, memmap=False) as hdul:
        source_header = hdul[0].header.copy()
        plane = np.squeeze(np.asarray(hdul[0].data))
    if plane.ndim != _IMAGE_DIMENSIONS or not np.issubdtype(
        plane.dtype, np.number
    ):
        raise ValueError(
            f"LoTSS cutout is not one numeric image plane: {plane.shape}"
        )
    if not np.any(np.isfinite(plane)):
        raise ValueError("LoTSS cutout contains no finite pixels")
    header = WCS(source_header, relax=True).celestial.to_header(relax=True)
    for key in _LOTSS_PRESERVED_HEADER_KEYS:
        if key in source_header:
            header[key] = source_header[key]
    frequency_hz = _reference_frequency_hz(header, source_header)
    for key, comment in (
        ("RESTFRQ", "Reference frequency [Hz]"),
        ("RESTFREQ", "Reference frequency [Hz]; released PyBDSF spelling"),
    ):
        if header.get(key) != frequency_hz:
            header[key] = (frequency_hz, comment)
    header["HISTORY"] = "Canonical 2D plane frozen by Hebog LoTSS campaign"
    fits.PrimaryHDU(data=plane, header=header).writeto(
        destination,
        checksum=True,
        output_verify="fix",
    )


def _materialize_input(
    source: Path, destination: Path, case: dict[str, Any]
) -> list[int] | None:
    """Write one SDC1 halo cutout or normalized LoTSS plane atomically."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".input-", dir=destination.parent) as raw:
        temporary = Path(raw) / "input.fits"
        if "bounds_xy" in case:
            core = _write_sdc1_cutout(
                source=source,
                destination=temporary,
                bounds_xy=case["bounds_xy"],
                halo_pixels=case["halo_pixels"],
            )
        elif case.get("normalisation") == "lotss-celestial-plane":
            _normalise_lotss_image(source, temporary)
            core = None
        else:
            raise ValueError(f"unsupported input normalisation: {case}")
        temporary.replace(destination)
    return core


def _build_images(engine: str, images: dict[str, str]) -> None:
    """Build local notebook reference images from the checked-in recipes."""
    recipes = _ROOT / _CONTAINER_RECIPES
    packages = (
        ("bdsf", "1.14.1", "bdsf-1.14.1.tar.gz"),
        ("AegeanTools", "2.3.5", "aegeantools-2.3.5-py3-none-any.whl"),
    )
    with TemporaryDirectory(prefix="hebog-notebook-build-") as raw:
        context = Path(raw)
        for source in recipes.glob("requirements-*.txt"):
            shutil.copy2(source, context / source.name)
        for name in ("Containerfile.pybdsf", "Containerfile.aegean"):
            shutil.copy2(recipes / name, context / name)
        for package, version, filename in packages:
            with urllib.request.urlopen(
                f"https://pypi.org/pypi/{package}/{version}/json",
                timeout=120,
            ) as response:
                release = json.load(response)
            artifact = next(
                item
                for item in release["urls"]
                if item["filename"] == filename
            )
            _download(artifact["url"], context / filename)
            if _sha256(context / filename) != artifact["digests"]["sha256"]:
                raise ValueError(
                    f"package download checksum mismatch: {filename}"
                )
        # Each Containerfile also checks its fixed package checksum. The
        # released target does not need the historical master wheel.
        for finder, recipe in zip(_FINDERS, ("pybdsf", "aegean"), strict=True):
            command = [
                engine,
                "build",
                "--file",
                str(context / f"Containerfile.{recipe}"),
                "--tag",
                images[finder],
                "--label",
                "org.hebog.purpose=notebook-diagnostic",
            ]
            if finder == "released-pybdsf":
                command += ["--target", "released"]
            subprocess.run([*command, str(context)], check=True)


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _write_once(path: Path, value: object) -> None:
    """Publish metadata atomically, or verify an unchanged resume record."""
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError(f"resume metadata changed: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _download_inventory() -> dict[str, Any]:
    helper = runpy.run_path(
        str(_ROOT / "scripts/benchmark/download_notebook_data.py")
    )
    return {item.name: item for item in helper["available_downloads"](_ROOT)}


def _download(url: str, destination: Path) -> None:
    helper = runpy.run_path(
        str(_ROOT / "scripts/benchmark/download_notebook_data.py")
    )
    helper["download_image"](url, destination, overwrite=False)


def _program_identity() -> str:
    """Bind current adapters/settings for a safe interrupted-run resume."""
    hashes = [_sha256(Path(__file__).with_name(name)) for name in _PROGRAMS]
    hashes.append(source_tree_sha256(_ROOT))
    hashes.append(_sha256(_ROOT / _CONFIGURATION))
    return hashlib.sha256("".join(hashes).encode()).hexdigest()


def _inspect_images(engine: str, images: dict[str, str]) -> dict[str, str]:
    """Resolve local images to immutable IDs; never pull or start a VM."""
    identities = {}
    for finder in _FINDERS:
        result = subprocess.run(
            [engine, "image", "inspect", images[finder]],
            check=True,
            capture_output=True,
            text=True,
        )
        records = json.loads(result.stdout)
        identifier = records[0].get("Id", "") if len(records) == 1 else ""
        if not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", identifier):
            raise ValueError(f"no immutable local image ID for {finder}")
        identities[finder] = identifier
    return identities


def _run_container(  # noqa: PLR0913
    *,
    repository_root: Path,
    comparison_root: Path,
    engine: str,
    image: str,
    input_path: Path,
    output: Path,
    case_id: str,
    finder_id: str,
    ncores: int,
    core: list[int] | None = None,
) -> None:
    """Run one finder serially with local-only images and bounded threads."""
    command = [
        engine,
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--userns=keep-id:uid=0,gid=0",
        "--cpus",
        str(ncores),
        "--volume",
        f"{repository_root}:/repository:ro",
        "--volume",
        f"{comparison_root}:/comparison:rw",
        "--workdir",
        "/comparison",
        "--entrypoint",
        "python3",
        "--env",
        "PYTHONPATH=/repository/src",
    ]
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMBA_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        command += ["--env", f"{name}=1"]
    command += [
        image,
        f"/repository/{_WORKER}",
        "--input",
        f"/repository/{input_path.relative_to(repository_root)}",
        "--output",
        f"/comparison/{output.relative_to(comparison_root)}",
        "--case-id",
        case_id,
        "--finder-id",
        finder_id,
        "--container-image-id",
        image,
        "--ncores",
        str(ncores),
    ]
    if core is not None:
        command += ["--core", *(str(value) for value in core)]
    subprocess.run(command, check=True)


def _verify_result(
    path: Path,
    *,
    case_id: str,
    finder: str,
    input_sha256: str,
    image: str,
) -> dict[str, Any]:
    """Reject incomplete or mismatched products before reuse/publication."""
    result = json.loads(path.read_text())
    expected = {
        "status": "success",
        "case_id": case_id,
        "finder_id": finder,
        "mode": "operational",
        "input_sha256": input_sha256,
        "container_image_id": image,
    }
    if any(result.get(key) != value for key, value in expected.items()):
        raise ValueError(f"reference result identity/status changed: {path}")
    artifacts = result.get("artifacts", {})
    required = (
        {
            "source-catalogue-fits",
            "gaussian-catalogue-fits",
            "island-labels-fits",
            "island-mask-fits",
        }
        if finder == "released-pybdsf"
        else {
            "component-catalogue-fits",
            "island-catalogue-fits",
            "support-proxy-labels-fits",
            "catalogue-exclusions-json",
        }
    ) | {"comparison-catalogue-json"}
    if not required <= artifacts.keys():
        raise ValueError(f"missing reference artifact: {path}")
    for item in artifacts.values():
        artifact = (path.parent / item["path"]).resolve()
        if (
            not artifact.is_relative_to(path.parent.resolve())
            or not artifact.is_file()
            or artifact.stat().st_size != item["byte_size"]
            or _sha256(artifact) != item["sha256"]
        ):
            raise ValueError(
                f"reference artifact changed or missing: {artifact}"
            )
    return result


def _prepare_input(  # noqa: PLR0913
    *,
    repository_root: Path,
    output: Path,
    name: str,
    download: Any,
    case: dict[str, Any],
    sources: dict[str, tuple[Path, str]],
) -> tuple[Path, dict[str, Any]]:
    source = (
        repository_root / "benchmark-results/notebook-data" / download.filename
    )
    record_path = output / "input-campaign/inputs" / name / "input.json"
    if case["download"] not in sources:
        if not record_path.exists() or not source.exists():
            _download(download.url, source)
        sources[case["download"]] = (source, _sha256(source))
    source, source_sha256 = sources[case["download"]]
    if record_path.exists():
        record = json.loads(record_path.read_text())
        image = repository_root / record["input_path"]
        if (
            not image.resolve().is_relative_to(repository_root)
            or record["source_sha256"] != source_sha256
            or record["input_sha256"] != _sha256(image)
        ):
            raise ValueError("resume input or source changed")
    else:
        image, core = source, None
        if case.get("normalisation") != "none":
            image = record_path.parent / "input.fits"
            core = _materialize_input(source, image, case)
        record = {
            "case_id": name,
            "input_location": "repository",
            "input_path": str(image.relative_to(repository_root)),
            "input_sha256": _sha256(image),
            "local_core_yx_half_open": core,
            "source_url": download.url,
            "source_sha256": source_sha256,
        }
    for campaign in ("input-campaign", "reference-campaign"):
        _write_once(output / campaign / "inputs" / name / "input.json", record)
    return image, record


def _check_output(
    repository_root: Path, output: Path, *, resume: bool
) -> None:
    """Protect existing work before starting containers or downloads."""
    if not output.is_relative_to(repository_root) or output == repository_root:
        raise ValueError("comparison output must be inside the checkout")
    if output.exists() and not resume:
        raise FileExistsError(
            f"output exists; use --resume or a new path: {output}"
        )
    if resume and not (output / "request.json").is_file():
        raise FileNotFoundError("no setup request to resume")


def prepare_comparison(  # noqa: PLR0913
    *,
    repository_root: Path,
    output: Path,
    datasets: tuple[str, ...],
    images: dict[str, str],
    engine: str = "podman",
    ncores: int = 2,
    resume: bool = False,
    dry_run: bool = False,
    build_images: bool = False,
) -> dict[str, Any]:
    """Prepare downloads and paired reference results for the notebook."""
    cases = _comparison_cases()
    selected = tuple(dict.fromkeys(datasets or cases))
    if set(selected) - set(cases) or ncores < 1:
        raise ValueError(
            "select supported comparison cases and positive ncores"
        )
    if set(images) != set(_FINDERS) or not all(images.values()):
        raise ValueError("provide both local PyBDSF and Aegean images")
    inventory = _download_inventory()
    plan = {
        "datasets": list(selected),
        "output": str(output),
        "images": images,
        "ncores": ncores,
        "build_images": build_images,
        "downloads": [
            inventory[name].url
            for name in dict.fromkeys(
                cases[name]["download"] for name in selected
            )
        ],
        "cases": {name: cases[name] for name in selected},
    }
    if dry_run:
        return {**plan, "status": "dry-run"}
    repository_root, output = repository_root.resolve(), output.resolve()
    _check_output(repository_root, output, resume=resume)
    if build_images:
        if resume:
            raise ValueError(
                "resume uses existing images; omit --build-images"
            )
        _build_images(engine, images)
    identities = _inspect_images(engine, images)
    request = {
        "schema_version": 1,
        "datasets": list(selected),
        "downloads": plan["downloads"],
        "containers": identities,
        "ncores": ncores,
        "program_sha256": _program_identity(),
        "scientific_claims_authorized": False,
    }
    output.mkdir(parents=True, exist_ok=resume)
    _write_once(output / "request.json", request)
    references = output / "reference-campaign"
    _write_once(references / "request.json", request)
    inputs, results = [], []
    sources: dict[str, tuple[Path, str]] = {}
    for name in selected:
        image, record = _prepare_input(
            repository_root=repository_root,
            output=output,
            name=name,
            download=inventory[cases[name]["download"]],
            case=cases[name],
            sources=sources,
        )
        inputs.append({"case_id": name, "status": "success"})
        for finder in _FINDERS:
            destination = (
                references / "results" / name / finder / "operational"
            )
            result_path = destination / "result.json"
            if not result_path.exists():
                print(f"Running {finder}: {name}", flush=True)
                _run_container(
                    repository_root=repository_root,
                    comparison_root=output,
                    engine=engine,
                    image=identities[finder],
                    input_path=image,
                    output=destination,
                    case_id=name,
                    finder_id=finder,
                    ncores=ncores,
                    core=record["local_core_yx_half_open"],
                )
            _verify_result(
                result_path,
                case_id=name,
                finder=finder,
                input_sha256=str(record["input_sha256"]),
                image=identities[finder],
            )
            results.append(
                {
                    "case_id": name,
                    "finder_id": finder,
                    "mode": "operational",
                    "status": "success",
                    "result_path": str(result_path.relative_to(references)),
                    "result_sha256": _sha256(result_path),
                }
            )
    if request["program_sha256"] != _program_identity():
        raise RuntimeError("notebook setup programs changed during execution")
    common = {
        "schema_version": 1,
        "status": "terminal-derived-results-sealed",
        "scientific_claims_authorized": False,
        "case_count": len(inputs),
    }
    _write_once(
        output / "input-campaign/campaign.json", {**common, "results": inputs}
    )
    _write_once(
        references / "campaign.json",
        {
            **common,
            "results": results,
            "run_count": len(results),
            "successful_run_count": len(results),
        },
    )
    return {**plan, "status": "ready", "campaign_root": str(references)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=_ROOT / "benchmark-results/notebook-comparison",
    )
    parser.add_argument(
        "--dataset", choices=tuple(_comparison_cases()), action="append"
    )
    parser.add_argument(
        "--pybdsf-image", default="localhost/hebog-notebook-pybdsf:1.14.1"
    )
    parser.add_argument(
        "--aegean-image", default="localhost/hebog-notebook-aegean:2.3.5"
    )
    parser.add_argument(
        "--build-images",
        action="store_true",
        help="Build images first (downloads packages and OCI layers)",
    )
    parser.add_argument("--podman-executable", default="podman")
    parser.add_argument("--ncores", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            prepare_comparison(
                repository_root=_ROOT,
                output=args.output,
                datasets=tuple(args.dataset or ()),
                images={
                    "released-pybdsf": args.pybdsf_image,
                    "aegean": args.aegean_image,
                },
                engine=args.podman_executable,
                ncores=args.ncores,
                resume=args.resume,
                dry_run=args.dry_run,
                build_images=args.build_images,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
