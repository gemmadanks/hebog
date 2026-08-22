#!/usr/bin/env python3
"""Freeze the approved powered Phase 5 recovery population."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    SyntheticRecipe,
    iter_dataset_recipes,
    recipe_sha256,
)
from hebog.validation.external_runners import file_sha256, source_tree_sha256

_ROOT = Path(__file__).parents[2]
_POWER_REVIEW = (
    _ROOT / "benchmark-results/phase-5/viewed-recovery-power-review.json"
)
_POWER_REVIEW_SHA256 = (
    "bbfab3a0781c8a12083190d8c591152d5c461a45824bab6cba39e770915af9fc"
)
_CUMULATIVE_LEDGER_SHA256 = (
    "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
)
_RECOVERY_DECISION_SHA256 = (
    "b35f4a811827df8960c22484193e9198d547bbb0e588e5b215d1f8d9ed66865f"
)
_CANDIDATE_REVISION = "c184acf7f55f936442285835b4601a6ac193fe2a"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "b4176ce387fa1569cc86ca300bfa7de6462758a1068de46cd4a16616a6ec3adc"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
)
_CONTINUUM_FIRST_SEEDS = (
    2026920001,
    2026921001,
    2026922001,
    2026923001,
)
_CONTINUUM_REALIZATIONS_PER_GEOMETRY = 422
_CONTINUUM_REALIZATIONS = 1688
_COMPACT_FIRST_SEED = 2026930001
_COMPACT_REALIZATIONS = 800
_EXPECTED_PRIOR_COUNT = 226
_MINIMUM_JOINT_POWER = 0.9
_OUTPUT_MARKER = "phase-5-external-recovery-"


def _json_bytes(value: object) -> bytes:
    """Serialize one finite governed record canonically."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _canonical_sha256(value: object) -> str:
    """Hash JSON-compatible data independently of indentation."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _changed_seed_record(
    template: DatasetRecord,
    *,
    identifier: str,
    purpose: str,
    first_seed: int,
    realization_count: int,
) -> DatasetRecord:
    """Reuse reviewed truth and geometry with only fresh noise seeds."""
    record = cast(
        dict[str, object],
        deepcopy(template.model_dump(mode="json")),
    )
    record["identifier"] = identifier
    record["purpose"] = purpose
    record["provenance"] = (
        "The approved Phase 5 recovery comparison reuses only reviewed "
        "geometry, beam, WCS, truth, endpoints, and gates. Every noise seed "
        "is disjoint from all checked-in development and campaign "
        "populations; no finder output or score is reused."
    )
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
    """Create 1,688 images balanced over four Continuum geometries."""
    if len(template.datasets) != len(_CONTINUUM_FIRST_SEEDS):
        raise ValueError("recovery continuum requires four geometries")
    datasets = tuple(
        _changed_seed_record(
            dataset,
            identifier=f"phase5-external-recovery-continuum-{index + 1}-1024",
            purpose=(
                "Fresh powered Phase 5 recovery Continuum geometry "
                f"{index + 1} of four."
            ),
            first_seed=first_seed,
            realization_count=_CONTINUUM_REALIZATIONS_PER_GEOMETRY,
        )
        for index, (dataset, first_seed) in enumerate(
            zip(template.datasets, _CONTINUUM_FIRST_SEEDS, strict=True)
        )
    )
    return template.model_copy(
        update={
            "manifest_id": "phase-5-external-recovery-continuum",
            "description": (
                "Fresh powered recovery Continuum population; four balanced "
                "reviewed geometries and no reused finder output."
            ),
            "datasets": datasets,
        }
    )


def _compact_manifest(template: DatasetManifest) -> DatasetManifest:
    """Create 800 fresh compact/blend realizations."""
    if len(template.datasets) != 1:
        raise ValueError("recovery compact population requires one geometry")
    dataset = _changed_seed_record(
        template.datasets[0],
        identifier="phase5-external-recovery-compact-blend-512",
        purpose="Fresh powered Phase 5 recovery compact and blend population.",
        first_seed=_COMPACT_FIRST_SEED,
        realization_count=_COMPACT_REALIZATIONS,
    )
    return template.model_copy(
        update={
            "manifest_id": "phase-5-external-recovery-compact-blend",
            "description": (
                "Fresh powered recovery compact/blend population with no "
                "reused finder output."
            ),
            "datasets": (dataset,),
        }
    )


def _manifest_seeds(manifest: DatasetManifest) -> set[int]:
    """Return every independent seed in one manifest."""
    return {
        recipe.seed
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }


def _population_audit(
    dataset_directory: Path,
    manifests: tuple[DatasetManifest, DatasetManifest],
) -> dict[str, object]:
    """Require global seed disjointness from every checked-in population."""
    records: list[dict[str, object]] = []
    historical: set[int] = set()
    for path in sorted(dataset_directory.glob("*.json")):
        if _OUTPUT_MARKER in path.name:
            continue
        manifest = DatasetManifest.model_validate_json(path.read_bytes())
        seeds = _manifest_seeds(manifest)
        if historical.intersection(seeds):
            raise ValueError(
                f"historical seeds overlap before recovery: {path}"
            )
        historical.update(seeds)
        records.append(
            {
                "path": str(path.relative_to(dataset_directory.parent.parent)),
                "sha256": file_sha256(path),
            }
        )
    continuum_seeds = _manifest_seeds(manifests[0])
    compact_seeds = _manifest_seeds(manifests[1])
    new_seeds = continuum_seeds | compact_seeds
    if (
        len(continuum_seeds) != _CONTINUUM_REALIZATIONS
        or len(compact_seeds) != _COMPACT_REALIZATIONS
        or not continuum_seeds.isdisjoint(compact_seeds)
        or not historical.isdisjoint(new_seeds)
    ):
        raise ValueError("recovery population seeds are not globally disjoint")
    return {
        "historical_manifest_count": len(records),
        "historical_registry_sha256": _canonical_sha256(records),
        "historical_seed_count": len(historical),
        "new_seed_count": len(new_seeds),
        "seed_disjoint": True,
    }


def _load_power_review(path: Path) -> dict[str, Any]:
    """Validate the exact approved recovery power decision."""
    if file_sha256(path) != _POWER_REVIEW_SHA256:
        raise ValueError("approved recovery power review changed")
    review = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    ledger = cast(dict[str, Any], review.get("cumulative_ledger"))
    planning = cast(dict[str, Any], review.get("planning"))
    power = cast(dict[str, Any], review.get("power"))
    authorization = cast(dict[str, Any], review.get("authorization"))
    if (
        review.get("schema_version") != 1
        or review.get("review_id") != "phase-5-viewed-recovery-power-review"
        or review.get("status") != "ready-for-named-scientific-freeze-review"
        or ledger.get("sha256") != _CUMULATIVE_LEDGER_SHA256
        or ledger.get("recovery_decision_sha256") != _RECOVERY_DECISION_SHA256
        or ledger.get("candidate_revision") != _CANDIDATE_REVISION
        or ledger.get("candidate_source_tree_sha256")
        != _CANDIDATE_SOURCE_TREE_SHA256
        or ledger.get("candidate_configuration_sha256")
        != _CANDIDATE_CONFIGURATION_SHA256
        or planning.get("paired_comparison_count") != _EXPECTED_PRIOR_COUNT
        or planning.get("selected_continuum_realization_count")
        != _CONTINUUM_REALIZATIONS
        or planning.get("continuum_realizations_per_geometry")
        != _CONTINUUM_REALIZATIONS_PER_GEOMETRY
        or planning.get("compact_realization_count") != _COMPACT_REALIZATIONS
        or power.get("minimum_joint_power") != _MINIMUM_JOINT_POWER
        or power.get("combined_familywise_power_lower_bound", 0)
        < _MINIMUM_JOINT_POWER
        or authorization.get("fresh_population_frozen") is not False
        or authorization.get("execution_authorized") is not False
    ):
        raise ValueError("approved recovery power review is invalid")
    assumptions = cast(list[object] | None, review.get("paired_assumptions"))
    if (
        not isinstance(assumptions, list)
        or len(assumptions) != _EXPECTED_PRIOR_COUNT
    ):
        raise ValueError("recovery paired power assumptions changed")
    return review


def build_recovery_documents(
    *,
    repository_root: Path,
    continuum_template_path: Path,
    compact_template_path: Path,
    power_review_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Build both fresh manifests and their approved population freeze."""
    if source_tree_sha256(repository_root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("approved recovery source tree changed")
    review = _load_power_review(power_review_path)
    continuum = _continuum_manifest(
        DatasetManifest.model_validate_json(
            continuum_template_path.read_bytes()
        )
    )
    compact = _compact_manifest(
        DatasetManifest.model_validate_json(compact_template_path.read_bytes())
    )
    continuum_document = cast(
        dict[str, object], continuum.model_dump(mode="json")
    )
    compact_document = cast(dict[str, object], compact.model_dump(mode="json"))
    audit = _population_audit(
        continuum_template_path.parent,
        (continuum, compact),
    )
    planning = cast(dict[str, object], review["planning"])
    power = cast(dict[str, object], review["power"])
    freeze = cast(
        dict[str, object],
        {
            "schema_version": 1,
            "contract_id": "phase-5-external-recovery-population",
            "status": "scientifically-approved-and-frozen-before-output",
            "scientific_approval": {
                "reviewer": "Gemma Danks",
                "approved_on": "2026-08-22",
                "scope": "recovery-scientific-freeze-only-no-execution",
            },
            "candidate": {
                "revision": _CANDIDATE_REVISION,
                "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
                "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
            },
            "evidence": {
                "cumulative_ledger_path": (
                    "benchmark-results/phase-5/"
                    "cumulative-regression-ledger-recovery.json"
                ),
                "cumulative_ledger_sha256": _CUMULATIVE_LEDGER_SHA256,
                "power_review_path": str(
                    power_review_path.relative_to(repository_root)
                ),
                "power_review_sha256": _POWER_REVIEW_SHA256,
                "recovery_decision_path": (
                    "config/contracts/phase-5-viewed-recovery-execution-decision.json"
                ),
                "recovery_decision_sha256": _RECOVERY_DECISION_SHA256,
            },
            "generator": {
                "relative_path": (
                    "scripts/validation/"
                    "freeze_phase5_external_recovery_population.py"
                ),
                "sha256": file_sha256(Path(__file__)),
            },
            "closed_campaign_policy": (
                "closed-evidence-not-pooled-rescored-or-reused"
            ),
            "populations": [
                {
                    "lane": "continuum",
                    "manifest": (
                        "config/datasets/phase-5-external-recovery-continuum.json"
                    ),
                    "manifest_sha256": hashlib.sha256(
                        _json_bytes(continuum_document)
                    ).hexdigest(),
                    "image_count": _CONTINUUM_REALIZATIONS,
                    "role": "regression",
                    "independent_unit": "noise-seed-image",
                },
                {
                    "lane": "compact-blend",
                    "manifest": (
                        "config/datasets/"
                        "phase-5-external-recovery-compact-blend.json"
                    ),
                    "manifest_sha256": hashlib.sha256(
                        _json_bytes(compact_document)
                    ).hexdigest(),
                    "image_count": _COMPACT_REALIZATIONS,
                    "role": "regression",
                    "independent_unit": "noise-seed-image",
                },
            ],
            "population_audit": audit,
            "power_audit": {
                **planning,
                **power,
                "paired_assumptions": review["paired_assumptions"],
            },
            "finder_output_generated": False,
            "finder_output_opened": False,
            "execution_authorized": False,
            "step_three_authorized": False,
            "optimization_authorized": False,
            "qualification_opened": False,
            "next_action": (
                "freeze-recovery-program-identities-for-one-look-review"
            ),
        },
    )
    return continuum_document, compact_document, freeze


def _parse_args() -> argparse.Namespace:
    """Parse fixed fresh population inputs and write-once outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--continuum-template",
        type=Path,
        default=(
            _ROOT
            / "config/datasets/phase-5-external-post-correction-continuum.json"
        ),
    )
    parser.add_argument(
        "--compact-template",
        type=Path,
        default=(
            _ROOT / "config/datasets/"
            "phase-5-external-post-correction-compact-blend.json"
        ),
    )
    parser.add_argument("--power-review", type=Path, default=_POWER_REVIEW)
    parser.add_argument(
        "--continuum-output",
        type=Path,
        default=(
            _ROOT / "config/datasets/phase-5-external-recovery-continuum.json"
        ),
    )
    parser.add_argument(
        "--compact-output",
        type=Path,
        default=(
            _ROOT
            / "config/datasets/phase-5-external-recovery-compact-blend.json"
        ),
    )
    parser.add_argument(
        "--freeze-output",
        type=Path,
        default=(
            _ROOT
            / "config/contracts/phase-5-external-recovery-population.json"
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Write the approved population records without replacement."""
    arguments = _parse_args()
    outputs = (
        arguments.continuum_output,
        arguments.compact_output,
        arguments.freeze_output,
    )
    if any(path.exists() for path in outputs):
        raise FileExistsError("refusing to overwrite frozen recovery output")
    continuum, compact, freeze = build_recovery_documents(
        repository_root=_ROOT,
        continuum_template_path=arguments.continuum_template,
        compact_template_path=arguments.compact_template,
        power_review_path=arguments.power_review,
    )
    for path, document in zip(
        outputs,
        (continuum, compact, freeze),
        strict=True,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(_json_bytes(document))
        print(path)


if __name__ == "__main__":
    main()
