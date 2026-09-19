#!/usr/bin/env python3
"""Profile one complete public source-finding run by stage.

``profile_complete_execution.py`` starts this worker in a fresh
single-thread process for each case. The worker times its own imports, then
wraps the functions that make up the public path with timers from
``hebog.validation.execution_profile`` and runs ``hebog.find_sources`` once
with the serial executor.

Wrapping replaces module attributes in this process only, in every module
that binds the function, so a call through an imported alias is timed as
its own stage; no Hebog code changes. ``--cprofile`` additionally writes a
``cProfile`` statistics file, which sees only the calling thread and slows
Python-heavy code, so stage times come from runs without it.
``--diagnostic-size-limit`` raises the public 1,024-pixel limit inside this
process only, as in the quick-benchmark worker.

Stage timing needs the POSIX ``resource`` module, so this worker runs on
macOS and Linux.
"""

from __future__ import annotations

import time

_PROCESS_STARTED = time.perf_counter()

import argparse  # noqa: E402
import cProfile  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from tempfile import TemporaryDirectory  # noqa: E402
from typing import Any  # noqa: E402

import hebog  # noqa: E402
from hebog import public_api  # noqa: E402
from hebog.config import SourceFinderConfig  # noqa: E402
from hebog.data_models import SuppliedImageMetadata  # noqa: E402
from hebog.executors import SerialExecutor  # noqa: E402
from hebog.validation.execution_profile import (  # noqa: E402
    StageRecorder,
    current_peak_rss_bytes,
    install_stage_timers,
    top_self_time,
)

# Imported lazily by ``find_sources``; imported here so that import time is
# not charged to the first stage that needs them.
importlib.import_module("hebog.public_science")
importlib.import_module("hebog.science.profile")
_IMPORT_SECONDS = time.perf_counter() - _PROCESS_STARTED

ROOT_STAGE = "find_sources"
# (module, attribute, stage). An attribute ``Class.method`` wraps a method.
# The module is where the public path looks the function up; every other
# binding of it in the package is wrapped too.
_STAGES = (
    ("hebog.public_api", "_file_sha256", "input hashing"),
    ("hebog.io.fits", "FitsImageSource.read_window", "FITS window read"),
    (
        "hebog.public_api",
        "run_detection_stage",
        "background, RMS and first-pass detection",
    ),
    (
        "hebog.stages.detection",
        "estimate_background_rms_grids",
        "coarse background and RMS grids",
    ),
    (
        "hebog.stages.detection",
        "discover_adaptive_candidates",
        "adaptive candidate scan",
    ),
    (
        "hebog.stages.detection",
        "refine_background_rms_grids",
        "background refinement and local noise",
    ),
    (
        "hebog.stages.detection",
        "_detect_and_write_background_rms",
        "tile detection and background/RMS writes",
    ),
    (
        "hebog.stages.detection",
        "_write_source_filtering_mask",
        "tile source-filtering mask writes",
    ),
    ("hebog.io.zarr", "ZarrProductSink.write_chunk", "Zarr chunk write"),
    (
        "hebog.io.zarr",
        "ZarrProductSink.read_completed_window",
        "Zarr plane read",
    ),
    (
        "hebog.public_api",
        "detect_multiscale_products",
        "tiled multiscale detection pass",
    ),
    (
        "hebog.stages.multiscale",
        "run_multiscale_stage",
        "multiscale filters, thresholds and labelling",
    ),
    (
        "hebog.public_science",
        "build_configured_continuum_products",
        "continuum science",
    ),
    (
        "hebog.public_api",
        "reduce_support_topology",
        "support component and persistence reductions",
    ),
    (
        "hebog.public_api",
        "publish_support_labels",
        "tiled support pass",
    ),
    (
        "hebog.stages.publication",
        "run_publication_stage",
        "owner connectivity and final labels",
    ),
    (
        "hebog.public_science",
        "build_continuum_candidate_products",
        "candidate products from published planes",
    ),
    ("hebog.public_science", "deblend_component_topology", "deblending"),
    (
        "hebog.public_science",
        "measure_component_models",
        "component moments and fitting",
    ),
    (
        "hebog.public_science",
        "build_hebog_reconstructed_source_catalogues",
        "source association and catalogues",
    ),
    ("hebog.public_api", "_public_catalogue", "public catalogue records"),
    (
        "hebog.public_api",
        "write_catalogue_fits_product",
        "catalogue FITS write",
    ),
    ("hebog.public_api", "write_rms_fits_product", "RMS FITS write"),
    ("hebog.public_api", "write_mask_fits_product", "mask FITS write"),
    (
        "hebog.public_api",
        "write_diagnostics_product",
        "diagnostics JSON write",
    ),
    (
        "hebog.public_api",
        "_scientific_composition_sha256",
        "composition hashing",
    ),
    ("hebog.public_api", "_publish_bundle", "bundle publication"),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--settings", required=True, help="finder JSON")
    parser.add_argument("--supplied-metadata", help="metadata JSON")
    parser.add_argument("--diagnostic-size-limit", type=int)
    parser.add_argument("--cprofile", type=Path, help="statistics path")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.diagnostic_size_limit is not None:
        public_api._MAXIMUM_PREVIEW_DIMENSION = args.diagnostic_size_limit  # pyright: ignore[reportPrivateUsage]
    supplied = (
        SuppliedImageMetadata(**json.loads(args.supplied_metadata))
        if args.supplied_metadata
        else None
    )
    recorder = StageRecorder()
    wrapped_bindings = install_stage_timers(recorder, _STAGES)
    import_rss_bytes = current_peak_rss_bytes()
    profiler = cProfile.Profile() if args.cprofile is not None else None
    with TemporaryDirectory(prefix="hebog-profile-") as temporary:
        if profiler is not None:
            profiler.enable()
        with recorder.stage(ROOT_STAGE):
            result = hebog.find_sources(
                hebog.SourceFinderRequest(
                    image_path=args.input,
                    output_directory=Path(temporary) / "products",
                    run_id="profile",
                    supplied_metadata=supplied,
                ),
                SourceFinderConfig(**json.loads(args.settings)),
                SerialExecutor(),
            )
        if profiler is not None:
            profiler.disable()
    record: dict[str, Any] = {
        "hebog_version": hebog.__version__,
        "python_version": sys.version.split()[0],
        "import_seconds": _IMPORT_SECONDS,
        "import_peak_rss_bytes": import_rss_bytes,
        "root_stage": ROOT_STAGE,
        "wrapped_bindings": wrapped_bindings,
        "source_count": result.source_count,
        "gaussian_component_count": result.gaussian_component_count,
        "island_count": result.island_count,
        "stages": [item.document() for item in recorder.records()],
        "cprofile": None,
    }
    if args.cprofile is not None and profiler is not None:
        profiler.dump_stats(args.cprofile)
        record["cprofile"] = {
            "statistics": str(args.cprofile),
            "top_self_time": top_self_time(args.cprofile),
        }
    # Process creation, interpreter start-up and shutdown lie outside this
    # script; the driver derives them from the lifetime recorded here. The
    # lifetime cannot cover the serialization and write below, because their
    # result is the file carrying it; those few milliseconds are reported
    # with the process time instead.
    record["worker_lifetime_seconds"] = time.perf_counter() - _PROCESS_STARTED
    args.result.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
