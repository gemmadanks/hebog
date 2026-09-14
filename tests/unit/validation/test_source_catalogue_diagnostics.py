"""Per-image diagnostics distinguish missing support, fragments and noise."""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
    ContinuumTruthObject,
)
from hebog.validation.source_catalogue_diagnostics import (
    SourceDiagnosticInput,
    compile_source_diagnostics,
)


def _batch() -> SourceDiagnosticInput:
    truth = np.zeros((32, 48), dtype=np.int32)
    truth[10:14, 10:18] = 1
    owners = np.zeros_like(truth)
    owners[10:14, 10:14] = 1
    owners[10:14, 15:18] = 2
    owners[25:28, 35:38] = 3
    return SourceDiagnosticInput(
        input_id="analytic-split",
        finder_id="current-hebog",
        truth=(
            ContinuumTruthObject(
                "truth-one",
                1,
                (13.5, 11.5),
                10.0,
                "astronomical-source",
                (),
            ),
        ),
        sources=(
            ContinuumCatalogueObject("left", 1, (11.5, 11.5), 6.0),
            ContinuumCatalogueObject("right", 2, (16.0, 11.5), 4.0),
            ContinuumCatalogueObject("noise", 3, (36.0, 26.0), 2.0),
        ),
        truth_labels=truth,
        source_union_labels=owners,
        stage_masks={"direct": owners > 0, "publication": owners > 0},
        background_error=np.full(truth.shape, -0.2),
        relative_rms_error=np.full(truth.shape, 0.1),
        valid_pixels=np.ones(truth.shape, dtype=np.bool_),
        beam_fwhm_pixels=2.0,
        dispositions=(),
    )


def test_truth_edges_separate_noise_splits_and_signed_residuals() -> None:
    record = compile_source_diagnostics(_batch())
    assert len(record["matching"]["eligible_associations"]) == 2
    assert len(record["matching"]["primary_associations"]) == 1
    assert record["extra_candidate_ids"] == ["noise"]
    assert record["fragment_candidate_ids"] == ["right"]
    assert record["signed_measurement_residuals"][0]["flux_fraction"] == -0.4
    assert record["signed_measurement_residuals"][0]["offset_x_pixels"] == -2.0
    assert record["stages"]["publication"]["truth_missing_pixel_count"] == 4
    assert record["stages"]["publication"]["extra_pixel_count"] == 9
    assert record["background_error"]["mean"] == pytest.approx(-0.2)
    assert record["relative_rms_error"]["mean"] == pytest.approx(0.1)
    assert json.loads(json.dumps(record, allow_nan=False)) == record


def test_diagnostic_measurement_support_need_not_equal_publication() -> None:
    batch = _batch()
    stages = {**batch.stage_masks, "measurement": batch.truth_labels > 0}
    record = compile_source_diagnostics(replace(batch, stage_masks=stages))
    assert record["stages"]["measurement"]["truth_missing_pixel_count"] == 0
    assert record["stages"]["publication"]["truth_missing_pixel_count"] == 4


def test_invalid_pixels_are_unavailable_not_zero_error() -> None:
    batch = _batch()
    invalid = np.zeros(batch.valid_pixels.shape, dtype=np.bool_)
    record = compile_source_diagnostics(replace(batch, valid_pixels=invalid))
    assert record["background_error"] == {
        "sample_count": 0,
        "mean": None,
        "rms": None,
        "maximum_absolute": None,
    }


def test_unpublished_measurements_survive_outside_truth_matching() -> None:
    row = CatalogueSource(
        identifier="pruned-source",
        right_ascension_degrees=180.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=0.1,
        integrated_flux_jy=0.5,
    )
    record = compile_source_diagnostics(
        replace(_batch(), measured_sources=(row,), measured_components=(row,))
    )
    assert (
        record["all_measured_source_records"][0]["identifier"]
        == row.identifier
    )
    assert (
        record["all_measured_component_records"][0]["integrated_flux_jy"]
        == 0.5
    )
    assert row.identifier not in record["extra_candidate_ids"]
    assert len(record["matching"]["eligible_associations"]) == 2


@pytest.mark.parametrize(
    "defect",
    (
        "shape",
        "dtype",
        "negative",
        "identity",
        "dimensions",
        "label-shape",
        "missing-stage",
    ),
)
def test_malformed_diagnostic_inputs_fail_before_retention(
    defect: str,
) -> None:
    batch = _batch()
    if defect == "shape":
        batch = replace(batch, background_error=np.zeros((3, 3)))
    elif defect == "dtype":
        batch = replace(batch, stage_masks={"direct": batch.truth_labels})
    elif defect == "negative":
        batch = replace(batch, source_union_labels=-batch.source_union_labels)
    elif defect == "dimensions":
        batch = replace(batch, truth_labels=batch.truth_labels[np.newaxis])
    elif defect == "label-shape":
        batch = replace(
            batch, source_union_labels=batch.source_union_labels[:-1]
        )
    elif defect == "missing-stage":
        batch = replace(batch, stage_masks={})
    else:
        batch = replace(batch, input_id="")
    with pytest.raises(ValueError):
        compile_source_diagnostics(batch)
