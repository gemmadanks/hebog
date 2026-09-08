"""Current source-level scoring never substitutes components or PyBDSF."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from hebog.data_models.measurement_diagnostics import MeasurementDisposition
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
    ContinuumTruthObject,
)
from hebog.validation.source_catalogue_diagnostics import SourceDiagnosticInput
from hebog.validation.source_catalogue_measurements import (
    SourceCatalogueMeasurement,
)
from hebog.validation.source_measurement_evidence import (
    SourceEvidenceInput,
    compile_source_measurement_summary,
)


def source_evidence_fixture(
    *, finder: str = "current-hebog", flux: float = 10.0
) -> SourceEvidenceInput:
    support = np.zeros((25, 31), dtype=np.int32)
    support[10, 10:17] = 1
    measurement = support > 0
    measurement[9:12, 9:18] = True
    return SourceEvidenceInput(
        diagnostics=SourceDiagnosticInput(
            input_id="thin-fixture",
            finder_id=finder,
            truth=(
                ContinuumTruthObject(
                    "truth", 1, (13, 10), 10, "astronomical-source", ()
                ),
            ),
            sources=(ContinuumCatalogueObject("source", 1, (13, 10), flux),),
            truth_labels=support,
            source_union_labels=support.copy(),
            stage_masks={
                "publication": support > 0,
                "measurement": measurement,
            },
            background_error=np.zeros(support.shape),
            relative_rms_error=np.zeros(support.shape),
            valid_pixels=np.ones(support.shape, dtype=np.bool_),
            beam_fwhm_pixels=2.0,
            dispositions=(
                MeasurementDisposition(
                    object_kind="source",
                    object_id="source",
                    status="measured",
                    estimator="source-owned-signed-aperture",
                    reason=None,
                    member_component_ids=("detection",),
                    catalogue_row_published=True,
                ),
                MeasurementDisposition(
                    object_kind="component",
                    object_id="detection",
                    status="unavailable",
                    estimator=None,
                    reason="underdetermined-fit",
                ),
            ),
        ),
        published_support_mask=support > 0,
        cell_id="thin-cell",
        dataset_identifier="thin-development",
        seed=123,
    )


def test_valid_aperture_source_is_scored_without_a_gaussian() -> None:
    summary = compile_source_measurement_summary(source_evidence_fixture())
    assert summary["metrics"]["completeness"] == 1
    assert summary["metrics"]["reliability"] == 1
    assert summary["metrics"]["integrated-flux-p95"] == [0]
    assert summary["metrics"]["mask-iou"] == 1
    assert summary["counts"]["source_count"] == 1
    assert summary["counts"]["gaussian_component_count"] == 0
    assert summary["diagnostics"]["stages"]["measurement"]["pixel_count"] > 7
    assert summary["diagnostics"]["measurement_dispositions"][1]["status"] == (
        "unavailable"
    )


def test_each_finder_is_independently_compared_with_analytic_truth() -> None:
    hebog = compile_source_measurement_summary(source_evidence_fixture())
    pybdsf = compile_source_measurement_summary(
        source_evidence_fixture(finder="released-pybdsf", flux=6)
    )
    assert hebog["metrics"]["integrated-flux-p95"] == [0]
    assert pybdsf["metrics"]["integrated-flux-p95"] == pytest.approx([0.4])
    assert (
        pybdsf["diagnostics"]["signed_measurement_residuals"][0][
            "flux_fraction"
        ]
        == -0.4
    )


@pytest.mark.parametrize("finder", ("current-hebog", "released-pybdsf"))
def test_source_summary_distinguishes_missing_support_from_missing_fit(
    finder: str,
) -> None:
    batch = source_evidence_fixture(finder=finder)
    diagnostic = batch.diagnostics
    summary = compile_source_measurement_summary(
        replace(
            batch,
            diagnostics=replace(
                diagnostic,
                sources=(
                    SourceCatalogueMeasurement("source", None, (13, 10), 10),
                ),
                source_union_labels=np.zeros_like(
                    diagnostic.source_union_labels
                ),
            ),
        )
    )
    assert summary["schema_version"] == 5
    assert summary["counts"]["source_count"] == 1
    assert summary["counts"]["source_union_count"] == 0
    assert summary["counts"]["unavailable_source_support_count"] == 1
    assert summary["metrics"]["completeness"] == 1
    assert summary["metrics"]["integrated-flux-p95"] == [0]
    assert summary["metrics"]["mask-iou"] == 1
    assert summary["diagnostics"]["unavailable_source_support_ids"] == [
        "source"
    ]


def test_unowned_published_support_still_penalizes_binary_mask() -> None:
    batch = source_evidence_fixture()
    mask = batch.published_support_mask.copy()
    mask[20, 20:27] = True
    diagnostic = replace(
        batch.diagnostics,
        stage_masks={**batch.diagnostics.stage_masks, "publication": mask},
    )
    summary = compile_source_measurement_summary(
        replace(batch, diagnostics=diagnostic, published_support_mask=mask)
    )
    assert summary["metrics"]["mask-precision"] == 0.5
    assert summary["metrics"]["mask-iou"] == 0.5
    assert summary["metrics"]["completeness"] == 1
    assert summary["metrics"]["reliability"] == 1


def test_measurement_only_ownership_cannot_leak_into_source_matching() -> None:
    batch = source_evidence_fixture()
    labels = batch.diagnostics.source_union_labels.copy()
    labels[0, 0] = 1
    with pytest.raises(ValueError, match="published"):
        compile_source_measurement_summary(
            replace(
                batch,
                diagnostics=replace(
                    batch.diagnostics, source_union_labels=labels
                ),
            )
        )


@pytest.mark.parametrize(
    "defect",
    (
        "cell",
        "dataset",
        "seed",
        "finder",
        "source-census",
        "duplicate-disposition",
        "publication-disposition",
        "detection-membership",
        "missing-publication-stage",
    ),
)
def test_incomplete_source_evidence_fails_before_retention(
    defect: str,
) -> None:
    batch = source_evidence_fixture()
    diagnostic = batch.diagnostics
    if defect == "cell":
        batch = replace(batch, cell_id="")
    elif defect == "dataset":
        batch = replace(batch, dataset_identifier="")
    elif defect == "seed":
        batch = replace(batch, seed=-1)
    elif defect == "finder":
        diagnostic = replace(diagnostic, finder_id="truth-as-finder")
    elif defect == "source-census":
        diagnostic = replace(diagnostic, sources=())
    elif defect == "duplicate-disposition":
        diagnostic = replace(
            diagnostic, dispositions=diagnostic.dispositions * 2
        )
    elif defect == "publication-disposition":
        source, component = diagnostic.dispositions
        diagnostic = replace(
            diagnostic,
            dispositions=(
                source.model_copy(update={"catalogue_row_published": False}),
                component,
            ),
        )
    elif defect == "detection-membership":
        diagnostic = replace(
            diagnostic, dispositions=diagnostic.dispositions[:1]
        )
    else:
        diagnostic = replace(
            diagnostic,
            stage_masks={"measurement": diagnostic.stage_masks["measurement"]},
        )
    with pytest.raises(ValueError, match="source evidence"):
        compile_source_measurement_summary(
            replace(batch, diagnostics=diagnostic)
        )
