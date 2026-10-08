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
    ("beam_major_fwhm_pixels", "recovery_radius_beams", "halo_pixels"),
    [
        (4.0, 0.0, 3),
        (0.5, 0.5, 3),
        (2.0, 0.5, 4),
        (3.0, 0.5, 4),
        (4.0, 0.5, 5),
        (5.0, 0.5, 5),
        (6.0, 0.5, 6),
        (10.0, 0.5, 8),
    ],
)
def test_support_halo_covers_persistence_at_whole_pixel_radii(
    beam_major_fwhm_pixels: float,
    recovery_radius_beams: float,
    halo_pixels: int,
) -> None:
    """Persistence reaches one pixel past refinement at a whole radius.

    Refinement reaches ``ceil(r) + 2`` pixels and persistence ``floor(r) +
    3``, for a recovery radius ``r`` of half a beam by default, so beams of
    2, 4, 6 and 10 pixels need one pixel more than refinement alone, and a
    zero radius still covers the three-pixel dense-core count.
    """
    assert (
        segment_refinement_halo_pixels(
            beam_major_fwhm_pixels,
            recovery_radius_beams=recovery_radius_beams,
        )
        == halo_pixels
    )


@pytest.mark.parametrize(
    ("beam_major_fwhm_pixels", "recovery_radius_beams", "message"),
    [
        (float("inf"), 0.5, "beam major FWHM"),
        (float("nan"), 0.5, "beam major FWHM"),
        (0.0, 0.5, "beam major FWHM"),
        (4.0, float("inf"), "recovery radius"),
        (4.0, -0.5, "recovery radius"),
    ],
)
def test_support_halo_rejects_an_undefined_radius(
    beam_major_fwhm_pixels: float,
    recovery_radius_beams: float,
    message: str,
) -> None:
    """A radius that is not finite and non-negative has no halo."""
    with pytest.raises(ValueError, match=message):
        segment_refinement_halo_pixels(
            beam_major_fwhm_pixels,
            recovery_radius_beams=recovery_radius_beams,
        )


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
