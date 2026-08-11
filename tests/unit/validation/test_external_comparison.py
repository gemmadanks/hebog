"""Tests for the frozen finder-neutral external-comparison boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import pytest

from hebog.validation.contracts import (
    PhaseFiveExternalExecutionDecision,
    load_phase_five_external_comparison_protocol,
)
from hebog.validation.external_comparison import (
    AssociationObject,
    match_truth_to_finder,
)
from hebog.validation.external_runners import (
    AuthorizedExternalRun,
    ExternalRuntimeIdentity,
    authorize_external_run,
    execute_external_run,
    file_sha256,
    load_external_run_result,
    source_tree_sha256,
)
from hebog.validation.materialization import (
    ExternalInputArtifact,
    ExternalInputBundle,
    materialize_external_realization,
)

_ROOT = Path(__file__).parents[3]
_PROTOCOL = _ROOT / "config/contracts/phase-5-external-comparison.json"
_BASE_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_COMPACT_MANIFEST = (
    _ROOT / "config/datasets/phase-5-external-compact-blend.json"
)
_COMPACT_DATASET = "phase5-external-compact-blend-512"
_COMPACT_SEED = 2026790002
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


def _authorized_run(tmp_path: Path) -> AuthorizedExternalRun:
    """Build a concise already-authorized boundary for output tests."""
    decision = PhaseFiveExternalExecutionDecision.model_validate(
        {
            "schema_version": 1,
            "decision_id": "phase-5-external-execution-decision",
            "status": "reviewed-before-external-output",
            "protocol_sha256": _SHA256,
            "candidate_review_sha256": _SHA256,
            "implementation_commit": "0" * 40,
            "source_tree_sha256": _SHA256,
            "hebog_container_image_digest": _CONTAINER_DIGEST,
            "hebog_dependency_inventory_sha256": _SHA256,
            "pybdsf_ncores": 1,
            "runners": [
                {
                    "relative_path": (
                        "scripts/benchmark/run_phase5_external_hebog.py"
                    ),
                    "sha256": _SHA256,
                },
                {
                    "relative_path": (
                        "scripts/benchmark/run_phase5_external_pybdsf.py"
                    ),
                    "sha256": _SHA256,
                },
                {
                    "relative_path": (
                        "scripts/benchmark/run_phase5_external_aegean.py"
                    ),
                    "sha256": _SHA256,
                },
            ],
            "named_review": "unit-test-review",
            "decision": "authorize-one-terminal-external-comparison",
            "execution_authorized": True,
            "one_look_opened": False,
            "step_three_authorized": False,
            "optimization_authorized": False,
            "qualification_opened": False,
            "next_action": (
                "execute-complete-frozen-comparison-once-without-opening-"
                "partial-results"
            ),
        }
    )
    bundle = ExternalInputBundle(
        schema_version=1,
        protocol_sha256=_SHA256,
        manifest_sha256=_SHA256,
        dataset_identifier="external-unit-test",
        seed=7,
        recipe_sha256=_SHA256,
        dtype="float64",
        shape_yx=(8, 8),
        artifacts=(
            ExternalInputArtifact(
                role="image",
                relative_path="image.fits",
                byte_count=1,
                sha256=_SHA256,
            ),
            ExternalInputArtifact(
                role="mean",
                relative_path="mean.fits",
                byte_count=1,
                sha256=_SHA256,
            ),
            ExternalInputArtifact(
                role="rms",
                relative_path="rms.fits",
                byte_count=1,
                sha256=_SHA256,
            ),
        ),
    )
    return AuthorizedExternalRun(
        protocol=load_phase_five_external_comparison_protocol(_PROTOCOL),
        decision=decision,
        input_bundle=bundle,
        protocol_path=_PROTOCOL,
        decision_path=tmp_path / "decision.json",
        input_bundle_path=tmp_path / "input.json",
        protocol_sha256=_SHA256,
        decision_sha256=_SHA256,
        input_bundle_sha256=_SHA256,
    )


def test_external_run_manifest_retains_success_and_verifies_artifacts(
    tmp_path: Path,
) -> None:
    """A successful isolated leg publishes only checksum-bound artifacts."""
    authorized = _authorized_run(tmp_path)

    def operation(staging: Path) -> dict[str, Path]:
        product = staging / "product.txt"
        product.write_text("finder output\n", encoding="utf-8")
        return {"native-product": product}

    path = execute_external_run(
        authorized,
        finder_id="hebog",
        mode="candidate",
        runtime=_runtime("hebog", "0.1.0"),
        configuration={"threshold": 5.0},
        output_directory=tmp_path / "result",
        operation=operation,
        failure_stage="unit-test-finder",
    )
    result = load_external_run_result(path, verify_artifacts=True)

    assert result.status == "success"
    assert result.failure is None
    assert result.artifacts[0].role == "native-product"
    product_path = path.parent / result.artifacts[0].relative_path
    product_path.write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"byte count|checksum"):
        load_external_run_result(path, verify_artifacts=True)


def test_external_run_retains_failure_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    """A finder exception remains in the denominator and cannot be replaced."""
    authorized = _authorized_run(tmp_path)

    def operation(_staging: Path) -> dict[str, Path]:
        raise RuntimeError("expected finder failure")

    output = tmp_path / "failed"
    path = execute_external_run(
        authorized,
        finder_id="aegean",
        mode="operational",
        runtime=_runtime("aegeantools", "2.3.5"),
        configuration={"seedclip": 5.0},
        output_directory=output,
        operation=operation,
        failure_stage="aegean-source-finding",
    )
    result = load_external_run_result(path, verify_artifacts=True)

    assert result.status == "failure"
    assert result.artifacts == ()
    assert result.failure is not None
    assert result.failure.message == "expected finder failure"
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        execute_external_run(
            authorized,
            finder_id="aegean",
            mode="operational",
            runtime=_runtime("aegeantools", "2.3.5"),
            configuration={},
            output_directory=output,
            operation=operation,
            failure_stage="aegean-source-finding",
        )


def test_external_authorization_binds_protocol_input_tree_and_runner(
    tmp_path: Path,
) -> None:
    """No input opens until every reviewed implementation byte matches."""
    input_path = materialize_external_realization(
        _PROTOCOL,
        _COMPACT_MANIFEST,
        _COMPACT_DATASET,
        _COMPACT_SEED,
        tmp_path / "input",
    )
    runner_paths = (
        "scripts/benchmark/run_phase5_external_hebog.py",
        "scripts/benchmark/run_phase5_external_pybdsf.py",
        "scripts/benchmark/run_phase5_external_aegean.py",
    )
    decision = PhaseFiveExternalExecutionDecision.model_validate(
        {
            "schema_version": 1,
            "decision_id": "phase-5-external-execution-decision",
            "status": "reviewed-before-external-output",
            "protocol_sha256": file_sha256(_PROTOCOL),
            "candidate_review_sha256": file_sha256(_BASE_REVIEW),
            "implementation_commit": "0" * 40,
            "source_tree_sha256": source_tree_sha256(_ROOT),
            "hebog_container_image_digest": _CONTAINER_DIGEST,
            "hebog_dependency_inventory_sha256": _SHA256,
            "pybdsf_ncores": 1,
            "runners": [
                {
                    "relative_path": relative_path,
                    "sha256": file_sha256(_ROOT / relative_path),
                }
                for relative_path in runner_paths
            ],
            "named_review": "unit-test-review",
            "decision": "authorize-one-terminal-external-comparison",
            "execution_authorized": True,
            "one_look_opened": False,
            "step_three_authorized": False,
            "optimization_authorized": False,
            "qualification_opened": False,
            "next_action": (
                "execute-complete-frozen-comparison-once-without-opening-"
                "partial-results"
            ),
        }
    )
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(decision.model_dump_json(), encoding="utf-8")
    hebog_runner = _ROOT / runner_paths[0]

    authorized = authorize_external_run(
        protocol_path=_PROTOCOL,
        execution_decision_path=decision_path,
        input_bundle_path=input_path,
        runner_path=hebog_runner,
        finder_id="hebog",
    )

    assert authorized.input_bundle.seed == _COMPACT_SEED
    assert authorized.artifact_path("image").name == "image.fits"
    with pytest.raises(ValueError, match="unexpected external runner"):
        authorize_external_run(
            protocol_path=_PROTOCOL,
            execution_decision_path=decision_path,
            input_bundle_path=input_path,
            runner_path=_ROOT / runner_paths[2],
            finder_id="hebog",
        )
