# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Measure the warm local Phase 1 FITS-to-Zarr-to-FITS path."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypeVar

import numpy as np
import psutil
import zarr
from astropy.io import fits

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.data_models import ProductChunk
from hebog.io import (
    FitsImageSource,
    ZarrProductSink,
    write_mask_fits_product,
    write_rms_fits_product,
)
from hebog.validation.datasets import DatasetRole
from hebog.validation.evidence import (
    BenchmarkEvidence,
    DatasetIdentity,
    EvidenceStatus,
    ExecutorKind,
    Measurement,
    ResourceAllocation,
    RuntimeMetrics,
    SoftwareIdentity,
    StageMetrics,
    StorageEvidence,
    UnavailableMetric,
    WorkloadClass,
    write_evidence,
)

Result = TypeVar("Result")
_MINIMUM_REPETITIONS = 5
_DEPENDENCIES = ("astropy", "hebog", "numpy", "zarr")
_COPY_REASON = (
    "Astropy and Zarr do not expose complete allocation counters; Hebog's "
    "bounded row-copy contract is tested structurally"
)


@dataclass(frozen=True, slots=True)
class _TimedResult:
    """One stage result and its process-level resource observation."""

    value: object
    metrics: RuntimeMetrics


@dataclass(frozen=True, slots=True)
class _RunResult:
    """One complete repetition plus deterministic storage observations."""

    measurement: Measurement
    object_count: int
    zarr_bytes: int
    final_fits_bytes: int
    maximum_row_block_bytes: int
    partition_count: int


def _parse_args() -> argparse.Namespace:
    """Parse one controlled local I/O benchmark configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--size", required=True, type=int)
    parser.add_argument("--tile-size", required=True, type=int)
    parser.add_argument("--warmups", default=1, type=int)
    parser.add_argument("--repetitions", default=5, type=int)
    parser.add_argument(
        "--zarr-concurrency",
        default=int(zarr.config.get("async.concurrency")),
        type=int,
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    """Hash one complete file without loading it as an array."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    """Hash one JSON-compatible value canonically."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


class _ResidentMemorySampler:
    """Sample portable current process RSS during one synchronous stage."""

    def __init__(self) -> None:
        self._peak_bytes = 0
        self._stop = threading.Event()
        self._process = psutil.Process()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _current_bytes(self) -> int:
        return int(self._process.memory_info().rss)

    def _sample(self) -> None:
        while not self._stop.is_set():
            self._peak_bytes = max(self._peak_bytes, self._current_bytes())
            self._stop.wait(0.005)

    def start(self) -> None:
        """Start sampling current resident memory."""
        self._peak_bytes = self._current_bytes()
        self._thread.start()

    def stop(self) -> int:
        """Stop sampling and return the largest observed resident set."""
        self._stop.set()
        self._thread.join()
        return max(self._peak_bytes, self._current_bytes())


def _runtime_metrics(
    *,
    wall_seconds: float,
    cpu_seconds: float,
    peak_rss_bytes: int,
) -> RuntimeMetrics:
    """Create truthful serial metrics with explicit copy unavailability."""
    return RuntimeMetrics(
        wall_seconds=wall_seconds,
        cpu_seconds=cpu_seconds,
        peak_rss_bytes=peak_rss_bytes,
        array_copy_count=None,
        array_copy_bytes=None,
        dask_task_count=0,
        transfer_bytes=0,
        spill_bytes=0,
        unavailable_metrics=(
            UnavailableMetric(
                metric="array_copy_count",
                reason=_COPY_REASON,
            ),
            UnavailableMetric(
                metric="array_copy_bytes",
                reason=_COPY_REASON,
            ),
        ),
    )


def _measure(function: Callable[[], Result]) -> _TimedResult:
    """Measure one already-configured stage."""
    sampler = _ResidentMemorySampler()
    sampler.start()
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    try:
        value = function()
    finally:
        peak_rss_bytes = sampler.stop()
    return _TimedResult(
        value=value,
        metrics=_runtime_metrics(
            wall_seconds=time.perf_counter() - wall_started,
            cpu_seconds=time.process_time() - cpu_started,
            peak_rss_bytes=peak_rss_bytes,
        ),
    )


def _generate_input(path: Path, *, size: int) -> None:
    """Write one deterministic non-negative noise-like radio image."""
    generator = np.random.default_rng(20260801)
    values = generator.normal(
        loc=1.0,
        scale=0.05,
        size=(size, size),
    ).astype(np.float64)
    values[0, 0] = np.nan
    hdu = fits.PrimaryHDU(values)
    hdu.header["BUNIT"] = "Jy/beam"
    hdu.header["BMAJ"] = 0.01
    hdu.header["BMIN"] = 0.008
    hdu.header["BPA"] = 20.0
    hdu.header["RESTFRQ"] = 150_000_000.0
    hdu.header["CTYPE1"] = "RA---SIN"
    hdu.header["CTYPE2"] = "DEC--SIN"
    hdu.header["CUNIT1"] = "deg"
    hdu.header["CUNIT2"] = "deg"
    hdu.header["CDELT1"] = -0.001
    hdu.header["CDELT2"] = 0.001
    hdu.header["CRPIX1"] = 1.0
    hdu.header["CRPIX2"] = 1.0
    hdu.header["CRVAL1"] = 180.0
    hdu.header["CRVAL2"] = -30.0
    hdu.writeto(path, checksum=True)


def _directory_observation(path: Path) -> tuple[int, int]:
    """Return file count and bytes for one local hierarchy."""
    files = tuple(
        candidate for candidate in path.rglob("*") if candidate.is_file()
    )
    return len(files), sum(candidate.stat().st_size for candidate in files)


def _complete_metrics(stages: tuple[StageMetrics, ...]) -> RuntimeMetrics:
    """Combine serial stage timings without fabricating copy counters."""
    return _runtime_metrics(
        wall_seconds=sum(stage.metrics.wall_seconds for stage in stages),
        cpu_seconds=sum(stage.metrics.cpu_seconds for stage in stages),
        peak_rss_bytes=max(stage.metrics.peak_rss_bytes for stage in stages),
    )


def _run_once(  # noqa: PLR0913
    *,
    input_path: Path,
    work_parent: Path,
    size: int,
    tile_size: int,
    repetition_index: int,
    warmup: bool,
) -> _RunResult:
    """Run one isolated serial ingestion and final-materialisation pass."""
    with TemporaryDirectory(dir=work_parent, prefix="run-") as temporary:
        root = Path(temporary)
        source = FitsImageSource(input_path)
        metadata = source.metadata()
        manifest = plan_image_partitions(
            image_shape_yx=metadata.shape_yx,
            tile_core_shape_yx=(tile_size, tile_size),
            halo_yx=(0, 0),
        )
        sink = ZarrProductSink(
            root / "products.zarr",
            manifest,
            generation_id=f"phase-1-io-{repetition_index}",
        )

        def ingest() -> tuple[ProductChunk, ...]:
            chunks: list[ProductChunk] = []
            sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))
            sink.initialize_product(
                product_name="mask", dtype=np.dtype(np.bool_)
            )
            for tile in manifest.tiles:
                window = source.read_window(tile.core_bounds)
                chunks.append(
                    sink.write_chunk(
                        product_name="rms",
                        tile=tile,
                        values=window.values,
                    )
                )
                chunks.append(
                    sink.write_chunk(
                        product_name="mask",
                        tile=tile,
                        values=window.valid_pixels,
                    )
                )
            return sink.publish_generation(
                product_names=("mask", "rms"),
                chunks=chunks,
            ).chunks

        ingestion = _measure(ingest)
        row_block_bytes = (
            min(tile_size, size) * size * np.dtype("<f8").itemsize
        )

        def materialize() -> tuple[int, int]:
            rms = write_rms_fits_product(
                root / "rms.fits",
                metadata,
                sink.iter_completed_row_blocks(
                    "rms",
                    max_block_bytes=row_block_bytes,
                ),
                dtype=np.dtype("<f8"),
                scientific_status="valid",
            )
            mask = write_mask_fits_product(
                root / "mask.fits",
                metadata,
                sink.iter_completed_row_blocks(
                    "mask",
                    max_block_bytes=row_block_bytes,
                ),
            )
            return rms.byte_count, mask.byte_count

        materialisation = _measure(materialize)
        stages = (
            StageMetrics(
                stage="fits-zarr-ingestion", metrics=ingestion.metrics
            ),
            StageMetrics(
                stage="zarr-fits-materialisation",
                metrics=materialisation.metrics,
            ),
        )
        object_count, zarr_bytes = _directory_observation(
            root / "products.zarr"
        )
        final_sizes = materialisation.value
        if not isinstance(
            final_sizes, tuple
        ):  # pragma: no cover - typed callback
            raise TypeError("materialisation did not return output sizes")
        return _RunResult(
            measurement=Measurement(
                repetition_index=repetition_index,
                warmup=warmup,
                complete=_complete_metrics(stages),
                stages=stages,
            ),
            object_count=object_count,
            zarr_bytes=zarr_bytes,
            final_fits_bytes=sum(final_sizes),
            maximum_row_block_bytes=row_block_bytes,
            partition_count=len(manifest.tiles),
        )


def _dependency_inventory() -> dict[str, str]:
    """Return relevant installed distribution versions."""
    return {name: importlib.metadata.version(name) for name in _DEPENDENCIES}


def main() -> None:
    """Run warm repetitions and write one exploratory benchmark document."""
    args = _parse_args()
    if args.size < 1 or args.tile_size < 1:
        raise ValueError("size and tile size must be positive")
    if args.zarr_concurrency < 1:
        raise ValueError("Zarr concurrency must be positive")
    if args.warmups < 1 or args.repetitions < _MINIMUM_REPETITIONS:
        raise ValueError("benchmark requires a warm-up and five measurements")
    captured_at = datetime.now(timezone.utc)
    dependency_inventory = _dependency_inventory()
    dependency_sha256 = _canonical_sha256(dependency_inventory)
    configuration = {
        "size": args.size,
        "tile_size": args.tile_size,
        "warmups": args.warmups,
        "repetitions": args.repetitions,
        "zarr_concurrency": args.zarr_concurrency,
        "dtype": "<f8",
        "codec_pipeline": ["bytes-little", "zstd-level-1", "crc32c"],
    }
    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "dependencies": dependency_inventory,
    }
    try:
        source_commit = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            or None
        )
    except (OSError, subprocess.CalledProcessError):
        source_commit = None
    with TemporaryDirectory(prefix="hebog-phase1-io-") as temporary:
        work_parent = Path(temporary)
        input_path = work_parent / "input.fits"
        _generate_input(input_path, size=args.size)
        with zarr.config.set({"async.concurrency": args.zarr_concurrency}):
            runs = tuple(
                _run_once(
                    input_path=input_path,
                    work_parent=work_parent,
                    size=args.size,
                    tile_size=args.tile_size,
                    repetition_index=index,
                    warmup=index < args.warmups,
                )
                for index in range(args.warmups + args.repetitions)
            )
        last = runs[-1]
        total_memory = int(psutil.virtual_memory().total)
        evidence = BenchmarkEvidence(
            schema_version=1,
            evidence_type="benchmark",
            run_id=(
                f"phase-1-io-{args.size}-"
                f"{captured_at.strftime('%Y%m%d%H%M%S')}"
            ),
            captured_at=captured_at,
            status=EvidenceStatus.EXPLORATORY,
            dataset=DatasetIdentity(
                identifier=f"phase-1-analytic-{args.size}",
                role=DatasetRole.DEVELOPMENT,
                content_sha256=_sha256(input_path),
                shape_yx=(args.size, args.size),
                workload_class=WorkloadClass.NORMAL,
            ),
            configuration_sha256=_canonical_sha256(configuration),
            subject=SoftwareIdentity(
                name="hebog",
                version=importlib.metadata.version("hebog"),
                commit_sha=source_commit,
                dependency_inventory_sha256=dependency_sha256,
            ),
            environment_sha256=_canonical_sha256(environment),
            resources=ResourceAllocation(
                executor=ExecutorKind.SERIAL,
                worker_nodes=1,
                workers_per_node=1,
                threads_per_worker=args.zarr_concurrency,
                allocated_cpu_cores=max(1, os.cpu_count() or 1),
                node_memory_bytes=total_memory,
                worker_memory_limit_bytes=total_memory,
                reserved_headroom_per_node_bytes=0,
                storage_identifier="temporary-local-filesystem",
            ),
            measurements=tuple(run.measurement for run in runs),
            storage=StorageEvidence(
                format_name="zarr-v3",
                library_name="zarr",
                library_version=importlib.metadata.version("zarr"),
                backend_name="LocalStore",
                chunk_shape_yx=(args.tile_size, args.tile_size),
                shard_shape_yx=None,
                codec_pipeline=("bytes-little", "zstd-level-1", "crc32c"),
                fill_value="0",
                missing_chunk_policy="error",
                write_empty_chunks=True,
                object_count=last.object_count,
                stored_bytes=last.zarr_bytes,
                internal_concurrency=args.zarr_concurrency,
                atomic_write_guarantee=(
                    "LocalStore deployment concurrency remains unqualified"
                ),
                conditional_create=True,
            ),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_evidence(args.output, evidence)
        print(
            json.dumps(
                {
                    "evidence": str(args.output),
                    "final_fits_bytes": last.final_fits_bytes,
                    "maximum_row_block_bytes": last.maximum_row_block_bytes,
                    "partition_count": last.partition_count,
                    "zarr_bytes": last.zarr_bytes,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
