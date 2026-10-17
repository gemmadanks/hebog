"""The memory each round's tasks declare to the executor.

A task holds what it reads and what it derives from each pixel it reads: a
tile task its core, halo and filter planes, an object batch its read
window. Each round therefore states its own cost per read pixel and
declares that cost for the largest window one of its tasks reads.
Intermediate Zarr stores decode whole chunks of their stage's tile-core
grid, so a read of them never costs less than one chunk, however small the
window or the image; a window of the FITS input is read alone. A
declaration is therefore bounded by tile, halo, batch and chunk, never by
the image.

The costs are measured, not derived: the largest ``tracemalloc`` peak of
one task above what the run held when it began, over the round's largest
read, the most over the reference anchors. Tracing misses
allocations outside Python's allocator, and an anchor need not hold a
round's worst content, so a declaration adds a fixed allowance for the
objects every task allocates and then a quarter of headroom. A change to
what a round holds per pixel re-measures its cost with
``scripts/benchmark/audit_task_memory.py``.

The executor refuses a declaration larger than a worker admits, narrows
its in-flight window by it, and attaches it to every Dask task under the
caller's memory resource, so Dask co-locates tasks only within the memory
a worker declares.
"""

from __future__ import annotations

from collections.abc import Iterable

from hebog.data_models.partitioning import ImageBounds
from hebog.executors.base import TaskRequirement
from hebog.stages.batching import read_pixels

TASK_ALLOWANCE_BYTES = 16 * 1024 * 1024
"""What every task allocates beyond its pixels: records, indices, codecs."""

_HEADROOM_NUMERATOR, _HEADROOM_DENOMINATOR = 5, 4


def read_requirement(
    bytes_per_read_pixel: int,
    reads: Iterable[ImageBounds],
    *,
    chunk_shape_yx: tuple[int, int] = (1, 1),
) -> TaskRequirement:
    """Return what each task of a round declares, from its largest read.

    ``bytes_per_read_pixel`` is the round's measured cost, ``reads`` every
    window its tasks read, and ``chunk_shape_yx`` the chunk grid of the
    stores it reads, the least a read of them decodes; the default of one
    pixel is for a round that reads only the FITS input. A round with no
    read declares only the allowance.

    Examples:
        >>> read_requirement(100, [ImageBounds(0, 10, 0, 10)]).memory_bytes
        20984020
        >>> read_requirement(
        ...     1, [ImageBounds(0, 10, 0, 10)], chunk_shape_yx=(64, 64)
        ... ).memory_bytes
        20976640
        >>> read_requirement(100, []).memory_bytes
        20971520
    """
    chunk_height, chunk_width = chunk_shape_yx
    largest = max(
        (
            max(read_pixels(bounds), chunk_height * chunk_width)
            for bounds in reads
        ),
        default=0,
    )
    traced = TASK_ALLOWANCE_BYTES + bytes_per_read_pixel * largest
    return TaskRequirement(
        memory_bytes=-(-traced * _HEADROOM_NUMERATOR // _HEADROOM_DENOMINATOR)
    )
