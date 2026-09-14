#!/usr/bin/env python3
"""Build the non-executable Phase 5 adaptive-background root-cause review."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

import numpy as np

from hebog.validation.adaptive_background_development import (
    AdaptiveDevelopmentCell,
    build_adaptive_development_matrix,
)
from hebog.validation.adaptive_background_lane import (
    AdaptiveDevelopmentObservation,
    build_adaptive_development_manifest,
    input_identifier,
)
from hebog.validation.datasets import iter_dataset_recipes
from hebog.validation.external_runners import canonical_sha256, file_sha256

_TERMINAL = Path(
    "benchmark-results/phase-5/adaptive-background-development-decision.json"
)
_TERMINAL_SHA256 = (
    "ff415f064f4ea7daa9254338041e52ad15d41b84edf692602092134850218026"
)
_TERMINAL_CANONICAL_SHA256 = (
    "4f6e37241ee58420c30f8416c784e6c57efbd6e55eae32c1e878757116d865ab"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-adaptive-background-development-937737d"
)
_CANDIDATE_REVISION = "937737d811dd229d71dbcfdbda6cb5829de6faca"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_EXPECTED_INPUTS = 144
_EXPECTED_FAILED_GEOMETRIES = 9
_UPSTREAM_BINDINGS = {
    "approved_development_review": (
        Path(
            "config/contracts/"
            "phase-5-adaptive-background-development-pre-review.json"
        ),
        "6287ad3ef734c91142637142f04abebfb7226253e9e49060af686fe07292eed4",
    ),
    "population_manifest": (
        Path(
            "config/contracts/"
            "phase-5-adaptive-background-development-manifest.json"
        ),
        "77203f85930a99ffbb5490f93db7073cab434b42c8350d6da864625efd09946b",
    ),
    "original_identity_review": (
        Path(
            "config/contracts/"
            "phase-5-adaptive-background-development-identity-review.json"
        ),
        "f9ccef67d942494c6ba1358f15ea09f02343a4f3dd930b2167f68ba5427cd5ba",
    ),
    "original_execution_decision": (
        Path(
            "config/contracts/"
            "phase-5-adaptive-background-development-execution-decision.json"
        ),
        "fc804d7d90d5a546425cebd9935d8c16f1877701fd8efd82992d1dbe4c4a4d25",
    ),
    "completion_repair_review": (
        Path(
            "config/contracts/phase-5-adaptive-background-development-"
            "completion-repair-pre-review.json"
        ),
        "d61b9643427a01094a7f8377e98930f2e8a102060e49b34e9cf4edf12238577f",
    ),
    "completion_identity_review": (
        Path(
            "config/contracts/phase-5-adaptive-background-development-"
            "completion-identity-review.json"
        ),
        "d2a664f578915fadab94ea3d8d8f2b92e2fd488aca3b293a68a5e9d99d433089",
    ),
    "completion_execution_decision": (
        Path(
            "config/contracts/phase-5-adaptive-background-development-"
            "completion-execution-decision.json"
        ),
        "0d5c071b0e4f035824461d6c2d2ad35fb02a8c4d8885025269775f6d8fe8f475",
    ),
    "public_candidate_identity": (
        Path("config/contracts/phase-5-public-interface-identity-review.json"),
        "a521c656683cdae8b8d2250a3d29dee716c4ff774a25e23556301b21e5d898f8",
    ),
}


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    """Load one required JSON object with a clear failure."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _round(value: float) -> float:
    """Keep the review compact while preserving diagnostic resolution."""
    return round(float(value), 6)


def _require_binding(path: Path, expected: str, *, label: str) -> None:
    """Fail closed if one governed input no longer has its exact identity."""
    if file_sha256(path) != expected:
        raise ValueError(f"{label} identity changed")


def _expected_observations() -> dict[str, AdaptiveDevelopmentCell]:
    """Index the exact reviewed cell metadata by realization identity."""
    matrix = build_adaptive_development_matrix()
    manifest = build_adaptive_development_manifest()
    expected = {
        input_identifier(cell, recipe.seed): cell
        for cell, dataset in zip(matrix, manifest.datasets, strict=True)
        for recipe in iter_dataset_recipes(dataset)
    }
    if len(expected) != _EXPECTED_INPUTS:
        raise ValueError("adaptive root-cause population changed")
    return expected


def _load_observations() -> tuple[
    tuple[AdaptiveDevelopmentObservation, ...], str
]:
    """Strictly load and bind all array-free terminal observations."""
    if not _SCRATCH.is_dir():
        raise FileNotFoundError(
            "preserved adaptive-background development scratch is absent"
        )
    paths = tuple(sorted(_SCRATCH.glob("*/observation.json")))
    if len(paths) != _EXPECTED_INPUTS:
        raise ValueError(
            "adaptive root-cause review requires 144 observations"
        )
    expected = _expected_observations()
    observations: list[AdaptiveDevelopmentObservation] = []
    file_records: list[dict[str, object]] = []
    for path in paths:
        observation = AdaptiveDevelopmentObservation.model_validate_json(
            path.read_bytes()
        )
        cell = expected.get(observation.input_id)
        if cell is None or (
            observation.cell_id != cell.cell_id
            or observation.seed not in cell.noise_seeds
            or observation.trigger_cohort != cell.trigger_cohort
        ):
            raise ValueError("adaptive observation identity changed")
        observations.append(observation)
        file_records.append(
            {
                "path": str(path.relative_to(_SCRATCH)),
                "sha256": file_sha256(path),
            }
        )
    if len({item.input_id for item in observations}) != _EXPECTED_INPUTS:
        raise ValueError("adaptive observation is duplicated")
    return tuple(observations), canonical_sha256(file_records)


def _morphology(item: AdaptiveDevelopmentObservation) -> str:
    """Return the canonical JSON key for one observation morphology."""
    return item.cell_id.split("--", maxsplit=1)[0]


def _geometry(item: AdaptiveDevelopmentObservation) -> str:
    """Return the trigger-independent geometry identifier."""
    return item.cell_id.rsplit("--", maxsplit=1)[0]


def _metric(
    item: AdaptiveDevelopmentObservation,
    arm: str,
    name: str,
) -> float:
    """Read one named scalar from an exact candidate or control summary."""
    summary = item.adaptive if arm == "adaptive" else item.coarse
    return float(getattr(summary, name))


def _distribution(values: np.ndarray) -> dict[str, float]:
    """Return compact deterministic order statistics."""
    return {
        "maximum": _round(float(np.max(values))),
        "median": _round(float(np.median(values))),
        "minimum": _round(float(np.min(values))),
        "p95": _round(float(np.percentile(values, 95.0))),
    }


def _correlation(first: np.ndarray, second: np.ndarray) -> float:
    """Return one finite Pearson correlation for retained paired evidence."""
    value = float(np.corrcoef(first, second)[0, 1])
    if not np.isfinite(value):
        raise ValueError("adaptive root-cause correlation is not finite")
    return _round(value)


def _active_signature(
    observations: tuple[AdaptiveDevelopmentObservation, ...],
    paired_margins: dict[str, float],
) -> dict[str, object]:
    """Summarize causal direction only where adaptive refinement activated."""
    active = tuple(
        item for item in observations if item.adaptive_candidate_positions_yx
    )
    background = np.asarray(
        [
            _metric(item, "adaptive", "background_error_median_rms")
            - _metric(item, "coarse", "background_error_median_rms")
            for item in active
        ],
        dtype=np.float64,
    )
    rms = np.asarray(
        [
            _metric(item, "adaptive", "rms_error_median_fraction")
            - _metric(item, "coarse", "rms_error_median_fraction")
            for item in active
        ],
        dtype=np.float64,
    )
    support = np.asarray(
        [
            _metric(item, "coarse", "support_recall")
            - _metric(item, "adaptive", "support_recall")
            for item in active
        ],
        dtype=np.float64,
    )
    mask = np.asarray(
        [
            _metric(item, "coarse", "mask_iou")
            - _metric(item, "adaptive", "mask_iou")
            for item in active
        ],
        dtype=np.float64,
    )
    flux = np.asarray(
        [
            _metric(
                item,
                "adaptive",
                "integrated_flux_absolute_fractional_error",
            )
            - _metric(
                item,
                "coarse",
                "integrated_flux_absolute_fractional_error",
            )
            for item in active
        ],
        dtype=np.float64,
    )
    by_morphology: dict[str, dict[str, int]] = {}
    for morphology in sorted({_morphology(item) for item in active}):
        selected = tuple(
            item for item in active if _morphology(item) == morphology
        )
        by_morphology[morphology] = {
            "active_images": len(selected),
            "flux": sum(
                _metric(
                    item,
                    "adaptive",
                    "integrated_flux_absolute_fractional_error",
                )
                - _metric(
                    item,
                    "coarse",
                    "integrated_flux_absolute_fractional_error",
                )
                > paired_margins["integrated_flux_absolute_fractional_error"]
                for item in selected
            ),
            "mask_iou": sum(
                _metric(item, "coarse", "mask_iou")
                - _metric(item, "adaptive", "mask_iou")
                > paired_margins["mask_iou"]
                for item in selected
            ),
            "support_recall": sum(
                _metric(item, "coarse", "support_recall")
                - _metric(item, "adaptive", "support_recall")
                > paired_margins["support_recall"]
                for item in selected
            ),
        }
    return {
        "adverse_image_counts": {
            "background_error": int(np.count_nonzero(background > 0.0)),
            "flux_error": int(np.count_nonzero(flux > 0.0)),
            "mask_iou": int(np.count_nonzero(mask > 0.0)),
            "rms_error": int(np.count_nonzero(rms > 0.0)),
            "support_recall": int(np.count_nonzero(support > 0.0)),
        },
        "background_error_increase_median_rms": _round(
            float(np.median(background))
        ),
        "background_error_increase_rms": _distribution(background),
        "background_error_vs_flux_error_correlation": _correlation(
            background, flux
        ),
        "background_error_vs_support_loss_correlation": _correlation(
            background, support
        ),
        "flux_error_increase": _distribution(flux),
        "mask_iou_loss": _distribution(mask),
        "outside_paired_margin_by_morphology": by_morphology,
        "rms_error_increase_fraction": _distribution(rms),
        "rms_error_vs_support_loss_correlation": _correlation(rms, support),
        "support_recall_loss": _distribution(support),
    }


def _paired_evidence(
    observations: tuple[AdaptiveDevelopmentObservation, ...],
    pre_review: dict[str, Any],
) -> dict[str, object]:
    """Build the exact trigger and paired causal contrast."""
    policy = cast(dict[str, Any], pre_review["decision_policy"])
    margins = cast(
        dict[str, float], policy["paired_adaptive_vs_coarse_margins"]
    )
    active = tuple(
        item for item in observations if item.adaptive_candidate_positions_yx
    )
    inactive = tuple(
        item
        for item in observations
        if not item.adaptive_candidate_positions_yx
    )
    trigger_counts = {
        cohort: {
            "active": sum(
                bool(item.adaptive_candidate_positions_yx)
                for item in observations
                if item.trigger_cohort == cohort
            ),
            "images": sum(
                item.trigger_cohort == cohort for item in observations
            ),
        }
        for cohort in ("above", "below", "boundary")
    }
    return {
        "active_exact_candidate_control_matches": sum(
            item.adaptive == item.coarse for item in active
        ),
        "active_input_count": len(active),
        "active_signature": _active_signature(observations, margins),
        "inactive_exact_candidate_control_matches": sum(
            item.adaptive == item.coarse for item in inactive
        ),
        "inactive_input_count": len(inactive),
        "input_count": len(observations),
        "trigger_counts": trigger_counts,
    }


def _coarse_floor_failures(
    items: list[AdaptiveDevelopmentObservation],
    floors: dict[str, float],
) -> list[str]:
    """Return the original hard-floor failures for one coarse geometry."""
    flux = np.asarray(
        [
            item.coarse.integrated_flux_absolute_fractional_error
            for item in items
        ]
    )
    mask = np.asarray([item.coarse.mask_iou for item in items])
    support = np.asarray([item.coarse.support_recall for item in items])
    checks = (
        (
            np.mean([item.coarse.completeness for item in items])
            < floors["completeness_minimum"],
            "completeness-floor",
        ),
        (
            np.median(flux)
            > floors[
                "integrated_flux_absolute_fractional_error_median_maximum"
            ],
            "integrated-flux-median-floor",
        ),
        (
            np.percentile(flux, 95.0)
            > floors["integrated_flux_absolute_fractional_error_p95_maximum"],
            "integrated-flux-p95-floor",
        ),
        (
            np.median(mask) < floors["mask_iou_cell_median_minimum"],
            "mask-iou-cell-median-floor",
        ),
        (
            np.min(mask) < floors["mask_iou_image_minimum"],
            "mask-iou-image-floor",
        ),
        (
            np.mean([item.coarse.split for item in items])
            > floors["split_fraction_maximum"],
            "split-fraction-floor",
        ),
        (
            np.median(support) < floors["support_recall_cell_median_minimum"],
            "support-recall-cell-median-floor",
        ),
        (
            np.min(support) < floors["support_recall_image_minimum"],
            "support-recall-image-floor",
        ),
    )
    return [failure for failed, failure in checks if failed]


def _coarse_failures(
    observations: tuple[AdaptiveDevelopmentObservation, ...],
    pre_review: dict[str, Any],
) -> dict[str, object]:
    """Apply the original absolute floors to the diagnostic coarse arm."""
    policy = cast(dict[str, Any], pre_review["decision_policy"])
    floors = cast(dict[str, float], policy["hard_truth_safety_floors"])
    grouped: dict[str, list[AdaptiveDevelopmentObservation]] = defaultdict(
        list
    )
    for item in observations:
        grouped[_geometry(item)].append(item)
    failing = [
        {"failures": sorted(failures), "geometry_id": geometry}
        for geometry, items in sorted(grouped.items())
        if (failures := _coarse_floor_failures(items, floors))
    ]
    active = tuple(
        item for item in observations if item.adaptive_candidate_positions_yx
    )
    transitions = Counter(
        (item.coarse.split, item.adaptive.split) for item in active
    )
    return {
        "active_split_transitions": {
            "coarse_false_adaptive_false": transitions[(False, False)],
            "coarse_false_adaptive_true": transitions[(False, True)],
            "coarse_true_adaptive_false": transitions[(True, False)],
            "coarse_true_adaptive_true": transitions[(True, True)],
        },
        "failing_geometries": failing,
        "failing_geometry_count": len(failing),
        "implication": (
            "restoring coarse-only behaviour cannot pass the frozen lane"
        ),
    }


def _binding_context(
    terminal: dict[str, Any],
    observation_set_sha256: str,
) -> dict[str, object]:
    """Return exact upstream, candidate, and terminal identities."""
    upstream = {
        name: {"path": str(path), "sha256": expected}
        for name, (path, expected) in sorted(_UPSTREAM_BINDINGS.items())
    }
    return {
        "candidate": {
            "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
            "revision": _CANDIDATE_REVISION,
            "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        },
        "preserved_observations": {
            "array_free_observation_count": _EXPECTED_INPUTS,
            "canonical_file_set_sha256": observation_set_sha256,
            "preserved_product_set_sha256": terminal["provenance"][
                "preserved_product_set_sha256"
            ],
            "scratch": str(_SCRATCH),
        },
        "terminal_decision": {
            "canonical_sha256": _TERMINAL_CANONICAL_SHA256,
            "path": str(_TERMINAL),
            "sha256": _TERMINAL_SHA256,
        },
        "upstream": upstream,
    }


def build_review(root: Path) -> dict[str, object]:
    """Build the deterministic terminal-evidence root-cause review."""
    root = root.resolve()
    for name, (path, expected) in _UPSTREAM_BINDINGS.items():
        _require_binding(root / path, expected, label=name)
    terminal_path = root / _TERMINAL
    _require_binding(
        terminal_path,
        _TERMINAL_SHA256,
        label="adaptive terminal decision",
    )
    terminal = _json_object(terminal_path, label="adaptive terminal decision")
    if canonical_sha256(terminal) != _TERMINAL_CANONICAL_SHA256:
        raise ValueError("adaptive terminal canonical identity changed")
    if (
        terminal.get("status") != "fail"
        or terminal.get("failed_geometry_count") != _EXPECTED_FAILED_GEOMETRIES
    ):
        raise ValueError("adaptive terminal scientific result changed")
    pre_review = _json_object(
        root / _UPSTREAM_BINDINGS["approved_development_review"][0],
        label="approved adaptive development review",
    )
    observations, observation_set_sha256 = _load_observations()
    paired = _paired_evidence(observations, pre_review)
    coarse_failures = _coarse_failures(observations, pre_review)
    failure_counts = Counter(
        failure
        for geometry in terminal["geometry_decisions"]
        for failure in geometry["failures"]
    )
    return {
        "allowed_after_separate_approval": [
            "test-first-source-protected-adaptive-background-repair",
            "fixture-only-background-rms-and-support-validation",
            "diagnostic-only-coarse-gap-reproductions",
            "bounded-pre-publication-attribution-telemetry",
            "serial-and-existing-dask-invariance-validation",
            "non-executable-replacement-identity-freeze-only-after-all-"
            "fixture-gates-pass",
        ],
        "authorization": {
            "candidate_execution_authorized": False,
            "cumulative_replay_authorized": False,
            "cutover_authorized": False,
            "development_lane_execution_authorized": False,
            "fresh_qualification_authorized": False,
            "optimization_authorized": False,
            "pybdsf_execution_authorized": False,
            "release_authorized": False,
            "rescoring_authorized": False,
            "source_finding_change_authorized": False,
            "threshold_or_margin_tuning_authorized": False,
            "viewed_data_execution_authorized": False,
        },
        "binding_context": _binding_context(terminal, observation_set_sha256),
        "causal_findings": {
            "adaptive_background_self_contamination": {
                "classification": "confirmed-primary-paired-regression-cause",
                "code_path": [
                    "discover_adaptive_candidates retains only strict "
                    "candidate peaks and discards source-island support",
                    "refine_background_rms_grids estimates 35-by-35 fine "
                    "windows from the original image and validity alone",
                    "estimate_rms_window_statistics sigma-clips those source-"
                    "contaminated samples as one distribution",
                    "blend_adaptive_background_rms gives the fine estimates "
                    "unit weight near each candidate",
                ],
                "evidence": (
                    "All 54 inactive images are exact candidate/control "
                    "matches; all 90 active images differ and all 90 have "
                    "larger median in-support background error. The error "
                    "increase tracks support loss at r=0.874107 and flux-"
                    "error increase at r=0.957040. Damage is severe for "
                    "source-filled shell and mixed windows but absent outside "
                    "the practical margins for curved filaments."
                ),
            },
            "integrated_flux_loss": {
                "classification": (
                    "confirmed-direct-and-support-mediated-effect-with-"
                    "independent-coarse-arm-gap"
                ),
                "direct_path": (
                    "source photometry sums image-minus-estimated-background "
                    "over the source aperture, so a positive adaptive "
                    "background bias directly removes source flux"
                ),
                "evidence_limit": (
                    "The array-free observations cannot apportion each loss "
                    "between direct background subtraction, changed support, "
                    "and changed source membership."
                ),
                "independent_gap": (
                    "Two mixed compact/extended coarse geometries already "
                    "fail flux floors, including the 12-beam, 75%-halo case; "
                    "a red fixture must test the fixed 1.5-beam aperture "
                    "against source-union scale before any measurement change."
                ),
            },
            "publication_specific_effect": {
                "classification": (
                    "unresolved-observability-gap-not-demonstrated-primary-"
                    "cause"
                ),
                "description": (
                    "Both arms use identical persistence and public "
                    "projection code, but retained summaries expose only the "
                    "final public "
                    "mask. They do not retain pre-publication support recall, "
                    "so publication-specific amplification cannot be measured "
                    "retrospectively."
                ),
            },
            "split_fraction": {
                "classification": "independent-pre-existing-topology-gap",
                "evidence": (
                    "Among 90 active pairs, adaptive refinement introduced "
                    "zero new split outcomes, left 30 split outcomes "
                    "unchanged, and removed three. Every terminal split-floor "
                    "failure is "
                    "therefore present in the one-factor control rather than "
                    "caused by adaptive background refinement."
                ),
            },
            "support_loss": {
                "classification": (
                    "confirmed-downstream-effect-not-independent-root-cause"
                ),
                "description": (
                    "The biased background and RMS enter normalized direct "
                    "detection and residual multiscale support before any "
                    "measurement or publication step. Both paired arms use "
                    "the same downstream algorithms; 87 of 90 active images "
                    "lose support while the inactive outputs are exact."
                ),
                "independent_gap": (
                    "Two mixed coarse geometries also miss mask or support "
                    "floors, so the background defect is not the sole "
                    "absolute support limitation."
                ),
            },
            "trigger_or_executor_defect": {
                "classification": "excluded-as-primary-cause",
                "evidence": (
                    "All 48 below-trigger inputs remain inactive, all 48 "
                    "above-trigger inputs activate on truth, the boundary "
                    "frequency is retained without reinterpretation, all "
                    "products validate, and all 12 Serial/existing-Dask "
                    "comparisons are identical."
                ),
            },
        },
        "change_control": {
            "forbidden_same_change": [
                "adaptive-trigger-threshold-change",
                "detection-or-island-threshold-change",
                "truth-aware-or-reference-finder-masking",
                "background-window-or-blend-radius-tuning",
                "measurement-aperture-change-without-red-fixture-and-renewed-"
                "review",
                "source-association-change-without-red-fixture-and-renewed-"
                "review",
                "publication-rule-change-without-pre-publication-attribution",
                "gate-margin-or-truth-definition-change",
                "retrospective-rescoring-of-the-terminal-lane",
                "runtime-optimization",
            ],
            "historical_terminal_failure_immutable": True,
            "no_lane_execution_before_fixture_closure": True,
            "no_threshold_or_margin_change": True,
        },
        "coarse_control_absolute_failures": coarse_failures,
        "paired_evidence": paired,
        "recommended_correction": {
            "fine_grid_policy": (
                "estimate only windows disjoint from protected support; mark "
                "intersecting windows unavailable and fill them only through "
                "the existing deterministic bounded interpolation fallback"
            ),
            "new_numeric_science_thresholds": False,
            "primary_scope": (
                "source-protected-adaptive-background-and-rms-estimation"
            ),
            "source_protection": {
                "execution": (
                    "retain or materialize protection as bounded tile "
                    "products; never send an image-sized mask through a "
                    "scheduler task"
                ),
                "seed": (
                    "coarse-normalized pixels above the existing 75-sigma "
                    "adaptive candidate threshold"
                ),
                "support": (
                    "the connected coarse-normalized island at the existing "
                    "public island threshold containing each adaptive seed"
                ),
            },
            "truth_or_reference_finder_inputs": False,
            "unchanged_science": [
                "75-sigma adaptive trigger",
                "public detection and island thresholds",
                "35-by-35 fine-grid geometry and seven-pixel step",
                "75-pixel influence and 20-pixel transition widths",
                "support, measurement, association, and publication "
                "algorithms",
                "all frozen lane floors, margins, truth, and trigger rules",
            ],
        },
        "required_next_decision": (
            "named-approval-of-this-exact-review-for-test-first-fixture-only-"
            "scientific-correction"
        ),
        "required_sequence": [
            "obtain-named-approval-of-this-exact-root-cause-review",
            "add-red-source-contamination-and-local-noise-discrimination-"
            "fixtures",
            "implement-bounded-source-protected-adaptive-window-eligibility",
            "add-pre-publication-support-attribution-and-rejection-telemetry",
            "add-red-mixed-halo-aperture-and-source-topology-fixtures",
            "obtain-renewed-review-before-any-independent-measurement-"
            "association-or-publication-change",
            "validate-all-original-background-and-affected-regression-fixtures",
            "validate-serial-existing-dask-tile-order-and-retry-invariance",
            "freeze-exact-non-executable-replacement-candidate-and-lane-"
            "identities",
            "obtain-separate-exact-approval-before-any-development-lane-"
            "execution",
            "open-held-out-qualification-only-after-the-replacement-lane-passes",
        ],
        "review_id": "phase-5-adaptive-background-root-cause-pre-review",
        "reviewed_on": "2026-09-04",
        "schema_version": 1,
        "status": "ready-for-named-adaptive-background-correction-review",
        "terminal_failure_summary": {
            "executor_invariance_passed": terminal[
                "executor_invariance_passed"
            ],
            "failed_geometry_count": terminal["failed_geometry_count"],
            "failure_reason_counts": dict(sorted(failure_counts.items())),
            "geometry_count": terminal["geometry_count"],
            "status": terminal["status"],
            "trigger_seam_passed": terminal["trigger_seam_passed"],
        },
        "test_first_matrix": [
            "source-protected-background-shell",
            "source-protected-background-mixed-core-halo",
            "local-noise-patch-remains-adaptive",
            "below-trigger-bitwise-inert",
            "overlapping-and-disjoint-bright-candidate-protection",
            "insufficient-source-free-window-fallback",
            "flat-and-varying-background-and-rms",
            "edge-corner-and-invalid-pixel-protection",
            "mixed-halo-measurement-aperture",
            "shell-and-filament-source-association",
            "pre-publication-versus-publication-support-attribution",
            "serial-existing-dask-tile-order-and-retry-invariance",
        ],
    }


def write_review(path: Path, review: dict[str, object]) -> None:
    """Write one finite sorted review without overwriting prior evidence."""
    if path.exists():
        raise FileExistsError(
            f"refusing to overwrite root-cause review: {path}"
        )
    path.write_text(
        json.dumps(review, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Build and write the exact non-executable scientific review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    review = build_review(arguments.repository_root)
    write_review(arguments.output, review)
    print(arguments.output)
    print(f"review_sha256={file_sha256(arguments.output)}")
    print(f"review_canonical_sha256={canonical_sha256(review)}")


if __name__ == "__main__":
    main()
