# pyright: reportMissingTypeStubs=false
"""Shared integration helpers: executors, and published stage inputs."""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

import numpy as np
import numpy.typing as npt
import pytest
from distributed import Client, LocalCluster

from hebog import SourceFinderResult
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.data_models.partitioning import ImageBounds
from hebog.data_models.products import ProductChunk
from hebog.executors import (
    DaskExecutor,
    Executor,
    SerialExecutor,
    TaskRequirement,
    ThreadExecutor,
)
from hebog.io.zarr import ZarrProductSink

_BACKGROUND_TILE_SHAPE_YX = (128, 128)
_Input = TypeVar("_Input")
_Output = TypeVar("_Output")


@contextmanager
def _serial_executor() -> Generator[Executor]:
    """Yield the deterministic reference executor."""
    yield SerialExecutor()


@contextmanager
def _thread_executor() -> Generator[Executor]:
    """Yield a caller-owned pool of four threads in this process."""
    with ThreadExecutor(thread_count=4) as executor:
        yield executor


@contextmanager
def _dask_executor() -> Generator[Executor]:
    """Yield a caller-owned client of two single-threaded in-process workers.

    In-process workers share this process, so no task result crosses a
    process boundary; the process-worker run in
    ``test_public_find_sources.py`` is the one that does.
    """
    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        # A random port, so parallel test workers never contend for one.
        dashboard_address=":0",
    )
    with cluster, Client(cluster) as client:
        yield DaskExecutor(client)


@pytest.fixture(
    params=(
        pytest.param(_serial_executor, id="serial"),
        pytest.param(_thread_executor, id="threads"),
        pytest.param(_dask_executor, id="dask"),
    )
)
def each_executor(request: pytest.FixtureRequest) -> Iterator[Executor]:
    """Yield every supported executor in turn, each closed afterwards.

    A product contract that holds for one executor must hold for all of
    them, so a test of it takes this fixture and runs under each.
    """
    open_executor: Callable[[], AbstractContextManager[Executor]] = (
        request.param
    )
    with open_executor() as executor:
        yield executor


def _publish_background_rms(
    work_directory: Path,
    background_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
    generation_id: str,
) -> ZarrProductSink:
    """Publish one analytic background/RMS generation.

    A test that substitutes the background stage still has to give the later
    passes a published generation to read, because no image-sized plane
    reaches a stage through the executor.
    """
    manifest = plan_image_partitions(
        image_shape_yx=background_jy_per_beam.shape,
        tile_core_shape_yx=_BACKGROUND_TILE_SHAPE_YX,
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "background.zarr",
        manifest,
        generation_id=generation_id,
    )
    planes: tuple[tuple[str, npt.NDArray[Any], np.dtype[Any]], ...] = (
        ("background", background_jy_per_beam, np.dtype("<f8")),
        ("rms", rms_jy_per_beam, np.dtype("<f8")),
    )
    for product_name, _, dtype in planes:
        sink.initialize_product(product_name=product_name, dtype=dtype)
    chunks: list[ProductChunk] = []
    for tile in manifest.tiles:
        bounds = tile.core_bounds
        selection = (
            slice(bounds.y_start, bounds.y_stop),
            slice(bounds.x_start, bounds.x_stop),
        )
        for product_name, values, dtype in planes:
            chunks.append(
                sink.write_chunk(
                    product_name=product_name,
                    tile=tile,
                    values=np.asarray(values[selection], dtype=dtype),
                )
            )
    sink.publish_generation(
        product_names=tuple(name for name, _, _ in planes),
        chunks=chunks,
    )
    return sink


EstimatedNoise = tuple[ZarrProductSink, bool]

SubstituteBackgroundRms = Callable[
    [
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ],
    Callable[..., EstimatedNoise],
]


def _substituted_background_rms(
    image_jy_per_beam: npt.NDArray[np.float64],
    background_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
) -> Callable[..., EstimatedNoise]:
    """Return a stand-in for the background stage over analytic planes.

    The stage publishes its estimate and answers the one question the
    composition asks of it: whether any pixel has a usable local noise
    estimate. The substitute has to do both. Keeping the work-directory
    argument's position here means one place knows it.
    """

    def estimate(
        *args: object,
        generation_id: str,
        **_kwargs: object,
    ) -> EstimatedNoise:
        """Publish the analytic planes and answer for their usable domain."""
        sink = _publish_background_rms(
            cast(Path, args[4]),
            background_jy_per_beam,
            rms_jy_per_beam,
            generation_id,
        )
        usable = bool(
            np.any(np.isfinite(image_jy_per_beam) & (rms_jy_per_beam > 0.0))
        )
        return sink, usable

    return estimate


@pytest.fixture
def substituted_background_rms() -> SubstituteBackgroundRms:
    """Return a helper standing in for the whole background/RMS stage."""
    return _substituted_background_rms


def product_hashes(result: SourceFinderResult) -> tuple[str, ...]:
    """Return the content identity of every published product.

    The order is catalogue, RMS, mask and diagnostics.
    """
    return (
        result.catalogue.content_sha256,
        result.rms.content_sha256,
        result.mask.content_sha256,
        result.diagnostics.content_sha256,
    )


def published_plane(
    sink: ZarrProductSink,
    product_name: str,
    dtype: npt.DTypeLike | None = None,
) -> npt.NDArray[Any]:
    """Read one complete published plane from the generation that wrote it.

    No pass hands its planes on any more, so a test comparing published
    pixels reads them back from the store that holds them. ``dtype`` is the
    type the caller reads them as; omitting it keeps the published one.
    """
    height, width = sink.manifest.image_shape_yx
    window = sink.read_completed_window(
        product_name, ImageBounds(0, height, 0, width)
    )
    return np.asarray(window) if dtype is None else np.asarray(window, dtype)


def estimated_maps(
    sink: ZarrProductSink,
    shape_yx: tuple[int, int],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Read the background and RMS estimates one generation published.

    The stage returns only its own decision about the estimate, so a test
    about the estimate itself reads it back from the store that holds it.
    """
    assert sink.manifest.image_shape_yx == shape_yx
    return (
        published_plane(sink, "background", np.float64),
        published_plane(sink, "rms", np.float64),
    )


class RecordingExecutor(SerialExecutor):
    """Keep what every round sent to its tasks and what they returned.

    Each entry names the task function, so a test can ask what crossed the
    executor boundary in one round without depending on round order.
    """

    def __init__(self) -> None:
        """Start with no recorded round."""
        super().__init__()
        self.rounds: list[tuple[str, tuple[object, ...], tuple[object, ...]]]
        self.rounds = []

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Evaluate serially and record the round's payloads and results."""
        materialized = tuple(batches)
        results = super().map_batches(
            function, materialized, requirement=requirement
        )
        name = cast(Any, getattr(function, "func", function)).__name__
        self.rounds.append((name, materialized, tuple(results)))
        return results


def carried_array_bytes(
    value: object,
    *,
    exempt: tuple[type, ...] = (),
) -> tuple[int, int]:
    """Return the array bytes one payload carries, and how many were exempt.

    Records, tuples and mappings are walked, so an array nested anywhere in
    what a task receives or returns is counted. An instance of an ``exempt``
    type is not walked; the second count says how many were met, so a test
    can require its exemption to still match something.
    """
    if isinstance(value, exempt):
        return 0, 1
    if isinstance(value, np.ndarray):
        return int(cast(npt.NDArray[Any], value).nbytes), 0
    children: Iterable[object]
    if is_dataclass(value) and not isinstance(value, type):
        children = (getattr(value, item.name) for item in fields(value))
    elif isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        children = (*mapping.keys(), *mapping.values())
    elif isinstance(value, tuple | list | set | frozenset):
        children = cast(Iterable[object], value)
    else:
        return 0, 0
    carried = 0
    exempted = 0
    for child in children:
        child_bytes, child_exempted = carried_array_bytes(child, exempt=exempt)
        carried += child_bytes
        exempted += child_exempted
    return carried, exempted
