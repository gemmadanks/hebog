"""The rules object rounds and tile rounds batch their work under."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from math import ceil
from typing import TypeVar

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hebog.data_models.partitioning import ImageBounds
from hebog.executors import ExecutorCapacity, SerialExecutor, TaskRequirement
from hebog.stages.batching import (
    LARGEST_TILE_CORE_PIXELS,
    batch_object_windows,
    map_round,
    objects_per_batch,
    read_pixels,
    tile_core_from_budget,
    tiles_per_batch,
)

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_REQUIREMENT = TaskRequirement(memory_bytes=1)
_CORE = (16, 16)
"""A storage core wider than every window the tests below place."""


def _square(y: int, x: int, side: int) -> ImageBounds:
    """Return one ``side``-pixel square window at ``(y, x)``."""
    return ImageBounds(y, y + side, x, x + side)


def _identity(bounds: ImageBounds) -> ImageBounds:
    """Treat each object as its own window."""
    return bounds


def test_one_read_serves_neighbours_in_raster_order() -> None:
    """Neighbours share a read until it would pass the budget."""
    windows = (
        _square(0, 0, 2),
        _square(0, 2, 2),
        _square(0, 8, 2),
        _square(8, 8, 2),
    )

    batches = batch_object_windows(
        windows,
        window=_identity,
        core_shape_yx=_CORE,
        maximum_batch_read_pixels=16,
    )

    assert [batch.objects for batch in batches] == [
        windows[:2],
        windows[2:3],
        windows[3:],
    ]
    assert [batch.read_bounds for batch in batches] == [
        ImageBounds(0, 2, 0, 4),
        windows[2],
        windows[3],
    ]


def test_a_batch_holds_no_more_objects_than_admitted() -> None:
    """The object limit closes a batch even when the read still fits."""
    windows = tuple(_square(0, index, 1) for index in range(5))

    batches = batch_object_windows(
        windows,
        window=_identity,
        core_shape_yx=_CORE,
        maximum_batch_read_pixels=100,
        maximum_objects_per_batch=2,
    )

    assert [len(batch.objects) for batch in batches] == [2, 2, 1]


def test_no_object_means_no_batch() -> None:
    """An image with no object submits no work."""
    assert (
        batch_object_windows(
            (),
            window=_identity,
            core_shape_yx=_CORE,
            maximum_batch_read_pixels=1,
        )
        == ()
    )


def test_an_object_wider_than_the_budget_is_refused_without_admission() -> (
    None
):
    """Nothing bounds such a read, so it is never silently batched.

    The first object of a batch used to be exempt from the budget, which let
    one filament make a task read an image-sized window.
    """
    with pytest.raises(ValueError, match="wider than the read budget"):
        batch_object_windows(
            (_square(0, 0, 1), _square(0, 4, 3)),
            window=_identity,
            core_shape_yx=_CORE,
            maximum_batch_read_pixels=8,
        )


def test_an_admitted_object_wider_than_the_budget_is_read_alone() -> None:
    """A window the admission bounds may pass the budget, but is read alone."""
    wide = _square(0, 4, 3)
    windows = (_square(0, 0, 1), _square(0, 1, 1), wide, _square(0, 8, 1))

    batches = batch_object_windows(
        windows,
        window=_identity,
        core_shape_yx=_CORE,
        maximum_batch_read_pixels=8,
        bounded_by_admission=lambda bounds: bounds == wide,
    )

    assert [batch.objects for batch in batches] == [
        windows[:2],
        (wide,),
        windows[3:],
    ]
    assert batches[1].read_bounds == wide


def test_objects_are_batched_a_core_at_a_time() -> None:
    """A batch's read stays in one core rather than a strip across cores.

    In raster order, two rows of objects across two cores side by side
    would be batched row by row, so each read would decode both cores'
    storage chunks, and a round at 15,402² decoded 656 chunks of a
    64-chunk plane.
    """
    windows = tuple(_square(y, x, 2) for y in (0, 4) for x in (0, 4, 8, 12))

    batches = batch_object_windows(
        windows,
        window=_identity,
        core_shape_yx=(8, 8),
        maximum_batch_read_pixels=48,
    )

    assert [batch.read_bounds for batch in batches] == [
        ImageBounds(0, 6, 0, 6),
        ImageBounds(0, 6, 8, 14),
    ]


def test_objects_starting_at_the_same_pixel_keep_the_given_order() -> None:
    """Order is decided by where windows start, and ties are left alone."""
    first = ImageBounds(0, 2, 0, 1)
    second = ImageBounds(0, 1, 0, 2)

    batches = batch_object_windows(
        (first, second),
        window=_identity,
        core_shape_yx=_CORE,
        maximum_batch_read_pixels=1,
        bounded_by_admission=lambda _: True,
    )

    assert [batch.objects for batch in batches] == [(first,), (second,)]


def test_the_admission_must_name_every_wide_object() -> None:
    """An admission rule that does not bound this object bounds nothing."""
    with pytest.raises(ValueError, match="wider than the read budget"):
        batch_object_windows(
            (_square(0, 0, 3),),
            window=_identity,
            core_shape_yx=_CORE,
            maximum_batch_read_pixels=8,
            bounded_by_admission=lambda _: False,
        )


@given(
    st.lists(
        st.tuples(st.integers(0, 40), st.integers(0, 40), st.integers(1, 6)),
        max_size=30,
    ),
    st.integers(1, 64),
    st.integers(1, 5),
)
def test_every_object_is_batched_once_and_no_shared_read_passes_the_budget(
    squares: list[tuple[int, int, int]],
    budget: int,
    maximum_objects_per_batch: int,
) -> None:
    """Batching changes which task reads an object, never whether it is read.

    Wide objects are admitted here, so the property covers both the shared
    reads, which stay within the budget, and the reads taken alone.
    """
    windows = tuple(_square(y, x, side) for y, x, side in squares)

    batches = batch_object_windows(
        windows,
        window=_identity,
        core_shape_yx=_CORE,
        maximum_batch_read_pixels=budget,
        maximum_objects_per_batch=maximum_objects_per_batch,
        bounded_by_admission=lambda _: True,
    )

    assert tuple(item for batch in batches for item in batch.objects) == (
        tuple(
            sorted(
                windows,
                key=lambda window: (
                    window.y_start // _CORE[0],
                    window.x_start // _CORE[1],
                    window.y_start,
                    window.x_start,
                ),
            )
        )
    )
    for batch in batches:
        assert 0 < len(batch.objects) <= maximum_objects_per_batch
        assert all(
            batch.read_bounds.contains(window) for window in batch.objects
        )
        if len(batch.objects) > 1:
            assert read_pixels(batch.read_bounds) <= budget


class _SilentExecutor(SerialExecutor):
    """Return nothing, as a lost round would."""

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Drop every result."""
        del function, batches, requirement
        return []


class _ShortExecutor(SerialExecutor):
    """Return the first result only, as a partly lost round would."""

    def __init__(self) -> None:
        """Start with no requirement seen."""
        super().__init__()
        self.requirements: list[TaskRequirement | None] = []

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Run the batches but keep only the first result."""
        self.requirements.append(requirement)
        return super().map_batches(function, batches)[:1]


def test_a_round_declares_its_requirement_to_the_executor() -> None:
    """Every task of a round asks for the memory the round declared."""
    executor = _ShortExecutor()

    map_round(executor, str, (1,), round_name="one", requirement=_REQUIREMENT)

    assert executor.requirements == [_REQUIREMENT]


def test_a_partly_lost_round_fails_closed() -> None:
    """Fewer results than batches would publish an incomplete result."""
    with pytest.raises(ValueError, match="1 short results for 2 batches"):
        map_round(
            _ShortExecutor(),
            str,
            (1, 2),
            round_name="short",
            requirement=_REQUIREMENT,
        )


def test_a_round_with_no_work_submits_nothing() -> None:
    """An image with no such object costs no task."""
    assert (
        map_round(
            _SilentExecutor(),
            str,
            (),
            round_name="empty",
            requirement=_REQUIREMENT,
        )
        == ()
    )


def test_a_round_returns_one_result_per_batch() -> None:
    """The executor's results come back in batch order."""
    assert map_round(
        SerialExecutor(),
        str,
        (1, 2),
        round_name="numbers",
        requirement=_REQUIREMENT,
    ) == ("1", "2")


def test_a_silent_round_fails_closed() -> None:
    """Nothing back for work given would publish an incomplete result."""
    with pytest.raises(ValueError, match="executor returned no lost results"):
        map_round(
            _SilentExecutor(),
            str,
            (1,),
            round_name="lost",
            requirement=_REQUIREMENT,
        )


def _slots(workers: int, threads: int) -> ExecutorCapacity:
    """Return a budget of ``workers`` workers of ``threads`` threads."""
    return ExecutorCapacity(workers, threads, workers * threads)


@pytest.mark.parametrize(
    ("tile_count", "workers", "threads", "expected"),
    [
        pytest.param(9, 1, 1, 4, id="serial"),
        pytest.param(3, 1, 1, 4, id="serial-few-tiles"),
        pytest.param(9, 1, 4, 1, id="5000-on-four-threads"),
        pytest.param(9, 2, 1, 2, id="5000-on-two-workers"),
        pytest.param(25, 6, 1, 2, id="10000-on-six-workers"),
        pytest.param(121, 1, 4, 4, id="22500-on-four-threads"),
        pytest.param(1, 6, 1, 1, id="one-tile"),
    ],
)
def test_tile_rounds_batch_as_coarsely_as_their_slots_allow(
    tile_count: int, workers: int, threads: int, expected: int
) -> None:
    """Four tiles a task until the round would leave task slots idle."""
    assert (
        tiles_per_batch(tile_count, _slots(workers, threads), maximum=4)
        == expected
    )


@given(
    tile_count=st.integers(1, 400),
    workers=st.integers(1, 16),
    threads=st.integers(1, 8),
    maximum=st.integers(1, 8),
)
def test_a_tile_batch_shrinks_until_every_slot_has_two(
    tile_count: int, workers: int, threads: int, maximum: int
) -> None:
    """A batch above one tile leaves each slot two; more never coarsen it."""
    size = tiles_per_batch(
        tile_count, _slots(workers, threads), maximum=maximum
    )
    wider = tiles_per_batch(
        tile_count, _slots(workers + 1, threads), maximum=maximum
    )

    assert 1 <= wider <= size <= maximum
    if workers * threads > 1 and size > 1:
        assert ceil(tile_count / size) >= 2 * workers * threads


@pytest.mark.parametrize(
    ("object_count", "workers", "threads", "expected"),
    [
        pytest.param(25_000, 1, 1, None, id="serial"),
        pytest.param(25_000, 4, 1, 3_125, id="dense-5000-on-four-workers"),
        pytest.param(100, 1, 4, 12, id="four-threads"),
        pytest.param(3, 6, 1, 1, id="fewer-objects-than-slots"),
        pytest.param(0, 4, 1, 1, id="no-objects"),
    ],
)
def test_object_rounds_close_batches_at_a_share_of_their_slots(
    object_count: int, workers: int, threads: int, expected: int | None
) -> None:
    """Serially the read budget alone closes a batch; wider, a share too."""
    assert objects_per_batch(object_count, _slots(workers, threads)) == (
        expected
    )


@given(
    object_count=st.integers(1, 5_000),
    workers=st.integers(1, 16),
    threads=st.integers(1, 8),
)
def test_an_object_share_leaves_every_slot_two_batches(
    object_count: int, workers: int, threads: int
) -> None:
    """Each slot gets two batches when the objects allow; more never coarsen.

    The read budget can only close a batch sooner, so these counts are the
    fewest batches the round holds.
    """
    slots = workers * threads
    share = objects_per_batch(object_count, _slots(workers, threads))
    wider = objects_per_batch(object_count, _slots(workers + 1, threads))

    if slots == 1:
        assert share is None
        return
    assert share is not None
    assert wider is not None
    assert 1 <= wider <= share
    assert ceil(object_count / share) >= min(object_count, 2 * slots)


# A 4-pixel beam's widest multiscale filter halo, the passes' widest.
_HALO = 28


@pytest.mark.parametrize(
    ("shape_yx", "workers", "threads", "halo", "expected"),
    [
        pytest.param((5000, 5000), 1, 1, _HALO, 2048, id="5000-serially"),
        pytest.param((5000, 5000), 2, 1, _HALO, 2048, id="5000-on-two"),
        pytest.param((5000, 5000), 4, 1, _HALO, 1024, id="5000-on-four"),
        pytest.param((5000, 5000), 6, 1, _HALO, 1024, id="5000-on-six"),
        pytest.param((5000, 5000), 1, 6, _HALO, 1024, id="5000-six-threads"),
        pytest.param((3000, 3000), 3, 1, _HALO, 1024, id="3000-on-three"),
        pytest.param((10000, 10000), 11, 1, _HALO, 2048, id="10000-on-11"),
        pytest.param((10000, 10000), 12, 1, _HALO, 1024, id="10000-on-12"),
        pytest.param((10000, 10000), 48, 1, _HALO, 1024, id="10000-on-48"),
        pytest.param((1024, 1024), 6, 1, _HALO, 2048, id="small-one-tile"),
        pytest.param((2048, 2048), 1, 1, _HALO, 2048, id="2048-serially"),
        pytest.param((2048, 2048), 4, 1, _HALO, 1024, id="2048-on-four"),
        pytest.param((5000, 5000), 6, 1, 103, 2048, id="wide-halo"),
        pytest.param((5000, 5000), 6, 1, 102, 1024, id="widest-halo-admitted"),
        pytest.param((15402, 15402), 192, 1, _HALO, 2048, id="15402-on-192"),
        pytest.param((11264, 11264), 192, 1, _HALO, 1024, id="eleven-a-side"),
        pytest.param((11265, 3000), 192, 1, _HALO, 2048, id="twelve-a-side"),
    ],
)
def test_the_tile_core_halves_while_its_largest_tile_sets_the_round(
    shape_yx: tuple[int, int],
    workers: int,
    threads: int,
    halo: int,
    expected: int,
) -> None:
    """A wider budget gets more, smaller tiles, within the stated bounds.

    The core halves only while its largest tile holds more than half of
    one slot's share of the image, and only to a core that adds tiles, is
    at least 1,024 pixels and ten halos wide, and keeps the grid within
    eleven tiles a side.
    """
    assert (
        tile_core_from_budget(
            shape_yx, halo_pixels=halo, capacity=_slots(workers, threads)
        )
        == expected
    )


@given(
    height=st.integers(1, 30_000),
    width=st.integers(1, 30_000),
    workers=st.integers(1, 256),
    halo=st.integers(0, 600),
)
def test_a_wider_budget_never_gets_a_coarser_core(
    height: int, width: int, workers: int, halo: int
) -> None:
    """More slots never widen the core, and every core keeps its bounds."""
    shape = (height, width)
    core = tile_core_from_budget(
        shape, halo_pixels=halo, capacity=_slots(workers, 1)
    )
    wider = tile_core_from_budget(
        shape, halo_pixels=halo, capacity=_slots(workers + 1, 1)
    )

    assert wider <= core <= LARGEST_TILE_CORE_PIXELS
    if core < LARGEST_TILE_CORE_PIXELS:
        assert core >= max(1024, 10 * halo)
        assert max(ceil(side / core) for side in shape) <= 11
        larger = min(2 * core, height) * min(2 * core, width)
        assert 2 * workers * larger > height * width


@pytest.mark.parametrize(
    ("in_flight", "tiles", "objects", "core"),
    [
        pytest.param(1, 4, None, 2048, id="one-in-flight"),
        pytest.param(2, 2, 25, 2048, id="two-in-flight"),
        pytest.param(8, 1, 6, 1024, id="every-thread-in-flight"),
    ],
)
def test_the_tasks_in_flight_bound_the_slots_a_round_is_sized_for(
    in_flight: int, tiles: int, objects: int | None, core: int
) -> None:
    """Admitting fewer tasks at once than threads gets coarser rounds.

    Four workers of two threads that admit only ``in_flight`` tasks at once
    run no more tasks together than that, so their rounds are sized as for
    that many slots.
    """
    capacity = ExecutorCapacity(4, 2, in_flight)

    assert tiles_per_batch(9, capacity, maximum=4) == tiles
    assert objects_per_batch(100, capacity) == objects
    assert (
        tile_core_from_budget(
            (5000, 5000), halo_pixels=_HALO, capacity=capacity
        )
        == core
    )
