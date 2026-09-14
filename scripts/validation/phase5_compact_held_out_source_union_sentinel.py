#!/usr/bin/env python3
"""Build the fresh source-union-aligned Phase 5 sentinel population.

This module only clones already reviewed analytic geometries onto a new,
seed-disjoint qualification population. It never generates pixels, reads a
finder product, or authorizes execution.
"""

from __future__ import annotations

import json
import runpy
from pathlib import Path

from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    DatasetRole,
    iter_dataset_recipes,
    recipe_sha256,
)
from hebog.validation.external_runners import canonical_sha256, file_sha256

build_parent_manifest = runpy.run_path(
    str(Path(__file__).with_name("phase5_compact_held_out_sentinel.py"))
)["build_manifest"]

_FIRST_SEED = 2026971001
_LAST_SEED = 2026971168
_REALIZATIONS_PER_CELL = 4
_MANIFEST_NAME = "phase-5-compact-held-out-source-union-sentinel.json"
_PREFIX = "phase5-source-union-sentinel-"
_PARENT_PREFIX = "phase5-sentinel-"
_EXPECTED_HISTORICAL_AUDIT = {
    "historical_manifest_count": 47,
    "historical_registry_canonical_sha256": (
        "39644fb6ee13279623c2aea52ba8ee818886203c84cf904fe47e9725668f00ff"
    ),
    "historical_seed_count": 21085,
}


def _clone_dataset(
    dataset: DatasetRecord, seeds: tuple[int, int, int, int]
) -> DatasetRecord:
    """Clone one reviewed cell with only prospective identity and seeds."""
    if not dataset.identifier.startswith(_PARENT_PREFIX):
        raise ValueError("parent sentinel dataset identifier changed")
    recipe = dataset.recipe.model_copy(update={"seed": seeds[0]})
    return dataset.model_copy(
        update={
            "identifier": _PREFIX
            + dataset.identifier.removeprefix(_PARENT_PREFIX),
            "role": DatasetRole.QUALIFICATION,
            "purpose": (
                "Fresh source-union-aligned held-out analogue of "
                f"{dataset.identifier}."
            ),
            "provenance": (
                "Seed-disjoint qualification clone of the prospectively "
                "reviewed compact sentinel geometry; no pixels or finder "
                "results were generated before execution."
            ),
            "recipe": recipe,
            "recipe_sha256": recipe_sha256(recipe),
            "noise_realization_seeds": seeds[1:],
        }
    )


def build_manifest() -> DatasetManifest:
    """Return the exact 42-cell, 168-image successor manifest."""
    parent = build_parent_manifest()
    seeds = tuple(range(_FIRST_SEED, _LAST_SEED + 1))
    if len(parent.datasets) * _REALIZATIONS_PER_CELL != len(seeds):
        raise ValueError("parent sentinel population changed")
    datasets = tuple(
        _clone_dataset(
            dataset,
            (
                seeds[index * _REALIZATIONS_PER_CELL],
                seeds[index * _REALIZATIONS_PER_CELL + 1],
                seeds[index * _REALIZATIONS_PER_CELL + 2],
                seeds[index * _REALIZATIONS_PER_CELL + 3],
            ),
        )
        for index, dataset in enumerate(parent.datasets)
    )
    return DatasetManifest(
        schema_version=3,
        manifest_id="phase-5-compact-held-out-source-union-sentinel",
        datasets=datasets,
    )


def _manifest_seeds(manifest: DatasetManifest) -> set[int]:
    """Return every independent seed declared by one manifest."""
    return {
        recipe.seed
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }


def audit_manifest(
    repository_root: Path, manifest: DatasetManifest
) -> dict[str, object]:
    """Prove the new seeds are exact, unique, and historically disjoint."""
    records: list[dict[str, object]] = []
    historical: set[int] = set()
    for path in sorted((repository_root / "config/datasets").glob("*.json")):
        if path.name == _MANIFEST_NAME:
            continue
        prior = DatasetManifest.model_validate_json(path.read_bytes())
        prior_seeds = _manifest_seeds(prior)
        if historical.intersection(prior_seeds):
            raise ValueError("checked-in historical dataset seeds overlap")
        historical.update(prior_seeds)
        records.append(
            {
                "path": path.relative_to(repository_root).as_posix(),
                "seed_count": len(prior_seeds),
                "sha256": file_sha256(path),
            }
        )
    observed = {
        "historical_manifest_count": len(records),
        "historical_registry_canonical_sha256": canonical_sha256(records),
        "historical_seed_count": len(historical),
    }
    prospective = _manifest_seeds(manifest)
    if observed != _EXPECTED_HISTORICAL_AUDIT:
        raise ValueError("historical seed registry changed after review")
    if prospective != set(
        range(_FIRST_SEED, _LAST_SEED + 1)
    ) or not historical.isdisjoint(prospective):
        raise ValueError("prospective sentinel seeds are not fresh and exact")
    return {
        **observed,
        "prospective_seed_count": len(prospective),
        "seed_disjoint": True,
    }


def cell_id(dataset: DatasetRecord) -> str:
    """Return the reviewed cell identity from a successor record."""
    if not dataset.identifier.startswith(_PREFIX):
        raise ValueError("source-union sentinel identifier is malformed")
    return dataset.identifier.removeprefix(_PREFIX)


def adaptive_background_trigger(dataset: DatasetRecord) -> str:
    """Return the prospective trigger stratum retained by the cell name."""
    identifier = cell_id(dataset)
    if identifier.startswith("compact-guard-"):
        return "boundary"
    trigger = identifier.rsplit("-", maxsplit=1)[-1]
    if trigger not in {"below", "boundary", "above"}:
        raise ValueError("source-union sentinel trigger is malformed")
    return trigger


def expected_input_ids(manifest: DatasetManifest) -> tuple[str, ...]:
    """Return all realization identities in deterministic order."""
    return tuple(
        f"{dataset.identifier}-seed-{recipe.seed}"
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    )


def manifest_json_bytes(manifest: DatasetManifest) -> bytes:
    """Serialize one exact finite manifest."""
    return (
        json.dumps(
            manifest.model_dump(mode="json"),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


if __name__ == "__main__":
    root = Path(__file__).parents[2]
    population = build_manifest()
    print(json.dumps(audit_manifest(root, population), sort_keys=True))
