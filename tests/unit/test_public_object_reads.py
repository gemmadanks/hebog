# pyright: reportPrivateUsage=false
"""Batched bounded reads behind the driver's remaining object round."""

from __future__ import annotations

from hebog import public_api


def _crop(
    y_start: int, y_stop: int, x_start: int, x_stop: int
) -> tuple[slice, slice]:
    """Return one object's window as the label scan reports it."""
    return (slice(y_start, y_stop), slice(x_start, x_stop))


def test_no_object_asks_the_store_for_nothing() -> None:
    """Labels that own no pixel read no window at all."""
    batches = public_api._component_read_batches(
        (None, None), maximum_batch_read_pixels=1024
    )

    assert list(batches) == []


def test_neighbours_within_the_budget_share_one_read() -> None:
    """One read serves several objects, which is why the budget exists.

    The store assembles a window from chunks far larger than one object, so
    neighbours sharing those chunks must not decode them once each.
    """
    windows = (_crop(0, 4, 0, 4), _crop(2, 6, 2, 6))

    batches = list(
        public_api._component_read_batches(
            windows, maximum_batch_read_pixels=1024
        )
    )

    assert len(batches) == 1
    assert batches[0].covering == _crop(0, 6, 0, 6)
    assert [component.label_value for component in batches[0].components] == [
        1,
        2,
    ]


def test_the_budget_splits_a_read_that_would_grow_past_it() -> None:
    """A batch stops before the covering read exceeds the caller's budget."""
    windows = (_crop(0, 4, 0, 4), _crop(20, 24, 20, 24))

    batches = list(
        public_api._component_read_batches(
            windows, maximum_batch_read_pixels=64
        )
    )

    assert [batch.covering for batch in batches] == [
        _crop(0, 4, 0, 4),
        _crop(20, 24, 20, 24),
    ]
    assert [
        component.label_value
        for batch in batches
        for component in batch.components
    ] == [1, 2]


def test_objects_are_visited_in_raster_order_of_their_windows() -> None:
    """Batches follow the image, so a batch covers a compact region."""
    windows = (_crop(8, 12, 0, 4), _crop(0, 4, 8, 12), _crop(0, 4, 0, 4))

    batches = list(
        public_api._component_read_batches(
            windows, maximum_batch_read_pixels=64
        )
    )

    assert [
        component.label_value
        for batch in batches
        for component in batch.components
    ] == [3, 2, 1]
