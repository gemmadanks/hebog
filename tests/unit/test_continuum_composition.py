# pyright: reportMissingTypeStubs=false
"""Boundary validation of the composition over published support planes."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.reconciliation import DetectedIsland
from hebog.data_models.partitioning import ImageBounds
from hebog.science.continuum import (
    build_continuum_detection,
    retained_scale_detections,
)
from hebog.science.models import (
    TiledMultiscaleDetection,
    TiledSupportLabels,
)

_SHAPE = (6, 7)


def _multiscale(
    *,
    significant_scale_masks: tuple[npt.NDArray[np.bool_], ...] | None = None,
    scale_islands_by_order: (
        tuple[tuple[DetectedIsland, ...], ...] | None
    ) = None,
) -> TiledMultiscaleDetection:
    """Return one published detection pass over a small analytic plane."""
    empty = np.zeros(_SHAPE, dtype=np.bool_)
    return TiledMultiscaleDetection(
        detection_labels=np.zeros(_SHAPE, dtype=np.int32),
        reconstruction_mask=empty,
        position_signal_jy_per_beam=np.zeros(_SHAPE, dtype=np.float64),
        significant_scale_masks=(
            (empty, empty, empty)
            if significant_scale_masks is None
            else significant_scale_masks
        ),
        detection_islands=(),
        scale_islands_by_order=(
            ((), (), ())
            if scale_islands_by_order is None
            else scale_islands_by_order
        ),
        scale_nominal_beam_fwhms=(1.0, 2.0, 4.0),
    )


def _labels(
    *,
    retained_mask: npt.NDArray[np.bool_] | None = None,
) -> TiledSupportLabels:
    """Return one published support pass over a small analytic plane."""
    return TiledSupportLabels(
        component_labels=np.zeros(_SHAPE, dtype=np.int32),
        measurement_labels=np.zeros(_SHAPE, dtype=np.int32),
        publication_labels=np.zeros(_SHAPE, dtype=np.int32),
        retained_mask=(
            np.zeros(_SHAPE, dtype=np.bool_)
            if retained_mask is None
            else retained_mask
        ),
    )


def test_composition_rejects_scale_support_outside_the_valid_domain() -> None:
    """Published scale support cannot claim a scientifically invalid pixel."""
    invalid_support = np.zeros(_SHAPE, dtype=np.bool_)
    invalid_support[2, 3] = True
    valid = np.ones(_SHAPE, dtype=np.bool_)
    valid[2, 3] = False

    with pytest.raises(ValueError, match="scientifically valid"):
        build_continuum_detection(
            valid,
            multiscale=_multiscale(
                significant_scale_masks=(
                    invalid_support,
                    np.zeros(_SHAPE, dtype=np.bool_),
                    np.zeros(_SHAPE, dtype=np.bool_),
                )
            ),
            labels=_labels(),
        )


def test_composition_rejects_a_mask_its_publication_labels_contradict() -> (
    None
):
    """The published mask is the publication labels, not a second decision."""
    disagreeing = np.zeros(_SHAPE, dtype=np.bool_)
    disagreeing[1, 1] = True

    with pytest.raises(ValueError, match="retained mask must agree"):
        build_continuum_detection(
            np.ones(_SHAPE, dtype=np.bool_),
            multiscale=_multiscale(),
            labels=_labels(retained_mask=disagreeing),
        )


def test_composition_describes_each_published_scale_feature() -> None:
    """Scale records are rebuilt from the published masks and islands."""
    support = np.zeros(_SHAPE, dtype=np.bool_)
    support[1:3, 1:3] = True
    island = DetectedIsland(
        island_id="island-00001",
        global_label=1,
        pixel_count=4,
        bounds=ImageBounds(1, 3, 1, 3),
        peak_signal_to_noise=7.0,
        peak_position_yx=(1, 1),
        first_pixel_yx=(1, 1),
        touches_image_edge=False,
        peak_response_jy_per_beam=0.5,
    )

    multiscale = _multiscale(
        significant_scale_masks=(
            support,
            np.zeros(_SHAPE, dtype=np.bool_),
            np.zeros(_SHAPE, dtype=np.bool_),
        ),
        scale_islands_by_order=((island,), (), ()),
    )

    scales = retained_scale_detections(
        multiscale, np.ones(_SHAPE, dtype=np.bool_)
    )
    detection = build_continuum_detection(
        np.ones(_SHAPE, dtype=np.bool_),
        multiscale=multiscale,
        labels=_labels(),
    )

    assert len(scales) == 3
    assert scales[0].scale_order == 1
    assert len(scales[0].detections) == 1
    assert scales[0].detections[0].support_pixel_count == 4
    assert scales[0].detections[0].peak_response_jy_per_beam == 0.5
    assert detection.component_count == 0
