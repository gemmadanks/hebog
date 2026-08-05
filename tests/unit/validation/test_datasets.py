"""Tests for versioned validation datasets and synthetic images."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from hebog.validation.campaign_runtime import campaign_dataset_identity
from hebog.validation.datasets import (
    AssociationTruthGroup,
    DatasetManifest,
    DatasetRecord,
    DatasetRole,
    SyntheticInvalidRectangle,
    SyntheticNoiseCorrelation,
    SyntheticRecipe,
    SyntheticSource,
    generate_synthetic_image,
    generate_synthetic_window,
    iter_dataset_recipes,
    load_dataset_manifest,
    recipe_sha256,
)

_DATASET_DIRECTORY = Path(__file__).parents[3] / "config" / "datasets"
MANIFEST_PATH = _DATASET_DIRECTORY / "phase-0-development.json"
_PHASE_FOUR_POWERED_SAMPLE_COUNT = 1_600


def _recipe(
    *,
    seed: int = 42,
    sources: tuple[SyntheticSource, ...] = (),
) -> SyntheticRecipe:
    """Return a small deterministic recipe for analytic tests."""
    return SyntheticRecipe(
        generator="hebog.synthetic.gaussian-noise",
        generator_version=1,
        seed=seed,
        shape_yx=(12, 10),
        background=2.5,
        noise_rms=0.25,
        sources=sources,
    )


def test_checked_in_manifest_is_valid_and_role_complete() -> None:
    """Every checked-in dataset has one explicit, validated test role."""
    manifest = load_dataset_manifest(MANIFEST_PATH)

    assert manifest.schema_version == 1
    assert len(manifest.datasets) == 2
    assert {dataset.role for dataset in manifest.datasets} == {
        DatasetRole.DEVELOPMENT,
    }
    assert len({dataset.identifier for dataset in manifest.datasets}) == len(
        manifest.datasets
    )


def test_phase_zero_freezes_regression_and_qualification_roles() -> None:
    """Algorithm work starts with reviewed lanes and held-out data frozen."""
    manifests = {
        path.stem: load_dataset_manifest(path)
        for path in sorted(_DATASET_DIRECTORY.glob("phase-0-*.json"))
    }

    assert set(manifests) == {
        "phase-0-development",
        "phase-0-qualification",
        "phase-0-regression",
    }
    assert {
        item.role for item in manifests["phase-0-regression"].datasets
    } == {DatasetRole.REGRESSION}
    qualification = manifests["phase-0-qualification"].datasets
    assert {item.role for item in qualification} == {DatasetRole.QUALIFICATION}
    assert qualification[0].recipe.shape_yx == (100_000, 100_000)

    identifiers = [
        dataset.identifier
        for manifest in manifests.values()
        for dataset in manifest.datasets
    ]
    assert len(set(identifiers)) == len(identifiers)


def test_phase_three_adds_immutable_role_specific_supplements() -> None:
    """Detection data extends rather than rewrites the Phase 0 manifests."""
    manifests = {
        path.stem: load_dataset_manifest(path)
        for path in sorted(_DATASET_DIRECTORY.glob("phase-3-*.json"))
    }

    assert set(manifests) == {
        "phase-3-development",
        "phase-3-qualification",
        "phase-3-regression",
    }
    assert {
        item.role for item in manifests["phase-3-development"].datasets
    } == {DatasetRole.DEVELOPMENT}
    assert {
        item.role for item in manifests["phase-3-regression"].datasets
    } == {DatasetRole.REGRESSION}
    qualification = manifests["phase-3-qualification"].datasets
    assert {item.role for item in qualification} == {DatasetRole.QUALIFICATION}
    assert qualification[0].recipe.shape_yx == (2048, 2048)

    phase_zero_identifiers = {
        dataset.identifier
        for path in sorted(_DATASET_DIRECTORY.glob("phase-0-*.json"))
        for dataset in load_dataset_manifest(path).datasets
    }
    phase_three_identifiers = {
        dataset.identifier
        for manifest in manifests.values()
        for dataset in manifest.datasets
    }
    assert phase_zero_identifiers.isdisjoint(phase_three_identifiers)


def test_phase_four_adds_immutable_role_specific_supplements() -> None:
    """Measurement data adds governed truth without rewriting prior phases."""
    manifests = {
        path.stem: load_dataset_manifest(path)
        for path in sorted(_DATASET_DIRECTORY.glob("phase-4-*.json"))
    }

    assert set(manifests) == {
        "phase-4-development",
        "phase-4-final-qualification",
        "phase-4-paired-regression",
        "phase-4-qualification",
        "phase-4-regression",
        "phase-4-viewed-extension-aware-qualification",
        "phase-4-viewed-qualification",
    }
    expected_roles = {
        "phase-4-development": DatasetRole.DEVELOPMENT,
        "phase-4-final-qualification": DatasetRole.QUALIFICATION,
        "phase-4-paired-regression": DatasetRole.REGRESSION,
        "phase-4-regression": DatasetRole.REGRESSION,
        "phase-4-qualification": DatasetRole.QUALIFICATION,
        "phase-4-viewed-extension-aware-qualification": (
            DatasetRole.QUALIFICATION
        ),
        "phase-4-viewed-qualification": DatasetRole.QUALIFICATION,
    }
    for manifest_id, manifest in manifests.items():
        assert {item.role for item in manifest.datasets} == {
            expected_roles[manifest_id]
        }
        assert all(
            item.recipe.generator_version in {2, 3}
            for item in manifest.datasets
        )

    assert {manifest.schema_version for manifest in manifests.values()} == {2}
    qualification = manifests["phase-4-qualification"].datasets
    assert len(qualification) == 1
    qualification_dataset = qualification[0]
    assert qualification_dataset.recipe.generator_version == 3
    assert qualification_dataset.recipe.noise_correlation is not None
    assert (
        qualification_dataset.recipe.noise_correlation.major_fwhm_pixels
        == qualification_dataset.beam.major_fwhm_pixels
    )
    qualification_recipes = iter_dataset_recipes(qualification_dataset)
    assert len(qualification_recipes) >= 200
    assert len({recipe.seed for recipe in qualification_recipes}) == len(
        qualification_recipes
    )
    assert "viewed failed evidence" in qualification_dataset.provenance.lower()
    sample_counts = {
        stratum.identifier: len(stratum.source_indices)
        * len(qualification_recipes)
        for stratum in qualification_dataset.validation_strata
    }
    assert set(sample_counts) == {
        "edge",
        "shape-clear-resolved",
        "shape-marginal-resolved",
        "shape-unresolved",
        "snr-10",
        "snr-15",
        "snr-25",
        "snr-50",
    }
    assert min(sample_counts.values()) >= _PHASE_FOUR_POWERED_SAMPLE_COUNT
    viewed_datasets = (
        manifests["phase-4-viewed-qualification"].datasets[0],
        manifests["phase-4-viewed-extension-aware-qualification"].datasets[0],
    )
    qualification_seeds = {recipe.seed for recipe in qualification_recipes}
    for viewed_dataset in viewed_datasets:
        assert qualification_seeds.isdisjoint(
            recipe.seed for recipe in iter_dataset_recipes(viewed_dataset)
        )
    assert viewed_datasets[0].recipe_sha256 == (
        "4b0104eddb7569bb68058783f836c9e701c0a4362b7d75ce50968b96ca25b3e6"
    )
    assert viewed_datasets[1].recipe_sha256 == (
        "54657fb15360afbbc2536667aec37e3f4b9b033f756633a82feec57a2a14ca49"
    )
    assert qualification_dataset.recipe_sha256 == (
        "7d2bf112051231f4fcad4dd8de40b58e5eeaefe572f315bd9f7e3f365f21087b"
    )
    assert qualification_dataset.recipe.invalid_rectangles
    assert qualification_dataset.recipe.noise_rms_fractional_gradient_xy != (
        0.0,
        0.0,
    )
    assert qualification_dataset.association_truth_groups
    classification: dict[str, set[int]] = {
        stratum.identifier: set(stratum.source_indices)
        for stratum in qualification_dataset.classification_strata
    }
    assert set(classification) == {
        "shape-clear-resolved",
        "shape-marginal-resolved",
        "shape-unresolved",
    }
    assert not any(
        left & right
        for index, left in enumerate(classification.values())
        for right in tuple(classification.values())[index + 1 :]
    )
    assert set().union(*classification.values()) == {
        group.source_indices[0]
        for group in qualification_dataset.association_truth_groups
        if group.resolution_class == "individually-resolvable"
    }
    beam_sigma_product = (
        qualification_dataset.beam.major_fwhm_pixels
        * qualification_dataset.beam.minor_fwhm_pixels
        / (8.0 * np.log(2.0))
    )
    classified_indices: set[int] = set()
    for source_indices in classification.values():
        classified_indices.update(source_indices)
    expected_clear: set[int] = set()
    for source_index in classified_indices:
        source = qualification_dataset.recipe.sources[source_index]
        area_ratio = (
            source.major_sigma_pixels
            * source.minor_sigma_pixels
            / beam_sigma_product
        )
        signal_to_noise = (
            source.peak_flux_jy_per_beam
            / qualification_dataset.recipe.noise_rms
        )
        if area_ratio >= 3.0 and signal_to_noise >= 25.0:
            expected_clear.add(source_index)
    assert classification["shape-clear-resolved"] == expected_clear
    assert {
        group.resolution_class
        for group in qualification_dataset.association_truth_groups
    } == {"individually-resolvable", "unresolved-blend"}
    assert {
        stratum.identifier
        for stratum in qualification_dataset.association_group_strata
    } == {"unresolved-blend"}
    assert (
        min(
            len(stratum.group_identifiers) * len(qualification_recipes)
            for stratum in qualification_dataset.association_group_strata
        )
        >= 200
    )

    earlier_identifiers = {
        dataset.identifier
        for phase in ("phase-0", "phase-3")
        for path in sorted(_DATASET_DIRECTORY.glob(f"{phase}-*.json"))
        for dataset in load_dataset_manifest(path).datasets
    }
    phase_four_identifiers = {
        dataset.identifier
        for manifest in manifests.values()
        for dataset in manifest.datasets
    }
    assert earlier_identifiers.isdisjoint(phase_four_identifiers)


def test_phase_four_paired_regression_is_independent_and_representative() -> (
    None
):
    """Planning evidence has final-like structure but cannot qualify Hebog."""
    paired = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4-paired-regression.json"
    ).datasets[0]
    recipes = iter_dataset_recipes(paired)
    other_seeds = {
        recipe.seed
        for path in sorted(_DATASET_DIRECTORY.glob("phase-4-*.json"))
        if path.name != "phase-4-paired-regression.json"
        for dataset in load_dataset_manifest(path).datasets
        for recipe in iter_dataset_recipes(dataset)
    }

    assert paired.role is DatasetRole.REGRESSION
    assert len(recipes) == 200
    assert not ({recipe.seed for recipe in recipes} & other_seeds)
    assert paired.recipe_sha256 == (
        "2669ad5c7e0883e50b6c82a8d1c66d92a8890df9d8fc7b64a645d6bdf52dedca"
    )
    assert len(paired.recipe.sources) == 34
    assert len(paired.association_truth_groups) == 33
    assert (
        sum(
            group.resolution_class == "unresolved-blend"
            for group in paired.association_truth_groups
        )
        == 1
    )
    classification = {
        stratum.identifier: len(stratum.source_indices)
        for stratum in paired.classification_strata
    }
    assert classification == {
        "shape-clear-resolved": 1,
        "shape-marginal-resolved": 23,
        "shape-unresolved": 8,
    }
    assert "planning" in paired.purpose.lower()
    assert "viewable" in paired.provenance.lower()


def test_phase_four_recovery_matrices_are_frozen_and_disjoint() -> None:
    """Ablation and confirmation evidence predates fitting behavior changes."""
    development = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4r-development.json"
    ).datasets[0]
    regression = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4r-regression.json"
    ).datasets[0]
    earlier_seeds = {
        recipe.seed
        for path in sorted(_DATASET_DIRECTORY.glob("phase-4-*.json"))
        for dataset in load_dataset_manifest(path).datasets
        for recipe in iter_dataset_recipes(dataset)
    }
    development_seeds = {
        recipe.seed for recipe in iter_dataset_recipes(development)
    }
    regression_seeds = {
        recipe.seed for recipe in iter_dataset_recipes(regression)
    }

    assert development.role is DatasetRole.DEVELOPMENT
    assert regression.role is DatasetRole.REGRESSION
    assert len(development_seeds) == 20
    assert len(regression_seeds) == 100
    assert not development_seeds & regression_seeds
    assert not (development_seeds | regression_seeds) & earlier_seeds
    assert development.recipe_sha256 == (
        "3e644ca21006c4e487fbd52c6b04ec05a30f750cf03d86140259e3ac2728642a"
    )
    assert regression.recipe_sha256 == (
        "e75f53e5e6eff5b8199563c5530d0e963089cb90e014a9a5c47b39b2d2881deb"
    )
    assert development.recipe.sources != regression.recipe.sources
    assert development.beam.position_angle_degrees != (
        regression.beam.position_angle_degrees
    )
    assert development.wcs.rotation_degrees_counterclockwise != (
        regression.wcs.rotation_degrees_counterclockwise
    )
    for dataset in (development, regression):
        strata = {item.identifier for item in dataset.validation_strata}
        assert strata == {
            "edge",
            "shape-clear-resolved",
            "shape-marginal-resolved",
            "shape-unresolved",
            "snr-10",
            "snr-15",
            "snr-25",
            "snr-50",
        }
        assert len(dataset.recipe.sources) == 14
        assert len(dataset.association_truth_groups) == 13
        assert (
            sum(
                group.resolution_class == "unresolved-blend"
                for group in dataset.association_truth_groups
            )
            == 1
        )


def test_second_recovery_iteration_is_frozen_before_scientific_changes() -> (
    None
):
    """Recovery iteration two has new viewable and confirmation-only noise."""
    paths = (
        "phase-4r-development.json",
        "phase-4r-regression.json",
        "phase-4r-development-2.json",
        "phase-4r-regression-2.json",
    )
    datasets = tuple(
        load_dataset_manifest(_DATASET_DIRECTORY / path).datasets[0]
        for path in paths
    )
    seed_sets = tuple(
        {recipe.seed for recipe in iter_dataset_recipes(dataset)}
        for dataset in datasets
    )

    assert [len(seeds) for seeds in seed_sets] == [20, 100, 40, 100]
    assert all(
        not left & right
        for index, left in enumerate(seed_sets)
        for right in seed_sets[index + 1 :]
    )
    assert datasets[2].role is DatasetRole.DEVELOPMENT
    assert datasets[3].role is DatasetRole.REGRESSION
    assert "before recovery-iteration production changes" in (
        datasets[2].provenance
    )
    assert "before recovery-iteration production changes" in (
        datasets[3].provenance
    )
    assert datasets[2].recipe_sha256 == (
        "c0e5e60f687a6c591e82b425eae3cd1fee8c697fcca7f023da62ce9ed72562e2"
    )
    assert datasets[3].recipe_sha256 == (
        "fb837bd85cce0968e590ac669307cacd7e1911bc24ebac163ee653c4081036e6"
    )


def test_tail_recovery_development_is_frozen_and_disjoint() -> None:
    """Post-confirmation tail work uses a larger, independently seeded set."""
    paths = (
        "phase-4r-development.json",
        "phase-4r-regression.json",
        "phase-4r-development-2.json",
        "phase-4r-regression-2.json",
        "phase-4r-development-3.json",
    )
    datasets = tuple(
        load_dataset_manifest(_DATASET_DIRECTORY / path).datasets[0]
        for path in paths
    )
    seed_sets = tuple(
        {recipe.seed for recipe in iter_dataset_recipes(dataset)}
        for dataset in datasets
    )

    assert len(seed_sets[-1]) == 200
    assert all(not seed_sets[-1] & earlier for earlier in seed_sets[:-1])
    assert datasets[-1].role is DatasetRole.DEVELOPMENT
    assert "before post-confirmation production changes" in (
        datasets[-1].provenance
    )
    assert datasets[-1].recipe_sha256 == (
        "d34919b359ec865601150faa8455d52ae02632a6d6a72431e1b69172d765d91a"
    )


def test_phase4r_qualification_is_powered_frozen_and_disjoint() -> None:
    """The reviewed one-look population cannot reuse any prior noise seed."""
    manifest_path = _DATASET_DIRECTORY / "phase-4r-qualification.json"
    qualification = load_dataset_manifest(manifest_path).datasets[0]
    qualification_seeds = {
        recipe.seed for recipe in iter_dataset_recipes(qualification)
    }
    prior_seeds = {
        recipe.seed
        for path in sorted(_DATASET_DIRECTORY.glob("phase-4*.json"))
        if path != manifest_path
        for dataset in load_dataset_manifest(path).datasets
        for recipe in iter_dataset_recipes(dataset)
    }

    assert qualification.role is DatasetRole.QUALIFICATION
    assert len(qualification_seeds) == 600
    assert not qualification_seeds & prior_seeds
    assert "after named scientific review" in qualification.provenance
    assert qualification.recipe_sha256 == (
        "82870d14dbe163c1d1ca79d0b163bc69c406ed2288da3cf489ebdb03989de5fc"
    )


def test_edge_retry_recovery_populations_are_frozen_and_disjoint() -> None:
    """Post-qualification recovery has new development and regression seeds."""
    paths = (
        "phase-4r-development.json",
        "phase-4r-regression.json",
        "phase-4r-development-2.json",
        "phase-4r-regression-2.json",
        "phase-4r-development-3.json",
        "phase-4r-qualification.json",
        "phase-4r-development-4.json",
        "phase-4r-regression-3.json",
    )
    datasets = tuple(
        load_dataset_manifest(_DATASET_DIRECTORY / path).datasets[0]
        for path in paths
    )
    seed_sets = tuple(
        {recipe.seed for recipe in iter_dataset_recipes(dataset)}
        for dataset in datasets
    )

    assert all(
        not left & right
        for index, left in enumerate(seed_sets)
        for right in seed_sets[index + 1 :]
    )
    assert [len(seeds) for seeds in seed_sets[-2:]] == [200, 200]
    assert datasets[-2].role is DatasetRole.DEVELOPMENT
    assert datasets[-1].role is DatasetRole.REGRESSION
    assert "before evaluating the bounded edge-retry correction" in (
        datasets[-2].provenance
    )
    assert "before evaluating the bounded edge-retry correction" in (
        datasets[-1].provenance
    )
    assert datasets[-2].recipe_sha256 == (
        "f07f450e266367c50614b9e67caf7131a0c75bb7bd7798c497d9170471f7bead"
    )
    assert datasets[-1].recipe_sha256 == (
        "3879a7a1890ab4791bb6508d904779dbca00051bb4d9012882964875a0e7655c"
    )


def test_phase4r_replacement_qualification_is_frozen_and_disjoint() -> None:
    """The approved replacement has a unique identity and unseen seeds."""
    manifest_path = (
        _DATASET_DIRECTORY / "phase-4r-qualification-replacement.json"
    )
    replacement = load_dataset_manifest(manifest_path).datasets[0]
    replacement_seeds = {
        recipe.seed for recipe in iter_dataset_recipes(replacement)
    }
    prior_seeds = {
        recipe.seed
        for path in sorted(_DATASET_DIRECTORY.glob("phase-4*.json"))
        if path != manifest_path
        for dataset in load_dataset_manifest(path).datasets
        for recipe in iter_dataset_recipes(dataset)
    }

    assert replacement.role is DatasetRole.QUALIFICATION
    assert len(replacement_seeds) == 600
    assert not replacement_seeds & prior_seeds
    assert "after Gemma Danks's named replacement review" in (
        replacement.provenance
    )
    assert replacement.recipe_sha256 == (
        "e104ec6d703bfa876ebdfd1bad3b39c0b0dba341afa6c57fbf32e3605c32d3d0"
    )
    assert campaign_dataset_identity(replacement).content_sha256 == (
        "1e566660eed6a995c55f399a5f1579c70b2ffe34cbb81cd2ad6dc67eaa07dee8"
    )


def test_phase_four_final_qualification_is_frozen_and_unseen() -> None:
    """The final one-look population is powered, disjoint, and unopened."""
    manifest_path = _DATASET_DIRECTORY / "phase-4-final-qualification.json"
    final = load_dataset_manifest(manifest_path).datasets[0]
    recipes = iter_dataset_recipes(final)
    other_seeds = {
        recipe.seed
        for path in sorted(_DATASET_DIRECTORY.glob("phase-4-*.json"))
        if path != manifest_path
        for dataset in load_dataset_manifest(path).datasets
        for recipe in iter_dataset_recipes(dataset)
    }

    assert final.role is DatasetRole.QUALIFICATION
    assert len(recipes) == 600
    assert not ({recipe.seed for recipe in recipes} & other_seeds)
    assert final.recipe_sha256 == (
        "15f8f607463f2db4cf4c0eb72255a998784e2d83d3a0d7ebc45eb733f6fbc7db"
    )
    assert campaign_dataset_identity(final).content_sha256 == (
        "07c736a9bafc79fb298ad1c076fb29b93d88ce9f988f38bba99c94af519d1fcb"
    )
    assert final.recipe.generator_version == 3
    assert final.recipe.noise_correlation is not None
    assert final.recipe.noise_correlation.major_fwhm_pixels == (
        final.beam.major_fwhm_pixels
    )
    assert len(final.recipe.sources) == 34
    assert len(final.association_truth_groups) == 33
    assert (
        sum(
            group.resolution_class == "unresolved-blend"
            for group in final.association_truth_groups
        )
        == 1
    )
    assert "one-look" in final.purpose.lower()
    assert "ungenerated" in final.provenance.lower()
    assert "unopened" in final.provenance.lower()

    classification = {
        stratum.identifier: len(stratum.source_indices)
        for stratum in final.classification_strata
    }
    assert classification == {
        "shape-clear-resolved": 1,
        "shape-marginal-resolved": 23,
        "shape-unresolved": 8,
    }


def test_phase4s_qualification_is_frozen_powered_and_disjoint() -> None:
    """The expert-reviewed compact population is new and fully declared."""
    manifest_path = _DATASET_DIRECTORY / "phase-4s-qualification.json"
    qualification = load_dataset_manifest(manifest_path).datasets[0]
    recipes = iter_dataset_recipes(qualification)
    other_seeds = {
        recipe.seed
        for path in sorted(_DATASET_DIRECTORY.glob("phase-4*.json"))
        if path != manifest_path
        for dataset in load_dataset_manifest(path).datasets
        for recipe in iter_dataset_recipes(dataset)
    }

    assert qualification.role is DatasetRole.QUALIFICATION
    assert len(recipes) == 800
    assert not ({recipe.seed for recipe in recipes} & other_seeds)
    assert qualification.recipe.generator_version == 3
    assert qualification.recipe.shape_yx == (512, 512)
    assert len(qualification.recipe.sources) == 34
    assert len(qualification.association_truth_groups) == 33
    assert len(qualification.recipe.invalid_rectangles) == 1
    assert qualification.recipe.noise_correlation is not None
    assert "ai-conducted expert review" in qualification.provenance.lower()
    assert "real residual" in qualification.provenance.lower()

    classification = {
        stratum.identifier: len(stratum.source_indices)
        for stratum in qualification.classification_strata
    }
    assert classification == {
        "shape-clear-resolved": 8,
        "shape-marginal-resolved": 16,
        "shape-unresolved": 8,
    }
    canonical = {
        stratum.identifier: len(stratum.source_indices)
        for stratum in qualification.canonical_source_strata()
    }
    assert canonical == {
        "edge": 8,
        "shape-clear-resolved": 8,
        "shape-marginal-resolved": 16,
        "shape-unresolved": 8,
        "snr-10": 8,
        "snr-15": 8,
        "snr-25": 8,
        "snr-50": 8,
    }


def test_phase4t_confirmation_is_frozen_and_seed_disjoint() -> None:
    """The corrective confirmation does not reuse any viewed noise seed."""
    manifest_path = _DATASET_DIRECTORY / "phase-4t-qualification.json"
    qualification = load_dataset_manifest(manifest_path).datasets[0]
    recipes = iter_dataset_recipes(qualification)
    other_seeds = {
        recipe.seed
        for path in sorted(_DATASET_DIRECTORY.glob("phase-4*.json"))
        if path != manifest_path
        for dataset in load_dataset_manifest(path).datasets
        for recipe in iter_dataset_recipes(dataset)
    }

    assert qualification.role is DatasetRole.QUALIFICATION
    assert len(recipes) == 800
    assert not ({recipe.seed for recipe in recipes} & other_seeds)
    assert len(qualification.recipe.sources) == 50
    assert len(qualification.association_truth_groups) == 49
    assert "phase 4s failure" in qualification.provenance.lower()
    assert "real residual" in qualification.provenance.lower()

    classifications = {
        stratum.identifier: len(stratum.source_indices)
        for stratum in qualification.classification_strata
    }
    assert classifications == {
        "shape-clear-resolved": 8,
        "shape-marginal-resolved": 8,
        "shape-unresolved": 32,
    }


def test_phase4u_qualification_is_frozen_and_seed_disjoint() -> None:
    """The final compact qualification reuses no viewed or development seed."""
    manifest_path = _DATASET_DIRECTORY / "phase-4u-qualification.json"
    qualification = load_dataset_manifest(manifest_path).datasets[0]
    recipes = iter_dataset_recipes(qualification)
    other_seeds = {
        recipe.seed
        for path in sorted(_DATASET_DIRECTORY.glob("phase-4*.json"))
        if path != manifest_path
        for dataset in load_dataset_manifest(path).datasets
        for recipe in iter_dataset_recipes(dataset)
    }

    assert qualification.role is DatasetRole.QUALIFICATION
    assert len(recipes) == 800
    assert not ({recipe.seed for recipe in recipes} & other_seeds)
    assert not (
        {recipe.seed for recipe in recipes}
        & set(range(2026501001, 2026501019))
    )
    assert len(qualification.recipe.sources) == 60
    assert len(qualification.association_truth_groups) == 54
    blend_groups = tuple(
        group
        for group in qualification.association_truth_groups
        if group.resolution_class == "unresolved-blend"
    )
    assert len(blend_groups) == 6
    assert "phase 4t failure" in qualification.provenance.lower()
    assert "real residual" in qualification.provenance.lower()


def test_paired_regression_preserves_unresolved_blend_geometry() -> None:
    """Rotating final-like populations preserves blend-to-beam geometry."""
    paired = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4-paired-regression.json"
    ).datasets[0]
    viewed = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4-qualification.json"
    ).datasets[0]
    final = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4-final-qualification.json"
    ).datasets[0]

    def beam_projected_separation(dataset: DatasetRecord) -> tuple[float, ...]:
        group = next(
            item
            for item in dataset.association_truth_groups
            if item.resolution_class == "unresolved-blend"
        )
        first, second = (
            dataset.recipe.sources[index] for index in group.source_indices
        )
        difference = np.asarray(
            [second.x_pixel - first.x_pixel, second.y_pixel - first.y_pixel]
        )
        angle = np.deg2rad(dataset.beam.position_angle_degrees)
        major = np.asarray([np.cos(angle), np.sin(angle)])
        minor = np.asarray([-np.sin(angle), np.cos(angle)])
        return tuple(
            sorted(abs(float(difference @ axis)) for axis in (major, minor))
        )

    assert beam_projected_separation(paired) == pytest.approx(
        beam_projected_separation(viewed)
    )
    assert beam_projected_separation(final) == pytest.approx(
        beam_projected_separation(paired)
    )


def test_manifest_rejects_duplicate_dataset_identifiers() -> None:
    """Dataset identifiers remain unambiguous across test lanes."""
    manifest = load_dataset_manifest(MANIFEST_PATH)
    first = manifest.datasets[0]

    with pytest.raises(ValidationError, match="dataset identifiers"):
        DatasetManifest.model_validate(
            {
                **manifest.model_dump(mode="json", exclude={"datasets"}),
                "datasets": [
                    first.model_dump(mode="json"),
                    first.model_dump(mode="json"),
                ],
            }
        )


def test_truth_groups_require_manifest_schema_two() -> None:
    """Legacy manifests cannot silently acquire new association semantics."""
    manifest = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4-regression.json"
    )
    payload = manifest.model_dump(mode="json")
    payload["schema_version"] = 1

    with pytest.raises(ValidationError, match="require manifest schema 2"):
        DatasetManifest.model_validate(payload)


def test_manifest_rejects_a_recipe_checksum_mismatch() -> None:
    """A changed generation recipe cannot retain stale provenance."""
    manifest = load_dataset_manifest(MANIFEST_PATH)
    document = manifest.model_dump(mode="json")
    document["datasets"][0]["recipe_sha256"] = "0" * 64

    with pytest.raises(ValidationError, match="recipe_sha256"):
        DatasetManifest.model_validate(document)


def test_recipe_checksum_is_canonical() -> None:
    """Equivalent validated recipes have the same provenance checksum."""
    recipe = _recipe()
    reloaded = SyntheticRecipe.model_validate(recipe.model_dump(mode="json"))

    assert recipe_sha256(recipe) == recipe_sha256(reloaded)


def test_synthetic_generation_is_repeatable_and_seeded() -> None:
    """A recipe reproduces exactly while a seed change changes the noise."""
    first = generate_synthetic_image(_recipe(seed=17))
    repeated = generate_synthetic_image(_recipe(seed=17))
    different_seed = generate_synthetic_image(_recipe(seed=18))

    np.testing.assert_array_equal(first, repeated)
    assert not np.array_equal(first, different_seed)


def test_synthetic_windows_are_partition_invariant() -> None:
    """Stitched windows reproduce a one-window plane exactly."""
    recipe = _recipe(
        sources=(
            SyntheticSource(
                x_pixel=4.5,
                y_pixel=6.0,
                peak_flux_jy_per_beam=3.0,
                major_sigma_pixels=1.5,
                minor_sigma_pixels=0.75,
                rotation_degrees_counterclockwise_from_x=25.0,
            ),
        )
    )
    whole = generate_synthetic_image(recipe)
    top_left = generate_synthetic_window(
        recipe,
        y_start=0,
        y_stop=5,
        x_start=0,
        x_stop=4,
    )
    top_right = generate_synthetic_window(
        recipe,
        y_start=0,
        y_stop=5,
        x_start=4,
        x_stop=10,
    )
    bottom_left = generate_synthetic_window(
        recipe,
        y_start=5,
        y_stop=12,
        x_start=0,
        x_stop=4,
    )
    bottom_right = generate_synthetic_window(
        recipe,
        y_start=5,
        y_stop=12,
        x_start=4,
        x_stop=10,
    )
    stitched = np.block([[top_left, top_right], [bottom_left, bottom_right]])

    np.testing.assert_array_equal(stitched, whole)


def test_version_two_generation_adds_partition_invariant_noise_and_masks() -> (
    None
):
    """Varying RMS and invalid rectangles retain exact window semantics."""
    recipe = SyntheticRecipe(
        generator="hebog.synthetic.gaussian-noise",
        generator_version=2,
        seed=2026080201,
        shape_yx=(12, 10),
        background=-0.5,
        noise_rms=0.25,
        noise_rms_fractional_gradient_xy=(0.4, -0.2),
        invalid_rectangles=(
            SyntheticInvalidRectangle(
                y_start=3,
                y_stop=6,
                x_start=4,
                x_stop=7,
            ),
        ),
    )

    whole = generate_synthetic_image(recipe)
    left = generate_synthetic_window(
        recipe,
        y_start=0,
        y_stop=12,
        x_start=0,
        x_stop=5,
    )
    right = generate_synthetic_window(
        recipe,
        y_start=0,
        y_stop=12,
        x_start=5,
        x_stop=10,
    )

    np.testing.assert_array_equal(
        np.isnan(np.column_stack((left, right))),
        np.isnan(whole),
    )
    np.testing.assert_array_equal(
        np.nan_to_num(np.column_stack((left, right))),
        np.nan_to_num(whole),
    )
    assert np.count_nonzero(~np.isfinite(whole)) == 9
    assert np.nanstd(whole[:, -2:]) > np.nanstd(whole[:, :2])
    unaffected = generate_synthetic_window(
        recipe,
        y_start=0,
        y_stop=2,
        x_start=0,
        x_stop=2,
    )
    assert np.all(np.isfinite(unaffected))


def test_version_three_generates_partition_invariant_correlated_noise() -> (
    None
):
    """Beam-correlated noise is normalized and independent of window layout."""
    recipe = SyntheticRecipe(
        generator="hebog.synthetic.gaussian-noise",
        generator_version=3,
        seed=2026080301,
        shape_yx=(512, 512),
        background=0.0,
        noise_rms=1.0,
        noise_correlation=SyntheticNoiseCorrelation(
            major_fwhm_pixels=4.0,
            minor_fwhm_pixels=2.0,
            position_angle_degrees=0.0,
        ),
    )

    whole = generate_synthetic_image(recipe)
    quarters = np.block(
        [
            [
                generate_synthetic_window(
                    recipe,
                    y_start=y_start,
                    y_stop=y_stop,
                    x_start=x_start,
                    x_stop=x_stop,
                )
                for x_start, x_stop in ((0, 173), (173, 512))
            ]
            for y_start, y_stop in ((0, 211), (211, 512))
        ]
    )

    np.testing.assert_array_equal(quarters, whole)
    assert np.std(whole) == pytest.approx(1.0, abs=0.03)
    measured_x_lag_one = float(
        np.mean(whole[:, :-1] * whole[:, 1:]) / np.var(whole)
    )
    major_sigma = 4.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    expected_x_lag_one = np.exp(-0.5 / np.square(major_sigma))
    assert measured_x_lag_one == pytest.approx(expected_x_lag_one, abs=0.03)


@pytest.mark.parametrize(
    ("version", "correlation", "message"),
    [
        (3, None, "version 3 requires"),
        (
            2,
            SyntheticNoiseCorrelation(
                major_fwhm_pixels=4.0,
                minor_fwhm_pixels=2.0,
                position_angle_degrees=0.0,
            ),
            "only in generator version 3",
        ),
    ],
)
def test_correlated_noise_requires_generator_version_three(
    version: int,
    correlation: SyntheticNoiseCorrelation | None,
    message: str,
) -> None:
    """A recipe version unambiguously determines its noise semantics."""
    payload = _recipe().model_dump(mode="python")
    payload.update(
        {
            "generator_version": version,
            "noise_correlation": correlation,
        }
    )

    with pytest.raises(ValidationError, match=message):
        SyntheticRecipe.model_validate(payload)


def test_invalid_rectangle_requires_increasing_bounds() -> None:
    """An empty half-open invalid region is rejected at its boundary."""
    with pytest.raises(ValidationError, match="bounds must be increasing"):
        SyntheticInvalidRectangle(
            y_start=3,
            y_stop=3,
            x_start=1,
            x_stop=2,
        )


def test_version_one_recipe_checksum_remains_stable() -> None:
    """Adding generator v2 does not rewrite frozen earlier provenance."""
    manifest = load_dataset_manifest(MANIFEST_PATH)

    assert recipe_sha256(manifest.datasets[0].recipe) == (
        manifest.datasets[0].recipe_sha256
    )


def test_dataset_realization_seeds_expand_without_changing_base_truth() -> (
    None
):
    """A governed campaign varies only noise seed across exact truth."""
    dataset = load_dataset_manifest(MANIFEST_PATH).datasets[0]
    expanded_dataset = dataset.model_copy(
        update={"noise_realization_seeds": (101, 102)}
    )

    recipes = tuple(iter_dataset_recipes(expanded_dataset))

    assert [recipe.seed for recipe in recipes] == [
        dataset.recipe.seed,
        101,
        102,
    ]
    assert all(
        recipe.model_dump(exclude={"seed"})
        == dataset.recipe.model_dump(exclude={"seed"})
        for recipe in recipes
    )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {
                "generator_version": 1,
                "noise_rms_fractional_gradient_xy": (0.1, 0.0),
            },
            "version 1",
        ),
        (
            {"noise_rms_fractional_gradient_xy": (np.inf, 0.0)},
            "gradient must be finite",
        ),
        (
            {"noise_rms_fractional_gradient_xy": (1.5, 0.6)},
            "must remain positive",
        ),
        (
            {
                "invalid_rectangles": (
                    SyntheticInvalidRectangle(
                        y_start=10,
                        y_stop=13,
                        x_start=0,
                        x_stop=2,
                    ),
                )
            },
            "inside shape_yx",
        ),
        (
            {
                "invalid_rectangles": (
                    SyntheticInvalidRectangle(
                        y_start=1,
                        y_stop=4,
                        x_start=1,
                        x_stop=4,
                    ),
                    SyntheticInvalidRectangle(
                        y_start=3,
                        y_stop=5,
                        x_start=3,
                        x_stop=5,
                    ),
                )
            },
            "must not overlap",
        ),
    ],
)
def test_version_two_recipe_rejects_invalid_variation(
    updates: dict[str, object],
    message: str,
) -> None:
    """Varying noise and invalid pixels cannot violate recipe geometry."""
    payload = _recipe().model_dump(mode="python")
    payload.update({"generator_version": 2, **updates})

    with pytest.raises(ValidationError, match=message):
        SyntheticRecipe.model_validate(payload)


@pytest.mark.parametrize(
    ("seeds", "message"),
    [
        ((101, 101), "must be unique"),
        ((0,), "must not repeat"),
        ((2**64,), "must fit uint64"),
    ],
)
def test_dataset_rejects_invalid_noise_realization_seeds(
    seeds: tuple[int, ...],
    message: str,
) -> None:
    """A governed noise campaign has distinct uint64 seeds."""
    dataset = load_dataset_manifest(MANIFEST_PATH).datasets[0]
    payload = dataset.model_dump(mode="json")
    payload["noise_realization_seeds"] = seeds

    with pytest.raises(ValidationError, match=message):
        type(dataset).model_validate(payload)


def test_version_one_dataset_rejects_rotated_wcs() -> None:
    """Legacy generator semantics stay byte-compatible and unrotated."""
    dataset = load_dataset_manifest(MANIFEST_PATH).datasets[0]
    payload = dataset.model_dump(mode="json")
    payload["wcs"]["rotation_degrees_counterclockwise"] = 15.0

    with pytest.raises(ValidationError, match="cannot use rotated WCS"):
        type(dataset).model_validate(payload)


@pytest.mark.parametrize(
    ("strata", "message"),
    [
        (
            [{"identifier": "negative", "source_indices": [-1]}],
            "must be non-negative",
        ),
        (
            [{"identifier": "duplicate", "source_indices": [0, 0]}],
            "must be unique and sorted",
        ),
        (
            [{"identifier": "outside", "source_indices": [99]}],
            "must identify recipe truth",
        ),
        (
            [
                {"identifier": "same", "source_indices": [0]},
                {"identifier": "same", "source_indices": [1]},
            ],
            "identifiers must be unique",
        ),
    ],
)
def test_dataset_rejects_invalid_source_validation_strata(
    strata: list[dict[str, object]],
    message: str,
) -> None:
    """Declared scientific strata remain valid and unambiguous."""
    dataset = load_dataset_manifest(MANIFEST_PATH).datasets[1]
    payload = dataset.model_dump(mode="json")
    payload["validation_strata"] = strata

    with pytest.raises(ValidationError, match=message):
        type(dataset).model_validate(payload)


def test_dataset_rejects_overlapping_classification_strata() -> None:
    """One truth source cannot have two extension classifications."""
    dataset = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4-regression.json"
    ).datasets[0]
    payload = dataset.model_dump(mode="json")
    payload["classification_strata"] = [
        {"identifier": "shape-unresolved", "source_indices": [0]},
        {"identifier": "shape-clear-resolved", "source_indices": [0]},
    ]

    with pytest.raises(ValidationError, match="must not overlap"):
        type(dataset).model_validate(payload)


def test_canonical_source_strata_prefer_governed_classification() -> None:
    """A classification cannot be widened by an older validation stratum."""
    dataset = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4r-qualification-replacement.json"
    ).datasets[0]

    strata = {
        item.identifier: item.source_indices
        for item in dataset.canonical_source_strata()
    }

    assert strata["shape-clear-resolved"] == (8, 11)
    assert strata["shape-marginal-resolved"] == (1, 2, 4, 5, 7, 10)
    assert strata["shape-unresolved"] == (0, 3, 6, 9)
    assert strata["edge"] == (1, 2, 3, 5, 6, 10, 11)
    assert strata["snr-10"] == (0, 1, 2)


def test_association_truth_group_freezes_derived_group_quantities() -> None:
    """Explicit group truth is bound to its analytic emitter membership."""
    dataset = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4-regression.json"
    ).datasets[1]
    group = dataset.association_truth_groups[0]

    assert group.identifier == "blend-00001"
    assert group.source_indices == (0, 1)
    assert group.resolution_class == "unresolved-blend"
    assert group.reference_position_xy == pytest.approx(
        (127.85714285714285, 128.28571428571428)
    )
    assert group.reference_integrated_brightness_jy_pixels_per_beam == (
        pytest.approx(0.09993854112450593)
    )


@pytest.mark.parametrize(
    ("update", "message"),
    [
        (
            {"source_indices": [-1, 0]},
            "source indices must be non-negative",
        ),
        (
            {"source_indices": [0]},
            "unresolved blend must contain at least two sources",
        ),
        (
            {"source_indices": [1, 0]},
            "source indices must be unique and sorted",
        ),
        (
            {"reference_position_xy": [0.0, 0.0]},
            "reference position does not match",
        ),
        (
            {"reference_position_xy": [float("inf"), 0.0]},
            "reference position must be finite",
        ),
        (
            {"reference_integrated_brightness_jy_pixels_per_beam": 1.0},
            "reference integrated brightness does not match",
        ),
    ],
)
def test_dataset_rejects_inconsistent_association_truth(
    update: dict[str, object],
    message: str,
) -> None:
    """Truth groups cannot drift from their governed analytic emitters."""
    dataset = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4-regression.json"
    ).datasets[1]
    payload = dataset.model_dump(mode="json")
    payload["association_truth_groups"][0].update(update)

    with pytest.raises(ValidationError, match=message):
        type(dataset).model_validate(payload)


def test_dataset_rejects_overlapping_or_incomplete_truth_groups() -> None:
    """Every emitter belongs to exactly one explicit association group."""
    dataset = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4-regression.json"
    ).datasets[1]
    payload = dataset.model_dump(mode="json")
    duplicate = payload["association_truth_groups"][0].copy()
    duplicate["identifier"] = "overlap"
    payload["association_truth_groups"].append(duplicate)

    with pytest.raises(ValidationError, match="partition recipe sources"):
        type(dataset).model_validate(payload)


def _remove_truth_but_keep_stratum(payload: dict[str, Any]) -> None:
    payload["association_group_strata"] = [
        {
            "identifier": "missing",
            "group_identifiers": ["blend-00001"],
        }
    ]
    payload["association_truth_groups"] = []


def _duplicate_truth_group_identifier(payload: dict[str, Any]) -> None:
    duplicate = {
        **payload["association_truth_groups"][0],
        "source_indices": [2, 3],
    }
    payload["association_truth_groups"].append(duplicate)


def _duplicate_group_stratum_identifier(payload: dict[str, Any]) -> None:
    payload["association_group_strata"].append(
        payload["association_group_strata"][0]
    )


def _use_unknown_group_identifier(payload: dict[str, Any]) -> None:
    payload["association_group_strata"][0]["group_identifiers"] = [
        "unknown-group"
    ]


def _use_noncanonical_group_identifiers(payload: dict[str, Any]) -> None:
    payload["association_group_strata"][0]["group_identifiers"] = [
        "blend-00002",
        "blend-00001",
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            _remove_truth_but_keep_stratum,
            "require association truth groups",
        ),
        (
            _duplicate_truth_group_identifier,
            "identifiers must be unique",
        ),
        (
            _duplicate_group_stratum_identifier,
            "stratum identifiers must be unique",
        ),
        (
            _use_unknown_group_identifier,
            "must identify governed truth",
        ),
        (
            _use_noncanonical_group_identifiers,
            "group identifiers must be unique and sorted",
        ),
    ],
)
def test_dataset_rejects_invalid_association_group_governance(
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    """Group identifiers and strata remain complete and unambiguous."""
    dataset = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4-regression.json"
    ).datasets[1]
    payload = dataset.model_dump(mode="json")
    mutation(payload)

    with pytest.raises(ValidationError, match=message):
        type(dataset).model_validate(payload)


def test_association_group_record_rejects_invalid_resolution_cardinality() -> (
    None
):
    """Resolvable emitters use singleton groups, not ambiguous containers."""
    with pytest.raises(ValidationError, match="individually resolvable"):
        AssociationTruthGroup(
            identifier="invalid-group",
            source_indices=(0, 1),
            resolution_class="individually-resolvable",
            reference_position_xy=(1.0, 1.0),
            reference_integrated_brightness_jy_pixels_per_beam=1.0,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("background_jy_per_beam", 99.0, "expected statistics"),
        ("finite_fraction", 0.5, "finite fraction"),
    ],
)
def test_dataset_rejects_inconsistent_version_two_statistics(
    field: str,
    value: float,
    message: str,
) -> None:
    """Manifest statistics must describe the exact governed recipe."""
    dataset = load_dataset_manifest(
        _DATASET_DIRECTORY / "phase-4-development.json"
    ).datasets[1]
    payload = dataset.model_dump(mode="json")
    payload["expected_statistics"][field] = value

    with pytest.raises(ValidationError, match=message):
        type(dataset).model_validate(payload)


def test_complete_generation_rejects_an_unbounded_allocation() -> None:
    """Large recipes require bounded windows unless explicitly authorized."""
    recipe = _recipe().model_copy(update={"shape_yx": (100_000, 100_000)})

    with pytest.raises(ValueError, match="generate_synthetic_window"):
        generate_synthetic_image(recipe)


def test_noiseless_source_has_analytic_peak() -> None:
    """An integer-centred Gaussian has its declared peak above background."""
    source = SyntheticSource(
        x_pixel=4.0,
        y_pixel=6.0,
        peak_flux_jy_per_beam=3.0,
        major_sigma_pixels=1.5,
        minor_sigma_pixels=1.0,
        rotation_degrees_counterclockwise_from_x=0.0,
    )
    recipe = _recipe(sources=(source,)).model_copy(update={"noise_rms": 0.0})

    image = generate_synthetic_image(recipe)

    assert image[6, 4] == pytest.approx(5.5)


def test_recipe_rejects_a_source_outside_the_image() -> None:
    """Synthetic truth cannot silently describe an absent source centre."""
    source = SyntheticSource(
        x_pixel=10.0,
        y_pixel=2.0,
        peak_flux_jy_per_beam=1.0,
        major_sigma_pixels=1.0,
        minor_sigma_pixels=1.0,
    )

    with pytest.raises(ValidationError, match="source centre"):
        _recipe(sources=(source,))


@pytest.mark.parametrize(
    ("bounds", "message"),
    [
        ((-1, 2, 0, 2), "window bounds"),
        ((0, 13, 0, 2), "window bounds"),
        ((3, 3, 0, 2), "non-empty"),
    ],
)
def test_generator_rejects_invalid_windows(
    bounds: tuple[int, int, int, int],
    message: str,
) -> None:
    """Window generation fails before indexing outside the declared plane."""
    y_start, y_stop, x_start, x_stop = bounds

    with pytest.raises(ValueError, match=message):
        generate_synthetic_window(
            _recipe(),
            y_start=y_start,
            y_stop=y_stop,
            x_start=x_start,
            x_stop=x_stop,
        )
