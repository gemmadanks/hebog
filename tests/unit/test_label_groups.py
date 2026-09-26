"""Contracts of grouping labelled pixels in one pass.

Scanning the whole plane once per label costs image size times label count.
These groups give every label its own pixels in one pass, so per-label work
depends on that label's support instead.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.label_groups import (
    group_labelled_pixels,
    label_extents,
    label_windows,
)


def _labels(rows: str) -> npt.NDArray[np.int32]:
    """Build a label plane from digits, one row per line."""
    return np.array(
        [[int(value) for value in row.strip()] for row in rows.split()],
        dtype=np.int32,
    )


def test_groups_hold_each_label_in_row_major_order() -> None:
    labels = _labels("""
        0110
        0102
        3002
    """)
    groups = group_labelled_pixels(labels, label_count=3)
    assert list(groups.sizes) == [3, 2, 1]
    assert list(groups.first_y) == [0, 1, 2]
    assert list(groups.first_x) == [1, 3, 0]
    assert [
        (int(y), int(x)) for y, x in zip(groups.y, groups.x, strict=True)
    ] == [(0, 1), (0, 2), (1, 1), (1, 3), (2, 3), (2, 0)]


def test_group_extremes_match_a_per_label_scan() -> None:
    generator = np.random.default_rng(2026091901)
    labels = generator.integers(0, 6, size=(9, 11)).astype(np.int32)
    values = generator.uniform(-5.0, 5.0, labels.shape)
    groups = group_labelled_pixels(labels, label_count=5)
    flat_values = values.reshape(-1)[groups.flat_positions]
    for index, label_value in enumerate(range(1, 6)):
        selected = values[labels == label_value]
        assert groups.minimum(flat_values)[index] == pytest.approx(
            selected.min()
        )
        assert groups.maximum(flat_values)[index] == pytest.approx(
            selected.max()
        )
        assert (
            groups.minimum(groups.y)[index]
            == np.nonzero(labels == label_value)[0].min()
        )
        assert groups.sizes[index] == selected.size


def test_a_plane_without_labels_has_no_groups() -> None:
    groups = group_labelled_pixels(
        np.zeros((4, 5), dtype=np.int32), label_count=0
    )
    assert groups.sizes.size == 0
    assert groups.flat_positions.size == 0
    assert groups.minimum(np.array([], dtype=np.float64)).size == 0
    assert groups.maximum(np.array([], dtype=np.float64)).size == 0


def test_every_label_must_have_support() -> None:
    """Reductions assume non-empty groups, so a gap fails closed."""
    labels = _labels("""
        0100
        0003
    """)
    with pytest.raises(ValueError, match="every label to have support"):
        group_labelled_pixels(labels, label_count=3)


def test_labels_must_be_two_dimensional_and_non_negative() -> None:
    with pytest.raises(ValueError, match="two-dimensional"):
        group_labelled_pixels(np.zeros(4, dtype=np.int32), label_count=0)
    with pytest.raises(ValueError, match="non-negative"):
        group_labelled_pixels(
            np.array([[-1, 0]], dtype=np.int32), label_count=1
        )


def test_values_must_align_with_the_grouped_pixels() -> None:
    labels = _labels("""
        0110
        0000
    """)
    groups = group_labelled_pixels(labels, label_count=1)
    with pytest.raises(ValueError, match="aligned"):
        groups.maximum(np.array([1.0], dtype=np.float64))


def test_label_windows_bound_each_label() -> None:
    labels = _labels("""
        0110
        0100
        0002
    """)
    windows = label_windows(labels)
    assert windows[0] == (slice(0, 2), slice(1, 3))
    assert windows[1] == (slice(2, 3), slice(3, 4))


def test_a_label_without_pixels_has_no_window() -> None:
    labels = _labels("""
        0100
        0003
    """)
    windows = label_windows(labels)
    assert windows[1] is None
    assert len(windows) == 3


def test_a_label_above_the_declared_count_is_rejected() -> None:
    """Reductions run to the end of the array, so a stray label would fold
    into the last group's extrema instead of being ignored."""
    labels = _labels("""
        0110
        0002
    """)
    with pytest.raises(ValueError, match="above the declared label count"):
        group_labelled_pixels(labels, label_count=1)


def _scanned_extents(
    labels: npt.NDArray[np.int32],
) -> dict[int, tuple[int, int, int, int, tuple[int, int], int]]:
    """Describe each label by scanning the whole plane once per label.

    This is the readable oracle that ``label_extents`` replaces: it costs
    plane area times label count, and states the intended result directly.
    """
    oracle: dict[int, tuple[int, int, int, int, tuple[int, int], int]] = {}
    for value in np.unique(labels):
        if int(value) <= 0:
            continue
        rows, columns = np.nonzero(labels == value)
        oracle[int(value)] = (
            int(rows.min()),
            int(rows.max()) + 1,
            int(columns.min()),
            int(columns.max()) + 1,
            (int(rows[0]), int(columns[0])),
            int(rows.size),
        )
    return oracle


def _extent_mapping(
    labels: npt.NDArray[np.int32],
) -> dict[int, tuple[int, int, int, int, tuple[int, int], int]]:
    """Describe each label through the one-pass kernel, for comparison."""
    extents = label_extents(labels)
    return {
        int(value): (
            int(extents.y_start[index]),
            int(extents.y_stop[index]),
            int(extents.x_start[index]),
            int(extents.x_stop[index]),
            (int(extents.first_y[index]), int(extents.first_x[index])),
            int(extents.pixel_count[index]),
        )
        for index, value in enumerate(extents.values)
    }


def test_extents_bound_each_label_and_name_its_first_pixel() -> None:
    labels = _labels("""
        0330
        0100
        1002
    """)
    assert _extent_mapping(labels) == {
        1: (1, 3, 0, 2, (1, 1), 2),
        2: (2, 3, 3, 4, (2, 3), 1),
        3: (0, 1, 1, 3, (0, 1), 2),
    }


def test_extents_describe_only_the_labels_pixels_carry() -> None:
    """Global labels are sparse, so gaps must not become empty entries."""
    labels = _labels("""
        0090
        4000
    """)
    assert sorted(label_extents(labels).values.tolist()) == [4, 9]


def test_extents_of_an_unlabelled_plane_are_empty() -> None:
    extents = label_extents(np.zeros((3, 4), dtype=np.int32))
    assert extents.values.size == 0
    assert extents.first_y.size == 0
    assert extents.y_stop.size == 0
    assert extents.pixel_count.size == 0


def test_extents_reject_a_plane_that_is_not_two_dimensional() -> None:
    with pytest.raises(ValueError, match="two-dimensional"):
        label_extents(np.zeros((2, 2, 2), dtype=np.int32))


@pytest.mark.parametrize("seed", range(6))
def test_extents_agree_with_the_per_label_scan(seed: int) -> None:
    """The one-pass kernel must equal the scan it replaces, gaps included."""
    generator = np.random.default_rng(seed)
    labels = generator.choice(
        np.array([0, 0, 0, 1, 2, 5, 9, 40], dtype=np.int32),
        size=(11, 7),
    ).astype(np.int32)
    scanned = _scanned_extents(labels)
    assert len(scanned) > 1
    assert _extent_mapping(labels) == scanned
