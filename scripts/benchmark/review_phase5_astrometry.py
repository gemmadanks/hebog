"""Run the frozen Phase 5 successor astrometry development review."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
    dependency_inventory_sha256,
)
from hebog.validation.contracts import (
    load_phase_five_astrometry_revision_review,
    load_phase_five_corrective_a_review,
)
from hebog.validation.datasets import DatasetRole, load_dataset_manifest
from hebog.validation.evidence import (
    EvidenceStatus,
    PhaseFiveAstrometryCandidateEvidence,
    PhaseFiveAstrometryCoverageEvidence,
    PhaseFiveAstrometryDevelopmentEvidence,
    PhaseFiveAstrometryEndpointEvidence,
    SoftwareIdentity,
    WorkloadClass,
    write_evidence,
)
from hebog.validation.phase_five_astrometry_review import (
    AstrometryCandidateResult,
    AstrometryCoverageResult,
    AstrometryEndpointResult,
    compile_astrometry_development,
    evaluate_astrometry_revision_population,
)

_DEPENDENCIES = ("hebog", "numpy", "pydantic", "scipy")


def _parse_args() -> argparse.Namespace:
    """Parse governed development inputs without admitting confirmation."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=(
            root / "config/contracts/phase-5-astrometry-revision-review.json"
        ),
    )
    parser.add_argument(
        "--base-protocol",
        type=Path,
        default=root / "config/contracts/phase-5-corrective-a-review.json",
    )
    parser.add_argument(
        "--closed-decision",
        type=Path,
        default=root / "config/contracts/phase-5-corrective-a-decision.json",
    )
    parser.add_argument(
        "--development-manifest",
        type=Path,
        default=(root / "config/datasets/phase-5-astrometry-development.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _file_sha256(path: Path) -> str:
    """Return the exact bytes identity of one governed input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_tree_sha256() -> str:
    """Hash every production Python file used by the review."""
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


def _candidate_evidence(
    summary: AstrometryCandidateResult,
    endpoints: tuple[AstrometryEndpointResult, ...],
    coverage: tuple[AstrometryCoverageResult, ...],
) -> PhaseFiveAstrometryCandidateEvidence:
    """Add auditable failure counts to one candidate conclusion."""
    candidate = summary.candidate
    return PhaseFiveAstrometryCandidateEvidence.model_validate(
        {
            **asdict(summary),
            "failed_endpoint_count": sum(
                not item.passed
                for item in endpoints
                if item.candidate == candidate
            ),
            "failed_coverage_count": sum(
                not item.passed
                for item in coverage
                if item.candidate == candidate
            ),
        }
    )


def main() -> None:
    """Run and persist the development-only estimator selection."""
    arguments = _parse_args()
    protocol = load_phase_five_astrometry_revision_review(arguments.protocol)
    base_review = load_phase_five_corrective_a_review(arguments.base_protocol)
    manifest = load_dataset_manifest(arguments.development_manifest)
    if any(
        dataset.role is not DatasetRole.DEVELOPMENT
        for dataset in manifest.datasets
    ):
        raise ValueError(
            "astrometry development runner requires development data"
        )
    governed = protocol.dataset_manifests[0]
    if (
        _file_sha256(arguments.development_manifest)
        != governed.manifest_sha256
    ):
        raise ValueError("astrometry development manifest checksum changed")
    if not protocol.development_execution_authorized:
        raise ValueError("astrometry development execution is not authorized")
    if protocol.confirmation_execution_authorized:
        raise ValueError("development protocol must keep confirmation sealed")
    closed_decision = json.loads(
        arguments.closed_decision.read_text(encoding="utf-8")
    )
    if (
        _file_sha256(arguments.closed_decision)
        != protocol.closed_decision_sha256
    ):
        raise ValueError("closed astrometry decision checksum changed")
    if closed_decision["protocol_sha256"] != _file_sha256(
        arguments.base_protocol
    ):
        raise ValueError("base corrective protocol is not the closed revision")

    observations = evaluate_astrometry_revision_population(
        manifest,
        base_review,
    )
    summary = compile_astrometry_development(observations, protocol)
    candidates = tuple(
        _candidate_evidence(
            candidate,
            summary.endpoints,
            summary.coverage,
        )
        for candidate in summary.candidates
    )
    if summary.selected_candidate == "direct-observable-pixel-centroid":
        decision = "select-direct"
    elif summary.selected_candidate == (
        "covariance-gated-model-assisted-centroid"
    ):
        decision = "select-model"
    else:
        decision = "reject-astrometry-candidates"
    environment = _environment()
    evidence = PhaseFiveAstrometryDevelopmentEvidence(
        schema_version=1,
        evidence_type="phase-five-astrometry-development",
        run_id="phase-five-astrometry-development-selection",
        captured_at=datetime.now(UTC),
        status=EvidenceStatus.REVIEWED,
        dataset=campaign_dataset_identity(manifest.datasets[0]).model_copy(
            update={"workload_class": WorkloadClass.DENSE_EXTENDED}
        ),
        configuration_sha256=canonical_sha256(
            {
                "protocol": protocol.model_dump(mode="json"),
                "base_protocol": base_review.model_dump(mode="json"),
                "manifest": manifest.model_dump(mode="json"),
                "runner_sha256": _file_sha256(Path(__file__)),
            }
        ),
        subject=SoftwareIdentity(
            name="hebog",
            source_tree_sha256=_source_tree_sha256(),
            dependency_inventory_sha256=dependency_inventory_sha256(),
        ),
        environment_sha256=canonical_sha256(environment),
        protocol_sha256=_file_sha256(arguments.protocol),
        base_protocol_sha256=_file_sha256(arguments.base_protocol),
        development_manifest_sha256=_file_sha256(
            arguments.development_manifest
        ),
        image_count=summary.image_count,
        group_count=summary.group_count,
        bootstrap_resamples=protocol.endpoint.bootstrap_resamples,
        bootstrap_seed=protocol.endpoint.bootstrap_seed,
        endpoints=tuple(
            PhaseFiveAstrometryEndpointEvidence.model_validate(asdict(item))
            for item in summary.endpoints
        ),
        coverage=tuple(
            PhaseFiveAstrometryCoverageEvidence.model_validate(asdict(item))
            for item in summary.coverage
        ),
        candidates=candidates,
        decision=decision,
        selected_candidate=summary.selected_candidate,
        confirmation_execution_authorized=(
            summary.confirmation_execution_authorized
        ),
        step_two_c_p_execution_authorized=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(arguments.output, evidence)
    print(arguments.output)
    print(f"decision={evidence.decision}")
    for candidate in evidence.candidates:
        print(
            f"{candidate.candidate}: p95="
            f"{candidate.overall_percentile_95_beams:.6f} "
            f"endpoint_failures={candidate.failed_endpoint_count} "
            f"coverage_failures={candidate.failed_coverage_count}"
        )


if __name__ == "__main__":
    main()
