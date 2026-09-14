#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Run one Hebog leg through the frozen Phase 5 recovery boundary."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any, cast

import numpy as np
from astropy.io import fits

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation import external_runners
from hebog.validation.contracts import load_phase_five_corrective_a_review
from hebog.validation.post_correction_recovery import (
    build_post_correction_continuum_products,
    post_correction_candidate_configuration,
)
from hebog.validation.products import (
    load_fits_plane,
    write_comparison_catalogue,
)


def _run_recovery_continuum_products(
    authorized: Any,
    dataset: Any,
    base_review_path: Path,
    staging: Path,
) -> dict[str, Path]:
    """Emit the exact shared-adapter Continuum products."""
    review = load_phase_five_corrective_a_review(base_review_path)
    image_path = authorized.artifact_path("image")
    image = load_fits_plane(image_path)
    mean = load_fits_plane(authorized.artifact_path("mean"))
    rms = load_fits_plane(authorized.artifact_path("rms"))
    beam = BeamShapePixels(
        dataset.beam.major_fwhm_pixels,
        dataset.beam.minor_fwhm_pixels,
        dataset.beam.position_angle_degrees,
    )
    header = cast(fits.Header, fits.getheader(image_path))
    products = build_post_correction_continuum_products(
        image,
        mean,
        rms,
        header,
        beam=beam,
        review=review,
    )
    segment_path = staging / "segment_catalogue.json"
    label_path = staging / "segment_labels.fits"
    mask_path = staging / "segment_mask.fits"
    write_comparison_catalogue(segment_path, products.catalogue)
    fits.PrimaryHDU(
        data=products.detection.component_labels[np.newaxis, np.newaxis, :, :],
        header=header,
    ).writeto(label_path)
    fits.PrimaryHDU(
        data=products.detection.retained_mask.astype(np.uint8)[
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
    """Install recovery loaders and the exact approved candidate products."""
    root = Path(__file__).parents[2]
    helpers = runpy.run_path(
        str(root / "scripts/validation/phase5_external_recovery_protocol.py")
    )
    external_runners.load_phase_five_external_comparison_protocol = helpers[
        "load_recovery_protocol"
    ]
    external_runners.load_phase_five_external_execution_decision = helpers[
        "load_recovery_execution_decision"
    ]
    external_runners._RUNNER_PATHS[  # pyright: ignore[reportPrivateUsage]
        "hebog"
    ] = "scripts/benchmark/run_phase5_external_recovery_hebog.py"
    terminal = runpy.run_path(
        str(root / "scripts/benchmark/run_phase5_external_hebog.py")
    )
    terminal["_run_hebog"].__globals__["_run_continuum_products"] = (
        _run_recovery_continuum_products
    )
    original_execute = terminal["main"].__globals__["execute_external_run"]
    base_review = root / "config/contracts/phase-5-corrective-a-review.json"

    def execute_with_recovery_configuration(
        authorized: Any,
        **kwargs: Any,
    ) -> Any:
        """Replace the obsolete emitted configuration with the approved one."""
        kwargs["configuration"] = post_correction_candidate_configuration(
            base_review
        )
        return original_execute(authorized, **kwargs)

    terminal["main"].__globals__["execute_external_run"] = (
        execute_with_recovery_configuration
    )
    terminal["main"].__globals__["__file__"] = str(Path(__file__))
    terminal["main"]()


if __name__ == "__main__":
    main()
