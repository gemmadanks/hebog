#!/usr/bin/env python3
"""Trace one complete public finder run and report its allocation peaks.

``measure_traced_peak.py`` starts this worker in a fresh process for every
repetition. Tracing starts before Hebog is imported, so the process peak
counts every allocation the run makes, the modules it loads included, and
the run itself is untouched: it uses the public API with the serial executor
exactly as the quick benchmark times it.

Nothing but the standard library and the public API is imported. Software
identity comes from the parent, which runs the same interpreter, because
importing the validation package here would add its own allocations to the
figure being measured.

``--diagnostic-size-limit`` is the documented diagnostic entry point for
inputs above the public size limit, which is how a raise candidate is
measured before its tier is admitted. The limit this Hebog would have applied
is reported, so the parent can say whether the measured size is supported.
"""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--settings", required=True, help="finder JSON")
    parser.add_argument("--supplied-metadata", help="metadata JSON")
    parser.add_argument(
        "--diagnostic-size-limit",
        type=int,
        help="largest admitted image dimension for this process only",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    settings = json.loads(args.settings)
    metadata = (
        json.loads(args.supplied_metadata) if args.supplied_metadata else None
    )
    tracemalloc.start()
    # Imported under tracing so the modules Hebog loads are counted.
    import hebog  # noqa: PLC0415
    from hebog import public_api  # noqa: PLC0415
    from hebog.config import SourceFinderConfig  # noqa: PLC0415
    from hebog.executors import SerialExecutor  # noqa: PLC0415

    request_options: dict[str, object] = {}
    if metadata is not None:
        from hebog.data_models import SuppliedImageMetadata  # noqa: PLC0415

        request_options["supplied_metadata"] = SuppliedImageMetadata(
            **metadata
        )
    size_limit = public_api._MAXIMUM_PREVIEW_DIMENSION
    if args.diagnostic_size_limit is not None:
        public_api._MAXIMUM_PREVIEW_DIMENSION = args.diagnostic_size_limit
    # The import span and the finder span partition the traced run, so the
    # process peak is the larger of the two.
    import_traced_bytes, import_peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    started = time.perf_counter()
    result = hebog.find_sources(
        hebog.SourceFinderRequest(
            image_path=args.input,
            output_directory=args.output_directory,
            run_id=args.run_id,
            **request_options,
        ),
        SourceFinderConfig(**settings),
        SerialExecutor(),
    )
    traced_wall_seconds = time.perf_counter() - started
    _, finder_peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    record = {
        "finder_peak_traced_bytes": finder_peak_bytes,
        "gaussian_component_count": result.gaussian_component_count,
        "import_traced_bytes": import_traced_bytes,
        "peak_traced_bytes": max(import_peak_bytes, finder_peak_bytes),
        "public_size_limit_pixels": size_limit,
        "source_count": result.source_count,
        "traced_wall_seconds": traced_wall_seconds,
    }
    args.result.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
