#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Freeze the approved powered Phase 5 post-correction population."""

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
    _ROOT / "benchmark-results/phase-5/post-correction-power-review.json"
)
_POWER_REVIEW_SHA256 = (
    "d68163f545d02f88433602a7b1ccd3f480aefafa7e30aa786bb9201bdadaa63d"
)
_CUMULATIVE_LEDGER = (
    _ROOT / "benchmark-results/phase-5/"
    "cumulative-regression-ledger-post-correction.json"
)
_CUMULATIVE_LEDGER_SHA256 = (
    "7ffd636482438c92462a0f15e00ff6759ae875d7b6ebab50bc1c8a3a9cf35be2"
)
_CANDIDATE_REVISION = "dfc3e25e635f4f6710558e483fa5a525ba904661"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "a549143b6475e75f7463c834e891c005a0660c2de9f4a0a3556c18bb9d39541d"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
)
_CONTINUUM_FIRST_SEEDS = (
    2026900001,
    2026901001,
    2026902001,
    2026903001,
)
_CONTINUUM_REALIZATIONS_PER_GEOMETRY = 422
_CONTINUUM_REALIZATIONS = 1688
_MINIMUM_CONTINUUM_REALIZATIONS = 1532
_COMPACT_FIRST_SEED = 2026910001
_COMPACT_REALIZATIONS = 800
_EXPECTED_PRIOR_COUNT = 226
_MINIMUM_JOINT_POWER = 0.9
_IMAGE_COUNT = 2488
_RESERVED_DEVELOPMENT_SEEDS = frozenset(range(2026880001, 2026880201)).union(
    *(
        range(first_seed, first_seed + 20)
        for first_seed in (
            2026890001,
            2026891001,
            2026892001,
            2026893001,
        )
    )
)
_MANIFEST_IDS = frozenset(
    {
        "phase-5-external-post-correction-continuum",
        "phase-5-external-post-correction-compact-blend",
    }
)


def _json_bytes(value: object) -> bytes:
    """Serialize one finite governed record canonically."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _canonical_sha256(value: object) -> str:
    """Hash a JSON-compatible value independently of indentation."""
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
        "The approved post-correction external comparison reuses reviewed "
        "geometry, beam, WCS, truth, endpoints, and gates. Every noise seed "
        "is disjoint from checked-in history and the viewed corrective "
        "development populations. No finder output or score is reused."
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
        raise ValueError("post-correction continuum requires four geometries")
    datasets = tuple(
        _changed_seed_record(
            dataset,
            identifier=(
                f"phase5-external-post-correction-continuum-{index + 1}-1024"
            ),
            purpose=(
                "Fresh powered post-correction Continuum geometry "
                f"{index + 1}."
            ),
            first_seed=first_seed,
            realization_count=_CONTINUUM_REALIZATIONS_PER_GEOMETRY,
        )
        for index, (dataset, first_seed) in enumerate(
            zip(template.datasets, _CONTINUUM_FIRST_SEEDS, strict=True)
        )
    )
    return DatasetManifest(
        schema_version=template.schema_version,
        manifest_id="phase-5-external-post-correction-continuum",
        datasets=datasets,
    )


def _compact_manifest(template: DatasetManifest) -> DatasetManifest:
    """Create 800 fresh compact, edge, resolved, and blend images."""
    if len(template.datasets) != 1:
        raise ValueError("post-correction compact requires one geometry")
    dataset = _changed_seed_record(
        template.datasets[0],
        identifier="phase5-external-post-correction-compact-blend-512",
        purpose="Fresh powered post-correction compact/blend comparison.",
        first_seed=_COMPACT_FIRST_SEED,
        realization_count=_COMPACT_REALIZATIONS,
    )
    return DatasetManifest(
        schema_version=template.schema_version,
        manifest_id="phase-5-external-post-correction-compact-blend",
        datasets=(dataset,),
    )


def _manifest_seeds(manifest: DatasetManifest) -> set[int]:
    """Return every independent image seed in one manifest."""
    return {
        recipe.seed
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }


def _population_audit(
    dataset_directory: Path,
    new_manifests: tuple[DatasetManifest, DatasetManifest],
) -> dict[str, object]:
    """Prove disjointness from checked-in and viewed development seeds."""
    historical_seeds: set[int] = set()
    records: list[dict[str, object]] = []
    for path in sorted(dataset_directory.glob("*.json")):
        manifest = DatasetManifest.model_validate_json(path.read_bytes())
        if manifest.manifest_id in _MANIFEST_IDS:
            continue
        seeds = _manifest_seeds(manifest)
        if historical_seeds.intersection(seeds):
            raise ValueError(f"historical dataset seeds overlap in {path}")
        historical_seeds.update(seeds)
        records.append(
            {
                "filename": path.name,
                "manifest_sha256": file_sha256(path),
                "seed_count": len(seeds),
            }
        )
    new_seeds: set[int] = set()
    for manifest in new_manifests:
        seeds = _manifest_seeds(manifest)
        if (
            historical_seeds.intersection(seeds)
            or new_seeds.intersection(seeds)
            or _RESERVED_DEVELOPMENT_SEEDS.intersection(seeds)
        ):
            raise ValueError("post-correction seeds must be globally disjoint")
        new_seeds.update(seeds)
    if len(new_seeds) != _IMAGE_COUNT:
        raise ValueError("post-correction population must have 2488 seeds")
    return {
        "historical_manifest_count": len(records),
        "historical_seed_count": len(historical_seeds),
        "historical_registry_sha256": _canonical_sha256(records),
        "reserved_development_seed_count": len(_RESERVED_DEVELOPMENT_SEEDS),
        "new_seed_count": len(new_seeds),
        "seed_disjoint": True,
    }


def _load_power_review(path: Path) -> dict[str, Any]:
    """Validate the exact reviewed science and sample-size decision."""
    if file_sha256(path) != _POWER_REVIEW_SHA256:
        raise ValueError("approved post-correction power review changed")
    review = cast(
        dict[str, Any],
        json.loads(path.read_text(encoding="utf-8")),
    )
    ledger = cast(dict[str, Any], review.get("cumulative_ledger"))
    planning = cast(dict[str, Any], review.get("planning"))
    power = cast(dict[str, Any], review.get("power"))
    authorization = cast(dict[str, Any], review.get("authorization"))
    if (
        review.get("schema_version") != 1
        or review.get("review_id") != "phase-5-post-correction-power-review"
        or review.get("status") != "ready-for-named-scientific-freeze-review"
        or ledger.get("sha256") != _CUMULATIVE_LEDGER_SHA256
        or ledger.get("candidate_revision") != _CANDIDATE_REVISION
        or ledger.get("candidate_source_tree_sha256")
        != _CANDIDATE_SOURCE_TREE_SHA256
        or ledger.get("candidate_configuration_sha256")
        != _CANDIDATE_CONFIGURATION_SHA256
        or planning.get("paired_comparison_count") != _EXPECTED_PRIOR_COUNT
        or planning.get("minimum_continuum_realization_count")
        != _MINIMUM_CONTINUUM_REALIZATIONS
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
        raise ValueError("approved post-correction power review is invalid")
    assumptions = review.get("paired_assumptions")
    if (
        not isinstance(assumptions, list)
        or len(assumptions) != _EXPECTED_PRIOR_COUNT
    ):
        raise ValueError("post-correction paired power assumptions changed")
    return review


def build_post_correction_documents(
    *,
    repository_root: Path,
    continuum_template_path: Path,
    compact_template_path: Path,
    power_review_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Build both fresh manifests and their approved population freeze."""
    if source_tree_sha256(repository_root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("approved post-correction source tree changed")
    if file_sha256(_CUMULATIVE_LEDGER) != _CUMULATIVE_LEDGER_SHA256:
        raise ValueError("approved cumulative ledger changed")
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
    freeze = {
        "schema_version": 1,
        "contract_id": "phase-5-external-post-correction-population",
        "status": "scientifically-approved-and-frozen-before-output",
        "scientific_approval": {
            "reviewer": "Gemma Danks",
            "approved_on": "2026-08-16",
            "scope": (
                "candidate-and-powered-design-for-freezing-fresh-external-"
                "identities-only"
            ),
        },
        "candidate": {
            "revision": _CANDIDATE_REVISION,
            "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
            "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        },
        "evidence": {
            "cumulative_ledger_path": str(
                _CUMULATIVE_LEDGER.relative_to(repository_root)
            ),
            "cumulative_ledger_sha256": _CUMULATIVE_LEDGER_SHA256,
            "power_review_path": str(
                power_review_path.relative_to(repository_root)
            ),
            "power_review_sha256": _POWER_REVIEW_SHA256,
        },
        "generator": {
            "relative_path": (
                "scripts/validation/"
                "freeze_phase5_external_post_correction_population.py"
            ),
            "sha256": file_sha256(Path(__file__)),
        },
        "closed_campaign_policy": (
            "development-regression-history-not-pooled-rescored-or-reused"
        ),
        "populations": [
            {
                "lane": "continuum",
                "manifest": (
                    "config/datasets/"
                    "phase-5-external-post-correction-continuum.json"
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
                    "phase-5-external-post-correction-compact-blend.json"
                ),
                "manifest_sha256": hashlib.sha256(
                    _json_bytes(compact_document)
                ).hexdigest(),
                "image_count": 800,
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
            "freeze-program-runtime-identities-for-named-one-look-review"
        ),
    }
    return continuum_document, compact_document, freeze


def _parse_args() -> argparse.Namespace:
    """Parse fixed fresh population inputs and write-once outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--continuum-template",
        type=Path,
        default=(
            _ROOT
            / "config/datasets/phase-5-external-post-failure-continuum.json"
        ),
    )
    parser.add_argument(
        "--compact-template",
        type=Path,
        default=(
            _ROOT / "config/datasets/"
            "phase-5-external-post-failure-compact-blend.json"
        ),
    )
    parser.add_argument("--power-review", type=Path, default=_POWER_REVIEW)
    parser.add_argument(
        "--continuum-output",
        type=Path,
        default=(
            _ROOT
            / "config/datasets/phase-5-external-post-correction-continuum.json"
        ),
    )
    parser.add_argument(
        "--compact-output",
        type=Path,
        default=(
            _ROOT / "config/datasets/"
            "phase-5-external-post-correction-compact-blend.json"
        ),
    )
    parser.add_argument(
        "--freeze-output",
        type=Path,
        default=(
            _ROOT / "config/contracts/"
            "phase-5-external-post-correction-population.json"
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
        raise FileExistsError(
            "refusing to overwrite frozen post-correction output"
        )
    continuum, compact, freeze = build_post_correction_documents(
        repository_root=_ROOT,
        continuum_template_path=arguments.continuum_template,
        compact_template_path=arguments.compact_template,
        power_review_path=arguments.power_review,
    )
    for path, document in zip(
        outputs, (continuum, compact, freeze), strict=True
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(_json_bytes(document))
        print(path)


if __name__ == "__main__":
    main()
