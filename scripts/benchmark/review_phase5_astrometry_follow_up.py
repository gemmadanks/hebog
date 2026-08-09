"""Run the frozen Phase 5 detected-segment position development review."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import os
import platform
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from hebog.validation.campaign_runtime import (
    canonical_sha256,
    dependency_inventory_sha256,
)
from hebog.validation.contracts import (
    load_phase_five_astrometry_follow_up_review,
    load_phase_five_corrective_a_review,
)
from hebog.validation.datasets import DatasetRole, load_dataset_manifest
from hebog.validation.evidence import (
    DatasetIdentity,
    EvidenceStatus,
    PhaseFiveAstrometryFollowUpDevelopmentEvidence,
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


def _parse_args() -> argparse.Namespace:
    """Parse development-only inputs without a confirmation option."""
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
        "--prior-decision",
        type=Path,
        default=(
            root
            / "config/contracts/phase-5-astrometry-selection-decision.json"
        ),
    )
    parser.add_argument(
        "--development-manifest",
        type=Path,
        default=(
            root / "config/datasets/"
            "phase-5-astrometry-follow-up-development.json"
        ),
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


def main() -> None:
    """Run and persist only the authorized fresh development population."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite development evidence: {arguments.output}"
        )
    protocol = load_phase_five_astrometry_follow_up_review(arguments.protocol)
    base_review = load_phase_five_corrective_a_review(arguments.base_protocol)
    manifest = load_dataset_manifest(arguments.development_manifest)
    if any(
        dataset.role is not DatasetRole.DEVELOPMENT
        for dataset in manifest.datasets
    ):
        raise ValueError("follow-up runner requires development data")
    governed = protocol.dataset_manifests[0]
    manifest_sha256 = _file_sha256(arguments.development_manifest)
    if manifest_sha256 != governed.manifest_sha256:
        raise ValueError("follow-up development manifest checksum changed")
    if (
        _file_sha256(arguments.base_protocol)
        != protocol.base_detection_protocol_sha256
    ):
        raise ValueError("follow-up base detection protocol checksum changed")
    if (
        _file_sha256(arguments.prior_decision)
        != protocol.prior_decision_sha256
    ):
        raise ValueError("follow-up prior decision checksum changed")
    if not protocol.development_execution_authorized:
        raise ValueError("follow-up development execution is not authorized")
    if (
        protocol.independent_human_review_complete
        or protocol.confirmation_execution_authorized
    ):
        raise ValueError("follow-up protocol must keep confirmation sealed")

    observations = evaluate_astrometry_follow_up_population(
        manifest,
        base_review,
    )
    summary = compile_astrometry_follow_up_development(
        observations,
        protocol,
    )
    decision = (
        "eligible-awaiting-human-review"
        if summary.eligible_for_human_review
        else "reject-segment-position"
    )
    environment = _environment()
    first_dataset = manifest.datasets[0]
    evidence = PhaseFiveAstrometryFollowUpDevelopmentEvidence(
        schema_version=1,
        evidence_type="phase-five-astrometry-follow-up-development",
        run_id="phase-five-astrometry-follow-up-development",
        captured_at=datetime.now(UTC),
        status=EvidenceStatus.EXPLORATORY,
        dataset=DatasetIdentity(
            identifier=manifest.manifest_id,
            role=DatasetRole.DEVELOPMENT,
            content_sha256=manifest_sha256,
            shape_yx=first_dataset.recipe.shape_yx,
            workload_class=WorkloadClass.DENSE_EXTENDED,
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
        development_manifest_sha256=manifest_sha256,
        image_count=summary.image_count,
        group_count=summary.group_count,
        bootstrap_resamples=protocol.endpoint.bootstrap_resamples,
        bootstrap_seed=protocol.endpoint.bootstrap_seed,
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
        eligible_for_human_review=summary.eligible_for_human_review,
        decision=decision,
        independent_human_review_complete=False,
        confirmation_execution_authorized=False,
        step_two_c_p_execution_authorized=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(arguments.output, evidence)
    print(arguments.output)
    print(f"decision={evidence.decision}")
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
