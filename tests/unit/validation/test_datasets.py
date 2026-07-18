"""Tests for versioned validation datasets and synthetic images."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRole,
    SyntheticRecipe,
    SyntheticSource,
    generate_synthetic_image,
    generate_synthetic_window,
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
