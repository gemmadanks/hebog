#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Run one authorized Phase 5 realization in the isolated Aegean image."""

from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
from pathlib import Path
from typing import Literal, cast

import numpy as np
from astropy.io import fits
from astropy.table import Table

from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.contracts import PhaseFiveExternalComparisonProtocol
from hebog.validation.external_runners import (
    AuthorizedExternalRun,
    ExternalRuntimeIdentity,
    authorize_external_run,
    execute_external_run,
)
from hebog.validation.products import (
    aegean_support_label_plane,
    load_aegean_catalogue,
)

AegeanMode = Literal["operational", "controlled-background"]
_IMAGE_DIMENSIONS = 2


def _parse_args() -> argparse.Namespace:
    """Parse one checksum-bound Aegean realization request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--execution-decision", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("operational", "controlled-background"),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--container-image-digest", required=True)
    return parser.parse_args()


def _configuration(
    protocol: PhaseFiveExternalComparisonProtocol,
    authorized: AuthorizedExternalRun,
    *,
    mode: AegeanMode,
    table_path: Path,
) -> dict[str, object]:
    """Return the exact covariance-enabled blind Aegean configuration."""
    frozen = protocol.aegean_configuration
    seedclip = (
        frozen.primary_seedclip_sigma
        if mode == "operational"
        else frozen.threshold_matched_seedclip_sigma
    )
    floodclip = (
        frozen.primary_floodclip_sigma
        if mode == "operational"
        else frozen.threshold_matched_floodclip_sigma
    )
    configuration: dict[str, object] = {
        "background": None,
        "cores": frozen.cores,
        "covariance": True,
        "find": True,
        "floodclip": floodclip,
        "island": frozen.island_catalogue,
        "noise": None,
        "seedclip": seedclip,
        "table": str(table_path),
    }
    if mode == "controlled-background":
        configuration["background"] = str(authorized.artifact_path("mean"))
        configuration["noise"] = str(authorized.artifact_path("rms"))
    return configuration


def _command(
    configuration: dict[str, object],
    *,
    image_path: Path,
) -> tuple[str, ...]:
    """Translate the frozen configuration without relying on CLI defaults."""
    command = [
        "aegean",
        "--find",
        "--cores",
        str(configuration["cores"]),
        "--seedclip",
        str(configuration["seedclip"]),
        "--floodclip",
        str(configuration["floodclip"]),
        "--island",
        "--table",
        str(configuration["table"]),
    ]
    noise = configuration["noise"]
    background = configuration["background"]
    if noise is not None or background is not None:
        if noise is None or background is None:
            raise ValueError(
                "Aegean controlled maps must be supplied together"
            )
        command.extend(
            ("--noise", str(noise), "--background", str(background))
        )
    command.append(str(image_path))
    return tuple(command)


def _configuration_identity(
    configuration: dict[str, object],
) -> dict[str, object]:
    """Normalize execution paths without discarding map provenance."""
    identity = dict(configuration)
    identity["table"] = "catalogue.fits"
    if identity["background"] is not None:
        identity["background"] = "mean.fits"
        identity["noise"] = "rms.fits"
    return identity


def _write_empty_catalogues(component_path: Path, island_path: Path) -> None:
    """Represent a successful zero-source run when Aegean writes no table."""
    component_names = (
        "island",
        "source",
        "ra",
        "dec",
        "peak_flux",
        "err_peak_flux",
        "int_flux",
        "err_int_flux",
        "a",
        "err_a",
        "b",
        "err_b",
        "pa",
        "err_pa",
        "flags",
    )
    Table(
        names=component_names,
        dtype=(int, int, *([float] * 12), int),
    ).write(component_path)
    Table(
        names=(
            "island",
            "components",
            "ra",
            "dec",
            "peak_flux",
            "int_flux",
            "err_int_flux",
        ),
        dtype=(int, int, float, float, float, float, float),
    ).write(island_path)


def _run_aegean(
    authorized: AuthorizedExternalRun,
    configuration: dict[str, object],
    staging: Path,
) -> dict[str, Path]:
    """Run Aegean and retain native catalogues plus its declared proxy."""
    image_path = authorized.artifact_path("image")
    completed = subprocess.run(
        _command(configuration, image_path=image_path),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Aegean failed with exit code "
            f"{completed.returncode}: {completed.stderr.strip()}"
        )
    table_path = Path(str(configuration["table"]))
    component_path = table_path.with_name(f"{table_path.stem}_comp.fits")
    island_path = table_path.with_name(f"{table_path.stem}_isle.fits")
    if not component_path.exists() and not island_path.exists():
        _write_empty_catalogues(component_path, island_path)
    elif not component_path.exists() or not island_path.exists():
        raise RuntimeError("Aegean wrote only one of its paired catalogues")
    sources = load_aegean_catalogue(component_path, island_path)
    input_data = np.asarray(fits.getdata(image_path)).squeeze()
    if input_data.ndim != _IMAGE_DIMENSIONS:
        raise ValueError("Aegean input must contain one image plane")
    input_header = cast(fits.Header, fits.getheader(image_path))
    labels, _ = aegean_support_label_plane(
        sources,
        input_header,
        shape_yx=(int(input_data.shape[0]), int(input_data.shape[1])),
    )
    support_path = staging / "support_proxy_labels.fits"
    fits.PrimaryHDU(
        data=labels[np.newaxis, np.newaxis, :, :],
        header=input_header,
    ).writeto(support_path)
    return {
        "component-catalogue-fits": component_path,
        "island-catalogue-fits": island_path,
        "support-proxy-labels-fits": support_path,
    }


def main() -> None:
    """Authorize and execute one immutable Aegean comparison leg."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite external result: {arguments.output}"
        )
    mode: AegeanMode = arguments.mode
    authorized = authorize_external_run(
        protocol_path=arguments.protocol,
        execution_decision_path=arguments.execution_decision,
        input_bundle_path=arguments.input,
        runner_path=Path(__file__),
        finder_id="aegean",
    )
    reference = next(
        item
        for item in authorized.protocol.references
        if item.finder_id == "aegean"
    )
    observed_version = importlib.metadata.version("AegeanTools")
    if observed_version != reference.version:
        raise RuntimeError(
            "installed AegeanTools version does not match frozen reference: "
            f"expected {reference.version}, observed {observed_version}"
        )
    if arguments.container_image_digest != reference.container_image_digest:
        raise ValueError(
            "Aegean container digest differs from frozen reference"
        )
    observed_inventory = dependency_inventory_sha256()
    if observed_inventory != reference.dependency_inventory_sha256:
        raise RuntimeError(
            "Aegean dependency inventory differs from reference"
        )

    def operation(staging: Path) -> dict[str, Path]:
        configuration = _configuration(
            authorized.protocol,
            authorized,
            mode=mode,
            table_path=staging / "catalogue.fits",
        )
        return _run_aegean(authorized, configuration, staging)

    execution_configuration = _configuration(
        authorized.protocol,
        authorized,
        mode=mode,
        table_path=Path("catalogue.fits"),
    )
    execute_external_run(
        authorized,
        finder_id="aegean",
        mode=mode,
        runtime=ExternalRuntimeIdentity(
            name="aegeantools",
            version=observed_version,
            source_revision=reference.source_revision,
            artifact_sha256=reference.artifact_sha256,
            container_image_digest=arguments.container_image_digest,
            dependency_inventory_sha256=observed_inventory,
        ),
        configuration=_configuration_identity(execution_configuration),
        output_directory=arguments.output,
        operation=operation,
        failure_stage="aegean-source-finding",
    )


if __name__ == "__main__":
    main()
