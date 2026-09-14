# pyright: reportMissingTypeStubs=false
"""Approved candidate composition for Phase 5 post-correction recovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.comparison import CatalogueSource
from hebog.validation.contracts import PhaseFiveCorrectiveAReview
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.hebog_campaign import (
    corrected_hebog_campaign_configuration,
)
from hebog.validation.phase_five_filter_review import ThresholdFilterResult
from hebog.validation.post_campaign_science import (
    CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS,
    evaluate_post_campaign_candidate_products,
)
from hebog.validation.products import build_hebog_segment_catalogue

_POSITION_POLICY = (
    "direct-plus-residual-b3-at-or-below-peak-to-mean-3-otherwise-original"
)
_SUPPORT_POLICY = "refined-residual-b3-multiscale-boundary"
_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class PostCorrectionContinuumProducts:
    """Complete approved Continuum products for one image."""

    detection: ThresholdFilterResult
    catalogue: tuple[CatalogueSource, ...]
    valid_pixels: npt.NDArray[np.bool_]


def post_correction_candidate_configuration(
    base_review_path: Path,
) -> dict[str, object]:
    """Return the exact approved compact and Continuum configuration."""
    return {
        "compact": corrected_hebog_campaign_configuration(),
        "continuum": {
            "base_review_sha256": file_sha256(base_review_path),
            "measurement_aperture_radius_beams": (
                CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
            ),
            "position_policy": _POSITION_POLICY,
            "support_policy": _SUPPORT_POLICY,
        },
    }


def post_correction_candidate_configuration_sha256(
    base_review_path: Path,
) -> str:
    """Return the canonical identity of the approved candidate."""
    return canonical_sha256(
        post_correction_candidate_configuration(base_review_path)
    )


def _aligned_plane(
    values: npt.ArrayLike,
    *,
    name: str,
    shape: tuple[int, int] | None = None,
) -> npt.NDArray[np.float64]:
    """Return one real two-dimensional plane with optional exact shape."""
    plane = np.asarray(values)
    if (
        plane.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(plane.dtype, np.number)
        or np.iscomplexobj(plane)
        or (shape is not None and plane.shape != shape)
    ):
        raise ValueError(
            f"post-correction {name} must be an aligned real "
            "two-dimensional plane"
        )
    return np.asarray(plane, dtype=np.float64)


def build_post_correction_continuum_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    header: fits.Header,
    *,
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveAReview,
) -> PostCorrectionContinuumProducts:
    """Build every reviewed candidate product through one shared adapter."""
    image = _aligned_plane(image_jy_per_beam, name="image")
    background = _aligned_plane(
        background_jy_per_beam,
        name="background",
        shape=image.shape,
    )
    rms = _aligned_plane(
        rms_jy_per_beam,
        name="RMS",
        shape=image.shape,
    )
    valid = np.isfinite(image) & np.isfinite(background) & np.isfinite(rms)
    if np.any(np.isfinite(image) != valid):
        raise ValueError(
            "post-correction mean/RMS validity differs from image"
        )
    products = evaluate_post_campaign_candidate_products(
        image,
        valid,
        background,
        rms,
        beam=beam,
        review=review,
    )
    catalogue = build_hebog_segment_catalogue(
        image,
        background,
        valid,
        products.detection.component_labels,
        header,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam.minor_fwhm_pixels,
        measurement_aperture_radius_beams=(
            CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
        ),
        position_signal_jy_per_beam=products.position_signal_jy_per_beam,
    )
    valid.setflags(write=False)
    return PostCorrectionContinuumProducts(
        detection=products.detection,
        catalogue=catalogue,
        valid_pixels=valid,
    )
