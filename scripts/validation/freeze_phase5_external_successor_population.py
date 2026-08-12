"""Freeze the powered Step 2C-PF successor population before finder output."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.contracts import (
    PhaseFiveExternalPowerAudit,
    load_phase_five_external_comparison_protocol,
    load_phase_five_external_execution_decision,
)
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    SyntheticRecipe,
    iter_dataset_recipes,
    recipe_sha256,
)
from hebog.validation.external_runners import (
    file_sha256,
    source_tree_sha256,
)

_CONTINUUM_FIRST_SEEDS = (
    2026820001,
    2026821001,
    2026822001,
    2026823001,
)
_CONTINUUM_REALIZATIONS_PER_GEOMETRY = 150
_COMPACT_FIRST_SEED = 2026830001
_COMPACT_REALIZATIONS = 800
_SUCCESSOR_IMAGE_COUNT: Literal[1400] = 1400
_CANDIDATE_COMMIT = "c1f7eb0bdf5e8581e0024f0f7469c2908a22a594"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "d50be758d788967cf13912190b9de43e021d7e9f4325c2b7e5180f89c29516fd"
)
_CANDIDATE_REVIEW = "config/contracts/phase-5-corrective-a-review.json"
_CANDIDATE_REVIEW_SHA256 = (
    "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
)
_SCIENCE_KERNEL = "src/hebog/validation/external_successor_compiler.py"
_SCIENCE_KERNEL_SHA256 = (
    "8e38de3b4347faee9636b89d03f8cdcdd77e39fd1e087d2b44454e5fd7063c55"
)
_RUNNERS = (
    (
        "scripts/benchmark/run_phase5_external_hebog.py",
        "ea912a43a8523d01af29350e5b9f9523c6175de48f9c4e31e45853c04657592b",
    ),
    (
        "scripts/benchmark/run_phase5_external_pybdsf.py",
        "84a567d06ba4c52bf538c6680fd9259354ef8ea8ad9accf39ad00a8f76fd86f3",
    ),
    (
        "scripts/benchmark/run_phase5_external_aegean.py",
        "016d6a852b0564c7a8f56068a97e9a8be3320ef91b3097099f1f9405f8320ae9",
    ),
)
_SUCCESSOR_MANIFEST_IDS = frozenset(
    {
        "phase-5-external-successor-continuum",
        "phase-5-external-successor-compact-blend",
    }
)


class _FreezeModel(BaseModel):
    """Strict immutable base for the prospective freeze document."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class _Artifact(_FreezeModel):
    """One exact repository artifact used by the successor."""

    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _SourceBinding(_FreezeModel):
    """Candidate source, science kernel, and corrected runner identities."""

    candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_review: _Artifact
    science_kernel: _Artifact
    corrected_runners: tuple[_Artifact, _Artifact, _Artifact]
    candidate_runtime_status: Literal[
        "rebuild-bound-source-before-execution-freeze"
    ]


class _RuntimeInventory(_FreezeModel):
    """One exact dependency inventory reserved for successor execution."""

    finder_id: Literal[
        "hebog",
        "released-pybdsf",
        "pinned-pybdsf-master",
        "aegean",
    ]
    version: str = Field(min_length=1)
    python_version: str = Field(min_length=1)
    dependency_inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    container_image_digest: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    image_status: Literal[
        "immutable-reference-present",
        "candidate-rebuild-required",
    ]

    @model_validator(mode="after")
    def validate_image_state(self) -> Self:
        """Require only the not-yet-rebuilt candidate to lack an image."""
        candidate = self.finder_id == "hebog"
        if candidate != (self.container_image_digest is None):
            raise ValueError("successor runtime image state is inconsistent")
        expected = (
            "candidate-rebuild-required"
            if candidate
            else "immutable-reference-present"
        )
        if self.image_status != expected:
            raise ValueError("successor runtime status is inconsistent")
        return self


class _Population(_FreezeModel):
    """One generated successor lane and its exact manifest identity."""

    lane: Literal["continuum", "compact-blend"]
    manifest: str = Field(pattern=r"^config/datasets/[a-z0-9-]+\.json$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_count: Literal[600, 800]
    role: Literal["regression"]
    independent_unit: Literal["noise-seed-image"]


class _PopulationAudit(_FreezeModel):
    """Machine-derived proof that all successor seeds are new."""

    historical_manifest_count: int = Field(ge=1)
    historical_seed_count: int = Field(ge=1)
    historical_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    new_seed_count: Literal[1400]
    seed_disjoint: Literal[True]


class _SuccessorPopulationFreeze(_FreezeModel):
    """Powered population and pre-results implementation identity freeze."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-external-successor-population"]
    status: Literal["power-audited-before-finder-output"]
    prior_power_design: _Artifact
    prior_runtime_inventory_design: _Artifact
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
    runtime_inventories: tuple[
        _RuntimeInventory,
        _RuntimeInventory,
        _RuntimeInventory,
        _RuntimeInventory,
    ]
    pre_results_checks: tuple[
        Literal["corrected-runner-matrix-12-of-12-applicable-cells-passed"],
        Literal["mask-only-kernel-focused-line-and-branch-coverage-complete"],
        Literal["reference-images-and-inventories-read-only-verified"],
    ]
    finder_output_generated: Literal[False]
    finder_output_opened: Literal[False]
    execution_authorized: Literal[False]
    qualification_opened: Literal[False]
    next_action: Literal[
        "rebuild-candidate-runtime-and-freeze-composed-one-look-protocol"
    ]

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Keep lane, runner, and runtime identities canonical."""
        if tuple(item.lane for item in self.populations) != (
            "continuum",
            "compact-blend",
        ):
            raise ValueError("successor population order is not canonical")
        if tuple(
            item.relative_path
            for item in self.source_binding.corrected_runners
        ) != tuple(path for path, _ in _RUNNERS):
            raise ValueError("successor runner order is not canonical")
        if tuple(item.finder_id for item in self.runtime_inventories) != (
            "hebog",
            "released-pybdsf",
            "pinned-pybdsf-master",
            "aegean",
        ):
            raise ValueError("successor runtime order is not canonical")
        return self


def _json_bytes(document: dict[str, object]) -> bytes:
    """Serialize one governed record canonically for hashing and review."""
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


def _changed_seed_record(  # noqa: PLR0913
    template: DatasetRecord,
    *,
    identifier: str,
    purpose: str,
    provenance: str,
    first_seed: int,
    realization_count: int,
) -> DatasetRecord:
    """Copy a reviewed geometry while replacing every noise seed."""
    record = cast(
        dict[str, object],
        deepcopy(template.model_dump(mode="json")),
    )
    record["identifier"] = identifier
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
    """Create 600 successor images over the four reviewed geometries."""
    if len(template.datasets) != len(_CONTINUUM_FIRST_SEEDS):
        raise ValueError("successor continuum template needs four geometries")
    datasets = tuple(
        _changed_seed_record(
            dataset,
            identifier=(
                f"phase5-external-successor-continuum-{index + 1}-1024"
            ),
            purpose=(
                "Fresh Step 2C-PF full-continuum comparison geometry "
                f"{index + 1}."
            ),
            provenance=(
                "Step 2C-PF reuses the reviewed pre-results geometry, beam, "
                "WCS, and truth design only. Every noise seed is disjoint "
                "from the closed campaign and all historical manifests; no "
                "finder output or scientific result is reused."
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
        manifest_id="phase-5-external-successor-continuum",
        datasets=datasets,
    )


def _compact_manifest(template: DatasetManifest) -> DatasetManifest:
    """Create 800 successor compact/blend images from reviewed truth."""
    if len(template.datasets) != 1:
        raise ValueError("successor compact template needs one geometry")
    dataset = _changed_seed_record(
        template.datasets[0],
        identifier="phase5-external-successor-compact-blend-512",
        purpose=(
            "Fresh Step 2C-PF compact, resolved, edge, and blend comparison."
        ),
        provenance=(
            "Step 2C-PF reuses the reviewed pre-results compact/blend truth "
            "design only. Every noise seed is disjoint from the closed "
            "campaign and all historical manifests; no finder output or "
            "scientific result is reused."
        ),
        first_seed=_COMPACT_FIRST_SEED,
        realization_count=_COMPACT_REALIZATIONS,
    )
    return DatasetManifest(
        schema_version=template.schema_version,
        manifest_id="phase-5-external-successor-compact-blend",
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
    *,
    dataset_directory: Path,
    new_manifests: tuple[DatasetManifest, DatasetManifest],
) -> _PopulationAudit:
    """Prove disjointness from all checked-in historical manifests."""
    historical_seeds: set[int] = set()
    historical_records: list[dict[str, object]] = []
    for path in sorted(dataset_directory.glob("*.json")):
        manifest = DatasetManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if manifest.manifest_id in _SUCCESSOR_MANIFEST_IDS:
            continue
        seeds = _manifest_seeds(manifest)
        if historical_seeds.intersection(seeds):
            raise ValueError(f"historical dataset seeds overlap in {path}")
        historical_seeds.update(seeds)
        historical_records.append(
            {
                "filename": path.name,
                "manifest_sha256": file_sha256(path),
                "seed_count": len(seeds),
            }
        )
    successor_seeds: set[int] = set()
    for manifest in new_manifests:
        seeds = _manifest_seeds(manifest)
        if historical_seeds.intersection(
            seeds
        ) or successor_seeds.intersection(seeds):
            raise ValueError("Step 2C-PF seeds must be globally disjoint")
        successor_seeds.update(seeds)
    if len(successor_seeds) != _SUCCESSOR_IMAGE_COUNT:
        raise ValueError(
            "Step 2C-PF successor population must have 1400 seeds"
        )
    return _PopulationAudit(
        historical_manifest_count=len(historical_records),
        historical_seed_count=len(historical_seeds),
        historical_registry_sha256=_canonical_sha256(historical_records),
        new_seed_count=_SUCCESSOR_IMAGE_COUNT,
        seed_disjoint=True,
    )


def _source_binding(repository_root: Path) -> _SourceBinding:
    """Verify and bind the selected source, kernel, and corrected runners."""
    observed_source = source_tree_sha256(repository_root)
    if observed_source != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("successor candidate source tree changed")
    kernel = repository_root / _SCIENCE_KERNEL
    if file_sha256(kernel) != _SCIENCE_KERNEL_SHA256:
        raise ValueError("successor science kernel changed")
    review = repository_root / _CANDIDATE_REVIEW
    if file_sha256(review) != _CANDIDATE_REVIEW_SHA256:
        raise ValueError("successor candidate review changed")
    artifacts: list[_Artifact] = []
    for relative_path, expected_sha256 in _RUNNERS:
        if file_sha256(repository_root / relative_path) != expected_sha256:
            raise ValueError(
                f"successor corrected runner changed: {relative_path}"
            )
        artifacts.append(
            _Artifact(relative_path=relative_path, sha256=expected_sha256)
        )
    return _SourceBinding(
        candidate_commit=_CANDIDATE_COMMIT,
        source_tree_sha256=observed_source,
        candidate_review=_Artifact(
            relative_path=_CANDIDATE_REVIEW,
            sha256=_CANDIDATE_REVIEW_SHA256,
        ),
        science_kernel=_Artifact(
            relative_path=_SCIENCE_KERNEL,
            sha256=_SCIENCE_KERNEL_SHA256,
        ),
        corrected_runners=cast(
            tuple[_Artifact, _Artifact, _Artifact],
            tuple(artifacts),
        ),
        candidate_runtime_status=(
            "rebuild-bound-source-before-execution-freeze"
        ),
    )


def _runtime_inventories(
    prior_protocol_path: Path,
    repository_root: Path,
) -> tuple[
    _RuntimeInventory,
    _RuntimeInventory,
    _RuntimeInventory,
    _RuntimeInventory,
]:
    """Carry forward exact reviewed package inventories, not old authority."""
    protocol = load_phase_five_external_comparison_protocol(
        prior_protocol_path
    )
    decision = load_phase_five_external_execution_decision(
        repository_root
        / "config/contracts/phase-5-external-execution-decision.json"
    )
    references = {item.finder_id: item for item in protocol.references}
    return (
        _RuntimeInventory(
            finder_id="hebog",
            version="0.6.0",
            python_version="3.14.7",
            dependency_inventory_sha256=(
                decision.hebog_dependency_inventory_sha256
            ),
            container_image_digest=None,
            image_status="candidate-rebuild-required",
        ),
        _RuntimeInventory(
            finder_id="released-pybdsf",
            version=references["released-pybdsf"].version,
            python_version="3.12.3",
            dependency_inventory_sha256=(
                references["released-pybdsf"].dependency_inventory_sha256
            ),
            container_image_digest=(
                references["released-pybdsf"].container_image_digest
            ),
            image_status="immutable-reference-present",
        ),
        _RuntimeInventory(
            finder_id="pinned-pybdsf-master",
            version=references["pinned-pybdsf-master"].version,
            python_version="3.12.3",
            dependency_inventory_sha256=(
                references["pinned-pybdsf-master"].dependency_inventory_sha256
            ),
            container_image_digest=(
                references["pinned-pybdsf-master"].container_image_digest
            ),
            image_status="immutable-reference-present",
        ),
        _RuntimeInventory(
            finder_id="aegean",
            version=references["aegean"].version,
            python_version="3.12.3",
            dependency_inventory_sha256=(
                references["aegean"].dependency_inventory_sha256
            ),
            container_image_digest=(
                references["aegean"].container_image_digest
            ),
            image_status="immutable-reference-present",
        ),
    )


def _documents(
    *,
    continuum_template_path: Path,
    compact_template_path: Path,
    dataset_directory: Path,
    prior_protocol_path: Path,
    repository_root: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Build and validate both new manifests and their power freeze."""
    continuum_template = DatasetManifest.model_validate_json(
        continuum_template_path.read_text(encoding="utf-8")
    )
    compact_template = DatasetManifest.model_validate_json(
        compact_template_path.read_text(encoding="utf-8")
    )
    continuum = _continuum_manifest(continuum_template)
    compact = _compact_manifest(compact_template)
    population_audit = _population_audit(
        dataset_directory=dataset_directory,
        new_manifests=(continuum, compact),
    )
    continuum_document = cast(
        dict[str, object], continuum.model_dump(mode="json")
    )
    compact_document = cast(dict[str, object], compact.model_dump(mode="json"))
    prior_protocol = load_phase_five_external_comparison_protocol(
        prior_protocol_path
    )
    power_audit = PhaseFiveExternalPowerAudit.model_validate(
        prior_protocol.power_audit.model_dump(mode="json")
    )
    if power_audit.combined_familywise_power_lower_bound < (
        power_audit.minimum_joint_power
    ):
        raise ValueError("successor population power is below target")
    freeze = _SuccessorPopulationFreeze(
        schema_version=1,
        contract_id="phase-5-external-successor-population",
        status="power-audited-before-finder-output",
        prior_power_design=_Artifact(
            relative_path=prior_protocol_path.relative_to(
                repository_root
            ).as_posix(),
            sha256=file_sha256(prior_protocol_path),
        ),
        prior_runtime_inventory_design=_Artifact(
            relative_path=(
                "config/contracts/phase-5-external-execution-decision.json"
            ),
            sha256=file_sha256(
                repository_root
                / "config/contracts/phase-5-external-execution-decision.json"
            ),
        ),
        closed_campaign_policy=(
            "diagnostic-history-not-pooled-rescored-or-reused"
        ),
        populations=(
            _Population(
                lane="continuum",
                manifest=(
                    "config/datasets/phase-5-external-successor-continuum.json"
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
                    "phase-5-external-successor-compact-blend.json"
                ),
                manifest_sha256=hashlib.sha256(
                    _json_bytes(compact_document)
                ).hexdigest(),
                image_count=800,
                role="regression",
                independent_unit="noise-seed-image",
            ),
        ),
        population_audit=population_audit,
        power_audit=power_audit,
        power_reuse_basis=(
            "same-reviewed-geometries-endpoints-margins-and-sample-sizes"
        ),
        source_binding=_source_binding(repository_root),
        runtime_inventories=_runtime_inventories(
            prior_protocol_path,
            repository_root,
        ),
        pre_results_checks=(
            "corrected-runner-matrix-12-of-12-applicable-cells-passed",
            "mask-only-kernel-focused-line-and-branch-coverage-complete",
            "reference-images-and-inventories-read-only-verified",
        ),
        finder_output_generated=False,
        finder_output_opened=False,
        execution_authorized=False,
        qualification_opened=False,
        next_action=(
            "rebuild-candidate-runtime-and-freeze-composed-one-look-protocol"
        ),
    )
    return (
        continuum_document,
        compact_document,
        cast(dict[str, object], freeze.model_dump(mode="json")),
    )


def _parse_args() -> argparse.Namespace:
    """Parse paths while keeping every scientific choice fixed in code."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--continuum-template",
        type=Path,
        default=root / "config/datasets/phase-5-external-continuum.json",
    )
    parser.add_argument(
        "--compact-template",
        type=Path,
        default=(root / "config/datasets/phase-5-external-compact-blend.json"),
    )
    parser.add_argument(
        "--prior-protocol",
        type=Path,
        default=root / "config/contracts/phase-5-external-comparison.json",
    )
    parser.add_argument(
        "--continuum-output",
        type=Path,
        default=(
            root / "config/datasets/phase-5-external-successor-continuum.json"
        ),
    )
    parser.add_argument(
        "--compact-output",
        type=Path,
        default=(
            root / "config/datasets/"
            "phase-5-external-successor-compact-blend.json"
        ),
    )
    parser.add_argument(
        "--freeze-output",
        type=Path,
        default=(
            root
            / "config/contracts/phase-5-external-successor-population.json"
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Write the three pre-results records once and refuse replacement."""
    arguments = _parse_args()
    outputs = (
        arguments.continuum_output,
        arguments.compact_output,
        arguments.freeze_output,
    )
    existing = tuple(path for path in outputs if path.exists())
    if existing:
        raise FileExistsError(
            f"refusing to overwrite frozen Step 2C-PF inputs: {existing}"
        )
    documents = _documents(
        continuum_template_path=arguments.continuum_template,
        compact_template_path=arguments.compact_template,
        dataset_directory=arguments.continuum_output.parent,
        prior_protocol_path=arguments.prior_protocol,
        repository_root=Path(__file__).parents[2],
    )
    for path, document in zip(outputs, documents, strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_json_bytes(document))


if __name__ == "__main__":
    main()
