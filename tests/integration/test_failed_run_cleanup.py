# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""A failed or killed run leaves nothing a later run cannot account for.

A failed run waits for the tasks it started before it removes its staging
directory, under every executor, so no late write recreates it. A killed run
cannot remove its staging directory; the next run to the same output removes
it once its owner has provably stopped, and reports every one it finds.
"""

from __future__ import annotations

import gc
import socket
import subprocess
import sys
import threading
import time
import warnings
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from astropy.io import fits
from distributed import Client, LocalCluster

import hebog
from hebog import (
    SourceFinderConfig,
    SourceFinderRequest,
    SourceFinderStagingWarning,
)
from hebog.executors import Executor, SerialExecutor, ThreadExecutor
from hebog.io.staging import (
    OWNER_LOCK_NAME,
    OWNER_RECORD_NAME,
    StagingOwner,
    reclaim_abandoned_staging,
    staging_directory,
)
from hebog.io.zarr import ZarrProductSink
from hebog.stages import detection as detection_stage

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

pytestmark = pytest.mark.integration

# Nine 128-pixel background tiles, each its own task below, so the first
# pass runs several tasks at once on a concurrent executor.
_SHAPE_YX = (300, 300)
_CONCURRENT_THREADS = 4
# Long enough that the failure reaches the caller while the later write
# still runs, so a run returning without waiting for it is observable.
_OUTLIVING_WRITE_SECONDS = 1.0
# How long the failing write waits for another tile's write to start; the
# serial reference never starts one beside it, so it does not wait.
_LATER_WRITE_WAIT_SECONDS = 30.0


def _header(shape_yx: tuple[int, int]) -> fits.Header:
    """Return one valid ICRS image header with a four-pixel beam."""
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


def _request(tmp_path: Path, shape_yx: tuple[int, int]) -> SourceFinderRequest:
    """Write one noise image with a bright source and request its products."""
    rng = np.random.default_rng(47)
    image = rng.normal(0.0, 1e-3, shape_yx)
    image[shape_yx[0] // 2, shape_yx[1] // 2] += 0.1
    image_path = tmp_path / "image.fits"
    fits.PrimaryHDU(data=image, header=_header(shape_yx)).writeto(image_path)
    return SourceFinderRequest(
        image_path=image_path,
        output_directory=tmp_path / "products",
        run_id="cleanup",
    )


def _config() -> SourceFinderConfig:
    """Return the public configuration."""
    return SourceFinderConfig(
        detection_threshold_sigma=5.0,
        island_threshold_sigma=3.0,
        minimum_island_pixels=7,
    )


@dataclass
class _WriteProbe:
    """Chunk writes in progress, and whether one outlives the failure."""

    concurrent: bool
    lock: threading.Lock = field(default_factory=threading.Lock)
    active: int = 0
    later_write_running: threading.Event = field(
        default_factory=threading.Event
    )


def _write_failing_while_another_runs(
    probe: _WriteProbe,
) -> Callable[..., Any]:
    """Fail the first tile's write while another tile's write outlives it.

    On a concurrent executor the first tile's write fails once another
    tile's first write is running, and that write finishes after the failure
    has reached the caller. Every other write proceeds unchanged.
    """
    original = ZarrProductSink.write_chunk

    def write_chunk(sink: ZarrProductSink, **arguments: Any) -> Any:
        tile = arguments["tile"]
        first_tile = (tile.tile_y_index, tile.tile_x_index) == (0, 0)
        with probe.lock:
            probe.active += 1
            outlives = (
                not first_tile and not probe.later_write_running.is_set()
            )
            if outlives:
                probe.later_write_running.set()
        try:
            if first_tile:
                if probe.concurrent:
                    probe.later_write_running.wait(_LATER_WRITE_WAIT_SECONDS)
                raise RuntimeError("injected tile write failure")
            if outlives:
                time.sleep(_OUTLIVING_WRITE_SECONDS)
            return original(sink, **arguments)
        finally:
            with probe.lock:
                probe.active -= 1

    return write_chunk


@contextmanager
def _serial() -> Generator[Executor]:
    """Yield the deterministic reference executor."""
    yield SerialExecutor()


@contextmanager
def _threads() -> Generator[Executor]:
    """Yield one caller-owned thread pool."""
    with ThreadExecutor(_CONCURRENT_THREADS) as executor:
        yield executor


@contextmanager
def _dask() -> Generator[Executor]:
    """Yield one executor over a caller-owned in-process Dask cluster."""
    from hebog.executors import DaskExecutor  # noqa: PLC0415

    cluster = LocalCluster(
        n_workers=1,
        threads_per_worker=_CONCURRENT_THREADS,
        processes=False,
        dashboard_address=":0",
    )
    with cluster, Client(cluster) as client:
        yield DaskExecutor(client)


@pytest.fixture(
    params=[
        pytest.param(_serial, id="serial"),
        pytest.param(_threads, id="threads"),
        pytest.param(_dask, id="dask"),
    ]
)
def executor(request: pytest.FixtureRequest) -> Iterator[Executor]:
    """Yield each supported executor."""
    factory: Callable[[], AbstractContextManager[Executor]] = request.param
    with factory() as value:
        yield value
    # A failed task's traceback can keep that task's handle on the input
    # alive after the run, and the collector may then finalize the file
    # before the source that would close it. Collect it here, where the
    # failure is expected, not during whichever test runs next.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        gc.collect()


def test_a_failed_run_waits_for_its_tasks_and_leaves_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    executor: Executor,
) -> None:
    """Given a task that fails while another task is still writing,
    when the run fails,
    then the caller sees the task's own error only after no task is
    running, and nothing is left beside the output to be recreated.
    """
    request = _request(tmp_path, _SHAPE_YX)
    # One tile per task changes scheduling only, and gives a small image
    # several tasks to run at once.
    monkeypatch.setattr(detection_stage, "_CELLS_PER_TASK", 1)
    probe = _WriteProbe(
        concurrent=executor.capacity.maximum_tasks_in_flight > 1
    )
    monkeypatch.setattr(
        ZarrProductSink,
        "write_chunk",
        _write_failing_while_another_runs(probe),
    )

    with pytest.raises(RuntimeError, match="injected tile write failure"):
        hebog.find_sources(request, _config(), executor)

    assert probe.active == 0
    assert sorted(path.name for path in tmp_path.iterdir()) == ["image.fits"]


def _stopped_run_staging(output: Path, *, run_id: str) -> Path:
    """Write what a run killed while staging ``output`` leaves beside it.

    The record and a lock file nobody holds are exactly what a kill leaves,
    because the operating system releases the lock when the process ends.
    """
    directory = output.parent / f".{output.name}.killed00"
    (directory / "work").mkdir(parents=True)
    (directory / OWNER_LOCK_NAME).touch()
    owner = StagingOwner(
        output_name=output.name,
        run_id=run_id,
        host=socket.gethostname(),
        process_id=4242,
        started_utc=datetime(2026, 10, 5, 3, 0, tzinfo=UTC),
        holds_lock=True,
    )
    (directory / OWNER_RECORD_NAME).write_text(
        owner.model_dump_json(), encoding="utf-8"
    )
    return directory


def test_a_run_reclaims_what_a_stopped_run_left_and_reports_it(
    tmp_path: Path,
) -> None:
    """Given the staging directory of a run killed on this host,
    when the same request runs again,
    then it removes that directory, says so, and publishes its products.
    """
    request = _request(tmp_path, (96, 96))
    leftover = _stopped_run_staging(request.output_directory, run_id="first")

    with pytest.warns(
        SourceFinderStagingWarning,
        match=r"removed staging directory .* run 'first' .* has stopped",
    ) as caught:
        result = hebog.find_sources(request, _config(), SerialExecutor())

    # The warning points at the caller's own call, not inside Hebog.
    (staging_warning,) = (
        record
        for record in caught
        if issubclass(record.category, SourceFinderStagingWarning)
    )
    assert Path(staging_warning.filename) == Path(__file__)
    assert not leftover.exists()
    assert result.catalogue_path.is_file()
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "image.fits",
        "products",
    ]


def test_a_run_leaves_staging_whose_owner_may_still_run(
    tmp_path: Path,
) -> None:
    """Given the staging directory of a run still holding it,
    when another run to the same output starts,
    then it leaves that directory in place, says so, and still runs.
    """
    request = _request(tmp_path, (96, 96))

    with staging_directory(request.output_directory, run_id="live") as live:
        with pytest.warns(
            SourceFinderStagingWarning,
            match=r"left staging directory .* run 'live' .* may still be",
        ):
            result = hebog.find_sources(request, _config(), SerialExecutor())

        assert (live / OWNER_RECORD_NAME).is_file()

    assert result.catalogue_path.is_file()
    assert not live.exists()


_KILLED_OWNER = """
import sys
import time
from pathlib import Path

from hebog.io.staging import staging_directory

with staging_directory(Path(sys.argv[1]), run_id="killed"):
    print("staging", flush=True)
    time.sleep(120)
"""


@pytest.mark.slow
def test_killing_the_owner_lets_the_next_run_reclaim_its_staging(
    tmp_path: Path,
) -> None:
    """Given a process holding a staging directory,
    when it is killed rather than allowed to clean up,
    then its directory stays while it runs and is reclaimed once it is dead.
    """
    output = tmp_path / "products"
    # Leaving the block closes the pipe and waits for the killed process.
    with subprocess.Popen(
        [sys.executable, "-c", _KILLED_OWNER, str(output)],
        stdout=subprocess.PIPE,
        text=True,
    ) as owner:
        try:
            assert owner.stdout is not None
            assert owner.stdout.readline().strip() == "staging"
            (running,) = reclaim_abandoned_staging(output)
            assert running.status == "unproven"
        finally:
            owner.kill()

    # Windows may release a dead process's locks a moment after it exits.
    deadline = time.monotonic() + 10.0
    statuses = [
        leftover.status for leftover in reclaim_abandoned_staging(output)
    ]
    while statuses == ["unproven"] and time.monotonic() < deadline:
        time.sleep(0.1)
        statuses = [
            leftover.status for leftover in reclaim_abandoned_staging(output)
        ]

    assert statuses == ["reclaimed"]
    assert list(tmp_path.iterdir()) == []
