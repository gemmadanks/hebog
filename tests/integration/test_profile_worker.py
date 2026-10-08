# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Complete-execution profile worker contract under both executors."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from distributed import Client, LocalCluster, Worker, get_task_stream

from hebog.validation.profile_cluster import (
    SharedClockWorker,
    local_profile_cluster,
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
# Far beyond any task here, so a shifted record cannot contain its reading.
_FORCED_ESTIMATE_SECONDS = 1000.0

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        importlib.util.find_spec("resource") is None,
        reason="stage timing needs the POSIX resource module",
    ),
]


def _header(shape_yx: tuple[int, int]) -> fits.Header:
    """Return one valid ICRS radio-continuum FITS header."""
    height, width = shape_yx
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = 4.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = width / 2 + 1
    header["CRPIX2"] = height / 2 + 1
    header["CRVAL1"] = 180.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["CUNIT1"] = "deg"
    header["CUNIT2"] = "deg"
    header["RESTFRQ"] = 150_000_000.0
    return header


def _two_source_image() -> npt.NDArray[np.float64]:
    """Return noise with two bright beam-shaped sources."""
    y_pixels, x_pixels = np.mgrid[:192, :192]
    values = np.random.default_rng(20260929).normal(0.0, 1.0e-4, (192, 192))
    for y, x in ((48.0, 60.0), (140.0, 120.0)):
        values += 0.01 * np.exp(
            -(((x_pixels - x) ** 2 + (y_pixels - y) ** 2) / 8.0)
        )
    return values


def _profile(tmp_path: Path, *arguments: str) -> dict[str, Any]:
    """Profile a two-source image once and return the worker's record."""
    image = tmp_path / "image.fits"
    fits.PrimaryHDU(
        data=_two_source_image(), header=_header((192, 192))
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


def test_serial_profile_records_no_tasks(tmp_path: Path) -> None:
    record = _profile(tmp_path)

    assert record["executor"] == {"kind": "serial"}
    assert record["tasks"] is None
    assert record["source_count"] == 2


def test_dask_profile_attributes_every_task_to_the_run(tmp_path: Path) -> None:
    """Every task runs inside the root stage, so all are attributed to it.

    The workers report task times on the driver's clock, so this holds
    however loaded the machine is. Stage timing still happens in the driver,
    and each stage's occupancy is the share of the two workers its tasks
    kept busy, so it lies in [0, 1].
    """
    record = _profile(tmp_path, "--dask-workers", "2")

    assert record["executor"] == {
        "kind": "dask",
        "workers": 2,
        "threads_per_worker": 1,
    }
    assert record["source_count"] == 2
    tasks = record["tasks"]
    assert tasks["count"] > 0
    assert tasks["compute_seconds"] > 0.0
    stages = {tuple(item["stage"]): item for item in tasks["stages"]}
    assert set(stages) == {tuple(item["stage"]) for item in record["stages"]}
    root = stages[tuple(_ROOT_STAGE)]
    assert root["task_count"] == tasks["count"]
    assert root["task_seconds"] == pytest.approx(tasks["compute_seconds"])
    for item in stages.values():
        assert 0.0 <= item["worker_occupancy"] <= 1.0 + 1e-9


class _FixedOffsetWorker(Worker):
    """A worker whose clock-offset estimate stays at the forced value."""

    @property
    def scheduler_delay(self) -> float:
        return _FORCED_ESTIMATE_SECONDS

    @scheduler_delay.setter
    def scheduler_delay(self, estimate: float) -> None:  # pyright: ignore[reportIncompatibleVariableOverride]
        del estimate


def _in_process_cluster(worker_class: type[Worker]) -> LocalCluster:
    """Return one single-threaded ``worker_class`` worker in this process."""
    return LocalCluster(
        n_workers=1,
        threads_per_worker=1,
        processes=False,
        dashboard_address=":0",
        worker_class=worker_class,
    )


@pytest.mark.parametrize(
    ("open_cluster", "recorded_shift_seconds"),
    [
        pytest.param(
            lambda: local_profile_cluster(1), 0.0, id="profile cluster"
        ),
        pytest.param(
            lambda: _in_process_cluster(SharedClockWorker),
            0.0,
            id="shared-clock worker",
        ),
        # The control: a worker that keeps an estimate shifts its records by
        # it, so the rows above would fail had their workers kept theirs.
        pytest.param(
            lambda: _in_process_cluster(_FixedOffsetWorker),
            _FORCED_ESTIMATE_SECONDS,
            id="fixed-offset worker",
        ),
    ],
)
def test_profile_workers_ignore_their_clock_offset_estimate(
    open_cluster: Callable[[], LocalCluster], recorded_shift_seconds: float
) -> None:
    """A profile worker reports task times on the driver's clock.

    A Dask worker adds ``scheduler_delay``, its heartbeat estimate of its
    clock's offset from the scheduler's, to the times of the tasks it runs.
    On one host the true offset is zero, so the profile's workers discard
    every estimate, here one far larger than any heartbeat would make.
    """

    def force_estimate(dask_worker: Worker) -> None:
        # What every heartbeat does with its new estimate.
        dask_worker.scheduler_delay = _FORCED_ESTIMATE_SECONDS

    cluster = open_cluster()
    with cluster, Client(cluster, timeout="60s") as client:
        client.run(force_estimate)
        task_stream = get_task_stream(client=client)
        with task_stream:
            futures = [client.submit(time.time, pure=False) for _ in range(4)]
            readings = dict(
                zip(
                    (cast(str, future.key) for future in futures),
                    cast(list[float], client.gather(futures)),
                    strict=True,
                )
            )
    steps = [
        (cast(str, task["key"]), cast(dict[str, Any], step))
        for task in cast(list[dict[str, Any]], task_stream.data)
        for step in task["startstops"]
        if step["action"] == "compute"
    ]

    assert sorted(key for key, _ in steps) == sorted(readings)
    for key, step in steps:
        # The task read the clock between its recorded start and stop.
        assert (
            step["start"]
            <= readings[key] + recorded_shift_seconds
            <= step["stop"]
        )
