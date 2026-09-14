#!/usr/bin/env python3
"""Build the non-executable Phase 5 coarse-science gap review."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
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

_ROOT_REVIEW = Path(
    "config/contracts/phase-5-adaptive-background-root-cause-pre-review.json"
)
_ROOT_REVIEW_SHA256 = (
    "8e00269924b50c1b52188beefcb177e50d9035e25a69755d5d2d31ddead3d902"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-adaptive-background-development-937737d"
)
_OBSERVATION_SET_SHA256 = (
    "b55f7385e17c9f78205aa48d9a8b5fefdde2c50602db5c10d6da5c9424fcdf17"
)
_EXPECTED_INPUTS = 144
_EXPECTED_FAILED_GEOMETRIES = 6
_CANDIDATE_REVISION = "7ebde589c82e153e0f7d475a8469c120138be4da"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "c83ee5a90c33f9c915b69402710835a5a094d08df83e003f8e2fd0799f23ae2d"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_SOURCE_PROTECTED_BINDINGS = {
    "implementation_decision": (
        Path(
            "config/contracts/phase-5-adaptive-background-source-protection-"
            "implementation-decision.json"
        ),
        "0bf418efede130b49a50ea0fea7c216856d5a0c434b64932111a7c7682a36e8f",
    ),
    "lane_identity": (
        Path(
            "config/contracts/phase-5-adaptive-background-source-protection-"
            "identity-review.json"
        ),
        "9f416775382a55dd600dbf6956b0ced069a6bd692bc7a0e36783702e34fe8eb3",
    ),
    "public_identity": (
        Path(
            "config/contracts/phase-5-adaptive-background-source-protection-"
            "public-interface-identity-review.json"
        ),
        "4f8c110fb45ffa151d54bc9c9dfdad1385306101a1e8397718f82a0b43388b81",
    ),
}
_MECHANISM_BINDINGS = {
    "attribution": (
        Path("src/hebog/validation/adaptive_background_diagnostics.py"),
        "172787221cdc4973ab4d716973f198775de3a493bf3553d9a00316247694f9f8",
    ),
    "attribution_fixtures": (
        Path("tests/unit/validation/test_adaptive_background_correction.py"),
        "a619bd74080988bbc1adae84cb0bf0b477bb795e124c0924976b3648a3c352b3",
    ),
    "measurement": (
        Path("src/hebog/validation/products.py"),
        "a03e33e88a8dee32df337e498970a865107de44546de3ea93402f35395d993e7",
    ),
    "multiscale_association": (
        Path("src/hebog/algorithms/multiscale_association.py"),
        "56eebff04dba0f3020eeaad862ea534c64251ecac2bd067e631a52350a9ee53b",
    ),
    "publication": (
        Path("src/hebog/algorithms/extended_measurement.py"),
        "c8cddfad678a575f96e7f7554854988d4d9fd3a839a4f6cd846242afc13692d8",
    ),
    "publication_composition": (
        Path("src/hebog/validation/publication_scale_persistence.py"),
        "d93be8a1736fb8e2817a56fcb09270b77fe1ddaf76778c03fcc5e5c9e676e990",
    ),
    "source_association": (
        Path("src/hebog/algorithms/source_association.py"),
        "a1bfe2896aacabe43d1ed553342766b645be9ef8063110fa16fe00342afec924",
    ),
}
_MEASUREMENT_GEOMETRY = (
    "mixed_compact_extended--beam-a--flat--scale-12--interior"
)
_TOPOLOGY_GEOMETRY = "shell--beam-a--varying--scale-8--tile-corner"


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    """Load one required JSON object with a clear failure."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _require_binding(path: Path, expected: str, *, label: str) -> None:
    """Fail closed if a governed input no longer has its exact identity."""
    if file_sha256(path) != expected:
        raise ValueError(f"{label} identity changed")


def _round(value: float) -> float:
    """Keep scalar evidence compact without hiding gate-scale movement."""
    return round(float(value), 6)


def _expected_observations() -> dict[str, AdaptiveDevelopmentCell]:
    """Index the exact reviewed development cells by realization identity."""
    matrix = build_adaptive_development_matrix()
    manifest = build_adaptive_development_manifest()
    expected = {
        input_identifier(cell, recipe.seed): cell
        for cell, dataset in zip(matrix, manifest.datasets, strict=True)
        for recipe in iter_dataset_recipes(dataset)
    }
    if len(expected) != _EXPECTED_INPUTS:
        raise ValueError("coarse-science review population changed")
    return expected


def _load_observations() -> tuple[AdaptiveDevelopmentObservation, ...]:
    """Strictly load the immutable array-free coarse-arm observations."""
    if not _SCRATCH.is_dir():
        raise FileNotFoundError(
            "preserved adaptive-background development scratch is absent"
        )
    paths = tuple(sorted(_SCRATCH.glob("*/observation.json")))
    if len(paths) != _EXPECTED_INPUTS:
        raise ValueError("coarse-science review requires 144 observations")
    expected = _expected_observations()
    observations: list[AdaptiveDevelopmentObservation] = []
    file_records: list[dict[str, str]] = []
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
            raise ValueError("coarse-science observation identity changed")
        observations.append(observation)
        file_records.append(
            {
                "path": str(path.relative_to(_SCRATCH)),
                "sha256": file_sha256(path),
            }
        )
    if len({item.input_id for item in observations}) != _EXPECTED_INPUTS:
        raise ValueError("coarse-science observation is duplicated")
    if canonical_sha256(file_records) != _OBSERVATION_SET_SHA256:
        raise ValueError("coarse-science observation set identity changed")
    return tuple(observations)


def _geometry(item: AdaptiveDevelopmentObservation) -> str:
    """Return one trigger-independent geometry identifier."""
    return item.cell_id.rsplit("--", maxsplit=1)[0]


def _summary(
    observations: list[AdaptiveDevelopmentObservation],
) -> dict[str, object]:
    """Summarize the exact diagnostic coarse arm for one geometry."""
    flux = np.asarray(
        [
            item.coarse.integrated_flux_absolute_fractional_error
            for item in observations
        ],
        dtype=np.float64,
    )
    mask = np.asarray(
        [item.coarse.mask_iou for item in observations], dtype=np.float64
    )
    support = np.asarray(
        [item.coarse.support_recall for item in observations],
        dtype=np.float64,
    )
    background = np.asarray(
        [item.coarse.background_error_median_rms for item in observations],
        dtype=np.float64,
    )
    return {
        "background_error_median_rms": _round(np.median(background)),
        "image_count": len(observations),
        "integrated_flux_error_median": _round(np.median(flux)),
        "integrated_flux_error_p95": _round(np.percentile(flux, 95.0)),
        "mask_iou_median": _round(np.median(mask)),
        "mask_iou_minimum": _round(np.min(mask)),
        "source_count_range": [
            min(item.coarse.source_count for item in observations),
            max(item.coarse.source_count for item in observations),
        ],
        "split_fraction": _round(
            np.mean([item.coarse.split for item in observations])
        ),
        "truth_support_recall_median": _round(np.median(support)),
        "truth_support_recall_minimum": _round(np.min(support)),
    }


def _coarse_evidence(
    root_review: dict[str, Any],
    observations: tuple[AdaptiveDevelopmentObservation, ...],
) -> dict[str, object]:
    """Retain exact summaries for every independent coarse-arm failure."""
    coarse = cast(
        dict[str, Any], root_review["coarse_control_absolute_failures"]
    )
    failures = cast(list[dict[str, Any]], coarse["failing_geometries"])
    failing_ids = {str(item["geometry_id"]) for item in failures}
    expected_ids = {
        "curved_filament--beam-a--varying--scale-12--interior",
        _MEASUREMENT_GEOMETRY,
        "mixed_compact_extended--beam-a--varying--scale-4--tile-corner",
        "mixed_compact_extended--beam-b--varying--scale-8--interior",
        _TOPOLOGY_GEOMETRY,
        "shell--beam-b--varying--scale-12--interior",
    }
    if (
        failing_ids != expected_ids
        or coarse["failing_geometry_count"] != _EXPECTED_FAILED_GEOMETRIES
    ):
        raise ValueError("coarse-arm failure set changed")
    grouped: dict[str, list[AdaptiveDevelopmentObservation]] = defaultdict(
        list
    )
    for item in observations:
        grouped[_geometry(item)].append(item)
    records = []
    for failure in sorted(failures, key=lambda item: item["geometry_id"]):
        geometry_id = str(failure["geometry_id"])
        records.append(
            {
                "failures": sorted(cast(list[str], failure["failures"])),
                "geometry_id": geometry_id,
                "summary": _summary(grouped[geometry_id]),
            }
        )
    return {
        "failing_geometries": records,
        "failing_geometry_count": len(records),
        "interpretation": (
            "the independent coarse arm localizes two mixed-source "
            "photometry/support failures and four catalogue over-splitting "
            "failures; it is diagnostic evidence, not a replacement public "
            "candidate"
        ),
    }


def _binding_context(root_review: dict[str, Any]) -> dict[str, Any]:
    """Bind the evidence, prospective candidate, and reviewed code paths."""
    terminal = cast(
        dict[str, Any],
        cast(dict[str, Any], root_review["binding_context"])[
            "terminal_decision"
        ],
    )
    return {
        "candidate": {
            "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
            "revision": _CANDIDATE_REVISION,
            "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        },
        "mechanism_code": {
            name: {"path": str(path), "sha256": expected}
            for name, (path, expected) in sorted(_MECHANISM_BINDINGS.items())
        },
        "preserved_observations": {
            "array_free_observation_count": _EXPECTED_INPUTS,
            "canonical_file_set_sha256": _OBSERVATION_SET_SHA256,
            "scratch": str(_SCRATCH),
        },
        "root_cause_review": {
            "path": str(_ROOT_REVIEW),
            "sha256": _ROOT_REVIEW_SHA256,
        },
        "source_protected_successor": {
            name: {"path": str(path), "sha256": expected}
            for name, (path, expected) in sorted(
                _SOURCE_PROTECTED_BINDINGS.items()
            )
        },
        "terminal_decision": terminal,
    }


def build_review(root: Path) -> dict[str, object]:
    """Build a deterministic, prospective, non-executable science review."""
    root = root.resolve()
    _require_binding(
        root / _ROOT_REVIEW,
        _ROOT_REVIEW_SHA256,
        label="adaptive-background root-cause review",
    )
    for name, (path, expected) in _SOURCE_PROTECTED_BINDINGS.items():
        _require_binding(root / path, expected, label=name)
    for name, (path, expected) in _MECHANISM_BINDINGS.items():
        _require_binding(root / path, expected, label=name)
    root_review = _json_object(
        root / _ROOT_REVIEW,
        label="adaptive-background root-cause review",
    )
    if root_review.get("status") != (
        "ready-for-named-adaptive-background-correction-review"
    ):
        raise ValueError("adaptive-background root review status changed")
    observations = _load_observations()
    coarse = _coarse_evidence(root_review, observations)
    summaries = {
        item["geometry_id"]: cast(dict[str, object], item["summary"])
        for item in cast(list[dict[str, object]], coarse["failing_geometries"])
    }
    measurement = summaries[_MEASUREMENT_GEOMETRY]
    topology = summaries[_TOPOLOGY_GEOMETRY]
    return {
        "allowed_after_separate_approval": [
            "test-first-source-owned-multiscale-measurement-support",
            "test-first-conservative-whole-source-parent-construction",
            "fixture-only-measurement-association-and-publication-validation",
            "bounded-non-binding-rejection-and-stage-attribution-telemetry",
            "serial-and-existing-dask-invariance-validation",
            "complete-no-write-combined-development-lane-validation",
            "non-executable-replacement-identity-freeze-only-after-every-"
            "fixture-gate-passes",
        ],
        "authorization": {
            "candidate_execution_authorized": False,
            "coarse_control_execution_authorized": False,
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
        "binding_context": _binding_context(root_review),
        "causal_findings": {
            "adaptive_background": {
                "classification": (
                    "fixture-corrected-but-unexecuted-prospective-successor"
                ),
                "implication": (
                    "the source-protected implementation must be composed "
                    "with both independent corrections before a new lane; "
                    "fixture evidence does not predict its terminal result"
                ),
            },
            "catalogue_source_topology": {
                "classification": (
                    "confirmed-catalogue-association-over-splitting"
                ),
                "code_path": [
                    "the lane defines split as len(catalogue.sources) > 1",
                    "catalogue source count is created from multiscale "
                    "hierarchy memberships over immutable direct components",
                    "publication retained-mask connectivity is not read by "
                    "the membership reducer",
                    "the current ideal shell fixtures provide exact clean "
                    "parents and do not cover the lane's eight-knot noisy, "
                    "varying, or tile-corner feature loss",
                ],
                "evidence": (
                    "The strongest shell cohort has median flux error "
                    "0.003100 and median mask IoU 0.926517, yet 8 of 12 "
                    "realizations publish more than one catalogue source. "
                    "The source is detected and measured well enough; its "
                    "direct components are not consistently assigned to one "
                    "source parent."
                ),
                "exact_rejection_branch": (
                    "unresolved-until-production-equivalent-red-fixtures-"
                    "retain-hierarchy-diagnostics"
                ),
                "strongest_observed_contrast": topology,
            },
            "publication_mask": {
                "classification": (
                    "excluded-as-the-cause-of-the-binding-split-metric"
                ),
                "remaining_scope": (
                    "publication can still change mask IoU and connectivity; "
                    "the existing analytic cut-shell fixture proves that "
                    "possible mechanism only, not the observed catalogue "
                    "split"
                ),
            },
            "source_photometry_support": {
                "classification": (
                    "localized-source-photometry-composition-gap"
                ),
                "code_path": [
                    "publication support admits persistent adjacent-scale "
                    "features independently of catalogue measurement",
                    "catalogue source labels contain only associated member "
                    "measurement-component labels",
                    "photometry expands those labels by the fixed 1.5-beam "
                    "outer guard and sums the original residual once",
                    "persistent source-owned scale support outside that seed "
                    "cannot contribute to the catalogue flux",
                ],
                "evidence": (
                    "In the flat 12-beam mixed cohort, median background "
                    "error is only 0.015469 RMS and median truth-support "
                    "recall is 0.947679, while median integrated-flux error "
                    "is 0.529076. A background or detection-only explanation "
                    "cannot account for that separation."
                ),
                "evidence_limit": (
                    "retained scalar observations do not identify the exact "
                    "missing aperture pixels or apportion the remaining loss "
                    "between source-owned support and finite aperture growth"
                ),
                "strongest_observed_contrast": measurement,
            },
            "trigger_or_executor": {
                "classification": "excluded-as-causes-of-the-coarse-gaps",
                "evidence": (
                    "the coarse arm has adaptive estimation disabled, and "
                    "the completed lane passed exact Serial/existing-Dask "
                    "science invariance"
                ),
            },
        },
        "change_control": {
            "forbidden_same_change": [
                "adaptive-trigger-or-background-policy-change",
                "detection-or-island-threshold-change",
                "global-measurement-aperture-radius-increase",
                "truth-aware-or-reference-finder-support",
                "spatial-proximity-only-source-merging",
                "single-scale-broad-support-merging",
                "publication-change-to-repair-a-catalogue-count",
                "gate-margin-or-truth-definition-change",
                "retrospective-rescoring-of-terminal-evidence",
                "runtime-optimization",
            ],
            "historical_terminal_failure_immutable": True,
            "no_lane_execution_before_both_fixture_closures": True,
            "no_threshold_or_margin_change": True,
        },
        "coarse_control_evidence": coarse,
        "recommended_correction": {
            "conservative_source_parent": {
                "membership_rule": (
                    "reduce the complete bounded component-feature graph as "
                    "one unit; never add a component that lacks immutable "
                    "direct ownership or accept a partial overlap with an "
                    "existing source group"
                ),
                "negative_controls": [
                    "close-unrelated-pair",
                    "crossing-or-branched-features",
                    "competing-source-parent",
                    "single-scale-broad-bridge",
                ],
                "positive_evidence": (
                    "one exclusive connected adjacent-scale feature graph "
                    "with every member anchored by immutable direct support "
                    "and no competing parent assignment"
                ),
                "resilience_rule": (
                    "an unowned persistent terminal feature may corroborate "
                    "topology but cannot add membership; one missing or "
                    "displaced child cannot veto an otherwise exclusive "
                    "persistent whole-source graph"
                ),
            },
            "global_aperture_radius_change": False,
            "new_numeric_science_thresholds": False,
            "publication_policy": (
                "leave publication science unchanged unless stage-attribution "
                "fixtures independently demonstrate a remaining mask defect"
            ),
            "source_owned_measurement_support": {
                "aperture_policy": (
                    "retain the existing 1.5-beam outer guard; extend its "
                    "seed from measurement labels to the exact source-owned "
                    "multiscale support union"
                ),
                "inputs": (
                    "immutable member measurement labels plus only adjacent-"
                    "scale persistent support assigned exclusively to the "
                    "accepted source parent"
                ),
                "ownership_conflicts": (
                    "assign once by deterministic nearest immutable member "
                    "support and canonical source identity for exact distance "
                    "ties"
                ),
                "photometry": (
                    "sum original background-subtracted pixels once per "
                    "source; do not fit or synthesize missing flux"
                ),
            },
            "truth_or_reference_finder_inputs": False,
            "unchanged_science": [
                "adaptive trigger and source-protected background policy",
                "public detection and island thresholds",
                "1.5-beam local measurement guard",
                "scale detection and adjacent-scale persistence thresholds",
                "truth definitions, floors, margins, and decision rules",
            ],
        },
        "required_next_decision": (
            "named-approval-of-this-exact-review-for-test-first-fixture-only-"
            "measurement-and-topology-correction"
        ),
        "required_sequence": [
            "obtain-named-approval-of-this-exact-review",
            "add-production-equivalent-red-measurement-and-hierarchy-"
            "fixtures-with-stage-diagnostics",
            "implement-exclusive-source-owned-multiscale-measurement-support",
            "implement-whole-graph-conservative-source-parent-construction",
            "retain-publication-science-and-add-bounded-stage-attribution",
            "pass-positive-negative-boundary-invalid-and-conflict-fixtures",
            "pass-serial-existing-dask-tile-order-and-retry-invariance",
            "run-the-complete-combined-lane-in-no-write-mode",
            "freeze-exact-non-executable-combined-candidate-and-lane-"
            "identities",
            "obtain-separate-exact-approval-before-running-the-combined-"
            "development-lane",
            "open-held-out-qualification-only-after-every-development-"
            "geometry-passes",
        ],
        "review_id": ("phase-5-coarse-measurement-and-topology-pre-review"),
        "reviewed_on": "2026-09-04",
        "schema_version": 1,
        "status": (
            "ready-for-named-measurement-and-topology-correction-review"
        ),
        "test_first_matrix": [
            "mixed-core-halo-source-owned-photometry-at-4-8-and-12-beam-"
            "extents",
            "mixed-core-halo-flat-and-varying-background",
            "eight-knot-shell-at-interior-edge-and-tile-corner",
            "seven-knot-curved-filament-negative-and-positive-controls",
            "missing-and-displaced-terminal-feature",
            "exact-parent-and-terminal-cycle-regression",
            "close-unrelated-blend-must-not-merge",
            "crossing-branched-and-competing-parent-must-fail-closed",
            "single-scale-broad-bridge-must-not-merge",
            "overlapping-source-support-is-owned-once",
            "measurement-versus-publication-attribution",
            "invalid-pixel-and-image-edge-support",
            "serial-existing-dask-tile-order-and-retry-invariance",
        ],
    }


def write_review(path: Path, review: dict[str, object]) -> None:
    """Write one finite canonical review without replacing evidence."""
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing review: {path}")
    payload = json.dumps(
        review,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload + "\n", encoding="utf-8")


def main() -> None:
    """Build and atomically retain the reviewed prospective diagnosis."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "config/contracts/"
            "phase-5-coarse-measurement-and-topology-pre-review.json"
        ),
    )
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output = args.output
    if not output.is_absolute():
        output = root / output
    write_review(output, build_review(root))


if __name__ == "__main__":
    main()
