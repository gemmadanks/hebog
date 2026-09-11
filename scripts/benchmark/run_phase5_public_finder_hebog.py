#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
"""Run one authorized Hebog public-comparison case."""

from __future__ import annotations

import argparse
import json
import re
import runpy
import warnings
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, cast

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from hebog import public_api
from hebog.config import SourceFinderConfig
from hebog.data_models import ImageBounds, SourceFinderRequest
from hebog.data_models.measurement_diagnostics import MeasurementDisposition
from hebog.data_models.source_association import SourceAssociationResult
from hebog.executors import SerialExecutor
from hebog.io import FitsImageSource
from hebog.validation.external_runners import (
    canonical_sha256,
    source_tree_sha256,
)
from hebog.validation.products import (
    write_comparison_catalogue,
)
from hebog.validation.public_measurement_projection import (
    project_public_measurements,
)

_ROOT = Path(__file__).parents[2]
_PROTOCOL = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_public_finder_protocol.py")
)
_PUBLIC_IDENTITY = (
    _ROOT
    / "config/contracts"
    / "phase-5-zero-noise-adaptive-repair-identity-review.json"
)
_PUBLIC_CONFIG = SourceFinderConfig(5.0, 3.0, 7, profile="continuum")


def public_hebog_configuration_sha256() -> str:
    """Verify a newly frozen repair identity; old passes do not transfer."""
    value: object = json.loads(_PUBLIC_IDENTITY.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("final public-interface identity is malformed")
    record = cast(dict[str, object], value)
    candidate = record.get("algorithm_candidate")
    if not isinstance(candidate, dict) or not re.fullmatch(
        r"[0-9a-f]{40}", str(candidate.get("revision", ""))
    ):
        raise ValueError("public-interface candidate identity is malformed")
    configuration = canonical_sha256(asdict(_PUBLIC_CONFIG))
    expected = {
        "configuration_sha256": configuration,
        "revision": candidate["revision"],
        "source_tree_sha256": source_tree_sha256(_ROOT),
    }
    if (
        candidate != expected
        or record.get("status") != "frozen-non-executable"
        or record.get("scientific_composition_sha256")
        != public_api._scientific_composition_sha256()
        or record.get("scientific_composition") != public_api._COMPOSITION_NAME
    ):
        raise ValueError("final public-interface identity changed")
    return configuration


def _core_catalogue(
    catalogue: tuple[Any, ...],
    header: fits.Header,
    core: ImageBounds,
) -> tuple[Any, ...]:
    """Admit candidates whose fitted centroid lies in the half-open core."""
    celestial = WCS(header, relax=True).celestial
    retained: list[Any] = []
    for source in catalogue:
        x_pixel, y_pixel = cast(
            tuple[float, float],
            celestial.world_to_pixel(
                SkyCoord(
                    source.right_ascension_degrees,
                    source.declination_degrees,
                    unit="deg",
                    frame="icrs",
                )
            ),
        )
        if (
            core.x_start <= float(x_pixel) < core.x_stop
            and core.y_start <= float(y_pixel) < core.y_stop
        ):
            retained.append(source)
    return tuple(retained)


def _core_header(header: fits.Header, core: ImageBounds) -> fits.Header:
    """Shift the haloed input WCS onto the selected output core."""
    shifted = header.copy()
    shifted["CRPIX1"] = float(cast(Any, shifted["CRPIX1"])) - core.x_start
    shifted["CRPIX2"] = float(cast(Any, shifted["CRPIX2"])) - core.y_start
    return shifted


def _write_plane(
    path: Path,
    values: np.ndarray,
    header: fits.Header,
) -> None:
    """Write one core plane with the input's singleton leading axes."""
    fits.PrimaryHDU(
        data=values[np.newaxis, np.newaxis, :, :],
        header=header,
    ).writeto(path)


def _warn_numerical_fit_failures(
    case_id: str, dispositions: tuple[MeasurementDisposition, ...]
) -> None:
    """Report incomplete Gaussian measurements once per diagnostic image."""
    count = sum(
        row.object_kind == "component"
        and row.reason == "fit-linear-algebra-failure"
        for row in dispositions
    )
    if count:
        warnings.warn(
            f"{case_id}: {count} Gaussian components unavailable "
            "after numerical fit failure; see measurement_dispositions",
            RuntimeWarning,
            stacklevel=2,
        )


def _build_public_bundle(  # noqa: PLR0913
    *,
    input_path: Path,
    output: Path,
    work_directory: Path,
    case_id: str,
    core: ImageBounds | None,
    configuration_sha256: str,
) -> dict[str, object]:
    """Build one complete bundle inside an unpublished private directory."""
    observed_configuration = public_hebog_configuration_sha256()
    if observed_configuration != configuration_sha256:
        raise ValueError("qualified Hebog configuration checksum changed")
    source = FitsImageSource(input_path)
    metadata = source.metadata()
    output.mkdir(parents=True)
    started = monotonic()
    header = cast(fits.Header, fits.getheader(input_path))
    scientific = public_api._analyse_image(
        SourceFinderRequest(input_path, output, case_id),
        source,
        metadata,
        SerialExecutor(),
        work_directory,
        config=_PUBLIC_CONFIG,
        header=header,
    )
    background, rms = scientific.background, scientific.rms
    products = scientific.terminal
    published_catalogue, public_mask = public_api._public_catalogue(
        scientific,
        metadata,
        run_id=case_id,
        profile=_PUBLIC_CONFIG.profile,
    )
    projection = project_public_measurements(
        products, published_catalogue, public_mask, header
    )
    _warn_numerical_fit_failures(case_id, projection.dispositions)
    published_source_ids = {
        row.source_id for row in published_catalogue.sources
    }
    published_component_ids = {
        row.gaussian_component_id
        for row in published_catalogue.gaussian_components
    }
    association = (
        products.source_association
        if products is not None
        else SourceAssociationResult((), (), (), ())
    )
    empty_labels = np.zeros(metadata.shape_yx, dtype=np.int32)
    publication_labels = (
        products.detection.component_labels
        if products is not None
        else empty_labels
    )
    component_labels = (
        products.measurement_component_labels
        if products is not None
        else empty_labels
    )
    publication_mask = (
        products.detection.retained_mask
        if products is not None
        else np.zeros(metadata.shape_yx, dtype=np.bool_)
    )
    selected_core = core or ImageBounds(
        y_start=0,
        y_stop=metadata.shape_yx[0],
        x_start=0,
        x_stop=metadata.shape_yx[1],
    )
    selected_core.require_inside(metadata.shape_yx)
    slices = (
        slice(selected_core.y_start, selected_core.y_stop),
        slice(selected_core.x_start, selected_core.x_stop),
    )
    core_header = _core_header(header, selected_core)
    source_catalogue_path = output / "source_catalogue.json"
    component_catalogue_path = output / "component_catalogue.json"
    association_path = output / "source_association.json"
    labels_path = output / "segment_labels.fits"
    component_labels_path = output / "component_labels.fits"
    mask_path = output / "segment_mask.fits"
    background_path = output / "background.fits"
    rms_path = output / "rms.fits"
    core_sources = _core_catalogue(
        tuple(
            row
            for row in products.catalogue
            if row.identifier in published_source_ids
        )
        if products is not None
        else (),
        header,
        selected_core,
    )
    core_components = _core_catalogue(
        tuple(
            row
            for row in products.component_catalogue
            if row.identifier in published_component_ids
        )
        if products is not None
        else (),
        header,
        selected_core,
    )
    write_comparison_catalogue(source_catalogue_path, core_sources)
    write_comparison_catalogue(component_catalogue_path, core_components)
    _PROTOCOL["write_once_json"](
        association_path,
        asdict(association),
    )
    _write_plane(
        labels_path,
        np.asarray(publication_labels[slices], dtype=np.int32),
        core_header,
    )
    _write_plane(
        component_labels_path,
        np.asarray(component_labels[slices], dtype=np.int32),
        core_header,
    )
    _write_plane(
        mask_path,
        np.asarray(publication_mask[slices], dtype=np.uint8),
        core_header,
    )
    _write_plane(
        background_path,
        np.asarray(background[slices], dtype=np.float64),
        core_header,
    )
    _write_plane(
        rms_path,
        np.asarray(rms[slices], dtype=np.float64),
        core_header,
    )
    artifacts = {
        "background-fits": background_path,
        "comparison-catalogue-json": component_catalogue_path,
        "component-labels-fits": component_labels_path,
        "rms-fits": rms_path,
        "source-catalogue-json": source_catalogue_path,
        "component-catalogue-json": component_catalogue_path,
        "source-association-json": association_path,
        "segment-labels-fits": labels_path,
        "segment-mask-fits": mask_path,
    }
    result: dict[str, object] = {
        "schema_version": 2,
        "result_id": f"phase-5-public-finder-{case_id}",
        "status": "success",
        "case_id": case_id,
        "configuration_sha256": observed_configuration,
        "input_sha256": _PROTOCOL["file_sha256"](input_path),
        "source_count": len(core_sources),
        "component_count": len(core_components),
        "association_edge_count": len(association.edges),
        "deblended_parent_count": (
            products.deblended_parent_count if products is not None else 0
        ),
        "deferred_deblend_parent_count": (
            products.deferred_deblend_parent_count
            if products is not None
            else 0
        ),
        "scientific_composition": public_api._COMPOSITION_NAME,
        "scientific_composition_sha256": (
            public_api._scientific_composition_sha256()
        ),
        "measurement_dispositions": [
            row.model_dump(mode="json") for row in projection.dispositions
        ],
        "measurement_diagnostic_domain": "full-input-before-core-crop",
        "all_measured_source_records": [
            asdict(row) for row in projection.measured_sources
        ],
        "all_measured_component_records": [
            asdict(row) for row in projection.measured_components
        ],
        "catalogue_semantics": {
            "coordinate_frame": "icrs",
            "comparison_rows": "gaussian-components",
            "source_rows": "associated-sources",
            "support_rows": "connected-islands",
        },
        "core_bounds_yx_half_open": [
            selected_core.y_start,
            selected_core.y_stop,
            selected_core.x_start,
            selected_core.x_stop,
        ],
        "elapsed_seconds": monotonic() - started,
        "artifacts": {
            role: {
                "path": path.name,
                "sha256": _PROTOCOL["file_sha256"](path),
                "byte_size": path.stat().st_size,
            }
            for role, path in sorted(artifacts.items())
        },
    }
    if public_hebog_configuration_sha256() != observed_configuration:
        raise ValueError("public science changed during bundle construction")
    result = json.loads(json.dumps(result, allow_nan=False))
    _PROTOCOL["write_once_json"](output / "result.json", result)
    return result


def run_public_hebog(
    *,
    input_path: Path,
    output: Path,
    case_id: str,
    core: ImageBounds | None,
    configuration_sha256: str,
) -> dict[str, object]:
    """Produce and atomically publish one restartable public result bundle."""
    if output.exists():
        raise FileExistsError(f"public finder output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{output.name}.",
        dir=output.parent,
    ) as temporary_directory:
        temporary = Path(temporary_directory)
        unpublished = temporary / "bundle"
        result = _build_public_bundle(
            input_path=input_path,
            output=unpublished,
            work_directory=temporary / "background-work",
            case_id=case_id,
            core=core,
            configuration_sha256=configuration_sha256,
        )
        if output.exists():
            raise FileExistsError(
                f"public finder output appeared during execution: {output}"
            )
        unpublished.rename(output)
    return result


def _parse_core(value: str | None) -> ImageBounds | None:
    """Parse one optional local ``y0,y1,x0,x1`` core."""
    if value is None:
        return None
    try:
        y_start, y_stop, x_start, x_stop = (
            int(item) for item in value.split(",")
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "core bounds must be y0,y1,x0,x1"
        ) from error
    return ImageBounds(y_start, y_stop, x_start, x_stop)


def _parse_args() -> argparse.Namespace:
    """Parse one authorized public Hebog invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--core")
    return parser.parse_args()


def _validate_invocation(
    *,
    protocol: dict[str, Any],
    input_path: Path,
    output: Path,
    case_id: str,
    core: ImageBounds | None,
) -> None:
    """Bind the internal runner to one reviewed campaign case and mount."""
    sdc1_cases = {
        f"sdc1-{item['stratum']}-{item['tile_id']}": item
        for item in protocol["sdc1"]["strata"]
    }
    hydra_cases = {
        item["case_id"]: item for item in protocol["hydra"]["cases"]
    }
    if case_id not in sdc1_cases and case_id not in hydra_cases:
        raise ValueError("public finder case identity changed")
    expected_output = Path("/campaign/results") / case_id
    if output != expected_output:
        raise ValueError("public finder case output path changed")
    if case_id in sdc1_cases:
        halo = int(protocol["sdc1"]["halo_pixels_yx"][0])
        x_start, x_stop, y_start, y_stop = sdc1_cases[case_id][
            "bounds_xy_half_open"
        ]
        expected_input = Path("/campaign/inputs") / case_id / "input.fits"
        expected_core = ImageBounds(
            y_start=halo,
            y_stop=halo + y_stop - y_start,
            x_start=halo,
            x_stop=halo + x_stop - x_start,
        )
        if input_path != expected_input or core != expected_core:
            raise ValueError("public SDC1 invocation changed")
        return
    acquisition = _PROTOCOL["json_object"](
        _ROOT / "benchmark-results/phase-5/public-comparison-acquisition/"
        "acquisition.json"
    )
    filenames = {
        item["identifier"]: item["filename"]
        for item in acquisition["artifacts"]
    }
    expected_input = (
        Path("/repository/benchmark-results/phase-5/")
        / "public-comparison-acquisition/raw"
        / filenames[hydra_cases[case_id]["source_identifier"]]
    )
    if input_path != expected_input or core is not None:
        raise ValueError("public Hydra invocation changed")


def main() -> None:
    """Reject pending authority before reading one public image."""
    arguments = _parse_args()
    decision = _PROTOCOL["load_public_finder_execution_decision"](
        arguments.authorization
    )
    if not decision["execution_authorized"]:
        raise ValueError("public finder execution is not authorized")
    protocol = _PROTOCOL["load_public_finder_protocol"](
        _ROOT / cast(str, decision["protocol"]["path"])
    )
    core = _parse_core(arguments.core)
    _validate_invocation(
        protocol=protocol,
        input_path=arguments.input,
        output=arguments.output,
        case_id=arguments.case_id,
        core=core,
    )
    run_public_hebog(
        input_path=arguments.input,
        output=arguments.output,
        case_id=arguments.case_id,
        core=core,
        configuration_sha256=protocol["candidate"]["configuration_sha256"],
    )


if __name__ == "__main__":
    main()
