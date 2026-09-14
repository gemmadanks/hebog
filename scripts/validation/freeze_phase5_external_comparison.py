"""Freeze the pre-results Step 2C-P external source-finder protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from statistics import NormalDist
from typing import cast

from hebog.validation.contracts import (
    PhaseFiveAstrometryFollowUpConfirmationDecision,
    PhaseFiveExternalComparisonProtocol,
    PhaseFiveExternalPowerAssumption,
    load_paired_noninferiority_contract,
)
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    SyntheticRecipe,
    iter_dataset_recipes,
    recipe_sha256,
)
from hebog.validation.noninferiority import (
    calculate_design_power,
    familywise_power_lower_bound,
)

_CONTINUUM_FIRST_SEEDS = (
    2026780001,
    2026781001,
    2026782001,
    2026783001,
)
_CONTINUUM_REALIZATIONS_PER_GEOMETRY = 150
_COMPACT_FIRST_SEED = 2026790001
_COMPACT_REALIZATIONS = 800
_CONFIDENCE_LEVEL = 0.95
_MINIMUM_JOINT_POWER = 0.9
_AEGEAN_CONTAINER_DIGEST = (
    "sha256:b496d2907c13d083e7c87eda61a6a40057f92b5cb6e605330bcb1b6db27158b8"
)


def _sha256(path: Path) -> str:
    """Return the exact identity of one frozen input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(document: dict[str, object]) -> bytes:
    """Serialize one frozen record canonically for review and hashing."""
    return (
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _changed_seed_record(  # noqa: PLR0913
    template: DatasetRecord,
    *,
    identifier: str,
    purpose: str,
    provenance: str,
    first_seed: int,
    realization_count: int,
) -> DatasetRecord:
    """Copy reviewed truth geometry into new, seed-disjoint images."""
    record = cast(
        dict[str, object], deepcopy(template.model_dump(mode="json"))
    )
    record["identifier"] = identifier
    record["role"] = "regression"
    record["purpose"] = purpose
    record["provenance"] = provenance
    recipe = cast(dict[str, object], record["recipe"])
    recipe["seed"] = first_seed
    record["noise_realization_seeds"] = list(
        range(first_seed + 1, first_seed + realization_count)
    )
    record["recipe_sha256"] = recipe_sha256(
        SyntheticRecipe.model_validate(recipe)
    )
    return DatasetRecord.model_validate(record)


def _continuum_manifest(template: DatasetManifest) -> DatasetManifest:
    """Create 600 new images across four reviewed geometries and beams."""
    if len(template.datasets) != len(_CONTINUUM_FIRST_SEEDS):
        raise ValueError("continuum template must contain four geometries")
    datasets = tuple(
        _changed_seed_record(
            dataset,
            identifier=f"phase5-external-continuum-{index + 1}-1024",
            purpose=(
                "Fresh Step 2C-P full-continuum source-finder comparison "
                f"geometry {index + 1}."
            ),
            provenance=(
                "Step 2C-P reuses only reviewed generator geometry, beam, "
                "WCS, and truth definitions. Every noise-seed image is new "
                "and no prior source-finder output or result is reused."
            ),
            first_seed=first_seed,
            realization_count=_CONTINUUM_REALIZATIONS_PER_GEOMETRY,
        )
        for index, (dataset, first_seed) in enumerate(
            zip(template.datasets, _CONTINUUM_FIRST_SEEDS, strict=True)
        )
    )
    return DatasetManifest(
        schema_version=3,
        manifest_id="phase-5-external-continuum",
        datasets=datasets,
    )


def _compact_manifest(template: DatasetManifest) -> DatasetManifest:
    """Create 800 new compact and blend images from reviewed truth design."""
    if len(template.datasets) != 1:
        raise ValueError("compact template must contain one dataset")
    dataset = _changed_seed_record(
        template.datasets[0],
        identifier="phase5-external-compact-blend-512",
        purpose=(
            "Fresh Step 2C-P compact, resolved, edge, and blend comparison "
            "for PyBDSF and Aegean catalogue products."
        ),
        provenance=(
            "Step 2C-P reuses the reviewed Phase 4U analytic compact and "
            "blend truth design but no prior noise image, finder output, or "
            "result. The Phase 5 qualification population remains untouched."
        ),
        first_seed=_COMPACT_FIRST_SEED,
        realization_count=_COMPACT_REALIZATIONS,
    )
    return DatasetManifest(
        schema_version=2,
        manifest_id="phase-5-external-compact-blend",
        datasets=(dataset,),
    )


def _manifest_seeds(manifest: DatasetManifest) -> set[int]:
    """Return every independent image seed in one manifest."""
    return {
        recipe.seed
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }


def _require_seed_disjointness(
    *,
    dataset_directory: Path,
    new_manifests: tuple[DatasetManifest, ...],
) -> None:
    """Reject overlap with all checked-in historical dataset manifests."""
    prior: set[int] = set()
    for path in sorted(dataset_directory.glob("*.json")):
        manifest = DatasetManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if manifest.manifest_id in {
            "phase-5-external-continuum",
            "phase-5-external-compact-blend",
        }:
            continue
        seeds = _manifest_seeds(manifest)
        if prior.intersection(seeds):
            raise ValueError(f"historical dataset seeds overlap in {path}")
        prior.update(seeds)
    combined_new: set[int] = set()
    for manifest in new_manifests:
        seeds = _manifest_seeds(manifest)
        if prior.intersection(seeds) or combined_new.intersection(seeds):
            raise ValueError("Step 2C-P seeds must be globally disjoint")
        combined_new.update(seeds)


def _continuum_assumptions() -> tuple[PhaseFiveExternalPowerAssumption, ...]:
    """Return conservative pre-results variance assumptions."""
    specifications = (
        ("completeness", 0.02, -0.01, 0.08, 70),
        ("reliability", 0.02, -0.01, 0.08, 70),
        ("integrated-flux-median", 0.05, -0.01, 0.20, 70),
        ("integrated-flux-p95", 0.05, -0.01, 0.25, 70),
        ("position-median", 0.05, -0.01, 0.15, 70),
        ("position-p95", 0.05, -0.01, 0.25, 70),
        ("duplicate-fraction", 0.01, -0.003, 0.03, 70),
        ("mask-precision", 0.05, -0.01, 0.15, 56),
        ("mask-recall", 0.05, -0.01, 0.15, 56),
        ("mask-iou", 0.05, -0.01, 0.15, 56),
        ("split-fraction", 0.02, -0.005, 0.06, 70),
        ("merge-fraction", 0.02, -0.005, 0.06, 70),
    )
    return tuple(
        PhaseFiveExternalPowerAssumption(
            metric_family=metric_family,
            practical_regression_margin=margin,
            planning_expected_regression=expected,
            planning_paired_standard_deviation=standard_deviation,
            comparison_count=comparison_count,
        )
        for (
            metric_family,
            margin,
            expected,
            standard_deviation,
            comparison_count,
        ) in specifications
    )


def _continuum_power_lower_bound(
    assumptions: tuple[PhaseFiveExternalPowerAssumption, ...],
) -> float:
    """Calculate a dependence-robust planning power lower bound."""
    critical = NormalDist().inv_cdf(_CONFIDENCE_LEVEL)
    total_failure = 0.0
    for item in assumptions:
        standard_error = item.planning_paired_standard_deviation / (
            (4 * _CONTINUUM_REALIZATIONS_PER_GEOMETRY) ** 0.5
        )
        threshold = (
            item.practical_regression_margin - critical * standard_error
        )
        power = NormalDist().cdf(
            (threshold - item.planning_expected_regression) / standard_error
        )
        total_failure += item.comparison_count * (1.0 - power)
    return max(0.0, 1.0 - total_failure)


def _protocol_document(  # noqa: PLR0913
    *,
    continuum_document: dict[str, object],
    compact_document: dict[str, object],
    confirmation_decision_path: Path,
    phase_five_gates_path: Path,
    phase_four_gates_path: Path,
    phase_four_registry_path: Path,
    compact_power_contract_path: Path,
) -> dict[str, object]:
    """Build and validate the complete pre-results comparison protocol."""
    decision = (
        PhaseFiveAstrometryFollowUpConfirmationDecision.model_validate_json(
            confirmation_decision_path.read_text(encoding="utf-8")
        )
    )
    if not decision.step_two_c_p_protocol_freeze_authorized:
        raise ValueError("Step 2C-P protocol freeze is not authorized")
    compact_contract = load_paired_noninferiority_contract(
        compact_power_contract_path
    )
    compact_estimates = calculate_design_power(compact_contract)
    compact_single = familywise_power_lower_bound(compact_estimates)
    compact_power = max(0.0, 1.0 - 3.0 * (1.0 - compact_single))
    assumptions = _continuum_assumptions()
    continuum_power = _continuum_power_lower_bound(assumptions)
    combined_power = max(
        0.0,
        1.0 - (1.0 - continuum_power) - (1.0 - compact_power),
    )
    protocol: dict[str, object] = {
        "schema_version": 1,
        "contract_id": "phase-5-external-comparison",
        "status": "frozen-before-external-output",
        "confirmation_decision_sha256": _sha256(confirmation_decision_path),
        "phase_five_scientific_gates_sha256": _sha256(phase_five_gates_path),
        "phase_four_scientific_gates_sha256": _sha256(phase_four_gates_path),
        "phase_four_metric_registry_sha256": _sha256(phase_four_registry_path),
        "candidate": "residual-b3-original-pixel-measurement",
        "candidate_position": "confirmed-detected-segment-centroid",
        "references": [
            {
                "finder_id": "released-pybdsf",
                "version": "1.14.1",
                "source_revision": (
                    "1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc"
                ),
                "artifact_type": "pypi-sdist",
                "artifact_sha256": (
                    "8d5113fecca19bb9f02a1a3e17aeb8f2d22c712cac9504e44271c4071f5434d2"
                ),
                "container_image_digest": (
                    "sha256:72454074489d5ed0d0ed08781ec11411a3e25ccf75e3378a924152176fa15b37"
                ),
                "dependency_inventory_sha256": (
                    "8211043e9fca55d706d1e890e2bf0b630e228a854db0949258c498506975669f"
                ),
                "comparison_scope": "binding-full-continuum",
            },
            {
                "finder_id": "pinned-pybdsf-master",
                "version": "1.14.2.dev40+gc70103be3",
                "source_revision": (
                    "c70103be3ae9ae9908286f144e6ce956acc0ce5c"
                ),
                "artifact_type": "local-wheel",
                "artifact_sha256": (
                    "2f1fdfbecd39de93bad53e2a85258959e5114e1f049787ac15c763e8fc8f4d8d"
                ),
                "container_image_digest": (
                    "sha256:192964b32d50a6e960cf3710013ffa92d782ecf43a4d6def4309a7cb10911e73"
                ),
                "dependency_inventory_sha256": (
                    "83574dd4c15d79f3cf2ac52fb8aa7b5bd2ff323c93343b2f1337eec938e8bf99"
                ),
                "comparison_scope": "binding-full-continuum",
            },
            {
                "finder_id": "aegean",
                "version": "2.3.5",
                "source_revision": (
                    "bb04f50a3ec117d180a79260c6a5c844f1d8dbbc"
                ),
                "artifact_type": "pypi-wheel",
                "artifact_sha256": (
                    "dda95cb525e229b60bc357d3e5fc454cac20f364ee8aa10b730c2f7223da428d"
                ),
                "container_image_digest": _AEGEAN_CONTAINER_DIGEST,
                "dependency_inventory_sha256": (
                    "346c1f32b0d78ce1d22f6d6ff20787a102d8491c14432865465596c9f41ba909"
                ),
                "comparison_scope": (
                    "binding-compact-blended-and-gaussian-like-catalogue"
                ),
            },
        ],
        "populations": [
            {
                "lane": "continuum",
                "manifest": (
                    "config/datasets/phase-5-external-continuum.json"
                ),
                "manifest_sha256": hashlib.sha256(
                    _json_bytes(continuum_document)
                ).hexdigest(),
                "role": "regression",
                "image_count": 600,
                "independent_unit": "noise-seed-image",
                "geometry_policy": (
                    "reviewed-generator-geometries-new-noise-images-no-prior-results"
                ),
            },
            {
                "lane": "compact-blend",
                "manifest": (
                    "config/datasets/phase-5-external-compact-blend.json"
                ),
                "manifest_sha256": hashlib.sha256(
                    _json_bytes(compact_document)
                ).hexdigest(),
                "role": "regression",
                "image_count": 800,
                "independent_unit": "noise-seed-image",
                "geometry_policy": (
                    "reviewed-generator-geometries-new-noise-images-no-prior-results"
                ),
            },
        ],
        "pybdsf_configuration": {
            "threshold_pixel_sigma": 5.0,
            "threshold_island_sigma": 3.0,
            "threshold_type": "hard",
            "mean_map": "zero",
            "rms_map": True,
            "rms_box": [150, 50],
            "adaptive_rms_box": True,
            "rms_box_bright": [35, 7],
            "adaptive_threshold": 75.0,
            "atrous_do": True,
            "atrous_bdsm_do": True,
            "atrous_jmax": 3,
            "atrous_lpf": "b3",
            "atrous_sum": True,
            "atrous_orig_isl": False,
            "primary_background": "finder-operational",
            "controlled_background_diagnostic": (
                "same-frozen-mean-and-rms-via-rmsmean-map-filename"
            ),
        },
        "aegean_configuration": {
            "mode": "blind-source-finding",
            "primary_seedclip_sigma": 5.0,
            "primary_floodclip_sigma": 4.0,
            "threshold_matched_seedclip_sigma": 5.0,
            "threshold_matched_floodclip_sigma": 3.0,
            "covariance": "enabled",
            "island_catalogue": True,
            "cores": 1,
            "primary_background": "finder-operational-internal-estimation",
            "controlled_background_diagnostic": (
                "same-frozen-background-and-rms"
            ),
        },
        "matcher": {
            "truth_authority": "analytic-and-injected-truth-first",
            "coordinate_system": "zero-based-fits-pixel-centre-x-y",
            "compact_edge": (
                "centre-distance-at-most-half-restoring-beam-fwhm"
            ),
            "extended_edge": (
                "minimum-support-overlap-at-least-0.1-or-centre-in-one-beam-dilation"
            ),
            "primary_assignment": (
                "maximum-cardinality-maximum-overlap-minimum-distance-stable-id"
            ),
            "topology_rule": (
                "retain-all-eligible-edges-after-primary-assignment"
            ),
            "no_cross_finder_matching": True,
            "hebog_compact_position": "fitted-gaussian-component-centre",
            "hebog_extended_position": "detected-segment-flux-centroid",
            "pybdsf_compact_position": "gaussian-component-centre",
            "pybdsf_extended_position": (
                "source-moment-only-when-grouping-and-model-semantics-align"
            ),
            "aegean_position": (
                "component-centre-compact-gaussian-and-mixed-scope-only"
            ),
            "hebog_support": "reconciled-detected-segment",
            "pybdsf_support": "island-mask",
            "aegean_support": "three-sigma-fitted-ellipse-union-proxy",
            "aegean_mask_metrics": "unavailable-not-failure",
        },
        "continuum_binding_metrics": [
            "completeness",
            "reliability",
            "integrated-flux-median",
            "integrated-flux-p95",
            "position-median",
            "position-p95",
            "duplicate-fraction",
            "mask-precision",
            "mask-recall",
            "mask-iou",
            "split-fraction",
            "merge-fraction",
        ],
        "compact_binding_registry": "phase-4r-metric-registry",
        "aegean_binding_scope": (
            "compact-blended-gaussian-like-and-mixed-catalogue-products"
        ),
        "aegean_diagnostic_scope": (
            "diffuse-filament-shell-mask-and-multiscale-provenance"
        ),
        "resampling": (
            "paired-whole-image-fixed-seed-bca-one-sided-95-percent"
        ),
        "bootstrap_resamples": 50_000,
        "bootstrap_seed": 20260810,
        "decision_rule": (
            "absolute-first-every-applicable-noninferiority-gate-no-compensation"
        ),
        "incomplete_reference_policy": (
            "comparison-unavailable-and-step-two-c-p-fails-closed"
        ),
        "failure_denominator": "retain-every-image",
        "one_look_rule": (
            "one-terminal-look-no-tuning-rescoring-or-adaptive-sample-size"
        ),
        "power_audit": {
            "method": (
                "cluster-normal-planning-plus-conservative-union-lower-bound"
            ),
            "confidence_level": _CONFIDENCE_LEVEL,
            "minimum_joint_power": _MINIMUM_JOINT_POWER,
            "continuum_realization_count": 600,
            "continuum_assumptions": [
                item.model_dump(mode="json") for item in assumptions
            ],
            "continuum_familywise_power_lower_bound": continuum_power,
            "compact_reviewed_contract_sha256": _sha256(
                compact_power_contract_path
            ),
            "compact_realization_count": 800,
            "compact_single_reference_familywise_power_lower_bound": (
                compact_single
            ),
            "compact_reference_count": 3,
            "compact_familywise_power_lower_bound": compact_power,
            "combined_familywise_power_lower_bound": combined_power,
            "assumption_failure": (
                "observed-variance-above-bound-makes-comparison-underpowered"
            ),
        },
        "public_cutout": (
            "deferred-to-step-6-no-redistributable-checksum-bound-input-on-host"
        ),
        "scientific_outcomes_before_runtime": True,
        "execution_authorized": False,
        "step_three_authorized": False,
        "optimization_authorized": False,
        "qualification_opened": False,
        "next_action": (
            "implement-and-hash-runners-and-matcher-before-execution-review"
        ),
    }
    validated = PhaseFiveExternalComparisonProtocol.model_validate(protocol)
    return cast(dict[str, object], validated.model_dump(mode="json"))


def _documents(  # noqa: PLR0913
    *,
    continuum_template_path: Path,
    compact_template_path: Path,
    dataset_directory: Path,
    confirmation_decision_path: Path,
    phase_five_gates_path: Path,
    phase_four_gates_path: Path,
    phase_four_registry_path: Path,
    compact_power_contract_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Build both fresh manifests and their bound protocol."""
    continuum_template = DatasetManifest.model_validate_json(
        continuum_template_path.read_text(encoding="utf-8")
    )
    compact_template = DatasetManifest.model_validate_json(
        compact_template_path.read_text(encoding="utf-8")
    )
    continuum = _continuum_manifest(continuum_template)
    compact = _compact_manifest(compact_template)
    _require_seed_disjointness(
        dataset_directory=dataset_directory,
        new_manifests=(continuum, compact),
    )
    continuum_document = cast(
        dict[str, object], continuum.model_dump(mode="json")
    )
    compact_document = cast(dict[str, object], compact.model_dump(mode="json"))
    protocol_document = _protocol_document(
        continuum_document=continuum_document,
        compact_document=compact_document,
        confirmation_decision_path=confirmation_decision_path,
        phase_five_gates_path=phase_five_gates_path,
        phase_four_gates_path=phase_four_gates_path,
        phase_four_registry_path=phase_four_registry_path,
        compact_power_contract_path=compact_power_contract_path,
    )
    return continuum_document, compact_document, protocol_document


def _parse_args() -> argparse.Namespace:
    """Parse paths while keeping every scientific choice fixed in code."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--continuum-template",
        type=Path,
        default=(
            root
            / "config/datasets/phase-5-astrometry-follow-up-confirmation.json"
        ),
    )
    parser.add_argument(
        "--compact-template",
        type=Path,
        default=root / "config/datasets/phase-4u-qualification.json",
    )
    parser.add_argument(
        "--confirmation-decision",
        type=Path,
        default=(
            root / "config/contracts/"
            "phase-5-astrometry-follow-up-confirmation-decision.json"
        ),
    )
    parser.add_argument(
        "--phase-five-gates",
        type=Path,
        default=root / "config/contracts/phase-5-scientific-gates.json",
    )
    parser.add_argument(
        "--phase-four-gates",
        type=Path,
        default=root / "config/contracts/phase-4-scientific-gates.json",
    )
    parser.add_argument(
        "--phase-four-registry",
        type=Path,
        default=root / "config/contracts/phase-4r-metric-registry.json",
    )
    parser.add_argument(
        "--compact-power-contract",
        type=Path,
        default=(
            root / "config/contracts/phase-4u-paired-noninferiority.json"
        ),
    )
    parser.add_argument(
        "--continuum-output",
        type=Path,
        default=root / "config/datasets/phase-5-external-continuum.json",
    )
    parser.add_argument(
        "--compact-output",
        type=Path,
        default=(root / "config/datasets/phase-5-external-compact-blend.json"),
    )
    parser.add_argument(
        "--protocol-output",
        type=Path,
        default=(root / "config/contracts/phase-5-external-comparison.json"),
    )
    return parser.parse_args()


def main() -> None:
    """Write every pre-results input once and refuse partial replacement."""
    arguments = _parse_args()
    outputs = (
        arguments.continuum_output,
        arguments.compact_output,
        arguments.protocol_output,
    )
    existing = tuple(path for path in outputs if path.exists())
    if existing:
        raise FileExistsError(
            f"refusing to overwrite frozen Step 2C-P inputs: {existing}"
        )
    documents = _documents(
        continuum_template_path=arguments.continuum_template,
        compact_template_path=arguments.compact_template,
        dataset_directory=arguments.continuum_output.parent,
        confirmation_decision_path=arguments.confirmation_decision,
        phase_five_gates_path=arguments.phase_five_gates,
        phase_four_gates_path=arguments.phase_four_gates,
        phase_four_registry_path=arguments.phase_four_registry,
        compact_power_contract_path=arguments.compact_power_contract,
    )
    for path, document in zip(outputs, documents, strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_json_bytes(document))


if __name__ == "__main__":
    main()
