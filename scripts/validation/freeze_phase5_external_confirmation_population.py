#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Freeze a seed-disjoint confirmation population before finder output."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.contracts import PhaseFiveExternalPowerAudit
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    SyntheticRecipe,
    iter_dataset_recipes,
    recipe_sha256,
)
from hebog.validation.external_runners import file_sha256, source_tree_sha256

_CONTINUUM_FIRST_SEEDS = (
    2026840001,
    2026841001,
    2026842001,
    2026843001,
)
_CONTINUUM_REALIZATIONS_PER_GEOMETRY = 150
_COMPACT_FIRST_SEED = 2026850001
_COMPACT_REALIZATIONS = 800
_IMAGE_COUNT: Literal[1400] = 1400
_CANDIDATE_COMMIT = "ee69ebae316e79b793c410d36c94fb3e0121908d"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "b002878831c5f00fbe15c7b1d5a34abcee773aa35457b6fb2d56acef050fc942"
)
_CANDIDATE_REVIEW = "config/contracts/phase-5-corrective-a-review.json"
_CANDIDATE_REVIEW_SHA256 = (
    "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
)
_SCIENCE_KERNEL = "src/hebog/validation/external_successor_compiler.py"
_SCIENCE_KERNEL_SHA256 = (
    "8e38de3b4347faee9636b89d03f8cdcdd77e39fd1e087d2b44454e5fd7063c55"
)
_RUNTIME_DIGEST = (
    "sha256:88696bd96844d5d28022ce21185b731b2d78183192db53991e8b04e556dfcbf3"
)
_RUNTIME_INVENTORY_SHA256 = (
    "d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2"
)
_CONFIRMATION_MANIFEST_IDS = frozenset(
    {
        "phase-5-external-confirmation-continuum",
        "phase-5-external-confirmation-compact-blend",
    }
)


class _FreezeModel(BaseModel):
    """Strict immutable base for confirmation-freeze records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class _Artifact(_FreezeModel):
    """One repository artifact identity."""

    relative_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _Population(_FreezeModel):
    """One powered confirmation population lane."""

    lane: Literal["continuum", "compact-blend"]
    manifest: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_count: int = Field(gt=0)
    role: Literal["regression"]
    independent_unit: Literal["noise-seed-image"]


class _PopulationAudit(_FreezeModel):
    """Machine-derived proof that every confirmation seed is new."""

    historical_manifest_count: int = Field(ge=1)
    historical_seed_count: int = Field(ge=1)
    historical_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    new_seed_count: Literal[1400]
    seed_disjoint: Literal[True]


class _SourceBinding(_FreezeModel):
    """Exact candidate science and runtime identity."""

    candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_review: _Artifact
    science_kernel: _Artifact
    container_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dependency_inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ConfirmationPopulationFreeze(_FreezeModel):
    """Powered population and pre-results implementation identity freeze."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-external-confirmation-population"]
    status: Literal["power-audited-before-finder-output"]
    predecessor_population: _Artifact
    generator: _Artifact
    closed_campaign_policy: Literal[
        "diagnostic-history-not-pooled-rescored-or-reused"
    ]
    populations: tuple[_Population, _Population]
    population_audit: _PopulationAudit
    power_audit: PhaseFiveExternalPowerAudit
    power_reuse_basis: Literal[
        "same-reviewed-geometries-endpoints-margins-and-sample-sizes"
    ]
    source_binding: _SourceBinding
    finder_output_generated: Literal[False]
    finder_output_opened: Literal[False]
    execution_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_population_order(self) -> ConfirmationPopulationFreeze:
        """Keep both confirmation lanes canonical."""
        if tuple(item.lane for item in self.populations) != (
            "continuum",
            "compact-blend",
        ):
            raise ValueError("confirmation population order is not canonical")
        return self


def _json_bytes(document: dict[str, object]) -> bytes:
    """Serialize one governed record canonically."""
    return (
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _canonical_sha256(value: object) -> str:
    """Hash one JSON-compatible value independently of presentation."""
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
    """Copy reviewed geometry while replacing every noise seed."""
    record = cast(
        dict[str, object],
        deepcopy(template.model_dump(mode="json")),
    )
    record["identifier"] = identifier
    record["purpose"] = purpose
    record["provenance"] = (
        "Phase 5 confirmation reuses only the reviewed geometry, beam, WCS, "
        "truth, endpoint, and sample-size design. Every noise seed is "
        "disjoint from all historical manifests; no finder output or "
        "scientific result is reused."
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
    """Create 600 fresh images over the four reviewed geometries."""
    if len(template.datasets) != len(_CONTINUUM_FIRST_SEEDS):
        raise ValueError(
            "confirmation continuum template needs four geometries"
        )
    datasets = tuple(
        _changed_seed_record(
            dataset,
            identifier=(
                f"phase5-external-confirmation-continuum-{index + 1}-1024"
            ),
            purpose=(
                "Fresh Phase 5 full-continuum confirmation geometry "
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
        manifest_id="phase-5-external-confirmation-continuum",
        datasets=datasets,
    )


def _compact_manifest(template: DatasetManifest) -> DatasetManifest:
    """Create 800 fresh compact, edge, resolved, and blend images."""
    if len(template.datasets) != 1:
        raise ValueError("confirmation compact template needs one geometry")
    dataset = _changed_seed_record(
        template.datasets[0],
        identifier="phase5-external-confirmation-compact-blend-512",
        purpose=(
            "Fresh Phase 5 compact, edge, resolved, and blend confirmation."
        ),
        first_seed=_COMPACT_FIRST_SEED,
        realization_count=_COMPACT_REALIZATIONS,
    )
    return DatasetManifest(
        schema_version=template.schema_version,
        manifest_id="phase-5-external-confirmation-compact-blend",
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
) -> _PopulationAudit:
    """Prove disjointness from all checked-in historical manifests."""
    historical_seeds: set[int] = set()
    records: list[dict[str, object]] = []
    for path in sorted(dataset_directory.glob("*.json")):
        manifest = DatasetManifest.model_validate_json(path.read_bytes())
        if manifest.manifest_id in _CONFIRMATION_MANIFEST_IDS:
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
    confirmation_seeds: set[int] = set()
    for manifest in new_manifests:
        seeds = _manifest_seeds(manifest)
        if historical_seeds.intersection(
            seeds
        ) or confirmation_seeds.intersection(seeds):
            raise ValueError("confirmation seeds must be globally disjoint")
        confirmation_seeds.update(seeds)
    if len(confirmation_seeds) != _IMAGE_COUNT:
        raise ValueError("confirmation population must have 1400 seeds")
    return _PopulationAudit(
        historical_manifest_count=len(records),
        historical_seed_count=len(historical_seeds),
        historical_registry_sha256=_canonical_sha256(records),
        new_seed_count=_IMAGE_COUNT,
        seed_disjoint=True,
    )


def build_confirmation_documents(
    *,
    repository_root: Path,
    continuum_template_path: Path,
    compact_template_path: Path,
    predecessor_population_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Build both fresh manifests and their governed freeze."""
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
    predecessor = json.loads(predecessor_population_path.read_bytes())
    power_audit = PhaseFiveExternalPowerAudit.model_validate(
        cast(dict[str, Any], predecessor)["power_audit"]
    )
    if power_audit.combined_familywise_power_lower_bound < (
        power_audit.minimum_joint_power
    ):
        raise ValueError("confirmation population power is below target")
    if source_tree_sha256(repository_root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("confirmation candidate source tree changed")
    review_path = repository_root / _CANDIDATE_REVIEW
    kernel_path = repository_root / _SCIENCE_KERNEL
    if file_sha256(review_path) != _CANDIDATE_REVIEW_SHA256:
        raise ValueError("confirmation candidate review changed")
    if file_sha256(kernel_path) != _SCIENCE_KERNEL_SHA256:
        raise ValueError("confirmation science kernel changed")
    audit = _population_audit(
        continuum_template_path.parent,
        (continuum, compact),
    )
    freeze = ConfirmationPopulationFreeze(
        schema_version=1,
        contract_id="phase-5-external-confirmation-population",
        status="power-audited-before-finder-output",
        predecessor_population=_Artifact(
            relative_path=predecessor_population_path.relative_to(
                repository_root
            ).as_posix(),
            sha256=file_sha256(predecessor_population_path),
        ),
        generator=_Artifact(
            relative_path=(
                "scripts/validation/"
                "freeze_phase5_external_confirmation_population.py"
            ),
            sha256=file_sha256(
                repository_root / "scripts/validation/"
                "freeze_phase5_external_confirmation_population.py"
            ),
        ),
        closed_campaign_policy=(
            "diagnostic-history-not-pooled-rescored-or-reused"
        ),
        populations=(
            _Population(
                lane="continuum",
                manifest=(
                    "config/datasets/phase-5-external-confirmation-continuum.json"
                ),
                manifest_sha256=hashlib.sha256(
                    _json_bytes(continuum_document)
                ).hexdigest(),
                image_count=600,
                role="regression",
                independent_unit="noise-seed-image",
            ),
            _Population(
                lane="compact-blend",
                manifest=(
                    "config/datasets/"
                    "phase-5-external-confirmation-compact-blend.json"
                ),
                manifest_sha256=hashlib.sha256(
                    _json_bytes(compact_document)
                ).hexdigest(),
                image_count=800,
                role="regression",
                independent_unit="noise-seed-image",
            ),
        ),
        population_audit=audit,
        power_audit=power_audit,
        power_reuse_basis=(
            "same-reviewed-geometries-endpoints-margins-and-sample-sizes"
        ),
        source_binding=_SourceBinding(
            candidate_commit=_CANDIDATE_COMMIT,
            source_tree_sha256=_CANDIDATE_SOURCE_TREE_SHA256,
            candidate_review=_Artifact(
                relative_path=_CANDIDATE_REVIEW,
                sha256=_CANDIDATE_REVIEW_SHA256,
            ),
            science_kernel=_Artifact(
                relative_path=_SCIENCE_KERNEL,
                sha256=_SCIENCE_KERNEL_SHA256,
            ),
            container_image_digest=_RUNTIME_DIGEST,
            dependency_inventory_sha256=_RUNTIME_INVENTORY_SHA256,
        ),
        finder_output_generated=False,
        finder_output_opened=False,
        execution_authorized=False,
        qualification_opened=False,
    )
    return (
        continuum_document,
        compact_document,
        cast(dict[str, object], freeze.model_dump(mode="json")),
    )


def _parse_args() -> argparse.Namespace:
    """Parse fixed confirmation outputs."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--continuum-output",
        type=Path,
        default=(
            root
            / "config/datasets/phase-5-external-confirmation-continuum.json"
        ),
    )
    parser.add_argument(
        "--compact-output",
        type=Path,
        default=(
            root / "config/datasets/"
            "phase-5-external-confirmation-compact-blend.json"
        ),
    )
    parser.add_argument(
        "--freeze-output",
        type=Path,
        default=(
            root
            / "config/contracts/phase-5-external-confirmation-population.json"
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Write the three pre-results records once and refuse replacement."""
    root = Path(__file__).parents[2]
    arguments = _parse_args()
    outputs = (
        arguments.continuum_output,
        arguments.compact_output,
        arguments.freeze_output,
    )
    if any(path.exists() for path in outputs):
        raise FileExistsError("refusing to overwrite confirmation inputs")
    documents = build_confirmation_documents(
        repository_root=root,
        continuum_template_path=(
            root / "config/datasets/phase-5-external-successor-continuum.json"
        ),
        compact_template_path=(
            root
            / "config/datasets/phase-5-external-successor-compact-blend.json"
        ),
        predecessor_population_path=(
            root
            / "config/contracts/phase-5-external-successor-population.json"
        ),
    )
    for path, document in zip(outputs, documents, strict=True):
        path.write_bytes(_json_bytes(document))


if __name__ == "__main__":
    main()
