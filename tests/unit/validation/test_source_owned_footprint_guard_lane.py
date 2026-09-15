"""Prospective contracts for the source-owned footprint-guard lane."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import numpy as np
import pytest

from hebog.validation import adaptive_background_lane


def test_support_topology_rejects_subthreshold_rows_inside_truth_box() -> None:
    """A nearby noise island is unmatched when its own support misses truth."""
    truth = np.zeros((7, 7), dtype=np.bool_)
    truth[2:5, 2:5] = True
    source_labels = np.zeros((7, 7), dtype=np.int32)
    source_labels[3, 3] = 1
    source_labels[1, 3] = 2

    topology = adaptive_background_lane.truth_linked_source_support_topology(
        ("source-a", "source-b"),
        source_labels,
        {1: "source-a", 2: "source-b"},
        truth,
    )

    assert topology.truth_linked_source_indices == (0,)
    assert topology.unmatched_source_indices == (1,)
    assert topology.truth_linked_split is False


def test_support_topology_detects_distinct_rows_overlapping_one_truth() -> (
    None
):
    """Two source-owned supports intersecting one truth remain a split."""
    truth = np.zeros((7, 7), dtype=np.bool_)
    truth[2:5, 2:5] = True
    source_labels = np.zeros((7, 7), dtype=np.int32)
    source_labels[2, 2] = 1
    source_labels[4, 4] = 2

    topology = adaptive_background_lane.truth_linked_source_support_topology(
        ("source-a", "source-b"),
        source_labels,
        {1: "source-a", 2: "source-b"},
        truth,
    )

    assert topology.truth_linked_source_indices == (0, 1)
    assert topology.unmatched_source_indices == ()
    assert topology.truth_linked_split is True


@pytest.mark.parametrize(
    ("source_identifiers", "source_labels", "mapping", "truth", "message"),
    (
        (
            ("source-a",),
            np.zeros((2, 2), dtype=np.int32),
            {},
            np.zeros((2, 2), dtype=np.bool_),
            "truth support must not be empty",
        ),
        (
            ("source-a",),
            np.ones((2, 2), dtype=np.int32),
            {1: "source-a"},
            np.ones((2, 2), dtype=np.int32),
            "two-dimensional boolean plane",
        ),
        (
            ("source-a",),
            np.ones((3, 2), dtype=np.int32),
            {1: "source-a"},
            np.ones((2, 2), dtype=np.bool_),
            "aligned non-negative integer plane",
        ),
        (
            ("source-a",),
            np.full((2, 2), -1, dtype=np.int32),
            {1: "source-a"},
            np.ones((2, 2), dtype=np.bool_),
            "aligned non-negative integer plane",
        ),
        (
            ("source-a", "source-a"),
            np.ones((2, 2), dtype=np.int32),
            {1: "source-a"},
            np.ones((2, 2), dtype=np.bool_),
            "source identifiers must be unique",
        ),
        (
            ("source-a",),
            np.ones((2, 2), dtype=np.int32),
            {2: "source-a"},
            np.ones((2, 2), dtype=np.bool_),
            "source label identity mapping is inconsistent",
        ),
    ),
)
def test_support_topology_fails_closed_on_inconsistent_inputs(
    source_identifiers: tuple[str, ...],
    source_labels: np.ndarray,
    mapping: dict[int, str],
    truth: np.ndarray,
    message: str,
) -> None:
    """Malformed linkage evidence cannot silently change split semantics."""
    with pytest.raises(ValueError, match=message):
        adaptive_background_lane.truth_linked_source_support_topology(
            source_identifiers,
            source_labels,
            mapping,
            truth,
        )
