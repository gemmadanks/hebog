"""Explicit missing topology must not hide available native measurements."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject as HistoricalCatalogueObject,
)
from hebog.validation.external_successor_compiler import (
    ContinuumTruthObject,
)
from hebog.validation.external_successor_compiler import (
    measure_continuum_image as historical_measurement,
)
from hebog.validation.source_catalogue_diagnostics import (
    SourceDiagnosticInput,
    compile_source_diagnostics,
)
from hebog.validation.source_catalogue_measurements import (
    SourceCatalogueMeasurement as ContinuumCatalogueObject,
)
from hebog.validation.source_catalogue_measurements import (
    measure_source_catalogue_image as measure_continuum_image,
)


def support_availability_fixture(finder: str) -> SourceDiagnosticInput:
    """One supported source, one centroid-only detection, one extra row."""
    truth = np.zeros((24, 32), dtype=np.int32)
    truth[3:6, 3:6] = 1
    truth[3:6, 13:16] = 2
    owners = np.zeros_like(truth)
    owners[truth == 1] = 1
    return SourceDiagnosticInput(
        input_id="synthetic-unavailable-source-support",
        finder_id=finder,
        truth=tuple(
            ContinuumTruthObject(
                f"truth-{label}",
                label,
                centre,
                flux,
                "astronomical-source",
                (),
            )
            for label, centre, flux in (
                (1, (4.0, 4.0), 3.0),
                (2, (14.0, 4.0), 2.0),
            )
        ),
        sources=(
            ContinuumCatalogueObject("supported", 1, (4.0, 4.0), 3.0),
            ContinuumCatalogueObject("dominated", None, (14.0, 4.0), 2.0),
            ContinuumCatalogueObject("extra", None, (28.0, 20.0), 1.0),
        ),
        truth_labels=truth,
        source_union_labels=owners,
        stage_masks={"publication": owners > 0},
        background_error=np.zeros(truth.shape),
        relative_rms_error=np.zeros(truth.shape),
        valid_pixels=np.ones(truth.shape, dtype=np.bool_),
        beam_fwhm_pixels=2.0,
        dispositions=(),
    )


def _metrics(batch: SourceDiagnosticInput) -> dict[str, Any]:
    return measure_continuum_image(
        batch.truth,
        batch.sources,
        truth_label_plane=batch.truth_labels,
        candidate_label_plane=batch.source_union_labels,
        beam_fwhm_pixels=batch.beam_fwhm_pixels,
    )


@pytest.mark.parametrize(
    "finder", ("current-hebog", "released-pybdsf", "pinned-pybdsf-master")
)
def test_missing_support_keeps_measurements_and_denominators(
    finder: str,
) -> None:
    batch = support_availability_fixture(finder)
    metrics = _metrics(batch)
    assert metrics["completeness"]["overall"] == 1.0
    assert metrics["reliability"]["overall"] == pytest.approx(2 / 3)
    assert metrics["integrated-flux-median"]["overall"] == (0.0, 0.0)
    assert metrics["mask-recall"]["overall"] == 0.5
    record = compile_source_diagnostics(batch)
    assert record["schema_version"] == 2
    assert record["unavailable_source_support_ids"] == ["dominated", "extra"]
    assert len(record["source_records"]) == 3
    edges = record["matching"]["eligible_associations"]
    dominated = next(
        edge for edge in edges if edge["candidate_identifier"] == "dominated"
    )
    assert dominated["minimum_support_overlap"] == 0.0
    assert dominated["eligibility_reasons"] == ["centre-in-one-beam-dilation"]
    assert record["extra_candidate_ids"] == ["extra"]
    reversed_batch = replace(batch, sources=tuple(reversed(batch.sources)))
    assert _metrics(reversed_batch) == metrics
    assert (
        compile_source_diagnostics(reversed_batch)["matching"]
        == record["matching"]
    )


def test_all_support_unavailable_is_not_an_empty_catalogue() -> None:
    batch = support_availability_fixture("released-pybdsf")
    batch = replace(
        batch,
        sources=tuple(
            replace(row, support_label=None) for row in batch.sources
        ),
        source_union_labels=np.zeros_like(batch.source_union_labels),
    )
    metrics = _metrics(batch)
    assert metrics["completeness"]["overall"] == 1.0
    assert metrics["reliability"]["overall"] == pytest.approx(2 / 3)
    assert metrics["mask-recall"]["overall"] == 0.0


def test_asserted_missing_label_still_fails_in_every_compiler() -> None:
    batch = support_availability_fixture("released-pybdsf")
    batch = replace(
        batch, sources=(replace(batch.sources[1], support_label=9),)
    )
    for compile_record in (_metrics, compile_source_diagnostics):
        with pytest.raises(ValueError, match="absent"):
            compile_record(batch)


@pytest.mark.parametrize("offset,matched", ((2.0, True), (2.0001, False)))
def test_centroid_only_matching_keeps_the_exact_one_beam_boundary(
    offset: float,
    matched: bool,
) -> None:
    batch = support_availability_fixture("released-pybdsf")
    batch = replace(
        batch,
        sources=(
            ContinuumCatalogueObject("edge", None, (15.0 + offset, 4.0), 2.0),
        ),
    )
    record = compile_source_diagnostics(batch)
    assert len(record["matching"]["primary_associations"]) == int(matched)


@pytest.mark.parametrize(
    "field,value",
    (
        ("identifier", ""),
        ("centre_xy", (float("nan"), 1.0)),
        ("integrated_flux_jy", 0.0),
        ("integrated_flux_jy", float("nan")),
        ("support_label", 0),
    ),
)
def test_missing_support_does_not_relax_native_measurement_validation(
    field: str,
    value: Any,
) -> None:
    row = support_availability_fixture("released-pybdsf").sources[1]
    with pytest.raises(ValueError):
        replace(row, **{field: value})


@pytest.mark.parametrize("mode", ("empty", "supported", "fitless", "extra"))
def test_previously_valid_metrics_remain_exactly_equal(mode: str) -> None:
    batch = support_availability_fixture("released-pybdsf")
    row = batch.sources[0]
    sources = (
        HistoricalCatalogueObject(
            row.identifier, 1, row.centre_xy, row.integrated_flux_jy
        ),
    )
    labels = batch.source_union_labels.copy()
    if mode == "empty":
        sources = ()
        labels[:] = 0
    elif mode == "fitless":
        labels[20, 20] = 9
    elif mode == "extra":
        labels[20, 20] = 9
        sources += (HistoricalCatalogueObject("extra", 9, (20.0, 20.0), 1.0),)
    arguments: dict[str, Any] = {
        "truth_label_plane": batch.truth_labels,
        "candidate_label_plane": labels,
        "beam_fwhm_pixels": batch.beam_fwhm_pixels,
    }
    assert measure_continuum_image(
        batch.truth, sources, **arguments
    ) == historical_measurement(batch.truth, sources, **arguments)


@pytest.mark.parametrize(
    "defect", ("empty-truth", "shape", "label-dtype", "negative-label")
)
def test_amended_compiler_keeps_plane_and_truth_validation(
    defect: str,
) -> None:
    batch = support_availability_fixture("released-pybdsf")
    if defect == "empty-truth":
        batch = replace(batch, truth=())
    elif defect == "shape":
        batch = replace(
            batch, source_union_labels=batch.source_union_labels[:-1]
        )
    elif defect == "label-dtype":
        batch = replace(
            batch, source_union_labels=batch.source_union_labels.astype(float)
        )
    else:
        batch = replace(batch, source_union_labels=-batch.source_union_labels)
    with pytest.raises(ValueError):
        _metrics(batch)
