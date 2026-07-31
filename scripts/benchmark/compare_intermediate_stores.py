#!/usr/bin/env python3
"""Compare the Phase 1 Zarr prototype with the NumPy-file oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Callable

import numpy as np
import numpy.typing as npt
import zarr

from hebog.data_models import PartitionManifest
from hebog.data_models.products import ProductChunk, ZarrProductChunk
from hebog.io import FilesystemProductSink, ZarrProductSink
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

_MINIMUM_REPETITIONS = 5

try:
    import resource
except ModuleNotFoundError:
    resource = None


@dataclass(frozen=True, slots=True)
class _ObservedRun:
    """Measured repetitions plus the final store footprint."""

    measurements: tuple[Measurement, ...]
    object_count: int
    stored_bytes: int


@dataclass(frozen=True, slots=True)
class _EvidenceContext:
    """Provenance shared by both sides of one matched comparison."""

    dataset: DatasetIdentity
    configuration_sha256: str
    environment_sha256: str
    dependency_sha256: str
    source_tree_sha256: str
    resources: ResourceAllocation


@dataclass(frozen=True, slots=True)
class _EvidenceSubject:
    """Identity unique to one side of the matched comparison."""

    run_id: str
    subject_name: str
    related_software: tuple[SoftwareIdentity, ...] = ()


def _parse_args() -> argparse.Namespace:
    """Parse one reproducible local-store probe configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--chunk-height", type=int, default=256)
    parser.add_argument("--chunk-width", type=int, default=256)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260731)
    return parser.parse_args()


def _sha256_bytes(payload: bytes) -> str:
    """Return one lowercase SHA-256 digest."""
    return hashlib.sha256(payload).hexdigest()


def _canonical_sha256(payload: object) -> str:
    """Hash one deterministic JSON representation."""
    return _sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )


def _source_tree_sha256(root: Path) -> str:
    """Hash source paths and bytes in deterministic order."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _peak_rss_bytes() -> int:
    """Return the process peak RSS on controlled POSIX benchmark hosts."""
    if resource is None:
        raise RuntimeError(
            "the intermediate-store probe requires POSIX RSS instrumentation"
        )
    maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(maximum_rss if sys.platform == "darwin" else maximum_rss * 1024)


def _node_memory_bytes() -> int:
    """Return installed physical memory on the controlled local host."""
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError) as error:
        raise RuntimeError(
            "the intermediate-store probe cannot determine node memory"
        ) from error


def _metrics(
    *,
    wall_seconds: float,
    cpu_seconds: float,
) -> RuntimeMetrics:
    """Build complete exploratory metrics without fabricated copy counts."""
    return RuntimeMetrics(
        wall_seconds=wall_seconds,
        cpu_seconds=cpu_seconds,
        peak_rss_bytes=_peak_rss_bytes(),
        array_copy_count=None,
        array_copy_bytes=None,
        dask_task_count=0,
        transfer_bytes=0,
        spill_bytes=0,
        unavailable_metrics=(
            UnavailableMetric(
                metric="array_copy_count",
                reason=(
                    "the local store probe does not instrument NumPy copies"
                ),
            ),
            UnavailableMetric(
                metric="array_copy_bytes",
                reason=(
                    "the local store probe does not instrument NumPy copies"
                ),
            ),
        ),
    )


def _timed(operation: Callable[[], None]) -> RuntimeMetrics:
    """Measure one complete synchronous stage."""
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    operation()
    return _metrics(
        wall_seconds=time.perf_counter() - wall_start,
        cpu_seconds=time.process_time() - cpu_start,
    )


def _stored_footprint(root: Path) -> tuple[int, int]:
    """Count durable files and bytes beneath one completed store."""
    files = tuple(path for path in root.rglob("*") if path.is_file())
    return len(files), sum(path.stat().st_size for path in files)


def _tile_values(
    plane: npt.NDArray[np.float64],
    manifest: PartitionManifest,
) -> tuple[npt.NDArray[np.float64], ...]:
    """Return views of every deterministic output core."""
    return tuple(
        plane[
            tile.core_bounds.y_start : tile.core_bounds.y_stop,
            tile.core_bounds.x_start : tile.core_bounds.x_stop,
        ]
        for tile in manifest.tiles
    )


def _measure_oracle(
    root: Path,
    manifest: PartitionManifest,
    values: tuple[npt.NDArray[np.float64], ...],
) -> tuple[tuple[StageMetrics, ...], tuple[int, int]]:
    """Write and validate one complete NumPy-file oracle generation."""
    holder: list[FilesystemProductSink] = []

    def initialize() -> None:
        holder.append(FilesystemProductSink(root))

    initialization = _timed(initialize)
    sink = holder[0]
    records: list[ProductChunk] = []

    def write() -> None:
        records.extend(
            sink.write_chunk(product_name="rms", tile=tile, values=tile_values)
            for tile, tile_values in zip(
                manifest.tiles,
                values,
                strict=True,
            )
        )

    writing = _timed(write)

    def validate() -> None:
        for record, expected in zip(records, values, strict=True):
            np.testing.assert_array_equal(sink.read_chunk(record), expected)

    validation = _timed(validate)
    return (
        (
            StageMetrics(stage="initialize-store", metrics=initialization),
            StageMetrics(stage="write-chunks", metrics=writing),
            StageMetrics(stage="validate-chunks", metrics=validation),
        ),
        _stored_footprint(root),
    )


def _measure_zarr(
    root: Path,
    manifest: PartitionManifest,
    values: tuple[npt.NDArray[np.float64], ...],
) -> tuple[tuple[StageMetrics, ...], tuple[int, int]]:
    """Write and validate one complete local Zarr v3 generation."""
    holder: list[ZarrProductSink] = []

    def initialize() -> None:
        sink = ZarrProductSink(root, manifest)
        sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))
        holder.append(sink)

    initialization = _timed(initialize)
    sink = holder[0]
    records: list[ZarrProductChunk] = []

    def write() -> None:
        records.extend(
            sink.write_chunk(product_name="rms", tile=tile, values=tile_values)
            for tile, tile_values in zip(
                manifest.tiles,
                values,
                strict=True,
            )
        )

    writing = _timed(write)

    def validate() -> None:
        for record, expected in zip(records, values, strict=True):
            np.testing.assert_array_equal(sink.read_chunk(record), expected)

    validation = _timed(validate)
    return (
        (
            StageMetrics(stage="initialize-store", metrics=initialization),
            StageMetrics(stage="write-chunks", metrics=writing),
            StageMetrics(stage="validate-chunks", metrics=validation),
        ),
        _stored_footprint(root),
    )


def _measure_store(
    *,
    output_directory: Path,
    store_name: str,
    warmups: int,
    repetitions: int,
    operation: Callable[
        [Path],
        tuple[tuple[StageMetrics, ...], tuple[int, int]],
    ],
) -> _ObservedRun:
    """Measure isolated generations and retain the final footprint."""
    measurements: list[Measurement] = []
    footprint = (0, 0)
    for index in range(warmups + repetitions):
        with tempfile.TemporaryDirectory(
            prefix=f"{store_name}-",
            dir=output_directory,
        ) as temporary_directory:
            wall_start = time.perf_counter()
            cpu_start = time.process_time()
            stages, footprint = operation(Path(temporary_directory))
            measurements.append(
                Measurement(
                    repetition_index=index,
                    warmup=index < warmups,
                    complete=_metrics(
                        wall_seconds=time.perf_counter() - wall_start,
                        cpu_seconds=time.process_time() - cpu_start,
                    ),
                    stages=stages,
                )
            )
    return _ObservedRun(
        measurements=tuple(measurements),
        object_count=footprint[0],
        stored_bytes=footprint[1],
    )


def _software_identity(
    name: str,
    package_version: str,
    dependency_sha256: str,
    source_tree_sha256: str | None = None,
) -> SoftwareIdentity:
    """Build one exact package identity for exploratory evidence."""
    return SoftwareIdentity(
        name=name,
        version=package_version,
        source_tree_sha256=source_tree_sha256,
        dependency_inventory_sha256=dependency_sha256,
    )


def _evidence(
    *,
    context: _EvidenceContext,
    subject: _EvidenceSubject,
    observed: _ObservedRun,
    storage: StorageEvidence,
) -> BenchmarkEvidence:
    """Bind one observed store to complete machine-readable provenance."""
    return BenchmarkEvidence(
        schema_version=1,
        evidence_type="benchmark",
        run_id=subject.run_id,
        captured_at=datetime.now(UTC),
        status=EvidenceStatus.EXPLORATORY,
        dataset=context.dataset,
        subject=_software_identity(
            subject.subject_name,
            version("hebog"),
            context.dependency_sha256,
            context.source_tree_sha256,
        ),
        related_software=subject.related_software,
        configuration_sha256=context.configuration_sha256,
        environment_sha256=context.environment_sha256,
        resources=context.resources,
        measurements=observed.measurements,
        storage=storage,
    )


def main() -> int:
    """Run the controlled local comparison and write two evidence files."""
    args = _parse_args()
    dimensions = (
        args.height,
        args.width,
        args.chunk_height,
        args.chunk_width,
        args.warmups,
        args.repetitions,
    )
    if min(dimensions) < 1 or args.repetitions < _MINIMUM_REPETITIONS:
        raise ValueError(
            "dimensions and warmups must be positive and at least five "
            "measurements are required"
        )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    plane = rng.normal(size=(args.height, args.width)).astype(np.float64)
    plane[0, 0] = np.nan
    manifest = PartitionManifest.create(
        image_shape_yx=tuple(plane.shape),
        tile_core_shape_yx=(args.chunk_height, args.chunk_width),
        halo_yx=(0, 0),
    )
    values = _tile_values(plane, manifest)
    dependency_path = Path("uv.lock")
    dependency_sha256 = _sha256_bytes(dependency_path.read_bytes())
    configuration = {
        "shape_yx": plane.shape,
        "chunk_shape_yx": manifest.tile_core_shape_yx,
        "warmups": args.warmups,
        "repetitions": args.repetitions,
        "seed": args.seed,
        "dtype": plane.dtype.str,
        "runner_sha256": _sha256_bytes(Path(__file__).read_bytes()),
    }
    configuration_sha256 = _canonical_sha256(configuration)
    environment_sha256 = _canonical_sha256(
        {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "zarr": zarr.__version__,
        }
    )
    dataset = DatasetIdentity(
        identifier=f"synthetic-store-probe-{args.height}x{args.width}",
        role=DatasetRole.DEVELOPMENT,
        content_sha256=_sha256_bytes(plane.tobytes()),
        shape_yx=tuple(plane.shape),
        workload_class=WorkloadClass.NORMAL,
    )
    node_memory = _node_memory_bytes()
    resources = ResourceAllocation(
        executor=ExecutorKind.SERIAL,
        worker_nodes=1,
        workers_per_node=1,
        threads_per_worker=1,
        allocated_cpu_cores=1,
        node_memory_bytes=node_memory,
        worker_memory_limit_bytes=node_memory // 2,
        reserved_headroom_per_node_bytes=node_memory // 4,
        storage_identifier="local-temporary-filesystem",
    )
    evidence_context = _EvidenceContext(
        dataset=dataset,
        configuration_sha256=configuration_sha256,
        environment_sha256=environment_sha256,
        dependency_sha256=dependency_sha256,
        source_tree_sha256=_source_tree_sha256(Path("src/hebog")),
        resources=resources,
    )
    oracle = _measure_store(
        output_directory=args.output_directory,
        store_name="numpy-oracle",
        warmups=args.warmups,
        repetitions=args.repetitions,
        operation=lambda root: _measure_oracle(
            root,
            manifest,
            values,
        ),
    )
    zarr_run = _measure_store(
        output_directory=args.output_directory,
        store_name="zarr-v3",
        warmups=args.warmups,
        repetitions=args.repetitions,
        operation=lambda root: _measure_zarr(root, manifest, values),
    )
    oracle_evidence = _evidence(
        context=evidence_context,
        subject=_EvidenceSubject(
            run_id="phase-1-numpy-store-probe",
            subject_name="hebog-filesystem-sink",
        ),
        observed=oracle,
        storage=StorageEvidence(
            format_name="numpy-npy-files",
            library_name="numpy",
            library_version=np.__version__,
            backend_name="local-filesystem",
            chunk_shape_yx=manifest.tile_core_shape_yx,
            shard_shape_yx=None,
            codec_pipeline=("npy", "sha256"),
            fill_value="not-applicable",
            missing_chunk_policy="error",
            write_empty_chunks=True,
            object_count=oracle.object_count,
            stored_bytes=oracle.stored_bytes,
            internal_concurrency=1,
            atomic_write_guarantee="same-filesystem hard-link publication",
            conditional_create=True,
        ),
    )
    zarr_evidence = _evidence(
        context=evidence_context,
        subject=_EvidenceSubject(
            run_id="phase-1-zarr-store-probe",
            subject_name="hebog-zarr-sink",
            related_software=(
                _software_identity(
                    "zarr",
                    zarr.__version__,
                    dependency_sha256,
                ),
            ),
        ),
        observed=zarr_run,
        storage=StorageEvidence(
            format_name="zarr-v3",
            library_name="zarr",
            library_version=zarr.__version__,
            backend_name="local-store",
            chunk_shape_yx=manifest.tile_core_shape_yx,
            shard_shape_yx=None,
            codec_pipeline=("bytes-little-endian", "zstd-1", "crc32c"),
            fill_value="0",
            missing_chunk_policy="error",
            write_empty_chunks=True,
            object_count=zarr_run.object_count,
            stored_bytes=zarr_run.stored_bytes,
            internal_concurrency=int(zarr.config.get("async.concurrency")),
            atomic_write_guarantee="not documented by Zarr LocalStore",
            conditional_create=False,
        ),
    )
    write_evidence(
        args.output_directory / "numpy-store-evidence.json",
        oracle_evidence,
    )
    write_evidence(
        args.output_directory / "zarr-store-evidence.json",
        zarr_evidence,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
