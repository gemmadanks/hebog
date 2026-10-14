#!/usr/bin/env python3
"""Run Rapthor's complete filter_skymodel step once and measure it.

This runs inside the matched benchmark image
(``scripts/benchmark/containers/filter-skymodel``), not on the host: it
imports the patched Rapthor installed there. The sector's working directory
holds the inputs ``measure_filter_skymodel.py`` placed in it, as Rapthor's
pipeline directory does; PyBDSF writes its mask beside its input image.

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
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import resource
import time
from pathlib import Path

from astropy.table import Table
from rapthor.execution.config import ExecutionConfig
from rapthor.execution.image import outputs
from rapthor.lib.records import file_record

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
    args = parser.parse_args()
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
    started_at = time.time()
    started = time.perf_counter()
    result = outputs.filter_skymodel_products(
        sector, "sector_1", *records, str(directory), execution_config=config
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
