# pyright: reportPrivateUsage=false
"""The profile's task recording counts the Zarr chunks each task moves."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from hebog.data_models import ImageBounds, PartitionManifest
from hebog.executors import SerialExecutor, ThreadExecutor
from hebog.io import ZarrProductSink
from hebog.validation.task_recording import (
    RecordingExecutor,
    ZarrIO,
    drain_driver_zarr_io,
)

pytestmark = pytest.mark.integration

# Four 3x4 cores of float64: two whole, two clipped by the image edge.
_MANIFEST = PartitionManifest.create(
    image_shape_yx=(5, 7),
    tile_core_shape_yx=(3, 4),
    halo_yx=(0, 0),
)
_WHOLE_IMAGE = ImageBounds(y_start=0, y_stop=5, x_start=0, x_stop=7)


def _published_sink(root: Path) -> ZarrProductSink:
    """Write and publish one float64 plane of four chunks."""
    sink = ZarrProductSink(root, _MANIFEST, generation_id="recording")
    sink.initialize_product(product_name="plane", dtype=np.dtype("<f8"))
    records = tuple(
        sink.write_chunk(
            product_name="plane",
            tile=tile,
            values=np.full(tile.core_bounds.shape_yx, float(index)),
        )
        for index, tile in enumerate(_MANIFEST.tiles)
    )
    sink.publish_generation(product_names=("plane",), chunks=records)
    return sink


def _read_plane(sink: ZarrProductSink) -> float:
    """Read every chunk of the plane once, as a task's window read does."""
    return float(sink.read_completed_window("plane", _WHOLE_IMAGE).sum())


def test_driver_io_outside_tasks_is_recorded_with_its_time(
    tmp_path: Path,
) -> None:
    """Writes and reads in the driver are timestamped events, not tasks."""
    RecordingExecutor(SerialExecutor())
    drain_driver_zarr_io()
    before = time.time()

    _read_plane(_published_sink(tmp_path / "store"))
    after = time.time()
    events = drain_driver_zarr_io()

    assert all(before <= instant <= after for instant, _ in events)
    total = sum((io for _, io in events), ZarrIO())
    # Four chunks of 35 float64 pixels in all are written, read back once
    # when publication validates them, and read again by the window.
    assert total == ZarrIO(
        read_chunks=8, read_bytes=2 * 35 * 8, written_chunks=4
    )
    assert drain_driver_zarr_io() == ()


@pytest.mark.parametrize("threads", [None, 2], ids=["serial", "threads"])
def test_each_task_counts_only_the_chunks_it_moved(
    tmp_path: Path, threads: int | None
) -> None:
    """Concurrent tasks keep separate counts, and none reaches the driver."""
    sink = _published_sink(tmp_path / "store")
    drain_driver_zarr_io()
    inner = SerialExecutor() if threads is None else ThreadExecutor(threads)
    executor = RecordingExecutor(inner)

    results = executor.map_batches(_read_plane, [sink, sink, sink])
    if isinstance(inner, ThreadExecutor):
        inner.close()

    assert results == [_read_plane(sink)] * 3
    assert [task.io for task in executor.tasks] == [
        ZarrIO(read_chunks=4, read_bytes=35 * 8)
    ] * 3
    # The comparison read above is the driver's own.
    assert sum((io for _, io in drain_driver_zarr_io()), ZarrIO()) == ZarrIO(
        read_chunks=4, read_bytes=35 * 8
    )
