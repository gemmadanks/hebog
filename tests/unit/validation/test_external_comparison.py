"""Tests for external-comparison matching and saved finder results."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import pytest

from hebog.validation.external_comparison import (
    AssociationObject,
    match_truth_to_finder,
)
from hebog.validation.external_runners import (
    ExternalRunArtifact,
    ExternalRunFailure,
    ExternalRunResult,
    ExternalRuntimeIdentity,
    file_sha256,
    load_external_run_result,
)

_SHA256 = "0" * 64
_CONTAINER_DIGEST = f"sha256:{_SHA256}"


def _runtime(name: str, version: str) -> ExternalRuntimeIdentity:
    """Build one concise isolated runtime identity."""
    return ExternalRuntimeIdentity(
        name=name,
        version=version,
        source_revision="0" * 40,
        container_image_digest=_CONTAINER_DIGEST,
        dependency_inventory_sha256=_SHA256,
    )


def _object(
    identifier: str,
    x_pixel: float,
    y_pixel: float,
    *,
    object_class: Literal["compact", "extended"] = "compact",
    support_label: int | None = None,
) -> AssociationObject:
    """Build one concise matcher input."""
    return AssociationObject(
        identifier=identifier,
        object_class=object_class,
        centre_x_pixel=x_pixel,
        centre_y_pixel=y_pixel,
        support_label=support_label,
    )


def test_compact_matcher_maximizes_cardinality_then_distance() -> None:
    """A locally nearest choice cannot prevent a second valid match."""
    truth = (
        _object("truth-a", 0.0, 0.0),
        _object("truth-b", 0.8, 0.0),
    )
    candidates = (
        _object("candidate-a", 0.4, 0.0),
        _object("candidate-b", -0.5, 0.0),
    )

    report = match_truth_to_finder(
        truth,
        candidates,
        beam_fwhm_pixels=1.0,
    )

    assert tuple(
        (edge.truth_identifier, edge.candidate_identifier)
        for edge in report.primary_associations
    ) == (
        ("truth-a", "candidate-b"),
        ("truth-b", "candidate-a"),
    )
    assert report.unmatched_truth_identifiers == ()
    assert report.unmatched_candidate_identifiers == ()


def test_extended_matcher_prioritizes_overlap_before_distance() -> None:
    """The frozen overlap objective wins before centre proximity."""
    truth_labels = np.zeros((7, 7), dtype=np.int32)
    truth_labels[2:5, 2:5] = 1
    candidate_labels = np.zeros_like(truth_labels)
    candidate_labels[2:5, 2:5] = 1
    candidate_labels[0:2, 0:2] = 2
    candidate_labels[2, 2] = 2
    truth = (
        _object(
            "truth",
            3.0,
            3.0,
            object_class="extended",
            support_label=1,
        ),
    )
    candidates = (
        _object(
            "far-full",
            4.0,
            3.0,
            object_class="extended",
            support_label=1,
        ),
        _object(
            "near-part",
            3.0,
            3.0,
            object_class="extended",
            support_label=2,
        ),
    )

    report = match_truth_to_finder(
        truth,
        candidates,
        beam_fwhm_pixels=2.0,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
    )

    primary = report.primary_associations[0]
    assert primary.candidate_identifier == "far-full"
    assert primary.minimum_support_overlap == 1.0
    assert len(report.eligible_associations) == 2
    assert report.split_truth_identifiers == ("truth",)


def test_extended_centre_dilation_retains_zero_overlap_edge() -> None:
    """A candidate centre inside one-beam dilation remains eligible."""
    truth_labels = np.zeros((9, 9), dtype=np.int32)
    truth_labels[4, 4] = 7
    truth = (
        _object(
            "truth",
            4.0,
            4.0,
            object_class="extended",
            support_label=7,
        ),
    )
    candidates = (_object("candidate", 6.0, 4.0, object_class="extended"),)

    report = match_truth_to_finder(
        truth,
        candidates,
        beam_fwhm_pixels=2.0,
        truth_label_plane=truth_labels,
    )

    edge = report.primary_associations[0]
    assert edge.minimum_support_overlap == 0.0
    assert edge.eligibility_reasons == ("centre-in-one-beam-dilation",)


def test_matcher_retains_secondary_edges_for_merges_and_stable_ties() -> None:
    """Primary one-to-one assignment cannot conceal topology errors."""
    truth = (
        _object("truth-a", 1.0, 1.0),
        _object("truth-b", 1.0, 1.0),
    )
    candidates = (
        _object("candidate-a", 1.0, 1.0),
        _object("candidate-b", 1.0, 1.0),
    )

    report = match_truth_to_finder(
        truth,
        candidates,
        beam_fwhm_pixels=2.0,
    )

    assert tuple(
        (edge.truth_identifier, edge.candidate_identifier)
        for edge in report.primary_associations
    ) == (
        ("truth-a", "candidate-a"),
        ("truth-b", "candidate-b"),
    )
    assert len(report.eligible_associations) == 4
    assert report.split_truth_identifiers == ("truth-a", "truth-b")
    assert report.merge_candidate_identifiers == (
        "candidate-a",
        "candidate-b",
    )


def test_matcher_rejects_missing_or_malformed_extended_support() -> None:
    """Extended truth cannot silently degrade to compact distance matching."""
    truth = (
        _object(
            "truth",
            1.0,
            1.0,
            object_class="extended",
            support_label=3,
        ),
    )

    with pytest.raises(ValueError, match="truth label plane"):
        match_truth_to_finder(
            truth,
            (_object("candidate", 1.0, 1.0),),
            beam_fwhm_pixels=2.0,
        )

    labels = np.zeros((3, 3), dtype=np.int32)
    with pytest.raises(ValueError, match="support label 3"):
        match_truth_to_finder(
            truth,
            (_object("candidate", 1.0, 1.0),),
            beam_fwhm_pixels=2.0,
            truth_label_plane=labels,
        )


def _result(
    *,
    status: Literal["success", "failure"],
    artifacts: tuple[ExternalRunArtifact, ...] = (),
    failure: ExternalRunFailure | None = None,
) -> ExternalRunResult:
    """Build one saved synthetic-campaign finder result."""
    return ExternalRunResult(
        schema_version=1,
        protocol_sha256=_SHA256,
        execution_decision_sha256=_SHA256,
        input_bundle_sha256=_SHA256,
        dataset_identifier="external-unit-test",
        seed=7,
        finder_id="aegean",
        mode="operational",
        runtime=_runtime("aegeantools", "2.3.5"),
        configuration_sha256=_SHA256,
        status=status,
        wall_seconds=1.0,
        artifacts=artifacts,
        failure=failure,
    )


def test_saved_external_run_verifies_artifact_bytes(tmp_path: Path) -> None:
    """A saved successful run is readable only while its products match."""
    product = tmp_path / "artifacts/product.txt"
    product.parent.mkdir()
    product.write_text("finder output\n", encoding="utf-8")
    result = _result(
        status="success",
        artifacts=(
            ExternalRunArtifact(
                role="native-product",
                relative_path="artifacts/product.txt",
                byte_count=product.stat().st_size,
                sha256=file_sha256(product),
            ),
        ),
    )
    path = tmp_path / "result.json"
    path.write_bytes(result.canonical_json_bytes())

    assert load_external_run_result(path, verify_artifacts=True) == result

    product.write_text("changed output\n", encoding="utf-8")
    assert load_external_run_result(path, verify_artifacts=False) == result
    with pytest.raises(ValueError, match=r"byte count|checksum"):
        load_external_run_result(path, verify_artifacts=True)


def test_saved_external_run_retains_failure_and_requires_canonical_json(
    tmp_path: Path,
) -> None:
    """Failures stay explicit, and reformatted records are rejected."""
    result = _result(
        status="failure",
        failure=ExternalRunFailure(
            stage="aegean-source-finding",
            exception_type="RuntimeError",
            message="expected finder failure",
            traceback="Traceback: expected finder failure",
        ),
    )
    path = tmp_path / "result.json"
    path.write_bytes(result.canonical_json_bytes())

    loaded = load_external_run_result(path)
    assert loaded.artifacts == ()
    assert loaded.failure is not None
    assert loaded.failure.message == "expected finder failure"

    path.write_text(result.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="not canonical JSON"):
        load_external_run_result(path)


@pytest.mark.parametrize(
    ("status", "artifacts", "failure", "message"),
    (
        ("success", (), None, "requires artifacts"),
        ("failure", (), None, "requires failure details"),
    ),
)
def test_saved_external_run_rejects_ambiguous_outcomes(
    status: Literal["success", "failure"],
    artifacts: tuple[ExternalRunArtifact, ...],
    failure: ExternalRunFailure | None,
    message: str,
) -> None:
    """A result cannot claim success without products or hide a failure."""
    with pytest.raises(ValueError, match=message):
        _result(status=status, artifacts=artifacts, failure=failure)
