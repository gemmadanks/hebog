"""Array-free truth-linked diagnostics, separate from scientific scoring."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from hebog.data_models.measurement_diagnostics import MeasurementDisposition
from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_comparison import (
    AssociationObject,
    match_truth_to_finder,
)
from hebog.validation.external_runners import canonical_sha256
from hebog.validation.external_successor_compiler import (
    ContinuumTruthObject,
)
from hebog.validation.source_catalogue_measurements import SourceCatalogueRow

_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class SourceDiagnosticInput:
    """Worker-local arrays; only their bounded summaries may be retained."""

    input_id: str
    finder_id: str
    truth: tuple[ContinuumTruthObject, ...]
    sources: tuple[SourceCatalogueRow, ...]
    truth_labels: np.ndarray
    source_union_labels: np.ndarray
    stage_masks: Mapping[str, np.ndarray]
    background_error: np.ndarray
    relative_rms_error: np.ndarray
    valid_pixels: np.ndarray
    beam_fwhm_pixels: float
    dispositions: tuple[MeasurementDisposition, ...]
    measured_sources: tuple[CatalogueSource, ...] = ()
    measured_components: tuple[CatalogueSource, ...] = ()


def _error_summary(values: np.ndarray, valid: np.ndarray) -> dict[str, Any]:
    """Keep signed bias, scatter and sample availability separately."""
    selected = values[valid & np.isfinite(values)]
    return {
        "sample_count": int(selected.size),
        "mean": float(np.mean(selected)) if selected.size else None,
        "rms": float(np.sqrt(np.mean(selected**2))) if selected.size else None,
        "maximum_absolute": float(np.max(np.abs(selected)))
        if selected.size
        else None,
    }


def _validate_input(batch: SourceDiagnosticInput) -> None:
    """Refuse misaligned arrays or labels before producing evidence."""
    if not batch.input_id or not batch.finder_id:
        raise ValueError("diagnostic input and finder identities are required")
    shape = batch.truth_labels.shape
    if len(shape) != _IMAGE_DIMENSIONS:
        raise ValueError("diagnostic labels must be two-dimensional")
    for plane in (batch.truth_labels, batch.source_union_labels):
        if plane.shape != shape or not np.issubdtype(plane.dtype, np.integer):
            raise ValueError(
                "diagnostic labels must be aligned integer planes"
            )
        if np.any(plane < 0):
            raise ValueError("diagnostic labels must be non-negative")
    for mask in (batch.valid_pixels, *batch.stage_masks.values()):
        if mask.shape != shape or mask.dtype != np.bool_:
            raise ValueError("diagnostic masks must be aligned boolean planes")
    for plane in (batch.background_error, batch.relative_rms_error):
        if plane.shape != shape or not np.issubdtype(plane.dtype, np.floating):
            raise ValueError("diagnostic errors must be aligned real planes")


def _association_object(
    row: ContinuumTruthObject | SourceCatalogueRow,
) -> AssociationObject:
    """Use the exact source-union matching domain of the frozen compiler."""
    return AssociationObject(
        identifier=row.identifier,
        object_class="extended",
        centre_x_pixel=row.centre_xy[0],
        centre_y_pixel=row.centre_xy[1],
        support_label=row.support_label,
    )


def compile_source_diagnostics(batch: SourceDiagnosticInput) -> dict[str, Any]:
    """Retain edges and signed residuals; never replace binding evaluation."""
    _validate_input(batch)
    if not batch.stage_masks or any(not name for name in batch.stage_masks):
        raise ValueError("diagnostic stages require explicit names")
    matching = match_truth_to_finder(
        tuple(_association_object(row) for row in batch.truth),
        tuple(_association_object(row) for row in batch.sources),
        truth_label_plane=batch.truth_labels,
        candidate_label_plane=batch.source_union_labels,
        beam_fwhm_pixels=batch.beam_fwhm_pixels,
    )
    truth = {row.identifier: row for row in batch.truth}
    sources = {row.identifier: row for row in batch.sources}
    residuals: list[dict[str, Any]] = []
    for edge in matching.primary_associations:
        known = truth[edge.truth_identifier]
        measured = sources[edge.candidate_identifier]
        residuals.append(
            {
                "truth_id": known.identifier,
                "source_id": measured.identifier,
                "flux_fraction": measured.integrated_flux_jy
                / known.integrated_flux_jy
                - 1,
                "offset_x_pixels": measured.centre_xy[0] - known.centre_xy[0],
                "offset_y_pixels": measured.centre_xy[1] - known.centre_xy[1],
                "truth_role": known.catalogue_role,
            }
        )
    eligible = {
        edge.candidate_identifier for edge in matching.eligible_associations
    }
    primary = {
        edge.candidate_identifier for edge in matching.primary_associations
    }
    truth_support = batch.truth_labels > 0
    stages = {
        name: {
            "pixel_count": int(mask.sum()),
            "truth_overlap_pixel_count": int(
                np.count_nonzero(mask & truth_support)
            ),
            "truth_missing_pixel_count": int(
                np.count_nonzero(~mask & truth_support)
            ),
            "extra_pixel_count": int(np.count_nonzero(mask & ~truth_support)),
            "per_truth_overlap": {
                row.identifier: int(
                    np.count_nonzero(
                        mask & (batch.truth_labels == row.support_label)
                    )
                )
                for row in batch.truth
            },
        }
        for name, mask in sorted(batch.stage_masks.items())
    }
    record = {
        "schema_version": 2,
        "input_id": batch.input_id,
        "finder_id": batch.finder_id,
        "truth_records": [asdict(row) for row in batch.truth],
        "source_records": [asdict(row) for row in batch.sources],
        "unavailable_source_support_ids": sorted(
            row.identifier
            for row in batch.sources
            if row.support_label is None
        ),
        "all_measured_source_records": [
            asdict(row) for row in batch.measured_sources
        ],
        "all_measured_component_records": [
            asdict(row) for row in batch.measured_components
        ],
        "matching": asdict(matching),
        "signed_measurement_residuals": residuals,
        "extra_candidate_ids": sorted(set(sources) - eligible),
        "fragment_candidate_ids": sorted(eligible - primary),
        "stages": stages,
        "background_error": _error_summary(
            batch.background_error, batch.valid_pixels
        ),
        "relative_rms_error": _error_summary(
            batch.relative_rms_error, batch.valid_pixels
        ),
        "measurement_dispositions": [
            row.model_dump(mode="json") for row in batch.dispositions
        ],
    }
    # Normalize tuples to JSON arrays and reject non-finite scalar arithmetic.
    document: dict[str, Any] = json.loads(json.dumps(record, allow_nan=False))
    document["record_sha256"] = canonical_sha256(document)
    return document
