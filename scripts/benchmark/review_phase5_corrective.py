"""Run the frozen Phase 5 Step 2C corrective continuum review."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np

from hebog.algorithms.multiscale import (
    BeamShapePixels,
    FilterFamily,
    build_residual_atrous_plan,
    build_scale_filter_bank,
)
from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
    dependency_inventory_sha256,
)
from hebog.validation.contracts import (
    PhaseFiveCorrectiveAReview,
    PhaseFiveCorrectiveReview,
    PhaseFiveCorrectiveRReview,
    load_phase_five_corrective_a_review,
    load_phase_five_corrective_r_review,
    load_phase_five_corrective_review,
)
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    DatasetRole,
    load_dataset_manifest,
)
from hebog.validation.evidence import (
    EvidenceStatus,
    PhaseFiveAstrometryDiagnostic,
    PhaseFiveAstrometryEstimatorDiagnostic,
    PhaseFiveCorrectiveAReviewEvidence,
    PhaseFiveCorrectiveReviewEvidence,
    PhaseFiveCorrectiveRReviewEvidence,
    PhaseFiveMeasurementDispositionDiagnostic,
    SoftwareIdentity,
    WorkloadClass,
    write_evidence,
)
from hebog.validation.phase_five_filter_analysis import (
    FilterReviewDatasets,
    FilterReviewObservations,
    compile_filter_review,
)
from hebog.validation.phase_five_filter_review import (
    GeneratedImageObservation,
    build_analytic_review_cases,
    evaluate_corrective_analytic_cases,
    evaluate_corrective_generated_population,
)

_DEPENDENCIES = ("hebog", "numpy", "pydantic", "scipy")
_SCALES = ((1, 1.0), (2, 2.0), (3, 4.0))


def _load_review(
    path: Path,
) -> (
    PhaseFiveCorrectiveReview
    | PhaseFiveCorrectiveRReview
    | PhaseFiveCorrectiveAReview
):
    """Load one supported corrective protocol by its governed identity."""
    protocol_id = json.loads(path.read_text(encoding="utf-8")).get(
        "contract_id"
    )
    if protocol_id == "phase-5-corrective-a-review":
        return load_phase_five_corrective_a_review(path)
    if protocol_id == "phase-5-corrective-r-review":
        return load_phase_five_corrective_r_review(path)
    if protocol_id == "phase-5-corrective-review":
        return load_phase_five_corrective_review(path)
    raise ValueError("unsupported corrective-review protocol")


def _evidence_definition(
    review: (
        PhaseFiveCorrectiveReview
        | PhaseFiveCorrectiveRReview
        | PhaseFiveCorrectiveAReview
    ),
) -> tuple[
    type[PhaseFiveCorrectiveReviewEvidence]
    | type[PhaseFiveCorrectiveRReviewEvidence]
    | type[PhaseFiveCorrectiveAReviewEvidence],
    str,
    str,
]:
    """Return the schema, type identity, and run identity for a review."""
    if isinstance(review, PhaseFiveCorrectiveAReview):
        return (
            PhaseFiveCorrectiveAReviewEvidence,
            "phase-five-corrective-a-review",
            "phase-five-corrective-a-review-confirmation",
        )
    if isinstance(review, PhaseFiveCorrectiveRReview):
        return (
            PhaseFiveCorrectiveRReviewEvidence,
            "phase-five-corrective-r-review",
            "phase-five-corrective-r-review-regression",
        )
    return (
        PhaseFiveCorrectiveReviewEvidence,
        "phase-five-corrective-review",
        "phase-five-corrective-review-regression",
    )


def _review_diagnostics(
    review: (
        PhaseFiveCorrectiveReview
        | PhaseFiveCorrectiveRReview
        | PhaseFiveCorrectiveAReview
    ),
    observations: tuple[GeneratedImageObservation, ...],
    dataset: DatasetRecord,
) -> dict[str, object]:
    """Build only diagnostics declared by the active review schema."""
    diagnostics: dict[str, object] = {}
    if isinstance(
        review, (PhaseFiveCorrectiveRReview, PhaseFiveCorrectiveAReview)
    ):
        diagnostics.update(
            astrometry_diagnostics=_astrometry_diagnostics(
                observations, dataset
            ),
            measurement_dispositions=_measurement_dispositions(observations),
        )
    if isinstance(review, PhaseFiveCorrectiveAReview):
        diagnostics["astrometry_estimator_diagnostics"] = (
            _astrometry_estimator_diagnostics(observations, dataset)
        )
    return diagnostics


def _astrometry_diagnostics(
    observations: tuple[GeneratedImageObservation, ...],
    dataset: DatasetRecord,
) -> tuple[PhaseFiveAstrometryDiagnostic, ...]:
    """Separate regression astrometry bias from centred seed scatter."""
    astronomical = frozenset(
        group.identifier
        for group in dataset.multiscale_truth_groups
        if group.catalogue_role == "astronomical-source"
    )
    strata = (
        ("overall", astronomical),
        *(
            (
                stratum.identifier,
                frozenset(stratum.group_identifiers) & astronomical,
            )
            for stratum in dataset.multiscale_group_strata
        ),
    )
    diagnostics: list[PhaseFiveAstrometryDiagnostic] = []
    for family in ("beam-aware-matched-filter", "residual-b3-atrous"):
        family_observations = tuple(
            item for item in observations if item.family == family
        )
        for stratum, identifiers in strata:
            offsets = np.asarray(
                [
                    group.position_offset_xy_beams
                    for observation in family_observations
                    for group in observation.groups
                    if group.group_identifier in identifiers
                    and group.position_offset_xy_beams is not None
                ],
                dtype=np.float64,
            )
            if offsets.size == 0:
                continue
            mean = np.mean(offsets, axis=0)
            centred = offsets - mean
            diagnostics.append(
                PhaseFiveAstrometryDiagnostic(
                    family=family,
                    stratum=stratum,
                    sample_count=len(offsets),
                    mean_offset_xy_beams=(float(mean[0]), float(mean[1])),
                    bias_beams=float(np.linalg.norm(mean)),
                    centred_percentile_95_beams=float(
                        np.percentile(np.linalg.norm(centred, axis=1), 95)
                    ),
                    radial_percentile_95_beams=float(
                        np.percentile(np.linalg.norm(offsets, axis=1), 95)
                    ),
                )
            )
    return tuple(diagnostics)


def _measurement_dispositions(
    observations: tuple[GeneratedImageObservation, ...],
) -> tuple[PhaseFiveMeasurementDispositionDiagnostic, ...]:
    """Count each typed measurement outcome in regression."""
    diagnostics: list[PhaseFiveMeasurementDispositionDiagnostic] = []
    for family in ("beam-aware-matched-filter", "residual-b3-atrous"):
        counts: Counter[
            Literal[
                "measured",
                "known-artifact-control",
                "truncated-observable-domain",
            ]
        ] = Counter(
            group.measurement_disposition
            for observation in observations
            if observation.family == family
            for group in observation.groups
        )
        diagnostics.extend(
            PhaseFiveMeasurementDispositionDiagnostic(
                family=family,
                disposition=disposition,
                count=count,
            )
            for disposition, count in sorted(counts.items())
        )
    return tuple(diagnostics)


def _astrometry_estimator_diagnostics(
    observations: tuple[GeneratedImageObservation, ...],
    dataset: DatasetRecord,
) -> tuple[PhaseFiveAstrometryEstimatorDiagnostic, ...]:
    """Summarize model availability and uncertainty without hiding rows."""
    astronomical = frozenset(
        group.identifier
        for group in dataset.multiscale_truth_groups
        if group.catalogue_role == "astronomical-source"
    )
    strata = (
        ("overall", astronomical),
        *(
            (
                stratum.identifier,
                frozenset(stratum.group_identifiers) & astronomical,
            )
            for stratum in dataset.multiscale_group_strata
        ),
    )
    diagnostics: list[PhaseFiveAstrometryEstimatorDiagnostic] = []
    for family in ("beam-aware-matched-filter", "residual-b3-atrous"):
        family_observations = tuple(
            item for item in observations if item.family == family
        )
        for stratum, identifiers in strata:
            groups = tuple(
                group
                for observation in family_observations
                for group in observation.groups
                if group.group_identifier in identifiers
            )
            if not groups:
                continue
            available = tuple(
                group for group in groups if group.position_estimator_available
            )
            uncertainties = np.asarray(
                [group.position_uncertainty_beams for group in available],
                dtype=np.float64,
            )
            errors = np.asarray(
                [group.position_error_beams for group in available],
                dtype=np.float64,
            )
            if uncertainties.size == 0 or not np.all(
                np.isfinite(uncertainties)
            ):
                raise ValueError(
                    f"Step 2C-A astrometry unavailable for {family}/{stratum}"
                )
            methods = Counter(group.position_estimator for group in available)
            diagnostics.append(
                PhaseFiveAstrometryEstimatorDiagnostic(
                    family=family,
                    stratum=stratum,
                    sample_count=len(groups),
                    available_count=len(available),
                    model_assisted_count=methods["model-assisted-shrinkage"],
                    fallback_count=methods[
                        "robust-observable-moment-fallback"
                    ],
                    median_uncertainty_beams=float(np.median(uncertainties)),
                    percentile_95_uncertainty_beams=float(
                        np.percentile(uncertainties, 95)
                    ),
                    percentile_95_error_to_uncertainty_ratio=float(
                        np.percentile(errors / uncertainties, 95)
                    ),
                )
            )
    return tuple(diagnostics)


def _parse_args() -> argparse.Namespace:
    """Parse governed inputs without admitting qualification data."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=root / "config/contracts/phase-5-corrective-review.json",
    )
    parser.add_argument(
        "--development-manifest",
        type=Path,
        default=root / "config/datasets/phase-5-development.json",
    )
    parser.add_argument(
        "--regression-manifest",
        type=Path,
        default=root / "config/datasets/phase-5-regression.json",
    )
    parser.add_argument(
        "--prior-decision",
        type=Path,
        default=(
            root / "config/contracts/phase-5-filter-paired-decision.json"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _file_sha256(path: Path) -> str:
    """Return the exact bytes identity of one governed input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_tree_sha256() -> str:
    """Hash all production Python used by this uncommitted review."""
    digest = hashlib.sha256()
    root = Path(__file__).parents[2]
    for path in sorted((root / "src" / "hebog").rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _environment() -> dict[str, object]:
    """Return the local environment identity used for the review."""
    return {
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "dependencies": {
            name: importlib.metadata.version(name) for name in _DEPENDENCIES
        },
    }


def _single_dataset(
    path: Path, role: DatasetRole
) -> tuple[DatasetManifest, DatasetRecord]:
    """Load exactly one governed dataset with the expected role."""
    manifest = load_dataset_manifest(path)
    if len(manifest.datasets) != 1:
        raise ValueError("corrective review requires one dataset per manifest")
    dataset = manifest.datasets[0]
    if dataset.role is not role:
        raise ValueError(f"corrective review expected {role.value} data")
    return manifest, dataset


def main() -> None:
    """Evaluate the comparator and corrective candidate fail-closed."""
    args = _parse_args()
    review = _load_review(args.protocol)
    development_manifest, development_dataset = _single_dataset(
        args.development_manifest, DatasetRole.DEVELOPMENT
    )
    regression_manifest, regression_dataset = _single_dataset(
        args.regression_manifest, DatasetRole.REGRESSION
    )
    for governed, path in zip(
        review.dataset_manifests,
        (args.development_manifest, args.regression_manifest),
        strict=True,
    ):
        if _file_sha256(path) != governed.manifest_sha256:
            raise ValueError(
                f"corrective-review manifest checksum changed: {path}"
            )
    if _file_sha256(args.prior_decision) != review.prior_decision_sha256:
        raise ValueError("corrective-review prior decision checksum changed")
    if review.qualification_opened or review.step_three_authorized:
        raise ValueError(
            "frozen review must keep qualification and Step 3 closed"
        )

    beam = BeamShapePixels(
        regression_dataset.beam.major_fwhm_pixels,
        regression_dataset.beam.minor_fwhm_pixels,
        regression_dataset.beam.position_angle_degrees,
    )
    analytic_cases = build_analytic_review_cases(beam, review)
    analytic = evaluate_corrective_analytic_cases(analytic_cases, beam, review)
    print(f"analytic_cases={len(analytic_cases)}")
    development = evaluate_corrective_generated_population(
        development_dataset, review
    )
    print(f"development_images={len(development) // len(review.candidates)}")
    regression = evaluate_corrective_generated_population(
        regression_dataset, review
    )
    print(f"regression_images={len(regression) // len(review.candidates)}")

    matched = build_scale_filter_bank(
        beam,
        family="beam-aware-matched-filter",
        scales=_SCALES,
        truncation_sigma=4.0,
        noise_correlation=beam,
    )
    atrous = build_residual_atrous_plan(beam, noise_correlation=beam)
    bounded_costs: dict[FilterFamily, tuple[int, int, int]] = {
        "beam-aware-matched-filter": (
            matched.convolution_count_per_evaluation,
            matched.temporary_plane_count,
            matched.maximum_halo_pixels,
        ),
        "residual-b3-atrous": (
            matched.convolution_count_per_evaluation
            + atrous.convolution_count_per_evaluation,
            max(
                matched.temporary_plane_count,
                atrous.temporary_plane_count,
            ),
            max(matched.maximum_halo_pixels, atrous.maximum_halo_pixels),
        ),
    }
    compiled = compile_filter_review(
        FilterReviewObservations(
            analytic=analytic,
            development=development,
            regression=regression,
        ),
        FilterReviewDatasets(
            development=development_dataset,
            regression=regression_dataset,
        ),
        review,
        bounded_costs=bounded_costs,
    )
    corrective = compiled.candidates[1]
    authorized = corrective.passes_absolute and (
        corrective.noninferior_to_other
    )
    environment = _environment()
    evidence_model, evidence_type, run_id = _evidence_definition(review)
    diagnostics = _review_diagnostics(review, regression, regression_dataset)
    evidence_payload: dict[str, object] = {
        "schema_version": 1,
        "evidence_type": evidence_type,
        "run_id": run_id,
        "captured_at": datetime.now(UTC),
        "status": EvidenceStatus.REVIEWED,
        "dataset": campaign_dataset_identity(regression_dataset).model_copy(
            update={"workload_class": WorkloadClass.DENSE_EXTENDED}
        ),
        "configuration_sha256": canonical_sha256(
            {
                "protocol": review.model_dump(mode="json"),
                "runner_sha256": _file_sha256(Path(__file__)),
                "development_manifest": development_manifest.model_dump(
                    mode="json"
                ),
                "regression_manifest": regression_manifest.model_dump(
                    mode="json"
                ),
            }
        ),
        "subject": SoftwareIdentity(
            name="hebog",
            source_tree_sha256=_source_tree_sha256(),
            dependency_inventory_sha256=dependency_inventory_sha256(),
        ),
        "environment_sha256": canonical_sha256(environment),
        "protocol_sha256": _file_sha256(args.protocol),
        "prior_decision_sha256": _file_sha256(args.prior_decision),
        "development_manifest_sha256": _file_sha256(args.development_manifest),
        "regression_manifest_sha256": _file_sha256(args.regression_manifest),
        "analytic_case_count": len(analytic_cases),
        "development_image_count": len(development) // len(review.candidates),
        "regression_image_count": len(regression) // len(review.candidates),
        "bootstrap_resamples": review.statistical_design.bootstrap_resamples,
        "bootstrap_seed": review.statistical_design.bootstrap_seed,
        "endpoints": compiled.endpoints,
        "paired_endpoints": compiled.paired_endpoints,
        "candidates": compiled.candidates,
        "decision": (
            "authorize-corrective" if authorized else "reject-corrective"
        ),
        "selected_family": "residual-b3-atrous" if authorized else None,
        "step_three_authorized": authorized,
        "qualification_opened": False,
        **diagnostics,
    }
    evidence = evidence_model.model_validate(evidence_payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(args.output, evidence)
    print(args.output)
    print(f"decision={evidence.decision}")
    for candidate in evidence.candidates:
        print(
            f"{candidate.family}: absolute_failures="
            f"{candidate.failed_absolute_endpoint_count} "
            f"paired_failures={candidate.failed_paired_endpoint_count}"
        )


if __name__ == "__main__":
    main()
