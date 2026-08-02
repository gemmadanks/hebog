"""Tests for versioned validation datasets and synthetic images."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRole,
    SyntheticInvalidRectangle,
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
        "phase-4-qualification",
        "phase-4-regression",
    }
    expected_roles = {
        "phase-4-development": DatasetRole.DEVELOPMENT,
        "phase-4-regression": DatasetRole.REGRESSION,
        "phase-4-qualification": DatasetRole.QUALIFICATION,
    }
    for manifest_id, manifest in manifests.items():
        assert {item.role for item in manifest.datasets} == {
            expected_roles[manifest_id]
        }
        assert all(
            item.recipe.generator_version == 2 for item in manifest.datasets
        )

    qualification = manifests["phase-4-qualification"].datasets
    assert len(qualification) == 1
    qualification_dataset = qualification[0]
    qualification_recipes = iter_dataset_recipes(qualification_dataset)
    assert len(qualification_recipes) >= 200
    assert len({recipe.seed for recipe in qualification_recipes}) == len(
        qualification_recipes
    )
    assert "unseen" in qualification_dataset.provenance.lower()
    sample_counts = {
        stratum.identifier: len(stratum.source_indices)
        * len(qualification_recipes)
        for stratum in qualification_dataset.validation_strata
    }
    assert set(sample_counts) == {
        "blend",
        "edge",
        "shape-resolved",
        "shape-unresolved",
        "snr-10",
        "snr-15",
        "snr-25",
        "snr-50",
    }
    assert min(sample_counts.values()) >= 200

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
