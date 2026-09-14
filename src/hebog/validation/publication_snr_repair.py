# pyright: reportMissingTypeStubs=false
"""Prospective original-pixel publication significance repair."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.algorithms.extended_measurement import (
    refine_multiscale_segment_labels,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.contracts import PhaseFiveCorrectiveAReview
from hebog.validation.external_runners import file_sha256
from hebog.validation.post_campaign_science import (
    CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS,
    PostCampaignCandidateProducts,
    evaluate_public_finder_correction_candidate_products,
)
from hebog.validation.products import (
    build_hebog_reconstructed_source_catalogues,
)
from hebog.validation.public_finder_correction import (
    PublicFinderCorrectionContinuumProducts,
)

_IMAGE_DIMENSIONS = 2
_PUBLICATION_SNR_POLICY = "direct-original-pixel-snr-published-boundary-v1"


def public_finder_publication_snr_repair_configuration(
    base_configuration: Mapping[str, object],
    publication_snr_pre_review_path: Path,
    publication_snr_implementation_decision_path: Path,
) -> dict[str, object]:
    """Bind original-pixel publication significance to one base identity."""
    compact = base_configuration.get("compact")
    continuum_value = base_configuration.get("continuum")
    if not isinstance(compact, dict) or not isinstance(continuum_value, dict):
        raise TypeError(
            "base publication-SNR configuration must contain dictionaries"
        )
    continuum = dict(cast(dict[str, object], continuum_value))
    continuum.update(
        {
            "publication_snr_policy": _PUBLICATION_SNR_POLICY,
            "publication_snr_pre_review_sha256": file_sha256(
                publication_snr_pre_review_path
            ),
            "publication_snr_implementation_decision_sha256": file_sha256(
                publication_snr_implementation_decision_path
            ),
        }
    )
    return {
        "compact": dict(cast(dict[str, object], compact)),
        "continuum": continuum,
    }


def _aligned_plane(
    values: npt.ArrayLike,
    *,
    name: str,
    shape: tuple[int, int] | None = None,
) -> npt.NDArray[np.float64]:
    """Return one aligned real two-dimensional prospective plane."""
    plane = np.asarray(values)
    if (
        plane.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(plane.dtype, np.number)
        or np.iscomplexobj(plane)
        or (shape is not None and plane.shape != shape)
    ):
        raise ValueError(
            f"publication-SNR repair {name} must be an aligned real "
            "two-dimensional plane"
        )
    return np.asarray(plane, dtype=np.float64)


def evaluate_publication_snr_repaired_candidate_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    *,
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveAReview,
) -> PostCampaignCandidateProducts:
    """Publish refined support from original-pixel rather than filtered S/N."""
    products = evaluate_public_finder_correction_candidate_products(
        image_jy_per_beam,
        valid_pixels,
        background_jy_per_beam,
        rms_jy_per_beam,
        beam=beam,
        review=review,
    )
    image = _aligned_plane(image_jy_per_beam, name="image")
    background = _aligned_plane(
        background_jy_per_beam,
        name="background",
        shape=image.shape,
    )
    rms = _aligned_plane(rms_jy_per_beam, name="RMS", shape=image.shape)
    valid = np.asarray(valid_pixels)
    if valid.shape != image.shape or valid.dtype != np.bool_:
        raise ValueError(
            "publication-SNR repair validity must be one aligned boolean plane"
        )
    direct_snr = np.full(image.shape, -np.inf, dtype=np.float64)
    direct_valid = (
        valid
        & np.isfinite(image)
        & np.isfinite(background)
        & np.isfinite(rms)
        & (rms > 0)
    )
    np.divide(
        image - background,
        rms,
        out=direct_snr,
        where=direct_valid,
    )
    labels = refine_multiscale_segment_labels(
        products.measurement_component_labels,
        direct_snr,
        products.significant_multiscale_support,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        recovered_minimum_snr=review.matrix.island_sigma,
    )
    retained = np.asarray(labels > 0, dtype=np.bool_)
    labels.setflags(write=False)
    retained.setflags(write=False)
    return replace(
        products,
        detection=replace(
            products.detection,
            retained_mask=retained,
            component_labels=labels,
            component_count=int(np.count_nonzero(np.unique(labels) > 0)),
        ),
    )


def build_publication_snr_repaired_continuum_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    header: fits.Header,
    *,
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveAReview,
) -> PublicFinderCorrectionContinuumProducts:
    """Build exact source products with repaired publication significance."""
    image = _aligned_plane(image_jy_per_beam, name="image")
    background = _aligned_plane(
        background_jy_per_beam,
        name="background",
        shape=image.shape,
    )
    rms = _aligned_plane(rms_jy_per_beam, name="RMS", shape=image.shape)
    valid = np.isfinite(image) & np.isfinite(background) & np.isfinite(rms)
    if np.any(np.isfinite(image) != valid):
        raise ValueError(
            "publication-SNR repair mean/RMS validity differs from image"
        )
    products = evaluate_publication_snr_repaired_candidate_products(
        image,
        valid,
        background,
        rms,
        beam=beam,
        review=review,
    )
    catalogues = build_hebog_reconstructed_source_catalogues(
        image,
        background,
        valid,
        products.measurement_component_labels,
        products.direct_component_labels,
        products.significant_multiscale_support,
        products.scale_detection_planes,
        header,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam.minor_fwhm_pixels,
        measurement_aperture_radius_beams=(
            CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
        ),
        position_signal_jy_per_beam=products.position_signal_jy_per_beam,
    )
    valid.setflags(write=False)
    return PublicFinderCorrectionContinuumProducts(
        detection=products.detection,
        measurement_component_labels=products.measurement_component_labels,
        catalogue=catalogues.source_catalogue,
        valid_pixels=valid,
        component_catalogue=catalogues.component_catalogue,
        source_association=catalogues.association,
    )
