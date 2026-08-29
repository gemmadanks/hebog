# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Evaluation-only support adapter for associated Hebog catalogue rows.

The closed successor compiler maps every catalogue row to one native label.
Source association deliberately changes that relationship: one catalogue
source owns the exact union of one or more immutable component labels.  This
module adapts only that evaluation boundary.  It does not alter candidate
products, matching thresholds, topology metrics, or any closed compiler file.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
from math import comb, isfinite
from typing import Any, Literal, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS

from hebog.validation import external_successor_compiler as successor
from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_comparison import AssociationObject

_COMPONENT_NAMESPACE = b"phase-5-detection-component-v1\0"
_SOURCE_NAMESPACE = b"phase-5-associated-source-v1\0"
_ASSOCIATED_PREFIX = "source-associated-"
_IMAGE_DIMENSIONS = 2
ContinuumFinderId = Literal[
    "hebog",
    "released-pybdsf",
    "pinned-pybdsf-master",
]


def _stable_identifier(
    namespace: bytes,
    prefix: str,
    values: tuple[str, ...],
) -> str:
    """Independently reproduce one frozen association identifier."""
    digest = sha256(namespace)
    for value in values:
        digest.update(value.encode("ascii"))
        digest.update(b"\0")
    return f"{prefix}-{digest.hexdigest()}"


def detection_component_identifier(
    canonical_pixel_yx: tuple[int, int],
) -> str:
    """Derive the frozen component identity from its canonical pixel."""
    if (
        len(canonical_pixel_yx) != _IMAGE_DIMENSIONS
        or any(type(value) is not int for value in canonical_pixel_yx)
        or min(canonical_pixel_yx) < 0
    ):
        raise ValueError(
            "canonical component pixel must contain non-negative integers"
        )
    return _stable_identifier(
        _COMPONENT_NAMESPACE,
        "component-detection",
        tuple(str(value) for value in canonical_pixel_yx),
    )


def associated_source_identifier(component_ids: tuple[str, ...]) -> str:
    """Derive the frozen source identity from canonical membership."""
    if not component_ids or component_ids != tuple(sorted(set(component_ids))):
        raise ValueError("associated source component IDs must be canonical")
    return _stable_identifier(
        _SOURCE_NAMESPACE,
        "source-associated",
        component_ids,
    )


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


@dataclass(frozen=True, slots=True)
class AssociatedContinuumCatalogueObject:
    """One measured source and its exact native component support union."""

    identifier: str
    support_labels: tuple[int, ...]
    centre_xy: tuple[float, float]
    integrated_flux_jy: float

    def __post_init__(self) -> None:
        """Require a physical row and a canonical non-empty support union."""
        if not self.identifier:
            raise ValueError("continuum object identifier must not be empty")
        if (
            not self.support_labels
            or self.support_labels != tuple(sorted(set(self.support_labels)))
            or min(self.support_labels) <= 0
        ):
            raise ValueError(
                "continuum support labels must be non-empty, positive, "
                "and canonical"
            )
        if not all(isfinite(value) for value in self.centre_xy):
            raise ValueError("continuum object centre must be finite")
        if (
            not isfinite(self.integrated_flux_jy)
            or self.integrated_flux_jy <= 0.0
        ):
            raise ValueError(
                "continuum object flux must be finite and positive"
            )


@dataclass(frozen=True, slots=True)
class ProspectiveSourceTopologyMeasurements:
    """Binding catalogue-source metrics plus component diagnostics."""

    binding_metrics: dict[str, dict[str, float | tuple[float, ...]]]
    native_component_split_fraction: dict[str, float]
    native_component_merge_fraction: dict[str, float]


def _native_component_labels_by_id(
    label_plane: npt.ArrayLike,
) -> dict[str, int]:
    """Recover stable component identities from canonical owner pixels."""
    labels = _label_plane(label_plane, name="candidate label plane")
    output: dict[str, int] = {}
    for label in sorted(int(item) for item in np.unique(labels) if item > 0):
        y_pixels, x_pixels = np.nonzero(labels == label)
        identifier = detection_component_identifier(
            (int(y_pixels[0]), int(x_pixels[0]))
        )
        if identifier in output:
            raise ValueError("native component identities are not unique")
        output[identifier] = label
    return output


def _candidate_component_subsets(
    components: tuple[tuple[str, int], ...],
    component_count: int,
) -> Iterable[tuple[tuple[str, int], ...]]:
    """Enumerate the smaller exact side of one finite membership search."""
    if component_count <= len(components) // 2:
        yield from combinations(components, component_count)
        return
    excluded_count = len(components) - component_count
    for excluded in combinations(components, excluded_count):
        excluded_ids = {item[0] for item in excluded}
        yield tuple(item for item in components if item[0] not in excluded_ids)


def _associated_component_counts(
    catalogue: tuple[CatalogueSource, ...],
    component_count: int,
) -> dict[str, int]:
    """Validate associated rows and their complete partition size."""
    identifiers = tuple(item.identifier for item in catalogue)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("associated source identifiers must be unique")
    counts: dict[str, int] = {}
    for source in catalogue:
        count = source.component_count
        if (
            source.identifier != source.island_identifier
            or not source.identifier.startswith(_ASSOCIATED_PREFIX)
            or type(count) is not int
            or count <= 0
        ):
            raise ValueError("associated source identity is malformed")
        counts[source.identifier] = count
    if sum(counts.values()) != component_count:
        raise ValueError(
            "associated source memberships must partition native supports"
        )
    return counts


def _verified_source_components(
    source: CatalogueSource,
    components: dict[str, int],
    component_count: int,
) -> tuple[tuple[str, int], ...]:
    """Resolve one digest-bound membership from the finite native set."""
    if component_count > len(components):
        raise ValueError("associated source membership cannot be verified")
    candidates = tuple(sorted(components.items()))
    matched: tuple[tuple[str, int], ...] | None = None
    for subset in _candidate_component_subsets(candidates, component_count):
        component_ids = tuple(sorted(item[0] for item in subset))
        if associated_source_identifier(component_ids) != source.identifier:
            continue
        if matched is not None:
            raise ValueError("associated source membership is ambiguous")
        matched = tuple(subset)
    if matched is None:
        raise ValueError("associated source membership cannot be verified")
    return matched


def _associated_support_labels(
    catalogue: tuple[CatalogueSource, ...],
    label_plane: npt.ArrayLike,
) -> dict[str, tuple[int, ...]]:
    """Verify every digest and recover one exact support partition."""
    components = _native_component_labels_by_id(label_plane)
    counts = _associated_component_counts(catalogue, len(components))
    pending = list(catalogue)
    remaining = dict(components)
    output: dict[str, tuple[int, ...]] = {}
    while pending:
        source = min(
            pending,
            key=lambda item: (
                comb(len(remaining), counts[item.identifier])
                if counts[item.identifier] <= len(remaining)
                else float("inf"),
                item.identifier,
            ),
        )
        matched = _verified_source_components(
            source,
            remaining,
            counts[source.identifier],
        )
        output[source.identifier] = tuple(sorted(item[1] for item in matched))
        for component_id, _ in matched:
            remaining.pop(component_id)
        pending.remove(source)
    if remaining:
        raise ValueError(
            "associated source memberships must partition native supports"
        )
    return output


def continuum_catalogue_objects(
    catalogue: Sequence[CatalogueSource],
    label_plane: npt.ArrayLike,
    *,
    finder_id: ContinuumFinderId,
    header: fits.Header,
) -> tuple[
    successor.ContinuumCatalogueObject | AssociatedContinuumCatalogueObject,
    ...,
]:
    """Translate associated Hebog rows or delegate unchanged semantics."""
    sources = tuple(catalogue)
    associated = finder_id == "hebog" and any(
        (item.island_identifier or "").startswith(_ASSOCIATED_PREFIX)
        for item in sources
    )
    if not associated:
        return successor.continuum_catalogue_objects(
            sources,
            label_plane,
            finder_id=finder_id,
            header=header,
        )
    if not all(
        (item.island_identifier or "").startswith(_ASSOCIATED_PREFIX)
        for item in sources
    ):
        raise ValueError(
            "Hebog catalogue cannot mix segment and associated sources"
        )
    support_by_source = _associated_support_labels(sources, label_plane)
    celestial = WCS(header, relax=True).celestial
    output: list[AssociatedContinuumCatalogueObject] = []
    for source in sources:
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
            AssociatedContinuumCatalogueObject(
                identifier=source.identifier,
                support_labels=support_by_source[source.identifier],
                centre_xy=(float(centre[0]), float(centre[1])),
                integrated_flux_jy=integrated_flux,
            )
        )
    return tuple(output)


def _synthetic_source_labels(
    catalogue: tuple[AssociatedContinuumCatalogueObject, ...],
    native_labels: npt.NDArray[np.int64],
) -> tuple[npt.NDArray[np.int64], dict[str, int]]:
    """Materialize a bounded label view for exact source-union matching."""
    source_labels = {
        source.identifier: index
        for index, source in enumerate(
            sorted(catalogue, key=lambda item: item.identifier),
            start=1,
        )
    }
    synthetic = np.zeros(native_labels.shape, dtype=np.int64)
    for source in catalogue:
        support = np.isin(native_labels, source.support_labels)
        if not np.any(support) or np.any(synthetic[support] != 0):
            raise ValueError(
                "associated source supports must be present and disjoint"
            )
        synthetic[support] = source_labels[source.identifier]
    if np.any((native_labels > 0) & (synthetic == 0)):
        raise ValueError(
            "associated source memberships must partition native supports"
        )
    return synthetic, source_labels


def _associated_context(
    truth: tuple[successor.ContinuumTruthObject, ...],
    catalogue: tuple[AssociatedContinuumCatalogueObject, ...],
    *,
    truth_labels: npt.NDArray[np.int64],
    candidate_labels: npt.NDArray[np.int64],
    beam_fwhm_pixels: float,
) -> Any:
    """Associate source unions and immutable native topology separately."""
    synthetic, source_labels = _synthetic_source_labels(
        catalogue,
        candidate_labels,
    )
    truth_objects = tuple(
        successor._association_object(item) for item in truth
    )
    catalogue_objects = tuple(
        AssociationObject(
            identifier=item.identifier,
            object_class="extended",
            centre_x_pixel=item.centre_xy[0],
            centre_y_pixel=item.centre_xy[1],
            support_label=source_labels[item.identifier],
        )
        for item in catalogue
    )
    catalogue_report = successor.match_truth_to_finder(
        truth_objects,
        catalogue_objects,
        beam_fwhm_pixels=beam_fwhm_pixels,
        truth_label_plane=truth_labels,
        candidate_label_plane=synthetic,
    )
    native_supports = successor.native_support_objects(candidate_labels)
    singleton_rows = tuple(
        successor.ContinuumCatalogueObject(
            identifier=item.identifier,
            support_label=item.support_labels[0],
            centre_xy=item.centre_xy,
            integrated_flux_jy=item.integrated_flux_jy,
        )
        for item in catalogue
        if len(item.support_labels) == 1
    )
    topology_supports = successor._topology_support_objects(
        native_supports,
        singleton_rows,
    )
    support_report = successor.match_truth_to_finder(
        truth_objects,
        tuple(
            successor._association_object(item) for item in topology_supports
        ),
        beam_fwhm_pixels=beam_fwhm_pixels,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
    )
    return successor._ContinuumAssociations(
        primary={
            item.truth_identifier: item.candidate_identifier
            for item in catalogue_report.primary_associations
        },
        candidate_by_id=cast(
            dict[str, successor.ContinuumCatalogueObject],
            {item.identifier: item for item in catalogue},
        ),
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


def _prospective_source_contexts(
    truth: tuple[successor.ContinuumTruthObject, ...],
    catalogue: tuple[AssociatedContinuumCatalogueObject, ...],
    *,
    truth_labels: npt.NDArray[np.int64],
    candidate_labels: npt.NDArray[np.int64],
    beam_fwhm_pixels: float,
) -> tuple[Any, Any]:
    """Associate binding source unions and diagnostic components separately."""
    synthetic, source_labels = _synthetic_source_labels(
        catalogue,
        candidate_labels,
    )
    truth_objects = tuple(
        successor._association_object(item) for item in truth
    )
    catalogue_objects = tuple(
        AssociationObject(
            identifier=item.identifier,
            object_class="extended",
            centre_x_pixel=item.centre_xy[0],
            centre_y_pixel=item.centre_xy[1],
            support_label=source_labels[item.identifier],
        )
        for item in catalogue
    )
    catalogue_report = successor.match_truth_to_finder(
        truth_objects,
        catalogue_objects,
        beam_fwhm_pixels=beam_fwhm_pixels,
        truth_label_plane=truth_labels,
        candidate_label_plane=synthetic,
    )
    native_supports = successor.native_support_objects(candidate_labels)
    native_report = successor.match_truth_to_finder(
        truth_objects,
        tuple(successor._association_object(item) for item in native_supports),
        beam_fwhm_pixels=beam_fwhm_pixels,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
    )

    def context(report: Any, *, source_rows: bool) -> Any:
        candidates = (
            {item.identifier: item for item in catalogue}
            if source_rows
            else {item.identifier: item for item in native_supports}
        )
        return successor._ContinuumAssociations(
            primary={
                item.truth_identifier: item.candidate_identifier
                for item in report.primary_associations
            },
            candidate_by_id=cast(
                dict[str, successor.ContinuumCatalogueObject],
                candidates,
            ),
            catalogue_truth_degrees=Counter(
                item.truth_identifier for item in report.eligible_associations
            ),
            support_truth_degrees=Counter(
                item.truth_identifier for item in report.eligible_associations
            ),
            support_candidate_degrees=Counter(
                item.candidate_identifier
                for item in report.eligible_associations
            ),
            support_edges=report.eligible_associations,
        )

    return context(catalogue_report, source_rows=True), context(
        native_report,
        source_rows=False,
    )


def _topology_fractions(
    selected: tuple[successor.ContinuumTruthObject, ...],
    associations: Any,
) -> tuple[float, float]:
    """Return split and merge fractions for one explicit topology layer."""
    identifiers = {item.identifier for item in selected}
    split = sum(
        associations.support_truth_degrees[identifier] > 1
        for identifier in identifiers
    ) / len(selected)
    selected_supports = {
        item.candidate_identifier
        for item in associations.support_edges
        if item.truth_identifier in identifiers
    }
    merge = (
        sum(
            associations.support_candidate_degrees[identifier] > 1
            for identifier in selected_supports
        )
        / len(selected_supports)
        if selected_supports
        else 0.0
    )
    return split, merge


def measure_prospective_source_topology(
    truth: tuple[successor.ContinuumTruthObject, ...],
    catalogue: tuple[AssociatedContinuumCatalogueObject, ...],
    *,
    truth_label_plane: npt.ArrayLike,
    candidate_label_plane: npt.ArrayLike,
    beam_fwhm_pixels: float,
) -> ProspectiveSourceTopologyMeasurements:
    """Measure future binding source topology and component diagnostics.

    The function accepts only current in-memory truth, catalogue, and label
    records. It has no campaign or ledger input and therefore cannot rescore a
    closed evidence product.
    """
    truth_rows = tuple(truth)
    catalogue_rows = tuple(catalogue)
    if not truth_rows:
        raise ValueError("successor continuum truth must not be empty")
    truth_labels = _label_plane(truth_label_plane, name="truth label plane")
    candidate_labels = _label_plane(
        candidate_label_plane,
        name="candidate label plane",
    )
    if truth_labels.shape != candidate_labels.shape:
        raise ValueError("truth and candidate label planes must share shape")
    binding, diagnostic = _prospective_source_contexts(
        truth_rows,
        catalogue_rows,
        truth_labels=truth_labels,
        candidate_labels=candidate_labels,
        beam_fwhm_pixels=beam_fwhm_pixels,
    )
    results: dict[str, dict[str, Any]] = {
        metric: {} for metric in successor._METRIC_FAMILIES
    }
    results["reliability"]["overall"] = (
        len(set(binding.primary.values())) / len(catalogue_rows)
        if catalogue_rows
        else 0.0
    )
    for metric, value in successor._mask_metrics(
        truth_labels,
        candidate_labels,
    ).items():
        results[metric]["overall"] = value
    native_split: dict[str, float] = {}
    native_merge: dict[str, float] = {}
    for stratum in successor._truth_strata(truth_rows):
        selected = successor._selected_truth(truth_rows, stratum)
        successor._populate_stratum_metrics(
            results,
            selected,
            stratum,
            binding,
            beam_fwhm_pixels=beam_fwhm_pixels,
        )
        native_split[stratum], native_merge[stratum] = _topology_fractions(
            selected,
            diagnostic,
        )
    return ProspectiveSourceTopologyMeasurements(
        binding_metrics=cast(
            dict[str, dict[str, float | tuple[float, ...]]],
            results,
        ),
        native_component_split_fraction=dict(sorted(native_split.items())),
        native_component_merge_fraction=dict(sorted(native_merge.items())),
    )


def measure_continuum_image(
    truth: tuple[successor.ContinuumTruthObject, ...],
    catalogue: tuple[
        successor.ContinuumCatalogueObject
        | AssociatedContinuumCatalogueObject,
        ...,
    ],
    *,
    truth_label_plane: npt.ArrayLike,
    candidate_label_plane: npt.ArrayLike,
    beam_fwhm_pixels: float,
) -> dict[str, dict[str, float | tuple[float, ...]]]:
    """Measure source unions while preserving native topology semantics."""
    catalogue_rows = tuple(catalogue)
    associated_rows = tuple(
        item
        for item in catalogue_rows
        if isinstance(item, AssociatedContinuumCatalogueObject)
    )
    if not associated_rows:
        return successor.measure_continuum_image(
            truth,
            cast(
                tuple[successor.ContinuumCatalogueObject, ...],
                catalogue_rows,
            ),
            truth_label_plane=truth_label_plane,
            candidate_label_plane=candidate_label_plane,
            beam_fwhm_pixels=beam_fwhm_pixels,
        )
    if len(associated_rows) != len(catalogue_rows):
        raise ValueError("continuum catalogue cannot mix support semantics")
    truth_rows = tuple(truth)
    if not truth_rows:
        raise ValueError("successor continuum truth must not be empty")
    truth_labels = _label_plane(truth_label_plane, name="truth label plane")
    candidate_labels = _label_plane(
        candidate_label_plane,
        name="candidate label plane",
    )
    if truth_labels.shape != candidate_labels.shape:
        raise ValueError("truth and candidate label planes must share shape")
    associations = _associated_context(
        truth_rows,
        associated_rows,
        truth_labels=truth_labels,
        candidate_labels=candidate_labels,
        beam_fwhm_pixels=beam_fwhm_pixels,
    )
    results: dict[str, dict[str, Any]] = {
        metric: {} for metric in successor._METRIC_FAMILIES
    }
    results["reliability"]["overall"] = (
        len(set(associations.primary.values())) / len(associated_rows)
        if associated_rows
        else 0.0
    )
    for metric, value in successor._mask_metrics(
        truth_labels,
        candidate_labels,
    ).items():
        results[metric]["overall"] = value
    for stratum in successor._truth_strata(truth_rows):
        successor._populate_stratum_metrics(
            results,
            successor._selected_truth(truth_rows, stratum),
            stratum,
            associations,
            beam_fwhm_pixels=beam_fwhm_pixels,
        )
    return cast(dict[str, dict[str, float | tuple[float, ...]]], results)


def install_source_association_evaluation_repair(
    terminal_globals: dict[str, Any],
) -> None:
    """Install only the associated-catalogue interpretation seams."""
    candidate_objects = terminal_globals.get("_candidate_objects")
    measure_image = terminal_globals.get("measure_continuum_image")
    if not callable(candidate_objects) or not callable(measure_image):
        raise ValueError("evaluation repair compiler seam changed")
    terminal_globals["_candidate_objects"] = continuum_catalogue_objects
    terminal_globals["measure_continuum_image"] = measure_continuum_image
