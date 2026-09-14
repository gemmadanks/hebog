"""Run the authorized one-look Phase 5 segment-position confirmation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import os
import platform
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from hebog.validation.campaign_runtime import (
    canonical_sha256,
    dependency_inventory_sha256,
)
from hebog.validation.contracts import (
    PhaseFiveAstrometryFollowUpDevelopmentDecision,
    PhaseFiveAstrometryFollowUpHumanDecision,
    PhaseFiveAstrometryFollowUpReview,
    PhaseFiveCorrectiveAReview,
    load_phase_five_astrometry_follow_up_development_decision,
    load_phase_five_astrometry_follow_up_human_decision,
    load_phase_five_astrometry_follow_up_review,
    load_phase_five_corrective_a_review,
)
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRole,
    load_dataset_manifest,
)
from hebog.validation.evidence import (
    DatasetIdentity,
    EvidenceStatus,
    PhaseFiveAstrometryFollowUpConfirmationEvidence,
    PhaseFiveAstrometryFollowUpDiagnosticEvidence,
    PhaseFiveAstrometryFollowUpEndpointEvidence,
    SoftwareIdentity,
    WorkloadClass,
    write_evidence,
)
from hebog.validation.phase_five_astrometry_follow_up import (
    compile_astrometry_follow_up_development,
    evaluate_astrometry_follow_up_population,
)

_DEPENDENCIES = ("hebog", "numpy", "pydantic", "scipy")


@dataclass(frozen=True, slots=True)
class _ConfirmationInputs:
    """Validated models and byte identities for one confirmation run."""

    protocol: PhaseFiveAstrometryFollowUpReview
    base_review: PhaseFiveCorrectiveAReview
    development_decision: PhaseFiveAstrometryFollowUpDevelopmentDecision
    human_decision: PhaseFiveAstrometryFollowUpHumanDecision
    manifest: DatasetManifest
    protocol_sha256: str
    base_protocol_sha256: str
    development_decision_sha256: str
    development_evidence_sha256: str
    human_decision_sha256: str
    manifest_sha256: str


def _parse_args() -> argparse.Namespace:
    """Parse only governed one-look confirmation inputs."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=(
            root / "config/contracts/phase-5-astrometry-follow-up-review.json"
        ),
    )
    parser.add_argument(
        "--base-protocol",
        type=Path,
        default=root / "config/contracts/phase-5-corrective-a-review.json",
    )
    parser.add_argument(
        "--development-decision",
        type=Path,
        default=(
            root / "config/contracts/"
            "phase-5-astrometry-follow-up-development-decision.json"
        ),
    )
    parser.add_argument(
        "--development-evidence",
        type=Path,
        default=(
            root / "benchmark-results/phase-5/"
            "astrometry-follow-up-development.json"
        ),
    )
    parser.add_argument(
        "--human-decision",
        type=Path,
        default=(
            root / "config/contracts/"
            "phase-5-astrometry-follow-up-human-decision.json"
        ),
    )
    parser.add_argument(
        "--confirmation-manifest",
        type=Path,
        default=(
            root / "config/datasets/"
            "phase-5-astrometry-follow-up-confirmation.json"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _file_sha256(path: Path) -> str:
    """Return the exact bytes identity of one governed input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_tree_sha256() -> str:
    """Hash every production Python file used by confirmation."""
    digest = hashlib.sha256()
    root = Path(__file__).parents[2]
    for path in sorted((root / "src" / "hebog").rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _environment() -> dict[str, object]:
    """Return the exact local software and platform inventory."""
    return {
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "dependencies": {
            name: importlib.metadata.version(name) for name in _DEPENDENCIES
        },
    }


def _load_inputs(arguments: argparse.Namespace) -> _ConfirmationInputs:
    """Load governed records and calculate their exact byte identities."""
    protocol = load_phase_five_astrometry_follow_up_review(arguments.protocol)
    base_review = load_phase_five_corrective_a_review(arguments.base_protocol)
    development_decision = (
        load_phase_five_astrometry_follow_up_development_decision(
            arguments.development_decision
        )
    )
    human_decision = load_phase_five_astrometry_follow_up_human_decision(
        arguments.human_decision
    )
    manifest = load_dataset_manifest(arguments.confirmation_manifest)
    return _ConfirmationInputs(
        protocol=protocol,
        base_review=base_review,
        development_decision=development_decision,
        human_decision=human_decision,
        manifest=manifest,
        protocol_sha256=_file_sha256(arguments.protocol),
        base_protocol_sha256=_file_sha256(arguments.base_protocol),
        development_decision_sha256=_file_sha256(
            arguments.development_decision
        ),
        development_evidence_sha256=_file_sha256(
            arguments.development_evidence
        ),
        human_decision_sha256=_file_sha256(arguments.human_decision),
        manifest_sha256=_file_sha256(arguments.confirmation_manifest),
    )


def _validate_inputs(inputs: _ConfirmationInputs) -> None:
    """Reject any drift from the approved development and confirmation."""
    if any(
        dataset.role is not DatasetRole.REGRESSION
        for dataset in inputs.manifest.datasets
    ):
        raise ValueError("follow-up confirmation requires regression data")
    identity_checks = (
        (
            inputs.manifest_sha256,
            inputs.protocol.dataset_manifests[1].manifest_sha256,
            "follow-up confirmation manifest checksum changed",
        ),
        (
            inputs.manifest_sha256,
            inputs.human_decision.confirmation_manifest_sha256,
            "human decision does not bind this confirmation",
        ),
        (
            inputs.protocol_sha256,
            inputs.human_decision.protocol_sha256,
            "human decision does not bind this protocol",
        ),
        (
            inputs.base_protocol_sha256,
            inputs.protocol.base_detection_protocol_sha256,
            "follow-up base detection protocol checksum changed",
        ),
        (
            inputs.development_decision_sha256,
            inputs.human_decision.development_decision_sha256,
            "human decision does not bind development decision",
        ),
        (
            inputs.development_evidence_sha256,
            inputs.human_decision.development_evidence_sha256,
            "human decision does not bind development evidence",
        ),
        (
            inputs.development_decision.protocol_sha256,
            inputs.protocol_sha256,
            "development decision does not bind this protocol",
        ),
        (
            inputs.development_decision.evidence_sha256,
            inputs.development_evidence_sha256,
            "development decision evidence checksum changed",
        ),
        (
            inputs.human_decision.candidate,
            inputs.development_decision.selected_candidate,
            "confirmation candidate changed after development",
        ),
        (
            inputs.human_decision.candidate,
            inputs.protocol.estimator.candidate,
            "confirmation candidate changed from frozen protocol",
        ),
    )
    for observed, expected, message in identity_checks:
        if observed != expected:
            raise ValueError(message)
    if not inputs.human_decision.confirmation_execution_authorized:
        raise ValueError("one-look confirmation is not authorized")


def _build_evidence(
    inputs: _ConfirmationInputs,
) -> PhaseFiveAstrometryFollowUpConfirmationEvidence:
    """Evaluate the sealed population and build raw one-look evidence."""
    observations = evaluate_astrometry_follow_up_population(
        inputs.manifest,
        inputs.base_review,
    )
    summary = compile_astrometry_follow_up_development(
        observations,
        inputs.protocol,
    )
    result = (
        "pass-awaiting-reviewed-decision"
        if summary.eligible_for_human_review
        else "reject-confirmation"
    )
    environment = _environment()
    first_dataset = inputs.manifest.datasets[0]
    return PhaseFiveAstrometryFollowUpConfirmationEvidence(
        schema_version=1,
        evidence_type="phase-five-astrometry-follow-up-confirmation",
        run_id="phase-five-astrometry-follow-up-confirmation",
        captured_at=datetime.now(UTC),
        status=EvidenceStatus.EXPLORATORY,
        dataset=DatasetIdentity(
            identifier=inputs.manifest.manifest_id,
            role=DatasetRole.REGRESSION,
            content_sha256=inputs.manifest_sha256,
            shape_yx=first_dataset.recipe.shape_yx,
            workload_class=WorkloadClass.DENSE_EXTENDED,
        ),
        configuration_sha256=canonical_sha256(
            {
                "protocol": inputs.protocol.model_dump(mode="json"),
                "base_protocol": inputs.base_review.model_dump(mode="json"),
                "development_decision": (
                    inputs.development_decision.model_dump(mode="json")
                ),
                "human_decision": inputs.human_decision.model_dump(
                    mode="json"
                ),
                "manifest": inputs.manifest.model_dump(mode="json"),
                "runner_sha256": _file_sha256(Path(__file__)),
            }
        ),
        subject=SoftwareIdentity(
            name="hebog",
            source_tree_sha256=_source_tree_sha256(),
            dependency_inventory_sha256=dependency_inventory_sha256(),
        ),
        environment_sha256=canonical_sha256(environment),
        protocol_sha256=inputs.protocol_sha256,
        base_protocol_sha256=inputs.base_protocol_sha256,
        human_decision_sha256=inputs.human_decision_sha256,
        development_decision_sha256=inputs.development_decision_sha256,
        development_evidence_sha256=inputs.development_evidence_sha256,
        confirmation_manifest_sha256=inputs.manifest_sha256,
        image_count=summary.image_count,
        group_count=summary.group_count,
        bootstrap_resamples=inputs.protocol.endpoint.bootstrap_resamples,
        bootstrap_seed=inputs.protocol.endpoint.bootstrap_seed,
        candidate="original-pixel-detected-segment-centroid",
        endpoints=tuple(
            PhaseFiveAstrometryFollowUpEndpointEvidence.model_validate(
                {
                    "candidate": ("original-pixel-detected-segment-centroid"),
                    **asdict(item),
                }
            )
            for item in summary.endpoints
        ),
        diagnostics=tuple(
            PhaseFiveAstrometryFollowUpDiagnosticEvidence.model_validate(
                asdict(item)
            )
            for item in summary.diagnostics
        ),
        failed_endpoint_count=sum(
            not item.passed for item in summary.endpoints
        ),
        confirmation_result=result,
        independent_human_scientific_review_complete=True,
        confirmation_one_look_complete=True,
        development_tuning_after_confirmation=False,
        step_two_c_p_execution_authorized=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )


def main() -> None:
    """Validate authorization and execute the sealed population once."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite confirmation evidence: {arguments.output}"
        )
    inputs = _load_inputs(arguments)
    _validate_inputs(inputs)
    evidence = _build_evidence(inputs)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(arguments.output, evidence)
    print(arguments.output)
    print(f"confirmation_result={evidence.confirmation_result}")
    print(f"failed_endpoints={evidence.failed_endpoint_count}")
    for endpoint in evidence.endpoints:
        if endpoint.stratum == "overall":
            print(
                f"overall/{endpoint.metric}: estimate={endpoint.estimate:.6f} "
                f"bound={endpoint.confidence_bound:.6f} "
                f"limit={endpoint.limit:.6f} passed={endpoint.passed}"
            )


if __name__ == "__main__":
    main()
