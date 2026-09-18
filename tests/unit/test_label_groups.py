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
