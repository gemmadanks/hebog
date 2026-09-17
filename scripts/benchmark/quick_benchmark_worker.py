#!/usr/bin/env python3
"""Run the public finder once on one input for the quick benchmark.

``quick_benchmark.py`` starts this worker in a fresh process for every
repetition, with the interpreter of the Hebog being measured: the current
checkout or an earlier release. The worker uses only the public API and the
standard library, so it runs unchanged on every release since 0.7.0;
supplied image metadata needs 0.8.0 or later.

``--diagnostic-size-limit`` is the documented diagnostic entry point for
inputs above the public 1,024-pixel limit. It raises the limit only inside
this worker process; the public envelope and ``hebog.find_sources`` are
unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import resource
import sys
import time
from pathlib import Path

import hebog
from hebog import public_api
from hebog.config import SourceFinderConfig
from hebog.executors import SerialExecutor


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


def _dependency_inventory_sha256() -> str:
    """Hash the installed distribution names and versions."""
    inventory = sorted(
        {
            (
                str(distribution.metadata["Name"]).lower().replace("_", "-"),
                distribution.version,
            )
            for distribution in importlib.metadata.distributions()
        }
    )
    return hashlib.sha256(
        json.dumps(inventory, separators=(",", ":")).encode()
    ).hexdigest()


def _peak_rss_bytes() -> int:
    maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return maximum if sys.platform == "darwin" else maximum * 1024


def main() -> None:
    args = _parse_args()
    if args.diagnostic_size_limit is not None:
        if not hasattr(public_api, "_MAXIMUM_PREVIEW_DIMENSION"):
            raise SystemExit(
                "this Hebog has no preview size limit to raise; update the "
                "quick-benchmark worker"
            )
        public_api._MAXIMUM_PREVIEW_DIMENSION = args.diagnostic_size_limit
    settings = json.loads(args.settings)
    request_options: dict[str, object] = {}
    if args.supplied_metadata:
        from hebog.data_models import SuppliedImageMetadata  # noqa: PLC0415

        request_options["supplied_metadata"] = SuppliedImageMetadata(
            **json.loads(args.supplied_metadata)
        )
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
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
    record = {
        "dependency_inventory_sha256": _dependency_inventory_sha256(),
        "finder": {
            "cpu_seconds": time.process_time() - cpu_started,
            "peak_rss_bytes": _peak_rss_bytes(),
            "wall_seconds": time.perf_counter() - wall_started,
        },
        "gaussian_component_count": result.gaussian_component_count,
        "hebog_version": hebog.__version__,
        "python_version": sys.version.split()[0],
        "source_count": result.source_count,
    }
    args.result.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
