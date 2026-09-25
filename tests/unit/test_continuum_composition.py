# pyright: reportMissingTypeStubs=false
"""The composition's per-scale records, which carry no published plane."""

from __future__ import annotations

from hebog.algorithms.reconciliation import DetectedIsland
from hebog.data_models.partitioning import ImageBounds
from hebog.science.continuum import retained_scale_detections
from hebog.science.models import TiledMultiscaleDetection


def test_composition_describes_each_published_scale_feature() -> None:
    """Scale records are rebuilt from the reconciled islands alone.

    The scale masks stay in the generation that wrote them: the cores already
    required their support to lie inside the domain their own estimate covers,
    so naming the features needs no plane.
    """
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

    scales = retained_scale_detections(
        TiledMultiscaleDetection(
            detection_islands=(),
            scale_islands_by_order=((island,), (), ()),
            scale_nominal_beam_fwhms=(1.0, 2.0, 4.0),
        )
    )

    assert len(scales) == 3
    assert scales[0].scale_order == 1
    assert len(scales[0].detections) == 1
    assert scales[0].detections[0].support_pixel_count == 4
    assert scales[0].detections[0].peak_response_jy_per_beam == 0.5
    assert scales[1].detections == ()
