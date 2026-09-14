"""Tests for the fast public catalogue-topology diagnostic."""

from __future__ import annotations

import runpy
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).parents[3]
_PROGRAM = runpy.run_path(
    str(_ROOT / "scripts/validation/check_phase5_public_catalogue_topology.py")
)
summarize_catalogue_topology = _PROGRAM["summarize_catalogue_topology"]


def test_multi_peak_support_requires_component_review() -> None:
    """One component cannot represent two beam-separated significant peaks."""
    image = np.zeros((15, 15), dtype=np.float64)
    image[7, 3] = 10.0
    image[7, 11] = 12.0
    labels = np.zeros_like(image, dtype=np.int32)
    labels[5:10, 1:14] = 7

    summary = summarize_catalogue_topology(
        image,
        np.zeros_like(image),
        np.ones_like(image),
        labels,
        beam_width_pixels=5.0,
        component_label_values=(7,),
    )

    assert summary["status"] == "review-required"
    assert summary["support_label_count"] == 1
    assert summary["multi_peak_support_count"] == 1
    assert summary["component_underrepresented_support_count"] == 1
    assert summary["maximum_peaks_per_support"] == 2
    assert summary["review_label_values"] == [7]


def test_multiple_components_can_represent_multi_peak_support() -> None:
    """The diagnostic passes when component multiplicity covers the peaks."""
    image = np.zeros((15, 15), dtype=np.float64)
    image[7, 3] = 10.0
    image[7, 11] = 12.0
    labels = np.zeros_like(image, dtype=np.int32)
    labels[5:10, 1:14] = 7

    summary = summarize_catalogue_topology(
        image,
        np.zeros_like(image),
        np.ones_like(image),
        labels,
        beam_width_pixels=5.0,
        component_label_values=(7, 7),
    )

    assert summary["status"] == "pass"
    assert summary["multi_peak_support_count"] == 1
    assert summary["component_underrepresented_support_count"] == 0
    assert summary["review_label_values"] == []


def test_component_plane_maps_new_component_ids_to_parent_support() -> None:
    """Deblended component IDs are counted under their support parent."""
    image = np.zeros((15, 15), dtype=np.float64)
    image[7, 3] = 10.0
    image[7, 11] = 12.0
    support = np.zeros_like(image, dtype=np.int32)
    support[5:10, 1:14] = 7
    components = np.zeros_like(image, dtype=np.int32)
    components[5:10, 1:8] = 1
    components[5:10, 8:14] = 2

    summary = summarize_catalogue_topology(
        image,
        np.zeros_like(image),
        np.ones_like(image),
        support,
        beam_width_pixels=5.0,
        component_label_values=(1, 2),
        component_labels=components,
    )

    assert summary["status"] == "pass"
    assert summary["published_component_count"] == 2
    assert summary["component_underrepresented_support_count"] == 0


def test_flat_peak_plateau_is_counted_once() -> None:
    """Pixel sampling of a flat peak must not fabricate components."""
    image = np.zeros((11, 11), dtype=np.float64)
    image[4:6, 4:6] = 10.0
    labels = np.zeros_like(image, dtype=np.int32)
    labels[2:8, 2:8] = 3

    summary = summarize_catalogue_topology(
        image,
        np.zeros_like(image),
        np.ones_like(image),
        labels,
        beam_width_pixels=3.0,
        component_label_values=(3,),
    )

    assert summary["selected_peak_count"] == 1
    assert summary["maximum_peaks_per_support"] == 1
    assert summary["status"] == "pass"


@pytest.mark.parametrize("beam_width", [0.0, -1.0, float("nan")])
def test_invalid_beam_width_is_rejected(beam_width: float) -> None:
    plane = np.ones((3, 3), dtype=np.float64)

    with pytest.raises(ValueError, match="beam_width_pixels"):
        summarize_catalogue_topology(
            plane,
            plane,
            plane,
            np.ones((3, 3), dtype=np.int32),
            beam_width_pixels=beam_width,
            component_label_values=(1,),
        )


def test_misaligned_planes_are_rejected() -> None:
    with pytest.raises(ValueError, match="aligned two-dimensional"):
        summarize_catalogue_topology(
            np.ones((3, 3)),
            np.ones((3, 2)),
            np.ones((3, 3)),
            np.ones((3, 3), dtype=np.int32),
            beam_width_pixels=2.0,
            component_label_values=(1,),
        )
