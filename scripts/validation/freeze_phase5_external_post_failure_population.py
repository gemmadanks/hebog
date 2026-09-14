#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Freeze approved fresh post-failure populations and exact power priors."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from math import isclose
from pathlib import Path
from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    SyntheticRecipe,
    iter_dataset_recipes,
    recipe_sha256,
)
from hebog.validation.external_runners import file_sha256, source_tree_sha256
from hebog.validation.phase_five_post_failure_power import (
    PairedPowerPrior,
    conservative_familywise_power,
    minimum_realization_count,
    prospective_joint_power,
)

_CONTINUUM_FIRST_SEEDS = (
    2026860001,
    2026861001,
    2026862001,
    2026863001,
)
_CONTINUUM_REALIZATIONS_PER_GEOMETRY = 400
_COMPACT_FIRST_SEED = 2026870001
_COMPACT_REALIZATIONS = 800
_IMAGE_COUNT: Literal[2400] = 2400
_EXPECTED_PRIOR_COUNT = 226
_CANDIDATE_COMMIT = "63e4b5886a3f5acb75125d258f5b71c13ca4eeaf"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "864d8f2b06cc8c561c8d1f7e2b2f9a511baa5e170b91150bf4c6fa5255002d75"
)
_PRE_REVIEW_SHA256 = (
    "31ca691e1c5fc7ca905e0ad874906533ed55b7a4746c68543457951264aba07d"
)
_PRE_REVIEW_PATH = (
    "benchmark-results/phase-5/post-failure-power-pre-review.json"
)
_POST_FAILURE_MANIFEST_IDS = frozenset(
    {
        "phase-5-external-post-failure-continuum",
        "phase-5-external-post-failure-compact-blend",
    }
)


class _FreezeModel(BaseModel):
    """Strict immutable base for post-failure freeze records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class _Artifact(_FreezeModel):
    """One exact repository or controlled-host artifact."""

    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _PairedPrior(_FreezeModel):
    """One exact endpoint/reference planning prior."""

    endpoint_id: str = Field(min_length=1)
    reference_id: str = Field(min_length=1)
    metric_family: str = Field(min_length=1)
    practical_regression_margin: float = Field(gt=0, allow_inf_nan=False)
    planning_expected_regression: float = Field(allow_inf_nan=False)
    planning_paired_standard_deviation: float = Field(
        gt=0,
        allow_inf_nan=False,
    )
    closed_positive_regression: float = Field(allow_inf_nan=False)
    closed_paired_standard_deviation: float = Field(
        ge=0,
        allow_inf_nan=False,
    )

    def planning_prior(self) -> PairedPowerPrior:
        """Return the pure calculator's immutable planning record."""
        return PairedPowerPrior(**self.model_dump())


class _EndpointPowerAudit(_FreezeModel):
    """Exact post-failure endpoint-specific power contract."""

    method: Literal[
        "endpoint-reference-cluster-normal-planning-plus-conservative-union-"
        "lower-bound"
    ]
    confidence_level: float = Field(ge=0.95, le=0.95, allow_inf_nan=False)
    minimum_joint_power: float = Field(ge=0.9, le=0.9, allow_inf_nan=False)
    variance_inflation: float = Field(
        ge=1.25,
        le=1.25,
        allow_inf_nan=False,
    )
    advantage_retention: float = Field(
        ge=0.5,
        le=0.5,
        allow_inf_nan=False,
    )
    family_variance_floor_retained: Literal[True]
    paired_assumptions: tuple[_PairedPrior, ...] = Field(
        min_length=_EXPECTED_PRIOR_COUNT,
        max_length=_EXPECTED_PRIOR_COUNT,
    )
    minimum_continuum_realization_count: Literal[1550]
    continuum_realization_count: Literal[1600]
    continuum_geometry_count: Literal[4]
    continuum_realizations_per_geometry: Literal[400]
    continuum_familywise_power_lower_bound: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    compact_realization_count: Literal[800]
    compact_familywise_power_lower_bound: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    combined_familywise_power_lower_bound: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    assumption_failure: Literal[
        "observed-variance-above-endpoint-bound-makes-comparison-underpowered"
    ]

    @model_validator(mode="after")
    def validate_power(self) -> Self:
        """Recompute the approved minimum and both conservative bounds."""
        identities = tuple(
            (item.endpoint_id, item.reference_id)
            for item in self.paired_assumptions
        )
        if len(identities) != len(set(identities)):
            raise ValueError("paired power identities must be unique")
        priors = tuple(
            item.planning_prior() for item in self.paired_assumptions
        )
        minimum = minimum_realization_count(
            priors,
            compact_familywise_power=(
                self.compact_familywise_power_lower_bound
            ),
            minimum_joint_power=self.minimum_joint_power,
        )
        continuum = conservative_familywise_power(
            priors,
            self.continuum_realization_count,
        )
        combined = prospective_joint_power(
            continuum,
            self.compact_familywise_power_lower_bound,
        )
        expected = (
            (minimum, self.minimum_continuum_realization_count),
            (continuum, self.continuum_familywise_power_lower_bound),
            (combined, self.combined_familywise_power_lower_bound),
        )
        if any(
            not isclose(actual, declared, rel_tol=0.0, abs_tol=1e-12)
            for actual, declared in expected
        ):
            raise ValueError("post-failure power audit does not recompute")
        return self


class _Population(_FreezeModel):
    """One fresh post-failure population lane."""

    lane: Literal["continuum", "compact-blend"]
    manifest: str = Field(pattern=r"^config/datasets/[a-z0-9-]+\.json$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_count: Literal[800, 1600]
    role: Literal["regression"]
    independent_unit: Literal["noise-seed-image"]


class _PopulationAudit(_FreezeModel):
    """Machine-derived proof that every post-failure seed is new."""

    historical_manifest_count: int = Field(ge=1)
    historical_seed_count: int = Field(ge=1)
    historical_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    new_seed_count: Literal[2400]
    seed_disjoint: Literal[True]


class _SourceBinding(_FreezeModel):
    """Exact reviewed candidate science identity."""

    candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observable_measurement: _Artifact
    observable_compiler: _Artifact
    candidate_runner: _Artifact
    candidate_runtime_status: Literal[
        "rebuild-bound-source-before-execution-decision"
    ]


class _ScientificApproval(_FreezeModel):
    """Named approval of the scientific and power pre-review."""

    reviewer: Literal["Gemma Danks"]
    approved_on: Literal["2026-08-14"]
    pre_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope: Literal[
        "implementation-and-freeze-only-separate-execution-approval-required"
    ]


class PostFailurePopulationFreeze(_FreezeModel):
    """Fresh population, power, and candidate-identity freeze."""

    schema_version: Literal[1]
    contract_id: Literal["phase-5-external-post-failure-population"]
    status: Literal["scientifically-approved-and-frozen-before-output"]
    scientific_approval: _ScientificApproval
    approved_pre_review: _Artifact
    review_generator: _Artifact
    generator: _Artifact
    closed_campaign_policy: Literal[
        "diagnostic-history-not-pooled-rescored-or-reused"
    ]
    populations: tuple[_Population, _Population]
    population_audit: _PopulationAudit
    power_audit: _EndpointPowerAudit
    source_binding: _SourceBinding
    finder_output_generated: Literal[False]
    finder_output_opened: Literal[False]
    execution_authorized: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]
    next_action: Literal[
        "bind-runners-compiler-evaluator-runtime-and-no-write-preflight"
    ]

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Keep the approved lane/count order canonical."""
        lanes = tuple(
            (item.lane, item.image_count) for item in self.populations
        )
        if lanes != (("continuum", 1600), ("compact-blend", 800)):
            raise ValueError("post-failure population order changed")
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
    """Copy reviewed truth and geometry while replacing every noise seed."""
    record = cast(
        dict[str, object],
        deepcopy(template.model_dump(mode="json")),
    )
    record["identifier"] = identifier
    record["purpose"] = purpose
    record["provenance"] = (
        "The approved post-failure comparison reuses only reviewed geometry, "
        "beam, WCS, truth, endpoints, and gates. Every noise seed is disjoint "
        "from all historical manifests; no finder output, score, or decision "
        "is reused."
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
    """Create 1,600 fresh images over the four reviewed geometries."""
    if len(template.datasets) != len(_CONTINUUM_FIRST_SEEDS):
        raise ValueError("post-failure continuum requires four geometries")
    datasets = tuple(
        _changed_seed_record(
            dataset,
            identifier=(
                f"phase5-external-post-failure-continuum-{index + 1}-1024"
            ),
            purpose=(
                f"Fresh approved post-failure Continuum geometry {index + 1}."
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
        manifest_id="phase-5-external-post-failure-continuum",
        datasets=datasets,
    )


def _compact_manifest(template: DatasetManifest) -> DatasetManifest:
    """Create 800 fresh compact, edge, resolved, and blend images."""
    if len(template.datasets) != 1:
        raise ValueError("post-failure compact requires one geometry")
    dataset = _changed_seed_record(
        template.datasets[0],
        identifier="phase5-external-post-failure-compact-blend-512",
        purpose="Fresh approved post-failure compact/blend comparison.",
        first_seed=_COMPACT_FIRST_SEED,
        realization_count=_COMPACT_REALIZATIONS,
    )
    return DatasetManifest(
        schema_version=template.schema_version,
        manifest_id="phase-5-external-post-failure-compact-blend",
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
    """Prove disjointness from every checked-in historical manifest."""
    historical_seeds: set[int] = set()
    records: list[dict[str, object]] = []
    for path in sorted(dataset_directory.glob("*.json")):
        manifest = DatasetManifest.model_validate_json(path.read_bytes())
        if manifest.manifest_id in _POST_FAILURE_MANIFEST_IDS:
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
        if historical_seeds.intersection(seeds) or new_seeds.intersection(
            seeds
        ):
            raise ValueError("post-failure seeds must be globally disjoint")
        new_seeds.update(seeds)
    if len(new_seeds) != _IMAGE_COUNT:
        raise ValueError("post-failure population must have 2400 seeds")
    return _PopulationAudit(
        historical_manifest_count=len(records),
        historical_seed_count=len(historical_seeds),
        historical_registry_sha256=_canonical_sha256(records),
        new_seed_count=_IMAGE_COUNT,
        seed_disjoint=True,
    )


def _power_audit(review: dict[str, Any]) -> _EndpointPowerAudit:
    """Translate the approved pre-review into a self-validating contract."""
    population = cast(dict[str, Any], review["population"])
    power = cast(dict[str, Any], review["power"])
    variance = cast(dict[str, Any], review["variance_rule"])
    regression = cast(dict[str, Any], review["expected_regression_rule"])
    assumptions = cast(list[dict[str, Any]], review["paired_assumptions"])
    return _EndpointPowerAudit(
        method=review["planning_method"],
        confidence_level=0.95,
        minimum_joint_power=power["minimum_joint_power"],
        variance_inflation=variance["inflation"],
        advantage_retention=(
            regression["retained_fraction_of_favourable_closed_difference"]
        ),
        family_variance_floor_retained=variance["family_floor_retained"],
        paired_assumptions=tuple(
            _PairedPrior.model_validate(item) for item in assumptions
        ),
        minimum_continuum_realization_count=(
            population["minimum_continuum_realization_count"]
        ),
        continuum_realization_count=(
            population["selected_continuum_realization_count"]
        ),
        continuum_geometry_count=population["continuum_geometry_count"],
        continuum_realizations_per_geometry=(
            population["continuum_realizations_per_geometry"]
        ),
        continuum_familywise_power_lower_bound=(
            power["continuum_familywise_power_lower_bound"]
        ),
        compact_realization_count=population["compact_realization_count"],
        compact_familywise_power_lower_bound=(
            power["compact_familywise_power_lower_bound"]
        ),
        combined_familywise_power_lower_bound=(
            power["combined_familywise_power_lower_bound"]
        ),
        assumption_failure=variance["assumption_failure"],
    )


def build_post_failure_documents(
    *,
    repository_root: Path,
    continuum_template_path: Path,
    compact_template_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Build both fresh manifests and their approved governed freeze."""
    pre_review_path = repository_root / _PRE_REVIEW_PATH
    if file_sha256(pre_review_path) != _PRE_REVIEW_SHA256:
        raise ValueError("approved post-failure pre-review identity changed")
    review = cast(
        dict[str, Any],
        json.loads(pre_review_path.read_text(encoding="utf-8")),
    )
    if review.get("review_id") != "phase-5-post-failure-power-pre-review":
        raise ValueError("approved post-failure pre-review is invalid")
    if source_tree_sha256(repository_root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("approved post-failure source tree changed")
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
    measurement_path = repository_root / (
        "src/hebog/validation/observable_truth.py"
    )
    compiler_path = repository_root / (
        "src/hebog/validation/post_failure_truth.py"
    )
    candidate_runner_path = repository_root / (
        "scripts/benchmark/run_phase5_post_failure_hebog.py"
    )
    generator_path = repository_root / (
        "scripts/validation/freeze_phase5_external_post_failure_population.py"
    )
    review_generator_path = repository_root / (
        "scripts/validation/review_phase5_post_failure_power.py"
    )
    freeze = PostFailurePopulationFreeze(
        schema_version=1,
        contract_id="phase-5-external-post-failure-population",
        status="scientifically-approved-and-frozen-before-output",
        scientific_approval=_ScientificApproval(
            reviewer="Gemma Danks",
            approved_on="2026-08-14",
            pre_review_sha256=_PRE_REVIEW_SHA256,
            scope=(
                "implementation-and-freeze-only-separate-execution-"
                "approval-required"
            ),
        ),
        approved_pre_review=_Artifact(
            relative_path=_PRE_REVIEW_PATH,
            sha256=_PRE_REVIEW_SHA256,
        ),
        review_generator=_Artifact(
            relative_path=(
                "scripts/validation/review_phase5_post_failure_power.py"
            ),
            sha256=file_sha256(review_generator_path),
        ),
        generator=_Artifact(
            relative_path=(
                "scripts/validation/"
                "freeze_phase5_external_post_failure_population.py"
            ),
            sha256=file_sha256(generator_path),
        ),
        closed_campaign_policy=(
            "diagnostic-history-not-pooled-rescored-or-reused"
        ),
        populations=(
            _Population(
                lane="continuum",
                manifest=(
                    "config/datasets/"
                    "phase-5-external-post-failure-continuum.json"
                ),
                manifest_sha256=hashlib.sha256(
                    _json_bytes(continuum_document)
                ).hexdigest(),
                image_count=1600,
                role="regression",
                independent_unit="noise-seed-image",
            ),
            _Population(
                lane="compact-blend",
                manifest=(
                    "config/datasets/"
                    "phase-5-external-post-failure-compact-blend.json"
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
        power_audit=_power_audit(review),
        source_binding=_SourceBinding(
            candidate_commit=_CANDIDATE_COMMIT,
            source_tree_sha256=_CANDIDATE_SOURCE_TREE_SHA256,
            observable_measurement=_Artifact(
                relative_path="src/hebog/validation/observable_truth.py",
                sha256=file_sha256(measurement_path),
            ),
            observable_compiler=_Artifact(
                relative_path="src/hebog/validation/post_failure_truth.py",
                sha256=file_sha256(compiler_path),
            ),
            candidate_runner=_Artifact(
                relative_path=(
                    "scripts/benchmark/run_phase5_post_failure_hebog.py"
                ),
                sha256=file_sha256(candidate_runner_path),
            ),
            candidate_runtime_status=(
                "rebuild-bound-source-before-execution-decision"
            ),
        ),
        finder_output_generated=False,
        finder_output_opened=False,
        execution_authorized=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
        next_action=(
            "bind-runners-compiler-evaluator-runtime-and-no-write-preflight"
        ),
    )
    freeze_document = cast(dict[str, object], freeze.model_dump(mode="json"))
    return continuum_document, compact_document, freeze_document


def _parse_args() -> argparse.Namespace:
    """Parse fixed post-failure output paths."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--continuum-output",
        type=Path,
        default=(
            root / "config/datasets/"
            "phase-5-external-post-failure-continuum.json"
        ),
    )
    parser.add_argument(
        "--compact-output",
        type=Path,
        default=(
            root / "config/datasets/"
            "phase-5-external-post-failure-compact-blend.json"
        ),
    )
    parser.add_argument(
        "--freeze-output",
        type=Path,
        default=(
            root / "config/contracts/"
            "phase-5-external-post-failure-population.json"
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
        raise FileExistsError("refusing to overwrite post-failure inputs")
    documents = build_post_failure_documents(
        repository_root=root,
        continuum_template_path=(
            root / "config/datasets/"
            "phase-5-external-confirmation-continuum.json"
        ),
        compact_template_path=(
            root / "config/datasets/"
            "phase-5-external-confirmation-compact-blend.json"
        ),
    )
    for path, document in zip(outputs, documents, strict=True):
        path.write_bytes(_json_bytes(document))


if __name__ == "__main__":
    main()
