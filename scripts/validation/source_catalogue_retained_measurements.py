"""Read-only R6 projections of sealed native finder products."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scripts.benchmark import (
    run_phase5_compact_held_out_source_union_pybdsf as native_geometry,
)
from scripts.benchmark import (
    run_phase5_compact_held_out_source_union_pybdsf_gaussian_count_repair,
)
from scripts.validation.compact_sentinel_source_unions import (
    PyBdsfGaussianRow,
    PyBdsfSourceRow,
    SourceUnionProjection,
    derive_pybdsf_source_model_dominance,
)

from hebog.data_models.measurement_diagnostics import MeasurementDisposition
from hebog.validation.comparison import CatalogueSource
from hebog.validation.diagnostic_retention import _verify_record_digest
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
)
from hebog.validation.parent_construction_association_evaluation import (
    continuum_catalogue_objects_from_association,
    load_source_association,
)
from hebog.validation.products import (
    load_comparison_catalogue,
    load_fits_plane,
    load_pybdsf_catalogue,
    load_pybdsf_gaussian_catalogue,
)

native_pybdsf = (
    run_phase5_compact_held_out_source_union_pybdsf_gaussian_count_repair
)


@dataclass(frozen=True)
class FinderMeasurementView:
    """Worker-local arrays and native rows, independent of injected truth."""

    sources: tuple[ContinuumCatalogueObject, ...]
    union_labels: np.ndarray
    publication: np.ndarray
    stages: dict[str, np.ndarray]
    background: np.ndarray
    rms: np.ndarray
    dispositions: tuple[MeasurementDisposition, ...]
    measured_sources: tuple[CatalogueSource, ...]
    measured_components: tuple[CatalogueSource, ...]


def checked_artifact(root: Path, binding: dict[str, Any]) -> Path:
    """Reject missing, escaped, substituted or truncated retained products."""
    path = root / binding["path"]
    if (
        Path(binding["path"]).is_absolute()
        or not path.resolve().is_relative_to(root.resolve())
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != binding["byte_count"]
        or file_sha256(path) != binding["sha256"]
    ):
        raise ValueError("retained measurement artifact changed")
    return path


def read_current_capture(
    path: Path,
) -> tuple[dict[str, Any], FinderMeasurementView]:
    """Verify a durable public capture before reconstructing its projection."""
    record: dict[str, Any] = json.loads(path.read_bytes())
    _verify_record_digest(record)
    root = path.parent
    planes = {
        name: load_fits_plane(checked_artifact(root, binding))
        for name, binding in record["planes"].items()
    }
    catalogues = {
        name: load_comparison_catalogue(checked_artifact(root, binding))
        for name, binding in record["catalogues"].items()
    }
    sources = tuple(
        ContinuumCatalogueObject(
            row["identifier"],
            row["support_label"],
            (row["centre_xy"][0], row["centre_xy"][1]),
            row["integrated_flux_jy"],
        )
        for row in record["sources"]
    )
    publication = planes["publication"] > 0
    stages = {
        name.removeprefix("stage-"): values > 0
        for name, values in planes.items()
        if name.startswith("stage-")
    }
    stages["publication"] = publication
    return record, FinderMeasurementView(
        sources,
        planes["source-union"].astype(np.int64),
        publication,
        stages,
        planes["background"],
        planes["rms"],
        tuple(
            MeasurementDisposition.model_validate_json(json.dumps(row))
            for row in record["measurement_dispositions"]
        ),
        catalogues["all-sources"],
        catalogues["all-components"],
    )


def capture_science_sha256(path: Path) -> str:
    """Compare complete science, excluding paths, clocks and compression."""
    record, _ = read_current_capture(path)
    payload: dict[str, Any] = {
        name: record[name]
        for name in (
            "input_id",
            "input_sha256",
            "configuration_sha256",
            "sources",
            "components",
            "measured_sources",
            "measured_components",
            "source_association",
            "measurement_dispositions",
            "public_catalogue",
        )
    }
    planes: dict[str, Any] = {}
    for name, binding in record["planes"].items():
        values = np.asarray(
            load_fits_plane(checked_artifact(path.parent, binding)),
            dtype="<f8",
        )
        values = np.ascontiguousarray(values)
        values[np.isnan(values)] = np.nan
        planes[name] = {
            "shape": list(values.shape),
            "sha256": hashlib.sha256(values.tobytes()).hexdigest(),
        }
    return canonical_sha256({**payload, "planes": planes})


def read_pybdsf_sources(
    artifacts: dict[str, Path],
    header: fits.Header,
) -> FinderMeasurementView:
    """Preserve srl observables; derive topology only inside native islands."""
    native = load_fits_plane(artifacts["island-labels-fits"]).astype(np.int32)
    gaussians = cast(
        np.ndarray,
        fits.getdata(artifacts["gaussian-catalogue-fits"], ext=1),
    )
    projection = project_pybdsf_source_unions(
        source_table=cast(
            np.ndarray,
            fits.getdata(artifacts["source-catalogue-fits"], ext=1),
        ),
        gaussian_table=gaussians,
        native_island_labels=native,
        header=header,
    )
    sources = tuple(
        ContinuumCatalogueObject(
            row.identifier, index, row.centre_xy, row.integrated_flux_jy
        )
        for index, row in enumerate(projection.sources, start=1)
    )
    publication = load_fits_plane(artifacts["island-mask-fits"]) > 0
    # Historical native products did not retain operational background/RMS.
    # Missing instrumentation is explicitly unavailable, never zero error.
    unavailable = np.full(native.shape, np.nan, dtype=np.float64)
    return FinderMeasurementView(
        sources,
        projection.source_union_label_plane,
        publication,
        {"publication": publication, "native-islands": native > 0},
        unavailable,
        unavailable,
        (),
        load_pybdsf_catalogue(artifacts["source-catalogue-fits"]),
        _measured_gaussians(artifacts["gaussian-catalogue-fits"], gaussians),
    )


def _native_gaussian_key(row: Any) -> tuple[int, int, int, int]:
    """Match the established native catalogue reader's ordering."""
    return (
        int(row["Isl_id"]),
        int(row["Source_id"]),
        int(row["Wave_id"]),
        int(row["Gaus_id"]),
    )


def _model_suffixes(table: np.ndarray) -> tuple[str, ...]:
    """Disambiguate native numbering collisions without changing any model.

    A collision is resolvable only if its native model observables differ.
    Identical models with the same complete key remain an integrity error;
    differing uncertainties or FITS row order cannot justify duplicates.
    Hex floats preserve exact native values, independent of FITS endianness.
    """
    counts = Counter(_native_gaussian_key(row) for row in table)
    suffixes = tuple(
        "-model-"
        + canonical_sha256(
            {
                name: float(row[name]).hex()
                for name in (
                    "RA",
                    "DEC",
                    "Total_flux",
                    "Peak_flux",
                    "Maj",
                    "Min",
                    "PA",
                )
            }
        )
        if counts[_native_gaussian_key(row)] > 1
        else ""
        for row in table
    )
    identities = [
        (_native_gaussian_key(row), suffix)
        for row, suffix in zip(table, suffixes, strict=True)
    ]
    if len(set(identities)) != len(identities):
        raise ValueError("PyBDSF source/Gaussian membership is inconsistent")
    return suffixes


def _measured_gaussians(
    path: Path, table: np.ndarray
) -> tuple[CatalogueSource, ...]:
    """Keep native diagnostics intact, including both colliding model rows."""
    order = sorted(
        range(len(table)), key=lambda i: _native_gaussian_key(table[i])
    )
    ordered = table[np.asarray(order, dtype=np.intp)]
    suffixes = _model_suffixes(ordered)
    return tuple(
        replace(row, identifier=row.identifier + suffix)
        for row, suffix in zip(
            load_pybdsf_gaussian_catalogue(path), suffixes, strict=True
        )
    )


def project_pybdsf_source_unions(
    *,
    source_table: np.ndarray,
    gaussian_table: np.ndarray,
    native_island_labels: np.ndarray,
    header: fits.Header,
) -> SourceUnionProjection:
    """Preserve wave-local Gaussian identities in the native source union.

    The wave suffix preserves the old lexical order when its shorter keys
    were unique, so already evaluable model sums keep the same input order.
    Distinct models sharing a full native key receive a model fingerprint.
    Indistinguishable duplicates still fail before the topology validator.
    """
    if source_table.size == 0 and gaussian_table.size == 0:
        return derive_pybdsf_source_model_dominance(
            source_rows=(),
            gaussian_rows=(),
            native_island_labels=native_island_labels,
        )
    source_table = native_pybdsf._with_derived_gaussian_counts(
        source_table, gaussian_table
    )
    native_geometry._required_columns(
        gaussian_table,
        {
            "Gaus_id",
            "Wave_id",
            "Isl_id",
            "Source_id",
            "RA",
            "DEC",
            "Total_flux",
            "Peak_flux",
            "Maj",
            "Min",
            "PA",
        },
    )
    celestial = WCS(header, relax=True).celestial
    sources = tuple(
        PyBdsfSourceRow(
            island_id=int(row["Isl_id"]),
            source_id=int(row["Source_id"]),
            centre_xy=native_geometry._pixel_centre(row, celestial),
            integrated_flux_jy=float(row["Total_flux"]),
            gaussian_count=int(row["N_gaus"]),
        )
        for row in source_table
    )
    gaussians: list[PyBdsfGaussianRow] = []
    for row, suffix in zip(
        gaussian_table, _model_suffixes(gaussian_table), strict=True
    ):
        centre = native_geometry._pixel_centre(row, celestial)
        gaussians.append(
            PyBdsfGaussianRow(
                identifier=(
                    f"pybdsf-island-{int(row['Isl_id'])}-source-"
                    f"{int(row['Source_id'])}-gaussian-"
                    f"{int(row['Gaus_id'])}-wave-{int(row['Wave_id'])}{suffix}"
                ),
                island_id=int(row["Isl_id"]),
                source_id=int(row["Source_id"]),
                centre_xy=centre,
                integrated_flux_jy=float(row["Total_flux"]),
                peak_flux_jy_per_beam=float(row["Peak_flux"]),
                covariance_pixels_squared=native_geometry._pixel_covariance(
                    row, celestial, centre
                ),
            )
        )
    return derive_pybdsf_source_model_dominance(
        source_rows=sources,
        gaussian_rows=tuple(gaussians),
        native_island_labels=native_island_labels,
    )


def read_incumbent_sources(
    artifacts: dict[str, Path],
    header: fits.Header,
) -> FinderMeasurementView:
    """Project recorded historical associations, never current regrouping."""
    native = load_fits_plane(artifacts["segment-labels-fits"]).astype(np.int64)
    catalogue = load_comparison_catalogue(artifacts["segment-catalogue-json"])
    association = load_source_association(artifacts["source-association-json"])
    objects = continuum_catalogue_objects_from_association(
        catalogue, native, association, finder_id="hebog", header=header
    )
    labels = np.zeros_like(native)
    sources: list[ContinuumCatalogueObject] = []
    for index, row in enumerate(objects, start=1):
        support = np.isin(native, row.support_labels)
        if np.any(support & (labels > 0)):
            raise ValueError("incumbent source membership overlaps")
        labels[support] = index
        sources.append(
            ContinuumCatalogueObject(
                row.identifier, index, row.centre_xy, row.integrated_flux_jy
            )
        )
    publication = load_fits_plane(artifacts["segment-mask-fits"]) > 0
    unavailable = np.full(native.shape, np.nan, dtype=np.float64)
    return FinderMeasurementView(
        tuple(sources),
        labels,
        publication,
        {"publication": publication, "native-components": native > 0},
        unavailable,
        unavailable,
        (),
        catalogue,
        (),
    )
