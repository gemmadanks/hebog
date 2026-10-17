#!/usr/bin/env python3
"""Run Rapthor's complete filter_skymodel step once and measure it.

This runs inside the matched benchmark image
(``scripts/benchmark/containers/filter-skymodel``), not on the host: it
imports the Rapthor installed there, from its Hebog branch. The sector's
working directory holds the inputs ``measure_filter_skymodel.py`` placed in
it, as Rapthor's pipeline directory does; PyBDSF writes its mask beside its
input image.

The measured span is Rapthor's ``filter_skymodel_products`` with
``source_finder`` set to ``hebog`` (the native task) or ``bdsf`` (the PyBDSF
subprocess), on ``--ncores`` cores, with Rapthor's command profiler off so
that it adds nothing to the PyBDSF subprocess alone. CPU time counts this
process and the children it waited for; peak memory is that of the largest
process. LSMTool's ``filter_sources`` rewrites the mask when it clips it to
the sector polygon and writes the filtered sky models last, so the files'
modification times split the span into the finder's part and LSMTool's
filtering, for both finders alike. The result is ``run.json`` in the working
directory::

    python /worker.py --finder hebog --directory /sector --ncores 4 \\
        --threshpix 5 --threshisl 3 --beam-ms /sector/beam.ms

Rapthor's Hebog branch runs Hebog only on threads. For a screening measurement
of what a Dask path could give (plan task 72), ``--dask-workers`` swaps the
native task's ``ThreadExecutor`` for a ``DaskExecutor`` on that many
single-threaded local worker processes. They split the task's memory budget
evenly, with Dask's spilling, pausing and restarting off, as in the scaling
profile, and starting and closing them is part of the measured span. They
are this process's children, so the CPU time includes them, and the native
task's diagnostics still name threads.

When Hebog refuses the sector, Rapthor falls back to PyBDSF. Such a Hebog
run writes ``run.json`` and exits 1, because it measured the wrong finder.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import resource
import sys
import time
from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from pathlib import Path
from unittest import mock

import dask.config
from astropy.table import Table
from distributed import Client, LocalCluster
from rapthor.execution.config import ExecutionConfig
from rapthor.execution.image import hebog_filter, outputs
from rapthor.lib.records import file_record

from hebog.executors import DaskExecutor

_INPUTS = (
    "sector_1-MFS-image.fits",
    "sector_1-MFS-image-pb.fits",
    "sector_1-sources.txt",
    "sector_1-sources-pb.txt",
)
_PRODUCTS = (
    "filtered_true_sky",
    "filtered_apparent_sky",
    "diagnostics",
    "flat_noise_rms",
    "true_sky_rms",
    "source_catalog",
    "source_filtering_mask",
)
_KIB = 1024
_MEMORY_ACTIONS_OFF = {
    f"distributed.worker.memory.{name}": False
    for name in ("target", "spill", "pause", "terminate")
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _components(path: Path) -> int:
    """Count a makesourcedb model's components, skipping patch rows."""
    rows = path.read_text(encoding="utf-8").splitlines()[1:]
    return sum(1 for row in rows if row.strip() and not row.startswith(" ,"))


@contextmanager
def _native_task_on_dask(worker_count: int) -> Generator[None]:
    """Run the native task's Hebog work on local Dask worker processes."""
    replaced_thread_counts: list[int] = []

    @contextmanager
    def dask_executor(
        *, thread_count: int, memory_bytes_per_worker: int
    ) -> Generator[DaskExecutor]:
        replaced_thread_counts.append(thread_count)
        with (
            dask.config.set(_MEMORY_ACTIONS_OFF),
            LocalCluster(
                n_workers=worker_count,
                threads_per_worker=1,
                processes=True,
                dashboard_address=":0",
                memory_limit=memory_bytes_per_worker // worker_count,
            ) as cluster,
            Client(cluster) as client,
        ):
            yield DaskExecutor(client)

    with mock.patch.object(hebog_filter, "ThreadExecutor", dask_executor):
        yield
    if not replaced_thread_counts:
        raise RuntimeError("the native task never asked for an executor")


def main() -> int:
    """Run and measure one filter step."""
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0]
    )
    parser.add_argument("--finder", choices=("hebog", "bdsf"), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--ncores", type=int, required=True)
    parser.add_argument("--threshpix", type=float, required=True)
    parser.add_argument("--threshisl", type=float, required=True)
    parser.add_argument("--beam-ms", type=Path)
    parser.add_argument("--dask-workers", type=int)
    args = parser.parse_args()
    if args.dask_workers is not None and args.finder != "hebog":
        parser.error("--dask-workers applies to Hebog's native task only")
    directory = args.directory
    sector = {
        "save_source_list": True,
        "obs_original_paths": []
        if args.beam_ms is None
        else [str(args.beam_ms)],
        "threshisl": args.threshisl,
        "threshpix": args.threshpix,
        "filter_by_mask": True,
        "source_finder": args.finder,
        "max_threads": args.ncores,
        "filter_skymodel_ncores": args.ncores,
        "vertices_file": str(directory / "sector_1_vertices.npy"),
    }
    records = [file_record(str(directory / name)) for name in _INPUTS]
    config = ExecutionConfig(
        task_runner="sync", cpus_per_task=args.ncores, command_profile="off"
    )
    own_before = resource.getrusage(resource.RUSAGE_SELF)
    children_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    executor: AbstractContextManager[None] = (
        nullcontext()
        if args.dask_workers is None
        else _native_task_on_dask(args.dask_workers)
    )
    started_at = time.time()
    started = time.perf_counter()
    with executor:
        result = outputs.filter_skymodel_products(
            sector,
            "sector_1",
            *records,
            str(directory),
            execution_config=config,
        )
    wall_seconds = time.perf_counter() - started
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_seconds = (
        own.ru_utime
        - own_before.ru_utime
        + own.ru_stime
        - own_before.ru_stime
        + children.ru_utime
        - children_before.ru_utime
        + children.ru_stime
        - children_before.ru_stime
    )
    products = {
        name: None if record is None else Path(record["path"])
        for name, record in zip(_PRODUCTS, result, strict=True)
    }
    diagnostics = json.loads(
        Path(str(products["diagnostics"])).read_text(encoding="utf-8")
    )
    clipped_at = Path(str(products["source_filtering_mask"])).stat().st_mtime
    filtered_at = max(
        Path(str(products[name])).stat().st_mtime
        for name in ("filtered_true_sky", "filtered_apparent_sky")
    )
    run = {
        "finder": args.finder,
        "ncores": args.ncores,
        "dask_workers": args.dask_workers,
        "beam_ms": None if args.beam_ms is None else str(args.beam_ms),
        "wall_seconds": wall_seconds,
        "finder_seconds": clipped_at - started_at,
        "filter_sources_seconds": filtered_at - clipped_at,
        "cpu_seconds": cpu_seconds,
        "peak_rss_bytes": max(own.ru_maxrss, children.ru_maxrss) * _KIB,
        "own_peak_rss_bytes": own.ru_maxrss * _KIB,
        "children_peak_rss_bytes": children.ru_maxrss * _KIB,
        "nsources": diagnostics["nsources"],
        "source_finding": diagnostics.get("source_finding"),
        "catalogue_rows": len(Table.read(products["source_catalog"])),
        "kept_true_sky_components": _components(
            Path(str(products["filtered_true_sky"]))
        ),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("bdsf", "hebog", "lsmtool", "rapthor", "numpy")
        },
        "products": {
            name: None
            if path is None
            else {"name": path.name, "sha256": _sha256(path)}
            for name, path in products.items()
        },
    }
    (directory / "run.json").write_text(
        json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source_finding = run["source_finding"] or {}
    if args.finder == "hebog" and source_finding.get("selected") != "hebog":
        print(
            "Rapthor ran PyBDSF instead of Hebog: "
            f"{source_finding.get('fallback_reason')}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
