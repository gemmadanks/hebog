"""Run one instrumented Rapthor/LSMTool PyBDSF reference invocation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

import numpy as np

Result = TypeVar("Result")


def _configuration(
    detection_threshold_sigma: float,
    island_threshold_sigma: float,
) -> dict[str, object]:
    """Build the explicit scientific profile for one baseline campaign."""
    if not (
        detection_threshold_sigma > 0
        and 0 < island_threshold_sigma <= detection_threshold_sigma
    ):
        raise ValueError("thresholds must satisfy 0 < island <= detection")
    return {
        "adaptive_rms_box": True,
        "adaptive_threshold": 75.0,
        "atrous_do": True,
        "atrous_jmax": 3,
        "filter_by_mask": True,
        "mean_map": "zero",
        "rms_box": [150, 50],
        "rms_box_bright": [35, 7],
        "rms_map": True,
        "threshold_island_sigma": island_threshold_sigma,
        "threshold_pixel_sigma": detection_threshold_sigma,
        "threshold_type": "hard",
    }


def _canonical_sha256(value: object) -> str:
    """Hash one JSON-compatible value using canonical separators."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    """Hash a file without retaining it in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _usage_seconds() -> tuple[float, float]:
    """Return cumulative process and child user/system CPU seconds."""
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + children.ru_utime, own.ru_stime + children.ru_stime


def _maximum_rss_bytes() -> int:
    """Return the largest reported resident set for this process or a child."""
    own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    children = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return int(max(own, children) * 1024)


class _ResidentMemorySampler:
    """Sample current parent RSS while one synchronous stage runs."""

    def __init__(self) -> None:
        self.peak_bytes = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        status_path = Path("/proc/self/status")
        while not self._stop.is_set():
            try:
                status = status_path.read_text(encoding="utf-8")
                resident_line = next(
                    line
                    for line in status.splitlines()
                    if line.startswith("VmRSS:")
                )
                resident_bytes = int(resident_line.split()[1]) * 1024
                self.peak_bytes = max(self.peak_bytes, resident_bytes)
            except (FileNotFoundError, StopIteration, ValueError):
                self.peak_bytes = max(self.peak_bytes, _maximum_rss_bytes())
            self._stop.wait(0.01)

    def start(self) -> None:
        """Start background RSS sampling."""
        self._thread.start()

    def stop(self) -> int:
        """Stop sampling and return the largest observed value."""
        self._stop.set()
        self._thread.join()
        return max(self.peak_bytes, _maximum_rss_bytes())


def _measure(
    function: Callable[[], Result],
) -> tuple[Result, dict[str, object]]:
    """Measure one synchronous callable including completed child CPU time."""
    user_start, system_start = _usage_seconds()
    sampler = _ResidentMemorySampler()
    sampler.start()
    wall_start = time.perf_counter()
    result = function()
    wall_seconds = time.perf_counter() - wall_start
    peak_rss_bytes = sampler.stop()
    user_end, system_end = _usage_seconds()
    user_seconds = user_end - user_start
    system_seconds = system_end - system_start
    return result, {
        "cpu_seconds": user_seconds + system_seconds,
        "peak_rss_bytes": peak_rss_bytes,
        "system_seconds": system_seconds,
        "user_seconds": user_seconds,
        "wall_seconds": wall_seconds,
    }


def _dependency_inventory() -> list[dict[str, object]]:
    """Capture every installed distribution, including direct-URL metadata."""
    inventory = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        direct_url_text = distribution.read_text("direct_url.json")
        direct_url = None
        if direct_url_text is not None:
            direct_url = json.loads(direct_url_text)
        inventory.append(
            {
                "direct_url": direct_url,
                "name": name.lower().replace("_", "-"),
                "version": distribution.version,
            }
        )
    return sorted(inventory, key=lambda item: str(item["name"]))


def _system_environment() -> dict[str, object]:
    """Capture stable local resource and interpreter facts."""
    memory_bytes = 0
    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        first_line = meminfo_path.read_text(encoding="utf-8").splitlines()[0]
        memory_bytes = int(first_line.split()[1]) * 1024
    return {
        "cpu_count": os.cpu_count(),
        "machine": platform.machine(),
        "node_memory_bytes": memory_bytes,
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


def _copy_optional(path: Path | None, destination: Path) -> Path:
    """Copy an optional input or return a deliberately absent path."""
    if path is None:
        return destination
    shutil.copyfile(path, destination)
    return destination


def _artifact_manifest(output_directory: Path) -> dict[str, object]:
    """Describe all standardized products emitted by this invocation."""
    artifact_names = (
        "apparent_sky.txt",
        "diagnostics.json",
        "flat_noise_rms.fits",
        "source_catalog.fits",
        "source_filter_mask.fits",
        "true_sky.txt",
        "true_sky_rms.fits",
    )
    artifacts: dict[str, object] = {}
    for name in artifact_names:
        path = output_directory / name
        artifacts[name] = {
            "bytes": path.stat().st_size,
            "sha256": _file_sha256(path),
        }
    return artifacts


def _parse_args() -> argparse.Namespace:
    """Parse one isolated reference-run request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flat-noise-image", required=True, type=Path)
    parser.add_argument("--true-sky-image", required=True, type=Path)
    parser.add_argument("--true-skymodel", type=Path)
    parser.add_argument("--apparent-skymodel", type=Path)
    parser.add_argument("--vertices", type=Path)
    parser.add_argument("--beam-ms", action="append", default=[], type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument(
        "--reference", choices=("release", "master"), required=True
    )
    parser.add_argument("--reference-commit", required=True)
    parser.add_argument("--reference-version", required=True)
    parser.add_argument("--rapthor-commit", required=True)
    parser.add_argument("--lsmtool-commit", required=True)
    parser.add_argument("--lsmtool-module-sha256", required=True)
    parser.add_argument("--container-image-digest", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument(
        "--detection-threshold-sigma", required=True, type=float
    )
    parser.add_argument("--island-threshold-sigma", required=True, type=float)
    parser.add_argument("--repetition-index", required=True, type=int)
    parser.add_argument("--warmup", action="store_true")
    parser.add_argument("--ncores", default=4, type=int)
    return parser.parse_args()


def _validate_stages(
    stages: list[dict[str, object]], *, has_beam: bool
) -> None:
    """Reject an unexpected number of instrumented PyBDSF calls."""
    expected_stage_count = 2 if has_beam else 1
    if len(stages) != expected_stage_count:
        raise RuntimeError(
            "unexpected PyBDSF call count: "
            f"expected {expected_stage_count}, observed {len(stages)}"
        )


def _verify_runtime_identity(
    args: argparse.Namespace,
    lsmtool_bdsf: Any,
    filter_image_skymodel: Callable[..., None],
) -> tuple[str, dict[str, object]]:
    """Verify imported code and return its version and explicit profile."""
    rapthor_module = Path(filter_image_skymodel.__code__.co_filename).resolve()
    if not rapthor_module.is_relative_to("/rapthor"):
        raise RuntimeError(
            "Rapthor was not imported from the mounted checkout: "
            f"{rapthor_module}"
        )
    lsmtool_module = Path(lsmtool_bdsf.__file__).resolve()
    if _file_sha256(lsmtool_module) != args.lsmtool_module_sha256:
        raise RuntimeError("installed LSMTool source does not match the pin")
    reference_version = importlib.metadata.version("bdsf")
    if reference_version != args.reference_version:
        raise RuntimeError(
            "installed PyBDSF version does not match the pin: "
            f"expected {args.reference_version}, observed {reference_version}"
        )
    configuration = _configuration(
        args.detection_threshold_sigma,
        args.island_threshold_sigma,
    )
    return reference_version, configuration


def _run(args: argparse.Namespace) -> dict[str, object]:
    """Run the complete compatibility path with PyBDSF call instrumentation."""
    # These exist only inside the isolated reference container.
    from lsmtool.filter_skymodel import bdsf as lsmtool_bdsf  # noqa: PLC0415
    from rapthor.execution.image.skymodel_filter import (  # noqa: PLC0415
        filter_image_skymodel,
    )

    reference_version, configuration = _verify_runtime_identity(
        args,
        lsmtool_bdsf,
        filter_image_skymodel,
    )

    output_directory: Path = args.output_directory
    output_directory.mkdir(parents=True, exist_ok=False)
    # Keep generated product metadata independent of the repetition number.
    # Every repetition runs in a fresh container, so this fixed path is both
    # isolated and reproducible.
    work_directory = Path("/tmp/hebog-pybdsf-reference")
    work_directory.mkdir()
    flat_noise_image = work_directory / "flat_noise_image.fits"
    true_sky_image = work_directory / "true_sky_image.fits"
    shutil.copyfile(args.flat_noise_image, flat_noise_image)
    shutil.copyfile(args.true_sky_image, true_sky_image)
    true_skymodel = _copy_optional(
        args.true_skymodel,
        work_directory / "input_true_sky.txt",
    )
    apparent_skymodel = _copy_optional(
        args.apparent_skymodel,
        work_directory / "input_apparent_sky.txt",
    )
    vertices = _copy_optional(
        args.vertices,
        work_directory / "vertices.npy",
    )
    if args.vertices is None:
        np.save(vertices, np.array([[0.0, 0.0]], dtype=np.float64))

    stages: list[dict[str, object]] = []
    processed_images: list[Any] = []
    original_process_image = lsmtool_bdsf.bdsf.process_image

    def instrumented_process_image(
        *positional: object, **keywords: object
    ) -> Any:
        stage_name = (
            "true-sky-pybdsf"
            if args.beam_ms and not stages
            else "flat-noise-pybdsf"
        )
        image, metrics = _measure(
            lambda: original_process_image(*positional, **keywords)
        )
        stages.append({"stage": stage_name, "metrics": metrics})
        processed_images.append(image)
        return image

    lsmtool_bdsf.bdsf.process_image = instrumented_process_image
    started_at = datetime.now(timezone.utc)
    standardized_mask = work_directory / "source_filter_mask.fits"

    def run_complete_path() -> None:
        filter_image_skymodel(
            str(flat_noise_image),
            str(true_sky_image),
            str(true_skymodel),
            str(apparent_skymodel),
            str(work_directory / "products"),
            str(vertices),
            [str(path) for path in args.beam_ms],
            threshisl=configuration["threshold_island_sigma"],
            threshpix=configuration["threshold_pixel_sigma"],
            rmsbox=tuple(configuration["rms_box"]),
            rmsbox_bright=tuple(configuration["rms_box_bright"]),
            adaptive_thresh=configuration["adaptive_threshold"],
            filter_by_mask=configuration["filter_by_mask"],
            ncores=args.ncores,
            source_finder="bdsf",
        )
        processed_image = true_sky_image if args.beam_ms else flat_noise_image
        compatibility_mask = Path(f"{processed_image}.mask.fits")
        if compatibility_mask.exists():
            shutil.copyfile(compatibility_mask, standardized_mask)
        else:
            processed_images[0].export_image(
                outfile=str(standardized_mask),
                clobber=True,
                img_type="island_mask",
            )

    try:
        _, complete_metrics = _measure(run_complete_path)
    finally:
        lsmtool_bdsf.bdsf.process_image = original_process_image

    _validate_stages(stages, has_beam=bool(args.beam_ms))

    product_root = work_directory / "products"
    product_sources: Mapping[str, Path] = {
        "apparent_sky.txt": product_root.with_suffix(".apparent_sky.txt"),
        "diagnostics.json": product_root.with_suffix(
            ".image_diagnostics.json"
        ),
        "flat_noise_rms.fits": product_root.with_suffix(
            ".flat_noise_rms.fits"
        ),
        "source_catalog.fits": product_root.with_suffix(
            ".source_catalog.fits"
        ),
        "true_sky.txt": product_root.with_suffix(".true_sky.txt"),
        "true_sky_rms.fits": product_root.with_suffix(".true_sky_rms.fits"),
    }
    for name, source in product_sources.items():
        shutil.copyfile(source, output_directory / name)
    shutil.copyfile(
        standardized_mask,
        output_directory / "source_filter_mask.fits",
    )

    dependency_inventory = _dependency_inventory()
    environment = _system_environment()

    document = {
        "artifacts": _artifact_manifest(output_directory),
        "captured_at": started_at.isoformat(),
        "complete": complete_metrics,
        "configuration": configuration,
        "configuration_sha256": _canonical_sha256(configuration),
        "container_image_digest": args.container_image_digest,
        "dataset": {
            "flat_noise_sha256": _file_sha256(args.flat_noise_image),
            "identifier": args.dataset_id,
            "true_sky_sha256": _file_sha256(args.true_sky_image),
        },
        "dependency_inventory": dependency_inventory,
        "dependency_inventory_sha256": _canonical_sha256(dependency_inventory),
        "environment": environment,
        "environment_sha256": _canonical_sha256(environment),
        "instrumentation": {
            "array_copies": "unavailable: external PyBDSF has no copy counter",
            "dask": "not applicable: one external process, no Dask executor",
            "peak_rss": (
                "maximum of parent sampling and RUSAGE_SELF/RUSAGE_CHILDREN; "
                "child maximum is not aggregate worker RSS"
            ),
        },
        "ncores": args.ncores,
        "reference": args.reference,
        "repetition_index": args.repetition_index,
        "schema_version": 1,
        "software": {
            "bdsf": {
                "commit": args.reference_commit,
                "version": reference_version,
            },
            "lsmtool": {
                "commit": args.lsmtool_commit,
                "version": importlib.metadata.version("lsmtool"),
            },
            "rapthor": {"commit": args.rapthor_commit},
        },
        "stages": stages,
        "warmup": args.warmup,
    }
    (output_directory / "run.json").write_text(
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document


def main() -> None:
    """Execute and report one isolated reference repetition."""
    document = _run(_parse_args())
    print(
        json.dumps(
            {
                "bdsf": document["software"]["bdsf"],
                "complete": document["complete"],
                "reference": document["reference"],
                "repetition_index": document["repetition_index"],
                "stages": document["stages"],
                "warmup": document["warmup"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
