# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Prospective continuum compiler kernels for the successor comparison.

The terminal Step 2C-P compiler is immutable evidence.  This module defines
the independently tested scientific interpretation for its successor without
importing or mutating that closed program.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from math import hypot, isfinite
from typing import Literal

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS

from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_comparison import (
    AssociationObject,
    EligibleAssociation,
    match_truth_to_finder,
)

_IMAGE_DIMENSIONS = 2
MetricValue = float | tuple[float, ...]
ContinuumFinderId = Literal[
    "hebog",
    "released-pybdsf",
    "pinned-pybdsf-master",
]
_CONTINUUM_FINDER_IDS = frozenset(
    {"hebog", "released-pybdsf", "pinned-pybdsf-master"}
)
_METRIC_FAMILIES = (
    "completeness",
    "reliability",
    "integrated-flux-median",
    "integrated-flux-p95",
    "absolute-mean-offset-x",
    "absolute-mean-offset-y",
    "position-median",
    "position-p95",
    "duplicate-fraction",
    "mask-precision",
    "mask-recall",
    "mask-iou",
    "split-fraction",
    "merge-fraction",
)


def _validate_object(
    identifier: str,
    support_label: int,
    centre_xy: tuple[float, float],
    integrated_flux_jy: float | None,
) -> None:
    """Validate common immutable compiler-object fields."""
    if not identifier:
        raise ValueError("continuum object identifier must not be empty")
    if support_label <= 0:
        raise ValueError("continuum support label must be positive")
    if not all(isfinite(value) for value in centre_xy):
        raise ValueError("continuum object centre must be finite")
    if integrated_flux_jy is not None and (
        not isfinite(integrated_flux_jy) or integrated_flux_jy <= 0.0
    ):
        raise ValueError("continuum object flux must be finite and positive")


@dataclass(frozen=True, slots=True)
class ContinuumTruthObject:
    """One prospectively declared injected continuum truth group."""

    identifier: str
    support_label: int
    centre_xy: tuple[float, float]
    integrated_flux_jy: float
    catalogue_role: Literal["astronomical-source", "artifact"]
    strata: tuple[str, ...]

    def __post_init__(self) -> None:
        """Require a measurable, canonically stratified truth object."""
        _validate_object(
            self.identifier,
            self.support_label,
            self.centre_xy,
            self.integrated_flux_jy,
        )
        if self.catalogue_role not in {
            "astronomical-source",
            "artifact",
        }:
            raise ValueError("continuum truth catalogue role is unsupported")
        if self.strata != tuple(sorted(set(self.strata))):
            raise ValueError("continuum truth strata must be canonical")


@dataclass(frozen=True, slots=True)
class ContinuumCatalogueObject:
    """One measurable finder catalogue row and its native support label."""

    identifier: str
    support_label: int
    centre_xy: tuple[float, float]
    integrated_flux_jy: float

    def __post_init__(self) -> None:
        """Require a finite positive catalogue measurement."""
        _validate_object(
            self.identifier,
            self.support_label,
            self.centre_xy,
            self.integrated_flux_jy,
        )


@dataclass(frozen=True, slots=True)
class ContinuumSupportObject:
    """One native positive support label, whether fitted or fitless."""

    identifier: str
    support_label: int
    centre_xy: tuple[float, float]

    def __post_init__(self) -> None:
        """Require a finite topology descriptor without source photometry."""
        _validate_object(
            self.identifier,
            self.support_label,
            self.centre_xy,
            None,
        )


@dataclass(frozen=True, slots=True)
class _ContinuumAssociations:
    """Reusable catalogue and native-support association summaries."""

    primary: dict[str, str]
    candidate_by_id: dict[str, ContinuumCatalogueObject]
    catalogue_truth_degrees: Counter[str]
    support_truth_degrees: Counter[str]
    support_candidate_degrees: Counter[str]
    support_edges: tuple[EligibleAssociation, ...]


@dataclass(frozen=True, slots=True)
class _ConditionalMeasurements:
    """Values defined only for primary astronomical catalogue matches."""

    flux_errors: tuple[float, ...]
    offsets_x: tuple[float, ...]
    offsets_y: tuple[float, ...]
    radial_offsets: tuple[float, ...]


def _label_plane(
    values: npt.ArrayLike,
    *,
    name: str,
) -> npt.NDArray[np.int64]:
    """Require one non-negative two-dimensional integer label plane."""
    labels = np.asarray(values)
    if labels.ndim != _IMAGE_DIMENSIONS or not np.issubdtype(
        labels.dtype,
        np.integer,
    ):
        raise ValueError(f"{name} must be a two-dimensional integer array")
    if np.any(labels < 0):
        raise ValueError(f"{name} must contain non-negative labels")
    return np.asarray(labels, dtype=np.int64)


def native_support_objects(
    label_plane: npt.ArrayLike,
) -> tuple[ContinuumSupportObject, ...]:
    """Return one topology object for every positive native label."""
    labels = _label_plane(label_plane, name="candidate label plane")
    output: list[ContinuumSupportObject] = []
    for label in sorted(int(item) for item in np.unique(labels) if item > 0):
        y_pixels, x_pixels = np.nonzero(labels == label)
        output.append(
            ContinuumSupportObject(
                identifier=f"support-{label}",
                support_label=label,
                centre_xy=(
                    float(np.mean(x_pixels)),
                    float(np.mean(y_pixels)),
                ),
            )
        )
    return tuple(output)


def _topology_support_objects(
    native_supports: tuple[ContinuumSupportObject, ...],
    catalogue: tuple[ContinuumCatalogueObject, ...],
) -> tuple[ContinuumSupportObject, ...]:
    """Preserve catalogue centres and fill only missing native supports."""
    rows_by_label: dict[int, list[ContinuumCatalogueObject]] = {}
    for row in catalogue:
        rows_by_label.setdefault(row.support_label, []).append(row)
    output: list[ContinuumSupportObject] = []
    for support in native_supports:
        rows = rows_by_label.get(support.support_label, [])
        centre_xy = (
            (
                float(np.mean([item.centre_xy[0] for item in rows])),
                float(np.mean([item.centre_xy[1] for item in rows])),
            )
            if rows
            else support.centre_xy
        )
        output.append(
            ContinuumSupportObject(
                identifier=support.identifier,
                support_label=support.support_label,
                centre_xy=centre_xy,
            )
        )
    return tuple(output)


def _catalogue_support_label(
    source: CatalogueSource,
    finder_id: ContinuumFinderId,
) -> int:
    """Map a measurable row to its exact native positive support label."""
    identifier = source.island_identifier
    if identifier is None:
        raise ValueError("continuum catalogue row lacks an island identity")
    if finder_id == "hebog":
        prefix = "hebog-segment-"
        if not identifier.startswith(prefix):
            raise ValueError("Hebog segment island identity is malformed")
        suffix = identifier[len(prefix) :]
        if not suffix.isdecimal():
            raise ValueError("Hebog segment island identity is malformed")
        return int(suffix)
    try:
        island_identifier = int(identifier)
    except ValueError:
        raise ValueError("PyBDSF island identity is malformed") from None
    if str(island_identifier) != identifier or island_identifier < 0:
        raise ValueError("PyBDSF island identity is malformed")
    return island_identifier + 1


def continuum_catalogue_objects(
    catalogue: Sequence[CatalogueSource],
    label_plane: npt.ArrayLike,
    *,
    finder_id: ContinuumFinderId,
    header: fits.Header,
) -> tuple[ContinuumCatalogueObject, ...]:
    """Translate measurable rows while permitting native fitless supports."""
    if finder_id not in _CONTINUUM_FINDER_IDS:
        raise ValueError("continuum finder identity is unsupported")
    native_labels = {
        item.support_label for item in native_support_objects(label_plane)
    }
    celestial = WCS(header, relax=True).celestial
    output: list[ContinuumCatalogueObject] = []
    for source in catalogue:
        label = _catalogue_support_label(source, finder_id)
        if label not in native_labels:
            raise ValueError("continuum catalogue support label is absent")
        centre = celestial.all_world2pix(
            [[source.right_ascension_degrees, source.declination_degrees]],
            0,
        )[0]
        integrated_flux = (
            source.association_integrated_flux_jy
            if source.association_integrated_flux_jy is not None
            else source.integrated_flux_jy
        )
        output.append(
            ContinuumCatalogueObject(
                identifier=source.identifier,
                support_label=label,
                centre_xy=(float(centre[0]), float(centre[1])),
                integrated_flux_jy=integrated_flux,
            )
        )
    return tuple(output)


def _association_object(
    item: ContinuumTruthObject
    | ContinuumCatalogueObject
    | ContinuumSupportObject,
) -> AssociationObject:
    """Translate one successor compiler record to the matcher boundary."""
    return AssociationObject(
        identifier=item.identifier,
        object_class="extended",
        centre_x_pixel=item.centre_xy[0],
        centre_y_pixel=item.centre_xy[1],
        support_label=item.support_label,
    )


def _truth_strata(
    truth: tuple[ContinuumTruthObject, ...],
) -> tuple[str, ...]:
    """Return the present overall and prospectively declared strata."""
    return (
        "overall",
        *sorted({stratum for item in truth for stratum in item.strata}),
    )


def _selected_truth(
    truth: tuple[ContinuumTruthObject, ...],
    stratum: str,
) -> tuple[ContinuumTruthObject, ...]:
    """Select one truth-defined scientific population."""
    return tuple(
        item
        for item in truth
        if stratum == "overall" or stratum in item.strata
    )


def _mask_metrics(
    truth_labels: npt.NDArray[np.int64],
    candidate_labels: npt.NDArray[np.int64],
) -> dict[str, float]:
    """Return whole-image support overlap fractions."""
    truth_mask = truth_labels > 0
    candidate_mask = candidate_labels > 0
    intersection = int(np.count_nonzero(truth_mask & candidate_mask))
    truth_count = int(np.count_nonzero(truth_mask))
    candidate_count = int(np.count_nonzero(candidate_mask))
    union = int(np.count_nonzero(truth_mask | candidate_mask))
    return {
        "mask-precision": (
            intersection / candidate_count if candidate_count else 0.0
        ),
        "mask-recall": intersection / truth_count if truth_count else 1.0,
        "mask-iou": intersection / union if union else 1.0,
    }


def _association_context(
    truth: tuple[ContinuumTruthObject, ...],
    catalogue: tuple[ContinuumCatalogueObject, ...],
    native_supports: tuple[ContinuumSupportObject, ...],
    *,
    label_planes: tuple[
        npt.NDArray[np.int64],
        npt.NDArray[np.int64],
    ],
    beam_fwhm_pixels: float,
) -> _ContinuumAssociations:
    """Associate catalogue measurements and all native supports separately."""
    truth_labels, candidate_labels = label_planes
    truth_objects = tuple(_association_object(item) for item in truth)
    catalogue_report = match_truth_to_finder(
        truth_objects,
        tuple(_association_object(item) for item in catalogue),
        beam_fwhm_pixels=beam_fwhm_pixels,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
    )
    support_report = match_truth_to_finder(
        truth_objects,
        tuple(_association_object(item) for item in native_supports),
        beam_fwhm_pixels=beam_fwhm_pixels,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
    )
    return _ContinuumAssociations(
        primary={
            item.truth_identifier: item.candidate_identifier
            for item in catalogue_report.primary_associations
        },
        candidate_by_id={item.identifier: item for item in catalogue},
        catalogue_truth_degrees=Counter(
            item.truth_identifier
            for item in catalogue_report.eligible_associations
        ),
        support_truth_degrees=Counter(
            item.truth_identifier
            for item in support_report.eligible_associations
        ),
        support_candidate_degrees=Counter(
            item.candidate_identifier
            for item in support_report.eligible_associations
        ),
        support_edges=support_report.eligible_associations,
    )


def _conditional_measurements(
    selected: tuple[ContinuumTruthObject, ...],
    associations: _ContinuumAssociations,
    *,
    beam_fwhm_pixels: float,
) -> _ConditionalMeasurements:
    """Measure only truth-primary catalogue pairs with physical values."""
    flux_errors: list[float] = []
    offsets_x: list[float] = []
    offsets_y: list[float] = []
    radial_offsets: list[float] = []
    for truth_item in selected:
        if truth_item.catalogue_role != "astronomical-source":
            continue
        candidate_id = associations.primary.get(truth_item.identifier)
        if candidate_id is None:
            continue
        candidate = associations.candidate_by_id[candidate_id]
        flux_errors.append(
            abs(candidate.integrated_flux_jy - truth_item.integrated_flux_jy)
            / truth_item.integrated_flux_jy
        )
        offset_x = (
            candidate.centre_xy[0] - truth_item.centre_xy[0]
        ) / beam_fwhm_pixels
        offset_y = (
            candidate.centre_xy[1] - truth_item.centre_xy[1]
        ) / beam_fwhm_pixels
        offsets_x.append(offset_x)
        offsets_y.append(offset_y)
        radial_offsets.append(hypot(offset_x, offset_y))
    return _ConditionalMeasurements(
        flux_errors=tuple(flux_errors),
        offsets_x=tuple(offsets_x),
        offsets_y=tuple(offsets_y),
        radial_offsets=tuple(radial_offsets),
    )


def _populate_stratum_metrics(
    results: dict[str, dict[str, MetricValue]],
    selected: tuple[ContinuumTruthObject, ...],
    stratum: str,
    associations: _ContinuumAssociations,
    *,
    beam_fwhm_pixels: float,
) -> None:
    """Populate one truth-defined stratum without dropping unmeasured rows."""
    identifiers = {item.identifier for item in selected}
    results["completeness"][stratum] = sum(
        identifier in associations.primary for identifier in identifiers
    ) / len(selected)
    results["duplicate-fraction"][stratum] = sum(
        associations.catalogue_truth_degrees[identifier] > 1
        for identifier in identifiers
    ) / len(selected)
    results["split-fraction"][stratum] = sum(
        associations.support_truth_degrees[identifier] > 1
        for identifier in identifiers
    ) / len(selected)
    selected_supports = {
        item.candidate_identifier
        for item in associations.support_edges
        if item.truth_identifier in identifiers
    }
    results["merge-fraction"][stratum] = (
        sum(
            associations.support_candidate_degrees[identifier] > 1
            for identifier in selected_supports
        )
        / len(selected_supports)
        if selected_supports
        else 0.0
    )
    measured = _conditional_measurements(
        selected,
        associations,
        beam_fwhm_pixels=beam_fwhm_pixels,
    )
    results["integrated-flux-median"][stratum] = measured.flux_errors
    results["integrated-flux-p95"][stratum] = measured.flux_errors
    results["absolute-mean-offset-x"][stratum] = measured.offsets_x
    results["absolute-mean-offset-y"][stratum] = measured.offsets_y
    results["position-median"][stratum] = measured.radial_offsets
    results["position-p95"][stratum] = measured.radial_offsets


def measure_continuum_image(
    truth: tuple[ContinuumTruthObject, ...],
    catalogue: tuple[ContinuumCatalogueObject, ...],
    *,
    truth_label_plane: npt.ArrayLike,
    candidate_label_plane: npt.ArrayLike,
    beam_fwhm_pixels: float,
) -> dict[str, dict[str, float | tuple[float, ...]]]:
    """Derive successor sufficient statistics without inventing rows."""
    truth_rows = tuple(truth)
    catalogue_rows = tuple(catalogue)
    if not truth_rows:
        raise ValueError("successor continuum truth must not be empty")
    truth_labels = _label_plane(
        truth_label_plane,
        name="truth label plane",
    )
    candidate_labels = _label_plane(
        candidate_label_plane,
        name="candidate label plane",
    )
    if truth_labels.shape != candidate_labels.shape:
        raise ValueError("truth and candidate label planes must share shape")
    native_supports = native_support_objects(candidate_labels)
    native_labels = {item.support_label for item in native_supports}
    catalogue_labels = {item.support_label for item in catalogue_rows}
    if not catalogue_labels.issubset(native_labels):
        raise ValueError(
            "catalogue support label is absent from native labels"
        )
    associations = _association_context(
        truth_rows,
        catalogue_rows,
        _topology_support_objects(native_supports, catalogue_rows),
        label_planes=(truth_labels, candidate_labels),
        beam_fwhm_pixels=beam_fwhm_pixels,
    )
    results: dict[str, dict[str, MetricValue]] = {
        metric: {} for metric in _METRIC_FAMILIES
    }
    results["reliability"]["overall"] = (
        len(set(associations.primary.values())) / len(catalogue_rows)
        if catalogue_rows
        else 0.0
    )
    for metric, value in _mask_metrics(
        truth_labels,
        candidate_labels,
    ).items():
        results[metric]["overall"] = value
    for stratum in _truth_strata(truth_rows):
        _populate_stratum_metrics(
            results,
            _selected_truth(truth_rows, stratum),
            stratum,
            associations,
            beam_fwhm_pixels=beam_fwhm_pixels,
        )
    return results
