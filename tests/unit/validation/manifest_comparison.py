"""Portable assertions for regenerated, not checksum-bound, truth fields."""

from copy import deepcopy
from typing import Any

import numpy as np


def assert_regenerated_manifest_matches_snapshot(
    generated: dict[str, Any], snapshot: dict[str, Any]
) -> None:
    """Allow only four-ULP roundoff in flux-weighted truth positions.

    Recipes, hashes, seeds, fluxes and all other fields stay exact. This
    test-only comparison never modifies either input or campaign admission.
    Historical file bytes must be checked separately against their bindings.
    """
    comparable = deepcopy(generated)
    for actual, expected in zip(
        comparable["datasets"], snapshot["datasets"], strict=True
    ):
        for field in ("association_truth_groups", "multiscale_truth_groups"):
            for actual_group, expected_group in zip(
                actual[field], expected[field], strict=True
            ):
                np.testing.assert_array_max_ulp(
                    actual_group["reference_position_xy"],
                    expected_group["reference_position_xy"],
                    maxulp=4,
                )
                actual_group["reference_position_xy"] = expected_group[
                    "reference_position_xy"
                ]
        assert actual == expected, expected["identifier"]
    assert comparable == snapshot
