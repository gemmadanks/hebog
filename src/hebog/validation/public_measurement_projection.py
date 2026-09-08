# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Current public measurements projected into the frozen truth domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from hebog.data_models.catalogues import SourceCatalogue
from hebog.data_models.measurement_diagnostics import MeasurementDisposition
from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
)
from hebog.validation.products import (
    _source_label_plane,  # pyright: ignore[reportPrivateUsage]
)
from hebog.validation.public_finder_correction import (
    PublicFinderCorrectionContinuumProducts,
)

_IMAGE_DIMENSIONS = 2


def _rows(
    measured: tuple[CatalogueSource, ...],
    labels: dict[str, int],
    published_ids: set[str],
    header: fits.Header,
) -> tuple[ContinuumCatalogueObject, ...]:
    """Preserve original observables and convert coordinates only once."""
    celestial = WCS(header).celestial
    selected = tuple(
        row for row in measured if row.identifier in published_ids
    )
    if {row.identifier for row in selected} != published_ids:
        raise ValueError("public rows must have their exact measurements")
    result: list[ContinuumCatalogueObject] = []
    for row in selected:
        coordinates = cast(
            np.ndarray,
            celestial.all_world2pix(
                [[row.right_ascension_degrees, row.declination_degrees]], 0
            ),
        )[0]
        if not np.isfinite(coordinates).all():
            raise ValueError("public measurement position must be finite")
        result.append(
            ContinuumCatalogueObject(
                row.identifier,
                labels[row.identifier],
                (float(coordinates[0]), float(coordinates[1])),
                row.integrated_flux_jy,
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class PublicMeasurementProjection:
    """Keep published truth matching separate from every measured owner."""

    sources: tuple[ContinuumCatalogueObject, ...]
    components: tuple[ContinuumCatalogueObject, ...]
    source_union_labels: np.ndarray
    publication_mask: np.ndarray
    dispositions: tuple[MeasurementDisposition, ...]
    measured_sources: tuple[CatalogueSource, ...]
    measured_components: tuple[CatalogueSource, ...]


def project_public_measurements(
    terminal: PublicFinderCorrectionContinuumProducts | None,
    catalogue: SourceCatalogue,
    publication_mask: np.ndarray,
    header: fits.Header,
) -> PublicMeasurementProjection:
    """Project exact public rows, preserving fitless and pruned detections."""
    if (
        publication_mask.ndim != _IMAGE_DIMENSIONS
        or publication_mask.dtype != np.bool_
    ):
        raise ValueError("public measurement mask must be a 2D Boolean plane")
    mask = np.array(publication_mask, copy=True)
    if terminal is None:
        if catalogue.sources or catalogue.gaussian_components or np.any(mask):
            raise ValueError(
                "absent terminal cannot contain public detections"
            )
        empty = np.zeros(mask.shape, dtype=np.int32)
        empty.setflags(write=False)
        mask.setflags(write=False)
        return PublicMeasurementProjection((), (), empty, mask, (), (), ())
    owners = np.asarray(terminal.measurement_component_labels)
    if (
        owners.shape != mask.shape
        or not np.issubdtype(owners.dtype, np.integer)
        or np.any(owners < 0)
        or np.any(mask & (owners == 0))
        or not np.array_equal(mask, terminal.detection.retained_mask)
    ):
        raise ValueError("public measurement ownership or publication changed")
    labels, memberships = _source_label_plane(
        np.asarray(owners, dtype=np.int64), terminal.source_association
    )
    source_labels = {
        row.source_id: value for value, row in memberships.items()
    }
    component_labels = {
        row.component_id: row.label_value
        for row in terminal.source_association.components
    }
    published = {
        "source": {row.source_id for row in catalogue.sources},
        "component": {
            row.gaussian_component_id for row in catalogue.gaussian_components
        },
    }
    if (
        not published["source"] <= source_labels.keys()
        or not published["component"] <= component_labels.keys()
    ):
        raise ValueError("public measurement memberships are incomplete")
    selected_labels = tuple(source_labels[key] for key in published["source"])
    # Measurement-only pixels and unpublished objects never enter matching.
    labels = np.where(mask & np.isin(labels, selected_labels), labels, 0)
    if set(np.unique(labels)) - {0} != set(selected_labels):
        raise ValueError("public source has no published support")
    dispositions = tuple(
        row.model_copy(
            update={
                "catalogue_row_published": (
                    row.object_id in published[row.object_kind]
                )
            }
        )
        for row in terminal.measurement_dispositions
    )
    for kind, identifiers in published.items():
        if {
            row.object_id
            for row in dispositions
            if row.object_kind == kind
            and row.status == "measured"
            and row.catalogue_row_published
        } != identifiers:
            raise ValueError("public measurement dispositions are incomplete")
    labels.setflags(write=False)
    mask.setflags(write=False)
    return PublicMeasurementProjection(
        _rows(terminal.catalogue, source_labels, published["source"], header),
        _rows(
            terminal.component_catalogue,
            component_labels,
            published["component"],
            header,
        ),
        labels,
        mask,
        dispositions,
        terminal.catalogue,
        terminal.component_catalogue,
    )
