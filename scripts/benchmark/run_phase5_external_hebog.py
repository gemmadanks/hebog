#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Run one authorized Phase 5 realization with the frozen Hebog candidate."""

from __future__ import annotations

import argparse
import importlib.metadata
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, cast

import numpy as np
from astropy.io import fits

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.contracts import load_phase_five_corrective_a_review
from hebog.validation.datasets import DatasetRecord, load_dataset_manifest
from hebog.validation.external_runners import (
    AuthorizedExternalRun,
    ExternalRuntimeIdentity,
    authorize_external_run,
    execute_external_run,
    file_sha256,
)
from hebog.validation.hebog_campaign import (
    corrected_hebog_campaign_configuration,
    process_hebog_image,
)
from hebog.validation.phase_five_filter_review import (
    evaluate_external_candidate_detection,
)
from hebog.validation.products import (
    build_hebog_segment_catalogue,
    load_fits_plane,
    write_comparison_catalogue,
)


def _parse_args() -> argparse.Namespace:
    """Parse one checksum-bound Hebog realization request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--execution-decision", required=True, type=Path)
    parser.add_argument("--base-review", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--container-image-digest", required=True)
    return parser.parse_args()


def _dataset(
    authorized: AuthorizedExternalRun,
    manifest_path: Path,
) -> DatasetRecord:
    """Resolve one dataset only from the checksum-bound population manifest."""
    if file_sha256(manifest_path) != authorized.input_bundle.manifest_sha256:
        raise ValueError("Hebog external manifest checksum changed")
    manifest = load_dataset_manifest(manifest_path)
    matches = tuple(
        dataset
        for dataset in manifest.datasets
        if dataset.identifier == authorized.input_bundle.dataset_identifier
    )
    if len(matches) != 1:
        raise ValueError("Hebog external dataset identity is not unique")
    return matches[0]


def _finder_lane(
    authorized: AuthorizedExternalRun,
) -> Literal["continuum", "compact-blend"]:
    """Resolve one lane from the checksum-bound population manifest."""
    matches = tuple(
        population.lane
        for population in authorized.protocol.populations
        if population.manifest_sha256
        == authorized.input_bundle.manifest_sha256
    )
    if len(matches) != 1:
        raise ValueError("Hebog external population lane is not unique")
    return matches[0]


def _run_continuum_products(
    authorized: AuthorizedExternalRun,
    dataset: DatasetRecord,
    base_review_path: Path,
    staging: Path,
) -> dict[str, Path]:
    """Emit extended products without depending on compact fitting."""
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
    detection = evaluate_external_candidate_detection(
        image,
        valid,
        mean,
        rms,
        beam=beam,
        review=review,
    )
    header = cast(fits.Header, fits.getheader(image_path))
    segment_sources = build_hebog_segment_catalogue(
        image,
        mean,
        valid,
        detection.component_labels,
        header,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam.minor_fwhm_pixels,
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


def _run_compact_products(
    authorized: AuthorizedExternalRun,
    dataset: DatasetRecord,
    staging: Path,
) -> dict[str, Path]:
    """Emit compact products without running the continuum branch."""
    image = load_fits_plane(authorized.artifact_path("image"))
    with TemporaryDirectory(prefix="hebog-phase5-external-compact-") as work:
        compact_sources = process_hebog_image(
            image,
            dataset,
            Path(work),
            generation_id=(
                f"{dataset.identifier}-{authorized.input_bundle.seed}"
            ),
        )
    compact_path = staging / "compact_catalogue.json"
    write_comparison_catalogue(compact_path, compact_sources)
    return {"compact-catalogue-json": compact_path}


def _run_hebog(
    authorized: AuthorizedExternalRun,
    dataset: DatasetRecord,
    base_review_path: Path,
    staging: Path,
) -> dict[str, Path]:
    """Emit only the products belonging to the authorized science lane."""
    if _finder_lane(authorized) == "continuum":
        return _run_continuum_products(
            authorized,
            dataset,
            base_review_path,
            staging,
        )
    return _run_compact_products(authorized, dataset, staging)


def main() -> None:
    """Authorize and execute one immutable Hebog comparison leg."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite external result: {arguments.output}"
        )
    authorized = authorize_external_run(
        protocol_path=arguments.protocol,
        execution_decision_path=arguments.execution_decision,
        input_bundle_path=arguments.input,
        runner_path=Path(__file__),
        finder_id="hebog",
    )
    if authorized.protocol.candidate != (
        "residual-b3-original-pixel-measurement"
    ):
        raise ValueError("external protocol does not select this Hebog runner")
    if (
        file_sha256(arguments.base_review)
        != authorized.decision.candidate_review_sha256
    ):
        raise ValueError("Hebog candidate review checksum is not authorized")
    dataset = _dataset(authorized, arguments.manifest)
    base_review = load_phase_five_corrective_a_review(arguments.base_review)
    if (
        arguments.container_image_digest
        != authorized.decision.hebog_container_image_digest
    ):
        raise ValueError("Hebog container digest is not authorized")
    observed_inventory = dependency_inventory_sha256()
    if (
        observed_inventory
        != authorized.decision.hebog_dependency_inventory_sha256
    ):
        raise RuntimeError("Hebog dependency inventory is not authorized")
    configuration = {
        "candidate": authorized.protocol.candidate,
        "candidate_position": authorized.protocol.candidate_position,
        "compact_branch": corrected_hebog_campaign_configuration(),
        "multiscale_review": base_review.model_dump(mode="json"),
    }
    observed_version = importlib.metadata.version("hebog")
    execute_external_run(
        authorized,
        finder_id="hebog",
        mode="candidate",
        runtime=ExternalRuntimeIdentity(
            name="hebog",
            version=observed_version,
            source_revision=authorized.decision.implementation_commit,
            container_image_digest=arguments.container_image_digest,
            dependency_inventory_sha256=observed_inventory,
        ),
        configuration=configuration,
        output_directory=arguments.output,
        operation=lambda staging: _run_hebog(
            authorized,
            dataset,
            arguments.base_review,
            staging,
        ),
        failure_stage="hebog-candidate-source-finding",
    )


if __name__ == "__main__":
    main()
