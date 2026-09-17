#!/usr/bin/env python3
"""Profile one complete public source-finding run by stage.

``profile_complete_execution.py`` starts this worker in a fresh
single-thread process for each case. The worker times its own imports, then
wraps the functions that make up the public path with timers and runs
``hebog.find_sources`` once with the serial executor. Each stage records
calls, wall and CPU seconds, the process peak resident memory when it ends
and block input and output operations. Nested stages are reported under
their parent, so a parent's self time excludes them.

Wrapping replaces module attributes in this process only; no Hebog code
changes. ``--cprofile`` additionally writes a ``cProfile`` statistics file.
It sees only the calling thread, so Zarr's I/O thread is missing from it,
and it slows Python-heavy code, so stage times come from runs without it.
``--diagnostic-size-limit`` raises the public 1,024-pixel limit inside this
process only, as in the quick-benchmark worker.
"""

from __future__ import annotations

import time

_PROCESS_STARTED = time.perf_counter()

import argparse  # noqa: E402
import cProfile  # noqa: E402
import functools  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
import resource  # noqa: E402
import sys  # noqa: E402
from collections.abc import Callable, Iterator  # noqa: E402
from contextlib import contextmanager  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402
from tempfile import TemporaryDirectory  # noqa: E402
from typing import Any  # noqa: E402

import hebog  # noqa: E402
from hebog import public_api  # noqa: E402
from hebog.config import SourceFinderConfig  # noqa: E402
from hebog.data_models import SuppliedImageMetadata  # noqa: E402
from hebog.executors import SerialExecutor  # noqa: E402

# Imported lazily by ``find_sources``; imported here so that import time is
# not charged to the first stage that needs them.
importlib.import_module("hebog.public_science")
importlib.import_module("hebog.science.profile")
_IMPORT_SECONDS = time.perf_counter() - _PROCESS_STARTED

# (module, attribute, stage). An attribute ``Class.method`` wraps a method.
# Each module is the one whose global the public path looks up at call time.
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
        "hebog.public_science",
        "build_configured_continuum_products",
        "continuum science",
    ),
    (
        "hebog.public_science",
        "evaluate_continuum_candidate_products",
        "multiscale candidate products",
    ),
    (
        "hebog.public_science",
        "_retain_configured_islands",
        "island size limits",
    ),
    ("hebog.public_science", "deblend_component_topology", "deblending"),
    (
        "hebog.public_science",
        "measure_component_models",
        "component moments and fitting",
    ),
    (
        "hebog.public_science",
        "evaluate_residual_atrous",
        "position filter transform",
    ),
    (
        "hebog.public_science",
        "reconstruct_denoised_atrous",
        "position filter reconstruction",
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
_TOP_FUNCTIONS = 40


@dataclass(slots=True)
class _StageTotals:
    calls: int = 0
    wall_seconds: float = 0.0
    cpu_seconds: float = 0.0
    child_wall_seconds: float = 0.0
    child_cpu_seconds: float = 0.0
    peak_rss_bytes: int = 0
    peak_rss_increase_bytes: int = 0
    block_inputs: int = 0
    block_outputs: int = 0


class _StageRecorder:
    """Accumulate nested stage usage for one single-threaded run."""

    def __init__(self) -> None:
        self.path: tuple[str, ...] = ()
        self.totals: dict[tuple[str, ...], _StageTotals] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        parent = self.path
        path = (*parent, name)
        before = resource.getrusage(resource.RUSAGE_SELF)
        wall_started = time.perf_counter()
        cpu_started = time.process_time()
        self.path = path
        try:
            yield
        finally:
            self.path = parent
            wall = time.perf_counter() - wall_started
            cpu = time.process_time() - cpu_started
            after = resource.getrusage(resource.RUSAGE_SELF)
            totals = self.totals.setdefault(path, _StageTotals())
            totals.calls += 1
            totals.wall_seconds += wall
            totals.cpu_seconds += cpu
            totals.peak_rss_bytes = max(
                totals.peak_rss_bytes, _rss_bytes(after.ru_maxrss)
            )
            totals.peak_rss_increase_bytes += _rss_bytes(
                after.ru_maxrss
            ) - _rss_bytes(before.ru_maxrss)
            totals.block_inputs += after.ru_inblock - before.ru_inblock
            totals.block_outputs += after.ru_oublock - before.ru_oublock
            if parent:
                parent_totals = self.totals.setdefault(parent, _StageTotals())
                parent_totals.child_wall_seconds += wall
                parent_totals.child_cpu_seconds += cpu

    def wrap(self, function: Callable[..., Any], name: str) -> Any:
        @functools.wraps(function)
        def timed(*args: Any, **kwargs: Any) -> Any:
            with self.stage(name):
                return function(*args, **kwargs)

        return timed

    def records(self) -> list[dict[str, Any]]:
        return [
            {
                "stage": list(path),
                "calls": totals.calls,
                "wall_seconds": totals.wall_seconds,
                "self_wall_seconds": totals.wall_seconds
                - totals.child_wall_seconds,
                "cpu_seconds": totals.cpu_seconds,
                "self_cpu_seconds": totals.cpu_seconds
                - totals.child_cpu_seconds,
                "peak_rss_bytes": totals.peak_rss_bytes,
                "peak_rss_increase_bytes": totals.peak_rss_increase_bytes,
                "block_inputs": totals.block_inputs,
                "block_outputs": totals.block_outputs,
            }
            for path, totals in sorted(self.totals.items())
        ]


def _rss_bytes(maximum_resident_set: int) -> int:
    return (
        maximum_resident_set
        if sys.platform == "darwin"
        else maximum_resident_set * 1024
    )


def _install_stage_timers(recorder: _StageRecorder) -> None:
    for module_name, attribute, stage in _STAGES:
        owner: Any = importlib.import_module(module_name)
        *owners, name = attribute.split(".")
        for owner_name in owners:
            owner = getattr(owner, owner_name)
        setattr(owner, name, recorder.wrap(getattr(owner, name), stage))


def _top_functions(statistics_path: Path) -> list[dict[str, Any]]:
    import pstats  # noqa: PLC0415

    statistics: Any = pstats.Stats(str(statistics_path))
    rows = [
        {
            "function": f"{Path(file).name}:{line}({function})",
            "calls": calls,
            "self_seconds": self_seconds,
            "cumulative_seconds": cumulative_seconds,
        }
        for (file, line, function), (
            _,
            calls,
            self_seconds,
            cumulative_seconds,
            _,
        ) in statistics.stats.items()
    ]
    return sorted(rows, key=lambda row: -row["self_seconds"])[:_TOP_FUNCTIONS]


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
    recorder = _StageRecorder()
    _install_stage_timers(recorder)
    import_rss_bytes = _rss_bytes(
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    )
    profiler = cProfile.Profile() if args.cprofile is not None else None
    with TemporaryDirectory(prefix="hebog-profile-") as temporary:
        if profiler is not None:
            profiler.enable()
        with recorder.stage("find_sources"):
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
        "source_count": result.source_count,
        "gaussian_component_count": result.gaussian_component_count,
        "island_count": result.island_count,
        "stages": recorder.records(),
        "cprofile": None,
    }
    if args.cprofile is not None and profiler is not None:
        profiler.dump_stats(args.cprofile)
        record["cprofile"] = {
            "statistics": str(args.cprofile),
            "top_self_time": _top_functions(args.cprofile),
        }
    args.result.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
