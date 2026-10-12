# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""Rapthor's filter step running Hebog, as Given/When/Then scenarios.

`config/contracts/phase-0-public-behaviours.json` names the test that holds
each behaviour. Each scenario runs one small sector through
:func:`hebog.adapters.find_sector_sources` as Rapthor's Prefect task would,
on the executor the task builds.
"""

from __future__ import annotations

import ctypes
import hashlib
import pickle
import shutil
import threading
import time
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
import pytest
from astropy.io import fits
from distributed import Client, LocalCluster

from hebog.adapters import (
    RapthorCompatibilityConfig,
    RapthorSourceFindingRequest,
    RapthorSourceFindingResult,
    find_sector_sources,
)
from hebog.adapters.rapthor_catalogue import (
    RAPTHOR_CATALOGUE_COLUMNS,
    read_rapthor_catalogue_fits,
)
from hebog.adapters.rapthor_comparison import (
    RapthorDualRunReport,
    RapthorSectorProducts,
    compare_sector_products,
)
from hebog.data_models import PublicSourceFindingDiagnostics
from hebog.executors import (
    DaskExecutor,
    Executor,
    ExecutorCapacity,
    SerialExecutor,
    TaskRequirement,
    ThreadExecutor,
)
from hebog.io import read_diagnostics_product
from hebog.pipeline import SourceFinderError, SourceFinderImageTooLargeError

pytestmark = pytest.mark.acceptance

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SHAPE_YX = (81, 97)


@contextmanager
def _serial(*, retry_limit: int = 0) -> Generator[Executor]:
    yield SerialExecutor(retry_limit=retry_limit)


@contextmanager
def _threads(*, retry_limit: int = 0) -> Generator[Executor]:
    with ThreadExecutor(thread_count=4, retry_limit=retry_limit) as executor:
        yield executor


@contextmanager
def _dask(*, retry_limit: int = 0) -> Generator[Executor]:
    """Yield a client of two single-threaded in-process workers."""
    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address=":0",
    )
    with cluster, Client(cluster) as client:
        yield DaskExecutor(client, retry_limit=retry_limit)


_EVERY_EXECUTOR = pytest.mark.parametrize(
    "make_executor",
    [
        pytest.param(_serial, id="serial"),
        pytest.param(_threads, id="threads"),
        pytest.param(_dask, id="dask"),
    ],
)


def _header(
    width: int = _SHAPE_YX[1], height: int = _SHAPE_YX[0]
) -> fits.Header:
    """Return a WSClean-style header: celestial, then frequency and Stokes."""
    header = fits.Header()
    header["BUNIT"] = "JY/BEAM"
    header["BMAJ"] = 4.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = width / 2 + 1
    header["CRPIX2"] = height / 2 + 1
    header["CRVAL1"] = 242.75
    header["CRVAL2"] = 54.95
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["CUNIT1"] = "deg"
    header["CUNIT2"] = "deg"
    header["CTYPE3"] = "FREQ"
    header["CRPIX3"] = 1.0
    header["CRVAL3"] = 143_650_000.0
    header["CDELT3"] = 23_437_500.0
    header["CUNIT3"] = "Hz"
    header["CTYPE4"] = "STOKES"
    header["CRPIX4"] = 1.0
    header["CRVAL4"] = 1.0
    header["CDELT4"] = 1.0
    header["CUNIT4"] = ""
    return header


def _write(path: Path, plane: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    height, width = plane.shape
    data = np.asarray(plane, dtype=np.float32)[np.newaxis, np.newaxis]
    fits.PrimaryHDU(data=data, header=_header(width, height)).writeto(path)
    return path


def _sector(directory: Path) -> RapthorSourceFindingRequest:
    """Given a sector: compact sources, outward-rising noise, a blank edge."""
    y_pixels, x_pixels = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    flat_noise = np.random.default_rng(7).normal(0.0, 1.0, _SHAPE_YX)
    for y, x, peak in ((40, 30, 40.0), (25, 70, 20.0), (60, 60, 12.0)):
        flat_noise += peak * np.exp(
            -((x_pixels - x) ** 2 + (y_pixels - y) ** 2) / 4.0
        )
    flat_noise[:, :4] = np.nan
    primary_beam = np.exp(
        -((x_pixels - 48.0) ** 2 + (y_pixels - 40.0) ** 2) / (2.0 * 70.0**2)
    )
    images = directory / "images"
    return RapthorSourceFindingRequest(
        true_sky_image_path=_write(
            images / "sector_1-MFS-image-pb.fits", flat_noise / primary_beam
        ),
        flat_noise_image_path=_write(
            images / "sector_1-MFS-image.fits", flat_noise
        ),
        output_root=directory / "pipeline" / "sector_1",
        run_id="image_1-sector_1",
    )


def _config() -> RapthorCompatibilityConfig:
    return RapthorCompatibilityConfig(threshpix=5.0, threshisl=3.0)


def _rapthor_files(result: RapthorSourceFindingResult) -> tuple[Path, ...]:
    return (
        result.source_catalog_path,
        result.true_sky_rms_path,
        result.flat_noise_rms_path,
        result.mask_path,
    )


def _rapthor_names(request: RapthorSourceFindingRequest) -> tuple[Path, ...]:
    directory = request.output_root.parent
    return (
        directory / "sector_1.source_catalog.fits",
        directory / "sector_1.true_sky_rms.fits",
        directory / "sector_1.flat_noise_rms.fits",
        directory / "sector_1-MFS-image-pb.fits.mask.fits",
    )


def _contents(paths: Iterable[Path]) -> tuple[bytes, ...]:
    return tuple(path.read_bytes() for path in paths)


class _WrappingExecutor:
    """Run every task through ``wrap``, on the executor the caller built."""

    def __init__(
        self, inner: Executor, wrap: Callable[[Callable[..., Any]], Any]
    ) -> None:
        self._inner = inner
        self._wrap = wrap

    @property
    def capacity(self) -> ExecutorCapacity:
        return self._inner.capacity

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        return self._inner.map_batches(
            self._wrap(function), batches, requirement=requirement
        )


class _CountingExecutor(SerialExecutor):
    """Serial executor that counts the maps it is given."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        self.calls += 1
        return super().map_batches(function, batches, requirement=requirement)


class _WorkerLostError(ConnectionError):
    """The worker running a task went away before the task finished."""


@dataclass(frozen=True)
class _LostOnce:
    """A task whose first attempt is lost with its worker.

    The marker directory records which payloads have been attempted, so the
    loss happens once per task under every executor, in any thread.
    """

    function: Callable[..., Any]
    markers: Path

    def __call__(self, *arguments: Any) -> Any:
        payload = hashlib.sha256(pickle.dumps(arguments)).hexdigest()
        try:
            (self.markers / payload).touch(exist_ok=False)
        except FileExistsError:
            return self.function(*arguments)
        raise _WorkerLostError("the worker running this task was lost")


_ACTIVITY_LOCK = threading.Lock()
_ACTIVITY = {"started": 0, "finished": 0}
_A_TASK_IS_RUNNING = threading.Event()
# Long enough that tasks are still running, or waiting to run, when the
# caller's deadline passes.
_TASK_SECONDS = 0.05


@dataclass(frozen=True)
class _Tracked:
    """A task that records when it starts and when it ends."""

    function: Callable[..., Any]

    def __call__(self, *arguments: Any) -> Any:
        with _ACTIVITY_LOCK:
            _ACTIVITY["started"] += 1
        _A_TASK_IS_RUNNING.set()
        try:
            time.sleep(_TASK_SECONDS)
            return self.function(*arguments)
        finally:
            with _ACTIVITY_LOCK:
                _ACTIVITY["finished"] += 1


class _CallerDeadlineError(Exception):
    """The caller's deadline for the analysis passed."""


def _raise_in(thread: threading.Thread, error: type[BaseException]) -> None:
    """Raise ``error`` in ``thread`` at its next bytecode.

    This is how Prefect enforces a synchronous task's timeout when the task
    runs off the main thread, as it does on a Dask worker: through CPython's
    ``PyThreadState_SetAsyncExc``.
    """
    assert thread.ident is not None
    raised = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread.ident), ctypes.py_object(error)
    )
    assert raised == 1


@_EVERY_EXECUTOR
def test_a_sector_run_writes_the_products_rapthor_reads(
    tmp_path: Path, make_executor: Callable[..., Any]
) -> None:
    """Given a sector, then Rapthor's four files and the count are returned.

    When Rapthor's task runs the adapter on the executor it built, then the
    catalogue holds the eight columns Rapthor reads, one row a source; both
    RMS maps cover the sector; and the island mask has PyBDSF's four axes,
    ready for LSMTool's ``filter_sources``.
    """
    request = _sector(tmp_path)

    with make_executor() as executor:
        result = find_sector_sources(request, _config(), executor)

    assert _rapthor_files(result) == _rapthor_names(request)
    catalogue = read_rapthor_catalogue_fits(result.source_catalog_path)
    assert tuple(catalogue.colnames) == RAPTHOR_CATALOGUE_COLUMNS
    assert len(catalogue) == result.source_count == 3
    for rms_path in (result.true_sky_rms_path, result.flat_noise_rms_path):
        rms = np.asarray(fits.getdata(rms_path), dtype=np.float64)
        assert rms.shape == _SHAPE_YX
        assert np.all(np.isfinite(rms[:, 4:]))
        assert np.all(rms[:, 4:] > 0)
    mask = np.asarray(fits.getdata(result.mask_path), dtype=np.float32)
    assert mask.shape == (1, 1, *_SHAPE_YX)
    assert set(np.unique(mask)) == {0.0, 1.0}


def test_a_retried_task_reuses_the_finished_analysis(tmp_path: Path) -> None:
    """Given a finished run whose mask LSMTool clipped, nothing is recomputed.

    When Rapthor's task fails after the adapter returned and is retried with
    the same request, then no task runs, and Rapthor's four files are
    written again from the finished analysis, the clipped mask included.
    """
    request = _sector(tmp_path)
    first = find_sector_sources(request, _config(), SerialExecutor())
    expected = _contents(_rapthor_files(first))
    with fits.open(first.mask_path, mode="update") as mask:
        mask[0].data[:] = 0.0
    retry_executor = _CountingExecutor()

    retried = find_sector_sources(request, _config(), retry_executor)

    assert retry_executor.calls == 0
    assert _contents(_rapthor_files(retried)) == expected
    assert retried.source_count == first.source_count


@_EVERY_EXECUTOR
def test_a_lost_task_is_retried_and_the_products_are_unchanged(
    tmp_path: Path, make_executor: Callable[..., Any]
) -> None:
    """Given every task's first attempt lost with its worker.

    When the executor retries idempotent tasks once, then the run completes
    and Rapthor's files equal those of a run that lost nothing.
    """
    expected = find_sector_sources(
        _sector(tmp_path / "no-loss"), _config(), SerialExecutor()
    )
    markers = tmp_path / "attempts"
    markers.mkdir()

    with make_executor(retry_limit=1) as executor:
        result = find_sector_sources(
            _sector(tmp_path / "loss"),
            _config(),
            _WrappingExecutor(
                executor, lambda function: _LostOnce(function, markers)
            ),
        )

    assert any(markers.iterdir())
    assert _contents(_rapthor_files(result)) == _contents(
        _rapthor_files(expected)
    )


def test_a_refused_sector_leaves_rapthor_free_to_fall_back(
    tmp_path: Path,
) -> None:
    """Given a sector wider than Hebog admits, Rapthor can use PyBDSF.

    When the adapter refuses it, then the failure is a typed
    ``SourceFinderError`` that Rapthor's fallback catches, and none of
    Rapthor's four files exists, an earlier run's included, so the
    products Rapthor reads afterwards are the fallback's alone.
    """
    wide = np.random.default_rng(3).normal(0.0, 1.0, (8, 15_403))
    images = tmp_path / "images"
    request = RapthorSourceFindingRequest(
        true_sky_image_path=_write(
            images / "sector_1-MFS-image-pb.fits", wide
        ),
        flat_noise_image_path=_write(images / "sector_1-MFS-image.fits", wide),
        output_root=tmp_path / "pipeline" / "sector_1",
        run_id="image_1-sector_1",
    )
    for path in _rapthor_names(request):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"an earlier cycle's product")

    with pytest.raises(SourceFinderError) as refusal:
        find_sector_sources(request, _config(), SerialExecutor())

    assert isinstance(refusal.value, SourceFinderImageTooLargeError)
    assert not any(path.exists() for path in _rapthor_names(request))
    for path in _rapthor_names(request):
        path.write_bytes(b"PyBDSF's product")
    assert _contents(_rapthor_names(request)) == (b"PyBDSF's product",) * 4


@pytest.mark.parametrize(
    "make_executor",
    [
        pytest.param(_threads, id="threads"),
        pytest.param(_dask, id="dask"),
    ],
)
def test_a_cancelled_analysis_stops_its_tasks_and_removes_its_staging(
    tmp_path: Path, make_executor: Callable[..., Any]
) -> None:
    """Given an analysis with tasks running, when the caller's deadline passes.

    Then the call raises the caller's error only once every task it started
    has finished, no task it submitted starts afterwards, and neither its
    staging directory nor any of Rapthor's files remains.
    """
    request = _sector(tmp_path)
    with _ACTIVITY_LOCK:
        _ACTIVITY.update(started=0, finished=0)
    _A_TASK_IS_RUNNING.clear()
    outcome: dict[str, BaseException | None] = {}
    activity_when_raised: dict[str, int] = {}

    with make_executor() as executor:
        tracked = _WrappingExecutor(executor, _Tracked)

        def run_rapthor_task() -> None:
            try:
                find_sector_sources(request, _config(), tracked)
            except BaseException as error:
                with _ACTIVITY_LOCK:
                    activity_when_raised.update(_ACTIVITY)
                outcome["error"] = error
            else:
                outcome["error"] = None

        task = threading.Thread(target=run_rapthor_task)
        task.start()
        assert _A_TASK_IS_RUNNING.wait(timeout=60)
        _raise_in(task, _CallerDeadlineError)
        task.join(timeout=120)
        assert not task.is_alive()
        time.sleep(10 * _TASK_SECONDS)

    assert isinstance(outcome["error"], _CallerDeadlineError)
    assert activity_when_raised["started"] >= 1
    assert activity_when_raised["started"] == activity_when_raised["finished"]
    assert _ACTIVITY["started"] == activity_when_raised["started"]
    pipeline = request.output_root.parent
    assert sorted(path.name for path in pipeline.iterdir()) == []
    assert not any(path.exists() for path in _rapthor_names(request))


def test_dual_run_keeps_products_and_reports_separate(tmp_path: Path) -> None:
    """Given dual-run mode, then products and reports retain provenance.

    Given one sector run by Hebog and by pinned PyBDSF ``master``, each
    under its own output root, when the two are compared, then neither
    product set changes, and the report binds the bytes of all eight files
    and Hebog's provenance, beside the agreement it measured, before Rapthor
    selects either.
    """
    reference = Path(__file__).parents[1] / "data" / "pybdsf"
    image = reference / "pybdsf-compact-reference-256" / "input.fits"
    pybdsf_run = reference / "pybdsf-compact-reference-256" / "master"
    hebog = find_sector_sources(
        RapthorSourceFindingRequest(
            true_sky_image_path=image,
            flat_noise_image_path=image,
            output_root=tmp_path / "hebog" / "sector_1",
            run_id="image_1-sector_1",
        ),
        _config(),
        SerialExecutor(),
    )
    pybdsf = RapthorSectorProducts.named(
        tmp_path / "pybdsf" / "sector_1", image
    )
    pybdsf.mask_path.parent.mkdir(parents=True)
    for name, path in (
        ("source_catalog.fits", pybdsf.source_catalog_path),
        ("true_sky_rms.fits", pybdsf.true_sky_rms_path),
        ("flat_noise_rms.fits", pybdsf.flat_noise_rms_path),
        ("source_filter_mask.fits", pybdsf.mask_path),
    ):
        shutil.copyfile(pybdsf_run / name, path)
    both = (*_rapthor_files(hebog), *pybdsf.paths())
    before = _contents(both)

    report = compare_sector_products(
        hebog, pybdsf, tmp_path / "sector_1.dual_run.json"
    )

    assert _contents(both) == before
    assert (
        RapthorDualRunReport.model_validate_json(
            (tmp_path / "sector_1.dual_run.json").read_bytes()
        )
        == report
    )
    for identity, path in zip(
        (
            report.hebog.source_catalog,
            report.hebog.true_sky_rms,
            report.hebog.flat_noise_rms,
            report.hebog.mask,
            report.pybdsf.source_catalog,
            report.pybdsf.true_sky_rms,
            report.pybdsf.flat_noise_rms,
            report.pybdsf.mask,
        ),
        both,
        strict=True,
    ):
        assert identity.path == path.as_posix()
        assert identity.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    diagnostics = read_diagnostics_product(
        hebog.products_directory / "diagnostics.json"
    )
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert report.hebog_provenance == diagnostics.provenance
    assert report.hebog.source_count == hebog.source_count
    assert report.pybdsf.source_count == 3
    assert report.matched_source_count == 3
    assert report.median_total_flux_ratio == pytest.approx(1.0, abs=0.1)
    assert report.true_sky_rms_median_ratio == pytest.approx(1.0, abs=0.1)
    assert report.shared_mask_pixel_count > 0
