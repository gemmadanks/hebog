"""Source-binding evidence for native fits and explicit aperture sources."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from hebog.validation.external_runners import canonical_sha256
from hebog.validation.external_successor_compiler import (
    _mask_metrics,  # pyright: ignore[reportPrivateUsage]
)
from hebog.validation.source_catalogue_diagnostics import (
    SourceDiagnosticInput,
    compile_source_diagnostics,
)
from hebog.validation.source_catalogue_measurements import (
    measure_source_catalogue_image,
)


@dataclass(frozen=True, slots=True)
class SourceEvidenceInput:
    """Transient public measurement evidence and prospective population ID."""

    diagnostics: SourceDiagnosticInput
    published_support_mask: np.ndarray
    cell_id: str
    dataset_identifier: str
    seed: int


def compile_source_measurement_summary(
    batch: SourceEvidenceInput,
) -> dict[str, Any]:
    """Compile binding source statistics without fabricating components."""
    diagnostic = compile_source_diagnostics(batch.diagnostics)
    _validate_publication(batch)
    measured = measure_source_catalogue_image(
        batch.diagnostics.truth,
        batch.diagnostics.sources,
        truth_label_plane=batch.diagnostics.truth_labels,
        candidate_label_plane=batch.diagnostics.source_union_labels,
        beam_fwhm_pixels=batch.diagnostics.beam_fwhm_pixels,
    )
    metrics = {name: strata["overall"] for name, strata in measured.items()}
    # Use the frozen compiler's binary definition on the public mask, not
    # the measurement aperture or only the pixels with fitted models.
    metrics.update(
        _mask_metrics(
            np.asarray(batch.diagnostics.truth_labels, dtype=np.int64),
            np.asarray(batch.published_support_mask, dtype=np.int64),
        )
    )
    sources = batch.diagnostics.sources
    record = {
        "schema_version": 5,
        "input_id": batch.diagnostics.input_id,
        "finder_id": batch.diagnostics.finder_id,
        "cell_id": batch.cell_id,
        "dataset_identifier": batch.dataset_identifier,
        "seed": batch.seed,
        "semantics": {
            "binding_catalogue_level": "source",
            "binding_topology_domain": "published-source-union",
            "binary_support_domain": "published-mask",
            "component_diagnostic_binding": False,
        },
        "counts": {
            "source_count": len(sources),
            "source_union_count": sum(
                row.support_label is not None for row in sources
            ),
            "unavailable_source_support_count": sum(
                row.support_label is None for row in sources
            ),
            "gaussian_component_count": sum(
                row.object_kind == "component" and row.catalogue_row_published
                for row in batch.diagnostics.dispositions
            ),
        },
        "product_valid": True,
        "ownership_valid": True,
        "metrics": metrics,
        "diagnostics": diagnostic,
    }
    document: dict[str, Any] = json.loads(json.dumps(record, allow_nan=False))
    document["record_sha256"] = canonical_sha256(document)
    return document


def _validate_publication(batch: SourceEvidenceInput) -> None:
    """Require an explicit census without assuming every owner has a fit."""
    diagnostic = batch.diagnostics
    if (
        not batch.cell_id
        or not batch.dataset_identifier
        or type(batch.seed) is not int
        or batch.seed < 0
        or diagnostic.finder_id not in {"current-hebog", "released-pybdsf"}
    ):
        raise ValueError("source evidence population identity is invalid")
    mask = batch.published_support_mask
    unions = diagnostic.source_union_labels
    published_stage = diagnostic.stage_masks.get("publication")
    if (
        mask.dtype != np.bool_
        or mask.shape != unions.shape
        or np.any((unions > 0) & ~mask)
        or published_stage is None
        or not np.array_equal(mask, published_stage)
    ):
        raise ValueError("source evidence must use exact published support")
    source_ids = {row.identifier for row in diagnostic.sources}
    source_labels = tuple(
        row.support_label
        for row in diagnostic.sources
        if row.support_label is not None
    )
    if (
        len(source_ids) != len(diagnostic.sources)
        or len(source_labels) != len(set(source_labels))
        or set(source_labels) != set(np.unique(unions)) - {0}
    ):
        raise ValueError("source evidence must retain exact source unions")
    dispositions = diagnostic.dispositions
    keys = {(row.object_kind, row.object_id) for row in dispositions}
    if len(keys) != len(dispositions):
        raise ValueError("source evidence dispositions must be unique")
    published_ids = {
        row.object_id
        for row in dispositions
        if row.object_kind == "source" and row.catalogue_row_published
    }
    if published_ids != source_ids:
        raise ValueError("source evidence publication dispositions changed")
    component_ids = {
        row.object_id for row in dispositions if row.object_kind == "component"
    }
    members = tuple(
        member
        for row in dispositions
        if row.object_kind == "source"
        for member in row.member_component_ids
    )
    if len(members) != len(set(members)) or set(members) != component_ids:
        raise ValueError("source evidence detection membership is incomplete")
