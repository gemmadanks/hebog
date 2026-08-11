#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Run one authorized Phase 5 realization in an isolated PyBDSF image."""

from __future__ import annotations

import argparse
import importlib.metadata
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
from astropy.io import fits

from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.contracts import (
    PhaseFiveExternalComparisonProtocol,
    PhaseFiveExternalReference,
)
from hebog.validation.external_runners import (
    AuthorizedExternalRun,
    ExternalRuntimeIdentity,
    authorize_external_run,
    execute_external_run,
)
from hebog.validation.products import (
    load_mask_plane,
    load_pybdsf_catalogue,
    load_pybdsf_gaussian_catalogue,
)

PybdsfFinderId = Literal["released-pybdsf", "pinned-pybdsf-master"]
PybdsfMode = Literal["operational", "controlled-background"]


def _parse_args() -> argparse.Namespace:
    """Parse one checksum-bound PyBDSF realization request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--execution-decision", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--finder-id",
        required=True,
        choices=("released-pybdsf", "pinned-pybdsf-master"),
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("operational", "controlled-background"),
    )
    parser.add_argument("--ncores", required=True, type=int)
    parser.add_argument("--container-image-digest", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _configuration(
    protocol: PhaseFiveExternalComparisonProtocol,
    authorized: AuthorizedExternalRun,
    *,
    mode: PybdsfMode,
    ncores: int,
) -> dict[str, object]:
    """Map every frozen PyBDSF setting to its exact native option."""
    if ncores < 1:
        raise ValueError("PyBDSF ncores must be positive")
    frozen = protocol.pybdsf_configuration
    configuration: dict[str, object] = {
        "adaptive_rms_box": frozen.adaptive_rms_box,
        "adaptive_thresh": frozen.adaptive_threshold,
        "atrous_bdsm_do": frozen.atrous_bdsm_do,
        "atrous_do": frozen.atrous_do,
        "atrous_jmax": frozen.atrous_jmax,
        "atrous_lpf": frozen.atrous_lpf,
        "atrous_orig_isl": frozen.atrous_orig_isl,
        "atrous_sum": frozen.atrous_sum,
        "mean_map": frozen.mean_map,
        "ncores": ncores,
        "quiet": True,
        "rms_box": frozen.rms_box,
        "rms_box_bright": frozen.rms_box_bright,
        "rms_map": frozen.rms_map,
        "thresh": frozen.threshold_type,
        "thresh_isl": frozen.threshold_island_sigma,
        "thresh_pix": frozen.threshold_pixel_sigma,
    }
    if mode == "controlled-background":
        minimum_size = min(authorized.input_bundle.shape_yx)
        if frozen.rms_box[0] > minimum_size / 4.0:
            raise ValueError(
                "PyBDSF ignores supplied RMS/mean maps when rms_box exceeds "
                "one quarter of the image; controlled diagnostic unavailable"
            )
        configuration["rmsmean_map_filename"] = (
            str(authorized.artifact_path("mean")),
            str(authorized.artifact_path("rms")),
        )
    return configuration


def _reference(
    protocol: PhaseFiveExternalComparisonProtocol,
    finder_id: PybdsfFinderId,
) -> PhaseFiveExternalReference:
    """Resolve the exact frozen identity for one isolated reference."""
    return next(
        item for item in protocol.references if item.finder_id == finder_id
    )


def _configuration_identity(
    configuration: dict[str, object],
) -> dict[str, object]:
    """Remove host paths while retaining the controlled-map semantics."""
    identity = dict(configuration)
    if "rmsmean_map_filename" in identity:
        identity["rmsmean_map_filename"] = ("mean.fits", "rms.fits")
    return identity


def _run_pybdsf(
    bdsf_module: Any,
    authorized: AuthorizedExternalRun,
    configuration: dict[str, object],
    staging: Path,
) -> dict[str, Path]:
    """Run PyBDSF and retain native catalogue, mask, and island labels."""
    image_path = authorized.artifact_path("image")
    catalogue_path = staging / "source_catalog.fits"
    gaussian_path = staging / "gaussian_catalog.fits"
    mask_path = staging / "island_mask.fits"
    label_path = staging / "island_labels.fits"
    processed = bdsf_module.process_image(str(image_path), **configuration)
    processed.write_catalog(
        outfile=str(catalogue_path),
        format="fits",
        catalog_type="srl",
        clobber=True,
        force_output=True,
    )
    processed.write_catalog(
        outfile=str(gaussian_path),
        format="fits",
        catalog_type="gaul",
        clobber=True,
        force_output=True,
    )
    if not processed.export_image(
        outfile=str(mask_path),
        clobber=True,
        img_type="island_mask",
    ):
        raise RuntimeError("PyBDSF did not export its island mask")
    input_header = cast(fits.Header, fits.getheader(image_path))
    labels = np.asarray(processed.pyrank + 1, dtype=np.int32)
    fits.PrimaryHDU(
        data=labels[np.newaxis, np.newaxis, :, :],
        header=input_header,
    ).writeto(label_path)
    catalogue = load_pybdsf_catalogue(catalogue_path)
    gaussian_catalogue = load_pybdsf_gaussian_catalogue(gaussian_path)
    mask = load_mask_plane(mask_path)
    if np.any(mask != (labels > 0)):
        raise ValueError("PyBDSF island mask and labels disagree")
    island_ids = {
        int(source.island_identifier)
        for source in catalogue
        if source.island_identifier is not None
    }
    if island_ids != {int(item) - 1 for item in np.unique(labels) if item > 0}:
        raise ValueError("PyBDSF catalogue and island labels disagree")
    if {
        int(source.island_identifier)
        for source in gaussian_catalogue
        if source.island_identifier is not None
    }.difference(island_ids):
        raise ValueError("PyBDSF Gaussian and source catalogues disagree")
    return {
        "gaussian-catalogue-fits": gaussian_path,
        "island-labels-fits": label_path,
        "island-mask-fits": mask_path,
        "source-catalogue-fits": catalogue_path,
    }


def main() -> None:
    """Authorize and execute one immutable PyBDSF comparison leg."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite external result: {arguments.output}"
        )
    finder_id: PybdsfFinderId = arguments.finder_id
    mode: PybdsfMode = arguments.mode
    authorized = authorize_external_run(
        protocol_path=arguments.protocol,
        execution_decision_path=arguments.execution_decision,
        input_bundle_path=arguments.input,
        runner_path=Path(__file__),
        finder_id=finder_id,
    )
    if arguments.ncores != authorized.decision.pybdsf_ncores:
        raise ValueError("PyBDSF ncores differs from execution decision")
    reference = _reference(authorized.protocol, finder_id)
    observed_version = importlib.metadata.version("bdsf")
    if observed_version != reference.version:
        raise RuntimeError(
            "installed PyBDSF version does not match frozen reference: "
            f"expected {reference.version}, observed {observed_version}"
        )
    if arguments.container_image_digest != reference.container_image_digest:
        raise ValueError(
            "PyBDSF container digest differs from frozen reference"
        )
    observed_inventory = dependency_inventory_sha256()
    if observed_inventory != reference.dependency_inventory_sha256:
        raise RuntimeError(
            "PyBDSF dependency inventory differs from reference"
        )
    configuration = _configuration(
        authorized.protocol,
        authorized,
        mode=mode,
        ncores=arguments.ncores,
    )
    import bdsf  # type: ignore[import-not-found]  # noqa: PLC0415

    execute_external_run(
        authorized,
        finder_id=finder_id,
        mode=mode,
        runtime=ExternalRuntimeIdentity(
            name="pybdsf",
            version=observed_version,
            source_revision=reference.source_revision,
            artifact_sha256=reference.artifact_sha256,
            container_image_digest=arguments.container_image_digest,
            dependency_inventory_sha256=observed_inventory,
        ),
        configuration=_configuration_identity(configuration),
        output_directory=arguments.output,
        operation=lambda staging: _run_pybdsf(
            bdsf,
            authorized,
            configuration,
            staging,
        ),
        failure_stage="pybdsf-source-finding",
    )


if __name__ == "__main__":
    main()
