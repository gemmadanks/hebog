#!/usr/bin/env python3
"""Audit one serial run's task memory against what each round declares.

Every round declares the memory its tasks hold, and
``hebog.analysis_memory_bytes`` states what the analysis holds between them
(``hebog.stages.task_memory``). This runner traces one public run under
``hebog.validation.task_memory_audit.TaskMemoryAuditExecutor``, starting
before Hebog is imported so the analysis's figure counts its modules, and
writes each round's largest task peak, declaration and load. It exits with
status 1 when a round declared nothing or any load exceeds one.

Example::

    uv run python scripts/benchmark/audit_task_memory.py \\
      --input image.fits --settings '<finder JSON>' --result audit.json

``--flat-noise`` names the sector's flat-noise image, and
``--diagnostic-size-limit`` raises the public size limit inside this process
only, as in the benchmark workers.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--flat-noise", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--settings", required=True, help="finder JSON")
    parser.add_argument("--diagnostic-size-limit", type=int)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    tracemalloc.start()
    # Imported under tracing, so the analysis's figure counts the modules.
    import hebog  # noqa: PLC0415
    from hebog import public_api  # noqa: PLC0415
    from hebog.config import SourceFinderConfig  # noqa: PLC0415
    from hebog.io import FitsImageSource  # noqa: PLC0415
    from hebog.validation.task_memory_audit import (  # noqa: PLC0415
        TaskMemoryAuditExecutor,
        audit_document,
    )

    import_bytes = tracemalloc.get_traced_memory()[0]
    if args.diagnostic_size_limit is not None:
        public_api._MAXIMUM_PREVIEW_DIMENSION = args.diagnostic_size_limit  # pyright: ignore[reportPrivateUsage]
    executor = TaskMemoryAuditExecutor()
    started = time.perf_counter()
    with TemporaryDirectory(prefix="hebog-memory-audit-") as temporary:
        result = hebog.find_sources(
            hebog.SourceFinderRequest(
                image_path=args.input,
                output_directory=Path(temporary) / "products",
                run_id="memory-audit",
                flat_noise_image_path=args.flat_noise,
            ),
            SourceFinderConfig(**json.loads(args.settings)),
            executor,
        )
        executor.record_analysis_peak()
    shape_yx = FitsImageSource(args.input).metadata().shape_yx
    audit = audit_document(
        executor, image_shape_yx=shape_yx, source_count=result.source_count
    )
    record: dict[str, Any] = {
        "input": args.input.as_posix(),
        "flat_noise": None
        if args.flat_noise is None
        else args.flat_noise.as_posix(),
        "image_shape_yx": list(shape_yx),
        "hebog_version": hebog.__version__,
        "import_bytes": import_bytes,
        "wall_seconds": time.perf_counter() - started,
        "source_count": result.source_count,
        **audit,
    }
    args.result.write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    analysis = audit["analysis"]
    print(
        f"analysis {analysis['peak_bytes'] / 2**20:.0f} MiB of "
        f"{analysis['stated_bytes'] / 2**20:.0f} MiB stated; most loaded "
        f"round {audit['largest_round_load']}"
    )
    failed = bool(audit["undeclared_rounds"]) or any(
        load is not None and load > 1
        for load in (
            analysis["load"],
            *(entry["load"] for entry in audit["rounds"]),
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
