"""Portable assertions for regenerated, not checksum-bound, truth fields."""

from copy import deepcopy
from typing import Any

import numpy as np

from hebog.validation.datasets import SyntheticRecipe, recipe_sha256


def _compare_derived_field(
    actual: dict[str, Any],
    expected: dict[str, Any],
    field: str,
) -> None:
    """Bound only an explicitly selected floating-point calculation."""
    try:
        np.testing.assert_array_max_ulp(
            actual[field], expected[field], maxulp=4
        )
    except AssertionError as error:
        raise AssertionError(f"{field}: {error}") from error
    actual[field] = expected[field]


def assert_regenerated_manifest_matches_snapshot(
    generated: dict[str, Any], snapshot: dict[str, Any]
) -> None:
    """Allow four-ULP roundoff in calibration amplitudes and derived truth.

    A Gaussian kernel's last-bit difference changes its calibrated amplitude,
    integrated truth flux, centroid and consequently its recipe digest. Each
    digest must still match its own complete recipe exactly; every prescribed
    recipe field (including seed, geometry and noise) remains exact. This
    test-only comparison never modifies either input or campaign admission.
    Historical file bytes must be checked separately against their bindings.
    """
    comparable = deepcopy(generated)
    for actual, expected in zip(
        comparable["datasets"], snapshot["datasets"], strict=True
    ):
        for dataset in (actual, expected):
            assert dataset["recipe_sha256"] == recipe_sha256(
                SyntheticRecipe.model_validate(dataset["recipe"])
            ), f"{dataset['identifier']}: recipe digest changed"
        for actual_source, expected_source in zip(
            actual["recipe"]["sources"],
            expected["recipe"]["sources"],
            strict=True,
        ):
            _compare_derived_field(
                actual_source, expected_source, "peak_flux_jy_per_beam"
            )
        actual["recipe_sha256"] = expected["recipe_sha256"]
        for field in ("association_truth_groups", "multiscale_truth_groups"):
            for actual_group, expected_group in zip(
                actual[field], expected[field], strict=True
            ):
                for quantity in (
                    "reference_position_xy",
                    "reference_integrated_brightness_jy_pixels_per_beam",
                ):
                    _compare_derived_field(
                        actual_group, expected_group, quantity
                    )
        changed = sorted(
            key
            for key in actual.keys() | expected.keys()
            if actual.get(key) != expected.get(key)
        )
        assert not changed, (
            f"{expected['identifier']}: changed fields {changed}"
        )
    assert comparable == snapshot
