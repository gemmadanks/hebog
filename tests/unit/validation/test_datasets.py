"""Tests for versioned validation datasets and synthetic images."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from hebog.validation.datasets import (
    AssociationTruthGroup,
    DatasetManifest,
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
        "phase-4-qualification",
        "phase-4-regression",
        "phase-4-viewed-qualification",
    }
    expected_roles = {
        "phase-4-development": DatasetRole.DEVELOPMENT,
        "phase-4-regression": DatasetRole.REGRESSION,
        "phase-4-qualification": DatasetRole.QUALIFICATION,
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
    assert "unseen" in qualification_dataset.provenance.lower()
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
    viewed_dataset = manifests["phase-4-viewed-qualification"].datasets[0]
    viewed_recipes = iter_dataset_recipes(viewed_dataset)
    assert {recipe.seed for recipe in qualification_recipes}.isdisjoint(
        recipe.seed for recipe in viewed_recipes
    )
    assert viewed_dataset.recipe_sha256 == (
        "4b0104eddb7569bb68058783f836c9e701c0a4362b7d75ce50968b96ca25b3e6"
    )
    assert qualification_dataset.recipe_sha256 == (
        "54657fb15360afbbc2536667aec37e3f4b9b033f756633a82feec57a2a14ca49"
    )
    assert qualification_dataset.recipe.invalid_rectangles
    assert qualification_dataset.recipe.noise_rms_fractional_gradient_xy != (
        0.0,
        0.0,
    )
    assert qualification_dataset.association_truth_groups
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
