#!/usr/bin/env python3
"""Freeze the approved final Phase 5 qualification population."""

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
    DatasetRole,
    SyntheticRecipe,
    iter_dataset_recipes,
    recipe_sha256,
)
from hebog.validation.external_runners import (
    file_sha256,
    source_tree_sha256,
)
from hebog.validation.post_correction_recovery import (
    post_correction_candidate_configuration_sha256,
)

_ROOT = Path(__file__).parents[2]
_CANDIDATE_REVISION = "90626641c8705ba9d55fdea02a705983528b8aa0"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "e4307246efa7db3ec941b3906f8ce443404b8b84cdc78aa89881e738850cdf8a"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
)
_TEMPLATE_SHA256 = (
    "d10f43874d5f2cf045a87b5f13e5cff8a29e74bc989dbfd113748a61403441b1"
)
_POWER_REVIEW_SHA256 = (
    "bbfab3a0781c8a12083190d8c591152d5c461a45824bab6cba39e770915af9fc"
)
_DESIGN_AUDIT_SHA256 = (
    "9b0fcb89a3ea4a10b791bca3589df8641b672d474e18d4abe0eb59d70292b2dc"
)
_COMPACT_QUALIFICATION_SHA256 = (
    "309ab639cafc5c8aafb75bc85e9b8d531def3e7c51ea424561bb399dc53795f0"
)
_COMPACT_REGRESSION_SHA256 = (
    "43381c51a583e8993bd47ea2c8d557c4315c78200d574a237e51958a1ce100a0"
)
_SCIENTIFIC_CONTRACTS = (
    (
        "config/contracts/phase-5-corrective-a-review.json",
        "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b",
    ),
    (
        "config/contracts/phase-5-multiscale.json",
        "7e79935d4870223d9448efb8c98407de63ecb148d98a4b8f5ef5c684cf55c5fe",
    ),
    (
        "config/contracts/phase-5-scientific-gates.json",
        "cbf467f517af40be798eb4cfbf68315b7b5a11f96688af51973730f7b9cef70b",
    ),
)
_FIRST_SEEDS = (2026940001, 2026941001, 2026942001, 2026943001)
_REALIZATIONS_PER_GEOMETRY = 422
_REALIZATION_COUNT = 1688
_OUTPUT_NAME = "phase-5-final-qualification-continuum.json"


def _json_bytes(value: object) -> bytes:
    """Serialize one finite governed record deterministically."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _canonical_sha256(value: object) -> str:
    """Hash JSON data independently of presentation whitespace."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _qualification_record(
    template: DatasetRecord,
    *,
    index: int,
    first_seed: int,
) -> DatasetRecord:
    """Reuse reviewed truth and geometry with fresh qualification seeds."""
    record = cast(
        dict[str, object],
        deepcopy(template.model_dump(mode="json")),
    )
    record.update(
        {
            "identifier": (
                f"phase5-final-qualification-continuum-{index}-1024"
            ),
            "purpose": (
                "Fresh final Phase 5 Continuum qualification geometry "
                f"{index} of four."
            ),
            "provenance": (
                "Named scientific approval on 2026-08-25 froze a fresh, "
                "seed-disjoint, four-geometry Continuum qualification. "
                "Only the reviewed truth and geometry template is reused; "
                "no image, finder output, score, or viewed seed is reused."
            ),
            "role": DatasetRole.QUALIFICATION.value,
            "noise_realization_seeds": list(
                range(
                    first_seed + 1,
                    first_seed + _REALIZATIONS_PER_GEOMETRY,
                )
            ),
        }
    )
    recipe = cast(dict[str, object], record["recipe"])
    recipe["seed"] = first_seed
    record["recipe_sha256"] = recipe_sha256(
        SyntheticRecipe.model_validate(recipe)
    )
    return DatasetRecord.model_validate(record)


def _qualification_manifest(template_path: Path) -> DatasetManifest:
    """Build the approved balanced Continuum qualification manifest."""
    if file_sha256(template_path) != _TEMPLATE_SHA256:
        raise ValueError("approved qualification geometry template changed")
    template = DatasetManifest.model_validate_json(template_path.read_bytes())
    if len(template.datasets) != len(_FIRST_SEEDS):
        raise ValueError("final qualification requires four geometries")
    datasets = tuple(
        _qualification_record(
            dataset,
            index=index,
            first_seed=first_seed,
        )
        for index, (dataset, first_seed) in enumerate(
            zip(template.datasets, _FIRST_SEEDS, strict=True),
            start=1,
        )
    )
    return template.model_copy(
        update={
            "manifest_id": "phase-5-final-qualification-continuum",
            "description": (
                "Approved fresh final Phase 5 Continuum qualification; "
                "1,688 images balanced over four reviewed geometries."
            ),
            "datasets": datasets,
        }
    )


def _manifest_seeds(manifest: DatasetManifest) -> set[int]:
    """Return every independent realization seed in one manifest."""
    return {
        recipe.seed
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }


def _population_audit(
    dataset_directory: Path,
    manifest: DatasetManifest,
) -> dict[str, object]:
    """Require exact balance and global seed disjointness."""
    historical: set[int] = set()
    records: list[dict[str, object]] = []
    for path in sorted(dataset_directory.glob("*.json")):
        if path.name == _OUTPUT_NAME:
            continue
        previous = DatasetManifest.model_validate_json(path.read_bytes())
        seeds = _manifest_seeds(previous)
        if historical.intersection(seeds):
            raise ValueError(f"historical seeds overlap before freeze: {path}")
        historical.update(seeds)
        records.append(
            {
                "path": path.relative_to(_ROOT).as_posix(),
                "sha256": file_sha256(path),
            }
        )
    new_seeds = _manifest_seeds(manifest)
    geometry_counts = tuple(
        len(dataset.noise_realization_seeds) + 1
        for dataset in manifest.datasets
    )
    if (
        len(new_seeds) != _REALIZATION_COUNT
        or geometry_counts != (_REALIZATIONS_PER_GEOMETRY,) * len(_FIRST_SEEDS)
        or not historical.isdisjoint(new_seeds)
    ):
        raise ValueError(
            "final qualification population is not fresh and balanced"
        )
    return {
        "historical_manifest_count": len(records),
        "historical_registry_sha256": _canonical_sha256(records),
        "historical_seed_count": len(historical),
        "new_seed_count": len(new_seeds),
        "geometry_counts": list(geometry_counts),
        "seed_disjoint": True,
    }


def _load_power_review(path: Path) -> dict[str, Any]:
    """Require the exact passing prospective power review."""
    if file_sha256(path) != _POWER_REVIEW_SHA256:
        raise ValueError("approved qualification power review changed")
    review = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    planning = cast(dict[str, Any], review.get("planning"))
    power = cast(dict[str, Any], review.get("power"))
    authorization = cast(dict[str, Any], review.get("authorization"))
    if (
        review.get("status") != "ready-for-named-scientific-freeze-review"
        or planning.get("selected_continuum_realization_count")
        != _REALIZATION_COUNT
        or planning.get("continuum_realizations_per_geometry")
        != _REALIZATIONS_PER_GEOMETRY
        or planning.get("geometry_count") != len(_FIRST_SEEDS)
        or power.get("combined_familywise_power_lower_bound", 0)
        < power.get("minimum_joint_power", 1)
        or authorization.get("qualification_opened") is not False
    ):
        raise ValueError("approved qualification power review is invalid")
    return review


def _load_compact_evidence(
    qualification_path: Path,
    regression_path: Path,
) -> dict[str, object]:
    """Bind two passing closed compact decisions without pooling them."""
    expected = (
        (qualification_path, _COMPACT_QUALIFICATION_SHA256),
        (regression_path, _COMPACT_REGRESSION_SHA256),
    )
    records: list[dict[str, object]] = []
    for path, sha256 in expected:
        if file_sha256(path) != sha256:
            raise ValueError("approved compact evidence changed")
        decision = cast(
            dict[str, Any], json.loads(path.read_text(encoding="utf-8"))
        )
        failures = decision.get("failure_reasons")
        if decision.get("passed") is not True or failures != []:
            raise ValueError("approved compact evidence changed")
        records.append(
            {
                "path": path.relative_to(_ROOT).as_posix(),
                "sha256": sha256,
                "passed": True,
                "dataset_identifier": cast(
                    dict[str, Any], decision["dataset"]
                )["identifier"],
            }
        )
    return {
        "policy": "bind-closed-evidence-without-pooling-or-rescoring",
        "fresh_compact_lane_required": False,
        "records": records,
    }


def _validate_candidate(repository_root: Path) -> None:
    """Require the exact approved source, configuration, and contracts."""
    if source_tree_sha256(repository_root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("approved candidate source tree changed")
    corrective_review = (
        repository_root / "config/contracts/phase-5-corrective-a-review.json"
    )
    if (
        post_correction_candidate_configuration_sha256(corrective_review)
        != _CANDIDATE_CONFIGURATION_SHA256
    ):
        raise ValueError("approved candidate configuration changed")
    for relative_path, sha256 in _SCIENTIFIC_CONTRACTS:
        if file_sha256(repository_root / relative_path) != sha256:
            raise ValueError(
                f"approved scientific contract changed: {relative_path}"
            )


def build_final_qualification_documents(
    *,
    repository_root: Path,
    continuum_template_path: Path,
    power_review_path: Path,
    compact_qualification_path: Path,
    compact_regression_path: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    """Build the approved fresh manifest and pre-execution freeze record."""
    _validate_candidate(repository_root)
    audit_path = (
        repository_root
        / "benchmark-results/phase-5/qualification-design-audit.json"
    )
    if file_sha256(audit_path) != _DESIGN_AUDIT_SHA256:
        raise ValueError("approved qualification design audit changed")
    power_review = _load_power_review(power_review_path)
    manifest = _qualification_manifest(continuum_template_path)
    manifest_document = cast(
        dict[str, object], manifest.model_dump(mode="json")
    )
    population_audit = _population_audit(
        continuum_template_path.parent,
        manifest,
    )
    planning = cast(dict[str, object], power_review["planning"])
    power = cast(dict[str, object], power_review["power"])
    compact_evidence = _load_compact_evidence(
        compact_qualification_path,
        compact_regression_path,
    )
    freeze: dict[str, object] = {
        "schema_version": 1,
        "contract_id": "phase-5-final-qualification-population",
        "status": "scientifically-approved-and-frozen-before-output",
        "scientific_approval": {
            "reviewer": "Gemma Danks",
            "approved_on": "2026-08-25",
            "scope": (
                "final-qualification-population-freeze-with-closed-compact-"
                "evidence-only-no-execution"
            ),
        },
        "candidate": {
            "revision": _CANDIDATE_REVISION,
            "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
            "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        },
        "scientific_contracts": [
            {"relative_path": path, "sha256": sha256}
            for path, sha256 in _SCIENTIFIC_CONTRACTS
        ],
        "design_evidence": {
            "audit_path": audit_path.relative_to(repository_root).as_posix(),
            "audit_sha256": _DESIGN_AUDIT_SHA256,
            "power_review_path": power_review_path.relative_to(
                repository_root
            ).as_posix(),
            "power_review_sha256": _POWER_REVIEW_SHA256,
        },
        "population": {
            "manifest": (
                "config/datasets/phase-5-final-qualification-continuum.json"
            ),
            "manifest_sha256": hashlib.sha256(
                _json_bytes(manifest_document)
            ).hexdigest(),
            "role": "qualification",
            "image_count": _REALIZATION_COUNT,
            "geometry_count": len(_FIRST_SEEDS),
            "realizations_per_geometry": _REALIZATIONS_PER_GEOMETRY,
            "independent_unit": "noise-seed-image",
            "population_audit": population_audit,
        },
        "power_audit": {
            "minimum_continuum_realization_count": planning[
                "minimum_continuum_realization_count"
            ],
            "selected_continuum_realization_count": planning[
                "selected_continuum_realization_count"
            ],
            "geometry_count": planning["geometry_count"],
            "continuum_realizations_per_geometry": planning[
                "continuum_realizations_per_geometry"
            ],
            "paired_comparison_count": planning["paired_comparison_count"],
            "minimum_joint_power": power["minimum_joint_power"],
            "combined_familywise_power_lower_bound": power[
                "combined_familywise_power_lower_bound"
            ],
        },
        "compact_evidence": compact_evidence,
        "generator": {
            "relative_path": (
                "scripts/validation/"
                "freeze_phase5_final_qualification_population.py"
            ),
            "sha256": file_sha256(Path(__file__)),
        },
        "old_qualification_manifest_preserved_unopened": True,
        "finder_output_generated": False,
        "scientific_products_opened": False,
        "execution_authorized": False,
        "qualification_opened": False,
        "cutover_authorized": False,
        "next_action": (
            "implement-and-freeze-final-runner-compiler-evaluator-and-runtime-"
            "identities-before-no-write-preflight"
        ),
    }
    return manifest_document, freeze


def _parse_args() -> argparse.Namespace:
    """Parse the reviewed inputs and write-once output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--continuum-template",
        type=Path,
        default=(
            _ROOT / "config/datasets/phase-5-external-recovery-continuum.json"
        ),
    )
    parser.add_argument(
        "--power-review",
        type=Path,
        default=(
            _ROOT
            / "benchmark-results/phase-5/viewed-recovery-power-review.json"
        ),
    )
    parser.add_argument(
        "--compact-qualification",
        type=Path,
        default=(
            _ROOT / "benchmark-results/phase-4u/qualification-decision.json"
        ),
    )
    parser.add_argument(
        "--compact-regression",
        type=Path,
        default=(
            _ROOT / "benchmark-results/phase-5/"
            "phase-4-compact-regression-58074cc-decision.json"
        ),
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=(
            _ROOT
            / "config/datasets/phase-5-final-qualification-continuum.json"
        ),
    )
    parser.add_argument(
        "--freeze-output",
        type=Path,
        default=(
            _ROOT
            / "config/contracts/phase-5-final-qualification-population.json"
        ),
    )
    return parser.parse_args()


def _write_once(path: Path, document: object) -> None:
    """Write one governed JSON document without replacing an identity."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(_json_bytes(document))


def main() -> None:
    """Write the approved manifest and freeze record exactly once."""
    arguments = _parse_args()
    if arguments.manifest_output.exists() or arguments.freeze_output.exists():
        raise FileExistsError("refusing to replace final qualification freeze")
    manifest, freeze = build_final_qualification_documents(
        repository_root=_ROOT,
        continuum_template_path=arguments.continuum_template,
        power_review_path=arguments.power_review,
        compact_qualification_path=arguments.compact_qualification,
        compact_regression_path=arguments.compact_regression,
    )
    _write_once(arguments.manifest_output, manifest)
    _write_once(arguments.freeze_output, freeze)


if __name__ == "__main__":
    main()
