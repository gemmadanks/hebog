"""Contracts for the reviewed continuum stage halos."""

from __future__ import annotations

import pytest

from hebog.algorithms.extended_measurement import (
    segment_refinement_halo_pixels,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    residual_atrous_scale_halos_pixels,
    scale_smoothing_halo_pixels,
)
from hebog.algorithms.multiscale_tiles import (
    scale_filter_halo_pixels,
    segment_association_halo_pixels,
)


def _beam() -> BeamShapePixels:
    """Return a representative five-pixel restoring beam."""
    return BeamShapePixels(5.0, 4.0, 20.0)


def test_allocation_free_halo_helpers_match_kernel_policies() -> None:
    """Planning and scientific kernels share the same exact radii."""
    assert tuple(
        scale_smoothing_halo_pixels(
            _beam(),
            width_beams=width,
            truncation_sigma=4.0,
        )
        for width in (1.0, 2.0, 4.0)
    ) == (9, 17, 34)
    assert residual_atrous_scale_halos_pixels() == (2, 6, 14)
    assert scale_filter_halo_pixels(_beam()) == 34
    assert segment_association_halo_pixels(_beam()) == 15
    assert segment_refinement_halo_pixels(5.0) == 5
    assert segment_refinement_halo_pixels(0.5) == 3


@pytest.mark.parametrize(
    ("width_beams", "truncation_sigma", "message"),
    [
        (0.0, 4.0, "scale width"),
        (1.0, 2.0, "truncation_sigma"),
    ],
)
def test_scale_halo_helper_rejects_undefined_kernel(
    width_beams: float,
    truncation_sigma: float,
    message: str,
) -> None:
    """Allocation-free planning rejects invalid filter geometry."""
    with pytest.raises(ValueError, match=message):
        scale_smoothing_halo_pixels(
            _beam(),
            width_beams=width_beams,
            truncation_sigma=truncation_sigma,
        )
