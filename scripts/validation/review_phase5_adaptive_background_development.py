#!/usr/bin/env python3
"""Freeze the non-executable Phase 5 adaptive-background development review."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from hebog.validation.adaptive_background_development import (
    build_adaptive_development_matrix,
)
from hebog.validation.datasets import (
    DatasetManifest,
    iter_dataset_recipes,
)
from hebog.validation.external_runners import canonical_sha256, file_sha256

_PUBLIC_IDENTITY_PATH = Path(
    "config/contracts/phase-5-public-interface-identity-review.json"
)
_PUBLIC_IDENTITY_SHA256 = (
    "a521c656683cdae8b8d2250a3d29dee716c4ff774a25e23556301b21e5d898f8"
)
_EXISTING_CONTINUUM_PATH = Path(
    "config/datasets/phase-5-external-post-failure-continuum.json"
)
_EXISTING_CONTINUUM_SHA256 = (
    "4ce811e8aebc26b858473eb4473abba1b3bb5a916acb2ee6b645441723322e77"
)
_RETENTION_REVIEW_PATH = Path(
    "config/contracts/phase-5-final-retention-confirmation-pre-review.json"
)
_RETENTION_REVIEW_SHA256 = (
    "913276423c5a93572ac48f18ab00ad9e13d18c21007a973284acbf7d3cbc3c21"
)
_ENDPOINT_REGISTRY_PATH = Path(
    "config/contracts/phase-5-prospective-science-endpoint-registry.json"
)
_ENDPOINT_REGISTRY_SHA256 = (
    "095354bce2f34ae257574f9168770a194f1f5b00024db0ec5bcafdafba006a7e"
)
_CANDIDATE_REVISION = "937737d811dd229d71dbcfdbda6cb5829de6faca"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_CLOSED_PAIRED_DECISION_SHA256 = (
    "5bced80488199696382233d8b0d513a83922d35cdee605c8e638798ef8f6faf4"
)
_ADAPTIVE_TRIGGER_SIGMA = 75.0
_IMAGE_COUNT = 144
_CANDIDATE_EXECUTIONS = 144
_COARSE_CONTROL_EXECUTIONS = 144
_DASK_REEXECUTIONS = 12
_FULL_REPLAY_CANDIDATE_EXECUTIONS = 2_400


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _mapping(value: object, *, label: str) -> dict[str, object]:
    """Require one nested JSON-like mapping."""
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return cast(dict[str, object], value)


def _require_file(path: Path, expected_sha256: str, *, label: str) -> None:
    """Fail closed when one prospective source binding changes."""
    if file_sha256(path) != expected_sha256:
        raise ValueError(f"{label} identity changed")


def _existing_coverage_gap(manifest: DatasetManifest) -> dict[str, object]:
    """Measure the trigger gap from analytic inputs without finder output."""
    brightest_by_dataset: list[dict[str, object]] = []
    shell_component_sigma: list[float] = []
    for dataset in manifest.datasets:
        rms = dataset.recipe.noise_rms
        if rms <= 0:
            raise ValueError("existing Continuum RMS must be positive")
        component_sigmas = tuple(
            source.peak_flux_jy_per_beam / rms
            for source in dataset.recipe.sources
        )
        shell_groups = tuple(
            group
            for group in dataset.multiscale_truth_groups
            if group.morphology == "shell"
        )
        if len(shell_groups) != 1:
            raise ValueError("each Continuum geometry requires one shell")
        shell_component_sigma.extend(
            component_sigmas[index] for index in shell_groups[0].source_indices
        )
        brightest_by_dataset.append(
            {
                "dataset_identifier": dataset.identifier,
                "brightest_component_sigma": max(component_sigmas),
                "shell_component_sigma_minimum": min(
                    component_sigmas[index]
                    for index in shell_groups[0].source_indices
                ),
                "shell_component_sigma_maximum": max(
                    component_sigmas[index]
                    for index in shell_groups[0].source_indices
                ),
            }
        )
    brightest = tuple(
        cast(float, row["brightest_component_sigma"])
        for row in brightest_by_dataset
    )
    crosses = max(brightest) > _ADAPTIVE_TRIGGER_SIGMA
    if crosses:
        raise ValueError("existing population unexpectedly crosses trigger")
    return {
        "adaptive_trigger_sigma": _ADAPTIVE_TRIGGER_SIGMA,
        "audit_basis": (
            "analytic input component peaks divided by each recipe's nominal "
            "noise RMS; no finder output was opened or rescored"
        ),
        "brightest_component_sigma_range": [min(brightest), max(brightest)],
        "dataset_audit": brightest_by_dataset,
        "existing_population_crosses_trigger": crosses,
        "shell_component_sigma_range": [
            min(shell_component_sigma),
            max(shell_component_sigma),
        ],
    }


def _historical_seed_audit(
    root: Path,
    prospective_seeds: tuple[int, ...],
) -> dict[str, object]:
    """Prove that every planned development realization is new."""
    historical_seeds: set[int] = set()
    manifest_records: list[dict[str, object]] = []
    for path in sorted((root / "config/datasets").glob("*.json")):
        manifest = DatasetManifest.model_validate_json(path.read_bytes())
        manifest_seeds = {
            recipe.seed
            for dataset in manifest.datasets
            for recipe in iter_dataset_recipes(dataset)
        }
        if historical_seeds.intersection(manifest_seeds):
            raise ValueError("checked-in historical dataset seeds overlap")
        historical_seeds.update(manifest_seeds)
        manifest_records.append(
            {
                "path": str(path.relative_to(root)),
                "seed_count": len(manifest_seeds),
                "sha256": file_sha256(path),
            }
        )
    if len(prospective_seeds) != len(set(prospective_seeds)):
        raise ValueError("prospective development seeds overlap")
    overlap = historical_seeds.intersection(prospective_seeds)
    if overlap:
        raise ValueError("prospective seeds overlap historical datasets")
    return {
        "historical_manifest_count": len(manifest_records),
        "historical_seed_count": len(historical_seeds),
        "historical_registry_canonical_sha256": canonical_sha256(
            manifest_records
        ),
        "prospective_seed_count": len(prospective_seeds),
        "seed_disjoint": True,
    }


def _validate_public_identity(identity: dict[str, Any]) -> None:
    """Require the exact candidate and already closed comparison evidence."""
    candidate = _mapping(
        identity.get("algorithm_candidate"),
        label="public candidate identity",
    )
    expected = {
        "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
    }
    if candidate != expected:
        raise ValueError("public candidate identity changed")
    evidence = _mapping(
        identity.get("paired_regression_evidence"),
        label="closed paired evidence",
    )
    if (
        evidence.get("file_sha256") != _CLOSED_PAIRED_DECISION_SHA256
        or evidence.get("all_dual_pybdsf_comparisons_pass") is not True
        or evidence.get("failed_incumbent_retention_comparisons") != 0
    ):
        raise ValueError("closed paired evidence identity or status changed")
    if identity.get("status") != "frozen-non-executable":
        raise ValueError("public interface review status changed")


def _geometry_specification() -> dict[str, object]:
    """Return the fixed source, observing, and placement construction rules."""
    return {
        "beams": {
            "beam-a": {
                "major_fwhm_pixels": 5.4,
                "minor_fwhm_pixels": 3.6,
                "position_angle_degrees": 31.0,
            },
            "beam-b": {
                "major_fwhm_pixels": 6.3,
                "minor_fwhm_pixels": 4.0,
                "position_angle_degrees": 68.0,
            },
        },
        "generator": "hebog.synthetic.gaussian-noise-v3",
        "morphologies": {
            "curved-filament": (
                "seven equal beam-convolved Gaussian knots on a 120-degree "
                "arc, with adjacent centres no farther than 1.25 major beams"
            ),
            "mixed-compact-extended": (
                "one restoring-beam core plus one co-centred elliptical halo; "
                "the halo contains 75% of integrated truth brightness"
            ),
            "shell": (
                "eight equal beam-convolved Gaussian knots uniformly spaced "
                "on a ring whose diameter is the declared major extent"
            ),
        },
        "noise": {
            "correlation_fwhm": "equal-to-restoring-beam",
            "flat": [0.0, 0.0],
            "nominal_rms_jy_per_beam": 0.0002,
            "varying": [0.4, -0.2],
        },
        "placements_xy": {
            "interior": [181.0, 173.0],
            "tile-corner": [256.0, 256.0],
        },
        "source_content": "one isolated governed truth group per image",
        "truth_support": (
            "finite pixels where the noiseless summed source contribution is "
            "at least three times the analytic local true RMS"
        ),
        "wcs": {
            "frame": "icrs",
            "pixel_scale_degrees_xy": [-0.0004, 0.0004],
            "rotation_degrees_counterclockwise": 23.0,
        },
    }


def build_review(root: Path) -> dict[str, object]:
    """Build the deterministic pre-result scientific review."""
    public_identity_path = root / _PUBLIC_IDENTITY_PATH
    existing_continuum_path = root / _EXISTING_CONTINUUM_PATH
    retention_review_path = root / _RETENTION_REVIEW_PATH
    endpoint_registry_path = root / _ENDPOINT_REGISTRY_PATH
    for path, expected, label in (
        (
            public_identity_path,
            _PUBLIC_IDENTITY_SHA256,
            "public interface review",
        ),
        (
            existing_continuum_path,
            _EXISTING_CONTINUUM_SHA256,
            "existing Continuum manifest",
        ),
        (
            retention_review_path,
            _RETENTION_REVIEW_SHA256,
            "retention pre-review",
        ),
        (
            endpoint_registry_path,
            _ENDPOINT_REGISTRY_SHA256,
            "prospective endpoint registry",
        ),
    ):
        _require_file(path, expected, label=label)

    identity = _json_object(public_identity_path, label="public identity")
    _validate_public_identity(identity)
    existing_manifest = DatasetManifest.model_validate_json(
        existing_continuum_path.read_bytes()
    )
    matrix = build_adaptive_development_matrix()
    seeds = tuple(seed for cell in matrix for seed in cell.noise_seeds)
    seed_audit = _historical_seed_audit(root, seeds)
    matrix_rows: list[dict[str, object]] = []
    for cell in matrix:
        row = cast(dict[str, object], asdict(cell))
        row["noise_seeds"] = list(cell.noise_seeds)
        matrix_rows.append(row)
    total_executions = (
        _CANDIDATE_EXECUTIONS + _COARSE_CONTROL_EXECUTIONS + _DASK_REEXECUTIONS
    )
    return {
        "authorization": {
            "candidate_execution_authorized": False,
            "coarse_control_execution_authorized": False,
            "cutover_authorized": False,
            "fresh_qualification_authorized": False,
            "optimization_authorized": False,
            "pybdsf_execution_authorized": False,
            "release_authorized": False,
            "replay_authorized": False,
            "rescoring_authorized": False,
            "source_finding_change_authorized": False,
            "threshold_or_margin_tuning_authorized": False,
            "viewed_data_execution_authorized": False,
        },
        "candidate_binding": {
            "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
            "revision": _CANDIDATE_REVISION,
            "scientific_composition": identity["scientific_composition"],
            "scientific_composition_sha256": identity[
                "scientific_composition_sha256"
            ],
            "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        },
        "comparators": {
            "candidate_path": (
                "exact frozen continuum candidate through hebog.find_sources"
            ),
            "coarse_control_path": (
                "same inputs and exact candidate science with only adaptive "
                "background/RMS refinement disabled; diagnostic, never a "
                "replacement candidate"
            ),
            "pybdsf_execution_required": False,
            "rationale": (
                "analytic truth and a paired one-factor counterfactual answer "
                "the local self-absorption question; final qualification "
                "retains both PyBDSF comparators"
            ),
        },
        "decision_policy": {
            "aggregation": (
                "evaluate every trigger-independent geometry separately; "
                "never pool a passing morphology over a failing one"
            ),
            "hard_truth_safety_floors": {
                "completeness_minimum": 1.0,
                "integrated_flux_absolute_fractional_error_median_maximum": (
                    0.10
                ),
                "integrated_flux_absolute_fractional_error_p95_maximum": 0.25,
                "mask_iou_cell_median_minimum": 0.75,
                "mask_iou_image_minimum": 0.60,
                "split_fraction_maximum": 0.25,
                "support_recall_cell_median_minimum": 0.90,
                "support_recall_image_minimum": 0.75,
            },
            "paired_adaptive_vs_coarse_margins": {
                "completeness": 0.02,
                "integrated_flux_absolute_fractional_error": 0.05,
                "mask_iou": 0.05,
                "split_fraction": 0.02,
                "support_recall": 0.05,
            },
            "pass_claim": (
                "development-risk-closed-not-qualification-or-release-readiness"
            ),
            "required_result": (
                "all product-validity, trigger-seam, hard-floor, "
                "paired-margin, "
                "and executor-invariance checks pass"
            ),
            "root_cause_sentinels": {
                "background_error": (
                    "median and p95 absolute estimated-minus-true background "
                    "inside truth support, in local true-RMS units"
                ),
                "rms_error": (
                    "median and p95 estimated-minus-true RMS inside truth "
                    "support, divided by local true RMS"
                ),
                "role": (
                    "binding diagnosis retention; values cannot waive a hard "
                    "truth floor or paired margin"
                ),
            },
            "trade_off_rule": {
                "hard_floor_waiver_allowed": False,
                "paired_movement": (
                    "movement inside every predeclared practical margin is "
                    "acceptable; movement outside any margin fails even if a "
                    "different metric improves"
                ),
                "post_result_rule_change_allowed": False,
            },
            "trigger_seam": {
                "above": (
                    "all 90-sigma realizations must activate at least one "
                    "adaptive region intersecting the truth group"
                ),
                "below": (
                    "all 60-sigma realizations must remain below the strict "
                    "75-sigma adaptive candidate threshold"
                ),
                "boundary": (
                    "75-sigma activation frequency is retained as non-binding "
                    "threshold-stability evidence"
                ),
                "retained_measurement": (
                    "maximum pre-adaptive coarse-normalized residual and "
                    "exact "
                    "adaptive candidate positions for every image"
                ),
            },
        },
        "evidence_bindings": {
            "closed_paired_decision_sha256": _CLOSED_PAIRED_DECISION_SHA256,
            "design_module": {
                "path": (
                    "src/hebog/validation/adaptive_background_development.py"
                ),
                "sha256": file_sha256(
                    root / "src/hebog/validation/"
                    "adaptive_background_development.py"
                ),
            },
            "existing_continuum_manifest": {
                "path": str(_EXISTING_CONTINUUM_PATH),
                "sha256": _EXISTING_CONTINUUM_SHA256,
            },
            "final_retention_pre_review": {
                "path": str(_RETENTION_REVIEW_PATH),
                "sha256": _RETENTION_REVIEW_SHA256,
            },
            "prospective_endpoint_registry": {
                "path": str(_ENDPOINT_REGISTRY_PATH),
                "sha256": _ENDPOINT_REGISTRY_SHA256,
            },
            "public_interface_review": {
                "path": str(_PUBLIC_IDENTITY_PATH),
                "sha256": _PUBLIC_IDENTITY_SHA256,
            },
            "review_program": {
                "path": (
                    "scripts/validation/"
                    "review_phase5_adaptive_background_development.py"
                ),
                "sha256": file_sha256(
                    root / "scripts/validation/"
                    "review_phase5_adaptive_background_development.py"
                ),
            },
        },
        "implementation_requirements": [
            (
                "freeze the exact generator, manifest, compiler, evaluator, "
                "public facade, internal coarse-control adapter, and runtime "
                "identities"
            ),
            (
                "calibrate noiseless composite templates to the nominal "
                "trigger targets before adding noise and retain the realized "
                "pre-adaptive trigger measurement"
            ),
            (
                "prove all 144 seeds remain disjoint immediately before "
                "freezing the population"
            ),
            (
                "exercise candidate publication through hebog.find_sources "
                "and keep the coarse-only control outside public product "
                "claims"
            ),
            (
                "retain array-free per-image truth, trigger, background, RMS, "
                "support, catalogue, flux, and provenance summaries"
            ),
            (
                "prove Serial versus caller-owned existing-Dask equivalence "
                "on one above-trigger realization from every geometry"
            ),
            (
                "run a complete no-write preflight before requesting one-use "
                "development-lane execution approval"
            ),
            (
                "publish one atomic terminal development decision without "
                "overwriting or adaptive reruns"
            ),
        ],
        "known_coverage_gap": _existing_coverage_gap(existing_manifest),
        "population": {
            "candidate_executions": _CANDIDATE_EXECUTIONS,
            "coarse_control_executions": _COARSE_CONTROL_EXECUTIONS,
            "existing_dask_invariance_reexecutions": _DASK_REEXECUTIONS,
            "full_replay_candidate_work_fraction": (
                total_executions / _FULL_REPLAY_CANDIDATE_EXECUTIONS
            ),
            "geometry_cell_count": 12,
            "geometry_specification": _geometry_specification(),
            "image_count": _IMAGE_COUNT,
            "image_shape_yx": [512, 512],
            "independent_unit": "noise-seed-image",
            "matrix": matrix_rows,
            "matrix_cell_count": len(matrix),
            "noise_realizations_per_cell": 4,
            "role": "development",
            "seed_audit": seed_audit,
            "total_finder_executions": total_executions,
            "trigger_cohorts": [
                {
                    "cohort": "below",
                    "scientific_role": "negative activation control",
                    "target_nominal_peak_sigma": 60.0,
                },
                {
                    "cohort": "boundary",
                    "scientific_role": "non-binding trigger stability",
                    "target_nominal_peak_sigma": 75.0,
                },
                {
                    "cohort": "above",
                    "scientific_role": "binding self-absorption challenge",
                    "target_nominal_peak_sigma": 90.0,
                },
            ],
        },
        "qualification_boundary": {
            "development_images_may_enter_qualification": False,
            "on_development_failure": (
                "document the terminal failure, obtain scientific approval "
                "for a test-first prospective correction, rerun affected "
                "small regression evidence, and freeze a replacement candidate"
            ),
            "on_development_pass": (
                "keep source science unchanged and add a seed-disjoint "
                "analogue "
                "to the unopened final qualification design"
            ),
            "qualification_opened": False,
            "qualification_or_parity_claim_from_this_lane": False,
        },
        "rejected_alternatives": [
            (
                "opening the 4,608-image held-out qualification population to "
                "discover this known development risk"
            ),
            (
                "using the viewed Hydra image as truth or tuning adaptive "
                "thresholds from it"
            ),
            (
                "disabling adaptive refinement as the production fix without "
                "prospective truth evidence"
            ),
            (
                "running another complete 2,400-image cumulative replay "
                "before the small lane passes"
            ),
            (
                "weakening existing PyBDSF, incumbent-retention, absolute "
                "safety, confidence, or trade-off rules"
            ),
        ],
        "review_id": "phase-5-adaptive-background-development-pre-review",
        "schema_version": 1,
        "scientific_question": (
            "Does the exact adaptive background/RMS refinement preserve "
            "bright "
            "extended truth support and photometry when the strict 75-sigma "
            "trigger activates, across the smallest morphology, scale, beam, "
            "noise-gradient, and placement design that exposes "
            "self-absorption?"
        ),
        "status": "awaiting-human-scientific-review",
    }


def write_review(path: Path, review: dict[str, object]) -> None:
    """Write one canonical review without overwriting existing evidence."""
    if path.exists():
        raise FileExistsError(f"refusing to overwrite pre-review: {path}")
    path.write_text(
        json.dumps(review, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Build and write the exact non-executable review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    review = build_review(arguments.repository_root.resolve())
    write_review(arguments.output, review)
    print(arguments.output)
    print(f"review_sha256={file_sha256(arguments.output)}")
    print(f"review_canonical_sha256={canonical_sha256(review)}")


if __name__ == "__main__":
    main()
