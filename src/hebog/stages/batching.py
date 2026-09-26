"""The one rule every per-object round batches its reads under.

Each round of ADR-008's object pass reads one window per object, and groups
neighbouring objects so that one read serves several: storage chunks are far
larger than most objects, and a read per object would decode the chunks its
neighbours share again for each of them.

A batch closes before its read would exceed ``maximum_batch_read_pixels``.
An object whose own window already exceeds that budget is never batched with
another. It reaches this module only when a reviewed admission rule bounds
its window independently of the image, and is then read alone; anything else
is refused, because nothing would bound its read. A round measures such an
object from the cores that hold it instead, or does not read it at all.
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
from hebog.executors.base import Executor


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


def batch_object_windows[T](
    objects: Sequence[T],
    *,
    window: Callable[[T], ImageBounds],
    maximum_batch_read_pixels: int,
    maximum_objects_per_batch: int | None = None,
    bounded_by_admission: Callable[[T], bool] | None = None,
) -> tuple[WindowBatch[T], ...]:
    """Group objects, in the order given, so one read serves several.

    Objects keep the caller's order, so a round that numbers its results in
    batch order still numbers them canonically. ``bounded_by_admission``
    names the objects whose own window a reviewed admission rule limits;
    such an object may be wider than the budget and is then read alone.

    Raises:
        ValueError: If an object's own window exceeds the budget and no
            admission rule bounds it.
    """
    batches: list[WindowBatch[T]] = []
    grouped: list[T] = []
    read: ImageBounds | None = None
    for item in objects:
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
) -> tuple[Result, ...]:
    """Evaluate one round of object work, which may have none to do.

    A round with no batch submits nothing, so an image without such objects
    costs no task.

    Raises:
        ValueError: If the executor returns nothing for work it was given,
            which would publish an incomplete result as a complete one.
    """
    if not batches:
        return ()
    results = tuple(executor.map_batches(function, batches))
    if len(results) != len(batches):
        if not results:
            raise ValueError(f"executor returned no {round_name} results")
        raise ValueError(
            f"executor returned {len(results)} {round_name} results for "
            f"{len(batches)} batches"
        )
    return results
