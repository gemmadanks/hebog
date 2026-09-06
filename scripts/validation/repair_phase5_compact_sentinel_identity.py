#!/usr/bin/env python3
"""Adapt stable public component identities to the frozen sentinel compiler."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import numpy as np
import numpy.typing as npt

from hebog.data_models.source_association import DetectionComponentRecord
from hebog.validation.comparison import CatalogueSource

_IMAGE_DIMENSIONS = 2


def link_stable_component_ownership(
    catalogue: Sequence[CatalogueSource],
    component_records: Sequence[DetectionComponentRecord],
    label_plane: npt.ArrayLike,
) -> tuple[CatalogueSource, ...]:
    """Return rows linked through exact stable component ownership records."""
    labels = np.asarray(label_plane)
    if labels.ndim != _IMAGE_DIMENSIONS or not np.issubdtype(
        labels.dtype, np.integer
    ):
        raise ValueError(
            "measurement labels must be a two-dimensional integer array"
        )
    if np.any(labels < 0):
        raise ValueError("measurement labels must be non-negative")
    records_by_id = {
        record.component_id: record for record in component_records
    }
    record_labels = tuple(record.label_value for record in component_records)
    if len(records_by_id) != len(component_records) or len(
        set(record_labels)
    ) != len(record_labels):
        raise ValueError("component ownership records must be unique")
    native_labels = {int(value) for value in np.unique(labels) if value > 0}
    if set(record_labels) != native_labels:
        raise ValueError(
            "component ownership record is absent from measurement labels"
        )
    linked: list[CatalogueSource] = []
    for source in catalogue:
        if source.island_identifier != source.identifier:
            raise ValueError("component identity and ownership disagree")
        record = records_by_id.get(source.identifier)
        if record is None:
            raise ValueError("catalogue component has no component record")
        linked.append(
            replace(
                source,
                island_identifier=f"hebog-segment-{record.label_value}",
            )
        )
    return tuple(linked)
