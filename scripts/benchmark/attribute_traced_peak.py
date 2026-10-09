#!/usr/bin/env python3
"""Attribute one serial run's traced peak to passes, tasks and call sites.

A diagnostic beside ``just traced-peak``, which alone produces the gate
figure: this process also holds the attribution's own wrappers and records,
so its peak is a little higher. Tracing starts before Hebog is imported,
with ``--frames`` frames a traceback. Every function of ``hebog.public_api``
and ``hebog.stages.composition``, which holds the stage runners, and every
serial executor task is measured as a nested call (see
``hebog.validation.traced_attribution``), and inside the call named by
``--snapshot-within`` the task that begins holding most is snapshotted and
reduced to the call sites holding that memory. ``--wrap-module`` adds the
functions another Hebog module defines, measured wherever they are bound.

Example::

    uv run python scripts/benchmark/attribute_traced_peak.py \\
      --input image.fits --settings '<finder JSON>' --result peak.json \\
      --snapshot-within detect_multiscale_products

``--diagnostic-size-limit`` raises the public size limit inside this
process only, as in the benchmark workers.
"""

from __future__ import annotations

import argparse
import importlib
import json
import time
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--settings", required=True, help="finder JSON")
    parser.add_argument("--diagnostic-size-limit", type=int)
    parser.add_argument(
        "--snapshot-within",
        default="detect_multiscale_products",
        help="the function whose tasks' largest entry is snapshotted",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=6,
        help=(
            "traceback frames kept for each allocation; each frame slows "
            "the run, and six took a 10,000-pixel run about two hours"
        ),
    )
    parser.add_argument(
        "--sites", type=int, default=40, help="call sites reported"
    )
    parser.add_argument(
        "--wrap-module",
        action="append",
        default=[],
        help="another module whose functions are measured (repeatable)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    tracemalloc.start(args.frames)
    # Imported under tracing, as in the traced-peak worker.
    import hebog  # noqa: PLC0415
    from hebog import public_api  # noqa: PLC0415
    from hebog.config import SourceFinderConfig  # noqa: PLC0415
    from hebog.executors import SerialExecutor, serial  # noqa: PLC0415
    from hebog.stages import composition  # noqa: PLC0415
    from hebog.validation.traced_attribution import (  # noqa: PLC0415
        TracedPeakTracker,
        serial_tasks_measured,
        wrap_module_functions,
    )

    import_bytes = tracemalloc.get_traced_memory()[0]
    if args.diagnostic_size_limit is not None:
        public_api._MAXIMUM_PREVIEW_DIMENSION = args.diagnostic_size_limit  # pyright: ignore[reportPrivateUsage]
    tracker = TracedPeakTracker(
        snapshot_within=args.snapshot_within, site_limit=args.sites
    )
    wrapped = (
        wrap_module_functions(tracker, public_api)
        + wrap_module_functions(tracker, composition)
        + sum(
            wrap_module_functions(tracker, importlib.import_module(name))
            for name in args.wrap_module
        )
    )
    started = time.perf_counter()
    with (
        TemporaryDirectory(prefix="hebog-attribution-") as temporary,
        serial_tasks_measured(tracker, serial),
    ):
        result = public_api.find_sources(
            hebog.SourceFinderRequest(
                image_path=args.input,
                output_directory=Path(temporary) / "products",
                run_id="attribution",
            ),
            SourceFinderConfig(**json.loads(args.settings)),
            SerialExecutor(),
        )
    record: dict[str, Any] = {
        "input": str(args.input),
        "hebog_version": hebog.__version__,
        "traceback_frames": args.frames,
        "import_bytes": import_bytes,
        "wall_seconds": time.perf_counter() - started,
        "wrapped_modules": [
            "hebog.public_api",
            "hebog.stages.composition",
            *args.wrap_module,
        ],
        "wrapped_bindings": wrapped,
        "source_count": result.source_count,
        "gaussian_component_count": result.gaussian_component_count,
        "snapshot_within": args.snapshot_within,
        "largest_entry": {
            "path": list(tracker.largest_entry_path or ()),
            "bytes": tracker.largest_entry_bytes,
            "sites": tracker.sites_at_largest_entry,
        },
        "spans": tracker.documents(),
    }
    args.result.write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
