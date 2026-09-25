#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
"""Run current Hebog on one notebook comparison input.

``refresh_public_notebook_hebog.py`` loads this runner for every case. The
result records the configuration and scientific-composition identities of the
checkout that produced it; they are provenance, not qualification.
"""

from __future__ import annotations

import json
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
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.products import write_comparison_catalogue
from hebog.validation.public_measurement_projection import (
    project_public_measurements,
)

_CONFIG = SourceFinderConfig(5.0, 3.0, 7, profile="continuum")


def hebog_configuration_sha256() -> str:
    """Return the canonical digest of the notebook Hebog configuration."""
    return canonical_sha256(asdict(_CONFIG))


def _write_once_json(path: Path, value: object) -> None:
    """Write one finite canonical JSON record without overwriting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(
            (
                json.dumps(value, allow_nan=False, indent=2, sort_keys=True)
                + "\n"
            ).encode()
        )


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


def _build_bundle(
    *,
    input_path: Path,
    output: Path,
    work_directory: Path,
    case_id: str,
    core: ImageBounds | None,
) -> dict[str, object]:
    """Build one complete bundle inside an unpublished private directory."""
    composition_sha256 = public_api._scientific_composition_sha256()
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
        config=_CONFIG,
        header=header,
    )
    products = scientific.terminal
    published_catalogue, public_mask = public_api._public_catalogue(
        scientific,
        metadata,
        run_id=case_id,
        profile=_CONFIG.profile,
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
    _write_once_json(association_path, asdict(association))
    for path, values in (
        (labels_path, np.asarray(publication_labels[slices], dtype=np.int32)),
        (
            component_labels_path,
            np.asarray(component_labels[slices], dtype=np.int32),
        ),
        (mask_path, np.asarray(publication_mask[slices], dtype=np.uint8)),
        (
            background_path,
            np.asarray(
                scientific.background_rms_source.read_completed_window(
                    "background", selected_core
                ),
                dtype=np.float64,
            ),
        ),
        (
            rms_path,
            np.asarray(
                scientific.background_rms_source.read_completed_window(
                    "rms", selected_core
                ),
                dtype=np.float64,
            ),
        ),
    ):
        _write_plane(path, values, core_header)
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
        "result_id": f"notebook-hebog-{case_id}",
        "status": "success",
        "case_id": case_id,
        "configuration_sha256": hebog_configuration_sha256(),
        "input_sha256": file_sha256(input_path),
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
        "scientific_composition_sha256": composition_sha256,
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
                "sha256": file_sha256(path),
                "byte_size": path.stat().st_size,
            }
            for role, path in sorted(artifacts.items())
        },
    }
    if public_api._scientific_composition_sha256() != composition_sha256:
        raise ValueError("Hebog science changed during bundle construction")
    result = json.loads(json.dumps(result, allow_nan=False))
    _write_once_json(output / "result.json", result)
    return result


def run_notebook_hebog(
    *,
    input_path: Path,
    output: Path,
    case_id: str,
    core: ImageBounds | None,
) -> dict[str, object]:
    """Produce and atomically publish one restartable result bundle."""
    if output.exists():
        raise FileExistsError(
            f"Hebog notebook output already exists: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{output.name}.",
        dir=output.parent,
    ) as temporary_directory:
        temporary = Path(temporary_directory)
        unpublished = temporary / "bundle"
        result = _build_bundle(
            input_path=input_path,
            output=unpublished,
            work_directory=temporary / "background-work",
            case_id=case_id,
            core=core,
        )
        if output.exists():
            raise FileExistsError(
                f"Hebog notebook output appeared during execution: {output}"
            )
        unpublished.rename(output)
    return result
