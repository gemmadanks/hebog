# pyright: reportPrivateUsage=false
"""The seeds a core needs to assign its share of a wide support component."""

from __future__ import annotations

import numpy as np
from hypothesis import given
from hypothesis import strategies as st

from hebog.algorithms.extended_measurement import nearest_source_seed_labels
from hebog.data_models.partitioning import ImageBounds
from hebog.stages.sources import _seeds_near_core

_WIDTH = 48


@given(
    st.lists(
        st.tuples(
            st.integers(0, _WIDTH - 1),
            st.integers(0, _WIDTH - 1),
            st.integers(1, 4),
        ),
        min_size=1,
        max_size=40,
        unique_by=lambda seed: (seed[0], seed[1]),
    ),
    st.integers(0, _WIDTH - 8),
    st.integers(0, _WIDTH - 8),
    st.integers(1, 8),
    st.integers(1, 8),
)
def test_a_core_keeps_every_seed_that_can_own_one_of_its_pixels(
    seeds: list[tuple[int, int, int]],
    y_start: int,
    x_start: int,
    height: int,
    width: int,
) -> None:
    """Every core pixel gets the owner the component's full seed set gives.

    Ties included: an exact tie goes to the smaller label, so a selection
    that dropped one tied seed could change the owner.
    """
    core = ImageBounds(y_start, y_start + height, x_start, x_start + width)
    indices = np.asarray([y * _WIDTH + x for y, x, _ in seeds], dtype=np.int64)
    labels = np.asarray([label for _, _, label in seeds], dtype=np.int64)
    points = np.column_stack(np.divmod(indices, _WIDTH))
    rows, columns = np.mgrid[
        core.y_start : core.y_stop, core.x_start : core.x_stop
    ]
    pixels = np.column_stack((rows.ravel(), columns.ravel())).astype(np.int64)

    kept = _seeds_near_core(indices, core, image_width=_WIDTH)

    np.testing.assert_array_equal(
        nearest_source_seed_labels(points[kept], labels[kept], pixels),
        nearest_source_seed_labels(points, labels, pixels),
    )


def test_a_seed_too_far_to_own_any_core_pixel_is_not_sent() -> None:
    """A seed beyond every pixel's nearest one stays on the driver."""
    core = ImageBounds(0, 4, 0, 4)
    near, far = 1 * 100 + 1, 50 * 100 + 50

    kept = _seeds_near_core(
        np.asarray([near, far], dtype=np.int64), core, image_width=100
    )

    np.testing.assert_array_equal(kept, [True, False])
