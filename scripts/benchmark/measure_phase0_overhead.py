# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Measure warm one-tile framework overhead against Phase 0 budgets."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

import numpy as np
from astropy.io import fits
from distributed import Client

from hebog.config import SourceFinderConfig
from hebog.executors.dask import DaskExecutor
from hebog.executors.serial import SerialExecutor
from hebog.validation.overhead import (
    OverheadEnvironment,
    OverheadEvidence,
    OverheadOperation,
    OverheadStatistics,
    write_overhead_evidence,
)

Result = TypeVar("Result")
_MINIMUM_REPETITIONS = 5

_BUDGET_KEYS: dict[OverheadOperation, str] = {
    "configuration": "configuration_seconds",
    "fits-io": "fits_io_seconds",
    "partition-planning": "partition_planning_seconds",
    "serial-dispatch": "serial_dispatch_seconds",
    "local-dispatch": "local_dispatch_seconds",
    "dask-dispatch": "dask_dispatch_seconds",
}


@dataclass(frozen=True)
class _Probe:
    """One isolated warm operation and its frozen budget."""

    operation: OverheadOperation
    method: str
    function: Callable[[], object]
    budget_seconds: float


def _parse_args() -> argparse.Namespace:
    """Parse controlled input, budget, and output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--performance-contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--warmups", default=1, type=int)
    parser.add_argument("--repetitions", default=50, type=int)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    """Return one complete file digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    """Hash one JSON-compatible value canonically."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _identity(value: Result) -> Result:
    """Return a dispatched value unchanged."""
    return value


def _plan_one_tile() -> tuple[slice, slice, slice, slice]:
    """Calculate one bounded core and clipped halo window."""
    height, width = 256, 256
    halo = 32
    core_y_start, core_y_stop = 0, height
    core_x_start, core_x_stop = 0, width
    return (
        slice(core_y_start, core_y_stop),
        slice(core_x_start, core_x_stop),
        slice(max(0, core_y_start - halo), min(height, core_y_stop + halo)),
        slice(max(0, core_x_start - halo), min(width, core_x_stop + halo)),
    )


def _measure(
    probe: _Probe,
    *,
    warmups: int,
    repetitions: int,
) -> OverheadStatistics:
    """Measure one already-initialized operation repeatedly."""
    for _ in range(warmups):
        probe.function()
    observations = []
    for _ in range(repetitions):
        started = time.perf_counter()
        probe.function()
        observations.append(time.perf_counter() - started)
    minimum = float(np.min(observations))
    median = float(np.median(observations))
    percentile_95 = float(np.percentile(observations, 95.0))
    maximum = float(np.max(observations))
    return OverheadStatistics(
        operation=probe.operation,
        method=probe.method,
        warmup_repetitions=warmups,
        measured_repetitions=repetitions,
        minimum_seconds=minimum,
        median_seconds=median,
        percentile_95_seconds=percentile_95,
        maximum_seconds=maximum,
        budget_seconds=probe.budget_seconds,
        within_budget=percentile_95 <= probe.budget_seconds,
    )


def _memory_bytes() -> int:
    """Read the host memory visible to this local process."""
    page_size = os.sysconf("SC_PAGE_SIZE")
    page_count = os.sysconf("SC_PHYS_PAGES")
    return int(page_size * page_count)


def _environment() -> OverheadEnvironment:
    """Capture exact interpreter and relevant dependency versions."""
    dependencies = {
        name: importlib.metadata.version(name)
        for name in ("astropy", "dask", "distributed", "hebog", "numpy")
    }
    return OverheadEnvironment(
        python=platform.python_version(),
        platform=platform.platform(),
        machine=platform.machine(),
        cpu_count=os.cpu_count(),
        node_memory_bytes=_memory_bytes(),
        dependency_versions=dependencies,
    )


def main() -> None:
    """Run the warm probe with reused local and Dask executors."""
    args = _parse_args()
    if args.warmups < 1 or args.repetitions < _MINIMUM_REPETITIONS:
        raise ValueError("probe requires a warm-up and five measurements")
    contract = json.loads(
        args.performance_contract.read_text(encoding="utf-8")
    )
    budgets = contract["one_tile_overhead_budget"]
    with fits.open(args.input, memmap=True) as hdus:
        data = hdus[0].data
        if data is None:
            raise ValueError("overhead input has no primary image")
        shape_yx = tuple(int(value) for value in data.shape[-2:])
    serial = SerialExecutor()
    local = ThreadPoolExecutor(max_workers=1)
    client = Client(
        processes=False,
        n_workers=1,
        threads_per_worker=1,
        dashboard_address=None,
    )
    dask = DaskExecutor(client)
    try:
        methods: tuple[
            tuple[OverheadOperation, str, Callable[[], object]], ...
        ] = (
            (
                "configuration",
                "SourceFinderConfig construction",
                SourceFinderConfig,
            ),
            (
                "fits-io",
                "Astropy memmap open plus complete 256-square plane read",
                lambda: np.asarray(fits.getdata(args.input)).sum(),
            ),
            (
                "partition-planning",
                "one core and clipped halo slice calculation",
                _plan_one_tile,
            ),
            (
                "serial-dispatch",
                "SerialExecutor one-batch identity map",
                lambda: serial.map_batches(_identity, (1,)),
            ),
            (
                "local-dispatch",
                "reused one-worker ThreadPoolExecutor submit and result",
                lambda: local.submit(_identity, 1).result(),
            ),
            (
                "dask-dispatch",
                "caller-owned warm in-process Dask client one-batch map",
                lambda: dask.map_batches(_identity, (1,)),
            ),
        )
        probes = tuple(
            _Probe(
                operation=operation,
                method=method,
                function=function,
                budget_seconds=float(budgets[_BUDGET_KEYS[operation]]),
            )
            for operation, method, function in methods
        )
        measurements = tuple(
            _measure(
                probe,
                warmups=args.warmups,
                repetitions=args.repetitions,
            )
            for probe in probes
        )
    finally:
        client.close()
        local.shutdown()
    environment = _environment()
    evidence = OverheadEvidence(
        schema_version=1,
        status="exploratory",
        captured_at=datetime.now(timezone.utc),
        source_commit=subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        dataset_identifier=args.dataset_id,
        dataset_content_sha256=_sha256(args.input),
        shape_yx=shape_yx,
        performance_contract_sha256=_sha256(args.performance_contract),
        environment_sha256=_canonical_sha256(
            environment.model_dump(mode="json")
        ),
        environment=environment,
        measurements=measurements,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_overhead_evidence(args.output, evidence)


if __name__ == "__main__":
    main()
