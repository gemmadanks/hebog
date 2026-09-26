"""The one rule every per-object round batches its reads under."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hebog.data_models.partitioning import ImageBounds
from hebog.stages.batching import batch_object_windows, read_pixels


def _square(y: int, x: int, side: int) -> ImageBounds:
    """Return one ``side``-pixel square window at ``(y, x)``."""
    return ImageBounds(y, y + side, x, x + side)


def _identity(bounds: ImageBounds) -> ImageBounds:
    """Treat each object as its own window."""
    return bounds


def test_one_read_serves_neighbours_in_the_given_order() -> None:
    """Neighbours share a read until it would pass the budget."""
    windows = (
        _square(0, 0, 2),
        _square(0, 2, 2),
        _square(0, 8, 2),
        _square(8, 8, 2),
    )

    batches = batch_object_windows(
        windows, window=_identity, maximum_batch_read_pixels=16
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
        maximum_batch_read_pixels=100,
        maximum_objects_per_batch=2,
    )

    assert [len(batch.objects) for batch in batches] == [2, 2, 1]


def test_no_object_means_no_batch() -> None:
    """An image with no object submits no work."""
    assert (
        batch_object_windows((), window=_identity, maximum_batch_read_pixels=1)
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
            maximum_batch_read_pixels=8,
        )


def test_an_admitted_object_wider_than_the_budget_is_read_alone() -> None:
    """A window the admission bounds may pass the budget, but shares nothing.

    The order the caller gave is kept, so a round that numbers its results
    by batch order still numbers them canonically.
    """
    wide = _square(0, 4, 3)
    windows = (_square(0, 0, 1), _square(0, 1, 1), wide, _square(0, 8, 1))

    batches = batch_object_windows(
        windows,
        window=_identity,
        maximum_batch_read_pixels=8,
        bounded_by_admission=lambda bounds: bounds == wide,
    )

    assert [batch.objects for batch in batches] == [
        windows[:2],
        (wide,),
        windows[3:],
    ]
    assert batches[1].read_bounds == wide


def test_the_admission_must_name_every_wide_object() -> None:
    """An admission rule that does not bound this object bounds nothing."""
    with pytest.raises(ValueError, match="wider than the read budget"):
        batch_object_windows(
            (_square(0, 0, 3),),
            window=_identity,
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
        maximum_batch_read_pixels=budget,
        maximum_objects_per_batch=maximum_objects_per_batch,
        bounded_by_admission=lambda _: True,
    )

    assert tuple(item for batch in batches for item in batch.objects) == (
        windows
    )
    for batch in batches:
        assert 0 < len(batch.objects) <= maximum_objects_per_batch
        assert all(
            batch.read_bounds.contains(window) for window in batch.objects
        )
        if len(batch.objects) > 1:
            assert read_pixels(batch.read_bounds) <= budget
