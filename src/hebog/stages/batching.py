"""The one rule every per-object round batches its reads under.

Each round of ADR-008's object pass reads one window per object, and groups
neighbouring objects so that one read serves several: storage chunks are far
larger than most objects, and a read per object would decode the chunks its
neighbours share again for each of them. Objects are taken a storage core at
a time, in raster order within each core, so a batch's read covers a compact
region rather than a strip across the image's chunks.

A batch closes before its read would exceed ``maximum_batch_read_pixels``.
An object whose own window already exceeds that budget is never batched with
another. It reaches this module only when a reviewed admission rule bounds
its window independently of the image, and is then read alone; anything else
is refused, because nothing would bound its read. A round measures such an
object from the cores that hold it instead, or does not read it at all.

Rounds over whole tiles batch by count instead (``tiles_per_batch``), as
coarsely as their executor's task slots allow, and an object round's batches
also close at the share of its objects those slots need
(``objects_per_batch``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from hebog.algorithms.reconciliation import TileLabelMapping
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.executors.base import (
    Executor,
    ExecutorCapacity,
    TaskRequirement,
)

# A round holds at least this many batches for each task slot when its work
# allows, so the slots share the round's last batches instead of one slot
# working through a long last batch while the others wait.
_BATCHES_PER_SLOT = 2


def tiles_per_batch(
    tile_count: int, capacity: ExecutorCapacity, *, maximum: int
) -> int:
    """Return how many tiles each batch of one tile round holds.

    Up to ``maximum`` tiles share a task, which spreads the reads a task
    makes before its first tile. A round of a few large tiles batched that
    coarsely leaves most task slots idle: the nine tiles of a 5,000-pixel
    image make tasks of four, four and one tile, so four slots finish the
    round no sooner than one slot working through four tiles. A batch
    therefore shrinks, down to one tile, until the round holds two batches
    for each of the executor's slots, its workers times their threads. One
    slot runs every batch in turn, so the serial reference keeps the coarse
    batches. Products do not depend on the batching.

    >>> serial = ExecutorCapacity(1, 1, 1)
    >>> four_threads = ExecutorCapacity(1, 4, 4)
    >>> tiles_per_batch(9, serial, maximum=4)
    4
    >>> tiles_per_batch(9, four_threads, maximum=4)
    1
    """
    slots = capacity.worker_count * capacity.threads_per_worker
    if slots == 1:
        return maximum
    return max(1, min(maximum, tile_count // (_BATCHES_PER_SLOT * slots)))


def objects_per_batch(
    object_count: int, capacity: ExecutorCapacity
) -> int | None:
    """Return the most objects one batch of an object round may hold.

    An object round's batches close at a read budget, so a small image's
    objects share a few reads and a few tasks: the component fits of a
    3,000-pixel LoTSS-DR3 sector make four batches, so four slots finish
    the round only with its slowest. With several slots a batch therefore
    also closes at a share of the round's objects, so the round holds at
    least two batches for each slot when it has the objects. One slot runs
    every batch in turn, so the serial reference closes batches at the read
    budget alone (``None``). Products do not depend on the batching.

    >>> objects_per_batch(100, ExecutorCapacity(1, 1, 1)) is None
    True
    >>> objects_per_batch(100, ExecutorCapacity(1, 4, 4))
    12
    >>> objects_per_batch(3, ExecutorCapacity(1, 4, 4))
    1
    """
    slots = capacity.worker_count * capacity.threads_per_worker
    if slots == 1:
        return None
    return max(1, object_count // (_BATCHES_PER_SLOT * slots))


@dataclass(frozen=True, slots=True)
class WindowBatch[T]:
    """Objects that share one read, and the read that serves them all."""

    objects: tuple[T, ...]
    read_bounds: ImageBounds


@dataclass(frozen=True, slots=True)
class HeldObjects:
    """One core and the local labels of the wide objects it holds.

    The mapping is cut down to those objects' labels, so a core carries a
    few integers rather than its whole reconciliation.
    """

    partition: TilePartition
    mapping: TileLabelMapping


def cores_holding(
    global_labels: frozenset[int],
    manifest: PartitionManifest,
    mappings: tuple[TileLabelMapping, ...],
) -> tuple[HeldObjects, ...]:
    """Name each core holding part of a reconciled object, and which part.

    The reconciliation that numbered the objects already knows which local
    label of which core each one joined, so no core is scanned to find them.
    """
    partitions = {partition.tile_id: partition for partition in manifest.tiles}
    cores: list[HeldObjects] = []
    for mapping in mappings:
        pairs = tuple(
            (local_label, global_label)
            for local_label, global_label in zip(
                mapping.local_labels, mapping.global_labels, strict=True
            )
            if global_label in global_labels
        )
        if pairs:
            cores.append(
                HeldObjects(
                    partition=partitions[mapping.tile_id],
                    mapping=TileLabelMapping(
                        tile_id=mapping.tile_id,
                        local_labels=tuple(local for local, _ in pairs),
                        global_labels=tuple(label for _, label in pairs),
                    ),
                )
            )
    return tuple(cores)


def read_pixels(bounds: ImageBounds) -> int:
    """Return how many pixels one read over these bounds holds.

    Examples:
        >>> read_pixels(ImageBounds(0, 3, 2, 6))
        12
    """
    height, width = bounds.shape_yx
    return height * width


def union_bounds(first: ImageBounds, second: ImageBounds) -> ImageBounds:
    """Return the smallest bounds holding both.

    Examples:
        >>> union_bounds(ImageBounds(0, 2, 0, 2), ImageBounds(4, 5, 1, 3))
        ImageBounds(y_start=0, y_stop=5, x_start=0, x_stop=3)
    """
    return ImageBounds(
        min(first.y_start, second.y_start),
        max(first.y_stop, second.y_stop),
        min(first.x_start, second.x_start),
        max(first.x_stop, second.x_stop),
    )


def batch_object_windows[T](  # noqa: PLR0913
    objects: Sequence[T],
    *,
    window: Callable[[T], ImageBounds],
    core_shape_yx: tuple[int, int],
    maximum_batch_read_pixels: int,
    maximum_objects_per_batch: int | None = None,
    bounded_by_admission: Callable[[T], bool] | None = None,
) -> tuple[WindowBatch[T], ...]:
    """Group objects a core at a time so one read serves several.

    Objects are ordered by the storage core, of ``core_shape_yx`` pixels,
    that their window starts in, then in raster order of that start; objects
    starting at one pixel keep the caller's order. Ordered by raster alone,
    a batch would be a strip across every core in its rows and decode each
    of their chunks. A round therefore keys its results by object, not by
    batch order.
    ``bounded_by_admission`` names the objects whose own window a reviewed
    admission rule limits; such an object may be wider than the budget and
    is then read alone.

    Raises:
        ValueError: If an object's own window exceeds the budget and no
            admission rule bounds it.
    """
    core_height, core_width = core_shape_yx

    def core_raster_order(item: T) -> tuple[int, int, int, int]:
        start = window(item)
        return (
            start.y_start // core_height,
            start.x_start // core_width,
            start.y_start,
            start.x_start,
        )

    batches: list[WindowBatch[T]] = []
    grouped: list[T] = []
    read: ImageBounds | None = None
    for item in sorted(objects, key=core_raster_order):
        own = window(item)
        if read_pixels(own) > maximum_batch_read_pixels:
            if bounded_by_admission is None or not bounded_by_admission(item):
                raise ValueError(
                    "an object wider than the read budget needs an admission "
                    "bound or its cores"
                )
            if read is not None:
                batches.append(WindowBatch(tuple(grouped), read))
            batches.append(WindowBatch((item,), own))
            grouped, read = [], None
            continue
        merged = own if read is None else union_bounds(read, own)
        if read is not None and (
            len(grouped) == maximum_objects_per_batch
            or read_pixels(merged) > maximum_batch_read_pixels
        ):
            batches.append(WindowBatch(tuple(grouped), read))
            grouped, merged = [], own
        grouped.append(item)
        read = merged
    if read is not None:
        batches.append(WindowBatch(tuple(grouped), read))
    return tuple(batches)


def map_round[Batch, Result](
    executor: Executor,
    function: Callable[[Batch], Result],
    batches: tuple[Batch, ...],
    *,
    round_name: str,
    requirement: TaskRequirement,
) -> tuple[Result, ...]:
    """Evaluate one round of object work, which may have none to do.

    A round with no batch submits nothing, so an image without such objects
    costs no task. Every task declares ``requirement``, the memory the
    round's largest read needs (``hebog.stages.task_memory``).

    Raises:
        ValueError: If the executor returns nothing for work it was given,
            which would publish an incomplete result as a complete one.
    """
    if not batches:
        return ()
    results = tuple(
        executor.map_batches(function, batches, requirement=requirement)
    )
    if len(results) != len(batches):
        if not results:
            raise ValueError(f"executor returned no {round_name} results")
        raise ValueError(
            f"executor returned {len(results)} {round_name} results for "
            f"{len(batches)} batches"
        )
    return results
