#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Run the prospective Hebog science fixes through the development boundary."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any, cast

import numpy as np
from astropy.io import fits

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation import external_runners
from hebog.validation.contracts import load_phase_five_corrective_a_review
from hebog.validation.post_campaign_science import (
    CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS,
    evaluate_post_campaign_candidate_products,
)
from hebog.validation.products import (
    build_hebog_segment_catalogue,
    load_fits_plane,
    write_comparison_catalogue,
)


def _run_reviewed_continuum_products(
    authorized: Any,
    dataset: Any,
    base_review_path: Path,
    staging: Path,
) -> dict[str, Path]:
    """Emit explicitly connected detection, position, and flux products."""
    review = load_phase_five_corrective_a_review(base_review_path)
    image_path = authorized.artifact_path("image")
    image = load_fits_plane(image_path)
    mean = load_fits_plane(authorized.artifact_path("mean"))
    rms = load_fits_plane(authorized.artifact_path("rms"))
    valid = np.isfinite(image) & np.isfinite(mean) & np.isfinite(rms)
    if np.any(np.isfinite(image) != valid):
        raise ValueError("external mean/RMS validity differs from image")
    beam = BeamShapePixels(
        dataset.beam.major_fwhm_pixels,
        dataset.beam.minor_fwhm_pixels,
        dataset.beam.position_angle_degrees,
    )
    products = evaluate_post_campaign_candidate_products(
        image,
        valid,
        mean,
        rms,
        beam=beam,
        review=review,
    )
    detection = products.detection
    header = cast(fits.Header, fits.getheader(image_path))
    segment_sources = build_hebog_segment_catalogue(
        image,
        mean,
        valid,
        detection.component_labels,
        header,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam.minor_fwhm_pixels,
        measurement_aperture_radius_beams=(
            CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
        ),
        position_signal_jy_per_beam=(products.position_signal_jy_per_beam),
    )
    segment_path = staging / "segment_catalogue.json"
    label_path = staging / "segment_labels.fits"
    mask_path = staging / "segment_mask.fits"
    write_comparison_catalogue(segment_path, segment_sources)
    fits.PrimaryHDU(
        data=detection.component_labels[np.newaxis, np.newaxis, :, :],
        header=header,
    ).writeto(label_path)
    fits.PrimaryHDU(
        data=detection.retained_mask.astype(np.uint8)[
            np.newaxis, np.newaxis, :, :
        ],
        header=header,
    ).writeto(mask_path)
    return {
        "segment-catalogue-json": segment_path,
        "segment-labels-fits": label_path,
        "segment-mask-fits": mask_path,
    }


def main() -> None:
    """Install prospective science seams around the historical runner."""
    root = Path(__file__).parents[2]
    runner_path = root / "scripts/benchmark/run_phase5_external_hebog.py"
    terminal = runpy.run_path(str(runner_path))
    run_hebog = terminal["_run_hebog"]
    run_hebog.__globals__["_run_continuum_products"] = (
        _run_reviewed_continuum_products
    )
    external_runners._RUNNER_PATHS[  # pyright: ignore[reportPrivateUsage]
        "hebog"
    ] = "scripts/benchmark/run_phase5_post_campaign_hebog.py"
    terminal["main"].__globals__["__file__"] = str(Path(__file__))
    terminal["main"]()


if __name__ == "__main__":
    main()
