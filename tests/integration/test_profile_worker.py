# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Complete-execution profile worker contract under every executor."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from astropy.io import fits
from conftest import (
    radio_header,
    two_source_image,
)

_ROOT = Path(__file__).parents[2]
_WORKER = _ROOT / "scripts/benchmark/profile_complete_execution_worker.py"
_SETTINGS = {
    "detection_threshold_sigma": 5.0,
    "island_threshold_sigma": 3.0,
    "minimum_island_pixels": 7,
    "profile": "continuum",
}
_ROOT_STAGE = ["find_sources"]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        importlib.util.find_spec("resource") is None,
        reason="stage timing needs the POSIX resource module",
    ),
]


def _profile(tmp_path: Path, *arguments: str) -> dict[str, Any]:
    """Profile a two-source image once and return the worker's record."""
    image = tmp_path / "image.fits"
    fits.PrimaryHDU(
        data=two_source_image(), header=radio_header((192, 192))
    ).writeto(image)
    result = tmp_path / "profile.json"
    subprocess.run(
        [
            sys.executable,
            str(_WORKER),
            "--input",
            str(image),
            "--result",
            str(result),
            "--settings",
            json.dumps(_SETTINGS),
            *arguments,
        ],
        check=True,
        capture_output=True,
    )
    return cast(dict[str, Any], json.loads(result.read_text("utf-8")))


_EXECUTORS = pytest.mark.parametrize(
    ("arguments", "executor"),
    [
        pytest.param((), {"kind": "serial", "workers": 1}, id="serial"),
        pytest.param(
            ("--threads", "2", "--memory-budget-bytes", "4000000000"),
            {
                "kind": "threads",
                "workers": 2,
                "threads_per_worker": 1,
                "memory_budget_bytes": 4_000_000_000,
            },
            id="threads",
        ),
        pytest.param(
            ("--dask-workers", "2", "--memory-budget-bytes", "4000000000"),
            {
                "kind": "dask",
                "workers": 2,
                "threads_per_worker": 1,
                "memory_budget_bytes": 4_000_000_000,
                "worker_memory_limit_bytes": 2_000_000_000,
            },
            id="dask",
        ),
    ],
)


@_EXECUTORS
def test_every_task_is_recorded_and_attributed_to_the_run(
    tmp_path: Path, arguments: tuple[str, ...], executor: dict[str, Any]
) -> None:
    """Every task runs inside the root stage, so all are attributed to it.

    Tasks time themselves where they run, on the host's clock, so this holds
    for inline, pool-thread and worker-process tasks however loaded the
    machine is. Stage timing happens in the driver, and each stage's
    occupancy is the share of the workers its tasks kept busy.
    """
    record = _profile(tmp_path, *arguments)

    described = dict(record["executor"])
    if executor["kind"] == "dask":
        assert described.pop("largest_worker_peak_rss_bytes") > 0
    assert described == executor
    assert record["source_count"] == 2
    tasks = record["tasks"]
    assert tasks["count"] > 0
    assert tasks["task_seconds"] > 0.0
    stages = {tuple(item["stage"]): item for item in tasks["stages"]}
    assert set(stages) == {tuple(item["stage"]) for item in record["stages"]}
    root = stages[tuple(_ROOT_STAGE)]
    assert root["task_count"] == tasks["count"]
    assert root["task_seconds"] == pytest.approx(tasks["task_seconds"])
    assert root["zarr_io"]["written_chunks"] > 0
    assert root["zarr_io"]["read_bytes"] > 0
    for item in stages.values():
        assert 0.0 <= item["worker_occupancy"] <= 1.0 + 1e-9
        assert item["executor_idle_seconds"] >= 0.0


def test_every_executor_runs_and_records_the_same_tasks(
    tmp_path: Path,
) -> None:
    """The same plan runs everywhere, so its tasks and chunks are the same.

    A worker process that failed to count its own I/O, or a task the
    recording missed, would make one executor's totals differ.
    """
    totals = []
    for index, arguments in enumerate(
        ((), ("--threads", "2"), ("--dask-workers", "2"))
    ):
        directory = tmp_path / str(index)
        directory.mkdir()
        record = _profile(directory, *arguments)
        root = next(
            item
            for item in record["tasks"]["stages"]
            if item["stage"] == _ROOT_STAGE
        )
        rounds = sorted(
            (item["round"], item["task_count"])
            for item in record["tasks"]["rounds"]
        )
        totals.append((record["tasks"]["count"], rounds, root["zarr_io"]))

    assert totals[0] == totals[1] == totals[2]


def test_profile_workers_admit_by_their_limit_and_never_pause_or_restart() -> (
    None
):
    """The limit is what Hebog admits tasks by, and nothing else.

    Hebog's workers hold no data between tasks, so Dask's spilling, pausing
    and restarting would act on the allocator's retained pages instead of
    on Hebog. A limit far below a worker's own memory would otherwise pause
    or restart it before any task runs.
    """
    from distributed import Client  # noqa: PLC0415

    from hebog.validation.profile_cluster import (  # noqa: PLC0415
        local_profile_cluster,
    )

    def memory_policy(dask_worker: Any) -> tuple[int, list[object]]:
        import dask.config  # noqa: PLC0415

        return dask_worker.memory_manager.memory_limit, [
            dask.config.get(f"distributed.worker.memory.{name}")
            for name in ("target", "spill", "pause", "terminate")
        ]

    cluster = local_profile_cluster(2, memory_limit_bytes=1_000)
    with cluster, Client(cluster, timeout="60s") as client:
        policies = cast(
            dict[str, tuple[int, list[object]]], client.run(memory_policy)
        )

    assert sorted(policies.values()) == [(1_000, [False] * 4)] * 2
